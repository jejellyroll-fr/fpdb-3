"""Shared harness for the HUD Preferences editor tests.

Three things live here so that every test of the editor speaks the same
language:

* the stat-sets fpdb ships (``HUD_config.xml.example`` and ``hud-packages/``),
  and a temporary configuration file that holds them -- never the user's own
  configuration;
* :func:`stat_set_snapshot`, a plain-data view of a parsed ``<ss>`` that two
  configurations can be compared by;
* :class:`EditorIO`, the editor's own load and write code driven without a
  window, and :func:`open_editor`, the real dialog built offscreen with every
  modal answered by the test or refused loudly.

A modal that nobody answered fails the test at once: the Qt suite runs headless
on CI, where an unanswered ``exec()`` would hang the job instead.
"""

from __future__ import annotations

import os
import shutil
from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import defusedxml.minidom

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "HUD_config.xml.example"
PACKAGES = ROOT / "hud-packages"

SET_FIELDS = (
    "rows",
    "cols",
    "xpad",
    "ypad",
    "rich_text",
    "font_size",
    "title_font_scale",
    "heading_font_scale",
    "positional_mode",
    "show_hero_hud",
)
BLOCK_FIELDS = (
    "label",
    "id",
    "scope",
    "audience",
    "position",
    "bgcolor",
    "fgcolor",
    "bordercolor",
    "title_bgcolor",
    "title_fgcolor",
    "title_font_scale",
    "heading_font_scale",
    "cell_width",
    "x",
    "y",
    "rows",
    "cols",
)
STAT_FIELDS = (
    "stat_name",
    "tip",
    "display_label",
    "click",
    "popup",
    "hudprefix",
    "hudsuffix",
    "hudcolor",
    "hudbgcolor",
    "stat_loth",
    "stat_hith",
    "stat_locolor",
    "stat_hicolor",
    "stat_midcolor",
    "colspan",
    "align",
    "data_source",
    "data_definition",
    "data_format",
    "data_min_sample",
)


# --- What fpdb ships ---------------------------------------------------------
def _stat_set_nodes(path: Path) -> list[Any]:
    doc = defusedxml.minidom.parse(str(path))
    return list(doc.getElementsByTagName("ss"))


def shipped_stat_sets() -> Iterator[tuple[str, Any]]:
    """``(id, <ss> node)`` for every stat-set in the example config and the packages."""
    for node in _stat_set_nodes(EXAMPLE):
        yield f"example:{node.getAttribute('name')}", node
    for package in sorted(PACKAGES.glob("*.fpdbhud")):
        for node in _stat_set_nodes(package):
            yield f"{package.stem}:{node.getAttribute('name')}", node


def config_copy(directory: Path, extra_stat_sets: list[Any] | tuple[Any, ...] = ()) -> Path:
    """A throwaway ``HUD_config.xml``: the example, plus any extra ``<ss>`` nodes."""
    target = directory / "HUD_config.xml"
    shutil.copy(EXAMPLE, target)
    if extra_stat_sets:
        doc = defusedxml.minidom.parse(str(target))
        parent = doc.getElementsByTagName("stat_sets")[0]
        for node in extra_stat_sets:
            parent.appendChild(doc.importNode(node, True))
        target.write_text(doc.toxml(), encoding="utf-8")
    return target


# --- Comparing stat-sets -----------------------------------------------------
def stat_set_snapshot(stat_set: Any) -> dict[str, Any]:
    """Everything the HUD reads from a parsed ``Stat_sets``, as plain data."""
    return {
        **{name: getattr(stat_set, name, None) for name in SET_FIELDS},
        "blocks": [
            {
                **{name: getattr(block, name, None) for name in BLOCK_FIELDS},
                "stats": {
                    rowcol: {name: getattr(stat, name, None) for name in STAT_FIELDS}
                    for rowcol, stat in sorted(block.stats.items())
                },
                "texts": sorted((dict(t) for t in block.texts), key=lambda t: t["rowcol"]),
                "hlines": sorted((dict(h) for h in block.hlines), key=lambda h: h["rowcol"]),
            }
            for block in stat_set.blocks
        ],
    }


# --- The editor's conversion code, without a window --------------------------
class EditorIO:
    """The dialog's own load/write methods, bound to a bare document.

    These methods only read ``self.config.doc`` and call each other, so they run
    unchanged here; what the editor would write is what this writes.
    """

    def __init__(self, doc: Any) -> None:
        from fpdb_3_legacy.modern_hud_preferences.main_dialog import ModernHudPreferences as Dialog

        self.config = SimpleNamespace(doc=doc)
        for name in (
            "_profile_from_stat_set",
            "_write_profile_stats",
            "_append_stat_node",
            "_append_text_node",
            "_append_hline_node",
        ):
            setattr(self, name, getattr(Dialog, name).__get__(self))
        self._stat_to_dict = Dialog._stat_to_dict

    def load(self, node: Any) -> Any:
        from fpdb_3_legacy import Configuration

        return getattr(self, "_profile_from_stat_set")(Configuration.Stat_sets(node))

    def write(self, node: Any, profile: Any, rows: int, cols: int) -> Any:
        """Write ``profile`` into ``node`` in place and parse it back."""
        from fpdb_3_legacy import Configuration

        getattr(self, "_write_profile_stats")(node, profile, rows, cols)
        return Configuration.Stat_sets(node)


# --- The real dialog, offscreen ----------------------------------------------
class UnexpectedModal(AssertionError):
    """A modal opened that the test did not plan to answer."""


@dataclass
class Modals:
    """Answers for the editor's modal calls, consumed in order.

    ``dialogs`` holds callables ``answer(dialog) -> int`` run in place of
    ``QDialog.exec()``; they may fill the dialog's widgets before "accepting".
    ``messages`` records every informational box the editor showed.
    """

    dialogs: deque[Callable[[Any], int]] = field(default_factory=deque)
    texts: deque[tuple[str, bool]] = field(default_factory=deque)
    colours: deque[Any] = field(default_factory=deque)
    questions: deque[Any] = field(default_factory=deque)
    messages: list[tuple[str, str]] = field(default_factory=list)

    def _next(self, queue: deque, what: str) -> Any:
        if not queue:
            raise UnexpectedModal(f"unanswered {what}")
        return queue.popleft()


def install_modals(monkeypatch: Any) -> Modals:
    """Route every modal of the editor through a :class:`Modals`."""
    from PySide6.QtWidgets import QColorDialog, QDialog, QInputDialog, QMessageBox

    modals = Modals()

    def exec_(dialog: Any) -> int:
        return modals._next(modals.dialogs, f"dialog {type(dialog).__name__}")(dialog)

    def record(kind: str) -> Callable[..., Any]:
        def show(_parent: Any, title: str, *args: Any, **_k: Any) -> Any:
            text = args[0] if args else ""
            modals.messages.append((kind, f"{title}: {text}"))
            return QMessageBox.StandardButton.Ok

        return staticmethod(show)

    monkeypatch.setattr(QDialog, "exec", exec_)
    monkeypatch.setattr(QMessageBox, "information", record("information"))
    monkeypatch.setattr(QMessageBox, "warning", record("warning"))
    monkeypatch.setattr(QMessageBox, "critical", record("critical"))
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *_a, **_k: modals._next(modals.questions, "question"))
    )
    monkeypatch.setattr(
        QInputDialog, "getText", staticmethod(lambda *_a, **_k: modals._next(modals.texts, "text input"))
    )
    monkeypatch.setattr(
        QColorDialog, "getColor", staticmethod(lambda *_a, **_k: modals._next(modals.colours, "colour picker"))
    )
    return modals


# Keeps the application this module created alive for the rest of the session.
_APP: Any = None


def open_editor(config_path: Path, monkeypatch: Any) -> tuple[Any, Modals]:
    """The real HUD Preferences dialog on ``config_path``, offscreen."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from fpdb_3_legacy import Configuration, dynamic_panels_consent
    from fpdb_3_legacy.modern_hud_preferences import ModernHudPreferences

    global _APP
    if QApplication.instance() is None:
        _APP = QApplication([])
    modals = install_modals(monkeypatch)
    dynamic_panels_consent.confirm(dynamic_panels_consent.consent_path(config_path))
    config = Configuration.Config(file=str(config_path))
    return ModernHudPreferences(config, None), modals


def select_profile(dialog: Any, name: str) -> dict[str, Any]:
    """Make ``name`` the active profile and return its editor data."""
    dialog.profile_combo.setCurrentText(name)
    assert dialog.profile_combo.currentText() == name
    return dialog.hud_profiles[name]


def reload_stat_set(config_path: Path, name: str) -> Any:
    """The stat-set ``name`` as a fresh reader of the file sees it."""
    from fpdb_3_legacy import Configuration

    return Configuration.Config(file=str(config_path)).stat_sets[name]
