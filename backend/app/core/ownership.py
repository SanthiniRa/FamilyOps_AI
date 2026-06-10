from __future__ import annotations

from typing import Any, Dict, Optional

from app.db.models import User


OWNER_FAMILY_MEMBER_KEY = "owner_family_member_id"


def get_owner_family_member_id(user: Optional[User]) -> Optional[str]:
    if not user:
        return None
    return user.family_member_id or None


def with_owner_metadata(
    metadata: Optional[Dict[str, Any]],
    owner_family_member_id: Optional[str],
    *,
    overwrite: bool = True,
) -> Dict[str, Any]:
    payload = dict(metadata or {})
    if owner_family_member_id:
        if overwrite or OWNER_FAMILY_MEMBER_KEY not in payload:
            payload[OWNER_FAMILY_MEMBER_KEY] = owner_family_member_id
    return payload


def metadata_matches_owner(
    metadata: Optional[Dict[str, Any]],
    owner_family_member_id: Optional[str],
) -> bool:
    if not owner_family_member_id:
        return True

    metadata = metadata or {}
    owner_in_record = metadata.get(OWNER_FAMILY_MEMBER_KEY)
    return owner_in_record in (None, owner_family_member_id)
