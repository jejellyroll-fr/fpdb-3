from __future__ import annotations

import datetime
import re
from decimal import Decimal
from typing import TYPE_CHECKING, Any, ClassVar
from zoneinfo import ZoneInfo

from fpdb_3_legacy.HandHistoryConverter import FpdbHandPartial, FpdbParseError
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("ipoker_parser")

# The recent iPoker client (PMU/bwin) anonymises a hand as "Player <N>" only
# when the hero is NOT dealt into it; every hand the hero plays carries real
# names. The anonymous name equals the seat number ("Player 3" sits at seat 3),
# and seats are stable within a session, so the hands the hero played give us a
# seat -> real name map that recovers the opponents of the anonymous hands.
# These patterns drive the de-anonymisation pass in readHandInfo.
_ANON_NAME_RE = re.compile(r"^Player\s+\d+$")
_PLAYER_TAG_RE = re.compile(
    r'<player\b(?=[^>]*\bname="(?P<PNAME>[^"]*)")(?=[^>]*\bseat="(?P<SEAT>\d+)")[^>]*>',
)
_SESSION_CODE_RE = re.compile(r'sessioncode="(?P<CODE>\d+)"')
_GAMECODE_RE = re.compile(r'<game gamecode="(?P<HID>\d+)"')
# The placeholder a seat gets when the session names nobody for it. Matched in
# full rather than by its "anon_" prefix: "anon_hunter" is a screen name someone
# may well be sitting under, and reading it as a placeholder would drop the
# hands that player is recovered in.
_ANON_SCOPE_RE = re.compile(r"^anon_\d+_\d+$")


class IPokerHandInfoMixin:
    """Hand metadata and player stack parsing for iPoker hand histories."""

    re_hand_info: ClassVar[re.Pattern[str]]
    re_date_time1: ClassVar[re.Pattern[str]]
    re_date_time2: ClassVar[re.Pattern[str]]
    re_date_time3: ClassVar[re.Pattern[str]]
    re_player_info: ClassVar[re.Pattern[str]]
    months: ClassVar[dict[str, int]]
    info: dict[str, Any]
    tinfo: dict[str, Any]
    tablename: str
    hero: str
    maxseats: int
    playerWinnings: dict[str, str]
    seat_mapping: dict[int, int]
    _seat_names: dict[int, str]
    _seat_names_src: str

    if TYPE_CHECKING:

        def getFileCreationTime(self) -> datetime.datetime: ...

        def guessMaxSeats(self, hand: Any) -> int: ...

        @staticmethod
        def clearMoneyString(money: str) -> str: ...

    def _session_code(self) -> str:
        """Return the session code used to scope unresolved anonymous names."""
        whole = getattr(self, "whole_file", "") or ""
        m = _SESSION_CODE_RE.search(whole)
        return m.group("CODE") if m else "0"

    def _session_seat_names(self) -> dict[int, str]:
        """Map physical seat -> real name, learned from the session's named hands.

        iPoker only anonymises a hand ("Player N") when the hero is not dealt in;
        the hands the hero plays carry real names. Scanning the whole session
        file for those real names, keyed by seat, lets the anonymous hands'
        opponents be recovered. A seat that shows more than one real name across
        the session (the occupant changed) is dropped as ambiguous rather than
        guessed. Cached per whole_file (re-read as the file grows during live
        auto-import) so later anonymous hands pick up names once the hero plays.
        """
        whole = getattr(self, "whole_file", "") or ""
        if getattr(self, "_seat_names_src", None) is whole:
            return self._seat_names

        seen: dict[int, set[str]] = {}
        for chunk in whole.split("</game>"):
            if "<game" not in chunk:
                continue
            for m in _PLAYER_TAG_RE.finditer(chunk):
                name = m.group("PNAME")
                if _ANON_NAME_RE.match(name):
                    continue
                seen.setdefault(int(m.group("SEAT")), set()).add(name)

        resolved = {seat: next(iter(names)) for seat, names in seen.items() if len(names) == 1}
        self._seat_names_src = whole
        self._seat_names = resolved
        return resolved

    @staticmethod
    def _named_players(hand_text: str) -> list[str]:
        """Players the hand can actually be credited to, placeholders excluded."""
        return [
            m.group("PNAME")
            for m in _PLAYER_TAG_RE.finditer(hand_text)
            if not _ANON_SCOPE_RE.match(m.group("PNAME"))
        ]

    def _deanonymize_players(self, hand: Any) -> tuple[int, int]:
        """Recover anonymous "Player N" opponents in place on hand.handText.

        Only hands where the hero is not dealt are anonymous. There is therefore
        no hero to inject here; each "Player N" (== seat N) is remapped to the
        real name that seat carried in a named hand of the same session, or, when
        that seat's occupant is unknown/ambiguous, scoped to
        ``anon_<sessioncode>_<seat>`` so stats never merge a "Player 3" across
        unrelated sessions. Named hands (real names already seated) are left
        untouched, so normal files and fixtures are unaffected.

        markStreets/readBlinds/readAction/readHoleCards/readCollectPot all
        re-parse hand.handText, so rewriting it once here keeps players, actions,
        cards and collectees consistent under the recovered names.

        Returns how many players were anonymous and how many of them were
        recovered, which is what lets readHandInfo drop a hand nobody can be put
        a name to.
        """
        hero_nick = getattr(self, "hero", "") or ""

        anon_players = [
            (m.group("PNAME"), int(m.group("SEAT")))
            for m in _PLAYER_TAG_RE.finditer(hand.handText)
            if _ANON_NAME_RE.match(m.group("PNAME"))
        ]
        if not anon_players:
            return 0, 0  # named hand (hero dealt in): real names already present.

        session = self._session_code()
        seat_names = self._session_seat_names()
        rename: dict[str, str] = {}
        for pname, seat in anon_players:
            real = seat_names.get(seat)
            # Never resurrect the hero: an anonymous hand is by definition one the
            # hero did not play, so a seat that was the hero's in a named hand
            # must be scoped, not renamed back to the hero.
            if real and real != hero_nick:
                rename[pname] = real
            else:
                rename[pname] = f"anon_{session}_{seat}"

        text = hand.handText
        for old, new in rename.items():
            text = text.replace(f'name="{old}"', f'name="{new}"').replace(f'player="{old}"', f'player="{new}"')
        hand.handText = text

        recovered = {old: new for old, new in rename.items() if not _ANON_SCOPE_RE.match(new)}
        if recovered:
            log.info("iPoker de-anonymisation: recovered opponents from session seat map: %s", recovered)
        log.debug("iPoker de-anonymisation rename map: %s", rename)
        return len(anon_players), len(recovered)

    def readHandInfo(self, hand: Any) -> None:
        """Parses the hand text and extracts relevant information about the hand.

        Args:
            hand: An instance of the Hand class that represents the hand being parsed.

        Raises:
            FpdbParseError: If the hand text cannot be parsed.
            FpdbHandPartial: If every player in the hand is anonymous and no seat
                can be put a name to.

        Returns:
            None
        """
        log.debug("Entering readHandInfo.")

        # Recover anonymous "Player N" opponents before anything else reads
        # player names (see _deanonymize_players).
        anonymous, recovered = self._deanonymize_players(hand)
        if anonymous and not recovered and not self._named_players(hand.handText):
            # Nothing in the session names a single seat yet -- live import
            # reaching an observed hand before the hero has played one. Storing
            # it would create a Players row per seat ("anon_<session>_<seat>")
            # that no statistic can ever be read back through: the hero is not in
            # the hand, so it builds no HUD, and the real names the file reveals
            # minutes later never reach the rows already written. Leave the hand
            # out instead; a later full import of the file, by then holding the
            # named hands, stores it under the real opponents.
            gamecode = _GAMECODE_RE.search(hand.handText)
            msg = (
                f"Hand {gamecode.group('HID') if gamecode else '?'} is fully anonymous and no seat is named "
                f"anywhere in the session yet; skipped rather than stored under placeholder players"
            )
            raise FpdbHandPartial(msg)

        # Parse hand info from regex
        match = self._parse_hand_info_regex(hand.handText)

        # Set basic hand information
        self._set_basic_hand_info(hand, match)

        # Parse and set start time
        self._parse_start_time(hand, match)

        # Set tournament-specific information if applicable
        self._set_tournament_info(hand)

        log.debug("Exiting readHandInfo.")

    def _parse_hand_info_regex(self, hand_text: str) -> re.Match[str]:
        """Parse hand info regex and return match object."""
        match = self.re_hand_info.search(hand_text)
        if match is None:
            tmp = hand_text[:200]
            log.error("iPokerToFpdb.readHandInfo: '%s'", tmp)
            raise FpdbParseError

        log.debug("HandInfo regex matched.")
        log.debug("Extracted groupdict: %s", match.groupdict())
        return match

    def _set_basic_hand_info(self, hand: Any, match: re.Match[str]) -> None:
        """Set basic hand information from match object."""
        # Set the table name and maximum number of seats for the hand
        hand.tablename = self.tablename
        log.debug("Set hand.tablename: %s", hand.tablename)

        if self.info.get("seats"):
            hand.maxseats = int(self.info["seats"])
            hand.gametype["maxSeats"] = hand.maxseats
            log.debug("Set hand.maxseats: %s", hand.maxseats)

        # Set the hand ID for the hand
        hand.handid = match.group("HID")
        log.debug("Set hand.handid: %s", hand.handid)

    def _parse_start_time(self, hand: Any, match: re.Match[str]) -> None:
        """Parse and set the start time for the hand."""
        datetime_str = match.group("DATETIME")
        if datetime_str is None:
            log.warning("No startdate found in hand %s. Using file creation time as fallback.", hand.handid)
            hand.startTime = self.getFileCreationTime()
            log.debug("Set hand.startTime from file creation time: %s", hand.startTime)
            return

        # Try different datetime parsing methods
        if self._try_parse_datetime_format1(hand, datetime_str):
            return

        if self._try_parse_default_format(hand, datetime_str):
            return

        self._try_parse_fallback_formats(hand, datetime_str)

    def _try_parse_datetime_format1(self, hand: Any, datetime_str: str) -> bool:
        """Try to parse datetime using format 1."""
        if m2 := self.re_date_time1.search(datetime_str):
            log.debug("Matched re_date_time1.")
            month = self.months[m2.group("M")]
            sec = m2.group("S") or "00"
            datetimestr = f"{m2.group('Y')}/{month}/{m2.group('D')} {m2.group('H')}:{m2.group('MIN')}:{sec}"
            hand.startTime = datetime.datetime.strptime(datetimestr, "%Y/%m/%d %H:%M:%S").replace(
                tzinfo=ZoneInfo("UTC"),
            )
            log.debug("Parsed hand.startTime: %s", hand.startTime)
            return True
        return False

    def _try_parse_default_format(self, hand: Any, datetime_str: str) -> bool:
        """Try to parse datetime using default format."""
        try:
            hand.startTime = datetime.datetime.strptime(datetime_str, "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=ZoneInfo("UTC"),
            )
            log.debug("Parsed hand.startTime using default format: %s", hand.startTime)
        except ValueError:
            log.debug("Failed to parse datetime using default format.")
            return False
        else:
            return True

    def _try_parse_fallback_formats(self, hand: Any, datetime_str: str) -> None:
        """Try to parse datetime using fallback formats."""
        try:
            log.warning("Failed to parse datetime: %s. Trying re_date_time2 or re_date_time3.", datetime_str)
            if date_match := self.re_date_time2.search(datetime_str):
                log.debug("Matched re_date_time2.")
                datestr = "%d/%m/%Y %H:%M:%S" if "/" in datetime_str else "%d.%m.%Y %H:%M:%S"
                if date_match.group("S") is None:
                    datestr = "%d/%m/%Y %H:%M"
            else:
                date_match1 = self.re_date_time3.search(datetime_str)
                if date_match1 is None:
                    log.exception("iPokerToFpdb.readHandInfo Could not read datetime: '%s'", hand.handid)
                    raise FpdbParseError
                datestr = "%Y/%m/%d %H:%M:%S"
                if date_match1.group("S") is None:
                    datestr = "%Y/%m/%d %H:%M"

            hand.startTime = datetime.datetime.strptime(datetime_str, datestr).replace(
                tzinfo=ZoneInfo("UTC"),
            )
            log.debug("Parsed hand.startTime using fallback format: %s", hand.startTime)
        except ValueError as e:
            log.exception("iPokerToFpdb.readHandInfo Could not read datetime: '%s'", hand.handid)
            raise FpdbParseError from e

    def _set_tournament_info(self, hand: Any) -> None:
        """Set tournament-specific information if applicable."""
        if self.info["type"] == "tour":
            log.debug("Hand is a tournament hand, setting tournament-specific info.")
            hand.tourNo = self.tinfo["tourNo"]
            hand.buyinCurrency = self.tinfo["buyinCurrency"]
            hand.buyin = self.tinfo["buyin"]
            hand.fee = self.tinfo["fee"]
            hand.tablename = str(self.info["table_name"])
            log.debug(
                "Set tournament info: tourNo=%s, buyinCurrency=%s, buyin=%s, fee=%s, tablename=%s",
                hand.tourNo,
                hand.buyinCurrency,
                hand.buyin,
                hand.fee,
                hand.tablename,
            )

    def _initialize_player_data(
        self,
        hand: Any,
    ) -> tuple[dict[str, str], dict[str, list[Any]], dict[int, int]]:
        """Initialize player data structures."""
        self.playerWinnings = {}
        plist: dict[str, list[Any]] = {}
        self.seat_mapping = {}  # Store seat mapping for tournaments
        hand.rake = Decimal("0.00")  # Initialize the total rake
        log.debug("Initialized playerWinnings, plist dictionaries, and hand.rake.")
        return self.playerWinnings, plist, self.seat_mapping

    def _extract_player_info(self, hand: Any) -> tuple[dict[str, list[Any]], list[int]]:
        """Extract player information from hand text."""
        plist: dict[str, list[Any]] = {}
        original_seats: list[int] = []

        m = self.re_player_info.finditer(hand.handText)
        log.debug("Running regex to find player information in hand text.")

        for a in m:
            # Handle players with empty names (sitting out or invalid entries)
            player_name = a.group("PNAME").strip()
            seat_number = int(a.group("SEAT"))

            if not player_name:
                # Generate unique name for unknown player based on seat
                player_name = f"UnknownPlayerSeat{seat_number}"
                log.info("🎯 SEAT DETECTION: Empty player name at seat %s, using %s", seat_number, player_name)
            else:
                log.info("🎯 SEAT DETECTION: Player %s detected at seat %s", player_name, seat_number)

            log.debug("Matched player info: %s", a.groupdict())

            # Extract rake amount, defaulting to '0' if not present
            rake_amount = self.clearMoneyString(a.group("RAKEAMOUNT") or "0")
            hand.rake += Decimal(rake_amount)
            log.debug("Added rake amount %s for player %s. Total rake: %s", rake_amount, player_name, hand.rake)

            # Store original seat number
            original_seat = seat_number
            original_seats.append(original_seat)

            # Create a dictionary entry for the player
            win_amount = a.group("WIN")
            win_cleaned = self.clearMoneyString(win_amount) if win_amount else "0"

            plist[player_name] = [
                original_seat,
                self.clearMoneyString(a.group("CASH")),
                win_cleaned,
                False,
            ]
            log.info(
                "🎯 PLAYER ADDED: %s at seat %s, stack %s, winnings %s.",
                player_name,
                original_seat,
                plist[player_name][1],
                plist[player_name][2],
            )

            # If the player is the button, set the button position
            if a.group("BUTTONPOS") == "1":
                hand.buttonpos = original_seat
                log.debug("Set button position to seat %s for player %s.", hand.buttonpos, player_name)

        return plist, original_seats

    def _validate_player_count(self, plist: dict, hand: Any) -> None:
        """Validate that there are enough players in the hand."""
        if len(plist) <= 1:
            log.warning(
                "iPokerToFpdb.readPlayerStacks: Less than 2 players in hand '%s'. Marking as partial.",
                hand.handid,
            )
            msg = f"iPoker partial hand history: Less than 2 players ({len(plist)} players found)"
            raise FpdbHandPartial(msg)

        log.debug("Player list extracted successfully. Total players: %s", len(plist))

    def _remap_tournament_seats(self, plist: dict, original_seats: list, hand: Any) -> None:
        """Remap seats for tournaments to sequential numbers."""
        if self.info["type"] != "tour":
            return

        # Sort original seats to maintain consistent mapping
        original_seats_sorted = sorted(original_seats)
        for i, original_seat in enumerate(original_seats_sorted):
            self.seat_mapping[original_seat] = i + 1

        log.info("🎯 SEAT MAPPING: %s", self.seat_mapping)

        # Remap button position if needed
        if hand.buttonpos and hand.buttonpos in self.seat_mapping:
            old_button = hand.buttonpos
            hand.buttonpos = self.seat_mapping[hand.buttonpos]
            log.info("🎯 BUTTON REMAPPED: %s -> %s", old_button, hand.buttonpos)

        # Remap seats in plist
        for pname in plist:
            old_seat = plist[pname][0]
            new_seat = self.seat_mapping.get(old_seat, old_seat)
            plist[pname][0] = new_seat
            log.info("🎯 SEAT REMAPPED: %s %s -> %s", pname, old_seat, new_seat)

    def _add_players_to_hand(self, plist: dict, hand: Any) -> None:
        """Add players to the hand object."""
        for pname in plist:
            seat, stack, win, sitout = plist[pname]
            log.info("🎯 ADDING TO HAND: %s at seat %s, stack %s, winnings %s", pname, seat, stack, win)
            hand.addPlayer(seat, pname, stack, None, sitout)
            if Decimal(win) != 0:
                self.playerWinnings[pname] = win
                log.debug("Player %s has winnings: %s", pname, win)
            # Set hand.hero if this player matches the hero nickname
            if hasattr(self, "hero") and self.hero and pname == self.hero:
                hand.hero = pname
                log.info("🎯 SET HAND HERO: %s", pname)

    def _determine_max_seats(self, hand: Any) -> None:
        """Determine the maximum number of seats."""
        # Log final hand.players structure
        log.info("🎯 FINAL HAND.PLAYERS: %s", [f"seat{p[0]}:{p[1]}" for p in hand.players])
        log.info("🎯 MAXSEATS WILL BE: %s", hand.maxseats if hand.maxseats else "TO_BE_DETERMINED")

        # Set the maxseats attribute in the Hand object if it is not already set
        if hand.maxseats is None:
            log.info("🎯 DETERMINING MAXSEATS...")
            if self.info["type"] == "tour" and self.maxseats == 0:
                hand.maxseats = self.guessMaxSeats(hand)
                self.maxseats = hand.maxseats
                log.info("🎯 GUESSED MAXSEATS for tournament: %s", hand.maxseats)
            elif self.info["type"] == "tour":
                hand.maxseats = self.maxseats
                log.info("🎯 SET MAXSEATS from tournament info: %s", hand.maxseats)
            else:
                # For ring games, use guessMaxSeats
                hand.maxseats = self.guessMaxSeats(hand)
                log.info("🎯 GUESSED MAXSEATS for ring game: %s", hand.maxseats)
            hand.gametype["maxSeats"] = hand.maxseats
        else:
            log.info("🎯 MAXSEATS already set: %s", hand.maxseats)

        log.info("🎯 FINAL MAXSEATS: %s", hand.maxseats)

    def readPlayerStacks(self, hand: Any) -> None:
        """Parse and read player stacks and positions from hand text.

        Args:
            hand: The hand object to populate with player information
        """
        log.debug("Entering readPlayerStacks for hand: %s", hand.handid)

        # Initialize data structures
        self._initialize_player_data(hand)

        # Extract player information
        plist, original_seats = self._extract_player_info(hand)

        # Validate player count
        self._validate_player_count(plist, hand)

        # Remap seats for tournaments
        self._remap_tournament_seats(plist, original_seats, hand)

        # Add players to hand
        self._add_players_to_hand(plist, hand)

        # Determine max seats
        self._determine_max_seats(hand)

        log.debug("Exiting readPlayerStacks.")
