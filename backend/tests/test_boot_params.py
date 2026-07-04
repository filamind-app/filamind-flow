"""Host Control - boot-parameter editing (device-tree overlays / kernel args).

Covers the minimal-diff parsers (round-trip + surgical edits), platform detection, the two-phase
gated apply (preview vs write), the backup/reboot safety, and op validation. The parsers are pure;
the sudo-backed writes are exercised with `_run_rc` / `_boot_is_regular` monkeypatched.
"""

from __future__ import annotations

import pytest

from app.services import host_control_service as hc

ARMBIAN_SAMPLE = """verbosity=1
bootlogo=true
overlay_prefix=rk3566
#
## comment kept verbatim
overlays=dsi
extraargs=cma=256M
"""

CONFIG_SAMPLE = """# rpi config
dtparam=audio=on
enable_uart=1
[pi4]
dtoverlay=vc4-kms-v3d
[all]
gpu_mem=64
"""


# --- round-trip (byte-for-byte) ------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        ARMBIAN_SAMPLE,
        CONFIG_SAMPLE,
        "console=serial0,115200 root=/dev/mmcblk0p2 rootwait\n",
        "",  # empty file
        "overlays=dsi",  # no trailing newline
        "\n",  # a lone newline
    ],
)
def test_line_model_round_trips(text: str) -> None:
    """The line model must reproduce a file byte-for-byte (including trailing-newline state)."""
    assert hc._from_lines(*hc._to_lines(text)) == text


# --- armbianEnv.txt minimal-diff edits -----------------------------------------


def test_armbian_add_overlay_is_minimal() -> None:
    out = hc._boot_apply_ops(
        "/boot/armbianEnv.txt",
        ARMBIAN_SAMPLE,
        "armbian",
        [{"op": "add_overlay", "name": "mcp2515"}],
    )
    assert "overlays=dsi mcp2515\n" in out
    assert "## comment kept verbatim" in out  # untouched lines preserved
    assert out.count("\n") == ARMBIAN_SAMPLE.count("\n")  # only one line changed, none added


def test_armbian_remove_last_overlay_keeps_key() -> None:
    out = hc._boot_apply_ops(
        "/boot/armbianEnv.txt", ARMBIAN_SAMPLE, "armbian", [{"op": "remove_overlay", "name": "dsi"}]
    )
    assert "overlays=\n" in out  # the key stays, value emptied - never deleted


def test_armbian_set_key_preserves_other_lines() -> None:
    out = hc._boot_apply_ops(
        "/boot/armbianEnv.txt",
        ARMBIAN_SAMPLE,
        "armbian",
        [{"op": "set_key", "key": "console", "value": "display"}],
    )
    assert "console=display\n" in out  # appended (absent key)
    assert "verbosity=1\n" in out


def test_armbian_set_extraarg_replaces_token() -> None:
    out = hc._boot_apply_ops(
        "/boot/armbianEnv.txt",
        ARMBIAN_SAMPLE,
        "armbian",
        [{"op": "set_extraarg", "key": "cma", "value": "512M"}],
    )
    assert "extraargs=cma=512M\n" in out


# --- config.txt scope handling -------------------------------------------------


def test_config_append_lands_in_global_scope() -> None:
    """A new dtparam must be inserted BEFORE the first [filter] header, not swallowed by [pi4]."""
    out = hc._boot_apply_ops(
        "/boot/config.txt",
        CONFIG_SAMPLE,
        "config",
        [{"op": "set_dtparam", "key": "spi", "value": "on"}],
    )
    lines = out.splitlines()
    assert "dtparam=spi=on" in lines
    assert lines.index("dtparam=spi=on") < lines.index("[pi4]")  # global scope


def test_config_set_dtparam_replaces_in_place() -> None:
    out = hc._boot_apply_ops(
        "/boot/config.txt",
        CONFIG_SAMPLE,
        "config",
        [{"op": "set_dtparam", "key": "audio", "value": "off"}],
    )
    assert "dtparam=audio=off" in out
    assert "dtparam=audio=on" not in out  # replaced, not duplicated


def test_config_edit_targets_all_scope_not_a_duplicate() -> None:
    """A curated edit of a directive that lives under [all] must REPLACE it there - not append a
    global duplicate that the later [all] value silently overrides."""
    out = hc._boot_apply_ops(
        "/boot/config.txt",
        CONFIG_SAMPLE,
        "config",
        [{"op": "set_kv", "key": "gpu_mem", "value": "128"}],
    )
    assert out.count("gpu_mem=") == 1  # the [all] line edited in place, no duplicate
    assert "gpu_mem=128" in out and "gpu_mem=64" not in out


def test_config_remove_reaches_all_scope() -> None:
    out = hc._boot_apply_ops(
        "/boot/config.txt", CONFIG_SAMPLE, "config", [{"op": "remove_kv", "key": "gpu_mem"}]
    )
    assert "gpu_mem" not in out  # the [all] assignment is removed, not left behind


def test_config_edit_preserves_model_specific_section() -> None:
    """A model-specific [pi4] line is NOT the editable scope - it must be left untouched."""
    out = hc._boot_apply_ops(
        "/boot/config.txt",
        CONFIG_SAMPLE,
        "config",
        [{"op": "remove_dtoverlay", "name": "vc4-kms-v3d"}],
    )
    assert "dtoverlay=vc4-kms-v3d" in out  # under [pi4] - preserved


def test_config_add_dtoverlay_upserts_by_name() -> None:
    """Re-adding an overlay with different params replaces it by name (an edit, not a conflicting
    second instance)."""
    before = "dtoverlay=w1-gpio,gpiopin=4\n"
    out = hc._boot_apply_ops(
        "/boot/config.txt",
        before,
        "config",
        [{"op": "add_dtoverlay", "name": "w1-gpio", "params": "gpiopin=17"}],
    )
    assert out.count("dtoverlay=w1-gpio") == 1 and "gpiopin=17" in out and "gpiopin=4" not in out


def test_config_add_dtoverlay_with_params() -> None:
    out = hc._boot_apply_ops(
        "/boot/config.txt",
        CONFIG_SAMPLE,
        "config",
        [
            {
                "op": "add_dtoverlay",
                "name": "mcp2515-can0",
                "params": "oscillator=16000000,interrupt=25",
            }
        ],
    )
    assert "dtoverlay=mcp2515-can0,oscillator=16000000,interrupt=25" in out


# --- cmdline.txt single-line invariant -----------------------------------------


def test_cmdline_edits_stay_one_line() -> None:
    before = "console=serial0,115200 root=/dev/mmcblk0p2 rootwait\n"
    out = hc._boot_apply_ops(
        "/boot/cmdline.txt", before, "cmdline", [{"op": "remove_token_key", "key": "console"}]
    )
    assert out.count("\n") == 1 and out.endswith("\n")
    assert "console=" not in out and "root=/dev/mmcblk0p2" in out


def test_cmdline_rejects_whitespace_token() -> None:
    with pytest.raises(ValueError):
        hc._boot_apply_ops(
            "/boot/cmdline.txt", "root=x\n", "cmdline", [{"op": "add_token", "token": "a b"}]
        )


# --- op validation -------------------------------------------------------------


def test_bad_op_value_raises() -> None:
    with pytest.raises(ValueError):
        hc._boot_apply_ops(
            "/boot/armbianEnv.txt", "", "armbian", [{"op": "add_overlay", "name": "bad name!"}]
        )


def test_unknown_op_raises() -> None:
    with pytest.raises(ValueError):
        hc._boot_apply_ops("/boot/armbianEnv.txt", "", "armbian", [{"op": "nope"}])


# --- platform detection --------------------------------------------------------


def test_detect_armbian_first(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        hc, "_boot_is_regular", lambda p: p in (hc._ARMBIAN_ENV, "/boot/config.txt")
    )
    plat = hc.detect_boot_platform()
    assert plat["platform"] == "armbian" and plat["config_path"] == hc._ARMBIAN_ENV


def test_detect_rpi_prefers_firmware(monkeypatch: pytest.MonkeyPatch) -> None:
    present = {"/boot/firmware/config.txt", "/boot/firmware/cmdline.txt"}
    monkeypatch.setattr(hc, "_boot_is_regular", lambda p: p in present)
    plat = hc.detect_boot_platform()
    assert plat["platform"] == "rpi"
    assert plat["config_path"] == "/boot/firmware/config.txt"
    assert plat["cmdline_path"] == "/boot/firmware/cmdline.txt"


def test_detect_unknown_read_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hc, "_boot_is_regular", lambda p: False)
    assert hc.read_boot_params() == {
        "platform": "unknown",
        "editable": False,
        "reboot_required": False,
        "files": [],
    }


# --- gated apply / preview -----------------------------------------------------

_ARMBIAN_PLAT = {"platform": "armbian", "config_path": hc._ARMBIAN_ENV, "cmdline_path": None}


async def test_preview_returns_diff_without_writing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hc, "detect_boot_platform", lambda: _ARMBIAN_PLAT)
    monkeypatch.setattr(hc, "_read", lambda p: ARMBIAN_SAMPLE)

    async def _fail(*_a: object, **_k: object) -> tuple[int, str]:
        raise AssertionError("preview must not run a privileged command")

    monkeypatch.setattr(hc, "_run_rc", _fail)
    res = await hc.apply_boot_change(
        {"file": "armbianEnv.txt", "ops": [{"op": "add_overlay", "name": "mcp2515"}]},
        dry_run=True,
        confirm=False,
        before_hash=None,
    )
    assert res["ok"] and res["diff"] and res["before_hash"] and "validation" in res


async def test_apply_requires_before_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    """A real apply must carry the preview hash (optimistic concurrency) - None is refused."""
    monkeypatch.setattr(hc, "detect_boot_platform", lambda: _ARMBIAN_PLAT)
    monkeypatch.setattr(hc, "_read", lambda p: ARMBIAN_SAMPLE)
    res = await hc.apply_boot_change(
        {"file": "armbianEnv.txt", "ops": [{"op": "add_overlay", "name": "mcp2515"}]},
        dry_run=False,
        confirm=True,
        before_hash=None,
    )
    assert res["refused"]


async def test_apply_stale_hash_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hc, "detect_boot_platform", lambda: _ARMBIAN_PLAT)
    monkeypatch.setattr(hc, "_read", lambda p: ARMBIAN_SAMPLE)
    res = await hc.apply_boot_change(
        {"file": "armbianEnv.txt", "ops": [{"op": "add_overlay", "name": "mcp2515"}]},
        dry_run=False,
        confirm=True,
        before_hash="stale",
    )
    assert res["refused"] and "changed" in res["output"]


async def test_apply_writes_via_backup_then_cp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hc, "detect_boot_platform", lambda: _ARMBIAN_PLAT)
    monkeypatch.setattr(hc, "_read", lambda p: ARMBIAN_SAMPLE)
    monkeypatch.setattr(hc, "_boot_is_regular", lambda p: True)
    monkeypatch.setattr(hc, "_list_boot_backups", lambda p: [])
    calls: list[list[str]] = []

    async def _rc(cmd: list[str], timeout: float = 10.0) -> tuple[int, str]:
        calls.append(cmd)
        return 0, ""

    monkeypatch.setattr(hc, "_run_rc", _rc)
    bh = hc._sha256(ARMBIAN_SAMPLE)
    res = await hc.apply_boot_change(
        {"file": "armbianEnv.txt", "ops": [{"op": "add_overlay", "name": "mcp2515"}]},
        dry_run=False,
        confirm=True,
        before_hash=bh,
    )
    assert res["ok"] and res["reboot_required"] is True
    assert calls[0][:4] == ["sudo", "-n", "cp", "-a"]  # backup first
    assert (
        calls[1][:3] == ["sudo", "-n", "cp"] and calls[1][-1] == hc._ARMBIAN_ENV
    )  # then the write


async def test_apply_no_effective_change(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hc, "detect_boot_platform", lambda: _ARMBIAN_PLAT)
    monkeypatch.setattr(hc, "_read", lambda p: ARMBIAN_SAMPLE)
    bh = hc._sha256(ARMBIAN_SAMPLE)
    res = await hc.apply_boot_change(
        {
            "file": "armbianEnv.txt",
            "ops": [{"op": "add_overlay", "name": "dsi"}],
        },  # already present
        dry_run=False,
        confirm=True,
        before_hash=bh,
    )
    assert res["ok"] and "No change" in res["output"]


# --- reboot gating -------------------------------------------------------------


async def test_reboot_requires_typed_token() -> None:
    res = await hc.reboot_host_for_boot("nope", "http://x")
    assert res["refused"]


async def test_reboot_refused_while_printing(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _busy(_client: object) -> bool:
        return True

    monkeypatch.setattr(hc.printer_guard, "is_busy", _busy)
    res = await hc.reboot_host_for_boot("REBOOT", "http://x")
    assert res["refused"] and "print" in res["output"].lower()
