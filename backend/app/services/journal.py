"""Printer journal — one timeline of everything that happened to the machine.

Merges the per-feature histories the app already keeps — firmware flashes (``flashed.json``),
config saves (the ``filamind-backups/`` snapshots), and tuning runs (the input-shaper archive) —
into a single newest-first event list. Events carry stable ``kind`` + ``params`` (the frontend
translates; no English leaks from here).
"""

from __future__ import annotations

from typing import Any

import httpx

from app.services import config_service, shaper_archive, version_store
from app.services.moonraker_client import MoonrakerClient

_MAX_EVENTS = 100


def _flash_events(data_dir: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for board_id, record in version_store.flash_records(data_dir).items():
        if not isinstance(record, dict):
            continue
        at = record.get("flashed_at")
        if not at:
            continue
        out.append(
            {
                "at": str(at),
                "kind": "flash",
                "params": {
                    "board": board_id,
                    "profile": record.get("profile"),
                    "version": record.get("version"),
                },
            }
        )
    return out


async def _config_events(client: MoonrakerClient) -> list[dict[str, Any]]:
    try:
        backups = await config_service.list_backups(client)
    except httpx.HTTPError:
        return []
    out: list[dict[str, Any]] = []
    for b in backups.get("backups", []):
        stamp = str(b.get("stamp", ""))
        # 20260612-014530 → 2026-06-12T01:45:30 (sortable alongside the other ISO stamps)
        at = (
            f"{stamp[0:4]}-{stamp[4:6]}-{stamp[6:8]}T{stamp[9:11]}:{stamp[11:13]}:{stamp[13:15]}"
            if len(stamp) == 15
            else stamp
        )
        out.append(
            {
                "at": at,
                "kind": "config_save",
                "params": {"file": str(b.get("flat", "")).replace("_", "/")},
            }
        )
    return out


def _tuning_events(data_dir: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for run in shaper_archive.read_index(data_dir):
        at = run.get("at")
        if not at:
            continue
        summary = run.get("summary")
        summary = summary if isinstance(summary, dict) else {}
        out.append(
            {
                "at": str(at),
                "kind": "tuning",
                "params": {
                    "run_kind": run.get("kind"),
                    "axis": run.get("axis"),
                    "shaper": summary.get("shaper"),
                    "freq": summary.get("freq"),
                },
            }
        )
    return out


async def gather_journal(client: MoonrakerClient, data_dir: str) -> dict[str, Any]:
    """The merged, newest-first machine timeline (capped at the most recent events)."""
    events = _flash_events(data_dir) + _tuning_events(data_dir)
    events += await _config_events(client)
    events.sort(key=lambda e: str(e["at"]), reverse=True)
    return {"events": events[:_MAX_EVENTS]}
