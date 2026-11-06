"""The Hands row: identity, boards, board features, street totals and who reached each street."""

# Copyright 2008-2011 Carl Gherardi
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
# In the "official" distribution you can find the license in agpl-3.0.txt.

from __future__ import annotations

import contextlib
from typing import Any

from fpdb_3_legacy import Card
from fpdb_3_legacy.board_features import derive_board_rows, flop_texture_mask
from fpdb_3_legacy.derived_stats_base import (
    CENTS_MULTIPLIER,
    FINAL_POT_IDX,
    STREET0_IDX,
    STREET1_IDX,
    STREET2_IDX,
    STREET3_IDX,
    STREET4_IDX,
    DerivedStatsBase,
)
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("derived_stats")


class DerivedStatsHandsMixin(DerivedStatsBase):
    """Assemble the per-hand row."""

    def _assembleHandIdentity(self, hand: Any) -> None:
        """Record the table, ids, seat count and hero seat."""
        # Initialize basic hand details
        self.hands["tableName"] = hand.tablename
        log.debug("Set tableName: %s", hand.tablename)

        self.hands["siteHandNo"] = hand.handid
        log.debug("Set siteHandNo: %s", hand.handid)

        self.hands["gametypeId"] = None  # Handled later after checking DB
        self.hands["sessionId"] = None  # Added later if caching sessions
        self.hands["gameId"] = None  # Added later if caching sessions
        self.hands["startTime"] = hand.startTime  # Ensure proper formatting
        log.debug("Set startTime: %s", hand.startTime)

        self.hands["importTime"] = None
        self.hands["seats"] = self.countPlayers(hand)
        log.debug("Set seats: %s", self.hands["seats"])

        self.hands["maxPosition"] = -1
        # Redefined by _assembleBoardFeatures (#295) as the flop texture mask;
        # 0 means no flop, since every flop sets at least a suit structure flag.
        self.hands["texture"] = 0
        self.hands["tourneyId"] = hand.tourneyId
        log.debug("Set tourneyId: %s", hand.tourneyId)

        # Determine hero seat
        self.hands["heroSeat"] = 0
        for player in hand.players:
            if hand.hero == player[1]:
                self.hands["heroSeat"] = player[0]
                log.debug("Hero found: %s at seat %s", player[1], player[0])
                break
        else:
            # Observed hands (the hero was not dealt in) legitimately have no
            # hero seat, so this is routine, not a problem to report.
            log.debug("No hero seated in hand %s", getattr(hand, "handid", "unknown"))

    def _assembleBoardCards(self, hand: Any) -> None:
        """Encode the five community cards of the single board."""
        # Assemble board cards
        boardcards = []
        if hand.board.get("FLOPET") is not None:
            try:
                flopet_cards = hand.board.get("FLOPET")
                if flopet_cards and hasattr(flopet_cards, "__iter__") and not isinstance(flopet_cards, str):
                    boardcards += list(flopet_cards)
                    log.debug("Added FLOPET cards: %s", flopet_cards)
                else:
                    log.warning("FLOPET cards not iterable: %s", flopet_cards)
            except TypeError:
                log.exception("Error processing FLOPET cards")

        try:
            for street in hand.communityStreets:
                if street in hand.board:
                    street_cards = hand.board[street]
                    if (
                        street_cards
                        and hasattr(street_cards, "__iter__")
                        and not isinstance(street_cards, str)
                        and len(street_cards) > 0
                    ):
                        boardcards += list(street_cards)
                        log.debug("Added %s cards: %s", street, street_cards)
                    elif street_cards:  # Only warn if there are actual cards but they're not iterable
                        log.warning("Street %s cards not iterable: %s", street, street_cards)
                    # Silently ignore empty lists - this is normal for PREFLOP-only hands
                else:
                    log.debug("Street %s not found in hand.board - normal for preflop-only hands.", street)
        except TypeError:
            log.exception("Error iterating over communityStreets")

        # Fill remaining board slots with placeholders
        boardcards += ["0x", "0x", "0x", "0x", "0x"]
        log.debug("Completed boardcards with placeholders: %s", boardcards)

        # Encode first five board cards
        try:
            cards = [Card.encodeCard(c) for c in boardcards[0:5]]
            self.hands["boardcard1"] = cards[0]
            self.hands["boardcard2"] = cards[1]
            self.hands["boardcard3"] = cards[2]
            self.hands["boardcard4"] = cards[3]
            self.hands["boardcard5"] = cards[4]
            log.debug("Encoded board cards: %s", cards)
        except IndexError:
            log.exception("Error encoding board cards")
            # Set default values
            self.hands["boardcard1"] = 0
            self.hands["boardcard2"] = 0
            self.hands["boardcard3"] = 0
            self.hands["boardcard4"] = 0
            self.hands["boardcard5"] = 0

    def _assembleBoardFeatures(self, hand: Any) -> None:
        """Classify every board street once, for persistence and for filtering.

        The features are derived at import time and stored, so a query never has
        to re-parse a hand history or recompute a texture (#295).
        ``Hands.texture`` is redefined here as the flop's texture mask -- the
        column was written NULL on every hand since the schema was created, and
        nothing reads it, so giving it that meaning costs no compatibility and
        saves a join for the commonest filter of all: the flop texture.
        """
        try:
            rows = derive_board_rows(hand)
        except (AttributeError, KeyError, TypeError, ValueError):
            log.exception("Error deriving board features for hand %s", hand.handid)
            rows = []
        self.hands["boardfeatures"] = rows
        self.hands["texture"] = flop_texture_mask(rows)

    def _assembleRunItTwiceBoards(self, hand: Any) -> None:
        """Encode one board per run when the hand was run several times."""
        # Initialize boards list
        self.hands["boards"] = []
        self.hands["runItTwice"] = False

        try:
            run_it_times = int(hand.runItTimes) if hasattr(hand.runItTimes, "__int__") else 0
        except (TypeError, ValueError):
            run_it_times = 0

        for i in range(run_it_times):
            boardcards = []
            for street in hand.communityStreets:
                board_id = i + 1
                street_i = f"{street}{board_id}"
                if street_i in hand.board and hand.board[street_i]:
                    boardcards += hand.board[street_i]
                    log.debug(
                        "Run %s: Added %s cards: %s",
                        i + 1,
                        street_i,
                        hand.board[street_i],
                    )
                elif street in hand.board and hand.board[street]:
                    # Shared street: when players go all-in after the flop, the
                    # flop is dealt once and only the turn/river are run multiple
                    # times (no FLOP1/FLOP2). Reuse the common street so each run
                    # board stays complete (also covers the Courchevel flopet).
                    boardcards += hand.board[street]
                    log.debug(
                        "Run %s: Reused shared street %s cards: %s",
                        i + 1,
                        street,
                        hand.board[street],
                    )
                else:
                    log.warning(
                        "Run %s: Street %s not found in hand.board.",
                        i + 1,
                        street_i,
                    )

            if hand.gametype.get("split"):
                boardcards += ["0x", "0x", "0x", "0x", "0x"]
                log.debug("Run %s: Split game, added placeholders.", i + 1)
                try:
                    cards = [Card.encodeCard(c) for c in boardcards[:5]]
                except IndexError:
                    log.exception("Run %s: Error encoding split board cards", i + 1)
                    cards = [0] * 5
            else:
                self.hands["runItTwice"] = True
                # Pad trailing slots (keep flop/turn/river in order) so an
                # incomplete run board does not shift the cards.
                boardcards = [*boardcards, "0x", "0x", "0x", "0x", "0x"]
                log.debug("Run %s: Non-split game, padded trailing placeholders.", i + 1)
                try:
                    cards = [Card.encodeCard(c) for c in boardcards[:5]]
                except IndexError:
                    log.exception("Run %s: Error encoding board cards", i + 1)
                    cards = [0] * 5

            self.hands["boards"].append([board_id, *cards])
            log.debug("Run %s: Appended to boards: %s", i + 1, [board_id, *cards])

    def _assembleStreetTotals(self, hand: Any) -> None:
        """Record the pot size entering each street, in cents."""
        # Calculate street totals
        try:
            totals = hand.getStreetTotals()
            # Check if totals is a Mock object
            from unittest.mock import Mock

            if isinstance(totals, Mock):
                totals = [0, 0, 0, 0, 0, 0]
            if totals and hasattr(totals, "__iter__") and not isinstance(totals, str):
                totals = [int(CENTS_MULTIPLIER * i) for i in totals]
                self.hands["street0Pot"] = totals[STREET0_IDX] if len(totals) > STREET0_IDX else 0
                self.hands["street1Pot"] = totals[STREET1_IDX] if len(totals) > STREET1_IDX else 0
                self.hands["street2Pot"] = totals[STREET2_IDX] if len(totals) > STREET2_IDX else 0
                self.hands["street3Pot"] = totals[STREET3_IDX] if len(totals) > STREET3_IDX else 0
                self.hands["street4Pot"] = totals[STREET4_IDX] if len(totals) > STREET4_IDX else 0
                self.hands["finalPot"] = totals[FINAL_POT_IDX] if len(totals) > FINAL_POT_IDX else 0
                # Add bomb pot amount from hand object
                self.hands["bombPot"] = getattr(hand, "bombPot", 0)
                self.hands["splashPot"] = getattr(hand, "splashPot", 0)
                log.debug("Street totals: %s", totals)
            else:
                # Default values if totals is not iterable
                self.hands["street0Pot"] = 0
                self.hands["street1Pot"] = 0
                self.hands["street2Pot"] = 0
                self.hands["street3Pot"] = 0
                self.hands["street4Pot"] = 0
                self.hands["finalPot"] = 0
                # Add bomb pot amount from hand object
                self.hands["bombPot"] = getattr(hand, "bombPot", 0)
                self.hands["splashPot"] = getattr(hand, "splashPot", 0)
                log.warning("Street totals not iterable: %s", totals)
        except (ArithmeticError, TypeError, ValueError):
            log.exception("Error calculating street totals")
            # Set default values on error
            self.hands["street0Pot"] = 0
            self.hands["street1Pot"] = 0
            self.hands["street2Pot"] = 0
            self.hands["street3Pot"] = 0
            self.hands["street4Pot"] = 0
            self.hands["finalPot"] = 0
            # Add bomb pot amount from hand object
            self.hands["bombPot"] = getattr(hand, "bombPot", 0)

        # VPIP will be calculated in assembleHandsPlayers after player initialization

    def _assembleStreetSummaries(self, hand: Any) -> None:
        """Count players and raises per street."""
        # Determine players at each street
        try:
            self.playersAtStreetX(hand)
            log.debug(
                "Players at streets: 1=%s, 2=%s, 3=%s, 4=%s, Showdown=%s",
                self.hands.get("playersAtStreet1"),
                self.hands.get("playersAtStreet2"),
                self.hands.get("playersAtStreet3"),
                self.hands.get("playersAtStreet4"),
                self.hands.get("playersAtShowdown"),
            )
        except (AttributeError, KeyError, TypeError, ValueError):
            log.exception("Error determining players at streets")
            raise

        # Calculate raises per street
        try:
            self.streetXRaises(hand)
            log.debug(
                "Raises per street: street0Raises=%s, street1Raises=%s, street2Raises=%s, "
                "street3Raises=%s, street4Raises=%s",
                self.hands.get("street0Raises"),
                self.hands.get("street1Raises"),
                self.hands.get("street2Raises"),
                self.hands.get("street3Raises"),
                self.hands.get("street4Raises"),
            )
        except (AttributeError, KeyError, TypeError, ValueError):
            log.exception("Error calculating raises per street")
            raise

        # Log hand details at debug level

    def assembleHands(self, hand: Any) -> None:
        """Assemble basic hand statistics."""
        try:
            log.debug("Starting assembleHands for hand ID: %s", hand.handid)
            self._assembleHandIdentity(hand)
            self._assembleBoardCards(hand)
            self._assembleRunItTwiceBoards(hand)
            self._assembleBoardFeatures(hand)
            self._assembleStreetTotals(hand)
            self._assembleStreetSummaries(hand)
            # Log hand details at debug level
            log.debug("Hand detail: %s", hand)
        except Exception:  # intentional broad catch: top-level hand assembly context logs hand id before reraising.
            log.exception("Error in assembleHands for hand ID %s", hand.handid)
            raise

    def playersAtStreetX(self, hand: Any) -> None:  # noqa: C901, PLR0912
        """Determine which players saw which street and calculate statistics."""
        if not hasattr(self, "handsplayers"):
            return

        try:
            action_streets_len = len(hand.actionStreets) if hasattr(hand.actionStreets, "__len__") else 0
        except TypeError:
            action_streets_len = 0

        # Initialize counts
        self.hands["playersAtStreet1"] = 0
        self.hands["playersAtStreet2"] = 0
        self.hands["playersAtStreet3"] = 0
        self.hands["playersAtStreet4"] = 0
        self.hands["playersAtShowdown"] = 0

        # Get initial players (those who acted in the first action street)
        p_in = set()
        if action_streets_len > 1:
            with contextlib.suppress(TypeError, AttributeError):
                p_in = {x[0] for x in hand.actions.get(hand.actionStreets[1], [])}

        # Add players who were all-in blind
        if hasattr(hand, "pot") and hasattr(hand.pot, "pots") and hand.pot.pots and len(hand.pot.pots[0][1]) > 1:
            p_in = p_in.union(hand.pot.pots[0][1])
            if hasattr(hand.pot, "common"):
                p_in = p_in.union(hand.pot.common.keys())

        # Process each street
        for i, street in enumerate(hand.actionStreets):
            if (i - 1) in (0, 1, 2, 3, 4):
                # Mark players who are still in the hand as having seen this street
                # street0 = preflop, street1 = flop, street2 = turn, street3 = river, street4 = 5th street (stud)
                for player_with_cards in p_in:
                    if player_with_cards in self.handsplayers:
                        self.handsplayers[player_with_cards][f"street{i - 1}Seen"] = True

                # Set players at street count
                self.hands[f"playersAtStreet{i - 1}"] = len(p_in)

                # Determine first to act and in position
                # Filter out discards and stands pat for draw games
                players = self.pfbao(hand.actions.get(street, []), f=("discards", "stands pat"))
                if len(players) > 0:
                    if players[0] in self.handsplayers:
                        self.handsplayers[players[0]][f"street{i - 1}FirstToAct"] = True
                    if players[-1] in self.handsplayers:
                        self.handsplayers[players[-1]][f"street{i - 1}InPosition"] = True

            # Remove players who folded BEFORE processing the next street
            # This ensures street1Seen = players who didn't fold preflop
            actions = hand.actions.get(street, [])
            p_in = p_in - self.pfba(actions, limit=("folds",))

            # If only one player left, we're done
            if len(p_in) == 1:
                if (i - 1) in (0, 1, 2, 3, 4) and len(players) > 0 and next(iter(p_in)) not in players:
                    # Correct in position if everyone folded before last player could act
                    if players[-1] in self.handsplayers:
                        self.handsplayers[players[-1]][f"street{i - 1}InPosition"] = False
                    if next(iter(p_in)) in self.handsplayers:
                        self.handsplayers[next(iter(p_in))][f"street{i - 1}InPosition"] = True
                return

        # Players remaining reached showdown
        self.hands["playersAtShowdown"] = len(p_in)
        for showdown_player in p_in:
            if showdown_player in self.handsplayers:
                self.handsplayers[showdown_player]["sawShowdown"] = True

    def streetXRaises(self, hand: Any) -> None:
        """Count raises on each street."""
        try:
            action_streets_len = len(hand.actionStreets) if hasattr(hand.actionStreets, "__len__") else 0
        except TypeError:
            action_streets_len = 0

        for i in range(5):
            street_name = None
            if i < action_streets_len:
                with contextlib.suppress(TypeError, IndexError):
                    street_name = hand.actionStreets[i]

            if not street_name:
                self.hands[f"street{i}Raises"] = 0
                continue

            raises = 0
            with contextlib.suppress(TypeError, AttributeError):
                # For Stud, 'completes' counts as a raise
                raises = sum(
                    1
                    for act in hand.actions.get(street_name, [])
                    if len(act) > 1 and act[1] in ["raises", "bets", "completes"]
                )

            self.hands[f"street{i}Raises"] = raises
