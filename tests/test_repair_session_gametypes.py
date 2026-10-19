"""The #595 repair restores what session caching overwrote.

The damaged database is built for real: the files are imported with session
caching on and appendHandsSessionIds put back the way it was before #594, which
wrote each hand's session id into its gametypeId. The repaired database must
hold the gametypes, sessions and tournament sessions a clean import stores.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.database_caches import DatabaseCachesMixin
from fpdb_3_legacy.Importer import Importer
from tests.helpers import analytics_golden as golden
from tools import repair_session_gametypes as repair_tool

REPO = Path(__file__).resolve().parent.parent

# iPoker cash and a Twister SNG, plus PokerStars: the bug was not iPoker's.
FILES = (
    REPO / "regression-test-files/cash/iPoker/Flop/5CPLO-EUR-2.00-4.00-201905.txt",
    REPO / "regression-test-files/cash/iPoker/Flop/NLHE-EUR-0.01-0.02-201701.new.datetime.format.txt",
    REPO / "tests/fixtures/hands/ipoker/twister/twister_sng.txt",
    REPO / "regression-test-files/cash/Stars/Flop/NLHE-6max-EUR-0.05-0.10-200911.txt",
    REPO / "regression-test-files/cash/Stars/Flop/NLHE-6max-EUR-0.02-0.04-201902.RIO.txt",
    REPO / "regression-test-files/cash/Stars/Flop/5-Card-PLO-6max-USD-3.00-6.00-201303.txt",
)

# Seeded so that session ids cannot coincide with gametype ids.
SEED_SESSION = (
    "INSERT INTO Sessions (id, weekId, monthId, sessionStart, sessionEnd) "
    "VALUES (100, NULL, NULL, '2000-01-01 00:00:00', '2000-01-01 00:00:00')"
)
HANDS = "SELECT siteHandNo, gametypeId, sessionId FROM Hands ORDER BY siteHandNo"
TOURNEYS = "SELECT id, sessionId FROM Tourneys ORDER BY id"
HAND_COUNT = "SELECT COUNT(*) FROM Hands"
TOUR_GAMETYPE = "SELECT id FROM Gametypes WHERE type = 'tour'"
FIVE_CARD_HAND = "SELECT id FROM Hands WHERE siteHandNo = 3422554305"
IPOKER_HOLDEM_RING = (
    "SELECT g.id FROM Gametypes g JOIN Sites s ON s.id = g.siteId "
    "WHERE s.name = 'iPoker' AND g.type = 'ring' AND g.category = 'holdem'"
)
MISFILE_HAND = "UPDATE Hands SET gametypeId = ? WHERE id = ?"
FORGET_PLAYER_SESSIONS = (
    "DELETE FROM SessionsCache WHERE playerId = (SELECT MIN(playerId) FROM HandsPlayers WHERE handId = ?)"
)
UNSESSIONED_HAND = "SELECT MIN(id) FROM Hands WHERE sessionId IS NULL"


def _append_session_ids_before_594(self) -> None:
    """appendHandsSessionIds as it was: one column short of the Hands row."""
    for i in range(len(self.hbulk)):
        session = self.s.get(self.hids[i])
        if session is not None:
            self.hbulk[i][4] = session["id"]
            if self.hbulk[i][2]:
                self.tbulk[self.hbulk[i][2]] = session["id"]


def _session_config(directory: Path):
    config = golden.build_config(directory)
    params = dict(config.get_import_parameters())
    params["cacheSessions"] = True
    config.get_import_parameters = lambda: params
    return config


def _import(config) -> None:
    db = Database(config)
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.database = db
    for path in FILES:
        importer.addImportFile(str(path), "auto")
    importer.runImport()


def _build(directory: Path, *, damaged: bool) -> None:
    directory.mkdir(parents=True)
    config = _session_config(directory)
    Database(config).recreate_tables()
    db = Database(config)
    db.get_cursor().execute(SEED_SESSION)
    db.commit()
    original = DatabaseCachesMixin.appendHandsSessionIds
    if damaged:
        DatabaseCachesMixin.appendHandsSessionIds = _append_session_ids_before_594  # type: ignore[method-assign]
    try:
        _import(config)
    finally:
        DatabaseCachesMixin.appendHandsSessionIds = original  # type: ignore[method-assign]


def _rows(db, statement: str, params: tuple = ()) -> list[tuple]:
    cursor = db.get_cursor()
    cursor.execute(statement, params)
    return [tuple(row) for row in cursor.fetchall()]


@pytest.fixture(scope="module")
def templates(tmp_path_factory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("sessions595")
    _build(root / "clean", damaged=False)
    _build(root / "damaged", damaged=True)
    return {"clean": root / "clean", "damaged": root / "damaged"}


@pytest.fixture
def open_copy(templates, tmp_path):
    def _open(name: str):
        target = tmp_path / name
        shutil.copytree(templates[name], target)
        config = _session_config(target)
        return config, Database(config)

    return _open


def test_the_scenario_reproduces_the_damage(open_copy) -> None:
    _config, clean = open_copy("clean")
    _config, damaged = open_copy("damaged")

    clean_hands = {row[0]: row[1:] for row in _rows(clean, HANDS)}
    damaged_hands = {row[0]: row[1:] for row in _rows(damaged, HANDS)}
    assert clean_hands.keys() == damaged_hands.keys()
    assert all(session is not None for _gametype, session in clean_hands.values())
    # The damaged gametype is the session id; the session column is empty.
    assert all(damaged_hands[k] == (clean_hands[k][1], None) for k in clean_hands)
    assert [session for _id, session in _rows(damaged, TOURNEYS)] == [None]


def test_the_repair_matches_a_clean_import(open_copy) -> None:
    config, damaged = open_copy("damaged")
    _config, clean = open_copy("clean")
    found = repair_tool.survey(damaged, repair_tool.ipoker_sites(config))

    assert found.unresolved == []
    assert found.cross_check_mismatches == 0
    repair_tool.repair(damaged, found, commit=True)

    assert _rows(damaged, HANDS) == _rows(clean, HANDS)
    assert _rows(damaged, TOURNEYS) == _rows(clean, TOURNEYS)


def test_a_clean_database_needs_nothing(open_copy) -> None:
    config, clean = open_copy("clean")

    found = repair_tool.survey(clean, repair_tool.ipoker_sites(config))

    assert not found.writes
    assert found.misclassified == {}
    assert found.hud_shortfall == {}


def test_the_missing_tournament_hud_rows_are_reported(open_copy) -> None:
    config, damaged = open_copy("damaged")
    (tour_gametype,) = _rows(damaged, TOUR_GAMETYPE)[0]

    found = repair_tool.survey(damaged, repair_tool.ipoker_sites(config))

    assert set(found.hud_shortfall) == {tour_gametype}
    hands, cached = found.hud_shortfall[tour_gametype]
    assert cached < hands


def test_a_rehearsal_writes_nothing(open_copy) -> None:
    config, damaged = open_copy("damaged")
    before = (_rows(damaged, HANDS), _rows(damaged, TOURNEYS))
    found = repair_tool.survey(damaged, repair_tool.ipoker_sites(config))

    changed = repair_tool.repair(damaged, found, commit=False)

    assert changed["Hands repaired"] == len(before[0])
    assert (_rows(damaged, HANDS), _rows(damaged, TOURNEYS)) == before


def test_a_damaged_database_stores_its_files_again(open_copy) -> None:
    """The duplicate check joins Hands to Gametypes: a session id there hides the hand."""
    config, damaged = open_copy("damaged")
    (hands,) = _rows(damaged, HAND_COUNT)[0]

    _import(config)

    assert _rows(Database(config), HAND_COUNT)[0][0] > hands


def test_a_repaired_database_recognises_its_files(open_copy) -> None:
    config, damaged = open_copy("damaged")
    (hands,) = _rows(damaged, HAND_COUNT)[0]
    found = repair_tool.survey(damaged, repair_tool.ipoker_sites(config))
    repair_tool.repair(damaged, found, commit=True)

    _import(config)

    assert _rows(Database(config), HAND_COUNT)[0][0] == hands


def test_hands_whose_players_disagree_are_left_alone(open_copy) -> None:
    config, damaged = open_copy("damaged")
    (hand_id,) = _rows(damaged, UNSESSIONED_HAND)[0]
    damaged.get_cursor().execute(FORGET_PLAYER_SESSIONS, (hand_id,))
    damaged.commit()

    found = repair_tool.survey(damaged, repair_tool.ipoker_sites(config))

    assert hand_id not in {fix.hand_id for fix in found.hand_fixes}
    assert any(f"hand row {hand_id} " in line for line in found.unresolved)


def test_misclassified_five_card_omaha_is_deleted_for_a_reimport(open_copy) -> None:
    """Before #594 an iPoker 5 card Omaha session filed its later hands under another game."""
    config, clean = open_copy("clean")
    expected = _rows(clean, HANDS)
    (hand_id,) = _rows(clean, FIVE_CARD_HAND)[0]
    (holdem,) = _rows(clean, IPOKER_HOLDEM_RING)[0]
    clean.get_cursor().execute(MISFILE_HAND, (holdem, hand_id))
    clean.commit()

    found = repair_tool.survey(clean, repair_tool.ipoker_sites(config))
    assert found.misclassified == {"100BB Feldkirch 10, 488784806": [hand_id]}

    repair_tool.repair(clean, found, commit=True, delete_misclassified=True)
    _import(config)

    assert _rows(Database(config), HANDS) == expected


def test_apply_and_rehearse_cannot_be_combined() -> None:
    with pytest.raises(SystemExit):
        repair_tool.build_parser().parse_args(["--apply", "--rehearse"])


def test_the_command_line_backs_up_and_repairs(open_copy, monkeypatch, tmp_path, capsys) -> None:
    config, damaged = open_copy("damaged")
    _config, clean = open_copy("clean")
    monkeypatch.setattr(repair_tool, "Config", lambda **_kwargs: config)
    monkeypatch.setattr(repair_tool, "Database", lambda _config: damaged)
    backup = tmp_path / "before.sqlite3"

    assert repair_tool.main([]) == 0
    assert "Dry run" in capsys.readouterr().out

    assert repair_tool.main(["--apply", "--backup", str(backup)]) == 0
    out = capsys.readouterr().out
    assert "Backup:" in out and backup.exists()
    assert "#591" in out
    assert _rows(damaged, HANDS) == _rows(clean, HANDS)
