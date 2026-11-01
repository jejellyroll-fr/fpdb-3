"""Cross-checking a captured SwC hand against the room's own text history.

SwC writes text histories for some game families and not others, so where both
exist they describe the same hand and must agree. These tests pin the comparison
itself — that it catches each kind of drift and stays quiet when the two views
match — so it can be trusted the moment it is pointed at real paired data.

The paired fixtures themselves are not in the tree: a capture archive and the
text history of the *same* session can only come from real play. Drop a pair
into ``tests/fixtures/hands/swc_paired/`` and ``test_paired_fixtures_agree``
starts covering it; until then it skips and says so.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from fpdb_3_legacy.swc_crosscheck import compare_hands

PAIRED_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "hands" / "swc_paired"


def _hand(**overrides):
    hand = {
        "hand_id": "299449673",
        "players": [
            {"name": "v8guy", "seat": 1},
            {"name": "RezaG", "seat": 2},
            {"name": "tortuga", "seat": 3},
        ],
        "board": ["8c", "Js", "8h", "Th"],
        "totalpot": Decimal("0.54"),
        "collectees": {"tortuga": Decimal("0.52")},
    }
    hand.update(overrides)
    return hand


class TestAgreement:
    def test_identical_views_report_nothing(self) -> None:
        assert compare_hands(_hand(), _hand()) == []

    def test_money_within_rounding_is_not_a_discrepancy(self) -> None:
        """The text history rounds to the table currency; the capture counts units."""
        captured = _hand(totalpot=Decimal("0.5401"), collectees={"tortuga": Decimal("0.5199")})

        assert compare_hands(_hand(), captured) == []

    def test_a_hand_object_and_a_dict_compare_the_same(self) -> None:
        class TextHand:
            handid = "299449673"
            players = [(1, "v8guy", "3.74"), (2, "RezaG", "4.11"), (3, "tortuga", "1.67")]
            board = {"FLOP": ["8c", "Js", "8h"], "TURN": ["Th"], "RIVER": []}
            totalpot = Decimal("0.54")
            collectees = {"tortuga": Decimal("0.52")}

        assert compare_hands(TextHand(), _hand()) == []


class TestDrift:
    def test_a_different_hand_id_is_reported(self) -> None:
        problems = compare_hands(_hand(), _hand(hand_id="999"))

        assert any("hand id" in problem for problem in problems)

    def test_a_missing_player_is_reported(self) -> None:
        captured = _hand(players=[{"name": "RezaG", "seat": 2}, {"name": "tortuga", "seat": 3}])

        problems = compare_hands(_hand(), captured)

        assert any("v8guy" in problem for problem in problems)

    def test_a_shifted_seat_is_reported(self) -> None:
        """The seat-zero bug shifted every player by one; this is what catches it."""
        captured = _hand(
            players=[
                {"name": "v8guy", "seat": 0},
                {"name": "RezaG", "seat": 1},
                {"name": "tortuga", "seat": 2},
            ],
        )

        problems = compare_hands(_hand(), captured)

        assert len(problems) == 3
        assert all("seat of" in problem for problem in problems)

    def test_a_wrong_board_is_reported(self) -> None:
        problems = compare_hands(_hand(), _hand(board=["8c", "Js", "8h", "2d"]))

        assert any("board" in problem for problem in problems)

    def test_a_short_pot_is_reported(self) -> None:
        """The GGPoker class of bug: a blind never reaching the pot."""
        problems = compare_hands(_hand(), _hand(totalpot=Decimal("0.50")))

        assert any("total pot" in problem for problem in problems)

    def test_wrong_winnings_are_reported(self) -> None:
        problems = compare_hands(_hand(), _hand(collectees={"tortuga": Decimal("0.10")}))

        assert any("winnings of tortuga" in problem for problem in problems)

    def test_a_winner_the_capture_missed_is_reported(self) -> None:
        problems = compare_hands(_hand(), _hand(collectees={}))

        assert any("winnings of tortuga" in problem for problem in problems)


@pytest.mark.skipif(
    not PAIRED_DIR.is_dir() or not any(PAIRED_DIR.glob("*.raw")),
    reason=(
        "no paired SwC fixtures: a capture archive and the text history of the same "
        "session have to come from real play. Add <name>.raw and <name>.txt under "
        "tests/fixtures/hands/swc_paired/ to enable this check."
    ),
)
def test_paired_fixtures_agree() -> None:
    from fpdb_3_legacy.Configuration import Config
    from fpdb_3_legacy.SealsWithClubsToFpdb import SealsWithClubs
    from fpdb_3_legacy.swc_native_capture import (
        iter_protocol_messages,
        normalize_native_hands,
        read_records_since,
    )

    for archive in sorted(PAIRED_DIR.glob("*.raw")):
        text_file = archive.with_suffix(".txt")
        assert text_file.exists(), f"{archive.name} has no matching text history"

        text_hands = {
            str(hand.handid): hand
            for hand in SealsWithClubs(config=Config(), in_path=str(text_file), autostart=True).getProcessedHands()
        }
        records, _ = read_records_since(archive, 0)
        captured_hands = normalize_native_hands(
            list(iter_protocol_messages(iter(records))),
            raw_ref=str(archive),
        )

        for captured in captured_hands:
            hand_id = str(captured.get("hand_id"))
            if hand_id not in text_hands:
                continue  # the room wrote no text history for this game family
            problems = compare_hands(text_hands[hand_id], captured)
            assert not problems, f"{archive.name} hand {hand_id}:\n  " + "\n  ".join(problems)
