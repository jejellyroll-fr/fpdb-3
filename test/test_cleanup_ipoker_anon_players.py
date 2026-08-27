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
    placeholders, hands, kept = survey(_db(_Cursor()))

    assert [p[0] for p in placeholders] == [655, 656, 658]  # 659 is a real name
    assert list(hands) == [1114]  # 2000 seats a real player, so it stays
    assert kept == [(658, "anon_5879604460_9", 2000)]


def test_a_real_player_named_like_a_placeholder_is_never_deleted() -> None:
    """"anon_hunter" passes the LIKE pre-filter and is somebody's screen name.

    Deleting them would take every hand they played with them, which is why the
    generated form is matched in full rather than by its prefix.
    """
    placeholders, hands, _kept = survey(_db(_Cursor()))

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
