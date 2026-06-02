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
                line = line.strip()
                if line.startswith("DATABASE_URL="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")

    return settings.database_url


async def init_db():
    global engine, AsyncSessionLocal

    db_url = _resolve_database_url()

    if not db_url:
        db_url = "sqlite+aiosqlite:///./familyops.db"

    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    db_url = db_url.split("?")[0]

    is_sqlite = "sqlite" in db_url

    engine_kwargs = {
        "echo": settings.debug,
        "pool_pre_ping": True,
    }

    if is_sqlite:
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    else:
        engine_kwargs["connect_args"] = {
            "statement_cache_size": 0,
            "timeout": 10,
        }

    engine = create_async_engine(db_url, **engine_kwargs)

    AsyncSessionLocal = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    from app.db.models import Base

    async def _create_tables():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    try:
        await asyncio.wait_for(_create_tables(), timeout=15)
        logger.info("db.initialized")
    except Exception as e:
        logger.error("db.failed", error=str(e)[:200])

        # fallback sqlite
        fallback_url = "sqlite+aiosqlite:///./familyops.db"

        engine = create_async_engine(
            fallback_url,
            echo=settings.debug,
            pool_pre_ping=True,
            connect_args={"check_same_thread": False},
        )

        AsyncSessionLocal = sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        logger.info("db.fallback_sqlite")


# ✅ THIS FIXES YOUR ERROR (IMPORTANT)
async def get_db():
    if AsyncSessionLocal is None:
        await init_db()

    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()