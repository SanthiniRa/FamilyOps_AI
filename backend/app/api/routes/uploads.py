from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.database import get_db
from app.services.vision_service import FoodVisionService
from app.services import document_service
from app.services import ingest_service
from app.db.models import UploadedImage, UploadedDocument

import asyncio
import os
from pathlib import Path
import tempfile

router = APIRouter(prefix="/uploads", tags=["uploads"])


# ============================================================
# FOOD IMAGE UPLOAD
# ============================================================
@router.post("/food-image")
async def upload_food_image(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """Upload food image to analyze ingredients"""

    vision_service = FoodVisionService()

    # Save temp file
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        analysis = await vision_service.analyze_food_image(tmp_path)
        recipes = await vision_service.suggest_recipes(analysis.get("foods", []))

        img = UploadedImage(
            image_url="",
            storage_path=tmp_path,
            analysis_result=analysis,
        )

        db.add(img)
        await db.commit()
        await db.refresh(img)

        return {
            "food_items": analysis,
            "recipes": recipes,
            "id": img.id
        }

    finally:
        # keep file for now
        pass


# ============================================================
# DOCUMENT UPLOAD
# ============================================================
@router.post("/document")
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """Upload document for ingestion pipeline"""

    dest_dir = Path(
        os.getenv(
            "DOCUMENT_UPLOAD_PATH",
            Path(__file__).resolve().parent.parent.parent / "uploads" / "documents"
        )
    )

    dest_dir.mkdir(parents=True, exist_ok=True)

    try:
        saved_path, metadata = await document_service.save_upload(file, dest_dir)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    doc = UploadedDocument(
        filename=metadata.get("filename"),
        content_type=metadata.get("content_type"),
        storage_path=str(saved_path),
        extra_metadata=metadata.get("meta", {}),  # FIXED HERE
        source=metadata.get("source", "upload"),
    )

    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    # fire-and-forget ingestion
    try:
        asyncio.create_task(ingest_service.ingest_document(doc.id))
    except Exception:
        pass

    return {
        "id": doc.id,
        "filename": doc.filename,
        "storage_path": doc.storage_path
    }


# ============================================================
# MANUAL INGEST TRIGGER
# ============================================================
@router.post("/{doc_id}/ingest")
async def trigger_ingest(doc_id: str):

    try:
        asyncio.create_task(ingest_service.ingest_document(doc_id))
        return {
            "status": "scheduled",
            "document_id": doc_id
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# PROVENANCE REPORT
# ============================================================
@router.get("/{doc_id}/provenance")
async def provenance_report(
    doc_id: str,
    db: AsyncSession = Depends(get_db)
):

    result = await db.execute(
        select(UploadedDocument).where(
            UploadedDocument.id == doc_id
        )
    )

    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(status_code=404, detail="document not found")

    return {
        "id": doc.id,
        "filename": doc.filename,
        "ingested": doc.ingested,
        "metadata": doc.extra_metadata,  # FIXED HERE
    }