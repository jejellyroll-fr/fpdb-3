"""Player metadata, database count, and dump utility queries."""

from __future__ import annotations


def utility_queries() -> dict[str, str]:
    """Return small player, count, and full-table dump queries."""
    query = {
        "get_player_comment": "\n            SELECT comment FROM Players WHERE id=%s\n        ",
        "update_player_comment": "\n            UPDATE Players SET comment=%s, commentTs=CURRENT_TIMESTAMP WHERE id=%s\n        ",
        "get_player_name": "SELECT name FROM Players WHERE id=%s",
        "getHandCount": "SELECT COUNT(*) FROM Hands",
        "getTourneyCount": "SELECT COUNT(*) FROM Tourneys",
        "getTourneyTypeCount": "SELECT COUNT(*) FROM TourneyTypes",
    }
    for table in (
        "Autorates",
        "Backings",
        "Gametypes",
        "Hands",
        "HandsActions",
        "HandsPlayers",
        "HudCache",
        "Players",
        "RawHands",
        "RawTourneys",
        "Settings",
        "Sites",
        "TourneyTypes",
        "Tourneys",
        "TourneysPlayers",
    ):
        query["get" + table] = "SELECT * FROM " + table
    return query
