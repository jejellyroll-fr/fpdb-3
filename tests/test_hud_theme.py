"""The HUD shows the theme chosen in fpdb (#693).

The HUD is a subprocess of fpdb, so the only way a theme reaches it is the
configuration file. These tests go through that file, the real qt_material and a
real QApplication. Every Config is built from a copy of the shipped file, and
custom themes come from a directory of the test's own.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication, QLabel

import fpdb_3_legacy.ThemeManager as theme_module
from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.hud_main_huds import HudMainHudsMixin
from fpdb_3_legacy.ThemeManager import DEFAULT_QT_THEME, ThemeManager

pytestmark = pytest.mark.qt

SHIPPED = Path(__file__).resolve().parents[1] / "HUD_config.xml"
CUSTOM_THEME = "test_emerald.xml"
CUSTOM_ACCENT = "#10b981"
CUSTOM_THEME_XML = f"""<resources>
  <color name="primaryColor">{CUSTOM_ACCENT}</color>
  <color name="primaryLightColor">#34d399</color>
  <color name="secondaryColor">#1e293b</color>
  <color name="secondaryLightColor">#334155</color>
  <color name="secondaryDarkColor">#0f172a</color>
  <color name="primaryTextColor">#f8fafc</color>
  <color name="secondaryTextColor">#cbd5e1</color>
</resources>
"""


@pytest.fixture(scope="module")
def app():
    # Read when the application is created, so nothing lands on a developer's screen.
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def isolated_theme_state(app, tmp_path, monkeypatch):
    """Give each test a new ThemeManager, its own custom themes and a clean application."""
    themes_dir = tmp_path / "themes"
    themes_dir.mkdir()
    (themes_dir / CUSTOM_THEME).write_text(CUSTOM_THEME_XML, encoding="utf-8")
    monkeypatch.setattr(theme_module, "CUSTOM_THEMES_DIR", themes_dir)
    monkeypatch.setattr(ThemeManager, "_instance", None)
    monkeypatch.setattr(ThemeManager, "AVAILABLE_QT_THEMES", None)
    stylesheet = app.styleSheet()
    app.setProperty("fpdb_qt_material_theme", None)
    yield
    app.setStyleSheet(stylesheet)
    app.setProperty("fpdb_qt_material_theme", None)


def _write_theme(path: Path, theme: str) -> None:
    """Change the saved theme the way fpdb's save does: a new file on disk."""
    doc = path.read_text(encoding="utf-8")
    start = doc.index('qt_material_theme="') + len('qt_material_theme="')
    end = doc.index('"', start)
    path.write_text(doc[:start] + theme + doc[end:], encoding="utf-8")


@pytest.fixture
def config_file(tmp_path) -> Path:
    mine = tmp_path / "HUD_config.xml"
    shutil.copy(SHIPPED, mine)
    return mine


def _hud(config_file: Path) -> HudMainHudsMixin:
    """The part of HudMain that follows the configuration, without its windows and database."""
    hud = object.__new__(HudMainHudsMixin)
    hud.config = Config(file=str(config_file))
    hud.hud_dict = {}
    hud._table_stat_set_overrides = {}
    hud._config_fingerprint = hud._read_config_fingerprint()
    hud.init_theme()
    return hud


def _save_theme_as_fpdb_would(config_file: Path, theme: str) -> None:
    _write_theme(config_file, theme)
    # The fingerprint is (mtime, size): make the change visible even within one clock tick.
    stat = config_file.stat()
    os.utime(config_file, (stat.st_atime, stat.st_mtime + 2))


def _shown_theme(app) -> str:
    return app.property("fpdb_qt_material_theme")


def test_the_hud_starts_with_the_saved_builtin_theme(app, config_file) -> None:
    _write_theme(config_file, "dark_teal.xml")

    _hud(config_file)

    assert _shown_theme(app) == "dark_teal.xml"


def test_the_hud_starts_with_a_saved_custom_theme(app, config_file) -> None:
    _write_theme(config_file, CUSTOM_THEME)

    _hud(config_file)

    assert _shown_theme(app) == CUSTOM_THEME
    assert CUSTOM_ACCENT in app.styleSheet().lower()


def test_an_unknown_theme_starts_the_hud_on_the_default(app, config_file) -> None:
    _write_theme(config_file, "no_such_theme.xml")

    _hud(config_file)

    assert _shown_theme(app) == DEFAULT_QT_THEME


def test_a_theme_that_fails_to_render_starts_the_hud_on_the_default(app, config_file) -> None:
    _write_theme(config_file, CUSTOM_THEME)
    real_apply = ThemeManager._apply_theme_to_application

    def fail_on_custom(manager: ThemeManager, theme: str) -> bool:
        if theme == CUSTOM_THEME:
            raise KeyError("a colour qt_material needs")
        return real_apply(manager, theme)

    with patch.object(ThemeManager, "_apply_theme_to_application", fail_on_custom):
        _hud(config_file)

    assert _shown_theme(app) == DEFAULT_QT_THEME


def test_a_theme_saved_in_fpdb_reaches_a_running_hud(app, config_file) -> None:
    _write_theme(config_file, "dark_teal.xml")
    hud = _hud(config_file)

    _save_theme_as_fpdb_would(config_file, CUSTOM_THEME)
    hud.refresh_profiles_from_config()

    assert _shown_theme(app) == CUSTOM_THEME
    assert CUSTOM_ACCENT in app.styleSheet().lower()


def test_a_custom_theme_created_after_the_hud_started_is_found(app, config_file, tmp_path) -> None:
    _write_theme(config_file, "dark_teal.xml")
    hud = _hud(config_file)
    (tmp_path / "themes" / "created_later.xml").write_text(CUSTOM_THEME_XML, encoding="utf-8")

    _save_theme_as_fpdb_would(config_file, "created_later.xml")
    hud.refresh_profiles_from_config()

    assert _shown_theme(app) == "created_later.xml"


def test_an_invalid_theme_keeps_the_one_on_screen(app, config_file) -> None:
    _write_theme(config_file, "dark_teal.xml")
    hud = _hud(config_file)

    _save_theme_as_fpdb_would(config_file, "no_such_theme.xml")
    hud.refresh_profiles_from_config()

    assert _shown_theme(app) == "dark_teal.xml"


def test_a_config_change_that_keeps_the_theme_restyles_nothing(config_file) -> None:
    _write_theme(config_file, "dark_teal.xml")
    hud = _hud(config_file)

    # The HUD's own layout saves change the file too, and must not restyle anything.
    stat = config_file.stat()
    os.utime(config_file, (stat.st_atime, stat.st_mtime + 2))
    with patch.object(ThemeManager, "_apply_theme_to_application") as apply_theme:
        hud.refresh_profiles_from_config()

    apply_theme.assert_not_called()


def test_following_the_theme_never_writes_the_config(config_file) -> None:
    _write_theme(config_file, "dark_teal.xml")
    hud = _hud(config_file)
    _save_theme_as_fpdb_would(config_file, CUSTOM_THEME)
    saved = config_file.read_bytes()

    hud.refresh_profiles_from_config()

    assert config_file.read_bytes() == saved


def test_a_theme_change_leaves_the_open_table_overlays_alone(app, config_file) -> None:
    """Restyling happens in place: the seat windows are neither rebuilt nor recoloured."""
    _write_theme(config_file, "dark_teal.xml")
    hud = _hud(config_file)
    seat_style = "background: #000000; color: #ffffff;"
    seat_label = QLabel("VP 30.0")
    seat_label.setStyleSheet(seat_style)
    seat_label.setGeometry(10, 20, 80, 24)
    seat_label.show()
    aux = MagicMock()
    stat_set = hud.config.stat_sets[next(iter(hud.config.stat_sets))]
    table = MagicMock(
        hud_context=object(),
        aux_windows=[aux],
        supported_games_parameters={"game_stat_set": stat_set},
    )
    # The content the table displays, as recorded where a profile is applied
    # (#741): a MagicMock invents the attribute on access, and the test is that
    # a theme-only change rebuilds nothing.
    table.applied_stat_set_signature = (stat_set.name, hud.config.stat_set_signature(stat_set.name))
    hud.hud_dict["table-a"] = table

    _save_theme_as_fpdb_would(config_file, CUSTOM_THEME)
    with patch.object(hud.config, "get_supported_games_parameters", return_value={"game_stat_set": stat_set}):
        rebuilt = hud.refresh_profiles_from_config()

    assert _shown_theme(app) == CUSTOM_THEME
    assert rebuilt == 0
    aux.destroy.assert_not_called()
    assert seat_label.styleSheet() == seat_style
    assert seat_label.geometry().getRect() == (10, 20, 80, 24)
    seat_label.close()
