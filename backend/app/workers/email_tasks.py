from app.core.celery_app import celery
from app.core.config import settings
from app.db.database import AsyncSessionLocal
from app.workers.email_ingestor import ingest_emails
from app.workers.email_processor import process_emails
from app.core.logging import logger
import asyncio


@celery.task(name="email.process_pipeline")
def process_email_pipeline():
    """
    Celery entrypoint (sync wrapper)
    """
    asyncio.run(_run_pipeline())


async def _run_pipeline():
    async with AsyncSessionLocal() as db:
        if not settings.email_address or not settings.email_password:
            logger.info("email.pipeline.skipped_missing_credentials")
            return

        await ingest_emails(
            db,
            settings.email_address,
            settings.email_password,
        )

        await process_emails(db)
