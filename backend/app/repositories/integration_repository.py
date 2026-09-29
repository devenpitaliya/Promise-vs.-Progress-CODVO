from typing import List, Optional

from sqlalchemy import select

from app.models.integration import Integration
from app.repositories.base import BaseRepository


class IntegrationRepository(BaseRepository[Integration]):
    model = Integration

    async def list_for_owner(self, owner_id: int) -> List[Integration]:
        result = await self.db.execute(select(Integration).where(Integration.owner_id == owner_id))
        return list(result.scalars().all())

    async def get_for_owner(self, owner_id: int, kind: str) -> Optional[Integration]:
        result = await self.db.execute(select(Integration).where(Integration.owner_id == owner_id, Integration.kind == kind))
        return result.scalar_one_or_none()
