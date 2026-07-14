from __future__ import annotations

import re
from decimal import Decimal
from typing import TYPE_CHECKING, Any, ClassVar

from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("ipoker_parser")


class IPokerStreetsActionsMixin:
    """Street parsing, cards, blinds, actions, and pot collection for iPoker."""

    re_board: ClassVar[re.Pattern[str]]
    re_action: ClassVar[re.Pattern[str]]
    re_hero_cards: ClassVar[re.Pattern[str]]
    re_player_info: ClassVar[re.Pattern[str]]
    THIRD_STREET_CARDS_COUNT: ClassVar[int]
    SECOND_STREET_CARDS_COUNT: ClassVar[int]

    if TYPE_CHECKING:

        def _raise_community_cards_error(self, hand_id: str, street: str) -> None: ...

        @staticmethod
        def clearMoneyString(money: str) -> str: ...

    def markStreets(self, hand: Any) -> None:
        """Extracts the rounds of a hand and adds them to the Hand object.

        Args:
            hand (Hand): the Hand object to which the rounds will be added
        """
        log.debug("Entering markStreets for hand: %s", hand.handid)

        if hand.gametype["base"] in ("hold"):
            log.debug("Parsing streets for Hold'em game.")
            m = re.search(
                r'(?P<PREFLOP>.+(?=<round no="2">)|.+)'  # Preflop round
                r'(<round no="2">(?P<FLOP>.+(?=<round no="3">)|.+))?'  # Flop round
                r'(<round no="3">(?P<TURN>.+(?=<round no="4">)|.+))?'  # Turn round
                r'(<round no="4">(?P<RIVER>.+))?',  # River round
                hand.handText,
                re.DOTALL,
            )
        elif hand.gametype["base"] in ("stud"):
            log.debug("Parsing streets for Stud game.")
            if hand.gametype["category"] == "5_studhi":
                log.debug("Parsing streets for 5-card Stud High game.")
                m = re.search(
                    r'(?P<ANTES>.+(?=<round no="2">)|.+)'  # Antes round
                    r'(<round no="2">(?P<SECOND>.+(?=<round no="3">)|.+))?'  # Second round
                    r'(<round no="3">(?P<THIRD>.+(?=<round no="4">)|.+))?'  # Third round
                    r'(<round no="4">(?P<FOURTH>.+(?=<round no="5">)|.+))?'  # Fourth round
                    r'(<round no="5">(?P<FIFTH>.+))?',  # Fifth round
                    hand.handText,
                    re.DOTALL,
                )
            else:
                log.debug("Parsing streets for 7-card Stud High/Low game.")
                m = re.search(
                    r'(?P<ANTES>.+(?=<round no="2">)|.+)'  # Antes round
                    r'(<round no="2">(?P<THIRD>.+(?=<round no="3">)|.+))?'  # Third round
                    r'(<round no="3">(?P<FOURTH>.+(?=<round no="4">)|.+))?'  # Fourth round
                    r'(<round no="4">(?P<FIFTH>.+(?=<round no="5">)|.+))?'  # Fifth round
                    r'(<round no="5">(?P<SIXTH>.+(?=<round no="6">)|.+))?'  # Sixth round
                    r'(<round no="6">(?P<SEVENTH>.+))?',  # Seventh round
                    hand.handText,
                    re.DOTALL,
                )

        if m:
            log.debug("Streets regex matched. Groups: %s", m.groupdict())
            hand.addStreets(m)
            log.debug("Streets added to hand object.")
        else:
            log.warning("No streets matched for hand: %s", hand.handid)

        log.debug("Exiting markStreets.")

    def readCommunityCards(self, hand: Any, street: str) -> None:
        """Parse the community cards for the given street and set them in the hand object.

        Args:
            hand (Hand): The hand object.
            street (str): The street to parse the community cards for.

        Raises:
            FpdbParseError: If the community cards could not be parsed.

        Returns:
            None
        """
        log.debug("Entering readCommunityCards for hand: %s, street: %s", hand.handid, street)
        cards: list[str] = []

        try:
            # Search for the board cards in the hand's streets
            if m := self.re_board.search(hand.streets[street]):
                log.debug("Regex matched for community cards on street: %s. Match groups: %s", street, m.groupdict())
                # Split the card string into a list of cards
                cards = m.group("CARDS").strip().split(" ")
                log.debug("Extracted raw cards: %s", cards)

                # Format the cards
                cards = [c[1:].replace("10", "T") + c[0].lower() for c in cards]
                log.debug("Formatted cards: %s", cards)

                # Set the community cards in the hand object
                hand.setCommunityCards(street, cards)
                log.debug("Community cards set for street %s: %s", street, cards)
            else:
                # Log an error if the board cards could not be found
                self._raise_community_cards_error(hand.handid, street)
        except Exception:
            log.exception(
                "Exception occurred while reading community cards for hand %s, street: %s",
                hand.handid,
                street,
            )
            raise

        log.debug("Exiting readCommunityCards for hand: %s, street: %s", hand.handid, street)

    def readAntes(self, hand: Any) -> None:
        """Reads the antes for each player in the given hand.

        Args:
            hand (Hand): The hand to read the antes from.

        Returns:
            None
        """
        log.debug("Entering readAntes for hand: %s", hand.handid)

        # Debug: show players in hand
        player_names = [player[1] for player in hand.players]
        log.debug("Players in hand: %s", player_names)

        # Find all the antes in the hand text using a regular expression
        m = self.re_action.finditer(hand.handText)
        log.debug("Searching for antes in hand text.")

        # Loop through each ante found
        for a in m:
            log.debug("Matched action: %s", a.groupdict())
            # If the ante is of type 15, add it to the hand
            if a.group("ATYPE") == "15":
                player_name = a.group("PNAME")
                ante_amount = self.clearMoneyString(a.group("BET"))
                log.debug("Adding ante for player: %s, amount: %s", player_name, ante_amount)

                # Check if player exists before adding ante
                if player_name not in player_names:
                    log.warning(
                        "Player %s not found in hand players list: %s. Skipping ante.",
                        player_name,
                        player_names,
                    )
                    continue

                hand.addAnte(player_name, ante_amount)

        log.debug("Exiting readAntes for hand: %s", hand.handid)

    def readBringIn(self, hand: Any) -> None:
        """Read the bring-in for a hand and set sb/bb values if not already set.

        Args:
            hand (Hand): The hand object for which to read the bring-in.

        Returns:
            None
        """
        log.debug("Entering readBringIn for hand: %s", hand.handid)
        if hand.gametype["sb"] is None and hand.gametype["bb"] is None:
            hand.gametype["sb"] = "1"  # default small blind value
            hand.gametype["bb"] = "2"  # default big blind value
            log.debug("Small blind and big blind not set. Default values assigned: sb=1, bb=2.")
        log.debug("Exiting readBringIn for hand: %s", hand.handid)

    def readBlinds(self, hand: Any) -> None:
        """Parses hand history to extract blind information for each player in the hand.

        :param hand: Hand object containing the hand history.
        :type hand: Hand
        """
        log.debug("Entering readBlinds for hand: %s", hand.handid)

        # Debug: show players in hand
        player_names = [player[1] for player in hand.players]
        log.debug("Players in hand: %s", player_names)

        # Find all actions in the preflop street
        log.debug("Searching for small blind actions in PREFLOP street.")
        for a in self.re_action.finditer(hand.streets["PREFLOP"]):
            if a.group("ATYPE") == "1":
                player_name = a.group("PNAME")
                sb_amount = self.clearMoneyString(a.group("BET"))
                log.debug("Small blind detected: Player=%s, Amount=%s", player_name, sb_amount)

                # Check if player exists before adding blind
                if player_name not in player_names:
                    log.warning(
                        "Player %s not found in hand players list: %s. Skipping small blind.",
                        player_name,
                        player_names,
                    )
                    continue

                hand.addBlind(player_name, "small blind", sb_amount)
                if not hand.gametype["sb"]:
                    hand.gametype["sb"] = sb_amount
                    log.debug("Small blind amount set in gametype: %s", sb_amount)

        # Find all actions in the preflop street for big blinds
        log.debug("Searching for big blind actions in PREFLOP street.")
        m = self.re_action.finditer(hand.streets["PREFLOP"])
        blinds = {
            int(a.group("ACT")): a.groupdict()
            for a in m
            if a.group("ATYPE") == "2" and a.group("PNAME") in player_names
        }
        log.debug("Big blinds found: %s players.", len(blinds))

        for b in sorted(blinds.keys()):
            blind = blinds[b]
            player_name = blind["PNAME"]
            bet_amount = self.clearMoneyString(blind["BET"])
            blind_type = "big blind"
            log.debug("Processing big blind: Player=%s, Amount=%s", player_name, bet_amount)

            if not hand.gametype["bb"]:
                hand.gametype["bb"] = bet_amount
                log.debug("Big blind amount set in gametype: %s", bet_amount)
            elif hand.gametype["sb"]:
                bb = Decimal(hand.gametype["bb"])
                amount = Decimal(bet_amount)
                if amount > bb:
                    blind_type = "both"
                    log.debug("Player %s posted both blinds: Amount=%s", player_name, bet_amount)
            hand.addBlind(player_name, blind_type, bet_amount)

        # Fix tournament blinds if necessary
        log.debug("Fixing tournament blinds if necessary.")
        self.fixTourBlinds(hand)

        log.debug("Exiting readBlinds for hand: %s", hand.handid)

    def fixTourBlinds(self, hand: Any) -> None:
        """Fix tournament blinds if small blind is missing or sb/bb is all-in.

        :param hand: A dictionary containing the game type information.
        :return: None
        """
        log.debug("Entering fixTourBlinds for hand: %s", hand.handid)
        if hand.gametype["type"] != "tour":
            log.debug("Hand type is not 'tour'. Exiting fixTourBlinds.")
            return

        log.debug("Initial gametype blinds: sb=%s, bb=%s", hand.gametype["sb"], hand.gametype["bb"])
        if hand.gametype["sb"] is None and hand.gametype["bb"] is None:
            hand.gametype["sb"] = "1"
            hand.gametype["bb"] = "2"
            log.debug("Blinds missing. Default values assigned: sb=1, bb=2.")
        elif hand.gametype["sb"] is None:
            hand.gametype["sb"] = str(int(int(hand.gametype["bb"]) // 2))
            log.debug("Small blind missing. Calculated and set to: sb=%s", hand.gametype["sb"])
        elif hand.gametype["bb"] is None:
            hand.gametype["bb"] = str(int(hand.gametype["sb"]) * 2)
            log.debug("Big blind missing. Calculated and set to: bb=%s", hand.gametype["bb"])

        if int(hand.gametype["bb"]) // 2 != int(hand.gametype["sb"]):
            if int(hand.gametype["bb"]) // 2 < int(hand.gametype["sb"]):
                hand.gametype["bb"] = str(int(hand.gametype["sb"]) * 2)
                log.debug("Big blind adjusted to match small blind: bb=%s", hand.gametype["bb"])
            else:
                hand.gametype["sb"] = str(int(hand.gametype["bb"]) // 2)
                log.debug("Small blind adjusted to match big blind: sb=%s", hand.gametype["sb"])
        log.debug("Final gametype blinds: sb=%s, bb=%s", hand.gametype["sb"], hand.gametype["bb"])
        log.debug("Exiting fixTourBlinds for hand: %s", hand.handid)

    def readButton(self, hand: Any) -> None:
        """Placeholder for future implementation of button reading."""
        log.debug("Entering readButton for hand: %s. Currently no implementation.", hand.handid)

    def readHoleCards(self, hand: Any) -> None:
        """Parse a Hand object to extract hole card information for each player on each street.

        Adds the hole card information to the Hand object.

        Args:
            hand: Hand object to extract hole card information from

        Returns:
            None
        """
        log.debug("Entering readHoleCards for hand: %s", hand.handid)

        # Process initial streets (PREFLOP, DEAL)
        self._process_initial_streets(hand)

        # Process remaining streets
        self._process_remaining_streets(hand)

        log.debug("Exiting readHoleCards for hand: %s", hand.handid)

    def _process_initial_streets(self, hand: Any) -> None:
        """Process initial streets (PREFLOP, DEAL) for hero's cards."""
        for street in ("PREFLOP", "DEAL"):
            if street in hand.streets:
                log.debug("Processing street: %s for hero's cards.", street)
                for found in self.re_hero_cards.finditer(hand.streets[street]):
                    player = found.group("PNAME")
                    cards = self._normalize_cards(found.group("CARDS").split(" "))

                    if hasattr(self, "hero") and player == self.hero and cards[0]:
                        hand.hero = player
                        log.debug("Hero identified: %s with cards: %s", player, cards)

                    # Check if player exists in hand before adding hole cards
                    player_names = [p[1] for p in hand.players]  # Extract player names from hand.players
                    if player not in player_names:
                        log.warning("Skipping hole cards for unknown player '%s' in hand '%s'", player, hand.handid)
                        continue

                    hand.addHoleCards(
                        street,
                        player,
                        closed=cards,
                        shown=True,
                        mucked=False,
                        dealt=True,
                    )

    def _process_remaining_streets(self, hand: Any) -> None:
        """Process remaining streets for all players."""
        for street, text in hand.streets.items():
            if not text or street in ("PREFLOP", "DEAL"):
                continue  # already done these
            log.debug("Processing street: %s for all players.", street)
            for found in self.re_hero_cards.finditer(text):
                player = found.group("PNAME")
                if player is not None:
                    self._process_player_hole_cards(hand, street, player, found)

    def _process_player_hole_cards(self, hand: Any, street: str, player: str, found: Any) -> None:
        """Process hole cards for a specific player on a specific street."""
        # Check if player exists in hand before processing hole cards
        player_names = [p[1] for p in hand.players]  # Extract player names from hand.players
        if player not in player_names:
            log.warning(
                "Skipping hole cards for unknown player '%s' in hand '%s' on street '%s'",
                player,
                hand.handid,
                street,
            )
            return

        cards = found.group("CARDS").split(" ")
        newcards, oldcards = self._categorize_cards(cards, street, player)

        if (
            street == "THIRD"
            and len(newcards) == self.THIRD_STREET_CARDS_COUNT
            and hasattr(self, "hero")
            and self.hero == player
        ):
            self._process_third_street_hero(hand, street, player, newcards)
        elif (
            street == "SECOND"
            and len(newcards) == self.SECOND_STREET_CARDS_COUNT
            and hasattr(self, "hero")
            and self.hero == player
        ):
            self._process_second_street_hero(hand, street, player, newcards)
        else:
            self._process_standard_hole_cards(hand, street, player, newcards, oldcards)

    def _normalize_cards(self, cards: list[str]) -> list[str]:
        """Normalize card format."""
        return [c[1:].replace("10", "T") + c[0].lower().replace("x", "") for c in cards]

    def _categorize_cards(self, cards: list[str], street: str, player: str) -> tuple[list[str], list[str]]:
        """Categorize cards into new and old cards based on street and player."""
        if street == "SEVENTH" and hasattr(self, "hero") and self.hero != player:
            newcards = []
            oldcards = [c[1:].replace("10", "T") + c[0].lower() for c in cards if c[0].lower() != "x"]
        else:
            newcards = [c[1:].replace("10", "T") + c[0].lower() for c in cards if c[0].lower() != "x"]
            oldcards = []
        return newcards, oldcards

    def _process_third_street_hero(self, hand: Any, street: str, player: str, newcards: list[str]) -> None:
        """Process hero cards on THIRD street."""
        hand.hero = player
        hand.dealt.add(player)
        hand.addHoleCards(
            street,
            player,
            closed=newcards[:2],
            open=[newcards[2]],
            shown=True,
            mucked=False,
            dealt=False,
        )
        log.debug("Hero cards on THIRD street: %s (closed), %s (open)", newcards[:2], newcards[2])

    def _process_second_street_hero(self, hand: Any, street: str, player: str, newcards: list[str]) -> None:
        """Process hero cards on SECOND street."""
        hand.hero = player
        hand.dealt.add(player)
        hand.addHoleCards(
            street,
            player,
            closed=[newcards[0]],
            open=[newcards[1]],
            shown=True,
            mucked=False,
            dealt=False,
        )
        log.debug("Hero cards on SECOND street: %s (closed), %s (open)", newcards[0], newcards[1])

    def _process_standard_hole_cards(
        self,
        hand: Any,
        street: str,
        player: str,
        newcards: list[str],
        oldcards: list[str],
    ) -> None:
        """Process standard hole cards."""
        hand.addHoleCards(
            street,
            player,
            open=newcards,
            closed=oldcards,
            shown=True,
            mucked=False,
            dealt=False,
        )
        log.debug("Player %s cards on %s: %s (open), %s (closed)", player, street, newcards, oldcards)

    def _process_action(self, hand: Any, street: str, action: dict) -> None:
        """Process a single action and add it to the hand."""
        atype = action["ATYPE"]
        player = action["PNAME"]
        bet = self.clearMoneyString(action["BET"])

        log.debug("Processing action: Player=%s, Type=%s, Bet=%s", player, atype, bet)

        action_handlers = {
            "0": lambda: hand.addFold(street, player),
            "4": lambda: hand.addCheck(street, player),
            "3": lambda: hand.addCall(street, player, bet),
            "23": lambda: hand.addRaiseTo(street, player, bet),
            "6": lambda: hand.addRaiseBy(street, player, bet),
            "5": lambda: hand.addBet(street, player, bet),
            "16": lambda: hand.addBringIn(player, bet),
            "7": lambda: hand.addAllIn(street, player, bet),
            "9": lambda: hand.addFold(street, player),
        }

        if atype in action_handlers:
            action_handlers[atype]()
            self._log_action_added(atype, player, street, bet)
        elif atype == "15":
            log.debug("Ante action skipped for player %s (handled in readAntes).", player)
        elif atype in ["1", "2", "8"]:
            log.debug("Blind or no-action skipped for player %s (Type=%s).", player, atype)
        else:
            log.error("Unimplemented readAction: Player=%s, Type=%s", player, atype)

    def _log_action_added(self, atype: str, player: str, street: str, bet: str) -> None:
        """Log the action that was added."""
        action_messages = {
            "0": f"Added fold for player {player} on street {street}.",
            "4": f"Added check for player {player} on street {street}.",
            "3": f"Added call for player {player} on street {street}, Bet={bet}.",
            "23": f"Added raise to {bet} for player {player} on street {street}.",
            "6": f"Added raise by {bet} for player {player} on street {street}.",
            "5": f"Added bet of {bet} for player {player} on street {street}.",
            "16": f"Added bring-in of {bet} for player {player}.",
            "7": f"Added all-in of {bet} for player {player} on street {street}.",
            "9": f"Player {player} sitting out, added fold for street {street}.",
        }

        if atype in action_messages:
            log.debug(action_messages[atype])

    def readAction(self, hand: Any, street: str) -> None:  # noqa: C901, PLR0912
        """Extracts actions from a hand and adds them to the corresponding street in a Hand object.

        Args:
            hand (Hand): Hand object to which the actions will be added.
            street (str): Name of the street in the hand (PREFLOP, FLOP, etc.).

        Returns:
            None
        """
        log.debug("Entering readAction for hand: %s, street: %s", hand.handid, street)

        # Debug: show players in hand
        player_names = [player[1] for player in hand.players]
        log.debug("Players in hand: %s", player_names)

        # HH format doesn't actually print the actions in order!
        matches = self.re_action.finditer(hand.streets[street])
        actions: dict[int, dict[str, Any]] = {}
        for match in matches:
            actions[int(match.group("ACT"))] = match.groupdict()

        for action_index in sorted(actions):
            action = actions[action_index]
            atype = action["ATYPE"]
            player = action["PNAME"]
            bet = self.clearMoneyString(action["BET"])
            log.debug("Processing action: street=%s, player=%s, atype=%s, bet=%s", street, player, atype, bet)

            # Check if player exists in hand before processing actions
            if player not in player_names:
                log.warning(
                    "Player %s not found in hand players list: %s. Skipping action type %s.",
                    player,
                    player_names,
                    atype,
                )
                continue

            if atype == "0":
                hand.addFold(street, player)
            elif atype == "4":
                hand.addCheck(street, player)
            elif atype == "3":
                hand.addCall(street, player, bet)
            elif atype == "23":  # Raise to
                hand.addRaiseTo(street, player, bet)
            elif atype == "6":  # Raise by
                hand.addRaiseBy(street, player, bet)
            elif atype == "5":
                hand.addBet(street, player, bet)
            elif atype == "16":  # BringIn
                hand.addBringIn(player, bet)
            elif atype == "7":
                hand.addAllIn(street, player, bet)
            elif atype == "15":  # Ante
                pass  # Antes dealt with in readAntes
            elif atype in ("1", "2", "8"):  # sb/bb/no action this hand (joined table)
                pass
            elif atype == "9":  # Sitting out
                hand.addFold(street, player)
            else:
                log.error("Unimplemented readAction: player='%s' atype='%s'", player, atype)

        log.debug("Exiting readAction for hand: %s, street: %s", hand.handid, street)

    def readShowdownActions(self, hand: Any) -> None:
        """Reads showdown actions and updates the hand object.

        Args:
            hand (Hand): The hand object to update with showdown actions.

        Returns:
            None
        """
        log.debug("Entering readShowdownActions for hand: %s", hand.handid)
        # Placeholder for showdown action logic
        log.debug("Currently no implementation for readShowdownActions.")
        log.debug("Exiting readShowdownActions for hand: %s", hand.handid)

    def readCollectPot(self, hand: Any) -> None:
        """Read and process pot collection information.

        Args:
            hand: The hand object to update with pot information
        """
        log.info("Entering readCollectPot method")

        # Enable uncalled bets
        hand.setUncalledBets(True)

        # Initialize total pot to zero
        total_pot = Decimal("0.00")

        # Go through player information to identify collected pots
        for m in self.re_player_info.finditer(hand.handText):
            player = m.group("PNAME")
            pot = m.group("WIN")
            if pot:  # Check if win amount is present
                pot_value = self.clearMoneyString(pot)
                total_pot += Decimal(pot_value)  # Add the amount to the total pot
                hand.addCollectPot(player=player, pot=pot_value)
                log.debug("Player collected pot method: readCollectPot, player: %s, amount: %s", player, pot_value)
            else:
                log.debug("No winnings recorded for player: %s", player)

        # Add the rake to the total pot
        total_pot += hand.rake or Decimal("0.00")

        # Update total pot in hand object
        hand.totalpot = total_pot
        log.debug("Total pot calculated: %s, Total rake: %s", hand.totalpot, hand.rake)

        log.info("Exiting readCollectPot method")

    def readShownCards(self, hand: Any) -> None:
        """Reads shown cards and updates the hand object.

        Args:
            hand (Hand): The hand object to update with shown cards.

        Returns:
            None
        """
        log.debug("Entering readShownCards for hand: %s", hand.handid)
        # Placeholder for shown cards logic
        log.debug("Currently no implementation for readShownCards.")
        log.debug("Exiting readShownCards for hand: %s", hand.handid)
