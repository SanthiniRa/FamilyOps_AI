from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from sqlalchemy.pool import NullPool
import asyncio
from urllib.parse import urlparse, urlencode, parse_qs, urlunparse

# ============================================================
# FIX: Supabase + PgBouncer safe URL
# ============================================================
def normalize_database_url(raw_url: str | None) -> str:
    candidate = (raw_url or "").strip()
    if not candidate:
        return "sqlite+aiosqlite:///./familyops.db"

    if candidate.startswith("sqlite://") and not candidate.startswith("sqlite+aiosqlite://"):
        return candidate.replace("sqlite://", "sqlite+aiosqlite://", 1)

    if candidate.startswith("postgresql://"):
        return candidate.replace("postgresql://", "postgresql+asyncpg://", 1)

    if candidate.startswith("postgres://"):
        return candidate.replace("postgres://", "postgresql+asyncpg://", 1)

    return candidate


DATABASE_URL = normalize_database_url(settings.database_url)

_connect_args: dict = {"statement_cache_size": 0}
IS_SQLITE = DATABASE_URL.startswith("sqlite")

if not IS_SQLITE:
    # Strip sslmode from URL query string — asyncpg does not accept it
    # as a keyword arg; we pass ssl=True via connect_args instead.
    _parsed = urlparse(DATABASE_URL)
    _qs = parse_qs(_parsed.query, keep_blank_values=True)
    _need_ssl = _qs.pop("sslmode", ["disable"])[0] not in ("disable", "allow")
    _clean_query = urlencode({k: v[0] for k, v in _qs.items()})
    DATABASE_URL = urlunparse(_parsed._replace(query=_clean_query))

    if _need_ssl:
        _connect_args["ssl"] = True

# ============================================================
# ENGINE (IMPORTANT FIXES HERE)
# ============================================================
engine = create_async_engine(
    DATABASE_URL if not IS_SQLITE else DATABASE_URL,
    echo=settings.debug,
    poolclass=NullPool,
    pool_pre_ping=True,
    connect_args={} if IS_SQLITE else _connect_args,
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
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise