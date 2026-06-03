import os
from sqlalchemy import select
from app.db.database import AsyncSessionLocal
from app.db.models import Email, Task, CalendarEvent
from app.services.email_service import EmailProcessor
from dateutil import parser

async def process_emails():
    print("MAIL_USER:", repr(os.getenv("MAIL_USER")))
    print("MAIL_PASSWORD:", repr(os.getenv("MAIL_PASSWORD")))
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
            actions = await email_service.extract_action_items(
                email["body_text"]
            )

            is_payment = actions.get("is_payment", False)

            # save email
            db_email = Email(**email)
            db_email.processed = True
            db_email.action_items = actions["actions"]
            db.add(db_email)

            # create tasks
            for action in actions["actions"]:

                task = Task(
                    title=action["text"],
                    due_date=action.get("due_date"),
                    tags=["email", "payment" if is_payment else "general"]
                )

                db.add(task)

            # NEW: create calendar events extracted by Gemini
            events = actions.get("calendar_events", [])

            for event_data in events:

                # skip invalid data
                if not event_data.get("title"):
                    continue

                # check duplicates
                existing = await db.execute(
                    select(CalendarEvent).where(
                        CalendarEvent.title == event_data["title"]
                    )
                )

                if existing.scalar_one_or_none():
                    continue
           

                start = parser.parse(event_data["start_time"])
                end = parser.parse(event_data["end_time"])
                event = CalendarEvent(
                    title=event_data["title"],
                    start_time=start,
                    end_time=end,
                    location=event_data.get("location")
                )

                db.add(event)

            await db.commit()