from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from fpdb_3_legacy.HandHistoryConverter import FpdbHandPartial, FpdbParseError
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("ipoker_parser")


class IPokerHandInfoMixin:
    """Hand metadata and player stack parsing for iPoker hand histories."""

    def readHandInfo(self, hand: Any) -> None:
        """Parses the hand text and extracts relevant information about the hand.

        Args:
            hand: An instance of the Hand class that represents the hand being parsed.

        Raises:
            FpdbParseError: If the hand text cannot be parsed.

        Returns:
            None
        """
        log.debug("Entering readHandInfo.")

        # Parse hand info from regex
        match = self._parse_hand_info_regex(hand.handText)

        # Set basic hand information
        self._set_basic_hand_info(hand, match)

        # Parse and set start time
        self._parse_start_time(hand, match)

        # Set tournament-specific information if applicable
        self._set_tournament_info(hand)

        log.debug("Exiting readHandInfo.")

    def _parse_hand_info_regex(self, hand_text: str) -> Any:
        """Parse hand info regex and return match object."""
        match = self.re_hand_info.search(hand_text)
        if match is None:
            tmp = hand_text[:200]
            log.error("iPokerToFpdb.readHandInfo: '%s'", tmp)
            raise FpdbParseError

        log.debug("HandInfo regex matched.")
        log.debug("Extracted groupdict: %s", match.groupdict())
        return match

    def _set_basic_hand_info(self, hand: Any, match: Any) -> None:
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

    def _parse_start_time(self, hand: Any, match: Any) -> None:
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

    def _initialize_player_data(self, hand: Any) -> tuple[dict, dict, dict]:
        """Initialize player data structures."""
        self.playerWinnings = {}
        plist = {}
        self.seat_mapping = {}  # Store seat mapping for tournaments
        hand.rake = Decimal("0.00")  # Initialize the total rake
        log.debug("Initialized playerWinnings, plist dictionaries, and hand.rake.")
        return self.playerWinnings, plist, self.seat_mapping

    def _extract_player_info(self, hand: Any) -> tuple[dict, list]:
        """Extract player information from hand text."""
        plist = {}
        original_seats = []

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
