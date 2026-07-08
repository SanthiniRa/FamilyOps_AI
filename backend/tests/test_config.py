import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import _parse_activity_search_source_domains  # noqa: E402


def test_parse_activity_search_source_domains_accepts_comma_string():
    value = "nationaltrust.org.uk, nhm.ac.uk; dayoutwiththekids.co.uk\nvisitlondon.com"

    assert _parse_activity_search_source_domains(value) == [
        "nationaltrust.org.uk",
        "nhm.ac.uk",
        "dayoutwiththekids.co.uk",
        "visitlondon.com",
    ]
