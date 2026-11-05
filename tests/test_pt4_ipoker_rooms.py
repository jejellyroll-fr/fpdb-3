"""A PokerTracker 4 iPoker hand goes to the room its hero plays on (#702).

No iPoker file names its skin and table names are shared across skins, so the
screen names in the configuration are what tell rooms apart. The fixture is two
accounts' hands, names replaced: alice's on one room, bob's on another with a
tournament and its summary. Configurations are changed in memory only.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from fpdb_3_legacy import ipoker_rooms
from fpdb_3_legacy.IdentifySite import IdentifySite
from fpdb_3_legacy.Importer import Importer
from fpdb_3_legacy.PokerTrackerSummary import PokerTrackerSummary
from fpdb_3_legacy.PokerTrackerToFpdb import PokerTracker
from fpdb_3_legacy.tracker_migration import scan_folder

ROOT = Path(__file__).resolve().parents[1]
EXPORT = ROOT / "tests" / "fixtures" / "pokertracker_ipoker_rooms"
ALICE_HAND = EXPORT / "Saratov, 560234179 - alice.txt"
BOB_HAND = EXPORT / "Saratov, 560234179 - bob.txt"
BOB_TOURNAMENT = EXPORT / "T#1192577340 - bob.txt"
BOB_SUMMARY = EXPORT / "T#1192577340 - bob - Summary.txt"
ARCHIVE_XML = ROOT / "tests" / "fixtures" / "pokertracker_ipoker_rooms_archive" / "alice.xml"


def _skin(name: str, screen_name: str = "", *, enabled: bool = True, aliases: tuple[str, ...] = ()) -> SimpleNamespace:
    return SimpleNamespace(
        site_name=name,
        screen_name=screen_name,
        hero_aliases=[screen_name, *aliases] if screen_name else [],
        enabled=enabled,
        network="iPoker",
        HH_path="",
        TS_path="",
    )


def _config(*skins: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(supported_sites={skin.site_name: skin for skin in skins})


@pytest.fixture
def accounts(legacy_config, monkeypatch):
    """Alice plays on PMU Poker and bob on Bwin.fr Poker; no other iPoker room is enabled."""
    for site in ipoker_rooms.skins_of(legacy_config):
        monkeypatch.setattr(site, "enabled", False)
    for room, name in (("PMU Poker", "alice"), ("Bwin.fr Poker", "bob")):
        site = legacy_config.supported_sites[room]
        monkeypatch.setattr(site, "enabled", True)
        monkeypatch.setattr(site, "screen_name", name)
        monkeypatch.setattr(site, "hero_aliases", [name])
        monkeypatch.setattr(site, "HH_path", "")
        monkeypatch.setattr(site, "TS_path", "")
    return legacy_config


@pytest.fixture
def undecided(legacy_config, monkeypatch):
    """Several iPoker rooms enabled, none holding the export's heroes: the shipped situation."""
    for room in ("PMU Poker", "Bwin.fr Poker"):
        site = legacy_config.supported_sites[room]
        monkeypatch.setattr(site, "enabled", True)
        monkeypatch.setattr(site, "screen_name", "someone")
        monkeypatch.setattr(site, "hero_aliases", ["someone"])
        monkeypatch.setattr(site, "HH_path", "")
        monkeypatch.setattr(site, "TS_path", "")
    return legacy_config


def _importer(config, database) -> Importer:
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.database = database
    importer.setCallHud(False)
    return importer


def _rows(database, query: str) -> dict[str, int]:
    cursor = database.get_cursor()
    cursor.execute(query)
    return dict(cursor.fetchall())


HANDS_BY_ROOM = (
    "SELECT s.name, COUNT(*) FROM Hands h JOIN Gametypes g ON g.id = h.gametypeId "
    "JOIN Sites s ON s.id = g.siteId GROUP BY s.name"
)
TOURNEYS_BY_ROOM = (
    "SELECT s.name, COUNT(*) FROM Tourneys t JOIN TourneyTypes tt ON tt.id = t.tourneyTypeId "
    "JOIN Sites s ON s.id = tt.siteId GROUP BY s.name"
)


# --- the rule ---------------------------------------------------------------


def test_a_hero_goes_to_the_room_holding_their_screen_name() -> None:
    config = _config(_skin("PMU Poker", "alice"), _skin("Bwin.fr Poker", "bob"))

    assert ipoker_rooms.room_for(config, ["alice"]) == "PMU Poker"
    assert ipoker_rooms.room_for(config, ["bob"]) == "Bwin.fr Poker"


def test_a_screen_name_is_matched_whatever_its_case() -> None:
    assert ipoker_rooms.room_for(_config(_skin("PMU Poker", "Alice"), _skin("FDJ Poker", "bob")), ["aLiCe"]) == "PMU Poker"


def test_a_hero_alias_counts_as_the_account() -> None:
    config = _config(_skin("PMU Poker", "alice", aliases=("alice2",)), _skin("FDJ Poker", "bob"))

    assert ipoker_rooms.room_for(config, ["alice2"]) == "PMU Poker"


def test_a_summary_finds_the_hero_among_its_players() -> None:
    config = _config(_skin("PMU Poker", "alice"), _skin("Bwin.fr Poker", "bob"))

    assert ipoker_rooms.room_for(config, ["carol", "bob", "dave"]) == "Bwin.fr Poker"


def test_a_disabled_room_holding_the_name_beats_the_one_enabled_room() -> None:
    config = _config(_skin("PMU Poker", "alice"), _skin("Unibet Poker", "bob", enabled=False))

    assert ipoker_rooms.room_for(config, ["bob"]) == "Unibet Poker"


def test_an_enabled_room_beats_a_disabled_one_holding_the_same_name() -> None:
    config = _config(_skin("PMU Poker", "alice"), _skin("FDJ Poker", "alice", enabled=False))

    assert ipoker_rooms.room_for(config, ["alice"]) == "PMU Poker"


def test_a_name_held_on_two_enabled_rooms_settles_nothing() -> None:
    config = _config(_skin("PMU Poker", "alice"), _skin("FDJ Poker", "alice"))

    assert ipoker_rooms.room_for(config, ["alice"]) is None


def test_the_only_enabled_room_takes_an_unknown_hero() -> None:
    config = _config(_skin("PMU Poker", ""), _skin("FDJ Poker", "", enabled=False))

    assert ipoker_rooms.room_for(config, ["alice"]) == "PMU Poker"
    assert ipoker_rooms.room_for(config, []) == "PMU Poker"


def test_several_enabled_rooms_and_an_unknown_hero_settle_nothing() -> None:
    assert ipoker_rooms.room_for(_config(_skin("PMU Poker"), _skin("FDJ Poker")), ["alice"]) is None


def test_the_users_answer_beats_the_configuration() -> None:
    config = _config(_skin("PMU Poker", "alice"), _skin("FDJ Poker"))

    assert ipoker_rooms.room_for(config, ["alice"], {"alice": "FDJ Poker"}) == "FDJ Poker"


def test_the_rooms_offered_start_with_the_enabled_ones() -> None:
    config = _config(_skin("Betclic Poker", enabled=False), _skin("PMU Poker"), _skin("FDJ Poker"))

    assert ipoker_rooms.room_choices(config) == ["FDJ Poker", "PMU Poker", "Betclic Poker"]


# --- every route ------------------------------------------------------------


@pytest.mark.parametrize("table", ["Saratov", "Scone", "Moscow", "Coral", "Skyline", "Winner 3", "PMU"])
def test_a_table_name_chooses_no_room(undecided, table) -> None:
    text = ALICE_HAND.read_text("utf-8").replace("Table Saratov, 560234179", f"Table {table}, 560234179")

    found = IdentifySite(undecided).idSite("export.txt", text, "utf-8")

    assert found.site.name == "iPoker"
    assert found.undecided_hero == "alice"


def test_the_scan_previews_each_account_under_its_room(accounts) -> None:
    scan = scan_folder(accounts, str(EXPORT))

    assert {room: len(files) for room, files in scan.rooms.items()} == {"PMU Poker": 1, "Bwin.fr Poker": 3}
    assert scan.undecided == {}


def test_the_scan_holds_back_a_hero_only_the_user_can_place(undecided) -> None:
    scan = scan_folder(undecided, str(EXPORT))

    assert {hero: len(files) for hero, files in scan.undecided.items()} == {"alice": 1, "bob": 2}
    assert {room: len(files) for room, files in scan.rooms.items()} == {"iPoker": 4}


def test_a_merge_hand_keeps_the_room_its_header_names(accounts) -> None:
    path = ROOT / "regression-test-files/cash/PokerTracker/Flop/NLHE-USD-0.50-1.00-201101.Merge.txt"

    hands = PokerTracker(config=accounts, in_path=str(path), autostart=True, sitename="iPoker").getProcessedHands()

    assert {hand.sitename for hand in hands} == {"Merge"}


def test_the_parser_keeps_the_room_it_is_given(accounts) -> None:
    parser = PokerTracker(config=accounts, in_path=str(BOB_HAND), autostart=True, sitename="Bwin.fr Poker")

    assert {hand.sitename for hand in parser.getProcessedHands()} == {"Bwin.fr Poker"}


def test_a_parser_given_no_room_stays_on_the_network(accounts) -> None:
    parser = PokerTracker(config=accounts, in_path=str(BOB_HAND), autostart=True)

    assert {hand.sitename for hand in parser.getProcessedHands()} == {"iPoker"}


def test_every_player_of_a_summary_is_read() -> None:
    assert PokerTrackerSummary.players_named_in(BOB_SUMMARY.read_text("utf-8")) == ["dave", "carol", "bob"]


def test_archive_xml_goes_to_the_room_of_its_nickname(accounts, tmp_path) -> None:
    path = tmp_path / ARCHIVE_XML.name
    shutil.copy(ARCHIVE_XML, path)

    found = IdentifySite(accounts).idSite(str(path), path.read_text("utf-8"), "utf-8")

    assert found.site.name == "PMU Poker"
    assert found.undecided_hero is None


def test_archive_xml_under_a_rooms_folder_stays_in_that_room(accounts, tmp_path, monkeypatch) -> None:
    client = tmp_path / "bwin" / "History"
    client.mkdir(parents=True)
    path = client / ARCHIVE_XML.name
    shutil.copy(ARCHIVE_XML, path)
    monkeypatch.setattr(accounts.supported_sites["Bwin.fr Poker"], "HH_path", str(client))

    found = IdentifySite(accounts).idSite(str(path), path.read_text("utf-8"), "utf-8")

    assert found.site.name == "Bwin.fr Poker"
    assert found.undecided_hero is None


def test_archive_xml_of_an_unknown_hero_waits_for_the_user(undecided, tmp_path) -> None:
    path = tmp_path / ARCHIVE_XML.name
    shutil.copy(ARCHIVE_XML, path)

    identifier = IdentifySite(undecided)

    assert identifier.idSite(str(path), path.read_text("utf-8"), "utf-8").undecided_hero == "alice"
    identifier.choose_ipoker_rooms({"alice": "FDJ Poker"})
    found = identifier.idSite(str(path), path.read_text("utf-8"), "utf-8")
    assert found.site.name == "FDJ Poker"
    assert found.undecided_hero is None


# --- a real import ----------------------------------------------------------


def test_each_account_imports_into_its_room_with_its_tournament(fresh_db, accounts) -> None:
    importer = _importer(accounts, fresh_db)

    assert importer.addBulkImportImportFileOrDir(str(EXPORT))
    importer.runImport()

    assert _rows(fresh_db, HANDS_BY_ROOM) == {"PMU Poker": 2, "Bwin.fr Poker": 3}
    assert _rows(fresh_db, TOURNEYS_BY_ROOM) == {"Bwin.fr Poker": 1}
    assert {result.site for result in importer.file_results.values()} == {"PMU Poker", "Bwin.fr Poker"}


def test_the_summary_completes_the_tournament_its_hands_opened(fresh_db, accounts) -> None:
    importer = _importer(accounts, fresh_db)

    assert importer.addImportFile(str(BOB_TOURNAMENT))
    assert importer.addImportFile(str(BOB_SUMMARY))
    importer.runImport()

    cursor = fresh_db.get_cursor()
    cursor.execute("SELECT COUNT(*) FROM Tourneys")
    assert cursor.fetchone()[0] == 1
    cursor.execute("SELECT COUNT(*) FROM TourneysPlayers")
    assert cursor.fetchone()[0] == 3
    assert _rows(fresh_db, TOURNEYS_BY_ROOM) == {"Bwin.fr Poker": 1}


def test_archive_xml_imports_into_the_room_of_its_nickname(fresh_db, accounts, tmp_path) -> None:
    path = tmp_path / ARCHIVE_XML.name
    shutil.copy(ARCHIVE_XML, path)
    importer = _importer(accounts, fresh_db)

    assert importer.addImportFile(str(path))
    importer.runImport()

    assert set(_rows(fresh_db, HANDS_BY_ROOM)) == {"PMU Poker"}
    assert importer.file_results[str(path)].site == "PMU Poker"


def test_archive_xml_nothing_places_stays_on_the_network(fresh_db, undecided, tmp_path) -> None:
    path = tmp_path / ARCHIVE_XML.name
    shutil.copy(ARCHIVE_XML, path)
    importer = _importer(undecided, fresh_db)

    assert importer.addImportFile(str(path))
    importer.runImport()

    assert set(_rows(fresh_db, HANDS_BY_ROOM)) == {"iPoker"}


def test_the_users_answers_place_hands_and_summaries(fresh_db, undecided) -> None:
    importer = _importer(undecided, fresh_db)
    importer.setIpokerRooms({"alice": "PMU Poker", "bob": "FDJ Poker"})

    assert importer.addBulkImportImportFileOrDir(str(EXPORT))
    importer.runImport()

    assert _rows(fresh_db, HANDS_BY_ROOM) == {"PMU Poker": 2, "FDJ Poker": 3}
    assert _rows(fresh_db, TOURNEYS_BY_ROOM) == {"FDJ Poker": 1}


def test_an_unplaced_export_stays_on_the_network_outside_the_wizard(fresh_db, undecided) -> None:
    importer = _importer(undecided, fresh_db)

    assert importer.addBulkImportImportFileOrDir(str(EXPORT))
    importer.runImport()

    assert _rows(fresh_db, HANDS_BY_ROOM) == {"iPoker": 5}
    assert _rows(fresh_db, TOURNEYS_BY_ROOM) == {"iPoker": 1}
