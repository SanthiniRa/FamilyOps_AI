from celery import Celery
import os
from app.core.config import settings

REDIS_URL = os.getenv("REDIS_URL", settings.redis_url or "redis://localhost:6379/0")

celery = Celery(
    "familyops",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.workers.email_tasks"],
)

celery.conf.update(
    task_track_started=True,
    worker_prefetch_multiplier=1,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)

# Import task modules so their decorators register with this Celery app.
import app.workers.email_tasks  # noqa: F401,E402
