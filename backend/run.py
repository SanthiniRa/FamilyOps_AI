from dotenv import load_dotenv
from pathlib import Path
import os

env_path = Path(__file__).parent / ".env"
load_dotenv(env_path, override=False)

host = os.getenv("HOST", "0.0.0.0")
port = int(os.getenv("PORT", "8000"))

import uvicorn
from app.core.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=settings.debug,
        log_level="debug" if settings.debug else "info",
    )
