"""iPoker hands as PokerTracker 4 stores them, in two shapes its text parser used to refuse (#814).

PT4 writes iPoker hands as ``GAME #…`` text, in its database and in *Export Hands*.
Two first lines were refused by ``PokerTrackerToFpdb.determineGameType``:

* fixed-limit hold'em, which PT4 writes ``Texas Hold'em L $0.10/$0.20``;
* a recent client's ``Version:… Uncalled:N``, where only ``Uncalled:Y`` was read.

They were 38 of the 3,230 iPoker cash hands of a real PT4 database. The fixture
holds one of each, anonymised with ``tools/anonymize_hh.py``.
"""

from __future__ import annotations

from pathlib import Path

from fpdb_3_legacy.PokerTrackerToFpdb import PokerTracker

FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "pokertracker_ipoker_gametypes"
    / "iPoker fixed limit and Uncalled N.txt"
)


def _hands(config) -> tuple[PokerTracker, list]:
    parser = PokerTracker(config, in_path=str(FIXTURE), autostart=False, sitename="iPoker")
    parser.start()
    return parser, parser.getProcessedHands()


def test_both_shapes_are_read_whole(legacy_config) -> None:
    parser, hands = _hands(legacy_config)

    assert (len(hands), parser.numErrors, parser.numPartial) == (2, 0, 0)


def test_l_is_fixed_limit_and_uncalled_n_keeps_the_game(legacy_config) -> None:
    _parser, hands = _hands(legacy_config)
    fixed_limit, pot_limit = hands

    assert (fixed_limit.gametype["category"], fixed_limit.gametype["limitType"]) == ("holdem", "fl")
    assert fixed_limit.gametype["currency"] == "USD"
    assert (pot_limit.gametype["category"], pot_limit.gametype["limitType"]) == ("omahahi", "pl")
    assert pot_limit.gametype["currency"] == "EUR"
