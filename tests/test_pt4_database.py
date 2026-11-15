"""Hands straight from a PokerTracker 4 database (#814), against a fake PT4 connection.

The rows are the shipped corpus' own hands, stored the way #615 found PT4 stores
them: the room's text, Mac Roman where PT4 decoded a cp1252 file as such, and no
file name. They are written out, scanned and imported into a throwaway SQLite
database exactly as the wizard does it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fpdb_3_legacy import pt4_database
from fpdb_3_legacy.Importer import Importer
from fpdb_3_legacy.pt4_database import Pt4Database, export_database, repair_mac_roman, winning_file_name
from fpdb_3_legacy.tracker_migration import scan_folder

ROOT = Path(__file__).resolve().parents[1]
STARS_CASH = ROOT / "regression-test-files" / "cash" / "Stars" / "Flop" / "2025-NL-uncalled-bet.txt"
RIO_TOURNEY = ROOT / "regression-test-files" / "tour" / "Stars" / "Flop" / "NLHE-3max-EUR-5.00-202103.classic.txt"
WINNING_V1 = (
    ROOT
    / "regression-test-files"
    / "tour"
    / "Winning"
    / "NLHE-9max-USD- HH20160828 T5795043-G33949698-201608.ante.2.txt"
)


WINNING_V1_CASH = (
    ROOT
    / "regression-test-files"
    / "cash"
    / "Winning"
    / "PLO8-6max-USD-40-80-201610.disconnected.allin.HH00000000 G0.txt"
)
BOM = chr(0xFEFF)


def _read(path: Path, encoding: str) -> str:
    return path.read_bytes().decode(encoding).lstrip(BOM)


WINAMAX_SUMMARY = ROOT / "regression-test-files" / "summaries" / "Winamax" / "NLHE-EUR-Expresso-1-202604.lottery.txt"


def _as_pt4_stores_winning(hand: str, tourney_no: str) -> str:
    """PT4 appends `` Tournament#<n>`` to an old-format Winning hand's first line."""
    first, _, rest = hand.partition("\n")
    return f"{first.rstrip()} Tournament#{tourney_no}\n{rest}"


def _as_pt4_stores_winamax_summary() -> str:
    """PT4 appends ``, Filename: <file>`` to a Winamax summary's first line."""
    first, _, rest = _read(WINAMAX_SUMMARY, "utf-8").partition("\n")
    return f"{first}, Filename: 20260410_Expresso(1096056742)_real_holdem_no-limit_summary.txt\n{rest}"


class FakeCursor:
    def __init__(self, conn: FakeConn, name: str | None) -> None:
        self.conn = conn
        self.name = name
        self.rows: list[tuple] = []
        self.itersize = 0

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *_exc) -> bool:
        if self.name:
            self.conn.closed_cursors.append(self.name)
        return False

    def execute(self, query: str, params: tuple = ()) -> None:
        self.conn.queries.append(query)
        since = params[0] if params else 0
        if query.startswith("SELECT count(*)"):
            kind = "cash" if "cash_" in query else "tourney"
            self.rows = [(sum(1 for row in self.conn.hands[kind] if row[0] > since),)]
        elif "FROM tourney_summary t JOIN" in query:
            self.rows = list(self.conn.summaries)
        else:
            kind = "cash" if "FROM cash_hand_histories" in query else "tourney"
            self.rows = [row for row in self.conn.hands[kind] if row[0] > since]

    def fetchone(self) -> tuple:
        return self.rows[0]

    def __iter__(self):
        return iter(self.rows)


class FakeTransaction:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *_exc) -> bool:
        return False


class FakeConn:
    """A psycopg-shaped PT4 connection that answers the module's queries from lists."""

    def __init__(self, cash=(), tourney=(), summaries=()) -> None:
        self.hands = {"cash": list(cash), "tourney": list(tourney)}
        self.summaries = list(summaries)
        self.queries: list[str] = []
        self.closed_cursors: list[str] = []

    def cursor(self, name: str | None = None) -> FakeCursor:
        return FakeCursor(self, name)

    def transaction(self) -> FakeTransaction:
        return FakeTransaction()


# --- what the database changed ---------------------------------------------------


def test_a_history_pt4_read_as_mac_roman_gets_its_euro_back() -> None:
    stored = RIO_TOURNEY.read_bytes().decode("mac_roman")
    assert "Ä4.69" in stored or "Ä" in stored.splitlines()[0]

    repaired, changed = repair_mac_roman(stored)

    assert changed
    assert repaired == RIO_TOURNEY.read_bytes().decode("cp1252")
    assert "€" in repaired.splitlines()[0]


def test_a_history_pt4_read_correctly_keeps_its_accents() -> None:
    text = "Winamax Poker - CashGame - HandId: #1 - Holdem no limit (0.01€/0.02€)\nSeat 1: Hélène (2€)"
    assert repair_mac_roman(text) == (text, False)


def test_a_history_mac_roman_cannot_encode_is_left_alone() -> None:
    text = "Poker Hand #RC1: Hold'em No Limit (Ä5) 玩家"
    assert repair_mac_roman(text) == (text, False)


def test_the_old_winning_format_gets_the_file_name_it_reads_its_tournament_from() -> None:
    history = _read(WINNING_V1, "utf-8")

    assert winning_file_name(history, "5795043") == "HH20160828 T5795043-G0"
    assert winning_file_name(history, None) is None
    assert winning_file_name("PokerStars Hand #1: Tournament #2", "2") is None


def test_the_tournament_pt4_appends_to_a_winning_hand_is_taken_off_and_named_in_the_file() -> None:
    hand = _read(WINNING_V1, "utf-8").split("\n\n\n")[0].strip()
    stored = _as_pt4_stores_winning(hand, "5795043")

    assert pt4_database.restore_winning(stored, None) == (hand, "HH20160828 T5795043-G0")
    assert pt4_database.restore_winning(stored.replace("#5795043", "#5795043-17"), "1")[1] == "HH20160828 T5795043-G0"
    assert pt4_database.restore_winning(hand, "42") == (hand, "HH20160828 T42-G0")
    assert pt4_database.restore_winning(hand, None) == (hand, None)
    assert pt4_database.restore_winning("PokerStars Hand #1: Tournament #2", "2") == (
        "PokerStars Hand #1: Tournament #2",
        None,
    )


def test_an_old_winning_cash_hand_gets_a_file_name_without_a_tournament() -> None:
    hand = _read(WINNING_V1_CASH, "utf-8").strip()

    assert pt4_database.restore_winning(hand, None, tournament=False) == (hand, "HH20161002 G0")


def test_the_file_name_pt4_appends_to_a_winamax_summary_is_taken_off() -> None:
    original = _read(WINAMAX_SUMMARY, "utf-8")

    assert pt4_database.restore_summary(_as_pt4_stores_winamax_summary()) == original
    assert pt4_database.restore_summary(original) == original
    other = "PokerStars Tournament #1, No Limit Hold'em, Filename: x"
    assert pt4_database.restore_summary(other) == other


# --- writing the files -------------------------------------------------------------


def test_hands_are_written_room_by_room_and_split_into_bounded_files(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pt4_database, "HANDS_PER_FILE", 2)
    stars = _read(STARS_CASH, "utf-8")
    conn = FakeConn(cash=[(i, "PokerStars", None, stars) for i in range(1, 6)] + [(9, "GG Poker", None, "\r\n")])
    seen: list[tuple[int, int]] = []

    export = export_database(conn, tmp_path / "out", progress=lambda done, total: seen.append((done, total)))

    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == [
        "cash-PokerStars-00001.txt",
        "cash-PokerStars-00002.txt",
        "cash-PokerStars-00003.txt",
    ]
    first = (tmp_path / "out" / "cash-PokerStars-00001.txt").read_text(encoding="utf-8")
    assert first.count("PokerStars Hand #") == 2
    assert export.hands == {("cash", "PokerStars"): 5}
    assert export.marks == {"cash": 5}
    assert seen[0] == (0, 6)
    assert seen[-1] == (6, 6)
    assert set(conn.closed_cursors) == {"fpdb_cash", "fpdb_tourney", "fpdb_summaries"}


def test_marks_skip_what_an_earlier_import_brought_over(tmp_path) -> None:
    stars = _read(STARS_CASH, "utf-8")
    conn = FakeConn(cash=[(1, "PokerStars", None, stars), (2, "PokerStars", None, stars)])

    export = export_database(conn, tmp_path, {"cash": 1, "tourney": 40})

    assert export.hands == {("cash", "PokerStars"): 1}
    assert export.marks == {"cash": 2, "tourney": 40}


def test_stopping_closes_the_server_side_cursor_and_the_open_file(tmp_path) -> None:
    stars = _read(STARS_CASH, "utf-8")
    conn = FakeConn(cash=[(i, "PokerStars", None, stars) for i in range(1, 4)])
    calls = iter([False, True])

    export = export_database(conn, tmp_path, should_stop=lambda: next(calls, True))

    assert export.hands == {("cash", "PokerStars"): 1}
    assert conn.closed_cursors == ["fpdb_cash"]
    assert (tmp_path / "cash-PokerStars-00001.txt").read_text(encoding="utf-8").endswith("\n")


def test_no_more_files_are_open_at_once_than_the_bound(tmp_path, monkeypatch) -> None:
    """Old-format Winning hands get a file per tournament: thousands must not mean thousands open."""
    monkeypatch.setattr(pt4_database, "MAX_OPEN_FILES", 2)
    hand = _read(WINNING_V1, "utf-8").split("\n\n\n")[0].strip()
    tournaments = [str(1000 + n) for n in range(5)]
    rows = [(i + 1, "Yatahay Network", number, hand) for i, number in enumerate(tournaments * 2)]
    most_open = 0
    write = pt4_database._Writers.write

    def counting(self, *args):
        nonlocal most_open
        write(self, *args)
        most_open = max(most_open, sum(w.handle is not None for w in self.writers.values()))

    monkeypatch.setattr(pt4_database._Writers, "write", counting)

    export_database(FakeConn(tourney=rows), tmp_path)

    assert most_open == 2
    for number in tournaments:
        text = (tmp_path / f"tourney-Yatahay_Network HH20160828 T{number}-G0.txt").read_text(encoding="utf-8")
        assert text.split(pt4_database.HAND_SEPARATOR) == [hand, hand + "\n"]  # reopened to append, nothing lost


def test_a_failed_file_holds_its_kind_s_mark_back_to_just_before_it(tmp_path) -> None:
    stars = _read(STARS_CASH, "utf-8")
    rows = [(10, "PokerStars", None, stars), (20, "GG Poker", None, stars), (30, "PokerStars", None, stars)]
    export = export_database(FakeConn(cash=rows), tmp_path, {"cash": 5, "tourney": 7})
    gg = str(tmp_path / "cash-GG_Poker-00001.txt")

    assert export.marks_after([]) == {"cash": 30, "tourney": 7}
    assert export.marks_after([gg]) == {"cash": 19, "tourney": 7}
    assert export.marks_after([str(tmp_path / "cash-PokerStars-00001.txt"), gg]) == {"cash": 9, "tourney": 7}
    # A summary, or a file the export did not write, holds nothing back.
    assert export.marks_after([str(tmp_path / "summary-Winamax-3.txt")]) == {"cash": 30, "tourney": 7}


def test_summaries_pt4_kept_are_written_one_per_file(tmp_path) -> None:
    conn = FakeConn(summaries=[(7, "PokerStars", "PokerStars Tournament #1, No Limit Hold'em"), (8, "Winamax", "")])

    export = export_database(conn, tmp_path)

    assert export.summaries == 1
    assert [p.name for p in tmp_path.iterdir()] == ["summary-PokerStars-7.txt"]


# --- through the scan and the import, as the wizard runs them ----------------------


@pytest.fixture
def pt4():
    """A PT4 database holding a Stars cash hand, a RunItOnce tournament stored as Mac Roman,
    old-format Winning tournament hands and a Winamax summary, each as PT4 stores it."""
    winning = _read(WINNING_V1, "utf-8")
    hands = [hand for hand in winning.split("\n\n\n") if hand.strip()]
    return FakeConn(
        cash=[
            (1, "PokerStars", None, _read(STARS_CASH, "utf-8")),
            (2, "Yatahay Network", None, _read(WINNING_V1_CASH, "utf-8")),
        ],
        tourney=[(10, "RunItOnce", "145677", RIO_TOURNEY.read_bytes().decode("mac_roman"))]
        + [
            # PT4 appends the tournament to the first line, and does not always link the hand to it.
            (20 + n, "Yatahay Network", None if n % 2 else "5795043", _as_pt4_stores_winning(hand, "5795043"))
            for n, hand in enumerate(hands)
        ],
        summaries=[(30, "Winamax", _as_pt4_stores_winamax_summary())],
    )


def test_what_the_database_holds_is_scanned_as_a_folder_would_be(pt4, legacy_config, tmp_path) -> None:
    export = export_database(pt4, tmp_path / "pt4")

    scan = scan_folder(legacy_config, export.folder)

    assert export.repaired == 1
    assert not scan.unsupported
    # The dollar cash hand and the euro tournament land where their files would: .COM and .EU.
    assert {room: len(files) for room, files in scan.rooms.items()} == {
        "PokerStars.COM": 1,
        "PokerStars.EU": 1,
        "Winamax": 1,
        "Ya Poker": 2,  # the cash hand's day and the tournament each name a file
    }
    names = [Path(path).name for files in scan.rooms.values() for path in files]
    assert "tourney-Yatahay_Network HH20160828 T5795043-G0.txt" in names
    assert "cash-Yatahay_Network HH20161002 G0.txt" in names


def test_every_hand_the_database_holds_is_imported(pt4, legacy_config, fresh_db, tmp_path) -> None:
    export = export_database(pt4, tmp_path / "pt4")
    scan = scan_folder(legacy_config, export.folder)
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=legacy_config, sql=None)
    importer.database = fresh_db
    importer.setCallHud(False)
    for files in scan.rooms.values():
        for path in files:
            importer.addBulkImportImportFileOrDir(path)

    importer.runImport()

    results = list(importer.file_results.values())
    assert sum(r.stored for r in results) == export.hand_count
    assert sum(r.partial + r.errors for r in results) == 0
    assert sum(getattr(r, "summaries", 0) for r in results) == 1
    cursor = fresh_db.get_cursor()
    cursor.execute("SELECT siteTourneyNo FROM Tourneys")
    assert sorted(str(row[0]) for row in cursor.fetchall()) == ["1096056742", "145677", "5795043"]


# --- what was already imported ----------------------------------------------------


def test_marks_are_kept_per_database_next_to_the_configuration(tmp_path) -> None:
    config = type("Config", (), {"file": str(tmp_path / "HUD_config.xml")})()
    here, there = Pt4Database(), Pt4Database(host="other", database="PT4 Old")

    pt4_database.save_marks(config, here, {"cash": 12, "tourney": 3})
    pt4_database.save_marks(config, there, {"cash": 5})

    assert pt4_database.load_marks(config, here) == {"cash": 12, "tourney": 3}
    assert pt4_database.load_marks(config, there) == {"cash": 5}
    stored = json.loads((tmp_path / pt4_database.MARKS_FILE).read_text(encoding="utf-8"))
    assert set(stored) == {"postgres@localhost:5432/PT4 DB", "postgres@other:5432/PT4 Old"}
    assert "password" not in json.dumps(stored)


def test_unreadable_marks_mean_starting_from_the_first_hand(tmp_path) -> None:
    config = type("Config", (), {"file": str(tmp_path / "HUD_config.xml")})()
    (tmp_path / pt4_database.MARKS_FILE).write_text("{not json", encoding="utf-8")

    assert pt4_database.load_marks(config, Pt4Database()) == {}
    assert pt4_database.load_marks(object(), Pt4Database()) == {}
