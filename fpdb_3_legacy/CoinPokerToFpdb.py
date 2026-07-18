#!/usr/bin/env python
"""Minimal CoinPoker converter — live-capture only, for HUD table detection.

CoinPoker ships no text hand histories; its hands come from the live
packet-capture pipeline (coinpoker_live_capture). This class exists so the HUD
can build a window-title search for CoinPoker tables via ``getTableTitleRe``
(HUD_main -> TableWindow -> getSiteHhc). It never claims a text file for import:
``re_identify`` matches nothing.
"""

from __future__ import annotations

import re

from fpdb_3_legacy.HandHistoryConverter import HandHistoryConverter


class CoinPoker(HandHistoryConverter):
    """CoinPoker (site id 140). Table-detection support only; no file import."""

    sitename = "CoinPoker"
    siteId = 140
    filetype = "text"
    codepage = ("utf8", "cp1252")
    # Never identify a text file as CoinPoker (hands arrive via live capture).
    re_identify = re.compile(r"$^")

    @staticmethod
    def getTableTitleRe(
        type=None,
        table_name=None,
        tournament=None,
        table_number=None,
        tourney_name=None,
    ) -> str:
        """Return a search string for CoinPoker table windows.

        CoinPoker's window title contains the numeric table id (e.g.
        "PLO4 921140 - ..."), so the DB table name (the table id) is used. When
        macOS hides the title (no Screen Recording permission) the macOS
        detector falls back to matching the CoinPoker process for any non-empty
        search string, which this still provides.
        """
        return re.escape(str(table_name or tournament or "CoinPoker"))

    @staticmethod
    def getTableNoRe(tournament=None) -> str:
        return r"\b(\d+)\b"
