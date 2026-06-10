from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from contextlib import asynccontextmanager
import asyncio
import traceback
from app.workers.email_ingestor import ingest_emails
from app.core.config import settings
from app.core.auth import require_api_token
from app.core.logging import setup_logging, logger
from app.db.database import init_db, AsyncSessionLocal
import os
from app.events.bus import event_bus
from app.workers.email_processor import process_emails
from app.observability.middleware import RequestLoggingMiddleware
from app.api.routes import briefing

from app.observability.tracing import tracer
from app.core.resilience import shared_resilience_health

from prometheus_fastapi_instrumentator import Instrumentator
from app.api.routes import (
    auth,
    tasks,
    grocery,
    meals,
    reminders,
    calendar,
    memory,
    family,
    agent,
    dashboard,
    uploads,
    web_search,
    weather,
    events,
    recipes,
)

# ============================================================
# LIFESPAN
# ============================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()

    logger.info(
        "familyops.starting",
        version=settings.app_version
    )

    # Initialize DB
    try:
        await init_db()
    except Exception as e:
        logger.exception(
            "database.startup.failed",
            error=str(e),
        )
        raise

    # Start event bus
    event_task = asyncio.create_task(event_bus.start())
    from app.observability.langfuse_client import langfuse as langfuse_client

    logger.info(
        "observability.initialized"
    )
    if langfuse_client:
        logger.info("observability.langfuse.enabled")
    else:
        logger.info("observability.langfuse.disabled")
    # Run email pipeline ONCE at startup (safe init)
    try:
        logger.info("email.startup.processing")

        async with AsyncSessionLocal() as db:
            if settings.email_address and settings.email_password:
                await ingest_emails(
                    db,
                    settings.email_address,
                    settings.email_password,
                )
            await process_emails(db)

        logger.info("email.startup.completed")

    except Exception as e:
        logger.exception("email.startup.error", error=str(e))

    logger.info("familyops.ready")

    yield

    logger.info("familyops.shutdown")

    event_task.cancel()

    try:
        await event_task
    except asyncio.CancelledError:
        pass

    event_bus.stop()

    try:
        from app.observability.langfuse_client import flush_langfuse

        flush_langfuse()
    except Exception as e:
        logger.exception("observability.langfuse.shutdown_flush_failed", error=str(e))
# ============================================================
# FASTAPI APP
# ============================================================
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI-powered Household Operations Platform",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# ============================================================
# MIDDLEWARE
# ============================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    GZipMiddleware,
    minimum_size=1000,
)


# ============================================================
# ROUTES
# ============================================================
protected = [Depends(require_api_token)]

app.include_router(dashboard.router, prefix="/api/v1", dependencies=protected)
app.include_router(auth.router, prefix="/api/v1")
app.include_router(tasks.router, prefix="/api/v1", dependencies=protected)
app.include_router(grocery.router, prefix="/api/v1", dependencies=protected)
app.include_router(meals.router, prefix="/api/v1", dependencies=protected)
app.include_router(reminders.router, prefix="/api/v1", dependencies=protected)
app.include_router(calendar.router, prefix="/api/v1", dependencies=protected)
app.include_router(memory.router, prefix="/api/v1", dependencies=protected)
app.include_router(family.router, prefix="/api/v1", dependencies=protected)
app.include_router(agent.router, prefix="/api/v1", dependencies=protected)
app.include_router(uploads.router, prefix="/api/v1", dependencies=protected)
app.include_router(web_search.router, prefix="/api/v1", dependencies=protected)
app.include_router(weather.router, prefix="/api/v1", dependencies=protected)
app.include_router(events.router, prefix="/api/v1", dependencies=protected)
app.include_router(recipes.router, prefix="/api/v1", dependencies=protected)
app.include_router(briefing.router, dependencies=protected)

Instrumentator().instrument(app).expose(app)

app.add_middleware(
    RequestLoggingMiddleware
)

# ============================================================
# ROOT
# ============================================================
@app.get("/")
async def root():
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/api/docs",
        "status": "running",
    }


@app.get("/health")
async def health():
    resilience = await shared_resilience_health()
    return {
        "status": "healthy",
        "version": settings.app_version,
        "shared_resilience_redis": resilience,
    }
