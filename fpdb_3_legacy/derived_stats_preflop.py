"""Preflop stats: VPIP, 3-bets and 4-bets, limps, squeezes, steals and blind defence."""

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

from decimal import Decimal
from typing import Any

from fpdb_3_legacy.derived_stats_base import (
    CENTS_MULTIPLIER,
    FOLD_TO_4BET_LEVEL,
    FOUR_BET_LEVEL,
    MIN_ACTION_LENGTH_FOR_ALLIN,
    MIN_STREETS_FOR_PREFLOP,
    THREE_BET_LEVEL,
    DerivedStatsBase,
    _is_all_in_or_fold,
    _to_decimal,
)
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("derived_stats")


class DerivedStatsPreflopMixin(DerivedStatsBase):
    """Calculate the preflop stats."""

    def vpip(self, hand: Any) -> None:
        """Calculate VPIP (Voluntarily Put In Pot) for all players.

        VPIP Opportunity: Player had a chance to act preflop (not all-in blind, didn't fold blinds)
        VPIP Done: Player voluntarily put money in pot (call/raise/bet/complete)
        """
        log.debug("Starting VPIP calculation for hand ID: %s", hand.handid)
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
        log.debug("vpip: Preflop actions: %s", preflop_actions)
        log.debug("vpip: actionStreets: %s", hand.actionStreets)
        log.debug("vpip: hand.actions keys: %s", list(hand.actions.keys()))
        vpip_count = 0

        # Get players who were all-in blind (should not get VPIP opportunity)
        allin_blind_players = set()
        blinds_antes_actions = hand.actions.get("BLINDSANTES", [])
        log.debug("vpip: Blinds/antes actions: %s", blinds_antes_actions)
        for act in blinds_antes_actions:
            if len(act) > 2 and act[2] == "allin":
                allin_blind_players.add(act[0])
        log.debug("vpip: All-in blind players: %s", allin_blind_players)

        # Get players who folded their blinds (no VPIP opportunity).
        #
        # Except in All-in or Fold, where folding from a blind is not giving up
        # a preflop the game does not have -- it is the one decision of the
        # hand, and the commonest way of taking it. Excluded, a player who
        # folds every blind is counted as never having been asked, and their
        # commit frequency comes out of a denominator missing precisely the
        # hands they declined.
        fold_blind_players = set()
        if not _is_all_in_or_fold(hand):
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
            if _is_all_in_or_fold(hand):
                # Written either way, because the initializer starts everyone
                # at True: leaving the negative case alone counts a player the
                # decision never reached as one who declined it, which in a
                # game whose whole record is that one decision is the
                # difference between a read and a fiction.
                player_stats["street0VPIChance"] = acted_preflop
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

            if (
                first_raise_seen
                and posn not in steal_positions
                and act not in ("folds", "bringin", "small blind", "big blind", "secondsb", "both", "button blind")
            ):
                log.debug("calcSteals: Non-steal position %s with action %s after first raise, ending loop", posn, act)
                break

        log.debug("calcSteals: Completed calcSteals for hand ID: %s", hand.handid)
