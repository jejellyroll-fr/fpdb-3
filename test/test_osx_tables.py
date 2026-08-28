"""The macOS table window, as the HUD attaches its overlays to it.

``OSXTables.Table`` is what turns a search string into a native window id, and
every Fast-Fold overlay is positioned against the geometry it reports. It sat
at 15% covered because it imports AppKit at module scope and asks a platform
detector for real windows.

Both are substitutable: the detector is already an injected abstraction shared
with the Windows implementation, and AppKit is only needed by ``topify``. So
this covers the whole class on any platform -- which is the point, since the
Windows and Linux table classes will be written against the same detector
contract and must not be able to change what macOS asks of it.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest


@pytest.fixture(scope="module")
def osx_tables():
    """Import OSXTables with AppKit stood in for, and hand back the module."""
    saved = {name: sys.modules.get(name) for name in ("AppKit", "fpdb_3_legacy.OSXTables")}
    appkit = sys.modules.get("AppKit")
    if appkit is None:
        appkit = types.ModuleType("AppKit")
        appkit.NSView = MagicMock()
        appkit.NSWindowAbove = 1
        sys.modules["AppKit"] = appkit
    try:
        from fpdb_3_legacy import OSXTables

        yield OSXTables
    finally:
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def geometry(x=10, y=33, width=757, height=592):
    return types.SimpleNamespace(x=x, y=y, width=width, height=height)


def found_window(title="Winamax Bucarest 3", window_id=61825, geom=None, process="Winamax"):
    return types.SimpleNamespace(
        title=title,
        window_id=window_id,
        geometry=geom or geometry(),
        process_name=process,
    )


def make_table(osx_tables, monkeypatch, detector, **kwargs):
    """Build a Table without running Table_Window's own constructor.

    ``Table_Window.__init__`` reaches for configuration, sites and a search
    string; none of that is what this module does, and standing it in keeps
    each test about the macOS window itself.
    """
    monkeypatch.setattr(osx_tables, "get_table_detector", lambda: detector)
    monkeypatch.setattr(osx_tables.Table_Window, "__init__", lambda self, *a, **k: None)
    table = osx_tables.Table(**kwargs)
    table.search_string = kwargs.get("search_string", "Winamax Bucarest 3")
    table.title = None
    table.check_bad_words = lambda title: False
    return table


# ---------------------------------------------------------------------------
# Resolving the window
# ---------------------------------------------------------------------------


def test_a_matching_window_becomes_the_table(osx_tables, monkeypatch) -> None:
    detector = MagicMock()
    detector.find_tables.return_value = [found_window()]
    table = make_table(osx_tables, monkeypatch, detector)

    assert table.find_table_parameters() == "Winamax Bucarest 3"
    assert table.number == 61825


def test_a_window_id_arriving_as_text_is_still_usable(osx_tables, monkeypatch) -> None:
    """Detectors differ on the type; the HUD needs an int to attach to."""
    detector = MagicMock()
    detector.find_tables.return_value = [found_window(window_id="61825")]
    table = make_table(osx_tables, monkeypatch, detector)

    table.find_table_parameters()

    assert table.number == 61825


def test_a_window_with_a_bad_word_in_its_title_is_refused(osx_tables, monkeypatch) -> None:
    """The lobby and the replayer carry the site's name too."""
    detector = MagicMock()
    detector.find_tables.return_value = [found_window(title="Winamax Lobby"), found_window()]
    table = make_table(osx_tables, monkeypatch, detector)
    table.check_bad_words = lambda title: "Lobby" in title

    assert table.find_table_parameters() == "Winamax Bucarest 3"


def test_no_match_reports_the_windows_that_were_open(osx_tables, monkeypatch, caplog) -> None:
    """A wrong search string and an absent table look identical without this."""
    detector = MagicMock()
    detector.find_tables.side_effect = [[], [found_window(title="Winamax Lobby"), found_window(title="")]]
    table = make_table(osx_tables, monkeypatch, detector)

    with caplog.at_level("ERROR"):
        assert table.find_table_parameters() is None

    messages = " ".join(record.getMessage() for record in caplog.records)
    assert "no match found" in messages
    assert "Winamax Lobby" in messages


def test_the_window_listing_is_best_effort(osx_tables, monkeypatch, caplog) -> None:
    """Screen Recording may be denied; the failure to detect is the real news."""
    detector = MagicMock()
    detector.find_tables.side_effect = [[], RuntimeError("screen recording denied")]
    table = make_table(osx_tables, monkeypatch, detector)

    with caplog.at_level("ERROR"):
        assert table.find_table_parameters() is None

    assert "Could not list open windows" in " ".join(r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------------------
# Reusing the window Fast-Fold already resolved
# ---------------------------------------------------------------------------


def test_a_pre_resolved_window_skips_the_scan(osx_tables, monkeypatch) -> None:
    """Fast-Fold resolves the window at hand-start.

    Scanning again can answer differently while TCC is changing, which is how
    a HUD ends up attached to the wrong table of a pool.
    """
    detector = MagicMock()
    resolved = types.SimpleNamespace(window_id=61825, title="Winamax Bucarest 3")
    table = make_table(osx_tables, monkeypatch, detector, resolved_window=resolved)

    assert table.find_table_parameters() == "Winamax Bucarest 3"
    assert table.number == 61825
    detector.find_tables.assert_not_called()


@pytest.mark.parametrize(
    "resolved",
    [
        types.SimpleNamespace(window_id=None, title="Winamax Bucarest 3"),
        types.SimpleNamespace(window_id="not-a-number", title="Winamax Bucarest 3"),
        types.SimpleNamespace(title="Winamax Bucarest 3"),
        types.SimpleNamespace(window_id=0, title="Winamax Bucarest 3"),
        types.SimpleNamespace(window_id=61825, title=""),
    ],
    ids=["no-id", "id-not-a-number", "id-missing", "id-zero", "no-title"],
)
def test_an_unusable_pre_resolved_window_falls_back_to_the_scan(osx_tables, monkeypatch, resolved) -> None:
    """Half an answer is worse than none; the scan is still there."""
    detector = MagicMock()
    detector.find_tables.return_value = [found_window()]
    table = make_table(osx_tables, monkeypatch, detector, resolved_window=resolved)

    assert table.find_table_parameters() == "Winamax Bucarest 3"
    detector.find_tables.assert_called_once()


def test_a_pre_resolved_window_with_a_bad_word_falls_back(osx_tables, monkeypatch) -> None:
    """The shortcut must not bypass the check the scan applies."""
    detector = MagicMock()
    detector.find_tables.return_value = [found_window()]
    resolved = types.SimpleNamespace(window_id=99, title="Winamax Lobby")
    table = make_table(osx_tables, monkeypatch, detector, resolved_window=resolved)
    table.check_bad_words = lambda title: "Lobby" in title

    assert table.find_table_parameters() == "Winamax Bucarest 3"
    assert table.number == 61825


# ---------------------------------------------------------------------------
# Geometry, which every overlay is positioned against
# ---------------------------------------------------------------------------


def test_geometry_comes_back_as_plain_integers(osx_tables, monkeypatch) -> None:
    """Overlay placement is integer pixels; a float here misplaces every block."""
    detector = MagicMock()
    detector.is_window_visible.return_value = True
    detector.get_window_geometry.return_value = geometry(10.6, 33.2, 757.9, 592.4)
    table = make_table(osx_tables, monkeypatch, detector)
    table.number = 61825

    assert table.get_geometry() == {"x": 10, "y": 33, "width": 757, "height": 592}


def test_a_table_with_no_window_has_no_geometry(osx_tables, monkeypatch) -> None:
    table = make_table(osx_tables, monkeypatch, MagicMock())
    table.number = None

    assert table.get_geometry() is None


def test_a_closed_window_has_no_geometry(osx_tables, monkeypatch) -> None:
    """Overlays must come down with the table, not follow a dead window id."""
    detector = MagicMock()
    detector.is_window_visible.return_value = False
    table = make_table(osx_tables, monkeypatch, detector)
    table.number = 61825

    assert table.get_geometry() is None
    detector.get_window_geometry.assert_not_called()


def test_a_window_that_will_not_report_its_geometry_yields_none(osx_tables, monkeypatch) -> None:
    detector = MagicMock()
    detector.is_window_visible.return_value = True
    detector.get_window_geometry.return_value = None
    table = make_table(osx_tables, monkeypatch, detector)
    table.number = 61825

    assert table.get_geometry() is None


# ---------------------------------------------------------------------------
# Title
# ---------------------------------------------------------------------------


def test_the_title_is_read_back_from_the_window(osx_tables, monkeypatch) -> None:
    """The client renames its windows, so it is re-read rather than cached."""
    detector = MagicMock()
    detector.get_window_title.return_value = "Winamax Bucarest 3"
    table = make_table(osx_tables, monkeypatch, detector)
    table.number = 61825

    assert table.get_window_title() == "Winamax Bucarest 3"


def test_a_table_with_no_window_has_no_title(osx_tables, monkeypatch) -> None:
    table = make_table(osx_tables, monkeypatch, MagicMock())
    table.number = None

    assert table.get_window_title() is None


# ---------------------------------------------------------------------------
# Raising the overlay above the table
# ---------------------------------------------------------------------------


def test_a_visible_overlay_is_ordered_above_the_table(osx_tables, monkeypatch) -> None:
    """This is what keeps the blocks on top of the felt rather than behind it."""
    ns_view = MagicMock()
    monkeypatch.setattr(osx_tables, "NSView", ns_view)
    table = make_table(osx_tables, monkeypatch, MagicMock())
    table.number = 61825
    window = MagicMock()
    window.effectiveWinId.return_value = 140234
    window.isVisible.return_value = True

    table.topify(window)

    ordered = ns_view.return_value.window.return_value.orderWindow_relativeTo_
    ordered.assert_called_once_with(osx_tables.NSWindowAbove, 61825)


def test_a_hidden_overlay_is_left_alone(osx_tables, monkeypatch) -> None:
    """Ordering a hidden window above the table would show it."""
    ns_view = MagicMock()
    monkeypatch.setattr(osx_tables, "NSView", ns_view)
    table = make_table(osx_tables, monkeypatch, MagicMock())
    table.number = 61825
    window = MagicMock()
    window.effectiveWinId.return_value = 140234
    window.isVisible.return_value = False

    table.topify(window)

    ns_view.return_value.window.return_value.orderWindow_relativeTo_.assert_not_called()


def test_an_overlay_with_no_table_is_not_ordered(osx_tables, monkeypatch) -> None:
    ns_view = MagicMock()
    monkeypatch.setattr(osx_tables, "NSView", ns_view)
    table = make_table(osx_tables, monkeypatch, MagicMock())
    table.number = None
    window = MagicMock()

    table.topify(window)

    ns_view.assert_not_called()
    window.effectiveWinId.assert_not_called()
