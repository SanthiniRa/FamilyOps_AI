from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.core.logging import logger
from pathlib import Path
import asyncio

engine = None
AsyncSessionLocal = None


def _resolve_database_url() -> str:
    candidates = [
        Path(__file__).parent.parent.parent.parent / ".env",
        Path(__file__).parent.parent.parent / ".env",
    ]

    for env_file in candidates:
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("DATABASE_URL="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")

    return settings.database_url


async def init_db():
    global engine, AsyncSessionLocal

    db_url = _resolve_database_url()

    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    db_url = db_url.split("?")[0]  # remove pgbouncer query

    is_sqlite = "sqlite" in db_url

    engine_kwargs = {
        "echo": settings.debug,
        "pool_pre_ping": True,
    }

    if is_sqlite:
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    else:
        # ✅ SUPABASE FIX
        engine_kwargs["connect_args"] = {
            "statement_cache_size": 0
        }

    engine = create_async_engine(db_url, **engine_kwargs)

    AsyncSessionLocal = sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    from app.db.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("db.initialized")


async def get_db():
    global AsyncSessionLocal

    if AsyncSessionLocal is None:
        await init_db()

    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()