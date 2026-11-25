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


# --------------------------------------------------------------------------
# Room money that has no action row
# --------------------------------------------------------------------------


def test_a_winamax_splash_comes_back_in_the_pot(importer, fresh_db, legacy_config, tmp_path, caplog) -> None:
    """The Escape splash is room money: no one posts it, so HandsActions has no
    row for it, only Hands.splashPot. Rebuilding the pot from the actions alone
    left it 0.10 short of what the winner collected, logged "Collected amount
    exceeds total pot" and showed the hand with no rake.
    """
    from fpdb_3_legacy.WinamaxToFpdb import Winamax

    source = FIXTURES / "winamax" / "plo_escape_splash.txt"
    parsed = Winamax(config=legacy_config, in_path=str(source), autostart=True).getProcessedHands()[0]

    copy = tmp_path / source.name
    shutil.copy(source, copy)
    importer.addImportFile(str(copy), "Winamax")
    assert importer.runImport()[0] == 1

    cursor = fresh_db.get_cursor()
    cursor.execute("SELECT id FROM Hands")
    (hand_id,) = cursor.fetchone()
    with caplog.at_level("WARNING"):
        rebuilt = hand_factory(hand_id, legacy_config, fresh_db)

    assert parsed.rake == Decimal("0.01")
    assert rebuilt.totalpot == parsed.totalpot
    assert rebuilt.rake == parsed.rake
    assert "exceeds total pot" not in caplog.text


# --------------------------------------------------------------------------
# PHH trimmed / layered antes (#886)
# --------------------------------------------------------------------------

_PHH_TRIMMED_SHORT_ANTE = """
variant = "NT"
antes = [10, 10, 10]
blinds_or_straddles = [1, 2, 0]
min_bet = 2
starting_stacks = [5, 100, 100]
ante_trimming_status = true
actions = [
  "d dh p1 AsAh",
  "d dh p2 2c3d",
  "d dh p3 KsKh",
  "p3 cbr 6",
  "p2 f",
  "d db 7c4d2s",
  "d db Jh",
  "d db 9c",
  "p1 sm AsAh",
  "p3 sm KsKh",
]
"""

_PHH_UNEVEN_TRIMMED_ANTES = _PHH_TRIMMED_SHORT_ANTE.replace("antes = [10, 10, 10]", "antes = [10, 20, 10]")

_PHH_HETEROGENEOUS_FOLDED_ANTE = """
variant = "NT"
antes = [10, 10, 0]
blinds_or_straddles = [1, 2, 0]
min_bet = 2
starting_stacks = [12, 100, 100]
ante_trimming_status = true
actions = [
  "d dh p1 AsAh",
  "d dh p2 2c3d",
  "d dh p3 KsKh",
  "p3 cbr 6",
  "p1 cc",
  "p2 f",
  "d db 7c4d2s",
  "d db Jh",
  "d db 9c",
  "p1 sm AsAh",
  "p3 sm KsKh",
]
winnings = [26, 0, 0]
"""

_PHH_STUD_TRIMMED_COMPLETE = """
variant = "F7S"
antes = [10, 10, 10]
bring_in = 2
small_bet = 5
big_bet = 10
starting_stacks = [5, 100, 100]
ante_trimming_status = true
actions = [
  "d dh p1 AsAhAc",
  "d dh p2 2c3d4h",
  "d dh p3 KsKhKd",
  "p2 pb",
  "p3 cbr 5",
  "p2 f",
  "d dh p1 2d",
  "d dh p3 7c",
  "d dh p1 3s",
  "d dh p3 Jh",
  "d dh p1 4c",
  "d dh p3 9c",
  "d dh p1 5h",
  "d dh p3 Qc",
  "p1 sm AsAhAc",
  "p3 sm KsKhKd",
]
winnings = [15, 0, 14]
"""


def _import_phh_and_reload(importer: Any, db: Any, config: Any, tmp_path: Path, text: str) -> tuple[Any, Any]:
    import tomllib

    from fpdb_3_legacy.phh_import import PHHDocument, build_hand

    hand_path = tmp_path / "layered_ante.phh"
    hand_path.write_text(text, encoding="utf-8")
    parsed = build_hand(PHHDocument(str(hand_path), "hand", 1, tomllib.loads(text)))
    parsed.totalPot()

    assert importer.addImportFile(str(hand_path))
    stored, duplicates, *_rest = importer.runImport()
    assert (stored, duplicates) == (1, 0)

    cursor = db.get_cursor()
    cursor.execute("SELECT id FROM Hands ORDER BY id DESC LIMIT 1")
    (hand_id,) = cursor.fetchone()
    rebuilt = hand_factory(hand_id, config, db)
    assert rebuilt is not None
    return parsed, rebuilt


def test_trimmed_short_ante_keeps_side_pots_and_net_collected_on_reload(
    importer, fresh_db, legacy_config, tmp_path
) -> None:
    parsed, rebuilt = _import_phh_and_reload(
        importer,
        fresh_db,
        legacy_config,
        tmp_path,
        _PHH_TRIMMED_SHORT_ANTE + "winnings = [15, 0, 14]\n",
    )

    assert rebuilt.layeredAntes is True
    assert sum(rebuilt.pot.common.values()) == 0
    assert rebuilt.pot.pots == [(Decimal("15"), {"p1", "p2", "p3"}), (Decimal("14"), {"p2", "p3"})]
    assert rebuilt.pot.returned == {"p3": Decimal("4")}
    assert rebuilt.totalpot == Decimal("29")
    assert rebuilt.rake == Decimal("0")

    parsed.calculate_net_collected()
    rebuilt.calculate_net_collected()
    expected_net = {"p1": Decimal("10"), "p2": Decimal("-12"), "p3": Decimal("2")}
    assert parsed.net_collected == expected_net
    assert rebuilt.net_collected == expected_net


def test_uneven_trimmed_antes_match_importer_pots_on_reload(importer, fresh_db, legacy_config, tmp_path) -> None:
    parsed, rebuilt = _import_phh_and_reload(
        importer,
        fresh_db,
        legacy_config,
        tmp_path,
        _PHH_UNEVEN_TRIMMED_ANTES + "winnings = [15, 0, 14]\n",
    )

    assert rebuilt.layeredAntes is True
    assert rebuilt.pot.pots == parsed.pot.pots
    assert rebuilt.pot.antes == parsed.pot.antes
    assert rebuilt.pot.committed == parsed.pot.committed
    assert rebuilt.pot.returned == parsed.pot.returned
    assert rebuilt.totalpot == parsed.totalpot
    assert rebuilt.rake == parsed.rake == Decimal("0")


def test_untrimmed_short_ante_stays_pooled_on_reload(importer, fresh_db, legacy_config, tmp_path) -> None:
    untrimmed = _PHH_TRIMMED_SHORT_ANTE.replace("ante_trimming_status = true\n", "") + "winnings = [25, 0, 4]\n"
    parsed, rebuilt = _import_phh_and_reload(importer, fresh_db, legacy_config, tmp_path, untrimmed)

    assert rebuilt.layeredAntes is False
    assert sum(rebuilt.pot.common.values()) == Decimal("25")
    assert rebuilt.pot.pots == parsed.pot.pots
    assert rebuilt.totalpot == parsed.totalpot == Decimal("29")
    assert rebuilt.rake == Decimal("0")


def test_heterogeneous_layered_ante_returns_uncalled_bet_to_bettor_not_folded_ante(
    importer, fresh_db, legacy_config, tmp_path
) -> None:
    parsed, rebuilt = _import_phh_and_reload(
        importer, fresh_db, legacy_config, tmp_path, _PHH_HETEROGENEOUS_FOLDED_ANTE
    )

    assert rebuilt.layeredAntes is True
    assert rebuilt.pot.returned == {"p3": Decimal("4")}
    assert (
        rebuilt.pot.committed
        == parsed.pot.committed
        == {
            "p1": Decimal("12"),
            "p2": Decimal("12"),
            "p3": Decimal("2"),
        }
    )
    assert rebuilt.pot.pots == parsed.pot.pots == [(Decimal("6"), {"p1", "p2", "p3"}), (Decimal("20"), {"p1", "p2"})]
    assert rebuilt.totalpot == parsed.totalpot == Decimal("26")
    assert rebuilt.rake == Decimal("0")


def test_stud_trimmed_ante_with_complete_keeps_side_pots_and_uncalled_return_on_reload(
    importer, fresh_db, legacy_config, tmp_path
) -> None:
    parsed, rebuilt = _import_phh_and_reload(importer, fresh_db, legacy_config, tmp_path, _PHH_STUD_TRIMMED_COMPLETE)

    assert rebuilt.layeredAntes is True
    assert sum(rebuilt.pot.common.values()) == 0
    assert rebuilt.pot.returned == parsed.pot.returned == {"p3": Decimal("3")}
    assert rebuilt.pot.pots == parsed.pot.pots == [(Decimal("15"), {"p1", "p2", "p3"}), (Decimal("14"), {"p2", "p3"})]
    assert rebuilt.totalpot == parsed.totalpot == Decimal("29")
    assert rebuilt.rake == Decimal("0")


def test_apply_layered_ante_uncalled_handles_single_bettor_street() -> None:
    from fpdb_3_legacy.Hand import HoldemOmahaHand

    hand = HoldemOmahaHand.__new__(HoldemOmahaHand)
    hand.actionStreets = ["BLINDSANTES", "PREFLOP", "FLOP"]
    hand.bets = {
        "BLINDSANTES": {"p1": [Decimal("5")], "p2": [Decimal("10")]},
        "PREFLOP": {"p1": [], "p2": []},
        "FLOP": {"p2": [Decimal("6")]},
    }
    returned: list[tuple[str, str, str]] = []
    hand.addUncalled = lambda street, player, amount: returned.append((street, player, amount))

    hand._apply_layered_ante_uncalled()

    assert returned == [("FLOP", "p2", "6")]
