"""ACR/WPN Spinz (lottery SnG) support.

Two regressions covered:
- SPINZID hand-history files were not recognised as a tournament type of
  their own: hand.tourneyName stayed None (nothing in Tourneys.tourneyName),
  so nothing downstream could tell a Spinz from a scheduled MTT;
- the tournament window-title regex only knew the scheduled-MTT format
  (", Table N - ... (tourno)"), which Spinz tables do not use, so the HUD
  never found the table ("Can't find table ... " in HUD-errors).
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.WinningToFpdb import Winning

SPINZ_PATH = (
    r"C:\ACR Poker\handHistory\edinapoker"
    r"\HH20260721 SPINZID-G35539941T1 TN-$0{FULLSTOP}25 Spinz Holdem"
    r" GAMETYPE-Hold'em LIMIT-no CUR-REAL OND-F BUYIN-25.txt"
)

MTT_PATH = (
    r"C:\ACR Poker\handHistory\edinapoker"
    r"\HH20260721 SCHEDULEDID-G35528538T3 TN-Lightning PKO - $6 GTD"
    r" GAMETYPE-Hold'em LIMIT-no CUR-REAL OND-F BUYIN-0.txt"
)

SPINZ_HAND = """Game Hand #2783336817 - Tournament #35539941 - Holdem (No Limit) - Level 1 (10.00/20.00) - 2026/07/21 13:37:40 UTC
Table '1' 3-max Seat #3 is the button
Seat 1: villain1 (300.00)
Seat 2: villain2 (300.00)
Seat 3: hero (300.00)
villain1 posts the small blind 10.00
villain2 posts the big blind 20.00
*** HOLE CARDS ***
Dealt to hero [7d Jd]
hero raises 40.00 to 40.00
villain1 folds
villain2 folds
Uncalled bet (20.00) returned to hero
hero does not show
*** SUMMARY ***
Total pot 30.00
Seat 3: hero did not show and won 30.00
"""


@pytest.fixture(scope="module")
def config() -> Config:
    return Config()


def _converter(config: Config, path: str) -> Winning:
    parser = Winning(config, autostart=False)
    parser.in_path = path
    parser.version = 2
    return parser


class TestSpinzHandInfo:
    def test_tourney_name_extracted_from_spinz_filename(self, config: Config) -> None:
        parser = _converter(config, SPINZ_PATH)
        assert parser._tourney_name_from_path() == "$0.25 Spinz Holdem"

    def test_fullstop_unescaped_in_scheduled_names_too(self, config: Config) -> None:
        parser = _converter(
            config,
            MTT_PATH.replace("Lightning PKO - $6 GTD", "Deep $12{FULLSTOP}50 GTD"),
        )
        assert parser._tourney_name_from_path() == "Deep $12.50 GTD"

    def test_spinzid_recognised_as_file_type(self, config: Config) -> None:
        parser = _converter(config, SPINZ_PATH)
        match = parser.re_File2.search(parser.in_path)
        assert match is not None
        assert match.group("TYPE") == "SPINZID"

    def test_read_hand_info_sets_spinz_tournament_fields(self, config: Config) -> None:
        parser = _converter(config, SPINZ_PATH)
        hand = SimpleNamespace(handText=SPINZ_HAND, gametype={"type": "tour"}, maxseats=None)
        parser._readHandInfo2(hand)

        assert hand.tourNo == "35539941"
        assert hand.tablename == "1"
        assert hand.tourneyName == "$0.25 Spinz Holdem"
        assert hand.isSng is True
        assert hand.isLottery is True
        assert hand.buyinCurrency == "USD"
        assert hand.buyin == 25
        assert hand.maxseats == 3


class TestSpinzTableTitle:
    TOURNAMENT = "35539941"

    def _regex(self) -> str:
        return Winning.getTableTitleRe(
            "tour",
            tournament=self.TOURNAMENT,
            table_number="1",
            tourney_name="$0.25 Spinz Holdem",
        )

    @pytest.mark.parametrize(
        "title",
        [
            # Real title captured live on 2026-07-22 (no branding at all; the
            # blinds part changes with the level, the number does not).
            "$0.25 - No Limit - 10 / 20 Hold'em (35539941)",
            "$0.25 - No Limit - 15 / 30 Hold'em (35539941)",
            "$0.25 Spinz Holdem - Table 1 (35539941)",  # branding + tournament number
            "Spinz $0.25 - Table 1",  # branding + amount, dot separator
            "Jackpot Poker $0,25 - Table 1",  # branding + amount, comma separator
            "$0.25 Spinz Holdem, Table 1 - No Limit Holdem - (35539941)",  # classic MTT format
        ],
        ids=[
            "real-title-level1",
            "real-title-level2",
            "brand-and-number",
            "brand-and-dot-amount",
            "brand-and-comma-amount",
            "classic-format",
        ],
    )
    def test_spinz_titles_match(self, title: str) -> None:
        assert re.search(self._regex(), title, re.IGNORECASE) is not None

    @pytest.mark.parametrize(
        "title",
        [
            "Lightning PKO - $6 GTD, Table 3 - No Limit Holdem - (35528538)",  # another tournament
            "$0.25 - No Limit - 10 / 20 Hold'em (35548425)",  # another Spinz, same stake
            "ACR Poker",  # client main window
            "ACR Poker Lobby Logged in as edinapoker",  # real lobby title
            "Arimo - Omaha PL - $0.01/$0.02",  # cash table
        ],
        ids=["other-tournament", "other-spinz-same-stake", "client-window", "lobby", "cash-table"],
    )
    def test_unrelated_titles_do_not_match(self, title: str) -> None:
        assert re.search(self._regex(), title, re.IGNORECASE) is None

    def test_scheduled_mtt_regex_unchanged(self) -> None:
        regex = Winning.getTableTitleRe(
            "tour",
            tournament="35528538",
            table_number="3",
            tourney_name="Lightning PKO - $6 GTD",
        )
        assert regex == r", Table 3\s\-.*\s\(35528538\)"

    def test_tour_without_name_keeps_classic_regex(self) -> None:
        """DB rows imported before this fix have tourneyName=None."""
        regex = Winning.getTableTitleRe("tour", tournament="35539941", table_number="1")
        assert regex == r", Table 1\s\-.*\s\(35539941\)"

    def test_cash_regex_unchanged(self) -> None:
        assert Winning.getTableTitleRe("ring", "Arimo") == "Arimo"
