"""Tests for the KlipperScreen service (status probe + save normalization; client is stubbed)."""

from __future__ import annotations

from typing import Any

from app.services import config_service, screen_service


class _Client:
    """Fake MoonrakerClient: canned system_info / file list / conf text, and a save spy."""

    def __init__(
        self,
        *,
        available: list[str] | None = None,
        files: list[dict[str, Any]] | None = None,
        conf: str = "",
    ) -> None:
        self._available = available
        self._files = files if files is not None else []
        self._conf = conf

    async def machine_system_info(self) -> dict[str, Any]:
        return {"available_services": self._available} if self._available is not None else {}

    async def list_files(self, root: str = "config") -> list[dict[str, Any]]:
        return self._files

    async def get_file_text(self, path: str, root: str = "config") -> str:
        return self._conf


async def test_status_reports_present_and_parses_options() -> None:
    client = _Client(
        available=["klipper", "moonraker", "KlipperScreen"],
        files=[{"path": "printer.cfg"}, {"path": "KlipperScreen.conf"}],
        conf="[main]\ntheme: z-bolt\nlanguage = en\n",
    )
    out = await screen_service.status(client)  # type: ignore[arg-type]
    assert out["present"] is True
    assert out["restartable"] is True
    assert out["conf_exists"] is True
    assert out["theme"] == "z-bolt"
    assert out["language"] == "en"


async def test_status_absent_when_no_conf_and_not_listed() -> None:
    client = _Client(available=["klipper", "moonraker"], files=[{"path": "printer.cfg"}])
    out = await screen_service.status(client)  # type: ignore[arg-type]
    assert out["present"] is False
    assert out["conf_exists"] is False


async def test_status_conf_without_allowed_service_is_still_present_not_restartable() -> None:
    # Older Moonraker may not report KlipperScreen in available_services — the editor still works.
    client = _Client(
        available=[], files=[{"path": "KlipperScreen.conf"}], conf="theme: material-dark\n"
    )
    out = await screen_service.status(client)  # type: ignore[arg-type]
    assert out["present"] is True
    assert out["restartable"] is False
    assert out["theme"] == "material-dark"


async def test_save_normalizes_crlf_to_lf(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    async def fake_save(
        client: Any, filename: str, content: str, expected: str | None = None, *, keep_n: int = 20
    ) -> dict[str, Any]:
        captured["filename"] = filename
        captured["content"] = content
        return {"ok": True}

    monkeypatch.setattr(config_service, "save_config_file", fake_save)
    await screen_service.save_conf(_Client(), "a\r\nb\rc\n", "sha")  # type: ignore[arg-type]
    assert captured["filename"] == "KlipperScreen.conf"
    assert captured["content"] == "a\nb\nc\n"  # CRLF and lone CR both become LF
