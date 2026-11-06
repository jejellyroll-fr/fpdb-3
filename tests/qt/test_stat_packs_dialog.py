"""Offscreen checks for the stat pack manager (#403)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from PySide6.QtWidgets import QMessageBox

from fpdb_3_legacy import analytics_definitions, stat_packs
from fpdb_3_legacy.stat_packs_dialog import StatPacksDialog

pytestmark = pytest.mark.qt

EXAMPLE = Path(__file__).resolve().parents[2] / "docs" / "examples" / "example-preflop-pack"
PACK_ID = "example.preflop"


@pytest.fixture
def dialog(qtbot, tmp_path: Path) -> StatPacksDialog:
    window = StatPacksDialog(packs_dir=tmp_path / "packs")
    qtbot.addWidget(window)
    return window


def statuses(window: StatPacksDialog) -> dict[str, str]:
    return {row.id: row.status for row in window.rows}


def test_the_manager_starts_with_the_built_in_library(dialog: StatPacksDialog) -> None:
    assert statuses(dialog) == {"builtin": stat_packs.BUILTIN}
    # Nothing can be done to the built-in library from here.
    assert not dialog.uninstall_button.isEnabled()
    assert not dialog.toggle_button.isEnabled()


def test_import_disable_export_and_uninstall(dialog: StatPacksDialog, tmp_path: Path) -> None:
    assert dialog.import_pack(str(EXAMPLE))
    assert statuses(dialog)[PACK_ID] == stat_packs.ENABLED
    assert dialog.selected().id == PACK_ID
    assert "Restart" in dialog.notice.text()

    dialog.toggle_selected()
    assert statuses(dialog)[PACK_ID] == stat_packs.DISABLED
    assert dialog.toggle_button.text() == "Enable"
    registry = analytics_definitions.load_default_registry(packs_dir=dialog.packs_dir)
    assert "example.preflop.btn_open" not in registry

    exported = dialog.export_selected(str(tmp_path / "shared.fpdbstats"))
    assert exported is not None and exported.is_file()

    dialog.uninstall_selected(confirm=False)
    assert PACK_ID not in statuses(dialog)


def test_a_refused_pack_says_why(dialog: StatPacksDialog, tmp_path: Path, monkeypatch) -> None:
    broken = tmp_path / "broken"
    shutil.copytree(EXAMPLE, broken)
    (broken / "manifest.json").write_text(
        (broken / "manifest.json").read_text(encoding="utf-8").replace('"version": 1', '"version": 9'),
        encoding="utf-8",
    )
    shown: list[str] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: shown.append(args[2]))

    assert not dialog.import_pack(str(broken))

    assert "pack schema version 9 is newer than supported" in shown[0]
    assert PACK_ID not in statuses(dialog)


def test_an_invalid_installed_pack_shows_its_errors(dialog: StatPacksDialog) -> None:
    dialog.import_pack(str(EXAMPLE))
    installed = Path(dialog.packs_dir) / PACK_ID / "stats" / "steals.json"
    installed.write_text("{not json", encoding="utf-8")

    dialog.refresh(PACK_ID)

    assert statuses(dialog)[PACK_ID] == stat_packs.INVALID
    assert "This pack is not loaded" in dialog.details.toPlainText()
    assert not dialog.toggle_button.isEnabled()
    assert dialog.uninstall_button.isEnabled()


def test_an_io_error_while_replacing_is_reported(dialog: StatPacksDialog, monkeypatch) -> None:
    assert dialog.import_pack(str(EXAMPLE))
    real_install = stat_packs.install_pack

    def install(path, packs_dir=None, *, replace=False, **kwargs):
        if replace:
            raise OSError("permission denied")
        return real_install(path, packs_dir, replace=replace, **kwargs)

    shown: list[str] = []
    monkeypatch.setattr(stat_packs, "install_pack", install)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: shown.append(args[2]))

    assert not dialog.import_pack(str(EXAMPLE))
    assert "permission denied" in shown[0]


def test_a_state_that_cannot_be_saved_is_reported(dialog: StatPacksDialog, monkeypatch) -> None:
    assert dialog.import_pack(str(EXAMPLE))

    def refuse(*_args, **_kwargs):
        raise OSError("read-only file system")

    shown: list[str] = []
    monkeypatch.setattr(stat_packs, "set_enabled", refuse)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: shown.append(args[2]))

    dialog.toggle_selected()

    assert "read-only file system" in shown[0]
    assert statuses(dialog)[PACK_ID] == stat_packs.ENABLED
