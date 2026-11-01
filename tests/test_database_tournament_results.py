"""Database-side contract for tournament results announced after the last hand."""

from __future__ import annotations

from types import SimpleNamespace

from fpdb_3_legacy.database_tournaments import DatabaseTournamentsMixin


class _Cursor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []

    def execute(self, query: str, values: tuple) -> None:
        self.calls.append((query, values))


class _TournamentResultsDatabase(DatabaseTournamentsMixin):
    def __init__(self, row) -> None:
        self.row = row
        self.cursor = _Cursor()
        self.sql = SimpleNamespace(
            query={
                "placeholder": "?",
                "updateTourneysPlayerResults": "UPDATE TourneysPlayers SET rank=%s WHERE id=%s",
            },
        )

    def getTourneyPlayerInfo(self, site_name, tourney_no, player_name):
        return ["id"], self.row

    def get_cursor(self):
        return self.cursor


def test_an_announced_place_reaches_the_tournament_player_row() -> None:
    database = _TournamentResultsDatabase((42,))

    updated = database.updateTourneyPlayerResult(
        "CoinPoker",
        "81499",
        "hero",
        1,
        winnings=56550,
        winnings_currency="EUR",
    )

    assert updated is True
    assert database.cursor.calls == [
        ("UPDATE TourneysPlayers SET rank=? WHERE id=?", (1, 56550, "EUR", 42)),
    ]


def test_an_unknown_tournament_player_is_not_reported_as_written() -> None:
    database = _TournamentResultsDatabase(None)

    assert database.updateTourneyPlayerResult("CoinPoker", "81499", "stranger", 20) is False
    assert database.cursor.calls == []
