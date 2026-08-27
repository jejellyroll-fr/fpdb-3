"""A Winamax HUD must not attach to the client's lobby window.

The Windows detector broadens its search to the bare client name, because the
precise title regex does not always match a Winamax table. That broadening
qualifies every window of the client, and the lobby's title is exactly
"Winamax" -- it carries none of the bad words either. When the hero's tables
closed and a hand of one of them was imported a moment later, the lobby was the
window the HUD attached to and drew its blocks over, scaled to a 1095x703
window, for as long as the lobby stayed open:

    HUD attach: table='Colorado 1' hwnd=264154 title='Winamax' geometry=(80,98 1095x703)
    HUD created: ... generation=4 table='Colorado 1' window_id=264154 ... overlays=ClassicHud:526644,...

These pin down which Winamax windows may be chosen, without narrowing the
broadened search itself: a table window always names its table, a lobby never
does.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace  # noqa: E402
from unittest.mock import MagicMock  # noqa: E402

from fpdb.infrastructure.platform import TableGeometry, TableInfo  # noqa: E402
from fpdb_3_legacy import WinTables  # noqa: E402

TABLE_GEOMETRY = TableGeometry(x=1131, y=107, width=691, height=519)
LOBBY_GEOMETRY = TableGeometry(x=80, y=98, width=1095, height=703)

LOBBY = TableInfo(window_id=264154, title="Winamax", geometry=LOBBY_GEOMETRY)
TABLE = TableInfo(window_id=1116098, title="Winamax Colorado 1", geometry=TABLE_GEOMETRY)


def _table(name: str, table_type: str = "cash", **attrs) -> WinTables.Table:
    """A Table carrying only what window selection reads."""
    t = object.__new__(WinTables.Table)
    t.site = "Winamax"
    t.name = name
    t.type = table_type
    t.number = None
    t.title = ""
    t.gdkhandle = None
    t._resolved_window = None
    t._table_geometry = None
    t._detector = MagicMock()
    t.search_string = r"Winamax\s+.*Colorado\ 1"
    for key, value in attrs.items():
        setattr(t, key, value)
    return t


def test_the_lobby_is_not_this_table() -> None:
    assert _table("Colorado 1")._select_window([LOBBY], "Winamax") is None


def test_the_table_is_chosen_from_among_the_client_windows() -> None:
    chosen = _table("Colorado 1")._select_window([LOBBY, TABLE], "Winamax")
    assert chosen is TABLE


def test_a_fast_fold_key_still_matches_the_pool_window() -> None:
    """Fast-Fold tables are keyed "<pool> #<hwnd>"; the title only has the pool."""
    chosen = _table("Colorado 1 #1116098")._select_window([LOBBY, TABLE], "Winamax")
    assert chosen is TABLE


def test_another_table_of_the_client_is_not_taken() -> None:
    other = TableInfo(window_id=394054, title="Winamax Colorado 2", geometry=TABLE_GEOMETRY)
    assert _table("Colorado 1")._select_window([LOBBY, other], "Winamax") is None


def test_a_tournament_table_keeps_its_own_check() -> None:
    tour = _table("22846014 - 3", table_type="tour", tournament=22846014, table=3)
    right = TableInfo(window_id=1, title="Winamax 22846014 - Table #03", geometry=TABLE_GEOMETRY)
    wrong = TableInfo(window_id=2, title="Winamax 22846014 - Table #04", geometry=TABLE_GEOMETRY)
    assert tour._select_window([LOBBY, wrong, right], "Winamax") is right


def test_the_client_drawing_a_non_breaking_space_still_matches() -> None:
    """Losing a table's HUD over a space would be worse than the bug being fixed."""
    drawn = TableInfo(window_id=3, title="Winamax\xa0Colorado\xa01", geometry=TABLE_GEOMETRY)
    assert _table("Colorado 1")._select_window([LOBBY, drawn], "Winamax") is drawn


def test_a_table_with_no_name_is_still_allowed_through() -> None:
    """Nothing to check against: refuse to prove the window wrong, as before."""
    assert _table("")._select_window([TABLE], "Winamax") is TABLE


def test_no_window_is_found_when_only_the_lobby_is_open() -> None:
    """The end of the story: no window, so no HUD is built at all."""
    t = _table("Colorado 1")
    t._detector.find_tables.return_value = [LOBBY]

    t.find_table_parameters()

    assert t.number is None
    assert t._table_geometry is None


def test_the_pre_resolved_window_path_is_untouched() -> None:
    """A window resolved from the client log is already known to be a table."""
    t = _table("Colorado 1")
    t._resolved_window = SimpleNamespace(window_id=1116098, title="Winamax Colorado 1")
    t._detector.get_window_geometry.return_value = TABLE_GEOMETRY

    t.find_table_parameters()

    assert t.number == 1116098
    t._detector.find_tables.assert_not_called()
