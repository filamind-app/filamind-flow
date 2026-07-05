"""Tests for the pure Klipper/Moonraker config text edits."""

from __future__ import annotations

from app.services import setup_confedit as ce


def test_upsert_appends_a_new_block() -> None:
    text = "[server]\nhost: 0.0.0.0\n"
    body = ["type: web", "channel: stable", "repo: mainsail-crew/mainsail", "path: ~/mainsail"]
    new, changed = ce.upsert_update_manager(text, "mainsail", body)
    assert changed
    assert "[update_manager mainsail]" in new
    assert "repo: mainsail-crew/mainsail" in new
    assert new.startswith("[server]")  # existing content preserved
    # idempotent: re-applying the identical block changes nothing.
    again, changed2 = ce.upsert_update_manager(new, "mainsail", body)
    assert again == new and changed2 is False


def test_upsert_replaces_an_existing_block() -> None:
    text = "[update_manager mainsail]\ntype: web\nchannel: beta\n\n[server]\nhost: x\n"
    new, changed = ce.upsert_update_manager(text, "mainsail", ["type: web", "channel: stable"])
    assert changed
    assert "channel: stable" in new and "channel: beta" not in new
    assert "[server]" in new  # the following section is untouched


def test_drop_update_manager_removes_block_and_gap() -> None:
    text = "[server]\nhost: x\n\n[update_manager fluidd]\ntype: web\npath: ~/f\n\n[foo]\na: b\n"
    new, changed = ce.drop_update_manager(text, "fluidd")
    assert changed
    assert "update_manager fluidd" not in new
    assert "[server]" in new and "[foo]" in new
    assert "\n\n\n" not in new  # didn't pile up blank lines
    # dropping a missing key is a no-op.
    same, changed2 = ce.drop_update_manager(new, "fluidd")
    assert same == new and changed2 is False


def test_include_add_and_drop() -> None:
    text = "[printer]\nkinematics: corexy\n"
    new, changed = ce.add_include(text, "KAMP_Settings.cfg")
    assert changed and ce.has_include(new, "KAMP_Settings.cfg")
    assert new.startswith("[include KAMP_Settings.cfg]")  # near the top
    # idempotent add.
    again, changed2 = ce.add_include(new, "KAMP_Settings.cfg")
    assert again == new and changed2 is False
    # drop removes it.
    dropped, changed3 = ce.drop_include(new, "KAMP_Settings.cfg")
    assert changed3 and not ce.has_include(dropped, "KAMP_Settings.cfg")
    assert "[printer]" in dropped
