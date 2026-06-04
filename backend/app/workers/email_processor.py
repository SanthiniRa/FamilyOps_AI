import os
from sqlalchemy import select
from dateutil import parser

from app.db import database
from app.db.models import Email, Task, CalendarEvent
from app.services.email_service import EmailProcessor


async def process_emails():

    email_service = EmailProcessor(
        os.getenv("EMAIL_ADDRESS"),
        os.getenv("EMAIL_PASSWORD")
    )

    if database.AsyncSessionLocal is None:
        await database.init_db()

    for email in email_service.fetch_emails():

        async with database.AsyncSessionLocal() as db:

            # Skip duplicates
            existing = await db.execute(
                select(Email).where(
                    Email.message_id == email["message_id"]
                )
            )

            if existing.scalar_one_or_none():
                continue

            print("EMAIL:", email["subject"])

            actions = await email_service.extract_action_items(
                email["body_text"]
            )

            is_payment = actions.get("is_payment", False)

            # Save email
            db_email = Email(**email)
            db_email.processed = True
            db_email.action_items = actions["actions"]

            db.add(db_email)

            # Create tasks
            for action in actions.get("actions", []):
    
                title = (
                    action.get("text")
                    or action.get("name")
                    or action.get("title")
                )
    
                if not title:
                    continue
    
                task = Task(
                    title=title,
                    due_date=action.get("due_date"),
                    tags=[
                        "email",
                        "payment" if is_payment else "general"
                    ]
                )

                db.add(task)

            

            # Create calendar events
            for event_data in actions.get("calendar_events", []):

                if not event_data.get("title"):
                    continue

                existing = await db.execute(
                    select(CalendarEvent).where(
                        CalendarEvent.title == event_data["title"]
                    )
                )

                if existing.scalar_one_or_none():
                    continue

                start = parser.parse(
                    event_data["start_time"]
                )

                end = parser.parse(
                    event_data["end_time"]
                )

                event = CalendarEvent(
                    title=event_data["title"],
                    start_time=start,
                    end_time=end,
                    location=event_data.get("location"),
                )

                db.add(event)

            await db.commit()