from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from contextlib import asynccontextmanager
import asyncio
import traceback
from app.workers.email_ingestor import ingest_emails
from app.core.config import settings
from app.core.logging import setup_logging, logger
from app.db.database import init_db, AsyncSessionLocal
import os
from app.events.bus import event_bus
from app.workers.email_processor import process_emails

from app.api.routes import briefing

from app.api.routes import (
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
    await init_db()

    # Start event bus
    event_task = asyncio.create_task(event_bus.start())

    # Run email pipeline ONCE at startup (safe init)
    try:
        logger.info("email.startup.processing")

        async with AsyncSessionLocal() as db:
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
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(tasks.router, prefix="/api/v1")
app.include_router(grocery.router, prefix="/api/v1")
app.include_router(meals.router, prefix="/api/v1")
app.include_router(reminders.router, prefix="/api/v1")
app.include_router(calendar.router, prefix="/api/v1")
app.include_router(memory.router, prefix="/api/v1")
app.include_router(family.router, prefix="/api/v1")
app.include_router(agent.router, prefix="/api/v1")
app.include_router(uploads.router, prefix="/api/v1")
app.include_router(briefing.router)
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
    return {
        "status": "healthy",
        "version": settings.app_version,
    }