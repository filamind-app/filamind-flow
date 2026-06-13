"""Tests for the KlipperScreen theme builder (pure rendering + name guard + conf theme set)."""

from __future__ import annotations

import json
import pathlib

import pytest

from app.services import screen_theme_service as ts


def test_render_style_css_uses_palette_and_rejects_bad_hex() -> None:
    css = ts.render_style_css(
        "My Theme", {"bg": "#102030", "color1": "#ABCDEF", "lines": "not-a-color"}, radius=12
    )
    assert "@define-color bg #102030;" in css
    assert "@define-color color1 #abcdef;" in css  # normalized to lowercase
    assert "@define-color lines #9a9a9a;" in css  # invalid hex → default kept
    assert "border-radius: 12px;" in css
    assert 'theme "My Theme"' in css


def test_render_style_conf_is_valid_json_with_graph_colors() -> None:
    conf = json.loads(ts.render_style_conf({"color1": "#111111"}))
    assert conf["graph_colors"]["extruder"] == ["#111111"]
    assert "bed" in conf["graph_colors"]


def test_generate_writes_folder_and_marker(tmp_path: pathlib.Path) -> None:
    out = ts.generate_theme(str(tmp_path), "Mocha Night", {"bg": "#0a0a0a"})
    d = pathlib.Path(out["path"])
    assert (d / "style.css").exists()
    assert (d / "style.conf").exists()
    assert (d / ts.MARKER).exists()
    assert {"name": "Mocha Night", "generated": True} in ts.list_themes(str(tmp_path))


def test_generate_refuses_to_overwrite_stock_theme(tmp_path: pathlib.Path) -> None:
    stock = tmp_path / "styles" / "z-bolt"
    stock.mkdir(parents=True)
    (stock / "style.css").write_text("/* stock */", encoding="utf-8")
    with pytest.raises(ValueError):
        ts.generate_theme(str(tmp_path), "z-bolt", {})


def test_delete_refuses_stock_and_removes_generated(tmp_path: pathlib.Path) -> None:
    ts.generate_theme(str(tmp_path), "mine", {})
    (tmp_path / "styles" / "stock").mkdir(parents=True)
    with pytest.raises(ValueError):
        ts.delete_theme(str(tmp_path), "stock")
    ts.delete_theme(str(tmp_path), "mine")
    assert not (tmp_path / "styles" / "mine").exists()


@pytest.mark.parametrize("bad", ["../evil", "a/b", "", "x" * 41])
def test_invalid_name_rejected(tmp_path: pathlib.Path, bad: str) -> None:
    with pytest.raises(ValueError):
        ts.generate_theme(str(tmp_path), bad, {})


def test_set_main_theme_adds_replaces_and_preserves_auto_block() -> None:
    # adds the key when [main] exists without one
    out = ts.set_main_theme("[main]\nlanguage = en\n", "mine")
    assert "theme = mine" in out and "language = en" in out
    # replaces an existing value (either separator)
    out2 = ts.set_main_theme("[main]\ntheme: old\nlanguage = en\n", "new")
    assert "theme = new" in out2 and "old" not in out2
    # leaves KlipperScreen's auto-generated #~# block untouched
    raw = (
        "[main]\nlanguage = en\n#~# --- Do not edit below --- #~#\n#~# [main]\n#~# theme = saved\n"
    )
    out3 = ts.set_main_theme(raw, "new")
    assert "theme = new" in out3
    assert "#~# theme = saved" in out3
    # creates [main] when there is none
    out4 = ts.set_main_theme("language = en\n", "new")
    assert out4.startswith("[main]\ntheme = new")
