from pydantic import BaseModel

from app.schemas.user import UserResponse


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105
    user: UserResponse
