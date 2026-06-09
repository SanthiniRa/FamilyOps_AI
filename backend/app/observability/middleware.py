from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
import time
from app.core.logging import logger


class RequestLoggingMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next):
        start = time.time()

        response = None
        try:
            response = await call_next(request)
            return response

        finally:
            duration = time.time() - start

            logger.info(
                "http.request",
                method=request.method,
                path=request.url.path,
                duration=duration,
                status_code=getattr(response, "status_code", None),
            )