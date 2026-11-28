from __future__ import annotations

from fpdb_3_legacy.iPoker.base import iPoker


class ChampionPokerIPoker(iPoker):
    """ChampionPoker, a crypto-oriented room on the iPoker network (#926).

    It writes the same XML hand histories as every iPoker skin (checked on a
    real cash session from client 26.7.1.32); only the room the hands are
    filed under differs.
    """

    sitename = "ChampionPoker"
    site_id = 152
