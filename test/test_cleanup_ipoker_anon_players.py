"""Tests for the placeholder-player cleanup tool.

The tool deletes hands and players, so the rule that decides what it may touch
is the part worth pinning down: a placeholder that shares a hand with a real
player must survive, and so must that hand.
"""

from __future__ import annotations

from types import SimpleNamespace

from tools.cleanup_ipoker_anon_players import (
    DELETE_BY_HAND,
    DELETE_BY_PLAYER,
    SELECT_HAND,
    SELECT_HANDS_OF_PLAYER,
    SELECT_PLACEHOLDERS,
    SELECT_PLAYERS_OF_HAND,
    SELECT_REMAINING_HANDS_OF_PLAYER,
    delete,
    survey,
)

# What the LIKE pre-filter returns: "anon_hunter" matches it and is a real
# player, which is why the tool tests the name in full before deleting anybody.
PLACEHOLDERS = [
    (655, "anon_5879604460_1", "Bwin.fr Poker"),
    (656, "anon_5879604460_5", "Bwin.fr Poker"),
    (658, "anon_5879604460_9", "Bwin.fr Poker"),
    (659, "anon_hunter", "Bwin.fr Poker"),
]
HANDS_OF_PLAYER = {655: [1114], 656: [1114], 658: [2000]}
PLAYERS_OF_HAND = {
    1114: [(655, "anon_5879604460_1"), (656, "anon_5879604460_5")],
    2000: [(658, "anon_5879604460_9"), (659, "anon_hunter")],
}
IPOKER_SITES = {"Bwin.fr Poker"}
HAND_ROWS = {
    1114: (1114, "Sea Lake, 560237915", "2026-08-27 21:12:11"),
    2000: (2000, "Scone, 560235983", "2026-08-27 21:30:00"),
}


class _Cursor:
    """Answers the tool's queries from the dicts above and records writes."""

    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple]] = []
        self._result: list = []
        self.rowcount = 1

    def execute(self, statement: str, params: tuple = ()) -> None:
        self.executed.append((statement, params))
        if statement == SELECT_PLACEHOLDERS:
            self._result = list(PLACEHOLDERS)
        elif statement == SELECT_HANDS_OF_PLAYER:
            self._result = [(hand,) for hand in HANDS_OF_PLAYER.get(params[0], [])]
        elif statement == SELECT_PLAYERS_OF_HAND:
            self._result = list(PLAYERS_OF_HAND.get(params[0], []))
        elif statement == SELECT_HAND:
            self._result = [HAND_ROWS[params[0]]]
        elif statement == SELECT_REMAINING_HANDS_OF_PLAYER:
            self._result = [(0,)]
        else:
            self._result = []

    def fetchall(self) -> list:
        return self._result

    def fetchone(self):
        return self._result[0] if self._result else None


def _db(cursor: _Cursor) -> SimpleNamespace:
    return SimpleNamespace(
        sql=SimpleNamespace(query={"placeholder": "%s"}),
        get_cursor=lambda: cursor,
        connection=SimpleNamespace(commit=lambda: None, rollback=lambda: None),
    )


def test_only_hands_made_entirely_of_placeholders_are_offered() -> None:
    placeholders, hands, kept = survey(_db(_Cursor()), IPOKER_SITES)

    assert [p[0] for p in placeholders] == [655, 656, 658]  # 659 is a real name
    assert list(hands) == [1114]  # 2000 seats a real player, so it stays
    assert kept == [(658, "anon_5879604460_9", 2000)]


def test_a_real_player_named_like_a_placeholder_is_never_deleted() -> None:
    """"anon_hunter" passes the LIKE pre-filter and is somebody's screen name.

    Deleting them would take every hand they played with them, which is why the
    generated form is matched in full rather than by its prefix.
    """
    placeholders, hands, _kept = survey(_db(_Cursor()), IPOKER_SITES)

    assert 659 not in [p[0] for p in placeholders]
    assert 2000 not in hands  # the hand they sit in is not offered either


def test_a_hand_is_emptied_before_it_is_removed() -> None:
    """Children first: deleting Hands before its rows would trip a foreign key."""
    cursor = _Cursor()

    delete(_db(cursor), [1114], [655], commit=False)

    order = [statement for statement, _params in cursor.executed]
    assert order.index("DELETE FROM HandsPlayers WHERE handId = %s") < order.index("DELETE FROM Hands WHERE id = %s")
    assert order.index("DELETE FROM Hands WHERE id = %s") < order.index("DELETE FROM Players WHERE id = %s")


def test_the_caches_a_placeholder_left_behind_are_removed_too() -> None:
    """A HudCache row is what a statistic would otherwise still be read out of."""
    cursor = _Cursor()

    delete(_db(cursor), [], [655], commit=False)

    executed = {statement for statement, _params in cursor.executed}
    for _table, statement in DELETE_BY_PLAYER:
        assert statement in executed


def test_every_table_hanging_off_a_hand_is_cleared() -> None:
    cursor = _Cursor()

    delete(_db(cursor), [1114], [], commit=False)

    executed = {statement for statement, _params in cursor.executed}
    for _table, statement in DELETE_BY_HAND:
        assert statement in executed


def test_every_table_named_matches_the_schema_casing() -> None:
    """MySQL with case-sensitive table names fails mid-transaction on a typo.

    PostgreSQL folds an unquoted name either way, so a wrong casing survives
    every rehearsal on it and only breaks on somebody else's backend, after the
    earlier deletions have already run.
    """
    import re
    from pathlib import Path

    repo = Path(__file__).resolve().parent.parent
    ddl = {"RawHands"}  # built by _raw_table_ddl(db_server, "RawHands", ...)
    for schema in list(repo.glob("fpdb_3_legacy/sql_schema_*.py")) + list(repo.glob("fpdb_3_legacy/sql_queries_*.py")):
        ddl |= set(re.findall(r"CREATE TABLE (?:IF NOT EXISTS )?([A-Za-z_]+)", schema.read_text(encoding="utf-8")))

    source = (repo / "tools" / "cleanup_ipoker_anon_players.py").read_text(encoding="utf-8")
    named = set(re.findall(r"DELETE FROM ([A-Za-z_]+)", source))
    named |= set(re.findall(r"FROM ([A-Za-z_]+) ", source)) | set(re.findall(r"JOIN ([A-Za-z_]+) ", source))

    assert named, "no table names found; the extraction above stopped matching"
    assert named <= ddl, f"not in the schema with this casing: {sorted(named - ddl)}"


def _schema_foreign_keys() -> list[tuple[str, str]]:
    """(child, parent) for every foreign key the schema declares."""
    import re
    from pathlib import Path

    repo = Path(__file__).resolve().parent.parent
    keys: list[tuple[str, str]] = []
    for schema in repo.glob("fpdb_3_legacy/sql_schema_*.py"):
        text = schema.read_text(encoding="utf-8")
        for table in re.finditer(r"CREATE TABLE (\w+)(.*?)(?=CREATE TABLE |\Z)", text, re.S):
            for fk in re.finditer(r"FOREIGN KEY \(\w+\) REFERENCES (\w+)\(", table.group(2)):
                keys.append((table.group(1), fk.group(1)))
    return keys


def test_nothing_is_deleted_before_what_points_at_it() -> None:
    """No foreign key in this schema cascades, so order is the whole safety.

    Checked against the DDL rather than against the list, because the list is
    what gets it wrong: AofDecisionAnalyses points at AofDecisions and Backings
    at TourneysPlayers, and both were deleted the wrong way round -- which
    PostgreSQL only reveals when such a row actually exists, mid-transaction,
    after the hands are already gone.

    Each pass is checked on its own. The hand pass runs first and in full, so a
    table it clears (PlayerAutoNotes) may legitimately be deleted again in the
    player pass, for rows pointing at hands that are staying.
    """
    keys = _schema_foreign_keys()

    for pass_name, statements in (("hand", DELETE_BY_HAND), ("player", DELETE_BY_PLAYER)):
        order = [table for table, _sql in statements]
        first = {table: min(i for i, t in enumerate(order) if t == table) for table in order}
        last = {table: max(i for i, t in enumerate(order) if t == table) for table in order}
        for child, parent in keys:
            if parent not in first or child not in first:
                continue
            assert last[child] < first[parent], (
                f"{pass_name} pass: {child} still references {parent} when {parent} is deleted"
            )


def test_the_foreign_keys_are_actually_read() -> None:
    """A silent extraction failure would make the order test vacuous."""
    keys = _schema_foreign_keys()

    assert ("AofDecisionAnalyses", "AofDecisions") in keys
    assert ("Backings", "TourneysPlayers") in keys


def test_nothing_points_at_a_deleted_table_from_outside_the_script() -> None:
    """Ordering is only half of it: a child table left out entirely still fails.

    That is how AofDecisionAnalyses slipped through -- it references
    AofDecisions, which the hand pass deletes, and it was in no pass at all, so
    an order check had nothing to compare.

    A child cleared by an earlier pass counts: the hand pass removes the rows of
    the hands being deleted, and `delete()` refuses a player still seated in any
    hand, so no row of theirs survives in a hand that stays.
    """
    passes = [[table for table, _sql in DELETE_BY_HAND], [table for table, _sql in DELETE_BY_PLAYER]]
    keys = _schema_foreign_keys()

    for index, tables in enumerate(passes):
        cleared = {table for earlier in passes[: index + 1] for table in earlier}
        for child, parent in keys:
            if parent not in tables:
                continue
            assert child in cleared, f"{child} references {parent} but is never deleted"


def test_a_matching_name_on_another_site_is_left_alone() -> None:
    """Only the iPoker converter ever wrote these names.

    A player on any other site whose screen name happens to read like one is
    somebody real, and this tool deletes players.
    """
    placeholders, hands, _kept = survey(_db(_Cursor()), {"PokerStars"})

    assert placeholders == []
    assert hands == {}


def test_apply_and_rehearse_cannot_be_asked_for_together() -> None:
    """--rehearse promises a rollback; combined with --apply it used to commit."""
    import subprocess
    import sys
    from pathlib import Path

    tool = Path(__file__).resolve().parent.parent / "tools" / "cleanup_ipoker_anon_players.py"
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(tool), "--apply", "--rehearse"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "not allowed with argument" in result.stderr
