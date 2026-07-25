"""File-by-file golden regression harness for actively supported poker rooms."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from fpdb_3_legacy.AbsoluteToFpdb import Absolute
from fpdb_3_legacy.BetfairToFpdb import Betfair
from fpdb_3_legacy.BetOnlineToFpdb import BetOnline
from fpdb_3_legacy.BossToFpdb import Boss
from fpdb_3_legacy.BovadaToFpdb import Bovada
from fpdb_3_legacy.CakeToFpdb import Cake
from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.EnetToFpdb import Enet
from fpdb_3_legacy.EntractionToFpdb import Entraction
from fpdb_3_legacy.EverestToFpdb import Everest
from fpdb_3_legacy.EverleafToFpdb import Everleaf
from fpdb_3_legacy.FulltiltToFpdb import Fulltilt
from fpdb_3_legacy.GGPokerToFpdb import GGPoker
from fpdb_3_legacy.iPoker.base import iPoker
from fpdb_3_legacy.KingsClubToFpdb import KingsClub
from fpdb_3_legacy.MergeToFpdb import Merge
from fpdb_3_legacy.MicrogamingToFpdb import Microgaming
from fpdb_3_legacy.OnGameToFpdb import OnGame
from fpdb_3_legacy.PacificPokerToFpdb import PacificPoker
from fpdb_3_legacy.PartyPokerToFpdb import PartyPoker
from fpdb_3_legacy.PkrToFpdb import Pkr
from fpdb_3_legacy.PokerStarsToFpdb import PokerStars
from fpdb_3_legacy.PokerTrackerToFpdb import PokerTracker
from fpdb_3_legacy.SealsWithClubsToFpdb import SealsWithClubs
from fpdb_3_legacy.UnibetToFpdb import Unibet
from fpdb_3_legacy.WinamaxToFpdb import Winamax
from fpdb_3_legacy.WinningToFpdb import Winning
from tests.helpers.parser_regression import file_snapshot, snapshot_digest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "hands"
REGRESSION_FILES = ROOT / "regression-test-files" / "cash"
MANIFEST_PATH = FIXTURES / "live_parser_snapshots.json"

ROOMS = {
    "bovada": (Bovada, sorted((FIXTURES / "bovada").rglob("*.txt"))),
    "cake": (Cake, sorted((FIXTURES / "cake").rglob("*.txt"))),
    "ggpoker": (GGPoker, [FIXTURES / "ggpoker" / "plo_cash.txt"]),
    "kingclub": (KingsClub, sorted((FIXTURES / "kingclub").rglob("*.txt"))),
    "pacific": (PacificPoker, sorted((FIXTURES / "pacific").rglob("*.txt"))),
    "partypoker": (PartyPoker, sorted((FIXTURES / "partypoker").rglob("*.txt"))),
    "pokerstars": (PokerStars, sorted((FIXTURES / "pokerstars").rglob("*.txt"))),
    "unibet": (Unibet, sorted((FIXTURES / "unibet").rglob("*.txt"))),
    "winamax": (Winamax, [FIXTURES / "winamax" / "nlhe_cash.txt"]),
    "winning": (Winning, sorted((FIXTURES / "winning").rglob("*.txt"))),
}


def test_fulltilt_player_regex_compilation_does_not_mutate_class_metadata() -> None:
    parser = Fulltilt.__new__(Fulltilt)
    parser.compiledPlayers = set()
    original_substitutions = dict(Fulltilt.substitutions)

    parser.compilePlayerRegexs(SimpleNamespace(players=[(1, "Alice", 100), (2, "Bob", 100)]))

    assert Fulltilt.substitutions == original_substitutions
    assert "PLAYERS" not in Fulltilt.substitutions


# Every hand-history file the project ships, parsed by the converter of its
# room. The corpus was already versioned but only one file per room was wired
# in for most of them; sweeping the directories is what turns the harness into
# a regression net rather than a smoke test.
REGRESSION_SITES = {
    "Absolute": Absolute,
    "BetOnline": BetOnline,
    "Betfair": Betfair,
    "Boss": Boss,
    "Bovada": Bovada,
    "Cake": Cake,
    "Enet": Enet,
    "Entraction": Entraction,
    "Everest": Everest,
    "Everleaf": Everleaf,
    "FTP": Fulltilt,
    "KingsClub": KingsClub,
    "Merge": Merge,
    "Microgaming": Microgaming,
    "OnGame": OnGame,
    "PKR": Pkr,
    "PacificPoker": PacificPoker,
    "PartyPoker": PartyPoker,
    "PokerTracker": PokerTracker,
    "SealsWithClubs": SealsWithClubs,
    "Stars": PokerStars,
    "Unibet": Unibet,
    "Winamax": Winamax,
    "Winning": Winning,
    "iPoker": iPoker,
}

CASES = [
    (f"{room}/{path.relative_to(FIXTURES / room).as_posix()}", parser_class, path)
    for room, (parser_class, paths) in ROOMS.items()
    for path in paths
]
CASES += [
    (f"regression/{site}/{path.relative_to(REGRESSION_FILES / site).as_posix()}", parser_class, path)
    for site, parser_class in REGRESSION_SITES.items()
    for path in sorted(
        candidate
        for candidate in (REGRESSION_FILES / site).rglob("*")
        if candidate.is_file() and candidate.suffix.lower() in {".txt", ".xml"}
    )
]

# Files every converter deliberately refuses, each for the reason its name
# states: cancelled and dead hands, truncated exports, an observed hand with no
# stacks. The whole PartyPoker group shares one cause -- an anonymised player
# acts without appearing in the seat preamble, so the converter raises
# FpdbHandPartialError instead of inventing a seat.
#
# Listing them keeps the refusals visible. A file that starts, or stops,
# yielding hands fails this test by name rather than quietly moving a digest.
KNOWN_EMPTY = {
    "regression/Absolute/Flop/LHE-USD-25-50-200708.timeout.allin.txt",
    "regression/Bovada/Flop/NLHE-USD-5-10-201511.concatenated.partial.txt",
    "regression/Everest/Flop/NLHE-USD-0.50-1.00-201203.penalty.txt",
    "regression/FTP/Draw/3-Draw-Limit-USD-10-20-201101.Dead.hand.txt",
    "regression/FTP/Draw/3-Draw-Limit-USD-20-40-201101.Partial.txt",
    "regression/FTP/Flop/NLHE-6max-USD-25-50.200610.Observed.No.player.stacks.txt",
    "regression/KingsClub/Stud/2-7 Razz-USD-500-1000-202102.multi.pot.failure.txt",
    "regression/Merge/Draw/3-Draw-PL-USD-0.05-0.10-201102.Cancelled.hand.txt",
    "regression/Merge/Flop/NLHE-6max-USD-0.02-0.04.201107.no.community.xml",
    "regression/Merge/Flop/NLHE-6max-USD-0.10-0.25-201208.player.not.in.preamble.txt",
    "regression/Merge/Flop/NLHE-USD-0.02-0.04.201105.Player.not.in.preamble.acts.xml",
    "regression/PKR/Flop/NLHE-USD-3.00-6.00-201108.partial.txt",
    "regression/PacificPoker/Flop/NLHE-USD-50.00-100.00-201406.blank.player.names.txt",
    "regression/PartyPoker/Flop/NLHE-0.02-0.04-USD-201207.players.joining.leaving.txt",
    "regression/PartyPoker/Flop/NLHE-6max-USD-0.10-0.25-201212.unseated.big.blind.txt",
    "regression/PartyPoker/Flop/NLHE-6max-USD-0.10-0.25-201309.player.joins.and.posts.a.bb.txt",
    "regression/PartyPoker/Flop/NLHE-6max-USD-0.10-0.25-201309.player.joins.as.bb.txt",
    "regression/PartyPoker/Flop/NLHE-6max-USD-0.50-1.00-201301.partial.player.names.txt",
    "regression/PartyPoker/Flop/NLHE-6max-USD-5-10-201408.joins.and.posts.bb.txt",
    "regression/PartyPoker/Flop/NLHE-USD-0.02-0.04-20100811.unseatedPlayerActions.txt",
    "regression/PartyPoker/Flop/PLO8-6max-USD-1.00-2.00-201601.preamble.fatal.txt",
    "regression/Stars/Draw/3-Draw-Limit-USD-1-2-200809.Hand.cancelled.txt",
    "regression/Stars/Flop/LO8-6max-USD-0.05-0.10-20090315.Hand-cancelled.txt",
}

# The pot equation -- collected + rake == total pot -- holds for 2 850 of the
# 2 867 hands in the corpus. These files are the exceptions, in three groups:
#
#  * cash-out hands, where a player takes an insured payout instead of the pot,
#    so what is collected is deliberately not a share of it;
#  * third-party re-exports (HM1, "converted") whose summary line is already a
#    lossy rendering of the original;
#  * two BetOnline files and three synthetic PokerStars fixtures whose totals do
#    not reconcile and have not been explained -- genuine suspects.
#
# Anything outside this list must balance, so the corpus is actively checked
# rather than merely digested.
POT_EQUATION_EXCEPTIONS = {
    "pokerstars/draw/5card_draw.txt",
    "pokerstars/holdem/cashed_out.txt",
    "pokerstars/stud/7stud.txt",
    "regression/BetOnline/Flop/NLHE-10max-USD-0.01-0.02-201605.winner.no.show.txt",
    "regression/BetOnline/Flop/PLO-10max-USD-0.05-0.10-201209.txt",
    "regression/Stars/Flop/2025-NL-6max-USD-0.05-0.10.cashout.txt",
    "regression/Stars/Flop/6+Holdem-6max-USD-0.25-0.25.multiple.Cash.Out.txt",
    "regression/Stars/Flop/6-Card-PLO-6max-USD-0.05-0.10-202111.cash.out.txt",
    "regression/Stars/Flop/6-Card-PLO-6max-USD-0.10-0.25-202201.multiway.allin.deadcards.txt",
    "regression/Stars/Flop/6-Card-PLO-6max-USD-0.50-1.00-202004.Cash.Out.txt",
    "regression/Stars/Flop/6-Card-PLO-6max-USD-1.00-2.00-202004.Cash.Out.2.txt",
    "regression/Stars/Flop/NLHE-10max-USD-1.00-2.00-200910.HM1.export.raiseTo.txt",
    "regression/Stars/Flop/NLHE-10max-USD-1.00-2.00-200910.HM1.shows.one.txt",
    "regression/Stars/Flop/NLHE-6-max-USD-10-20-201701.converted.split.summary.txt",
    "regression/Stars/Flop/NLHE-6-max-USD-10-20-201701.pot1.converted.walk.txt",
    "regression/Stars/Flop/NLHE-6-max-USD-10-20-201701.pot2.converted.walk.txt",
    "regression/Stars/Flop/NLHE-6max-USD-3.00-6.00-201310.old.converted.walk.txt",
}


@pytest.fixture(scope="module")
def parser_config() -> Config:
    return Config()


@pytest.fixture(scope="module")
def golden_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize(("key", "parser_class", "hand_file"), CASES, ids=[case[0] for case in CASES])
def test_live_parser_file_matches_golden_snapshot(
    key: str,
    parser_class,
    hand_file: Path,
    parser_config: Config,
    golden_manifest: dict,
) -> None:
    parser = parser_class(config=parser_config, in_path=str(hand_file), autostart=True)
    snapshot = file_snapshot(parser.getProcessedHands())
    expected = golden_manifest[key]

    assert len(snapshot) == expected["hand_count"]
    assert snapshot_digest(snapshot) == expected["sha256"], json.dumps(snapshot, indent=2, sort_keys=True)


def test_live_parser_manifest_covers_every_fixture(golden_manifest: dict) -> None:
    expected_keys = {key for key, _, _ in CASES}
    assert set(golden_manifest) == expected_keys


def test_only_the_listed_fixtures_yield_no_hand(golden_manifest: dict) -> None:
    empty = {key for key, entry in golden_manifest.items() if entry["hand_count"] == 0}

    assert empty == KNOWN_EMPTY


def test_every_listed_refusal_is_still_a_fixture() -> None:
    assert KNOWN_EMPTY <= {key for key, _, _ in CASES}


def test_partypoker_conversion_does_not_open_a_database(parser_config: Config) -> None:
    hand_file = FIXTURES / "partypoker" / "stud" / "7stud.txt"
    parser = PartyPoker(config=parser_config, in_path=str(hand_file), autostart=True)

    assert parser.getProcessedHands()
    assert not hasattr(parser, "db")


def test_every_listed_pot_exception_is_still_a_fixture() -> None:
    assert POT_EQUATION_EXCEPTIONS <= {key for key, _, _ in CASES}


@pytest.mark.parametrize(
    ("key", "parser_class", "hand_file"),
    [case for case in CASES if case[0] not in POT_EQUATION_EXCEPTIONS],
    ids=[case[0] for case in CASES if case[0] not in POT_EQUATION_EXCEPTIONS],
)
def test_collected_plus_rake_matches_the_total_pot(key, parser_class, hand_file, parser_config) -> None:
    parser = parser_class(config=parser_config, in_path=str(hand_file), autostart=True)

    for hand in parser.getProcessedHands():
        collected = sum(Decimal(str(amount)) for amount in hand.collectees.values())
        rake = Decimal(str(hand.rake))
        total = Decimal(str(hand.totalpot))

        assert rake >= 0, f"{key} hand {hand.handid}: negative rake {rake}"
        assert abs((collected + rake) - total) <= Decimal("0.05"), (
            f"{key} hand {hand.handid}: collected {collected} + rake {rake} != pot {total}"
        )
