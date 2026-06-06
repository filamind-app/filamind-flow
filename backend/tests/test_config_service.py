"""Tests for the Config Editor read path (config_service)."""

from __future__ import annotations

from typing import Any

import pytest

from app.services import config_service

SAMPLE = """\
# printer.cfg
[stepper_x]
step_pin: PF13
rotation_distance: 40  # 20T pulley

[tmc2209 stepper_x]
uart_pin: PC4
run_current: 0.8

[extruder]
nozzle_diameter = 0.4
gcode:
    G1 X10 F3000
    G1 Y10 F3000

#*# <---------- SAVE_CONFIG ---------->
#*# [extruder]
#*# pid_kp = 21.527
"""


def test_build_file_view_structure() -> None:
    view = config_service.build_file_view("printer.cfg", SAMPLE)
    assert view["filename"] == "printer.cfg"
    assert view["raw"] == SAMPLE
    headers = [s["header"] for s in view["sections"]]
    assert headers == ["stepper_x", "tmc2209 stepper_x", "extruder", "#*#"]
    # The SAVE_CONFIG pseudo-section is excluded from the editable count.
    assert view["section_count"] == 3


def test_build_file_view_section_type_and_name() -> None:
    view = config_service.build_file_view("printer.cfg", SAMPLE)
    by_header = {s["header"]: s for s in view["sections"]}
    assert by_header["stepper_x"]["type"] == "stepper_x"
    assert by_header["stepper_x"]["name"] == ""
    assert by_header["tmc2209 stepper_x"]["type"] == "tmc2209"
    assert by_header["tmc2209 stepper_x"]["name"] == "stepper_x"
    assert by_header["#*#"]["is_save_config"] is True


def test_build_file_view_params_and_separator_and_comment() -> None:
    view = config_service.build_file_view("printer.cfg", SAMPLE)
    stepper = next(s for s in view["sections"] if s["header"] == "stepper_x")
    rot = next(p for p in stepper["params"] if p["key"] == "rotation_distance")
    assert rot["value"] == "40"
    assert rot["separator"] == ":"
    assert rot["comment"] == "# 20T pulley"
    extruder = next(s for s in view["sections"] if s["header"] == "extruder")
    nozzle = next(p for p in extruder["params"] if p["key"] == "nozzle_diameter")
    assert nozzle["separator"] == "="
    gcode = next(p for p in extruder["params"] if p["key"] == "gcode")
    assert "G1 X10 F3000" in gcode["value"]  # multi-line value preserved


def test_build_file_view_flags_duplicate_sections() -> None:
    dup = "[stepper_x]\nstep_pin: PA1\n\n[stepper_x]\nstep_pin: PA2\n"
    view = config_service.build_file_view("printer.cfg", dup)
    levels = {i["level"] for i in view["issues"]}
    assert "error" in levels
    assert any("Duplicate" in i["message"] for i in view["issues"])


def test_is_config_file() -> None:
    assert config_service._is_config_file("printer.cfg")
    assert config_service._is_config_file("macros/print.CFG")
    assert config_service._is_config_file("moonraker.conf")
    assert not config_service._is_config_file("notes.txt")
    assert not config_service._is_config_file("image.png")


@pytest.mark.parametrize("bad", ["../secrets", "/etc/passwd", "a/../../b", ""])
def test_reject_unsafe_paths(bad: str) -> None:
    with pytest.raises(ValueError):
        config_service._reject_unsafe(bad)


def test_accepts_safe_nested_path() -> None:
    config_service._reject_unsafe("macros/print.cfg")  # does not raise


class _FakeClient:
    """Stub MoonrakerClient with just the two methods config_service uses."""

    def __init__(self, files: list[dict[str, Any]], text: str) -> None:
        self._files = files
        self._text = text
        self.requested: str | None = None

    async def list_files(self, root: str = "config") -> list[dict[str, Any]]:
        return self._files

    async def get_file_text(self, path: str, root: str = "config") -> str:
        self.requested = path
        return self._text


async def test_list_config_files_filters_and_sorts() -> None:
    client = _FakeClient(
        files=[
            {"path": "zzz.cfg", "size": 10, "modified": 2.0},
            {"path": "notes.txt", "size": 5, "modified": 1.0},
            {"path": "aaa.conf", "size": 7, "modified": 3.0},
        ],
        text="",
    )
    files = await config_service.list_config_files(client)  # type: ignore[arg-type]
    assert [f["path"] for f in files] == ["aaa.conf", "zzz.cfg"]
    assert files[0]["size"] == 7


async def test_read_config_file_returns_view() -> None:
    client = _FakeClient(files=[], text=SAMPLE)
    view = await config_service.read_config_file(client, "printer.cfg")  # type: ignore[arg-type]
    assert client.requested == "printer.cfg"
    assert view["section_count"] == 3


async def test_read_config_file_rejects_unsafe() -> None:
    client = _FakeClient(files=[], text=SAMPLE)
    with pytest.raises(ValueError):
        await config_service.read_config_file(client, "../moonraker.conf")  # type: ignore[arg-type]


# ── route-level tests ────────────────────────────────────────────────────────
def _app() -> Any:
    from app.config import Settings, get_settings
    from app.main import create_app

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(moonraker_url="http://127.0.0.1:1")
    return app


def test_route_files_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    async def fake_list(_client: Any) -> list[dict[str, Any]]:
        return [{"path": "printer.cfg", "size": 12, "modified": 1.0}]

    monkeypatch.setattr(config_service, "list_config_files", fake_list)
    resp = TestClient(_app()).get("/api/config/files")
    assert resp.status_code == 200
    assert resp.json() == {"files": [{"path": "printer.cfg", "size": 12, "modified": 1.0}]}


def test_route_file_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    async def fake_read(_client: Any, filename: str) -> dict[str, Any]:
        return config_service.build_file_view(filename, SAMPLE)

    monkeypatch.setattr(config_service, "read_config_file", fake_read)
    resp = TestClient(_app()).get("/api/config/file", params={"filename": "printer.cfg"})
    assert resp.status_code == 200
    assert resp.json()["section_count"] == 3


def test_route_file_unsafe_path_400() -> None:
    from fastapi.testclient import TestClient

    # No monkeypatch: read_config_file's guard rejects before any network call.
    resp = TestClient(_app()).get("/api/config/file", params={"filename": "../secrets"})
    assert resp.status_code == 400
