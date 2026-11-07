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
# Current-format play money: blinds with no "$", on a "(Cap)" table whose name
# has no "PM" prefix, in a file whose name has no CUR- marker. The fixed
# converter stores it as play money too; only its buy-in type was wrong.
PLAY_HAND = 2790000002
PLO8_CAP = REPO / "tests" / "fixtures" / "hands" / "winning" / "plo8_cap_2026.txt"
# Where the imported files are found again: fpdb keeps only their names.
HH_DIRS = (PLO8_CAP.parent, WINNING)


def _play_money_copy(directory: Path) -> Path:
    text = PLO8_CAP.read_text(encoding="utf-8").replace("$", "").replace("2790000001", str(PLAY_HAND))
    path = directory / "plo8_cap_play.txt"
    path.write_text(text, encoding="utf-8")
    return path


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


def _build(directory: Path, files: tuple[Path, ...], *, damaged: bool, reimported: bool = False) -> None:
    directory.mkdir(parents=True)
    config = golden.build_config(directory)
    Database(config).recreate_tables()
    restore = _as_before_the_fix() if damaged else None
    try:
        _import(config, files)
    finally:
        if restore:
            restore()
    if reimported:
        # The user updated fpdb and imported the same hands again, from copies:
        # the importer skips a file it already knows by path.
        copies = directory / "copies"
        copies.mkdir()
        _import(config, [Path(shutil.copy(path, copies / path.name)) for path in files])


def _rows(db, statement: str) -> list[tuple]:
    return _rows_with(db, statement, ())


def _rows_with(db, statement: str, params: tuple) -> list[tuple]:
    cursor = db.get_cursor()
    cursor.execute(statement, params)
    return [tuple(row) for row in cursor.fetchall()] if cursor.description else []


@pytest.fixture(scope="module")
def templates(tmp_path_factory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("wpn_cash_repair")
    files = (*FILES, _play_money_copy(root))
    _build(root / "clean", files, damaged=False)
    _build(root / "damaged", files, damaged=True)
    _build(root / "reimported", files, damaged=True, reimported=True)
    return {name: root / name for name in ("clean", "damaged", "reimported")}


@pytest.fixture
def open_copy(templates, tmp_path):
    def _open(name: str):
        target = tmp_path / name
        shutil.copytree(templates[name], target)
        return Database(golden.build_config(target))

    return _open


@pytest.fixture
def headers(templates) -> repair_tool.HeaderCurrencies:
    # The play-money copy sits beside the databases.
    return repair_tool.HeaderCurrencies([*HH_DIRS, templates["clean"].parent])


@pytest.fixture(scope="module")
def sites(tmp_path_factory) -> set[str]:
    return repair_tool.wpn_sites(golden.build_config(tmp_path_factory.mktemp("wpn_sites")))


def test_every_wpn_skin_is_covered(sites: set[str]) -> None:
    # The importer files a WPN hand under whichever skin the config names, not
    # always "WinningPoker".
    assert {"WinningPoker", "ACR Poker", "Americas Cardroom"} <= sites


MISFILED = CURRENT_FORMAT_HANDS | {PLAY_HAND}
UPDATE_FILE = "UPDATE Files SET file = ? WHERE file = ?"
CURRENCY = "SELECT g.currency, g.buyinType FROM Hands h JOIN Gametypes g ON g.id = h.gametypeId WHERE h.siteHandNo = ?"


def test_the_scenario_reproduces_the_damage(open_copy) -> None:
    clean = {row[0]: row[1:] for row in _rows(open_copy("clean"), HANDS)}
    damaged = {row[0]: row[1:] for row in _rows(open_copy("damaged"), HANDS)}

    assert clean.keys() == damaged.keys()
    differing = {hand for hand in clean if clean[hand] != damaged[hand]}
    assert differing == MISFILED
    assert {damaged[hand][:2] for hand in differing} == {("play", "regular")}
    assert {clean[hand][:2] for hand in CURRENT_FORMAT_HANDS} == {("USD", "cap"), ("USD", "regular")}
    assert clean[PLAY_HAND][:2] == ("play", "cap")


def test_the_repair_matches_a_clean_import(open_copy, sites, headers) -> None:
    damaged = open_copy("damaged")
    clean = open_copy("clean")

    found = repair_tool.survey(damaged, sites, headers)
    assert {fix.site_hand_no for fix in found.misfiled} == MISFILED
    assert found.undecided == []
    changed = repair_tool.repair(damaged, found, commit=True)

    # Both paths run. The NLHE cap table's game type held only misfiled hands
    # and is corrected in place. The PLO8 game type held a real-money and a
    # play-money hand, which go their separate ways; the regular $0.02/$0.05
    # hand moves to the game type the old-format real-money file stored.
    assert changed["Gametypes corrected in place"] == 1
    assert changed["Hands moved to another gametype"] == 3
    assert _rows(damaged, HANDS) == _rows(clean, HANDS)
    assert _rows(damaged, HUD_COUNTS) == _rows(clean, HUD_COUNTS)
    assert not repair_tool.survey(damaged, sites, headers).writes


def test_current_format_play_money_stays_play_money(open_copy, sites, headers) -> None:
    damaged = open_copy("damaged")

    repair_tool.repair(damaged, repair_tool.survey(damaged, sites, headers), commit=True)

    # Its table name has no "PM" prefix, but its header writes no "$".
    assert _rows_with(damaged, CURRENCY, (PLAY_HAND,)) == [("play", "cap")]


def test_a_hand_with_no_evidence_is_left_as_it_is(open_copy, sites, headers) -> None:
    damaged = open_copy("damaged")
    # The real-money PLO8 file was renamed after it was imported.
    _rows_with(damaged, UPDATE_FILE, ("plo8_cap_2026 renamed", "plo8_cap_2026"))
    damaged.commit()

    found = repair_tool.survey(damaged, sites, headers)
    repair_tool.repair(damaged, found, commit=True)

    assert [hand.site_hand_no for hand in found.undecided] == [2790000001]
    # Still play money, though its "(Cap)" table name sets the buy-in type.
    assert _rows_with(damaged, CURRENCY, (2790000001,)) == [("play", "cap")]


def test_hands_move_when_their_game_type_already_exists(open_copy, sites, headers) -> None:
    damaged = open_copy("damaged")
    clean = open_copy("clean")
    found = repair_tool.survey(damaged, sites, headers)
    # A corrected game type stored meanwhile, for the hand whose row would
    # otherwise be corrected in place.
    (cap_fix,) = [fix for fix in found.misfiled if fix.site_hand_no == 151588328]
    repair_tool._find_or_create(damaged, cap_fix.target)

    changed = repair_tool.repair(damaged, found, commit=True)

    assert "Gametypes corrected in place" not in changed
    assert changed["Hands moved to another gametype"] == len(MISFILED)
    assert changed["Caches rebuilt"]
    assert _rows(damaged, HANDS) == _rows(clean, HANDS)
    assert _rows(damaged, HUD_COUNTS) == _rows(clean, HUD_COUNTS)


def test_reimporting_after_the_fix_leaves_the_hands_misfiled(open_copy, sites, headers) -> None:
    # Why the tool exists: the duplicate check finds each hand by site and hand
    # number and skips it, whatever game type it was filed under.
    reimported = open_copy("reimported")
    clean = open_copy("clean")

    assert _rows(reimported, HAND_COUNT) == _rows(clean, HAND_COUNT)
    found = repair_tool.survey(reimported, sites, headers)
    assert {fix.site_hand_no for fix in found.misfiled} == MISFILED

    repair_tool.repair(reimported, found, commit=True)

    assert _rows(reimported, HANDS) == _rows(clean, HANDS)


def test_a_rehearsal_changes_nothing(open_copy, sites, headers) -> None:
    damaged = open_copy("damaged")
    before = _rows(damaged, HANDS)

    changed = repair_tool.repair(damaged, repair_tool.survey(damaged, sites, headers), commit=False)

    assert changed["Hands refiled"] == len(MISFILED)
    assert _rows(damaged, HANDS) == before


def test_a_clean_database_needs_nothing(open_copy, sites, headers) -> None:
    assert not repair_tool.survey(open_copy("clean"), sites, headers).writes


@pytest.mark.parametrize(
    ("table", "file_name", "site_hand_no", "real"),
    [
        # The file name says, whatever the table or the file's content.
        ("PM Hold`em 5/10", "HH20260721 CASHID-G1 TN-x GAMETYPE-Hold'em LIMIT-no CUR-REAL OND-F BUYIN-0", 1, True),
        ("Miramar (Cap)", "HH20260721 CASHID-G1 TN-x GAMETYPE-Hold'em LIMIT-no CUR-PLAY OND-F BUYIN-0", 1, False),
        # An old-format play-money table.
        ("PM Hold`em 5/10", None, 1, False),
        # Otherwise the hand's own header, read back from its file.
        ("Vesta (Cap)", "plo8_cap_2026", 2790000001, True),
        ("Vesta (Cap)", "plo8_cap_play", PLAY_HAND, False),
        # Nothing to go by: never assumed to be real money.
        ("Vesta (Cap)", None, 2790000001, None),
        ("Vesta (Cap)", "plo8_cap_2026 renamed", 2790000001, None),
        ("Vesta (Cap)", "plo8_cap_2026", 123, None),
    ],
)
def test_real_money_needs_evidence(
    tmp_path: Path, table: str, file_name: str | None, site_hand_no: int, real: bool | None
) -> None:
    _play_money_copy(tmp_path)
    headers = repair_tool.HeaderCurrencies([PLO8_CAP.parent, tmp_path])

    assert repair_tool.real_money_evidence(table, file_name, site_hand_no, headers) is real
