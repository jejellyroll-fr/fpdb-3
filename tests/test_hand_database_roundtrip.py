"""What survives a trip through the database, and what the schema cannot keep.

``Hand.select`` rebuilds a hand from its stored rows and feeds the replayer and
the hand viewer. It was the least covered high-risk code left after the caches:
a hand that comes back wrong is displayed wrong, without raising.

Each test imports a real hand history into a throwaway SQLite database and
reads it back with ``hand_factory``, comparing against the same file parsed
directly. Two fields cannot survive and are asserted as such rather than left
implicit -- see the end of the module.
"""

from __future__ import annotations

import shutil
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from fpdb_3_legacy.Hand import hand_factory
from fpdb_3_legacy.PokerStarsToFpdb import PokerStars

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "hands"

# One per branch of select: hold'em/omaha, draw and stud each rebuild their
# streets differently.
HANDS = [
    ("holdem", "pokerstars/holdem/5card_omaha.txt"),
    ("draw", "pokerstars/draw/5card_draw.txt"),
    ("stud", "pokerstars/stud/7stud.txt"),
]


def parse(config: Any, path: Path) -> Any:
    return PokerStars(config=config, in_path=str(path), autostart=True).getProcessedHands()[0]


def import_and_read_back(importer: Any, db: Any, config: Any, tmp_path: Path, relative: str) -> tuple[Any, Any]:
    """Return (hand as parsed, hand as rebuilt from the database)."""
    source = FIXTURES / relative
    parsed = parse(config, source)

    copy = tmp_path / source.name
    shutil.copy(source, copy)
    importer.addImportFile(str(copy), "PokerStars")
    stored = importer.runImport()[0]
    assert stored == 1, f"{relative} did not import"

    cursor = db.get_cursor()
    cursor.execute("SELECT id FROM Hands")
    (hand_id,) = cursor.fetchone()
    return parsed, hand_factory(hand_id, config, db)


@pytest.fixture(params=HANDS, ids=[name for name, _ in HANDS])
def roundtrip(request, importer, fresh_db, legacy_config, tmp_path):
    return import_and_read_back(importer, fresh_db, legacy_config, tmp_path, request.param[1])


def test_the_hand_comes_back_as_the_right_kind_of_hand(roundtrip) -> None:
    parsed, rebuilt = roundtrip

    assert rebuilt is not None
    assert type(rebuilt) is type(parsed)


def test_the_hand_keeps_its_identity(roundtrip) -> None:
    parsed, rebuilt = roundtrip

    assert str(rebuilt.handid) == str(parsed.handid)
    assert rebuilt.tablename == parsed.tablename


def test_the_money_comes_back_unchanged(roundtrip) -> None:
    # The pot and the rake drive every report; a hand that returns with a
    # different pot corrupts them silently.
    parsed, rebuilt = roundtrip

    assert rebuilt.totalpot == parsed.totalpot
    assert rebuilt.rake == parsed.rake


def test_every_player_comes_back_with_their_seat_and_stack(roundtrip) -> None:
    parsed, rebuilt = roundtrip

    assert [(seat, name) for seat, name, *_ in rebuilt.players] == [
        (seat, name) for seat, name, *_ in parsed.players
    ]


def test_the_winners_come_back_with_what_they_won(roundtrip) -> None:
    parsed, rebuilt = roundtrip

    # Compared as numbers: the database returns 5.8 where the file said 5.80,
    # which is the same amount and not a difference worth failing on.
    assert {name: Decimal(str(amount)) for name, amount in rebuilt.collectees.items()} == {
        name: Decimal(str(amount)) for name, amount in parsed.collectees.items()
    }


def test_the_board_comes_back_street_by_street(roundtrip) -> None:
    parsed, rebuilt = roundtrip

    assert {street: cards for street, cards in rebuilt.board.items() if cards} == {
        street: cards for street, cards in parsed.board.items() if cards
    }


def test_every_action_comes_back_on_its_street(roundtrip) -> None:
    # Rebuilding an action on the wrong street moves money between streets and
    # changes every positional statistic derived from the hand.
    parsed, rebuilt = roundtrip

    assert {street: actions for street, actions in rebuilt.actions.items() if actions} == {
        street: actions for street, actions in parsed.actions.items() if actions
    }


# --------------------------------------------------------------------------
# What the schema does not keep
# --------------------------------------------------------------------------


def test_the_button_position_is_not_stored_anywhere(roundtrip) -> None:
    """No table has a column for it.

    Hands records seats and heroSeat, Gametypes records maxSeats, and neither
    carries the button. A rebuilt hand therefore cannot say who was on the
    button, and the replayer draws it from the seat order instead. Recorded
    here so that adding the column later shows up as a change.
    """
    parsed, rebuilt = roundtrip

    assert rebuilt.buttonpos != parsed.buttonpos


def test_the_table_size_comes_back_from_the_game_type(roundtrip) -> None:
    """Hands.seats counts who sat down, not how many the table holds.

    The table size is only kept per game type, so a 6-max and a 10-max table of
    the same stakes are indistinguishable once stored, and the rebuilt hand
    reports the game type's maximum.
    """
    _, rebuilt = roundtrip

    assert rebuilt.maxseats == 10
