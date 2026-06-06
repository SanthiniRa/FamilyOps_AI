from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from sqlalchemy.pool import NullPool
import asyncio

# ============================================================
# FIX: Supabase + PgBouncer safe URL
# ============================================================
DATABASE_URL = settings.database_url

# Force asyncpg driver
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgresql://",
        "postgresql+asyncpg://"
    )

# ============================================================
# ENGINE (IMPORTANT FIXES HERE)
# ============================================================
engine = create_async_engine(
    DATABASE_URL,
    echo=settings.debug,
    poolclass=NullPool,
    pool_pre_ping=True,
    connect_args={
        "statement_cache_size": 0,
    }
)

# ============================================================
# SESSION
# ============================================================
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# ============================================================
# DB INIT
# ============================================================
async def init_db():
    from app.db.models import Base

    for attempt in range(3):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            return

        except Exception as e:
            print(f"DB startup attempt {attempt+1} failed: {e}")

            if attempt == 2:
                raise

            await asyncio.sleep(2)


# ============================================================
# DEPENDENCY
# ============================================================
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session