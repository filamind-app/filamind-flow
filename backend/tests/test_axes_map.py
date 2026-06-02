from __future__ import annotations

import numpy as np
import pytest

from app.services import axes_map_service, shaper_service

_FS = 3200.0
_N = 4000
_GRAVITY = 9810.0


def _synth(
    accel_col: int | None, sign: float = 1.0, *, gravity_col: int = 3, seed: int = 0
) -> bytes:
    """A synthetic per-axis capture: a +then- accel pulse (→ a velocity bump) on
    ``accel_col`` (1=x,2=y,3=z), gravity on ``gravity_col``, plus light noise.
    ``accel_col=None`` → a noise-only axis (bed-slinger: no toolhead motion)."""
    rng = np.random.default_rng(seed)
    t = np.arange(_N) / _FS
    data = np.zeros((_N, 4))
    data[:, 0] = t
    data[:, gravity_col] += _GRAVITY
    if accel_col is not None:
        half = _N // 2
        pulse = np.empty(_N)
        pulse[:half] = sign * 3000.0
        pulse[half:] = -sign * 3000.0
        data[:, accel_col] += pulse
    data[:, 1:] += rng.normal(0, 20.0, size=(_N, 3))
    lines = ["#time,accel_x,accel_y,accel_z"]
    lines += [f"{r[0]:.6f},{r[1]:.2f},{r[2]:.2f},{r[3]:.2f}" for r in data]
    return ("\n".join(lines) + "\n").encode()


def test_identity_mount_detects_xyz() -> None:
    result = axes_map_service.analyze_axesmap(
        _synth(1, seed=1), _synth(2, seed=2), _synth(3, seed=3), accel=3000.0
    )
    assert result["axes_map"] == "x, y, z"
    assert result["status"] in ("ok", "warning")
    assert result["gravity"] == pytest.approx(9.81, abs=0.6)
    assert result["matches_current"] is None  # nothing configured to compare
    assert len(result["velocity_series"]) == 3


def test_rotated_mount_detected_and_compared() -> None:
    # Sensor rotated: machine X→accel y(+), Y→accel x(-), Z→accel z(+).
    result = axes_map_service.analyze_axesmap(
        _synth(2, 1.0, seed=4),
        _synth(1, -1.0, seed=5),
        _synth(3, 1.0, seed=6),
        current_axes_map="x, y, z",
        accel=3000.0,
    )
    assert result["axes_map"] == "y, -x, z"
    assert result["matches_current"] is None  # current is identity → nothing to compare
    # All three accel axes are used exactly once.
    assert {m["accel_axis"] for m in result["mappings"]} == {"x", "y", "z"}


def test_configured_axes_map_is_inverted_then_round_trips() -> None:
    # When a non-identity axes_map is configured, the service inverts it to recover
    # raw readings; feeding identity captures + that map round-trips back to it.
    result = axes_map_service.analyze_axesmap(
        _synth(1, seed=7), _synth(2, seed=8), _synth(3, seed=9), current_axes_map="-z, y, x"
    )
    assert result["axes_map"] == "-z, y, x"
    assert result["matches_current"] is True


def test_two_axis_machine_extrapolates_missing_axis() -> None:
    # Bed-slinger: no toolhead signal on Y (the bed moves there).
    result = axes_map_service.analyze_axesmap(
        _synth(1, seed=10), _synth(None, seed=11), _synth(3, seed=12), accel=3000.0
    )
    assert result["extrapolated_axis"] == 1  # Y was reconstructed
    assert result["mappings"][1]["extrapolated"] is True
    # Still a valid, unique-axis map.
    assert {m["accel_axis"] for m in result["mappings"]} == {"x", "y", "z"}


def test_malformed_capture_raises() -> None:
    with pytest.raises(shaper_service.ShaperAnalysisError):
        axes_map_service.analyze_axesmap(b"garbage\n1,2\n", _synth(2), _synth(3))
