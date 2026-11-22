"""PokerStars on Sisal and PokerStars on SNAI: the Italian skins on PokerStars (#893).

Sisal (December 2024) and SNAI (May 2026) moved their Italian clients from the
iPoker network to the PokerStars Italy network. Each new client is filed under
a room of its own, PokerStars on Sisal (148) and PokerStars on SNAI (149),
apart from the iPoker rooms Sisal Poker (73) and Snai Poker (76), which keep the
hands the old clients wrote, and from PokerStars' own Italian client,
PokerStars.IT (34).

An Italian PokerStars history carries an ADM ID, but nothing in it is known to
name the skin, and the new clients' folders are not documented, so fpdb
guesses none. A hand is filed under a new room only on explicit provenance:
the folder the user configured for the room, or a hero mapped to it in
``pokerstars_skin_mapping.conf``. Never on EUR stakes, an ADM ID or a plain
PokerStars header, and never for a hand dated before the client's month.

PROVISIONAL: no real export from either client is in the corpus yet. These
tests run PokerStars' own fixtures, re-dated and given an Italian header, from a
configured folder. They check how hands are filed, not that the parser reads
every line the new clients write.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.iPoker.dispatcher import IPokerSkinDispatcher
from fpdb_3_legacy.iPoker.skins.sisal import SisalIPoker
from fpdb_3_legacy.iPoker.skins.snai import SnaiIPoker
from fpdb_3_legacy.PokerStarsToFpdb import (
    POKERSTARS_CONFIGURED_PATH_SKINS,
    POKERSTARS_SKIN_FIRST_DAYS,
    POKERSTARS_SKIN_IDS,
    SITE_POKERSTARS_IT,
    SITE_POKERSTARS_SISAL,
    SITE_POKERSTARS_SNAI,
    PokerStars,
)

ROOT = Path(__file__).resolve().parents[1]
CASH_HAND = ROOT / "regression-test-files/cash/Stars/Flop/2025-NL-uncalled-bet.txt"
SUMMARY = ROOT / "regression-test-files/summaries/Stars/6+Holdem-3max-STT-USD-1.00-201907.txt"
SISAL = "PokerStars on Sisal"
SNAI = "PokerStars on SNAI"
IT = ("PokerStars.IT", SITE_POKERSTARS_IT)
ADM = "[ADM ID: 1A2B3C4D5E6F7G8H]"


class Room(SimpleNamespace):
    name: str
    site_id: int
    first_day: str
    before: str  # a day before the client's month
    after: str  # a day the client was dealing
    ipoker: str
    ipoker_id: int
    folder: str


ROOMS = [
    Room(
        name=SISAL,
        site_id=148,
        first_day="2024-12-01",
        before="2024/11/30",
        after="2025/02/10",
        ipoker="Sisal Poker",
        ipoker_id=73,
        folder="Sisal",
    ),
    Room(
        name=SNAI,
        site_id=149,
        first_day="2026-05-01",
        before="2026/04/30",
        after="2026/06/10",
        ipoker="Snai Poker",
        ipoker_id=76,
        folder="SNAI",
    ),
]
ROOM_IDS = [room.folder for room in ROOMS]


@pytest.fixture(params=ROOMS, ids=ROOM_IDS)
def room(request) -> Room:
    return request.param


def _italian_hand(date: str, et_date: str | None = None, hero: str = "Hero") -> str:
    et_date = et_date or date
    return (
        f"PokerStars Hand #260000000001:  Hold'em No Limit (€0.05/€0.10 EUR) {ADM} - {date} 20:15:00 CET"
        f" [{et_date} 14:15:00 ET]\n"
        "Table 'Esempio II' 6-max Seat #1 is the button\n"
        "Seat 1: Hero (€10 in chips)\n"
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


def _configured(base: Path, *rooms: Room) -> _Config:
    return _Config(
        {r.name: _site(str(base / r.folder / "HandHistory"), str(base / r.folder / "TournSummary")) for r in rooms}
    )


# ---------------------------------------------------------------------------
# The rooms' identity
# ---------------------------------------------------------------------------


def test_each_room_has_its_own_site_id() -> None:
    assert POKERSTARS_SKIN_IDS[SISAL] == SITE_POKERSTARS_SISAL == 148
    assert POKERSTARS_SKIN_IDS[SNAI] == SITE_POKERSTARS_SNAI == 149
    ids = list(POKERSTARS_SKIN_IDS.values())
    assert ids.count(148) == ids.count(149) == 1
    # Not the iPoker rooms' ids, and not PokerStars.IT's.
    assert (SisalIPoker.site_id, SnaiIPoker.site_id) == (73, 76)
    assert not {73, 76} & set(ids)
    assert POKERSTARS_SKIN_IDS["PokerStars.IT"] == 34


def test_each_room_opened_in_its_month(room: Room) -> None:
    assert POKERSTARS_SKIN_FIRST_DAYS[room.name].isoformat() == room.first_day


def test_each_room_is_filed_by_its_configured_folder(room: Room) -> None:
    assert room.name in POKERSTARS_CONFIGURED_PATH_SKINS


def test_the_room_policy_is_pokerstars(room: Room) -> None:
    from fpdb_3_legacy import hud_room_policy

    assert hud_room_policy.network_of(room.name) == "pokerstars"
    assert hud_room_policy.capabilities_at(room.name) == hud_room_policy.capabilities_at("PokerStars.IT")
    assert hud_room_policy.why_not("dynamic_hud", room.name)
    assert not hud_room_policy.capabilities_at(room.name).positional_hud
    # The iPoker room keeps the iPoker policy.
    assert hud_room_policy.network_of(room.ipoker) == "ipoker"


# ---------------------------------------------------------------------------
# What files a hand under a room, and what does not
# ---------------------------------------------------------------------------


def test_a_hand_in_the_configured_folder_is_filed_under_the_room(tmp_path: Path, room: Room) -> None:
    parser = _parser(_configured(tmp_path, room))
    path = tmp_path / room.folder / "HandHistory" / "Hero" / "HH.txt"

    assert parser.detectPokerStarsSkin(_italian_hand(room.after), str(path)) == (room.name, room.site_id)


def test_a_summary_in_the_configured_folder_is_filed_under_the_room(tmp_path: Path, room: Room) -> None:
    parser = _parser(_configured(tmp_path, room))
    summary = (
        "PokerStars Tournament #4000000001, No Limit Hold'em\n"
        f"Tournament started {room.after} 20:00:00 CET [{room.after} 14:00:00 ET]\n"
    )
    path = tmp_path / room.folder / "TournSummary" / "TS.txt"

    assert parser.detectPokerStarsSkin(summary, str(path)) == (room.name, room.site_id)


@pytest.mark.parametrize(
    "relative",
    [
        # A sibling folder sharing the configured folder's name as a prefix.
        "HandHistory2/HH.txt",
        "TournSummaryOld/TS.txt",
    ],
)
def test_a_sibling_folder_is_not_the_room(tmp_path: Path, room: Room, relative: str) -> None:
    parser = _parser(_configured(tmp_path, room))

    assert parser.detectPokerStarsSkin(_italian_hand(room.after), str(tmp_path / room.folder / relative)) == IT


def test_a_copy_outside_the_configured_folders_stays_pokerstars_it(tmp_path: Path, room: Room) -> None:
    # A relocated copy keeps no provenance: its ADM ID makes it PokerStars.IT's.
    parser = _parser(_configured(tmp_path, *ROOMS))

    assert parser.detectPokerStarsSkin(_italian_hand(room.after), str(tmp_path / "Downloads" / "HH.txt")) == IT


def test_an_unconfigured_room_files_nothing(tmp_path: Path, room: Room) -> None:
    # The shipped rooms have no folder: nothing is filed under them until the user sets one.
    parser = _parser(_Config({room.name: _site()}))

    assert parser.detectPokerStarsSkin(_italian_hand(room.after), str(tmp_path / "HH.txt")) == IT
    assert _parser(None).detectPokerStarsSkin(_italian_hand(room.after), str(tmp_path / "HH.txt")) == IT


@pytest.mark.parametrize(
    "path",
    [
        r"C:\Users\alice\AppData\Local\Sisal\HandHistory\alice\HH.txt",
        r"C:\Users\alice\AppData\Local\SisalPoker\HandHistory\alice\HH.txt",
        r"C:\Users\alice\AppData\Local\PokerStars.IT\Sisal\HandHistory\alice\HH.txt",
        r"C:\Users\alice\AppData\Local\SNAI\HandHistory\alice\HH.txt",
        r"C:\Program Files\Snai Poker\HandHistory\alice\HH.txt",
        "/home/alice/snai/HH.txt",
    ],
)
def test_no_folder_name_is_guessed(path: str) -> None:
    # The new clients' folders are not documented: a folder merely named after
    # Sisal or SNAI is not taken as their provenance.
    assert _parser(None).detectPokerStarsSkin(_italian_hand("2026/06/10"), path) == IT


def test_an_italian_header_alone_does_not_name_a_room() -> None:
    # EUR stakes and an ADM ID are PokerStars.IT's as much as Sisal's or SNAI's.
    assert _parser(None).detectPokerStarsSkin(_italian_hand("2026/06/10"), None) == IT


def test_a_hero_mapped_to_the_room_files_it_there(room: Room) -> None:
    # The opt-in for copied files (e-mailed exports, backups).
    parser = _parser(None, {"hero": room.name})

    assert parser.detectPokerStarsSkin(_italian_hand(room.after), None) == (room.name, room.site_id)
    assert parser.detectPokerStarsSkin(_italian_hand(room.after), "/home/alice/backup/HH.txt") == (
        room.name,
        room.site_id,
    )


@pytest.mark.parametrize("how", ["folder", "hero"])
def test_a_hand_from_before_the_move_is_never_filed_there(tmp_path: Path, room: Room, how: str) -> None:
    # A player may have played PokerStars.IT under the same name before the
    # move; those hands are not the new client's.
    config = _configured(tmp_path, room) if how == "folder" else None
    parser = _parser(config, {"hero": room.name} if how == "hero" else None)
    path = str(tmp_path / room.folder / "HandHistory" / "HH.txt")

    assert parser.detectPokerStarsSkin(_italian_hand(room.before), path) == IT


def test_the_first_day_counts(room: Room) -> None:
    parser = _parser(None, {"hero": room.name})
    first = room.first_day.replace("-", "/")

    assert parser.detectPokerStarsSkin(_italian_hand(first), None) == (room.name, room.site_id)
    # Already the 1st in Italy, still the day before in ET: the hand counts.
    assert parser.detectPokerStarsSkin(_italian_hand(first, et_date=room.before), None) == (room.name, room.site_id)


# ---------------------------------------------------------------------------
# Not conflated with each other or with PokerStars.IT
# ---------------------------------------------------------------------------


def test_sisal_and_snai_folders_each_keep_their_room(tmp_path: Path) -> None:
    parser = _parser(_configured(tmp_path, *ROOMS))
    hand = _italian_hand("2026/06/10")

    sisal = tmp_path / "Sisal" / "HandHistory" / "HH.txt"
    snai = tmp_path / "SNAI" / "HandHistory" / "HH.txt"
    assert parser.detectPokerStarsSkin(hand, str(sisal)) == (SISAL, 148)
    assert parser.detectPokerStarsSkin(hand, str(snai)) == (SNAI, 149)


def test_a_sisal_hand_from_before_snais_move_is_still_sisals(tmp_path: Path) -> None:
    # Dated after Sisal's move but before SNAI's: Sisal's folder files it, SNAI's does not.
    parser = _parser(_configured(tmp_path, *ROOMS))
    hand = _italian_hand("2025/06/10")

    assert parser.detectPokerStarsSkin(hand, str(tmp_path / "Sisal" / "HandHistory" / "HH.txt")) == (SISAL, 148)
    assert parser.detectPokerStarsSkin(hand, str(tmp_path / "SNAI" / "HandHistory" / "HH.txt")) == IT


def test_a_hero_mapped_to_pokerstars_it_stays_there(tmp_path: Path, room: Room) -> None:
    # A PokerStars.IT player keeps PokerStars.IT, even with the Italian rooms configured.
    parser = _parser(_configured(tmp_path, *ROOMS), {"hero": "PokerStars.IT"})

    assert parser.detectPokerStarsSkin(_italian_hand(room.after), str(tmp_path / "Stars" / "HH.txt")) == IT


# ---------------------------------------------------------------------------
# The iPoker rooms keep the old clients' hands
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (r"C:\Users\alice\AppData\Local\Sisal Poker\data\alice\History\Data\Tables\x.xml", ("Sisal Poker", 73)),
        (r"C:\Programmi\Sisal\data\alice\History\Data\Tables\x.xml", ("Sisal Poker", 73)),
        (r"C:\Users\alice\AppData\Local\Snai Poker\data\alice\History\Data\Tables\x.xml", ("Snai Poker", 76)),
        ("/home/alice/.wine/drive_c/Program Files/SNAI/data/alice/History/Data/Tables/x.xml", ("Snai Poker", 76)),
    ],
)
def test_old_ipoker_hands_stay_under_their_site(path: str, expected: tuple[str, int]) -> None:
    skin = IPokerSkinDispatcher().detect(path)

    assert skin is not None
    assert (skin.site_name, skin.default_site_id) == expected


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
            "db-databaseName": str(tmp_path / "italy.sqlite3"),
            "db-path": "",
        }
    )
    config.get_db_parameters = lambda: params
    for room in ROOMS:
        site = config.supported_sites[room.name]
        site.HH_path = str(tmp_path / room.folder / "HandHistory")
        site.TS_path = str(tmp_path / room.folder / "TournSummary")
    schema = Database(config)
    schema.recreate_tables()
    schema.close_connection()
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.setCallHud(False)
    yield importer
    importer.close()


def _italian_copy(target: Path, new_date: str | None) -> Path:
    """The PokerStars cash fixture with an Italian header, re-dated when ``new_date`` is given."""
    text = CASH_HAND.read_text(encoding="utf-8").replace("USD) - ", f"USD) {ADM} - ")
    if new_date:
        text = text.replace("2025/04/24", new_date)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


def _copy(source: Path, target: Path, old_date: str, new_date: str) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source.read_text(encoding="utf-8").replace(old_date, new_date), encoding="utf-8")
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


def test_hands_from_the_configured_folder_are_filed_under_the_room(importer, tmp_path, room: Room) -> None:
    hand = _italian_copy(tmp_path / room.folder / "HandHistory" / "Hero" / CASH_HAND.name, room.after)

    assert _import(importer, hand) == 0
    assert _hand_sites(importer) == [room.name]


def test_old_hands_in_the_configured_folder_stay_pokerstars_it(importer, tmp_path, room: Room) -> None:
    hand = _italian_copy(tmp_path / room.folder / "HandHistory" / "Hero" / CASH_HAND.name, room.before)

    assert _import(importer, hand) == 0
    assert _hand_sites(importer) == ["PokerStars.IT"]


def test_an_imported_copy_outside_the_configured_folders_stays_pokerstars_it(importer, tmp_path, room: Room) -> None:
    hand = _italian_copy(tmp_path / "copies" / CASH_HAND.name, room.after)

    assert _import(importer, hand) == 0
    assert _hand_sites(importer) == ["PokerStars.IT"]


def test_summaries_from_the_configured_folder_are_filed_under_the_room(importer, tmp_path, room: Room) -> None:
    target = tmp_path / room.folder / "TournSummary" / "Hero" / SUMMARY.name
    summary = _copy(SUMMARY, target, "2019/07/31", room.after)

    _import(importer, summary)

    cursor = importer.database.get_cursor()
    cursor.execute("SELECT DISTINCT s.name FROM TourneyTypes t JOIN Sites s ON t.siteId = s.id")
    assert [row[0] for row in cursor.fetchall()] == [room.name]


def test_a_new_database_has_the_sites_rows(importer) -> None:
    cursor = importer.database.get_cursor()
    cursor.execute("SELECT id, name, code FROM Sites WHERE id IN (34, 73, 76, 148, 149) ORDER BY id")
    assert cursor.fetchall() == [
        (34, "PokerStars.IT", "PS"),
        (73, "Sisal Poker", "IP"),
        (76, "Snai Poker", "IP"),
        (148, SISAL, "PS"),
        (149, SNAI, "PS"),
    ]


def test_an_older_database_gains_the_sites_rows(importer) -> None:
    database = importer.database
    cursor = database.get_cursor()
    cursor.execute("DELETE FROM Sites WHERE id IN (148, 149)")
    database.commit()

    database.ensure_sites_rows()

    cursor.execute("SELECT id, name, code FROM Sites WHERE id IN (73, 76, 148, 149) ORDER BY id")
    assert cursor.fetchall() == [
        (73, "Sisal Poker", "IP"),
        (76, "Snai Poker", "IP"),
        (148, SISAL, "PS"),
        (149, SNAI, "PS"),
    ]


@pytest.mark.parametrize("template", ["HUD_config.xml", "HUD_config.xml.example"])
def test_the_shipped_configuration_knows_the_rooms(tmp_path, template: str, room: Room) -> None:
    from fpdb_3_legacy.HandHistoryConverter import getSiteHhc

    shutil.copyfile(ROOT / template, tmp_path / "HUD_config.xml")
    config = Config(file=str(tmp_path / "HUD_config.xml"))

    assert config.get_site_id(room.name) == room.site_id
    assert config.get_site_id(room.ipoker) == room.ipoker_id
    site = config.supported_sites[room.name]
    assert not site.enabled
    assert site.HH_path == site.TS_path == ""
    assert site.network == "PokerStars"
    # No <hhc> of its own: it goes through PokerStars' converter.
    assert room.name not in config.hhcs
    assert config.get_site_parameters(room.name)["converter"] == "PokerStarsToFpdb"
    assert config.get_site_parameters(room.name)["summaryImporter"] == "PokerStarsSummary"
    assert getSiteHhc(config, room.name) is PokerStars
