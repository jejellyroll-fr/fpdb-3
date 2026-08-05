"""A player in seat 0 must still get a HUD panel.

Reported from a live SwC table: eight players seated, seven stat panels. The
missing one sat in the snapshot's first seat.

Two things combined. The capture adapter numbers seats by their index in the
snapshot's seat array, so the first player is seat 0, while every other site
and the rest of fpdb number seats from 1. And the HUD decided which seats were
occupied with `if seat:`, which reads 0 as an empty chair — so that player was
dropped from the layout and never got a panel.

Both ends are pinned here: the builder now emits 1-based seats, and the
occupancy check no longer confuses seat 0 with an empty one.
"""

from __future__ import annotations

from types import SimpleNamespace

from fpdb_3_legacy.Aux_Base import AuxSeats
from fpdb_3_legacy.http_capture_hand_builder import build_hand_operations


def _hand_data(*names: str) -> dict:
    return {
        "players": [
            {"name": name, "seat_idx": index, "starting_stack": 100} for index, name in enumerate(names)
        ],
        "actions": [],
        "steps": [],
    }


def _add_player_ops(operations: list[dict]) -> list[dict]:
    return [op for op in operations if op.get("method") == "addPlayer"]


class TestSeatNumbering:
    def test_the_first_player_is_not_seated_at_zero(self) -> None:
        """Seat 0 is what the HUD read as an empty chair."""
        operations = build_hand_operations(_hand_data("v8guy", "RezaG", "edinapoker"))

        seats = [op["args"][0] for op in _add_player_ops(operations)]

        assert 0 not in seats
        assert seats == [1, 2, 3]

    def test_every_player_keeps_their_own_seat(self) -> None:
        operations = build_hand_operations(_hand_data("v8guy", "RezaG", "edinapoker"))

        seated = [(op["args"][0], op["args"][1]) for op in _add_player_ops(operations)]

        assert seated == [(1, "v8guy"), (2, "RezaG"), (3, "edinapoker")]

    def test_a_missing_seat_index_is_passed_through_untouched(self) -> None:
        data = _hand_data("v8guy")
        data["players"][0]["seat_idx"] = None

        operations = build_hand_operations(data)

        assert _add_player_ops(operations)[0]["args"][0] is None


class TestOccupancy:
    @staticmethod
    def _occupied(stat_dict: dict) -> list[int]:
        seats = AuxSeats.__new__(AuxSeats)
        seats.hud = SimpleNamespace(stat_dict=stat_dict)
        return seats._occupied_seats()

    def test_seat_zero_counts_as_occupied(self) -> None:
        """`if seat:` dropped this player; `if seat is not None:` keeps them."""
        occupied = self._occupied({1: {"seat": 0}, 2: {"seat": 1}, 3: {"seat": 2}})

        assert occupied == [0, 1, 2]

    def test_an_absent_seat_is_still_skipped(self) -> None:
        occupied = self._occupied({1: {"seat": None}, 2: {"seat": 3}})

        assert occupied == [3]

    def test_no_player_is_lost_from_a_full_table(self) -> None:
        stat_dict = {index: {"seat": index} for index in range(9)}

        assert len(self._occupied(stat_dict)) == 9
