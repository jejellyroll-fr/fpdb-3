from __future__ import annotations

from fpdb_3_legacy.iPoker.base import iPoker


class Bet365FrIPoker(iPoker):
    """bet365.fr, the French skin of bet365 on the iPoker network.

    It writes the same XML hand histories as every iPoker skin; only the room
    the hands are filed under differs from the international "Bet365 Poker".
    """

    sitename = "Bet365.fr Poker"
    site_id = 132
