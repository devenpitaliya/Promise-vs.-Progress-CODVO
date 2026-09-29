from typing import Generic, Iterable, Optional, Type, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Common persistence helpers. Subclasses add tenant-scoped queries."""

    model: Type[ModelT]

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, entity_id: int) -> Optional[ModelT]:
        return await self.db.get(self.model, entity_id)

    async def add(self, entity: ModelT) -> ModelT:
        self.db.add(entity)
        await self.db.flush()
        return entity

    async def add_all(self, entities: Iterable[ModelT]) -> list[ModelT]:
        items = list(entities)
        self.db.add_all(items)
        await self.db.flush()
        return items

    async def delete(self, entity: ModelT) -> None:
        await self.db.delete(entity)
        await self.db.flush()
