"""Declarative menu layout for the main fpdb window.

The menu bar is described here as data (a tuple of ``Menu`` each holding
``MenuItem``s) instead of being built imperatively. This keeps the structure in
one place — easy to reorganise, unit-test and translate — while the main window
turns it into real Qt menus in ``createMenuBar``.

Labels and tips are wrapped in :func:`N_`, a gettext *no-op* marker, so a string
extractor (xgettext/pybabel with ``--keyword=N_``) can collect them. The actual
translation is applied at build time via :func:`translate`, which defers to the
process-wide gettext domain (installed by ``L10n``); until that domain is bound
it returns the text unchanged, so this module is safe to use before i18n is set
up.
"""

from __future__ import annotations

from dataclasses import dataclass

from fpdb_3_legacy.i18n import N_
from fpdb_3_legacy.i18n import gettext as translate

__all__ = ["LANGUAGE_SUBMENU", "THEMES_SUBMENU", "Menu", "MenuItem", "N_", "menu_layout", "translate"]


@dataclass(frozen=True)
class MenuItem:
    """A single menu action bound to a method on the main window."""

    label: str
    handler: str  # name of the method on the main window to call
    shortcut: str | None = None
    tip: str | None = None
    separator_before: bool = False


@dataclass(frozen=True)
class Menu:
    """A top-level menu and the items it contains."""

    title: str
    items: tuple[MenuItem, ...]


# Sentinels used as an item's handler to mark where a dynamically-built submenu
# should be inserted (their content is resolved at runtime by the main window).
THEMES_SUBMENU = "__themes_submenu__"
LANGUAGE_SUBMENU = "__language_submenu__"

# Special language code meaning "follow the operating-system language".
SYSTEM_LANGUAGE = "system"
# Source language of the UI strings: selecting it disables translation.
SOURCE_LANGUAGE = "en"


def language_options(available: list[str], current: str | None) -> list[tuple[str, bool]]:
    """Ordered ``(code, is_current)`` entries for the Language menu.

    ``system`` (follow the OS) comes first, then ``en`` (the untranslated source
    strings — there is no ``en`` catalog), then each installed locale code.
    ``current`` is the configured ``ui_language`` ("system" when unset).
    """
    active = current or SYSTEM_LANGUAGE
    options = [(SYSTEM_LANGUAGE, active == SYSTEM_LANGUAGE), (SOURCE_LANGUAGE, active == SOURCE_LANGUAGE)]
    options.extend((code, code == active) for code in available if code != SOURCE_LANGUAGE)
    return options


def menu_layout() -> tuple[Menu, ...]:
    """Return the menu bar grouped by user intent (File / Import / analysis / DB…)."""
    return (
        Menu(
            N_("File"),
            (
                MenuItem(N_("Preferences"), "dia_advanced_preferences", tip=N_("Edit your preferences")),
                MenuItem(
                    N_("Databases…"),
                    "dia_database_config",
                    tip=N_("Add, edit, test and select the database (SQLite / PostgreSQL / MySQL)"),
                ),
                MenuItem(N_("Quit"), "quit", "Ctrl+Q", N_("Quit the program"), separator_before=True),
            ),
        ),
        Menu(
            N_("Configure"),
            (
                MenuItem(N_("Site Settings"), "dia_site_preferences"),
                MenuItem(N_("Seat Settings"), "dia_site_preferences_seat"),
                MenuItem(N_("HUD Preferences"), "dia_hud_preferences"),
                MenuItem(N_("Manage HUD Sites"), "dia_manage_hud_sites"),
                MenuItem(
                    N_("Auto Note Rules"),
                    "dia_auto_note_rules",
                    tip=N_("Edit automatic player-note rules"),
                    separator_before=True,
                ),
                MenuItem(N_("Import filters"), "dia_import_filters"),
                MenuItem(
                    N_("Import PT4 HUD (.pt4hud)"),
                    "dia_import_pt4hud",
                    tip=N_("Import a PokerTracker 4 HUD layout (stats + range charts)"),
                    separator_before=True,
                ),
                MenuItem(
                    N_("Import PT4 Stats (.pt4stat)"),
                    "dia_import_pt4stat",
                    tip=N_("Import PokerTracker 4 custom statistics as declarative stat descriptors"),
                ),
            ),
        ),
        Menu(
            N_("Import"),
            (
                MenuItem(N_("Bulk Import"), "tab_bulk_import", "Ctrl+B"),
                MenuItem(N_("HUD and Auto Import"), "tab_auto_import", "Ctrl+A"),
            ),
        ),
        Menu(
            N_("Cash"),
            (
                MenuItem(N_("Graphs"), "tabGraphViewer", "Ctrl+G"),
                MenuItem(N_("Ring Player Stats"), "tab_ring_player_stats", "Ctrl+P"),
                MenuItem(N_("Opponents Report"), "tab_opponents_report", "Ctrl+O"),
                MenuItem(N_("Hand Viewer"), "tab_hand_viewer"),
                MenuItem(N_("Session Stats"), "tab_session_stats", "Ctrl+S"),
            ),
        ),
        Menu(
            N_("Tournament"),
            (
                MenuItem(N_("Tourney Graphs"), "tabTourneyGraphViewer"),
                MenuItem(N_("Tourney Stats"), "tab_tourney_player_stats", "Ctrl+T"),
                MenuItem(N_("Tourney Hand Viewer"), "tab_tourney_viewer_stats"),
            ),
        ),
        Menu(
            N_("Database"),
            (
                MenuItem(N_("Statistics"), "dia_database_stats", tip=N_("View database statistics")),
                MenuItem(N_("Create or Recreate Tables"), "dia_recreate_tables"),
                MenuItem(N_("Rebuild HUD Cache"), "dia_recreate_hudcache"),
                MenuItem(N_("Rebuild DB Indexes"), "dia_rebuild_indexes"),
                MenuItem(
                    N_("Dump Database to Textfile"),
                    "dia_dump_db",
                    tip=N_("Export the whole database to a text file (slow)"),
                    separator_before=True,
                ),
            ),
        ),
        Menu(
            N_("Tools"),
            (
                MenuItem(N_("Auto Notes Workbench"), "tab_auto_notes_workbench"),
                MenuItem(N_("Launch SwC HTTP Capture"), "launch_swc_capture"),
                MenuItem(
                    N_("Logger Dev Tool"),
                    "show_logger_dev_tool",
                    tip=N_("Advanced logger manager"),
                    separator_before=True,
                ),
            ),
        ),
        Menu(
            N_("View"),
            (
                MenuItem(N_("Themes"), THEMES_SUBMENU),
                MenuItem(N_("Language"), LANGUAGE_SUBMENU),
            ),
        ),
        Menu(
            N_("Help"),
            (
                MenuItem(N_("Help Tab"), "tab_main_help"),
                MenuItem(N_("Stats Guide"), "tabStatsInfo"),
                MenuItem(N_("Log Messages"), "dia_logs", tip=N_("Log and debug messages")),
                MenuItem(N_("About"), "dia_about", tip=N_("About the program"), separator_before=True),
            ),
        ),
    )
