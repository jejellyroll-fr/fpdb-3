"""Tournament buy-in contracts for the PokerTracker converter."""

from __future__ import annotations

from pathlib import Path

import pytest

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.PokerTrackerToFpdb import PokerTracker

ROOT = Path(__file__).resolve().parents[1]
TOUR = ROOT / "regression-test-files" / "tour" / "PokerTracker" / "Flop"


@pytest.fixture(scope="module")
def parser_config() -> Config:
    return Config()


def _first_hand(config: Config, path: Path):
    hands = PokerTracker(config=config, in_path=str(path), autostart=True).getProcessedHands()
    assert hands, f"no hand parsed from {path.name}"
    return hands[0]


def _derived(tmp_path: Path, source: Path, replacements: dict[str, str]) -> Path:
    text = source.read_text(encoding="cp1252")
    for old, new in replacements.items():
        assert old in text, f"{old!r} not in {source.name}"
        text = text.replace(old, new)
    target = tmp_path / source.name
    target.write_text(text, encoding="cp1252")
    return target


def test_named_free_tournament_keeps_its_stated_buyin(parser_config: Config) -> None:
    # "$5 Free PLO Hero Arena" states "Buy-In: $5+$0.50": the word Free in the
    # table name does not make it a freeroll.
    hand = _first_hand(parser_config, TOUR / "PLO-USD-5-201202.Merge.all.in.blind.txt")

    assert hand.buyinCurrency == "USD"
    assert hand.buyin == 500
    assert hand.fee == 50


def test_freezeout_on_merge_is_not_a_freeroll(parser_config: Config, tmp_path: Path) -> None:
    # Merge is the only site that reads the table name, and "Freezeout" starts
    # with the same four letters as a freeroll.
    source = TOUR / "PLO-USD-5-201202.Merge.all.in.blind.txt"
    derived = _derived(tmp_path, source, {"$5 Free PLO Hero Arena": "$5 Freezeout PLO Arena"})

    hand = _first_hand(parser_config, derived)

    assert hand.buyinCurrency == "USD"
    assert hand.buyin == 500


def test_freeroll_named_tournament_has_no_buyin(parser_config: Config, tmp_path: Path) -> None:
    # The corpus holds no Merge freeroll, so derive one from a real hand.
    source = TOUR / "PLO-USD-5-201202.Merge.all.in.blind.txt"
    derived = _derived(tmp_path, source, {"$5 Free PLO Hero Arena": "$5 Freeroll PLO Arena"})

    hand = _first_hand(parser_config, derived)

    assert hand.buyinCurrency == "FREE"
    assert hand.buyin == 0
    assert hand.fee == 0


def test_progressive_knockout_buyin_splits_bounty_and_fee(parser_config: Config) -> None:
    # "Buy-In: EUR22,25 + EUR22,25 + EUR5,50" is buy-in + bounty + fee.
    hand = _first_hand(parser_config, TOUR / "NLHE-MTT-EUR-22.25-22.25-202104.KO.iPoker.txt")

    assert hand.buyinCurrency == "EUR"
    assert hand.isKO
    assert hand.koBounty == 2225
    assert hand.buyin == 4450
    assert hand.fee == 550


@pytest.mark.parametrize(
    ("filename", "currency", "buyin", "fee"),
    [
        ("NLHE-USD-SNG-2-201111.Merge.txt", "USD", 200, 20),
        # cp1252 euro sign in the header.
        ("NLHE-EUR-200-MTT-201901.iPoker.txt", "EUR", 91, 9),
    ],
)
def test_buyin_currency_comes_from_the_stated_symbol(
    parser_config: Config,
    filename: str,
    currency: str,
    buyin: int,
    fee: int,
) -> None:
    hand = _first_hand(parser_config, TOUR / filename)

    assert hand.buyinCurrency == currency
    assert hand.buyin == buyin
    assert hand.fee == fee
