import json
import logging
from datetime import UTC, datetime
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.integration import Integration
from app.models.user import User
from app.repositories import IntegrationRepository
from app.schemas.integration import (
    DefaultTrackerRequest,
    IntegrationField,
    IntegrationsResponse,
    IntegrationStatus,
    SaveIntegrationRequest,
    TestIntegrationResponse,
)
from app.services.connectors import CONNECTORS, TRACKER_KINDS, ConnectorConfigError, TrackerConnector, build, is_available, secret_names
from app.services.connectors.registry import user_config
from app.utils.exceptions import ConflictError, InvalidRequestError, NotFoundError, RateLimitedError
from app.utils.rate_limit import SlidingWindowLimiter
from app.utils.security import decrypt_secret, encrypt_secret, mask_secret

logger = logging.getLogger(__name__)

integration_test_limiter = SlidingWindowLimiter(max_events=settings.INTEGRATION_TESTS_PER_5_MIN, window_seconds=300)


def _connector_class(kind: str):
    if kind not in CONNECTORS:
        raise NotFoundError(f"Unknown integration '{kind}'")
    return CONNECTORS[kind]


def _require_available(kind: str) -> None:
    if not is_available(kind):
        raise ConflictError(f"{CONNECTORS[kind].label} is coming soon.")


def _stored_secrets(integration: Optional[Integration]) -> Dict[str, str]:
    if integration is None:
        return {}
    return json.loads(decrypt_secret(integration.secrets_encrypted) or "{}")


class IntegrationController:
    def __init__(self, db: AsyncSession, user: User):
        self.db = db
        self.user = user
        self.repo = IntegrationRepository(db)

    def _status(self, kind: str, stored: Optional[Integration]) -> IntegrationStatus:
        connector_class = _connector_class(kind)
        connector = build(kind, stored)
        secrets = _stored_secrets(stored)
        return IntegrationStatus(
            kind=kind,
            label=connector_class.label,
            category="tracker" if issubclass(connector_class, TrackerConnector) else "notifier",
            available=is_available(kind),
            fields=[IntegrationField(**f.__dict__) for f in connector_class.fields],
            source=connector.source if connector.is_configured() else "none",
            mode=connector.mode,
            has_user_connection=stored is not None,
            config={k: str(v) for k, v in (stored.config if stored else {}).items()},
            secrets_masked={name: mask_secret(secrets.get(name)) for name in secret_names(kind)},
            last_tested_at=stored.last_tested_at if stored else None,
            last_test_ok=stored.last_test_ok if stored else None,
            last_test_message=stored.last_test_message if stored else None,
        )

    async def list(self) -> IntegrationsResponse:
        stored = {i.kind: i for i in await self.repo.list_for_owner(self.user.id)}
        return IntegrationsResponse(
            integrations=[self._status(kind, stored.get(kind)) for kind in CONNECTORS],
            default_tracker=self.user.default_tracker
            if self.user.default_tracker in TRACKER_KINDS and is_available(self.user.default_tracker)
            else "github",  # type: ignore[arg-type]
        )

    async def save(self, kind: str, payload: SaveIntegrationRequest) -> IntegrationStatus:
        connector_class = _connector_class(kind)
        _require_available(kind)
        known = {f.name for f in connector_class.fields}
        unknown = set(payload.values) - known
        if unknown:
            raise InvalidRequestError(f"Unknown settings for {connector_class.label}: {', '.join(sorted(unknown))}")

        stored = await self.repo.get_for_owner(self.user.id, kind)
        secret_fields = set(secret_names(kind))
        merged: Dict[str, Any] = user_config(stored) if stored else {}
        for name, value in payload.values.items():
            if value:
                merged[name] = value
            elif name not in secret_fields:
                merged.pop(name, None)  # an empty setting clears it; an empty secret keeps the saved one

        try:
            validate = getattr(connector_class, "validate", None)
            merged = validate(dict(merged)) if validate else merged
        except ConnectorConfigError as exc:
            raise InvalidRequestError(str(exc)) from exc
        if not connector_class(merged).is_configured():
            missing = [f.label for f in connector_class.fields if f.required and not merged.get(f.name)]
            hint = f"Missing: {', '.join(missing)}." if missing else "Add a webhook URL, or a bot token and a channel."
            raise InvalidRequestError(f"{connector_class.label} is not fully configured. {hint}")

        config = {k: v for k, v in merged.items() if k not in secret_fields}
        secrets = {k: v for k, v in merged.items() if k in secret_fields}
        if stored is None:
            stored = await self.repo.add(Integration(owner_id=self.user.id, kind=kind, config=config))
        stored.config = config
        stored.secrets_encrypted = encrypt_secret(json.dumps(secrets))
        stored.enabled = True
        stored.last_tested_at = stored.last_test_ok = stored.last_test_message = None
        await self.db.flush()
        logger.info("User %s saved the %s integration", self.user.id, kind)
        return self._status(kind, stored)

    async def disconnect(self, kind: str) -> IntegrationStatus:
        _connector_class(kind)
        stored = await self.repo.get_for_owner(self.user.id, kind)
        if stored is not None:
            await self.repo.delete(stored)
            logger.info("User %s disconnected the %s integration", self.user.id, kind)
        return self._status(kind, None)

    async def test(self, kind: str) -> TestIntegrationResponse:
        """Real, harmless API call with the active credentials (yours, else the server's)."""
        _connector_class(kind)
        _require_available(kind)
        if not integration_test_limiter.hit(f"{self.user.id}:{kind}"):
            raise RateLimitedError("Too many connection tests. Try again in a few minutes.")
        stored = await self.repo.get_for_owner(self.user.id, kind)
        result = await build(kind, stored).test()
        now = datetime.now(UTC)
        if stored is not None:
            stored.last_tested_at, stored.last_test_ok, stored.last_test_message = now, result.ok, result.message[:500]
            await self.db.flush()
        logger.info("User %s tested the %s integration: %s", self.user.id, kind, "ok" if result.ok else "failed")
        return TestIntegrationResponse(ok=result.ok, message=result.message, tested_at=now)

    async def set_default_tracker(self, payload: DefaultTrackerRequest) -> IntegrationsResponse:
        _require_available(payload.default_tracker)
        self.user.default_tracker = payload.default_tracker
        await self.db.flush()
        return await self.list()
