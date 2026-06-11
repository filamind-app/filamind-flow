"""Tests for the Config Editor read path (config_service)."""

from __future__ import annotations

from typing import Any

import httpx
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


def test_project_graph_includes_and_cross_file_lint() -> None:
    files = [
        (
            "printer.cfg",
            "[include steppers.cfg]\n[include missing.cfg]\n"
            "[tmc2209 stepper_q]\nrun_current: 0.5\n"  # orphan: no [stepper_q] anywhere
            "[extruder]\nsensor_type: PT1000\n",
        ),
        (
            "steppers.cfg",
            "[stepper_x]\nstep_pin: PA1\n[tmc2209 stepper_x]\nrun_current: 0.8\n"
            "[extruder]\nnozzle_diameter: 0.4\n",  # duplicate [extruder] across files
        ),
    ]
    files.append(
        # A dated backup copy sitting in the same folder: NOT included by printer.cfg, so its
        # [extruder] must not masquerade as a cross-file duplicate of the active config.
        ("printer-20260101.cfg", "[extruder]\nnozzle_diameter: 0.4\n[stepper_z]\nstep_pin: PB0\n"),
    )
    out = config_service.project_graph_from_files(files)
    assert out["reachable"] is True
    assert out["roots"] == ["printer.cfg"]  # only the active root drives the tree
    assert "printer-20260101.cfg" not in out["active"]  # the backup is not part of the live config
    node = next(n for n in out["nodes"] if n["file"] == "printer.cfg")
    assert "steppers.cfg" in node["includes"] and "missing.cfg" in node["missing"]
    rules = {(lt["rule"], lt["message"]) for lt in out["lint"]}
    assert ("broken_include", "missing.cfg") in rules
    assert ("orphan_driver", "stepper_q") in rules
    assert ("duplicate_section", "extruder") in rules  # printer.cfg + steppers.cfg (both active)
    # The paired [tmc2209 stepper_x] is NOT an orphan (its [stepper_x] exists).
    assert ("orphan_driver", "stepper_x") not in rules
    # The backup's [extruder] is excluded, so the duplicate is only flagged across active files.
    dup = next(lt for lt in out["lint"] if lt["rule"] == "duplicate_section")
    assert "printer-20260101.cfg" not in dup["files"]


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
    """Stub MoonrakerClient covering the methods config_service uses (read + save + restart)."""

    def __init__(
        self,
        files: list[dict[str, Any]] | None = None,
        text: str = "",
        *,
        state: str = "standby",
        missing: bool = False,
    ) -> None:
        self._files = files or []
        self._text = text
        self._state = state
        self._missing = missing
        self.requested: str | None = None
        self.uploads: list[tuple[str, str]] = []
        self.restarted = False

    async def list_files(self, root: str = "config") -> list[dict[str, Any]]:
        return self._files

    async def get_file_text(self, path: str, root: str = "config") -> str:
        self.requested = path
        if self._missing:
            raise httpx.HTTPStatusError(
                "404", request=httpx.Request("GET", "http://x"), response=httpx.Response(404)
            )
        return self._text

    async def query_objects(self, objects: list[str]) -> dict[str, Any]:
        return {"print_stats": {"state": self._state}}

    async def upload_file(self, path: str, content: str, root: str = "config") -> dict[str, Any]:
        self.uploads.append((path, content))
        return {"item": {"path": path}}

    async def firmware_restart(self) -> None:
        self.restarted = True


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


# ── save / restart path ──────────────────────────────────────────────────────
async def test_save_backs_up_then_overwrites() -> None:
    client = _FakeClient(text="[old]\nk: 1\n")
    new = "[new]\nk: 2\n"
    result = await config_service.save_config_file(client, "printer.cfg", new)  # type: ignore[arg-type]
    # Two uploads: the backup (original content) first, then the new content.
    assert len(client.uploads) == 2
    backup_path, backup_content = client.uploads[0]
    file_path, file_content = client.uploads[1]
    assert backup_path.startswith("filamind-backups/")
    assert backup_content == "[old]\nk: 1\n"
    assert file_path == "printer.cfg"
    assert file_content == new
    assert result["ok"] is True
    assert result["backup"] == backup_path


async def test_save_new_file_skips_backup() -> None:
    client = _FakeClient(missing=True)  # get_file_text -> 404
    result = await config_service.save_config_file(client, "new.cfg", "[a]\n")  # type: ignore[arg-type]
    assert result["backup"] is None
    assert len(client.uploads) == 1  # only the write, no backup
    assert client.uploads[0][0] == "new.cfg"


async def test_save_refused_when_busy() -> None:
    client = _FakeClient(text="[x]\n", state="printing")
    with pytest.raises(config_service.ConfigBusyError):
        await config_service.save_config_file(client, "printer.cfg", "[x]\ny: 1\n")  # type: ignore[arg-type]
    assert client.uploads == []  # nothing written


async def test_save_rejects_unsafe_path() -> None:
    client = _FakeClient(text="[x]\n")
    with pytest.raises(ValueError):
        await config_service.save_config_file(client, "../evil.cfg", "[x]\n")  # type: ignore[arg-type]
    assert client.uploads == []


async def test_restart_calls_firmware_restart() -> None:
    client = _FakeClient()
    result = await config_service.restart_firmware(client)  # type: ignore[arg-type]
    assert client.restarted is True
    assert result["ok"] is True


async def test_restart_refused_when_busy() -> None:
    client = _FakeClient(state="paused")
    with pytest.raises(config_service.ConfigBusyError):
        await config_service.restart_firmware(client)  # type: ignore[arg-type]
    assert client.restarted is False


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


def test_route_save_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    async def fake_save(_client: Any, filename: str, content: str) -> dict[str, Any]:
        return {"ok": True, "filename": filename, "backup": "filamind-backups/x.bak", "issues": []}

    monkeypatch.setattr(config_service, "save_config_file", fake_save)
    resp = TestClient(_app()).post(
        "/api/config/save", json={"filename": "printer.cfg", "content": "[x]\n"}
    )
    assert resp.status_code == 200
    assert resp.json()["backup"] == "filamind-backups/x.bak"


def test_route_save_busy_409(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    async def fake_save(_client: Any, filename: str, content: str) -> dict[str, Any]:
        raise config_service.ConfigBusyError("busy")

    monkeypatch.setattr(config_service, "save_config_file", fake_save)
    resp = TestClient(_app()).post(
        "/api/config/save", json={"filename": "printer.cfg", "content": "[x]\n"}
    )
    assert resp.status_code == 409


def test_route_save_unsafe_400() -> None:
    from fastapi.testclient import TestClient

    # No monkeypatch: the guard rejects before any network call.
    resp = TestClient(_app()).post(
        "/api/config/save", json={"filename": "../evil.cfg", "content": "[x]\n"}
    )
    assert resp.status_code == 400


def test_route_restart_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    async def fake_restart(_client: Any) -> dict[str, Any]:
        return {"ok": True}

    monkeypatch.setattr(config_service, "restart_firmware", fake_restart)
    resp = TestClient(_app()).post("/api/config/restart")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


# ── disk-vs-live drift + adopt (C3) ──────────────────────────────────────────
def test_adopt_param_surgically_sets_value() -> None:
    from app.services import config_service

    content = "[tmc2209 stepper_x]\nrun_current: 0.800\nhold_current: 0.5\n"
    out = config_service.adopt_param(content, "tmc2209 stepper_x", "run_current", "1.000")
    assert "run_current: 1.000" in out
    assert "hold_current: 0.5" in out  # the other param is untouched
    # An unknown param leaves the text unchanged.
    assert config_service.adopt_param(content, "nope", "x", "1") == content


async def test_gather_drift_flags_edited_not_restarted() -> None:

    from app.services import config_service

    # On disk run_current was bumped to 1.2; Klipper is still running the loaded 0.8 → drift.
    disk = "[tmc2209 stepper_x]\nrun_current: 1.2\nhold_current: 0.5\n"
    live_config = {"tmc2209 stepper_x": {"run_current": "0.8", "hold_current": "0.5"}}

    class _Client:
        async def query_objects(self, _objects: list[str]) -> dict[str, Any]:
            return {
                "configfile": {
                    "config": live_config,
                    "save_config_pending": True,
                    "warnings": [{"message": "deprecated option"}],
                }
            }

        async def get_file_text(self, _path: str, root: str = "config") -> str:
            return disk

    out = await config_service.gather_drift(_Client(), "printer.cfg")  # type: ignore[arg-type]
    assert out["reachable"] is True and out["save_config_pending"] is True
    assert len(out["warnings"]) == 1
    assert out["drifts"] == [
        {"section": "tmc2209 stepper_x", "key": "run_current", "disk": "1.2", "live": "0.8"}
    ]
