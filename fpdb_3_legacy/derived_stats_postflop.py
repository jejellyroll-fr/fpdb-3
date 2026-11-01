"""Postflop stats: continuation bets, probes, check-raises, postflop 3-bets and 4-bets,
and the flop, turn and river stat families."""

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

from typing import Any

from fpdb_3_legacy.derived_stats_base import (
    MIN_ACTIONS_FOR_CHECK_CALL_RAISE,
    DerivedStatsBase,
)
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("derived_stats")


class DerivedStatsPostflopMixin(DerivedStatsBase):
    """Calculate the postflop stats."""

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
                if (
                    ps is not None
                    and raise_seen
                    and act
                    not in (
                        "small blind",
                        "big blind",
                        "secondsb",
                        "both",
                        "button blind",
                        "ante",
                        "bringin",
                    )
                ):
                    ps[f"street{idx}FaceRaise"] = True
                if act in ("raises", "completes"):
                    raise_seen = True

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
