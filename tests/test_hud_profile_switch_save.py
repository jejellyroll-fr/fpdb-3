"""Editing one HUD profile, switching to another, editing and saving again (#741).

Drives the real preferences dialog against a real configuration file: the edit
of the first profile must still be on disk after the second profile was edited
and saved, and both must survive reopening the file.
"""

from __future__ import annotations

import os
import shutil

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
EXAMPLE = os.path.join(ROOT, "HUD_config.xml.example")

pytestmark = [pytest.mark.qt, pytest.mark.skipif(not os.path.exists(EXAMPLE), reason="example config missing")]


def _open(tmp_path):
    from PySide6.QtWidgets import QApplication

    from fpdb_3_legacy import Configuration as Conf
    from fpdb_3_legacy import ModernHudPreferences as M
    from fpdb_3_legacy import dynamic_panels_consent

    QApplication.instance() or QApplication([])
    config_path = tmp_path / "HUD_config.xml"
    if not config_path.exists():
        shutil.copy(EXAMPLE, config_path)
    dynamic_panels_consent.confirm(dynamic_panels_consent.consent_path(config_path))
    config = Conf.Config(file=str(config_path))
    dlg = M.ModernHudPreferences(config, None)
    dlg._config_path = config_path
    return dlg, config_path


def test_edit_switch_edit_save_persists_both_profiles(tmp_path, monkeypatch) -> None:
    from PySide6.QtWidgets import QMessageBox

    from fpdb_3_legacy import Configuration as Conf

    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: None))

    dlg, config_path = _open(tmp_path)
    names = list(dlg.hud_profiles.keys())
    assert len(names) >= 2
    first, second = names[0], names[1]

    # Edit the first profile and save.
    dlg.profile_combo.setCurrentText(first)
    dlg.hud_profiles[first]["stats"].append({"row": 4, "col": 4, "stat": "vpip", "click": "", "popup": ""})
    dlg.save_changes()

    on_disk = Conf.Config(file=str(config_path))
    assert (4, 4) in on_disk.stat_sets[first].stats

    # Switch to another profile, edit it, save again.
    dlg.profile_combo.setCurrentText(second)
    dlg.hud_profiles[second]["rows"] = 7
    dlg.save_changes()

    # Reopen from disk: both edits survived.
    reopened = Conf.Config(file=str(config_path))
    assert (4, 4) in reopened.stat_sets[first].stats
    assert reopened.stat_sets[second].rows == 7
