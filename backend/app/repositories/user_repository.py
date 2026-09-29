from typing import Optional

from sqlalchemy import select

from app.models.user import User
from app.repositories.base import BaseRepository


def normalise_email(email: str) -> str:
    return email.strip().lower()


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_email(self, email: str) -> Optional[User]:
        result = await self.db.execute(select(User).where(User.email == normalise_email(email)))
        return result.scalar_one_or_none()
