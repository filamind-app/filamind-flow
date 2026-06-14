from __future__ import annotations

import pytest

from app.services import host_control_service as hc


async def test_monitor_returns_all_blocks() -> None:
    # Smoke test: works on any OS because every read degrades gracefully (missing /proc, /sys and
    # commands just yield empty/None). The contract the frontend depends on must always be present.
    snap = await hc.monitor("~/printer_data/config/filamind")
    for key in (
        "host",
        "cpu",
        "memory",
        "disk",
        "throttle",
        "processes",
        "network",
        "time",
        "locale",
    ):
        assert key in snap
    assert isinstance(snap["host"]["hostname"], str)
    assert isinstance(snap["disk"], list)
    assert isinstance(snap["processes"], list)
    assert set(snap["memory"]) == {
        "total_kb",
        "available_kb",
        "used_kb",
        "swap_total_kb",
        "swap_used_kb",
    }


def test_memory_parser(monkeypatch: pytest.MonkeyPatch) -> None:
    meminfo = "MemTotal: 1000 kB\nMemAvailable: 250 kB\nSwapTotal: 400 kB\nSwapFree: 100 kB\n"
    monkeypatch.setattr(hc, "_read", lambda path: meminfo)
    mem = hc._memory_block()
    assert mem["total_kb"] == 1000
    assert mem["available_kb"] == 250
    assert mem["used_kb"] == 750  # total - available
    assert mem["swap_used_kb"] == 300  # swap_total - swap_free


async def test_throttle_parses_pi_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    # 0x50000 = bit16 (undervoltage_occurred) + bit18 (throttled_occurred).
    async def fake_run(cmd: list[str], timeout: float = 5.0) -> str:
        return "throttled=0x50000\n"

    monkeypatch.setattr(hc, "_run", fake_run)
    t = await hc._throttle_block()
    assert t["supported"] is True
    assert t["undervoltage"] is True
    assert "undervoltage_occurred" in t["flags"]
    assert "throttled_occurred" in t["flags"]


async def test_throttle_unsupported_when_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run(cmd: list[str], timeout: float = 5.0) -> str:
        return ""  # vcgencmd not installed (most non-Pi boards)

    monkeypatch.setattr(hc, "_run", fake_run)
    t = await hc._throttle_block()
    assert t["supported"] is False
    assert t["flags"] == []


async def test_time_block_reads_timedatectl(monkeypatch: pytest.MonkeyPatch) -> None:
    show = (
        "Timezone=Europe/Berlin\nNTP=yes\nNTPSynchronized=yes\nTimeUSec=Sat 2026-06-14 10:00:00\n"
    )

    async def fake_run(cmd: list[str], timeout: float = 5.0) -> str:
        return show

    monkeypatch.setattr(hc, "_run", fake_run)
    tb = await hc._time_block()
    assert tb["timezone"] == "Europe/Berlin"
    assert tb["ntp_enabled"] is True
    assert tb["ntp_synced"] is True


async def test_run_returns_empty_on_missing_binary() -> None:
    # A read-only command that does not exist must not raise — it yields "".
    assert await hc._run(["definitely-not-a-real-binary-xyz"]) == ""


# ── Services (Phase 2) ─────────────────────────────────────────────────────────


def test_unit_name_validation() -> None:
    assert hc._valid_unit("moonraker")
    assert hc._valid_unit("klipper-mcu.service")
    assert hc._valid_unit("getty@tty1.service")  # instanced template
    assert not hc._valid_unit("")
    assert not hc._valid_unit("../etc/passwd")  # path traversal
    assert not hc._valid_unit("foo; rm -rf /")  # shell metachars / spaces


def test_protected_and_critical_flags() -> None:
    assert hc._is_protected("ssh")
    assert hc._is_protected("filamind-flow.service")
    assert hc._is_protected("systemd-journald")
    assert not hc._is_protected("moonraker")
    # Critical (warn) but not protected (still manageable).
    assert hc._is_critical("moonraker")
    assert hc._is_critical("systemd-tmpfiles-clean")  # systemd-* prefix
    assert not hc._is_critical("myrandomapp")


def _svc_runner(units: str, files: str):
    async def fake(cmd: list[str], timeout: float = 10.0) -> tuple[int, str]:
        if "list-units" in cmd:
            return 0, units
        if "list-unit-files" in cmd:
            return 0, files
        return 0, ""

    return fake


async def test_list_units_merges_state(monkeypatch: pytest.MonkeyPatch) -> None:
    units = (
        "moonraker.service loaded active running API host\n"
        "ssh.service loaded active running OpenBSD Secure Shell server\n"
        "myapp.service loaded active running My app\n"
    )
    files = (
        "moonraker.service enabled enabled\n"
        "ssh.service enabled enabled\n"
        "myapp.service enabled enabled\n"
        "dormant.service disabled disabled\n"  # installed but not loaded
    )
    monkeypatch.setattr(hc, "_run_rc", _svc_runner(units, files))
    svcs = {s["name"]: s for s in await hc.list_units()}
    assert svcs["moonraker"]["active"] is True
    assert svcs["moonraker"]["enabled"] == "enabled"
    assert svcs["moonraker"]["critical"] is True and svcs["moonraker"]["protected"] is False
    assert svcs["ssh"]["protected"] is True
    assert svcs["myapp"]["critical"] is False
    # A unit present only in list-unit-files shows up as inactive.
    assert svcs["dormant"]["active"] is False and svcs["dormant"]["enabled"] == "disabled"


async def test_manage_unit_refuses_destructive_on_protected() -> None:
    res = await hc.manage_unit("ssh", "stop")
    assert res["ok"] is False and res["refused"] is True
    # unmask is not destructive, so it is allowed even on a protected unit (would shell out).


async def test_manage_unit_rejects_bad_action() -> None:
    with pytest.raises(ValueError):
        await hc.manage_unit("myapp", "obliterate")


async def test_manage_unit_runs_allowed_action(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake(cmd: list[str], timeout: float = 10.0) -> tuple[int, str]:
        assert cmd == ["sudo", "-n", "systemctl", "restart", "myapp.service"]
        return 0, ""

    monkeypatch.setattr(hc, "_run_rc", fake)
    res = await hc.manage_unit("myapp", "restart")
    assert res["ok"] is True and res["refused"] is False


async def test_delete_unit_requires_matching_confirm() -> None:
    res = await hc.delete_unit("myapp", "wrong")
    assert res["ok"] is False and res["refused"] is True


async def test_delete_unit_refuses_protected() -> None:
    res = await hc.delete_unit("ssh", "ssh")
    assert res["ok"] is False and res["refused"] is True


async def test_delete_unit_refuses_vendor_path(monkeypatch: pytest.MonkeyPatch) -> None:
    # A unit whose fragment lives under /lib/systemd (vendor) must not be deletable.
    async def fake(cmd: list[str], timeout: float = 10.0) -> tuple[int, str]:
        if "show" in cmd:
            return 0, "FragmentPath=/lib/systemd/system/myapp.service\nDescription=x\n"
        return 0, ""

    monkeypatch.setattr(hc, "_run_rc", fake)
    res = await hc.delete_unit("myapp", "myapp")
    assert res["ok"] is False and res["refused"] is True


async def test_delete_unit_removes_user_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    async def fake(cmd: list[str], timeout: float = 10.0) -> tuple[int, str]:
        calls.append(cmd)
        if "show" in cmd:
            return 0, "FragmentPath=/etc/systemd/system/myapp.service\nDescription=x\n"
        return 0, ""

    monkeypatch.setattr(hc, "_run_rc", fake)
    res = await hc.delete_unit("myapp", "myapp")
    assert res["ok"] is True and res["refused"] is False
    assert any(c[:3] == ["sudo", "-n", "rm"] for c in calls)
    assert any("daemon-reload" in c for c in calls)


# ── Disk cleanup (Phase 3) ─────────────────────────────────────────────────────


def test_parse_size_human_units() -> None:
    assert hc._parse_size("120.0M in the file system.") == int(120.0 * 1024**2)
    assert hc._parse_size("1.5G") == int(1.5 * 1024**3)
    assert hc._parse_size("512K") == 512 * 1024
    assert hc._parse_size("nonsense") == 0


def test_rotated_logs_keeps_live_log(tmp_path) -> None:
    logs = tmp_path / "printer_data" / "logs"
    logs.mkdir(parents=True)
    (logs / "klippy.log").write_text("live")  # kept
    (logs / "klippy.log.2026-06-01").write_text("rotated")  # dropped
    (logs / "moonraker.log.1").write_text("rotated")  # dropped
    (logs / "crowsnest.log.gz").write_bytes(b"gz")  # dropped
    data_dir = str(tmp_path / "printer_data" / "config" / "filamind")
    found = {hc.os.path.basename(p) for p in hc._rotated_logs(data_dir)}
    assert found == {"klippy.log.2026-06-01", "moonraker.log.1", "crowsnest.log.gz"}


def test_dir_size_counts_regular_files(tmp_path) -> None:
    (tmp_path / "a").write_bytes(b"x" * 10)
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b").write_bytes(b"y" * 5)
    total, count = hc._dir_size(str(tmp_path))
    assert total == 15 and count == 2


def test_rm_contents_clears_dir_but_keeps_it(tmp_path) -> None:
    (tmp_path / "f1").write_bytes(b"x" * 4)
    (tmp_path / "d1").mkdir()
    (tmp_path / "d1" / "f2").write_bytes(b"y" * 6)
    freed, removed = hc._rm_contents(str(tmp_path))
    assert freed == 10 and removed == 2
    assert tmp_path.is_dir() and not list(tmp_path.iterdir())


async def test_cleanup_scan_returns_all_targets() -> None:
    targets = await hc.cleanup_scan("~/printer_data/config/filamind")
    ids = {t["id"] for t in targets}
    assert ids == set(hc.CLEANUP_TARGETS)
    for t in targets:
        assert set(t) == {"id", "bytes", "count", "available"}
        assert isinstance(t["bytes"], int)


async def test_cleanup_run_ignores_unknown_ids() -> None:
    out = await hc.cleanup_run(["not-a-target"], "~/printer_data/config/filamind")
    assert out["results"] == [] and out["freed_bytes"] == 0


async def test_scan_journal_parses_disk_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake(cmd: list[str], timeout: float = 10.0) -> tuple[int, str]:
        return 0, "Archived and active journals take up 120.0M in the file system.\n"

    monkeypatch.setattr(hc, "_run_rc", fake)
    b, available = await hc._scan_journal_bytes()
    assert available is True and b == int(120.0 * 1024**2)


# ── System settings (Phase 4) ──────────────────────────────────────────────────


async def test_set_hostname_validates() -> None:
    with pytest.raises(ValueError):
        await hc.set_hostname("bad host name")  # spaces
    with pytest.raises(ValueError):
        await hc.set_hostname("-leadinghyphen")
    with pytest.raises(ValueError):
        await hc.set_hostname("has/slash")


async def test_set_timezone_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        await hc.set_timezone("../etc/passwd")


async def test_set_time_rejects_bad_format() -> None:
    with pytest.raises(ValueError):
        await hc.set_time("not-a-time")


async def test_power_rejects_bad_action() -> None:
    with pytest.raises(ValueError):
        await hc.power("explode", "http://x")


async def test_set_hostname_runs_sudo(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    async def fake(cmd: list[str], timeout: float = 10.0) -> tuple[int, str]:
        calls.append(cmd)
        return 0, ""

    monkeypatch.setattr(hc, "_run_rc", fake)
    res = await hc.set_hostname("printer1")
    assert res["ok"] is True
    assert calls[0] == ["sudo", "-n", "hostnamectl", "set-hostname", "printer1"]


async def test_set_timezone_checks_membership(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake(cmd: list[str], timeout: float = 10.0) -> tuple[int, str]:
        if "list-timezones" in cmd:
            return 0, "Europe/Berlin\nUTC\n"
        return 0, ""

    monkeypatch.setattr(hc, "_run_rc", fake)
    res = await hc.set_timezone("UTC")
    assert res["ok"] is True
    with pytest.raises(ValueError):
        await hc.set_timezone("Mars/Phobos")  # passes regex, not in the list


async def test_power_refuses_while_printing(monkeypatch: pytest.MonkeyPatch) -> None:
    async def busy(client: object, **_kw: object) -> bool:
        return True

    monkeypatch.setattr(hc.printer_guard, "is_busy", busy)
    res = await hc.power("reboot", "http://x")
    assert res["ok"] is False and res["refused"] is True


async def test_power_runs_when_idle(monkeypatch: pytest.MonkeyPatch) -> None:
    async def idle(client: object, **_kw: object) -> bool:
        return False

    calls: list[list[str]] = []

    async def fake(cmd: list[str], timeout: float = 10.0) -> tuple[int, str]:
        calls.append(cmd)
        return 0, ""

    monkeypatch.setattr(hc.printer_guard, "is_busy", idle)
    monkeypatch.setattr(hc, "_run_rc", fake)
    res = await hc.power("reboot", "http://x")
    assert res["ok"] is True
    assert ["sudo", "-n", "systemctl", "reboot"] in calls


# ── needs_setup detection (the sudo-not-granted UX bug) ─────────────────────────


def test_result_flags_needs_setup_on_sudo_auth_failure() -> None:
    assert hc._result(1, "sudo: a password is required")["needs_setup"] is True
    assert hc._result(0, "")["needs_setup"] is False
    # A genuine non-sudo failure is ok:false but NOT needs_setup.
    assert hc._result(1, "Failed to set hostname: boom")["needs_setup"] is False


async def test_clean_apt_reports_needs_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hc, "_apt_debs", lambda: ["/var/cache/apt/archives/x.deb"])
    monkeypatch.setattr(hc, "_sum_sizes", lambda paths: 100)

    async def fake(cmd: list[str], timeout: float = 10.0) -> tuple[int, str]:
        return 1, "sudo: a password is required"

    monkeypatch.setattr(hc, "_run_rc", fake)
    r = await hc._clean_target("apt", "~/printer_data/config/filamind")
    assert r["ok"] is False and r["needs_setup"] is True


# ── Network / IPv4 (Phase: network) ────────────────────────────────────────────


def test_validate_static_accepts_a_good_config() -> None:
    addr, gw, dns = hc._validate_static("192.168.0.50", 24, "192.168.0.1", "1.1.1.1, 8.8.8.8")
    assert addr == "192.168.0.50/24"
    assert gw == "192.168.0.1"
    assert dns == "1.1.1.1,8.8.8.8"


def test_validate_static_rejects_bad_input() -> None:
    with pytest.raises(ValueError):
        hc._validate_static("999.1.1.1", 24, "192.168.0.1", "")  # bad address
    with pytest.raises(ValueError):
        hc._validate_static("192.168.0.50", 33, "192.168.0.1", "")  # bad prefix
    with pytest.raises(ValueError):
        hc._validate_static("192.168.0.50", 24, "10.0.0.1", "")  # gateway off-subnet (lockout)
    with pytest.raises(ValueError):
        hc._validate_static("192.168.0.50", 24, "192.168.0.50", "")  # gateway == host
    with pytest.raises(ValueError):
        hc._validate_static("192.168.0.50", 24, "192.168.0.1", "1.1.1.1, notanip")  # bad DNS


def test_validate_static_rejects_network_and_broadcast() -> None:
    # Using the subnet's network or broadcast address as the host IP / gateway is a guaranteed
    # lockout — the validator must reject both (the review's HIGH finding).
    with pytest.raises(ValueError):
        hc._validate_static("192.168.0.0", 24, "192.168.0.1", "")  # host = network address
    with pytest.raises(ValueError):
        hc._validate_static("192.168.0.255", 24, "192.168.0.1", "")  # host = broadcast address
    with pytest.raises(ValueError):
        hc._validate_static("192.168.0.50", 24, "192.168.0.0", "")  # gateway = network address
    with pytest.raises(ValueError):
        hc._validate_static("192.168.0.50", 24, "192.168.0.255", "")  # gateway = broadcast address


def test_needs_setup_matches_localized_and_variant_sudo_errors() -> None:
    assert hc._needs_setup("sudo: a password is required")
    assert hc._needs_setup("Sorry, user biqu is not allowed to execute '/usr/bin/nmcli'")
    assert hc._needs_setup("sudo: sorry, you must have a tty to run sudo")
    assert not hc._needs_setup("Error: nmcli connection not found")


async def test_set_network_rejects_bad_mode() -> None:
    with pytest.raises(ValueError):
        await hc.set_network("bridge", "", None, "", "", "http://x")


async def test_set_network_unavailable_without_nmcli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hc, "_has_cmd", lambda name: False)
    res = await hc.set_network("auto", "", None, "", "", "http://x")
    assert res["refused"] is True


def _patch_network(
    monkeypatch: pytest.MonkeyPatch, calls: list[list[str]], conn: str = "MyCon"
) -> None:
    monkeypatch.setattr(hc, "_has_cmd", lambda name: True)

    async def fake_info() -> dict:
        return {"available": True, "configurable": True, "connection": conn, "device": "wlan0"}

    async def idle(client: object, **_kw: object) -> bool:
        return False

    async def fake_run(cmd: list[str], timeout: float = 10.0) -> tuple[int, str]:
        calls.append(cmd)
        return 0, ""

    monkeypatch.setattr(hc, "network_info", fake_info)
    monkeypatch.setattr(hc.printer_guard, "is_busy", idle)
    monkeypatch.setattr(hc, "_run_rc", fake_run)


async def test_set_network_dhcp_clears_static(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    _patch_network(monkeypatch, calls)
    res = await hc.set_network("auto", "", None, "", "", "http://x")
    assert res["ok"] is True
    modify = next(c for c in calls if "modify" in c)
    assert "auto" in modify and modify[modify.index("ipv4.addresses") + 1] == ""
    assert any(c[:4] == ["sudo", "-n", "nmcli", "connection"] and "up" in c for c in calls)


async def test_set_network_static_passes_validated_args(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    _patch_network(monkeypatch, calls)
    res = await hc.set_network("manual", "192.168.0.50", 24, "192.168.0.1", "1.1.1.1", "http://x")
    assert res["ok"] is True
    modify = next(c for c in calls if "modify" in c)
    assert modify[modify.index("ipv4.addresses") + 1] == "192.168.0.50/24"
    assert modify[modify.index("ipv4.gateway") + 1] == "192.168.0.1"
    assert modify[modify.index("ipv4.dns") + 1] == "1.1.1.1"
    assert "manual" in modify


async def test_set_network_refuses_while_printing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hc, "_has_cmd", lambda name: True)

    async def fake_info() -> dict:
        return {"available": True, "configurable": True, "connection": "MyCon", "device": "wlan0"}

    async def busy(client: object, **_kw: object) -> bool:
        return True

    monkeypatch.setattr(hc, "network_info", fake_info)
    monkeypatch.setattr(hc.printer_guard, "is_busy", busy)
    res = await hc.set_network("auto", "", None, "", "", "http://x")
    assert res["ok"] is False and res["refused"] is True


async def test_network_info_unavailable_without_nmcli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hc, "_has_cmd", lambda name: False)
    info = await hc.network_info()
    assert info["available"] is False and info["configurable"] is False
