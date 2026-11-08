#!/usr/bin/env python
# Module name and the camelCase converter API follow the *ToFpdb convention of
# every hand-history converter (base-class overrides cannot be renamed).
# pylint: disable=invalid-name
"""Betclic 2025+ in-house client: the native ``*** HEADER ***`` text format (#730).

Betclic left the iPoker network in January 2025 and its own client now writes
plain-text hand histories. This converter is registered under the site name
``Betclic`` (id 142), kept apart from the historical iPoker skin
``Betclic Poker`` (id 131, XML), which :mod:`fpdb_3_legacy.iPoker` still serves.

A hand looks like::

    *** HEADER ***
    Site: Betclic.fr
    Game Mode: Spin
    Game Type: NL Texas Hold'em
    Game Name: Spin & Rush 2€
    Game ID: 01KE0E9VW7KKPNRM9PYPG9D7A5
    Prize pool: 4.00€
    Multiplier: x2
    Buy In: 2.00€
    Hand ID: 01KE0EM78GQ5YJ5JGPZKQKTVCA
    Date & Time: 2026-01-02 22:53:05 (UTC)
    Table ID: 01KE0E9VWGGSCNGV98FEW34PMH
    Blinds: 50/100
    Total Pot: 1360
    Rake: 0
    *** PLAYERS ***
    Seat 1: <name> (680) [BTN SB Hero]
    *** HOLE CARDS ***
    <name>: [Kc 2d]
    *** PRE-FLOP ***
    22:53:05 - <name>: Posts SB 50
    ...
    *** SUMMARY ***
    <name> wins main pot of 1360
    <name> finished 1st and wins 4.00 EUR

Hands are separated by a ``------------`` line, except for the occasional
export that omits it, so the splitter anchors on the ``*** HEADER ***`` line
itself. Player names may contain spaces and accented characters; the hero is
the seat whose tag list carries ``Hero``.

Hand, game and table ids are ULIDs (26 Crockford base-32 characters, 128
bits). ``Hands.siteHandNo`` and ``Tourneys.siteTourneyNo`` are BIGINT and the
duplicate check keys on them, so :func:`ulid_to_int` maps a ULID to the 63-bit
value ``(48-bit millisecond timestamp << 15) | (15 low bits of the random
part)``, which fits a signed BIGINT and stayed collision-free over the whole
4,416-hand / 300-tournament reference corpus.

``Game Mode: Spin`` hands are Spin & Rush lottery sit-and-gos: the header
carries the buy-in, the prize pool and the multiplier, and the summary carries
each player's finishing place and winnings. ``Game Mode: Cash Game`` hands
(ring games, e.g. PLO Omaha) carry euro amounts instead of chip counts.
"""

from __future__ import annotations

import datetime
import re
from decimal import Decimal
from typing import Any

from fpdb_3_legacy.Exceptions import FpdbParseError
from fpdb_3_legacy.HandHistoryConverter import HandHistoryConverter
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("betclic_parser")

# Crockford base-32 (as used by ULIDs) differs from the alphabet int(_, 32)
# expects: I, L, O and U are excluded, so translate before decoding.
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_PYTHON_BASE32 = "0123456789ABCDEFGHIJKLMNOPQRSTUV"
_ULID_TO_PY32 = str.maketrans(_CROCKFORD, _PYTHON_BASE32)

RE_ULID = r"[0-9A-HJKMNP-TV-Z]{26}"

# A signed BIGINT tops out at 2**63 - 1: 48 timestamp bits + 15 random bits.
BIGINT_MAX = 2**63 - 1


def ulid_to_int(ulid: str) -> int:
    """Map a 26-character ULID to a stable signed-BIGINT-safe integer.

    The value is the ULID's 48-bit millisecond timestamp shifted left by 15,
    plus the 15 lowest bits of its 80-bit random part, so it never exceeds
    2**63 - 1 and two ULIDs born in the same millisecond still differ unless
    their random parts agree on those 15 bits. The mapping is deterministic,
    so re-importing a file yields the same ``siteHandNo``/``siteTourneyNo``
    and the existing duplicate check rejects the second copy.
    """
    value = int(ulid.strip().upper().translate(_ULID_TO_PY32), 32)
    timestamp_ms = value >> 80
    random_part = value & ((1 << 80) - 1)
    return (timestamp_ms << 15) | (random_part & 0x7FFF)


class _StreetMatch:
    """Adapter so Hand.addStreets can consume explicit street slices."""

    def __init__(self, streets):
        self._streets = streets

    def groupdict(self):
        return self._streets


class Betclic(HandHistoryConverter):
    # The read* methods are the converter contract; parseHeader stays unimplemented
    # because copyGameHeader is off for this format.
    # pylint: disable=too-many-public-methods,abstract-method
    """Betclic 2025+ client (site id 142), the ``*** HEADER ***`` text format."""

    sitename = "Betclic"
    siteId = 142  # Needs to match the id entry in the Sites database
    filetype = "text"
    codepage = ("utf8", "cp1252", "ISO-8859-1")

    sym = {
        "USD": r"\$",
        "EUR": "€",
        "GBP": r"\£",
        "CAD": r"C\$",
        "AUD": r"A\$",
        "T$": "",
        "play": "",
    }
    substitutions = {
        "LS": r"\$|€|£|C\$|A\$",
        "CUR": r"(\$|€|£)?",
    }

    currencies = {"€": "EUR", "$": "USD", "£": "GBP"}

    # One marker per hand chunk; the export's "------------" separator is
    # missing between a few hands, so hands split at each header line.
    # \r? because IdentifySite matches the raw file: a Windows checkout rewrites
    # the fixtures with CRLF line endings (core.autocrlf=true on the runners).
    re_identify = re.compile(r"^\*\*\* HEADER \*\*\*\r?$", re.MULTILINE)
    re_SplitHands = re.compile(r"^(?=\*\*\* HEADER \*\*\*$)", re.MULTILINE)

    re_HeaderSection = re.compile(r"\*\*\* HEADER \*\*\*\n(?P<FIELDS>.*?)\n\*\*\* PLAYERS \*\*\*", re.DOTALL)
    re_PlayerInfo = re.compile(
        r"^Seat (?P<SEAT>[0-9]+): (?P<PNAME>.+) \((?P<STACK>[^)]+)\)(?: \[(?P<TAGS>[^\]]+)\])?$",
        re.MULTILINE,
    )
    re_HoleCards = re.compile(r"^(?P<PNAME>.+): \[(?P<CARDS>[^\]]+)\]$", re.MULTILINE)
    re_Board = re.compile(r"\[(?P<CARDS>[^\]]+)\]")
    re_ActionLine = re.compile(
        r"^[0-9]{2}:[0-9]{2}:[0-9]{2} - (?P<PNAME>.+): (?P<ACTION>.*)$",
        re.MULTILINE,
    )
    re_PostSB = re.compile(r"^Posts SB (?P<AMT>[^ ]+)( and is all-in)?$", re.MULTILINE)
    re_PostBB = re.compile(r"^Posts BB (?P<AMT>[^ ]+)( and is all-in)?$", re.MULTILINE)
    re_ShowdownAction = re.compile(
        r"^(?P<PNAME>.+) shows \[(?P<CARDS>[^\]]+)\](?: \((?P<STRING>[^)]+)\))?(?: \[(?P<BEST>[^\]]+)\])?$",
        re.MULTILINE,
    )
    re_WinPot = re.compile(
        r"^(?P<PNAME>.+) wins (?:(?P<SIDE>[0-9]+(?:st|nd|rd|th)) side |main )pot of (?P<AMT>\S+)$",
        re.MULTILINE,
    )
    re_Finished = re.compile(
        r"^(?P<PNAME>.+) finished (?P<RANK>[0-9]+)(?:st|nd|rd|th)"
        r"(?: and wins (?P<AMT>[0-9.,]+) (?P<CUR>[A-Z]{3}))?$",
        re.MULTILINE,
    )
    re_DateTime = re.compile(
        r"^(?P<DATETIME>[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}) \(UTC\)$", re.MULTILINE
    )
    re_MaxSeats = re.compile(r"(?P<MAX>[0-9]+)\s*[Mm]ax")

    def readSupportedGames(self):
        return [
            ["ring", "hold", "nl"],
            ["ring", "hold", "pl"],
            ["ring", "hold", "fl"],
            ["tour", "hold", "nl"],
            ["tour", "hold", "pl"],
            ["tour", "hold", "fl"],
        ]

    # -- header helpers -----------------------------------------------------

    def _header_fields(self, handText: str) -> dict[str, str]:
        m = self.re_HeaderSection.search(handText)
        if not m:
            return {}
        fields: dict[str, str] = {}
        for line in m.group("FIELDS").splitlines():
            key, sep, value = line.partition(": ")
            if sep:
                fields[key.strip()] = value.strip()
        return fields

    def _amount(self, raw: str) -> str:
        """Strip the currency symbol, then normalise the number."""
        return self.clearMoneyString(re.sub(r"[^\d.,-]", "", raw))

    @classmethod
    def _limit_category(cls, game_label: str) -> tuple[str, str]:
        """Derive (limitType, category) from a Game Type label."""
        low = game_label.strip().lower()
        if "omaha" in low:
            category = "omahahilo" if ("hi/lo" in low or "h/l" in low or "8" in low) else "omahahi"
        elif "hold" in low:
            category = "holdem"
        elif "stud" in low:
            category = "7stud"
        else:
            category = "holdem"
        if low.startswith(("nl", "no limit")):
            limit = "nl"
        elif low.startswith(("pl", "pot limit")) or category.startswith("omaha"):
            limit = "pl"
        elif low.startswith(("fl", "fixed limit", "limit")):
            limit = "fl"
        else:
            limit = "nl"
        return limit, category

    def _currency_of(self, *texts: str) -> str:
        for text in texts:
            for sym, iso in self.currencies.items():
                if sym in text:
                    return iso
        return "EUR"

    def determineGameType(self, handText):
        fields = self._header_fields(handText)
        if not fields:
            log.error("determineGameType: no *** HEADER *** block in hand")
            raise FpdbParseError
        mode = fields.get("Game Mode", "")
        limit, category = self._limit_category(fields.get("Game Type", ""))
        blinds = fields.get("Blinds", "")
        parts = re.split(r"/", blinds)
        if len(parts) != 2:
            log.error(f"determineGameType: cannot parse Blinds '{blinds}'")
            raise FpdbParseError
        is_tour = mode != "Cash Game"
        info: dict[str, Any] = {
            "type": "tour" if is_tour else "ring",
            "split": False,
            "base": "hold",
            "limitType": limit,
            "category": category,
            "sb": self._amount(parts[0]),
            "bb": self._amount(parts[1]),
            # Tournament blinds/pots are chips, not currency amounts: only the
            # buy-in carries real money, so the gametype stays in "T$".
            "currency": "T$"
            if is_tour
            else self._currency_of(blinds, fields.get("Buy In", ""), fields.get("Total Pot", "")),
        }
        log.info(f"determineGameType (Betclic): {info}")
        return info

    # -- hand-level parsing ---------------------------------------------------

    def readHandInfo(self, hand) -> None:
        fields = self._header_fields(hand.handText)
        if not fields or "Hand ID" not in fields:
            log.error("readHandInfo: no Hand ID in the header")
            raise FpdbParseError

        hand.handid = str(ulid_to_int(fields["Hand ID"]))
        hand.tablename = fields.get("Table ID", "")

        m = self.re_DateTime.search(fields.get("Date & Time", ""))
        if m:
            # The client stamps UTC explicitly; store it as the naive UTC time.
            hand.startTime = datetime.datetime.strptime(m.group("DATETIME"), "%Y-%m-%d %H:%M:%S")  # noqa: DTZ007
        else:
            log.warning(f"readHandInfo: unparseable Date & Time '{fields.get('Date & Time')}'")

        game_name = fields.get("Game Name", "")
        hand.tourneyName = game_name or None
        m = self.re_MaxSeats.search(game_name)
        if m:
            hand.maxseats = int(m.group("MAX"))
            hand.gametype["maxSeats"] = hand.maxseats

        if hand.gametype["type"] == "tour":
            # Spin & Rush (and any other tournament mode): the header carries
            # the game id, the buy-in, the prize pool and the multiplier.
            if "Game ID" not in fields:
                log.error("readHandInfo: tournament hand without a Game ID")
                raise FpdbParseError
            hand.tourNo = str(ulid_to_int(fields["Game ID"]))
            # Real money only on the buy-in; the gametype currency stays "T$"
            # (chips) so chip amounts are not displayed as euros.
            hand.buyinCurrency = self._currency_of(fields.get("Buy In", ""), fields.get("Prize pool", ""))
            hand.buyin = int(round(100 * Decimal(self._amount(fields.get("Buy In", "0")))))
            hand.fee = 0  # the export states a single entry amount
            hand.isKO = False
            if hand.maxseats is None and fields.get("Game Mode") == "Spin":
                hand.maxseats = 3
                hand.gametype["maxSeats"] = 3
            if "Multiplier" in fields:
                # A multiplier line marks a lottery sit-and-go (Spin & Rush).
                hand.isSng = True
                hand.isLottery = True
                hand.tourneyMultiplier = int(fields["Multiplier"].strip().lstrip("x"), 10)
        log.info(f"readHandInfo: {hand}")

    def compilePlayerRegexs(self, hand) -> None:
        # Player names are matched positionally (timestamp-prefixed action
        # lines, seat lines), not through per-player compiled regexes.
        pass

    def readPlayerStacks(self, hand) -> None:
        for m in self.re_PlayerInfo.finditer(hand.handText):
            seat = int(m.group("SEAT"))
            name = m.group("PNAME").strip()
            tags = (m.group("TAGS") or "").split()
            hand.addPlayer(seat, name, self._amount(m.group("STACK")))
            if "Hero" in tags:
                hand.hero = name
        if not hand.hero:
            # Observed hand: fall back to the configured screen name.
            try:
                configured = self.config.get_site_parameters(self.sitename).get("screen_name")
            except (AttributeError, KeyError, TypeError):
                configured = None
            if configured and any(p[1] == configured for p in hand.players):
                hand.hero = configured
        log.info(f"readPlayerStacks: hero='{hand.hero}' players={hand.players}")

    def readButton(self, hand) -> None:
        for m in self.re_PlayerInfo.finditer(hand.handText):
            if "BTN" in (m.group("TAGS") or "").split():
                hand.buttonpos = int(m.group("SEAT"))
                log.info(f"readButton: seat {hand.buttonpos}")
                return
        log.info("readButton: no BTN tag found")

    def markStreets(self, hand) -> None:
        text = hand.handText
        markers = [
            ("*** HOLE CARDS ***", "PREFLOP"),
            ("*** FLOP ***", "FLOP"),
            ("*** TURN ***", "TURN"),
            ("*** RIVER ***", "RIVER"),
        ]
        stops = {"*** SHOWDOWN ***", "*** SUMMARY ***"}
        found = []
        for marker, street in markers:
            idx = text.find(marker)
            if idx >= 0:
                found.append((idx, marker, street))
        found.sort()
        streets = {street: "" for street in hand.allStreets}
        for i, (pos, marker, street) in enumerate(found):
            start = pos + len(marker)
            ends = [text.find(stop, start) for stop in stops]
            ends += [p for p, _m, _s in found[i + 1 :]]
            ends = [e for e in ends if e >= 0]
            streets[street] = text[start : min(ends) if ends else len(text)]
        hand.addStreets(_StreetMatch(streets))

    def readCommunityCards(self, hand, street) -> None:
        m = self.re_Board.search(hand.streets[street])
        if not m:
            log.error(f"readCommunityCards: no board on {street}")
            return
        cards = m.group("CARDS").split()
        # Each street header carries the cumulative board; TURN/RIVER add one card.
        if street == "TURN":
            cards = cards[3:4]
        elif street == "RIVER":
            cards = cards[4:5]
        hand.setCommunityCards(street, cards)
        log.info(f"readCommunityCards {street}: {cards}")

    def readBlinds(self, hand) -> None:
        for line in self.re_ActionLine.finditer(hand.handText):
            action = line.group("ACTION")
            m = self.re_PostSB.match(action)
            if m:
                hand.addBlind(line.group("PNAME"), "small blind", self._amount(m.group("AMT")))
                continue
            m = self.re_PostBB.match(action)
            if m:
                hand.addBlind(line.group("PNAME"), "big blind", self._amount(m.group("AMT")))

    def readHoleCards(self, hand) -> None:
        street = "PREFLOP"
        text = hand.streets.get(street) or ""
        cut = text.find("*** PRE-FLOP ***")
        hole_section = text[:cut] if cut >= 0 else text
        for m in self.re_HoleCards.finditer(hole_section):
            cards = m.group("CARDS").split()
            hand.addHoleCards(street, m.group("PNAME").strip(), closed=cards, shown=False, mucked=False, dealt=True)
            log.info(f"readHoleCards: '{m.group('PNAME')}' {cards}")

    def readAction(self, hand, street) -> None:
        text = hand.streets.get(street) or ""
        if not text:
            return
        for line in self.re_ActionLine.finditer(text):
            player = line.group("PNAME").strip()
            action = line.group("ACTION").strip()
            if action.endswith("and is all-in"):
                # The all-in flag rides on the stack reaching zero inside the
                # add* calls, which the suffix guarantees; strip it and dispatch.
                action = action[: -len(" and is all-in")].strip()
            self._doAction(hand, street, player, action)

    def _doAction(self, hand, street, player: str, action: str) -> None:
        if action == "Folds":
            hand.addFold(street, player)
        elif action == "Checks":
            hand.addCheck(street, player)
        elif action.startswith("Calls "):
            hand.addCall(street, player, self._amount(action[len("Calls ") :]))
        elif action.startswith("Bets "):
            hand.addBet(street, player, self._amount(action[len("Bets ") :]))
        elif action.startswith("Raises to "):
            hand.addRaiseTo(street, player, self._amount(action[len("Raises to ") :]))
        elif action.startswith("Posts "):
            pass  # blinds are read by readBlinds
        elif action in ("Sits out", "Sits in", "Disconnected", "Reconnected"):
            pass  # informational; sittingOut() derives the sit-out set
        else:
            log.warning(f"readAction: unhandled action '{player}: {action}' on {street}")

    def readShowdownActions(self, hand) -> None:
        for m in self.re_ShowdownAction.finditer(hand.handText):
            player = m.group("PNAME").strip()
            cards = m.group("CARDS").split()
            hand.addShownCards(cards, player, shown=True, string=m.group("STRING"))
            if m.group("BEST"):
                hand.winningHand[player] = m.group("BEST").split()
            log.info(f"readShowdownActions: '{player}' shows {cards}")

    def readCollectPot(self, hand) -> None:
        for m in self.re_WinPot.finditer(hand.handText):
            amount = self._amount(m.group("AMT"))
            hand.addCollectPot(m.group("PNAME").strip(), amount)
            log.info(f"readCollectPot: '{m.group('PNAME')}' {amount} ({'side' if m.group('SIDE') else 'main'} pot)")

    def readTourneyResults(self, hand) -> None:
        for m in self.re_Finished.finditer(hand.handText):
            player = m.group("PNAME").strip()
            hand.tourneyRanks[player] = int(m.group("RANK"))
            if m.group("AMT"):
                hand.tourneyWinnings[player] = int(round(100 * Decimal(m.group("AMT"))))
            else:
                # An explicit non-paying finish is a zero, not an unknown: leaving
                # winnings unset would store NULL and drop the entry cost from
                # the net-profit queries that sum winnings without coalescing.
                hand.tourneyWinnings[player] = 0
            hand.tourneyWinningsCurrency[player] = m.group("CUR") or hand.buyinCurrency or hand.gametype.get("currency")
            log.info(f"readTourneyResults: '{player}' rank {m.group('RANK')} winnings {m.group('AMT')}")

    def readOther(self, hand) -> None:
        # The header states the pot and the rake outright; trust both so the
        # pot equation (collected + rake == total pot) holds by construction.
        fields = self._header_fields(hand.handText)
        if "Total Pot" in fields:
            hand.totalpot = Decimal(self._amount(fields["Total Pot"]))
        if "Rake" in fields:
            hand.rake = Decimal(self._amount(fields["Rake"]))
            hand.rake_parsed = True  # type: ignore[attr-defined]

    def getRake(self, hand) -> None:
        if hand.rake is None and hand.totalpot is not None:
            hand.rake = hand.totalpot - hand.totalcollected

    def readShownCards(self, hand) -> None:
        pass

    def readSTP(self, hand) -> None:
        pass

    def readAntes(self, hand) -> None:
        pass

    def readBringIn(self, hand) -> None:
        pass

    def readSummaryInfo(self, summaryInfoList) -> bool:
        return True

    @staticmethod
    def getTableTitleRe(_game_type, table_name=None, tournament=None, table_number=None):
        """Search string for the 2026 client's table windows.

        The window title carries the table id; for tournaments the stored
        table name is ``<tourneyNo> <table ULID>``, so the ULID is the last
        token. Best effort until the title format is captured live.
        """
        candidate = table_name if table_name else (tournament if tournament is not None else table_number)
        if candidate is None:
            return None
        candidate = str(candidate).split()[-1]
        return re.escape(candidate)

    @staticmethod
    def getTableNoRe(tournament) -> str:
        return rf"\b({RE_ULID})\b"
