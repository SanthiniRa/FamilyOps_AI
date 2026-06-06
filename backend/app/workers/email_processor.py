    from app.agents.email_graph import build_graph


    graph = build_graph()


    async def process_emails(db):

        emails = await db.execute("SELECT * FROM emails WHERE processed = false")
        emails = emails.fetchall()

        for email in emails:

            await graph.ainvoke({
                "email": {
                    "id": email.id,
                    "subject": email.subject,
                    "body_text": email.body_text,
                    "sender": email.sender,
                }
            })