"""PokerStars.UK: the retired UK client's histories, under a legacy room of their own (#889).

The standalone PokerStars UK client was retired on 7 October 2026, when its
players moved to PokerStars on Betfair. Its histories name no skin: only the
``PokerStars.UK`` folder the client wrote them to, or an explicit hero mapping,
tells them from PokerStars.COM's.

No authentic UK export is in the corpus yet. These tests run PokerStars' own
fixtures from a UK folder: they pin how hands are *filed*, and are no evidence
that the parser reads every UK-specific line.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import fpdb_3_legacy.DetectInstalledSites as detect_module
from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.DetectInstalledSites import PokerStarsDetector
from fpdb_3_legacy.PokerStarsToFpdb import (
    POKERSTARS_RETIRED_SKINS,
    POKERSTARS_SKIN_IDS,
    SITE_POKERSTARS_COM,
    SITE_POKERSTARS_UK,
    PokerStars,
)

ROOT = Path(__file__).resolve().parents[1]
CASH_HAND = ROOT / "regression-test-files/cash/Stars/Flop/2025-NL-uncalled-bet.txt"
SUMMARY = ROOT / "regression-test-files/summaries/Stars/6+Holdem-3max-STT-USD-1.00-201907.txt"
SKIN = "PokerStars.UK"

UK_FOLDER = r"C:\Users\alice\AppData\Local\PokerStars.UK\HandHistory\alice\HH20260601 Table.txt"


def _hand(date: str, *, hero: str = "alice", currency: str = "£", iso: str = "GBP") -> str:
    """A PokerStars header dated ``date`` (``YYYY/MM/DD``), local and ET alike."""
    return (
        f"PokerStars Hand #1:  Hold'em No Limit ({currency}0.02/{currency}0.05 {iso}) - "
        f"{date} 17:21:34 GMT [{date} 12:21:34 ET]\n"
        "Table 'Alpha' 6-max Seat #1 is the button\n"
        f"Seat 1: {hero} ({currency}5 in chips)\n"
        "*** HOLE CARDS ***\n"
        f"Dealt to {hero} [Ah Kd]\n"
    )


def _parser(mappings: dict[str, str] | None = None) -> PokerStars:
    parser = PokerStars.__new__(PokerStars)
    parser._hero_mappings = mappings or {}
    return parser


# ---------------------------------------------------------------------------
# The skin's identity
# ---------------------------------------------------------------------------


def test_the_skin_has_its_own_site_id() -> None:
    # Not PokerStars on Betfair (143), nor the legacy Betfair (7) or iPoker (66) rooms.
    assert POKERSTARS_SKIN_IDS[SKIN] == SITE_POKERSTARS_UK == 145
    assert list(POKERSTARS_SKIN_IDS.values()).count(145) == 1
    assert POKERSTARS_SKIN_IDS["PokerStars on Betfair"] == 143
    assert {7, 66}.isdisjoint(POKERSTARS_SKIN_IDS.values())


def test_the_client_closed_on_7_october_2026() -> None:
    assert POKERSTARS_RETIRED_SKINS[SKIN].isoformat() == "2026-10-07"


def test_the_room_policy_is_pokerstars() -> None:
    from fpdb_3_legacy import hud_room_policy

    assert hud_room_policy.capabilities_at(SKIN) == hud_room_policy.capabilities_at("PokerStars.FR")


# ---------------------------------------------------------------------------
# Provenance: the UK folder, or an explicit hero mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        UK_FOLDER,
        r"C:\Users\alice\AppData\Local\PokerStars.UK\TournSummary\alice\TS20260601.txt",
        "/home/alice/.wine/drive_c/users/alice/AppData/Local/PokerStars.UK/HandHistory/alice/HH.txt",
    ],
)
def test_the_uk_folder_names_the_skin(path: str) -> None:
    assert _parser()._detectSkinByPath(path) == (SKIN, 145)
    assert _parser().detectPokerStarsSkin(_hand("2026/06/01"), path) == (SKIN, 145)


@pytest.mark.parametrize(
    "path",
    [
        # "PokerStars.UK" inside a screen name or a Windows user is not the client's folder.
        r"C:\Users\alice\AppData\Local\PokerStars.FR\HandHistory\PokerStars.UKfan\HH.txt",
        r"C:\Users\pokerstars.uk.fan\AppData\Local\PokerStars.FR\HandHistory\alice\HH.txt",
    ],
)
def test_a_lookalike_name_is_not_the_uk_folder(path: str) -> None:
    assert _parser()._detectSkinByPath(path) == ("PokerStars.FR", 33)


def test_an_explicit_hero_mapping_files_copied_hands_under_the_skin() -> None:
    parser = _parser({"alice": SKIN})

    assert parser.detectPokerStarsSkin(_hand("2026/06/01"), "/tmp/copied/HH.txt") == (SKIN, 145)


# ---------------------------------------------------------------------------
# Nothing else makes a hand a UK hand
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", [None, "/tmp/copied/HH20260601 Table.txt", r"C:\PokerStars\HandHistory\alice\HH.txt"])
def test_a_gbp_hand_outside_the_uk_folder_stays_generic(path: str | None) -> None:
    # Currency is no provenance: PokerStars.COM and Betfair players play in GBP too.
    assert _parser().detectPokerStarsSkin(_hand("2026/06/01"), path) == ("PokerStars.COM", SITE_POKERSTARS_COM)


@pytest.mark.parametrize("hero", ["alice.uk", "alice_uk", "London.UK"])
def test_a_uk_looking_screen_name_is_no_provenance(hero: str) -> None:
    skin, _site_id = _parser().detectPokerStarsSkin(_hand("2026/06/01", hero=hero), "/tmp/copied/HH.txt")

    assert skin != SKIN


# ---------------------------------------------------------------------------
# Nothing dealt after the client closed is a UK hand
# ---------------------------------------------------------------------------


def test_a_hand_dealt_after_the_client_closed_is_not_filed_under_it() -> None:
    # A PokerStars on Betfair hand saved next to the old ones keeps the UK folder.
    assert _parser().detectPokerStarsSkin(_hand("2026/10/08"), UK_FOLDER) == ("PokerStars.COM", SITE_POKERSTARS_COM)


def test_a_hero_mapping_does_not_reach_past_the_closing_day() -> None:
    # The same screen name carries on at PokerStars on Betfair.
    parser = _parser({"alice": SKIN})

    assert parser.detectPokerStarsSkin(_hand("2026/11/01"), "/tmp/copied/HH.txt")[0] != SKIN


def test_the_last_day_is_still_the_uk_client() -> None:
    assert _parser().detectPokerStarsSkin(_hand("2026/10/07"), UK_FOLDER) == (SKIN, 145)


def test_a_late_local_date_with_an_earlier_et_date_is_still_the_uk_client() -> None:
    hand = "PokerStars Hand #1:  Hold'em No Limit (£0.02/£0.05 GBP) - 2026/10/08 0:30:00 BST [2026/10/07 19:30:00 ET]\n"

    assert _parser().detectPokerStarsSkin(hand, UK_FOLDER) == (SKIN, 145)


def test_a_hand_with_no_readable_date_goes_by_its_folder() -> None:
    assert _parser().detectPokerStarsSkin("PokerStars Hand #1:  Hold'em No Limit (£0.02/£0.05 GBP)\n", UK_FOLDER) == (
        SKIN,
        145,
    )


def test_other_skins_are_not_bounded_by_the_uk_closing_day() -> None:
    path = r"C:\Users\alice\AppData\Local\PokerStars.FR\HandHistory\alice\HH.txt"

    assert _parser().detectPokerStarsSkin(_hand("2026/11/01", currency="€", iso="EUR"), path) == ("PokerStars.FR", 33)


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
            "db-databaseName": str(tmp_path / "uk.sqlite3"),
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


def _copy(tmp_path: Path, root: str, folder: str, source: Path) -> Path:
    target = tmp_path / "AppData" / "Local" / root / folder / "alice" / source.name
    target.parent.mkdir(parents=True)
    shutil.copyfile(source, target)
    return target


def _hand_sites(importer) -> list[str]:
    cursor = importer.database.get_cursor()
    cursor.execute(
        "SELECT DISTINCT s.name FROM Hands h JOIN Gametypes g ON h.gametypeId = g.id JOIN Sites s ON g.siteId = s.id"
    )
    return [row[0] for row in cursor.fetchall()]


def test_hands_from_the_uk_folder_are_filed_under_the_skin(importer, tmp_path) -> None:
    importer.addImportFile(str(_copy(tmp_path, "PokerStars.UK", "HandHistory", CASH_HAND)), "auto")
    stored, _dups, _partial, _skipped, errors, _time = importer.runImport()

    assert stored >= 1
    assert errors == 0
    assert _hand_sites(importer) == [SKIN]


def test_the_same_hands_elsewhere_stay_where_they_were(importer, tmp_path) -> None:
    # Already-imported generic PokerStars hands are never moved to the UK room.
    importer.addImportFile(str(_copy(tmp_path, "PokerStars", "HandHistory", CASH_HAND)), "auto")
    importer.runImport()

    assert _hand_sites(importer) == ["PokerStars.COM"]


def test_summaries_from_the_uk_folder_are_filed_under_the_skin(importer, tmp_path) -> None:
    importer.addImportFile(str(_copy(tmp_path, "PokerStars.UK", "TournSummary", SUMMARY)), "auto")
    importer.runImport()

    cursor = importer.database.get_cursor()
    cursor.execute("SELECT DISTINCT s.name FROM TourneyTypes t JOIN Sites s ON t.siteId = s.id")
    assert [row[0] for row in cursor.fetchall()] == [SKIN]


def test_a_new_database_has_the_sites_row(importer) -> None:
    cursor = importer.database.get_cursor()
    cursor.execute("SELECT name, code FROM Sites WHERE id = 145")
    assert cursor.fetchall() == [(SKIN, "PS")]


def test_an_older_database_gains_the_sites_row(importer) -> None:
    database = importer.database
    cursor = database.get_cursor()
    cursor.execute("DELETE FROM Sites WHERE id = 145")
    database.commit()

    database.ensure_sites_rows()

    cursor.execute("SELECT name, code FROM Sites WHERE id = 145")
    assert cursor.fetchall() == [(SKIN, "PS")]


# ---------------------------------------------------------------------------
# Folder detection
# ---------------------------------------------------------------------------


@pytest.fixture
def detector() -> PokerStarsDetector:
    config = MagicMock()
    config.os_family = "Win7"
    return PokerStarsDetector(config)


def test_the_uk_client_folder_is_found_on_windows(detector, tmp_path) -> None:
    local = tmp_path / "AppData" / "Local"
    (local / "PokerStars.UK" / "HandHistory" / "alice").mkdir(parents=True)
    (local / "PokerStars.UK" / "TournSummary" / "alice").mkdir(parents=True)
    elsewhere = str(tmp_path / "x")
    paths = {
        "local_appdata": str(local),
        "appdata": elsewhere,
        "program_files": elsewhere,
        "program_files_x86": elsewhere,
    }
    detector.platform = "Windows"

    with patch.object(detect_module, "get_windows_paths", return_value=paths):
        detector.detect()

    found = [variant for variant in detector.all_detected_variants if variant["variant"] == SKIN]
    assert len(found) == 1
    assert found[0]["heroname"] == "alice"
    assert Path(found[0]["hhpath"]) == local / "PokerStars.UK" / "HandHistory" / "alice"
    assert Path(found[0]["tspath"]) == local / "PokerStars.UK" / "TournSummary" / "alice"


def test_the_uk_client_folder_is_found_in_a_wine_users_appdata(detector, tmp_path) -> None:
    users = tmp_path / ".wine" / "drive_c" / "users"
    local = users / "alice" / "AppData" / "Local" / "PokerStars.UK"
    (local / "HandHistory" / "alice").mkdir(parents=True)
    (local / "TournSummary" / "alice").mkdir(parents=True)
    paths = {
        "wine_drive_c": str(tmp_path / ".wine" / "drive_c"),
        "wine_program_files": str(tmp_path / "pf"),
        "wine_program_files_x86": str(tmp_path / "pf86"),
        "wine_users": str(users),
    }
    detector.platform = "Linux"

    with patch.object(detect_module, "get_linux_paths", return_value=paths):
        found = detector._detect_variant(SKIN)

    assert found["detected"]
    assert found["heroname"] == "alice"
    assert Path(found["hhpath"]) == local / "HandHistory" / "alice"
    assert Path(found["tspath"]) == local / "TournSummary" / "alice"
