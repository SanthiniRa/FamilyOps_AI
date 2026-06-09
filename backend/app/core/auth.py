from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings


bearer_scheme = HTTPBearer(auto_error=False)


async def require_api_token(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> None:
    if not settings.api_bearer_token:
        if settings.environment == "development":
            return
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API bearer token is not configured",
        )

    token = None
    if credentials and credentials.scheme.lower() == "bearer":
        token = credentials.credentials

    if token != settings.api_bearer_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API token",
            headers={"WWW-Authenticate": "Bearer"},
        )
