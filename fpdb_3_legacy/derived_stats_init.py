"""The per-player stat row every hand starts from (`_INIT_STATS`)."""

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


def _initMoneyAndResults(init: dict[str, Any]) -> None:
    """Stacks, money committed, winnings and rake attribution."""
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


def _initHandOutcome(init: dict[str, Any]) -> None:
    """Showdown participation, holdings and seating context."""
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


def _initPreflop(init: dict[str, Any]) -> None:
    """Preflop actions, raise levels, limps and the sizing faced."""
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


def _initPostflopRaiseLevels(init: dict[str, Any]) -> None:
    """Postflop per-street re-raise stats. street1 = flop, street2 = turn,
    street3 = river.
    """
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


def _initStealAndBlindDefence(init: dict[str, Any]) -> None:
    """Steal attempts and blind defence."""
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


def _initStreetsSeenAndAllIn(init: dict[str, Any]) -> None:
    """Streets reached, aggression faced preflop and all-in exposure."""
    init["tourneyTypeId"] = None
    init["street1Seen"] = False
    init["street2Seen"] = False
    init["street3Seen"] = False
    init["street4Seen"] = False
    init["otherRaisedStreet0"] = False
    init["foldToOtherRaisedStreet0"] = False
    init["wentAllIn"] = False
    # Money the room drops on the table and pays beside the pot, in cents. It
    # is neither a bet nor a share of the pot, so it cannot live in either
    # column without making the rake or the winnings wrong.
    init["splashWinnings"] = 0
    # Faced an all-in (an opponent's all-in bet/raise put the player to a
    # decision) and whether they folded to it (PT4 enum_face_allin, modelled
    # the fpdb way as a chance/done boolean pair).
    init["flg_faced_allin"] = False
    init["flg_fold_to_allin"] = False


def _initPerStreetCounters(init: dict[str, Any]) -> None:
    """Action counters, continuation bets and check-raises, per street."""
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


def _initPostflopStreetStats(init: dict[str, Any]) -> None:
    """Per-street donk/float/position flags and bet sizing, flop to river."""
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


def _initRaiseSizing(init: dict[str, Any]) -> None:
    """Sizing of raises made and faced, per street and level."""
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


# PT4 enum_*_action columns, in the order HandsPlayers stores them. Both
# database_schema.HANDS_PLAYERS_KEYS and the store_hands_players insert repeat
# this order; test_action_enum_persistence guards the three against drift.
ACTION_ENUM_KEYS = (
    "enum_p_3bet_action", "enum_p_4bet_action", "enum_p_squeeze_action",
    "enum_f_3bet_action", "enum_f_4bet_action", "enum_f_cbet_action",
    "enum_f_donk_action", "enum_t_3bet_action", "enum_t_4bet_action",
    "enum_t_cbet_action", "enum_t_float_action", "enum_t_donk_action",
    "enum_r_3bet_action", "enum_r_4bet_action", "enum_r_cbet_action",
    "enum_r_float_action", "enum_r_donk_action",
    "enum_face_allin", "enum_face_allin_action", "enum_folded",
)


def _initActionEnums(init: dict[str, Any]) -> None:
    """PT4 action enums: response char F/C/R, or N when situation absent.

    enum_folded carries the street of the fold (P/F/T/R/N); enum_face_allin
    uses a lowercase street char when folded, uppercase otherwise.
    """
    for key in ACTION_ENUM_KEYS:
        init[key] = "N"


def _buildStatsInitializer() -> dict:
    """Build the per-player stat row every hand starts from."""
    init: dict[str, Any] = {}
    _initMoneyAndResults(init)
    _initHandOutcome(init)
    _initPreflop(init)
    _initPostflopRaiseLevels(init)
    _initStealAndBlindDefence(init)
    _initStreetsSeenAndAllIn(init)
    _initPerStreetCounters(init)
    _initPostflopStreetStats(init)
    _initRaiseSizing(init)
    _initActionEnums(init)
    return init


_INIT_STATS = _buildStatsInitializer()
