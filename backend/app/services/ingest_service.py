from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

from sqlalchemy import select

from app.core.config import settings
from app.db.database import AsyncSessionLocal
from app.db.models import UploadedDocument
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
            doc.ingested = True
            doc.extra_metadata = {
                **(doc.extra_metadata or {}),
                "stored_chunks": stored_ids,
                "stored_count": len(stored_ids),
                "parsed_at": datetime.utcnow().isoformat() + "Z",
                "pages": len(pages),
                "content_type": doc.content_type,
                "source": doc.source,
            }
            await db.commit()

    logger.info(
        "ingest.completed",
        document_id=uploaded_doc_id,
        stored_chunks=len(stored_ids)
    )


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
