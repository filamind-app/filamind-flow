"""One printer-wide guard for every actuating operation.

Two protections, shared by all widgets:

* :func:`is_busy` — the single definition of "the printer is busy" (printing / paused / error),
  replacing the per-service copies that had drifted apart.
* :func:`acquire` — a process-wide mutual-exclusion slot for operations that move the machine or
  write to it (resonance tests, max-flow runs, driver writes, firmware flashes, restarts). Two
  browser tabs — or a retried request after a proxy timeout — can no longer interleave G-code on
  a hot, moving machine: the second caller is refused with the name of the operation already
  running.

Operations are identified by stable snake_case KEYS (``resonance_test``, ``max_flow``, …) so the
frontend can localise them; :func:`status` exposes the slot for the shell's polling badge.

Single-process by design: the app runs as one uvicorn worker, and the check-and-set in
:func:`acquire` happens synchronously (no ``await`` between check and set), so it is race-free
within the event loop.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Protocol


class _QueryClient(Protocol):
    async def query_objects(self, objects: list[str]) -> dict[str, Any]: ...


#: Print states during which actuating writes are refused.
_BUSY_STATES = ("printing", "paused", "error")

#: The operation currently holding the exclusive slot (None = free).
_current_op: str | None = None


class GuardBusyError(RuntimeError):
    """Raised when an actuating operation is refused because another one is already running."""

    def __init__(self, operation: str) -> None:
        super().__init__(f"Another operation is already running: {operation}")
        self.operation = operation


async def is_busy(client: _QueryClient, *, block_on_error: bool = True) -> bool:
    """True while the printer is printing / paused (and, by default, in an error state).

    The one shared busy definition — every gated write/motion path should call this instead of
    re-reading ``print_stats`` itself.
    """
    status_ = await client.query_objects(["print_stats"])
    stats = status_.get("print_stats")
    stats = stats if isinstance(stats, dict) else {}
    state = str(stats.get("state", "")).lower()
    states = _BUSY_STATES if block_on_error else ("printing", "paused")
    return state in states


@asynccontextmanager
async def acquire(operation: str) -> AsyncIterator[None]:
    """Hold the printer's exclusive actuating slot for the duration of ``operation``.

    Raises :class:`GuardBusyError` (naming the running operation) when the slot is taken.
    """
    global _current_op
    if _current_op is not None:
        raise GuardBusyError(_current_op)
    _current_op = operation
    try:
        yield
    finally:
        _current_op = None


def status() -> dict[str, Any]:
    """The slot's current state — ``{"locked": bool, "operation": key | None}``."""
    return {"locked": _current_op is not None, "operation": _current_op}


async def guarded_stream(operation: str, inner: AsyncIterator[str]) -> AsyncIterator[str]:
    """Wrap a streaming generator (e.g. a flash log) so the slot is held while it runs.

    When the slot is already taken, a single error line is emitted instead of the stream and the
    inner generator is never started.
    """
    try:
        async with acquire(operation):
            async for chunk in inner:
                yield chunk
    except GuardBusyError as exc:
        yield f"ERROR: another operation is already running: {exc.operation}\n"
