"""Unit tests for reading Winamax seats off the table window.

The accessibility plumbing needs a running client, so these cover the parts that
turn what it returns into a ring: telling names from the rest of the table, and
ordering them the way the client draws them.
"""

from __future__ import annotations

from types import SimpleNamespace

from fpdb_3_legacy import winamax_ax_seats
from fpdb_3_legacy.winamax_ax_seats import (
    AXSeat,
    AXTableWindow,
    WinamaxAXSeatReader,
    is_stack_label,
    seat_slots_from_positions,
    seats_from_labels,
)

# A 757x592 table window at the origin, as the client lays it out.
CENTRE = (378.5, 329.0)


def test_stack_labels_are_recognised() -> None:
    assert is_stack_label("552,5 BB")
    assert is_stack_label("129 BB")
    assert is_stack_label("7,64 €")
    assert not is_stack_label("Hero")
    assert not is_stack_label("Pot : 23,5 BB")


def test_names_are_the_labels_with_a_stack_drawn_under_them() -> None:
    """Measured on the client: the stack sits ~17px below, ~11px across."""
    labels = [
        AXSeat("Hero", 346, 474),
        AXSeat("552,5 BB", 335, 491),
        AXSeat("Player_Three", 69, 181),
        AXSeat("130,5 BB", 74, 198),
        AXSeat("Pot : 23,5 BB", 340, 300),
        AXSeat("LANCE TON DÉ OFFERT !", 26, 74),
    ]

    assert [s.login for s in seats_from_labels(labels)] == ["Hero", "Player_Three"]


def test_bare_units_and_readouts_are_not_players() -> None:
    """A timer or slider readout can sit above a chip amount without being a seat."""
    labels = [
        AXSeat("80%", 300, 450),
        AXSeat("23", 310, 460),
        AXSeat("BB", 320, 450),
        AXSeat("1 BB", 305, 470),
    ]

    assert seats_from_labels(labels) == []


def test_slots_run_clockwise_from_the_bottom_chair() -> None:
    """Positions taken from a real 6-max Escape window."""
    seats = [
        AXSeat("Player_Three", 69, 181),  # left, upper (slot 2)
        AXSeat("PlayerFive", 329, 139),  # top centre (slot 3)
        AXSeat("Player04", 601, 181),  # right, upper (slot 4)
        AXSeat("Player06", 599, 432),  # right, lower (slot 5)
        AXSeat("Hero", 346, 474),  # bottom centre -- the hero (slot 0)
    ]

    slots = seat_slots_from_positions(seats, CENTRE, 6)

    assert slots[0] == "Hero"
    assert slots[2] == "Player_Three"
    assert slots[3] == "PlayerFive"
    assert slots[4] == "Player04"
    assert slots[5] == "Player06"
    # Nobody in the left-lower chair, so slot 1 stays empty.
    assert 1 not in slots


def test_an_empty_chair_does_not_shift_the_players_after_it() -> None:
    """Numbering players consecutively puts blocks on the wrong seats."""
    seats = [
        AXSeat("Hero", 346, 474),  # bottom centre (slot 0)
        AXSeat("player07", 69, 432),  # left lower (slot 1)
        AXSeat("Player06", 69, 181),  # left upper (slot 2)
        # top centre empty (slot 3 empty)
        AXSeat("player2", 601, 181),  # right upper (slot 4)
        AXSeat("PLAYERCAPS", 599, 432),  # right lower (slot 5)
    ]

    slots = seat_slots_from_positions(seats, CENTRE, 6)

    assert slots == {0: "Hero", 1: "player07", 2: "Player06", 4: "player2", 5: "PLAYERCAPS"}


def test_slots_do_not_depend_on_the_order_read() -> None:
    seats = [
        AXSeat("Hero", 346, 474),
        AXSeat("Player04", 601, 181),
        AXSeat("Player_Three", 69, 181),
    ]

    assert seat_slots_from_positions(seats, CENTRE, 6) == seat_slots_from_positions(
        list(reversed(seats)), CENTRE, 6
    )


def test_empty_input_gives_no_slots() -> None:
    assert seat_slots_from_positions([], CENTRE, 6) == {}
    assert seat_slots_from_positions([AXSeat("A", 1, 1)], CENTRE, 0) == {}
    assert seats_from_labels([]) == []


def test_the_window_header_names_the_game() -> None:
    """It is what lets a table be created without any imported hand."""
    from fpdb_3_legacy.winamax_ax_seats import AXTableWindow, poker_game_from_description

    assert poker_game_from_description("ESCAPE - 0,01-0,02 € - Pot Limit Omaha") == "omahahi"
    assert poker_game_from_description("ESCAPE - 0,01-0,02 € - No Limit Holdem") == "holdem"
    assert poker_game_from_description("Go Fast - 1-2 € - Omaha Hi/Lo") == "omahahilo"
    assert poker_game_from_description("ESCAPE - 5 Card Omaha") == "5_omahahi"
    assert poker_game_from_description("ESCAPE - 0,01-0,02 €") is None
    assert poker_game_from_description("") is None

    window = AXTableWindow(title="Winamax Casablanca 6", description="ESCAPE - 0,01 € - Pot Limit Omaha")
    # fpdb keys the table by the title without the site prefix, which is also
    # what narrows the window search back to this one window.
    assert window.table_name == "Casablanca 6"
    assert window.poker_game == "omahahi"


def test_seat_labels_are_not_players() -> None:
    """The client draws these where a name goes, with a chip amount beneath."""
    from fpdb_3_legacy.winamax_ax_seats import is_seat_label

    assert is_seat_label("SMALL BLIND")
    assert is_seat_label("BIG BLIND")
    assert is_seat_label("ABSENT")
    assert is_seat_label("Full : 2-6")
    assert is_seat_label("Hauteur : A")

    # Logins, including shouty ones, must survive.
    assert not is_seat_label("PLAYERCAPS")
    assert not is_seat_label("Hero")
    assert not is_seat_label("Player Ten10")
    assert not is_seat_label("player-123456")


def test_a_blind_label_does_not_take_a_seat() -> None:
    """Taken from a real read where 'SMALL BLIND' was seated and shifted a player."""
    labels = [
        AXSeat("Hero", 346, 474),
        AXSeat("552,5 BB", 335, 491),
        AXSeat("SMALL BLIND", 601, 181),
        AXSeat("1 BB", 605, 198),
        AXSeat("Player08", 599, 432),
        AXSeat("24 BB", 601, 449),
    ]

    assert [s.login for s in seats_from_labels(labels)] == ["Hero", "Player08"]


def test_non_breaking_spaces_do_not_smuggle_a_label_into_a_seat() -> None:
    """The client writes "Pot total\xa0:\xa01,5\xa0BB", which a literal " : " test misses."""
    from fpdb_3_legacy.winamax_ax_seats import is_seat_label

    assert is_seat_label("Pot total\xa0: 1,5\xa0BB")
    assert is_seat_label("Pot\xa0total\xa0:\xa010\xa0BB")
    assert is_seat_label("Full\xa0: 2-6")
    assert not is_seat_label("Player Ten10")


def test_the_pot_label_does_not_take_a_seat() -> None:
    """Taken from a real read where the pot was seated and displaced a player."""
    labels = [
        AXSeat("Hero", 346, 474),
        AXSeat("552,5 BB", 335, 491),
        AXSeat("Pot total\xa0: 1,5\xa0BB", 601, 181),
        AXSeat("1 BB", 605, 198),
        AXSeat("Player08", 599, 432),
        AXSeat("24 BB", 601, 449),
    ]

    assert [s.login for s in seats_from_labels(labels)] == ["Hero", "Player08"]


class _Detector:
    """Small stand-in for the shared MacOSTableDetector lookup order."""

    def __init__(self, quartz=(), fallback=()) -> None:
        self.quartz = list(quartz)
        self.fallback = list(fallback)
        self.calls: list[tuple[str, bool]] = []

    def find_tables(self, search: str, *, allow_fallback: bool = True):
        self.calls.append((search, allow_fallback))
        return self.fallback if allow_fallback else self.quartz


class TestFindTableWindow:
    """Fast Fold shares the platform detector used later by OSXTables."""

    @staticmethod
    def _table(title: str, window_id: int = 48_782) -> SimpleNamespace:
        return SimpleNamespace(title=title, window_id=window_id)

    @staticmethod
    def _enable_macos(monkeypatch) -> None:
        monkeypatch.setattr(winamax_ax_seats.platform, "system", lambda: "Darwin")

    def test_quartz_window_is_preferred_and_enriched_by_accessibility(self, monkeypatch) -> None:
        self._enable_macos(monkeypatch)
        detector = _Detector(quartz=[self._table("Winamax Colorado 4")])
        from_ax = AXTableWindow(
            title="Winamax Colorado 4",
            description="ESCAPE - 0,01-0,02 € - Pot Limit Omaha",
        )
        monkeypatch.setattr(WinamaxAXSeatReader, "_find_table_window_ax", lambda _self, _no: from_ax)

        window = WinamaxAXSeatReader(detector).find_table_window("4")

        assert window == AXTableWindow(
            title="Winamax Colorado 4",
            description=from_ax.description,
            window_id=48_782,
        )
        assert window.poker_game == "omahahi"
        assert detector.calls == [(r"^Winamax\s+.*\s4\s*$", False)]

    def test_system_events_is_only_the_shared_detectors_last_resort(self, monkeypatch) -> None:
        self._enable_macos(monkeypatch)
        detector = _Detector(fallback=[self._table("Winamax Colorado 4", 2_123_456)])
        monkeypatch.setattr(WinamaxAXSeatReader, "_find_table_window_ax", lambda _self, _no: None)
        window = WinamaxAXSeatReader(detector).find_table_window("4")

        assert window is not None
        assert window.title == "Winamax Colorado 4"
        assert window.window_id == 2_123_456
        assert window.poker_game is None
        assert detector.calls == [
            (r"^Winamax\s+.*\s4\s*$", False),
            (r"^Winamax\s+.*\s4\s*$", True),
        ]

    def test_only_the_window_carrying_the_client_index_matches(self, monkeypatch) -> None:
        self._enable_macos(monkeypatch)
        detector = _Detector(
            quartz=[
                self._table("Winamax Colorado 3", 101),
                self._table("Winamax Colorado 4", 102),
            ]
        )
        monkeypatch.setattr(WinamaxAXSeatReader, "_find_table_window_ax", lambda _self, _no: None)

        window = WinamaxAXSeatReader(detector).find_table_window("4")

        assert window is not None
        assert window.title == "Winamax Colorado 4"
        assert window.window_id == 102

    def test_accessibility_answer_survives_when_no_window_id_is_available(self, monkeypatch) -> None:
        self._enable_macos(monkeypatch)
        detector = _Detector()
        from_ax = AXTableWindow(
            title="Winamax Colorado 4",
            description="ESCAPE - 0,01-0,02 € - Pot Limit Omaha",
        )
        monkeypatch.setattr(WinamaxAXSeatReader, "_find_table_window_ax", lambda _self, _no: from_ax)

        assert WinamaxAXSeatReader(detector).find_table_window("4") == from_ax

    def test_nothing_is_attempted_off_macos(self, monkeypatch) -> None:
        monkeypatch.setattr(winamax_ax_seats.platform, "system", lambda: "Linux")
        detector = _Detector(quartz=[self._table("Winamax Colorado 4")])

        assert WinamaxAXSeatReader(detector).find_table_window("4") is None
        assert detector.calls == []


def test_full_six_max_table_slots_and_layout_seat_map() -> None:
    """Verify that a full 6-max table maps all 6 players to layout seats 3, 4, 5, 6, 1, 2."""
    seats = [
        AXSeat("Hero", 346, 474),  # Slot 0 -> Seat 3 (Bottom centre)
        AXSeat("Meteorito8", 69, 432),  # Slot 1 -> Seat 4 (Bottom left)
        AXSeat("Putignac", 69, 181),  # Slot 2 -> Seat 5 (Top left)
        AXSeat("Jokic....", 329, 139),  # Slot 3 -> Seat 6 (Top centre)
        AXSeat("almarcha0346", 601, 181),  # Slot 4 -> Seat 1 (Top right)
        AXSeat("Stun_Gun_Tim", 599, 432),  # Slot 5 -> Seat 2 (Bottom right)
    ]

    slots = seat_slots_from_positions(seats, CENTRE, 6)
    anchor_seat = 3
    seat_map = {((slot + anchor_seat - 1) % 6) + 1: login for slot, login in slots.items()}

    assert seat_map[3] == "Hero"
    assert seat_map[4] == "Meteorito8"
    assert seat_map[5] == "Putignac"
    assert seat_map[6] == "Jokic...."
    assert seat_map[1] == "almarcha0346"
    assert seat_map[2] == "Stun_Gun_Tim"

