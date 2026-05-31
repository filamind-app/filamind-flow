"""In-memory store of background tasks (batch build / flash runs).

A batch operation can take minutes and the user wants to watch it and be able to
stop it, so it runs as a background task whose log + status the UI polls. Tasks
are ephemeral — held in memory, lost on restart — which is fine for something you
start and watch live. Completed tasks are capped so the store can't grow forever.
"""

from __future__ import annotations

import uuid

_MAX_TASKS = 50


class Task:
    """A single background run: its accumulating log, status, and cancel flag."""

    def __init__(self, task_id: str) -> None:
        self.id = task_id
        #: running / done / cancelled / failed.
        self.status = "running"
        self.log = ""
        self.cancelled = False

    def append(self, text: str) -> None:
        self.log += text

    def as_dict(self) -> dict[str, object]:
        return {"id": self.id, "status": self.status, "log": self.log, "cancelled": self.cancelled}


_tasks: dict[str, Task] = {}
_order: list[str] = []


def create_task() -> Task:
    """Creates and registers a new running task, evicting the oldest if full."""
    task = Task(f"task_{uuid.uuid4().hex[:12]}")
    _tasks[task.id] = task
    _order.append(task.id)
    while len(_order) > _MAX_TASKS:
        _tasks.pop(_order.pop(0), None)
    return task


def get_task(task_id: str) -> Task | None:
    """Returns a task by id, or None."""
    return _tasks.get(task_id)


def cancel_task(task_id: str) -> bool:
    """Flags a task to stop at its next checkpoint. False if it is unknown."""
    task = _tasks.get(task_id)
    if task is None:
        return False
    task.cancelled = True
    return True
