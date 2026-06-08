from sqlalchemy import select
from app.db.models import FamilyMember


async def get_household_preferences(db):

    result = await db.execute(select(FamilyMember))
    members = result.scalars().all()

    dietary_restrictions = set()
    likes = set()
    dislikes = set()

    for m in members:

        dietary_restrictions.update(
            m.dietary_restrictions or []
        )

        prefs = m.preferences or {}

        likes.update(prefs.get("likes", []))
        dislikes.update(prefs.get("dislikes", []))

    return {
        "family_size": len(members),
        "dietary_restrictions": list(dietary_restrictions),
        "likes": list(likes),
        "dislikes": list(dislikes),
    }