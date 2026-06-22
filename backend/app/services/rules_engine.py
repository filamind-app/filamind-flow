"""Rules engine - safe-by-default IF-THEN automation over polled Moonraker state.

The rule set + a master on/off switch live in ``<data_dir>/rules.json``; a capped fire log lives in
``<data_dir>/rules-log.json``. The engine is **OFF by default** and each rule is armed individually,
so nothing runs autonomously until the operator opts in twice (master + per-rule). A background tick
(wired in the app lifespan) polls Moonraker, evaluates each armed rule, and fires on the *rising
edge* of its condition - once per crossing, not every tick. Actions are a logged notification or a
gcode script routed through :mod:`printer_guard` (refused while busy). Every outcome is logged.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

import httpx

from app.services import printer_guard
from app.services.moonraker_client import MoonrakerClient

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_HEATERS = ("extruder", "extruder1", "extruder2", "heater_bed")
TRIGGERS = ("print_complete", "print_error", "temp_above", "temp_below")
ACTIONS = ("notify", "gcode")
_LOG_CAP = 50
_GCODE_MAX = 256


def _rules_path(data_dir: str) -> str:
    return os.path.join(os.path.expanduser(data_dir), "rules.json")


def _log_path(data_dir: str) -> str:
    return os.path.join(os.path.expanduser(data_dir), "rules-log.json")


def _read_json(path: str, default: Any) -> Any:
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
    os.replace(tmp, path)


def load_state(data_dir: str) -> dict[str, Any]:
    """The engine config: ``{enabled: bool, rules: [...]}``."""
    data = _read_json(_rules_path(data_dir), {})
    return {
        "enabled": bool(data.get("enabled", False)),
        "rules": data.get("rules", []) if isinstance(data.get("rules"), list) else [],
    }


def _save_state(data_dir: str, state: dict[str, Any]) -> None:
    _write_json(_rules_path(data_dir), state)


def read_log(data_dir: str) -> list[dict[str, Any]]:
    log = _read_json(_log_path(data_dir), [])
    return log if isinstance(log, list) else []


def _append_log(data_dir: str, entry: dict[str, Any]) -> None:
    log = read_log(data_dir)
    log.insert(0, entry)
    _write_json(_log_path(data_dir), log[:_LOG_CAP])


def validate_rule(rule: dict[str, Any]) -> dict[str, Any]:
    """Normalise + bounds-check a rule; raises ValueError on anything unsafe."""
    name = str(rule.get("name", "")).strip() or "Rule"
    trigger = rule.get("trigger") or {}
    action = rule.get("action") or {}
    t_type = str(trigger.get("type", ""))
    a_type = str(action.get("type", ""))
    if t_type not in TRIGGERS:
        raise ValueError("unknown trigger type")
    if a_type not in ACTIONS:
        raise ValueError("unknown action type")

    out_trigger: dict[str, Any] = {"type": t_type}
    if t_type in ("temp_above", "temp_below"):
        heater = str(trigger.get("heater", ""))
        if heater not in _HEATERS:
            raise ValueError("unknown heater")
        value = float(trigger.get("value", 0))
        if not (0 <= value <= 500):
            raise ValueError("threshold out of range")
        out_trigger["heater"] = heater
        out_trigger["value"] = value

    out_action: dict[str, Any] = {"type": a_type}
    if a_type == "notify":
        out_action["message"] = str(action.get("message", "")).strip()[:280]
    else:  # gcode
        gcode = str(action.get("gcode", "")).strip()
        if not gcode or len(gcode) > _GCODE_MAX:
            raise ValueError("gcode missing or too long")
        out_action["gcode"] = gcode

    rid = str(rule.get("id", "")) or _slug(name)
    if not _ID_RE.match(rid):
        rid = _slug(name)
    return {
        "id": rid,
        "name": name[:80],
        "enabled": bool(rule.get("enabled", False)),
        "trigger": out_trigger,
        "action": out_action,
    }


def _slug(name: str) -> str:
    base = re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", name.lower())).strip("-") or "rule"
    return f"{base[:48]}-{int(time.time())}"


def list_rules(data_dir: str) -> dict[str, Any]:
    return load_state(data_dir)


def set_engine_enabled(data_dir: str, enabled: bool) -> dict[str, Any]:
    state = load_state(data_dir)
    state["enabled"] = bool(enabled)
    _save_state(data_dir, state)
    return state


def upsert_rule(data_dir: str, rule: dict[str, Any]) -> dict[str, Any]:
    """Create or replace a rule (matched by id). Returns the stored rule."""
    norm = validate_rule(rule)
    state = load_state(data_dir)
    rules = [r for r in state["rules"] if r.get("id") != norm["id"]]
    rules.append(norm)
    state["rules"] = rules
    _save_state(data_dir, state)
    return norm


def delete_rule(data_dir: str, rule_id: str) -> bool:
    state = load_state(data_dir)
    before = len(state["rules"])
    state["rules"] = [r for r in state["rules"] if r.get("id") != rule_id]
    _save_state(data_dir, state)
    return len(state["rules"]) < before


def objects_needed(rules: list[dict[str, Any]]) -> list[str]:
    """Moonraker objects to query for the given rules."""
    objs = {"print_stats", "webhooks"}
    for r in rules:
        trig = r.get("trigger") or {}
        if trig.get("type") in ("temp_above", "temp_below") and trig.get("heater"):
            objs.add(str(trig["heater"]))
    return sorted(objs)


def condition_met(rule: dict[str, Any], status: dict[str, Any]) -> bool:
    """Whether a rule's trigger condition currently holds, given a Moonraker status map."""
    trig = rule.get("trigger") or {}
    t_type = trig.get("type")
    print_state = str((status.get("print_stats") or {}).get("state", "")).lower()
    klippy = str((status.get("webhooks") or {}).get("state", "")).lower()
    if t_type == "print_complete":
        return print_state == "complete"
    if t_type == "print_error":
        return print_state == "error" or klippy in ("error", "shutdown")
    if t_type in ("temp_above", "temp_below"):
        heater = str(trig.get("heater", ""))
        temp = (status.get(heater) or {}).get("temperature")
        if not isinstance(temp, (int, float)):
            return False
        thr = float(trig.get("value", 0))
        return temp >= thr if t_type == "temp_above" else temp <= thr
    return False


async def _fire(data_dir: str, rule: dict[str, Any], client: MoonrakerClient) -> None:
    """Run a rule's action (notify = log only; gcode = gated run). Always logs the outcome."""
    action = rule.get("action") or {}
    a_type = action.get("type")
    base = {"time": time.time(), "rule": rule.get("name", ""), "trigger": rule["trigger"]["type"]}
    if a_type == "notify":
        _append_log(data_dir, {**base, "outcome": "notify", "message": action.get("message", "")})
        return
    # gcode action - gated; never runs on a busy printer
    try:
        if await printer_guard.is_busy(client):
            _append_log(
                data_dir, {**base, "outcome": "skipped_busy", "gcode": action.get("gcode", "")}
            )
            return
        await client.run_gcode(str(action.get("gcode", "")))
    except httpx.HTTPError as exc:
        _append_log(data_dir, {**base, "outcome": "error", "error": str(exc)})
        return
    _append_log(data_dir, {**base, "outcome": "ran", "gcode": action.get("gcode", "")})


async def tick(
    data_dir: str, moonraker_url: str, prev: dict[str, bool], timeout: float = 10.0
) -> dict[str, bool]:
    """One evaluation pass. Fires each armed rule on the rising edge of its condition.

    ``prev`` maps rule-id -> last condition value; returns the updated map. A no-op (returns
    ``prev``) when the engine is disabled or no rule is armed.
    """
    state = load_state(data_dir)
    if not state["enabled"]:
        return prev
    armed = [r for r in state["rules"] if r.get("enabled")]
    if not armed:
        return prev
    client = MoonrakerClient(moonraker_url, timeout=timeout)
    try:
        status = await client.query_objects(objects_needed(armed))
    except httpx.HTTPError:
        return prev
    new_prev = dict(prev)
    for rule in armed:
        rid = rule["id"]
        now = condition_met(rule, status)
        if now and not prev.get(rid, False):  # rising edge
            await _fire(data_dir, rule, client)
        new_prev[rid] = now
    return new_prev
