"""The HandsActions rows, and the per-player stats read straight off the action list:
special blinds, facing an all-in and PT4's action enums."""

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

from fpdb_3_legacy.action_enum_stats import derive_counters as derive_action_enum_counters
from fpdb_3_legacy.action_events import (
    attach_action_events,
)
from fpdb_3_legacy.derived_stats_base import (
    ACTION_AMOUNT_IDX,
    ACTION_CALLED_IDX,
    ACTION_CARDS_DISCARDED_IDX,
    ACTION_RAISETO_IDX,
    CENTS_MULTIPLIER,
    MIN_ACTION_LENGTH_FOR_ALLIN,
    DerivedStatsBase,
)
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("derived_stats")


class DerivedStatsActionsMixin(DerivedStatsBase):
    """Record the actions and the stats read straight off them."""

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
                    # Preserve a missing/unparseable discard count separately
                    # from an explicit zero (stand pat). -1 is outside the
                    # valid count domain and fits the existing SMALLINT column.
                    if action_type == "discards":
                        self.handsactions[k]["numDiscarded"] = -1
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

            # Second pass over the same stream: the rows above are what the
            # replayer and the old aggregates read, the events are the context
            # the analytics layers compose (issue #293).
            attach_action_events(self.handsactions, hand, self.handsplayers)

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
                    bool(action[-1]) if len(action) > MIN_ACTION_LENGTH_FOR_ALLIN and act != "discards" else False
                )
                if allin_aggr and pname != aggressor and pname not in recorded:
                    recorded.add(pname)
                    ps["flg_faced_allin"] = True
                    if act == "folds":
                        ps["flg_fold_to_allin"] = True
                if is_allin and act in ("bets", "raises", "completes"):
                    allin_aggr = True
                    aggressor = pname

    def calcActionEnums(self, hand: Any) -> None:
        """PT4 enum_*_action family: response char (F/C/R) per situation.

        Mirrors the validated Rust/Modern semantics: facing the Nth raise
        preflop, squeeze defence (cold caller between open and 3-bet),
        c-bet / donk / float facing postflop (float requires position),
        aggressive all-ins faced, and the street of the fold. Situation
        absent leaves "N".
        """
        if not getattr(self, "handsplayers", None):
            return
        ps_all = self.handsplayers

        resp_of = {"folds": "F", "calls": "C", "completes": "C",
                   "bets": "R", "raises": "R"}
        decision = set(resp_of) | {"checks"}

        snapshot = getattr(self, "raw_actions_snapshot", {})
        acts_by = {st: snapshot.get(st, [])
                   for st in ("PREFLOP", "FLOP", "TURN", "RIVER")}

        def pos_code(name: str) -> int | None:
            """Positional rank: lower means closer to the button, i.e. later.

            ``position`` is an int for seated players (0 = button, growing
            away from it) and "S"/"B" for the blinds, which act first
            postflop and therefore rank behind every numbered seat.
            """
            v = ps_all.get(name, {}).get("position")
            if isinstance(v, str):
                if v in ("S", "B"):
                    return 9 if v == "S" else 8
                return int(v) if v.isdigit() else None
            return v if isinstance(v, int) else None


        # ---- enum_folded -------------------------------------------------
        # Each player is marked on the street where THEY folded, so there is no
        # global break: several players fold on different streets.
        fold_streets = (("P", "BLINDSANTES"), ("P", "PREFLOP"), ("F", "FLOP"),
                        ("T", "TURN"), ("R", "RIVER"))
        pending = set(ps_all)
        for ch, st in fold_streets:
            if not pending:
                break
            acts_st = hand.actions.get(st, [])
            for pname in list(pending):
                if any(a[0] == pname and a[1] == "folds" for a in acts_st):
                    ps_all[pname]["enum_folded"] = ch
                    pending.discard(pname)

        # ---- preflop: facing raises levels 2/3 + squeeze defender --------
        # Facing levels are counted over PREFLOP raises only (blinds excluded;
        # legacy convention: open = first raise, 3-bet = second, etc.). Raw
        # entries are normalised defensively because other calculators may
        # reshape hand.actions before this runs.
        def _norm(entry):
            a = entry[0] if isinstance(entry, tuple) and entry and                 not isinstance(entry[0], str) else entry
            if isinstance(a, (tuple, list)) and len(a) >= 2 \
                    and isinstance(a[0], str) and isinstance(a[1], str):
                return a[0], a[1]
            return None

        preflop_raw = []
        for idx, entry in enumerate(snapshot.get("BLINDSANTES", []) + acts_by["PREFLOP"]):
            norm = _norm(entry)
            if norm is None:
                continue
            preflop_raw.append((idx, norm[0], norm[1]))

        level = 1
        last_raiser = None
        prev_raise_pos = None
        cold_calls_at_2 = 0
        for pos_i, (raw_i, pname, act) in enumerate(preflop_raw):
            ps = ps_all.get(pname)
            if ps is not None and level >= 2 and pname != last_raiser:
                # Keep a player's FIRST answer to the standing raise: anything
                # they did between that raise and now has already answered it.
                # Preflop this is close to unreachable -- one decision per raise
                # level -- but it pins the enum to the first reaction when a
                # parser emits an extra action for the same level.
                already = any(
                    other == pname and a2 in decision
                    for j, (_raw_j, other, a2) in enumerate(preflop_raw)
                    if prev_raise_pos is not None and prev_raise_pos < j < pos_i
                )
                if not already:
                    resp = resp_of.get(act)
                    if resp is not None and resp in ("F", "C", "R"):
                        if level == 3:
                            ps["enum_p_3bet_action"] = resp
                            # Squeeze defence: responder facing the 3-bet
                            # when >=1 cold call was made between open and 3-bet.
                            # F/C/R responses all qualify (PT4 convention).
                            if cold_calls_at_2 >= 1:
                                ps["enum_p_squeeze_action"] = resp
                        elif level == 4:
                            ps["enum_p_4bet_action"] = resp
            if act in ("raises", "bets", "completes"):
                if act == "raises":
                    if level == 2:
                        cold_calls_at_2 = sum(
                            1 for _pi, _n2, a2 in preflop_raw
                            if prev_raise_pos is not None
                            and prev_raise_pos < _pi < pos_i and a2 == "calls")
                    prev_raise_pos = pos_i
                    level += 1
                last_raiser = pname

        preflop_aggr = None
        for _pi, _n, a2 in reversed(preflop_raw):
            if a2 == "raises":
                preflop_aggr = _n
                break

        # ---- helpers ------------------------------------------------------
        def first_agg(acts):
            for i, a in enumerate(acts):
                if a[1] in ("bets", "raises"):
                    return i, a
            return None, None

        def raises_only(acts):
            return [(i, a) for i, a in enumerate(acts) if a[1] == "raises"]

        def first_decision(acts, pname, after_i=None):
            for i, a in enumerate(acts):
                if a[0] == pname and a[1] in decision \
                        and (after_i is None or i > after_i):
                    return i, a
            return None, None

        # ---- postflop aggressor chain -------------------------------------
        # The street aggressor is the last player to RAISE on that street.
        # If no one raised, the prior-street aggressor who c-bet remains the
        # aggressor for chain purposes. If a non-prior-aggressor donks the
        # street, the prior aggressor's chain ownership is preserved
        # (donk defence / re-raise is handled by the 3-bet/4-bet enum and
        # the donk enum).
        flop_first_i, flop_first_a = first_agg(acts_by["FLOP"])
        flop_lrs = raises_only(acts_by["FLOP"])
        if flop_lrs:
            flop_aggr = flop_lrs[-1][1][0]
        elif preflop_aggr is not None and flop_first_a is not None \
                and flop_first_a[0] == preflop_aggr:
            flop_aggr = preflop_aggr
        else:
            flop_aggr = None
        turn_first_i, turn_first_a = first_agg(acts_by["TURN"])
        turn_lrs = raises_only(acts_by["TURN"])
        if turn_lrs:
            turn_aggr = turn_lrs[-1][1][0]
        elif turn_first_a is not None and flop_aggr is not None \
                and turn_first_a[0] == flop_aggr:
            turn_aggr = flop_aggr
        else:
            turn_aggr = None

        # ---- cbet facing ---------------------------------------------------
        def face_cbet(acts, aggr, key):
            if not aggr:
                return
            fi, fa = first_agg(acts)
            if fi is None or fa[0] != aggr:
                return
            for pname, ps in ps_all.items():
                if pname == aggr:
                    continue
                di, da = first_decision(acts, pname, fi)
                if da is not None:
                    ps[key] = resp_of.get(da[1], "N")

        face_cbet(acts_by["FLOP"], preflop_aggr, "enum_f_cbet_action")
        face_cbet(acts_by["TURN"], flop_aggr, "enum_t_cbet_action")
        face_cbet(acts_by["RIVER"], turn_aggr, "enum_r_cbet_action")

        # ---- donk facing ---------------------------------------------------
        def face_donk(acts, prev_aggr, key):
            if not prev_aggr:
                return
            fi, fa = first_agg(acts)
            if fi is None or fa[0] == prev_aggr:
                return
            di, da = first_decision(acts, prev_aggr, fi)
            if da is not None:
                ps_all[prev_aggr][key] = resp_of.get(da[1], "N")

        face_donk(acts_by["FLOP"], preflop_aggr, "enum_f_donk_action")
        face_donk(acts_by["TURN"], flop_aggr, "enum_t_donk_action")
        face_donk(acts_by["RIVER"], turn_aggr, "enum_r_donk_action")

        # ---- 3bet/4bet facing postflop --------------------------------------
        def record_facing_post(acts, key3, key4):
            rs = raises_only(acts)
            for level, key in ((2, key3), (3, key4)):
                if len(rs) < level:
                    continue
                ti, ta = rs[level - 1]
                pi, _pa = rs[level - 2]
                for pname, ps in ps_all.items():
                    if pname == ta[0]:
                        continue
                    acted_between = any(x[0] == pname and x[1] in decision
                                        for x in acts[pi + 1:ti])
                    if acted_between:
                        continue
                    di, da = first_decision(acts, pname, ti)
                    if da is not None:
                        ps[key] = resp_of.get(da[1], "N")

        record_facing_post(acts_by["FLOP"], "enum_f_3bet_action", "enum_f_4bet_action")
        record_facing_post(acts_by["TURN"], "enum_t_3bet_action", "enum_t_4bet_action")
        record_facing_post(acts_by["RIVER"], "enum_r_3bet_action", "enum_r_4bet_action")

        # ---- float (IP only) -----------------------------------------------
        # PT4 float semantics (validated ~99.4% in Rust/Modern vs PT4 live):
        # the prior-street aggressor fires a c-bet, the IP caller calls, then
        # the prior aggressor bets the next street — the enum records the
        # CALLER's response to that second barrel (F/C/R). "Delayed bet"
        # (caller donks the next street into a checking aggressor) is covered
        # by enum_*_donk_action, not here.
        def called_cbet_ip(acts, aggr, pname):
            fi, fa = first_agg(acts)
            if fi is None or fa[0] != aggr:
                return False
            pa, pn_ = pos_code(pname), pos_code(aggr)
            if pa is None or pn_ is None or not (pa < pn_):
                return False
            return any(a[0] == pname and a[1] == "calls" for a in acts[fi + 1:])

        for prev_acts, prev_aggr, next_acts, key in (
            ("FLOP", preflop_aggr, "TURN", "enum_t_float_action"),
            ("TURN", flop_aggr, "RIVER", "enum_r_float_action"),
        ):
            if not prev_aggr:
                continue
            p_acts = hand.actions.get(prev_acts, [])
            n_acts = hand.actions.get(next_acts, [])
            fi, fa = first_agg(p_acts)
            if fi is None or fa[0] != prev_aggr:
                continue
            for pname, ps in ps_all.items():
                if pname == prev_aggr:
                    continue
                if not called_cbet_ip(p_acts, prev_aggr, pname):
                    continue
                bi, ba = first_agg(n_acts)
                if ba is None or ba[0] != prev_aggr:
                    continue
                di, da = first_decision(n_acts, pname, bi)
                if da is not None:
                    ps[key] = resp_of.get(da[1], "N")

        # ---- faced all-in ----------------------------------------------------
        recorded_ai = set()
        faced_any = False
        for sc_key, st in (("P", "PREFLOP"), ("F", "FLOP"),
                           ("T", "TURN"), ("R", "RIVER")):
            if faced_any:
                break
            acts_st = snapshot.get(st, [])
            spots = []
            for i, a in enumerate(acts_st):
                is_ai = bool(a[-1]) if len(a) > MIN_ACTION_LENGTH_FOR_ALLIN \
                    and a[1] != "discards" else False
                if is_ai and a[1] in ("bets", "raises", "completes"):
                    spots.append((i, a))
            for ai_i, ai_a in spots:
                aggressor = ai_a[0]
                for pname, ps in ps_all.items():
                    if pname == aggressor or pname in recorded_ai:
                        continue
                    di, da = first_decision(acts_st, pname, ai_i)
                    if da is None:
                        continue
                    r = resp_of.get(da[1], "N")
                    street_ch = sc_key.lower() if r == "F" else sc_key
                    ps["enum_face_allin"] = street_ch
                    ps["enum_face_allin_action"] = r
                    recorded_ai.add(pname)
                    faced_any = True

        # The HUD sums HudCache and cannot sum a char, so turn each response
        # into faced/called/raised counters while the enums are in hand.
        for ps in ps_all.values():
            derive_action_enum_counters(ps)

    @staticmethod
    def _pt4_ring_code(hand: Any, seat: Any):
        """PT4 ring index for a seat (BTN=0 ... SB=9); None when unknown."""
        if seat is None:
            return None
        try:
            seats = sorted({p[0] for p in hand.players})
        except Exception:
            return None
        if seat not in seats:
            return None
        btn = getattr(hand, "buttonpos", None)
        if btn not in seats:
            btn = seats[0]
        start = seats.index(btn)
        ordered = seats[start:] + seats[:start]
        return ordered.index(seat)
