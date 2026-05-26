from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from contextlib import asynccontextmanager
import asyncio

from app.core.config import settings
from app.core.logging import setup_logging, logger
from app.db.database import init_db
from app.events.bus import event_bus
from app.api.routes import tasks, grocery, meals, reminders, calendar, memory, family, agent, dashboard


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("familyops.starting", version=settings.app_version)

    await init_db()

    asyncio.create_task(event_bus.start())

    logger.info("familyops.ready")
    yield

    event_bus.stop()
    logger.info("familyops.shutdown")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI-powered Household Operations Platform",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

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
    return {"status": "healthy", "version": settings.app_version}
