from app.core.celery_app import celery
from app.db.database import AsyncSessionLocal
from app.workers.email_ingestor import ingest_emails
from app.workers.email_processor import process_emails
import asyncio
import os


@celery.task(name="email.process_pipeline")
def process_email_pipeline():
    """
    Celery entrypoint (sync wrapper)
    """
    asyncio.run(_run_pipeline())


async def _run_pipeline():
    async with AsyncSessionLocal() as db:
        await ingest_emails(
            db,
            os.getenv("EMAIL_ADDRESS"),
            os.getenv("EMAIL_PASSWORD"),
        )

        await process_emails(db)