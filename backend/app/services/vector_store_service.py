"""Tenant-scoped semantic search over commitments (ChromaDB).

Each collection is bound to exactly one embedding model, so vectors of different sizes are never
mixed. Chroma is synchronous, so every call runs in a worker thread. Indexing failures are logged
and never break the primary workflow; the database stays the source of truth.
"""

import asyncio
import hashlib
import logging
import math
from typing import Any, Dict, Iterable, List, Optional

from app.config import settings
from app.models.task import Task
from app.utils.tracing import observe

logger = logging.getLogger(__name__)

_LOCAL_DIM = 256


def _local_embed(texts: Iterable[str]) -> List[List[float]]:
    """Hashed bag-of-words embedding: deterministic, offline, good enough for keyword-ish recall."""
    vectors = []
    for text in texts:
        vec = [0.0] * _LOCAL_DIM
        for token in text.lower().split():
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            vec[int.from_bytes(digest, "big") % _LOCAL_DIM] += 1.0
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        vectors.append([x / norm for x in vec])
    return vectors


def _gemini_embed(texts: List[str]) -> List[List[float]]:
    from google import genai

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    result = client.models.embed_content(model=settings.GEMINI_EMBEDDING_MODEL, contents=texts)
    return [list(e.values) for e in result.embeddings]


class VectorStoreService:
    def __init__(self) -> None:
        self._collection = None
        self._disabled = False
        self.provider = settings.EMBEDDING_PROVIDER
        self.enabled = settings.SEMANTIC_SEARCH_ENABLED

    def _embed(self, texts: List[str]) -> List[List[float]]:
        return _gemini_embed(texts) if self.provider == "gemini" else _local_embed(texts)

    def _get_collection(self):
        if self._collection is not None or self._disabled or not self.enabled:
            return self._collection
        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings

            settings.chroma_dir.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(settings.chroma_dir), settings=ChromaSettings(anonymized_telemetry=False))
            self._collection = client.get_or_create_collection(name=f"commitments_{self.provider}", metadata={"hnsw:space": "cosine"})
        except Exception:
            logger.exception("ChromaDB unavailable; semantic search disabled")
            self._disabled = True
        return self._collection

    def _index_sync(self, tasks: List[Task]) -> None:
        collection = self._get_collection()
        if collection is None or not tasks:
            return
        documents = [f"{t.assignee}: {t.description}" for t in tasks]
        collection.upsert(
            ids=[f"task-{t.id}" for t in tasks],
            documents=documents,
            embeddings=self._embed(documents),
            metadatas=[{"task_id": t.id, "owner_id": t.owner_id, "meeting_id": t.meeting_id} for t in tasks],
        )

    def _delete_sync(self, task_ids: List[int]) -> None:
        collection = self._get_collection()
        if collection is not None and task_ids:
            collection.delete(ids=[f"task-{i}" for i in task_ids])

    def _search_sync(self, owner_id: int, query: str, limit: int) -> List[Dict[str, Any]]:
        collection = self._get_collection()
        if collection is None:
            return []
        result = collection.query(query_embeddings=self._embed([query]), n_results=limit, where={"owner_id": owner_id})
        ids = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        return [{"task_id": int(m["task_id"]), "score": round(1 - d, 3)} for m, d in zip(ids, distances, strict=False)]

    @observe("vector-index", as_type="tool")
    async def index_tasks(self, tasks: Iterable[Task]) -> None:
        try:
            await asyncio.to_thread(self._index_sync, list(tasks))
        except Exception:
            logger.warning("Semantic indexing failed", exc_info=True)

    async def delete_tasks(self, task_ids: Iterable[int]) -> None:
        try:
            await asyncio.to_thread(self._delete_sync, list(task_ids))
        except Exception:
            logger.warning("Semantic index cleanup failed", exc_info=True)

    async def health(self) -> Optional[int]:
        """Number of indexed commitments, or None when the store cannot be opened."""

        def count() -> Optional[int]:
            collection = self._get_collection()
            return None if collection is None else collection.count()

        return await asyncio.to_thread(count)

    @observe("semantic-search", as_type="retriever", capture_input=True, capture_output=True)
    async def search(self, owner_id: int, query: str, limit: Optional[int] = None) -> Optional[List[Dict[str, Any]]]:
        """Returns None when search is unavailable, so callers can say so instead of showing nothing."""
        if not self.enabled:
            return None
        try:
            return await asyncio.to_thread(self._search_sync, owner_id, query, limit or settings.SEMANTIC_SEARCH_RESULTS)
        except Exception:
            logger.warning("Semantic search failed", exc_info=True)
            return None


vector_store = VectorStoreService()
