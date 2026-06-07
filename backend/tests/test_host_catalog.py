"""Locks for the canonical host-computer catalog: entities, config snippet, routes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from app.services import host_search, reference_data

client = TestClient(create_app())


def test_hosts_exist_with_unique_ids() -> None:
    hosts = reference_data.hosts()
    assert len(hosts) >= 150, "expected the canonical host set"
    ids = [h["host_id"] for h in hosts]
    assert len(ids) == len(set(ids)), "host_id must be unique"
    kinds = {h["kind"] for h in hosts}
    assert {"sbc", "x86", "os"} <= kinds


def test_every_host_has_copyable_snippet() -> None:
    for h in reference_data.hosts():
        assert (h.get("configSnippet") or "").strip(), f"{h['host_id']} has no configSnippet"


def test_open_hosts_emit_mcu_host_block_others_note() -> None:
    """Open Linux hosts (sbc/x86) carry the real host-MCU config line; OS images / locked
    hosts get a note and must NOT emit the actual [mcu host] serial config."""
    block = "serial: /tmp/klipper_host_mcu"
    for h in reference_data.hosts():
        snip = h["configSnippet"]
        if h.get("klipperOpen"):
            assert block in snip, f"{h['host_id']} open host missing the host-MCU block"
        if h["kind"] in ("os", "locked"):
            assert block not in snip, f"{h['host_id']} {h['kind']} must not emit the host-MCU block"


def test_route_hosts_list_and_detail() -> None:
    r = client.get("/api/hardware/hosts", params={"limit": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 150 and body["hosts"]
    assert "configSnippet" not in body["hosts"][0]

    sbc = client.get("/api/hardware/hosts", params={"kind": "sbc"})
    assert sbc.status_code == 200 and all(h["kind"] == "sbc" for h in sbc.json()["hosts"])

    one_id = body["hosts"][0]["host_id"]
    one = client.get(f"/api/hardware/hosts/{one_id}")
    assert one.status_code == 200 and one.json()["host_id"] == one_id

    assert client.get("/api/hardware/hosts/does-not-exist").status_code == 404


def test_summary_is_lightweight() -> None:
    summ = host_search.summarize(reference_data.hosts()[0])
    assert "configSnippet" not in summ and "specs" not in summ
