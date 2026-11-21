"""PokerStars on Betfair: a PokerStars skin with its own room and folders (#733).

Betfair's 2026 client writes PokerStars hand histories and tournament
summaries under ``%LOCALAPPDATA%\\Betfair.UK\\HandHistory`` and
``\\TournSummary`` (PokerTracker 4.19's documentation), under its own name:
"Betfair Hand #N" and "Betfair Tournament #N" where PokerStars writes
"PokerStars". That header files them under their own room wherever they lie;
the folder still files PokerStars-headed files found in it.

The real export is a 3-max sit & go shared on #854, anonymised with
tools/anonymize_hh.py: six hands and the tournament's summary.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import fpdb_3_legacy.DetectInstalledSites as detect_module
from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.DetectInstalledSites import PokerStarsDetector
from fpdb_3_legacy.PokerStarsToFpdb import POKERSTARS_SKIN_IDS, SITE_POKERSTARS_BETFAIR, PokerStars

ROOT = Path(__file__).resolve().parents[1]
CASH_HAND = ROOT / "regression-test-files/cash/Stars/Flop/2025-NL-uncalled-bet.txt"
SUMMARY = ROOT / "regression-test-files/summaries/Stars/6+Holdem-3max-STT-USD-1.00-201907.txt"
SKIN = "PokerStars on Betfair"
# The real export (#854), hands and summary of the same sit & go.
BETFAIR_NAME = "NLHE-3max-STT-USD-0.46-0.04-202610.Betfair.txt"
BETFAIR_HANDS = ROOT / "regression-test-files/tour/Stars/Flop" / BETFAIR_NAME
BETFAIR_SUMMARY = ROOT / "regression-test-files/summaries/Stars" / BETFAIR_NAME


def _parser() -> PokerStars:
    return PokerStars.__new__(PokerStars)


# ---------------------------------------------------------------------------
# The skin's identity
# ---------------------------------------------------------------------------


def test_the_skin_has_its_own_site_id() -> None:
    assert POKERSTARS_SKIN_IDS[SKIN] == SITE_POKERSTARS_BETFAIR == 143


@pytest.mark.parametrize(
    "path",
    [
        r"C:\Users\alice\AppData\Local\Betfair.UK\HandHistory\alice\HH20260917 Table.txt",
        "/home/alice/.wine/drive_c/users/alice/AppData/Local/Betfair.UK/TournSummary/alice/TS20260917.txt",
    ],
)
def test_the_betfair_folder_names_the_skin(path: str) -> None:
    assert _parser()._detectSkinByPath(path) == (SKIN, 143)


@pytest.mark.parametrize(
    "path",
    [
        r"C:\Users\alice\AppData\Local\PokerStars.FR\HandHistory\alice\HH.txt",
        # "Betfair" in a screen name or a Windows user is not Betfair's client.
        r"C:\Users\alice\AppData\Local\PokerStars.FR\HandHistory\BetfairGrinder\HH.txt",
        r"C:\Users\betfair.uk.fan\AppData\Local\PokerStars.FR\HandHistory\alice\HH.txt",
    ],
)
def test_pokerstars_own_folders_are_unchanged(path: str) -> None:
    assert _parser()._detectSkinByPath(path) == ("PokerStars.FR", 33)


def test_the_room_policy_is_pokerstars() -> None:
    from fpdb_3_legacy import hud_room_policy

    assert hud_room_policy.capabilities_at(SKIN) == hud_room_policy.capabilities_at("PokerStars.FR")
    assert hud_room_policy.why_not("dynamic_hud", SKIN)


# ---------------------------------------------------------------------------
# The client's own header (#854)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", [BETFAIR_HANDS, BETFAIR_SUMMARY], ids=["hands", "summary"])
def test_the_betfair_header_names_the_skin_wherever_the_file_lies(path: Path) -> None:
    text = path.read_text(encoding="utf-8-sig")
    elsewhere = r"C:\Users\alice\AppData\Local\PokerStars.FR\HandHistory\alice\HH.txt"

    assert _parser().detectPokerStarsSkin(text, elsewhere) == (SKIN, 143)
    assert _parser().detectPokerStarsSkin("\ufeff" + text, None) == (SKIN, 143)


def test_the_betfair_header_outranks_a_hero_mapping() -> None:
    parser = _parser()
    parser._hero_mappings = {"hero": "PokerStars.COM"}

    assert parser.detectPokerStarsSkin(BETFAIR_HANDS.read_text(encoding="utf-8-sig")) == (SKIN, 143)


def test_both_converters_recognise_the_betfair_header() -> None:
    from fpdb_3_legacy.PokerStarsSummary import PokerStarsSummary

    assert PokerStars.re_identify.search(BETFAIR_HANDS.read_text(encoding="utf-8-sig"))
    assert PokerStarsSummary.re_identify.search(BETFAIR_SUMMARY.read_text(encoding="utf-8"))


def test_the_old_betfair_poker_client_is_not_taken_for_pokerstars() -> None:
    old_client = "***** Betfair Poker Hand History for Game 123456789 *****\n"

    assert not PokerStars.re_identify.search(old_client)
    assert _parser()._detectSkinByContent(old_client) == ("PokerStars.COM", 32)


@pytest.fixture
def parser_config(tmp_path) -> Config:
    shutil.copyfile(ROOT / "HUD_config.xml.example", tmp_path / "HUD_config.xml")
    return Config(file=str(tmp_path / "HUD_config.xml"))


def test_the_real_hands_are_read_whole(parser_config) -> None:
    parser = PokerStars(config=parser_config, in_path=str(BETFAIR_HANDS), autostart=True)
    hands = parser.getProcessedHands()

    assert (parser.numErrors, parser.numPartial) == (0, 0)
    assert [hand.handid for hand in hands] == [
        "262450453117",
        "262450467817",
        "262450474211",
        "262450482173",
        "262450493121",
        "262450494272",
    ]
    for hand in hands:
        assert (hand.sitename, hand.siteId) == (SKIN, 143)
        assert hand.gametype["type"] == "tour"
        assert (hand.tourNo, hand.buyin, hand.fee, hand.buyinCurrency) == ("4040982342", 46, 4, "USD")
        assert (hand.maxseats, hand.hero) == (3, "Hero")
        assert hand.totalpot == hand.totalcollected
    assert [hand.level for hand in hands] == ["I", "II", "II", "III", "IV", "IV"]


def test_the_real_summary_ranks_every_player() -> None:
    from fpdb_3_legacy.PokerStarsSummary import PokerStarsSummary
    from tests.helpers.summary_regression import make_summary, read_text, summary_fingerprint

    summary = make_summary(PokerStarsSummary, read_text(BETFAIR_SUMMARY), SKIN, 143, "summary")
    summary.parseSummary()
    tournament = summary_fingerprint(summary)["tournament"]
    players = summary_fingerprint(summary)["players"]

    assert tournament["tourNo"] == "4040982342"
    assert [tournament[key] for key in ("buyin", "fee", "currency", "entries")] == [46, 4, "USD", 3]
    # The winner's "$1.00 Power Path Step 2 Ticket" is counted at its value.
    assert [(player["name"], player["rank"], player["winnings"]) for player in players] == [
        ("alice", 1, 100),
        ("Hero", 2, 0),
        ("bob", 3, 0),
    ]


# ---------------------------------------------------------------------------
# Hands and summaries go through the PokerStars converters unchanged
# ---------------------------------------------------------------------------


@pytest.fixture
def importer(tmp_path):
    from fpdb_3_legacy.Database import Database
    from fpdb_3_legacy.Importer import Importer

    shutil.copyfile(ROOT / "HUD_config.xml", tmp_path / "HUD_config.xml")
    config = Config(file=str(tmp_path / "HUD_config.xml"))
    params = config.get_db_parameters()
    params.update(
        {
            "db-server": "sqlite",
            "db-backend": 4,
            "db-databaseName": str(tmp_path / "betfair.sqlite3"),
            "db-path": "",
        }
    )
    config.get_db_parameters = lambda: params
    schema = Database(config)
    schema.recreate_tables()
    schema.close_connection()
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.setCallHud(False)
    yield importer
    importer.close()


def _betfair_copy(tmp_path: Path, folder: str, source: Path) -> Path:
    target = tmp_path / "AppData" / "Local" / "Betfair.UK" / folder / "alice" / source.name
    target.parent.mkdir(parents=True)
    shutil.copyfile(source, target)
    return target


def test_hands_from_the_betfair_folder_are_filed_under_the_skin(importer, tmp_path) -> None:
    importer.addImportFile(str(_betfair_copy(tmp_path, "HandHistory", CASH_HAND)), "auto")
    stored, _dups, _partial, _skipped, errors, _time = importer.runImport()

    assert stored >= 1
    assert errors == 0
    cursor = importer.database.get_cursor()
    cursor.execute(
        "SELECT DISTINCT s.name FROM Hands h JOIN Gametypes g ON h.gametypeId = g.id JOIN Sites s ON g.siteId = s.id"
    )
    assert [row[0] for row in cursor.fetchall()] == [SKIN]


def test_summaries_from_the_betfair_folder_are_filed_under_the_skin(importer, tmp_path) -> None:
    importer.addImportFile(str(_betfair_copy(tmp_path, "TournSummary", SUMMARY)), "auto")
    importer.runImport()

    cursor = importer.database.get_cursor()
    cursor.execute("SELECT DISTINCT s.name FROM TourneyTypes t JOIN Sites s ON t.siteId = s.id")
    assert [row[0] for row in cursor.fetchall()] == [SKIN]


def test_the_real_export_is_filed_under_the_skin_from_any_folder(importer, tmp_path) -> None:
    # Neither file lies under Betfair.UK: their header alone names the room.
    for source in (BETFAIR_HANDS, BETFAIR_SUMMARY):
        target = tmp_path / "elsewhere" / source.parent.name / source.name
        target.parent.mkdir(parents=True)
        shutil.copyfile(source, target)
        importer.addImportFile(str(target), "auto")
    _stored, _dups, _partial, _skipped, errors, _time = importer.runImport()

    assert errors == 0
    cursor = importer.database.get_cursor()
    cursor.execute("SELECT COUNT(*) FROM Hands")
    assert cursor.fetchone()[0] == 6
    cursor.execute(
        "SELECT DISTINCT s.name FROM Hands h JOIN Gametypes g ON h.gametypeId = g.id JOIN Sites s ON g.siteId = s.id"
    )
    assert [row[0] for row in cursor.fetchall()] == [SKIN]
    cursor.execute(
        "SELECT p.name, tp.rank, tp.winnings FROM TourneysPlayers tp"
        " JOIN Tourneys t ON tp.tourneyId = t.id JOIN Players p ON tp.playerId = p.id"
        " WHERE t.siteTourneyNo = 4040982342 ORDER BY tp.rank"
    )
    assert cursor.fetchall() == [("alice", 1, 100), ("Hero", 2, 0), ("bob", 3, 0)]
    cursor.execute("SELECT DISTINCT p.siteId FROM Players p WHERE p.name IN ('alice', 'Hero', 'bob')")
    assert [row[0] for row in cursor.fetchall()] == [143]


def test_an_older_database_gains_the_sites_row(importer) -> None:
    database = importer.database
    cursor = database.get_cursor()
    cursor.execute("DELETE FROM Sites WHERE id = 143")
    database.commit()

    database.ensure_sites_rows()

    cursor.execute("SELECT name, code FROM Sites WHERE id = 143")
    assert cursor.fetchall() == [(SKIN, "PS")]


# ---------------------------------------------------------------------------
# Folder detection
# ---------------------------------------------------------------------------


@pytest.fixture
def detector() -> PokerStarsDetector:
    config = MagicMock()
    config.os_family = "Win7"
    return PokerStarsDetector(config)


def _windows_paths(local: Path, elsewhere: Path) -> dict[str, str]:
    return {
        "local_appdata": str(local),
        "appdata": str(elsewhere),
        "program_files": str(elsewhere),
        "program_files_x86": str(elsewhere),
    }


def test_the_betfair_client_folder_is_found_on_windows(detector, tmp_path) -> None:
    local = tmp_path / "AppData" / "Local"
    (local / "Betfair.UK" / "HandHistory" / "alice").mkdir(parents=True)
    (local / "Betfair.UK" / "TournSummary" / "alice").mkdir(parents=True)
    detector.platform = "Windows"

    with patch.object(detect_module, "get_windows_paths", return_value=_windows_paths(local, tmp_path / "x")):
        found = detector._detect_variant(SKIN)
        everything = detector.detect()

    assert found["detected"]
    assert found["variant"] == SKIN
    assert found["heroname"] == "alice"
    assert Path(found["hhpath"]) == local / "Betfair.UK" / "HandHistory" / "alice"
    assert Path(found["tspath"]) == local / "Betfair.UK" / "TournSummary" / "alice"
    assert [variant["variant"] for variant in detector.all_detected_variants] == [SKIN]
    assert everything["variant"] == SKIN


def test_histories_written_without_a_player_folder_are_still_found(detector, tmp_path) -> None:
    local = tmp_path / "AppData" / "Local"
    history = local / "Betfair.UK" / "HandHistory"
    history.mkdir(parents=True)
    (history / "HH20260917 Table.txt").write_text("PokerStars Hand #1:", encoding="utf-8")
    detector.platform = "Windows"

    with patch.object(detect_module, "get_windows_paths", return_value=_windows_paths(local, tmp_path / "x")):
        found = detector._detect_variant(SKIN)

    assert found["detected"]
    assert Path(found["hhpath"]) == history
    assert found["heroname"] == ""


def _flat_history(tmp_path: Path, files: dict[str, str]) -> Path:
    """A Betfair.UK HandHistory folder holding ``files`` directly, newest first."""
    local = tmp_path / "AppData" / "Local"
    history = local / "Betfair.UK" / "HandHistory"
    history.mkdir(parents=True)
    for age, (name, text) in enumerate(files.items()):
        path = history / name
        path.write_text(text, encoding="utf-8")
        os.utime(path, (1_800_000_000 - age * 60, 1_800_000_000 - age * 60))
    return local


def _detect_flat(detector, tmp_path: Path, local: Path) -> dict[str, Any]:
    detector.platform = "Windows"
    with patch.object(detect_module, "get_windows_paths", return_value=_windows_paths(local, tmp_path / "x")):
        return detector._detect_variant(SKIN)


def test_the_real_export_names_its_hero_without_a_player_folder(detector, tmp_path) -> None:
    # The #854 reporter's files lie straight in HandHistory, with their real names:
    # the hero is read from "Dealt to Hero [Qd 2d]" (CRLF, BOM and all).
    local = tmp_path / "AppData" / "Local"
    history = local / "Betfair.UK" / "HandHistory"
    history.mkdir(parents=True)
    shutil.copyfile(BETFAIR_HANDS, history / "HH20261019 T4040982342 No Limit Hold'em $0.46 + $0.04.txt")

    found = _detect_flat(detector, tmp_path, local)

    assert found["detected"]
    assert Path(found["hhpath"]) == history
    assert found["heroname"] == "Hero"


def test_the_newest_history_names_the_hero(detector, tmp_path) -> None:
    local = _flat_history(
        tmp_path,
        {
            "HH20261020 new.txt": "Betfair Hand #2: ...\nDealt to new name [Ah Kh]\n",
            "HH20261019 old.txt": "Betfair Hand #1: ...\nDealt to old_name [2c 3c]\n",
        },
    )

    assert _detect_flat(detector, tmp_path, local)["heroname"] == "new name"


def test_a_stud_opponents_upcards_do_not_name_the_hero(detector, tmp_path) -> None:
    # Stud lists every upcard as "Dealt to": one card a street for an opponent,
    # the hero's own three on third street.
    local = _flat_history(
        tmp_path,
        {
            "HH20261019 stud.txt": (
                "Betfair Hand #3: 7 Card Stud\n*** 3rd STREET ***\n"
                "Dealt to bob [4h]\nDealt to Hero [2c 3d 5s]\n*** 4th STREET ***\nDealt to bob [4h] [9c]\n"
            )
        },
    )

    assert _detect_flat(detector, tmp_path, local)["heroname"] == "Hero"


def test_the_betfair_client_folder_is_found_under_wine(detector, tmp_path) -> None:
    users = tmp_path / ".wine" / "drive_c" / "users"
    (users / "alice" / "AppData" / "Local" / "Betfair.UK" / "HandHistory" / "alice").mkdir(parents=True)
    detector.platform = "Linux"
    paths: dict[str, Any] = {
        "wine_drive_c": str(tmp_path / ".wine" / "drive_c"),
        "wine_program_files": str(tmp_path / "pf"),
        "wine_program_files_x86": str(tmp_path / "pf86"),
        "wine_users": str(users),
    }

    with patch.object(detect_module, "get_linux_paths", return_value=paths):
        found = detector._detect_variant(SKIN)

    assert found["detected"]
    assert found["heroname"] == "alice"


def test_no_betfair_client_means_no_betfair_variant(detector, tmp_path) -> None:
    detector.platform = "Windows"
    with patch.object(detect_module, "get_windows_paths", return_value=_windows_paths(tmp_path, tmp_path)):
        assert detector._detect_variant(SKIN)["detected"] is False
