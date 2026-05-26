from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.core.logging import logger

engine = None
AsyncSessionLocal = None


async def init_db():
    global engine, AsyncSessionLocal

    db_url = settings.database_url

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

    engine = create_async_engine(db_url, **engine_kwargs)

    AsyncSessionLocal = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    from app.db.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("db.initialized", url=db_url.split("@")[-1] if "@" in db_url else db_url)


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
