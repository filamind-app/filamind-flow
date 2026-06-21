"""Known-Good Packs - snapshot every printer config file as a restorable bundle.

A pack is a folder ``<data_dir>/known-good-packs/<pack_id>/`` holding a copy of each config file
under ``files/<relpath>`` plus a ``meta.json``; a single ``index.json`` at the root lists packs
(summary only, so it stays tiny). Creating a pack reads the live config files (read-only);
restoring writes them back via Moonraker, gated - refused while the printer is busy. Path traversal
is guarded by a pack-id regex and ``realpath`` containment.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

import httpx

from app.services import config_service, printer_guard
from app.services.moonraker_client import MoonrakerClient

_PACK_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")


def packs_dir(data_dir: str) -> str:
    path = os.path.join(os.path.expanduser(data_dir), "known-good-packs")
    os.makedirs(path, exist_ok=True)
    return path


def _index_path(data_dir: str) -> str:
    return os.path.join(packs_dir(data_dir), "index.json")


def validate_pack_id(pack_id: str) -> str:
    if not _PACK_RE.match(pack_id):
        raise ValueError("invalid pack id")
    return pack_id


def _pack_dir(data_dir: str, pack_id: str) -> str:
    base = packs_dir(data_dir)
    path = os.path.join(base, validate_pack_id(pack_id))
    # realpath containment guard (defence in depth on top of the id regex)
    if os.path.commonpath([os.path.realpath(path), os.path.realpath(base)]) != os.path.realpath(
        base
    ):
        raise ValueError("invalid pack path")
    return path


def read_index(data_dir: str) -> list[dict[str, Any]]:
    try:
        with open(_index_path(data_dir), encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def _write_index(data_dir: str, packs: list[dict[str, Any]]) -> None:
    path = _index_path(data_dir)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(packs, handle, indent=2)
    os.replace(tmp, path)


def _slug(label: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", label.lower())).strip("-") or "pack"


def _make_pack_id(label: str, existing: set[str]) -> str:
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    base = f"{_slug(label)[:40]}-{stamp}"
    pack_id, n = base, 1
    while pack_id in existing:
        n += 1
        pack_id = f"{base}-{n}"
    return pack_id


def _safe_join(root: str, relpath: str) -> str:
    """Join + verify the result stays under ``root`` (guards against ``..`` in config paths)."""
    dest = os.path.normpath(os.path.join(root, relpath))
    if os.path.commonpath(
        [os.path.realpath(os.path.dirname(dest) or root), os.path.realpath(root)]
    ) != os.path.realpath(root):
        raise ValueError("unsafe path")
    return dest


async def create_pack(
    data_dir: str, moonraker_url: str, label: str, timeout: float = 20.0
) -> dict[str, Any]:
    """Snapshot every live config file into a new pack. Read-only on the printer."""
    client = MoonrakerClient(moonraker_url, timeout=timeout)
    files = await config_service.list_config_files(client)
    index = read_index(data_dir)
    pack_id = _make_pack_id(label or "pack", {p.get("id", "") for p in index})
    files_root = os.path.join(_pack_dir(data_dir, pack_id), "files")
    os.makedirs(files_root, exist_ok=True)

    saved = 0
    for entry in files:
        path = str(entry.get("path", ""))
        if not path:
            continue
        try:
            text = await client.get_file_text(path, root="config")
        except httpx.HTTPError:
            continue
        dest = _safe_join(files_root, path)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8") as handle:
            handle.write(text)
        saved += 1

    meta = {"id": pack_id, "label": label or pack_id, "created": time.time(), "file_count": saved}
    with open(os.path.join(_pack_dir(data_dir, pack_id), "meta.json"), "w", encoding="utf-8") as h:
        json.dump(meta, h, indent=2)
    index.insert(0, meta)
    _write_index(data_dir, index)
    return meta


def list_packs(data_dir: str) -> list[dict[str, Any]]:
    return read_index(data_dir)


def pack_files(data_dir: str, pack_id: str) -> list[str]:
    """Relative paths of the files stored in a pack (for the detail view)."""
    files_root = os.path.join(_pack_dir(data_dir, pack_id), "files")
    out: list[str] = []
    for root, _dirs, names in os.walk(files_root):
        for name in names:
            rel = os.path.relpath(os.path.join(root, name), files_root)
            out.append(rel.replace(os.sep, "/"))
    return sorted(out)


async def restore_pack(
    data_dir: str, moonraker_url: str, pack_id: str, timeout: float = 30.0
) -> dict[str, Any]:
    """Write a pack's files back to the printer (gated; refused while busy). Restart to apply."""
    files_root = os.path.join(_pack_dir(data_dir, pack_id), "files")
    if not os.path.isdir(files_root):
        return {"ok": False, "code": "not_found", "params": {}}
    rels = pack_files(data_dir, pack_id)
    if not rels:
        return {"ok": False, "code": "empty", "params": {}}
    client = MoonrakerClient(moonraker_url, timeout=timeout)
    try:
        if await printer_guard.is_busy(client):
            return {"ok": False, "code": "busy", "params": {}}
        for rel in rels:
            with open(_safe_join(files_root, rel), encoding="utf-8") as handle:
                text = handle.read()
            await client.upload_file(rel, text, root="config")
    except httpx.HTTPError as exc:
        return {"ok": False, "code": "moonraker_error", "params": {"error": str(exc)}}
    return {"ok": True, "code": "restored", "params": {"count": len(rels)}}


def delete_pack(data_dir: str, pack_id: str) -> bool:
    """Remove a pack folder + its index entry. Returns True if it existed."""
    import shutil

    pdir = _pack_dir(data_dir, pack_id)
    existed = os.path.isdir(pdir)
    shutil.rmtree(pdir, ignore_errors=True)
    index = [p for p in read_index(data_dir) if p.get("id") != pack_id]
    _write_index(data_dir, index)
    return existed
