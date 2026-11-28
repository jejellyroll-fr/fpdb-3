"""ChampionPoker on the iPoker network: a room of its own (#926).

ChampionPoker writes the network's XML hand histories, read by the shared
iPoker parser; only the room its hands are filed under differs. The fixture is
a real cash session (PLO €0.02/€0.04, client 26.7.1.32), anonymized with
tools/anonymize_hh.py. Five of its eight hands were played while the hero was
not dealt in, so the client lists their players as "Player <seat>".

PROVISIONAL: the client's folder names are not confirmed. A path is claimed by
the brand's name, in one word or two.
"""

from __future__ import annotations

import shutil
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import defusedxml.minidom
import pytest

from fpdb_3_legacy import hud_room_policy as policy
from fpdb_3_legacy.config_migrations import reference_errors, upgrade_document
from fpdb_3_legacy.Configuration import CONFIG_VERSION, Config
from fpdb_3_legacy.database_migrations import SITES_ADDED_LATER
from fpdb_3_legacy.iPoker.base import iPoker
from fpdb_3_legacy.iPoker.dispatcher import (
    DEFAULT_DISPATCHER,
    IPOKER_SKINS,
    detect_skin,
    get_parser_class_for_path,
    resolve_site_id,
)
from fpdb_3_legacy.iPoker.skins import ChampionPokerIPoker

ROOT = Path(__file__).resolve().parents[1]
SITE = "ChampionPoker"
SITE_ID = 152
SESSION = ROOT / "regression-test-files/cash/iPoker/Flop/PLO-EUR-0.02-0.04-202611.ChampionPoker.anonymous.seats.xml"
WINDOWS_PATH = r"C:\Users\al\AppData\Local\ChampionPoker\data\hero\History\Data\Tables\1.xml"


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


# --------------------------------------------------------------------------
# The iPoker room
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        WINDOWS_PATH,
        r"C:\Program Files\Champion Poker\data\hero\History\Data\Tables\1.xml",
        "/Users/x/Library/Application Support/championpoker/data/hero/History/Data/Tables/1.xml",
        "/home/x/.wine/drive_c/users/x/AppData/Local/CHAMPION-POKER/data/hero/History/Data/Tables/1.xml",
    ],
)
def test_a_championpoker_path_is_filed_under_the_room(path: str) -> None:
    assert detect_skin(path) == SITE
    assert get_parser_class_for_path(path) is ChampionPokerIPoker


def test_no_other_skin_claims_a_championpoker_path() -> None:
    owners = [skin.site_name for skin in IPOKER_SKINS if skin.matches(WINDOWS_PATH.lower())]
    assert owners == [SITE]


def test_a_bare_champion_folder_is_not_claimed() -> None:
    # "champion" alone is a common word (player names, tournament names).
    assert detect_skin(r"C:\Users\champion\AppData\Local\iPoker\History\1.xml") == "iPoker"


def test_the_room_is_its_own_site() -> None:
    skin = DEFAULT_DISPATCHER.get_by_site_name(SITE)

    assert skin.default_site_id == SITE_ID
    assert ChampionPokerIPoker.sitename == SITE
    assert ChampionPokerIPoker.site_id == SITE_ID
    assert resolve_site_id(SimpleNamespace(), SITE) == SITE_ID
    assert [s.site_name for s in IPOKER_SKINS if s.default_site_id == SITE_ID] == [SITE]
    assert [row for row in SITES_ADDED_LATER if row[0] == SITE_ID] == [(SITE_ID, SITE, "IP")]


def test_the_site_id_is_no_data_sources() -> None:
    from fpdb_3_legacy.http_capture_db_import import SWC_SITE_ID
    from fpdb_3_legacy.phh_import import PHH_SITE_ID

    assert SITE_ID not in {PHH_SITE_ID, SWC_SITE_ID}


def test_a_converter_of_a_championpoker_file_files_it_under_the_room() -> None:
    hhc = converter(WINDOWS_PATH, "iPoker")
    hhc._apply_skin_from_input_path()  # what determineGameType() does for every hand

    assert (hhc.sitename, hhc.site_id) == (SITE, SITE_ID)


def test_the_room_follows_the_ipoker_hud_policy() -> None:
    assert policy.network_of(SITE) == "ipoker"
    assert policy.policy_for(SITE) == policy.policy_for("iPoker")


# --------------------------------------------------------------------------
# The real session
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def session_hands() -> list:
    hhc = converter(str(SESSION), "iPoker")
    hhc.start()
    assert (hhc.numHands, hhc.numErrors, hhc.numPartial) == (8, 0, 0)
    return hhc.getProcessedHands()


def test_the_session_is_pot_limit_omaha_in_euros(session_hands) -> None:
    for hand in session_hands:
        gametype = hand.gametype
        assert (gametype["category"], gametype["limitType"], gametype["currency"]) == ("omahahi", "pl", "EUR")
        assert (gametype["sb"], gametype["bb"]) == ("0.02", "0.04")
        assert hand.maxseats == 6


def test_every_pot_balances(session_hands) -> None:
    for hand in session_hands:
        assert hand.totalcollected + hand.rake == hand.totalpot


def test_the_hero_is_found_only_where_dealt_in(session_hands) -> None:
    assert [hand.hero for hand in session_hands] == ["", "", "", "", "", "Hero", "Hero", "Hero"]


def test_the_hero_all_in_returns_the_uncalled_raise(session_hands) -> None:
    hand = session_hands[5]

    assert (hand.totalpot, hand.rake, hand.totalcollected) == (Decimal("4.28"), Decimal("0.28"), Decimal("4.00"))
    assert {name: won for name, won in hand.collectees.items() if won} == {"dave": Decimal("4.00")}


def test_anonymous_seats_take_the_names_learned_from_the_session(session_hands) -> None:
    # The client writes "Player <seat>" where the hero is not dealt in; the
    # session's named hands say who sat there.
    names = {name for hand in session_hands for _seat, name, *_ in hand.players}

    assert not any(name.startswith("Player ") for name in names)
    assert names == {"alice", "bob", "carol", "dave", "erin", "Hero"}


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


def parse(text: str):
    return defusedxml.minidom.parseString(text)


def test_v104_adds_the_room() -> None:
    template = defusedxml.minidom.parse(str(ROOT / "HUD_config.xml.example"))
    old = parse("""<FreePokerToolsConfig><general version="103"/>
      <supported_sites>
      <site site_name="iPoker" HH_path="/old/ipoker" network="iPoker"><layout_set ls="custom"/></site>
      </supported_sites>
      <layout_sets><ls name="custom"/></layout_sets>
      <hhcs><hhc site="iPoker" converter="iPokerToFpdb"/></hhcs>
      </FreePokerToolsConfig>""")

    updated = upgrade_document(old, template, CONFIG_VERSION)

    sites = {node.getAttribute("site_name"): node for node in updated.getElementsByTagName("site")}
    assert set(sites) == {"iPoker", SITE}
    new = sites[SITE]
    assert new.getAttribute("enabled") == "False"
    assert new.getAttribute("network") == "iPoker"
    assert new.getAttribute("HH_path") == new.getAttribute("TS_path") == ""
    assert {n.getAttribute("ls") for n in new.getElementsByTagName("layout_set")} == {"ipoker_default"}
    assert sites["iPoker"].getAttribute("HH_path") == "/old/ipoker"
    hhcs = {n.getAttribute("site"): n.getAttribute("converter") for n in updated.getElementsByTagName("hhc")}
    assert hhcs == {"iPoker": "iPokerToFpdb", SITE: "iPokerToFpdb"}
    assert "ipoker_default" in {node.getAttribute("name") for node in updated.getElementsByTagName("ls")}
    assert not reference_errors(updated)
    assert upgrade_document(updated, template, CONFIG_VERSION).toxml() == updated.toxml()


def test_v104_keeps_an_entry_the_user_wrote() -> None:
    template = defusedxml.minidom.parse(str(ROOT / "HUD_config.xml.example"))
    old = parse("""<FreePokerToolsConfig><general version="103"/>
      <supported_sites><site site_name="ChampionPoker" enabled="True" HH_path="/my/champion" network="iPoker">
      <layout_set ls="custom"/></site></supported_sites>
      <layout_sets><ls name="custom"/></layout_sets>
      <hhcs/>
      </FreePokerToolsConfig>""")

    updated = upgrade_document(old, template, CONFIG_VERSION)

    (site,) = [n for n in updated.getElementsByTagName("site") if n.getAttribute("site_name") == SITE]
    assert site.getAttribute("HH_path") == "/my/champion"
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
            "db-databaseName": str(tmp_path / "championpoker.sqlite3"),
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


def test_a_new_database_has_the_sites_row(importer) -> None:
    cursor = importer.database.get_cursor()
    cursor.execute("SELECT name, code FROM Sites WHERE id = 152")
    assert cursor.fetchall() == [(SITE, "IP")]


def test_an_older_database_gains_the_sites_row(importer) -> None:
    database = importer.database
    cursor = database.get_cursor()
    cursor.execute("DELETE FROM Sites WHERE id = 152")
    database.commit()

    database.ensure_sites_rows()

    cursor.execute("SELECT name, code FROM Sites WHERE id = 152")
    assert cursor.fetchall() == [(SITE, "IP")]


def test_the_session_in_a_championpoker_folder_is_filed_under_the_room(importer, tmp_path) -> None:
    folder = tmp_path / "ChampionPoker" / "data" / "Hero" / "History" / "Data" / "Tables"
    folder.mkdir(parents=True)
    hand = Path(shutil.copy(SESSION, folder / "8757181114.xml"))

    importer.addImportFile(str(hand), "auto")
    stored, _dups, _partial, _skipped, errors, _time = importer.runImport()

    assert (stored, errors) == (8, 0)
    assert _hand_sites(importer) == [SITE]
