from typing import Iterable, List, Optional

from sqlalchemy import select

from app.enums import ApprovalStatus, SyncStatus, TaskStatus
from app.models.task import Task
from app.repositories.base import BaseRepository


class TaskRepository(BaseRepository[Task]):
    model = Task

    async def get_owned(self, owner_id: int, task_id: int) -> Optional[Task]:
        result = await self.db.execute(select(Task).where(Task.id == task_id, Task.owner_id == owner_id))
        return result.scalar_one_or_none()

    async def list_owned(
        self,
        owner_id: int,
        *,
        meeting_id: Optional[int] = None,
        approval_status: Optional[ApprovalStatus] = None,
        status: Optional[TaskStatus] = None,
        task_ids: Optional[Iterable[int]] = None,
    ) -> List[Task]:
        stmt = select(Task).where(Task.owner_id == owner_id)
        if meeting_id is not None:
            stmt = stmt.where(Task.meeting_id == meeting_id)
        if approval_status is not None:
            stmt = stmt.where(Task.approval_status == approval_status)
        if status is not None:
            stmt = stmt.where(Task.status == status)
        if task_ids is not None:
            stmt = stmt.where(Task.id.in_(list(task_ids)))
        result = await self.db.execute(stmt.order_by(Task.id.desc()))
        return list(result.scalars().all())

    async def list_tracked(self, owner_id: int, meeting_id: Optional[int] = None, task_ids: Optional[Iterable[int]] = None) -> List[Task]:
        """Approved commitments only: pending and rejected items are not tracked yet."""
        tasks = await self.list_owned(owner_id, meeting_id=meeting_id, approval_status=ApprovalStatus.APPROVED, task_ids=task_ids)
        return sorted(tasks, key=lambda t: t.id)

    async def owners_with_synced_tasks(self) -> List[int]:
        result = await self.db.execute(
            select(Task.owner_id).where(Task.approval_status == ApprovalStatus.APPROVED, Task.sync_status == SyncStatus.SYNCED).distinct()
        )
        return [owner_id for (owner_id,) in result.all()]
