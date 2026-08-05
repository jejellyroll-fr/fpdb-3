"""The site's tournament catalogue must not rename the table being played.

A live session broke this way: the player opened the lobby while at a cash
table, one ``lobby.lobby_details`` arrived carrying the whole site's tournament
list, and from the very next hand the cash table was written as
``Tournament #70623, 32.0`` on a 2-max table. The buy-in "32.0" then failed
every insert into the integer ``TourneyTypes.buyin`` column, so no hand reached
the database at all and the HUD sat frozen on the players it already had.
"""

from __future__ import annotations

import pytest

from fpdb_3_legacy.coinpoker_hand_builder import _tournament_info
from fpdb_3_legacy.http_capture_hand_builder import _money_to_cents

# Shaped like the real payload: the lobby publishes every tournament running on
# the site, each with its own id and entry fee, and names no table.
LOBBY_CATALOGUE = (
    "lobby.lobby_details",
    None,
    {
        "mainLobbyTournamentSharedData": {
            "2": {
                "0": [
                    {"tournamentId": 70623, "tournamentName": "Comm_Tournament_70623", "entryFee": 32.0},
                    {"tournamentId": 82305, "tournamentName": "Comm_Tournament_82305", "entryFee": 0.88},
                    {"tournamentId": 84648, "tournamentName": "Comm_Tournament_84648", "entryFee": 0.33},
                ]
            }
        }
    },
)

RING_HAND_EVENT = ("game.seat", "13014700993", {"seatId": 3, "userName": "GG18vivek", "userChips": 1.9})


def test_the_lobby_catalogue_does_not_turn_a_cash_table_into_a_tournament() -> None:
    events = [LOBBY_CATALOGUE, RING_HAND_EVENT]

    assert _tournament_info(events, table_id="130147", sole_table=True) is None


def test_a_single_named_tournament_still_speaks_for_the_only_table() -> None:
    """The reason table-less markers are read at all must keep working."""
    events = [
        (
            "game.tournament_message",
            None,
            {"commonTournamentResponseData": {"TournamentId": 77, "TournamentName": "Sunday MTT"}},
        ),
        RING_HAND_EVENT,
    ]

    info = _tournament_info(events, table_id="130147", sole_table=True)

    assert info is not None
    assert info["tour_no"] == "77"


def test_a_marker_naming_another_table_is_not_read_for_this_one() -> None:
    events = [
        ("game.tournament_message", None, {"tableId": "999999", "tournamentId": 70623, "buyIn": 32.0}),
        RING_HAND_EVENT,
    ]

    assert _tournament_info(events, table_id="130147", sole_table=True) is None


def test_the_catalogue_cannot_donate_a_buy_in_to_a_real_tournament() -> None:
    """A genuine tournament keeps its own buy-in, not the catalogue's first."""
    events = [
        LOBBY_CATALOGUE,
        ("game.tournament_message", None, {"tournamentId": 77, "buyIn": "5.50"}),
        RING_HAND_EVENT,
    ]

    info = _tournament_info(events, table_id="130147", sole_table=True)

    assert info is not None
    assert info["tour_no"] == "77"
    assert info["buyin"] == "5.50"


@pytest.mark.parametrize(
    ("amount", "cents"),
    [("32.0", 3200), (32.0, 3200), ("32", 3200), ("0.25", 25), ("1,50", 150), (None, 0), ("", 0), ("Ticket", 0)],
)
def test_tournament_amounts_are_stored_as_whole_cents(amount, cents) -> None:
    """The columns are integers; "32.0" reaching one killed the whole import."""
    assert _money_to_cents(amount) == cents
    assert isinstance(_money_to_cents(amount), int)
