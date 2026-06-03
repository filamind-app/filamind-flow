from __future__ import annotations

from pathlib import Path

import pytest

from app.services import shaper_archive


def _csv(directory: Path, name: str) -> Path:
    path = directory / name
    path.write_text("#time,accel_x,accel_y,accel_z\n0,0,0,9810\n")
    return path


def test_save_config_run_round_trips(tmp_path: Path) -> None:
    run = shaper_archive.save_run(
        str(tmp_path), kind="config", axis="x", config_text="[input_shaper]\nshaper_type_x: mzv\n"
    )
    assert run["kind"] == "config"
    assert "input_shaper.cfg" in run["files"]

    fetched = shaper_archive.get_run(str(tmp_path), run["id"])
    assert fetched is not None
    assert "shaper_type_x: mzv" in fetched["config_text"]
    listed = shaper_archive.read_index(str(tmp_path))
    assert [r["id"] for r in listed] == [run["id"]]


def test_save_run_copies_csv_and_serves_it(tmp_path: Path) -> None:
    src = _csv(tmp_path, "raw_data_x_filamind_x.csv")
    run = shaper_archive.save_run(
        str(tmp_path), kind="shaper", axis="x", csv_sources=[str(src)], summary={"freq": 57.0}
    )
    assert run["files"] == ["raw_data_x_filamind_x.csv"]
    assert run["size"] > 0
    path = shaper_archive.run_file_path(str(tmp_path), run["id"], "raw_data_x_filamind_x.csv")
    assert path is not None and Path(path).is_file()


def test_save_config_run_attaches_to_existing_run(tmp_path: Path) -> None:
    src = _csv(tmp_path, "raw_data_y_filamind_y.csv")
    run = shaper_archive.save_run(str(tmp_path), kind="shaper", axis="y", csv_sources=[str(src)])
    attached = shaper_archive.save_config_run(
        str(tmp_path), config_text="[input_shaper]\n", run_id=run["id"]
    )
    assert attached is not None
    assert attached["id"] == run["id"]  # same run, not a new one
    assert "input_shaper.cfg" in attached["files"]
    assert len(shaper_archive.read_index(str(tmp_path))) == 1


def test_prune_keeps_keep_n_per_kind(tmp_path: Path) -> None:
    for _ in range(22):
        shaper_archive.save_run(str(tmp_path), kind="shaper", axis="x", config_text="x", keep_n=20)
    shaper_archive.save_run(str(tmp_path), kind="noise", config_text="n", keep_n=20)
    index = shaper_archive.read_index(str(tmp_path))
    by_kind = [r["kind"] for r in index]
    assert by_kind.count("shaper") == 20  # capped per kind
    assert by_kind.count("noise") == 1  # a different kind is untouched


def test_delete_run(tmp_path: Path) -> None:
    run = shaper_archive.save_run(str(tmp_path), kind="config", config_text="x")
    assert shaper_archive.delete_run(str(tmp_path), run["id"]) is True
    assert shaper_archive.read_index(str(tmp_path)) == []
    assert shaper_archive.delete_run(str(tmp_path), run["id"]) is False  # already gone


def test_corrupt_index_reads_as_empty(tmp_path: Path) -> None:
    Path(shaper_archive.archive_dir(str(tmp_path)), "index.json").write_text("{ not json")
    assert shaper_archive.read_index(str(tmp_path)) == []


@pytest.mark.parametrize("bad", ["..", "../evil", "a/b", "foo\\bar"])
def test_path_traversal_is_rejected(tmp_path: Path, bad: str) -> None:
    with pytest.raises(shaper_archive.ArchiveError):
        shaper_archive.validate_run_id(bad)
    with pytest.raises(shaper_archive.ArchiveError):
        shaper_archive.get_run(str(tmp_path), bad)


def test_run_file_path_rejects_escaping_filename(tmp_path: Path) -> None:
    run = shaper_archive.save_run(str(tmp_path), kind="config", config_text="x")
    with pytest.raises(shaper_archive.ArchiveError):
        shaper_archive.run_file_path(str(tmp_path), run["id"], "../../etc/passwd")
    # A non-existent (but well-formed) name resolves to None, not a raise.
    assert shaper_archive.run_file_path(str(tmp_path), run["id"], "nope.csv") is None
