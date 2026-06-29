"""Full CAN-bus control for the printer host - view link state + bring interfaces up/down + set
bitrate, all from the panel.

A SocketCAN interface (``can0`` …) is a kernel netdev, not a Klipper MCU, so it's managed with
``ip`` rather than Klipper/Moonraker. Reading status is unprivileged (``ip … link show``); changing
it (``ip link set``) goes through the host's narrow passwordless-sudo grant (scripts/install.sh
sudoers). Every change is refused while a print is running - taking the bus down mid-print drops
every CAN MCU - and only ever targets a discovered CAN interface (never an arbitrary netdev).

This is the *control* side of CAN; flashing the USB-CAN *adapter's* firmware is a separate concern
(see ``canbus_flash.py`` / the Firmware Manager).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
from typing import Any

import httpx

from app.services import board_topology, topology_overrides
from app.services.moonraker_client import MoonrakerClient

#: A SocketCAN interface name we will act on. Restricting ``ip link set`` to this shape (and to an
#: interface we actually discovered as CAN) keeps the privileged grant from touching other netdevs.
_IFACE_RE = re.compile(r"^can[0-9]{1,2}$")

#: Sane SocketCAN bitrate bounds (bit/s). Common values: 1000000 / 500000 / 250000 / 125000.
_MIN_BITRATE = 10_000
_MAX_BITRATE = 1_000_000

_BUSY_MSG = "A print is running. Stop the print before changing the CAN bus."

#: Sudo refused / not granted - same signatures host_control_service watches for, so the UI can tell
#: "passwordless sudo isn't set up" from a genuine failure.
_SUDO_NOT_GRANTED_RE = re.compile(
    r"a password is required|not allowed to execute|must have a tty|sudo:.*(askpass|required)",
    re.IGNORECASE,
)


def _needs_setup(out: str) -> bool:
    return bool(_SUDO_NOT_GRANTED_RE.search(out))


async def _run(cmd: list[str], timeout: float = 10.0) -> tuple[int, str]:
    """Run a command, returning (returncode, combined stdout+stderr). C locale keeps sudo/ip
    messages parseable (and the sudo-not-granted signature detectable) on a non-English host."""
    env = {**os.environ, "LC_ALL": "C", "LANG": "C"}
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, env=env
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except (FileNotFoundError, NotImplementedError):
        return 127, f"{cmd[0]}: not found"
    except (OSError, asyncio.TimeoutError) as exc:
        return 1, str(exc)
    return proc.returncode or 0, out.decode("utf-8", "replace")


#: CAN control-mode flags we surface/set, mapped to how `ip` names them on the wire.
_CTRL_FLAGS: dict[str, str] = {
    "listen_only": "listen-only",
    "loopback": "loopback",
    "triple_sampling": "triple-sampling",
    "one_shot": "one-shot",
    "berr_reporting": "berr-reporting",
    "fd": "fd",
    "presume_ack": "presume-ack",
}


def _active_ctrlmodes(info: dict[str, Any]) -> set[str]:
    """The set of currently-active control modes, normalised lower-kebab. iproute2 reports them as a
    list (``ctrlmode``) or a dict of booleans depending on version - handle both."""
    cm = info.get("ctrlmode")
    if isinstance(cm, list):
        return {str(x).strip().lower() for x in cm}
    if isinstance(cm, dict):
        return {str(k).strip().lower() for k, v in cm.items() if v}
    return set()


def _d(value: Any) -> dict[str, Any]:
    """A dict, or {} - so an unexpected ``ip -json`` shape can never throw an AttributeError."""
    return value if isinstance(value, dict) else {}


def _parse_live(entry: dict[str, Any]) -> dict[str, Any]:
    """Pull the fields we surface from one ``ip -details -statistics -json link show`` record:
    link/controller state + error counters, plus the FULL tunable parameter set (bit timing,
    control modes, recovery, CAN-FD) and the controller's allowed ranges so the UI can bound it.

    Every nested lookup goes through :func:`_d` so a controller whose JSON shape differs from the
    common case (a field that is null / a list / a string) degrades to empty rather than 500-ing."""
    flags = entry.get("flags")
    link_up = "UP" in flags if isinstance(flags, list) else None
    txqlen = entry.get("txqlen")
    info = _d(_d(entry.get("linkinfo")).get("info_data"))
    berr = _d(info.get("berr_counter"))
    bt = _d(info.get("bittiming"))
    state = info.get("state")
    bitrate = bt.get("bitrate")

    # Current tunable values (omit any the controller doesn't report).
    params: dict[str, Any] = {}
    for key in ("sample_point", "sjw", "brp", "tq", "prop_seg", "phase_seg1", "phase_seg2"):
        if isinstance(bt.get(key), int | float):
            params[key] = bt[key]
    if isinstance(info.get("restart_ms"), int):
        params["restart_ms"] = info["restart_ms"]
    dbt = _d(info.get("data_bittiming"))
    if isinstance(dbt.get("bitrate"), int):
        params["dbitrate"] = dbt["bitrate"]
    if isinstance(dbt.get("sample_point"), int | float):
        params["dsample_point"] = dbt["sample_point"]
    active = _active_ctrlmodes(info)
    params["flags"] = {api: kebab in active for api, kebab in _CTRL_FLAGS.items()}

    # Controller-reported limits (drive the UI's input bounds + which params are supported).
    const = _d(info.get("bittiming_const"))
    limits: dict[str, Any] = {}
    for key in (
        "tseg1_min",
        "tseg1_max",
        "tseg2_min",
        "tseg2_max",
        "sjw_max",
        "brp_min",
        "brp_max",
    ):
        if isinstance(const.get(key), int):
            limits[key] = const[key]
    clock = _d(info.get("clock")).get("freq")
    if isinstance(clock, int):
        limits["clock_freq"] = clock
    limits["fd_supported"] = bool(info.get("data_bittiming_const"))

    return {
        "link_up": bool(link_up) if link_up is not None else None,
        # CAN controller state: ERROR-ACTIVE (healthy) / ERROR-PASSIVE / BUS-OFF / STOPPED.
        "state": str(state) if state else None,
        "errors_rx": berr["rx"] if isinstance(berr.get("rx"), int) else None,
        "errors_tx": berr["tx"] if isinstance(berr.get("tx"), int) else None,
        "txqueuelen": txqlen if isinstance(txqlen, int) else None,
        "bitrate": bitrate if isinstance(bitrate, int) else None,
        "params": params,
        "limits": limits,
    }


async def _all_live_status() -> dict[str, dict[str, Any]]:
    """Live status of every CAN interface, keyed by name, from a single ``ip`` call. ``{}`` if
    ``ip`` is missing or its JSON can't be parsed (older iproute2); the caller degrades."""
    rc, out = await _run(["ip", "-details", "-statistics", "-json", "link", "show", "type", "can"])
    if rc != 0 or not out.strip():
        return {}
    try:
        data = json.loads(out)
    except (json.JSONDecodeError, ValueError):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for entry in data if isinstance(data, list) else []:
        if isinstance(entry, dict) and entry.get("ifname"):
            # One malformed record must never sink the whole read (the panel would 500).
            with contextlib.suppress(Exception):
                result[str(entry["ifname"])] = _parse_live(entry)
    return result


async def _printer_busy(moonraker_url: str) -> bool:
    """True while a print is running/paused (Moonraker down → treated as not busy)."""
    client = MoonrakerClient(moonraker_url)
    try:
        status = await client.query_objects(["print_stats"])
    except httpx.HTTPError:
        return False
    state = str((status.get("print_stats") or {}).get("state") or "").lower()
    return state in {"printing", "paused"}


async def list_can_buses(moonraker_url: str, data_dir: str) -> list[dict[str, Any]]:
    """Every host CAN interface with its live status (link up/down, controller state, bitrate, bus
    error counters, tx queue length) plus its best-effort bridging-adapter link from the catalog.

    Sources: Moonraker ``/machine/system_info`` ``canbus`` (driver + configured bitrate + adapter
    match) merged with live ``ip`` data. Either source can be absent and the list still builds."""
    buses: list[dict[str, Any]] = []
    overrides = topology_overrides.read_overrides(data_dir)
    client = MoonrakerClient(moonraker_url)
    # Best-effort: Moonraker down, a malformed system_info, or a catalog hiccup must degrade to the
    # live `ip` data (or empty) - this read must NEVER 500 the panel.
    with contextlib.suppress(Exception):
        system_info = await client.machine_system_info()
        buses = board_topology._can_buses(system_info, overrides)

    live = await _all_live_status()
    known = {b["interface"] for b in buses}
    # CAN interfaces the kernel reports but Moonraker's system_info didn't (older Moonraker).
    for iface in live:
        if iface not in known:
            buses.append(
                {
                    "interface": iface,
                    "driver": None,
                    "bitrate": None,
                    "board_id": None,
                    "board_match": None,
                    "board_match_confidence": 0.0,
                }
            )

    for bus in buses:
        status = live.get(bus["interface"]) or {}
        bus["link_up"] = status.get("link_up")
        bus["state"] = status.get("state")
        bus["errors_rx"] = status.get("errors_rx")
        bus["errors_tx"] = status.get("errors_tx")
        bus["txqueuelen"] = status.get("txqueuelen")
        bus["params"] = status.get("params") or {}
        bus["limits"] = status.get("limits") or {}
        if status.get("bitrate"):
            bus["bitrate"] = status["bitrate"]  # live value wins over the configured one
    return buses


def _refused(message: str, iface: str = "") -> dict[str, Any]:
    return {"interface": iface, "ok": False, "refused": True, "output": message}


def _result(iface: str, rc: int, out: str) -> dict[str, Any]:
    return {
        "interface": iface,
        "ok": rc == 0,
        "refused": False,
        "output": out.strip(),
        "needs_setup": rc != 0 and _needs_setup(out),
    }


async def _require_can_iface(iface: str) -> None:
    """Reject anything that isn't a real, discovered CAN interface (raises ValueError → 400)."""
    if not _IFACE_RE.match(iface):
        raise ValueError(f"Invalid CAN interface name '{iface}'.")
    live = await _all_live_status()
    # Only enforce membership when we could actually enumerate (ip present); else trust the regex.
    if live and iface not in live:
        raise ValueError(f"'{iface}' is not a CAN interface on this host.")


async def _set_link_raw(iface: str, up: bool) -> tuple[int, str]:
    """``ip link set <iface> up|down`` with no guards (callers gate on printing/iface first)."""
    return await _run(["sudo", "-n", "ip", "link", "set", iface, "up" if up else "down"])


async def _firmware_restart(moonraker_url: str) -> tuple[bool, str]:
    """Ask Klipper for a ``FIRMWARE_RESTART`` (restarts the host + resets every MCU, so the CAN
    MCUs reconnect on the freshly-retimed bus). Best-effort: a Moonraker error is reported, not
    raised."""
    try:
        await MoonrakerClient(moonraker_url).firmware_restart()
    except httpx.HTTPError as exc:
        return False, f"Klipper restart request failed: {exc}"
    return True, "Klipper FIRMWARE_RESTART requested (host + MCUs reconnecting)."


async def set_link(iface: str, up: bool, moonraker_url: str) -> dict[str, Any]:
    """Bring a CAN interface up or down. Refused while printing. Bringing it up needs a bitrate to
    already be configured (the kernel rejects ``up`` otherwise - surfaced in the output)."""
    await _require_can_iface(iface)
    if await _printer_busy(moonraker_url):
        return _refused(_BUSY_MSG, iface)
    rc, out = await _set_link_raw(iface, up)
    return _result(iface, rc, out)


async def set_bitrate(
    iface: str, bitrate: int, moonraker_url: str, restart: bool = False
) -> dict[str, Any]:
    """Set a CAN interface's bitrate. SocketCAN can't retime a running controller, so this brings
    the interface DOWN (if up), sets the bitrate, then brings it back UP so the bus resumes. With
    ``restart`` it then triggers a Klipper FIRMWARE_RESTART so every CAN MCU reconnects on the new
    timing (a host bitrate change otherwise leaves Klipper talking to a now-mismatched/disconnected
    bus). Refused while printing."""
    await _require_can_iface(iface)
    if not _MIN_BITRATE <= bitrate <= _MAX_BITRATE:
        raise ValueError(f"Bitrate must be between {_MIN_BITRATE} and {_MAX_BITRATE} bit/s.")
    if await _printer_busy(moonraker_url):
        return _refused(_BUSY_MSG, iface)
    set_cmd = ["sudo", "-n", "ip", "link", "set", iface, "type", "can", "bitrate", str(bitrate)]
    return await _apply_cycle(
        iface, [set_cmd], needs_down=True, restart=restart, moonraker=moonraker_url
    )


async def _apply_cycle(
    iface: str,
    commands: list[list[str]],
    *,
    needs_down: bool,
    restart: bool,
    moonraker: str,
) -> dict[str, Any]:
    """Run the change commands inside a down→change→up cycle (when ``needs_down``), then optionally
    a Klipper FIRMWARE_RESTART. The interface always ends UP so the bus resumes; if bringing it
    down fails we abort before touching anything (the bus stays as it was)."""
    outputs: list[str] = []
    rc_total = 0
    was_up = bool(((await _all_live_status()).get(iface) or {}).get("link_up"))
    if needs_down and was_up:
        rc, out = await _set_link_raw(iface, False)
        outputs.append(out)
        if rc != 0:  # couldn't take it down - don't run the change; the bus is untouched
            return _result(iface, rc, "\n".join(o.strip() for o in outputs if o.strip()))
    for cmd in commands:
        rc, out = await _run(cmd)
        rc_total = rc_total or rc
        outputs.append(out)
    if (
        needs_down
    ):  # bring the bus back up so it resumes (a configured bitrate is required for `up`)
        rc, out = await _set_link_raw(iface, True)
        rc_total = rc_total or rc
        outputs.append(out)
    restarted: bool | None = None
    if restart and rc_total == 0:
        restarted, msg = await _firmware_restart(moonraker)
        outputs.append(msg)
    res = _result(iface, rc_total, "\n".join(o.strip() for o in outputs if o.strip()))
    if restarted is not None:
        res["restarted"] = restarted
    return res


#: Settable numeric CAN parameters: api key -> (ip token, kind, (min, max)). Bit timing + recovery +
#: CAN-FD data phase. (sjw is further bounded by the controller's reported sjw_max when known.)
_CAN_NUMERIC: dict[str, tuple[str, type, tuple[float, float]]] = {
    "bitrate": ("bitrate", int, (_MIN_BITRATE, _MAX_BITRATE)),
    "sample_point": ("sample-point", float, (0.0, 0.999)),
    "sjw": ("sjw", int, (1, 128)),
    "restart_ms": ("restart-ms", int, (0, 100_000)),
    "dbitrate": ("dbitrate", int, (_MIN_BITRATE, 8_000_000)),
    "dsample_point": ("dsample-point", float, (0.0, 0.999)),
    "dsjw": ("dsjw", int, (1, 128)),
}


def _validate_numeric(
    key: str, val: Any, kind: type, lo: float, hi: float, limits: dict[str, Any]
) -> float:
    if isinstance(val, bool):  # bool is an int subclass - reject so True can't read as 1
        raise ValueError(f"{key} must be a number.")
    if kind is int:
        if not isinstance(val, int):
            raise ValueError(f"{key} must be an integer.")
        num: float = val
    else:
        if not isinstance(val, int | float):
            raise ValueError(f"{key} must be a number.")
        num = float(val)
    if not lo <= num <= hi:
        raise ValueError(f"{key} must be between {lo} and {hi}.")
    if key == "sjw" and isinstance(limits.get("sjw_max"), int) and num > limits["sjw_max"]:
        raise ValueError(f"sjw must be at most {limits['sjw_max']} on this controller.")
    return num


def _build_can_args(params: dict[str, Any], limits: dict[str, Any]) -> list[str]:
    """Translate a validated param dict into ``ip link set … type can`` arguments (raises ValueError
    on an unknown key or out-of-range value, so a bad request is a 400, never a bad ip call)."""
    args: list[str] = []
    for key, val in params.items():
        if key in ("txqueuelen", "flags"):
            continue
        if key in _CAN_NUMERIC:
            token, kind, (lo, hi) = _CAN_NUMERIC[key]
            num = _validate_numeric(key, val, kind, lo, hi, limits)
            args += [token, str(int(num)) if kind is int else str(num)]
        elif key in _CTRL_FLAGS:
            if not isinstance(val, bool):
                raise ValueError(f"{key} must be true or false.")
            args += [_CTRL_FLAGS[key], "on" if val else "off"]
        else:
            raise ValueError(f"Unknown CAN parameter '{key}'.")
    return args


async def set_params(
    iface: str, params: dict[str, Any], moonraker_url: str, restart: bool = False
) -> dict[str, Any]:
    """Set any combination of CAN parameters - bit timing (bitrate/sample-point/sjw), control modes
    (listen-only/loopback/triple-sampling/one-shot/berr-reporting/fd/presume-ack), recovery
    (restart-ms), CAN-FD data phase (dbitrate/dsample-point/dsjw) and txqueuelen. All but txqueuelen
    need the interface DOWN, so this brings it down (if up), applies the change, and brings it back
    UP. With ``restart`` it then triggers a Klipper FIRMWARE_RESTART so every CAN MCU reconnects on
    the new settings. Refused while printing; values validated against the controller's limits."""
    await _require_can_iface(iface)
    if not isinstance(params, dict) or not params:
        raise ValueError("No parameters given.")
    if await _printer_busy(moonraker_url):
        return _refused(_BUSY_MSG, iface)
    status = (await _all_live_status()).get(iface) or {}
    can_args = _build_can_args(params, status.get("limits") or {})

    txq = params.get("txqueuelen")
    if txq is not None and (
        isinstance(txq, bool) or not isinstance(txq, int) or not 0 <= txq <= 100_000
    ):
        raise ValueError("txqueuelen must be an integer between 0 and 100000.")
    if not can_args and txq is None:
        raise ValueError("No recognised CAN parameters given.")

    commands: list[list[str]] = []
    if can_args:
        commands.append(["sudo", "-n", "ip", "link", "set", iface, "type", "can", *can_args])
    if txq is not None:
        commands.append(["sudo", "-n", "ip", "link", "set", iface, "txqueuelen", str(txq)])
    # Only the bit-timing/control-mode change (can_args) requires the link down; a txqueuelen-only
    # change does not, so don't disturb a running bus for it.
    return await _apply_cycle(
        iface, commands, needs_down=bool(can_args), restart=restart, moonraker=moonraker_url
    )


async def restart_klipper(moonraker_url: str) -> dict[str, Any]:
    """Trigger a Klipper FIRMWARE_RESTART (host + every MCU) so CAN MCUs reconnect after a bus
    change. Exposed as its own action so the user can restart without re-applying. Refused while
    printing (a firmware restart aborts a print)."""
    if await _printer_busy(moonraker_url):
        return _refused(_BUSY_MSG)
    ok, msg = await _firmware_restart(moonraker_url)
    return {"interface": "", "ok": ok, "refused": False, "output": msg, "needs_setup": False}


async def set_restart(iface: str, moonraker_url: str) -> dict[str, Any]:
    """Restart a BUS-OFF CAN controller (``ip link set <iface> type can restart``) to recover the
    bus after an error storm. Refused while printing."""
    await _require_can_iface(iface)
    if await _printer_busy(moonraker_url):
        return _refused(_BUSY_MSG, iface)
    rc, out = await _run(["sudo", "-n", "ip", "link", "set", iface, "type", "can", "restart"])
    return _result(iface, rc, out)
