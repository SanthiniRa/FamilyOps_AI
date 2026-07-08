from pathlib import Path
import csv
import re
from typing import List, Dict, Any
from datetime import datetime

from sqlalchemy import select

from app.core.config import settings
from app.db.database import AsyncSessionLocal
from app.db.models import GroceryItem, GroceryList, UploadedDocument
from app.services.rag_service import rag_service
from app.services.rag_retrieval import split_semantic_chunks
from app.core.logging import logger

try:
    from pdfminer.high_level import extract_text
except ImportError:
    extract_text = None

try:
    from docx import Document as DocxDocument
except ImportError:
    DocxDocument = None

try:
    from PIL import Image
    import pytesseract
except ImportError:
    Image = None
    pytesseract = None

try:
    from pdf2image import convert_from_path
except ImportError:
    convert_from_path = None


async def ingest_document(uploaded_doc_id: str):
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(UploadedDocument).where(
                UploadedDocument.id == uploaded_doc_id
            )
        )
        doc = result.scalar_one_or_none()

        if not doc:
            logger.error("ingest.document.not_found", id=uploaded_doc_id)
            return

        storage_path = doc.storage_path
        filename = doc.filename

    path = Path(storage_path)

    if not path.exists():
        logger.error("ingest.document.missing_file", path=storage_path)
        return

    ext = path.suffix.lower()
    pages = []

    try:
        if ext == ".pdf":
            pages = await _extract_text_from_pdf(path)
        elif ext == ".docx":
            pages = await _extract_text_from_docx(path)
        elif ext in (".txt", ".md"):
            pages = await _extract_text_from_txt(path)
        elif ext == ".csv":
            pages = await _extract_text_from_csv(path)
        elif ext in (".png", ".jpg", ".jpeg", ".tiff"):
            pages = await _extract_text_via_ocr(path)
        else:
            pages = await _extract_text_from_pdf(path)
    except Exception as e:
        logger.exception("ingest.extract_failed", error=str(e))
        return

    stored_ids = []

    for p in pages:
        text = p.get("text", "").strip()
        if not text:
            continue

        chunks = _chunk_text(text)

        for idx, chunk in enumerate(chunks):
            metadata = _build_chunk_metadata(
                document=doc,
                page=p.get("page", 1),
                chunk_index=idx,
            )

            try:
                mem_id = await rag_service.store_memory(
                    content=chunk,
                    memory_type="document",
                    metadata=metadata
                )
                if mem_id:
                    stored_ids.append(mem_id)
            except Exception as e:
                logger.exception("ingest.store_failed", error=str(e))

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(UploadedDocument).where(
                UploadedDocument.id == uploaded_doc_id
            )
        )
        doc = result.scalar_one_or_none()

        if doc:
            grocery_import = {
                "created": False,
                "skipped": True,
                "reason": "not_attempted",
            }
            try:
                grocery_import = await _maybe_import_grocery_list_from_document(
                    db=db,
                    document=doc,
                    pages=pages,
                )
            except Exception as e:
                logger.exception("ingest.grocery_import_failed", error=str(e))

            doc.ingested = True
            doc.extra_metadata = {
                **(doc.extra_metadata or {}),
                "stored_chunks": stored_ids,
                "stored_count": len(stored_ids),
                "parsed_at": datetime.utcnow().isoformat() + "Z",
                "pages": len(pages),
                "content_type": doc.content_type,
                "source": doc.source,
                "grocery_import": grocery_import,
            }
            await db.commit()

    logger.info(
        "ingest.completed",
        document_id=uploaded_doc_id,
        stored_chunks=len(stored_ids)
    )


async def _maybe_import_grocery_list_from_document(
    db,
    document: UploadedDocument,
    pages: List[Dict[str, Any]],
) -> Dict[str, Any]:
    metadata = document.extra_metadata or {}
    existing_import = metadata.get("grocery_import")
    if isinstance(existing_import, dict) and existing_import.get("created"):
        return existing_import

    raw_text = "\n".join((page.get("text") or "") for page in pages or [])
    parsed_items = _extract_grocery_items(raw_text)

    if len(parsed_items) < 2:
        return {
            "created": False,
            "skipped": True,
            "reason": "not_enough_candidates",
            "candidate_count": len(parsed_items),
        }

    unique_items: List[Dict[str, Any]] = []
    seen_names: set[str] = set()
    for item in parsed_items:
        normalized_name = _normalize_item_name(item["name"])
        if not normalized_name or normalized_name in seen_names:
            continue
        seen_names.add(normalized_name)
        unique_items.append(item)

    if len(unique_items) < 2:
        return {
            "created": False,
            "skipped": True,
            "reason": "not_enough_unique_items",
            "candidate_count": len(parsed_items),
            "added_count": len(unique_items),
        }

    list_name = _build_grocery_list_name(document)
    grocery_list = GroceryList(
        name=list_name,
        status="active",
        scheduled_date=datetime.utcnow(),
    )
    db.add(grocery_list)
    await db.flush()

    added_items: List[Dict[str, Any]] = []

    for item in unique_items:
        db.add(
            GroceryItem(
                list_id=grocery_list.id,
                name=item["name"],
                category=item.get("category"),
                quantity=item.get("quantity", 1),
                unit=item.get("unit"),
                notes=item.get("notes"),
                added_by="memory_import",
            )
        )
        added_items.append(item)

    return {
        "created": True,
        "skipped": False,
        "list_id": grocery_list.id,
        "list_name": grocery_list.name,
        "added_count": len(added_items),
        "items": added_items,
    }


async def _extract_text_from_pdf(path: Path) -> List[Dict[str, Any]]:
    if extract_text is None:
        raise RuntimeError("pdfminer.six is not installed")

    try:
        text = extract_text(str(path)) or ""
        page_results = [{"page": 1, "text": text}]

        if not text.strip():
            page_results = await _extract_text_from_pdf_with_ocr(path)

        return page_results
    except Exception as e:
        logger.exception("ingest.pdf_parse_failed", error=str(e), path=str(path))
        return [{"page": 1, "text": ""}]


async def _extract_text_from_pdf_with_ocr(path: Path) -> List[Dict[str, Any]]:
    if Image is None or pytesseract is None:
        raise RuntimeError("Pillow and pytesseract are required for PDF OCR fallback")

    page_texts: List[Dict[str, Any]] = []

    try:
        if convert_from_path:
            images = convert_from_path(str(path), fmt="png")
            for idx, image in enumerate(images, start=1):
                text = pytesseract.image_to_string(image) or ""
                page_texts.append({"page": idx, "text": text})
            return page_texts or [{"page": 1, "text": ""}]

        with Image.open(path) as pdf_image:
            page_index = 1
            while True:
                pdf_image.seek(page_index - 1)
                text = pytesseract.image_to_string(pdf_image) or ""
                page_texts.append({"page": page_index, "text": text})
                page_index += 1
    except EOFError:
        pass
    except Exception as e:
        logger.exception("ingest.pdf_ocr_failed", error=str(e), path=str(path))

    return page_texts or [{"page": 1, "text": ""}]


async def _extract_text_from_docx(path: Path) -> List[Dict[str, Any]]:
    if DocxDocument is None:
        raise RuntimeError("python-docx is not installed")

    try:
        doc = DocxDocument(str(path))
        paragraphs = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
        return [{"page": 1, "text": "\n".join(paragraphs)}]
    except Exception as e:
        logger.exception("ingest.docx_parse_failed", error=str(e), path=str(path))
        return [{"page": 1, "text": ""}]


async def _extract_text_from_txt(path: Path) -> List[Dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
        return [{"page": 1, "text": text}]
    except Exception as e:
        logger.exception("ingest.txt_parse_failed", error=str(e), path=str(path))
        return [{"page": 1, "text": ""}]


async def _extract_text_from_csv(path: Path) -> List[Dict[str, Any]]:
    try:
        rows: List[Dict[str, Any]] = []
        with path.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
            reader = csv.reader(handle)
            for row_index, row in enumerate(reader):
                cleaned = [cell.strip() for cell in row if cell and cell.strip()]
                if not cleaned:
                    continue
                lowered = [cell.lower() for cell in cleaned]
                if row_index == 0 and _looks_like_csv_header(lowered):
                    continue
                rows.append({"page": 1, "text": " | ".join(cleaned)})
        return rows or [{"page": 1, "text": ""}]
    except Exception as e:
        logger.exception("ingest.csv_parse_failed", error=str(e), path=str(path))
        return [{"page": 1, "text": ""}]


async def _extract_text_via_ocr(path: Path) -> List[Dict[str, Any]]:
    if Image is None or pytesseract is None:
        raise RuntimeError("Pillow and pytesseract are required for OCR")

    try:
        with Image.open(path) as image:
            text = pytesseract.image_to_string(image) or ""
        return [{"page": 1, "text": text}]
    except Exception as e:
        logger.exception("ingest.ocr_failed", error=str(e), path=str(path))
        return [{"page": 1, "text": ""}]


async def extract_text_from_image(path: Path) -> List[Dict[str, Any]]:
    """Public wrapper for OCR on a single image file."""
    return await _extract_text_via_ocr(path)


def _build_chunk_metadata(document: UploadedDocument, page: int, chunk_index: int) -> Dict[str, Any]:
    citation = f"{document.filename or document.id}"
    if page is not None:
        citation += f"#page={page}"
    citation += f"#chunk={chunk_index}"

    return {
        "origin": "uploaded_document",
        "document_id": document.id,
        "filename": document.filename,
        "content_type": document.content_type,
        "source": document.source or "upload",
        "page": page,
        "chunk_index": chunk_index,
        "citation": citation,
    }


def _chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    # Preserve semantic boundaries first, then fall back to bounded word chunks.
    return split_semantic_chunks(
        text,
        max_words=min(chunk_size, settings.rag_document_chunk_words),
        overlap=min(overlap, settings.rag_document_chunk_overlap),
    )


def _normalize_item_name(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def _build_grocery_list_name(document: UploadedDocument) -> str:
    base_name = (document.filename or "uploaded document").strip()
    base_name = re.sub(r"\.[a-z0-9]{1,6}$", "", base_name, flags=re.IGNORECASE)
    if len(base_name) > 60:
        base_name = base_name[:57].rstrip() + "..."
    return f"Memory Grocery - {base_name}"


def _extract_grocery_items(text: str) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for raw_line in re.split(r"[\r\n]+", text or ""):
        for segment in _split_document_segment(raw_line):
            parsed = _parse_grocery_line(segment)
            if not parsed:
                continue
            normalized_name = _normalize_item_name(parsed["name"])
            if not normalized_name or normalized_name in seen:
                continue
            seen.add(normalized_name)
            candidates.append(parsed)

    return candidates


def _split_document_segment(line: str) -> List[str]:
    cleaned = _clean_document_line(line)
    if not cleaned:
        return []

    if ";" in cleaned:
        parts = [part.strip() for part in cleaned.split(";") if part.strip()]
        if len(parts) > 1:
            return parts

    return [cleaned]


def _clean_document_line(line: str) -> str:
    cleaned = re.sub(r"^\s*(?:[-*•●▪▫]|[\d]+[.)]|[a-zA-Z][.)])\s*", "", (line or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _parse_grocery_line(line: str) -> Dict[str, Any] | None:
    if not line:
        return None

    lowered = line.strip().lower()
    if lowered in {
        "grocery list",
        "shopping list",
        "weekly groceries",
        "weekly grocery list",
        "meal plan",
        "diet plan",
        "ingredients",
        "notes",
        "pantry",
        "house memory",
    }:
        return None

    candidate = line
    if ":" in candidate:
        left, right = candidate.split(":", 1)
        if left.strip().lower() in {
            "breakfast",
            "lunch",
            "dinner",
            "snacks",
            "shopping",
            "groceries",
            "ingredients",
            "weekly groceries",
            "diet",
            "meal plan",
        } and right.strip():
            candidate = right.strip()

    parsed = _parse_structured_grocery_line(candidate)
    if parsed:
        return parsed

    words = candidate.split()
    if len(words) > 8:
        return None
    if any(char.isdigit() for char in candidate):
        return None

    name = candidate.strip(" -:;,.")
    if not name:
        return None

    return {
        "name": _format_item_name(name),
        "quantity": 1,
        "unit": None,
        "category": _infer_grocery_category(name),
        "notes": candidate.strip(),
    }


def _parse_structured_grocery_line(line: str) -> Dict[str, Any] | None:
    if not line:
        return None

    if "|" in line:
        parts = [part.strip() for part in line.split("|") if part.strip()]
        if len(parts) >= 2:
            quantity = _parse_quantity(parts[1])
            if quantity is not None:
                return {
                    "name": _format_item_name(parts[0]),
                    "quantity": quantity,
                    "unit": parts[2].strip() if len(parts) >= 3 and parts[2].strip() else None,
                    "category": parts[3].strip() if len(parts) >= 4 and parts[3].strip() else _infer_grocery_category(parts[0]),
                    "notes": line.strip(),
                }

    if "," in line and re.search(r"\d", line):
        parts = [part.strip() for part in line.split(",") if part.strip()]
        if len(parts) >= 2:
            quantity = _parse_quantity(parts[1])
            if quantity is not None:
                return {
                    "name": _format_item_name(parts[0]),
                    "quantity": quantity,
                    "unit": parts[2].strip() if len(parts) >= 3 and parts[2].strip() else None,
                    "category": parts[3].strip() if len(parts) >= 4 and parts[3].strip() else _infer_grocery_category(parts[0]),
                    "notes": line.strip(),
                }

    patterns = [
        re.compile(r"^(?P<name>.+?)\s*[x×]\s*(?P<quantity>\d+(?:[.,]\d+)?)(?:\s*(?P<unit>[A-Za-z][A-Za-z0-9/%.-]*))?(?:\s*-\s*(?P<category>.+))?$"),
        re.compile(r"^(?P<name>.+?)\s+(?P<quantity>\d+(?:[.,]\d+)?)(?:\s*(?P<unit>[A-Za-z][A-Za-z0-9/%.-]*))?(?:\s*-\s*(?P<category>.+))?$"),
        re.compile(r"^(?P<quantity>\d+(?:[.,]\d+)?)\s*(?P<unit>[A-Za-z][A-Za-z0-9/%.-]*)?\s+(?P<name>.+)$"),
    ]

    for pattern in patterns:
        match = pattern.match(line)
        if not match:
            continue

        name = match.groupdict().get("name")
        if not name:
            continue

        quantity = _parse_quantity(match.groupdict().get("quantity"))
        if quantity is None:
            continue

        unit = match.groupdict().get("unit")
        category = match.groupdict().get("category") or _infer_grocery_category(name)
        return {
            "name": _format_item_name(name),
            "quantity": quantity,
            "unit": unit.strip() if unit and unit.strip() else None,
            "category": category.strip() if isinstance(category, str) and category.strip() else _infer_grocery_category(name),
            "notes": line.strip(),
        }

    return None


def _parse_quantity(value: Any) -> float | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _format_item_name(value: str) -> str:
    text = " ".join((value or "").strip().split())
    return text.title()


def _infer_grocery_category(value: str) -> str:
    lowered = _normalize_item_name(value)
    keyword_map = [
        ("produce", ["fruit", "banana", "apple", "berry", "orange", "tomato", "onion", "spinach", "lettuce", "salad", "carrot", "potato", "vegetable"]),
        ("dairy", ["milk", "yogurt", "cheese", "butter", "cream", "paneer"]),
        ("protein", ["chicken", "turkey", "beef", "fish", "salmon", "tuna", "egg", "eggs", "tofu", "lentil", "beans", "bean"]),
        ("pantry", ["rice", "pasta", "flour", "oats", "cereal", "oil", "sauce", "spice", "sugar", "salt"]),
        ("bakery", ["bread", "bagel", "bun", "roll", "tortilla"]),
        ("frozen", ["frozen", "ice cream"]),
        ("beverages", ["juice", "tea", "coffee", "water", "soda", "milkshake"]),
        ("snacks", ["snack", "cracker", "chip", "nuts", "peanut butter"]),
    ]

    for category, keywords in keyword_map:
        if any(keyword in lowered for keyword in keywords):
            return category.title()

    return "Groceries"


def _looks_like_csv_header(values: List[str]) -> bool:
    header_tokens = {
        "item",
        "items",
        "name",
        "quantity",
        "qty",
        "amount",
        "unit",
        "category",
        "notes",
        "price",
        "cost",
        "label",
    }
    normalized = {value.strip().lower() for value in values if value.strip()}
    if not normalized:
        return False
    return normalized.issubset(header_tokens) or (
        {"item", "quantity"}.issubset(normalized)
        or {"name", "qty"}.issubset(normalized)
    )
