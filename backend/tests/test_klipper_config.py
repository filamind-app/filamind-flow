"""Tests for the round-trip Klipper INI engine."""

from __future__ import annotations

from app.services import klipper_config as kc

# A representative config: leading comment, a [stepper_x] with a multi-line value and an
# inline comment, a [tmc2209 stepper_x] (header with a name), an [extruder] using '=' as
# the separator, a full-line comment, and an auto-saved SAVE_CONFIG block.
SAMPLE = """\
# printer.cfg — representative sample
[stepper_x]
step_pin: PF13
dir_pin: !PF12
rotation_distance: 40  # 20T pulley
homing_speed: 50
position_endstop: 0

[tmc2209 stepper_x]
uart_pin: PC4
run_current: 0.8
# tuned for cool running
stealthchop_threshold: 999999

[extruder]
nozzle_diameter = 0.4
filament_diameter = 1.750

[gcode_macro PRIME_LINE]
gcode:
    G1 X10 F3000
    G1 Y10 F3000
    G1 E5 F300

#*# <---------- SAVE_CONFIG ---------->
#*# DO NOT EDIT THIS BLOCK OR BELOW. The contents are auto-generated.
#*#
#*# [extruder]
#*# pid_kp = 21.527
#*# pid_ki = 1.207
"""


def test_roundtrip_full_sample() -> None:
    assert kc.dump(kc.parse(SAMPLE)) == SAMPLE


def test_roundtrip_no_trailing_newline() -> None:
    text = "[stepper_y]\nstep_pin: PG0\n"
    assert kc.dump(kc.parse(text)) == text
    no_nl = "[stepper_y]\nstep_pin: PG0"
    assert kc.dump(kc.parse(no_nl)) == no_nl


def test_roundtrip_crlf_preserved() -> None:
    text = "[stepper_x]\r\nstep_pin: PF13\r\n"
    assert kc.dump(kc.parse(text)) == text


def test_read_param_and_separator() -> None:
    cfg = kc.parse(SAMPLE)
    stepper = cfg.get("stepper_x")
    assert stepper is not None
    assert stepper.value("rotation_distance") == "40"
    assert stepper.get("step_pin") is not None
    assert stepper.get("step_pin").separator == ":"
    extruder = cfg.get("extruder")
    assert extruder is not None
    assert extruder.value("nozzle_diameter") == "0.4"
    assert extruder.get("nozzle_diameter").separator == "="


def test_header_name_split() -> None:
    cfg = kc.parse(SAMPLE)
    tmc = cfg.get("tmc2209 stepper_x")
    assert tmc is not None
    assert tmc.name == "stepper_x"
    assert tmc.value("run_current") == "0.8"
    # Single-token header has an empty name.
    assert cfg.get("extruder").name == ""


def test_section_header_with_trailing_inline_comment() -> None:
    """Klipper accepts a comment after a section header's ``]`` — the section must still parse
    (header without the comment) and round-trip byte-for-byte (raw line keeps the comment)."""
    src = "[stepper_z] # Z motor\nstep_pin: PA1\n\n[gcode_macro FOO] ; note\ngcode:\n  M117 hi\n"
    cfg = kc.parse(src)
    assert cfg.get("stepper_z") is not None
    assert cfg.get("stepper_z").value("step_pin") == "PA1"
    assert cfg.get("gcode_macro FOO") is not None
    assert kc.dump(cfg) == src  # the trailing comment survives verbatim
    # A line with non-comment text after ``]`` is not a section header.
    assert kc.parse("[x] y z\n").get("x") is None


def test_inline_comment_preserved_on_param() -> None:
    cfg = kc.parse(SAMPLE)
    rd = cfg.get("stepper_x").get("rotation_distance")
    assert rd is not None
    assert rd.comment is not None
    assert "20T pulley" in rd.comment


def test_full_line_comment_kept_in_section() -> None:
    cfg = kc.parse(SAMPLE)
    tmc = cfg.get("tmc2209 stepper_x")
    assert tmc is not None
    assert any("tuned for cool running" in line for line in tmc.raw_lines)


def test_multiline_value_folded() -> None:
    cfg = kc.parse(SAMPLE)
    macro = cfg.get("gcode_macro PRIME_LINE")
    assert macro is not None
    gcode = macro.get("gcode")
    assert gcode is not None
    assert gcode.value.count("\n") == 3
    assert "G1 E5 F300" in gcode.value


def test_save_config_block_roundtrips() -> None:
    cfg = kc.parse(SAMPLE)
    save = cfg.get(kc.SAVE_CONFIG_MARKER)
    assert save is not None
    assert any("pid_kp" in line for line in save.raw_lines)
    # The auto-saved block is excluded from validation noise.
    assert kc.validate(cfg) == []


def test_validate_flags_duplicate_section() -> None:
    text = "[stepper_x]\nstep_pin: PF13\n\n[stepper_x]\nstep_pin: PF14\n"
    issues = kc.validate(kc.parse(text))
    assert any(i["level"] == "error" and "Duplicate" in i["message"] for i in issues)
    dup = next(i for i in issues if "Duplicate" in i["message"])
    assert dup["section"] == "stepper_x"


def test_validate_flags_param_outside_section() -> None:
    text = "orphan_key: 5\n[stepper_x]\nstep_pin: PF13\n"
    issues = kc.validate(kc.parse(text))
    assert any(i["level"] == "warning" and "outside any section" in i["message"] for i in issues)


def test_validate_clean_config_has_no_issues() -> None:
    text = "[stepper_x]\nstep_pin: PF13\n\n[extruder]\nnozzle_diameter: 0.4\n"
    assert kc.validate(kc.parse(text)) == []
