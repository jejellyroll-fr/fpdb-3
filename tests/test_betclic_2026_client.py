"""The 2025+ in-house Betclic client: its ``*** HEADER ***`` exports (#730).

* The client writes text hand histories of its own since it left iPoker; the
  legacy skin "Betclic Poker" (id 131, iPoker XML) is a different site, so the
  new format is claimed by a separate converter under the site name "Betclic"
  (id 142).
* Hand, game and table ids are ULIDs; :func:`ulid_to_int` maps them to stable
  signed-BIGINT values for ``Hands.siteHandNo`` / ``Tourneys.siteTourneyNo``,
  so re-importing a file stores nothing twice.
* ``Game Mode: Spin`` hands are Spin & Rush lottery sit-and-gos: buy-in,
  prize pool, multiplier, and each player's finishing place and winnings all
  come from the header and the summary.
* ``Game Mode: Cash Game`` hands (PLO Omaha, NLHE) carry euro amounts.
* Fixtures under ``tests/fixtures/hands/betclic`` are anonymised (Hero /
  VillainN); the spin one is sliced from the public MIT-licensed
  florentvdry/spintracker corpus (4,416 hands, 300 tournaments), and the cash
  ones from a real 2026 export, so parsed totals are cross-checked against the
  raw text here.
"""

from __future__ import annotations

import datetime
import re
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from fpdb_3_legacy.BetclicToFpdb import BIGINT_MAX, Betclic, ulid_to_int
from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.DetectInstalledSites import BetclicDetector

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "hands" / "betclic"
SPIN = FIXTURES / "spin_rush_2026.txt"
PLO_CASH = FIXTURES / "plo_cash_2026.txt"
NLHE_CASH = FIXTURES / "nlhe_cash_2026.txt"

IPOKER_XML = """<?xml version="1.0" encoding="utf-8"?>
<session><game gamecode="1"><general><nickname>jejellyroll</nickname></general></game></session>
"""


def _parse(path: Path) -> list:
    return Betclic(config=Config(), in_path=str(path), autostart=True).getProcessedHands()


def _amount(raw: str) -> Decimal:
    return Decimal(re.sub(r"[^\d.]", "", raw))


# --- ULID identifiers -------------------------------------------------------


def test_ulid_mapping_is_stable_and_fits_a_signed_bigint() -> None:
    ulid = "01KE0EM78GQ5YJ5JGPZKQKTVCA"
    value = ulid_to_int(ulid)
    assert ulid_to_int(ulid) == value  # deterministic: re-import dedupes on it
    assert 0 <= value <= BIGINT_MAX
    # Lowercase Crockford is the same id.
    assert ulid_to_int(ulid.lower()) == value


def test_ulid_mapping_orders_by_timestamp_and_separates_same_millisecond_ids() -> None:
    # 48 timestamp bits shifted left by 15 keep the millisecond order...
    assert (
        ulid_to_int("01KE0E9VW7KKPNRM9PYPG9D7A5")
        < ulid_to_int("01KE0EM78GQ5YJ5JGPZKQKTVCA")
        < ulid_to_int("01M6RMBV2FTHQPW4GM3ZHBAV8J")
    )
    # ...and the 15 low random bits separate ids born in the same millisecond.
    same_ms_a = "01KE0E9VW7KKPNRM9PYPG9D7A5"
    same_ms_b = "01KE0E9VW7KKPNRM9PYPG9D7A6"
    assert ulid_to_int(same_ms_a) != ulid_to_int(same_ms_b)


def test_ulid_mapping_is_unique_over_every_fixture_id() -> None:
    for fixture in (SPIN, PLO_CASH, NLHE_CASH):
        text = fixture.read_text(encoding="utf-8")
        ulids = set(re.findall(r"^(?:Hand|Game|Table) ID: (\S+)$", text, re.MULTILINE))
        mapped = [ulid_to_int(u) for u in ulids]
        assert len(set(mapped)) == len(ulids)
        assert all(0 <= m <= BIGINT_MAX for m in mapped)


# --- identification ---------------------------------------------------------


def test_the_new_format_is_identified_and_the_ipoker_xml_is_not() -> None:
    spin_text = SPIN.read_text(encoding="utf-8")
    assert Betclic.re_identify.search(spin_text)
    assert not Betclic.re_identify.search(IPOKER_XML)
    # ...and the legacy iPoker skin does not claim the new text format either.
    from fpdb_3_legacy.iPoker.base import iPoker

    assert not iPoker.re_identify.search(spin_text)


def test_each_hand_chunk_identifies_exactly_once() -> None:
    converter = Betclic(config=Config(), in_path=str(SPIN), autostart=False)
    for hand_text in converter.allHandsAsList():
        assert not converter.isPartial(hand_text)


def test_a_crlf_export_is_still_identified(tmp_path: Path) -> None:
    # A Windows checkout rewrites the fixtures with CRLF; IdentifySite matches
    # the raw file, so the header regex must tolerate the carriage return.
    crlf = tmp_path / "export_crlf.txt"
    crlf.write_bytes(SPIN.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    text = crlf.read_bytes().decode("utf-8")
    assert Betclic.re_identify.search(text)
    hands = Betclic(config=Config(), in_path=str(crlf), autostart=True).getProcessedHands()
    assert len(hands) == 76


# --- Spin & Rush lottery sit-and-gos ---------------------------------------


def test_spin_hands_are_lottery_sit_and_gos() -> None:
    hands = _parse(SPIN)
    assert len(hands) == 76
    tourney_hands = [h for h in hands if h.gametype["type"] == "tour"]
    assert tourney_hands
    assert {h.isSng for h in tourney_hands} == {True}
    assert {h.isLottery for h in tourney_hands} == {True}
    # Multipliers x2 to x100 all come through, buy-in is the 2.00 EUR entry.
    assert {h.tourneyMultiplier for h in tourney_hands} == {2, 3, 4, 5, 100}
    assert {(h.buyin, h.fee, h.buyinCurrency) for h in tourney_hands} == {(200, 0, "EUR")}
    assert {h.gametype["category"] for h in tourney_hands} == {"holdem"}
    assert {h.gametype["limitType"] for h in tourney_hands} == {"nl"}
    # Tournament blinds/pots are chips: the gametype currency is "T$", while
    # the buy-in keeps the real currency (EUR).
    assert {h.gametype["currency"] for h in tourney_hands} == {"T$"}
    assert {h.maxseats for h in tourney_hands} == {3}


def test_spin_hand_identity_uses_the_mapped_ulids() -> None:
    hands = _parse(SPIN)
    first = hands[0]
    # The raw ULID from the fixture header maps to the stored integer id.
    raw_hand_id = re.search(r"^Hand ID: (\S+)$", SPIN.read_text(encoding="utf-8"), re.MULTILINE).group(1)
    raw_game_id = re.search(r"^Game ID: (\S+)$", SPIN.read_text(encoding="utf-8"), re.MULTILINE).group(1)
    assert first.handid == str(ulid_to_int(raw_hand_id))
    assert first.tourNo == str(ulid_to_int(raw_game_id))
    assert int(first.handid) <= BIGINT_MAX and int(first.tourNo) <= BIGINT_MAX
    # The table keeps the raw ULID as its name (a TEXT column), prefixed with
    # the tournament number for tournament hands.
    raw_table_id = re.search(r"^Table ID: (\S+)$", SPIN.read_text(encoding="utf-8"), re.MULTILINE).group(1)
    assert first.tablename == f"{first.tourNo} {raw_table_id}"
    assert len({h.handid for h in hands}) == len(hands)  # no collision in the fixture


def test_spin_hand_content() -> None:
    hands = _parse(SPIN)
    # The hand quoted in the issue, present in the fixture.
    first = next(h for h in hands if h.handid == str(ulid_to_int("01KE0EM78GQ5YJ5JGPZKQKTVCA")))
    assert first.hero == "Hero"
    assert first.buttonpos == 1
    # The header stamps UTC; the stored start time is that naive UTC time.
    raw_dt = re.search(r"^Date & Time: (.+) \(UTC\)$", first.handText, re.MULTILINE).group(1)
    assert first.startTime == datetime.datetime.strptime(raw_dt, "%Y-%m-%d %H:%M:%S")
    opponent = next(p[1] for p in first.players if p[1] != "Hero")
    assert [(p[0], p[2]) for p in first.players] == [(1, "680"), (3, "820")]
    assert first.players[0][1] == "Hero" and opponent.startswith("Villain")
    # Blinds land in BLINDSANTES, the raise/call in PREFLOP with the all-in flag.
    assert first.actions["BLINDSANTES"] == [
        ("Hero", "small blind", Decimal("50"), False),
        (opponent, "big blind", Decimal("100"), False),
    ]
    preflop = first.actions["PREFLOP"]
    # (player, "raises", raise-by, raise-to, ..., all-in flag)
    assert preflop[0][:4] == ("Hero", "raises", Decimal("580"), Decimal("680"))
    assert preflop[0][-1] is True  # "and is all-in": the stack hit zero
    assert preflop[1][:3] == (opponent, "calls", Decimal("580"))
    assert first.board["FLOP"] == ["3c", "9s", "Js"]
    assert first.board["TURN"] == ["2c"]  # street headers carry the cumulative board
    assert first.board["RIVER"] == ["7h"]
    assert first.holecards["PREFLOP"]["Hero"] == [[], ["Kc", "2d"]]
    assert first.collectees == {opponent: Decimal("1360")}
    assert first.totalpot == Decimal("1360") and first.rake == Decimal("0")
    # The tournament result: winner 1st with the 4.00 EUR prize, hero 2nd with
    # an explicit zero (never left unset, so the winnings column is not NULL).
    assert first.tourneyRanks == {opponent: 1, "Hero": 2}
    assert first.tourneyWinnings == {opponent: 400, "Hero": 0}
    assert first.tourneyWinningsCurrency == {opponent: "EUR", "Hero": "EUR"}


def test_spin_totals_match_the_raw_export_text() -> None:
    """Cross-check the parser against the corpus's own numbers (#730).

    The fixture is a slice of the public spintracker corpus (whose full
    4,416-hand / 300-tournament counts were verified against its
    excepted_result.txt while preparing it); here every parsed euro/chip the
    hero is credited must equal the raw "wins ... pot of" / "finished ... and
    wins" lines of the same file.
    """
    text = SPIN.read_text(encoding="utf-8")
    hands = _parse(SPIN)

    raw_won = sum(
        (_amount(m) for m in re.findall(r"wins (?:main|\d+(?:st|nd|rd|th) side) pot of (\S+)", text)),
        Decimal(0),
    )
    parsed_won = sum((sum(h.collectees.values()) for h in hands), Decimal(0))
    assert parsed_won == raw_won

    raw_hero_eur = sum(
        (
            _amount(m)
            for m in re.findall(r"^Hero finished \d+(?:st|nd|rd|th) and wins ([0-9.]+) EUR$", text, re.MULTILINE)
        ),
        Decimal(0),
    )
    parsed_hero_eur = sum((Decimal(h.tourneyWinnings.get("Hero", 0)) / 100 for h in hands), Decimal(0))
    assert parsed_hero_eur == raw_hero_eur

    # Every pot balances: collected + rake == the header's Total Pot.
    for hand in hands:
        collected = sum(hand.collectees.values(), Decimal(0))
        assert collected + Decimal(str(hand.rake)) == Decimal(str(hand.totalpot))


# --- Cash games (the user's own PLO / NLHE exports, anonymised) -------------


def test_plo_cash_hands_parse_as_euro_pot_limit_omaha() -> None:
    hands = _parse(PLO_CASH)
    assert len(hands) == 8
    assert {h.gametype["type"] for h in hands} == {"ring"}
    assert {h.gametype["category"] for h in hands} == {"omahahi"}
    assert {h.gametype["limitType"] for h in hands} == {"pl"}
    assert {(h.gametype["sb"], h.gametype["bb"], h.gametype["currency"]) for h in hands} == {("0.02", "0.05", "EUR")}
    assert {h.tourNo for h in hands} == {None}
    assert all(h.hero == "Hero" for h in hands)
    first = hands[0]
    assert first.holecards["PREFLOP"]["Hero"] == [[], ["4c", "4d", "Kh", "3c"]]  # PLO: four hole cards
    assert first.collectees == {"Villain4": Decimal("0.76")}
    assert first.totalpot == Decimal("0.80") and first.rake == Decimal("0.04")
    assert first.shown == {"Villain3", "Villain4"}
    assert first.winningHand["Villain4"] == ["As", "Ac", "2d", "2c", "Jh"]


def test_nlhe_cash_hands_parse() -> None:
    hands = _parse(NLHE_CASH)
    assert len(hands) == 4
    assert {h.gametype["category"] for h in hands} == {"holdem"}
    assert {h.gametype["limitType"] for h in hands} == {"nl"}
    assert all(len(h.holecards["PREFLOP"].get("Hero", [[], []])[1]) == 2 for h in hands)


# --- Re-import stores nothing twice ------------------------------------------


def test_reimporting_a_file_stores_nothing_twice(tmp_path, legacy_config, fresh_db) -> None:
    from fpdb_3_legacy.Importer import Importer

    first_copy = tmp_path / "export_a.txt"
    second_copy = tmp_path / "export_b.txt"
    first_copy.write_bytes(SPIN.read_bytes())
    second_copy.write_bytes(SPIN.read_bytes())

    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=legacy_config, sql=None)
    importer.database = fresh_db
    importer.addImportFile(str(first_copy), "Betclic")
    importer.runImport()
    cursor = fresh_db.get_cursor()
    cursor.execute("SELECT COUNT(*) FROM Hands WHERE siteHandNo IS NOT NULL")
    (stored,) = cursor.fetchone()
    assert stored == 76

    # A second file holding the same hands (same ULIDs -> same siteHandNo).
    importer.addImportFile(str(second_copy), "Betclic")
    importer.runImport()
    cursor.execute("SELECT COUNT(*) FROM Hands")
    (still,) = cursor.fetchone()
    assert still == stored
    del importer


# --- Installed-site detection ------------------------------------------------


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    return tmp_path


def _detector() -> BetclicDetector:
    detector = BetclicDetector(SimpleNamespace(os_family="Mac"))
    detector.platform = "Darwin"
    return detector


def test_exports_are_found_in_downloads_and_the_hero_named(home: Path) -> None:
    downloads = home / "Downloads"
    downloads.mkdir(parents=True)
    (downloads / "62497366_ExportHH_2026-11-8.txt").write_text(SPIN.read_text(encoding="utf-8"), encoding="utf-8")

    found = _detector().detect()

    assert found == {"detected": True, "hhpath": str(downloads), "heroname": "Hero", "tspath": str(downloads)}


def test_a_folder_of_xml_ipoker_hands_is_not_a_betclic_export(home: Path) -> None:
    downloads = home / "Downloads"
    downloads.mkdir(parents=True)
    (downloads / "12345_ExportHH_2026-11-8.txt").write_text(IPOKER_XML, encoding="utf-8")

    assert _detector().detect()["detected"] is False


def test_crlf_exports_are_still_detected(home: Path) -> None:
    # Windows exports carry CRLF line endings; detection must not reject them.
    downloads = home / "Downloads"
    downloads.mkdir(parents=True)
    crlf = SPIN.read_text(encoding="utf-8").replace("\n", "\r\n")
    (downloads / "62497366_ExportHH_2026-11-8.txt").write_bytes(crlf.encode("utf-8"))

    found = _detector().detect()

    assert found["detected"] is True
    assert found["heroname"] == "Hero"


def test_windows_downloads_and_onedrive_documents_are_searched(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    profile = tmp_path / "profile"
    folder = profile / "OneDrive" / "Documents"
    folder.mkdir(parents=True)
    (folder / "62497366_ExportHH_2026-11-6.txt").write_text(SPIN.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "elsewhere"))
    monkeypatch.setenv("USERPROFILE", str(profile))
    monkeypatch.setenv("LOCALAPPDATA", str(profile / "AppData" / "Local"))
    monkeypatch.setenv("APPDATA", str(profile / "AppData" / "Roaming"))
    detector = _detector()
    detector.platform = "Windows"

    assert detector.detect()["hhpath"] == str(folder)
