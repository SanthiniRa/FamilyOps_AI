from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.core.logging import logger
from pathlib import Path


def _resolve_database_url() -> str:
    """
    Read DATABASE_URL directly from the .env file so it takes priority over
    any system-level environment variable (e.g. Replit's internal helium DB).
    Checks workspace root and backend/ directory. Falls back to the OS env var.
    """
    candidates = [
        Path(__file__).parent.parent.parent.parent / ".env",  # workspace root
        Path(__file__).parent.parent.parent / ".env",         # backend/
    ]
    for env_file in candidates:
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if line.startswith("DATABASE_URL=") and not line.startswith("#"):
                    value = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if value:
                        return value
    return settings.database_url


engine = None
AsyncSessionLocal = None


async def init_db():
    global engine, AsyncSessionLocal

    db_url = _resolve_database_url()

    if not db_url:
        db_url = "sqlite+aiosqlite:///./familyops.db"
        logger.info("db.using_sqlite", path="./familyops.db")
    elif db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        db_url = db_url.split("?")[0]
    elif db_url.startswith("postgresql+asyncpg://"):
        db_url = db_url.split("?")[0]

    is_sqlite = "sqlite" in db_url

    engine_kwargs = {
        "echo": settings.debug,
        "pool_pre_ping": True,
    }

    if is_sqlite:
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    else:
        # Fail fast on unreachable host instead of hanging indefinitely
        engine_kwargs["connect_args"] = {"timeout": 10, "command_timeout": 10}
        engine_kwargs["pool_timeout"] = 15
        engine_kwargs["connect_args"] = {"server_settings": {}, "timeout": 10}

    engine = create_async_engine(db_url, **engine_kwargs)

    AsyncSessionLocal = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    from app.db.models import Base
    import asyncio

    async def _create_tables():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    try:
        await asyncio.wait_for(_create_tables(), timeout=15.0)
        logger.info("db.initialized", url=db_url.split("@")[-1] if "@" in db_url else db_url)
    except (asyncio.TimeoutError, Exception) as e:
        err = "timeout" if isinstance(e, asyncio.TimeoutError) else str(e)[:120]
        logger.error("db.connection_failed", error=err,
                     hint="Falling back to SQLite. Fix DATABASE_URL to use Supabase pooler (port 6543).")
        # Graceful fallback so the backend still starts
        fallback_url = "sqlite+aiosqlite:///./familyops.db"
        engine = create_async_engine(fallback_url, echo=settings.debug, pool_pre_ping=True,
                                     connect_args={"check_same_thread": False})
        AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("db.fallback_sqlite", path="./familyops.db")


async def get_db():
    if AsyncSessionLocal is None:
        await init_db()
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
