from fastapi import APIRouter

from app.controllers.settings_controller import system_status
from app.dependencies import CurrentUser
from app.dependencies.controllers import SettingsCtl
from app.dependencies.database import DbSession
from app.schemas.settings import AiSettingsResponse, SystemStatus, TestAiKeyRequest, TestAiKeyResponse, UpdateAiSettingsRequest

router = APIRouter(prefix="/settings", tags=["Settings"])


@router.get("/ai", response_model=AiSettingsResponse)
async def get_ai_settings(controller: SettingsCtl) -> AiSettingsResponse:
    return controller.ai_settings()


@router.put("/ai", response_model=AiSettingsResponse)
async def update_ai_settings(payload: UpdateAiSettingsRequest, controller: SettingsCtl) -> AiSettingsResponse:
    return await controller.update_ai_settings(payload)


@router.post("/ai/test", response_model=TestAiKeyResponse)
async def test_ai_key(payload: TestAiKeyRequest, controller: SettingsCtl) -> TestAiKeyResponse:
    return await controller.test_key(payload)


@router.get("/system", response_model=SystemStatus)
async def get_system_status(user: CurrentUser, db: DbSession) -> SystemStatus:
    return await system_status(db, user)
