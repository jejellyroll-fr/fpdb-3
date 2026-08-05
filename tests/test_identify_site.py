"""Which converter a file is handed to.

IdentifySite reads the head of a file and decides which parser gets it. Send a
file to the wrong converter and it is either refused or, worse, misread; send
nothing and the file is silently skipped. Nothing else in the suite checks that
decision against the corpus.

The whole shipped corpus is the bench here: every room's directory names the
parser its files must be identified as.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.IdentifySite import IdentifySite

ROOT = Path(__file__).resolve().parents[1]
CASH = ROOT / "regression-test-files" / "cash"

# Room directory -> the converter its files belong to. Two are not the identity:
# UltimateBet and Absolute were one network, and every iPoker file identifies as
# one of the network's skins.
EXPECTED_PARSER = {
    "Absolute": "Absolute",
    "BetOnline": "BetOnline",
    "Betfair": "Betfair",
    "Boss": "Boss",
    "Bovada": "Bovada",
    "Cake": "Cake",
    "Enet": "Enet",
    "Entraction": "Entraction",
    "Everest": "Everest",
    "Everleaf": "Everleaf",
    "FTP": "Fulltilt",
    "GGPoker": "GGPoker",
    "KingsClub": "KingsClub",
    "Merge": "Merge",
    "Microgaming": "Microgaming",
    "OnGame": "OnGame",
    "PKR": "Pkr",
    "PacificPoker": "PacificPoker",
    "PartyPoker": "PartyPoker",
    "PokerTracker": "PokerTracker",
    "SealsWithClubs": "SealsWithClubs",
    "Stars": "PokerStars",
    "UltimateBet": "Absolute",
    "Unibet": "Unibet",
    "Winamax": "Winamax",
    "Winning": "Winning",
    "iPoker": "iPoker",
}

# TheBigGame ships a corpus but has no converter, so its files are correctly
# identified as nothing at all.
WITHOUT_A_PARSER = "TheBigGame"

# Sidecar files written by the regression comparator, plus directory noise.
NOT_HAND_HISTORIES = {".gt", ".hands", ".hp", ".py", ".DS_Store"}


def is_candidate(path: Path) -> bool:
    return path.is_file() and path.suffix not in NOT_HAND_HISTORIES and path.name not in NOT_HAND_HISTORIES


def hand_histories(room: str) -> list[Path]:
    return sorted(path for path in (CASH / room).rglob("*") if is_candidate(path) and path.stat().st_size > 0)


@pytest.fixture(scope="module")
def identifier() -> Any:
    """Built from the configuration this repository ships.

    Which converter a file reaches depends on which sites the configuration
    enables: the shipped HUD_config.xml knows 26, while a bare environment with
    no user configuration knows 16, and the ten missing rooms then identify as
    nothing at all. Pinning the shipped file keeps this about identification
    rather than about whose machine runs it.
    """
    return IdentifySite(Config(file=str(ROOT / "HUD_config.xml")))


def test_the_shipped_configuration_knows_the_rooms_it_configures(identifier) -> None:
    # Not every room of the corpus needs an entry: PokerTracker files are
    # exports of other rooms' hands and are recognised by their content.
    known = {site.filter_name for site in identifier.sitelist.values()}

    assert {"PokerStars", "Winamax", "iPoker", "GGPoker", "Absolute"} <= known
    assert "PokerTracker" not in known


def parser_for(identifier: Any, path: Path) -> str | None:
    identifier.clear_filelist()
    identifier.processFile(str(path))
    found = identifier.get_fobj(str(path))
    site = getattr(found, "site", None)
    return getattr(site, "filter_name", None)


@pytest.mark.parametrize("room", sorted(EXPECTED_PARSER))
def test_every_file_of_a_room_goes_to_that_room_s_converter(identifier, room) -> None:
    files = hand_histories(room)
    assert files, f"no hand history left to identify under {room}"

    identified = {parser_for(identifier, path) for path in files}

    assert identified == {EXPECTED_PARSER[room]}


def test_a_room_with_no_converter_identifies_as_nothing(identifier) -> None:
    files = hand_histories(WITHOUT_A_PARSER)
    assert files

    assert {parser_for(identifier, path) for path in files} == {None}


def test_an_empty_file_is_not_handed_to_any_converter(identifier, tmp_path) -> None:
    # The corpus holds two of these; a converter given one produces nothing.
    empty = tmp_path / "empty.txt"
    empty.write_bytes(b"")

    assert parser_for(identifier, empty) is None


@pytest.mark.parametrize("suffix", [".gt", ".hands", ".hp"])
def test_a_comparator_sidecar_is_not_taken_for_a_hand_history(identifier, tmp_path, suffix) -> None:
    sidecar = tmp_path / f"sample.txt{suffix}"
    sidecar.write_text("{'siteHandNo': '1'}", encoding="utf-8")

    assert parser_for(identifier, sidecar) is None


def test_a_file_of_no_known_room_identifies_as_nothing(identifier, tmp_path) -> None:
    stranger = tmp_path / "stranger.txt"
    stranger.write_text("this is not a hand history from anywhere\n", encoding="utf-8")

    assert parser_for(identifier, stranger) is None


# --------------------------------------------------------------------------
# Reading a file before deciding
# --------------------------------------------------------------------------


def test_a_utf16_export_is_read_rather_than_refused(identifier) -> None:
    # Half the Full Tilt corpus is UTF-16; a reader that gave up here would
    # leave those files unidentified.
    utf16 = next(path for path in hand_histories("FTP") if path.read_bytes()[:2] in (b"\xff\xfe", b"\xfe\xff"))

    text, codec = identifier.read_file(str(utf16))

    assert text
    assert codec


def test_a_plain_export_is_read(identifier) -> None:
    plain = hand_histories("Stars")[0]

    text, codec = identifier.read_file(str(plain))

    assert "PokerStars" in text
    assert codec


def test_a_file_that_is_not_there_is_reported_rather_than_raised(identifier, tmp_path) -> None:
    result = identifier.read_file(str(tmp_path / "absent.txt"))

    assert result is None or result[0] in (None, "")


# --------------------------------------------------------------------------
# Scanning a directory
# --------------------------------------------------------------------------


def test_scanning_a_directory_identifies_what_is_in_it(identifier, tmp_path) -> None:
    import shutil

    shutil.copy(hand_histories("Stars")[0], tmp_path)
    shutil.copy(hand_histories("Winamax")[0], tmp_path)

    identifier.clear_filelist()
    identifier.scan(str(tmp_path))

    parsers = {found.site.filter_name for found in identifier.get_filelist().values() if found.site}
    assert parsers == {"PokerStars", "Winamax"}


def test_the_files_of_one_site_can_be_asked_for(identifier, tmp_path) -> None:
    import shutil

    shutil.copy(hand_histories("Winamax")[0], tmp_path)
    identifier.clear_filelist()
    identifier.scan(str(tmp_path))
    (found,) = identifier.get_filelist().values()

    assert len(identifier.getFilesForSite(found.site.name, "hh")) == 1


def test_asking_for_an_unknown_site_yields_nothing(identifier, tmp_path) -> None:
    identifier.clear_filelist()
    identifier.scan(str(tmp_path))

    assert identifier.getFilesForSite("A Site That Does Not Exist", "hh") == []


def test_clearing_the_list_forgets_what_was_scanned(identifier, tmp_path) -> None:
    import shutil

    shutil.copy(hand_histories("Stars")[0], tmp_path)
    identifier.scan(str(tmp_path))

    identifier.clear_filelist()

    assert identifier.get_filelist() == {}
