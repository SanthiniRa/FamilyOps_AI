from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.services.email_service import EmailProcessor
from app.db.database import AsyncSessionLocal
from app.db.models import Email, Task, CalendarEvent
from app.agents.orchestrator import orchestrator

async def process_emails():
    """Scheduled task to process incoming emails"""
    email_service = EmailProcessor(os.getenv("MAIL_USER"), os.getenv("MAIL_PASSWORD"))
    
    async for email in email_service.fetch_emails():
        async with AsyncSessionLocal() as db:
            # Check if already processed
            existing = await db.execute(
                select(Email).where(Email.message_id == email['message_id'])
            )
            if existing.scalar_one_or_none():
                continue
            
            # Extract action items
            actions = await email_service.extract_action_items(email['body_text'])
            is_payment = await email_service.detect_payment_emails(email['subject'], email['body_text'])
            
            # Save email record
            db_email = Email(**email)
            db_email.action_items = actions['actions']
            db_email.processed = True
            db.add(db_email)
            
            # Create tasks/events from actions
            for action in actions['actions']:
                task = Task(
                    title=action['text'],
                    due_date=action.get('due_date'),
                    tags=['email', 'payment' if is_payment else 'general']
                )
                db.add(task)
            
            await db.commit()
