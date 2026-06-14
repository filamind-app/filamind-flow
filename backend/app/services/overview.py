"""Mission-control overview — one call that answers "is my printer healthy?".

A thin, concurrent fan-out over data the app already computes: the live print state, per-MCU
firmware sync (computed for the Firmware Manager but never rendered as a table until now), the
latest tuning result per axis from the input-shaper archive, and whether the hardware changed
against the saved Machine Map baseline. Each block degrades independently (``reachable`` /
``available`` flags) so a down Moonraker still renders a truthful home page.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.config import Settings
from app.services import (
    board_topology,
    firmware_service,
    max_flow_store,
    shaper_archive,
    topology_snapshot,
)
from app.services.moonraker_client import MoonrakerClient


async def _printer_block(client: MoonrakerClient) -> dict[str, Any]:
    try:
        objs = await client.query_objects(["print_stats", "display_status"])
    except Exception:
        return {"reachable": False}
    stats = objs.get("print_stats")
    stats = stats if isinstance(stats, dict) else {}
    display = objs.get("display_status")
    display = display if isinstance(display, dict) else {}
    progress = display.get("progress")
    return {
        "reachable": True,
        "state": str(stats.get("state", "unknown")).lower() or "unknown",
        "filename": stats.get("filename") or None,
        "progress": float(progress) if isinstance(progress, (int, float)) else None,
        "print_duration": stats.get("print_duration"),
    }


async def _firmware_block(settings: Settings) -> dict[str, Any]:
    try:
        out = await firmware_service.gather_status(
            settings.moonraker_url, settings.klipper_dir, settings.katapult_dir, settings.data_dir
        )
    except Exception:
        return {"available": False, "mcus": []}
    host = out.get("host")
    host = host if isinstance(host, dict) else {}
    mcus = [
        {"name": m.get("name"), "version": m.get("version"), "in_sync": m.get("in_sync")}
        for m in out.get("mcus", [])
    ]
    return {
        "available": True,
        "host_version": host.get("version"),
        "mcus": mcus,
        "out_of_sync": sum(1 for m in mcus if m["in_sync"] is False),
    }


def _tuning_block(data_dir: str) -> dict[str, Any]:
    """Latest shaper run per axis from the archive index (summaries only — never reads CSVs)."""
    try:
        runs = shaper_archive.read_index(data_dir)
    except Exception:
        return {"available": False, "axes": []}
    latest: dict[str, dict[str, Any]] = {}
    for run in runs:  # index is newest-first; keep the first (= latest) per axis
        # Saved [input_shaper] configs are archived as kind "config"; older builds used "shaper".
        if str(run.get("kind", "")) not in ("config", "shaper"):
            continue
        summary = run.get("summary")
        summary = summary if isinstance(summary, dict) else {}
        axis = str(run.get("axis") or summary.get("axis") or "").lower()
        if not axis or axis in latest:
            continue
        latest[axis] = {
            "axis": axis,
            "shaper": summary.get("shaper"),
            "freq": summary.get("freq"),
            "grade": summary.get("grade"),
            "created": run.get("at") or run.get("created"),
        }
    return {"available": True, "axes": sorted(latest.values(), key=lambda a: str(a["axis"]))}


def _maxflow_block(data_dir: str) -> dict[str, Any]:
    """The last Max-Flow run's headline numbers, from the small store the widget writes after a
    test (summaries only; never reruns anything). Degrades to ``available: False`` when no run
    has been recorded yet."""
    last = max_flow_store.read_last(data_dir)
    if not isinstance(last, dict) or not isinstance(last.get("max_flow_mm3s"), (int, float)):
        return {"available": False}
    return {
        "available": True,
        "max_flow_mm3s": last.get("max_flow_mm3s"),
        "expected_max_flow_mm3s": last.get("expected_max_flow_mm3s"),
        "hotend": last.get("hotend"),
        "at": last.get("at"),
    }


async def _setup_block(client: MoonrakerClient, data_dir: str) -> dict[str, Any]:
    """Onboarding facts the home's Get-Started checklist needs: how many MCUs have an
    identified board, and whether any motors are assigned. (Baseline / firmware / tuning
    status already live in their own blocks.)"""
    from app.services import motor_mapping

    identified = 0
    total = 0
    try:
        topo = await board_topology.gather_topology(client, data_dir)
        mcus = topo.get("mcus", [])
        total = len(mcus)
        identified = sum(1 for m in mcus if m.get("board_id"))
    except Exception:
        pass
    return {
        "boards_identified": identified,
        "boards_total": total,
        "motors_assigned": len(motor_mapping.read_mapping(data_dir)),
    }


async def _hardware_block(client: MoonrakerClient, data_dir: str) -> dict[str, Any]:
    baseline = topology_snapshot.read_snapshot(data_dir)
    if baseline is None:
        return {"available": True, "has_baseline": False, "changes": 0}
    try:
        topo = await board_topology.gather_topology(client, data_dir)
    except Exception:
        return {"available": False, "has_baseline": True, "changes": 0}
    if topo.get("reachable") is False:
        return {"available": False, "has_baseline": True, "changes": 0}
    changes = topology_snapshot.diff(baseline, topo.get("mcus", []))
    return {"available": True, "has_baseline": True, "changes": len(changes)}


async def gather_overview(settings: Settings) -> dict[str, Any]:
    """All home tiles in one concurrent call; each block degrades independently."""
    client = MoonrakerClient(settings.moonraker_url)
    printer, firmware, hardware, setup = await asyncio.gather(
        _printer_block(client),
        _firmware_block(settings),
        _hardware_block(client, settings.data_dir),
        _setup_block(client, settings.data_dir),
    )
    return {
        "printer": printer,
        "firmware": firmware,
        "tuning": _tuning_block(settings.data_dir),
        "max_flow": _maxflow_block(settings.data_dir),
        "hardware": hardware,
        "setup": setup,
    }
