"""Linux host control - read the printer host's OS state (and, in later phases, change it).

The FilaMind backend runs *on* the printer host, so most of the read-only monitor comes straight
from stdlib (``os``/``shutil``/``/proc``/``/sys``) with no subprocess and no sudo; a few items
(top processes, Wi-Fi, timezone/NTP, locale) shell out to read-only commands. Phase 1 is the
monitor only - services, cleanup and the system-changing actions (time/locale/hostname/power) build
on this in later phases and are the parts that gate behind confirmations + sudo.
"""

from __future__ import annotations

import asyncio
import contextlib
import difflib
import glob
import hashlib
import ipaddress
import os
import platform
import re
import shutil
import socket
import stat
import tempfile
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


# --- Boot / splash (read-only here; changing the splash + the studio land in a later phase) ------

#: Known boot-splash image locations across the common printer-host images (Raspberry Pi OS,
#: Armbian / BTT CB1, generic). The first that exists is treated as the active boot splash.
_SPLASH_PATHS: tuple[str, ...] = (
    "/boot/firmware/splash.png",
    "/boot/splash.png",
    "/boot/boot.bmp",
    "/usr/share/plymouth/themes/spinner/watermark.png",
)


def _find_splash() -> dict[str, Any] | None:
    """The active boot-splash image (path + byte size), best-effort, or None if none is found."""
    for p in _SPLASH_PATHS:
        try:
            st = os.stat(p)
        except OSError:
            continue
        if stat.S_ISREG(st.st_mode):
            return {"path": p, "size": st.st_size}
    return None


def splash_path() -> str | None:
    """The active boot-splash file path (restricted to the known locations), for serving it."""
    found = _find_splash()
    return found["path"] if found else None


async def boot_info() -> dict[str, Any]:
    """Read-only boot configuration: the systemd default target, the active boot splash, and the
    plymouth theme when present. Nothing here changes the system (that lands in a later phase)."""
    default_target = (await _run(["systemctl", "get-default"])).strip()
    plymouth = (await _run(["plymouth-set-default-theme"])).strip()
    return {
        "default_target": default_target or None,
        "graphical": default_target.startswith("graphical"),
        "splash": _find_splash(),
        "plymouth_theme": plymouth or None,
    }


#: A boot splash should be tiny; cap it so we never copy a huge file into /boot.
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_MAX_SPLASH_BYTES = 1_000_000  # 1 MB


async def set_splash(data: bytes, target: str | None = None) -> dict[str, Any]:
    """Place a new boot-splash PNG at a KNOWN splash location (gated write).

    Validated (must be a PNG, ≤ 1 MB) + path-guarded (the destination must be one of the known
    splash locations, never an arbitrary path) + copied with the narrow passwordless ``sudo cp``.
    Best-effort: whether the new image actually shows at boot depends on the host's splash mechanism
    (plymouth / firmware splash), which this does not reconfigure - it just places a valid PNG.
    """
    if data[:8] != _PNG_MAGIC:
        return {"ok": False, "refused": True, "output": "The boot splash must be a PNG image."}
    if len(data) > _MAX_SPLASH_BYTES:
        kb = _MAX_SPLASH_BYTES // 1000
        return {"ok": False, "refused": True, "output": f"The image is too large (max {kb} KB)."}
    dest = target or splash_path() or _SPLASH_PATHS[0]
    if dest not in _SPLASH_PATHS:
        return {
            "ok": False,
            "refused": True,
            "output": "Refusing to write outside the known boot-splash locations.",
        }
    tmp = ""
    try:
        fd, tmp = tempfile.mkstemp(suffix=".png")
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        rc, out = await _run_rc(["sudo", "-n", "cp", tmp, dest])
    finally:
        if tmp:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
    if rc == 0:
        return {
            "ok": True,
            "refused": False,
            "output": f"Boot splash written to {dest}.",
            "dest": dest,
        }
    return {
        "ok": False,
        "refused": False,
        "output": out.strip() or "Could not write the boot splash.",
        "needs_setup": _needs_setup(out),
    }


def _host_block() -> dict[str, Any]:
    osr = _read("/etc/os-release")
    distro = ""
    for line in osr.splitlines():
        if line.startswith("PRETTY_NAME="):
            distro = line.split("=", 1)[1].strip().strip('"')
            break
    # os.uname() is POSIX-only; platform.uname() is the cross-platform fallback (keeps the local
    # Windows dev/test run from crashing - the real host is always Linux).
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
        if key in seen:  # data_dir often lives on / - don't list the same filesystem twice
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


# -- Services (Phase 2) ---------------------------------------------------------
# A general systemd unit manager. The backend is the security boundary: it validates the unit
# name, refuses destructive actions on a protected set (so the user can't lock themselves out or
# kill this panel), and path-guards unit-file deletion to /etc/systemd/system. Privileged actions
# go through the host's passwordless-sudo rule (scripts/install.sh sudoers).

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
    # The native FilaMind touch units (the .deb apps that can own the touchscreen). Guard them like
    # KlipperScreen so the Services tab can't stop whichever one currently drives the display, which
    # would blank the screen mid-session. Bare names (no .service) - _is_critical strips the suffix.
    "filamind-kiosk",
    "filamind-screen-kiosk",
    "NetworkManager",
    "wpa_supplicant",
    "networking",
    "systemd-networkd",
    "systemd-resolved",
    "getty",
}

#: A unit name is a safe argument when it has no shell-hostile or path characters. (We never use a
#: shell - this is belt-and-suspenders + a guard against absurd input.)
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

    Forces the C locale so tool/sudo messages come back in English - both so our parsers (systemctl,
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
            "output": f"'{name}' is protected - {action} is not allowed.",
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
    # result from BOTH privileged steps (disable + rm), not just rm - a sudo-grant failure can show
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


# -- Disk cleanup (Phase 3) -----------------------------------------------------
# Reclaim space from caches and rotated logs the user never needs to keep. Every target offers a
# dry-run "frees X" scan before anything is deleted, and the deletes are tightly scoped: only the
# user's own caches/temp files and rotated (non-live) logs, plus the apt download cache and the
# systemd journal (vacuumed, not erased). User data - G-code, timelapses, configs - is untouched.

#: The cleanup targets, in display order.
CLEANUP_TARGETS = ("apt", "journal", "cache", "tmp", "logs")
#: Only remove /tmp files this old (seconds) - younger files may be in active use.
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


# -- System settings (Phase 4) --------------------------------------------------
# Time / locale / hostname / network / power. Each setter validates its input (and, where there's a
# canonical list, checks membership) before shelling out through the host's passwordless-sudo rule.
# Power actions refuse while a print is in progress. The network (IPv4) controls need NetworkManager
# (nmcli); when it's absent the feature reports unavailable rather than guessing the network stack.

_HOSTNAME_RE = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$")
_TIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
_TZ_RE = re.compile(r"^[A-Za-z0-9_+\-/]+$")
_LOCALE_RE = re.compile(r"^[A-Za-z0-9_.@\-]+$")
_KEYMAP_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")
POWER_ACTIONS = ("reboot", "shutdown")


# A passwordless-sudo command fails like this when the sudoers grant isn't installed yet
# (scripts/install.sh sudoers). We flag it so the UI can show an actionable hint instead of a
# meaningless "sudo: a password is required".
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
    """Current time/locale/hostname/network settings + the option lists the System form offers."""
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
    # timedatectl refuses to set the clock while NTP is on - surface that as a friendly refusal.
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


async def power(action: str, moonraker_url: str) -> dict[str, Any]:
    """Reboot or shut down the host - refused while a print is in progress."""
    if action not in POWER_ACTIONS:
        raise ValueError("invalid power action")
    try:
        busy = await printer_guard.is_busy(MoonrakerClient(moonraker_url))
    except httpx.HTTPError:
        # Can't confirm the printer is idle, so refuse rather than risk a power-off mid-print.
        return _refused("Refused: could not reach Moonraker to confirm the printer is idle.")
    if busy:
        return _refused("Refused: a print is in progress.")
    unit_action = "reboot" if action == "reboot" else "poweroff"
    return _result(*await _run_rc(["sudo", "-n", "systemctl", unit_action]))


# -- Network / IPv4 (NetworkManager) --------------------------------------------
# View and switch the panel's active connection between DHCP (auto) and a static IPv4
# (address/CIDR + gateway + DNS). IPv4-only by design. The connection to modify is resolved
# SERVER-SIDE (the active connection on the device that owns the panel's IP) - never taken from the
# client - so a request can't retarget an unrelated profile. Changing the IP of the serving
# connection will drop this panel; the UI warns and tells the user where to reconnect. Refused while
# a print is in progress (a network drop can orphan Moonraker mid-print). nmcli is already granted
# by 'scripts/install.sh sudoers', so no new sudoers entry is needed.

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


# -- Host health advisor (Phase 6) ---------------------------------------------
# Graded, actionable health cards over the SAME read-only signals the monitor uses (CPU temp /
# throttle, memory + swap, disk, clock/NTP, the print-stack services). No new privilege - every
# source is already read for the monitor. Thresholds mirror the monitor's bar colours so the grade
# agrees with what the user sees there.

_ADV_TEMP_WARN, _ADV_TEMP_FAIL = 70.0, 80.0
_ADV_MEM_WARN, _ADV_MEM_FAIL = 75, 90
_ADV_DISK_WARN, _ADV_DISK_FAIL = 85, 95
#: The print-stack services whose health the Advisor surfaces (not the whole critical set).
_ADV_SERVICES = ("klipper", "moonraker")
_GRADE_BANDS = ((90, "A"), (78, "B"), (62, "C"), (45, "D"))


def _grade(score: int) -> str:
    """Map a 0-100 score to a letter, matching the Machine Doctor bands."""
    for floor, letter in _GRADE_BANDS:
        if score >= floor:
            return letter
    return "F"


def _gb(kb: int) -> str:
    return f"{kb / 1048576:.1f} GB"


def _card(
    card_id: str,
    status: str,
    score: float,
    *,
    badges: list[str] | None = None,
    detail: str = "",
    fix: str | None = None,
) -> dict[str, Any]:
    s = int(max(0, min(100, round(score))))
    return {
        "id": card_id,
        "status": status,
        "score": s,
        "grade": _grade(s),
        "badges": list(dict.fromkeys(badges or [])),  # de-duplicated, order-preserving
        "detail": detail,
        "fix_code": fix,
    }


def _cpu_card(cpu: dict[str, Any], throttle: dict[str, Any]) -> dict[str, Any]:
    temp = cpu.get("temp_c")
    badges: list[str] = []
    fix: str | None = None
    if isinstance(temp, int | float):
        if temp >= _ADV_TEMP_FAIL:
            status, score, fix = "fail", 30, "cpu_temp"
            badges.append("temp_high")
        elif temp >= _ADV_TEMP_WARN:
            status, score, fix = "warn", 68, "cpu_temp"
            badges.append("temp_high")
        else:
            status, score = "ok", max(70, round(100 - max(0.0, temp - 40) * 1.5))
    else:
        status, score = "ok", 90
    flags = throttle.get("flags") or []
    if throttle.get("undervoltage"):
        badges.append("undervolt")
    if any(str(f).endswith("_now") for f in flags):
        status, score, fix = "fail", min(score, 30), "cpu_throttled"
        badges.append("throttled")
    elif any(str(f).endswith("_occurred") for f in flags):
        if status == "ok":
            status, score = "warn", min(score, 68)
        badges.append("throttled")
    detail = f"{temp} °C" if isinstance(temp, int | float) else "—"
    load = cpu.get("load")
    if load:
        detail += " · " + " ".join(str(x) for x in load)
    return _card("cpu", status, score, badges=badges, detail=detail, fix=fix)


def _mem_card(mem: dict[str, Any]) -> dict[str, Any]:
    total = mem.get("total_kb") or 0
    used = mem.get("used_kb") or 0
    pct = round(used / total * 100) if total else 0
    badges: list[str] = []
    if pct >= _ADV_MEM_FAIL:
        status, fix = "fail", "memory_pressure"
    elif pct >= _ADV_MEM_WARN:
        status, fix = "warn", "memory_pressure"
    else:
        status, fix = "ok", None
    score = max(0, 100 - pct)
    swap_total = mem.get("swap_total_kb") or 0
    swap_used = mem.get("swap_used_kb") or 0
    spct = round(swap_used / swap_total * 100) if swap_total else 0
    if swap_total and spct >= 50:
        badges.append("swap_heavy")
        if status == "ok":
            status, score = "warn", min(score, 68)
        fix = fix or "memory_pressure"
    detail = f"{pct}% · {_gb(used)}/{_gb(total)}"
    if swap_total:
        detail += f" · swap {spct}%"
    return _card("memory", status, score, badges=badges, detail=detail, fix=fix)


def _disk_card(disks: list[dict[str, Any]]) -> dict[str, Any]:
    if not disks:
        return _card("disk", "unknown", 50, detail="—")
    maxpct = max(int(d.get("pct", 0)) for d in disks)
    if maxpct >= _ADV_DISK_FAIL:
        status, fix = "fail", "disk_full"
    elif maxpct >= _ADV_DISK_WARN:
        status, fix = "warn", "disk_full"
    else:
        status, fix = "ok", None
    detail = " · ".join(f"{d['label']} {d['pct']}%" for d in disks)
    return _card("disk", status, max(0, 100 - maxpct), detail=detail, fix=fix)


def _clock_card(time_b: dict[str, Any]) -> dict[str, Any]:
    tz = time_b.get("timezone") or "—"
    if time_b.get("ntp_synced"):
        return _card("clock", "ok", 95, detail=f"{tz} · NTP ✓")
    mark = "⟳" if time_b.get("ntp_enabled") else "✗"
    score = 60 if time_b.get("ntp_enabled") else 55
    return _card(
        "clock", "warn", score, badges=["ntp_unsync"], detail=f"{tz} · NTP {mark}", fix="ntp_unsync"
    )


async def _services_card() -> dict[str, Any]:
    units = await list_units()
    by_name: dict[str, dict[str, Any]] = {}
    for u in units:
        by_name.setdefault(str(u.get("name")), u)
        by_name.setdefault(_base(str(u.get("name"))), u)
    parts: list[str] = []
    down = False
    for svc in _ADV_SERVICES:
        unit = by_name.get(svc)
        if not unit:
            continue
        active = bool(unit.get("active"))
        parts.append(f"{svc} {'✓' if active else '✕'}")
        down = down or not active
    if not parts:
        return _card("services", "unknown", 50, detail="—")
    if down:
        return _card("services", "fail", 25, detail=" · ".join(parts), fix="service_down")
    return _card("services", "ok", 100, detail=" · ".join(parts))


async def advisory(data_dir: str) -> dict[str, Any]:
    """Graded host-health cards (CPU / memory / disk / clock / services). Read-only - same signals
    as the monitor, scored independently per card with an actionable fix hint."""
    throttle, time_b, services = await asyncio.gather(
        _throttle_block(), _time_block(), _services_card()
    )
    cards = [
        _cpu_card(_cpu_block(), throttle),
        _mem_card(_memory_block()),
        _disk_card(_disk_block(data_dir)),
        _clock_card(time_b),
        services,
    ]
    return {"cards": cards}


# =========================== Boot parameters ===================================
# Edit the host's boot configuration - /boot/armbianEnv.txt on Armbian (RK/Allwinner boards like the
# BTT CB1/CB2), or config.txt + cmdline.txt on Raspberry Pi - through a curated capability UI plus a
# raw advanced editor. Every write is a MINIMAL-DIFF edit (only the targeted token changes; every
# other line is preserved byte-for-byte), backed up first, path-guarded to the known boot files, and
# applied through the already-granted `sudo -n cp` - so no new sudoers entry is needed. Nothing
# reboots automatically; the UI shows a "reboot required" state and offers a gated reboot.

_ARMBIAN_ENV = "/boot/armbianEnv.txt"
_RPI_CONFIG_CANDIDATES = ("/boot/firmware/config.txt", "/boot/config.txt")
_RPI_CMDLINE_CANDIDATES = ("/boot/firmware/cmdline.txt", "/boot/cmdline.txt")

#: The ONLY paths a boot write may target. This allow-list is the security boundary (sudoers grants
#: an unrestricted `cp`; THIS restricts where it may land), the same role _SPLASH_PATHS plays.
_BOOT_MANAGED_PATHS: frozenset[str] = frozenset(
    (_ARMBIAN_ENV, *_RPI_CONFIG_CANDIDATES, *_RPI_CMDLINE_CANDIDATES)
)
_MAX_BOOT_BYTES = 64 * 1024  # a boot config over 64 KiB is pathological -> refuse to touch it
_MAX_BOOT_BACKUPS = 10  # keep at most this many timestamped backups per file
_BOOT_BAK_MARK = ".filamind.bak-"  # suffix marker: <path>.filamind.bak-YYYYmmddHHMMSS
_BOOT_BAK_RE = re.compile(r"\.filamind\.bak-(\d{14})$")

#: Whitelist regexes (defence-in-depth; the curated UI only sends known-safe values).
_BOOT_VALUE_RE = re.compile(r"^[^\n\x00]*$")  # any single-line value (armbian kv / extraarg)
_BOOT_TOKEN_RE = re.compile(r"^[A-Za-z0-9._,=:+@/-]+$")  # an overlay / dtoverlay / dtparam token
_BOOT_KEY_RE = re.compile(r"^[A-Za-z0-9_]+$")
_CMDLINE_TOKEN_RE = re.compile(r"^[^\s\x00]+$")
_SECTION_RE = re.compile(r"^\s*\[.+\]\s*$")  # a config.txt [filter] header


# --- platform detection (pure filesystem, no sudo) ---


def _boot_is_regular(path: str) -> bool:
    try:
        return stat.S_ISREG(os.stat(path).st_mode)
    except OSError:
        return False


def _boot_first_existing(cands: tuple[str, ...]) -> str | None:
    return next((p for p in cands if _boot_is_regular(p)), None)


def detect_boot_platform() -> dict[str, Any]:
    """Which boot-config mechanism this host uses. Armbian-FIRST: an Armbian image can ship a stub
    /boot/config.txt, but /boot/armbianEnv.txt is the authoritative one when present. Within RPi,
    /boot/firmware (Bookworm) beats legacy /boot, and cmdline.txt is the SIBLING of the chosen
    config.txt so both writes stay on one partition."""
    if _boot_is_regular(_ARMBIAN_ENV):
        return {"platform": "armbian", "config_path": _ARMBIAN_ENV, "cmdline_path": None}
    cfg = _boot_first_existing(_RPI_CONFIG_CANDIDATES)
    if cfg:
        sibling = os.path.join(os.path.dirname(cfg), "cmdline.txt")
        cmd = (
            sibling if _boot_is_regular(sibling) else _boot_first_existing(_RPI_CMDLINE_CANDIDATES)
        )
        return {"platform": "rpi", "config_path": cfg, "cmdline_path": cmd}
    return {"platform": "unknown", "config_path": None, "cmdline_path": None}


def _boot_paths_for(plat: dict[str, Any]) -> list[str]:
    if plat["platform"] == "armbian":
        return [plat["config_path"]]
    if plat["platform"] == "rpi":
        return [p for p in (plat["config_path"], plat["cmdline_path"]) if p]
    return []


def _boot_format_for(path: str) -> str:
    base = os.path.basename(path)
    if base == "armbianEnv.txt":
        return "armbian"
    if base == "cmdline.txt":
        return "cmdline"
    return "config"


def _boot_resolve_file(plat: dict[str, Any], name: str | None) -> str | None:
    """Map a client-sent file basename to its absolute, SERVER-resolved path (never trust a client
    path). Defaults to the platform's config file; only the platform's own files resolve."""
    if not name:
        return plat.get("config_path")
    base = os.path.basename(str(name))
    for path in (plat.get("config_path"), plat.get("cmdline_path")):
        if path and os.path.basename(path) == base:
            return path
    return None


# --- line model (preserve trailing-newline state; round-trips byte-for-byte) ---


def _to_lines(text: str) -> tuple[list[str], bool]:
    if text == "":
        return [], False
    had_nl = text.endswith("\n")
    body = text[:-1] if had_nl else text
    return body.split("\n"), had_nl


def _from_lines(lines: list[str], had_nl: bool) -> str:
    text = "\n".join(lines)
    return text + "\n" if had_nl else text


# --- armbianEnv.txt (KEY=VALUE; `overlays=` + `extraargs=` are space-separated token lists) ---


def _armbian_find_kv(lines: list[str], key: str) -> int:
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith("#") or "=" not in s:
            continue
        if s.split("=", 1)[0].strip() == key:
            return i
    return -1


def _armbian_get(lines: list[str], key: str) -> str | None:
    i = _armbian_find_kv(lines, key)
    return lines[i].split("=", 1)[1] if i >= 0 else None


def _armbian_set_key(lines: list[str], key: str, value: str) -> None:
    i = _armbian_find_kv(lines, key)
    if i < 0:
        lines.append(f"{key}={value}")
    else:  # keep the on-disk key text (casing), replace only the value
        lines[i] = f"{lines[i].split('=', 1)[0]}={value}"


def _armbian_add_overlay(lines: list[str], name: str) -> None:
    toks = (_armbian_get(lines, "overlays") or "").split()
    if name not in toks:
        toks.append(name)
    _armbian_set_key(lines, "overlays", " ".join(toks))


def _armbian_remove_overlay(lines: list[str], name: str) -> None:
    toks = [t for t in (_armbian_get(lines, "overlays") or "").split() if t != name]
    _armbian_set_key(lines, "overlays", " ".join(toks))


def _armbian_set_extraarg(lines: list[str], key: str, value: str) -> None:
    toks = (_armbian_get(lines, "extraargs") or "").split()
    newtok = f"{key}={value}" if value != "" else key
    out: list[str] = []
    replaced = False
    for t in toks:
        if t.split("=", 1)[0] == key:
            if not replaced:
                out.append(newtok)
                replaced = True
        else:
            out.append(t)
    if not replaced:
        out.append(newtok)
    _armbian_set_key(lines, "extraargs", " ".join(out))


def _armbian_remove_extraarg(lines: list[str], key: str) -> None:
    toks = [
        t for t in (_armbian_get(lines, "extraargs") or "").split() if t.split("=", 1)[0] != key
    ]
    _armbian_set_key(lines, "extraargs", " ".join(toks))


# --- config.txt (line-oriented; edits happen in the EDITABLE scope: the pre-filter global block or
# an [all] section - never a model-specific [pi4]/[cm4]/[none] block, which is left as the user set
# it. This keeps a curated edit from being silently overridden by a later [all] assignment.) -


def _config_section_name(ln: str) -> str | None:
    """The lowercased name of a ``[filter]`` header line, else None (not a header)."""
    return ln.strip()[1:-1].strip().lower() if _SECTION_RE.match(ln) else None


def _config_editable_scope(section: str | None) -> bool:
    """True for scopes a curated edit may touch: the pre-filter global block (None) and ``[all]``
    (both apply to every model). Model-specific filters are preserved untouched."""
    return section is None or section == "all"


def _dtparam_key(s: str) -> str:
    return s[len("dtparam=") :].split("=", 1)[0].split(",")[0]


def _dtoverlay_name(s: str) -> str:
    return s[len("dtoverlay=") :].split(",", 1)[0].strip()


def _config_is_plain_kv(s: str) -> bool:
    return (
        "=" in s
        and not s.startswith("#")
        and not s.startswith("dtparam=")
        and not s.startswith("dtoverlay=")
    )


def _config_insert_global(lines: list[str], newline: str) -> None:
    """Insert a new line into global scope - before the first [filter] header (so a later filter
    can't swallow it), or at EOF when there are no filters."""
    for i, ln in enumerate(lines):
        if _SECTION_RE.match(ln):
            lines.insert(i, newline)
            return
    lines.append(newline)


def _config_set_line(lines: list[str], match: Any, newline: str) -> None:
    """Replace the LAST editable-scope line matching ``match`` in place (the last one is the value
    that actually wins); if none exists, insert into global scope."""
    section: str | None = None
    hit = -1
    for i, ln in enumerate(lines):
        if _SECTION_RE.match(ln):
            section = _config_section_name(ln)
            continue
        if _config_editable_scope(section) and match(ln.strip()):
            hit = i
    if hit >= 0:
        lines[hit] = newline
    else:
        _config_insert_global(lines, newline)


def _config_remove(lines: list[str], match: Any) -> None:
    """Drop every editable-scope line matching ``match`` (model-specific sections are preserved)."""
    out: list[str] = []
    section: str | None = None
    for ln in lines:
        if _SECTION_RE.match(ln):
            section = _config_section_name(ln)
            out.append(ln)
            continue
        if _config_editable_scope(section) and match(ln.strip()):
            continue
        out.append(ln)
    lines[:] = out


def _config_set_dtparam(lines: list[str], key: str, value: str) -> None:
    target = f"dtparam={key}={value}" if value != "" else f"dtparam={key}"
    _config_set_line(lines, lambda s: s.startswith("dtparam=") and _dtparam_key(s) == key, target)


def _config_remove_dtparam(lines: list[str], key: str) -> None:
    _config_remove(lines, lambda s: s.startswith("dtparam=") and _dtparam_key(s) == key)


def _config_set_kv(lines: list[str], key: str, value: str) -> None:
    target = f"{key}={value}"
    _config_set_line(
        lines, lambda s: _config_is_plain_kv(s) and s.split("=", 1)[0].strip() == key, target
    )


def _config_remove_kv(lines: list[str], key: str) -> None:
    _config_remove(lines, lambda s: _config_is_plain_kv(s) and s.split("=", 1)[0].strip() == key)


def _config_add_dtoverlay(lines: list[str], name: str, params: str) -> None:
    """Upsert a dtoverlay by NAME: replace an existing same-name overlay in editable scope (so
    changing its params is an edit, not a conflicting duplicate); otherwise insert it global."""
    line = f"dtoverlay={name},{params}" if params else f"dtoverlay={name}"
    _config_set_line(
        lines, lambda s: s.startswith("dtoverlay=") and _dtoverlay_name(s) == name, line
    )


def _config_remove_dtoverlay(lines: list[str], name: str) -> None:
    _config_remove(lines, lambda s: s.startswith("dtoverlay=") and _dtoverlay_name(s) == name)


# --- cmdline.txt (a single space-separated line) ---


def _cmdline_has_key(text: str, key: str) -> bool:
    return any(t.split("=", 1)[0] == key for t in text.split())


# --- op dispatch (each op is validated against the whitelist; unknown/bad -> ValueError -> 400) ---


def _boot_req(op: dict[str, Any], field: str, rx: re.Pattern[str]) -> str:
    v = str(op.get(field, ""))
    if not v or not rx.match(v):
        raise ValueError(f"invalid boot op value for '{field}'")
    return v


def _boot_val(op: dict[str, Any], field: str) -> str:
    v = str(op.get(field, ""))
    if not _BOOT_VALUE_RE.match(v):
        raise ValueError(f"invalid boot value for '{field}'")
    return v


def _boot_opt_token(op: dict[str, Any], field: str) -> str:
    v = str(op.get(field, ""))
    if v and not _BOOT_TOKEN_RE.match(v):
        raise ValueError(f"invalid boot token for '{field}'")
    return v


def _apply_armbian_op(lines: list[str], op: dict[str, Any]) -> None:
    name = op.get("op")
    if name == "set_key":
        _armbian_set_key(lines, _boot_req(op, "key", _BOOT_KEY_RE), _boot_val(op, "value"))
    elif name == "add_overlay":
        _armbian_add_overlay(lines, _boot_req(op, "name", _BOOT_TOKEN_RE))
    elif name == "remove_overlay":
        _armbian_remove_overlay(lines, _boot_req(op, "name", _BOOT_TOKEN_RE))
    elif name == "set_extraarg":
        _armbian_set_extraarg(
            lines, _boot_req(op, "key", _BOOT_KEY_RE), _boot_opt_token(op, "value")
        )
    elif name == "remove_extraarg":
        _armbian_remove_extraarg(lines, _boot_req(op, "key", _BOOT_KEY_RE))
    else:
        raise ValueError(f"unsupported armbian op: {name!r}")


def _apply_config_op(lines: list[str], op: dict[str, Any]) -> None:
    name = op.get("op")
    if name == "set_dtparam":
        _config_set_dtparam(lines, _boot_req(op, "key", _BOOT_KEY_RE), _boot_opt_token(op, "value"))
    elif name == "remove_dtparam":
        _config_remove_dtparam(lines, _boot_req(op, "key", _BOOT_KEY_RE))
    elif name == "set_kv":
        _config_set_kv(lines, _boot_req(op, "key", _BOOT_KEY_RE), _boot_opt_token(op, "value"))
    elif name == "remove_kv":
        _config_remove_kv(lines, _boot_req(op, "key", _BOOT_KEY_RE))
    elif name == "add_dtoverlay":
        _config_add_dtoverlay(
            lines, _boot_req(op, "name", _BOOT_TOKEN_RE), _boot_opt_token(op, "params")
        )
    elif name == "remove_dtoverlay":
        _config_remove_dtoverlay(lines, _boot_req(op, "name", _BOOT_TOKEN_RE))
    else:
        raise ValueError(f"unsupported config op: {name!r}")


def _apply_cmdline_op(tokens: list[str], op: dict[str, Any]) -> list[str]:
    name = op.get("op")
    if name == "add_token":
        tok = _boot_req(op, "token", _CMDLINE_TOKEN_RE)
        if tok not in tokens:
            tokens.append(tok)
        return tokens
    if name == "remove_token":
        tok = str(op.get("token", ""))
        return [t for t in tokens if t != tok]
    if name == "set_token":
        key = _boot_req(op, "key", _BOOT_KEY_RE)
        val = _boot_req(op, "value", _CMDLINE_TOKEN_RE)
        newtok = f"{key}={val}"
        out: list[str] = []
        replaced = False
        for t in tokens:
            if t.split("=", 1)[0] == key:
                if not replaced:
                    out.append(newtok)
                    replaced = True
            else:
                out.append(t)
        if not replaced:
            out.append(newtok)
        return out
    if name == "remove_token_key":
        key = str(op.get("key", ""))
        return [t for t in tokens if t.split("=", 1)[0] != key]
    raise ValueError(f"unsupported cmdline op: {name!r}")


def _boot_apply_ops(path: str, before: str, fmt: str, ops: list[dict[str, Any]]) -> str:
    """Build the after-text by applying validated ops onto the parsed before-text. Minimal-diff:
    only targeted tokens change; everything else is preserved. Raises ValueError on a bad op."""
    if fmt == "cmdline":
        had_nl = before.endswith("\n") or before == ""
        tokens = before.split()
        for op in ops:
            tokens = _apply_cmdline_op(tokens, op)
        for t in tokens:
            if not _CMDLINE_TOKEN_RE.match(t):
                raise ValueError("invalid cmdline token")
        return " ".join(tokens) + ("\n" if had_nl else "")
    lines, had_nl = _to_lines(before)
    for op in ops:
        if fmt == "armbian":
            _apply_armbian_op(lines, op)
        else:
            _apply_config_op(lines, op)
    return _from_lines(lines, had_nl)


# --- read state (read-only, no sudo) ---


def _project_boot_file(path: str, text: str, fmt: str) -> dict[str, Any]:
    lines, _ = _to_lines(text)
    out: dict[str, Any] = {
        "name": os.path.basename(path),
        "path": path,
        "exists": _boot_is_regular(path),
        "format": {"armbian": "armbian", "cmdline": "cmdline"}.get(fmt, "config.txt"),
        "raw_lines": len(lines),
        "backups": _list_boot_backups(path),
    }
    if fmt == "armbian":
        keys = []
        for ln in lines:
            s = ln.strip()
            if s and not s.startswith("#") and "=" in s:
                k, v = s.split("=", 1)
                keys.append({"key": k.strip(), "value": v})
        out["keys"] = keys
        out["overlays"] = (_armbian_get(lines, "overlays") or "").split()
        out["extraargs"] = (_armbian_get(lines, "extraargs") or "").split()
    elif fmt == "cmdline":
        out["tokens"] = text.split()
    else:
        overlays, dtparams, kv = _config_parse(lines)
        out["overlays"] = overlays
        out["dtparams"] = dtparams
        out["kv"] = kv
    return out


def _config_parse(lines: list[str]) -> tuple[list[dict], list[dict], list[dict]]:
    section: str | None = None
    overlays: list[dict[str, Any]] = []
    dtparams: list[dict[str, Any]] = []
    kv: list[dict[str, Any]] = []
    for ln in lines:
        if _SECTION_RE.match(ln):
            section = ln.strip()[1:-1].strip()
            continue
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("dtoverlay="):
            body = s[len("dtoverlay=") :]
            nm, _, pr = body.partition(",")
            overlays.append({"name": nm.strip(), "params": pr, "section": section})
        elif s.startswith("dtparam="):
            body = s[len("dtparam=") :]
            k, _, v = body.partition("=")
            dtparams.append({"key": k.strip(), "value": v or None, "section": section})
        elif "=" in s:
            k, v = s.split("=", 1)
            kv.append({"key": k.strip(), "value": v, "section": section})
    return overlays, dtparams, kv


def _boot_time() -> float | None:
    up = _read("/proc/uptime").split()
    if not up:
        return None
    try:
        return time.time() - float(up[0])
    except ValueError:
        return None


def _boot_reboot_pending(plat: dict[str, Any]) -> bool:
    """A reboot is pending when any managed boot file was modified AFTER the last boot - a stateless
    signal that survives a backend restart and also catches edits made by other tools."""
    bt = _boot_time()
    if bt is None:
        return False
    for path in _boot_paths_for(plat):
        try:
            if os.stat(path).st_mtime > bt + 2:  # +2s guards vfat mtime granularity at boot
                return True
        except OSError:
            continue
    return False


def read_boot_params() -> dict[str, Any]:
    """The host's boot configuration, projected for the UI. Read-only, safe on every platform."""
    plat = detect_boot_platform()
    if plat["platform"] == "unknown":
        return {"platform": "unknown", "editable": False, "reboot_required": False, "files": []}
    files = [_project_boot_file(p, _read(p), _boot_format_for(p)) for p in _boot_paths_for(plat)]
    return {
        "platform": plat["platform"],
        "editable": True,
        "reboot_required": _boot_reboot_pending(plat),
        "files": files,
    }


# --- backup / write (reuse the granted `cp` + `rm`) ---


def _list_boot_backups(path: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in glob.glob(f"{path}{_BOOT_BAK_MARK}*"):
        m = _BOOT_BAK_RE.search(p)
        if not (m and _boot_is_regular(p)):
            continue
        try:
            size = os.stat(p).st_size
        except OSError:
            size = 0
        out.append({"name": os.path.basename(p), "ts": m.group(1), "size": size})
    out.sort(key=lambda b: b["ts"], reverse=True)
    return out


def _boot_latest_backup(path: str) -> str | None:
    baks = _list_boot_backups(path)
    return f"{os.path.dirname(path)}/{baks[0]['name']}" if baks else None


async def _boot_backup(path: str) -> tuple[bool, str]:
    """`sudo -n cp -a <path> <path>.filamind.bak-YYYYmmddHHMMSS`. No-op (ok) if the source is absent
    (a fresh file will be created). A failed backup is a hard stop for the caller."""
    if not _boot_is_regular(path):
        return True, ""
    bak = f"{path}{_BOOT_BAK_MARK}{time.strftime('%Y%m%d%H%M%S')}"
    rc, out = await _run_rc(["sudo", "-n", "cp", "-a", path, bak])
    return (rc == 0), (bak if rc == 0 else out)


async def _boot_prune_backups(path: str) -> None:
    for b in _list_boot_backups(path)[_MAX_BOOT_BACKUPS:]:
        await _run_rc(["sudo", "-n", "rm", "-f", f"{os.path.dirname(path)}/{b['name']}"])


async def _boot_write_file(path: str, content: str) -> dict[str, Any]:
    """Gated write: back up the current file (hard-stop on failure), stage a temp file, then the
    narrow `sudo -n cp`. Mirrors set_splash's write, plus the mandatory backup."""
    ok, bak = await _boot_backup(path)
    if not ok:
        return {
            "ok": False,
            "refused": False,
            "output": bak.strip() or "Could not back up the boot file.",
            "needs_setup": _needs_setup(bak),
        }
    tmp = ""
    try:
        fd, tmp = tempfile.mkstemp(suffix=".bootcfg")
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content)
        rc, out = await _run_rc(["sudo", "-n", "cp", tmp, path])
    finally:
        if tmp:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
    if rc == 0:
        with contextlib.suppress(Exception):
            await _boot_prune_backups(path)
        res: dict[str, Any] = {
            "ok": True,
            "refused": False,
            "output": f"Updated {os.path.basename(path)}.",
            "needs_setup": False,
            "reboot_required": True,
        }
        if bak:
            res["backup"] = os.path.basename(bak)
        return res
    return {
        "ok": False,
        "refused": False,
        "output": out.strip() or "Could not write the boot file.",
        "needs_setup": _needs_setup(out),
    }


# --- validation / diff ---


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _boot_validate(fmt: str, before: str, after: str) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if fmt == "cmdline":
        if "\n" in after.rstrip("\n"):
            errors.append(
                {
                    "code": "cmdline_multiline",
                    "message": "The kernel command line must be one line.",
                }
            )
        if _cmdline_has_key(before, "root") and not _cmdline_has_key(after, "root"):
            warnings.append(
                {"code": "removes_root", "message": "This removes the root= boot token."}
            )
        if _cmdline_has_key(before, "console") and not _cmdline_has_key(after, "console"):
            warnings.append(
                {"code": "removes_console", "message": "This removes the console= token."}
            )
    return {"errors": errors, "warnings": warnings}


def _boot_diff(path: str, before: str, after: str) -> list[str]:
    base = os.path.basename(path)
    return list(
        difflib.unified_diff(
            before.splitlines(),
            after.splitlines(),
            fromfile=base,
            tofile=f"{base} (new)",
            lineterm="",
        )
    )


# --- gated apply / preview / revert / reboot ---


async def apply_boot_change(
    payload: dict[str, Any], *, dry_run: bool, confirm: bool, before_hash: str | None
) -> dict[str, Any]:
    """Two-phase: dry_run=True previews (diff + hashes + validation, NO write); dry_run=False writes
    (requires confirm + a matching before_hash for optimistic concurrency)."""
    plat = detect_boot_platform()
    if plat["platform"] == "unknown":
        return _refused("Editing boot parameters is not supported on this host image.")
    path = _boot_resolve_file(plat, payload.get("file"))
    if path is None or path not in _BOOT_MANAGED_PATHS:
        return _refused("Refusing to write outside the known boot-config locations.")
    fmt = _boot_format_for(path)
    before = _read(path)
    if len(before.encode("utf-8")) > _MAX_BOOT_BYTES:
        return _refused("This boot file is unexpectedly large; refusing to edit it.")
    ops = payload.get("ops") or []
    if not isinstance(ops, list):
        raise ValueError("ops must be a list")
    after = _boot_apply_ops(path, before, fmt, ops)  # ValueError -> 400
    validation = _boot_validate(fmt, before, after)
    if validation["errors"]:
        out = _refused(validation["errors"][0]["message"])
        out["validation"] = validation
        return out
    bh, ah = _sha256(before), _sha256(after)
    if dry_run:
        return {
            "ok": True,
            "refused": False,
            "output": "",
            "needs_setup": False,
            "file": os.path.basename(path),
            "editable": True,
            "diff": _boot_diff(path, before, after),
            "before_hash": bh,
            "after_hash": ah,
            "validation": validation,
        }
    if not confirm:
        return _refused("Apply requires explicit confirmation.")
    # Optimistic concurrency: a real apply MUST carry the hash from its preview, and the file must
    # still be exactly what was previewed - re-read here to close the preview->apply window so a
    # concurrent write (another apply / revert / an external tool) can't be silently clobbered.
    if before_hash is None:
        return _refused("Apply requires the preview hash. Preview the changes again.")
    if _sha256(_read(path)) != before_hash:
        return _refused("The boot file changed since you previewed it. Reload and try again.")
    if ah == bh:
        return {"ok": True, "refused": False, "output": "No change to apply.", "needs_setup": False}
    return await _boot_write_file(path, after)


async def revert_boot_file(file: str, backup: str | None) -> dict[str, Any]:
    """Restore a timestamped backup (a revert is itself a gated, backed-up write)."""
    plat = detect_boot_platform()
    path = _boot_resolve_file(plat, file)
    if path is None or path not in _BOOT_MANAGED_PATHS:
        return _refused("Unknown boot file.")
    if backup:
        cand = f"{os.path.dirname(path)}/{os.path.basename(str(backup))}"
        bak = (
            cand
            if (cand.startswith(f"{path}{_BOOT_BAK_MARK}") and _boot_is_regular(cand))
            else None
        )
    else:
        bak = _boot_latest_backup(path)
    if not bak:
        return _refused("No backup available to restore.")
    content = _read(bak)
    if not content.strip():
        return _refused("Could not read the backup.")
    return await _boot_write_file(path, content)


async def reboot_host_for_boot(confirm: str, moonraker_url: str) -> dict[str, Any]:
    """Reboot the host to apply boot changes - gated by a typed confirmation AND the print-busy
    guard, exactly like `power('reboot')`. Never automatic."""
    if confirm != "REBOOT":
        return _refused("Reboot requires confirmation.")
    try:
        busy = await printer_guard.is_busy(MoonrakerClient(moonraker_url))
    except httpx.HTTPError:
        return _refused("Refused: could not reach Moonraker to confirm the printer is idle.")
    if busy:
        return _refused("Refused: a print is in progress.")
    return _result(*await _run_rc(["sudo", "-n", "systemctl", "reboot"]))
