from typing import List, Optional

from sqlalchemy import select

from app.models.meeting import Meeting
from app.repositories.base import BaseRepository


class MeetingRepository(BaseRepository[Meeting]):
    model = Meeting

    async def get_owned(self, owner_id: int, meeting_id: int) -> Optional[Meeting]:
        result = await self.db.execute(select(Meeting).where(Meeting.id == meeting_id, Meeting.owner_id == owner_id))
        return result.scalar_one_or_none()

    async def list_for_owner(self, owner_id: int) -> List[Meeting]:
        result = await self.db.execute(
            select(Meeting).where(Meeting.owner_id == owner_id).order_by(Meeting.meeting_date.desc(), Meeting.id.desc())
        )
        return list(result.scalars().all())

    async def recent_participant_lists(self, owner_id: int, limit: int = 50) -> List[list]:
        result = await self.db.execute(
            select(Meeting.participants).where(Meeting.owner_id == owner_id).order_by(Meeting.created_at.desc()).limit(limit)
        )
        return [participants or [] for (participants,) in result.all()]
