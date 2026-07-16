#!/usr/bin/env python3
"""Regression tests for the legacy UnibetToFpdb parser, 2026 "Unibet Hand #" format.

Unibet's current (Relax Gaming) client writes a different header than the
legacy 2021 "Game #...: Table €1 NL" format:

    === HAND HISTORIES ===

    Unibet Hand #1558006027 - 0.03/0.05 - Pot Limit Omaha - UTC 21:59:40 2026/06/05
    Table "86113818" 6-max

The body (seats, blinds, streets, summary) is identical to the legacy format,
so only the header handling and identification needed to change. These tests
lock in that the new header is recognised and parsed at the same level as the
legacy one.
"""

from __future__ import annotations

import re
import tempfile
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from fpdb_3_legacy import GuiReplayer
from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.Importer import Importer
from fpdb_3_legacy.UnibetSummary import UnibetSummary
from fpdb_3_legacy.UnibetToFpdb import Unibet

pytestmark = pytest.mark.qt

# Two-hand sample in the 2026 format (anonymised, real € sign, hero suffix kept).
SAMPLE = """=== HAND HISTORIES ===

Unibet Hand #1558006027 - 0.03/0.05 - Pot Limit Omaha - UTC 21:59:40 2026/06/05
Table "86113818" 6-max
*** Seated players ***
Seat 1: lembourou (€0) (sitting out)
Seat 2: cla17 (€1.53)
Seat 3: Savy-95 (€4.86)
Seat 4: hero[Unibet_28204e083c0fb55a] (€3.84)
*** Blinds and button ***
cla17 has the button
Savy-95 posts small blind €0.03
hero[Unibet_28204e083c0fb55a] posts big blind €0.05
*** Hole cards ***
Dealt to Savy-95 [Ts Kd 4c Td]
Dealt to hero[Unibet_28204e083c0fb55a] [5h 9c Qc 7h]
Dealt to cla17 [9h 8d 2s Tc]
*** Preflop ***
cla17 calls €0.05
Savy-95 calls €0.02
hero[Unibet_28204e083c0fb55a] checks
*** Flop *** [2h 3s 6s]
Savy-95 checks
hero[Unibet_28204e083c0fb55a] checks
cla17 checks
*** Turn *** [2h 3s 6s] [Qs]
Savy-95 checks
hero[Unibet_28204e083c0fb55a] checks
cla17 checks
*** River *** [2h 3s 6s] [Qs] [4d]
Savy-95 checks
hero[Unibet_28204e083c0fb55a] checks
cla17 checks
*** Showdown ***
cla17 shows [9h 8d 2s Tc], A Pair of Deuces
Savy-95 shows [Ts Kd 4c Td], A Pair of Tens
hero[Unibet_28204e083c0fb55a] shows [5h 9c Qc 7h], A Straight
hero[Unibet_28204e083c0fb55a] wins €0.14
*** Summary ***
Total pot €0.15 Rake €0.01
Seat 2: cla17: bet €0.05 and won €0, net result: €-0.05
Seat 3: Savy-95: bet €0.05 and won €0, net result: €-0.05
Seat 4: hero[Unibet_28204e083c0fb55a]: bet €0.05 and won €0.14, net result: €0.09


Unibet Hand #1558007138 - 0.03/0.05 - Pot Limit Omaha - UTC 22:00:21 2026/06/05
Table "86113818" 6-max
*** Seated players ***
Seat 2: cla17 (€1.48)
Seat 3: Savy-95 (€4.81)
Seat 4: hero[Unibet_28204e083c0fb55a] (€3.93)
*** Blinds and button ***
Savy-95 has the button
hero[Unibet_28204e083c0fb55a] posts small blind €0.03
cla17 posts big blind €0.05
*** Hole cards ***
Dealt to hero[Unibet_28204e083c0fb55a] [6c 9c 8s Ad]
Dealt in cla17
Dealt in Savy-95
*** Preflop ***
hero[Unibet_28204e083c0fb55a] folds
*** Summary ***
Total pot €0.08 Rake €0
Seat 4: hero[Unibet_28204e083c0fb55a]: bet €0.03 and won €0, net result: €-0.03
"""


def test_re_identify_matches_2026_format() -> None:
    assert Unibet.re_identify.search(SAMPLE) is not None


def test_determine_game_type_2026() -> None:
    parser = Unibet(Config(), autostart=False)
    info = parser.determineGameType(SAMPLE)
    assert info["type"] == "ring"
    assert info["base"] == "hold"
    assert info["category"] == "omahahi"
    assert info["limitType"] == "pl"
    assert info["currency"] == "EUR"
    assert info["sb"] == "0.03"
    assert info["bb"] == "0.05"


def test_full_import_2026() -> None:
    with tempfile.NamedTemporaryFile(
        "w", suffix=".txt", encoding="utf-8", delete=False,
    ) as fh:
        fh.write(SAMPLE)
        tmp = fh.name
    try:
        hhc = Unibet(Config(), in_path=tmp, autostart=True)
        assert hhc.numErrors == 0
        assert hhc.numPartial == 0
        assert len(hhc.processedHands) == 2

        hand = hhc.processedHands[0]
        assert hand.handid == "1558006027"
        assert hand.tablename == "86113818"
        assert hand.maxseats == 6
        assert hand.gametype["category"] == "omahahi"
        assert hand.gametype["limitType"] == "pl"
        # The per-session "[Unibet_...]" token is stripped from the hero name.
        assert {p[1] for p in hand.players} == {
            "lembourou",
            "cla17",
            "Savy-95",
            "hero",
        }
        # Hand 1 is a showdown that lists every player's cards under "Dealt to";
        # the hero must still be the token-identified player, not the last one.
        assert hand.hero == "hero"
        assert hand.board["FLOP"] == ["2h", "3s", "6s"]
        assert hand.board["TURN"] == ["Qs"]
        assert hand.board["RIVER"] == ["4d"]
        assert hand.actions["BLINDSANTES"] == [
            ("Savy-95", "small blind", Decimal("0.03"), False),
            ("hero", "big blind", Decimal("0.05"), False),
        ]
        assert [a[:2] for a in hand.actions["PREFLOP"]] == [
            ("cla17", "calls"),
            ("Savy-95", "calls"),
            ("hero", "checks"),
        ]
        assert [a[:2] for a in hand.actions["FLOP"]] == [
            ("Savy-95", "checks"),
            ("hero", "checks"),
            ("cla17", "checks"),
        ]
        assert [a[:2] for a in hand.actions["TURN"]] == [
            ("Savy-95", "checks"),
            ("hero", "checks"),
            ("cla17", "checks"),
        ]
        assert [a[:2] for a in hand.actions["RIVER"]] == [
            ("Savy-95", "checks"),
            ("hero", "checks"),
            ("cla17", "checks"),
        ]

        replayer = GuiReplayer.GuiReplayer.__new__(GuiReplayer.GuiReplayer)
        model = replayer._build_replay_model(hand)
        assert len(model.states) > 1
    finally:
        Path(tmp).unlink(missing_ok=True)


def test_hero_token_is_stripped() -> None:
    parser = Unibet(Config(), autostart=False)
    cleaned = parser.re_HeroToken.sub("", "hero[Unibet_28204e083c0fb55a] posts big blind €0.05")
    assert cleaned == "hero posts big blind €0.05"


def test_successful_import_with_missing_expected_data_records_warning() -> None:
    parser = Unibet(Config(), autostart=False)

    class ParsedButEmptyHand:
        handid = "warning-case"
        gametype = {"base": "hold", "sb": "0.03", "bb": "0.05"}
        players = [(1, "small blind"), (2, "big blind")]
        actionStreets = ["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"]
        actions = {street: [] for street in actionStreets}
        handText = "*** Flop *** [2h 3s 6s]"
        board = {"FLOP": [], "TURN": [], "RIVER": []}

    parser._warn_if_hand_missing_expected_data(ParsedButEmptyHand())

    assert parser.parsing_issues
    assert "without parser errors" in parser.parsing_issues[-1]
    assert "no blind/ante actions" in parser.parsing_issues[-1]
    assert "no betting actions" in parser.parsing_issues[-1]
    assert "flop marker present but board cards missing" in parser.parsing_issues[-1]


# --- 2026 tournament format -------------------------------------------------

TOUR_SAMPLE = """=== HAND HISTORIES ===

Unibet Hand #1558006464, Tournament #85614762, €0.93 + €0.07 - 25.00/50.00 - No Limit Hold'Em - Total prize €4 - UTC 21:59:56 2026/06/05
Table "86116111" 3-max
*** Seated players ***
Seat 1: evymm (415)
Seat 3: DrikC79 (315)
Seat 5: hero[Unibet_28204e083c0fb55a] (770)
*** Blinds and button ***
DrikC79 has the button
hero[Unibet_28204e083c0fb55a] posts small blind 25
evymm posts big blind 50
*** Hole cards ***
Dealt to hero[Unibet_28204e083c0fb55a] [8c Jc]
Dealt to evymm [Qc Kh]
Dealt in DrikC79
*** Preflop ***
DrikC79 folds
hero[Unibet_28204e083c0fb55a] calls 25
evymm checks
*** Flop *** [4s Tc 8d]
hero[Unibet_28204e083c0fb55a] bets 50
evymm calls 50
*** Turn *** [4s Tc 8d] [Ac]
hero[Unibet_28204e083c0fb55a] bets 50
evymm calls 50
*** River *** [4s Tc 8d] [Ac] [9d]
hero[Unibet_28204e083c0fb55a] checks
evymm checks
*** Showdown ***
evymm shows [Qc Kh], High card
hero[Unibet_28204e083c0fb55a] shows [8c Jc], A Pair of Eights
hero[Unibet_28204e083c0fb55a] wins 300
*** Summary ***
Total pot 300
Seat 1: evymm: bet 150 and won 0, net result: -150
Seat 5: hero[Unibet_28204e083c0fb55a]: bet 150 and won 300, net result: 150
"""


def test_buyin_is_read_only_from_the_tournament_header() -> None:
    # readHandInfo reads the buy-in from the TBUYIN/TFEE/TCURRENCY fields of the
    # tournament header, and nowhere else: no Unibet pattern states a buy-in in
    # any other shape. This guards against reviving a dispatch branch keyed on
    # fields the parser cannot produce.
    produced = set()
    for name in dir(Unibet):
        attr = getattr(Unibet, name)
        if isinstance(attr, re.Pattern):
            produced |= set(attr.groupindex)

    assert {"TBUYIN", "TFEE", "TCURRENCY"} <= produced
    assert not {"BUYIN", "BIAMT", "BIRAKE", "BOUNTY"} & produced


def test_determine_game_type_tournament() -> None:
    parser = Unibet(Config(), autostart=False)
    info = parser.determineGameType(TOUR_SAMPLE)
    assert info["type"] == "tour"
    assert info["category"] == "holdem"
    assert info["limitType"] == "nl"
    assert info["currency"] == "EUR"
    assert info["sb"] == "25.00"
    assert info["bb"] == "50.00"


def test_full_import_tournament() -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8", delete=False) as fh:
        fh.write(TOUR_SAMPLE)
        tmp = fh.name
    try:
        hhc = Unibet(Config(), in_path=tmp, autostart=True)
        assert hhc.numErrors == 0
        assert hhc.numPartial == 0
        assert len(hhc.processedHands) == 1
        hand = hhc.processedHands[0]
        assert hand.handid == "1558006464"
        assert hand.tourNo == "85614762"
        assert hand.buyin == 93  # €0.93 in cents
        assert hand.fee == 7
        assert hand.buyinCurrency == "EUR"
        assert hand.gametype["type"] == "tour"
        assert hand.hero == "hero"
        # Chip stacks (no currency symbol) parse.
        assert dict((p[1], p[2]) for p in hand.players)["hero"] == "770"
        # Only the winner is collected (losers' negative net result excluded).
        assert hand.collected == [["hero", "150"]]
        assert hand.actions["BLINDSANTES"] == [
            ("hero", "small blind", Decimal("25"), False),
            ("evymm", "big blind", Decimal("50"), False),
        ]
        assert hand.board["FLOP"] == ["4s", "Tc", "8d"]
        assert hand.board["TURN"] == ["Ac"]
        assert hand.board["RIVER"] == ["9d"]
        assert [a[:2] for a in hand.actions["PREFLOP"]] == [
            ("DrikC79", "folds"),
            ("hero", "calls"),
            ("evymm", "checks"),
        ]
        assert [a[:2] for a in hand.actions["FLOP"]] == [
            ("hero", "bets"),
            ("evymm", "calls"),
        ]
        assert [a[:2] for a in hand.actions["TURN"]] == [
            ("hero", "bets"),
            ("evymm", "calls"),
        ]
        assert [a[:2] for a in hand.actions["RIVER"]] == [
            ("hero", "checks"),
            ("evymm", "checks"),
        ]
    finally:
        Path(tmp).unlink(missing_ok=True)


def test_bulk_import_2026_exports_ignore_non_hand_banner() -> None:
    config = Config()
    db_file = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
    db_file.close()
    db_params = config.get_db_parameters().copy()
    db_params.update(
        {
            "db-backend": Database.SQLITE,
            "db-server": "sqlite",
            "db-databaseName": db_file.name,
            "db-host": "",
            "db-user": "",
            "db-password": "",
        },
    )
    config.get_db_parameters = lambda: db_params

    database = Database(config)
    database.recreate_tables()
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.database = database
    importer.set_progress_callbacks(lambda total: None, lambda filename, count: None, lambda: None)

    paths = []
    try:
        for text in (SAMPLE, TOUR_SAMPLE):
            with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8", delete=False) as fh:
                fh.write(text)
                paths.append(Path(fh.name))
            importer.clearFileList()
            importer.addBulkImportImportFileOrDir(str(paths[-1]), site="Unibet")
            stored, duplicates, partial, skipped, errors, _duration = importer.runImport()
            assert stored > 0
            assert duplicates == 0
            assert partial == 0
            assert skipped == 0
            assert errors == 0
    finally:
        database.close_connection()
        Path(db_file.name).unlink(missing_ok=True)
        for path in paths:
            path.unlink(missing_ok=True)


SUMMARY_SAMPLE = """=== TOURNAMENT SUMMARIES ===

Unibet Tournament #85614762, No Limit Holdem
Buy-In: €0.93 + €0.07
3 players
Total Prize Pool: €4.00
Tournament started 2026/06/05 21:50:39 UTC
1: Unibet_28204e083c0fb55a finished €4.00
2: DrikC79 finished
3: evymm finished
You finished in 1st place.
"""


def test_unibet_summary_parses_and_maps_hero() -> None:
    config = MagicMock()
    config.get_import_parameters.return_value = {}
    config.get_site_parameters.return_value = {"screen_name": "hero"}
    db = MagicMock()
    db.get_site_id.return_value = [[30]]

    ts = UnibetSummary(
        db=db, config=config, siteName="Unibet", summaryText=SUMMARY_SAMPLE, builtFrom="file",
    )

    assert ts.tourNo == "85614762"
    assert ts.buyin == 93
    assert ts.fee == 7
    assert ts.buyinCurrency == "EUR"
    assert ts.entries == 3
    assert ts.prizepool == 400
    # The bare "Unibet_<id>" winner token is mapped to the configured hero name.
    assert ts.ranks["hero"] == [1]
    assert ts.winnings["hero"] == [400]
    assert "Unibet_28204e083c0fb55a" not in ts.players
