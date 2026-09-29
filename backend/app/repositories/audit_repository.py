from datetime import datetime
from typing import List, Optional

from sqlalchemy import func, select

from app.enums import ScheduleStatus
from app.models.audit import EmailLog, ScheduledAudit
from app.repositories.base import BaseRepository


class ScheduledAuditRepository(BaseRepository[ScheduledAudit]):
    model = ScheduledAudit

    async def get_owned(self, owner_id: int, audit_id: int) -> Optional[ScheduledAudit]:
        result = await self.db.execute(select(ScheduledAudit).where(ScheduledAudit.id == audit_id, ScheduledAudit.owner_id == owner_id))
        return result.scalar_one_or_none()

    async def list_for_owner(self, owner_id: int) -> List[ScheduledAudit]:
        result = await self.db.execute(
            select(ScheduledAudit).where(ScheduledAudit.owner_id == owner_id).order_by(ScheduledAudit.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_active(self) -> List[ScheduledAudit]:
        result = await self.db.execute(select(ScheduledAudit).where(ScheduledAudit.status == ScheduleStatus.ACTIVE))
        return list(result.scalars().all())


class EmailLogRepository(BaseRepository[EmailLog]):
    model = EmailLog

    async def count_since(self, owner_id: int, since: datetime) -> int:
        result = await self.db.execute(select(func.count(EmailLog.id)).where(EmailLog.owner_id == owner_id, EmailLog.created_at >= since))
        return int(result.scalar_one())

    async def list_recent(self, owner_id: int, limit: int) -> List[EmailLog]:
        result = await self.db.execute(
            select(EmailLog).where(EmailLog.owner_id == owner_id).order_by(EmailLog.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())
