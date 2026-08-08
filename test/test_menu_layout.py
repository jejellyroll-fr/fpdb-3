#!/usr/bin/env python3
"""Tests for the declarative menu layout (fpdb_3_legacy/menu_layout.py).

These stay lightweight: the layout is plain data, so they never construct the
heavy Qt main window. Handler existence is checked by scanning fpdb.pyw source.
"""

from __future__ import annotations

import ast
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "fpdb_3_legacy")))

import menu_layout

FPDB_PYW = os.path.join(os.path.dirname(__file__), "..", "fpdb_3_legacy", "fpdb.pyw")


def _all_items():
    for menu in menu_layout.menu_layout():
        for item in menu.items:
            yield menu, item


def test_top_level_menus_are_grouped_by_intent():
    titles = [m.title for m in menu_layout.menu_layout()]
    assert titles == [
        "File",
        "Configure",
        "Import",
        "Cash",
        "Tournament",
        "Database",
        "Tools",
        "View",
        "Help",
    ]


def test_no_duplicate_keyboard_shortcuts():
    shortcuts = [item.shortcut for _menu, item in _all_items() if item.shortcut]
    assert len(shortcuts) == len(set(shortcuts)), f"duplicate shortcut(s): {shortcuts}"


def test_every_item_has_a_handler():
    for _menu, item in _all_items():
        assert item.label and item.handler, f"empty label/handler: {item}"


def test_themes_submenu_sentinel_appears_exactly_once():
    sentinels = [item for _m, item in _all_items() if item.handler == menu_layout.THEMES_SUBMENU]
    assert len(sentinels) == 1


def test_all_handlers_are_defined_on_the_main_window():
    """Every referenced handler must exist as a method in fpdb.pyw."""
    with open(FPDB_PYW, encoding="utf-8") as fh:
        source = fh.read()
    defined = set(re.findall(r"def (\w+)\s*\(", source))
    sentinels = {menu_layout.THEMES_SUBMENU, menu_layout.LANGUAGE_SUBMENU}
    for _menu, item in _all_items():
        if item.handler in sentinels:
            continue
        assert item.handler in defined, f"handler '{item.handler}' not defined in fpdb.pyw"


def test_graphing_modules_are_lazy_so_auto_import_does_not_build_the_font_cache():
    """Frozen startup must not import Matplotlib-backed tabs Auto Import does not use."""
    with open(FPDB_PYW, encoding="utf-8") as source_file:
        tree = ast.parse(source_file.read())

    expensive = {
        "GuiGraphViewer",
        "GuiRingPlayerStats",
        "GuiSessionViewer",
        "GuiTourneyGraphViewer",
    }
    eager = {
        alias.name
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module == "fpdb_3_legacy"
        for alias in node.names
    }

    assert eager.isdisjoint(expensive)


def test_view_menu_exposes_themes_and_language_submenus():
    handlers = {item.handler for _m, item in _all_items()}
    assert menu_layout.THEMES_SUBMENU in handlers
    assert menu_layout.LANGUAGE_SUBMENU in handlers


def test_language_options_puts_system_and_english_first_and_marks_current():
    options = menu_layout.language_options(["fr_FR", "es_ES", "de_DE"], "fr_FR")
    assert options[0] == (menu_layout.SYSTEM_LANGUAGE, False)  # System default is always first
    assert options[1] == (menu_layout.SOURCE_LANGUAGE, False)  # English (source) always offered
    assert ("fr_FR", True) in options  # the configured language is marked current
    assert [code for code, _checked in options] == ["system", "en", "fr_FR", "es_ES", "de_DE"]


def test_language_options_marks_english_when_selected():
    options = menu_layout.language_options(["fr_FR"], "en")
    assert (menu_layout.SOURCE_LANGUAGE, True) in options
    assert ("fr_FR", False) in options


def test_language_options_defaults_to_system_when_unset():
    for current in (None, "", "system"):
        options = menu_layout.language_options(["fr_FR"], current)
        assert options[0] == (menu_layout.SYSTEM_LANGUAGE, True)
        assert ("fr_FR", False) in options


def test_language_options_does_not_duplicate_english_from_available():
    codes = [code for code, _c in menu_layout.language_options(["en", "fr_FR"], "system")]
    assert codes.count("en") == 1  # en is the fixed source entry, not repeated


def test_translate_is_identity_without_a_bound_domain():
    # No fpdb gettext domain is installed in the test process.
    assert menu_layout.translate("Bulk Import") == "Bulk Import"


def test_new_database_panel_is_reachable_from_the_menu():
    """Regression: the multi-backend Databases panel must stay in the menu."""
    handlers = {item.handler for _m, item in _all_items()}
    assert "dia_database_config" in handlers


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
