from __future__ import annotations

from fpdb_3_legacy.iPoker.base import iPoker


class Win2dayIPoker(iPoker):
    """win2day (Austria), on the iPoker network since its move to Playtech (#891).

    It writes the same XML hand histories as every iPoker skin; only the room
    the hands are filed under differs. win2day's first client (Boss Media,
    2008) wrote another format: its files keep going through the Boss
    converter, filed under "Boss", and never reach this parser.
    """

    sitename = "Win2day Poker"
    site_id = 151
