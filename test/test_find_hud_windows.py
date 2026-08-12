"""Naming the process that draws over a poker table.

Five rounds of a duplicate-HUD investigation went into fpdb's own code before
anyone asked the window server who owned the extra blocks. It answered in one
call: PokerTracker 4, running its own HUD over the same tables. Nothing in
fpdb could have found that, because fpdb can only enumerate its own windows.

The tool exists so the next person asks the cheap question first. These cover
its logic against window lists supplied directly, so they run anywhere --
Quartz is only needed to fetch the real list.
"""

from __future__ import annotations

import io
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools.find_hud_windows import (
    Window,
    group_by_process,
    overlays_on,
    poker_tables,
)


def window(pid=1, owner="Winamax", name="", x=0.0, y=0.0, width=100.0, height=100.0, layer=0) -> Window:
    return Window(pid=pid, owner=owner, name=name, x=x, y=y, width=width, height=height, layer=layer)


TABLE = window(pid=100, owner="Winamax", name="Winamax Colorado 1", x=755, y=33, width=757, height=592)


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("other", "overlapping"),
    [
        (window(x=800, y=100, width=200, height=60), True),  # a stat block on the felt
        (window(x=755, y=33, width=1, height=1), True),  # touching the top-left corner
        (window(x=1512, y=33, width=100, height=100), False),  # just past the right edge
        (window(x=755, y=625, width=100, height=100), False),  # just past the bottom edge
        (window(x=0, y=0, width=100, height=100), False),  # another screen corner
    ],
)
def test_overlap_is_a_rectangle_intersection(other, overlapping) -> None:
    assert TABLE.overlaps(other) is overlapping
    assert other.overlaps(TABLE) is overlapping


# ---------------------------------------------------------------------------
# Finding the tables
# ---------------------------------------------------------------------------


def test_a_table_is_found_by_the_site_in_its_owner_or_title() -> None:
    by_owner = window(owner="Winamax", name="", width=757, height=592)
    by_title = window(owner="Python", name="Winamax Colorado 2", width=757, height=592)
    unrelated = window(owner="Finder", name="Downloads", width=757, height=592)

    found = poker_tables([by_owner, by_title, unrelated], "Winamax")

    assert found == [by_owner, by_title]


def test_the_search_is_case_insensitive() -> None:
    assert poker_tables([window(owner="WINAMAX", width=10, height=10)], "winamax")


def test_an_overlay_is_not_mistaken_for_a_table() -> None:
    """HUD windows float above the ordinary layer; tables sit on it."""
    overlay = window(owner="Winamax", name="Winamax Colorado 1", layer=3, width=200, height=60)

    assert poker_tables([overlay], "Winamax") == []


def test_a_window_with_no_area_is_not_a_table() -> None:
    assert poker_tables([window(owner="Winamax", width=0, height=0)], "Winamax") == []


# ---------------------------------------------------------------------------
# Finding what sits on top
# ---------------------------------------------------------------------------


def test_a_small_window_from_another_process_is_an_overlay() -> None:
    """This is the shape of the answer: PokerTracker's blocks over a Winamax table."""
    block = window(pid=1342, owner="PokerTracker 4", x=800, y=100, width=200, height=60, layer=3)

    assert overlays_on(TABLE, [TABLE, block]) == [block]


def test_the_client_s_own_windows_are_not_overlays() -> None:
    """The table draws its own buttons and chips on itself."""
    own = window(pid=TABLE.pid, owner="Winamax", x=800, y=100, width=200, height=60)

    assert overlays_on(TABLE, [TABLE, own]) == []


def test_a_window_as_large_as_the_table_is_not_an_overlay() -> None:
    """A browser behind the table overlaps it without drawing stat blocks."""
    big = window(pid=999, owner="Safari", x=700, y=0, width=1400, height=900)

    assert overlays_on(TABLE, [TABLE, big]) == []


def test_a_window_beside_the_table_is_not_an_overlay() -> None:
    beside = window(pid=999, owner="Terminal", x=0, y=0, width=200, height=60)

    assert overlays_on(TABLE, [TABLE, beside]) == []


def test_overlays_are_counted_per_process() -> None:
    blocks = [window(pid=1342, owner="PokerTracker 4", x=800 + i * 10, y=100, width=50, height=30) for i in range(6)]
    other = window(pid=555, owner="Python", x=900, y=200, width=50, height=30)

    counts = group_by_process([*blocks, other])

    assert counts == {(1342, "PokerTracker 4"): 6, (555, "Python"): 1}


# ---------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------


def run_report(windows, site="Winamax", monkeypatch=None):
    import tools.find_hud_windows as tool

    monkeypatch.setattr(tool, "on_screen_windows", lambda: windows)
    out = io.StringIO()
    status = tool.report(site, out=out)
    return status, out.getvalue()


def test_a_foreign_hud_is_named_with_its_pid(monkeypatch) -> None:
    """The whole point: a pid the reader can kill."""
    blocks = [window(pid=1342, owner="PokerTracker 4", x=800 + i * 10, y=100, width=50, height=30) for i in range(6)]

    status, text = run_report([TABLE, *blocks], monkeypatch=monkeypatch)

    assert "pid   1342  PokerTracker 4  6 window(s)" in text
    assert "kill <pid>" in text
    assert status == 1


def test_a_clean_table_says_so(monkeypatch) -> None:
    status, text = run_report([TABLE], monkeypatch=monkeypatch)

    assert "Nothing is drawing over them." in text
    assert status == 0


def test_no_tables_open_is_not_a_finding(monkeypatch) -> None:
    status, text = run_report([window(owner="Finder", width=500, height=500)], monkeypatch=monkeypatch)

    assert "No Winamax table windows are open" in text
    assert status == 0


def test_this_process_is_not_reported_as_a_stranger(monkeypatch) -> None:
    """Running the tool from inside fpdb must not accuse fpdb of itself."""
    mine = window(pid=os.getpid(), owner="Python", x=800, y=100, width=50, height=30)

    status, text = run_report([TABLE, mine], monkeypatch=monkeypatch)

    assert "(this process)" in text
    assert "kill <pid>" not in text
    assert status == 0


def test_the_tables_themselves_are_listed(monkeypatch) -> None:
    """Their geometry is what makes an overlay report checkable by eye."""
    _status, text = run_report([TABLE], monkeypatch=monkeypatch)

    assert "757x592 at (755,33)" in text
    assert "Winamax Colorado 1" in text


def test_an_unsupported_platform_explains_itself(monkeypatch, capsys) -> None:
    import tools.find_hud_windows as tool

    def refuse() -> None:
        msg = "this tool needs macOS and the Quartz bindings (pyobjc)"
        raise RuntimeError(msg)

    monkeypatch.setattr(tool, "on_screen_windows", refuse)

    assert tool.main([]) == 2
    assert "needs macOS" in capsys.readouterr().err
