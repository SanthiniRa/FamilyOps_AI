from dotenv import load_dotenv
from pathlib import Path
import os

env_path = Path(__file__).parent / ".env"

load_dotenv(env_path, override=True)

# FORCE refresh environment (important)
os.environ["EMAIL_ADDRESS"] = os.getenv("EMAIL_ADDRESS", "")
os.environ["EMAIL_PASSWORD"] = os.getenv("EMAIL_PASSWORD", "")

print("BOOT MAIL_USER =", repr(os.getenv("MAIL_USER")))
print("BOOT MAIL_PASSWORD =", repr(os.getenv("MAIL_PASSWORD")))

#import google.generativeai as genai

#genai.configure(api_key=os.getenv("GOOGLE_API_KEY", ""))

#print([m.name for m in genai.list_models()])
import uvicorn
from app.core.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="localhost",
        port=8000,
        reload=settings.debug,
        log_level="debug" if settings.debug else "info",
    )
