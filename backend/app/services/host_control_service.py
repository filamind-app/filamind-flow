"""Linux host control — read the printer host's OS state (and, in later phases, change it).

The FilaMind backend runs *on* the printer host, so most of the read-only monitor comes straight
from stdlib (``os``/``shutil``/``/proc``/``/sys``) with no subprocess and no sudo; a few items
(top processes, Wi-Fi, timezone/NTP, locale) shell out to read-only commands. Phase 1 is the
monitor only — services, cleanup and the system-changing actions (time/locale/hostname/power) build
on this in later phases and are the parts that gate behind confirmations + sudo.
"""

from __future__ import annotations

import asyncio
import contextlib
import glob
import ipaddress
import os
import platform
import re
import shutil
import socket
import stat
import time
from typing import Any

import httpx

from app.services import printer_guard
from app.services.moonraker_client import MoonrakerClient


async def _run(cmd: list[str], timeout: float = 5.0) -> str:
    """Run a read-only command, returning stdout (empty string on any error/timeout)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except (OSError, NotImplementedError, asyncio.TimeoutError):
        return ""
    return out.decode(errors="replace")


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def _host_block() -> dict[str, Any]:
    osr = _read("/etc/os-release")
    distro = ""
    for line in osr.splitlines():
        if line.startswith("PRETTY_NAME="):
            distro = line.split("=", 1)[1].strip().strip('"')
            break
    # os.uname() is POSIX-only; platform.uname() is the cross-platform fallback (keeps the local
    # Windows dev/test run from crashing — the real host is always Linux).
    uname = platform.uname()
    uptime_s: float | None = None
    up = _read("/proc/uptime").split()
    if up:
        try:
            uptime_s = float(up[0])
        except ValueError:
            uptime_s = None
    return {
        "hostname": socket.gethostname(),
        "distro": distro,
        "kernel": uname.release,
        "arch": uname.machine,
        "uptime_s": uptime_s,
    }


def _cpu_block() -> dict[str, Any]:
    temp_c: float | None = None
    # Prefer the thermal zone whose type looks like a CPU/SoC sensor; else the first one.
    zones = sorted(glob.glob("/sys/class/thermal/thermal_zone*"))
    for z in zones:
        raw = _read(os.path.join(z, "temp")).strip()
        if raw:
            try:
                temp_c = round(int(raw) / 1000.0, 1)
                break
            except ValueError:
                continue
    load: list[float] | None = None
    getloadavg = getattr(os, "getloadavg", None)  # POSIX-only
    if getloadavg is not None:
        try:
            load = [round(x, 2) for x in getloadavg()]
        except OSError:
            load = None
    return {"temp_c": temp_c, "load": load, "cores": os.cpu_count()}


def _memory_block() -> dict[str, int]:
    fields = {"MemTotal": 0, "MemAvailable": 0, "SwapTotal": 0, "SwapFree": 0}
    for line in _read("/proc/meminfo").splitlines():
        key, _, rest = line.partition(":")
        if key in fields:
            with contextlib.suppress(ValueError, IndexError):
                fields[key] = int(rest.strip().split()[0])  # kB
    total = fields["MemTotal"]
    avail = fields["MemAvailable"]
    swap_total = fields["SwapTotal"]
    return {
        "total_kb": total,
        "available_kb": avail,
        "used_kb": max(0, total - avail),
        "swap_total_kb": swap_total,
        "swap_used_kb": max(0, swap_total - fields["SwapFree"]),
    }


def _disk_block(data_dir: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for label, path in (("/", "/"), ("data", os.path.expanduser(data_dir)), ("/tmp", "/tmp")):
        try:
            usage = shutil.disk_usage(path)
        except OSError:
            continue
        key = f"{usage.total}:{usage.free}"
        if key in seen:  # data_dir often lives on / — don't list the same filesystem twice
            continue
        seen.add(key)
        pct = round(usage.used / usage.total * 100) if usage.total else 0
        out.append(
            {
                "label": label,
                "path": path,
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
                "pct": pct,
            }
        )
    return out


async def _throttle_block() -> dict[str, Any]:
    """Raspberry-Pi under-voltage / throttle flags via ``vcgencmd`` (absent on most other SBCs)."""
    out = (await _run(["vcgencmd", "get_throttled"])).strip()
    if not out or "=" not in out:
        return {"supported": False, "value": None, "undervoltage": None, "flags": []}
    try:
        value = int(out.split("=", 1)[1], 16)
    except ValueError:
        return {"supported": False, "value": None, "undervoltage": None, "flags": []}
    bits = {
        0: "undervoltage_now",
        1: "freq_capped_now",
        2: "throttled_now",
        16: "undervoltage_occurred",
        17: "freq_capped_occurred",
        18: "throttled_occurred",
    }
    flags = [name for bit, name in bits.items() if value & (1 << bit)]
    return {
        "supported": True,
        "value": value,
        "undervoltage": bool(value & (1 << 0) or value & (1 << 16)),
        "flags": flags,
    }


async def _processes_block() -> list[dict[str, Any]]:
    out = await _run(["ps", "-eo", "pid,pcpu,pmem,comm", "--sort=-pcpu", "--no-headers"])
    procs: list[dict[str, Any]] = []
    for line in out.splitlines()[:6]:
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        try:
            procs.append(
                {
                    "pid": int(parts[0]),
                    "cpu": float(parts[1]),
                    "mem": float(parts[2]),
                    "command": parts[3],
                }
            )
        except ValueError:
            continue
    return procs


async def _network_block() -> dict[str, Any]:
    iface = ip = ssid = ""
    signal: int | None = None
    ip_out = await _run(["ip", "-o", "-4", "addr", "show", "scope", "global"])
    for line in ip_out.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[2] == "inet":
            iface = parts[1]
            ip = parts[3].split("/")[0]
            break
    ssid = (await _run(["iwgetid", "-r"])).strip()
    # /proc/net/wireless: signal level (link quality) per wireless iface.
    for line in _read("/proc/net/wireless").splitlines():
        if ":" in line and (not iface or line.strip().startswith(iface)):
            cols = line.split()
            if len(cols) >= 3:
                try:
                    signal = int(float(cols[2].rstrip(".")))
                except ValueError:
                    signal = None
            break
    return {"iface": iface, "ip": ip, "ssid": ssid, "signal": signal}


async def _time_block() -> dict[str, Any]:
    out = await _run(["timedatectl", "show"])
    kv: dict[str, str] = {}
    for line in out.splitlines():
        key, _, val = line.partition("=")
        if key:
            kv[key] = val.strip()
    return {
        "now": kv.get("TimeUSec", ""),
        "timezone": kv.get("Timezone", ""),
        "ntp_enabled": kv.get("NTP", "") == "yes",
        "ntp_synced": kv.get("NTPSynchronized", "") == "yes",
        "rtc": kv.get("RTCTimeUSec", ""),
    }


async def _locale_block() -> dict[str, str]:
    lang = ""
    for line in _read("/etc/default/locale").splitlines():
        if line.startswith("LANG="):
            lang = line.split("=", 1)[1].strip().strip('"')
            break
    if not lang:
        lang = os.environ.get("LANG", "")
    keymap = ""
    for line in (await _run(["localectl", "status"])).splitlines():
        low = line.strip().lower()
        if low.startswith("vc keymap:"):
            keymap = line.split(":", 1)[1].strip()
            break
    return {"lang": lang, "keymap": keymap}


async def monitor(data_dir: str) -> dict[str, Any]:
    """A read-only snapshot of the host's health + OS state for the Host Control widget."""
    throttle, processes, network, time_b, locale = await asyncio.gather(
        _throttle_block(),
        _processes_block(),
        _network_block(),
        _time_block(),
        _locale_block(),
    )
    return {
        "host": _host_block(),
        "cpu": _cpu_block(),
        "memory": _memory_block(),
        "disk": _disk_block(data_dir),
        "throttle": throttle,
        "processes": processes,
        "network": network,
        "time": time_b,
        "locale": locale,
    }


# ── Services (Phase 2) ─────────────────────────────────────────────────────────
# A general systemd unit manager. The backend is the security boundary: it validates the unit
# name, refuses destructive actions on a protected set (so the user can't lock themselves out or
# kill this panel), and path-guards unit-file deletion to /etc/systemd/system. Privileged actions
# go through the host's passwordless-sudo rule (deploy/setup-sudoers.sh).

_SVC = ".service"
_SVC_LEN = len(_SVC)

#: Actions the Services tab can run on a unit.
SERVICE_ACTIONS = ("start", "stop", "restart", "enable", "disable", "mask", "unmask")
#: Actions that take a service away (stop it, prevent it starting, or remove it). These are refused
#: outright on protected units and require a typed confirmation in the UI for everything else.
_DESTRUCTIVE = {"stop", "restart", "disable", "mask", "delete"}

#: Units whose loss would lock the user out, break the host, or kill this panel mid-action.
#: Destructive actions (and deletion) are refused on these regardless of confirmation.
_PROTECTED = {
    "filamind",
    "filamind-flow",
    "filamind-agent",
    "dbus",
    "dbus-broker",
    "systemd-journald",
    "systemd-logind",
    "systemd-udevd",
    "ssh",
    "sshd",
    "polkit",
}
#: Marked "critical" in the UI (extra warning) but still manageable with a typed confirmation.
_CRITICAL_EXTRA = {
    "klipper",
    "klipper-mcu",
    "moonraker",
    "KlipperScreen",
    "NetworkManager",
    "wpa_supplicant",
    "networking",
    "systemd-networkd",
    "systemd-resolved",
    "getty",
}

#: A unit name is a safe argument when it has no shell-hostile or path characters. (We never use a
#: shell — this is belt-and-suspenders + a guard against absurd input.)
_UNIT_RE = re.compile(r"^[A-Za-z0-9@._:\-\\]+$")


def _valid_unit(name: str) -> bool:
    return bool(name) and len(name) <= 255 and _UNIT_RE.match(name) is not None


def _base(name: str) -> str:
    """The template base of an instanced unit (``getty@tty1`` → ``getty``)."""
    return name.split("@", 1)[0]


def _with_suffix(name: str) -> str:
    return name if name.endswith(_SVC) else name + _SVC


def _strip_suffix(name: str) -> str:
    return name[:-_SVC_LEN] if name.endswith(_SVC) else name


def _is_protected(name: str) -> bool:
    base = _strip_suffix(name)
    return base in _PROTECTED or _base(base) in _PROTECTED


def _is_critical(name: str) -> bool:
    base = _strip_suffix(name)
    if _is_protected(name):
        return True
    if base in _CRITICAL_EXTRA or _base(base) in _CRITICAL_EXTRA:
        return True
    return base.startswith("systemd-")


async def _run_rc(cmd: list[str], timeout: float = 10.0) -> tuple[int, str]:
    """Run a command, returning (returncode, combined stdout+stderr). 127 if it can't be run.

    Forces the C locale so tool/sudo messages come back in English — both so our parsers (systemctl,
    timedatectl, nmcli ``-t``/``-g`` are already locale-stable, but sudo's error text isn't) and so
    the "sudo: a password is required" signature stays detectable on a non-English host.
    """
    env = {**os.environ, "LC_ALL": "C", "LANG": "C"}
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, env=env
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except (FileNotFoundError, NotImplementedError):
        return 127, ""
    except (OSError, asyncio.TimeoutError) as exc:
        return 1, str(exc)
    return proc.returncode or 0, out.decode(errors="replace")


async def list_units() -> list[dict[str, Any]]:
    """All systemd .service units (loaded + installed-but-inactive) with their state. Read-only."""
    _, units_out = await _run_rc(
        ["systemctl", "list-units", "--type=service", "--all", "--plain", "--no-legend"]
    )
    _, files_out = await _run_rc(["systemctl", "list-unit-files", "--type=service", "--no-legend"])

    enabled: dict[str, str] = {}
    for line in files_out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].endswith(_SVC):
            enabled[parts[0][:-_SVC_LEN]] = parts[1]  # STATE: enabled/disabled/static/masked/…

    result: dict[str, dict[str, Any]] = {}
    for line in units_out.splitlines():
        parts = line.split(None, 4)
        if len(parts) < 4 or not parts[0].endswith(_SVC):
            continue
        name = parts[0][:-_SVC_LEN]
        result[name] = {
            "name": name,
            "load_state": parts[1],
            "active": parts[2] == "active",
            "active_state": parts[2],
            "sub_state": parts[3],
            "description": parts[4] if len(parts) > 4 else "",
            "enabled": enabled.get(name, ""),
            "critical": _is_critical(name),
            "protected": _is_protected(name),
        }
    # Installed unit files that aren't currently loaded (inactive, absent from list-units).
    for name, state in enabled.items():
        if name not in result:
            result[name] = {
                "name": name,
                "load_state": "",
                "active": False,
                "active_state": "inactive",
                "sub_state": "dead",
                "description": "",
                "enabled": state,
                "critical": _is_critical(name),
                "protected": _is_protected(name),
            }
    return sorted(result.values(), key=lambda s: s["name"])


async def unit_detail(name: str) -> dict[str, Any]:
    """Per-unit detail (fragment path, states) + whether its unit file is safe to delete."""
    if not _valid_unit(name):
        raise ValueError("invalid unit name")
    unit = _with_suffix(name)
    _, out = await _run_rc(
        [
            "systemctl",
            "show",
            unit,
            "--property=Id,Description,LoadState,ActiveState,SubState,UnitFileState,FragmentPath",
        ]
    )
    props: dict[str, str] = {}
    for line in out.splitlines():
        key, _, val = line.partition("=")
        if key:
            props[key] = val
    frag = props.get("FragmentPath", "")
    # Only user-installed units (under /etc/systemd/system) are deletable, and never protected ones.
    can_delete = bool(frag) and frag.startswith("/etc/systemd/system/") and not _is_protected(name)
    return {
        "name": _strip_suffix(name),
        "description": props.get("Description", ""),
        "load_state": props.get("LoadState", ""),
        "active_state": props.get("ActiveState", ""),
        "sub_state": props.get("SubState", ""),
        "enabled": props.get("UnitFileState", ""),
        "fragment_path": frag,
        "can_delete": can_delete,
        "critical": _is_critical(name),
        "protected": _is_protected(name),
    }


async def unit_logs(name: str, lines: int = 200) -> str:
    """Recent journal lines for a unit (read-only)."""
    if not _valid_unit(name):
        raise ValueError("invalid unit name")
    lines = max(1, min(lines, 1000))
    rc, out = await _run_rc(
        [
            "sudo",
            "-n",
            "journalctl",
            "-u",
            _with_suffix(name),
            "-n",
            str(lines),
            "--no-pager",
            "--output=short-iso",
        ]
    )
    if rc == 127:
        return "journalctl is not available on this host."
    return out


async def manage_unit(name: str, action: str) -> dict[str, Any]:
    """Run a systemctl action on a unit. Destructive actions are refused on protected units."""
    if action not in SERVICE_ACTIONS:
        raise ValueError("invalid action")
    if not _valid_unit(name):
        raise ValueError("invalid unit name")
    if action in _DESTRUCTIVE and _is_protected(name):
        return {
            "name": name,
            "action": action,
            "ok": False,
            "refused": True,
            "output": f"'{name}' is protected — {action} is not allowed.",
        }
    rc, out = await _run_rc(["sudo", "-n", "systemctl", action, _with_suffix(name)])
    return {
        "name": name,
        "action": action,
        "ok": rc == 0,
        "refused": False,
        "output": out.strip(),
        "needs_setup": rc != 0 and _needs_setup(out),
    }


async def delete_unit(name: str, confirm: str) -> dict[str, Any]:
    """Remove a user-installed unit file (stop + disable + rm + daemon-reload). Typed-confirm."""
    if not _valid_unit(name):
        raise ValueError("invalid unit name")
    if confirm != _strip_suffix(name):
        return {"name": name, "ok": False, "refused": True, "output": "Confirmation did not match."}
    if _is_protected(name):
        return {"name": name, "ok": False, "refused": True, "output": f"'{name}' is protected."}
    detail = await unit_detail(name)
    frag = detail["fragment_path"]
    if not detail["can_delete"]:
        return {
            "name": name,
            "ok": False,
            "refused": True,
            "output": "Only user-installed unit files under /etc/systemd/system can be removed.",
        }
    unit = _with_suffix(name)
    # Stop + disable first so nothing keeps a dangling reference, then remove and reload. Derive the
    # result from BOTH privileged steps (disable + rm), not just rm — a sudo-grant failure can show
    # up on the disable while rm -f still returns 0 on an already-absent file.
    rc_dis, out_dis = await _run_rc(["sudo", "-n", "systemctl", "disable", "--now", unit])
    rc_rm, out_rm = await _run_rc(["sudo", "-n", "rm", "-f", frag])
    await _run_rc(["sudo", "-n", "systemctl", "daemon-reload"])
    ok = rc_dis == 0 and rc_rm == 0
    needs_setup = (rc_dis != 0 and _needs_setup(out_dis)) or (rc_rm != 0 and _needs_setup(out_rm))
    return {
        "name": name,
        "ok": ok,
        "refused": False,
        "output": (out_rm or out_dis).strip() or f"Removed {frag}",
        "needs_setup": needs_setup,
    }


# ── Disk cleanup (Phase 3) ─────────────────────────────────────────────────────
# Reclaim space from caches and rotated logs the user never needs to keep. Every target offers a
# dry-run "frees X" scan before anything is deleted, and the deletes are tightly scoped: only the
# user's own caches/temp files and rotated (non-live) logs, plus the apt download cache and the
# systemd journal (vacuumed, not erased). User data — G-code, timelapses, configs — is untouched.

#: The cleanup targets, in display order.
CLEANUP_TARGETS = ("apt", "journal", "cache", "tmp", "logs")
#: Only remove /tmp files this old (seconds) — younger files may be in active use.
_TMP_AGE_S = 24 * 3600
#: Vacuum the systemd journal down to this size (keeps recent logs).
_JOURNAL_KEEP = "50M"
#: A file under a log dir is "rotated" (safe to drop) if it isn't the live ``<name>.log``.
_ROTATED_RE = re.compile(r"(\.gz|\.old|\.zip|\.log\.[^/]+|\.\d+)$")


def _dir_size(path: str) -> tuple[int, int]:
    """(total bytes, file count) of a directory tree, ignoring unreadable entries."""
    total = 0
    count = 0
    for root, _dirs, files in os.walk(path, onerror=lambda _e: None):
        for name in files:
            try:
                st = os.lstat(os.path.join(root, name))
            except OSError:
                continue
            if stat.S_ISREG(st.st_mode):
                total += st.st_size
                count += 1
    return total, count


def _rm_contents(path: str) -> tuple[int, int]:
    """Delete the *contents* of a directory (not the directory). Returns (freed bytes, items)."""
    real = os.path.realpath(os.path.expanduser(path))
    if not os.path.isdir(real):
        return 0, 0
    freed = 0
    removed = 0
    for name in os.listdir(real):
        child = os.path.join(real, name)
        try:
            if os.path.islink(child) or os.path.isfile(child):
                size = os.path.getsize(child)
                os.remove(child)
                freed += size
                removed += 1
            elif os.path.isdir(child):
                b, c = _dir_size(child)
                shutil.rmtree(child, ignore_errors=True)
                freed += b
                removed += c
        except OSError:
            continue
    return freed, removed


def _parse_size(text: str) -> int:
    """Parse a human size like ``120.0M`` / ``1.2G`` (journalctl --disk-usage) into bytes."""
    m = re.search(r"([\d.]+)\s*([KMGTP])?", text)
    if not m:
        return 0
    value = float(m.group(1))
    mult = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4, "P": 1024**5}
    return int(value * mult.get(m.group(2) or "", 1))


def _apt_debs() -> list[str]:
    return glob.glob("/var/cache/apt/archives/*.deb") + glob.glob(
        "/var/cache/apt/archives/partial/*.deb"
    )


def _sum_sizes(paths: list[str]) -> int:
    total = 0
    for p in paths:
        try:
            total += os.path.getsize(p)
        except OSError:
            continue
    return total


def _logs_dir(data_dir: str) -> str:
    """The printer's log directory (``~/printer_data/logs``), derived from the data dir."""
    p = os.path.realpath(os.path.expanduser(data_dir))
    for _ in range(4):
        cand = os.path.join(p, "logs")
        if os.path.isdir(cand):
            return cand
        p = os.path.dirname(p)
    home_logs = os.path.expanduser("~/printer_data/logs")
    return home_logs if os.path.isdir(home_logs) else ""


def _rotated_logs(data_dir: str) -> list[str]:
    d = _logs_dir(data_dir)
    if not d:
        return []
    out: list[str] = []
    for root, _dirs, files in os.walk(d, onerror=lambda _e: None):
        for name in files:
            if name.endswith(".log"):
                continue  # keep the live log
            if _ROTATED_RE.search(name):
                out.append(os.path.join(root, name))
    return out


def _tmp_old_files() -> list[str]:
    """Our own regular files under /tmp older than the age cutoff (safe to drop)."""
    if not os.path.isdir("/tmp"):
        return []
    cutoff = time.time() - _TMP_AGE_S
    uid = getattr(os, "getuid", lambda: None)()
    out: list[str] = []
    for name in os.listdir("/tmp"):
        fp = os.path.join("/tmp", name)
        try:
            st = os.lstat(fp)
        except OSError:
            continue
        if not stat.S_ISREG(st.st_mode) or st.st_mtime > cutoff:
            continue
        if uid is not None and st.st_uid != uid:
            continue  # don't touch other users' temp files
        out.append(fp)
    return out


async def _scan_journal_bytes() -> tuple[int, bool]:
    rc, out = await _run_rc(["sudo", "-n", "journalctl", "--disk-usage"])
    if rc != 0 or "take up" not in out:
        return 0, rc != 127
    return _parse_size(out.split("take up", 1)[1]), True


async def _scan_target(tid: str, data_dir: str) -> dict[str, Any]:
    """Dry-run: how much a target would free, without deleting anything."""
    if tid == "apt":
        debs = _apt_debs()
        return {
            "id": tid,
            "bytes": _sum_sizes(debs),
            "count": len(debs),
            "available": os.path.isdir("/var/cache/apt/archives"),
        }
    if tid == "journal":
        b, av = await _scan_journal_bytes()
        return {"id": tid, "bytes": b, "count": 0, "available": av}
    if tid == "cache":
        d = os.path.expanduser("~/.cache")
        b, c = _dir_size(d) if os.path.isdir(d) else (0, 0)
        return {"id": tid, "bytes": b, "count": c, "available": os.path.isdir(d)}
    if tid == "tmp":
        files = _tmp_old_files()
        return {
            "id": tid,
            "bytes": _sum_sizes(files),
            "count": len(files),
            "available": os.path.isdir("/tmp"),
        }
    if tid == "logs":
        files = _rotated_logs(data_dir)
        return {
            "id": tid,
            "bytes": _sum_sizes(files),
            "count": len(files),
            "available": bool(_logs_dir(data_dir)),
        }
    raise ValueError("unknown cleanup target")


def _clean_files(paths: list[str]) -> tuple[int, int]:
    """Delete a list of files (no sudo), returning (freed bytes, removed count)."""
    freed = 0
    removed = 0
    for fp in paths:
        try:
            size = os.path.getsize(fp)
            os.remove(fp)
            freed += size
            removed += 1
        except OSError:
            continue
    return freed, removed


async def _clean_target(tid: str, data_dir: str) -> dict[str, Any]:
    """Perform a target's cleanup. Returns freed bytes + items removed + per-target ok/needs_setup.

    The sudo-backed targets (apt, journal) report ``ok``/``needs_setup`` from the privileged command
    so the UI can flag a missing passwordless-sudo grant instead of silently claiming success.
    """
    if tid == "apt":
        debs = _apt_debs()
        before = _sum_sizes(debs)
        ok = True
        needs_setup = False
        if debs:
            rc, out = await _run_rc(["sudo", "-n", "rm", "-f", *debs])
            ok = rc == 0
            needs_setup = rc != 0 and _needs_setup(out)
        freed = before - _sum_sizes(_apt_debs())
        return {
            "id": tid,
            "freed_bytes": max(0, freed),
            "removed": len(debs),
            "ok": ok,
            "needs_setup": needs_setup,
        }
    if tid == "journal":
        before, _ = await _scan_journal_bytes()
        rc, out = await _run_rc(["sudo", "-n", "journalctl", f"--vacuum-size={_JOURNAL_KEEP}"])
        after, _ = await _scan_journal_bytes()
        return {
            "id": tid,
            "freed_bytes": max(0, before - after),
            "removed": 0,
            "ok": rc == 0,
            "needs_setup": rc != 0 and _needs_setup(out),
        }
    if tid == "cache":
        freed, removed = _rm_contents("~/.cache")
        return {
            "id": tid,
            "freed_bytes": freed,
            "removed": removed,
            "ok": True,
            "needs_setup": False,
        }
    if tid == "tmp":
        freed, removed = _clean_files(_tmp_old_files())
        return {
            "id": tid,
            "freed_bytes": freed,
            "removed": removed,
            "ok": True,
            "needs_setup": False,
        }
    if tid == "logs":
        freed, removed = _clean_files(_rotated_logs(data_dir))
        return {
            "id": tid,
            "freed_bytes": freed,
            "removed": removed,
            "ok": True,
            "needs_setup": False,
        }
    raise ValueError("unknown cleanup target")


async def cleanup_scan(data_dir: str) -> list[dict[str, Any]]:
    """Dry-run every cleanup target (no deletion)."""
    return [await _scan_target(tid, data_dir) for tid in CLEANUP_TARGETS]


async def cleanup_run(ids: list[str], data_dir: str) -> dict[str, Any]:
    """Clean the requested targets; ignores unknown ids. Returns per-target + total freed."""
    results: list[dict[str, Any]] = []
    for tid in ids:
        if tid in CLEANUP_TARGETS:
            results.append(await _clean_target(tid, data_dir))
    return {"results": results, "freed_bytes": sum(r["freed_bytes"] for r in results)}


# ── System settings (Phase 4) ──────────────────────────────────────────────────
# Time / locale / hostname / Wi-Fi / power. Each setter validates its input (and, where there's a
# canonical list, checks membership) before shelling out through the host's passwordless-sudo rule.
# Power actions refuse while a print is in progress. Wi-Fi needs NetworkManager (nmcli); when it's
# absent the feature reports unavailable rather than guessing at the network stack.

_HOSTNAME_RE = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$")
_TIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
_TZ_RE = re.compile(r"^[A-Za-z0-9_+\-/]+$")
_LOCALE_RE = re.compile(r"^[A-Za-z0-9_.@\-]+$")
_KEYMAP_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")
POWER_ACTIONS = ("reboot", "shutdown")


# A passwordless-sudo command fails like this when the sudoers grant isn't installed yet — the one
# manual step (deploy/setup-sudoers.sh). We flag it so the UI can show an actionable hint instead
# of a meaningless "sudo: a password is required".
_SUDO_NOT_GRANTED_RE = re.compile(
    r"a password is required|not allowed to execute|must have a tty|sudo:.*(askpass|required)",
    re.IGNORECASE,
)


def _needs_setup(out: str) -> bool:
    return bool(_SUDO_NOT_GRANTED_RE.search(out))


def _result(rc: int, out: str) -> dict[str, Any]:
    return {
        "ok": rc == 0,
        "refused": False,
        "output": out.strip(),
        "needs_setup": rc != 0 and _needs_setup(out),
    }


def _refused(message: str) -> dict[str, Any]:
    return {"ok": False, "refused": True, "output": message, "needs_setup": False}


def _has_cmd(name: str) -> bool:
    return shutil.which(name) is not None


async def _list_lines(cmd: list[str]) -> list[str]:
    rc, out = await _run_rc(cmd)
    if rc != 0:
        return []
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


async def system_info() -> dict[str, Any]:
    """Current time/locale/hostname/Wi-Fi settings + the option lists the System form offers."""
    timezones, locales, keymaps = await asyncio.gather(
        _list_lines(["timedatectl", "list-timezones"]),
        _list_lines(["localectl", "list-locales"]),
        _list_lines(["localectl", "list-keymaps"]),
    )
    time_b, locale_b, network = await asyncio.gather(_time_block(), _locale_block(), network_info())
    return {
        "timezone": time_b["timezone"],
        "ntp_enabled": time_b["ntp_enabled"],
        "ntp_synced": time_b["ntp_synced"],
        "timezones": timezones,
        "lang": locale_b["lang"],
        "keymap": locale_b["keymap"],
        "locales": locales,
        "keymaps": keymaps,
        "hostname": socket.gethostname(),
        "wifi_available": _has_cmd("nmcli"),
        "network": network,
    }


async def set_timezone(tz: str) -> dict[str, Any]:
    if not _TZ_RE.match(tz):
        raise ValueError("invalid timezone")
    valid = await _list_lines(["timedatectl", "list-timezones"])
    if valid and tz not in valid:
        raise ValueError("unknown timezone")
    return _result(*await _run_rc(["sudo", "-n", "timedatectl", "set-timezone", tz]))


async def set_ntp(enabled: bool) -> dict[str, Any]:
    flag = "true" if enabled else "false"
    return _result(*await _run_rc(["sudo", "-n", "timedatectl", "set-ntp", flag]))


async def set_time(value: str) -> dict[str, Any]:
    if not _TIME_RE.match(value):
        raise ValueError("time must be 'YYYY-MM-DD HH:MM:SS'")
    rc, out = await _run_rc(["sudo", "-n", "timedatectl", "set-time", value])
    # timedatectl refuses to set the clock while NTP is on — surface that as a friendly refusal.
    if rc != 0 and "NTP" in out:
        return _refused("Turn off automatic time (NTP) before setting the clock manually.")
    return _result(rc, out)


async def set_locale(lang: str) -> dict[str, Any]:
    if not _LOCALE_RE.match(lang):
        raise ValueError("invalid locale")
    valid = await _list_lines(["localectl", "list-locales"])
    if valid and lang not in valid:
        raise ValueError("unknown locale")
    return _result(*await _run_rc(["sudo", "-n", "localectl", "set-locale", f"LANG={lang}"]))


async def set_keymap(keymap: str) -> dict[str, Any]:
    if not _KEYMAP_RE.match(keymap):
        raise ValueError("invalid keymap")
    valid = await _list_lines(["localectl", "list-keymaps"])
    if valid and keymap not in valid:
        raise ValueError("unknown keymap")
    return _result(*await _run_rc(["sudo", "-n", "localectl", "set-keymap", keymap]))


async def set_hostname(name: str) -> dict[str, Any]:
    if not _HOSTNAME_RE.match(name):
        raise ValueError("invalid hostname")
    return _result(*await _run_rc(["sudo", "-n", "hostnamectl", "set-hostname", name]))


async def wifi_connect(ssid: str, password: str) -> dict[str, Any]:
    """Join a Wi-Fi network via NetworkManager. The password is never logged."""
    if not _has_cmd("nmcli"):
        return _refused("Wi-Fi editing needs NetworkManager (nmcli), which isn't installed here.")
    if not ssid or len(ssid) > 64 or any(ord(c) < 32 for c in ssid):
        raise ValueError("invalid SSID")
    if password and not (8 <= len(password) <= 63):
        raise ValueError("Wi-Fi password must be 8-63 characters")
    cmd = ["sudo", "-n", "nmcli", "dev", "wifi", "connect", ssid]
    if password:
        cmd += ["password", password]
    rc, out = await _run_rc(cmd, timeout=30.0)
    return _result(rc, out)


async def power(action: str, moonraker_url: str) -> dict[str, Any]:
    """Reboot or shut down the host — refused while a print is in progress."""
    if action not in POWER_ACTIONS:
        raise ValueError("invalid power action")
    try:
        busy = await printer_guard.is_busy(MoonrakerClient(moonraker_url))
    except httpx.HTTPError:
        busy = False  # no reachable Moonraker → Klipper isn't printing
    if busy:
        return _refused("Refused: a print is in progress.")
    unit_action = "reboot" if action == "reboot" else "poweroff"
    return _result(*await _run_rc(["sudo", "-n", "systemctl", unit_action]))


# ── Network / IPv4 (NetworkManager) ────────────────────────────────────────────
# View and switch the panel's active connection between DHCP (auto) and a static IPv4
# (address/CIDR + gateway + DNS). IPv4-only by design. The connection to modify is resolved
# SERVER-SIDE (the active connection on the device that owns the panel's IP) — never taken from the
# client — so a request can't retarget an unrelated profile. Changing the IP of the serving
# connection will drop this panel; the UI warns and tells the user where to reconnect. Refused while
# a print is in progress (a network drop can orphan Moonraker mid-print). nmcli is already granted
# in setup-sudoers.sh, so no new sudoers entry is needed.

NETWORK_MODES = ("auto", "manual")


async def _nmcli_get(field: str, *target: str) -> str:
    """`nmcli -g <field> <target...>` → the raw value (empty on any error)."""
    rc, out = await _run_rc(["nmcli", "-g", field, *target])
    return out.strip() if rc == 0 else ""


async def _nmcli_get_lines(field: str, *target: str) -> list[str]:
    rc, out = await _run_rc(["nmcli", "-g", field, *target])
    return [ln.strip() for ln in out.splitlines() if ln.strip()] if rc == 0 else []


async def network_info() -> dict[str, Any]:
    """The panel's active connection IPv4 config (read-only, no sudo). ``configurable`` is False
    when NetworkManager isn't present or no NM connection owns the panel's interface."""
    empty = {
        "available": _has_cmd("nmcli"),
        "configurable": False,
        "device": "",
        "connection": "",
        "type": "",
        "method": "",
        "address": "",
        "cidr": None,
        "gateway": "",
        "dns": [],
    }
    if not _has_cmd("nmcli"):
        return empty
    net = await _network_block()
    dev = net["iface"]
    if not dev:
        return empty
    conn = await _nmcli_get("GENERAL.CONNECTION", "device", "show", dev)
    if not conn:
        return {**empty, "device": dev}
    ctype, method, gateway = await asyncio.gather(
        _nmcli_get("GENERAL.TYPE", "device", "show", dev),
        _nmcli_get("ipv4.method", "connection", "show", conn),
        _nmcli_get("IP4.GATEWAY", "device", "show", dev),
    )
    addrs, dns = await asyncio.gather(
        _nmcli_get_lines("IP4.ADDRESS", "device", "show", dev),
        _nmcli_get_lines("IP4.DNS", "device", "show", dev),
    )
    address, _, cidr = (addrs[0] if addrs else "").partition("/")
    return {
        "available": True,
        "configurable": True,
        "device": dev,
        "connection": conn,
        "type": ctype,
        "method": method or "auto",
        "address": address,
        "cidr": int(cidr) if cidr.isdigit() else None,
        "gateway": gateway,
        "dns": dns,
    }


def _validate_static(
    address: str, cidr: int | None, gateway: str, dns: str
) -> tuple[str, str, str]:
    """Validate a static IPv4 config → (addr/prefix, gateway, comma-DNS). Raises ValueError."""
    try:
        iface = ipaddress.ip_interface(f"{address}/{cidr}")
    except (ValueError, TypeError) as exc:
        raise ValueError("Enter a valid IPv4 address and subnet prefix.") from exc
    if not isinstance(iface, ipaddress.IPv4Interface):
        raise ValueError("IPv4 addresses only.")
    prefix = iface.network.prefixlen
    if not (1 <= prefix <= 30):
        raise ValueError("Subnet prefix must be between 1 and 30.")
    ip = iface.ip
    net = iface.network
    if ip.is_loopback or ip.is_multicast or ip.is_link_local or ip.is_unspecified:
        raise ValueError("That host IP address isn't usable.")
    if ip in (net.network_address, net.broadcast_address):
        raise ValueError("That IP is the subnet's network or broadcast address.")
    try:
        gw = ipaddress.IPv4Address(gateway)
    except (ValueError, TypeError) as exc:
        raise ValueError("Enter a valid gateway address.") from exc
    if gw not in net:
        raise ValueError("The gateway must be in the same subnet as the address.")
    if gw == ip:
        raise ValueError("The gateway can't be the same as the host address.")
    if gw in (net.network_address, net.broadcast_address):
        raise ValueError("The gateway can't be the network or broadcast address.")
    dns_list: list[str] = []
    for raw in re.split(r"[,\s]+", dns.strip()):
        if not raw:
            continue
        try:
            ipaddress.IPv4Address(raw)
        except ValueError as exc:
            raise ValueError(f"Invalid DNS server: {raw}") from exc
        dns_list.append(raw)
    if len(dns_list) > 3:
        raise ValueError("At most 3 DNS servers.")
    return f"{ip}/{prefix}", str(gw), ",".join(dns_list)


async def set_network(
    method: str,
    address: str,
    cidr: int | None,
    gateway: str,
    dns: str,
    moonraker_url: str,
) -> dict[str, Any]:
    """Switch the panel's active connection to DHCP (auto) or a static IPv4 (manual)."""
    if method not in NETWORK_MODES:
        raise ValueError("invalid network mode")
    if not _has_cmd("nmcli"):
        return _refused("Network editing needs NetworkManager (nmcli), which isn't installed here.")
    # Validate static input BEFORE touching anything (cheap, prevents a lockout from a typo).
    static_args: tuple[str, str, str] | None = None
    if method == "manual":
        static_args = _validate_static(address, cidr, gateway, dns)
    info = await network_info()
    conn = info.get("connection")
    if not conn:
        return _refused("No active NetworkManager connection to modify.")
    try:
        busy = await printer_guard.is_busy(MoonrakerClient(moonraker_url))
    except httpx.HTTPError:
        busy = False
    if busy:
        return _refused("Refused: a print is in progress.")
    if method == "auto":
        # Clear the static fields too, or a stale address/gateway/DNS would linger in the profile.
        mod = [
            "ipv4.method", "auto",
            "ipv4.addresses", "", "ipv4.gateway", "", "ipv4.dns", "",
            "ipv4.ignore-auto-dns", "no",
        ]  # fmt: skip
    else:
        assert static_args is not None
        addr_cidr, gw, dns_csv = static_args
        mod = [
            "ipv4.method", "manual",
            "ipv4.addresses", addr_cidr, "ipv4.gateway", gw, "ipv4.dns", dns_csv,
            "ipv4.ignore-auto-dns", "yes" if dns_csv else "no",
        ]  # fmt: skip
    rc, out = await _run_rc(
        ["sudo", "-n", "nmcli", "connection", "modify", conn, *mod], timeout=30.0
    )
    if rc != 0:
        return _result(rc, out)  # carries needs_setup when sudo isn't granted
    # Reactivate so the change takes effect. On a real self-disconnect the client never receives
    # this response (the socket dies first) and the frontend treats that as "applied, reconnect".
    # If the call instead returns/timeouts here, the old link is still up and a non-zero rc is a
    # genuine reactivation failure, so we report ok:false (the modify did persist to the profile).
    rc2, out2 = await _run_rc(["sudo", "-n", "nmcli", "connection", "up", conn], timeout=30.0)
    return _result(rc2, out2)
