from fastapi import APIRouter

from app.config import settings
from app.routers.v1 import auth, briefings, commitments, config, integrations, meetings, reconciliation
from app.routers.v1 import settings as settings_routes

api_router = APIRouter(prefix=settings.API_PREFIX)

for module in (config, auth, meetings, commitments, reconciliation, briefings, integrations, settings_routes):
    api_router.include_router(module.router)
