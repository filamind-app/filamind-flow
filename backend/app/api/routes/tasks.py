"""Generic supervised-task endpoints — poll progress / collect the result / cancel.

Long actuating runs (the vibrations profile, a max-flow ramp) start via their own widget
endpoints, run in the background under the printer guard, and report here. The result is held
on the task, so a dropped tab or proxy timeout no longer loses a minutes-long run's outcome.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.models.schemas import TaskStatus
from app.services import task_store

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/{task_id}", response_model=TaskStatus)
async def get_task(task_id: str) -> TaskStatus:
    """A supervised task's status, structured progress, log, and (when finished) result."""
    task = task_store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    return TaskStatus.model_validate(task.as_dict())


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str) -> dict[str, str]:
    """Flag a supervised task to stop at its next checkpoint (its cleanup always runs)."""
    if not task_store.cancel_task(task_id):
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    return {"status": "cancelling"}
