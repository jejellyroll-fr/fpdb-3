"""The WPN cash repair refiles hands the way a fresh import files them.

The damaged database is built for real: the files are imported with the
converter put back the way it was -- current-format cash hands filed as play
money, their "(Cap)" table name unread. The repaired database must hold the
game types and HUD counts a clean import stores.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.Importer import Importer
from fpdb_3_legacy.WinningToFpdb import Winning
from tests.helpers import analytics_golden as golden
from tools import repair_wpn_cash_gametypes as repair_tool

REPO = Path(__file__).resolve().parent.parent
WINNING = REPO / "regression-test-files" / "cash" / "Winning" / "Flop"

FILES = (
    # Current format: a cap table, a regular table, a cap PLO8 hand.
    REPO / "tests" / "fixtures" / "hands" / "winning" / "modern_cash.txt",
    REPO / "tests" / "fixtures" / "hands" / "winning" / "plo8_cap_2026.txt",
    WINNING / "NLHE-9max-USD-0.02-0.05-202104.walk.txt",
    # Old format, never affected: real money, and play money on a "PM" table.
    WINNING / "NLHE-6max-USD-0.02-0.05-201608.HH00000000 G0.txt",
    WINNING / "NLHE-9max-play-5.00-10.00-201608.HH00000000 G0.txt",
)

HANDS = (
    "SELECT h.siteHandNo, g.currency, g.buyinType, g.category, g.limitType, g.smallBlind, g.bigBlind "
    "FROM Hands h JOIN Gametypes g ON g.id = h.gametypeId ORDER BY h.siteHandNo"
)
HAND_COUNT = "SELECT COUNT(*) FROM Hands"
HUD_COUNTS = (
    "SELECT g.currency, g.buyinType, g.category, g.smallBlind, g.bigBlind, p.name, SUM(c.n), SUM(c.totalProfit) "
    "FROM HudCache c JOIN Gametypes g ON g.id = c.gametypeId JOIN Players p ON p.id = c.playerId "
    "GROUP BY g.currency, g.buyinType, g.category, g.smallBlind, g.bigBlind, p.name "
    "ORDER BY g.currency, g.buyinType, g.category, g.smallBlind, g.bigBlind, p.name"
)
CURRENT_FORMAT_HANDS = {151588328, 2790000001, 784373412}


def _import(config, files=FILES) -> None:
    db = Database(config)
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.database = db
    for path in files:
        importer.addImportFile(str(path), "auto")
    importer.runImport()


def _as_before_the_fix():
    """Patch the converter back to filing current-format cash hands wrongly."""
    determine = Winning._determineGameType2
    read_buyin_type = Winning._read_buyin_type

    def play_money(self, hand_text):
        info = determine(self, hand_text)
        if info["type"] == "ring":
            info["currency"] = "play"
        return info

    def old_format_only(self, hand, table_name):
        if self.version == 1:
            read_buyin_type(self, hand, table_name)

    Winning._determineGameType2 = play_money  # type: ignore[method-assign]
    Winning._read_buyin_type = old_format_only  # type: ignore[method-assign]

    def restore() -> None:
        Winning._determineGameType2 = determine  # type: ignore[method-assign]
        Winning._read_buyin_type = read_buyin_type  # type: ignore[method-assign]

    return restore


def _build(directory: Path, *, damaged: bool, reimported: bool = False) -> None:
    directory.mkdir(parents=True)
    config = golden.build_config(directory)
    Database(config).recreate_tables()
    restore = _as_before_the_fix() if damaged else None
    try:
        _import(config)
    finally:
        if restore:
            restore()
    if reimported:
        # The user updated fpdb and imported the same hands again, from copies:
        # the importer skips a file it already knows by path.
        copies = directory / "copies"
        copies.mkdir()
        _import(config, [Path(shutil.copy(path, copies / path.name)) for path in FILES])


def _rows(db, statement: str) -> list[tuple]:
    cursor = db.get_cursor()
    cursor.execute(statement)
    return [tuple(row) for row in cursor.fetchall()]


@pytest.fixture(scope="module")
def templates(tmp_path_factory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("wpn_cash_repair")
    _build(root / "clean", damaged=False)
    _build(root / "damaged", damaged=True)
    _build(root / "reimported", damaged=True, reimported=True)
    return {name: root / name for name in ("clean", "damaged", "reimported")}


@pytest.fixture
def open_copy(templates, tmp_path):
    def _open(name: str):
        target = tmp_path / name
        shutil.copytree(templates[name], target)
        return Database(golden.build_config(target))

    return _open


@pytest.fixture(scope="module")
def sites(tmp_path_factory) -> set[str]:
    return repair_tool.wpn_sites(golden.build_config(tmp_path_factory.mktemp("wpn_sites")))


def test_every_wpn_skin_is_covered(sites: set[str]) -> None:
    # The importer files a WPN hand under whichever skin the config names, not
    # always "WinningPoker".
    assert {"WinningPoker", "ACR Poker", "Americas Cardroom"} <= sites


def test_the_scenario_reproduces_the_damage(open_copy) -> None:
    clean = {row[0]: row[1:] for row in _rows(open_copy("clean"), HANDS)}
    damaged = {row[0]: row[1:] for row in _rows(open_copy("damaged"), HANDS)}

    assert clean.keys() == damaged.keys()
    differing = {hand for hand in clean if clean[hand] != damaged[hand]}
    assert differing == CURRENT_FORMAT_HANDS
    assert {damaged[hand][:2] for hand in differing} == {("play", "regular")}
    assert {clean[hand][:2] for hand in differing} == {("USD", "cap"), ("USD", "regular")}


def test_the_repair_matches_a_clean_import(open_copy, sites) -> None:
    damaged = open_copy("damaged")
    clean = open_copy("clean")

    found = repair_tool.survey(damaged, sites)
    assert {fix.site_hand_no for fix in found.misfiled} == CURRENT_FORMAT_HANDS
    changed = repair_tool.repair(damaged, found, commit=True)

    # Both paths run: the cap tables' game types held only misfiled hands and
    # are corrected in place; the regular $0.02/$0.05 hand moves to the game
    # type the old-format real-money file already stored.
    assert changed["Gametypes corrected in place"] == 2
    assert changed["Hands moved to another gametype"] == 1
    assert _rows(damaged, HANDS) == _rows(clean, HANDS)
    assert _rows(damaged, HUD_COUNTS) == _rows(clean, HUD_COUNTS)
    assert not repair_tool.survey(damaged, sites).writes


def test_hands_move_when_their_game_type_already_exists(open_copy, sites) -> None:
    damaged = open_copy("damaged")
    clean = open_copy("clean")
    found = repair_tool.survey(damaged, sites)
    # A corrected game type stored meanwhile, for a cap hand that would
    # otherwise have its row corrected in place.
    (cap_fix,) = [fix for fix in found.misfiled if fix.site_hand_no == 2790000001]
    repair_tool._find_or_create(damaged, cap_fix.target)

    changed = repair_tool.repair(damaged, found, commit=True)

    assert changed["Gametypes corrected in place"] == 1
    assert changed["Hands moved to another gametype"] == 2
    assert changed["Caches rebuilt"]
    assert _rows(damaged, HANDS) == _rows(clean, HANDS)
    assert _rows(damaged, HUD_COUNTS) == _rows(clean, HUD_COUNTS)


def test_reimporting_after_the_fix_leaves_the_hands_misfiled(open_copy, sites) -> None:
    # Why the tool exists: the duplicate check finds each hand by site and hand
    # number and skips it, whatever game type it was filed under.
    reimported = open_copy("reimported")
    clean = open_copy("clean")

    assert _rows(reimported, HAND_COUNT) == _rows(clean, HAND_COUNT)
    found = repair_tool.survey(reimported, sites)
    assert {fix.site_hand_no for fix in found.misfiled} == CURRENT_FORMAT_HANDS

    repair_tool.repair(reimported, found, commit=True)

    assert _rows(reimported, HANDS) == _rows(clean, HANDS)


def test_a_rehearsal_changes_nothing(open_copy, sites) -> None:
    damaged = open_copy("damaged")
    before = _rows(damaged, HANDS)

    changed = repair_tool.repair(damaged, repair_tool.survey(damaged, sites), commit=False)

    assert changed["Hands refiled"] == len(CURRENT_FORMAT_HANDS)
    assert _rows(damaged, HANDS) == before


def test_a_clean_database_needs_nothing(open_copy, sites) -> None:
    assert not repair_tool.survey(open_copy("clean"), sites).writes


@pytest.mark.parametrize(
    ("table", "file_name", "real"),
    [
        ("Miramar (Cap)", None, True),
        ("PM Hold`em 5/10", None, False),
        # The file name wins over the table name when it says.
        ("PM Hold`em 5/10", r"C:\ACR\HH20260721 CASHID-G1 TN-x GAMETYPE-Hold'em LIMIT-no CUR-REAL OND-F.txt", True),
        ("Miramar (Cap)", "/acr/HH20260721 CASHID-G1 TN-x GAMETYPE-Hold'em LIMIT-no CUR-PLAY OND-F.txt", False),
    ],
)
def test_play_money_is_told_by_file_then_table(table: str, file_name: str | None, real: bool) -> None:
    assert repair_tool.is_real_money(table, file_name) is real
