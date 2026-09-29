from fastapi import APIRouter

from app.controllers.settings_controller import public_config
from app.schemas.settings import PublicConfig

router = APIRouter(tags=["Config"])


@router.get("/config", response_model=PublicConfig)
async def get_public_config() -> PublicConfig:
    """Non-secret settings the web app needs before sign-in (demo mode, input limits)."""
    return public_config()
