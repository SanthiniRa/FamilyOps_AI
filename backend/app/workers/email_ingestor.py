from app.db.models import Email
from app.services.email_service import EmailProcessor
from sqlalchemy.ext.asyncio import AsyncSession


async def ingest_emails(db: AsyncSession, user, password):

    processor = EmailProcessor(user, password)
    print("FOUND EMAIL:before loop")
    for mail in processor.fetch_emails():
        print("FOUND EMAIL:", mail["subject"])
        # avoid duplicates
        exists = await db.execute(
            Email.__table__.select().where(
                Email.message_id == mail["message_id"]
            )
        )

        if exists.first():
            continue

        db.add(Email(
            message_id=mail["message_id"],
            subject=mail["subject"],
            sender=mail["sender"],
            body_text=mail["body_text"],
            received_at=mail["received_at"]
        ))

    await db.commit()
    print("EMAILS SAVED")