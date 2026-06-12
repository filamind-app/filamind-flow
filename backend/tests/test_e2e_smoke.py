"""End-to-end smoke: the real app against a real HTTP Moonraker stub.

Boots the stub (in-process uvicorn on an ephemeral port), points the app at it, and
walks the critical reads PLUS the full gated write path — apply-section merge, the
backup it takes, the stale-write 412 and the busy 409. This is the test that fails
if the app can no longer talk to a Moonraker-shaped boundary end to end.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app
from tests.stub_moonraker import PRINTER_CFG, StubServer

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module")
def stub() -> Iterator[StubServer]:
    server = StubServer()
    server.start()
    yield server
    server.stop()


@pytest.fixture()
def client(stub: StubServer, tmp_path: Path) -> Iterator[TestClient]:
    # Fresh host state per test: the stub is module-scoped, its files are not.
    stub.state.files = {"printer.cfg": PRINTER_CFG}
    stub.state.print_state = "standby"
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        moonraker_url=stub.url, data_dir=str(tmp_path)
    )
    with TestClient(app) as test_client:
        yield test_client


def test_core_reads_come_up(client: TestClient) -> None:
    assert client.get("/api/health").status_code == 200

    guard = client.get("/api/guard/status").json()
    assert guard["reachable"] is True
    assert guard["locked"] is False
    assert guard["print_state"] == "standby"

    overview = client.get("/api/overview")
    assert overview.status_code == 200

    scan = client.get("/api/doctor/scan")
    assert scan.status_code == 200
    assert scan.json().get("grade") in {"A", "B", "C", "D", "F"}

    topo = client.get("/api/topology")
    assert topo.status_code == 200
    names = [m["name"] for m in topo.json()["mcus"]]
    assert "mcu" in names

    view = client.get("/api/config/file", params={"filename": "printer.cfg"})
    assert view.status_code == 200
    assert view.json()["sha256"]


def test_gated_write_path_end_to_end(client: TestClient, stub: StubServer) -> None:
    view = client.get("/api/config/file", params={"filename": "printer.cfg"}).json()
    sha = view["sha256"]

    block = "[input_shaper]\nshaper_type_x = mzv\nshaper_freq_x = 57.0\n"
    applied = client.post(
        "/api/config/apply-section",
        json={"filename": "printer.cfg", "block": block, "expected_sha256": sha},
    )
    assert applied.status_code == 200
    body = applied.json()
    assert body["changes"], "the merge must report what it wrote"

    # The write really landed on the (stub) host, and a backup was taken first.
    assert "[input_shaper]" in stub.state.files["printer.cfg"]
    assert any(path.startswith("filamind-backups/") for path in stub.state.files)

    # Stale precondition → 412 (the block differs, so the write path runs and checks).
    stale = client.post(
        "/api/config/apply-section",
        json={
            "filename": "printer.cfg",
            "block": "[input_shaper]\nshaper_freq_x = 61.0\n",
            "expected_sha256": "0" * 64,
        },
    )
    assert stale.status_code == 412

    # Re-applying the same block is an idempotent no-op (no new changes).
    again = client.post(
        "/api/config/apply-section", json={"filename": "printer.cfg", "block": block}
    )
    assert again.status_code == 200
    assert again.json()["changes"] == []


def test_write_refused_while_printing(client: TestClient, stub: StubServer) -> None:
    stub.state.print_state = "printing"
    try:
        refused = client.post(
            "/api/config/apply-section",
            json={"filename": "printer.cfg", "block": "[input_shaper]\nshaper_type_x = mzv\n"},
        )
        assert refused.status_code == 409
        guard = client.get("/api/guard/status").json()
        assert guard["print_state"] == "printing"
    finally:
        stub.state.print_state = "standby"
