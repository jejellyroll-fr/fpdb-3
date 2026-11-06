"""What each player faced and made in chips: raise and bet facing, bet sizes and stack-to-pot ratios."""

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

from fpdb_3_legacy.action_events import (
    action_chips,
    effective_stack_cents,
)
from fpdb_3_legacy.derived_stats_base import (
    CENTS_MULTIPLIER,
    MIN_ACTION_LENGTH_FOR_ALLIN,
    DerivedStatsBase,
    _pot_stp,
    _to_decimal,
)


class DerivedStatsFacingMixin(DerivedStatsBase):
    """Price what each player faced and made, street by street."""

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
                if (
                    len(a) > MIN_ACTION_LENGTH_FOR_ALLIN
                    and a[-1] is True
                    and act in ("calls", "raises", "bets", "completes")
                    and chips(a) < to_call
                ):
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
        street_key = {
            "BLINDSANTES": ("amt_blind", "amt_bet_p"),
            "PREFLOP": ("amt_bet_p",),
            "FLOP": ("amt_bet_f",),
            "TURN": ("amt_bet_t",),
            "RIVER": ("amt_bet_r",),
        }
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
                    if (
                        len(a) > MIN_ACTION_LENGTH_FOR_ALLIN
                        and a[-1] is True
                        and act in ("calls", "raises", "bets", "completes")
                        and a_chips < to_call
                    ):
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
                running += action_chips(a)

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
                        eff = effective_stack_cents(rem, p, active)
                        if eff <= 0:
                            continue
                        ps = self.handsplayers[p]
                        ps[cnt_key] = 1
                        ps[val_key] = int(eff * 100 // pot)
            for a in acts:
                p = a[0]
                if p in committed:
                    committed[p] += action_chips(a)

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
