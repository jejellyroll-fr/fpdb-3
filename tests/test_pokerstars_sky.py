"""PokerStars on Sky: Sky Poker's client on PokerStars software (#887).

Sky Poker moved from the iPoker network to the PokerStars network on 19
November 2026. Its new client is filed under a room of its own, PokerStars on
Sky (147), apart from the iPoker room Sky Poker (72), which keeps the hands the
old client wrote.

Nothing in a PokerStars history is known to name the skin, and the new client's
folders are not documented, so fpdb guesses none. A hand is filed under the new
room only on explicit provenance: the folder the user configured for the room,
or a hero mapped to it in ``pokerstars_skin_mapping.conf``. Never on GBP stakes
or a plain PokerStars header, and never for a hand dated before the client
opened.

PROVISIONAL: no real export from the new client is public yet. These tests run
PokerStars' own fixtures, re-dated, from a configured folder. They check how
hands are filed, not that the parser reads every line the new client writes.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.iPoker.dispatcher import IPokerSkinDispatcher
from fpdb_3_legacy.iPoker.skins.sky import SkyIPoker
from fpdb_3_legacy.PokerStarsToFpdb import (
    POKERSTARS_CONFIGURED_PATH_SKINS,
    POKERSTARS_SKIN_FIRST_DAYS,
    POKERSTARS_SKIN_IDS,
    SITE_POKERSTARS_SKY,
    PokerStars,
)

ROOT = Path(__file__).resolve().parents[1]
CASH_HAND = ROOT / "regression-test-files/cash/Stars/Flop/2025-NL-uncalled-bet.txt"
SUMMARY = ROOT / "regression-test-files/summaries/Stars/6+Holdem-3max-STT-USD-1.00-201907.txt"
SKIN = "PokerStars on Sky"
PADDY_POWER = "PokerStars on Paddy Power"


def _gbp_hand(date: str = "2026/11/20", et_date: str | None = None, hero: str = "Hero") -> str:
    et_date = et_date or date
    return (
        f"PokerStars Hand #260000000001:  Hold'em No Limit (£0.05/£0.10 GBP) - {date} 20:15:00 GMT"
        f" [{et_date} 15:15:00 ET]\n"
        "Table 'Example II' 6-max Seat #1 is the button\n"
        "Seat 1: Hero (£10 in chips)\n"
        "*** HOLE CARDS ***\n"
        f"Dealt to {hero} [As Kc]\n"
    )


def _site(hh_path: str = "", ts_path: str = "") -> SimpleNamespace:
    # The configuration's own attribute names, spelled as Configuration spells them.
    return SimpleNamespace(**{"HH_path": hh_path, "TS_path": ts_path})


class _Config:
    def __init__(self, sites: dict[str, SimpleNamespace]) -> None:
        self.supported_sites = sites


def _parser(config: object = None, mappings: dict[str, str] | None = None) -> PokerStars:
    parser = PokerStars.__new__(PokerStars)
    parser.config = config
    parser._hero_mappings = mappings or {}
    return parser


def _configured(folder: Path, **others: Path) -> _Config:
    sites = {SKIN: _site(str(folder / "HandHistory"), str(folder / "TournSummary"))}
    if "paddy_power" in others:
        pp = others["paddy_power"]
        sites[PADDY_POWER] = _site(str(pp / "HandHistory"), str(pp / "TournSummary"))
    return _Config(sites)


# ---------------------------------------------------------------------------
# The room's identity
# ---------------------------------------------------------------------------


def test_the_room_has_its_own_site_id() -> None:
    assert POKERSTARS_SKIN_IDS[SKIN] == SITE_POKERSTARS_SKY == 147
    # Distinct from every other PokerStars room and from the iPoker Sky Poker room.
    assert list(POKERSTARS_SKIN_IDS.values()).count(147) == 1
    assert SkyIPoker.site_id == 72
    assert 72 not in POKERSTARS_SKIN_IDS.values()


def test_the_room_opened_on_19_november_2026() -> None:
    assert POKERSTARS_SKIN_FIRST_DAYS[SKIN].isoformat() == "2026-11-19"


def test_the_room_is_filed_by_its_configured_folder() -> None:
    assert SKIN in POKERSTARS_CONFIGURED_PATH_SKINS


def test_the_room_policy_is_pokerstars() -> None:
    from fpdb_3_legacy import hud_room_policy

    assert hud_room_policy.network_of(SKIN) == "pokerstars"
    assert hud_room_policy.capabilities_at(SKIN) == hud_room_policy.capabilities_at("PokerStars.FR")
    assert hud_room_policy.why_not("dynamic_hud", SKIN)
    assert not hud_room_policy.capabilities_at(SKIN).positional_hud
    # The iPoker room keeps the iPoker policy.
    assert hud_room_policy.network_of("Sky Poker") == "ipoker"


# ---------------------------------------------------------------------------
# What files a hand under the room, and what does not
# ---------------------------------------------------------------------------


def test_a_hand_in_the_configured_folder_is_filed_under_the_room(tmp_path: Path) -> None:
    parser = _parser(_configured(tmp_path / "Sky"))
    path = tmp_path / "Sky" / "HandHistory" / "Hero" / "HH20261120.txt"

    assert parser.detectPokerStarsSkin(_gbp_hand(), str(path)) == (SKIN, 147)


def test_a_summary_in_the_configured_folder_is_filed_under_the_room(tmp_path: Path) -> None:
    parser = _parser(_configured(tmp_path / "Sky"))
    summary = "PokerStars Tournament #4000000001, No Limit Hold'em\nTournament started 2026/11/20 20:00:00 GMT\n"

    assert parser.detectPokerStarsSkin(summary, str(tmp_path / "Sky" / "TournSummary" / "TS.txt")) == (SKIN, 147)


@pytest.mark.parametrize(
    "relative",
    [
        # A sibling folder sharing the configured folder's name as a prefix.
        "Sky/HandHistory2/HH.txt",
        "Sky/TournSummaryOld/TS.txt",
        # A copy elsewhere: the copy keeps no provenance unless its hero is mapped.
        "Downloads/HH20261120.txt",
    ],
)
def test_a_file_outside_the_configured_folders_is_not(tmp_path: Path, relative: str) -> None:
    parser = _parser(_configured(tmp_path / "Sky"))

    assert parser.detectPokerStarsSkin(_gbp_hand(), str(tmp_path / relative)) == ("PokerStars.COM", 32)


def test_an_unconfigured_room_files_nothing(tmp_path: Path) -> None:
    # The shipped room has no folder: nothing is filed under it until the user sets one.
    parser = _parser(_Config({SKIN: _site()}))

    assert parser.detectPokerStarsSkin(_gbp_hand(), str(tmp_path / "HH.txt")) == ("PokerStars.COM", 32)
    assert _parser(None).detectPokerStarsSkin(_gbp_hand(), str(tmp_path / "HH.txt")) == ("PokerStars.COM", 32)


@pytest.mark.parametrize(
    "path",
    [
        r"C:\Users\alice\AppData\Local\SkyPoker\HandHistory\alice\HH20261120.txt",
        r"C:\Users\alice\AppData\Local\Sky Poker\HandHistory\alice\HH20261120.txt",
        r"C:\Program Files\Sky Poker\HandHistory\alice\HH20261120.txt",
        "/home/alice/sky/HH20261120.txt",
    ],
)
def test_no_folder_name_is_guessed(path: str) -> None:
    # The new client's folder is not documented: a folder merely named after
    # Sky is not taken as its provenance.
    assert _parser(None).detectPokerStarsSkin(_gbp_hand(), path) == ("PokerStars.COM", 32)


def test_gbp_stakes_alone_do_not_name_the_room() -> None:
    assert _parser(None).detectPokerStarsSkin(_gbp_hand(), None) == ("PokerStars.COM", 32)


def test_a_hero_mapped_to_the_room_files_it_there() -> None:
    # The opt-in for copied files (e-mailed exports, backups).
    parser = _parser(None, {"hero": SKIN})

    assert parser.detectPokerStarsSkin(_gbp_hand(), None) == (SKIN, 147)
    assert parser.detectPokerStarsSkin(_gbp_hand(), "/home/alice/backup/HH.txt") == (SKIN, 147)


@pytest.mark.parametrize("how", ["folder", "hero"])
def test_a_hand_from_before_the_move_is_never_filed_there(tmp_path: Path, how: str) -> None:
    # A Sky player may have played PokerStars under the same name before the
    # move; those hands are not the new client's.
    config = _configured(tmp_path / "Sky") if how == "folder" else None
    parser = _parser(config, {"hero": SKIN} if how == "hero" else None)
    path = str(tmp_path / "Sky" / "HandHistory" / "HH.txt")

    assert parser.detectPokerStarsSkin(_gbp_hand("2026/11/18"), path) == ("PokerStars.COM", 32)


def test_the_first_day_counts() -> None:
    parser = _parser(None, {"hero": SKIN})

    assert parser.detectPokerStarsSkin(_gbp_hand("2026/11/19"), None) == (SKIN, 147)
    # Already the 19th in local time, still the 18th in ET: the hand is the new client's.
    assert parser.detectPokerStarsSkin(_gbp_hand("2026/11/19", et_date="2026/11/18"), None) == (SKIN, 147)


def test_a_hand_with_no_readable_date_goes_by_its_provenance() -> None:
    parser = _parser(None, {"hero": SKIN})
    undated = "PokerStars Hand #1: Hold'em No Limit (£0.05/£0.10 GBP)\nDealt to Hero [As Kc]\n"

    assert parser.detectPokerStarsSkin(undated, None) == (SKIN, 147)


# ---------------------------------------------------------------------------
# Not conflated with the other UK PokerStars skins
# ---------------------------------------------------------------------------


def test_a_betfair_history_is_betfairs_even_in_the_sky_folder(tmp_path: Path) -> None:
    # Betfair's client names itself in every header: no folder overrides that.
    parser = _parser(_configured(tmp_path / "Sky"))
    betfair = _gbp_hand().replace("PokerStars Hand #", "Betfair Hand #", 1)
    path = tmp_path / "Sky" / "HandHistory" / "HH.txt"

    assert parser.detectPokerStarsSkin(betfair, str(path)) == ("PokerStars on Betfair", 143)


def test_a_betfair_folder_is_not_sky(tmp_path: Path) -> None:
    parser = _parser(_configured(tmp_path / "Sky"))
    path = r"C:\Users\alice\AppData\Local\Betfair.UK\HandHistory\alice\HH20261120.txt"

    assert parser.detectPokerStarsSkin(_gbp_hand(), path) == ("PokerStars on Betfair", 143)


def test_sky_and_paddy_power_folders_each_keep_their_room(tmp_path: Path) -> None:
    parser = _parser(_configured(tmp_path / "Sky", paddy_power=tmp_path / "PP"))

    sky = tmp_path / "Sky" / "HandHistory" / "HH.txt"
    pp = tmp_path / "PP" / "HandHistory" / "HH.txt"
    assert parser.detectPokerStarsSkin(_gbp_hand(), str(sky)) == (SKIN, 147)
    assert parser.detectPokerStarsSkin(_gbp_hand(), str(pp)) == (PADDY_POWER, 146)


def test_the_most_specific_configured_folder_wins(tmp_path: Path) -> None:
    # Paddy Power's folder configured inside Sky's: a hand in it is Paddy Power's.
    parser = _parser(_configured(tmp_path / "Clients", paddy_power=tmp_path / "Clients" / "HandHistory" / "PP"))

    inner = tmp_path / "Clients" / "HandHistory" / "PP" / "HandHistory" / "HH.txt"
    outer = tmp_path / "Clients" / "HandHistory" / "Hero" / "HH.txt"
    assert parser.detectPokerStarsSkin(_gbp_hand(), str(inner)) == (PADDY_POWER, 146)
    assert parser.detectPokerStarsSkin(_gbp_hand(), str(outer)) == (SKIN, 147)


def test_a_hand_between_the_two_moves_stays_generic_in_the_sky_folder(tmp_path: Path) -> None:
    # Dated after Paddy Power's move but before Sky's: not the new Sky client's.
    parser = _parser(_configured(tmp_path / "Sky"))
    path = str(tmp_path / "Sky" / "HandHistory" / "HH.txt")

    assert parser.detectPokerStarsSkin(_gbp_hand("2026/11/01"), path) == ("PokerStars.COM", 32)


# ---------------------------------------------------------------------------
# The iPoker room keeps the old client's hands
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        r"C:\Users\alice\AppData\Local\Sky Poker\data\alice\History\Data\Tables\x.xml",
        "/home/alice/.wine/drive_c/Program Files/SkyPoker/data/alice/History/Data/Tables/x.xml",
    ],
)
def test_old_ipoker_hands_stay_under_site_72(path: str) -> None:
    skin = IPokerSkinDispatcher().detect(path)

    assert skin is not None
    assert (skin.site_name, skin.default_site_id) == ("Sky Poker", 72)


# ---------------------------------------------------------------------------
# End to end: import into SQLite
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
            "db-databaseName": str(tmp_path / "sky.sqlite3"),
            "db-path": "",
        }
    )
    config.get_db_parameters = lambda: params
    site = config.supported_sites[SKIN]
    site.HH_path = str(tmp_path / "Sky" / "HandHistory")
    site.TS_path = str(tmp_path / "Sky" / "TournSummary")
    schema = Database(config)
    schema.recreate_tables()
    schema.close_connection()
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.setCallHud(False)
    yield importer
    importer.close()


def _copy(source: Path, target: Path, old_date: str, new_date: str | None) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    text = source.read_text(encoding="utf-8")
    target.write_text(text.replace(old_date, new_date) if new_date else text, encoding="utf-8")
    return target


def _hand_sites(importer) -> list[str]:
    cursor = importer.database.get_cursor()
    cursor.execute(
        "SELECT DISTINCT s.name FROM Hands h JOIN Gametypes g ON h.gametypeId = g.id JOIN Sites s ON g.siteId = s.id"
    )
    return [row[0] for row in cursor.fetchall()]


def _import(importer, path: Path) -> int:
    importer.addImportFile(str(path), "auto")
    _stored, _dups, _partial, _skipped, errors, _time = importer.runImport()
    return errors


def test_hands_from_the_configured_folder_are_filed_under_the_room(importer, tmp_path) -> None:
    hand = _copy(CASH_HAND, tmp_path / "Sky" / "HandHistory" / "Hero" / CASH_HAND.name, "2025/04/24", "2026/11/20")

    assert _import(importer, hand) == 0
    assert _hand_sites(importer) == [SKIN]


def test_old_hands_in_the_configured_folder_stay_generic(importer, tmp_path) -> None:
    hand = _copy(CASH_HAND, tmp_path / "Sky" / "HandHistory" / "Hero" / CASH_HAND.name, "2025/04/24", None)

    assert _import(importer, hand) == 0
    assert _hand_sites(importer) == ["PokerStars.COM"]


def test_a_copy_outside_the_configured_folder_stays_generic(importer, tmp_path) -> None:
    hand = _copy(CASH_HAND, tmp_path / "copies" / CASH_HAND.name, "2025/04/24", "2026/11/20")

    assert _import(importer, hand) == 0
    assert _hand_sites(importer) == ["PokerStars.COM"]


def test_summaries_from_the_configured_folder_are_filed_under_the_room(importer, tmp_path) -> None:
    summary = _copy(SUMMARY, tmp_path / "Sky" / "TournSummary" / "Hero" / SUMMARY.name, "2019/07/31", "2026/11/20")

    _import(importer, summary)

    cursor = importer.database.get_cursor()
    cursor.execute("SELECT DISTINCT s.name FROM TourneyTypes t JOIN Sites s ON t.siteId = s.id")
    assert [row[0] for row in cursor.fetchall()] == [SKIN]


def test_each_summary_of_an_export_is_filed_by_its_own_date(importer, tmp_path) -> None:
    # An export of several summaries spanning the move: a tournament played
    # before 19 November 2026 is not the new client's.
    old = SUMMARY.read_text(encoding="utf-8")
    new = old.replace("2019/07/31", "2026/11/20").replace("#2663538841", "#4000000001")
    export = tmp_path / "Sky" / "TournSummary" / "Hero" / "export.txt"
    export.parent.mkdir(parents=True)
    export.write_text(new + "\n\n\n" + old, encoding="utf-8")

    _import(importer, export)

    cursor = importer.database.get_cursor()
    cursor.execute(
        "SELECT t.siteTourneyNo, s.name FROM Tourneys t JOIN TourneyTypes tt ON t.tourneyTypeId = tt.id"
        " JOIN Sites s ON tt.siteId = s.id ORDER BY t.siteTourneyNo"
    )
    assert [(str(no), site) for no, site in cursor.fetchall()] == [
        ("2663538841", "PokerStars.COM"),
        ("4000000001", SKIN),
    ]


def test_a_new_database_has_the_sites_row(importer) -> None:
    cursor = importer.database.get_cursor()
    cursor.execute("SELECT name, code FROM Sites WHERE id IN (72, 147) ORDER BY id")
    assert cursor.fetchall() == [("Sky Poker", "IP"), (SKIN, "PS")]


def test_an_older_database_gains_the_sites_row(importer) -> None:
    database = importer.database
    cursor = database.get_cursor()
    cursor.execute("DELETE FROM Sites WHERE id = 147")
    database.commit()

    database.ensure_sites_rows()

    cursor.execute("SELECT name, code FROM Sites WHERE id IN (72, 147) ORDER BY id")
    assert cursor.fetchall() == [("Sky Poker", "IP"), (SKIN, "PS")]


@pytest.mark.parametrize("template", ["HUD_config.xml", "HUD_config.xml.example"])
def test_the_shipped_configuration_knows_the_room(tmp_path, template: str) -> None:
    from fpdb_3_legacy.HandHistoryConverter import getSiteHhc

    shutil.copyfile(ROOT / template, tmp_path / "HUD_config.xml")
    config = Config(file=str(tmp_path / "HUD_config.xml"))

    assert config.get_site_id(SKIN) == 147
    assert config.get_site_id("Sky Poker") == 72
    site = config.supported_sites[SKIN]
    assert not site.enabled
    assert site.HH_path == site.TS_path == ""
    assert site.network == "PokerStars"
    # No <hhc> of its own: it goes through PokerStars' converter.
    assert SKIN not in config.hhcs
    assert config.get_site_parameters(SKIN)["converter"] == "PokerStarsToFpdb"
    assert config.get_site_parameters(SKIN)["summaryImporter"] == "PokerStarsSummary"
    assert getSiteHhc(config, SKIN) is PokerStars
