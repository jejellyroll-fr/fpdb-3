"""The macOS seat reader, driven through a stand-in accessibility API.

This is the part of the Fast-Fold HUD that reads who is sitting where, and it
was the least covered: every method that matters imports ApplicationServices
or AppKit, so it needed a running client, granted TCC permissions and a real
screen. :mod:`test.fastfold_ax_doubles` supplies those four functions instead,
faithfully enough that the reader cannot tell -- including the API's habit of
returning ``(error, value)`` rather than raising, and of handing geometry over
boxed.

Covering it matters beyond the current bugs: a Windows or Linux seat reader
will be added beside this one, and the shared entry points
(``find_table_window``, ``read_window``, ``is_supported``) dispatch on
platform. Without these, a change made for another OS could silently take the
macOS path with it.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

from fpdb_3_legacy import winamax_ax_seats as ax
from fpdb_3_legacy.winamax_ax_seats import AXSeat, AXTableWindow, WinamaxAXSeatReader

from .fastfold_ax_doubles import AXElement, FakeAX, RunningApplication, button, installed, text

pytestmark = []


@pytest.fixture
def darwin(monkeypatch):
    """Run the body as though this were macOS."""
    monkeypatch.setattr(ax.platform, "system", lambda: "Darwin")


@pytest.fixture
def windows(monkeypatch):
    """Run the body as though this were Windows."""
    monkeypatch.setattr(ax.platform, "system", lambda: "Windows")


@pytest.fixture
def linux(monkeypatch):
    """Run the body as though this were Linux."""
    monkeypatch.setattr(ax.platform, "system", lambda: "Linux")


# ---------------------------------------------------------------------------
# Platform gates
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("system", "supported"),
    [("Darwin", True), ("Windows", True), ("Linux", False), ("FreeBSD", False)],
)
def test_only_platforms_with_a_window_resolver_are_supported(monkeypatch, system, supported) -> None:
    """A platform that cannot name a table window cannot drive a Fast-Fold HUD."""
    monkeypatch.setattr(ax.platform, "system", lambda: system)

    assert ax.is_supported() is supported


def test_the_api_is_available_on_macos_with_the_bindings(darwin) -> None:
    """pyobjc present: seats can be read."""
    with installed(FakeAX()):
        assert ax.is_ax_available() is True


def test_the_api_is_unavailable_on_macos_without_the_bindings(darwin) -> None:
    """A build with no pyobjc must say so rather than raise at read time."""
    with installed(FakeAX(), absent=("ApplicationServices",)):
        assert ax.is_ax_available() is False


def test_the_api_is_unavailable_on_macos_without_appkit(darwin) -> None:
    """ApplicationServices alone is not enough: the client is found via AppKit."""
    with installed(FakeAX(), absent=("AppKit",)):
        assert ax.is_ax_available() is False


def test_windows_availability_follows_comtypes(windows, monkeypatch) -> None:
    """On Windows the equivalent binding is comtypes."""
    monkeypatch.setitem(sys.modules, "comtypes", MagicMock())
    monkeypatch.setitem(sys.modules, "comtypes.client", MagicMock())
    assert ax.is_ax_available() is True

    monkeypatch.setitem(sys.modules, "comtypes.client", None)
    assert ax.is_ax_available() is False


def test_no_accessibility_api_on_other_platforms(linux) -> None:
    """Linux has neither binding, and must not be probed for one."""
    assert ax.is_ax_available() is False


# ---------------------------------------------------------------------------
# Talking to the client application
# ---------------------------------------------------------------------------


def test_the_client_is_found_by_name_and_its_web_tree_switched_on(darwin) -> None:
    """Chromium only builds its accessibility tree when asked."""
    fake = FakeAX([RunningApplication("Finder", 1), RunningApplication("Winamax", 4242)])
    reader = WinamaxAXSeatReader()

    with installed(fake):
        app = reader._application()

    assert app is fake.app_element
    assert fake.created == [4242]
    assert ("AXManualAccessibility", True) in [(name, value) for _el, name, value in fake.set_calls]


def test_a_client_that_is_not_running_yields_nothing(darwin) -> None:
    """No Winamax process: no handle, and no stale one kept."""
    reader = WinamaxAXSeatReader()
    reader._app, reader._pid = object(), 999

    with installed(FakeAX([RunningApplication("Finder", 1)])):
        assert reader._application() is None

    assert reader._app is None
    assert reader._pid is None


def test_an_application_with_no_name_is_skipped(darwin) -> None:
    """localizedName can be None, and comparing it must not raise."""
    fake = FakeAX([RunningApplication(None, 7), RunningApplication("Winamax", 4242)])
    reader = WinamaxAXSeatReader()

    with installed(fake):
        assert reader._application() is fake.app_element


def test_the_handle_is_reused_while_the_pid_holds(darwin) -> None:
    """Re-creating it every read would rebuild the web tree each time."""
    fake = FakeAX()
    reader = WinamaxAXSeatReader()

    with installed(fake):
        reader._application()
        reader._application()

    assert fake.created == [4242]


def test_a_restarted_client_gets_a_fresh_handle(darwin) -> None:
    """A new pid is a new application; the old handle names nothing."""
    fake = FakeAX()
    reader = WinamaxAXSeatReader()

    with installed(fake):
        reader._application()
        fake.applications = [RunningApplication("Winamax", 5555)]
        reader._application()

    assert fake.created == [4242, 5555]


# ---------------------------------------------------------------------------
# Reading attributes and geometry
# ---------------------------------------------------------------------------


def test_an_attribute_the_element_lacks_reads_as_none(darwin) -> None:
    """The API reports absence through its error code, not an exception."""
    element = AXElement("AXStaticText")

    with installed(FakeAX()):
        assert WinamaxAXSeatReader._attr(element, "AXValue") is None
        assert WinamaxAXSeatReader._attr(element, "AXRole") == "AXStaticText"


def test_geometry_is_unboxed_and_rounded(darwin) -> None:
    """Positions arrive as floats behind an opaque box."""
    element = AXElement("AXWindow", position=(10.4, 20.6), size=(757.5, 592.2))

    with installed(FakeAX()):
        origin, size = WinamaxAXSeatReader._geometry(element)

    assert origin == (10, 21)
    assert size == (758, 592)


def test_missing_geometry_is_reported_as_none(darwin) -> None:
    """A window that will not say where it is cannot be used to place seats."""
    with installed(FakeAX()):
        assert WinamaxAXSeatReader._geometry(AXElement("AXWindow")) == (None, None)


def test_geometry_that_will_not_unbox_is_reported_as_none(darwin) -> None:
    """A stale handle boxes a value of the wrong kind; it must not be trusted."""
    element = AXElement("AXWindow", position=(1.0, 2.0))
    element.attrs["AXSize"] = element.attrs["AXPosition"]  # a point where a size belongs

    with installed(FakeAX()):
        origin, size = WinamaxAXSeatReader._geometry(element)

    assert origin == (1, 2)
    assert size is None


# ---------------------------------------------------------------------------
# Walking the tree for labels
# ---------------------------------------------------------------------------


def _collect(root: AXElement) -> list[AXSeat]:
    found: list[AXSeat] = []
    with installed(FakeAX()):
        WinamaxAXSeatReader()._collect_text(root, found)
    return found


def test_static_text_is_collected_with_its_position() -> None:
    root = AXElement("AXWindow", children=[text("jejellyroll", 100, 200)])

    assert _collect(root) == [AXSeat("jejellyroll", 100, 200)]


def test_the_tree_is_walked_depth_first() -> None:
    """Labels are nested several levels down inside the web view."""
    root = AXElement(
        "AXWindow",
        children=[AXElement("AXGroup", children=[AXElement("AXGroup", children=[text("deep", 1, 2)])])],
    )

    assert _collect(root) == [AXSeat("deep", 1, 2)]


def test_buttons_and_their_contents_are_skipped() -> None:
    """Action controls label themselves and sit above chip amounts.

    Left in, "POT" and "ALL-IN" pair with the amount beneath them and read as
    players.
    """
    root = AXElement(
        "AXWindow",
        children=[
            AXElement("AXButton", children=[text("POT", 300, 690)]),
            button("ALL-IN", 400, 690),
            text("jejellyroll", 100, 200),
        ],
    )

    assert _collect(root) == [AXSeat("jejellyroll", 100, 200)]


def test_non_breaking_spaces_are_normalised() -> None:
    """The client writes "Pot total\\xa0:\\xa01,5\\xa0BB"; a literal test missed it."""
    root = AXElement("AXWindow", children=[text("Pot total\xa0:\xa01,5\xa0BB", 5, 6)])

    assert _collect(root) == [AXSeat("Pot total : 1,5 BB", 5, 6)]


@pytest.mark.parametrize(
    ("value", "why"),
    [
        (None, "no AXValue at all"),
        (12345, "a number rather than text"),
        ("", "empty after stripping"),
        ("   ", "whitespace only"),
        ("x" * 41, "longer than any login the client draws"),
    ],
)
def test_values_that_cannot_be_a_label_are_dropped(value, why) -> None:
    node = AXElement("AXStaticText", position=(1, 2))
    if value is not None:
        node.attrs["AXValue"] = value

    assert _collect(AXElement("AXWindow", children=[node])) == [], why


def test_a_label_with_no_position_is_dropped() -> None:
    """Without coordinates a label cannot be paired with a stack or a slot."""
    root = AXElement("AXWindow", children=[AXElement("AXStaticText", value="jejellyroll")])

    assert _collect(root) == []


def test_the_walk_stops_before_it_can_run_away() -> None:
    """A cyclic or pathological tree must not hang the GUI thread."""
    deepest = AXElement("AXStaticText", value="too deep", position=(1, 2))
    node = deepest
    for _ in range(30):
        node = AXElement("AXGroup", children=[node])

    assert _collect(node) == []


def test_the_walk_stops_once_it_has_more_labels_than_a_table_can_hold() -> None:
    """A table draws tens of labels; hundreds means something else is going on."""
    root = AXElement("AXWindow", children=[text(f"label{i}", i, i) for i in range(500)])

    found = _collect(root)

    assert 400 < len(found) <= 500


# ---------------------------------------------------------------------------
# Resolving which window is which table
# ---------------------------------------------------------------------------


def _detector(tables) -> MagicMock:
    detector = MagicMock()
    detector.find_tables.return_value = tables
    return detector


def _detected(title: str, window_id) -> MagicMock:
    table = MagicMock()
    table.title = title
    table.window_id = window_id
    return table


@pytest.mark.parametrize(
    ("title", "table_no", "matches"),
    [
        ("Winamax Bucarest 3", "3", True),
        ("Winamax Bucarest 3 ", "3", True),
        ("Winamax Bucarest 13", "3", False),  # a suffix, not the index
        ("Winamax Bucarest", "3", False),
        ("", "3", False),
    ],
)
def test_a_window_title_carries_the_client_index(title, table_no, matches) -> None:
    """The trailing number in the title is the same index the log writes."""
    assert WinamaxAXSeatReader._is_table_no(title, table_no) is matches


def test_an_unsupported_platform_resolves_nothing(linux) -> None:
    reader = WinamaxAXSeatReader(table_detector=_detector([_detected("Winamax Bucarest 3", 61825)]))

    assert reader.find_table_window("3") is None


def test_windows_uses_the_detector_and_never_the_ax_tree(windows) -> None:
    """The AX reader imports pyobjc; probing it on Windows would fail the call.

    The shared reader supports both operating systems, so this is the line that
    keeps a macOS-only import out of the Windows path.
    """
    reader = WinamaxAXSeatReader(table_detector=_detector([_detected("Winamax Bucarest 3", 61825)]))
    reader._find_table_window_ax = MagicMock(side_effect=AssertionError("must not be called on Windows"))

    window = reader.find_table_window("3")

    assert window == AXTableWindow(title="Winamax Bucarest 3", description="", window_id=61825)


def test_quartz_supplies_the_window_id_and_ax_the_header(darwin) -> None:
    """Each source answers what only it can, without an Apple Event."""
    reader = WinamaxAXSeatReader(table_detector=_detector([_detected("Winamax Bucarest 3", 61825)]))
    reader._find_table_window_ax = MagicMock(
        return_value=AXTableWindow(title="Winamax Bucarest 3", description="ESCAPE - 0,01-0,02 EUR - PLO"),
    )

    window = reader.find_table_window("3")

    assert window.window_id == 61825
    assert window.description == "ESCAPE - 0,01-0,02 EUR - PLO"


def test_a_window_quartz_alone_found_keeps_an_empty_header(darwin) -> None:
    """No header is workable; no window id is not."""
    reader = WinamaxAXSeatReader(table_detector=_detector([_detected("Winamax Bucarest 3", 61825)]))
    reader._find_table_window_ax = MagicMock(return_value=None)

    window = reader.find_table_window("3")

    assert window == AXTableWindow(title="Winamax Bucarest 3", description="", window_id=61825)


def test_system_events_is_only_asked_once_quartz_has_failed(darwin) -> None:
    """Its Apple Event is throttled and prompts the user, so it is the last resort."""
    detector = MagicMock()
    detector.find_tables.side_effect = [[], [_detected("Winamax Bucarest 3", 61825)]]
    reader = WinamaxAXSeatReader(table_detector=detector)
    reader._find_table_window_ax = MagicMock(
        return_value=AXTableWindow(title="Winamax Bucarest 3", description="ESCAPE"),
    )

    window = reader.find_table_window("3")

    assert [call.kwargs["allow_fallback"] for call in detector.find_tables.call_args_list] == [False, True]
    assert window.window_id == 61825
    assert window.description == "ESCAPE"


def test_the_fallback_answer_stands_alone_when_ax_said_nothing(darwin) -> None:
    detector = MagicMock()
    detector.find_tables.side_effect = [[], [_detected("Winamax Bucarest 3", 61825)]]
    reader = WinamaxAXSeatReader(table_detector=detector)
    reader._find_table_window_ax = MagicMock(return_value=None)

    assert reader.find_table_window("3").window_id == 61825


def test_ax_alone_answers_when_no_window_id_can_be_had(darwin) -> None:
    """Better a table named without an id than no table at all."""
    reader = WinamaxAXSeatReader(table_detector=_detector([]))
    accessible = AXTableWindow(title="Winamax Bucarest 3", description="ESCAPE")
    reader._find_table_window_ax = MagicMock(return_value=accessible)

    assert reader.find_table_window("3") is accessible


def test_nothing_found_anywhere_is_nothing(darwin) -> None:
    reader = WinamaxAXSeatReader(table_detector=_detector([]))
    reader._find_table_window_ax = MagicMock(return_value=None)

    assert reader.find_table_window("3") is None


# ---------------------------------------------------------------------------
# The shared platform detector
# ---------------------------------------------------------------------------


def test_the_detector_search_is_anchored_on_the_index(darwin) -> None:
    """"Bucarest 3" must not be matched by "Bucarest 13"."""
    detector = _detector([])
    WinamaxAXSeatReader(table_detector=detector)._find_table_window_detector("3", allow_fallback=False)

    pattern = detector.find_tables.call_args.args[0]
    import re

    assert re.match(pattern, "Winamax Bucarest 3")
    assert not re.match(pattern, "Winamax Bucarest 13")


def test_a_detector_answer_for_another_table_is_ignored(darwin) -> None:
    """The detector matches on a pattern; the index is checked again here."""
    reader = WinamaxAXSeatReader(table_detector=_detector([_detected("Winamax Bucarest 13", 1)]))

    assert reader._find_table_window_detector("3", allow_fallback=False) is None


def test_a_window_id_that_is_not_a_number_is_dropped_not_fatal(darwin) -> None:
    """A detector may answer without one; the table is still worth naming."""
    reader = WinamaxAXSeatReader(table_detector=_detector([_detected("Winamax Bucarest 3", "not-a-number")]))

    window = reader._find_table_window_detector("3", allow_fallback=False)

    assert window == AXTableWindow(title="Winamax Bucarest 3", description="", window_id=None)


def test_a_detector_that_raises_does_not_take_the_hud_down(darwin) -> None:
    """Screen Recording can be revoked mid-session."""
    detector = MagicMock()
    detector.find_tables.side_effect = RuntimeError("screen recording denied")
    reader = WinamaxAXSeatReader(table_detector=detector)

    assert reader._find_table_window_detector("3", allow_fallback=False) is None


def test_the_shared_detector_is_created_once_on_demand(darwin, monkeypatch) -> None:
    """It owns a System Events circuit breaker that must not be duplicated."""
    import fpdb.infrastructure.platform as platform_module

    detector = _detector([])
    get_detector = MagicMock(return_value=detector)
    monkeypatch.setattr(platform_module, "get_table_detector", get_detector)
    reader = WinamaxAXSeatReader()

    reader._find_table_window_detector("3", allow_fallback=False)
    reader._find_table_window_detector("3", allow_fallback=False)

    assert get_detector.call_count == 1


# ---------------------------------------------------------------------------
# Naming a table through the accessibility tree
# ---------------------------------------------------------------------------


def test_the_header_is_the_first_text_the_client_draws(darwin) -> None:
    fake = FakeAX()
    fake.app_element = AXElement(
        "AXApplication",
        windows=[
            AXElement("AXWindow", title="Winamax Bucarest 4", children=[text("other table", 1, 1)]),
            AXElement(
                "AXWindow",
                title="Winamax Bucarest 3",
                children=[text("ESCAPE - 0,01-0,02 EUR - Pot Limit Omaha", 10, 10), text("jejellyroll", 20, 20)],
            ),
        ],
    )
    reader = WinamaxAXSeatReader()

    with installed(fake):
        window = reader._find_table_window_ax("3")

    assert window == AXTableWindow(title="Winamax Bucarest 3", description="ESCAPE - 0,01-0,02 EUR - Pot Limit Omaha")
    assert window.poker_game == "omahahi"
    assert window.table_name == "Bucarest 3"


def test_a_window_with_no_labels_is_named_without_a_header(darwin) -> None:
    fake = FakeAX()
    fake.app_element = AXElement("AXApplication", windows=[AXElement("AXWindow", title="Winamax Bucarest 3")])

    with installed(fake):
        window = WinamaxAXSeatReader()._find_table_window_ax("3")

    assert window == AXTableWindow(title="Winamax Bucarest 3", description="")


def test_no_ax_bindings_means_no_ax_lookup(darwin) -> None:
    with installed(FakeAX(), absent=("ApplicationServices",)):
        assert WinamaxAXSeatReader()._find_table_window_ax("3") is None


def test_no_running_client_means_no_ax_lookup(darwin) -> None:
    with installed(FakeAX([RunningApplication("Finder", 1)])):
        assert WinamaxAXSeatReader()._find_table_window_ax("3") is None


def test_a_client_with_no_matching_window_answers_nothing(darwin) -> None:
    fake = FakeAX()
    fake.app_element = AXElement("AXApplication", windows=[AXElement("AXWindow", title="Winamax Bucarest 9")])

    with installed(fake):
        assert WinamaxAXSeatReader()._find_table_window_ax("3") is None


def test_an_accessibility_failure_is_logged_not_raised(darwin) -> None:
    """TCC can be revoked between two calls; the HUD must survive it."""
    reader = WinamaxAXSeatReader()
    reader._application = MagicMock(side_effect=RuntimeError("AX denied"))

    with installed(FakeAX()):
        assert reader._find_table_window_ax("3") is None


# ---------------------------------------------------------------------------
# Reading the seats off a window
# ---------------------------------------------------------------------------


def _seated_window(title: str, *, origin=(0, 0), size=(776, 606), players=None) -> AXElement:
    """A table window drawing each player's name with a stack beneath it.

    The name/stack pairing is what identifies a seat, so a window built
    without the stacks would read as having no players at all.
    """
    labels: list[AXElement] = []
    for name, (x, y) in (players or {}).items():
        labels.append(text(name, x, y))
        labels.append(text("100 BB", x, y + 20))
    return AXElement("AXWindow", title=title, position=origin, size=size, children=labels)


#: Six chairs of a 776x606 table, positioned as the client draws them.
SIX_MAX = {
    "jejellyroll": (350, 520),  # bottom centre  -> slot 0
    "villain_bl": (60, 470),  # bottom left    -> slot 1
    "villain_tl": (50, 150),  # top left       -> slot 2
    "villain_tc": (350, 90),  # top centre     -> slot 3
    "villain_tr": (650, 150),  # top right      -> slot 4
    "villain_br": (660, 470),  # bottom right   -> slot 5
}


def _read(fake: FakeAX, title: str, **kwargs) -> dict:
    with installed(fake):
        return WinamaxAXSeatReader().read_window(title, **kwargs)


def test_seats_are_read_clockwise_from_the_hero(darwin) -> None:
    """Slot 0 is the bottom-centre chair; the rest follow clockwise."""
    fake = FakeAX()
    fake.app_element = AXElement(
        "AXApplication",
        windows=[_seated_window("Winamax Bucarest 3", players=SIX_MAX)],
    )

    slots = _read(fake, "Winamax Bucarest 3")

    assert slots == {
        0: "jejellyroll",
        1: "villain_bl",
        2: "villain_tl",
        3: "villain_tc",
        4: "villain_tr",
        5: "villain_br",
    }


def test_an_empty_chair_leaves_its_slot_empty(darwin) -> None:
    """Slots come from angles, not from order.

    Renumbering the remaining players would move every block after the gap
    onto the wrong person.
    """
    players = {name: pos for name, pos in SIX_MAX.items() if name != "villain_tc"}
    fake = FakeAX()
    fake.app_element = AXElement("AXApplication", windows=[_seated_window("Winamax Bucarest 3", players=players)])

    slots = _read(fake, "Winamax Bucarest 3")

    assert 3 not in slots
    assert slots[4] == "villain_tr"


def test_the_hud_overlay_is_not_read_back_as_players(darwin) -> None:
    """The HUD draws its own labels over the table; they must not seat anyone."""
    window = _seated_window("Winamax Bucarest 3", players={"jejellyroll": (350, 520)})
    window.attrs["AXChildren"].extend(
        [text("jejel.", 340, 430), text("100 BB", 340, 450), text("VP 50.9", 400, 430), text("100 BB", 400, 450)],
    )
    fake = FakeAX()
    fake.app_element = AXElement("AXApplication", windows=[window])

    assert list(_read(fake, "Winamax Bucarest 3").values()) == ["jejellyroll"]


def test_a_window_id_suffix_in_the_key_is_ignored(darwin) -> None:
    """HUD keys carry "#61825"; the OS window title does not."""
    fake = FakeAX()
    fake.app_element = AXElement(
        "AXApplication",
        windows=[_seated_window("Winamax Bucarest 3", players=SIX_MAX)],
    )

    assert _read(fake, "Winamax Bucarest 3 #61825")


def test_a_window_with_a_different_index_is_not_read(darwin) -> None:
    """Two tables of one pool differ only by their index."""
    fake = FakeAX()
    fake.app_element = AXElement(
        "AXApplication",
        windows=[_seated_window("Winamax Bucarest 4", players=SIX_MAX)],
    )

    assert _read(fake, "Winamax Bucarest 3") == {}


def test_a_title_that_is_a_prefix_of_the_window_still_matches(darwin) -> None:
    """The client appends to its titles; neither side carries an index here."""
    fake = FakeAX()
    fake.app_element = AXElement(
        "AXApplication",
        windows=[_seated_window("Winamax Casablanca - Escape", players=SIX_MAX)],
    )

    assert _read(fake, "Winamax Casablanca")


def test_an_unrelated_window_is_not_read(darwin) -> None:
    fake = FakeAX()
    fake.app_element = AXElement("AXApplication", windows=[_seated_window("Winamax Lobby", players=SIX_MAX)])

    assert _read(fake, "Winamax Casablanca") == {}


def test_the_nearest_window_wins_when_two_share_a_title(darwin) -> None:
    """Multi-tabling identical stakes gives two windows the same title."""
    near = _seated_window("Winamax Bucarest 3", origin=(0, 33), players={"near_hero": (350, 553)})
    far = _seated_window("Winamax Bucarest 3", origin=(800, 33), players={"far_hero": (1150, 553)})
    fake = FakeAX()
    fake.app_element = AXElement("AXApplication", windows=[far, near])

    assert list(_read(fake, "Winamax Bucarest 3", table_pos=(0.0, 33.0)).values()) == ["near_hero"]
    assert list(_read(fake, "Winamax Bucarest 3", table_pos=(800.0, 33.0)).values()) == ["far_hero"]


def test_the_first_window_is_used_when_no_position_is_given(darwin) -> None:
    first = _seated_window("Winamax Bucarest 3", origin=(0, 33), players={"first_hero": (350, 553)})
    second = _seated_window("Winamax Bucarest 3", origin=(800, 33), players={"second_hero": (1150, 553)})
    fake = FakeAX()
    fake.app_element = AXElement("AXApplication", windows=[first, second])

    assert list(_read(fake, "Winamax Bucarest 3").values()) == ["first_hero"]


def test_a_window_without_geometry_is_skipped(darwin) -> None:
    """Seats are placed relative to the window's centre; without it, there is none."""
    unplaced = AXElement("AXWindow", title="Winamax Bucarest 3", children=[text("jejellyroll", 1, 1)])
    fake = FakeAX()
    fake.app_element = AXElement("AXApplication", windows=[unplaced])

    assert _read(fake, "Winamax Bucarest 3") == {}


def test_a_window_collapsed_to_nothing_is_skipped(darwin) -> None:
    """A zero-sized window has no centre to measure angles from."""
    fake = FakeAX()
    fake.app_element = AXElement(
        "AXApplication",
        windows=[_seated_window("Winamax Bucarest 3", size=(0, 0), players=SIX_MAX)],
    )

    assert _read(fake, "Winamax Bucarest 3") == {}


def test_a_table_drawing_nobody_reads_as_empty(darwin) -> None:
    """Between hands the felt carries labels but no name/stack pair."""
    window = AXElement(
        "AXWindow",
        title="Winamax Bucarest 3",
        position=(0, 0),
        size=(776, 606),
        children=[text("En attente de joueurs", 300, 700), text("ESCAPE!", 350, 300)],
    )
    fake = FakeAX()
    fake.app_element = AXElement("AXApplication", windows=[window])

    assert _read(fake, "Winamax Bucarest 3") == {}


def test_no_bindings_means_no_read(darwin) -> None:
    with installed(FakeAX(), absent=("ApplicationServices",)):
        assert WinamaxAXSeatReader().read_window("Winamax Bucarest 3") == {}


def test_no_running_client_means_no_read(darwin) -> None:
    assert _read(FakeAX([RunningApplication("Finder", 1)]), "Winamax Bucarest 3") == {}


def test_a_read_that_raises_is_logged_not_propagated(darwin) -> None:
    """A HUD update must never die on a revoked permission."""
    reader = WinamaxAXSeatReader()
    reader._application = MagicMock(side_effect=RuntimeError("AX denied"))

    with installed(FakeAX()):
        assert reader.read_window("Winamax Bucarest 3") == {}


# ---------------------------------------------------------------------------
# Label classification corners
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["", "   ", "\xa0"])
def test_an_empty_label_is_treated_as_hud_noise(value) -> None:
    """Nothing to read is not a player, and must not pair with a stack."""
    assert ax.is_hud_label(value) is True


def test_two_players_rounding_to_one_slot_keep_the_nearer(darwin) -> None:
    """The table is an ellipse, so angles round unevenly.

    Two names can land on one slot; the one closer to the slot's centre is the
    player really sitting there, and the other must not displace them.
    """
    centre = (388.0, 303.0)
    near = AXSeat("nearer", 388, 550)  # dead centre of slot 0
    far = AXSeat("further", 500, 545)  # same slot, off to the side

    assert ax.seat_slots_from_positions([near, far], centre, 6)[0] == "nearer"
    assert ax.seat_slots_from_positions([far, near], centre, 6)[0] == "nearer"


@pytest.mark.parametrize(("seats", "max_seats"), [([], 6), ([AXSeat("x", 1, 2)], 0)])
def test_nothing_to_place_yields_no_slots(seats, max_seats) -> None:
    assert ax.seat_slots_from_positions(seats, (0.0, 0.0), max_seats) == {}


def test_a_supported_platform_with_no_reader_resolves_nothing(monkeypatch) -> None:
    """Defensive: is_supported and the dispatch below must not drift apart.

    If a platform is ever added to is_supported without a branch here, this is
    the line that stops it silently taking the macOS path.
    """
    monkeypatch.setattr(ax, "is_supported", lambda: True)
    monkeypatch.setattr(ax.platform, "system", lambda: "Linux")
    reader = WinamaxAXSeatReader(table_detector=_detector([]))

    assert reader.find_table_window("3") is None


def test_a_window_whose_title_has_no_index_is_compared_whole(darwin) -> None:
    """One side carrying an index and the other not is not a match."""
    fake = FakeAX()
    fake.app_element = AXElement(
        "AXApplication",
        windows=[_seated_window("Winamax Lobby", players=SIX_MAX)],
    )

    assert _read(fake, "Winamax Bucarest 3") == {}


def test_titles_that_differ_but_share_an_index_are_the_same_table(darwin) -> None:
    """The client renames its windows; the trailing index is the identity.

    "Winamax Bucarest 3" and "Winamax Bucarest Escape 3" are one table, and
    refusing to read the second would leave a live table with no seats.
    """
    fake = FakeAX()
    fake.app_element = AXElement(
        "AXApplication",
        windows=[_seated_window("Winamax Bucarest Escape 3", players=SIX_MAX)],
    )

    assert _read(fake, "Winamax Bucarest 3")[0] == "jejellyroll"
