"""Password authentication and account creation."""

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories import UserRepository, normalise_email
from app.utils.security import get_password_hash, verify_password

# Compared against when the email is unknown, so login timing does not reveal which accounts exist.
_DUMMY_HASH = get_password_hash("timing-equaliser-password-1")


async def authenticate_user(db: AsyncSession, email: str, password: str) -> Optional[User]:
    user = await UserRepository(db).get_by_email(email)
    if user is None:
        verify_password(password, _DUMMY_HASH)
        return None
    if not verify_password(password, user.hashed_password) or not user.is_active:
        return None
    return user


async def create_user(db: AsyncSession, *, email: str, password: str, full_name: str, is_demo: bool = False) -> User:
    return await UserRepository(db).add(
        User(email=normalise_email(email), hashed_password=get_password_hash(password), full_name=full_name, is_demo=is_demo)
    )
