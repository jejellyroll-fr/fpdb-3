#!/usr/bin/env python3
"""Test fpdb_3_legacy.pt4hud.import_to_config — writing a .pt4hud into HUD_config.

Copies the example HUD_config.xml, imports the real .pt4hud fixture, saves, and
re-parses to confirm a valid stat-set + RangeChartPopup were added and the chart
JSON sidecar was written.
"""

from __future__ import annotations

import os
import shutil
import sys

import pytest

pytestmark = pytest.mark.qt

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "generationpoker_3h.pt4hud")
EXAMPLE = os.path.join(ROOT, "HUD_config.xml.example")


@pytest.mark.skipif(not (os.path.exists(FIXTURE) and os.path.exists(EXAMPLE)), reason="fixtures missing")
def test_import_to_config_roundtrip(tmp_path):
    from fpdb_3_legacy import Configuration as Conf
    from fpdb_3_legacy import pt4hud

    cfg_path = tmp_path / "HUD_config.xml"
    shutil.copy(EXAMPLE, cfg_path)
    cfg = Conf.Config(file=str(cfg_path))
    n_ss, n_pu = len(cfg.stat_sets), len(cfg.popup_windows)

    summary = pt4hud.import_to_config(FIXTURE, cfg)
    cfg.save()

    assert summary["stats"] >= 18
    assert summary["charts"] == ["Push Nash", "Call Nash"]
    assert os.path.exists(summary["charts_path"])

    # the saved config must re-parse and contain the new stat-set + popups
    # (the RangeChartPopup plus one BlockPopup per imported popup group)
    cfg2 = Conf.Config(file=str(cfg_path))
    assert len(cfg2.stat_sets) == n_ss + 1
    assert len(cfg2.popup_windows) == n_pu + 1 + len(summary["popup_groups"])
    assert summary["name"] in cfg2.stat_sets
    # imported as multi-panel blocks (SB/BB/BU/info), re-parsed cleanly
    assert summary["blocks"] >= 3
    imported = cfg2.stat_sets[summary["name"]]
    assert imported.is_multiblock
    assert imported.show_hero_hud == "false"
    assert len(imported.blocks) == summary["blocks"]
    # position-conditional bindings carried through from PT4 panel labels
    positions = {b.label.split()[0]: b.position for b in imported.blocks if b.label}
    assert positions.get("SB") == "SB"
    assert positions.get("BB") == "BB"
    assert positions.get("BU") == "BTN"
    styled = {b.label.split()[0]: b for b in imported.blocks if b.label}
    assert styled["SB"].bordercolor == "#d7b500"
    assert styled["BB"].bordercolor == "#b75a70"
    assert styled["BU"].bordercolor == "#009a9a"
    assert (styled["SB"].x, styled["SB"].y) == (0, 0)
    assert styled["Villain"].y > 0
    hands = next(
        stat
        for block in imported.blocks
        for stat in block.stats.values()
        if stat.stat_name == "n"
    )
    assert hands.tip == "Hands Abbreviated"
    assert hands.hudcolor == "#0069d2"
    assert hands.hudbgcolor == "#a2a28a"
    pu = cfg2.popup_windows[summary["popup"]]
    assert pu.pu_class == "RangeChartPopup"
    assert pu.pu_class_params.get("source") == summary["charts_path"]

    # the sidecar JSON drives the render widget
    from fpdb_3_legacy import RangeChartPopup as R

    charts = R.load_charts(summary["charts_path"])
    assert {c.name for c in charts} == {"Push Nash", "Call Nash"}


@pytest.mark.skipif(not (os.path.exists(FIXTURE) and os.path.exists(EXAMPLE)), reason="fixtures missing")
def test_import_to_config_reimport_replaces_chart_popup(tmp_path):
    """Re-importing the same chart HUD replaces both the stat-set and popup."""
    from fpdb_3_legacy import Configuration as Conf
    from fpdb_3_legacy import pt4hud

    cfg_path = tmp_path / "HUD_config.xml"
    shutil.copy(EXAMPLE, cfg_path)
    cfg = Conf.Config(file=str(cfg_path))

    first = pt4hud.import_to_config(FIXTURE, cfg)
    second = pt4hud.import_to_config(FIXTURE, cfg)
    cfg.save()

    cfg2 = Conf.Config(file=str(cfg_path))
    stat_set_names = [
        ss.getAttribute("name")
        for ss in cfg2.doc.getElementsByTagName("ss")
        if ss.getAttribute("name") == second["name"]
    ]
    popup_names = [
        pu.getAttribute("pu_name")
        for pu in cfg2.doc.getElementsByTagName("pu")
        if pu.getAttribute("pu_name") == second["popup"]
    ]

    assert first["name"] == second["name"]
    assert stat_set_names == [second["name"]]
    assert popup_names == [second["popup"]]


@pytest.mark.skipif(not (os.path.exists(FIXTURE) and os.path.exists(EXAMPLE)), reason="fixtures missing")
def test_modern_hud_prefs_import_pt4hud(tmp_path, monkeypatch):
    """The HUD Preferences 'Import HUD' button accepts .pt4hud end to end."""
    from PySide6.QtWidgets import QApplication, QComboBox, QMessageBox

    from fpdb_3_legacy import Configuration as Conf
    from fpdb_3_legacy import ModernHudPreferences as M

    QApplication.instance() or QApplication([])
    # message boxes must not block the test
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: None))

    cfg_path = tmp_path / "HUD_config.xml"
    shutil.copy(EXAMPLE, cfg_path)
    cfg = Conf.Config(file=str(cfg_path))
    n_ss = len(cfg.stat_sets)

    # build a bare dialog instance and stub the UI-refresh hooks
    dlg = M.ModernHudPreferences.__new__(M.ModernHudPreferences)
    dlg.config = cfg
    dlg.profile_combo = QComboBox()
    dlg.load_profiles = lambda: None
    dlg.load_popup_windows = lambda: None
    dlg.on_profile_selected = lambda _i: None

    dlg._import_pt4hud(str(FIXTURE))

    # config saved with the imported multi-block stat-set
    cfg2 = Conf.Config(file=str(cfg_path))
    assert len(cfg2.stat_sets) == n_ss + 1
    assert any(ss.is_multiblock for ss in cfg2.stat_sets.values())


@pytest.mark.skipif(not (os.path.exists(FIXTURE) and os.path.exists(EXAMPLE)), reason="fixtures missing")
def test_editor_shows_all_multiblock_stats(tmp_path):
    """load_profiles must surface every panel's stats (no (row,col) collision loss)."""
    from PySide6.QtWidgets import QApplication, QComboBox

    from fpdb_3_legacy import Configuration as Conf
    from fpdb_3_legacy import ModernHudPreferences as M
    from fpdb_3_legacy import pt4hud

    QApplication.instance() or QApplication([])
    cfg_path = tmp_path / "HUD_config.xml"
    shutil.copy(EXAMPLE, cfg_path)
    cfg = Conf.Config(file=str(cfg_path))
    summary = pt4hud.import_to_config(FIXTURE, cfg)
    cfg.save()
    cfg.reload()

    dlg = M.ModernHudPreferences.__new__(M.ModernHudPreferences)
    dlg.config = cfg
    dlg.profile_combo = QComboBox()
    dlg.load_profiles()

    prof = dlg.hud_profiles[summary["name"]]
    # every block's stats present (no collapse to ~9), panels stacked by row
    total_block_stats = sum(len(b.stats) for b in cfg.stat_sets[summary["name"]].blocks)
    assert len(prof["stats"]) == total_block_stats
    assert len(prof["stats"]) > 9
    assert prof.get("multiblock") is True
    assert {"SB 3h", "BB 3h", "BU 3h"} <= {s.get("panel", "") for s in prof["stats"]}
    # stacked: rows span beyond a single panel
    assert prof["rows"] >= 6


@pytest.mark.skipif(not (os.path.exists(FIXTURE) and os.path.exists(EXAMPLE)), reason="fixtures missing")
def test_editor_prefers_stat_sets_over_flat_hud_profiles_for_preview(tmp_path):
    """A stale/flat hud_profiles cache must not hide imported PT4 block metadata."""
    from PySide6.QtWidgets import QApplication, QComboBox

    from fpdb_3_legacy import Configuration as Conf
    from fpdb_3_legacy import ModernHudPreferences as M
    from fpdb_3_legacy import pt4hud

    QApplication.instance() or QApplication([])
    cfg_path = tmp_path / "HUD_config.xml"
    shutil.copy(EXAMPLE, cfg_path)
    cfg = Conf.Config(file=str(cfg_path))
    summary = pt4hud.import_to_config(FIXTURE, cfg)
    cfg.save()
    cfg.reload()

    cfg.hud_profiles = {
        summary["name"]: {
            "rows": 5,
            "cols": 4,
            "stats": [{"row": 0, "col": 0, "stat": "vpip"}],
        },
    }

    dlg = M.ModernHudPreferences.__new__(M.ModernHudPreferences)
    dlg.config = cfg
    dlg.profile_combo = QComboBox()
    dlg.load_profiles()

    prof = dlg.hud_profiles[summary["name"]]
    assert prof.get("multiblock") is True
    assert len(prof["blocks"]) == summary["blocks"]
    assert len(prof["stats"]) == summary["stats"]


@pytest.mark.skipif(not (os.path.exists(FIXTURE) and os.path.exists(EXAMPLE)), reason="fixtures missing")
def test_save_changes_preserves_multiblock_stat_sets(tmp_path, monkeypatch):
    """Saving preferences must not flatten imported PT4 <block> panels."""
    from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QMessageBox, QSpinBox

    from fpdb_3_legacy import Configuration as Conf
    from fpdb_3_legacy import ModernHudPreferences as M
    from fpdb_3_legacy import pt4hud

    QApplication.instance() or QApplication([])
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: None))

    cfg_path = tmp_path / "HUD_config.xml"
    shutil.copy(EXAMPLE, cfg_path)
    cfg = Conf.Config(file=str(cfg_path))
    summary = pt4hud.import_to_config(FIXTURE, cfg)
    cfg.save()
    cfg.reload()

    dlg = M.ModernHudPreferences.__new__(M.ModernHudPreferences)
    dlg.config = cfg
    dlg.profile_combo = QComboBox()
    dlg.popup_windows = {}
    dlg.profiling_checkbox = QCheckBox()
    dlg.profile_in_name_checkbox = QCheckBox()
    dlg.profile_min_hands_spin = QSpinBox()
    dlg._deep_copy_profiles = M.ModernHudPreferences._deep_copy_profiles.__get__(dlg, M.ModernHudPreferences)
    dlg._deep_copy_popups = M.ModernHudPreferences._deep_copy_popups.__get__(dlg, M.ModernHudPreferences)
    dlg.accept = lambda: None
    dlg.load_profiles()

    dlg.save_changes()

    cfg2 = Conf.Config(file=str(cfg_path))
    imported = cfg2.stat_sets[summary["name"]]
    assert imported.is_multiblock
    assert len(imported.blocks) == summary["blocks"]
    assert sum(len(block.stats) for block in imported.blocks) == summary["stats"]


@pytest.mark.skipif(not (os.path.exists(FIXTURE) and os.path.exists(EXAMPLE)), reason="fixtures missing")
def test_full_dialog_multiblock_preview_gets_real_geometry(tmp_path):
    """The preview must not collapse the rendered HUD box to a tiny dot."""
    from PySide6.QtWidgets import QApplication

    from fpdb_3_legacy import Configuration as Conf
    from fpdb_3_legacy import ModernHudPreferences as M
    from fpdb_3_legacy import pt4hud

    app = QApplication.instance() or QApplication([])
    cfg_path = tmp_path / "HUD_config.xml"
    shutil.copy(EXAMPLE, cfg_path)
    cfg = Conf.Config(file=str(cfg_path))
    summary = pt4hud.import_to_config(FIXTURE, cfg)
    cfg.save()
    cfg.reload()

    dlg = M.ModernHudPreferences(cfg)
    dlg.resize(1600, 900)
    dlg.show()
    app.processEvents()
    dlg.profile_combo.setCurrentText(summary["name"])
    dlg.on_profile_selected(dlg.profile_combo.currentIndex())
    app.processEvents()
    app.processEvents()

    # The preview mirrors the canvas: it shows the selected panel only (one block),
    # and must render at a real size (not collapsed to a dot).
    assert len(dlg.preview.blocks) == 1
    assert dlg.preview.hud_window.width() > 100
    assert dlg.preview.hud_window.height() > 60


@pytest.mark.skipif(not (os.path.exists(FIXTURE) and os.path.exists(EXAMPLE)), reason="fixtures missing")
def test_import_emits_text_items_in_grid():
    """Import captures PT4 text labels (headers/captions) as positioned <text> items."""
    from fpdb_3_legacy import Configuration as Conf
    from fpdb_3_legacy import pt4hud
    import tempfile

    td = tempfile.mkdtemp()
    cfg = os.path.join(td, "HUD_config.xml")
    shutil.copy(EXAMPLE, cfg)
    c = Conf.Config(file=cfg)
    summary = pt4hud.import_to_config(FIXTURE, c)
    c.save()
    c.reload()
    bb = next(b for b in c.stat_sets[summary["name"]].blocks if b.label == "BB 3h")
    labels = {t["label"] for t in bb.texts}
    # column headers, row labels and the section caption are present as text items
    assert {"FLAT", "3B", "ISO", "TOTAL", "POST FLOP", "FvCB"} <= labels
    # POST FLOP spans the full width
    post = next(t for t in bb.texts if t["label"] == "POST FLOP")
    assert post["colspan"] == bb.cols


@pytest.mark.skipif(not (os.path.exists(FIXTURE) and os.path.exists(EXAMPLE)), reason="fixtures missing")
def test_editor_save_preserves_text_items(tmp_path):
    """Editing+saving a multi-panel profile must not drop its <text> items."""
    from PySide6.QtWidgets import QApplication, QComboBox

    from fpdb_3_legacy import Configuration as Conf
    from fpdb_3_legacy import ModernHudPreferences as M
    from fpdb_3_legacy import pt4hud

    QApplication.instance() or QApplication([])
    cfg = tmp_path / "HUD_config.xml"
    shutil.copy(EXAMPLE, cfg)
    c = Conf.Config(file=str(cfg))
    summary = pt4hud.import_to_config(FIXTURE, c)
    c.save()
    c.reload()

    dlg = M.ModernHudPreferences.__new__(M.ModernHudPreferences)
    dlg.config = c
    dlg.profile_combo = QComboBox()
    dlg.load_profiles()
    prof = dlg.hud_profiles[summary["name"]]
    assert any(b.get("texts") for b in prof["blocks"])  # loaded with texts

    # write the profile back (simulating Save Changes) and confirm texts survive
    ss_node = next(n for n in c.doc.getElementsByTagName("ss") if n.getAttribute("name") == summary["name"])
    dlg._write_profile_stats(ss_node, prof, prof["rows"], prof["cols"])
    c.save()
    c.reload()
    bb = next(b for b in c.stat_sets[summary["name"]].blocks if b.label == "BB 3h")
    assert len(bb.texts) >= 6


@pytest.mark.skipif(not (os.path.exists(FIXTURE) and os.path.exists(EXAMPLE)), reason="fixtures missing")
def test_block_aware_edit_persists(tmp_path):
    """Editing a multi-panel profile must modify the block and survive save."""
    from PySide6.QtWidgets import QApplication, QComboBox

    from fpdb_3_legacy import Configuration as Conf
    from fpdb_3_legacy import ModernHudPreferences as M
    from fpdb_3_legacy import pt4hud

    QApplication.instance() or QApplication([])

    class FakeTable:  # headless: report a selectable current row
        def __init__(self):
            self._cur = -1
        def setRowCount(self, n):
            pass
        def setItem(self, *a):
            pass
        def currentRow(self):
            return self._cur
        def setCurrentCell(self, r, _c):
            self._cur = r

    cfg = tmp_path / "HUD_config.xml"
    shutil.copy(EXAMPLE, cfg)
    c = Conf.Config(file=str(cfg))
    summary = pt4hud.import_to_config(FIXTURE, c)
    c.save()
    c.reload()

    dlg = M.ModernHudPreferences.__new__(M.ModernHudPreferences)
    dlg.config = c
    dlg.profile_combo = QComboBox()
    dlg.stat_table = FakeTable()
    dlg.preview = type("P", (), {m: (lambda *a, **k: None) for m in
                                 ("set_hud_params", "set_grid", "set_blocks", "set_stats")})()
    dlg.update_status = lambda *a, **k: None
    dlg._hud_preview_params = lambda: {"bgcolor": "#000", "fgcolor": "#fff", "font": "Sans", "font_size": 8}
    dlg.load_profiles()
    dlg.profile_combo.setCurrentText(summary["name"])
    dlg.on_profile_selected(dlg.profile_combo.currentIndex())

    prof = dlg.hud_profiles[summary["name"]]
    before = sum(len(b["stats"]) for b in prof["blocks"])
    stat_row = next(r for r, (bi, kind, ref) in enumerate(dlg._row_items) if kind == "stat")
    dlg.stat_table.setCurrentCell(stat_row, 0)
    dlg.remove_stat()
    after = sum(len(b["stats"]) for b in prof["blocks"])
    assert after == before - 1  # removed from the block, not a flat list

    ss_node = next(n for n in c.doc.getElementsByTagName("ss") if n.getAttribute("name") == summary["name"])
    dlg._write_profile_stats(ss_node, prof, prof["rows"], prof["cols"])
    c.save()
    saved = sum(len(b.stats) for b in Conf.Config(file=str(cfg)).stat_sets[summary["name"]].blocks)
    assert saved == after  # the edit persisted through save+reload


@pytest.mark.skipif(not (os.path.exists(FIXTURE) and os.path.exists(EXAMPLE)), reason="fixtures missing")
def test_add_label_block_and_props_persist(tmp_path):
    """Add Text Label / Add Block / Block Properties edit blocks and survive save."""
    import unittest.mock as mk

    from PySide6.QtWidgets import QApplication, QComboBox

    from fpdb_3_legacy import Configuration as Conf
    from fpdb_3_legacy import ModernHudPreferences as M
    from fpdb_3_legacy import pt4hud

    QApplication.instance() or QApplication([])

    class FakeTable:
        def __init__(self):
            self._cur = -1
        def setRowCount(self, n):
            pass
        def setItem(self, *a):
            pass
        def currentRow(self):
            return self._cur
        def setCurrentCell(self, r, _c):
            self._cur = r

    cfg = tmp_path / "HUD_config.xml"
    shutil.copy(EXAMPLE, cfg)
    c = Conf.Config(file=str(cfg))
    summary = pt4hud.import_to_config(FIXTURE, c)
    c.save()
    c.reload()

    dlg = M.ModernHudPreferences.__new__(M.ModernHudPreferences)
    dlg.config = c
    dlg.profile_combo = QComboBox()
    dlg.stat_table = FakeTable()
    dlg.preview = type("P", (), {m: (lambda *a, **k: None) for m in
                                 ("set_hud_params", "set_grid", "set_blocks", "set_stats")})()
    dlg.update_status = lambda *a, **k: None
    dlg._hud_preview_params = lambda: {"bgcolor": "#000", "fgcolor": "#fff", "font": "Sans", "font_size": 8}
    dlg.load_profiles()
    dlg.profile_combo.setCurrentText(summary["name"])
    dlg.on_profile_selected(dlg.profile_combo.currentIndex())
    prof = dlg.hud_profiles[summary["name"]]

    dlg.stat_table.setCurrentCell(0, 0)
    with mk.patch("PySide6.QtWidgets.QInputDialog.getText", return_value=("MY LABEL", True)):
        dlg.add_text_label()
    nblocks = len(prof["blocks"])
    with mk.patch("PySide6.QtWidgets.QInputDialog.getText", return_value=("CO 3h", True)):
        dlg.add_block()
    assert len(prof["blocks"]) == nblocks + 1
    d = M.BlockPropertiesDialog(prof["blocks"][0])
    d.label_input.setText("SB EDITED")
    d._colors["title_bgcolor"] = "#123456"
    prof["blocks"][0].update(d.get_props())

    ss_node = next(n for n in c.doc.getElementsByTagName("ss") if n.getAttribute("name") == summary["name"])
    dlg._write_profile_stats(ss_node, prof, prof["rows"], prof["cols"])
    c.save()
    blks = Conf.Config(file=str(cfg)).stat_sets[summary["name"]].blocks
    assert len(blks) == nblocks + 1
    assert blks[0].label == "SB EDITED"
    assert blks[0].title_bgcolor == "#123456"
    assert any(t["label"] == "MY LABEL" for b in blks for t in b.texts)


@pytest.mark.skipif(not (os.path.exists(FIXTURE) and os.path.exists(EXAMPLE)), reason="fixtures missing")
def test_add_hline_appears_and_persists(tmp_path):
    """Add Line inserts an <hline> into the block, shows in the table, and saves."""
    from PySide6.QtWidgets import QApplication, QComboBox

    from fpdb_3_legacy import Configuration as Conf
    from fpdb_3_legacy import ModernHudPreferences as M
    from fpdb_3_legacy import pt4hud

    QApplication.instance() or QApplication([])

    class FakeTable:
        def __init__(self):
            self._cur = -1
        def setRowCount(self, n):
            pass
        def setItem(self, *a):
            pass
        def currentRow(self):
            return self._cur
        def setCurrentCell(self, r, _c):
            self._cur = r

    cfg = tmp_path / "HUD_config.xml"
    shutil.copy(EXAMPLE, cfg)
    c = Conf.Config(file=str(cfg))
    summary = pt4hud.import_to_config(FIXTURE, c)
    c.save()
    c.reload()

    dlg = M.ModernHudPreferences.__new__(M.ModernHudPreferences)
    dlg.config = c
    dlg.profile_combo = QComboBox()
    dlg.stat_table = FakeTable()
    dlg.preview = type("P", (), {m: (lambda *a, **k: None) for m in
                                 ("set_hud_params", "set_grid", "set_blocks", "set_stats")})()
    dlg.update_status = lambda *a, **k: None
    dlg._hud_preview_params = lambda: {"bgcolor": "#000", "fgcolor": "#fff", "font": "Sans", "font_size": 8}
    dlg.load_profiles()
    dlg.profile_combo.setCurrentText(summary["name"])
    dlg.on_profile_selected(dlg.profile_combo.currentIndex())
    prof = dlg.hud_profiles[summary["name"]]

    dlg.stat_table.setCurrentCell(0, 0)
    before = sum(len(b.get("hlines", [])) for b in prof["blocks"])
    dlg.add_hline()
    assert sum(len(b.get("hlines", [])) for b in prof["blocks"]) == before + 1
    assert any(kind == "hline" for _bi, kind, _ref in dlg._row_items)  # shown in table

    ss_node = next(n for n in c.doc.getElementsByTagName("ss") if n.getAttribute("name") == summary["name"])
    dlg._write_profile_stats(ss_node, prof, prof["rows"], prof["cols"])
    c.save()
    saved = sum(len(b.hlines) for b in Conf.Config(file=str(cfg)).stat_sets[summary["name"]].blocks)
    assert saved == before + 1


@pytest.mark.skipif(not (os.path.exists(FIXTURE) and os.path.exists(EXAMPLE)), reason="fixtures missing")
def test_group_panel_list_select_rename_delete(tmp_path):
    """PT4-style Panels list + Group Properties: list, select, rename, delete."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (QApplication, QComboBox, QGroupBox, QLineEdit,
                                   QListWidget, QSlider, QVBoxLayout, QWidget)

    from fpdb_3_legacy import Configuration as Conf
    from fpdb_3_legacy import ModernHudPreferences as M
    from fpdb_3_legacy import pt4hud

    QApplication.instance() or QApplication([])

    class FakeTable:
        def __init__(self):
            self._cur = -1
        def setRowCount(self, n):
            pass
        def setItem(self, *a):
            pass
        def currentRow(self):
            return self._cur
        def setCurrentCell(self, r, _c):
            self._cur = r

    cfg = tmp_path / "HUD_config.xml"
    shutil.copy(EXAMPLE, cfg)
    c = Conf.Config(file=str(cfg))
    summary = pt4hud.import_to_config(FIXTURE, c)
    c.save()
    c.reload()

    d = M.ModernHudPreferences.__new__(M.ModernHudPreferences)
    d.config = c
    d.profile_combo = QComboBox()
    d.stat_table = FakeTable()
    d.preview = type("P", (), {m: (lambda *a, **k: None) for m in
                               ("set_hud_params", "set_grid", "set_blocks", "set_stats")})()
    d.update_status = lambda *a, **k: None
    d._hud_preview_params = lambda: {"bgcolor": "#000", "fgcolor": "#fff", "font": "Sans", "font_size": 8}
    host = QWidget()
    d._design_host = host
    d._design_layout = QVBoxLayout(host)
    d._design_canvases = []
    d._loading_group = False
    d._current_block_index = 0
    d.group_list = QListWidget()
    d.group_list.currentRowChanged.connect(d._on_group_selected)
    d.gp_name = QLineEdit()
    d.gp_position = QComboBox()
    d.gp_position.addItems(["", "SB", "BB", "BTN", "CO", "MP", "EP"])
    d._group_color_btns = {}
    for attr in ("title_bgcolor", "title_fgcolor", "bordercolor", "bgcolor"):
        setattr(d, f"gp_{attr}", d._group_color_btn(attr))
    d.gp_opacity = QSlider(Qt.Orientation.Horizontal)
    d.gp_opacity.setRange(0, 255)
    d.gp_opacity.setValue(178)
    d.group_props_box = QGroupBox()

    d.load_profiles()
    d.profile_combo.setCurrentText(summary["name"])
    d.on_profile_selected(d.profile_combo.currentIndex())

    assert d.group_list.count() == 5
    assert [d.group_list.item(i).text() for i in range(5)] == [
        "SB 3h", "BB 3h", "BU 3h", "Villain Info 3H", "Min Stack (Table)",
    ]

    d.group_list.setCurrentRow(1)
    assert d.gp_name.text() == "BB 3h"
    assert d.gp_position.currentText() == "BB"

    d.gp_name.setText("BB STACKED")
    d._group_prop_changed()
    assert d.hud_profiles[summary["name"]]["blocks"][1]["label"] == "BB STACKED"
    assert d.group_list.item(1).text() == "BB STACKED"

    # rename persists through save
    prof = d.hud_profiles[summary["name"]]
    ss_node = next(n for n in c.doc.getElementsByTagName("ss") if n.getAttribute("name") == summary["name"])
    d._write_profile_stats(ss_node, prof, prof["rows"], prof["cols"])
    c.save()
    blks = Conf.Config(file=str(cfg)).stat_sets[summary["name"]].blocks
    assert blks[1].label == "BB STACKED"

    # delete a panel
    d._current_block_index = 3
    d._group_delete()
    assert len(d.hud_profiles[summary["name"]]["blocks"]) == 4


@pytest.mark.skipif(not (os.path.exists(FIXTURE) and os.path.exists(EXAMPLE)), reason="fixtures missing")
def test_group_items_and_item_properties(tmp_path):
    """PT4-style Group Items list + Item Properties edit (block-aware, persists)."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (QApplication, QComboBox, QGroupBox, QLineEdit, QListWidget,
                                   QSlider, QSpinBox, QTabWidget, QVBoxLayout, QWidget)

    from fpdb_3_legacy import Configuration as Conf
    from fpdb_3_legacy import ModernHudPreferences as M
    from fpdb_3_legacy import pt4hud

    QApplication.instance() or QApplication([])

    class FakeTable:
        def __init__(self):
            self._cur = -1
        def setRowCount(self, n):
            pass
        def setItem(self, *a):
            pass
        def currentRow(self):
            return self._cur
        def setCurrentCell(self, r, _c):
            self._cur = r

    cfg = tmp_path / "HUD_config.xml"
    shutil.copy(EXAMPLE, cfg)
    c = Conf.Config(file=str(cfg))
    summary = pt4hud.import_to_config(FIXTURE, c)
    c.save()
    c.reload()

    d = M.ModernHudPreferences.__new__(M.ModernHudPreferences)
    d.config = c
    d.profile_combo = QComboBox()
    d.stat_table = FakeTable()
    d.preview = type("P", (), {m: (lambda *a, **k: None) for m in
                               ("set_hud_params", "set_grid", "set_blocks", "set_stats")})()
    d.update_status = lambda *a, **k: None
    d._hud_preview_params = lambda: {"bgcolor": "#000", "fgcolor": "#fff", "font": "Sans", "font_size": 8}
    host = QWidget()
    d._design_host = host
    d._design_layout = QVBoxLayout(host)
    d._design_canvases = []
    d._loading_group = False
    d._current_block_index = 0
    d.group_list = QListWidget()
    d.group_list.currentRowChanged.connect(d._on_group_selected)
    d.gp_name = QLineEdit()
    d.gp_position = QComboBox()
    d.gp_position.addItems(["", "SB", "BB", "BTN", "CO", "MP", "EP"])
    d._group_color_btns = {}
    for attr in ("title_bgcolor", "title_fgcolor", "bordercolor", "bgcolor"):
        setattr(d, f"gp_{attr}", d._group_color_btn(attr))
    d.gp_opacity = QSlider(Qt.Orientation.Horizontal)
    d.gp_opacity.setRange(0, 255)
    d.gp_opacity.setValue(178)
    d.group_props_box = QGroupBox()
    d._loading_item = False
    d._group_item_refs = []
    d.group_items_list = QListWidget()
    d.group_items_list.currentRowChanged.connect(d._on_group_item_selected)
    d.item_props_tabs = QTabWidget()
    d.item_props_tabs.addTab(QWidget(), "Item")
    d.item_props_tabs.addTab(QWidget(), "CR")
    d.ip_text = QLineEdit()
    d.ip_popup = QLineEdit()
    d.ip_colspan = QSpinBox()
    d.ip_colspan.setRange(1, 12)
    d.ip_align = QComboBox()
    d.ip_align.addItems(["center", "left", "right"])
    d._item_color_btns = {}
    d.ip_fg = d._item_color_btn("fg")
    d.ip_bg = d._item_color_btn("bg")
    d.ip_loth = QSpinBox()
    d.ip_loth.setRange(0, 100)
    d.ip_hith = QSpinBox()
    d.ip_hith.setRange(0, 100)
    d.ip_locolor = d._item_color_btn("lo")
    d.ip_midcolor = d._item_color_btn("mid")
    d.ip_hicolor = d._item_color_btn("hi")

    d.load_profiles()
    d.profile_combo.setCurrentText(summary["name"])
    d.on_profile_selected(d.profile_combo.currentIndex())
    d.group_list.setCurrentRow(1)  # BB panel

    assert d.group_items_list.count() > 0
    stat_row = next(i for i, (k, _r) in enumerate(d._group_item_refs) if k == "stat")
    d.group_items_list.setCurrentRow(stat_row)
    assert d.item_props_tabs.isTabEnabled(1)  # tab always clickable
    assert d.ip_loth.isEnabled()  # colour-range controls active for stats
    d.ip_colspan.setValue(3)
    d.ip_align.setCurrentText("left")
    d.ip_loth.setValue(20)
    d.ip_hith.setValue(60)
    d._item_prop_changed()
    _k, ref = d._current_item()
    assert ref["colspan"] == 3 and ref["align"] == "left"
    assert ref["stat_loth"] == "20" and ref["stat_hith"] == "60"

    text_row = next(i for i, (k, _r) in enumerate(d._group_item_refs) if k == "text")
    d.group_items_list.setCurrentRow(text_row)
    assert d.item_props_tabs.isTabEnabled(1)  # tab still clickable for text items
    assert not d.ip_loth.isEnabled()  # but colour-range controls are disabled

    # the stat colspan/align edit persists through Save
    prof = d.hud_profiles[summary["name"]]
    ss_node = next(n for n in c.doc.getElementsByTagName("ss") if n.getAttribute("name") == summary["name"])
    d._write_profile_stats(ss_node, prof, prof["rows"], prof["cols"])
    c.save()
    blk = Conf.Config(file=str(cfg)).stat_sets[summary["name"]].blocks[1]
    assert any(st.colspan == 3 and st.align == "left" for st in blk.stats.values())


@pytest.mark.skipif(not (os.path.exists(FIXTURE) and os.path.exists(EXAMPLE)), reason="fixtures missing")
def test_full_dialog_pt4_layout_smoke(tmp_path):
    """The full HUD editor builds with the PT4 zones and a hidden flat table."""
    from PySide6.QtWidgets import QApplication

    from fpdb_3_legacy import Configuration as Conf
    from fpdb_3_legacy import ModernHudPreferences as M
    from fpdb_3_legacy import pt4hud

    QApplication.instance() or QApplication([])

    cfg = tmp_path / "HUD_config.xml"
    shutil.copy(EXAMPLE, cfg)
    c = Conf.Config(file=str(cfg))
    summary = pt4hud.import_to_config(FIXTURE, c)
    c.save()
    c.reload()

    dlg = M.ModernHudPreferences(c, None)
    idx = dlg.profile_combo.findText(summary["name"])
    assert idx >= 0
    dlg.profile_combo.setCurrentIndex(idx)
    dlg.on_profile_selected(idx)

    # PT4 zones present
    assert dlg.group_list.count() == 5               # Panels (SB/BB/BU/Villain/Min Stack)
    assert dlg.group_props_box is not None           # Group Properties
    assert dlg.item_props_tabs.count() == 2          # Item Properties + Color Ranges
    assert not dlg.stat_table.isVisibleTo(dlg)       # flat table hidden in PT4 layout

    dlg.group_list.setCurrentRow(1)                  # BB panel
    assert dlg.group_items_list.count() > 0          # Items list populated
    # Canvas shows only the selected panel (box-by-box, like PT4).
    assert len(dlg._design_canvases) == 1
    assert dlg._design_canvases[0].block_index == 1  # follows the selected panel
    # switching panels updates the canvas to that panel
    dlg.group_list.setCurrentRow(2)
    assert dlg._design_canvases[0].block_index == 2


@pytest.mark.skipif(not (os.path.exists(FIXTURE) and os.path.exists(EXAMPLE)), reason="fixtures missing")
def test_popup_preview_renders_imported_range_charts(tmp_path):
    """The imported RangeChartPopup renders its 13x13 grids in the popup preview."""
    from PySide6.QtWidgets import QApplication, QLabel

    from fpdb_3_legacy import Configuration as Conf
    from fpdb_3_legacy import ModernHudPreferences as M
    from fpdb_3_legacy import pt4hud

    QApplication.instance() or QApplication([])
    cfg = tmp_path / "HUD_config.xml"
    shutil.copy(EXAMPLE, cfg)
    c = Conf.Config(file=str(cfg))
    summary = pt4hud.import_to_config(FIXTURE, c)
    c.save()
    c.reload()

    dlg = M.ModernHudPreferences(c, None)
    ci = dlg.popup_combo.findText(summary["popup"])
    assert ci >= 0
    dlg.popup_combo.setCurrentIndex(ci)
    dlg.on_popup_selected(ci)

    labels = {w.text() for w in dlg.popup_preview.findChildren(QLabel)}
    assert {"Push Nash", "Call Nash"} <= labels          # both chart titles render
    assert {"AA", "AKs", "72o"} <= labels                # grid hand cells render
    assert "No popup stats configured" not in " ".join(labels)


@pytest.mark.skipif(not (os.path.exists(FIXTURE) and os.path.exists(EXAMPLE)), reason="fixtures missing")
def test_popup_chart_renders_even_if_class_overwritten(tmp_path):
    """The range-chart popup still renders from its source if the class combo
    (which can't represent RangeChartPopup) left the class as 'default'."""
    from PySide6.QtWidgets import QApplication, QLabel

    from fpdb_3_legacy import Configuration as Conf
    from fpdb_3_legacy import ModernHudPreferences as M
    from fpdb_3_legacy import pt4hud

    QApplication.instance() or QApplication([])
    cfg = tmp_path / "HUD_config.xml"
    shutil.copy(EXAMPLE, cfg)
    c = Conf.Config(file=str(cfg))
    summary = pt4hud.import_to_config(FIXTURE, c)
    c.save()
    c.reload()

    dlg = M.ModernHudPreferences(c, None)
    dlg.popup_windows[summary["popup"]]["class"] = "default"  # simulate corruption
    ci = dlg.popup_combo.findText(summary["popup"])
    dlg.popup_combo.setCurrentIndex(ci)
    dlg.on_popup_selected(ci)

    labels = {w.text() for w in dlg.popup_preview.findChildren(QLabel)}
    assert {"Push Nash", "Call Nash"} <= labels      # chart still drawn via source
    assert "RangeChartPopup" in [dlg.popup_class_combo.itemText(i)
                                 for i in range(dlg.popup_class_combo.count())]
    assert not dlg.popup_stats_list.isVisibleTo(dlg)  # redundant list hidden


@pytest.mark.skipif(not (os.path.exists(FIXTURE) and os.path.exists(EXAMPLE)), reason="fixtures missing")
def test_import_writes_popup_groups_as_blockpopups(tmp_path):
    """PT4 popup groups import as BlockPopup <pu> entries + a JSON grid sidecar."""
    import json

    from fpdb_3_legacy import Configuration as Conf
    from fpdb_3_legacy import pt4hud

    cfg = tmp_path / "HUD_config.xml"
    shutil.copy(EXAMPLE, cfg)
    c = Conf.Config(file=str(cfg))
    summary = pt4hud.import_to_config(FIXTURE, c)
    c.save()
    c.reload()

    assert summary["popup_groups"], "expected imported popup groups"
    block_popups = {n: p for n, p in c.popup_windows.items() if p.pu_class == "BlockPopup"}
    assert block_popups
    one = next(iter(block_popups.values()))
    assert "source" in one.pu_class_params and "group" in one.pu_class_params
    # the JSON sidecar carries the full text/stat grid for each group
    data = json.load(open(one.pu_class_params["source"], encoding="utf-8"))
    groups = {g["name"]: g for g in data["popup_groups"]}
    assert one.pu_class_params["group"] in groups
    grid = groups[one.pu_class_params["group"]]
    assert grid["rows"] >= 1 and grid["cols"] >= 1 and grid["cells"]
    # re-import must not duplicate the BlockPopup entries
    pt4hud.import_to_config(FIXTURE, Conf.Config(file=str(cfg)))


@pytest.mark.skipif(not (os.path.exists(FIXTURE) and os.path.exists(EXAMPLE)), reason="fixtures missing")
def test_blockpopup_renders_grid_in_preview(tmp_path):
    """An imported BlockPopup renders its text/stat grid in the popup preview."""
    from PySide6.QtWidgets import QApplication, QLabel, QPushButton

    from fpdb_3_legacy import Configuration as Conf
    from fpdb_3_legacy import pt4hud
    from fpdb_3_legacy import ModernHudPreferences as M

    QApplication.instance() or QApplication([])
    cfg = tmp_path / "HUD_config.xml"
    shutil.copy(EXAMPLE, cfg)
    c = Conf.Config(file=str(cfg))
    pt4hud.import_to_config(FIXTURE, c)
    c.save()
    c.reload()

    dlg = M.ModernHudPreferences(c, None)
    block = next((n for n, p in dlg.popup_windows.items() if p.get("class") == "BlockPopup"), None)
    assert block is not None
    ci = dlg.popup_combo.findText(block)
    dlg.popup_combo.setCurrentIndex(ci)
    dlg.on_popup_selected(ci)

    labels = [w.text() for w in dlg.popup_preview.findChildren(QLabel)]
    assert any(labels)                                    # cells rendered
    assert dlg.popup_canvas.chips                         # WYSIWYG canvas populated
    assert dlg.popup_canvas._host.findChildren(QPushButton)  # row +/- controls like Statistics
    assert "No popup stats configured" not in " ".join(labels)


@pytest.mark.skipif(not (os.path.exists(FIXTURE) and os.path.exists(EXAMPLE)), reason="fixtures missing")
def test_imported_blockpopup_preview_keeps_full_scrollable_extent(tmp_path):
    """The preview frame must keep the full PT4 grid size instead of clipping it."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from fpdb_3_legacy import Configuration as Conf
    from fpdb_3_legacy import ModernHudPreferences as M
    from fpdb_3_legacy import pt4hud

    QApplication.instance() or QApplication([])
    cfg = tmp_path / "HUD_config.xml"
    shutil.copy(EXAMPLE, cfg)
    c = Conf.Config(file=str(cfg))
    pt4hud.import_to_config(FIXTURE, c)
    c.save()
    c.reload()

    dlg = M.ModernHudPreferences(c, None)
    block = next((n for n, p in dlg.popup_windows.items()
                  if p.get("class") == "BlockPopup" and p.get("group") == "Call Nash"), None)
    assert block is not None
    ci = dlg.popup_combo.findText(block)
    dlg.popup_combo.setCurrentIndex(ci)
    dlg.on_popup_selected(ci)

    preview = dlg.popup_preview
    frame = preview.popup_frame
    assert not preview.scroll_area.widgetResizable()
    assert preview.scroll_area.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOn
    assert frame.width() >= frame.minimumWidth() >= 14 * (22 + 22) + 28
    assert frame.height() >= frame.minimumHeight() >= 17 * (22 + 2) + 44


def test_legacy_popup_classes_preview_fill_viewport():
    """default, Multicol and Submenu previews should still render in resizable mode."""
    from PySide6.QtWidgets import QApplication, QLabel

    from fpdb_3_legacy import Configuration as Conf
    from fpdb_3_legacy import ModernHudPreferences as M

    QApplication.instance() or QApplication([])
    c = Conf.Config(file=EXAMPLE)
    dlg = M.ModernHudPreferences(c, None)

    for popup_name, expected_text in [
        ("pophands", "totalprofit"),
        ("default", "playername"),
        ("holdring_main", "> hold_pre"),
    ]:
        ci = dlg.popup_combo.findText(popup_name)
        assert ci >= 0
        dlg.popup_combo.setCurrentIndex(ci)
        dlg.on_popup_selected(ci)

        preview = dlg.popup_preview
        labels = [w.text() for w in preview.popup_frame.findChildren(QLabel)]
        assert preview.scroll_area.widgetResizable()
        assert any(expected_text in text for text in labels)
        assert preview.popup_frame.width() >= preview.scroll_area.viewport().width()
        assert preview.popup_frame.height() >= preview.scroll_area.viewport().height()


def test_build_block_popup_widget_lays_cells_in_grid():
    from PySide6.QtWidgets import QApplication, QGridLayout, QLabel

    from fpdb_3_legacy.BlockPopup import build_block_popup_widget

    QApplication.instance() or QApplication([])
    group = {"name": "SMK", "rows": 2, "cols": 3, "cells": [
        {"kind": "text", "text": "A", "row": 0, "col": 1, "fg": "#fff", "bg": ""},
        {"kind": "text", "text": "20+", "row": 1, "col": 1, "fg": "#0f0", "bg": "#111"},
        {"kind": "stat", "text": "VPIP", "row": 1, "col": 2, "fg": "", "bg": ""},
    ]}
    w = build_block_popup_widget(group)
    texts = {lab.text() for lab in w.findChildren(QLabel)}
    assert {"SMK", "A", "20+", "VPIP"} <= texts
    assert w.findChild(QGridLayout) is not None


@pytest.mark.skipif(not (os.path.exists(FIXTURE) and os.path.exists(EXAMPLE)), reason="fixtures missing")
def test_delete_profile_and_popup_persist_through_save(tmp_path):
    """Deleting a HUD profile / popup must remove it from the saved XML, and
    imported chart/block popups must keep their data source across a save."""
    import unittest.mock as mk

    from PySide6.QtWidgets import QApplication, QMessageBox

    from fpdb_3_legacy import Configuration as Conf
    from fpdb_3_legacy import ModernHudPreferences as M
    from fpdb_3_legacy import pt4hud

    QApplication.instance() or QApplication([])
    cfg = tmp_path / "HUD_config.xml"
    shutil.copy(EXAMPLE, cfg)
    c = Conf.Config(file=str(cfg))
    summary = pt4hud.import_to_config(FIXTURE, c)
    c.save()
    c.reload()

    dlg = M.ModernHudPreferences(c, None)
    # Patch every blocking modal, incl. warning/critical: an unpatched error
    # dialog runs a modal exec() that hangs the headless suite instead of failing.
    with mk.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes), \
         mk.patch.object(QMessageBox, "information", lambda *a, **k: None), \
         mk.patch.object(QMessageBox, "warning", lambda *a, **k: None), \
         mk.patch.object(QMessageBox, "critical", lambda *a, **k: None):
        idx = dlg.profile_combo.findText(summary["name"])
        dlg.profile_combo.setCurrentIndex(idx)
        dlg.delete_profile()
        block = next(n for n, p in dlg.popup_windows.items() if p["class"] == "BlockPopup")
        pi = dlg.popup_combo.findText(block)
        dlg.popup_combo.setCurrentIndex(pi)
        dlg.delete_popup()
        dlg.save_changes()

    reread = Conf.Config(file=str(cfg))
    assert summary["name"] not in reread.stat_sets          # HUD deletion persisted
    assert block not in reread.popup_windows                # popup deletion persisted
    # surviving imported popups keep their data source (not wiped by the save)
    survivors = [p for p in reread.popup_windows.values() if p.pu_class in ("BlockPopup", "RangeChartPopup")]
    assert survivors
    assert all(p.pu_class_params.get("source") for p in survivors)


@pytest.mark.skipif(not (os.path.exists(FIXTURE) and os.path.exists(EXAMPLE)), reason="fixtures missing")
def test_popup_item_properties_edit_persists(tmp_path):
    """Selecting a BlockPopup cell loads its Item Properties; editing persists."""
    import json

    from PySide6.QtWidgets import QApplication

    from fpdb_3_legacy import Configuration as Conf
    from fpdb_3_legacy import ModernHudPreferences as M
    from fpdb_3_legacy import pt4hud

    QApplication.instance() or QApplication([])
    cfg = tmp_path / "HUD_config.xml"
    shutil.copy(EXAMPLE, cfg)
    c = Conf.Config(file=str(cfg))
    pt4hud.import_to_config(FIXTURE, c)
    c.save()
    c.reload()

    dlg = M.ModernHudPreferences(c, None)
    block = next(n for n, p in dlg.popup_windows.items() if p.get("class") == "BlockPopup")
    ci = dlg.popup_combo.findText(block)
    dlg.popup_combo.setCurrentIndex(ci)
    dlg.on_popup_selected(ci)

    assert dlg._popup_group is not None
    assert not dlg.pi_props_box.isEnabled()          # nothing selected yet
    dlg.popup_canvas.chips[0].clicked.emit()
    assert dlg.pi_props_box.isEnabled()              # cell selected -> panel active
    assert dlg.pi_text.text()                        # shows the cell text
    assert dlg._popup_item_cell is not None

    dlg.pi_text.setText("ZZZ")
    dlg._popup_item_changed()
    data = json.load(open(dlg._popup_group_source, encoding="utf-8"))
    grp = next(g for g in data["popup_groups"] if g["name"] == dlg._popup_group["name"])
    assert any(cell["text"] == "ZZZ" for cell in grp["cells"])   # edit persisted to JSON


@pytest.mark.skipif(not (os.path.exists(FIXTURE) and os.path.exists(EXAMPLE)), reason="fixtures missing")
def test_pt4_hierarchical_import_metadata(tmp_path):
    from fpdb_3_legacy import Configuration as Conf
    from fpdb_3_legacy import pt4hud

    cfg = tmp_path / "HUD_config.xml"
    shutil.copy(EXAMPLE, cfg)
    c = Conf.Config(file=str(cfg))
    summary = pt4hud.import_to_config(FIXTURE, c)
    c.save()
    c.reload()

    ss = c.stat_sets[summary["name"]]
    assert ss is not None
    assert len(ss.blocks) > 0

    min_stack_block = next((b for b in ss.blocks if b.label == "Min Stack (Table)"), None)
    assert min_stack_block is not None
    assert min_stack_block.scope == "table"
    assert min_stack_block.audience == "everyone"
    assert min_stack_block.id == "min_stack__table"

    villain_block = next((b for b in ss.blocks if b.label == "Villain Info 3H"), None)
    assert villain_block is not None
    assert villain_block.scope == "player"
    assert villain_block.audience == "opponents"
    assert villain_block.id == "villain_info_3h"

    bu_block = next((b for b in ss.blocks if b.label == "BU 3h"), None)
    assert bu_block is not None
    assert bu_block.scope == "player"
    assert bu_block.audience == "everyone"
    assert bu_block.id == "bu_3h"

    assert len(villain_block.hlines) > 0


@pytest.mark.skipif(not (os.path.exists(FIXTURE) and os.path.exists(EXAMPLE)), reason="fixtures missing")
def test_pt4_min_stack_table_has_no_phantom_stat(tmp_path):
    """Min Stack (Table) must import exactly its PT4 items: 5 in total, and a
    single stat (live_min_stack_bb). The trailing colourless GP 2X definition
    record must not become a phantom cell."""
    from fpdb_3_legacy import Configuration as Conf
    from fpdb_3_legacy import pt4hud

    cfg = tmp_path / "HUD_config.xml"
    shutil.copy(EXAMPLE, cfg)
    c = Conf.Config(file=str(cfg))
    summary = pt4hud.import_to_config(FIXTURE, c)
    c.save()
    c.reload()

    block = next(b for b in c.stat_sets[summary["name"]].blocks if b.label == "Min Stack (Table)")
    stat_names = [s.stat_name for s in block.stats.values()]
    assert stat_names == ["live_min_stack_bb"]
    total_items = len(block.stats) + len(block.texts) + len(block.hlines)
    assert total_items == 5, f"expected 5 PT4 items, got {total_items}"
    assert "gp_2x" not in stat_names


@pytest.mark.skipif(not (os.path.exists(FIXTURE) and os.path.exists(EXAMPLE)), reason="fixtures missing")
def test_pt4_villain_tips_align_by_column(tmp_path):
    """Each villain stat's tooltip is the header directly above it in the grid,
    not an index-rotated neighbour (vpip -> VP, not vpip -> AFq)."""
    from fpdb_3_legacy import Configuration as Conf
    from fpdb_3_legacy import pt4hud

    cfg = tmp_path / "HUD_config.xml"
    shutil.copy(EXAMPLE, cfg)
    c = Conf.Config(file=str(cfg))
    summary = pt4hud.import_to_config(FIXTURE, c)
    c.save()
    c.reload()

    block = next(b for b in c.stat_sets[summary["name"]].blocks if b.label == "Villain Info 3H")
    tip_by_stat = {s.stat_name: s.tip for s in block.stats.values()}
    assert tip_by_stat["vpip"] == "VP"
    assert tip_by_stat["pfr"] == "PFR"
    assert tip_by_stat["agg_fact_pct"] == "AFq"
    assert tip_by_stat["squeeze"] == "SQ"


@pytest.mark.skipif(not (os.path.exists(FIXTURE) and os.path.exists(EXAMPLE)), reason="fixtures missing")
def test_pt4_black_on_black_headers_made_legible(tmp_path):
    """PT4 exports the villain VP/PFR/AFq/SQ headers as black-on-black; the
    importer must give them a contrasting (white) foreground so they render."""
    from fpdb_3_legacy import Configuration as Conf
    from fpdb_3_legacy import pt4hud

    cfg = tmp_path / "HUD_config.xml"
    shutil.copy(EXAMPLE, cfg)
    c = Conf.Config(file=str(cfg))
    summary = pt4hud.import_to_config(FIXTURE, c)
    c.save()
    c.reload()

    block = next(b for b in c.stat_sets[summary["name"]].blocks if b.label == "Villain Info 3H")
    header_labels = {"VP", "PFR", "AFq", "SQ"}
    headers = [t for t in block.texts if t.get("label") in header_labels]
    assert headers, "villain column headers not found"
    for t in headers:
        assert t.get("fgcolor", "").lower() != t.get("bgcolor", "").lower()
