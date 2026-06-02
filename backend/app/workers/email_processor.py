import os
from sqlalchemy import select
from app.db.database import AsyncSessionLocal
from app.db.models import Email, Task, CalendarEvent
from app.services.email_service import EmailProcessor


async def process_emails():
    email_service = EmailProcessor(
        os.getenv("MAIL_USER"),
        os.getenv("MAIL_PASSWORD")
    )

    for email in email_service.fetch_emails():   # ✅ FIXED
        async with AsyncSessionLocal() as db:

            # skip duplicates
            existing = await db.execute(
                select(Email).where(Email.message_id == email["message_id"])
            )

            if existing.scalar_one_or_none():
                continue
            print("EMAIL:", email["subject"])
            print("BODY:", email["body_text"])
            # extract actions
            actions = await email_service.extract_action_items(email["body_text"])
            is_payment = actions.get("is_payment", False)

            # save email
            db_email = Email(**email)
            db_email.processed = True
            db_email.action_items = actions["actions"]
            db.add(db_email)

            # create tasks + calendar events
            for action in actions["actions"]:
                task = Task(
                    title=action["text"],
                    due_date=action.get("due_date"),
                    tags=["email", "payment" if is_payment else "general"]
                )
                db.add(task)
                print("EMAIL:", email["subject"])
                print("BODY:", email["body_text"])
                print("ACTIONS:", actions)
                # ✅ AUTO calendar event
                if action.get("due_date"):
                    event = CalendarEvent(
                        title=action["text"],
                        start_time=action["due_date"],
                        end_time=action["due_date"]
                    )
                    db.add(event)

            await db.commit()