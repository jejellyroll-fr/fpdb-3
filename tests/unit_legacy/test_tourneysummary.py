"""Unit tests for fpdb_3_legacy.TourneySummary (non-DB, pure-logic parts).

The constructor calls ``parseSummary`` (a no-op in the base class). A fake db
object is supplied so the real Database is never instantiated, and a fake
config provides ``get_import_parameters``.
"""

from __future__ import annotations

import io
import types

import pytest

from fpdb_3_legacy.TourneySummary import TourneySummary


def _make_config():
    return types.SimpleNamespace(get_import_parameters=lambda: {"foo": "bar"})


class _FakeDb:
    """Minimal db stub. ``get_site_id`` returns nothing by default."""

    def __init__(self, site_id_result=None):
        self._site_id_result = site_id_result

    def get_site_id(self, name):
        return self._site_id_result


def _make_summary(db=None, site_name="PokerStars", summary_text="text"):
    if db is None:
        db = _FakeDb()
    return TourneySummary(
        db=db,
        config=_make_config(),
        siteName=site_name,
        summaryText=summary_text,
    )


class TestConstruction:
    def test_basic_attributes(self) -> None:
        ts = _make_summary(summary_text="hello")
        assert ts.siteName == "PokerStars"
        assert ts.summaryText == "hello"
        assert ts.import_parameters == {"foo": "bar"}
        assert ts.players == {}
        assert ts.buyin == 0
        assert ts.speed == "Normal"
        assert ts.gametype == {"category": None, "limitType": None, "mix": "none"}

    def test_site_id_from_hardcoded_table(self) -> None:
        ts = _make_summary(site_name="PokerStars")
        assert ts.siteId == TourneySummary.SITEIDS["PokerStars"]

    def test_site_id_from_database(self) -> None:
        db = _FakeDb(site_id_result=[[99]])
        ts = _make_summary(db=db, site_name="Anything")
        assert ts.siteId == 99

    def test_site_id_db_exception_falls_back(self) -> None:
        class _BoomDb(_FakeDb):
            def get_site_id(self, name):
                raise RuntimeError("db down")

        ts = _make_summary(db=_BoomDb(), site_name="Winamax")
        assert ts.siteId == TourneySummary.SITEIDS["Winamax"]

    def test_site_id_unknown_remains_none(self) -> None:
        ts = _make_summary(site_name="NoSuchSite")
        assert ts.siteId is None

    def test_db_empty_result_falls_back(self) -> None:
        db = _FakeDb(site_id_result=[])
        ts = _make_summary(db=db, site_name="Betfair")
        assert ts.siteId == TourneySummary.SITEIDS["Betfair"]


class TestClearMoneyString:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("$1 200", "1200"),
            ("2,000", "2000"),
            ("€5.50", "5.50"),
            ("&euro;5.50", "5.50"),
            ("$ 10", "10"),
        ],
    )
    def test_strips_symbols_and_separators(self, raw, expected) -> None:
        assert TourneySummary.clearMoneyString(raw) == expected


class TestGetSummaryText:
    def test_returns_summary(self) -> None:
        ts = _make_summary(summary_text="abc")
        assert ts.getSummaryText() == "abc"


class TestNoOpHooks:
    def test_get_split_re(self) -> None:
        ts = _make_summary()
        assert ts.getSplitRe("head") is None

    def test_parse_summary(self) -> None:
        ts = _make_summary()
        assert ts.parseSummary() is None


class TestAddPlayer:
    def test_add_new_player(self) -> None:
        ts = _make_summary()
        ts.addPlayer(1, "alice", 100, "USD", 0, 0, 0)
        assert ts.players["alice"] == [1]
        assert ts.ranks["alice"] == [1]
        assert ts.winnings["alice"] == [100]
        assert ts.winningsCurrency["alice"] == ["USD"]
        assert ts.rebuyCounts["alice"] == [0]
        assert ts.addOnCounts["alice"] == [0]
        assert ts.koCounts["alice"] == [0]

    def test_add_new_player_with_explicit_entry_id(self) -> None:
        ts = _make_summary()
        ts.addPlayer(2, "bob", 50, "EUR", 1, 1, 1, entryId=7)
        assert ts.players["bob"] == [7]

    def test_add_new_player_rank_none(self) -> None:
        ts = _make_summary()
        ts.addPlayer(None, "carol", 0, "USD", 0, 0, 0)
        assert ts.ranks["carol"] == [None]
        assert ts.winnings["carol"] == [0]

    def test_second_entry_no_entry_id_increments(self) -> None:
        ts = _make_summary()
        ts.addPlayer(1, "dave", 100, "USD", 0, 0, 0)
        ts.addPlayer(2, "dave", 200, "USD", 0, 0, 0)
        # entries = last element (1) + 1 => 2 appended
        assert ts.players["dave"] == [1, 2]
        assert ts.ranks["dave"] == [1, 2]
        assert ts.winnings["dave"] == [100, 200]
        assert ts.rebuyCounts["dave"] == [0, None]

    def test_second_entry_rank_none(self) -> None:
        ts = _make_summary()
        ts.addPlayer(1, "erin", 100, "USD", 0, 0, 0)
        ts.addPlayer(None, "erin", 200, "USD", 0, 0, 0)
        assert ts.ranks["erin"] == [1, None]

    def test_duplicate_entry_id_ignored(self) -> None:
        ts = _make_summary()
        ts.addPlayer(1, "frank", 100, "USD", 0, 0, 0, entryId=5)
        ts.addPlayer(1, "frank", 999, "USD", 0, 0, 0, entryId=5)
        # entryId 5 already present -> ignored, no second entry
        assert ts.players["frank"] == [5]
        assert ts.winnings["frank"] == [100]

    def test_new_entry_id_appended(self) -> None:
        ts = _make_summary()
        ts.addPlayer(1, "gina", 100, "USD", 0, 0, 0, entryId=5)
        ts.addPlayer(2, "gina", 200, "USD", 0, 0, 0, entryId=6)
        assert ts.players["gina"] == [5, 6]
        assert ts.ranks["gina"] == [1, 2]


class TestImapBranch:
    def test_builtfrom_imap(self) -> None:
        ts = TourneySummary(
            db=_FakeDb(),
            config=_make_config(),
            siteName="PokerStars",
            summaryText="x",
            builtFrom="IMAP",
        )
        # IMAP branch is a no-op pass; object still constructs fine.
        assert ts.siteName == "PokerStars"


class _InsertDb(_FakeDb):
    """Fake db recording the calls made by insertOrUpdate."""

    def __init__(self):
        super().__init__()
        self.calls = []
        self.printdata = None

    def set_printdata(self, flag):
        self.printdata = flag

    def getSqlPlayerIDs(self, names, site_id, hero):
        self.calls.append("getSqlPlayerIDs")
        return {name: i for i, name in enumerate(names)}

    def createOrUpdateTourneyType(self, summary):
        self.calls.append("type")
        return 11

    def createOrUpdateTourney(self, summary):
        self.calls.append("tourney")
        return 22

    def createOrUpdateTourneysPlayers(self, summary):
        self.calls.append("players")

    def commit(self):
        self.calls.append("commit")


class TestInsertOrUpdate:
    def test_inserts_and_returns_counters(self) -> None:
        db = _InsertDb()
        ts = _make_summary(db=db)
        ts.addPlayer(1, "alice", 100, "USD", 0, 0, 0)
        result = ts.insertOrUpdate(printtest=True)
        assert result == (0, 0, 0, 0, 0)
        assert db.printdata is True
        assert ts.tourneyTypeId == 11
        assert ts.tourneyId == 22
        assert db.calls == [
            "getSqlPlayerIDs",
            "type",
            "tourney",
            "players",
            "commit",
        ]


class TestReadFile:
    def test_reads_with_first_codec(self, tmp_path) -> None:
        f = tmp_path / "summary.txt"
        f.write_text("hello world", encoding="utf-8")
        ts = _make_summary()
        ts.codepage = ["utf-8"]
        # readFile is a (mis-declared) staticmethod taking (self, filename).
        content = TourneySummary.readFile(ts, str(f))
        assert content == "hello world"

    def test_returns_none_when_all_codecs_fail(self, tmp_path) -> None:
        f = tmp_path / "bin.dat"
        # 0xff 0xff is NOT a UTF-16 BOM (those are ff fe / fe ff), so readFile does
        # not take the BOM fast-path and falls through to the codepage loop, where
        # the invalid bytes fail every codec -> None.
        f.write_bytes(b"\xff\xffinvalid")
        ts = _make_summary()
        ts.codepage = ["utf-8"]
        content = TourneySummary.readFile(ts, str(f))
        assert content is None


class TestExcelSummaries:
    def test_groups_rows_by_text_tournament_id(self, monkeypatch) -> None:
        rows = [
            ["Tournament report"],
            ["Tournament ID", "Player", "Winnings"],
            ["42", "Alice", "100"],
            ["42", "Bob", "0"],
        ]
        sheet = types.SimpleNamespace(nrows=len(rows), row_values=lambda index: rows[index])
        workbook = types.SimpleNamespace(sheet_by_index=lambda _index: sheet)
        fake_xlrd = types.SimpleNamespace(open_workbook=lambda _filename: workbook)
        monkeypatch.setattr("fpdb_3_legacy.TourneySummary.xlrd", fake_xlrd)

        summaries = TourneySummary.summaries_from_excel("report.xls", "Tournament ID")

        assert len(summaries) == 1
        assert [entry["Player"] for entry in summaries[0]] == ["Alice", "Bob"]
        assert summaries[0][0]["header"] == "Tournament report"


class TestStr:
    def test_str_contains_sections(self) -> None:
        ts = _make_summary()
        ts.addPlayer(1, "alice", 100, "USD", 0, 0, 0)
        s = str(ts)
        assert "SITE" in s
        assert "PLAYERS" in s
        assert "alice" in s

    def test_str_contains_modern_tournament_flags(self) -> None:
        ts = _make_summary()
        ts.isProgressive = True
        ts.isReEntry = True
        ts.isFlighted = True
        ts.isLottery = True
        ts.tourneyMultiplier = 5

        rendered = str(ts)

        assert "PROGRESSIVE = True" in rendered
        assert "RE-ENTRY = True" in rendered
        assert "FLIGHTED = True" in rendered
        assert "LOTTERY = True" in rendered
        assert "TOURNEY MULTIPLIER = 5" in rendered


class TestWriteAndPrint:
    def test_write_summary_default_override_message(self) -> None:
        ts = _make_summary()
        buf = io.StringIO()
        ts.writeSummary(buf)
        assert buf.getvalue() == "Override me\n"

    def test_print_summary(self, capsys) -> None:
        ts = _make_summary()
        ts.printSummary()
        assert "Override me" in capsys.readouterr().out
