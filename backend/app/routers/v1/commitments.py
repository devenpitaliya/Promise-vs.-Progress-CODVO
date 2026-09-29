from typing import List, Optional

from fastapi import APIRouter, Query, status

from app.dependencies.controllers import CommitmentCtl
from app.enums import ApprovalStatus, TaskStatus
from app.models.task import Task
from app.schemas.task import (
    RetryFailedRequest,
    RetryFailedResult,
    ReviewRequest,
    ReviewResult,
    SearchResponse,
    SimulatedSyncResult,
    SimulateStateRequest,
    TaskCreate,
    TaskResponse,
    TaskUpdate,
)

router = APIRouter(prefix="/commitments", tags=["Commitments"])


@router.get("/", response_model=List[TaskResponse])
async def list_commitments(
    controller: CommitmentCtl,
    meeting_id: Optional[int] = None,
    approval_status: Optional[ApprovalStatus] = None,
    status_filter: Optional[TaskStatus] = Query(default=None, alias="status"),
) -> List[Task]:
    return await controller.list(meeting_id, approval_status, status_filter)


@router.get("/search", response_model=SearchResponse)
async def search_commitments(controller: CommitmentCtl, q: str = Query(min_length=2, max_length=200)) -> SearchResponse:
    return await controller.search(q)


@router.post("/", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_commitment(payload: TaskCreate, controller: CommitmentCtl) -> Task:
    return await controller.create(payload)


@router.post("/review", response_model=ReviewResult)
async def review_commitments(payload: ReviewRequest, controller: CommitmentCtl, meeting_id: int = Query(...)) -> ReviewResult:
    """Human-in-the-loop decision. Only the IDs listed are approved or rejected."""
    return await controller.review(meeting_id, payload)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_commitment(task_id: int, controller: CommitmentCtl) -> Task:
    return await controller.get_owned(task_id)


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_commitment(task_id: int, payload: TaskUpdate, controller: CommitmentCtl) -> Task:
    return await controller.update(task_id, payload)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_commitment(task_id: int, controller: CommitmentCtl) -> None:
    await controller.delete(task_id)


@router.post("/retry-failed", response_model=RetryFailedResult)
async def retry_failed_syncs(payload: RetryFailedRequest, controller: CommitmentCtl) -> RetryFailedResult:
    """Retry every approved commitment whose ticket could not be created, optionally fixing repository and references."""
    return await controller.retry_failed(payload)


@router.post("/sync-simulated", response_model=SimulatedSyncResult)
async def sync_simulated_commitments(controller: CommitmentCtl) -> SimulatedSyncResult:
    """After connecting GitHub or Jira: create or link real tickets for commitments tracked in simulation."""
    return await controller.sync_simulated()


@router.post("/{task_id}/sync", response_model=TaskResponse)
async def retry_sync(task_id: int, controller: CommitmentCtl) -> Task:
    return await controller.retry_sync(task_id)


@router.post("/{task_id}/simulate", response_model=TaskResponse)
async def simulate_github_state(task_id: int, payload: SimulateStateRequest, controller: CommitmentCtl) -> Task:
    return await controller.simulate(task_id, payload)
