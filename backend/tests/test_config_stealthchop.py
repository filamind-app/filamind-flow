"""Tests for the marker-tagged temporary StealthChop config edits (pure text)."""

from __future__ import annotations

from app.services import config_stealthchop as cs

_CFG = """\
[extruder]
step_pin: PB1

[tmc2209 extruder]
uart_pin: toolhead_mcu:PB10
run_current: 0.8
sense_resistor: 0.150

[verify_heater extruder]
max_error: 120

#*# <---------------------- SAVE_CONFIG ---------------------->
#*# [tmc2209 extruder]
#*# stealthchop_threshold = 0
"""


def test_apply_inserts_marked_line_in_section() -> None:
    out, changed = cs.apply_stealthchop(_CFG, "tmc2209", 999999)
    assert changed
    lines = out.split("\n")
    hdr = lines.index("[tmc2209 extruder]")
    assert lines[hdr + 1] == f"stealthchop_threshold: 999999  {cs.MARKER}"
    # the SAVE_CONFIG autosave block (commented) is untouched
    assert "#*# stealthchop_threshold = 0" in out


def test_apply_then_comment_round_trip() -> None:
    enabled, c1 = cs.apply_stealthchop(_CFG, "tmc2209", 999999)
    assert c1
    reverted, c2 = cs.comment_stealthchop(enabled, "tmc2209")
    assert c2
    assert f"# stealthchop_threshold: 999999  {cs.MARKER}" in reverted
    # no ACTIVE stealthchop line remains in the extruder section
    assert "\nstealthchop_threshold: 999999" not in reverted


def test_apply_reactivates_commented_marker_no_duplicate() -> None:
    enabled, _ = cs.apply_stealthchop(_CFG, "tmc2209", 999999)
    commented, _ = cs.comment_stealthchop(enabled, "tmc2209")
    reenabled, changed = cs.apply_stealthchop(commented, "tmc2209", 999999)
    assert changed
    # exactly one marker line (reactivated, not duplicated)
    assert reenabled.count(cs.MARKER) == 1
    assert f"stealthchop_threshold: 999999  {cs.MARKER}" in reenabled


def test_apply_leaves_users_own_stealthchop_alone() -> None:
    cfg = _CFG.replace("sense_resistor: 0.150", "sense_resistor: 0.150\nstealthchop_threshold: 500")
    out, changed = cs.apply_stealthchop(cfg, "tmc2209", 999999)
    assert not changed
    assert out == cfg
    assert cs.MARKER not in out


def test_apply_no_section_is_noop() -> None:
    _out, changed = cs.apply_stealthchop("[printer]\nkinematics: corexy\n", "tmc2209", 999999)
    assert not changed


def test_comment_is_idempotent_and_safe() -> None:
    enabled, _ = cs.apply_stealthchop(_CFG, "tmc2209", 999999)
    once, c1 = cs.comment_stealthchop(enabled, "tmc2209")
    twice, c2 = cs.comment_stealthchop(once, "tmc2209")
    assert c1 and not c2  # second time nothing active to comment
    assert once == twice


def test_comment_noop_when_only_user_line() -> None:
    cfg = _CFG.replace("sense_resistor: 0.150", "sense_resistor: 0.150\nstealthchop_threshold: 500")
    out, changed = cs.comment_stealthchop(cfg, "tmc2209")
    assert not changed
    assert out == cfg  # never touches a non-marker line


def test_apply_noop_even_when_commented_marker_precedes_user_active_line() -> None:
    # A leftover commented marker ABOVE the user's own active line must NOT cause a duplicate.
    cfg = _CFG.replace(
        "sense_resistor: 0.150",
        f"# stealthchop_threshold: 999999  {cs.MARKER}\nstealthchop_threshold: 700",
    )
    out, changed = cs.apply_stealthchop(cfg, "tmc2209", 999999)
    assert not changed  # the user owns an active line → leave everything alone
    assert out == cfg
    active = [
        ln
        for ln in out.split("\n")
        if ln.strip().startswith("stealthchop_threshold") and not ln.strip().startswith("#")
    ]
    assert active == ["stealthchop_threshold: 700"]  # exactly one active line, the user's
