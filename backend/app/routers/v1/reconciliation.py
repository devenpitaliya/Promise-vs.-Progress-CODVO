from typing import Optional

from fastapi import APIRouter

from app.dependencies.controllers import ReconciliationCtl
from app.schemas.integration import SlackPostResponse
from app.schemas.reconciliation import ReconcileRequest, ReconciliationReport

router = APIRouter(prefix="/reconciliation", tags=["Reconciliation"])


@router.get("/report", response_model=ReconciliationReport)
async def get_report(controller: ReconciliationCtl, meeting_id: Optional[int] = None) -> ReconciliationReport:
    """Evaluate tracked commitments from stored state. Read-only."""
    return await controller.report(meeting_id)


@router.post("/run", response_model=ReconciliationReport)
async def run_reconciliation(payload: ReconcileRequest, controller: ReconciliationCtl) -> ReconciliationReport:
    """Query GitHub for the current state of every tracked commitment, then evaluate."""
    return await controller.run(payload)


@router.post("/reminders/slack", response_model=SlackPostResponse)
async def remind_on_slack(controller: ReconciliationCtl, meeting_id: Optional[int] = None) -> SlackPostResponse:
    """Post commitments that need attention to the connected Slack channel, grouped by owner."""
    return await controller.remind_on_slack(meeting_id)
