#!/usr/bin/env python
from __future__ import annotations

"""DerivedStats module for calculating poker statistics."""

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

# fpdb modules

import contextlib
import os
from decimal import ROUND_DOWN, Decimal
from typing import Any

from fpdb_3_legacy import Card
from fpdb_3_legacy.equity import EquityUnavailableError, calculate_equity, expected_pot_share, load_poker_eval
from fpdb_3_legacy.loggingFpdb import get_logger

pokereval = load_poker_eval()


# logging has been set up in fpdb.py or HUD_main.py, use their settings:
log = get_logger("derived_stats")

# Constants for street indices
STREET0_IDX = 0
STREET1_IDX = 1
STREET2_IDX = 2
STREET3_IDX = 3
STREET4_IDX = 4
FINAL_POT_IDX = 5

# Constants for action indices
ACTION_PLAYER_IDX = 0
ACTION_TYPE_IDX = 1
ACTION_AMOUNT_IDX = 2
ACTION_RAISETO_IDX = 3
ACTION_CALLED_IDX = 4
ACTION_CARDS_DISCARDED_IDX = 3
MIN_ACTION_LENGTH_FOR_ALLIN = 3

# Constants for other common values
CENTS_MULTIPLIER = 100
MIN_STREETS_FOR_PREFLOP = 2
MIN_PLAYERS_FOR_GAME = 2
MIN_ACTIONS_FOR_CHECK_CALL_RAISE = 2
MIN_PLAYER_TUPLE_LENGTH = 2

def _to_decimal(value: Any) -> Decimal:
    """Best-effort Decimal conversion. Accepts numbers and numeric strings
    (parsers store blinds as strings); returns 0 for anything else (e.g. mocks)."""
    try:
        return Decimal(str(value))
    except (TypeError, ValueError, ArithmeticError):
        return Decimal(0)


def _pot_stp(hand: Any) -> Decimal:
    """Bomb / 'Escape to Pot' money seeded into the pot (currency units, 0 if absent)."""
    return _to_decimal(getattr(getattr(hand, "pot", None), "stp", 0))


# Constants for betting levels
THREE_BET_LEVEL = 2
FOUR_BET_LEVEL = 3
FOLD_TO_4BET_LEVEL = 4

# Constants for poker evaluations
MIN_POSTFLOP_BOARD_SIZE = 3
MIN_MAXCARDS_SIZE = 5
ANTE_ALL_IN_POSITION = 9
MIN_RUN_IT_TIMES = 2


def _chip_increment(factor: int) -> Decimal:
    """Return the smallest distributable unit without mixing Decimal and float."""
    return Decimal(1) / Decimal(factor)


def _buildStatsInitializer() -> dict:  # noqa: PLR0915
    # TODO @future: REFACTOR - This function is too long (79 statements > 50)
    # Consider breaking into smaller functions for different stat categories
    init: dict[str, Any] = {}
    # Init vars that may not be used, but still need to be inserted.
    # All stud street4 need this when importing holdem
    init["effStack"] = 0
    init["startBounty"] = None
    init["endBounty"] = None
    init["common"] = 0
    init["committed"] = 0
    init["winnings"] = 0
    init["rake"] = 0
    init["rakeDealt"] = 0
    init["rakeContributed"] = 0
    init["rakeWeighted"] = 0
    init["totalProfit"] = 0
    init["allInEV"] = 0
    init["showdownWinnings"] = 0
    init["nonShowdownWinnings"] = 0
    init["cashOutAmount"] = 0  # Insurance payout (not pot winnings)
    init["cashOutFee"] = 0  # Fee deducted from cash out
    init["sawShowdown"] = False
    init["showed"] = False
    init["wonAtSD"] = False
    init["flg_won_hand"] = False
    init["startCards"] = 170
    init["handString"] = None
    init["position"] = 9  # ANTE ALL IN
    init["seat"] = 0  # Player's seat number at the table
    init["cnt_players"] = 0  # Total number of players at the table
    init["flg_blind_s"] = False  # Player is small blind
    init["flg_blind_b"] = False  # Player is big blind
    # Special blinds (PT4 parity). ds = dead small blind, db = dead big blind,
    # k = straddle. fpdb routes dead blinds to "secondsb"/"both"; it has no
    # standalone dead-big-blind action, so flg_blind_db stays False until a
    # parser provides one (kept for PT4 column-shape parity).
    init["flg_blind_ds"] = False  # Player posted a dead small blind
    init["flg_blind_db"] = False  # Player posted a dead big blind (see note)
    init["flg_blind_k"] = False  # Player straddled (voluntary kill blind)
    init["street0CalledRaiseChance"] = 0
    init["street0CalledRaiseDone"] = 0
    init["street0FaceRaise"] = False
    init["street0VPIChance"] = True
    init["street0VPI"] = False
    init["street0AggrChance"] = True
    # Limp stats (modern addition for parity with PT4/modern)
    init["street0Limp"] = False  # limp_done: Any limp (open or over-limp)
    init["street0OpenLimp"] = False  # open_limp_done: First to limp (no prior limpers)
    init["street0OpenLimpChance"] = False  # open_limp_opp: faced an unopened pot
    init["street0_2BChance"] = False
    init["street0_2BDone"] = False
    init["street0_3BChance"] = False
    init["street0_3BDone"] = False
    init["street0_4BChance"] = False
    init["street0_4BDone"] = False
    init["street0_C4BChance"] = False
    init["street0_C4BDone"] = False
    init["street0_FoldTo2BChance"] = False
    init["street0_FoldTo2BDone"] = False
    init["street0_FoldTo3BChance"] = False
    init["street0_FoldTo3BDone"] = False
    init["street0_FoldTo4BChance"] = False
    init["street0_FoldTo4BDone"] = False
    init["street0_SqueezeChance"] = False
    init["street0_SqueezeDone"] = False
    # Squeeze defense: opportunity (faced a squeeze 3-bet) and fold response.
    # Mirrors PT4 flg_p_squeeze_def_opp; the paired "Done" lets the HUD show a
    # fold-to-squeeze percentage.
    init["street0_FoldToSqueezeChance"] = False
    init["street0_FoldToSqueezeDone"] = False
    # Number of limpers a player faced before their first preflop action
    # (PT4 cnt_p_face_limpers). Count, aggregated as a sum in HudCache.
    init["street0_FaceLimpers"] = 0
    # "GenerationPoker" open-sizing / limp counts (PT4 cnt_gp_* custom pack):
    # open opportunity (denominator), normal open ("2X"), open-shove ("OS",
    # an open committing >= 40% of own stack) and limp. Summed for HudCache.
    init["cnt_gp_open_opp"] = 0
    init["cnt_gp_2x"] = 0
    init["cnt_gp_os"] = 0
    init["cnt_gp_limp"] = 0
    # Bet-sizing: size of the preflop raise faced, per level, as basis points of
    # the pot before the raise (PT4 amt_p_{2,3,4}bet_facing / val_*_pct). cnt =
    # opportunity, val = raise-to * 10000 / pot, summed for HudCache.
    init["cnt_p_2bet_facing"] = 0
    init["val_p_2bet_facing_bp"] = 0
    init["cnt_p_3bet_facing"] = 0
    init["val_p_3bet_facing_bp"] = 0
    init["cnt_p_4bet_facing"] = 0
    init["val_p_4bet_facing_bp"] = 0
    # Postflop per-street re-raise stats. street1 = flop, street2 = turn,
    # street3 = river.
    for _s in (1, 2, 3):
        init[f"street{_s}_3BChance"] = False
        init[f"street{_s}_3BDone"] = False
        init[f"street{_s}_FoldTo3BChance"] = False
        init[f"street{_s}_FoldTo3BDone"] = False
        init[f"street{_s}_4BChance"] = False
        init[f"street{_s}_4BDone"] = False
        init[f"street{_s}_FoldTo4BChance"] = False
        init[f"street{_s}_FoldTo4BDone"] = False
        init[f"street{_s}OpenChance"] = False
        init[f"street{_s}OpenDone"] = False
        init[f"street{_s}FirstRaise"] = False
        init[f"street{_s}FaceRaise"] = False
    init["stealChance"] = False
    init["stealDone"] = False
    init["success_Steal"] = False
    init["raiseToStealChance"] = False
    init["raiseToStealDone"] = False
    init["raiseFirstInChance"] = False
    init["raisedFirstIn"] = False
    init["foldBbToStealChance"] = False
    init["foldSbToStealChance"] = False
    init["foldedSbToSteal"] = False
    init["foldedBbToSteal"] = False
    init["tourneyTypeId"] = None
    init["street1Seen"] = False
    init["street2Seen"] = False
    init["street3Seen"] = False
    init["street4Seen"] = False
    init["otherRaisedStreet0"] = False
    init["foldToOtherRaisedStreet0"] = False
    init["wentAllIn"] = False
    # Faced an all-in (an opponent's all-in bet/raise put the player to a
    # decision) and whether they folded to it (PT4 enum_face_allin, modelled
    # the fpdb way as a chance/done boolean pair).
    init["flg_faced_allin"] = False
    init["flg_fold_to_allin"] = False

    for i in range(5):
        init["street%dCalls" % i] = 0
        init["street%dBets" % i] = 0
        init["street%dRaises" % i] = 0
        init["street%dAggr" % i] = False
        init["street%dInPosition" % i] = False
        init["street%dFirstToAct" % i] = False
        init["street%dAllIn" % i] = False

    for i in range(1, 4):
        init["street%dDiscards" % i] = 0

    for i in range(1, 5):
        init["street%dCBChance" % i] = False
        init["street%dCBDone" % i] = False
        init["street%dCheckCallRaiseChance" % i] = False
        init["street%dCheckCallDone" % i] = False
        init["street%dCheckRaiseDone" % i] = False
        init["otherRaisedStreet%d" % i] = False
        init["foldToOtherRaisedStreet%d" % i] = False
        init["foldToStreet%dCBChance" % i] = False
        init["foldToStreet%dCBDone" % i] = False
        init["wonWhenSeenStreet%d" % i] = False

    # Delayed turn continuation bet: PFR checked the flop (declined the c-bet),
    # then opens the turn. See calcCBets().
    init["street2DelayedCBChance"] = False
    init["street2DelayedCBDone"] = False

    # Turn probe bet: a non-PFR opens the turn after the PFR checked the flop
    # (showed weakness). See calcCBets().
    init["street2ProbeChance"] = False
    init["street2ProbeDone"] = False

    # Cash out fees (stored in cents) and cash out flag
    init["cashOutFee"] = 0
    init["isCashOut"] = False

    # Flop statistics
    init["flg_f_donk"] = False
    init["flg_f_donk_opp"] = False
    init["flg_f_donk_def_opp"] = False
    init["flg_f_has_position"] = False
    init["flg_f_first"] = False
    init["flg_f_fold"] = False
    # Bet-sizing: flop bet faced. cnt = opportunity (faced the first flop bet);
    # val = that bet as basis points of the pot before the bet (bet*10000/pot).
    # Stored as scaled integers so they aggregate in the INT-only HudCache; the
    # HUD averages val_sum / cnt (PT4 amt_f_bet_facing / val_f_bet_facing_pct).
    init["cnt_f_bet_facing"] = 0
    init["val_f_bet_facing_bp"] = 0
    # Bet-sizing: flop bet made (the bettor's own first-bet size, % of pot).
    init["cnt_f_bet_made"] = 0
    init["val_f_bet_made_bp"] = 0
    # Bet-sizing: flop SPR (effective stack / pot entering the flop, x100).
    init["cnt_f_spr"] = 0
    init["val_f_spr"] = 0

    # Turn statistics
    init["flg_t_float"] = False
    init["flg_t_float_opp"] = False
    init["flg_t_float_def_opp"] = False
    init["flg_t_donk"] = False
    init["flg_t_donk_opp"] = False
    init["flg_t_donk_def_opp"] = False
    init["flg_t_has_position"] = False
    init["flg_t_first"] = False
    init["flg_t_fold"] = False
    # Bet-sizing: turn bet faced (see flop equivalent above).
    init["cnt_t_bet_facing"] = 0
    init["val_t_bet_facing_bp"] = 0
    # Bet-sizing: turn bet made.
    init["cnt_t_bet_made"] = 0
    init["val_t_bet_made_bp"] = 0
    # Bet-sizing: turn SPR.
    init["cnt_t_spr"] = 0
    init["val_t_spr"] = 0

    # River statistics
    init["flg_r_float"] = False
    init["flg_r_float_opp"] = False
    init["flg_r_float_def_opp"] = False
    init["flg_r_donk"] = False
    init["flg_r_donk_opp"] = False
    init["flg_r_donk_def_opp"] = False
    init["flg_r_has_position"] = False
    init["flg_r_first"] = False
    init["flg_r_fold"] = False
    # Bet-sizing: river bet faced (see flop equivalent above).
    init["cnt_r_bet_facing"] = 0
    init["val_r_bet_facing_bp"] = 0
    # Bet-sizing: river bet made.
    init["cnt_r_bet_made"] = 0
    init["val_r_bet_made_bp"] = 0
    # Bet-sizing: river SPR.
    init["cnt_r_spr"] = 0
    init["val_r_spr"] = 0
    # Bet-sizing: size of the first raise the player makes per street, as basis
    # points of the pot before the raise (PT4 amt_*_raise_made / val_*_pct).
    init["cnt_p_raise_made"] = 0
    init["val_p_raise_made_bp"] = 0
    init["cnt_f_raise_made"] = 0
    init["val_f_raise_made_bp"] = 0
    init["cnt_t_raise_made"] = 0
    init["val_t_raise_made_bp"] = 0
    init["cnt_r_raise_made"] = 0
    init["val_r_raise_made_bp"] = 0
    # Bet-sizing: postflop raise faced per street and level (2/3/4-bet), as basis
    # points of the pot before the raise (PT4 amt_{f,t,r}_{2,3,4}bet_facing).
    for street_code in ("f", "t", "r"):
        for _lvl in (2, 3, 4):
            init[f"cnt_{street_code}_{_lvl}bet_facing"] = 0
            init[f"val_{street_code}_{_lvl}bet_facing_bp"] = 0
    # Bet-sizing completion (low-value / parity):
    # Raw amounts invested per street (cents) + blinds + total.
    init["amt_blind"] = 0
    init["amt_bet_p"] = 0
    init["amt_bet_f"] = 0
    init["amt_bet_t"] = 0
    init["amt_bet_r"] = 0
    init["amt_bet_ttl"] = 0
    # Generic raise faced per street (first raise faced, any level), basis points.
    for street_code in ("p", "f", "t", "r"):
        init[f"cnt_{street_code}_raise_facing"] = 0
        init[f"val_{street_code}_raise_facing_bp"] = 0
    # Size of the player's *second* raise per street, basis points.
    for street_code in ("p", "f", "t", "r"):
        init[f"cnt_{street_code}_raise_made_2"] = 0
        init[f"val_{street_code}_raise_made_2_bp"] = 0
    # Preflop 5-bet faced (rare), basis points.
    init["cnt_p_5bet_facing"] = 0
    init["val_p_5bet_facing_bp"] = 0

    return init


_INIT_STATS = _buildStatsInitializer()


class DerivedStats:
    """Calculate derived statistics for poker hands."""

    def __init__(self) -> None:
        """Initialize DerivedStats instance."""
        self.hands: dict[str, Any] = {}
        self.handsplayers: dict[str, dict[str, Any]] = {}
        self.handsactions: dict[Any, Any] = {}
        self.handsstove: list[Any] = []
        self.handspots: list[Any] = []

        # Check environment variable for rake rounding mode
        self.use_round_down = os.environ.get("FPDB_RAKE_ROUND_DOWN", "true").lower() in ("true", "1", "yes")
        log.debug("Rake rounding mode: %s", "ROUND_DOWN" if self.use_round_down else "default")

    def getStats(self, hand: Any) -> None:
        """Calculate and store statistics for a poker hand."""
        for player in hand.players:
            self.handsplayers[player[1]] = _INIT_STATS.copy()

        self.assembleHands(hand)
        self.assembleHandsPlayers(hand)
        self.assembleHandsActions(hand)

        if pokereval and hand.gametype["category"] in Card.games and getattr(hand, "playerIds", None):
            self.assembleHandsStove(hand)
            self.assembleHandsPots(hand)

    def getHands(self) -> dict:
        """Get hands statistics."""
        return self.hands

    def getHandsPlayers(self) -> dict:
        """Get hands players statistics."""
        return self.handsplayers

    def getHandsActions(self) -> dict:
        """Get hands actions statistics."""
        return self.handsactions

    def getHandsStove(self) -> list:
        """Get hands stove statistics."""
        return self.handsstove

    def getHandsPots(self) -> list:
        """Get hands pots statistics."""
        return self.handspots

    @staticmethod
    def _players_who_called_aggressor(actions: list, aggressor: str | None) -> set[str]:
        """Return players who called after the aggressor bet or raised on a street."""
        if not aggressor:
            return set()

        callers = set()
        aggressor_bet_seen = False
        for action in actions:
            player, action_type = action[0], action[1]
            if player == aggressor and action_type in ("bets", "raises"):
                aggressor_bet_seen = True
            elif aggressor_bet_seen and player != aggressor and action_type == "calls":
                callers.add(player)
        return callers

    def _set_float_stats(
        self,
        street_actions: list,
        previous_actions: list,
        previous_aggressor: str | None,
        seen_key: str,
        float_opp_key: str,
        float_done_key: str,
        float_def_opp_key: str,
        log_prefix: str,
    ) -> None:
        """Set float opportunity/done flags when an IP caller bets after the aggressor checks."""
        candidates = self._players_who_called_aggressor(previous_actions, previous_aggressor)
        if not previous_aggressor or not candidates:
            log.debug(
                "%s: No float candidates (previous_aggressor=%s, candidates=%s)",
                log_prefix,
                previous_aggressor,
                candidates,
            )
            return

        aggressor_checked = False
        for action in street_actions:
            player, action_type = action[0], action[1]
            if player == previous_aggressor and action_type == "checks":
                aggressor_checked = True
                log.debug("%s: Previous aggressor %s checked", log_prefix, previous_aggressor)
                continue

            if not aggressor_checked:
                continue

            if player in candidates and player in self.handsplayers and self.handsplayers[player].get(seen_key, False):
                log.debug("%s: Setting %s=True for player %s", log_prefix, float_opp_key, player)
                self.handsplayers[player][float_opp_key] = True
                if action_type in ("bets", "raises"):
                    log.debug("%s: Setting %s=True for player %s", log_prefix, float_done_key, player)
                    self.handsplayers[player][float_done_key] = True
                    if (
                        previous_aggressor in self.handsplayers
                        and self.handsplayers[previous_aggressor].get(seen_key, False)
                    ):
                        log.debug(
                            "%s: Setting %s=True for previous aggressor %s",
                            log_prefix,
                            float_def_opp_key,
                            previous_aggressor,
                        )
                        self.handsplayers[previous_aggressor][float_def_opp_key] = True
                    break
            elif action_type in ("bets", "raises"):
                break

    def assembleHands(self, hand: Any) -> None:  # noqa: C901, PLR0912, PLR0915
        """Assemble basic hand statistics.

        TODO @future: REFACTOR - This method is too complex (C901: 25 > 10, PLR0912: 30 > 12, PLR0915: 144 > 50)
        Consider breaking into smaller methods:
        - _assembleBasicHandInfo()
        - _assembleBoardCards()
        - _assembleStreetTotals()
        - _assemblePlayerStats()
        """
        try:
            log.debug("Starting assembleHands for hand ID: %s", hand.handid)

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
            self.hands["texture"] = None  # No calculation done yet
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
                log.warning("No hero found in the hand.")

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
            log.debug("Hand detail: %s", hand)

        except Exception:  # intentional broad catch: top-level hand assembly context logs hand id before reraising.
            log.exception("Error in assembleHands for hand ID %s", hand.handid)
            raise

    def assembleHandsPlayers(self, hand: Any) -> None:  # noqa: C901, PLR0912, PLR0915
        """Assemble statistics for each player in the hand.

        TODO @future: REFACTOR - This method is too complex (C901: 25 > 10, PLR0912: 28 > 12)
        Consider breaking into smaller methods:
        - _assemblePlayerBasicStats()
        - _assemblePlayerPositions()
        - _assemblePlayerActions()
        """
        # street0VPI/vpip already called in Hand
        # sawShowdown is calculated in playersAtStreetX, as that calculation gives us a convenient list of names

        # Set seat and cnt_players for all players
        total_players = len(hand.players)
        for player in hand.players:
            player_name = player[1]
            player_stats = self.handsplayers[player_name]
            player_stats["seatNo"] = player[0]
            player_stats["seat"] = player[0]  # Duplicate for consistency with requested name
            player_stats["cnt_players"] = total_players
            player_stats["startCash"] = int(CENTS_MULTIPLIER * Decimal(player[2]))
            if player[4] is not None:
                player_stats["startBounty"] = int(CENTS_MULTIPLIER * Decimal(player[4]))
                player_stats["endBounty"] = int(CENTS_MULTIPLIER * Decimal(player[4]))
            if player_name in hand.endBounty:
                player_stats["endBounty"] = int(hand.endBounty.get(player_name))
            if player_name in hand.sitout:
                player_stats["sitout"] = True
            else:
                player_stats["sitout"] = False
            if hand.gametype["type"] == "tour":
                player_stats["tourneyTypeId"] = hand.tourneyTypeId
                player_stats["tourneysPlayersId"] = hand.tourneysPlayersIds.get(player[1], None)
            else:
                player_stats["tourneysPlayersId"] = None
            if player_name in hand.shown:
                player_stats["showed"] = True

            # Cash out fees - convert from Decimal to cents for database storage
            # and set cash out flag
            if hasattr(hand, "cashOutFees") and player_name in hand.cashOutFees:
                player_stats["cashOutFee"] = int(CENTS_MULTIPLIER * hand.cashOutFees[player_name])
                player_stats["isCashOut"] = True
            else:
                player_stats["cashOutFee"] = 0
                player_stats["isCashOut"] = False

        #### seen now processed in playersAtStreetX()

        for i, _street in enumerate(hand.actionStreets[1:]):
            self.aggr(hand, i)
            self.calls(hand, i)
            self.bets(hand, i)
            self.raises(hand, i)
            if i > 0:
                self.folds(hand, i)

        # Winnings is a non-negative value of money collected from the pot, which already includes the
        # rake taken out. hand.collectees is Decimal, database requires cents
        num_collectees, i = len(hand.collectees), 0
        even_split = hand.totalpot / num_collectees if num_collectees > 0 else 0
        unraked = [c for c in hand.collectees.values() if even_split == c]
        for player, winnings in hand.collectees.items():
            collectee_stats = self.handsplayers[player]
            collectee_stats["winnings"] = int(CENTS_MULTIPLIER * winnings)
            # Splits evenly on split pots and gives remainder to first player
            # Gets overwritten when calculating multi-way pots in assembleHandsPots
            if num_collectees == 0:
                collectee_stats["rake"] = 0
            elif len(unraked) == 0:
                rake_share = int(100 * hand.rake) / num_collectees
                remainder_1 = 0.0
                remainder_2 = 0.0
                if rake_share > 0 and i == 0:
                    leftover = int(100 * hand.rake) - (rake_share * num_collectees)
                    remainder_1 = int(100 * hand.rake) % rake_share
                    remainder_2 = leftover if remainder_1 == 0 else 0
                collectee_stats["rake"] = rake_share + remainder_1 + remainder_2
            else:
                collectee_stats["rake"] = int(100 * (even_split - winnings))
            if collectee_stats["street1Seen"]:
                collectee_stats["wonWhenSeenStreet1"] = True
            if collectee_stats["street2Seen"]:
                collectee_stats["wonWhenSeenStreet2"] = True
            if collectee_stats["street3Seen"]:
                collectee_stats["wonWhenSeenStreet3"] = True
            if collectee_stats["street4Seen"]:
                collectee_stats["wonWhenSeenStreet4"] = True
            if collectee_stats["sawShowdown"]:
                collectee_stats["wonAtSD"] = True
            i += 1

        contributed, i = [], 0
        for player, money_committed in hand.pot.committed.items():
            committed_player_stats = self.handsplayers[player]

            # Note: pot.committed already has uncalled bets subtracted via pot.removeMoney()
            # So we use money_committed directly without additional subtraction

            # Calculate paid amount
            paid = (100 * money_committed) + (100 * hand.pot.common[player])

            committed_player_stats["common"] = int(100 * hand.pot.common[player])
            committed_player_stats["committed"] = int(100 * money_committed)
            committed_player_stats["totalProfit"] = int(committed_player_stats["winnings"] - paid)
            committed_player_stats["flg_won_hand"] = committed_player_stats["totalProfit"] > 0
            committed_player_stats["allInEV"] = committed_player_stats["totalProfit"]
            committed_player_stats["rakeDealt"] = 100 * hand.rake / len(hand.players)
            committed_player_stats["rakeWeighted"] = (
                100 * hand.rake * paid / (100 * hand.totalpot) if hand.rake > 0 else 0
            )
            if paid > 0:
                contributed.append(player)
            i += 1

        for _i, player in enumerate(contributed):
            self.handsplayers[player]["rakeContributed"] = 100 * hand.rake / len(contributed)

        # Cash Out handling - store amounts separately from winnings
        # Cash out is an insurance payout, not pot winnings
        if hasattr(hand, "cashOutAmounts") and hand.cashOutAmounts:
            for player, amount in hand.cashOutAmounts.items():
                if player in self.handsplayers:
                    self.handsplayers[player]["cashOutAmount"] = int(100 * amount)

        if hasattr(hand, "cashOutFees") and hand.cashOutFees:
            for player, fee in hand.cashOutFees.items():
                if player in self.handsplayers:
                    self.handsplayers[player]["cashOutFee"] = int(100 * fee)

        self.calcCBets(hand)
        self.calcLimpStreet0(hand)

        # More inner-loop speed hackery.
        encode_card = Card.encodeCard
        calc_start_cards = Card.calcStartCards
        for player in hand.players:
            player_name = player[1]
            hcs = hand.join_holecards(player_name, asList=True)
            hcs = hcs + ["0x"] * 18
            player_stats = self.handsplayers[player_name]
            if player_stats["sawShowdown"]:
                player_stats["showdownWinnings"] = player_stats["totalProfit"]
            else:
                player_stats["nonShowdownWinnings"] = player_stats["totalProfit"]
            for i, card in enumerate(hcs[:20]):
                player_stats["card%d" % (i + 1)] = encode_card(card)
            try:
                player_stats["startCards"] = calc_start_cards(hand, player_name)
            except IndexError:
                log.exception("IndexError: string index out of range %s %s", hand.handid, hand.in_path)

        self.setPositions(hand)
        self.calcSpecialBlinds(hand)
        self.calcFacedAllin(hand)
        self.calcBetFacing(hand)
        self.calcPreflopRaiseFacing(hand)
        self.calcPostflopRaiseFacing(hand)
        self.calcRaiseMade(hand)
        self.calcBetAmounts(hand)
        self.calcEffectiveStack(hand)
        self.calcStreetSPR(hand)
        self.calcCheckCallRaise(hand)
        self.calc34BetStreet0(hand)
        self.calcSqueezeDefense(hand)
        self.calcFaceLimpers(hand)
        self.calc3BetPostflop(hand)
        self.calc4BetPostflop(hand)
        self.calcPostflopOpen(hand)
        self.calcPostflopFirstRaise(hand)
        self.calcFaceRaise(hand)
        self.calcCalledRaiseStreet0(hand)
        self.calcSteals(hand)
        self.calcFlopStats(hand)
        self.calcTurnStats(hand)
        self.calcRiverStats(hand)
        self.calcGpStats(hand)  # after calcSteals: needs raiseFirstInChance/raisedFirstIn
        self.vpip(hand)  # Calculate VPIP after all player stats are initialized
        # Additional stats
        # 3betSB, 3betBB
        # Squeeze, Ratchet?

    def assembleHandsActions(self, hand: Any) -> None:  # noqa: C901, PLR0912, PLR0915
        """Assemble and record all actions taken during the hand.

        Captures player moves, amounts, and all-in statuses.
        """
        try:
            log.debug("Starting assembleHandsActions for hand ID: %s", hand.handid)
            k = 0

            # Handle Mock objects for actionStreets
            try:
                if hasattr(hand.actionStreets, "__iter__") and not isinstance(hand.actionStreets, str):
                    action_streets = list(hand.actionStreets)
                else:
                    log.warning("hand.actionStreets is not iterable, skipping assembleHandsActions")
                    return
            except TypeError:
                log.warning("hand.actionStreets is not iterable, skipping assembleHandsActions")
                return

            for i, street in enumerate(action_streets):
                log.debug("Processing street: %s (index: %s)", street, i)
                for j, act in enumerate(hand.actions.get(street, [])):
                    k += 1
                    log.debug("Processing action %s: %s", k, act)

                    self.handsactions[k] = {}
                    # Initialize default values
                    self.handsactions[k]["amount"] = 0
                    self.handsactions[k]["raiseTo"] = 0
                    self.handsactions[k]["amountCalled"] = 0
                    self.handsactions[k]["numDiscarded"] = 0
                    self.handsactions[k]["cardsDiscarded"] = None
                    self.handsactions[k]["allIn"] = False

                    # Insert values from hand.actions
                    player_name = act[0]
                    action_type = act[1]
                    self.handsactions[k]["player"] = player_name
                    self.handsactions[k]["street"] = i - 1
                    self.handsactions[k]["actionNo"] = k
                    self.handsactions[k]["streetActionNo"] = j + 1

                    # Safely get actionId
                    try:
                        if action_type == "allin":
                            self.handsactions[k]["actionId"] = 18
                        else:
                            self.handsactions[k]["actionId"] = hand.ACTION.get(
                                action_type,
                                None,
                            )
                        if self.handsactions[k]["actionId"] is None:
                            log.warning(
                                "Unknown action type '%s' for player %s in action %s.",
                                action_type,
                                player_name,
                                k,
                            )
                    except (AttributeError, KeyError, TypeError):
                        log.exception("Error retrieving actionId for action %s", k)
                        self.handsactions[k]["actionId"] = None

                    # Handle different action types
                    if action_type not in ("discards") and len(act) > ACTION_AMOUNT_IDX:
                        try:
                            self.handsactions[k]["amount"] = int(CENTS_MULTIPLIER * act[ACTION_AMOUNT_IDX])
                            log.debug(
                                "Action %s: Set amount to %s for player %s.",
                                k,
                                self.handsactions[k]["amount"],
                                player_name,
                            )
                        except (TypeError, ValueError):
                            log.exception("Error converting amount for action %s", k)

                    if action_type in ("raises", "completes") and len(act) > ACTION_CALLED_IDX:
                        try:
                            self.handsactions[k]["raiseTo"] = int(CENTS_MULTIPLIER * act[ACTION_RAISETO_IDX])
                            self.handsactions[k]["amountCalled"] = int(CENTS_MULTIPLIER * act[ACTION_CALLED_IDX])
                            log.debug(
                                "Action %s: Set raiseTo to %s and amountCalled to %s for player %s.",
                                k,
                                self.handsactions[k]["raiseTo"],
                                self.handsactions[k]["amountCalled"],
                                player_name,
                            )
                        except (TypeError, ValueError):
                            log.exception(
                                "Error converting raiseTo or amountCalled for action %s",
                                k,
                            )

                    if action_type in ("discards"):
                        try:
                            self.handsactions[k]["numDiscarded"] = int(act[2])
                            self.handsplayers[player_name][f"street{(i - 1)}Discards"] = int(act[2])
                            log.debug(
                                "Action %s: Set numDiscarded to %s for player %s.",
                                k,
                                self.handsactions[k]["numDiscarded"],
                                player_name,
                            )
                        except (TypeError, ValueError, IndexError):
                            log.exception(
                                "Error setting numDiscarded for action %s and player %s",
                                k,
                                player_name,
                            )

                    if action_type in ("discards") and len(act) > ACTION_CARDS_DISCARDED_IDX:
                        try:
                            self.handsactions[k]["cardsDiscarded"] = act[ACTION_CARDS_DISCARDED_IDX]
                            log.debug(
                                "Action %s: Set cardsDiscarded to %s for player %s.",
                                k,
                                self.handsactions[k]["cardsDiscarded"],
                                player_name,
                            )
                        except (IndexError, KeyError, TypeError):
                            log.exception(
                                "Error setting cardsDiscarded for action %s and player %s",
                                k,
                                player_name,
                            )

                    if len(act) > MIN_ACTION_LENGTH_FOR_ALLIN and action_type not in ("discards"):
                        try:
                            self.handsactions[k]["allIn"] = act[-1]
                            log.debug(
                                "Action %s: Set allIn to %s for player %s.",
                                k,
                                self.handsactions[k]["allIn"],
                                player_name,
                            )
                            if act[-1]:
                                self.handsplayers[player_name]["wentAllIn"] = True
                                self.handsplayers[player_name][f"street{(i - 1)}AllIn"] = True
                                log.debug(
                                    "Player %s wentAllIn set to True for street %s.",
                                    player_name,
                                    i - 1,
                                )
                        except IndexError:
                            log.exception(
                                "Error accessing allIn flag for action %s and player %s",
                                k,
                                player_name,
                            )

                    # Additional validation or logging can be added here as needed

            log.debug("Completed assembleHandsActions for hand ID: %s", hand.handid)

        except Exception:  # intentional broad catch: top-level action assembly context logs hand id before reraising.
            log.exception("Error in assembleHandsActions for hand ID %s", hand.handid)
            raise

    def calcSpecialBlinds(self, hand: Any) -> None:
        """Flag special blind postings: dead small/big blind and straddle (PT4).

        Verified against PT4 cash_hand_player_statistics:
        - ``straddle`` -> flg_blind_k.
        - dead small blind (flg_blind_ds): a ``secondsb`` posting, or a ``both``
          posting made *after* a big blind already exists (a returning player
          posting a dead SB + live BB). A ``both`` that is itself the big blind
          (no prior BB, e.g. some converters tag a plain BB as "both") is not a
          dead small blind.
        - dead big blind (flg_blind_db): a ``big blind`` posted when one was
          already posted by another player (the 2nd+ big blind is dead).
        """
        if not getattr(self, "handsplayers", None):
            return

        seen_bb = False
        for action in hand.actions.get(hand.actionStreets[0], []):
            pname, btype = action[0], action[1]
            ps = self.handsplayers.get(pname)
            if btype == "straddle":
                if ps is not None:
                    ps["flg_blind_k"] = True
            elif btype == "secondsb":
                if ps is not None:
                    ps["flg_blind_ds"] = True
            elif btype == "both":
                if ps is not None and seen_bb:
                    ps["flg_blind_ds"] = True
                seen_bb = True  # a "both" posting includes a big blind
            elif btype == "big blind":
                if ps is not None and seen_bb:
                    ps["flg_blind_db"] = True
                seen_bb = True

    def calcFacedAllin(self, hand: Any) -> None:
        """Flag players who faced an all-in and whether they folded to it.

        A player "faces an all-in" when an opponent makes an all-in *aggressive*
        action (bet/raise/complete) and the player still has a decision. The
        first such spot in the hand is recorded: ``flg_faced_allin`` marks the
        opportunity and ``flg_fold_to_allin`` marks a fold. Mirrors PT4
        enum_face_allin, modelled as a chance/done pair so it aggregates in
        HudCache and drives a fold-to-all-in HUD stat.
        """
        if not getattr(self, "handsplayers", None):
            return

        recorded: set[str] = set()
        # Skip the blinds/antes street; all-in pressure starts once betting does.
        for street in hand.actionStreets[1:]:
            allin_aggr = False
            aggressor = None
            for action in hand.actions.get(street, []):
                pname, act = action[0], action[1]
                ps = self.handsplayers.get(pname)
                if ps is None:
                    continue
                is_allin = (
                    bool(action[-1])
                    if len(action) > MIN_ACTION_LENGTH_FOR_ALLIN and act != "discards"
                    else False
                )
                if allin_aggr and pname != aggressor and pname not in recorded:
                    recorded.add(pname)
                    ps["flg_faced_allin"] = True
                    if act == "folds":
                        ps["flg_fold_to_allin"] = True
                if is_allin and act in ("bets", "raises", "completes"):
                    allin_aggr = True
                    aggressor = pname

    def calcPreflopRaiseFacing(self, hand: Any) -> None:
        """Record the size of the preflop raise faced, per level (PT4 convention).

        For each preflop raise (level 2 = open/2-bet, 3 = 3-bet, 4 = 4-bet,
        5 = 5-bet) the players who then act "face" it. PT4 records this as a
        pot-odds price: the amount the player must call divided by the pot at the
        moment they decide (which already includes the raise). Both the running
        pot and each player's invested amount are tracked across the blinds and
        preflop actions. Mirrors PT4 val_p_{2,3,4,5}bet_facing_pct and
        val_p_raise_facing_pct, encoded as integer basis points.
        """
        if not getattr(self, "handsplayers", None):
            return
        if "PREFLOP" not in hand.actionStreets:
            return
        actions = hand.actions.get("PREFLOP", [])
        if not actions:
            return

        def chips(a):
            act = a[1]
            if act == "raises":
                return a[2] + a[4]  # Rb + C (chips this raise adds to the pot)
            if act in ("calls", "bets", "completes"):
                return a[2]
            if len(a) > 2 and isinstance(a[2], (int, float, Decimal)):
                return a[2]  # blinds / antes
            return Decimal(0)

        # Seed the running pot and per-player investment from the blinds/antes.
        # The full posting goes into the pot (running), but only the *live* part
        # counts toward the bet to match (invested/bet_level): a dead small blind
        # ("secondsb", and the SB part of "both"), antes and bring-ins are dead
        # money and do not raise the level a caller must match.
        bb_amt = _to_decimal(getattr(hand, "bb", 0))
        # Bomb / "Escape to Pot" money is in the pot from the start (PT4 counts
        # it in the facing pot-odds denominator).
        running = _pot_stp(hand)
        invested: dict[str, Decimal] = {}
        bet_level = Decimal(0)
        for a in hand.actions.get(hand.actionStreets[0], []):
            c = chips(a)
            btype = a[1]
            # A standalone dead small blind ("secondsb") is in the real pot but
            # PT4 excludes it from the facing pot-odds denominator (a "both"
            # posting's dead SB, by contrast, is counted — verified vs PT4).
            if btype == "secondsb":
                continue
            running += c
            if btype in ("ante", "bringin"):
                live = Decimal(0)
            elif btype == "both":
                live = min(c, bb_amt) if bb_amt else c  # big-blind part is live, dead SB is not
            else:
                live = c
            invested[a[0]] = invested.get(a[0], Decimal(0)) + live
            if invested[a[0]] > bet_level:
                bet_level = invested[a[0]]

        levels = {
            2: ("cnt_p_2bet_facing", "val_p_2bet_facing_bp"),
            3: ("cnt_p_3bet_facing", "val_p_3bet_facing_bp"),
            4: ("cnt_p_4bet_facing", "val_p_4bet_facing_bp"),
            5: ("cnt_p_5bet_facing", "val_p_5bet_facing_bp"),
        }
        level = 1  # blinds posted == level 1
        last_raiser = None
        for a in actions:
            pname, act = a[0], a[1]
            ps = self.handsplayers.get(pname)
            inv = invested.get(pname, Decimal(0))
            # Facing an outstanding raise: call price = (bet_level - invested) / pot.
            if ps is not None and level >= 2 and pname != last_raiser and bet_level > inv and running > 0:
                to_call = bet_level - inv
                pot = running
                # A short stack that calls/raises all-in for less than the full
                # amount only faces what it can put in, and only contests the
                # part of the pot capped at its effective total (PT4 convention).
                if len(a) > MIN_ACTION_LENGTH_FOR_ALLIN and a[-1] is True and act in ("calls", "raises", "bets", "completes") and chips(a) < to_call:
                    to_call = chips(a)
                    eff = inv + to_call  # the all-in player's effective total
                    pot = sum(min(iv, eff) for iv in invested.values())
                val_bp = int(to_call * 10000 / pot) if pot > 0 else 0
                if level in levels:
                    cnt_key, bp_key = levels[level]
                    if not ps.get(cnt_key):
                        ps[cnt_key] = 1
                        ps[bp_key] = val_bp
                # Generic raise faced = the most recent raise faced (overwrite).
                ps["cnt_p_raise_facing"] = 1
                ps["val_p_raise_facing_bp"] = val_bp
            c = chips(a)
            running += c
            invested[pname] = inv + c
            if act in ("raises", "bets", "completes"):
                if invested[pname] > bet_level:
                    bet_level = invested[pname]
                level += 1
                last_raiser = pname

    def calcBetAmounts(self, hand: Any) -> None:
        """Sum the chips each player invests per street (PT4 amt_blind/amt_bet_*).

        Raw amounts in cents: amt_blind (blinds/antes), amt_bet_{p,f,t,r} per
        street, and amt_bet_ttl across the whole hand. Stake-dependent, so kept
        mainly for PT4 parity; summed in HudCache and averaged over n by the HUD.
        """
        if not getattr(self, "handsplayers", None):
            return

        def chips(a):
            act = a[1]
            if act == "raises":
                try:
                    return a[2] + a[4]
                except (IndexError, TypeError):
                    return Decimal(0)
            if act in ("folds", "checks", "stands pat", "discards", "cashout"):
                return Decimal(0)
            if len(a) > 2 and isinstance(a[2], (int, float, Decimal)):
                return a[2]
            return Decimal(0)

        # PT4 amt_bet_p is the full preflop investment, *including* the blind
        # (which is also counted separately in amt_blind).
        street_key = {"BLINDSANTES": ("amt_blind", "amt_bet_p"), "PREFLOP": ("amt_bet_p",),
                      "FLOP": ("amt_bet_f",), "TURN": ("amt_bet_t",), "RIVER": ("amt_bet_r",)}
        for street in hand.actionStreets:
            keys = street_key.get(street, ())
            for a in hand.actions.get(street, []):
                ps = self.handsplayers.get(a[0])
                if ps is None:
                    continue
                c = int(CENTS_MULTIPLIER * chips(a))
                for key in keys:
                    ps[key] = ps.get(key, 0) + c
                ps["amt_bet_ttl"] = ps.get("amt_bet_ttl", 0) + c
        # PT4 amt_bet_ttl is net of the uncalled bet. fpdb's pot.returned is not
        # always populated here (e.g. preflop walks), so derive the uncalled
        # amount directly: only the largest total contributor can have chips
        # returned, and the returned amount is their total minus the next-highest
        # total committed (the most any single opponent could match). This is
        # computed on totals across all streets (a preflop raise is partly
        # matched by the blinds, which live on the BLINDSANTES street).
        totals = sorted(
            ((p, ps.get("amt_bet_ttl", 0)) for p, ps in self.handsplayers.items()),
            key=lambda kv: kv[1],
            reverse=True,
        )
        if totals:
            top_player, top_amt = totals[0]
            second = totals[1][1] if len(totals) > 1 else 0
            if top_amt > second:
                self.handsplayers[top_player]["amt_bet_ttl"] = second

    def calcPostflopRaiseFacing(self, hand: Any) -> None:
        """Record the size of postflop raises faced, per street and level.

        On a postflop street the first bet is level 1; a raise is level 2 (the
        "2-bet"), a re-raise level 3, etc. The players who act after a raise
        "face" it; the size recorded is the raise-to amount as basis points of
        the pot before that raise (a running pot carried across the hand).
        Mirrors PT4 amt_{f,t,r}_{2,3,4}bet_facing / val_*_pct.
        """
        if not getattr(self, "handsplayers", None):
            return

        def chips(a):
            act = a[1]
            if act == "raises":
                try:
                    return a[2] + a[4]  # Rb + C
                except (IndexError, TypeError):
                    return Decimal(0)
            if act in ("folds", "checks", "stands pat", "discards", "cashout"):
                return Decimal(0)
            if len(a) > 2 and isinstance(a[2], (int, float, Decimal)):
                return a[2]
            return Decimal(0)

        levels_map = {
            "FLOP": {
                2: ("cnt_f_2bet_facing", "val_f_2bet_facing_bp"),
                3: ("cnt_f_3bet_facing", "val_f_3bet_facing_bp"),
                4: ("cnt_f_4bet_facing", "val_f_4bet_facing_bp"),
            },
            "TURN": {
                2: ("cnt_t_2bet_facing", "val_t_2bet_facing_bp"),
                3: ("cnt_t_3bet_facing", "val_t_3bet_facing_bp"),
                4: ("cnt_t_4bet_facing", "val_t_4bet_facing_bp"),
            },
            "RIVER": {
                2: ("cnt_r_2bet_facing", "val_r_2bet_facing_bp"),
                3: ("cnt_r_3bet_facing", "val_r_3bet_facing_bp"),
                4: ("cnt_r_4bet_facing", "val_r_4bet_facing_bp"),
            },
        }
        generic_map = {
            "FLOP": ("cnt_f_raise_facing", "val_f_raise_facing_bp"),
            "TURN": ("cnt_t_raise_facing", "val_t_raise_facing_bp"),
            "RIVER": ("cnt_r_raise_facing", "val_r_raise_facing_bp"),
        }
        bet_facing_map = {
            "FLOP": ("cnt_f_bet_facing", "val_f_bet_facing_bp"),
            "TURN": ("cnt_t_bet_facing", "val_t_bet_facing_bp"),
            "RIVER": ("cnt_r_bet_facing", "val_r_bet_facing_bp"),
        }
        # Bomb / "Escape to Pot" money seeds the pot (PT4 counts it).
        running = int(CENTS_MULTIPLIER * _pot_stp(hand))
        for street in hand.actionStreets:
            lm = levels_map.get(street)
            gk = generic_map.get(street)
            bk = bet_facing_map.get(street)
            invested: dict[str, int] = {}
            bet_level = 0  # current amount to match this street (cents)
            level = 0  # 1 = a bet is out, 2 = a raise (2-bet), ...
            last_aggr = None
            for a in hand.actions.get(street, []):
                pname, act = a[0], a[1]
                ps = self.handsplayers.get(pname)
                inv = invested.get(pname, 0)
                # Facing an outstanding bet/raise: price = (bet_level - invested) / pot.
                if ps is not None and last_aggr is not None and pname != last_aggr and bet_level > inv and running > 0:
                    to_call = bet_level - inv
                    pot = running
                    # A short stack calling/raising all-in only faces what it can
                    # put in, and contests the pot capped at its effective total.
                    a_chips = int(CENTS_MULTIPLIER * chips(a))
                    if len(a) > MIN_ACTION_LENGTH_FOR_ALLIN and a[-1] is True and act in ("calls", "raises", "bets", "completes") and a_chips < to_call:
                        to_call = a_chips
                        eff = inv + to_call
                        pot = sum(min(iv, eff) for iv in invested.values())
                    val_bp = int(to_call * 10000 / pot) if pot > 0 else 0
                    if level == 1 and bk:
                        if not ps.get(bk[0]):
                            ps[bk[0]] = 1
                            ps[bk[1]] = val_bp
                    elif level >= 2:
                        if lm and level in lm and not ps.get(lm[level][0]):
                            ps[lm[level][0]] = 1
                            ps[lm[level][1]] = val_bp
                        if gk:  # generic raise faced = most recent (overwrite)
                            ps[gk[0]] = 1
                            ps[gk[1]] = val_bp
                c = int(CENTS_MULTIPLIER * chips(a))
                running += c
                invested[pname] = inv + c
                if act in ("bets", "raises", "completes"):
                    if invested[pname] > bet_level:
                        bet_level = invested[pname]
                    level += 1
                    last_aggr = pname

    def calcRaiseMade(self, hand: Any) -> None:
        """Record the size of the first raise the player makes on each street.

        For each street, the player's first ``raises`` action is recorded as the
        raise-to amount in basis points of the pot *before* that raise (a running
        pot carried across the whole hand). Captures open/3-bet sizing preflop
        and check-raise/raise-of-bet sizing postflop (PT4 amt_*_raise_made /
        val_*_raise_made_pct, encoded as integer basis points). A plain bet
        (first voluntary chips on a street) is not a raise and is not counted
        here; that is covered by *_bet_made.
        """
        if not getattr(self, "handsplayers", None):
            return

        def chips(a):
            act = a[1]
            if act == "raises":
                try:
                    return a[2] + a[4]  # Rb + C
                except (IndexError, TypeError):
                    return Decimal(0)
            if act in ("folds", "checks", "stands pat", "discards", "cashout"):
                return Decimal(0)
            if len(a) > 2 and isinstance(a[2], (int, float, Decimal)):
                return a[2]
            return Decimal(0)

        streets_map = {
            "PREFLOP": ("cnt_p_raise_made", "val_p_raise_made_bp", "cnt_p_raise_made_2", "val_p_raise_made_2_bp"),
            "FLOP": ("cnt_f_raise_made", "val_f_raise_made_bp", "cnt_f_raise_made_2", "val_f_raise_made_2_bp"),
            "TURN": ("cnt_t_raise_made", "val_t_raise_made_bp", "cnt_t_raise_made_2", "val_t_raise_made_2_bp"),
            "RIVER": ("cnt_r_raise_made", "val_r_raise_made_bp", "cnt_r_raise_made_2", "val_r_raise_made_2_bp"),
        }
        # Bomb / "Escape to Pot" money seeds the pot (PT4 counts it).
        running = int(CENTS_MULTIPLIER * _pot_stp(hand))
        for street in hand.actionStreets:
            keys = streets_map.get(street)
            made_count: dict[str, int] = {}  # raises made by each player this street
            for a in hand.actions.get(street, []):
                pname, act = a[0], a[1]
                ps = self.handsplayers.get(pname)
                if act == "raises" and keys and ps is not None:
                    n = made_count.get(pname, 0)
                    # First raise -> raise_made; second raise -> raise_made_2.
                    cnt_key, bp_key = (keys[0], keys[1]) if n == 0 else (keys[2], keys[3]) if n == 1 else (None, None)
                    if cnt_key is not None and bp_key is not None and running > 0 and not ps.get(cnt_key):
                        ps[cnt_key] = 1
                        try:
                            ps[bp_key] = int(int(CENTS_MULTIPLIER * a[3]) * 10000 // running)
                        except (TypeError, ValueError, ZeroDivisionError, IndexError):
                            pass
                    made_count[pname] = n + 1
                running += int(CENTS_MULTIPLIER * chips(a))

    def calcStreetSPR(self, hand: Any) -> None:
        """Record the stack-to-pot ratio (SPR) at the start of each postflop street.

        SPR = effective stack / pot, measured entering the flop/turn/river. The
        pot entering a street is the chips committed so far; a player's remaining
        stack is startCash minus their commitments; the effective stack is
        min(own remaining, deepest active opponent). Players who act on the
        street are the "active" contenders. Stored as cnt + SPR*100 (centi-SPR)
        so the INT-only HudCache averages val_sum / cnt / 100. Drives PT4
        amt_{f,t,r}_effective_stack relative to pot (a stake-independent HUD SPR).
        """
        if not getattr(self, "handsplayers", None):
            return

        def chips(a):
            act = a[1]
            if act == "raises":
                try:
                    return a[2] + a[4]  # Rb + C
                except (IndexError, TypeError):
                    return Decimal(0)
            if act in ("folds", "checks", "stands pat", "discards", "cashout"):
                return Decimal(0)
            if len(a) > 2 and isinstance(a[2], (int, float, Decimal)):
                return a[2]
            return Decimal(0)

        targets = {
            "FLOP": ("cnt_f_spr", "val_f_spr"),
            "TURN": ("cnt_t_spr", "val_t_spr"),
            "RIVER": ("cnt_r_spr", "val_r_spr"),
        }
        committed = {p: 0 for p in self.handsplayers}  # cents committed so far
        start_cash = {p: self.handsplayers[p].get("startCash", 0) for p in self.handsplayers}
        # Bomb / "Escape to Pot" money is in the pot from the start.
        stp = int(CENTS_MULTIPLIER * _pot_stp(hand))

        for street in hand.actionStreets:
            acts = hand.actions.get(street, [])
            if street in targets:
                pot = sum(committed.values()) + stp  # cents in the pot entering this street
                active = []
                seen = set()
                for a in acts:
                    p = a[0]
                    if p in self.handsplayers and p not in seen:
                        seen.add(p)
                        active.append(p)
                if pot > 0 and len(active) >= 2:
                    cnt_key, val_key = targets[street]
                    rem = {p: start_cash[p] - committed[p] for p in active}
                    for p in active:
                        others = [rem[q] for q in active if q != p]
                        if not others:
                            continue
                        eff = min(rem[p], max(others))
                        if eff <= 0:
                            continue
                        ps = self.handsplayers[p]
                        ps[cnt_key] = 1
                        ps[val_key] = int(eff * 100 // pot)
            for a in acts:
                p = a[0]
                if p in committed:
                    committed[p] += int(CENTS_MULTIPLIER * chips(a))

    def calcBetFacing(self, hand: Any) -> None:
        """Record the size of the first bet *made* on each postflop street.

        The first voluntary bettor on a street records a "bet made": the bet as
        basis points of the pot before the bet (= the pot entering the street,
        since checks add nothing). PT4 uses this sizing convention for *_bet_made
        (bet / pot_before). The matching "bet faced" (pot-odds price) is handled
        by calcPostflopRaiseFacing alongside the raise levels.
        """
        if not getattr(self, "handsplayers", None):
            return
        for street, keys in (
            ("FLOP", ("cnt_f_bet_made", "val_f_bet_made_bp")),
            ("TURN", ("cnt_t_bet_made", "val_t_bet_made_bp")),
            ("RIVER", ("cnt_r_bet_made", "val_r_bet_made_bp")),
        ):
            self._calcStreetBetMade(hand, street, *keys)

    def _calcStreetBetMade(self, hand: Any, street: str, made_cnt_key: str, made_bp_key: str) -> None:
        """Shared per-street first-bet-made sizing (see calcBetFacing)."""
        streets = hand.actionStreets
        if street not in streets:
            return
        # Pot entering this street = pot total at the end of the previous street.
        pre_street = streets[streets.index(street) - 1]
        try:
            pot = hand.pot.getTotalAtStreet(pre_street)
        except (AttributeError, KeyError):
            return
        if not pot or pot <= 0:
            return

        for action in hand.actions.get(street, []):
            pname, act = action[0], action[1]
            ps = self.handsplayers.get(pname)
            if ps is None:
                continue
            if act == "bets":
                ps[made_cnt_key] = 1
                try:
                    ps[made_bp_key] = int(action[2] * 10000 // pot)
                except (TypeError, ValueError, ZeroDivisionError):
                    pass
                return  # only the first bet on the street

    def setPositions(self, hand: Any) -> None:  # noqa: C901, PLR0912
        """Sets the position for each player in HandsPlayers.

        Any blinds are negative values, and the last person to act on the
        first betting round is 0.
        NOTE: HU, both values are negative for non-stud games.
        NOTE2: I've never seen a HU stud match.
        """
        if not hasattr(self, "handsplayers"):
            return

        actions = hand.actions[hand.holeStreets[0]]
        # Note:  pfbao list may not include big blind if all others folded
        players = self.pfbao(actions)
        seated_players = [p[1] for p in getattr(hand, "players", [])]

        # set blinds first, then others from pfbao list, avoids problem if bb
        # is missing from pfbao list or if there is no small blind
        sb: list[str] = []
        bb: list[str] = []
        bi: list[str] = []
        ub: list[str] = []
        if hand.gametype["base"] == "stud":
            # Stud position is determined after cards are dealt
            # First player to act is always the bring-in position in stud
            # even if they decided to bet/completed
            opening_actions = hand.actions[hand.actionStreets[1]]
            if not opening_actions:
                for player in self.handsplayers.values():
                    player["position"] = ANTE_ALL_IN_POSITION
                self.hands["maxPosition"] = -1
                return
            bi = [opening_actions[0][0]]
        else:
            ub = [x[0] for x in hand.actions[hand.actionStreets[0]] if x[1] == "button blind"]
            bb = [x[0] for x in hand.actions[hand.actionStreets[0]] if x[1] == "big blind"]
            sb = [x[0] for x in hand.actions[hand.actionStreets[0]] if x[1] == "small blind"]
        # Set positions in order: Button=0, SB=S, BB=B, then others backwards (CO=1, HJ=2...)

        # Button position
        if ub:
            self.handsplayers[ub[0]]["position"] = 0
            self.handsplayers[ub[0]]["street0InPosition"] = True

        # Small blind position
        if sb:
            self.handsplayers[sb[0]]["position"] = "S"
            self.handsplayers[sb[0]]["flg_blind_s"] = True
            self.handsplayers[sb[0]]["street0FirstToAct"] = True

        # Big blind position
        if bb:
            self.handsplayers[bb[0]]["position"] = "B"
            self.handsplayers[bb[0]]["flg_blind_b"] = True
            self.handsplayers[bb[0]]["street0InPosition"] = True

        # Bring-in position (stud). Legacy HUD/database code treats this like
        # the first blind slot ("S") and uses numeric positions for the rest.
        if bi:
            self.handsplayers[bi[0]]["position"] = "S"
            self.handsplayers[bi[0]]["street0FirstToAct"] = True

            action_order = []
            for action in hand.actions[hand.actionStreets[1]][1:]:
                pname = action[0]
                if pname == bi[0]:
                    break
                if pname not in action_order:
                    action_order.append(pname)

            pos_val = 0
            for pname in reversed(action_order):
                if pname in self.handsplayers:
                    self.handsplayers[pname]["position"] = pos_val
                    if pos_val == 0:
                        self.handsplayers[pname]["street0InPosition"] = True
                    pos_val += 1
            self.hands["maxPosition"] = max(pos_val - 1, 0)
            return

        # Assign positions to remaining players
        # The CO is 1, HJ is 2, etc. (distance backwards from button)
        assigned_players = set()
        if ub:
            assigned_players.add(ub[0])
        if sb:
            assigned_players.add(sb[0])
        if bb:
            assigned_players.add(bb[0])
        if bi:
            assigned_players.add(bi[0])

        # We want to find players who are NOT blinds/BTN and assign them CO, HJ, etc.
        # starting from the player right before the Button (CO).

        try:
            log.debug("setPositions: players=%s, sb=%s, bb=%s", players, sb, bb)
            btn_idx = -1
            if ub:
                if ub[0] in players:
                    btn_idx = players.index(ub[0])
                    log.debug("setPositions: Found button via ub: %s (idx %s)", ub[0], btn_idx)
                elif ub[0] in seated_players:
                    if ub[0] in self.handsplayers:
                        self.handsplayers[ub[0]]["position"] = 0
                        self.handsplayers[ub[0]]["street0InPosition"] = True
                        assigned_players.add(ub[0])
            elif sb:
                # Button is the player before SB
                if sb[0] in players:
                    sb_idx = players.index(sb[0])
                    btn_idx = (sb_idx - 1) % len(players)
                    log.debug("setPositions: Found button via sb fallback: %s (idx %s)", players[btn_idx], btn_idx)
                elif sb[0] in seated_players:
                    seat_idx = seated_players.index(sb[0])
                    button_name = seated_players[seat_idx - 1]
                    if button_name in players:
                        btn_idx = players.index(button_name)
                    elif button_name in self.handsplayers:
                        self.handsplayers[button_name]["position"] = 0
                        self.handsplayers[button_name]["street0InPosition"] = True
                        assigned_players.add(button_name)
            elif bb and seated_players and bb[0] in seated_players:
                bb_idx = seated_players.index(bb[0])
                button_name = seated_players[bb_idx - 1]
                if button_name in players:
                    btn_idx = players.index(button_name)
                elif button_name in self.handsplayers:
                    self.handsplayers[button_name]["position"] = 0
                    self.handsplayers[button_name]["street0InPosition"] = True
                    assigned_players.add(button_name)

            if btn_idx != -1:
                # Set Button position to 0 explicitly, except heads-up where
                # the button is also the small blind and keeps the blind marker.
                btn_p = players[btn_idx]
                if btn_p not in assigned_players:
                    self.handsplayers[btn_p]["position"] = 0
                    self.handsplayers[btn_p]["street0InPosition"] = True
                    assigned_players.add(btn_p)

                # Iterate backwards from btn_idx - 1
                pos_val = 1
                for i in range(1, len(players)):
                    idx = (btn_idx - i) % len(players)
                    p = players[idx]
                    if p not in assigned_players:
                        self.handsplayers[p]["position"] = pos_val
                        log.debug("setPositions: Set %s to position %s", p, pos_val)
                        pos_val += 1
                self.hands["maxPosition"] = pos_val - 1
                for p in self.handsplayers:
                    log.debug("setPositions: Final position for %s: %s", p, self.handsplayers[p].get("position"))
            elif 0 in [self.handsplayers[p].get("position") for p in self.handsplayers]:
                pos_val = 1
                for pname in reversed(seated_players):
                    if pname not in assigned_players and pname in self.handsplayers:
                        self.handsplayers[pname]["position"] = pos_val
                        pos_val += 1
                self.hands["maxPosition"] = pos_val - 1
        except (ValueError, ZeroDivisionError):
            log.exception("setPositions: Error calculating positions")

    def vpip(self, hand: Any) -> None:
        """Calculate VPIP (Voluntarily Put In Pot) for all players.

        VPIP Opportunity: Player had a chance to act preflop (not all-in blind, didn't fold blinds)
        VPIP Done: Player voluntarily put money in pot (call/raise/bet/complete)
        """
        log.warning("Starting VPIP calculation for hand ID: %s", hand.handid)
        if not hasattr(self, "handsplayers"):
            log.warning("vpip: handsplayers not available, returning")
            return

        # Check if we have enough action streets for preflop
        if len(hand.actionStreets) < MIN_STREETS_FOR_PREFLOP:
            log.warning("Not enough action streets for VPIP calculation")
            log.warning(
                "vpip: Setting playersVpi=0 due to insufficient action streets (%s < %s)",
                len(hand.actionStreets),
                MIN_STREETS_FOR_PREFLOP,
            )
            self.hands["playersVpi"] = 0
            return

        preflop_actions = hand.actions.get(hand.actionStreets[1], [])
        log.warning("vpip: Preflop actions: %s", preflop_actions)
        log.warning("vpip: actionStreets: %s", hand.actionStreets)
        log.warning("vpip: hand.actions keys: %s", list(hand.actions.keys()))
        vpip_count = 0

        # Get players who were all-in blind (should not get VPIP opportunity)
        allin_blind_players = set()
        blinds_antes_actions = hand.actions.get("BLINDSANTES", [])
        log.debug("vpip: Blinds/antes actions: %s", blinds_antes_actions)
        for act in blinds_antes_actions:
            if len(act) > 2 and act[2] == "allin":
                allin_blind_players.add(act[0])
        log.debug("vpip: All-in blind players: %s", allin_blind_players)

        # Get players who folded their blinds (no VPIP opportunity)
        fold_blind_players = set()
        for act in preflop_actions:
            if act[1] == "folds" and act[0] in [
                x[0] for x in blinds_antes_actions if x[1] in ["small blind", "big blind"]
            ]:
                fold_blind_players.add(act[0])
        log.debug("vpip: Fold blind players: %s", fold_blind_players)

        log.debug("vpip: Processing VPIP for each player")
        for p in self.handsplayers:
            player_stats = self.handsplayers[p]
            log.debug("vpip: Processing player %s", p)

            # Players who were all-in blind or folded blinds don't get VPIP opportunity
            if p in allin_blind_players or p in fold_blind_players:
                log.debug("vpip: Player %s excluded from VPIP (all-in blind or folded blind)", p)
                player_stats["street0VPIChance"] = False
                continue

            # All other players who acted get VPIP opportunity
            acted_preflop = any(act[0] == p for act in preflop_actions)
            log.debug("vpip: Player %s acted preflop: %s", p, acted_preflop)
            if acted_preflop:
                player_stats["street0VPIChance"] = True

                # Check if they voluntarily put money in pot
                # For Stud, 'completes' is a voluntary action like calls/raises/bets
                vpip_action = any(
                    act[0] == p and act[1] in ["calls", "raises", "bets", "completes"] for act in preflop_actions
                )
                log.debug("vpip: Player %s had VPIP action: %s", p, vpip_action)
                if vpip_action:
                    log.debug("vpip: Setting street0VPI=True for player %s", p)
                    player_stats["street0VPI"] = True
                    vpip_count += 1
                else:
                    log.debug("vpip: Player %s did not voluntarily put money in pot", p)
            else:
                log.debug("vpip: Player %s did not act preflop, no VPIP opportunity", p)

        log.debug("vpip: Final VPIP count: %s", vpip_count)
        self.hands["playersVpi"] = vpip_count
        log.debug("vpip: Completed vpip calculation for hand ID: %s", hand.handid)

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

    def countPlayers(self, hand: Any) -> int:
        """Count the number of players in the hand."""
        return len(hand.players) if hand.players else 0

    def pfba(self, actions: Any, f: Any = None, limit: Any = None) -> set:
        """Helper method. Returns set of PlayersFilteredByActions.

        f - forbidden actions (will be excluded)
        limit - limited to actions (only these will be included)
        """
        players = set()
        for action in actions:
            if limit is not None and action[1] not in limit:
                continue
            if f is not None and action[1] in f:
                continue
            players.add(action[0])
        return players

    def pfbao(self, actions: Any, f: Any = None, limit: Any = None, *, unique: bool = True) -> list:
        """Helper method. Returns ordered list of PlayersFilteredByActionsOrdered.

        f - forbidden actions (will be excluded)
        limit - limited to actions (only these will be included)
        """
        seen = {}
        players = []
        for action in actions:
            if limit is not None and action[1] not in limit:
                continue
            if f is not None and action[1] in f:
                continue
            if action[0] in seen and unique:
                continue
            seen[action[0]] = 1
            players.append(action[0])
        return players

    def firstsBetOrRaiser(self, actions: Any) -> str | None:
        """Find the first player to bet or raise."""
        for act in actions:
            if act[1] in ["bets", "raises"]:
                return act[0]
        return None

    def lastBetOrRaiser(self, actions: Any, street: Any) -> str | None:
        """Find the last player to bet or raise on a given street."""
        aggressors = [act[0] for act in actions.get(street, []) if act[1] in ["bets", "raises"]]
        return aggressors[-1] if aggressors else None

    def calcCBets(self, hand: Any) -> None:  # noqa: C901, PLR0912
        """Calculate continuation bets for all players."""
        if not hasattr(self, "handsplayers"):
            return

        # Find preflop aggressor
        preflop_actions = hand.actions.get(hand.actionStreets[1], [])
        preflop_aggressor = None
        for act in reversed(preflop_actions):
            if act[1] in ["raises", "bets"]:
                preflop_aggressor = act[0]
                break

        if not preflop_aggressor:
            return

        # Track if preflop aggressor has folded
        aggressor_folded = False

        # Check for CBets on each street
        for i in range(1, min(5, len(hand.actionStreets) - 1)):
            street_name = hand.actionStreets[i + 1]
            street_actions = hand.actions.get(street_name, [])

            if preflop_aggressor in self.handsplayers:
                # Initialize street stats if they don't exist (for run-it-twice scenarios)
                if f"street{i}CBChance" not in self.handsplayers[preflop_aggressor]:
                    self.handsplayers[preflop_aggressor][f"street{i}CBChance"] = False
                if f"street{i}CBDone" not in self.handsplayers[preflop_aggressor]:
                    self.handsplayers[preflop_aggressor][f"street{i}CBDone"] = False

                # Only give CBet chance if aggressor hasn't folded yet
                if not aggressor_folded:
                    self.handsplayers[preflop_aggressor][f"street{i}CBChance"] = True

                # Check if they bet first on this street, and track if they fold
                cbet_made = False
                for act in street_actions:
                    if act[0] == preflop_aggressor:
                        if act[1] in ["bets", "raises"]:
                            if not aggressor_folded:
                                self.handsplayers[preflop_aggressor][f"street{i}CBDone"] = True
                                cbet_made = True
                            break
                        elif act[1] == "folds":
                            aggressor_folded = True
                            break

                # If a CBet was made, check for fold to CBet for other players
                if cbet_made:
                    # Find the position of the CBet in the action sequence
                    cbet_position = -1
                    for idx, act in enumerate(street_actions):
                        if act[0] == preflop_aggressor and act[1] in ["bets", "raises"]:
                            cbet_position = idx
                            break

                    if cbet_position >= 0:
                        for player in self.handsplayers:
                            if player != preflop_aggressor:
                                # Check if this player acted after the CBet
                                player_faced_cbet = False
                                player_folded_to_cbet = False

                                # Look for actions by this player after the CBet
                                for idx in range(cbet_position + 1, len(street_actions)):
                                    act = street_actions[idx]
                                    if act[0] == player:
                                        player_faced_cbet = True
                                        if act[1] == "folds":
                                            player_folded_to_cbet = True
                                        break

                                if player_faced_cbet:
                                    self.handsplayers[player][f"foldToStreet{i}CBChance"] = True
                                    if player_folded_to_cbet:
                                        self.handsplayers[player][f"foldToStreet{i}CBDone"] = True

        self._calc_delayed_turn_cbet(hand, preflop_aggressor)
        self._calc_turn_probe(hand, preflop_aggressor)

    def _calc_turn_probe(self, hand: Any, preflop_aggressor: str) -> None:
        """Turn probe bet: a non-PFR opens the turn after the PFR checked the flop.

        The mirror of a delayed c-bet. Precondition: the PFR had a flop c-bet
        chance but checked (declined) it. Then the first non-PFR player to act on
        the turn with no bet in front of them gets a probe *chance*; if that
        action is a bet/raise it is a probe *done*. Only that first eligible
        player is credited (once a bet lands, others are facing it, not probing).
        """
        pfr = self.handsplayers.get(preflop_aggressor)
        if pfr is None or len(hand.actionStreets) < 4:
            return
        # PFR must have had a flop c-bet chance and checked it (declined the lead,
        # not faced+called a bet — same "checked flop" test as the delayed c-bet).
        if not pfr.get("street1CBChance") or pfr.get("street1CBDone"):
            return
        flop_actions = hand.actions.get(hand.actionStreets[2], [])
        pfr_flop = [a[1] for a in flop_actions if a[0] == preflop_aggressor]
        if "checks" not in pfr_flop or any(act in ("bets", "raises", "calls", "folds") for act in pfr_flop):
            return

        turn_actions = hand.actions.get(hand.actionStreets[3], [])
        bet_before = False
        for player, kind, *_ in turn_actions:
            if player == preflop_aggressor:
                if kind in ("bets", "raises"):
                    return  # PFR led the turn (delayed c-bet), not a probe spot
                continue  # PFR checked behind/ahead — keep scanning for a prober
            if bet_before:
                return  # this player is facing a bet, not opening
            hp = self.handsplayers.get(player)
            if hp is not None:
                hp.setdefault("street2ProbeChance", False)
                hp.setdefault("street2ProbeDone", False)
                hp["street2ProbeChance"] = True
                if kind in ("bets", "raises"):
                    hp["street2ProbeDone"] = True
            return  # only the first eligible non-PFR is credited

    def _calc_delayed_turn_cbet(self, hand: Any, preflop_aggressor: str) -> None:
        """Delayed turn c-bet: PFR checks the flop, then opens the turn.

        Chance: the preflop aggressor had a flop c-bet chance, *checked* the flop
        (declined the lead and did not face+call a bet), reaches the turn, and is
        able to open it (no bet has occurred when they act). Done: they bet or
        raise the turn in that spot. Uses HandsPlayers.position encoding-free
        action data, so it is correct in and out of position.
        """
        hp = self.handsplayers.get(preflop_aggressor)
        if hp is None:
            return
        hp.setdefault("street2DelayedCBChance", False)
        hp.setdefault("street2DelayedCBDone", False)

        # Need a flop (street index 2) and a turn (street index 3).
        if len(hand.actionStreets) < 4:
            return

        # The PFR must have had a flop c-bet chance but declined it.
        if not hp.get("street1CBChance") or hp.get("street1CBDone"):
            return

        # Genuine "checked flop": the PFR checked and did NOT bet/raise/call/fold
        # the flop (a check-call faces a bet, so it is not a delayed-cbet setup).
        flop_actions = hand.actions.get(hand.actionStreets[2], [])
        pfr_flop = [a[1] for a in flop_actions if a[0] == preflop_aggressor]
        if "checks" not in pfr_flop or any(act in ("bets", "raises", "calls", "folds") for act in pfr_flop):
            return

        # On the turn, the PFR may open only if no bet has occurred when they act.
        turn_actions = hand.actions.get(hand.actionStreets[3], [])
        bet_before_pfr = False
        for act in turn_actions:
            if act[0] == preflop_aggressor:
                if not bet_before_pfr:
                    hp["street2DelayedCBChance"] = True
                    if act[1] in ("bets", "raises"):
                        hp["street2DelayedCBDone"] = True
                return
            if act[1] in ("bets", "raises"):
                bet_before_pfr = True

    def calcCheckCallRaise(self, hand: Any) -> None:
        """Calculate check-call and check-raise statistics."""
        if not hasattr(self, "handsplayers"):
            return

        for i in range(1, min(5, len(hand.actionStreets) - 1)):
            street_name = hand.actionStreets[i + 1]
            street_actions = hand.actions.get(street_name, [])

            for player in self.handsplayers:
                player_actions = [act for act in street_actions if act[0] == player]

                if len(player_actions) >= MIN_ACTIONS_FOR_CHECK_CALL_RAISE:
                    first_action = player_actions[0]
                    if first_action[1] == "checks":
                        # Initialize street stats if they don't exist (for run-it-twice scenarios)
                        if f"street{i}CheckCallRaiseChance" not in self.handsplayers[player]:
                            self.handsplayers[player][f"street{i}CheckCallRaiseChance"] = False
                        if f"street{i}CheckCallDone" not in self.handsplayers[player]:
                            self.handsplayers[player][f"street{i}CheckCallDone"] = False
                        if f"street{i}CheckRaiseDone" not in self.handsplayers[player]:
                            self.handsplayers[player][f"street{i}CheckRaiseDone"] = False

                        self.handsplayers[player][f"street{i}CheckCallRaiseChance"] = True

                        # Look for subsequent action
                        for subsequent_action in player_actions[1:]:
                            if subsequent_action[1] == "calls":
                                self.handsplayers[player][f"street{i}CheckCallDone"] = True
                                break
                            if subsequent_action[1] == "raises":
                                self.handsplayers[player][f"street{i}CheckRaiseDone"] = True
                                break

    def calc34BetStreet0(self, hand: Any) -> None:  # noqa: C901, PLR0912, PLR0915
        """Fills street0_(3|4)B(Chance|Done), other(3|4)BStreet0.

        For Stud games:
        - bet_level starts at 0 (bring-in doesn't count as first bet level)
        - 'completes' action is treated as aggressive action
        - bring-in player gets first action but it's not voluntary

        For Hold'em/Omaha games:
        - bet_level starts at 1 (blinds count as first bet level)
        """
        log.debug("Starting calc34BetStreet0 for hand ID: %s", hand.handid)
        bet_level = 0 if hand.gametype["base"] == "stud" else 1
        log.debug("calc34BetStreet0: Initial bet_level: %s (game base: %s)", bet_level, hand.gametype["base"])

        squeeze_chance, raise_chance, action_cnt, first_agressor = False, True, {}, None
        p0_in = {x[0] for x in hand.actions[hand.actionStreets[0]] if not x[-1]}
        p1_in = {x[0] for x in hand.actions[hand.actionStreets[1]]}
        p_in = p1_in.union(p0_in)
        log.debug("calc34BetStreet0: Players in hand: %s", p_in)

        for p in p_in:
            action_cnt[p] = 0

        log.debug("calc34BetStreet0: Processing preflop actions")
        for action in hand.actions[hand.actionStreets[1]]:
            pname, act = action[0], action[1]
            # For Stud, 'completes' is an aggressive action like 'raises' and 'bets'
            aggr = act in ("raises", "bets", "completes")
            allin = False

            # Debug logging
            log.debug("calc34BetStreet0: Processing %s %s, bet_level=%s, aggr=%s", pname, act, bet_level, aggr)
            player_stats = self.handsplayers.get(pname)
            if not player_stats:
                log.debug("calc34BetStreet0: Player %s not found in handsplayers", pname)
                continue

            action_cnt[pname] += 1
            if len(action) > MIN_ACTION_LENGTH_FOR_ALLIN and act != "discards":
                allin = action[-1]
                log.debug("calc34BetStreet0: Player %s is all-in: %s", pname, allin)

            if len(p_in) == 1 and action_cnt[pname] == 1:
                raise_chance = False
                log.debug("calc34BetStreet0: Only one player left, setting raise_chance=False for %s", pname)
                player_stats["street0AggrChance"] = raise_chance

            if act == "folds" or allin or player_stats["sitout"]:
                log.debug(
                    "calc34BetStreet0: Removing player %s from active players (fold=%s, allin=%s, sitout=%s)",
                    pname,
                    act == "folds",
                    allin,
                    player_stats["sitout"],
                )
                p_in.discard(pname)
                if player_stats["sitout"]:
                    continue

            if bet_level == 0:
                if aggr:
                    if first_agressor is None:
                        first_agressor = pname
                        log.debug("calc34BetStreet0: First aggressor set to %s", first_agressor)
                    bet_level += 1
                    log.debug("calc34BetStreet0: Bet level increased to %s", bet_level)
                continue

            if bet_level == 1:
                log.debug("calc34BetStreet0: Setting 2B chance for %s: %s", pname, raise_chance)
                player_stats["street0_2BChance"] = raise_chance
                if aggr:
                    if first_agressor is None:
                        first_agressor = pname
                        log.debug("calc34BetStreet0: First aggressor set to %s", first_agressor)
                    log.debug("calc34BetStreet0: Setting 2B done for %s", pname)
                    player_stats["street0_2BDone"] = True
                    bet_level += 1
                    log.debug("calc34BetStreet0: Bet level increased to %s", bet_level)
                continue

            if bet_level == THREE_BET_LEVEL:
                log.debug("calc34BetStreet0: Setting 3B chance for %s: %s", pname, raise_chance)
                player_stats["street0_3BChance"] = raise_chance
                log.debug("calc34BetStreet0: Setting squeeze chance for %s: %s", pname, squeeze_chance)
                player_stats["street0_SqueezeChance"] = squeeze_chance
                if pname == first_agressor:
                    log.debug("calc34BetStreet0: Setting fold to 2B chance for original aggressor %s", pname)
                    player_stats["street0_FoldTo2BChance"] = True
                    if act == "folds":
                        log.debug("calc34BetStreet0: Setting fold to 2B done for %s", pname)
                        player_stats["street0_FoldTo2BDone"] = True
                if not squeeze_chance and act == "calls":
                    squeeze_chance = True
                    log.debug("calc34BetStreet0: Squeeze chance activated by %s call", pname)
                    continue
                if aggr:
                    log.debug("calc34BetStreet0: Setting 3B done for %s", pname)
                    player_stats["street0_3BDone"] = True
                    log.debug("calc34BetStreet0: Setting squeeze done for %s: %s", pname, squeeze_chance)
                    player_stats["street0_SqueezeDone"] = squeeze_chance
                    bet_level += 1
                    log.debug("calc34BetStreet0: Bet level increased to %s", bet_level)
                continue

            if bet_level == FOUR_BET_LEVEL:
                if pname == first_agressor:
                    log.debug("calc34BetStreet0: Setting 4B chance for original aggressor %s: %s", pname, raise_chance)
                    player_stats["street0_4BChance"] = raise_chance
                    log.debug("calc34BetStreet0: Setting fold to 3B chance for original aggressor %s", pname)
                    player_stats["street0_FoldTo3BChance"] = True
                    if aggr:
                        log.debug("calc34BetStreet0: Setting 4B done for original aggressor %s", pname)
                        player_stats["street0_4BDone"] = raise_chance
                        bet_level += 1
                        log.debug("calc34BetStreet0: Bet level increased to %s", bet_level)
                    elif act == "folds":
                        log.debug("calc34BetStreet0: Setting fold to 3B done for original aggressor %s", pname)
                        player_stats["street0_FoldTo3BDone"] = True
                        break
                else:
                    log.debug("calc34BetStreet0: Setting C4B chance for %s: %s", pname, raise_chance)
                    player_stats["street0_C4BChance"] = raise_chance
                    if aggr:
                        log.debug("calc34BetStreet0: Setting C4B done for %s", pname)
                        player_stats["street0_C4BDone"] = raise_chance
                        bet_level += 1
                        log.debug("calc34BetStreet0: Bet level increased to %s", bet_level)
                continue

            if bet_level == FOLD_TO_4BET_LEVEL and pname != first_agressor:
                log.debug("calc34BetStreet0: Setting fold to 4B chance for %s", pname)
                player_stats["street0_FoldTo4BChance"] = True
                if act == "folds":
                    log.debug("calc34BetStreet0: Setting fold to 4B done for %s", pname)
                    player_stats["street0_FoldTo4BDone"] = True

        log.debug("calc34BetStreet0: Completed calc34BetStreet0 for hand ID: %s", hand.handid)

    def calcFaceLimpers(self, hand: Any) -> None:
        """Count the limpers each player faced before their first preflop action.

        A limper is a player who calls while the pot is still unraised (only the
        blinds have acted). For each player, ``street0_FaceLimpers`` records how
        many limps had occurred when they first got to act preflop. Once the pot
        is raised, later calls are cold-calls of a raise, not limps, so counting
        stops. Mirrors PT4 ``cnt_p_face_limpers``.
        """
        if not getattr(self, "handsplayers", None):
            return

        limpers = 0
        raised = False
        acted: set[str] = set()
        for action in hand.actions.get(hand.actionStreets[1], []):
            pname, act = action[0], action[1]
            ps = self.handsplayers.get(pname)
            if ps is None:
                continue
            if pname not in acted:
                acted.add(pname)
                # PT4 only counts limpers faced while the pot is still unraised:
                # a player whose first action is after a raise faced a raise, not
                # limpers, so they record 0.
                if not raised:
                    ps["street0_FaceLimpers"] = limpers
            if raised:
                continue
            if act == "calls":
                limpers += 1
            elif act in ("raises", "bets", "completes"):
                raised = True

    def calcGpStats(self, hand: Any) -> None:
        """Open-sizing and limp frequencies (PT4 "GenerationPoker" cnt_gp_* pack).

        Reuses the first-in flags from :meth:`calcSteals` (so this must run after
        it) and adds an open-size bucket:

        * ``cnt_gp_open_opp`` — had the chance to open (``raiseFirstInChance``);
          this is the denominator for all three GP frequencies.
        * ``cnt_gp_2x`` / ``cnt_gp_os`` — the player opened (``raisedFirstIn``);
          the open is an *open-shove* ("OS") when the raise-to is >= 40% of the
          player's own starting stack, otherwise a normal open ("2X"). The 40%
          threshold matches PT4's ``amt_p_raise_made / amt_before``.
        * ``cnt_gp_limp`` — the player's first voluntary preflop action was a
          call while the pot was still unraised (PT4 ``flg_p_limp``).
        """
        if not getattr(self, "handsplayers", None):
            return
        streets = getattr(hand, "actionStreets", [])
        if len(streets) < MIN_STREETS_FOR_PREFLOP:
            return
        preflop = hand.actions.get(streets[1], [])

        # Raise-to of each player's first preflop raise (their open size).
        first_rt: dict[str, Decimal] = {}
        for a in preflop:
            if a[1] == "raises" and a[0] not in first_rt and len(a) > 3:
                first_rt[a[0]] = _to_decimal(a[3])

        # Limp = first voluntary action is a call while the pot is still unraised.
        limpers: set[str] = set()
        raised = False
        acted: set[str] = set()
        for a in preflop:
            pname, act = a[0], a[1]
            if pname not in acted:
                acted.add(pname)
                if not raised and act in ("calls", "completes"):
                    limpers.add(pname)
            if act == "raises":
                raised = True

        shove = Decimal("0.4")
        for pname, ps in self.handsplayers.items():
            if ps.get("raiseFirstInChance"):
                ps["cnt_gp_open_opp"] = 1
            if ps.get("raisedFirstIn"):
                rt = first_rt.get(pname, Decimal(0))
                stack = _to_decimal(ps.get("startCash", 0)) / CENTS_MULTIPLIER
                if stack > 0 and rt / stack >= shove:
                    ps["cnt_gp_os"] = 1
                else:
                    ps["cnt_gp_2x"] = 1
            if pname in limpers:
                ps["cnt_gp_limp"] = 1

    def calcSqueezeDefense(self, hand: Any) -> None:
        """Mark squeeze-defense opportunities and fold responses preflop.

        A squeeze is a preflop 3-bet made after an open-raise *and* at least one
        cold-call. The players who already invested (the original raiser and the
        caller(s)) then face the squeeze and may defend (fold/call/re-raise).
        ``street0_FoldToSqueezeChance`` marks that they faced it (PT4
        ``flg_p_squeeze_def_opp``); ``street0_FoldToSqueezeDone`` marks a fold,
        so the HUD can show a fold-to-squeeze percentage.
        """
        if not getattr(self, "handsplayers", None):
            return

        bet_level = 0 if hand.gametype["base"] == "stud" else 1
        raiser = None
        callers: list[str] = []
        squeeze = False
        defenders: set[str] = set()
        faced: set[str] = set()

        for action in hand.actions.get(hand.actionStreets[1], []):
            pname, act = action[0], action[1]
            ps = self.handsplayers.get(pname)
            if ps is None:
                continue

            # A squeeze is live: defenders who still act face it (record once).
            if squeeze and pname in defenders and pname not in faced:
                faced.add(pname)
                ps["street0_FoldToSqueezeChance"] = True
                if act == "folds":
                    ps["street0_FoldToSqueezeDone"] = True

            if squeeze:
                continue

            aggr = act in ("raises", "bets", "completes")
            if bet_level == 2 and act == "calls":
                callers.append(pname)
            if aggr:
                bet_level += 1
                if bet_level == 2:
                    raiser = pname
                elif bet_level == 3 and callers:
                    # This raise is a squeeze: the raiser + caller(s) are the
                    # defenders (the squeezer itself is excluded).
                    squeeze = True
                    defenders = {name for name in [raiser, *callers] if isinstance(name, str) and name != pname}

    def calc3BetPostflop(self, hand: Any) -> None:
        """Per-street postflop 3-bet (re-raise) chance/done and fold-to-3bet.

        A postflop 3-bet is the third level of aggression on a street
        (bet -> raise -> re-raise), mirroring PT4's ``flg_f/t/r_3bet``. For each
        postflop street (flop, turn, river) ``bet_level`` counts aggressive
        actions; a player faces a 3-bet opportunity when it is their turn with
        ``bet_level == 2`` (a bet and a raise have already happened) and
        completes it by raising. The level-2 raiser then faces fold-to-3bet once
        a re-raise lands.

        Results are written to the ``street{1,2,3}_3BChance/3BDone`` and
        ``FoldTo3BChance/Done`` player keys.
        """
        if not getattr(self, "handsplayers", None):
            return
        # actionStreets: [BLINDSANTES, PREFLOP, FLOP, TURN, RIVER] for hold'em.
        for idx, street in enumerate(hand.actionStreets[2:], start=1):
            bet_level = 0
            raiser = None  # player who pushed bet_level to 2 (the "raise")
            for action in hand.actions.get(street, []):
                pname, act = action[0], action[1]
                ps = self.handsplayers.get(pname)
                if ps is None:
                    continue
                aggr = act in ("bets", "raises", "completes")
                # Facing a raise after a bet: this player can re-raise (3-bet).
                if bet_level == 2 and pname != raiser:
                    ps[f"street{idx}_3BChance"] = True
                    if aggr:
                        ps[f"street{idx}_3BDone"] = True
                # The level-2 raiser, once a 3-bet has landed, faces fold-to-3bet.
                if bet_level >= 3 and pname == raiser:
                    ps[f"street{idx}_FoldTo3BChance"] = True
                    if act == "folds":
                        ps[f"street{idx}_FoldTo3BDone"] = True
                if aggr:
                    bet_level += 1
                    if bet_level == 2:
                        raiser = pname

    def calc4BetPostflop(self, hand: Any) -> None:
        """Per-street postflop 4-bet chance/done and fold-to-4bet.

        A postflop 4-bet is the fourth level of aggression on a street
        (bet -> raise -> re-raise -> re-re-raise), mirroring PT4's
        ``flg_f/t/r_4bet`` family. The player who made the 3-bet then faces
        fold-to-4bet once a 4-bet lands.
        """
        if not getattr(self, "handsplayers", None):
            return

        for idx, street in enumerate(hand.actionStreets[2:], start=1):
            bet_level = 0
            three_bettor = None
            for action in hand.actions.get(street, []):
                pname, act = action[0], action[1]
                ps = self.handsplayers.get(pname)
                if ps is None:
                    continue

                aggr = act in ("bets", "raises", "completes")
                if bet_level == 3 and pname != three_bettor:
                    ps[f"street{idx}_4BChance"] = True
                    if aggr:
                        ps[f"street{idx}_4BDone"] = True
                if bet_level >= 4 and pname == three_bettor:
                    ps[f"street{idx}_FoldTo4BChance"] = True
                    if act == "folds":
                        ps[f"street{idx}_FoldTo4BDone"] = True
                if aggr:
                    bet_level += 1
                    if bet_level == 3:
                        three_bettor = pname

    def calcPostflopOpen(self, hand: Any) -> None:
        """Track who had a chance to make, and who made, the first postflop bet.

        PT4's flop/turn/river open flags represent the first voluntary bet into
        an unopened postflop street. Players who act before the first bet have an
        opportunity; the player who makes that first bet also records done.
        """
        if not getattr(self, "handsplayers", None):
            return

        for idx, street in enumerate(hand.actionStreets[2:], start=1):
            opened = False
            for action in hand.actions.get(street, []):
                pname, act = action[0], action[1]
                ps = self.handsplayers.get(pname)
                if ps is None or opened:
                    continue

                ps[f"street{idx}OpenChance"] = True
                if act in ("bets", "completes"):
                    ps[f"street{idx}OpenDone"] = True
                    opened = True

    def calcPostflopFirstRaise(self, hand: Any) -> None:
        """Mark the first player to raise on each postflop street."""
        if not getattr(self, "handsplayers", None):
            return

        for idx, street in enumerate(hand.actionStreets[2:], start=1):
            for action in hand.actions.get(street, []):
                pname, act = action[0], action[1]
                if act == "raises" and pname in self.handsplayers:
                    self.handsplayers[pname][f"street{idx}FirstRaise"] = True
                    break

    def calcFaceRaise(self, hand: Any) -> None:
        """Mark players who act while facing a raise on each street."""
        if not getattr(self, "handsplayers", None):
            return

        for idx, street in enumerate(hand.actionStreets[1:], start=0):
            raise_seen = False
            for action in hand.actions.get(street, []):
                pname, act = action[0], action[1]
                ps = self.handsplayers.get(pname)
                if ps is not None and raise_seen and act not in (
                    "small blind",
                    "big blind",
                    "secondsb",
                    "both",
                    "button blind",
                    "ante",
                    "bringin",
                ):
                    ps[f"street{idx}FaceRaise"] = True
                if act in ("raises", "completes"):
                    raise_seen = True

    def calcLimpStreet0(self, hand: Any) -> None:
        """Calculate limp statistics for preflop.

        PT4 behavior (verified by testing):
        - street0Limp = False for BOTH open-limp AND over-limp
        - PT4 does NOT track limps in the legacy system (they're just calls)

        Modern behavior (separate stats for better tracking):
        - street0OpenLimp = True for open-limp (first to limp)
        - street0Limp = True for over-limp only
        """
        log.debug("Starting calcLimpStreet0 for hand ID: %s", hand.handid)
        if not hasattr(self, "handsplayers"):
            log.debug("calcLimpStreet0: handsplayers not available, returning")
            return

        preflop_actions = hand.actions.get(hand.actionStreets[1], [])
        log.debug("calcLimpStreet0: Preflop actions: %s", preflop_actions)
        if not preflop_actions:
            log.debug("calcLimpStreet0: No preflop actions, returning")
            return

        # Track if anyone has limped yet (for open vs over-limp distinction)
        someone_limped = False

        for action in preflop_actions:
            player_name = action[0]
            action_type = action[1]
            player_stats = self.handsplayers.get(player_name)
            if not player_stats:
                log.debug("calcLimpStreet0: Player %s not found in handsplayers", player_name)
                continue

            log.debug(
                "calcLimpStreet0: Processing %s action %s, someone_limped=%s", player_name, action_type, someone_limped
            )

            # Check if this is a limp (call without raise)
            if action_type == "calls":
                if not someone_limped:
                    # This is an open limp (first to limp)
                    # Legacy: street0Limp = False (PT4 doesn't track limps)
                    # Modern: open_limp_done = True
                    log.debug("calcLimpStreet0: Setting open limp for %s", player_name)
                    player_stats["street0Limp"] = False
                    player_stats["street0OpenLimp"] = True
                    someone_limped = True
                else:
                    # This is an over-limp (limping after someone else)
                    # Legacy: street0Limp = False (PT4 doesn't track limps)
                    # Modern: limp_done = True
                    log.debug("calcLimpStreet0: Setting over-limp for %s", player_name)
                    player_stats["street0Limp"] = False
                    player_stats["street0OpenLimp"] = False
            else:
                log.debug("calcLimpStreet0: Action %s is not a call, skipping limp calculation", action_type)

        log.debug("calcLimpStreet0: Completed calcLimpStreet0 for hand ID: %s", hand.handid)

    def calcCalledRaiseStreet0(self, hand: Any) -> None:
        """Fill street0CalledRaiseChance, street0CalledRaiseDone.

        For flop games, go through the preflop actions:
            skip through first raise
            For each subsequent action:
                if the next action is fold :
                    player chance + 1
                if the next action is raise :
                    player chance + 1
                if the next non-fold action is call :
                    player chance + 1
                    player done + 1
                    skip through list to the next raise action.
        """
        fast_forward = True
        for tupleread in hand.actions[hand.actionStreets[1]]:
            action = tupleread[1]
            if fast_forward:
                if action in ("raises", "completes"):
                    fast_forward = False  # raisefound, end fast-forward
            else:
                player = tupleread[0]
                player_stats = self.handsplayers[player]
                player_stats["street0CalledRaiseChance"] += 1
                if action == "calls":
                    player_stats["street0CalledRaiseDone"] += 1
                    fast_forward = True

    def calcSteals(self, hand: Any) -> None:  # noqa: C901, PLR0912
        """Fills raiseFirstInChance|raisedFirstIn, fold(Bb|Sb)ToSteal(Chance|).

        Steal attempt - open raise on positions 1 0 S - i.e. CO, BU, SB
                        (note: I don't think PT2 counts SB steals in HU hands, maybe we shouldn't?)
        Fold to steal - folding blind after steal attemp wo any other callers or raisers
        """
        log.debug("Starting calcSteals for hand ID: %s", hand.handid)
        steal_attempt = False
        stealer = None
        if hand.gametype["base"] == "stud":
            steal_positions: tuple[int | str, ...] = (2, 1, 0)
        elif len([x for x in hand.actions[hand.actionStreets[0]] if x[1] == "button blind"]) > 0:
            steal_positions = (3, 2, 1)
        else:
            steal_positions = (1, 0, "S")
        log.debug("calcSteals: Steal positions: %s", steal_positions)

        pot_opened = False
        first_raise_seen = False
        for action in hand.actions[hand.actionStreets[1]]:
            pname, act = action[0], action[1]
            player_stats = self.handsplayers.get(pname)
            if not player_stats:
                log.debug("calcSteals: Player %s not found in handsplayers", pname)
                continue
            posn = player_stats.get("position")
            log.debug("calcSteals DEBUG: pname=%s, posn=%s, id(player_stats)=%s", pname, posn, id(player_stats))
            if player_stats["sitout"]:
                log.debug("calcSteals: Player %s is sitting out, skipping", pname)
                continue

            if posn == "B":
                # NOTE: Stud games will never hit this section
                if steal_attempt:
                    log.debug("calcSteals: Setting BB steal stats for %s", pname)
                    player_stats["foldBbToStealChance"] = True
                    player_stats["raiseToStealChance"] = True
                    player_stats["foldedBbToSteal"] = act == "folds"
                    player_stats["raiseToStealDone"] = act == "raises"
                    if stealer:
                        success = act == "folds"
                        log.debug("calcSteals: Setting steal success for %s: %s", stealer, success)
                        self.handsplayers[stealer]["success_Steal"] = success
                break

            if posn == "S":
                log.debug("calcSteals: Setting SB steal stats for %s, steal_attempt=%s", pname, steal_attempt)
                player_stats["raiseToStealChance"] = steal_attempt
                player_stats["foldSbToStealChance"] = steal_attempt
                player_stats["foldedSbToSteal"] = steal_attempt and act == "folds"
                player_stats["raiseToStealDone"] = steal_attempt and act == "raises"
                if steal_attempt and stealer:
                    success = act == "folds" and hand.gametype["base"] == "stud"
                    log.debug("calcSteals: Setting steal success for %s (stud): %s", stealer, success)
                    self.handsplayers[stealer]["success_Steal"] = success

            if steal_attempt and act != "folds":
                log.debug("calcSteals: Steal attempt ended by non-fold action %s from %s", act, pname)
                break

            # Skip forced blinds/antes but NOT "checks" if someone posted out of position
            if act in ("bringin", "small blind", "big blind", "secondsb", "both", "button blind"):
                continue

            # Identify First Raise opportunity/done (matches PT4 flg_p_first_raise)
            if not first_raise_seen:
                if act in ("bets", "raises", "completes"):
                    log.debug("calcSteals: Player %s made the FIRST RAISE", pname)
                    player_stats["raisedFirstIn"] = True  # We use this key for First Raise parity
                    first_raise_seen = True
                    # Also set stealDone if it's an RFI from steal position
                    if not pot_opened and posn in steal_positions:
                        log.debug("calcSteals: Steal done by %s", pname)
                        player_stats["stealDone"] = True
                        steal_attempt = True
                        stealer = pname

            # Identify RFI opportunity (unopened pot). Facing an unopened pot is
            # also the opportunity to open-limp (call instead of raise).
            if not pot_opened:
                log.debug("calcSteals: Pot is UNOPENED for %s", pname)
                player_stats["raiseFirstInChance"] = True
                player_stats["street0OpenLimpChance"] = True
                if posn in steal_positions:
                    log.debug("calcSteals: Setting stealChance for %s (position %s)", pname, posn)
                    player_stats["stealChance"] = True

                if act in ("bets", "raises", "calls", "completes", "checks"):
                    log.debug("calcSteals: Pot OPENED by %s with %s", pname, act)
                    pot_opened = True

            if first_raise_seen and posn not in steal_positions and act not in ("folds", "bringin", "small blind", "big blind", "secondsb", "both", "button blind"):
                log.debug("calcSteals: Non-steal position %s with action %s after first raise, ending loop", posn, act)
                break

        log.debug("calcSteals: Completed calcSteals for hand ID: %s", hand.handid)

    def calcFlopStats(self, hand: Any) -> None:
        """Calculate flop-specific statistics."""
        log.debug("Starting calcFlopStats for hand ID: %s", hand.handid)
        if not hasattr(self, "handsplayers"):
            log.debug("calcFlopStats: handsplayers not available, returning")
            return

        # Get flop actions (street2 in actionStreets, since 0=blinds, 1=preflop, 2=flop)
        if len(hand.actionStreets) < 3:
            log.debug("calcFlopStats: No flop street available (actionStreets length: %s)", len(hand.actionStreets))
            return  # No flop

        flop_actions = hand.actions.get(hand.actionStreets[2], [])
        log.debug("calcFlopStats: Flop actions extracted: %s", flop_actions)
        if not flop_actions:
            log.debug("calcFlopStats: No flop actions found")
            return

        # Find preflop aggressor (last raiser/bettor from preflop)
        preflop_actions = hand.actions.get(hand.actionStreets[1], [])
        log.debug("calcFlopStats: Preflop actions: %s", preflop_actions)
        preflop_aggressor = None
        for act in reversed(preflop_actions):
            if act[1] in ["raises", "bets"]:
                preflop_aggressor = act[0]
                break
        log.debug("calcFlopStats: Preflop aggressor: %s", preflop_aggressor)

        # If no preflop aggressor, skip donk calculations
        if not preflop_aggressor:
            log.debug("calcFlopStats: No preflop aggressor found, skipping donk calculations")
            return

        # Get players who saw the flop
        flop_players = [act[0] for act in flop_actions]
        flop_players = list(dict.fromkeys(flop_players))  # Remove duplicates while preserving order
        log.debug("calcFlopStats: Flop players: %s", flop_players)

        # Find position of preflop aggressor in flop action order
        aggressor_position = -1
        if preflop_aggressor in flop_players:
            aggressor_position = flop_players.index(preflop_aggressor)
        log.debug("calcFlopStats: Aggressor position: %s", aggressor_position)

        # Players who act before the aggressor are out of position
        oop_players = flop_players[:aggressor_position] if aggressor_position >= 0 else []
        log.debug("calcFlopStats: OOP players: %s", oop_players)

        # Set donk opportunity for OOP players who saw the flop
        log.debug("calcFlopStats: Setting donk opportunities for OOP players")
        for player in oop_players:
            if player in self.handsplayers and self.handsplayers[player].get("street1Seen", False):
                log.debug("calcFlopStats: Setting flg_f_donk_opp=True for player %s", player)
                self.handsplayers[player]["flg_f_donk_opp"] = True
            else:
                log.debug(
                    "calcFlopStats: Skipping donk opportunity for player %s (not in handsplayers or didn't see flop)",
                    player,
                )

        # Find first bet on flop (donk bet)
        first_bet_player = None
        for act in flop_actions:
            if act[1] in ["bets", "raises"]:
                first_bet_player = act[0]
                break
        log.debug("calcFlopStats: First bet player: %s", first_bet_player)

        # If the first bet was by an OOP player, mark as donk
        if first_bet_player and first_bet_player in oop_players:
            log.debug(
                "calcFlopStats: Setting flg_f_donk=True for player %s (first bet by OOP player)", first_bet_player
            )
            self.handsplayers[first_bet_player]["flg_f_donk"] = True
            if (
                preflop_aggressor
                and preflop_aggressor in self.handsplayers
                and self.handsplayers[preflop_aggressor].get("street1Seen", False)
            ):
                log.debug(
                    "calcFlopStats: Setting flg_f_donk_def_opp=True for previous aggressor %s",
                    preflop_aggressor,
                )
                self.handsplayers[preflop_aggressor]["flg_f_donk_def_opp"] = True
        else:
            log.debug(
                "calcFlopStats: No donk bet detected (first_bet_player=%s, oop_players=%s)",
                first_bet_player,
                oop_players,
            )

        # Set fold and other flags
        log.debug("calcFlopStats: Setting fold and other flags")
        for act in flop_actions:
            player_name = act[0]
            action_type = act[1]

            if player_name not in self.handsplayers:
                log.debug("calcFlopStats: Player %s not in handsplayers, skipping", player_name)
                continue

            if action_type == "folds":
                log.debug("calcFlopStats: Setting flg_f_fold=True for player %s", player_name)
                self.handsplayers[player_name]["flg_f_fold"] = True

        # Set position and first to act flags
        log.debug("calcFlopStats: Setting position and first to act flags")
        for player in hand.players:
            player_name = player[1]
            has_position = self.handsplayers[player_name].get("street1InPosition", False)
            first_to_act = self.handsplayers[player_name].get("street1FirstToAct", False)
            log.debug(
                "calcFlopStats: Player %s - flg_f_has_position=%s, flg_f_first=%s",
                player_name,
                has_position,
                first_to_act,
            )
            self.handsplayers[player_name]["flg_f_has_position"] = has_position
            self.handsplayers[player_name]["flg_f_first"] = first_to_act

        log.debug("calcFlopStats: Completed calcFlopStats for hand ID: %s", hand.handid)

    def calcTurnStats(self, hand: Any) -> None:
        """Calculate turn-specific statistics."""
        log.debug("Starting calcTurnStats for hand ID: %s", hand.handid)
        if not hasattr(self, "handsplayers"):
            log.debug("calcTurnStats: handsplayers not available, returning")
            return

        # Get turn actions (street3 in actionStreets, since 0=blinds, 1=preflop, 2=flop, 3=turn)
        if len(hand.actionStreets) < 4:
            log.debug("calcTurnStats: No turn street available (actionStreets length: %s)", len(hand.actionStreets))
            return  # No turn

        # Validate that actionStreets[3] corresponds to turn street
        if hand.actionStreets[3] != "TURN":
            log.debug("calcTurnStats: Street 3 is not TURN, it's %s, returning", hand.actionStreets[3])
            return  # Not actually turn actions

        turn_actions = hand.actions.get(hand.actionStreets[3], [])
        log.debug("calcTurnStats: Turn actions extracted: %s", turn_actions)
        if not turn_actions:
            log.debug("calcTurnStats: No turn actions found")
            return

        # Find preflop aggressor (last raiser/bettor from preflop)
        preflop_actions = hand.actions.get(hand.actionStreets[1], [])
        log.debug("calcTurnStats: Preflop actions: %s", preflop_actions)
        preflop_aggressor = None
        for act in reversed(preflop_actions):
            if act[1] in ["raises", "bets"]:
                preflop_aggressor = act[0]
                break
        log.debug("calcTurnStats: Preflop aggressor: %s", preflop_aggressor)

        # Get players who saw the turn
        turn_players = [act[0] for act in turn_actions]
        turn_players = list(dict.fromkeys(turn_players))  # Remove duplicates while preserving order
        log.debug("calcTurnStats: Turn players: %s", turn_players)

        # For float and donk calculations, we need to consider the previous street's aggressor
        # For turn, the aggressor from flop
        flop_actions = hand.actions.get(hand.actionStreets[2], [])
        log.debug("calcTurnStats: Flop actions: %s", flop_actions)
        previous_aggressor = None
        for act in reversed(flop_actions):
            if act[1] in ["raises", "bets"]:
                previous_aggressor = act[0]
                break
        log.debug("calcTurnStats: Previous aggressor (from flop): %s", previous_aggressor)

        # If no previous aggressor, use preflop aggressor as fallback
        if not previous_aggressor:
            previous_aggressor = preflop_aggressor
            log.debug("calcTurnStats: Using preflop aggressor as fallback: %s", previous_aggressor)

        # Find position of previous aggressor in turn action order
        aggressor_position = -1
        if previous_aggressor and previous_aggressor in turn_players:
            aggressor_position = turn_players.index(previous_aggressor)
        log.debug("calcTurnStats: Aggressor position: %s", aggressor_position)

        # Players who act before the aggressor are out of position
        oop_players = turn_players[:aggressor_position] if aggressor_position >= 0 else []
        log.debug("calcTurnStats: OOP players: %s", oop_players)

        # Set donk opportunity for OOP players who saw the turn
        log.debug("calcTurnStats: Setting donk opportunities for OOP players")
        for player in oop_players:
            if player in self.handsplayers and self.handsplayers[player].get("street2Seen", False):
                log.debug("calcTurnStats: Setting flg_t_donk_opp=True for player %s", player)
                self.handsplayers[player]["flg_t_donk_opp"] = True
            else:
                log.debug(
                    "calcTurnStats: Skipping donk opportunity for player %s (not in handsplayers or didn't see turn)",
                    player,
                )

        # Find first bet on turn (donk bet)
        first_bet_player = None
        for act in turn_actions:
            if act[1] in ["bets", "raises"]:
                first_bet_player = act[0]
                break
        log.debug("calcTurnStats: First bet player: %s", first_bet_player)

        # If the first bet was by an OOP player, mark as donk
        if first_bet_player and first_bet_player in oop_players:
            log.debug(
                "calcTurnStats: Setting flg_t_donk=True for player %s (first bet by OOP player)", first_bet_player
            )
            self.handsplayers[first_bet_player]["flg_t_donk"] = True
            if (
                previous_aggressor
                and previous_aggressor in self.handsplayers
                and self.handsplayers[previous_aggressor].get("street2Seen", False)
            ):
                log.debug(
                    "calcTurnStats: Setting flg_t_donk_def_opp=True for previous aggressor %s",
                    previous_aggressor,
                )
                self.handsplayers[previous_aggressor]["flg_t_donk_def_opp"] = True
        else:
            log.debug(
                "calcTurnStats: No donk bet detected (first_bet_player=%s, oop_players=%s)",
                first_bet_player,
                oop_players,
            )

        self._set_float_stats(
            turn_actions,
            flop_actions,
            previous_aggressor,
            "street2Seen",
            "flg_t_float_opp",
            "flg_t_float",
            "flg_t_float_def_opp",
            "calcTurnStats",
        )

        # Set fold and other flags
        log.debug("calcTurnStats: Setting fold and other flags")
        for act in turn_actions:
            player_name = act[0]
            action_type = act[1]

            if player_name not in self.handsplayers:
                log.debug("calcTurnStats: Player %s not in handsplayers, skipping", player_name)
                continue

            if action_type == "folds":
                log.debug("calcTurnStats: Setting flg_t_fold=True for player %s", player_name)
                self.handsplayers[player_name]["flg_t_fold"] = True

        # Set position and first to act flags
        log.debug("calcTurnStats: Setting position and first to act flags")
        for player in hand.players:
            player_name = player[1]
            has_position = self.handsplayers[player_name].get("street3InPosition", False)
            first_to_act = self.handsplayers[player_name].get("street3FirstToAct", False)
            log.debug(
                "calcTurnStats: Player %s - flg_t_has_position=%s, flg_t_first=%s",
                player_name,
                has_position,
                first_to_act,
            )
            self.handsplayers[player_name]["flg_t_has_position"] = has_position
            self.handsplayers[player_name]["flg_t_first"] = first_to_act

        log.debug("calcTurnStats: Completed calcTurnStats for hand ID: %s", hand.handid)

    def calcRiverStats(self, hand: Any) -> None:
        """Calculate river-specific statistics."""
        log.debug("Starting calcRiverStats for hand ID: %s", hand.handid)
        if not hasattr(self, "handsplayers"):
            log.debug("calcRiverStats: handsplayers not available, returning")
            return

        # Get river actions (street4 in actionStreets, since 0=blinds, 1=preflop, 2=flop, 3=turn, 4=river)
        if len(hand.actionStreets) < 5:
            log.debug("calcRiverStats: No river street available (actionStreets length: %s)", len(hand.actionStreets))
            return  # No river

        river_actions = hand.actions.get(hand.actionStreets[4], [])
        log.debug("calcRiverStats: River actions extracted: %s", river_actions)
        if not river_actions:
            log.debug("calcRiverStats: No river actions found")
            return

        # Find previous aggressor from turn
        turn_actions = hand.actions.get(hand.actionStreets[3], [])
        log.debug("calcRiverStats: Turn actions: %s", turn_actions)
        previous_aggressor = None
        for act in reversed(turn_actions):
            if act[1] in ["raises", "bets"]:
                previous_aggressor = act[0]
                break
        log.debug("calcRiverStats: Previous aggressor (from turn): %s", previous_aggressor)

        # If no turn aggressor, use flop aggressor as fallback
        if not previous_aggressor:
            flop_actions = hand.actions.get(hand.actionStreets[2], [])
            log.debug("calcRiverStats: Flop actions: %s", flop_actions)
            for act in reversed(flop_actions):
                if act[1] in ["raises", "bets"]:
                    previous_aggressor = act[0]
                    break
            log.debug("calcRiverStats: Using flop aggressor as fallback: %s", previous_aggressor)

        # If still no aggressor, use preflop aggressor as fallback
        if not previous_aggressor:
            preflop_actions = hand.actions.get(hand.actionStreets[1], [])
            log.debug("calcRiverStats: Preflop actions: %s", preflop_actions)
            for act in reversed(preflop_actions):
                if act[1] in ["raises", "bets"]:
                    previous_aggressor = act[0]
                    break
            log.debug("calcRiverStats: Using preflop aggressor as fallback: %s", previous_aggressor)

        # Get players who saw the river
        river_players = [act[0] for act in river_actions]
        river_players = list(dict.fromkeys(river_players))  # Remove duplicates while preserving order
        log.debug("calcRiverStats: River players: %s", river_players)

        # Find position of previous aggressor in river action order
        aggressor_position = -1
        if previous_aggressor and previous_aggressor in river_players:
            aggressor_position = river_players.index(previous_aggressor)
        log.debug("calcRiverStats: Aggressor position: %s", aggressor_position)

        # Players who act before the aggressor are out of position
        oop_players = river_players[:aggressor_position] if aggressor_position >= 0 else []
        log.debug("calcRiverStats: OOP players: %s", oop_players)

        # Set donk opportunity for OOP players who saw the river
        log.debug("calcRiverStats: Setting donk opportunities for OOP players")
        for player in oop_players:
            if player in self.handsplayers and self.handsplayers[player].get("street3Seen", False):
                log.debug("calcRiverStats: Setting flg_r_donk_opp=True for player %s", player)
                self.handsplayers[player]["flg_r_donk_opp"] = True
            else:
                log.debug(
                    "calcRiverStats: Skipping donk opportunity for player %s (not in handsplayers or didn't see river)",
                    player,
                )

        # Find first bet on river (donk bet)
        first_bet_player = None
        for act in river_actions:
            if act[1] in ["bets", "raises"]:
                first_bet_player = act[0]
                break
        log.debug("calcRiverStats: First bet player: %s", first_bet_player)

        # If the first bet was by an OOP player, mark as donk
        if first_bet_player and first_bet_player in oop_players:
            log.debug(
                "calcRiverStats: Setting flg_r_donk=True for player %s (first bet by OOP player)", first_bet_player
            )
            self.handsplayers[first_bet_player]["flg_r_donk"] = True
            if (
                previous_aggressor
                and previous_aggressor in self.handsplayers
                and self.handsplayers[previous_aggressor].get("street3Seen", False)
            ):
                log.debug(
                    "calcRiverStats: Setting flg_r_donk_def_opp=True for previous aggressor %s",
                    previous_aggressor,
                )
                self.handsplayers[previous_aggressor]["flg_r_donk_def_opp"] = True
        else:
            log.debug(
                "calcRiverStats: No donk bet detected (first_bet_player=%s, oop_players=%s)",
                first_bet_player,
                oop_players,
            )

        previous_float_actions = turn_actions if turn_actions else hand.actions.get(hand.actionStreets[2], [])
        self._set_float_stats(
            river_actions,
            previous_float_actions,
            previous_aggressor,
            "street3Seen",
            "flg_r_float_opp",
            "flg_r_float",
            "flg_r_float_def_opp",
            "calcRiverStats",
        )

        # Set fold and other flags
        log.debug("calcRiverStats: Setting fold and other flags")
        for act in river_actions:
            player_name = act[0]
            action_type = act[1]

            if player_name not in self.handsplayers:
                log.debug("calcRiverStats: Player %s not in handsplayers, skipping", player_name)
                continue

            if action_type == "folds":
                log.debug("calcRiverStats: Setting flg_r_fold=True for player %s", player_name)
                self.handsplayers[player_name]["flg_r_fold"] = True

        # Set position and first to act flags
        log.debug("calcRiverStats: Setting position and first to act flags")
        for player in hand.players:
            player_name = player[1]
            has_position = self.handsplayers[player_name].get("street4InPosition", False)
            first_to_act = self.handsplayers[player_name].get("street4FirstToAct", False)
            log.debug(
                "calcRiverStats: Player %s - flg_r_has_position=%s, flg_r_first=%s",
                player_name,
                has_position,
                first_to_act,
            )
            self.handsplayers[player_name]["flg_r_has_position"] = has_position
            self.handsplayers[player_name]["flg_r_first"] = first_to_act

        log.debug("calcRiverStats: Completed calcRiverStats for hand ID: %s", hand.handid)

    def calcEffectiveStack(self, hand: Any) -> None:  # noqa: C901, PLR0912
        """Calculate effective stack sizes for all players."""
        if not hasattr(self, "handsplayers"):
            return

        # Check if there are any actions (excluding BLINDSANTES)
        has_actions = False
        for street, actions in hand.actions.items():
            if street != "BLINDSANTES" and actions:
                has_actions = True
                break

        # If no actions, set all effective stacks to 0
        if not has_actions:
            for player_name in self.handsplayers:
                self.handsplayers[player_name]["effStack"] = 0
            return

        # Build a dictionary of player stacks for easier lookup
        # Exclude players who are sitting out
        player_stacks = {}
        for player in hand.players:
            player_name = player[1]
            if player_name in self.handsplayers and player_name not in hand.sitout:
                # Try to get stack from hand.stacks first, then player data, then handsplayers
                stack = 0

                # Check hand.stacks attribute first
                if hasattr(hand, "stacks") and player_name in hand.stacks:
                    with contextlib.suppress(ValueError, TypeError):
                        stack = int(CENTS_MULTIPLIER * hand.stacks[player_name])  # Convert to cents

                # Try player tuple data
                if stack == 0 and len(player) > MIN_PLAYER_TUPLE_LENGTH:
                    with contextlib.suppress(ValueError, TypeError, IndexError):
                        stack = int(CENTS_MULTIPLIER * Decimal(str(player[2])))  # Convert to cents

                # Finally try handsplayers
                if stack == 0:
                    stack = self.handsplayers[player_name].get("startCash", 0)

                if stack > 0:
                    player_stacks[player_name] = stack
                    # Update the player's startCash if it wasn't set
                    if self.handsplayers[player_name].get("startCash", 0) == 0:
                        self.handsplayers[player_name]["startCash"] = stack

        # Calculate effective stack for each player individually
        # Using formula: min(player_stack, max(opponent_stacks))
        for player_name in player_stacks:
            player_stack = player_stacks[player_name]

            # Find the largest opponent stack (excluding sitting out players)
            opponent_stacks = [stack for name, stack in player_stacks.items() if name != player_name]

            if opponent_stacks:
                max_opponent_stack = max(opponent_stacks)
                # Effective stack is the minimum of player's stack and largest opponent's stack
                effective_stack = min(player_stack, max_opponent_stack)
            else:
                # Only one player, effective stack is their own stack
                effective_stack = player_stack

            self.handsplayers[player_name]["effStack"] = effective_stack

        # Set effective stack to 0 for sitting out players
        for player in hand.players:
            player_name = player[1]
            if player_name in hand.sitout and player_name in self.handsplayers:
                self.handsplayers[player_name]["effStack"] = 0

    def calcFoldToOtherRaisedStreet(self, hand: Any) -> None:
        """Calculate fold to other raised street statistics."""
        if not hasattr(self, "handsplayers"):
            return

        for i in range(5):
            if i >= len(hand.actionStreets):
                continue

            street_name = hand.actionStreets[i]
            street_actions = hand.actions.get(street_name, [])

            # Find raises on this street
            raisers = [act[0] for act in street_actions if act[1] in ["raises", "bets"]]

            if raisers:
                for player in self.handsplayers:
                    if player not in raisers:
                        # Check if they folded to a raise
                        for act in street_actions:
                            if act[0] == player and act[1] == "folds":
                                self.handsplayers[player][f"otherRaisedStreet{i}"] = True
                                self.handsplayers[player][f"foldToOtherRaisedStreet{i}"] = True
                                break

    def noBetsBefore(self, actions: Any, street: Any, player: Any) -> bool:
        """Check if there were no bets before this player on this street."""
        street_actions = actions.get(street, [])

        for act in street_actions:
            if act[0] == player:
                break
            if act[1] in ["bets", "raises"]:
                return False
        return True

    def aggr(self, hand: Any, i: int) -> None:
        """Calculate aggression statistics for a given street."""
        aggrers = set()
        others = set()
        # Growl - actionStreets contains 'BLINDSANTES', which isn't actually an action street

        first_aggr_made = False
        for act in hand.actions[hand.actionStreets[i + 1]]:
            if first_aggr_made:
                others.add(act[0])
            if act[1] in ("completes", "bets", "raises"):
                aggrers.add(act[0])
                first_aggr_made = True

        for player in hand.players:
            if player[1] in aggrers:
                # Initialize street stats if they don't exist (for run-it-twice scenarios)
                if f"street{i}Aggr" not in self.handsplayers[player[1]]:
                    self.handsplayers[player[1]][f"street{i}Aggr"] = False
                self.handsplayers[player[1]][f"street{i}Aggr"] = True

        if len(aggrers) > 0 and i > 0:
            for playername in others:
                # Initialize street stats if they don't exist (for run-it-twice scenarios)
                if f"otherRaisedStreet{i}" not in self.handsplayers[playername]:
                    self.handsplayers[playername][f"otherRaisedStreet{i}"] = False
                self.handsplayers[playername][f"otherRaisedStreet{i}"] = True
                # print "otherRaised detected on handid "+str(hand.handid)+" for "+playername+" on street "+str(i)

        if i > 0 and len(aggrers) > 0:
            for playername in others:
                self.handsplayers[playername][f"otherRaisedStreet{i}"] = True
                # print "DEBUG: otherRaised detected on handid %s for %s on actionStreet[%s]: %s"
                #                           %(hand.handid, playername, hand.actionStreets[i+1], i)

    def calls(self, hand: Any, i: int) -> None:
        """Calculate call statistics for a given street."""
        for act in hand.actions[hand.actionStreets[i + 1]]:
            if act[1] in ("calls"):
                player_stats = self.handsplayers[act[0]]
                # Initialize street stats if they don't exist (for run-it-twice scenarios)
                if f"street{i}Calls" not in player_stats:
                    player_stats[f"street{i}Calls"] = 0
                player_stats[f"street{i}Calls"] = 1 + player_stats[f"street{i}Calls"]

    def bets(self, hand: Any, i: int) -> None:
        """Calculate bet statistics for a given street."""
        for act in hand.actions[hand.actionStreets[i + 1]]:
            if act[1] in ("bets"):
                player_stats = self.handsplayers[act[0]]
                # Initialize street stats if they don't exist (for run-it-twice scenarios)
                if f"street{i}Bets" not in player_stats:
                    player_stats[f"street{i}Bets"] = 0
                player_stats[f"street{i}Bets"] = 1 + player_stats[f"street{i}Bets"]

    def raises(self, hand: Any, i: int) -> None:
        """Calculate raise statistics for a given street."""
        for act in hand.actions[hand.actionStreets[i + 1]]:
            if act[1] in ("completes", "raises"):
                player_stats = self.handsplayers[act[0]]
                # Initialize street stats if they don't exist (for run-it-twice scenarios)
                if f"street{i}Raises" not in player_stats:
                    player_stats[f"street{i}Raises"] = 0
                player_stats[f"street{i}Raises"] = 1 + player_stats[f"street{i}Raises"]

    def folds(self, hand: Any, i: int) -> None:
        """Calculate fold statistics for a given street."""
        for act in hand.actions[hand.actionStreets[i + 1]]:
            if act[1] in ("folds"):
                player_stats = self.handsplayers[act[0]]
                # Initialize street stats if they don't exist (for run-it-twice scenarios)
                if f"otherRaisedStreet{i}" not in player_stats:
                    player_stats[f"otherRaisedStreet{i}"] = False
                if f"foldToOtherRaisedStreet{i}" not in player_stats:
                    player_stats[f"foldToOtherRaisedStreet{i}"] = False
                if player_stats[f"otherRaisedStreet{i}"]:
                    player_stats[f"foldToOtherRaisedStreet{i}"] = True
                    # print "DEBUG: fold detected on handid %s for %s on actionStreet[%s]: %s"
                    #                       %(hand.handid, act[0],hand.actionStreets[i+1], i)

    def assembleHandsStove(self, hand: Any) -> None:  # noqa: C901, PLR0912, PLR0915
        """Assemble hands stove data for equity calculations."""
        engine = pokereval
        if engine is None:
            return
        category = hand.gametype["category"]
        holecards: dict[str, dict[str, Any]] = {}
        holeplayers: list[str] = []
        base, evalgame, hilo, streets, last, hrange = Card.games[category]
        hi_lo_key = {"h": [("h", "hi")], "l": [("l", "low")], "s": [("h", "hi"), ("l", "low")], "r": [("l", "hi")]}
        boards = self.getBoardsDict(hand, base, streets)
        for player in hand.players:
            pname = player[1]
            hp = self.handsplayers[pname]
            if evalgame:
                hcs = hand.join_holecards(pname, asList=True)
                holecards[pname] = {}
                holecards[pname]["cards"] = []
                holecards[pname]["eq"] = 0
                holecards[pname]["committed"] = 0
                holeplayers.append(pname)
                for street, board in boards.items():
                    street_id = streets[street]
                    street_seen = hp[f"street{street_id!s}Seen"] if street_id > 0 else True
                    if (pname == hand.hero and street_seen) or (hp["showed"] and street_seen) or hp["sawShowdown"]:
                        board_id, hl, rank_id, value, _cards = 0, "n", 1, 0, None
                        for n in range(len(board["board"])):
                            street_idx = -1 if base == "hold" else street_id
                            cards = hcs[hrange[street_idx][0] : hrange[street_idx][1]]
                            board_id = (n + 1) if (len(board["board"]) > 1) else n
                            cards += board["board"][n] if (board["board"][n] and "omaha" not in evalgame) else []
                            bcards = board["board"][n] if (board["board"][n] and "omaha" in evalgame) else []
                            cards = [str(c) if Card.encodeCard(c) else "0x" for c in cards]
                            bcards = [str(b) if Card.encodeCard(b) else "0x" for b in bcards]
                            holecards[pname]["hole"] = cards[hrange[street_idx][0] : hrange[street_idx][1]]
                            holecards[pname]["cards"] += [cards]
                            notnull = ("0x" not in cards) and ("0x" not in bcards)
                            postflop = base == "hold" and len(board["board"][n]) >= MIN_POSTFLOP_BOARD_SIZE
                            maxcards = base != "hold" and len(cards) >= MIN_MAXCARDS_SIZE
                            if notnull and (postflop or maxcards):
                                for hl, side in hi_lo_key[hilo]:
                                    try:
                                        value, rank = engine.best(side, cards, bcards)
                                        rank_id = Card.hands[rank[0]][0]
                                        if rank is not None and rank[0] != "Nothing":
                                            _cards = "".join([engine.card2string(i)[0] for i in rank[1:]])
                                        else:
                                            _cards = None
                                        self.handsstove.append(
                                            [
                                                hand.dbid_hands,
                                                hand.playerIds[pname],
                                                street_id,
                                                board_id,
                                                hl,
                                                rank_id,
                                                value,
                                                _cards,
                                                0,
                                            ],
                                        )
                                    except RuntimeError:  # noqa: PERF203
                                        log.exception(
                                            "assembleHandsStove: error determining value and rank for hand %s %s",
                                            hand.handid,
                                            hand.in_path,
                                        )
                                        self.handsstove.append(
                                            [
                                                hand.dbid_hands,
                                                hand.playerIds[pname],
                                                street_id,
                                                board_id,
                                                "n",
                                                1,
                                                0,
                                                None,
                                                0,
                                            ],
                                        )
                            else:
                                self.handsstove.append(
                                    [hand.dbid_hands, hand.playerIds[pname], street_id, board_id, "n", 1, 0, None, 0],
                                )
            else:
                hl, street_id = hi_lo_key[hilo][0][0], 0
                if hp["sawShowdown"] or hp["showed"]:
                    hp["handString"] = hand.showdownStrings.get(pname)
                    street_id = streets[last]
                self.handsstove.append([hand.dbid_hands, hand.playerIds[player[1]], street_id, 0, hl, 1, 0, None, 0])

        if base == "hold" and evalgame:
            self.getAllInEV(hand, evalgame, holeplayers, boards, streets, holecards)

    def assembleHandsPots(self, hand: Any) -> None:  # noqa: C901, PLR0912, PLR0915
        """Assemble hands pots data and calculate winnings."""
        engine = pokereval
        if engine is None:
            return
        category = hand.gametype["category"]
        positions: list[Any] = []
        players_pots: dict[str, list[Any]] = {}
        pot_found: dict[str, list[Any]] = {}
        position_dict: dict[Any, str] = {}
        showdown = False
        allin_ante = False
        for p in hand.players:
            players_pots[p[1]] = [0, []]
            pot_found[p[1]] = [0, 0]
            position_dict[self.handsplayers[p[1]]["position"]] = p[1]
            positions.append(self.handsplayers[p[1]]["position"])
            if self.handsplayers[p[1]]["sawShowdown"]:
                showdown = True
                if (
                    self.handsplayers[p[1]]["position"] == ANTE_ALL_IN_POSITION
                    and self.handsplayers[p[1]]["winnings"] > 0
                ):
                    allin_ante = True
        # Sort positions handling both strings ('B', 'S') and integers
        positions.sort(
            reverse=True,
            key=lambda x: (isinstance(x, str), x) if not isinstance(x, str) else (False, ord(x)),
        )
        factor = 100
        if (
            hand.gametype["type"] == "tour"
            or (
                hand.gametype["type"] == "ring"
                and (hand.gametype["currency"] == "play" and (hand.sitename not in ("Winamax", "PacificPoker")))
            )
        ) and (not [n for (n, v) in hand.pot.pots if (n % Decimal("1.00")) != 0]):
            factor = 1
        hi_lo_key = {"h": ["hi"], "l": ["low"], "r": ["low"], "s": ["hi", "low"]}
        base, evalgame, hilo, streets, last, hrange = Card.games[category]
        if (
            (hand.sitename != "KingsClub" or hand.adjustCollected)  # Can't trust KingsClub draw/stud holecards
            and evalgame
            and (len(hand.pot.pots) > 1 or (showdown and (hilo == "s" or hand.runItTimes >= MIN_RUN_IT_TIMES)))
            and not allin_ante
        ):
            # print 'DEBUG hand.collected', hand.collected
            # print 'DEBUG hand.collectees', hand.collectees
            if not hand.cashedOut:
                for p in hand.players:
                    self.handsplayers[p[1]]["rake"] = 0
                hand.rake = 0
            for pot_id, (pot, players) in enumerate(hand.pot.pots):
                if pot_id == 0:
                    pot += sum(hand.pot.common.values()) + hand.pot.stp  # noqa: PLW2901
                boards, board_id = self.getBoardsList(hand), 0
                for b in boards:
                    board_id += hand.runItTimes >= MIN_RUN_IT_TIMES
                    pot_board = Decimal(int(pot / len(boards) * factor)) / factor
                    mod_board = pot - pot_board * len(boards)
                    if board_id == 1:
                        pot_board += mod_board
                    holeplayers, holecards = [], []
                    for p in players:
                        hcs = hand.join_holecards(p, asList=True)
                        holes = [
                            str(c)
                            for c in hcs[hrange[-1][0] : hrange[-1][1]]
                            if Card.ENCODE_CARD_LIST.get(c) is not None or c == "0x"
                        ]
                        board = [str(c) for c in b if "omaha" in evalgame]
                        if "omaha" not in evalgame:
                            holes = holes + [str(c) for c in b if base == "hold"]
                        if "0x" not in holes and "0x" not in board:
                            holecards.append(holes)
                            holeplayers.append(p)
                    if len(holecards) > 1:
                        try:
                            win = engine.winners(game=evalgame, pockets=holecards, board=board)
                        except RuntimeError:
                            log.exception(
                                "assembleHandsPots: error evaluating winners for hand %s %s",
                                hand.handid,
                                hand.in_path,
                            )
                            win = {}
                            win[hi_lo_key[hilo][0]] = [0]
                    else:
                        win = {}
                        win[hi_lo_key[hilo][0]] = [0]
                    for hl in hi_lo_key[hilo]:
                        if hl in win and len(win[hl]) > 0:
                            pot_hi_lo = Decimal(int(pot_board / len(win) * factor)) / factor
                            mod_hi_lo = pot_board - pot_hi_lo * len(win)
                            if len(win) == 1 or hl == "hi":
                                pot_hi_lo += mod_hi_lo
                            pot_split = Decimal(int(pot_hi_lo / len(win[hl]) * factor)) / factor
                            mod_split = pot_hi_lo - pot_split * len(win[hl])
                            pnames = players if len(holeplayers) == 0 else [holeplayers[w] for w in win[hl]]
                            for n in positions:
                                if position_dict[n] in pnames:
                                    pname = position_dict[n]
                                    ppot = pot_split
                                    if mod_split > 0:
                                        cent = _chip_increment(factor)
                                        ppot += cent
                                        mod_split -= cent
                                    players_pots[pname][0] += ppot
                                    pot_found[pname][0] += ppot
                                    data = {
                                        "potId": pot_id,
                                        "boardId": board_id,
                                        "hiLo": hl,
                                        "ppot": ppot,
                                        "winners": [m for m in pnames if pname != n],
                                        "mod": ppot > pot_split,
                                    }
                                    players_pots[pname][1].append(data)

            for p, (total, info) in players_pots.items():
                if hand.collectees.get(p) and info:
                    pot_found[p][1] = hand.collectees.get(p)
                    for item in info:
                        split = [
                            n
                            for n in item["winners"]
                            if len(players_pots[n][1]) == 1 and hand.collectees.get(n) is not None
                        ]
                        if len(info) == 1:
                            ppot = item["ppot"]
                            rake = ppot - hand.collectees[p]
                            collected = hand.collectees[p]
                        elif item == info[-1]:
                            ppot, collected = pot_found[p]
                            rake = ppot - collected
                        elif len(split) > 0 and not item["mod"]:
                            ppot = item["ppot"]
                            collected = min([hand.collectees[s] for s in split] + [ppot])
                            rake = ppot - collected
                        else:
                            ppot = item["ppot"]
                            totalrake = total - hand.collectees[p]
                            if self.use_round_down:
                                rake = (totalrake * (ppot / total)).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
                            else:
                                rake = (totalrake * (ppot / total)).quantize(Decimal("0.01"))
                            collected = ppot - rake
                        pot_found[p][0] -= ppot
                        pot_found[p][1] -= collected
                        insert = [
                            None,
                            item["potId"],
                            item["boardId"],
                            item["hiLo"][0],
                            hand.playerIds[p],
                            int(item["ppot"] * 100),
                            int(collected * 100),
                            int(rake * 100),
                        ]
                        self.handspots.append(insert)
                        if not hand.cashedOut:
                            self.handsplayers[p]["rake"] += int(rake * 100)
                            hand.rake += rake

    def getBoardsDict(self, hand: Any, _game_type: Any, streets: Any) -> dict:
        """Get boards dictionary for equity calculations."""
        try:
            log.debug("Getting boards dict for hand %s", hand.handid)
            boards = {}
            cumulative_board: list[Any] = []

            for street_name in streets:
                try:
                    if street_name == "PREFLOP" or street_name in hand.board:
                        cumulative_board.extend(hand.board.get(street_name, []) or [])
                        street_actions = hand.actions.get(street_name, [])
                        allin = any(
                            isinstance(action, (list, tuple)) and len(action) > 2 and action[-1] is True
                            for action in street_actions
                        )
                        boards[street_name] = {"board": [list(cumulative_board)], "allin": allin}
                        log.debug("Added board for %s: %s", street_name, boards[street_name])
                    else:
                        log.error("Street %s not found in hand.board", street_name)

                except (AttributeError, KeyError, TypeError):  # noqa: PERF203
                    log.exception("Error processing street %s", street_name)

            return boards  # noqa: TRY300

        except (AttributeError, KeyError, TypeError):
            log.exception("Error in getBoardsDict for hand %s", hand.handid)
            return {}

    def _raise_invalid_run_it_times_error(self, run_it_times: Any) -> None:
        """Helper method to raise ValueError for invalid runItTimes."""
        msg = f"Invalid runItTimes type: {type(run_it_times)}"
        raise ValueError(msg)

    def getBoardsList(self, hand: Any) -> list:
        """Get boards list for hand."""
        try:
            log.debug("Getting boards list for hand %s", hand.handid)

            if hand.gametype["base"] != "hold":
                return []

            # Check for invalid runItTimes
            if hasattr(hand, "runItTimes") and not isinstance(hand.runItTimes, int):
                self._raise_invalid_run_it_times_error(hand.runItTimes)

            return [hand.board[street] for street in hand.communityStreets if street in hand.board]

        except (AttributeError, KeyError, TypeError, ValueError):
            log.exception("Error in getBoardsList for hand %s", hand.handid)
            raise

    def getAllInEV(self, hand: Any, game_type: Any, players: Any, boards: Any, streets: Any, holecards: Any) -> None:  # noqa: C901, PLR0913, PLR0912
        """Calculate all-in equity for players.

        Adapted to handle both Hold'em and Draw games:
        - Hold'em: Uses community cards + hole cards
        - Draw: Uses only player's cards (5 cards)
        """
        try:
            log.debug("Calculating all-in EV for hand %s, game type: %s", hand.handid, game_type)

            # Get game base type
            base = hand.gametype.get("base", "")

            # For non-hold'em games (like draw), we need different handling
            if base != "hold" and game_type:
                return self.getAllInEVDraw(hand, game_type, players, streets, holecards)

            # Original Hold'em logic
            # Check if we have valid players for EV calculation
            valid_players = [
                player
                for player in players
                if player in self.handsplayers
                and (
                    self.handsplayers[player].get("sawShowdown", False)
                    or self.handsplayers[player].get("wentAllIn", False)
                )
            ]

            if len(valid_players) < MIN_PLAYERS_FOR_GAME:
                log.warning("Not enough valid players for EV calculation: %s", valid_players)
                return None

            # Initialize stove data if not exists
            if not hasattr(self, "handsstove"):
                self.handsstove = []

            # Calculate equity for each all-in situation
            for street_name, street_data in boards.items():
                if street_data.get("allin", False):
                    try:
                        if pokereval:
                            player_hands = []
                            evaluated_players = []
                            for player in valid_players:
                                if player in holecards:
                                    hole = holecards[player].get("hole", [])
                                    if hole and hole != ["0x", "0x"]:
                                        player_hands.append(hole)
                                        evaluated_players.append(player)

                            if len(player_hands) >= MIN_PLAYERS_FOR_GAME:
                                board_cards = street_data["board"][0] if street_data["board"] else []

                                result = calculate_equity(
                                    game_type,
                                    player_hands,
                                    board_cards,
                                    backend=pokereval,
                                )
                                pot = Decimal(hand.totalpot)
                                rake = Decimal(hand.rake)
                                for player, player_result in zip(evaluated_players, result.players, strict=True):
                                    committed = Decimal(hand.pot.committed.get(player, 0)) + Decimal(
                                        hand.pot.common.get(player, 0)
                                    )
                                    expected = expected_pot_share(player_result.equity, pot, rake)
                                    self.handsplayers[player]["allInEV"] = int(100 * (expected - committed))
                                    log.debug(
                                        "Player %s all-in equity=%s expected-profit=%s",
                                        player,
                                        player_result.equity,
                                        expected - committed,
                                    )

                    except (EquityUnavailableError, RuntimeError):
                        log.exception("RuntimeError in pokereval calculation")
                    except (AttributeError, KeyError, TypeError, ValueError):
                        log.exception("Error calculating equity for %s", street_name)

        except Exception:  # intentional broad catch: all-in EV is best-effort stats enrichment.
            log.exception("Error in getAllInEV for hand %s", hand.handid)

    def getAllInEVDraw(self, hand: Any, _game_type: Any, _players: Any, _streets: Any, holecards: Any) -> None:  # noqa: C901
        """Calculate all-in equity for Draw games.

        Draw games have different characteristics:
        - No community cards
        - Players have 5 cards each
        - All-in situations need to evaluate complete hands
        """
        try:
            log.debug("Calculating Draw all-in EV for hand %s", hand.handid)

            # Find the street where all-in occurred
            for pot_id, (pot, pot_players) in enumerate(hand.pot.pots):
                if pot_id == 0:
                    pot += sum(hand.pot.common.values()) + hand.pot.stp  # noqa: PLW2901

                # Get valid players who went all-in
                valid_players = []
                player_cards = []

                for player in pot_players:
                    if (
                        player in self.handsplayers
                        and (
                            self.handsplayers[player].get("sawShowdown", False)
                            or self.handsplayers[player].get("wentAllIn", False)
                        )
                        and player in holecards
                        and "cards" in holecards[player]
                        and holecards[player]["cards"]
                        and len(holecards[player]["cards"]) > 0
                    ):
                        # Get player's cards for Draw games
                        cards = holecards[player]["cards"]
                        # For draw games, use the complete hand
                        player_hand = cards[-1] if isinstance(cards, list) else cards
                        # Filter out placeholder cards
                        player_hand = [c for c in player_hand if c != "0x"]

                        if len(player_hand) >= MIN_MAXCARDS_SIZE:  # Draw games need 5 cards
                            valid_players.append(player)
                            player_cards.append(player_hand[:MIN_MAXCARDS_SIZE])  # Use first 5 cards

                if len(valid_players) >= MIN_PLAYERS_FOR_GAME and len(player_cards) >= MIN_PLAYERS_FOR_GAME:
                    try:
                        # Calculate equity for draw games
                        # Note: Draw games don't use board cards
                        iterations = 1000

                        # Use poker_eval for draw games
                        engine = pokereval
                        if engine is None:
                            return
                        evs = engine.poker_eval(
                            game="5draw",  # Default for draw games
                            iterations=iterations,
                            pockets=player_cards,
                            board=[],  # No board in draw games
                        )

                        equities = [e["ev"] for e in evs["eval"]]

                        # Adjust equities to sum to 1000
                        remainder = (1000 - sum(equities)) / Decimal(len(equities))
                        for i in range(len(equities)):
                            equities[i] += remainder

                            player = valid_players[i]
                            # Calculate committed amount
                            committed = 100 * hand.pot.committed.get(player, 0) + 100 * hand.pot.common.get(player, 0)

                            # Calculate EV
                            rake = hand.rake * (Decimal(pot) / Decimal(hand.totalpot))
                            ev = ((pot - rake) * equities[i]) / Decimal(10)

                            # Set all-in EV
                            self.handsplayers[player]["allInEV"] = int(ev - committed)
                            log.debug(
                                "Draw game - Player %s all-in EV: %s",
                                player,
                                self.handsplayers[player]["allInEV"],
                            )

                    except RuntimeError:
                        log.exception("getAllInEVDraw: error running poker_eval for hand %s", hand.handid)
                    except (AttributeError, KeyError, TypeError, ValueError):
                        log.exception("getAllInEVDraw: unexpected error for hand %s", hand.handid)

        except Exception:  # intentional broad catch: draw all-in EV is best-effort stats enrichment.
            log.exception("Error in getAllInEVDraw for hand %s", hand.handid)

    def awardPots(self, hand: Any) -> None:  # noqa: C901, PLR0912
        """Award pots to winners."""
        try:
            log.debug("Awarding pots for hand %s", hand.handid)

            engine = pokereval
            if engine is None:
                log.warning("pokereval not available for pot awarding")
                return

            # Process each pot
            for pot_amount, eligible_players in hand.pot.pots:
                try:
                    # Get hole cards for eligible players
                    holeplayers = []
                    for player in eligible_players:
                        hole_cards = hand.join_holecards(player)
                        if hole_cards and hole_cards != ["0x", "0x"]:
                            holeplayers.append((player, hole_cards))

                    if not holeplayers:
                        log.warning("No valid hole cards found for pot of %s", pot_amount)
                        continue

                    # Get board cards
                    boards = self.getBoardsList(hand)
                    if boards:
                        board = boards[0]  # Use first board

                        # Calculate winners using pokereval
                        winners = engine.winners(
                            game=hand.gametype["category"],
                            pockets=[hole for _, hole in holeplayers],
                            board=board,
                        )

                        if not winners or not winners.get("hi", []):
                            log.warning("No winners found for pot of %s", pot_amount)
                            continue

                        # Award pot to winners
                        winner_indices = winners["hi"]
                        num_winners = len(winner_indices)
                        if num_winners > 0:
                            pot_share = pot_amount / num_winners
                            for winner_idx in winner_indices:
                                if winner_idx < len(holeplayers):
                                    winner_name = holeplayers[winner_idx][0]
                                    hand.addCollectPot(winner_name, pot_share)
                                    log.debug("Awarded %s to %s", pot_share, winner_name)

                except RuntimeError:
                    log.exception("RuntimeError awarding pot")
                except (AttributeError, KeyError, TypeError, ValueError):
                    log.exception("Error awarding pot of %s", pot_amount)

        except Exception:  # intentional broad catch: pot awarding is best-effort stats enrichment.
            log.exception("Error in awardPots for hand %s", hand.handid)

    def assembleHudCache(self, hand: Any) -> None:
        """Assemble HUD cache data - required for HUD functionality."""
        # No real work to be done - HandsPlayers data already contains the correct info
