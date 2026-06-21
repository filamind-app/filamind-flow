from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app
from app.services import known_good_pack


class _FakeClient:
    """Stands in for MoonrakerClient: a tiny in-memory config filesystem."""

    def __init__(self, *, state: str = "ready") -> None:
        self.state = state
        self.files = {"printer.cfg": "[printer]\nkinematics: corexy\n", "macros/m.cfg": "# macro\n"}
        self.uploaded: dict[str, str] = {}

    async def list_files(self, root: str = "config") -> list[dict[str, Any]]:
        return [{"path": p, "size": len(t), "modified": 0.0} for p, t in self.files.items()]

    async def get_file_text(self, path: str, root: str = "config") -> str:
        return self.files[path]

    async def query_objects(self, objects: list[str]) -> dict[str, Any]:
        return {"print_stats": {"state": self.state}} if "print_stats" in objects else {}

    async def upload_file(self, path: str, content: str, root: str = "config") -> dict[str, Any]:
        self.uploaded[path] = content
        return {}


def test_validate_pack_id_rejects_traversal() -> None:
    for bad in ["../x", "a/b", "UPPER", "", "x" * 90]:
        with pytest.raises(ValueError):
            known_good_pack.validate_pack_id(bad)
    assert known_good_pack.validate_pack_id("printer-20260101-120000") == "printer-20260101-120000"


async def test_create_list_and_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient()
    monkeypatch.setattr(known_good_pack, "MoonrakerClient", lambda *a, **k: fake)
    meta = await known_good_pack.create_pack(str(tmp_path), "http://x", "Before tuning")
    assert meta["file_count"] == 2
    packs = known_good_pack.list_packs(str(tmp_path))
    assert len(packs) == 1 and packs[0]["id"] == meta["id"]
    assert known_good_pack.pack_files(str(tmp_path), meta["id"]) == ["macros/m.cfg", "printer.cfg"]


async def test_restore_writes_files_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient()
    monkeypatch.setattr(known_good_pack, "MoonrakerClient", lambda *a, **k: fake)
    meta = await known_good_pack.create_pack(str(tmp_path), "http://x", "snap")
    res = await known_good_pack.restore_pack(str(tmp_path), "http://x", meta["id"])
    assert res["ok"] is True and res["code"] == "restored" and res["params"]["count"] == 2
    assert fake.uploaded["printer.cfg"].startswith("[printer]")
    assert fake.uploaded["macros/m.cfg"] == "# macro\n"


async def test_restore_refused_while_busy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient()
    monkeypatch.setattr(known_good_pack, "MoonrakerClient", lambda *a, **k: fake)
    meta = await known_good_pack.create_pack(str(tmp_path), "http://x", "snap")
    fake.state = "printing"
    res = await known_good_pack.restore_pack(str(tmp_path), "http://x", meta["id"])
    assert res["ok"] is False and res["code"] == "busy"
    assert fake.uploaded == {}


async def test_restore_missing_pack(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient()
    monkeypatch.setattr(known_good_pack, "MoonrakerClient", lambda *a, **k: fake)
    res = await known_good_pack.restore_pack(str(tmp_path), "http://x", "nope-00000000-000000")
    assert res["code"] == "not_found"


def test_delete_pack(tmp_path: Path) -> None:
    # nothing to delete yet
    assert known_good_pack.delete_pack(str(tmp_path), "missing-0-0") is False


def test_kgp_routes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient()
    monkeypatch.setattr(known_good_pack, "MoonrakerClient", lambda *a, **k: fake)
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(data_dir=str(tmp_path))
    client = TestClient(app)

    assert client.get("/api/kgp").json()["packs"] == []
    created = client.post("/api/kgp", json={"label": "Working SV08"})
    assert created.status_code == 200
    pid = created.json()["id"]

    listed = client.get("/api/kgp").json()["packs"]
    assert len(listed) == 1 and listed[0]["file_count"] == 2

    detail = client.get(f"/api/kgp/{pid}").json()
    assert "printer.cfg" in detail["files"]

    restored = client.post(f"/api/kgp/{pid}/restore")
    assert restored.status_code == 200 and restored.json()["code"] == "restored"

    assert client.delete(f"/api/kgp/{pid}").status_code == 204
    assert client.get(f"/api/kgp/{pid}").status_code == 404
    assert client.get("/api/kgp/bad..id").status_code == 400
