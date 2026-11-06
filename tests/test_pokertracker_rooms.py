"""PokerTracker's own export format: every hand is filed under its real room (#617).

One PokerTracker export carries Everest, iPoker, Merge and Microgaming hands,
and the converter reads the room from each hand's header. The golden snapshots
in ``test_live_parser_regression`` do not record the room, so the room each
corpus file resolves to is pinned here, for cash and tournament files alike.
A header the converter does not know is refused, never filed under a default.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.Exceptions import FpdbParseError
from fpdb_3_legacy.PokerTrackerToFpdb import PokerTracker

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "regression-test-files"

# Corpus file -> (room, site id). Two names do not say their room; their header does.
ROOMS = {
    "cash/PokerTracker/Flop/NLHE-2max-EUR-25.00-50.00-201305.new.format.txt": ("Microgaming", 20),
    "cash/PokerTracker/Flop/NLHE-6max-USD-0.02-0.04-201412.Merge.v2.post.sb.txt": ("Merge", 12),
    "cash/PokerTracker/Flop/NLHE-6max-USD-0.02-0.04-201412.Merge.weird.allin.sb.corrupted.txt": ("Merge", 12),
    "cash/PokerTracker/Flop/NLHE-EUR-0.01-0.02-201901.iPoker.Uncalled.txt": ("iPoker", 14),
    "cash/PokerTracker/Flop/NLHE-EUR-0.05-0.10-201111.Microgaming.txt": ("Microgaming", 20),
    "cash/PokerTracker/Flop/NLHE-EUR-0.05-0.10-201205.Microgaming.post.both.txt": ("Microgaming", 20),
    "cash/PokerTracker/Flop/NLHE-EUR-0.05-0.10-201901.iPoker.new.version.txt": ("iPoker", 14),
    "cash/PokerTracker/Flop/NLHE-EUR-10-20-202104.iPoker.all.in.blind.txt": ("iPoker", 14),
    "cash/PokerTracker/Flop/NLHE-EUR-5-10-202104.iPoker.shows.one.txt": ("iPoker", 14),
    "cash/PokerTracker/Flop/NLHE-USD-0.05-0.10-201110.iPoker.txt": ("iPoker", 14),
    "cash/PokerTracker/Flop/NLHE-USD-0.10-0.20-201204.PT4.Merge.txt": ("Merge", 12),
    "cash/PokerTracker/Flop/NLHE-USD-0.10-0.25-201201.Merge-post-both.txt": ("Merge", 12),
    "cash/PokerTracker/Flop/NLHE-USD-0.50-1.00-201101.Everest.txt": ("Everest", 16),
    "cash/PokerTracker/Flop/NLHE-USD-0.50-1.00-201101.Merge.txt": ("Merge", 12),
    "cash/PokerTracker/Flop/NLHE-USD-0.50-1.00-201101.iPoker.post.both.txt": ("iPoker", 14),
    "cash/PokerTracker/Flop/NLHE-USD-0.50-1.00-201101.iPoker.raise.by.txt": ("iPoker", 14),
    "cash/PokerTracker/Flop/NLHE-USD-1.00-2.00-201812.iPoker.Zone.txt": ("iPoker", 14),
    "cash/PokerTracker/Flop/PLO-2max-EUR-0.25-0.50-201309.Microgaming.Export.txt": ("Microgaming", 20),
    "cash/PokerTracker/Flop/PLO-2max-USD-50.00-100.00-201308.iPoker.archive.txt": ("iPoker", 14),
    "cash/PokerTracker/Flop/PLO-EUR-0.25-0.50-201601.all.in.call.txt": ("Microgaming", 20),
    "tour/PokerTracker/Flop/LHE-EUR-SNG-201111.Everest.txt": ("Everest", 16),
    "tour/PokerTracker/Flop/NLHE-10max-MTT-USD-5.00-202104.iPoker.txt": ("iPoker", 14),
    "tour/PokerTracker/Flop/NLHE-2max-USD-0-STT-201307.Microgaming.allin.blind.txt": ("Microgaming", 20),
    "tour/PokerTracker/Flop/NLHE-2max-USD-0-STT-201307.Microgaming.txt": ("Microgaming", 20),
    "tour/PokerTracker/Flop/NLHE-9max-USD-MTT-16.50-201307.Microgaming.antes.txt": ("Microgaming", 20),
    "tour/PokerTracker/Flop/NLHE-EUR-200-MTT-201901.iPoker.txt": ("iPoker", 14),
    "tour/PokerTracker/Flop/NLHE-MTT-EUR-22.25-22.25-202104.KO.iPoker.txt": ("iPoker", 14),
    "tour/PokerTracker/Flop/NLHE-USD-SNG-2-201106.iPoker.txt": ("iPoker", 14),
    "tour/PokerTracker/Flop/NLHE-USD-SNG-2-201111.Merge.txt": ("Merge", 12),
    "tour/PokerTracker/Flop/PLO-USD-5-201202.Merge.all.in.blind.txt": ("Merge", 12),
}


@pytest.fixture(scope="module")
def config() -> Config:
    return Config(file=str(ROOT / "HUD_config.xml"))


def test_every_pokertracker_corpus_file_is_pinned() -> None:
    on_disk = {
        path.relative_to(CORPUS).as_posix()
        for kind in ("cash", "tour")
        for path in (CORPUS / kind / "PokerTracker").rglob("*.txt")
    }

    assert on_disk == set(ROOMS)


@pytest.mark.parametrize("relative", sorted(ROOMS))
def test_each_hand_is_filed_under_the_room_in_its_header(config, relative) -> None:
    parser = PokerTracker(config=config, in_path=str(CORPUS / relative), autostart=True)
    hands = parser.getProcessedHands()

    assert hands
    assert {(hand.sitename, hand.siteId) for hand in hands} == {ROOMS[relative]}


@pytest.mark.parametrize(
    "header",
    [
        "Some Other Poker Game #123: Hold'em NL $0.50/$1 01/01/2011 12:01:23",
        "PokerStars Hand #123: Hold'em No Limit ($0.01/$0.02 USD)",
        "",
    ],
)
def test_a_header_with_no_known_room_is_refused_not_filed_under_a_default(header) -> None:
    parser = PokerTracker.__new__(PokerTracker)

    with pytest.raises(FpdbParseError):
        parser.determineGameType(header + "\nSeat 1: Player0 ($100 in chips)\n")
