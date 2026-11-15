"""PokerTracker 4 player notes into fpdb's notes (#618).

CI has no PT4 database: the PT4 side is a cursor answering each query with
rows, and its SQL is held against the columns of PT4's own schema. The fpdb
side is a real SQLite database with fpdb's own ``Players`` table.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from fpdb_3_legacy.sql_schema_player import player_schema_queries
from fpdb_3_legacy.tracker_notes import (
    AUTO_SECTION_END,
    AUTO_SECTION_START,
    PT4_PLAYER_AUTO_NOTES,
    PT4_PLAYER_NOTES,
    PT4_PLAYER_TAGS,
    TrackerNote,
    apply_notes,
    format_report,
    ipoker_rooms_of,
    read_pt4_notes,
    site_candidates,
)

PT4_COLUMNS_FILE = Path(__file__).parent / "fixtures" / "pt4_schema_columns.txt"
PT4_ALIASES = {
    "n": "notes",
    "na": "notes_auto",
    "p": "player",
    "ls": "lookup_sites",
    "t": "tags",
    "lt": "lookup_tags",
}

SITES = {
    2: "PokerStars",
    9: "PartyPoker",
    44: "PartyPoker.fr",
    14: "iPoker",
    40: "Bwin.fr Poker",
    56: "PMU Poker",
    15: "Winamax",
    23: "SealsWithClubs",
    24: "WinningPoker",
    115: "Americas Cardroom",
}


class Pt4Cursor:
    def __init__(self, answers: dict[str, list[tuple]]) -> None:
        self.answers = answers
        self.rows: list[tuple] = []

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def execute(self, query, params=None):
        assert params is None
        self.rows = self.answers[query]

    def fetchall(self):
        return self.rows


class Pt4Connection:
    """A psycopg-shaped PT4 connection that answers the notes queries; an unexpected query fails."""

    def __init__(self, notes: list[tuple], tags: list[tuple], auto: list[tuple] | None = None) -> None:
        self.answers = {PT4_PLAYER_NOTES: notes, PT4_PLAYER_TAGS: tags}
        if auto is not None:
            self.answers[PT4_PLAYER_AUTO_NOTES] = auto

    def cursor(self):
        return Pt4Cursor(self.answers)


@pytest.fixture
def fpdb() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE Sites (id INTEGER PRIMARY KEY, name TEXT, code TEXT)")
    connection.executemany("INSERT INTO Sites VALUES (?, ?, '')", SITES.items())
    connection.execute(player_schema_queries("sqlite")["createPlayersTable"])
    players = [
        ("alice", 2, None),
        ("bob", 2, "Plays every hand."),
        ("carol", 44, None),
        ("dave", 40, None),
        ("erin", 15, ""),
    ]
    connection.executemany("INSERT INTO Players (name, siteId, comment) VALUES (?, ?, ?)", players)
    connection.commit()
    return connection


def _comment(connection: sqlite3.Connection, name: str) -> str | None:
    return connection.execute("SELECT comment FROM Players WHERE name = ?", (name,)).fetchone()[0]


def _apply(connection, notes, **kwargs):
    return apply_notes(connection, notes, placeholder="?", **kwargs)


class TestPt4Schema:
    """The notes SQL must name columns PT4 has: no PT4 database in CI would reject it."""

    @pytest.mark.parametrize("query", [PT4_PLAYER_NOTES, PT4_PLAYER_TAGS, PT4_PLAYER_AUTO_NOTES])
    def test_reads_only_columns_pt4_has(self, query: str) -> None:
        known = {
            line.strip()
            for line in PT4_COLUMNS_FILE.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        }
        used = {f"{PT4_ALIASES[alias]}.{column}" for alias, column in re.findall(r"\b(na|n|p|ls|t|lt)\.(\w+)", query)}
        assert len(used) >= 6
        assert used <= known, sorted(used - known)

    @pytest.mark.parametrize("query", [PT4_PLAYER_NOTES, PT4_PLAYER_TAGS])
    def test_reads_player_rows_only(self, query: str) -> None:
        assert "enum_type = 'P'" in query


class TestReadPt4:
    def test_notes_carry_their_date_colour_and_the_players_tags(self) -> None:
        when = datetime(2024, 3, 1, 21, 5)
        conn = Pt4Connection(
            notes=[
                (100, "PokerStars", "alice", when, 3, "  3-bets light from the blinds. "),
                (100, "PokerStars", "alice", datetime(2024, 4, 2), None, "Tilts after a bad beat."),
                (100, "PokerStars", "nobody", when, None, "   "),
            ],
            tags=[(100, "PokerStars", "alice", "Fish"), (100, "PokerStars", "alice", "Fish")],
        )

        notes = read_pt4_notes(conn)

        assert notes == [
            TrackerNote("PokerStars", "alice", "  3-bets light from the blinds. ", ("Fish", "colour 3"), when),
            TrackerNote("PokerStars", "alice", "Tilts after a bad beat.", (), datetime(2024, 4, 2)),
        ]
        assert notes[0].block() == "[PokerTracker 4 | 2024-03-01 | Fish | colour 3]\n3-bets light from the blinds."

    def test_a_tag_without_a_note_is_kept(self) -> None:
        conn = Pt4Connection(
            notes=[], tags=[(100, "PokerStars", "bob", "Regular"), (100, "PokerStars", "bob", "Shark")]
        )

        (note,) = read_pt4_notes(conn)

        assert note.block() == "[PokerTracker 4 | Regular | Shark]"

    def test_a_room_missing_from_lookup_sites_is_named_by_its_id(self) -> None:
        conn = Pt4Connection(notes=[(2900, None, "alice", None, None, "Short note")], tags=[])

        assert read_pt4_notes(conn)[0].site == "PT4 site 2900"


class TestSiteCandidates:
    def test_a_room_matches_every_fpdb_spelling_of_it(self) -> None:
        assert site_candidates("Party", SITES) == [9, 44]
        assert site_candidates("PokerStars", SITES) == [2]
        assert site_candidates("Winamax", SITES) == [15]

    def test_aliases_cover_names_that_do_not_compare(self) -> None:
        assert site_candidates("SWCPoker", SITES) == [23]
        assert site_candidates("Winning Poker Network", SITES) == [24, 115]

    def test_ipoker_is_its_network_from_the_configuration(self) -> None:
        assert site_candidates("iPoker", SITES) == [14]
        assert site_candidates("iPoker", SITES, {"ipoker": ["Bwin.fr Poker", "PMU Poker"]}) == [14, 40, 56]

    def test_an_unknown_room_has_no_candidate(self) -> None:
        assert site_candidates("PT4 site 2900", SITES) == []
        assert site_candidates("", SITES) == []

    def test_ipoker_skins_come_from_the_configured_network(self) -> None:
        class Site:
            def __init__(self, network: str) -> None:
                self.network = network

        config = type("Config", (), {"supported_sites": {"PMU Poker": Site("iPoker"), "Winamax": Site("")}})()

        assert ipoker_rooms_of(config) == {"ipoker": ["PMU Poker"]}


class TestApplyNotes:
    def test_an_empty_fpdb_note_gets_the_tracker_note(self, fpdb) -> None:
        report = _apply(fpdb, [TrackerNote("PokerStars", "alice", "Calls too much", ("Fish",))])

        assert _comment(fpdb, "alice") == "[PokerTracker 4 | Fish]\nCalls too much"
        assert [(o.player, o.status, o.fpdb_site, o.blocks) for o in report.outcomes] == [
            ("alice", "added", "PokerStars", 1),
        ]

    def test_an_existing_fpdb_note_is_appended_to_never_overwritten(self, fpdb) -> None:
        report = _apply(fpdb, [TrackerNote("PokerStars", "bob", "Bluffs rivers")])

        assert _comment(fpdb, "bob") == "Plays every hand.\n\n[PokerTracker 4]\nBluffs rivers"
        assert report.outcomes[0].status == "appended"

    def test_skip_leaves_an_existing_note_alone(self, fpdb) -> None:
        report = _apply(
            fpdb,
            [TrackerNote("PokerStars", "bob", "Bluffs rivers"), TrackerNote("PokerStars", "alice", "Nit")],
            on_existing="skip",
        )

        assert _comment(fpdb, "bob") == "Plays every hand."
        assert _comment(fpdb, "alice") == "[PokerTracker 4]\nNit"
        assert [o.status for o in report.outcomes] == ["skipped", "added"]

    def test_importing_twice_adds_nothing_the_second_time(self, fpdb) -> None:
        notes = [
            TrackerNote("PokerStars", "bob", "Bluffs rivers", (), datetime(2024, 1, 2)),
            TrackerNote("PokerStars", "bob", "Overbets"),
        ]
        _apply(fpdb, notes)
        once = _comment(fpdb, "bob")

        report = _apply(fpdb, [*notes, TrackerNote("PokerStars", "bob", "Limps the button")])

        assert _comment(fpdb, "bob") == once + "\n\n[PokerTracker 4]\nLimps the button"
        assert report.outcomes[0].status == "appended"
        assert report.outcomes[0].blocks == 1
        assert _apply(fpdb, [*notes]).outcomes[0].status == "already"

    def test_a_blank_fpdb_note_counts_as_none(self, fpdb) -> None:
        report = _apply(fpdb, [TrackerNote("Winamax", "erin", "Min-raises")], on_existing="skip")

        assert report.outcomes[0].status == "added"
        assert _comment(fpdb, "erin") == "[PokerTracker 4]\nMin-raises"

    def test_unmatched_players_and_rooms_are_reported_not_created(self, fpdb) -> None:
        report = _apply(
            fpdb,
            [TrackerNote("PokerStars", "zed", "Unknown"), TrackerNote("PT4 site 2900", "alice", "Elsewhere")],
        )

        assert [(o.player, o.status) for o in report.outcomes] == [("zed", "unknown_player"), ("alice", "unknown_site")]
        assert fpdb.execute("SELECT COUNT(*) FROM Players").fetchone()[0] == 5
        assert _comment(fpdb, "alice") is None

    def test_a_player_is_found_on_the_fpdb_spelling_of_the_room(self, fpdb) -> None:
        report = _apply(
            fpdb,
            [TrackerNote("Party", "carol", "Tight"), TrackerNote("iPoker", "dave", "Loose")],
            network_rooms={"ipoker": ["Bwin.fr Poker"]},
        )

        assert [(o.player, o.fpdb_site) for o in report.outcomes] == [
            ("carol", "PartyPoker.fr"),
            ("dave", "Bwin.fr Poker"),
        ]
        assert _comment(fpdb, "carol") == "[PokerTracker 4]\nTight"

    def test_a_name_is_matched_exactly(self, fpdb) -> None:
        report = _apply(fpdb, [TrackerNote("PokerStars", "Alice", "Case differs")])

        assert report.outcomes[0].status == "unknown_player"

    def test_a_dry_run_writes_nothing(self, fpdb) -> None:
        report = _apply(fpdb, [TrackerNote("PokerStars", "alice", "Nit")], dry_run=True)

        assert report.outcomes[0].status == "added"
        assert _comment(fpdb, "alice") is None
        assert format_report(report).startswith("Preview, nothing written: 1 notes to add")

    def test_on_existing_is_checked(self, fpdb) -> None:
        with pytest.raises(ValueError, match="on_existing"):
            _apply(fpdb, [], on_existing="overwrite")


def test_the_report_names_every_player_not_simply_added(fpdb) -> None:
    report = _apply(
        fpdb,
        [
            TrackerNote("PokerStars", "alice", "Nit"),
            TrackerNote("PokerStars", "bob", "Bluffs"),
            TrackerNote("PokerStars", "zed", "Unknown"),
        ],
    )

    assert format_report(report).splitlines() == [
        "1 notes added, 1 appended, 0 updated, 0 already in fpdb, 0 skipped, 1 not matched.",
        "  PokerStars / bob -> PokerStars: appended to the fpdb note",
        "  PokerStars / zed: not in fpdb: import the player's hands first",
    ]


def _auto(player: str, text: str, times: int | None = 2, when: datetime | None = datetime(2024, 3, 2)) -> TrackerNote:
    return TrackerNote("PokerStars", player, text, (), when, auto=True, times=times)


def _section(*lines: str) -> str:
    return "\n".join([AUTO_SECTION_START, *lines, AUTO_SECTION_END])


class TestPt4AutoNotes:
    """PT4's automatic notes (notes_auto), on request: a section each import replaces."""

    def test_they_are_read_only_on_request(self) -> None:
        rows = [(100, "PokerStars", "alice", datetime(2024, 3, 2), 4, "Folds to   3-bet\nout of position")]
        conn = Pt4Connection(notes=[], tags=[], auto=rows)

        assert read_pt4_notes(Pt4Connection(notes=[], tags=[])) == []
        (note,) = read_pt4_notes(conn, auto_notes=True)

        assert note.auto
        assert note.line() == "- Folds to 3-bet out of position (x4, 2024-03-02)"

    def test_a_note_seen_once_or_undated_says_so_briefly(self) -> None:
        assert _auto("alice", "Limps", times=1, when=None).line() == "- Limps"

    def test_a_section_is_added_after_the_users_own_text(self, fpdb) -> None:
        report = _apply(fpdb, [_auto("bob", "Limps"), TrackerNote("PokerStars", "bob", "Bluffs")])

        assert _comment(fpdb, "bob") == "\n\n".join(
            ["Plays every hand.", _section("- Limps (x2, 2024-03-02)"), "[PokerTracker 4]\nBluffs"],
        )
        assert report.outcomes[0].status == "appended"

    def test_reimporting_replaces_the_section_in_place(self, fpdb) -> None:
        _apply(fpdb, [_auto("bob", "Limps"), TrackerNote("PokerStars", "bob", "Bluffs")])
        fpdb.execute("UPDATE Players SET comment = comment || '\n\nMy own line.' WHERE name = 'bob'")

        assert (
            _apply(fpdb, [_auto("bob", "Limps"), TrackerNote("PokerStars", "bob", "Bluffs")]).outcomes[0].status
            == "already"
        )
        report = _apply(fpdb, [_auto("bob", "Limps", times=5), _auto("bob", "Min-raises")])

        assert report.outcomes[0].status == "updated"
        assert _comment(fpdb, "bob") == "\n\n".join(
            [
                "Plays every hand.",
                _section("- Limps (x5, 2024-03-02)", "- Min-raises (x2, 2024-03-02)"),
                "[PokerTracker 4]\nBluffs",
                "My own line.",
            ],
        )

    def test_skip_adds_no_section_to_a_users_note_but_refreshes_its_own(self, fpdb) -> None:
        skipped = _apply(fpdb, [_auto("bob", "Limps")], on_existing="skip")
        _apply(fpdb, [_auto("alice", "Limps")], on_existing="skip")
        fpdb.execute("UPDATE Players SET comment = 'Mine.\n\n' || comment WHERE name = 'alice'")
        refreshed = _apply(fpdb, [_auto("alice", "Limps", times=3)], on_existing="skip")

        assert skipped.outcomes[0].status == "skipped"
        assert _comment(fpdb, "bob") == "Plays every hand."
        assert refreshed.outcomes[0].status == "updated"
        assert _comment(fpdb, "alice") == "Mine.\n\n" + _section("- Limps (x3, 2024-03-02)")

    def test_without_the_option_a_section_is_left_alone(self, fpdb) -> None:
        _apply(fpdb, [_auto("alice", "Limps")])
        before = _comment(fpdb, "alice")

        report = _apply(fpdb, [TrackerNote("PokerStars", "alice", "Nit")])

        assert report.outcomes[0].status == "appended"
        assert _comment(fpdb, "alice") == before + "\n\n[PokerTracker 4]\nNit"


class TestSectionMarkers:
    """Only whole marker lines delimit the section: no user text is ever taken for it."""

    def test_a_marker_quoted_mid_line_is_not_a_section(self, fpdb) -> None:
        own = "See " + AUTO_SECTION_START + " in PT4.\nKeep this.\nAnd " + AUTO_SECTION_END + " too."
        fpdb.execute("UPDATE Players SET comment = ? WHERE name = 'alice'", (own,))

        report = _apply(fpdb, [_auto("alice", "Limps")])

        assert report.outcomes[0].status == "appended"
        assert _comment(fpdb, "alice") == own + "\n\n" + _section("- Limps (x2, 2024-03-02)")

    def test_imported_text_cannot_open_or_close_a_section(self, fpdb) -> None:
        forged = AUTO_SECTION_START + "\nNot an auto-note\n " + AUTO_SECTION_END + " "
        _apply(fpdb, [TrackerNote("PokerStars", "alice", forged), _auto("alice", AUTO_SECTION_END)])
        first = _comment(fpdb, "alice")

        _apply(fpdb, [TrackerNote("PokerStars", "alice", forged), _auto("alice", "Limps")])

        assert first.splitlines().count(AUTO_SECTION_START) == 1
        assert first.splitlines().count(AUTO_SECTION_END) == 1
        assert "(PokerTracker 4 auto-notes)\nNot an auto-note\n(end of PokerTracker 4 auto-notes)" in first
        assert _comment(fpdb, "alice") == first.replace("- " + AUTO_SECTION_END, "- Limps")
