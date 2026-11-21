"""PokerStars on Paddy Power: Paddy Power Poker's client on PokerStars software (#888).

Paddy Power Poker moved from iPoker to the PokerStars network on 28 October
2026. Its new client is filed under a room of its own, PokerStars on Paddy
Power (146), apart from the iPoker room Paddy Power Poker (65), which keeps the
hands the old client wrote.

Nothing in a PokerStars history names the skin, and the new client's folders
are not documented, so fpdb guesses none. A hand is filed under the new room
only on explicit provenance: the folder the user configured for the room, or a
hero mapped to it in ``pokerstars_skin_mapping.conf``. Never on GBP stakes or a
plain PokerStars header, and never for a hand dated before the client opened.

No real export from the new client is public yet: these tests run PokerStars'
own fixtures, re-dated, from a configured folder. They check how hands are
filed, not that the parser reads every line the new client writes.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.iPoker.dispatcher import IPokerSkinDispatcher
from fpdb_3_legacy.iPoker.skins.paddy_power import PaddyPowerIPoker
from fpdb_3_legacy.PokerStarsToFpdb import (
    POKERSTARS_SKIN_FIRST_DAYS,
    POKERSTARS_SKIN_IDS,
    SITE_POKERSTARS_PADDY_POWER,
    PokerStars,
)

ROOT = Path(__file__).resolve().parents[1]
CASH_HAND = ROOT / "regression-test-files/cash/Stars/Flop/2025-NL-uncalled-bet.txt"
SUMMARY = ROOT / "regression-test-files/summaries/Stars/6+Holdem-3max-STT-USD-1.00-201907.txt"
SKIN = "PokerStars on Paddy Power"


def _gbp_hand(date: str = "2026/11/02", et_date: str | None = None, hero: str = "Hero") -> str:
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
    def __init__(self, **sites: SimpleNamespace) -> None:
        self.supported_sites = {name.replace("_", " "): site for name, site in sites.items()}


def _parser(config: object = None, mappings: dict[str, str] | None = None) -> PokerStars:
    parser = PokerStars.__new__(PokerStars)
    parser.config = config
    parser._hero_mappings = mappings or {}
    return parser


def _configured(folder: Path) -> _Config:
    return _Config(PokerStars_on_Paddy_Power=_site(str(folder / "HandHistory"), str(folder / "TournSummary")))


# ---------------------------------------------------------------------------
# The room's identity
# ---------------------------------------------------------------------------


def test_the_room_has_its_own_site_id() -> None:
    assert POKERSTARS_SKIN_IDS[SKIN] == SITE_POKERSTARS_PADDY_POWER == 146
    # Distinct from every other PokerStars room and from the iPoker Paddy Power room.
    assert list(POKERSTARS_SKIN_IDS.values()).count(146) == 1
    assert PaddyPowerIPoker.site_id == 65


def test_the_room_opened_on_28_october_2026() -> None:
    assert POKERSTARS_SKIN_FIRST_DAYS[SKIN].isoformat() == "2026-10-28"


def test_the_room_policy_is_pokerstars() -> None:
    from fpdb_3_legacy import hud_room_policy

    assert hud_room_policy.network_of(SKIN) == "pokerstars"
    assert hud_room_policy.capabilities_at(SKIN) == hud_room_policy.capabilities_at("PokerStars.FR")
    assert hud_room_policy.why_not("dynamic_hud", SKIN)
    assert not hud_room_policy.capabilities_at(SKIN).positional_hud
    # The iPoker room keeps the iPoker policy.
    assert hud_room_policy.network_of("Paddy Power Poker") == "ipoker"


# ---------------------------------------------------------------------------
# What files a hand under the room, and what does not
# ---------------------------------------------------------------------------


def test_a_hand_in_the_configured_folder_is_filed_under_the_room(tmp_path: Path) -> None:
    parser = _parser(_configured(tmp_path / "PP"))
    path = tmp_path / "PP" / "HandHistory" / "Hero" / "HH20261102.txt"

    assert parser.detectPokerStarsSkin(_gbp_hand(), str(path)) == (SKIN, 146)


def test_a_summary_in_the_configured_folder_is_filed_under_the_room(tmp_path: Path) -> None:
    parser = _parser(_configured(tmp_path / "PP"))
    summary = "PokerStars Tournament #4000000001, No Limit Hold'em\nTournament started 2026/11/02 20:00:00 GMT\n"

    assert parser.detectPokerStarsSkin(summary, str(tmp_path / "PP" / "TournSummary" / "TS.txt")) == (SKIN, 146)


@pytest.mark.parametrize(
    "relative",
    [
        # A sibling folder sharing the configured folder's name as a prefix.
        "PP/HandHistory2/HH.txt",
        "PP/TournSummaryOld/TS.txt",
        # A copy elsewhere.
        "Downloads/HH20261102.txt",
    ],
)
def test_a_file_outside_the_configured_folders_is_not(tmp_path: Path, relative: str) -> None:
    parser = _parser(_configured(tmp_path / "PP"))

    assert parser.detectPokerStarsSkin(_gbp_hand(), str(tmp_path / relative)) == ("PokerStars.COM", 32)


def test_an_unconfigured_room_files_nothing(tmp_path: Path) -> None:
    # The shipped room has no folder: nothing is filed under it until the user sets one.
    parser = _parser(_Config(PokerStars_on_Paddy_Power=_site()))

    assert parser.detectPokerStarsSkin(_gbp_hand(), str(tmp_path / "HH.txt")) == ("PokerStars.COM", 32)
    assert _parser(None).detectPokerStarsSkin(_gbp_hand(), str(tmp_path / "HH.txt")) == ("PokerStars.COM", 32)


@pytest.mark.parametrize(
    "path",
    [
        r"C:\Users\alice\AppData\Local\PaddyPower\HandHistory\alice\HH20261102.txt",
        r"C:\Users\alice\AppData\Local\Paddy Power Poker\HandHistory\alice\HH20261102.txt",
        "/home/alice/paddypower/HH20261102.txt",
    ],
)
def test_no_folder_name_is_guessed(path: str) -> None:
    # The new client's folder is not documented: a folder merely named after
    # Paddy Power is not taken as its provenance.
    assert _parser(None).detectPokerStarsSkin(_gbp_hand(), path) == ("PokerStars.COM", 32)


def test_gbp_stakes_alone_do_not_name_the_room() -> None:
    assert _parser(None).detectPokerStarsSkin(_gbp_hand(), None) == ("PokerStars.COM", 32)


def test_a_hero_mapped_to_the_room_files_it_there() -> None:
    parser = _parser(None, {"hero": SKIN})

    assert parser.detectPokerStarsSkin(_gbp_hand(), None) == (SKIN, 146)


@pytest.mark.parametrize("how", ["folder", "hero"])
def test_a_hand_from_before_the_move_is_never_filed_there(tmp_path: Path, how: str) -> None:
    # A Paddy Power player may have played PokerStars under the same name
    # before the move; those hands are not the new client's.
    config = _configured(tmp_path / "PP") if how == "folder" else None
    parser = _parser(config, {"hero": SKIN} if how == "hero" else None)
    path = str(tmp_path / "PP" / "HandHistory" / "HH.txt")

    assert parser.detectPokerStarsSkin(_gbp_hand("2026/10/27"), path) == ("PokerStars.COM", 32)


def test_the_first_day_counts() -> None:
    parser = _parser(None, {"hero": SKIN})

    assert parser.detectPokerStarsSkin(_gbp_hand("2026/10/28"), None) == (SKIN, 146)
    # Already the 28th in local time, still the 27th in ET: the hand is the new client's.
    assert parser.detectPokerStarsSkin(_gbp_hand("2026/10/28", et_date="2026/10/27"), None) == (SKIN, 146)


def test_a_hand_with_no_readable_date_goes_by_its_provenance() -> None:
    parser = _parser(None, {"hero": SKIN})
    undated = "PokerStars Hand #1: Hold'em No Limit (£0.05/£0.10 GBP)\nDealt to Hero [As Kc]\n"

    assert parser.detectPokerStarsSkin(undated, None) == (SKIN, 146)


def test_other_rooms_are_not_affected_by_the_first_day(tmp_path: Path) -> None:
    parser = _parser(_configured(tmp_path / "PP"), {"hero": "PokerStars.FR"})

    assert parser.detectPokerStarsSkin(_gbp_hand("2019/01/01"), None) == ("PokerStars.FR", 33)
    path = r"C:\Users\alice\AppData\Local\PokerStars.FR\HandHistory\alice\HH.txt"
    assert _parser(_configured(tmp_path / "PP")).detectPokerStarsSkin(_gbp_hand("2019/01/01"), path) == (
        "PokerStars.FR",
        33,
    )


# ---------------------------------------------------------------------------
# The iPoker room keeps the old client's hands
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        r"C:\Users\alice\AppData\Local\Paddy Power Poker\data\alice\History\Data\Tables\x.xml",
        "/home/alice/.wine/drive_c/Program Files/PaddyPower/data/alice/History/Data/Tables/x.xml",
    ],
)
def test_old_ipoker_hands_stay_under_site_65(path: str) -> None:
    skin = IPokerSkinDispatcher().detect(path)

    assert skin is not None
    assert (skin.site_name, skin.default_site_id) == ("Paddy Power Poker", 65)


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
            "db-databaseName": str(tmp_path / "paddy_power.sqlite3"),
            "db-path": "",
        }
    )
    config.get_db_parameters = lambda: params
    site = config.supported_sites[SKIN]
    site.HH_path = str(tmp_path / "PP" / "HandHistory")
    site.TS_path = str(tmp_path / "PP" / "TournSummary")
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
    hand = _copy(CASH_HAND, tmp_path / "PP" / "HandHistory" / "Hero" / CASH_HAND.name, "2025/04/24", "2026/11/02")

    assert _import(importer, hand) == 0
    assert _hand_sites(importer) == [SKIN]


def test_old_hands_in_the_configured_folder_stay_generic(importer, tmp_path) -> None:
    hand = _copy(CASH_HAND, tmp_path / "PP" / "HandHistory" / "Hero" / CASH_HAND.name, "2025/04/24", None)

    assert _import(importer, hand) == 0
    assert _hand_sites(importer) == ["PokerStars.COM"]


def test_a_copy_outside_the_configured_folder_stays_generic(importer, tmp_path) -> None:
    hand = _copy(CASH_HAND, tmp_path / "copies" / CASH_HAND.name, "2025/04/24", "2026/11/02")

    assert _import(importer, hand) == 0
    assert _hand_sites(importer) == ["PokerStars.COM"]


def test_summaries_from_the_configured_folder_are_filed_under_the_room(importer, tmp_path) -> None:
    summary = _copy(SUMMARY, tmp_path / "PP" / "TournSummary" / "Hero" / SUMMARY.name, "2019/07/31", "2026/11/02")

    _import(importer, summary)

    cursor = importer.database.get_cursor()
    cursor.execute("SELECT DISTINCT s.name FROM TourneyTypes t JOIN Sites s ON t.siteId = s.id")
    assert [row[0] for row in cursor.fetchall()] == [SKIN]


def test_a_new_database_has_the_sites_row(importer) -> None:
    cursor = importer.database.get_cursor()
    cursor.execute("SELECT name, code FROM Sites WHERE id IN (65, 146) ORDER BY id")
    assert cursor.fetchall() == [("Paddy Power Poker", "IP"), (SKIN, "PS")]


def test_an_older_database_gains_the_sites_row(importer) -> None:
    database = importer.database
    cursor = database.get_cursor()
    cursor.execute("DELETE FROM Sites WHERE id = 146")
    database.commit()

    database.ensure_sites_rows()

    cursor.execute("SELECT name, code FROM Sites WHERE id = 146")
    assert cursor.fetchall() == [(SKIN, "PS")]


def test_the_shipped_configuration_knows_the_room(tmp_path) -> None:
    shutil.copyfile(ROOT / "HUD_config.xml", tmp_path / "HUD_config.xml")
    config = Config(file=str(tmp_path / "HUD_config.xml"))

    assert config.get_site_id(SKIN) == 146
    assert config.get_site_id("Paddy Power Poker") == 65
    site = config.supported_sites[SKIN]
    assert not site.enabled
    assert site.HH_path == site.TS_path == ""
    assert site.network == "PokerStars"


def test_each_summary_of_an_export_is_filed_by_its_own_date(importer, tmp_path) -> None:
    # An export of several summaries spanning the move: the room is decided for
    # the file as a whole, but a tournament played before 28 October 2026 is
    # not the new client's and stays where its own text puts it.
    old = SUMMARY.read_text(encoding="utf-8")
    new = old.replace("2019/07/31", "2026/11/02").replace("#2663538841", "#4000000001")
    export = tmp_path / "PP" / "TournSummary" / "Hero" / "export.txt"
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


def test_each_hand_of_a_file_is_filed_by_its_own_date(importer, tmp_path) -> None:
    old = CASH_HAND.read_text(encoding="utf-8")
    new = old.replace("2025/04/24", "2026/11/02").replace("#255867983097", "#260000000001")
    hands = tmp_path / "PP" / "HandHistory" / "Hero" / "mixed.txt"
    hands.parent.mkdir(parents=True)
    hands.write_text(old.rstrip("\n") + "\n\n\n\n" + new, encoding="utf-8")

    assert _import(importer, hands) == 0

    cursor = importer.database.get_cursor()
    cursor.execute(
        "SELECT h.siteHandNo, s.name FROM Hands h JOIN Gametypes g ON h.gametypeId = g.id"
        " JOIN Sites s ON g.siteId = s.id ORDER BY h.siteHandNo"
    )
    assert [(str(no), site) for no, site in cursor.fetchall()] == [
        ("255867983097", "PokerStars.COM"),
        ("260000000001", SKIN),
    ]


# ---------------------------------------------------------------------------
# The room has no <hhc> of its own: it goes through PokerStars' converter
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("template", ["HUD_config.xml", "HUD_config.xml.example"])
def test_the_room_borrows_the_pokerstars_converter(tmp_path, template: str) -> None:
    from fpdb_3_legacy.HandHistoryConverter import getSiteHhc, getTableNoRe

    shutil.copyfile(ROOT / template, tmp_path / "HUD_config.xml")
    config = Config(file=str(tmp_path / "HUD_config.xml"))

    assert SKIN not in config.hhcs
    assert config.get_site_hhc(SKIN).converter == "PokerStarsToFpdb"
    assert config.get_site_parameters(SKIN)["converter"] == "PokerStarsToFpdb"
    assert config.get_site_parameters(SKIN)["summaryImporter"] == "PokerStarsSummary"
    # The tournament HUD's table lookup (Table_Window) used to raise KeyError here.
    assert getSiteHhc(config, SKIN) is PokerStars
    assert getTableNoRe(config, SKIN, "4000000001") == PokerStars.getTableNoRe("4000000001")


def test_a_site_with_no_converter_and_no_network_still_has_none(tmp_path) -> None:
    shutil.copyfile(ROOT / "HUD_config.xml", tmp_path / "HUD_config.xml")
    config = Config(file=str(tmp_path / "HUD_config.xml"))
    config.supported_sites[SKIN].network = "Unknown"

    assert config.get_site_hhc(SKIN) is None
    assert config.get_site_hhc("No Such Room") is None
    assert config.get_site_hhc("PokerStars.FR") is config.hhcs["PokerStars.FR"]
