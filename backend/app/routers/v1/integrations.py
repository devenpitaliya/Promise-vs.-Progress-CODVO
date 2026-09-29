from fastapi import APIRouter

from app.dependencies.controllers import IntegrationCtl
from app.schemas.integration import (
    DefaultTrackerRequest,
    IntegrationsResponse,
    IntegrationStatus,
    SaveIntegrationRequest,
    TestIntegrationResponse,
)

router = APIRouter(prefix="/integrations", tags=["Integrations"])


@router.get("/", response_model=IntegrationsResponse)
async def list_integrations(controller: IntegrationCtl) -> IntegrationsResponse:
    """Every supported tool, whether it is connected (yours, the server default, or none) and its fields."""
    return await controller.list()


@router.put("/default-tracker", response_model=IntegrationsResponse)
async def set_default_tracker(payload: DefaultTrackerRequest, controller: IntegrationCtl) -> IntegrationsResponse:
    return await controller.set_default_tracker(payload)


@router.put("/{kind}", response_model=IntegrationStatus)
async def save_integration(kind: str, payload: SaveIntegrationRequest, controller: IntegrationCtl) -> IntegrationStatus:
    """Save your connection. Secrets are encrypted at rest and only ever returned masked."""
    return await controller.save(kind, payload)


@router.delete("/{kind}", response_model=IntegrationStatus)
async def disconnect_integration(kind: str, controller: IntegrationCtl) -> IntegrationStatus:
    return await controller.disconnect(kind)


@router.post("/{kind}/test", response_model=TestIntegrationResponse)
async def test_integration(kind: str, controller: IntegrationCtl) -> TestIntegrationResponse:
    """Check the connection with a real API call (Slack posts a short test message)."""
    return await controller.test(kind)
