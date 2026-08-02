"""Unit tests for the legacy ``TableWindow.Table_Window`` base class.

``Table_Window`` holds the platform-independent window lifecycle logic shared
by the X/OSX/Windows ``Table`` subclasses: constructor plumbing for tournament
vs cash tables, game detection from the window title, table-number extraction,
geometry change detection, and the periodic ``check_*`` pollers that drive the
HUD.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import Mock, patch

import pytest

pytestmark = pytest.mark.qt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Light Qt stubs so the module imports without a real display.
sys.modules.setdefault("PySide6", Mock())
sys.modules.setdefault("PySide6.QtCore", Mock())
sys.modules.setdefault("PySide6.QtGui", Mock())
sys.modules.setdefault("PySide6.QtWidgets", Mock())

from fpdb_3_legacy.TableWindow import (  # noqa: E402
    Table_Window,
    bad_words,
    limit_game_names,
    nlpl_game_names,
)


def make_config() -> Mock:
    return Mock(hhcs={"PokerStars": Mock(converter=Mock())})


class _Bare:
    """Minimal stand-in with the attributes the base methods touch."""

    def __init__(self) -> None:
        self.title = ""
        self.name = ""
        self.type = ""
        self.tournament = None
        self.table = None
        self.search_string = ""
        self.tableno_re = ""
        self.width = 0
        self.height = 0
        self.x = 0
        self.y = 0
        self.oldx = 0
        self.oldy = 0
        self.number = None
        self.gdkhandle = None
        self.game = False


def _bare(attrs: dict | None = None) -> _Bare:
    obj = _Bare()
    if attrs:
        for k, v in attrs.items():
            setattr(obj, k, v)
    return obj


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------


def test_constructor_cash_table() -> None:
    config = make_config()
    with patch("fpdb_3_legacy.TableWindow.getTableTitleRe", return_value="My Table"):
        with patch("fpdb_3_legacy.TableWindow.sleep"):
            with patch.object(Table_Window, "get_geometry", return_value=None):
                tw = _construct(config, "PokerStars", table_name="My Table")
    assert tw.name == "My Table"
    assert tw.type == "cash"
    assert tw.tournament is None
    assert tw.search_string == "My Table"
    assert tw.game is False


def test_constructor_tournament() -> None:
    config = make_config()
    with patch("fpdb_3_legacy.TableWindow.getTableTitleRe", return_value="Tour 5"):
        with patch("fpdb_3_legacy.TableWindow.getTableNoRe", return_value=r"#(\d+)"):
            with patch("fpdb_3_legacy.TableWindow.sleep"):
                with patch.object(Table_Window, "get_geometry", return_value=None):
                    tw = _construct(config, "PokerStars", tournament="123", table_number="4", tourney_name="T")
    assert tw.type == "tour"
    assert tw.tournament == 123
    assert tw.table == 4
    assert tw.name == "123 - 4"
    assert tw.tableno_re == r"#(\d+)"


def test_constructor_tournament_table_number_fallback() -> None:
    # "Twister 0.25€, 1091614818" style table_number: digits are extracted.
    config = make_config()
    with patch("fpdb_3_legacy.TableWindow.getTableTitleRe", return_value="Tour 5"):
        with patch("fpdb_3_legacy.TableWindow.getTableNoRe", return_value="x"):
            with patch("fpdb_3_legacy.TableWindow.sleep"):
                with patch.object(Table_Window, "get_geometry", return_value=None):
                    tw = _construct(config, "PokerStars", tournament="5", table_number="Twister 0.25, 1091614818")
    assert tw.table == 1091614818


def test_constructor_tournament_table_number_undecodable() -> None:
    # No trailing digits: fall back to the tournament number.
    config = make_config()
    with patch("fpdb_3_legacy.TableWindow.getTableTitleRe", return_value="Tour 5"):
        with patch("fpdb_3_legacy.TableWindow.getTableNoRe", return_value="x"):
            with patch("fpdb_3_legacy.TableWindow.sleep"):
                with patch.object(Table_Window, "get_geometry", return_value=None):
                    tw = _construct(config, "PokerStars", tournament="7", table_number="no-digits")
    assert tw.table == 7


def test_constructor_decodes_bytes() -> None:
    config = make_config()
    with patch("fpdb_3_legacy.TableWindow.getTableTitleRe", return_value="Table"):
        with patch("fpdb_3_legacy.TableWindow.getTableNoRe", return_value="x"):
            with patch("fpdb_3_legacy.TableWindow.sleep"):
                with patch.object(Table_Window, "get_geometry", return_value=None):
                    tw = _construct(config, "PokerStars", tournament=b"5", table_number=b"3")
    assert tw.tournament == 5
    assert tw.table == 3


def test_constructor_cash_table_name_bytes() -> None:
    # table_name arriving as bytes is decoded to str in the cash path.
    config = make_config()
    with patch("fpdb_3_legacy.TableWindow.getTableTitleRe", return_value="Table"):
        with patch("fpdb_3_legacy.TableWindow.sleep"):
            with patch.object(Table_Window, "get_geometry", return_value=None):
                tw = _construct(config, "PokerStars", table_name=b"My Table")
    assert tw.type == "cash"
    assert tw.name == "My Table"


def test_constructor_window_found_but_no_geometry() -> None:
    # find_table_parameters sets self.number; geometry lookup then fails.
    config = make_config()
    with patch("fpdb_3_legacy.TableWindow.getTableTitleRe", return_value="Table"):
        with patch("fpdb_3_legacy.TableWindow.sleep"):
            with patch.object(Table_Window, "find_table_parameters", new=lambda self_: setattr(self_, "number", 5)):
                with patch.object(Table_Window, "get_geometry", return_value=None):
                    tw = Table_Window(config, "PokerStars", table_name="T")
    assert tw.number == 5


def test_constructor_no_table_no_tournament() -> None:
    config = make_config()
    with patch("fpdb_3_legacy.TableWindow.sleep"):
        tw = _construct(config, "PokerStars")
    assert tw.type == ""
    assert tw.number is None


def test_constructor_no_geometry_returns_early() -> None:
    config = make_config()
    with patch("fpdb_3_legacy.TableWindow.getTableTitleRe", return_value="Table"):
        with patch("fpdb_3_legacy.TableWindow.sleep"):
            with patch.object(Table_Window, "find_table_parameters"):
                with patch.object(Table_Window, "get_geometry", return_value=None):
                    tw = _construct(config, "PokerStars", table_name="T")
    assert tw.width == 0


def test_constructor_sets_geometry_and_game() -> None:
    config = make_config()
    with patch("fpdb_3_legacy.TableWindow.getTableTitleRe", return_value="Table"):
        with patch("fpdb_3_legacy.TableWindow.sleep"):
            with patch.object(Table_Window, "find_table_parameters"):
                with patch.object(Table_Window, "get_geometry", return_value={"x": 1, "y": 2, "width": 800, "height": 600}):
                    with patch.object(Table_Window, "get_game", return_value=("nl", "holdem")):
                        tw = _construct(config, "PokerStars", table_name="T")
    assert tw.width == 800
    assert tw.height == 600
    assert tw.x == 1
    assert tw.y == 2
    assert tw.oldx == 1
    assert tw.game == ("nl", "holdem")


def _construct(config, site, **kwargs) -> Table_Window:
    """Construct a Table_Window, stubbing only the platform window lookup."""
    # find_table_parameters is overridden in subclasses; the constructor calls
    # it, so stub it to an inert no-op. get_geometry is left for the caller to
    # patch (tests that need geometry set it explicitly).
    with patch.object(Table_Window, "find_table_parameters"):
        return Table_Window(config, site, **kwargs)


# ---------------------------------------------------------------------------
# __str__
# ---------------------------------------------------------------------------


def test_str_lists_set_attributes() -> None:
    tw = _bare({"number": 42, "site": "PokerStars", "title": "Hello", "width": 800})
    text = str(_to_table_window(tw))
    assert "TableWindow object" in text
    assert "number = 42" in text
    assert "site = PokerStars" in text
    assert "title = Hello" in text
    assert "width = 800" in text


def _to_table_window(bare: _Bare) -> Table_Window:
    """Wrap the bare stand-in into a Table_Window instance for __str__."""
    tw = object.__new__(Table_Window)
    for k, v in vars(bare).items():
        setattr(tw, k, v)
    return tw


# ---------------------------------------------------------------------------
# get_game
# ---------------------------------------------------------------------------


def test_get_game_nl_holdem() -> None:
    tw = _bare({"title": "Table 1 - No Limit Hold'em"})
    assert tw.game is False
    assert _to_table_window(tw).get_game() == ("nl", "holdem")


def test_get_game_limit_omaha_hl() -> None:
    tw = _bare({"title": "Table 2 - Limit Omaha H/L"})
    assert _to_table_window(tw).get_game() == ("fl", "omahahilo")


def test_get_game_unknown_title() -> None:
    tw = _bare({"title": "Table 3 - Unusual Game"})
    assert _to_table_window(tw).get_game() is False


# ---------------------------------------------------------------------------
# get_table_no
# ---------------------------------------------------------------------------


def test_get_table_no_match() -> None:
    tw = _to_table_window(_bare({"tableno_re": r"#(\d+)", "get_window_title": lambda: "Tour #45"}))
    assert tw.get_table_no() == 45


def test_get_table_no_no_match() -> None:
    tw = _to_table_window(_bare({"tableno_re": r"#(\d+)", "get_window_title": lambda: "No number here"}))
    assert tw.get_table_no() is False


def test_get_table_no_title_none() -> None:
    tw = _to_table_window(_bare({"tableno_re": r"#(\d+)", "get_window_title": lambda: None}))
    assert tw.get_table_no() is False


def test_get_table_no_missing_tableno_re() -> None:
    tw = _to_table_window(_bare({"get_window_title": lambda: "Tour #45"}))
    del tw.tableno_re
    assert tw.get_table_no() is False


# ---------------------------------------------------------------------------
# check_table / check_size / check_loc
# ---------------------------------------------------------------------------


def test_check_table_destroyed() -> None:
    tw = _to_table_window(_bare({"get_geometry": lambda: None}))
    assert tw.check_table() == "client_destroyed"


def test_check_table_resized() -> None:
    tw = _to_table_window(_bare({"width": 800, "height": 600, "get_geometry": lambda: {"x": 0, "y": 0, "width": 900, "height": 700}}))
    assert tw.check_table() == "client_resized"
    assert tw.width == 900
    assert tw.height == 700
    assert tw.oldwidth == 800


def test_check_table_moved() -> None:
    tw = _to_table_window(_bare({"x": 0, "y": 0, "width": 800, "height": 600, "get_geometry": lambda: {"x": 5, "y": 7, "width": 800, "height": 600}}))
    assert tw.check_table() == "client_moved"
    assert tw.x == 5
    assert tw.y == 7


def test_check_table_no_change() -> None:
    tw = _to_table_window(_bare({"x": 0, "y": 0, "width": 800, "height": 600, "get_geometry": lambda: {"x": 0, "y": 0, "width": 800, "height": 600}}))
    assert tw.check_table() is False


def test_check_size_destroyed() -> None:
    tw = _to_table_window(_bare({"get_geometry": lambda: None}))
    assert tw.check_size() == "client_destroyed"


def test_check_size_resized() -> None:
    tw = _to_table_window(_bare({"width": 800, "height": 600, "get_geometry": lambda: {"x": 0, "y": 0, "width": 800, "height": 600}}))
    assert tw.check_size() is False
    tw.width = 1000
    assert tw.check_size() == "client_resized"


def test_check_loc_destroyed() -> None:
    tw = _to_table_window(_bare({"get_geometry": lambda: None}))
    assert tw.check_loc() == "client_destroyed"


def test_check_loc_moved() -> None:
    tw = _to_table_window(_bare({"x": 0, "y": 0, "get_geometry": lambda: {"x": 10, "y": 0, "width": 800, "height": 600}}))
    assert tw.check_loc() == "client_moved"
    assert tw.x == 10


def test_check_loc_no_change() -> None:
    tw = _to_table_window(_bare({"x": 0, "y": 0, "get_geometry": lambda: {"x": 0, "y": 0, "width": 800, "height": 600}}))
    assert tw.check_loc() is False


# ---------------------------------------------------------------------------
# has_table_title_changed
# ---------------------------------------------------------------------------


def test_has_table_title_changed() -> None:
    tw = _to_table_window(_bare({"table": 3, "get_table_no": lambda: 45}))
    assert tw.has_table_title_changed(Mock()) is True
    assert tw.table == 45


def test_has_table_title_changed_no_hud() -> None:
    tw = _to_table_window(_bare({"table": 3, "get_table_no": lambda: 45}))
    assert tw.has_table_title_changed(None) is False
    assert tw.table == 45


def test_has_table_title_changed_unchanged() -> None:
    tw = _to_table_window(_bare({"table": 3, "get_table_no": lambda: 3}))
    assert tw.has_table_title_changed(Mock()) is False


def test_has_table_title_changed_no_result() -> None:
    tw = _to_table_window(_bare({"table": 3, "get_table_no": lambda: False}))
    assert tw.has_table_title_changed(Mock()) is False


# ---------------------------------------------------------------------------
# check_bad_words
# ---------------------------------------------------------------------------


def test_check_bad_words() -> None:
    tw = _to_table_window(_bare({}))
    for word in bad_words:
        assert tw.check_bad_words(f"Some {word} window") is True
    assert tw.check_bad_words("A clean table title") is False
    assert tw.check_bad_words("") is False


# ---------------------------------------------------------------------------
# abstract methods
# ---------------------------------------------------------------------------


def test_abstract_methods_raise() -> None:
    tw = _to_table_window(_bare({}))
    with pytest.raises(NotImplementedError):
        tw.find_table_parameters()
    with pytest.raises(NotImplementedError):
        tw.get_geometry()
    with pytest.raises(NotImplementedError):
        tw.get_window_title()


def test_game_name_tables_are_static() -> None:
    assert nlpl_game_names[("nl", "holdem")] == ("No Limit Hold'em",)
    assert limit_game_names[("fl", "razz")] == ("Limit Razz",)
