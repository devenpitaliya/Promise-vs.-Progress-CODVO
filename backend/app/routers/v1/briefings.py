from typing import List

from fastapi import APIRouter, status

from app.dependencies.controllers import BriefingCtl
from app.models.audit import EmailLog
from app.schemas.briefing import (
    AuditRunResponse,
    BriefingPreview,
    BriefingRequest,
    EmailLogResponse,
    ScheduleAuditRequest,
    ScheduledAuditResponse,
    SendBriefingRequest,
    SendBriefingResponse,
)
from app.schemas.integration import SlackPostRequest, SlackPostResponse

router = APIRouter(prefix="/briefings", tags=["Briefings"])


@router.post("/preview", response_model=BriefingPreview)
async def preview_briefing(payload: BriefingRequest, controller: BriefingCtl) -> BriefingPreview:
    return await controller.preview(payload)


@router.post("/send", response_model=SendBriefingResponse)
async def send_briefing(payload: SendBriefingRequest, controller: BriefingCtl) -> SendBriefingResponse:
    return await controller.send(payload)


@router.post("/slack", response_model=SlackPostResponse)
async def post_briefing_to_slack(payload: SlackPostRequest, controller: BriefingCtl) -> SlackPostResponse:
    """Post the pre-meeting briefing to the connected Slack channel."""
    return await controller.post_to_slack(payload)


@router.get("/emails", response_model=List[EmailLogResponse])
async def email_history(controller: BriefingCtl) -> List[EmailLog]:
    return await controller.email_history()


@router.post("/schedules", response_model=ScheduledAuditResponse, status_code=status.HTTP_201_CREATED)
async def create_schedule(payload: ScheduleAuditRequest, controller: BriefingCtl) -> ScheduledAuditResponse:
    return await controller.create_schedule(payload)


@router.get("/schedules", response_model=List[ScheduledAuditResponse])
async def list_schedules(controller: BriefingCtl) -> List[ScheduledAuditResponse]:
    return await controller.list_schedules()


@router.delete("/schedules/{audit_id}", response_model=ScheduledAuditResponse)
async def cancel_schedule(audit_id: int, controller: BriefingCtl) -> ScheduledAuditResponse:
    return await controller.cancel_schedule(audit_id)


@router.post("/schedules/{audit_id}/run", response_model=AuditRunResponse)
async def run_schedule_now(audit_id: int, controller: BriefingCtl) -> AuditRunResponse:
    return await controller.run_schedule_now(audit_id)
