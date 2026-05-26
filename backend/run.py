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
