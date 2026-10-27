"""Regression tests for the currency symbol in a PokerStars finishing list (#624).

The currency group of ``re_player_stars`` and ``re_player_rio`` used to be
written ``\\[{LS}]``. ``LS`` is an alternation (``\\$|€|£|...``), not a set of
characters, so the group read "``[$``" or "``€``" or "``£``"...: a plain ``$``
never matched and every dollar prize was stored as 0, while euro and pound
prizes worked.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.PokerStarsSummary import PokerStarsSummary

SAMPLE = (
    Path(__file__).resolve().parents[1]
    / "regression-test-files"
    / "summaries"
    / "Stars"
    / "6+Holdem-3max-STT-USD-1.00-201907.txt"
)


@pytest.fixture(scope="module")
def config() -> Config:
    # The repository template, never the user's own ~/.fpdb configuration.
    return Config(file="HUD_config.xml")


def parse(text: str, config: Config) -> PokerStarsSummary:
    # A real db=None would open the user's database; parsing never touches it.
    return PokerStarsSummary(
        db=MagicMock(),
        config=config,
        siteName="PokerStars",
        summaryText=text,
        builtFrom="IMAP",
    )


def test_a_dollar_prize_is_read(config: Config) -> None:
    summary = parse(SAMPLE.read_text(encoding="utf-8"), config)

    assert summary.currency == "USD"
    assert summary.winnings == {"freddie10248": [300], "mignolinu": [0], "TommyD38": [0]}
    assert summary.ranks == {"freddie10248": [1], "mignolinu": [2], "TommyD38": [3]}
    assert summary.winningsCurrency["freddie10248"] == ["USD"]


@pytest.mark.parametrize(("symbol", "iso"), [("€", "EUR"), ("£", "GBP")])
def test_euro_and_pound_prizes_are_unchanged(config: Config, symbol: str, iso: str) -> None:
    text = SAMPLE.read_text(encoding="utf-8").replace("$", symbol).replace("USD", iso)

    summary = parse(text, config)

    assert summary.currency == iso
    assert summary.winnings == {"freddie10248": [300], "mignolinu": [0], "TommyD38": [0]}
    assert summary.winningsCurrency["freddie10248"] == [iso]
