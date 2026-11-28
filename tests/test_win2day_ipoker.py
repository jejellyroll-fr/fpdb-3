"""win2day on the iPoker network, and Sökö refused rather than misread (#891).

win2day (Austria) opened its poker room in 2008 on Boss Media, then moved to
Playtech's iPoker network (2015). The two eras write different files:

- Boss Media era: ``<HISTORY ...>`` files, read by ``BossToFpdb`` and filed
  under "Boss" (site 4), as the ``Win2day -> Boss`` alias has always said.
- iPoker era: the network's XML, read by ``iPokerToFpdb`` and filed under the
  room "Win2day Poker" (site 151).

Each file goes to its parser by its format, never by the room name, so a Boss
archive kept in a win2day folder stays Boss, and win2day's iPoker XML never
reaches the Boss parser.

Sökö (Finnish five-card stud) ranks a four-card flush and a four-card straight
between two pair and one pair. fpdb has no evaluator for that order, so a Sökö
hand is refused with an error, never imported as five-card stud nor read with
no game at all, as it was before.

PROVISIONAL: no authentic win2day iPoker export is public yet, nor the client's
folder names. These tests run iPoker's own fixtures from a folder naming
win2day; the 2005 Sökö excerpts are historical B2B text, not win2day hands.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import defusedxml.minidom
import pytest

from fpdb_3_legacy import hud_room_policy as policy
from fpdb_3_legacy.BossToFpdb import Boss
from fpdb_3_legacy.config_migrations import reference_errors, upgrade_document
from fpdb_3_legacy.Configuration import CONFIG_VERSION, Config
from fpdb_3_legacy.database_migrations import SITES_ADDED_LATER
from fpdb_3_legacy.EntractionToFpdb import Entraction
from fpdb_3_legacy.HandHistoryConverter import FpdbParseError
from fpdb_3_legacy.iPoker.base import iPoker
from fpdb_3_legacy.iPoker.dispatcher import (
    DEFAULT_DISPATCHER,
    IPOKER_SKINS,
    detect_skin,
    get_parser_class_for_path,
    resolve_site_id,
)
from fpdb_3_legacy.iPoker.gametype_text import read_gametype, soko_gametype
from fpdb_3_legacy.iPoker.skins import Win2dayIPoker
from fpdb_3_legacy.Options import site_alias

ROOT = Path(__file__).resolve().parents[1]
SITE = "Win2day Poker"
SITE_ID = 151
IPOKER_HAND = (
    ROOT / "regression-test-files/cash/iPoker/Flop/NLHE-6max-EUR-0.01-0.02-202607.tablesize.in.session.header.xml"
)
STUD_HAND = ROOT / "regression-test-files/cash/iPoker/Stud/5-StudL-USD-0.05-0.10-201111.Sample.with.showdown.xml"
BOSS_HAND = ROOT / "regression-test-files/cash/Boss/Flop/NLHE-GBP-0.05-0.10-Date-unknown.Sample.txt"
SOKO_DIR = ROOT / "regression-test-files/unsupported-sites/soko"
SOKO_COMPLETE = SOKO_DIR / "soko_2005_001_complete_anonymized.txt"
SOKO_HEADERLESS = SOKO_DIR / "soko_2005_002_header_missing_anonymized.txt"
WINDOWS_PATH = r"C:\Users\al\AppData\Local\win2day Poker\data\hero\History\Data\Tables\1.xml"
STUD_GAMETYPE = "<gametype>5 Card Stud L $0.05/$0.10</gametype>"


def converter(path: str, sitename: str = SITE) -> iPoker:
    """The iPoker converter the importer builds for ``path``, watched by ``sitename``."""
    config = MagicMock()
    config.supported_sites = {sitename: SimpleNamespace(network="iPoker")}
    return get_parser_class_for_path(path)(
        config,
        in_path=path,
        index=0,
        autostart=False,
        starsArchive=False,
        ftpArchive=False,
        sitename=sitename,
    )


def soko_file(tmp_path: Path, gametype: str = "Sökö PL €0.25/€0.50") -> Path:
    """An iPoker session of Sökö, built from the five-card stud fixture (no native file is public)."""
    text = STUD_HAND.read_text(encoding="utf-8")
    assert STUD_GAMETYPE in text
    target = tmp_path / "win2day Poker" / "data" / "Hero" / "History" / "Data" / "Tables" / "1.xml"
    target.parent.mkdir(parents=True)
    target.write_text(text.replace(STUD_GAMETYPE, f"<gametype>{gametype}</gametype>"), encoding="utf-8")
    return target


# --------------------------------------------------------------------------
# The iPoker room
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        WINDOWS_PATH,
        r"C:\Program Files\win2day\Poker\data\hero\History\Data\Tables\1.xml",
        "/Users/x/Library/Application Support/Win2day Poker/data/hero/History/Data/Tables/1.xml",
        "/home/x/.wine/drive_c/users/x/AppData/Local/WIN2DAY/data/hero/History/Data/Tables/1.xml",
    ],
)
def test_a_win2day_path_is_filed_under_the_room(path: str) -> None:
    assert detect_skin(path) == SITE
    assert get_parser_class_for_path(path) is Win2dayIPoker


def test_no_other_skin_claims_a_win2day_path() -> None:
    owners = [skin.site_name for skin in IPOKER_SKINS if skin.matches(WINDOWS_PATH.lower())]
    assert owners == [SITE]


def test_the_room_is_its_own_site() -> None:
    skin = DEFAULT_DISPATCHER.get_by_site_name(SITE)

    assert skin.default_site_id == SITE_ID
    assert Win2dayIPoker.sitename == SITE
    assert Win2dayIPoker.site_id == SITE_ID
    assert resolve_site_id(SimpleNamespace(), SITE) == SITE_ID
    assert [s.site_name for s in IPOKER_SKINS if s.default_site_id == SITE_ID] == [SITE]
    assert (SITE_ID, SITE, "IP") in SITES_ADDED_LATER
    assert [row for row in SITES_ADDED_LATER if row[0] == SITE_ID] == [(SITE_ID, SITE, "IP")]


def test_the_site_id_is_no_data_sources():
    # PHH files and SwC's HTTP capture register their own Sites rows when they
    # first import: sharing an id would file one source's hands under the other.
    from fpdb_3_legacy.http_capture_db_import import SWC_SITE_ID
    from fpdb_3_legacy.phh_import import PHH_SITE_ID

    assert SITE_ID not in {PHH_SITE_ID, SWC_SITE_ID}


def test_a_converter_of_a_win2day_file_files_it_under_the_room() -> None:
    hhc = converter(WINDOWS_PATH, "iPoker")
    hhc._apply_skin_from_input_path()  # what determineGameType() does for every hand

    assert (hhc.sitename, hhc.site_id) == (SITE, SITE_ID)


def test_the_room_follows_the_ipoker_hud_policy() -> None:
    assert policy.network_of(SITE) == "ipoker"
    assert policy.policy_for(SITE) == policy.policy_for("iPoker")


# --------------------------------------------------------------------------
# The Boss Media era keeps its own route
# --------------------------------------------------------------------------


def test_the_win2day_alias_still_names_the_boss_parser() -> None:
    assert site_alias("Win2day") == "Boss"
    assert Boss.sitename == "Boss"


def test_neither_parser_identifies_the_other_eras_files() -> None:
    boss_text = BOSS_HAND.read_text(encoding="utf-8")
    ipoker_text = IPOKER_HAND.read_text(encoding="utf-8")

    assert Boss.re_Identify.search(boss_text)
    assert not Boss.re_Identify.search(ipoker_text)
    assert iPoker.re_identify.search(ipoker_text)
    assert not iPoker.re_identify.search(boss_text)


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "template", ["HUD_config.xml", "HUD_config.xml.example", "fpdb_3_legacy/HUD_config.xml.example"]
)
def test_the_shipped_configuration_knows_the_room(tmp_path, template: str) -> None:
    shutil.copyfile(ROOT / template, tmp_path / "HUD_config.xml")
    config = Config(file=str(tmp_path / "HUD_config.xml"))

    assert config.get_site_id(SITE) == SITE_ID
    site = config.supported_sites[SITE]
    assert not site.enabled
    assert site.HH_path == site.TS_path == ""  # the client's folders are not confirmed
    assert site.screen_name == ""
    assert site.network == "iPoker"
    assert config.get_site_parameters(SITE)["converter"] == "iPokerToFpdb"
    assert config.get_site_parameters(SITE)["summaryImporter"] == "iPokerSummary"


def test_the_boss_room_keeps_its_own_converter(tmp_path) -> None:
    # win2day's Boss Media era files keep their room and parser.
    shutil.copyfile(ROOT / "HUD_config.xml", tmp_path / "HUD_config.xml")
    config = Config(file=str(tmp_path / "HUD_config.xml"))

    assert config.get_site_id("Boss") == 4
    assert config.get_site_parameters("Boss")["converter"] == "BossToFpdb"


def parse(text: str):
    return defusedxml.minidom.parseString(text)


def test_v103_adds_the_room() -> None:
    template = defusedxml.minidom.parse(str(ROOT / "HUD_config.xml.example"))
    old = parse("""<FreePokerToolsConfig><general version="102"/>
      <supported_sites>
      <site site_name="Boss" HH_path="/old/win2day" network="Boss"><layout_set ls="custom"/></site>
      </supported_sites>
      <layout_sets><ls name="custom"/></layout_sets>
      <hhcs><hhc site="Boss" converter="BossToFpdb"/></hhcs>
      </FreePokerToolsConfig>""")

    updated = upgrade_document(old, template, CONFIG_VERSION)

    sites = {node.getAttribute("site_name"): node for node in updated.getElementsByTagName("site")}
    assert set(sites) == {"Boss", SITE, "ChampionPoker"}  # v104 (#926)
    new = sites[SITE]
    assert new.getAttribute("enabled") == "False"
    assert new.getAttribute("network") == "iPoker"
    assert new.getAttribute("HH_path") == new.getAttribute("TS_path") == ""
    assert {n.getAttribute("ls") for n in new.getElementsByTagName("layout_set")} == {"ipoker_default"}
    assert sites["Boss"].getAttribute("HH_path") == "/old/win2day"
    hhcs = {n.getAttribute("site"): n.getAttribute("converter") for n in updated.getElementsByTagName("hhc")}
    assert hhcs == {"Boss": "BossToFpdb", SITE: "iPokerToFpdb", "ChampionPoker": "iPokerToFpdb"}
    assert "ipoker_default" in {node.getAttribute("name") for node in updated.getElementsByTagName("ls")}
    assert not reference_errors(updated)
    assert upgrade_document(updated, template, CONFIG_VERSION).toxml() == updated.toxml()


def test_v103_keeps_an_entry_the_user_wrote() -> None:
    template = defusedxml.minidom.parse(str(ROOT / "HUD_config.xml.example"))
    old = parse("""<FreePokerToolsConfig><general version="102"/>
      <supported_sites><site site_name="Win2day Poker" enabled="True" HH_path="/my/win2day" network="iPoker">
      <layout_set ls="custom"/></site></supported_sites>
      <layout_sets><ls name="custom"/></layout_sets>
      <hhcs/>
      </FreePokerToolsConfig>""")

    updated = upgrade_document(old, template, CONFIG_VERSION)

    (site,) = [n for n in updated.getElementsByTagName("site") if n.getAttribute("site_name") == SITE]
    assert site.getAttribute("HH_path") == "/my/win2day"
    assert site.getAttribute("enabled") == "True"


# --------------------------------------------------------------------------
# Database and import
# --------------------------------------------------------------------------


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
            "db-databaseName": str(tmp_path / "win2day.sqlite3"),
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


def _hand_sites(importer) -> list[str]:
    cursor = importer.database.get_cursor()
    cursor.execute(
        "SELECT DISTINCT s.name FROM Hands h JOIN Gametypes g ON h.gametypeId = g.id JOIN Sites s ON g.siteId = s.id"
    )
    return [row[0] for row in cursor.fetchall()]


def _import(importer, path: Path) -> tuple[int, int]:
    importer.addImportFile(str(path), "auto")
    stored, _dups, _partial, _skipped, errors, _time = importer.runImport()
    return stored, errors


def _copy(source: Path, folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    return Path(shutil.copy(source, folder / source.name))


def test_a_new_database_has_the_sites_row(importer) -> None:
    cursor = importer.database.get_cursor()
    cursor.execute("SELECT name, code FROM Sites WHERE id IN (4, 151) ORDER BY id")
    assert cursor.fetchall() == [("Boss", "BM"), (SITE, "IP")]


def test_an_older_database_gains_the_sites_row(importer) -> None:
    database = importer.database
    cursor = database.get_cursor()
    cursor.execute("DELETE FROM Sites WHERE id = 151")
    database.commit()

    database.ensure_sites_rows()

    cursor.execute("SELECT name, code FROM Sites WHERE id = 151")
    assert cursor.fetchall() == [(SITE, "IP")]


def test_ipoker_hands_in_a_win2day_folder_are_filed_under_the_room(importer, tmp_path) -> None:
    hand = _copy(IPOKER_HAND, tmp_path / "win2day Poker" / "data" / "Hero" / "History" / "Data" / "Tables")

    stored, errors = _import(importer, hand)

    assert (stored > 0, errors) == (True, 0)
    assert _hand_sites(importer) == [SITE]


def test_a_boss_archive_in_a_win2day_folder_stays_boss(importer, tmp_path) -> None:
    # A Boss Media era file is read by its format, wherever it is kept: it
    # never reaches the iPoker parser, nor is it filed under the iPoker room.
    hand = _copy(BOSS_HAND, tmp_path / "win2day Poker" / "HandHistory")

    stored, errors = _import(importer, hand)

    assert (stored > 0, errors) == (True, 0)
    assert _hand_sites(importer) == ["Boss"]


def test_a_soko_session_is_refused_not_stored(importer, tmp_path) -> None:
    stored, errors = _import(importer, soko_file(tmp_path))

    assert stored == 0
    assert errors > 0
    assert _hand_sites(importer) == []


# --------------------------------------------------------------------------
# Sökö
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "Sökö PL €0.25/€0.50",
        "Pot Limit Sökö €0.25/€0.50",
        "Soko PL €0.25/€0.50",
        "SOKO PL",
        "Sökö Pot limit 0,25€/0,50€",
        "Soekoe PL €0.25/€0.50",
        "SÃ¶kÃ¶ PL €0.25/€0.50",  # UTF-8 read as cp1252
    ],
)
def test_soko_is_recognized_in_any_spelling(value: str) -> None:
    assert soko_gametype(f"<session><general><gametype>{value}</gametype></general></session>") == value
    # The shared reader knows no such game, so nothing reads it as five-card stud.
    assert read_gametype(value) is None


@pytest.mark.parametrize(
    "text",
    [
        "<gametype>5 Card Stud L $0.05/$0.10</gametype>",
        "<gametype>Holdem NL €0.01/€0.02</gametype>",
        "<tablename>Sokolov, 123</tablename><gametype>Omaha PL €1/€2</gametype>",
        "<nickname>Soko</nickname><gametype>Holdem NL €0.01/€0.02</gametype>",
    ],
)
def test_other_games_and_names_are_not_soko(text: str) -> None:
    assert soko_gametype(text) is None


def test_five_card_stud_is_still_five_card_stud() -> None:
    assert read_gametype("5 Card Stud L $0.05/$0.10")["category"] == "5_studhi"


def test_the_parser_refuses_a_soko_hand(tmp_path) -> None:
    path = soko_file(tmp_path)
    hhc = converter(str(path))
    hhc.whole_file = path.read_text(encoding="utf-8")

    with pytest.raises(FpdbParseError, match="Sökö PL"):
        hhc.determineGameType(hhc.whole_file)


def test_a_later_hand_of_a_soko_session_is_refused_too(tmp_path) -> None:
    # Every hand but the first is a bare <game> block: its game is the session's.
    path = soko_file(tmp_path)
    hhc = converter(str(path))
    hhc.whole_file = path.read_text(encoding="utf-8")
    bare_game = hhc.whole_file[hhc.whole_file.index("<game gamecode=") :]

    with pytest.raises(FpdbParseError, match="#891"):
        hhc.determineGameType(bare_game)


def test_the_parser_still_reads_five_card_stud(tmp_path) -> None:
    path = soko_file(tmp_path, gametype="5 Card Stud L $0.05/$0.10")
    hhc = converter(str(path))
    hhc.whole_file = path.read_text(encoding="utf-8")

    info = hhc.determineGameType(hhc.whole_file)

    assert (info["base"], info["category"]) == ("stud", "5_studhi")


def test_the_2005_soko_excerpt_is_refused_by_the_entraction_parser() -> None:
    # Its "Game # ... - " header is the B2B text family Entraction reads: the
    # hand is refused as an unsupported game, not read as hold'em or Omaha.
    text = SOKO_COMPLETE.read_text(encoding="utf-8")
    assert Entraction.re_Identify.search(text)
    hhc = Entraction.__new__(Entraction)

    with pytest.raises(FpdbParseError, match="Unsupported game 'Soko Pot Limit"):
        hhc.determineGameType(text)


def test_the_headerless_2005_excerpt_is_claimed_by_no_parser_known_for_it() -> None:
    # Posted without its header: nothing names its room or game, and it must
    # not be given one to make it parse.
    text = SOKO_HEADERLESS.read_text(encoding="utf-8")

    assert not Entraction.re_Identify.search(text)
    assert not Boss.re_Identify.search(text)
    assert not iPoker.re_identify.search(text)
