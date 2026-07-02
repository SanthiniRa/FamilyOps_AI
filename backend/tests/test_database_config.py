from app.db import database


def test_normalize_database_url_defaults_to_sqlite():
    assert database.normalize_database_url("") == "sqlite+aiosqlite:///./familyops.db"
    assert database.normalize_database_url("   ") == "sqlite+aiosqlite:///./familyops.db"
