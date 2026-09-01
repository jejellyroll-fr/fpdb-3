"""The Windows seat reader, and the line between it and the macOS one.

``WinamaxAXSeatReader`` already carries a Windows branch that reads seats
through UIAutomation instead of the macOS accessibility API. It was entirely
uncovered, which makes it the easiest place to break macOS while building
Windows out: both branches share ``read_window``, ``seats_from_labels`` and
``seat_slots_from_positions``, so a change made for one lands on the other.

These pin the Windows branch down before that work starts: what it asks the
platform detector for, how it chooses between two windows of the same title,
and that every failure it can meet ends as an empty read rather than an
exception on the GUI thread.

The comtypes bindings are stood in for, so this runs on any platform -- which
is the point: a macOS or Linux developer must be able to see a Windows
regression without a Windows machine.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest

from fpdb_3_legacy import winamax_ax_seats as ax
from fpdb_3_legacy.winamax_ax_seats import WinamaxAXSeatReader


@pytest.fixture(autouse=True)
def _fresh_uia_client():
    """Forget the process-wide UIAutomation client between tests.

    It is deliberately built once per process, so without this each test would
    read the previous test's tree.
    """
    ax.reset_windows_uia()
    yield
    ax.reset_windows_uia()


@pytest.fixture
def windows(monkeypatch):
    """Run the body as though this were Windows, bindings and all."""
    monkeypatch.setattr(ax.platform, "system", lambda: "Windows")
    monkeypatch.setitem(sys.modules, "comtypes", MagicMock())
    monkeypatch.setitem(sys.modules, "comtypes.client", MagicMock())


class Rect:
    """A UIAutomation bounding rectangle."""

    def __init__(self, left: float, top: float, right: float = 0.0, bottom: float = 0.0) -> None:
        self.left, self.top, self.right, self.bottom = left, top, right, bottom


class UIAElement:
    """One node of a UIAutomation tree: a name and where it is drawn."""

    def __init__(self, name, rect: Rect | None) -> None:
        self.CurrentName = name
        self.CurrentBoundingRectangle = rect


class UIAArray:
    """What FindAll returns: a length and indexed access."""

    def __init__(self, elements: list[UIAElement]) -> None:
        self._elements = elements
        self.Length = len(elements)

    def GetElement(self, index: int) -> UIAElement:  # noqa: N802 - mirrors the COM API
        return self._elements[index]


def install_uia(monkeypatch, *, window: UIAElement | None, descendants: list[UIAElement] | None) -> MagicMock:
    """Put a UIAutomation tree behind comtypes and return the automation stub."""
    automation = MagicMock()
    automation.ElementFromHandle.return_value = window
    automation.FindAll = MagicMock()
    if window is not None:
        window.FindAll = MagicMock(return_value=None if descendants is None else UIAArray(descendants))

    client = types.ModuleType("comtypes.client")
    client.GetModule = MagicMock(
        return_value=types.SimpleNamespace(CUIAutomation=object(), TreeScope_Subtree=4),
    )
    client.CreateObject = MagicMock(return_value=automation)
    comtypes = types.ModuleType("comtypes")
    comtypes.client = client
    monkeypatch.setitem(sys.modules, "comtypes", comtypes)
    monkeypatch.setitem(sys.modules, "comtypes.client", client)
    return automation


def seated_table(players: dict[str, tuple[float, float]]) -> list[UIAElement]:
    """Each player's name with a stack beneath it, as the client draws them."""
    nodes: list[UIAElement] = []
    for name, (x, y) in players.items():
        nodes.append(UIAElement(name, Rect(x, y)))
        nodes.append(UIAElement("100 BB", Rect(x, y + 20)))
    return nodes


#: Six chairs of a 776x606 table, matching the macOS fixture.
SIX_MAX = {
    "jejellyroll": (350, 520),
    "villain_bl": (60, 470),
    "villain_tl": (50, 150),
    "villain_tc": (350, 90),
    "villain_tr": (650, 150),
    "villain_br": (660, 470),
}

TABLE_WINDOW = Rect(0, 0, 776, 606)


def detected(title: str, window_id, geometry=None) -> MagicMock:
    table = MagicMock()
    table.title = title
    table.window_id = window_id
    table.geometry = geometry
    return table


# ---------------------------------------------------------------------------
# Reading a window by handle
# ---------------------------------------------------------------------------


def test_seats_are_read_clockwise_from_the_hero(windows, monkeypatch) -> None:
    """The same slot contract as macOS: slot 0 is the bottom-centre chair.

    Both readers feed ``seat_slots_from_positions``, so agreeing here is what
    makes a HUD layout mean the same thing on either platform.
    """
    install_uia(monkeypatch, window=UIAElement("table", TABLE_WINDOW), descendants=seated_table(SIX_MAX))

    slots = WinamaxAXSeatReader()._read_window_windows(61825)

    assert slots == {
        0: "jejellyroll",
        1: "villain_bl",
        2: "villain_tl",
        3: "villain_tc",
        4: "villain_tr",
        5: "villain_br",
    }


def test_the_hud_overlay_is_not_read_back_as_players(windows, monkeypatch) -> None:
    """The HUD's own labels sit over the table on Windows too."""
    nodes = seated_table({"jejellyroll": (350, 520)})
    nodes += [UIAElement("jejel.", Rect(340, 430)), UIAElement("100 BB", Rect(340, 450))]
    install_uia(monkeypatch, window=UIAElement("table", TABLE_WINDOW), descendants=nodes)

    assert list(WinamaxAXSeatReader()._read_window_windows(61825).values()) == ["jejellyroll"]


def test_non_breaking_spaces_are_normalised(windows, monkeypatch) -> None:
    """As on macOS, the client separates words with \\xa0."""
    nodes = [UIAElement("Pot total\xa0:\xa01,5\xa0BB", Rect(300, 300)), *seated_table({"jejellyroll": (350, 520)})]
    install_uia(monkeypatch, window=UIAElement("table", TABLE_WINDOW), descendants=nodes)

    assert list(WinamaxAXSeatReader()._read_window_windows(61825).values()) == ["jejellyroll"]


@pytest.mark.parametrize(
    ("name", "rect"),
    [(None, Rect(1, 1)), (12345, Rect(1, 1)), ("x" * 41, Rect(1, 1)), ("jejellyroll", None)],
    ids=["no-name", "not-text", "too-long", "no-rectangle"],
)
def test_a_node_that_cannot_be_a_label_is_dropped(windows, monkeypatch, name, rect) -> None:
    nodes = [UIAElement(name, rect), *seated_table({"jejellyroll": (350, 520)})]
    install_uia(monkeypatch, window=UIAElement("table", TABLE_WINDOW), descendants=nodes)

    assert list(WinamaxAXSeatReader()._read_window_windows(61825).values()) == ["jejellyroll"]


def test_the_walk_stops_once_it_has_more_labels_than_a_table_can_hold(windows, monkeypatch) -> None:
    """A subtree walk on Windows returns everything; it has to be bounded."""
    nodes = [UIAElement(f"label{i}", Rect(i, i)) for i in range(500)]
    window = UIAElement("table", TABLE_WINDOW)
    install_uia(monkeypatch, window=window, descendants=nodes)

    WinamaxAXSeatReader()._read_window_windows(61825)

    assert window.FindAll.call_count == 1  # one walk, not one per label


def test_the_client_is_built_once_for_the_whole_process(windows, monkeypatch) -> None:
    """Reading a window must not re-import comtypes and re-create the COM object.

    Rebuilding it per read is what made a read cost hundreds of milliseconds on
    the GUI thread, six times a hand per table.
    """
    install_uia(monkeypatch, window=UIAElement("table", TABLE_WINDOW), descendants=seated_table(SIX_MAX))
    import comtypes.client as client

    reader = WinamaxAXSeatReader()
    reader._read_window_windows(61825)
    reader._read_window_windows(61825)
    reader._read_window_windows(61825)

    assert client.GetModule.call_count == 1
    assert client.CreateObject.call_count == 1


def test_a_client_that_cannot_be_built_is_not_rebuilt_every_hand(windows, monkeypatch) -> None:
    """No comtypes, no COM, no window station: answer empty and stop trying."""
    client = types.ModuleType("comtypes.client")
    client.GetModule = MagicMock(side_effect=OSError("UIAutomationCore.dll not found"))
    comtypes = types.ModuleType("comtypes")
    comtypes.client = client
    monkeypatch.setitem(sys.modules, "comtypes", comtypes)
    monkeypatch.setitem(sys.modules, "comtypes.client", client)

    reader = WinamaxAXSeatReader()
    assert reader._read_window_windows(61825) == {}
    assert reader._read_window_windows(61825) == {}
    assert client.GetModule.call_count == 1


def test_prewarm_builds_the_client_before_the_first_hand(windows, monkeypatch) -> None:
    """The one-off cost of the bindings belongs to startup, not to a dealt hand."""
    install_uia(monkeypatch, window=UIAElement("table", TABLE_WINDOW), descendants=[])
    monkeypatch.setattr(ax, "is_ax_available", lambda: True)
    import comtypes.client as client

    WinamaxAXSeatReader().prewarm()

    assert client.CreateObject.call_count == 1


def test_prewarm_is_a_no_op_off_windows(monkeypatch) -> None:
    monkeypatch.setattr(ax.platform, "system", lambda: "Linux")
    monkeypatch.setattr(ax, "_windows_uia", MagicMock(side_effect=AssertionError("built off Windows")))

    WinamaxAXSeatReader().prewarm()


def test_a_handle_that_names_no_window_reads_as_empty(windows, monkeypatch) -> None:
    install_uia(monkeypatch, window=None, descendants=[])

    assert WinamaxAXSeatReader()._read_window_windows(61825) == {}


@pytest.mark.parametrize("descendants", [None, []], ids=["find-all-failed", "empty-tree"])
def test_a_window_with_nothing_in_it_reads_as_empty(windows, monkeypatch, descendants) -> None:
    install_uia(monkeypatch, window=UIAElement("table", TABLE_WINDOW), descendants=descendants)

    assert WinamaxAXSeatReader()._read_window_windows(61825) == {}


def test_a_table_drawing_nobody_reads_as_empty(windows, monkeypatch) -> None:
    """Labels with no stack beneath them are not players."""
    install_uia(
        monkeypatch,
        window=UIAElement("table", TABLE_WINDOW),
        descendants=[UIAElement("En attente de joueurs", Rect(300, 700))],
    )

    assert WinamaxAXSeatReader()._read_window_windows(61825) == {}


def test_a_window_without_a_rectangle_reads_as_empty(windows, monkeypatch) -> None:
    """Seats are placed relative to the window centre; without it there is none."""
    install_uia(monkeypatch, window=UIAElement("table", None), descendants=seated_table(SIX_MAX))

    assert WinamaxAXSeatReader()._read_window_windows(61825) == {}


def test_a_com_failure_is_logged_not_propagated(windows, monkeypatch) -> None:
    """A HUD update must never die because UIAutomation was busy."""
    automation = install_uia(monkeypatch, window=UIAElement("table", TABLE_WINDOW), descendants=[])
    automation.ElementFromHandle.side_effect = OSError("RPC server unavailable")

    assert WinamaxAXSeatReader()._read_window_windows(61825) == {}


# ---------------------------------------------------------------------------
# Finding the handle from a title
# ---------------------------------------------------------------------------


def test_the_title_is_matched_literally_not_as_a_pattern(windows, monkeypatch) -> None:
    """Table names carry characters a regex would read as syntax."""
    detector = MagicMock()
    detector.find_tables.return_value = []
    reader = WinamaxAXSeatReader(table_detector=detector)

    reader._read_window_windows_by_title("Winamax Casablanca (2)")

    import re

    pattern = detector.find_tables.call_args.args[0]
    assert re.search(pattern, "Winamax Casablanca (2)")


def test_the_only_window_is_read(windows, monkeypatch) -> None:
    reader = WinamaxAXSeatReader(table_detector=MagicMock())
    reader._table_detector.find_tables.return_value = [detected("Winamax Bucarest 3", 61825)]
    reader._read_window_windows = MagicMock(return_value={0: "jejellyroll"})

    assert reader._read_window_windows_by_title("Winamax Bucarest 3") == {0: "jejellyroll"}
    reader._read_window_windows.assert_called_once_with(61825, 6)


def test_the_nearest_window_wins_when_two_share_a_title(windows) -> None:
    """Multi-tabling identical stakes gives two windows the same title."""
    near = detected("Winamax Bucarest 3", 61825, types.SimpleNamespace(x=0, y=33))
    far = detected("Winamax Bucarest 3", 61826, types.SimpleNamespace(x=800, y=33))
    reader = WinamaxAXSeatReader(table_detector=MagicMock())
    reader._table_detector.find_tables.return_value = [far, near]
    reader._read_window_windows = MagicMock(return_value={})

    reader._read_window_windows_by_title("Winamax Bucarest 3", table_pos=(0.0, 33.0))

    assert reader._read_window_windows.call_args.args[0] == 61825


def test_a_window_with_no_geometry_does_not_break_the_choice(windows) -> None:
    """The detector may answer without coordinates."""
    reader = WinamaxAXSeatReader(table_detector=MagicMock())
    reader._table_detector.find_tables.return_value = [
        detected("Winamax Bucarest 3", 61825, None),
        detected("Winamax Bucarest 3", 61826, types.SimpleNamespace(x=800, y=33)),
    ]
    reader._read_window_windows = MagicMock(return_value={})

    reader._read_window_windows_by_title("Winamax Bucarest 3", table_pos=(0.0, 33.0))

    reader._read_window_windows.assert_called_once()


def test_no_window_found_reads_as_empty(windows) -> None:
    reader = WinamaxAXSeatReader(table_detector=MagicMock())
    reader._table_detector.find_tables.return_value = []

    assert reader._read_window_windows_by_title("Winamax Bucarest 3") == {}


def test_a_window_without_a_handle_reads_as_empty(windows) -> None:
    """Without a handle there is nothing to hand UIAutomation."""
    reader = WinamaxAXSeatReader(table_detector=MagicMock())
    reader._table_detector.find_tables.return_value = [detected("Winamax Bucarest 3", None)]

    assert reader._read_window_windows_by_title("Winamax Bucarest 3") == {}


def test_a_detector_failure_reads_as_empty(windows) -> None:
    reader = WinamaxAXSeatReader(table_detector=MagicMock())
    reader._table_detector.find_tables.side_effect = RuntimeError("no window station")

    assert reader._read_window_windows_by_title("Winamax Bucarest 3") == {}


def test_the_shared_detector_is_created_once_on_demand(windows, monkeypatch) -> None:
    """The same singleton the macOS path uses, for the same reason."""
    import fpdb.infrastructure.platform as platform_module

    detector = MagicMock()
    detector.find_tables.return_value = []
    get_detector = MagicMock(return_value=detector)
    monkeypatch.setattr(platform_module, "get_table_detector", get_detector)
    reader = WinamaxAXSeatReader()

    reader._read_window_windows_by_title("Winamax Bucarest 3")
    reader._read_window_windows_by_title("Winamax Bucarest 3")

    assert get_detector.call_count == 1


# ---------------------------------------------------------------------------
# The dispatch that keeps the two apart
# ---------------------------------------------------------------------------


def test_read_window_on_windows_never_touches_the_macos_api(windows) -> None:
    """The macOS branch imports pyobjc, which does not exist on Windows.

    This is the line that keeps a shared entry point from dragging one
    platform's bindings onto the other.
    """
    reader = WinamaxAXSeatReader()
    reader._application = MagicMock(side_effect=AssertionError("macOS path taken on Windows"))
    reader._read_window_windows_by_title = MagicMock(return_value={0: "jejellyroll"})

    assert reader.read_window("Winamax Bucarest 3", 6, table_pos=(1.0, 2.0)) == {0: "jejellyroll"}
    reader._read_window_windows_by_title.assert_called_once_with("Winamax Bucarest 3", 6, table_pos=(1.0, 2.0))


def test_a_known_handle_is_read_without_searching_the_desktop(windows) -> None:
    """Every window of a Fast-Fold pool shares a title; the handle is the identity.

    It also spares an enumeration of every window on the desktop, which the HUD
    would otherwise pay for on each of the six reads it makes per hand.
    """
    reader = WinamaxAXSeatReader()
    reader._read_window_windows = MagicMock(return_value={0: "jejellyroll"})
    reader._read_window_windows_by_title = MagicMock(side_effect=AssertionError("searched by title"))

    assert reader.read_window("Winamax Bucarest 3", 6, window_id=61825) == {0: "jejellyroll"}
    reader._read_window_windows.assert_called_once_with(61825, 6)


def test_a_partial_ring_off_frame_is_refused_until_a_full_one_is_seen(monkeypatch) -> None:
    """Seating people from a centre nobody measured puts stats on the wrong chairs.

    The client reports its content in a different space from its frame, so the
    centre has to come from the players -- and a partial ring's bounding box is
    not the table's centre. The hero would still land on slot 0 and the answer
    be accepted, with the neighbours two chairs from where they sit.
    """
    ax.forget_window_state()
    ax.reset_windows_uia()
    # A window at 3840..4800 whose players report at 1767..2259, as measured.
    window = UIAElement("Winamax Colorado 1", Rect(3840, 0, 4800, 739))
    partial = seated_table({"jejellyroll": (2000, 365), "depor81": (1783, 329)})
    install_uia(monkeypatch, window=window, descendants=partial)

    assert ax.WinamaxAXSeatReader()._read_window_windows(1234, 6) == {}
