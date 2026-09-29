from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.dependencies.database import DbSession
from app.models.user import User
from app.repositories import UserRepository
from app.utils.exceptions import UnauthorizedError
from app.utils.security import decode_access_token

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if credentials is None or not credentials.credentials:
        raise UnauthorizedError("Not authenticated")
    payload = decode_access_token(credentials.credentials)
    subject = payload.get("sub") if payload else None
    if not subject or not str(subject).isdigit():
        raise UnauthorizedError("Invalid or expired session")
    user = await UserRepository(db).get(int(subject))
    if user is None or not user.is_active:
        raise UnauthorizedError("Invalid or expired session")
    return user


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


CurrentUser = Annotated[User, Depends(get_current_user)]
ClientIP = Annotated[str, Depends(client_ip)]
