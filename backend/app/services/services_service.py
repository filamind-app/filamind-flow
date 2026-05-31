"""Klipper / Moonraker service control.

Lists the host's firmware-related systemd units and starts / stops / restarts
them, so the user (or a flash workflow) can free or restore Klipper without a
shell. Privileged actions go through passwordless sudo — the same sudoers rule
the flasher relies on. The panel's own service is never touched.
"""

from __future__ import annotations

import asyncio
from typing import Any

#: Never start/stop our own backend service from the services manager.
_PROTECTED = ("filamind",)
#: Bring low-level MCUs up first; tear them down last (reverse on stop).
_ORDER = ("klipper-mcu", "klipper", "moonraker")

VALID_ACTIONS = ("start", "stop", "restart")


async def _run(cmd: list[str]) -> tuple[int, str]:
    """Runs a command, returning (returncode, combined output)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        out, _ = await proc.communicate()
    except (OSError, NotImplementedError) as exc:
        return 1, str(exc)
    return proc.returncode or 0, out.decode(errors="replace")


def _parse_services(out: str) -> list[dict[str, Any]]:
    """Parses ``systemctl list-units --plain`` rows, dropping protected units."""
    services: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 3 or not parts[0].endswith(".service"):
            continue
        name = parts[0][: -len(".service")]
        if name in seen or any(p in name for p in _PROTECTED):
            continue
        seen.add(name)
        services.append({"name": name, "active": parts[2] == "active"})
    return services


async def list_services() -> list[dict[str, Any]]:
    """Lists klipper* / moonraker* systemd services with their active state."""
    _, out = await _run(
        [
            "systemctl",
            "list-units",
            "--type=service",
            "--all",
            "--plain",
            "--no-legend",
            "klipper*",
            "moonraker*",
        ]
    )
    return _parse_services(out)


def _order_key(name: str, action: str) -> int:
    """Orders units so dependencies start before, and stop after, their users."""
    rank = next((i for i, part in enumerate(_ORDER) if part in name), len(_ORDER))
    return rank if action == "start" else -rank


async def manage_services(action: str) -> list[dict[str, Any]]:
    """Runs ``action`` (start/stop/restart) on every klipper*/moonraker* unit."""
    services = sorted(await list_services(), key=lambda s: _order_key(s["name"], action))
    results: list[dict[str, Any]] = []
    for svc in services:
        code, _ = await _run(["sudo", "-n", "systemctl", action, svc["name"]])
        results.append({"name": svc["name"], "ok": code == 0})
    return results
