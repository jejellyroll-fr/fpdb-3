"""
Parser for Winamax window titles.

This module extracts information from Winamax client window titles
to enable association with hand histories.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class WinamaxTableType(Enum):
    """Winamax table types."""

    CASH_GAME = "cash"
    GO_FAST = "go_fast"
    TOURNAMENT = "tournament"
    EXPRESSO = "expresso"
    SIT_AND_GO = "sng"
    UNKNOWN = "unknown"


@dataclass
class WinamaxWindowInfo:
    """Information extracted from a Winamax window title."""

    table_name: str
    table_type: WinamaxTableType
    blinds: str | None = None
    currency: str | None = None
    tournament_name: str | None = None
    table_number: int | None = None
    buyin: str | None = None
    is_fast_fold: bool = False
    raw_title: str = ""

    @property
    def display_name(self) -> str:
        """Display name for the HUD."""
        if self.table_type == WinamaxTableType.TOURNAMENT and self.table_number:
            return f"{self.tournament_name} - Table {self.table_number}"
        return self.table_name


class WinamaxTitleParser:
    """
    Parse Winamax window titles to extract table information.

    Supported formats:
    - Cash Game: "Winamax Poker - CashGame - TableName - 0.01€/0.02€ - EUR"
    - Go Fast: "Winamax Poker - Go Fast "PoolName" - 0.05€/0.10€"
    - Tournament: "Winamax Poker - Tournament "Name" - Table 5"
    - Expresso: "Winamax Poker - Expresso 5€ - 123456789"
    - HOLD-UP: "Winamax Poker - HOLD-UP "PoolName" - 0.05€/0.10€"
    """

    # Patterns for different table types
    PATTERNS = {
        # Cash Game: "Winamax Poker - CashGame - TableName - 0.01€/0.02€ - EUR"
        # Aussi: "Winamax Poker - NL Holdem - TableName - 0.01€/0.02€"
        "cash": re.compile(
            r"Winamax\s+Poker\s*-\s*(?:CashGame|NL\s*Hold'?em|PL\s*Omaha|Omaha)"
            r"\s*-\s*(?P<table_name>[^-]+?)\s*-\s*"
            r"(?P<blinds>[\d.,]+\s*[€$£]?\s*/\s*[\d.,]+\s*[€$£]?)"
            r"(?:\s*-\s*(?P<currency>\w+))?",
            re.IGNORECASE,
        ),
        # Go Fast: "Winamax Poker - Go Fast "PoolName" - 0.05€/0.10€"
        "go_fast": re.compile(
            r"Winamax\s+Poker\s*-\s*Go\s*Fast\s*[\"']?"
            r"(?P<pool_name>[^\"'-]+?)[\"']?\s*-\s*"
            r"(?P<blinds>[\d.,]+\s*[€$£]?\s*/\s*[\d.,]+\s*[€$£]?)",
            re.IGNORECASE,
        ),
        # HOLD-UP (autre variante fast-fold): "Winamax Poker - HOLD-UP "PoolName" - blinds"
        "holdup": re.compile(
            r"Winamax\s+Poker\s*-\s*HOLD-?UP\s*[\"']?"
            r"(?P<pool_name>[^\"'-]+?)[\"']?\s*-\s*"
            r"(?P<blinds>[\d.,]+\s*[€$£]?\s*/\s*[\d.,]+\s*[€$£]?)",
            re.IGNORECASE,
        ),
        # Tournament: "Winamax Poker - Tournament "Name" - Table 5"
        # Also with tournament number: "Winamax Poker - Tournament(123456789) "Name" - Table 5"
        "tournament": re.compile(
            r"Winamax\s+Poker\s*-\s*Tournament"
            r"(?:\((?P<tourney_id>\d+)\))?\s*[\"']?"
            r"(?P<tourney_name>[^\"']+?)[\"']?\s*-\s*"
            r"Table\s*(?P<table_num>\d+)",
            re.IGNORECASE,
        ),
        # Expresso: "Winamax Poker - Expresso 5€ - 123456789", "Winamax Poker - Expresso Nitro 5€ - 123456789", "Winamax Expresso Nitro(123456789)"
        "expresso": re.compile(
            r"Winamax\s+(?:Poker\s*-\s*)?Expresso(?:\s+Nitro)?(?:\s+Turbo)?\s*"
            r"(?:(?P<buyin>[\d.,]+\s*[€$£]?)\s*-\s*)?"
            r"(?:\(?(?P<table_id>\d+)\)?)(?:\(#\d+\))?",
            re.IGNORECASE,
        ),
        # Sit & Go: "Winamax Poker - Sit&Go "Name" - Table 1"
        "sng": re.compile(
            r"Winamax\s+Poker\s*-\s*(?:Sit\s*&?\s*Go|S&G)\s*[\"']"
            r"(?P<sng_name>[^\"']+)[\"']\s*-\s*"
            r"(?:Table\s*)?(?P<table_num>\d+)?",
            re.IGNORECASE,
        ),
        # Linux Cash Game: Simple format "Winamax TableName" (without "Poker -")
        # Examples: "Winamax Aalen 14", "Winamax Casablanca 02"
        "linux_cash": re.compile(r"^Winamax\s+(?P<table_name>[A-Za-z]+(?:\s+\d+)?)\s*$", re.IGNORECASE),
        # Generic Winamax (fallback) - must contain "Winamax Poker -"
        "generic": re.compile(r"Winamax\s+Poker\s*-\s*(?P<content>.+)", re.IGNORECASE),
        # Linux generic (fallback for any Winamax window without "Poker")
        "linux_generic": re.compile(r"^Winamax\s+(?P<content>.+)$", re.IGNORECASE),
    }

    # Pattern to detect whether this is a Winamax window
    WINAMAX_PATTERN = re.compile(r"winamax", re.IGNORECASE)

    @classmethod
    def is_winamax_window(cls, title: str) -> bool:
        """Check whether the title matches a Winamax window."""
        if not title:
            return False
        return bool(cls.WINAMAX_PATTERN.search(title))

    @classmethod
    def parse(cls, title: str) -> WinamaxWindowInfo | None:
        """
        Parse a Winamax window title.

        Args:
            title: Window title

        Returns:
            WinamaxWindowInfo if this is a Winamax window, otherwise None
        """
        if not title or not cls.is_winamax_window(title):
            return None

        # Essayer chaque pattern (sauf generic et linux_generic)
        for table_type, pattern in cls.PATTERNS.items():
            if table_type in ("generic", "linux_generic"):
                continue

            match = pattern.search(title)
            if match:
                return cls._create_info(table_type, match, title)

        # Generic fallback (Winamax Poker - ...)
        generic_match = cls.PATTERNS["generic"].search(title)
        if generic_match:
            return WinamaxWindowInfo(
                table_name=generic_match.group("content").strip(), table_type=WinamaxTableType.UNKNOWN, raw_title=title
            )

        # Generic Linux fallback (Winamax ...)
        linux_generic_match = cls.PATTERNS["linux_generic"].search(title)
        if linux_generic_match:
            return WinamaxWindowInfo(
                table_name=linux_generic_match.group("content").strip(),
                table_type=WinamaxTableType.UNKNOWN,
                raw_title=title,
            )

        return None

    @classmethod
    def _create_info(cls, table_type: str, match: re.Match, title: str) -> WinamaxWindowInfo:
        """Create a WinamaxWindowInfo from a regex match."""
        groups = match.groupdict()

        if table_type == "cash":
            return WinamaxWindowInfo(
                table_name=groups.get("table_name", "").strip(),
                table_type=WinamaxTableType.CASH_GAME,
                blinds=cls._normalize_blinds(groups.get("blinds")),
                currency=groups.get("currency"),
                raw_title=title,
            )

        elif table_type == "go_fast":
            return WinamaxWindowInfo(
                table_name=groups.get("pool_name", "").strip(),
                table_type=WinamaxTableType.GO_FAST,
                blinds=cls._normalize_blinds(groups.get("blinds")),
                is_fast_fold=True,
                raw_title=title,
            )

        elif table_type == "holdup":
            return WinamaxWindowInfo(
                table_name=groups.get("pool_name", "").strip(),
                table_type=WinamaxTableType.GO_FAST,  # Treated as fast-fold
                blinds=cls._normalize_blinds(groups.get("blinds")),
                is_fast_fold=True,
                raw_title=title,
            )

        elif table_type == "tournament":
            return WinamaxWindowInfo(
                table_name=groups.get("tourney_name", "").strip(),
                table_type=WinamaxTableType.TOURNAMENT,
                tournament_name=groups.get("tourney_name", "").strip(),
                table_number=int(groups.get("table_num", 0)),
                raw_title=title,
            )

        elif table_type == "expresso":
            return WinamaxWindowInfo(
                table_name=f"Expresso {groups.get('buyin', '')}".strip(),
                table_type=WinamaxTableType.EXPRESSO,
                buyin=groups.get("buyin"),
                table_number=int(groups.get("table_id", 0)),
                is_fast_fold=False,  # Expresso n'est pas du fast-fold classique
                raw_title=title,
            )

        elif table_type == "sng":
            table_num = groups.get("table_num")
            return WinamaxWindowInfo(
                table_name=groups.get("sng_name", "").strip(),
                table_type=WinamaxTableType.SIT_AND_GO,
                tournament_name=groups.get("sng_name", "").strip(),
                table_number=int(table_num) if table_num else None,
                raw_title=title,
            )

        elif table_type == "linux_cash":
            # Linux cash game: simple "Winamax TableName" format
            return WinamaxWindowInfo(
                table_name=groups.get("table_name", "").strip(), table_type=WinamaxTableType.CASH_GAME, raw_title=title
            )

        # Fallback
        return WinamaxWindowInfo(table_name="Unknown", table_type=WinamaxTableType.UNKNOWN, raw_title=title)

    @classmethod
    def _normalize_blinds(cls, blinds: str | None) -> str | None:
        """Normalize the blinds format."""
        if not blinds:
            return None
        # Remove extra whitespace
        return re.sub(r"\s+", "", blinds)

    @classmethod
    def matches_hand_history(
        cls, window_info: WinamaxWindowInfo, hh_table_name: str, hh_tournament_id: str | None = None
    ) -> bool:
        """
        Check whether a window corresponds to a hand-history table.

        Args:
            window_info: Window information
            hh_table_name: Nom de table extrait du hand history
            hh_tournament_id: ID de tournoi si applicable

        Returns:
            True if the window corresponds to the hand history
        """
        if not window_info or not hh_table_name:
            return False

        # Normalize names for comparison
        window_name = cls._normalize_name(window_info.table_name)
        hh_name = cls._normalize_name(hh_table_name)

        # Match exact
        if window_name == hh_name:
            return True

        # Partial match (the HH name is contained in the title or vice versa)
        if hh_name in window_name or window_name in hh_name:
            return True

        # For tournaments, also compare the table number
        if window_info.table_type == WinamaxTableType.TOURNAMENT:
            # Format HH possible: "TourneyName(123456789)#5" ou similaire
            if window_info.table_number:
                # Look for the table number in the HH name
                table_patterns = [
                    f"#{window_info.table_number}",
                    f"table{window_info.table_number}",
                    f"table {window_info.table_number}",
                ]
                for pattern in table_patterns:
                    if pattern in hh_name.lower():
                        return True

        # For Expresso, match on the table ID
        if window_info.table_type == WinamaxTableType.EXPRESSO:
            if window_info.table_number and str(window_info.table_number) in hh_table_name:
                return True

        return False

    @classmethod
    def _normalize_name(cls, name: str) -> str:
        """Normalize a name for comparison."""
        if not name:
            return ""
        # Lowercase, remove special characters, normalize whitespace
        normalized = name.lower().strip()
        normalized = re.sub(r"[^\w\s]", "", normalized)
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized


# Alias for shorter imports
parse_winamax_title = WinamaxTitleParser.parse
is_winamax_window = WinamaxTitleParser.is_winamax_window
