"""Kconfig config editor — reads Klipper's firmware menu and writes ``.config`` files.

Klipper drives ``make menuconfig`` with the same ``kconfiglib`` that the kernel
uses, shipped under ``<klipper>/lib/kconfiglib``. We load that bundled copy
(falling back to a system install), parse ``src/Kconfig`` into a JSON-friendly
menu tree the browser can render as a form, apply the user's choices, and write
the resulting ``.config`` — exactly what a board's firmware build consumes.

All Kconfig work is funnelled through one lock and an ``asyncio.to_thread`` hop:
``kconfiglib`` relies on process-wide CWD + ``srctree`` env, which is not safe to
run concurrently.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import threading
from functools import lru_cache
from typing import Any

_kconfiglib: Any = None

# kconfiglib mutates process-wide CWD + srctree env, so the actual parse/write
# (which runs in a worker thread) must be serialised across all requests.
_KCONFIG_LOCK = threading.Lock()


def _load_kconfiglib(klipper_dir: str) -> Any:
    """Imports kconfiglib, preferring Klipper's bundled copy over a system one."""
    global _kconfiglib
    if _kconfiglib is not None:
        return _kconfiglib
    bundled = os.path.join(klipper_dir, "lib", "kconfiglib")
    if os.path.isdir(bundled) and bundled not in sys.path:
        sys.path.insert(0, bundled)
    import kconfiglib  # type: ignore[import-untyped]

    _kconfiglib = kconfiglib
    return kconfiglib


class KconfigError(RuntimeError):
    """Raised when the Kconfig system can't be loaded (missing Klipper/kconfiglib)."""


class KconfigService:
    """Loads Klipper's Kconfig and serialises it into an editable menu tree."""

    def __init__(self, klipper_dir: str) -> None:
        self.klipper_dir = os.path.abspath(os.path.expanduser(klipper_dir))
        self.kconfig_file = os.path.join(self.klipper_dir, "src", "Kconfig")

    @property
    def available(self) -> bool:
        """True if Klipper's Kconfig is present on disk."""
        return os.path.isfile(self.kconfig_file)

    async def menu_tree(
        self,
        config_file: str | None = None,
        values: list[tuple[str, str]] | None = None,
        show_optional: bool = False,
    ) -> list[dict[str, Any]]:
        """Returns the menu tree, optionally pre-loaded with a profile and edits."""
        return await asyncio.to_thread(self._build_tree, config_file, values or [], show_optional)

    async def write_config(
        self, output_path: str, config_file: str | None, values: list[tuple[str, str]]
    ) -> None:
        """Applies ``values`` onto a base config and writes a ``.config`` file."""
        await asyncio.to_thread(self._write_config, output_path, config_file, values)

    # -- internals (run in a worker thread, serialised by the lock) -------------

    def _run_kalico_extras(self) -> None:
        """Generate ``src/extras/Kconfig`` for Kalico forks (normally a make step)."""
        script = os.path.join(self.klipper_dir, "scripts", "find-firmware-extras.sh")
        extras = os.path.join(self.klipper_dir, "src", "extras", "Kconfig")
        if not os.path.isfile(script) or os.path.isfile(extras):
            return
        try:
            subprocess.run(
                ["bash", script],
                cwd=self.klipper_dir,
                timeout=10,
                check=True,
                capture_output=True,
            )
        except (OSError, subprocess.SubprocessError):
            os.makedirs(os.path.dirname(extras), exist_ok=True)
            with open(extras, "w"):
                pass

    def _load(self, config_file: str | None) -> Any:
        if not self.available:
            raise KconfigError(
                f"Klipper Kconfig not found at {self.kconfig_file}. "
                "Check that Klipper is installed and klipper_dir is correct."
            )
        try:
            kl = _load_kconfiglib(self.klipper_dir)
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise KconfigError("kconfiglib is not available") from exc

        # kconfiglib reads the lowercase `srctree` to resolve relative `source`
        # directives; SRCTREE is set too for older/forked variants.
        os.environ["srctree"] = self.klipper_dir  # noqa: SIM112
        os.environ["SRCTREE"] = self.klipper_dir
        self._run_kalico_extras()

        old_cwd = os.getcwd()
        os.chdir(self.klipper_dir)
        try:
            kconf = kl.Kconfig(self.kconfig_file, warn=False)
        finally:
            os.chdir(old_cwd)

        if config_file:
            expanded = os.path.expanduser(config_file)
            if os.path.isfile(expanded):
                kconf.load_config(expanded)
        return kconf

    def _apply_values(self, kconf: Any, values: list[tuple[str, str]]) -> None:
        """Applies edits in several passes so cascading ``select`` deps settle."""
        for _ in range(10):
            for name, value in values:
                sym = kconf.syms.get(name)
                if sym is None or sym.visibility == 0:
                    continue
                if sym.choice and value in kconf.syms:
                    kconf.syms[value].set_value(2)  # 2 == 'y'
                else:
                    sym.set_value(str(value))

    def _build_tree(
        self, config_file: str | None, values: list[tuple[str, str]], show_optional: bool
    ) -> list[dict[str, Any]]:
        with _KCONFIG_LOCK:
            kconf = self._load(config_file)
            self._apply_values(kconf, values)
            return self._serialize_children(kconf.top_node, show_optional)

    def _serialize_children(self, node: Any, show_optional: bool) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        child = node.list
        while child:
            entry = self._serialize_node(child, show_optional)
            if entry is not None:
                if child.list and entry["type"] in ("menu", "bool", "tristate"):
                    entry["children"] = self._serialize_children(child, show_optional)
                items.append(entry)
            child = child.next
        return items

    def _serialize_node(self, node: Any, show_optional: bool) -> dict[str, Any] | None:
        kl = _kconfiglib
        if not node.prompt:
            return None
        prompt_text, prompt_cond = node.prompt
        item = node.item

        # Plain menus / comments (not symbols).
        if not isinstance(item, (kl.Symbol, kl.Choice)):
            visible = show_optional or kl.expr_value(prompt_cond) > 0
            if not visible:
                return None
            return {
                "type": "menu" if node.list else "comment",
                "name": f"__menu_{node.linenr}",
                "prompt": prompt_text,
                "value": None,
                "help": node.help,
                "choices": [],
                "readonly": False,
            }

        want_optional = show_optional and bool(item.name) and "WANT_" in item.name
        if item.visibility == 0 and not want_optional:
            return None

        type_names = {
            kl.BOOL: "bool",
            kl.TRISTATE: "tristate",
            kl.STRING: "string",
            kl.INT: "int",
            kl.HEX: "hex",
            kl.UNKNOWN: "unknown",
        }
        entry: dict[str, Any] = {
            "type": type_names.get(item.type, "unknown"),
            "name": item.name or f"__node_{node.linenr}",
            "prompt": prompt_text,
            "value": item.str_value,
            "help": node.help,
            "choices": [],
            "readonly": False,
        }

        if isinstance(item, kl.Symbol):
            if kl.expr_value(item.rev_dep) > 0:
                entry["readonly"] = True  # selected by another symbol
        elif isinstance(item, kl.Choice):
            entry["type"] = "choice"
            choices = [
                {"name": s.name, "prompt": s.nodes[0].prompt[0] if s.nodes else s.name}
                for s in item.syms
                if s.visibility > 0
            ]
            entry["choices"] = choices
            selected = getattr(item.selection, "name", None)
            entry["value"] = selected
            if len(choices) <= 1:
                return None  # a settled single-option choice adds no value
        return entry

    def _write_config(
        self, output_path: str, config_file: str | None, values: list[tuple[str, str]]
    ) -> None:
        with _KCONFIG_LOCK:
            kconf = self._load(config_file)
            self._apply_values(kconf, values)
            kconf.write_config(os.path.expanduser(output_path))


@lru_cache(maxsize=4)
def get_kconfig_service(klipper_dir: str) -> KconfigService:
    """Returns a shared KconfigService per klipper_dir (so the lock is shared)."""
    return KconfigService(klipper_dir)
