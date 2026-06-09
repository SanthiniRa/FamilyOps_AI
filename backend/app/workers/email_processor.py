from sqlalchemy import select
from app.db.models import Email
from app.agents.email_graph import build_graph
from app.core.logging import logger

# Initialize graph once (important for performance)
graph = build_graph()


async def process_emails(db):
    """
    Fetch unprocessed emails and run them through the agent graph.
    """

    try:
        # 1. Fetch unprocessed emails
        result = await db.execute(
            select(Email).where(Email.processed.is_(False))
        )

        emails = result.scalars().all()

        if not emails:
            logger.info("No unprocessed emails found")
            return

        logger.info(f"Processing {len(emails)} emails")

        # 2. Process each email through agent graph
        for email in emails:
            try:
                logger.info(f"Processing email id={email.id}")

                await graph.ainvoke({
                    "email": {
                        "id": email.id,
                        "subject": email.subject,
                        "body_text": email.body_text,
                        "body_html": email.body_html,
                        "sender": email.sender,
                        "attachments": (email.extra_data or {}).get("attachments", []),
                        "attachment_text": (email.extra_data or {}).get("attachment_text", ""),
                        "attachment_count": (email.extra_data or {}).get("attachment_count", 0),
                    }
                })

                logger.info(f"Successfully processed email id={email.id}")

            except Exception as e:
                logger.error(
                    "email.processing.failed",
                    extra={
                        "email_id": email.id,
                        "error": str(e),
                    },
                    exc_info=True,
                )

    except Exception as e:
        logger.error(
            "email.batch.failed",
            extra={"error": str(e)},
            exc_info=True,
        )
        raise
