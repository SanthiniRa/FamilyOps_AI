from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from contextlib import asynccontextmanager
import asyncio
import traceback
from app.core.config import settings
from app.core.logging import setup_logging, logger
from app.db.database import init_db
from app.events.bus import event_bus

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
)

from app.workers.email_processor import process_emails

async def email_polling_loop():
    """
    Continuously checks email inbox and processes
    new emails every 5 minutes.
    """
    while True:
        try:
            logger.info("email.polling.started")

            await process_emails()

            logger.info("email.polling.completed")

        except Exception as e:
            print("FULL ERROR:", repr(e))
            traceback.print_exc()
    
        await asyncio.sleep(300)  # 5 minutes


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()

    logger.info(
        "familyops.starting",
        version=settings.app_version
    )

    # Initialize database
    await init_db()

    # Start event bus
    event_task = asyncio.create_task(
        event_bus.start()
    )

    # Process inbox immediately at startup
    try:
        logger.info("email.startup.processing")

        await process_emails()

        logger.info("email.startup.completed")

    except Exception as e:
        logger.exception(
            "email.startup.error",
            error=str(e)
        )

    # Start recurring email polling
    email_task = asyncio.create_task(
        email_polling_loop()
    )

    logger.info("familyops.ready")

    yield

    logger.info("familyops.shutdown")

    # Cancel background tasks
    email_task.cancel()
    event_task.cancel()

    try:
        await email_task
    except asyncio.CancelledError:
        pass

    try:
        await event_task
    except asyncio.CancelledError:
        pass

    event_bus.stop()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI-powered Household Operations Platform",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# Middleware
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

# Routers
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(tasks.router, prefix="/api/v1")
app.include_router(grocery.router, prefix="/api/v1")
app.include_router(meals.router, prefix="/api/v1")
app.include_router(reminders.router, prefix="/api/v1")
app.include_router(calendar.router, prefix="/api/v1")
app.include_router(memory.router, prefix="/api/v1")
app.include_router(family.router, prefix="/api/v1")
app.include_router(agent.router, prefix="/api/v1")


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