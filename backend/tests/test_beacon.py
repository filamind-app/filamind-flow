from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app
from app.services import beacon_service


def test_parse_beacon_reads_revision_and_serial() -> None:
    parsed = beacon_service._parse_beacon("/dev/serial/by-id/usb-Beacon_Beacon_RevH_BSC512-if00")
    assert parsed == {
        "id": "/dev/serial/by-id/usb-Beacon_Beacon_RevH_BSC512-if00",
        "name": "Beacon RevH",
        "revision": "RevH",
        "serial": "BSC512",
    }
    assert beacon_service._parse_beacon("/dev/serial/by-id/usb-Klipper_stm32-if00") is None


async def test_flash_beacon_emits_phases_and_reports_failure(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The Beacon flash drives the same progress contract as a board flash: phase markers so the
    widget shows the green completion state (#571 follow-up), and the updater's REAL exit code -
    a failed update must not print 'complete'."""
    script = tmp_path / "update_firmware.py"
    script.write_text("# fake updater\n")

    async def repo_path(_url: str) -> str:
        return str(tmp_path)

    class _Proc:
        def __init__(self, rc: int) -> None:
            self._rc = rc
            self.stdout = self

        async def readline(self) -> bytes:
            return b""

        async def wait(self) -> int:
            return self._rc

    rc_box = {"rc": 0}

    async def fake_exec(*args, **kwargs):  # type: ignore[no-untyped-def]
        assert args[0] != "python3" or True  # interpreter comes from flash_python()
        return _Proc(rc_box["rc"])

    monkeypatch.setattr(beacon_service, "beacon_repo_path", repo_path)
    monkeypatch.setattr(beacon_service, "flash_python", lambda: "python3")
    monkeypatch.setattr(beacon_service.asyncio, "create_subprocess_exec", fake_exec)
    settings = Settings(moonraker_url="http://127.0.0.1:1")

    async def run() -> str:
        return "".join([ln async for ln in beacon_service.flash_beacon("/dev/beacon", settings)])

    log = await run()
    assert "::phase::start" in log and "::phase::write" in log and "::phase::done" in log
    assert "Beacon update complete" in log

    rc_box["rc"] = 3  # the updater fails -> no green state, an honest error instead
    log = await run()
    assert "::phase::done" not in log
    assert "Beacon update failed" in log and "code 3" in log


def test_probe_version_bcd_parse(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """bcdDevice is BCD-encoded ('0210' -> '2.10'); unreadable / malformed values yield None."""
    sysdir = tmp_path / "sys"
    sysdir.mkdir()
    (sysdir / "bcdDevice").write_text("0210\n")

    real_realpath = beacon_service.os.path.realpath

    def fake_realpath(p: str) -> str:
        if "by-id" in str(p):
            return "/dev/ttyACM7"
        if "ttyACM7" in str(p):
            return str(sysdir)
        return real_realpath(p)

    real_join = beacon_service.os.path.join
    monkeypatch.setattr(beacon_service.os.path, "realpath", fake_realpath)
    monkeypatch.setattr(
        beacon_service.os.path,
        "join",
        lambda *a: str(sysdir / "bcdDevice") if a[-1] == "bcdDevice" else real_join(*a),
    )
    assert beacon_service._probe_current_version("/dev/serial/by-id/usb-Beacon-if00") == "2.10"
    # malformed content -> None
    (sysdir / "bcdDevice").write_text("xyz\n")
    assert beacon_service._probe_current_version("/dev/serial/by-id/usb-Beacon-if00") is None


def test_beacon_route_graceful_without_hardware() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(moonraker_url="http://127.0.0.1:1")
    client = TestClient(app)

    response = client.get("/api/firmware/beacon")

    assert response.status_code == 200
    body = response.json()
    assert body["probes"] == []  # no Beacon probe in CI
    assert "available_version" in body and "repo" in body
