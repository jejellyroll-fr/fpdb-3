"""Pots, boards and all-in EV: the HandsStove and HandsPots rows and the pots awarded."""

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

from decimal import ROUND_DOWN, Decimal
from itertools import chain
from typing import Any

from fpdb_3_legacy import Card
from fpdb_3_legacy.derived_stats_base import (
    ANTE_ALL_IN_POSITION,
    MIN_MAXCARDS_SIZE,
    MIN_PLAYERS_FOR_GAME,
    MIN_POSTFLOP_BOARD_SIZE,
    MIN_RUN_IT_TIMES,
    DerivedStatsBase,
    _chip_increment,
)
from fpdb_3_legacy.equity import (
    DEFAULT_EQUITY_ITERATIONS,
    FUSION_ALL_HOLE_CARDS_BOARD,
    EquityResult,
    EquityUnavailableError,
    calculate_equity,
    fusion_pockets,
    load_poker_eval,
)
from fpdb_3_legacy.loggingFpdb import get_logger

pokereval = load_poker_eval()

# A sampled all-in EV is seeded so the same hand stores the same EV on every
# import, whatever was sampled before it in the process (poker-eval #301).
ALL_IN_EV_SEED = 818

log = get_logger("derived_stats")

# An action tuple is (player, action, amount, ..., all-in flag).
MIN_ALL_IN_ACTION_SIZE = 3


def _is_all_in(action: Any) -> bool:
    """Whether this action put its player all-in."""
    return isinstance(action, (list, tuple)) and len(action) >= MIN_ALL_IN_ACTION_SIZE and action[-1] is True


def _fusion_iterations(board: list) -> int | None:
    """Fusion's all-in equity deals the hole cards still to come (#818).

    Exhaustively that is 25 s for a three-way flop and out of reach preflop,
    so before the turn it is sampled.
    """
    return DEFAULT_EQUITY_ITERATIONS if len(board) < FUSION_ALL_HOLE_CARDS_BOARD else None


class DerivedStatsAllInMixin(DerivedStatsBase):
    """Evaluate boards, all-ins and pots."""

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
            self.getAllInEV(hand, evalgame, holeplayers, boards, holecards)
        elif base == "draw" and evalgame:
            self.getAllInEVDraw(hand, evalgame, holeplayers, boards, last, hrange)

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
            # The rake is zeroed below and rebuilt pot by pot. A parser that
            # takes the pot and rake from the summary (GGPoker) leaves no pots
            # to rebuild from, so every hand run twice lost its rake.
            and hand.pot.pots
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
                # Stud and draw deal no community cards, so getBoardsList returns
                # nothing and this loop used to run zero times: the pots were
                # never built and no HandsPots row was written -- yet the rake had
                # just been zeroed a few lines above, so it stayed at zero and the
                # hand no longer balanced. A boardless game still has exactly one
                # board; it is simply empty.
                boards, board_id = self.getBoardsList(hand) or [[]], 0
                for b in boards:
                    board_id += hand.runItTimes >= MIN_RUN_IT_TIMES
                    pot_board = Decimal(int(pot / len(boards) * factor)) / factor
                    mod_board = pot - pot_board * len(boards)
                    if board_id == 1:
                        pot_board += mod_board
                    holeplayers, holecards = [], []
                    for p in players:
                        # A pot lists everyone who paid into it, including players who
                        # folded later. They cannot win it, so evaluating their cards
                        # awards the pot to a folder whenever his hand happens to be
                        # the best -- which happens as soon as those cards are known,
                        # the hero's always being. The real winner is then credited
                        # with less than he collected, and his rake comes out negative.
                        if not self.handsplayers[p]["sawShowdown"]:
                            continue
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
                        allin = any(_is_all_in(action) for action in street_actions)
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
        """Return the complete board(s) dealt in this hand, one entry per run.

        An entry is a whole board, not a street: callers evaluate each one against
        the players' holecards and split the pot across the runs. Returning the
        streets separately handed the evaluator a one-card "board" for the turn and
        the river ("wrong # of board cards"), and divided the pot by the number of
        streets instead of the number of runs.
        """
        try:
            log.debug("Getting boards list for hand %s", hand.handid)

            if hand.gametype["base"] != "hold":
                return []

            # Check for invalid runItTimes
            if hasattr(hand, "runItTimes") and not isinstance(hand.runItTimes, int):
                self._raise_invalid_run_it_times_error(hand.runItTimes)

            if hand.runItTimes >= MIN_RUN_IT_TIMES:
                # Each run is dealt onto its own streets: FLOP1/TURN1/RIVER1, FLOP2...
                # but only the streets actually dealt twice are numbered. Older FTP
                # archives agree to run it twice *after* the flop, so the flop is
                # shared (FLOP + TURN1/RIVER1 + TURN2/RIVER2) and FLOP1/FLOP2 stay
                # empty; without the fallback to the shared street each run was just
                # [turn, river] and the evaluator rejected the two-card board
                # ("pyenum returned error code 1005"), losing the pot split.
                return [
                    [
                        card
                        for street in hand.communityStreets
                        for card in (hand.board.get(f"{street}{run}") or hand.board.get(street) or [])
                    ]
                    for run in range(1, hand.runItTimes + 1)
                ]

            return [[card for street in hand.communityStreets for card in hand.board.get(street, [])]]

        except (AttributeError, KeyError, TypeError, ValueError):
            log.exception("Error in getBoardsList for hand %s", hand.handid)
            raise

    def getAllInEV(  # pylint: disable=invalid-name  # called by this name, as getBoardsDict
        self, hand: Any, game_type: Any, players: Any, boards: Any, holecards: Any
    ) -> None:
        """Store the all-in EV of a flop game's players (draw games: getAllInEVDraw).

        The pot is split into the main pot and side pots (#836): a short stack
        all-in can only win what each opponent matched of its stake. Each pot is
        evaluated among the players who can win it, with the board of the street
        its money went in: the street its smallest stake went all-in, so a short
        stack all-in on the flop keeps its flop equity for the main pot while the
        side pot is decided by a later all-in. A pot whose smallest stake never
        went all-in goes with the last all-in street.
        """
        log.debug("Calculating all-in EV for hand %s, game type: %s", hand.handid, game_type)
        if not pokereval:
            return
        try:
            expected = self._layered_all_in_ev(hand, game_type, boards, self._all_in_pockets(players, holecards))
        except (EquityUnavailableError, RuntimeError):
            log.exception("RuntimeError in pokereval calculation for hand %s", hand.handid)
            return
        # All-in EV is best-effort stats enrichment: it never stops a hand's import.
        except Exception:  # pylint: disable=broad-exception-caught
            log.exception("Error in getAllInEV for hand %s", hand.handid)
            return
        paid = self._paid_into_pot(hand)
        for player, share in expected.items():
            profit = share - paid.get(player, Decimal(0))
            self.handsplayers[player]["allInEV"] = int(100 * profit)
            self.handsplayers[player]["allInEVCalculated"] = True
            log.debug("Player %s all-in expected-profit=%s", player, profit)

    def _layered_all_in_ev(
        self, hand: Any, game_type: str, boards: dict, pockets: dict[str, list]
    ) -> dict[str, Decimal]:
        """What each player expects back from the main pot and the side pots they can win."""
        allin_streets = [street for street, data in boards.items() if data.get("allin", False)]
        if not allin_streets or len(pockets) < MIN_PLAYERS_FOR_GAME:
            return {}
        bets = self._bets(hand)
        allin_street_of = self._all_in_street_of(hand, list(pockets), allin_streets)
        fusion = hand.gametype.get("category") == "fusion"
        expected = dict.fromkeys(pockets, Decimal(0))
        for net, eligible in self._net_pot_layers(hand, list(pockets), bets):
            if len(eligible) == 1:
                expected[eligible[0]] += net
                continue
            street = self._layer_street(eligible, bets, allin_street_of, allin_streets)
            result = self._all_in_equity(game_type, eligible, pockets, boards[street], fusion=fusion)
            for player, player_result in zip(eligible, result.players, strict=True):
                expected[player] += player_result.equity * net
        return expected

    def _all_in_pockets(self, players: Any, holecards: Any) -> dict[str, list]:
        """The hole cards of each player at showdown or all-in whose hand is known."""
        pockets: dict[str, list] = {}
        for player in players:
            stats = self.handsplayers.get(player) or {}
            if not (stats.get("sawShowdown", False) or stats.get("wentAllIn", False)):
                continue
            hole = holecards.get(player, {}).get("hole", [])
            # Skip fully-unknown hands regardless of card count: Omaha's
            # unrevealed hand is ["0x","0x","0x","0x"], which a two-card check
            # let through, feeding duplicate "0x" cards to the equity engine.
            if hole and not all(str(c) in ("0x", "0", "") for c in hole):
                pockets[player] = hole
        return pockets

    @staticmethod
    def _all_in_street_of(hand: Any, players: list[str], allin_streets: list[str]) -> dict[str, str]:
        """The street on which each of these players went all-in, if they did."""
        actions = getattr(hand, "actions", None) or {}
        street_of: dict[str, str] = {}
        for street in allin_streets:
            for action in actions.get(street) or []:
                if _is_all_in(action) and action[0] in players:
                    street_of.setdefault(action[0], street)
        return street_of

    @staticmethod
    def _layer_street(
        eligible: list[str], bets: dict[str, Decimal], allin_street_of: dict[str, str], allin_streets: list[str]
    ) -> str:
        """The street a pot's money went in: the one its smallest stake went all-in, else the last all-in."""
        level = min(bets.get(player, Decimal(0)) for player in eligible)
        capped = [
            allin_street_of[player]
            for player in eligible
            if player in allin_street_of and bets.get(player, Decimal(0)) == level
        ]
        return max(capped, key=allin_streets.index) if capped else allin_streets[-1]

    @staticmethod
    def _all_in_equity(
        game_type: str, eligible: list[str], pockets: dict[str, list], street_data: dict, *, fusion: bool
    ) -> EquityResult:
        """The equity of the eligible hands with the board of the street they went all-in.

        The known cards of the players who cannot win this pot are dead: they
        cannot come on the board.
        """
        board_cards = street_data["board"][0] if street_data["board"] else []
        hands = [pockets[player] for player in eligible]
        dead = [pocket for player, pocket in pockets.items() if player not in eligible]
        iterations = None
        if fusion:
            game_type, iterations = "fusion", _fusion_iterations(board_cards)
            hands, dead = fusion_pockets(hands, board_cards), fusion_pockets(dead, board_cards)
        return calculate_equity(
            game_type,
            hands,
            board_cards,
            dead=list(chain.from_iterable(dead)),
            iterations=iterations,
            backend=pokereval,
            seed=None if iterations is None else ALL_IN_EV_SEED,
        )

    def getAllInEVDraw(  # noqa: PLR0913  # pylint: disable=invalid-name  # sibling of getAllInEV
        self,
        hand: Any,
        evalgame: str,
        players: list[str],
        boards: dict,
        last: str,
        hrange: list[tuple[int, int]],
    ) -> None:
        """Store the all-in EV of a draw hand whose money went in after the last draw (#831).

        Every hand is complete then, so the showdown result is the equity, as on
        a hold'em river. An all-in before the last draw depends on the draws
        still to come, which poker-eval does not play: no EV is stored, rather
        than one computed from cards nobody held at the time.
        """
        allin_streets = {street for street, data in boards.items() if data.get("allin")}
        if allin_streets != {last}:
            return
        pocket_of = self._showdown_draw_hands(hand, players, hrange[-1])
        if pocket_of is None or len(pocket_of) < MIN_PLAYERS_FOR_GAME:
            return
        evaluated = list(pocket_of)
        paid = self._paid_into_pot(hand)
        expected = dict.fromkeys(evaluated, Decimal(0))
        try:
            for net, eligible in self._net_pot_layers(hand, evaluated, self._bets(hand)):
                if len(eligible) == 1:
                    expected[eligible[0]] += net
                    continue
                result = calculate_equity(evalgame, [pocket_of[player] for player in eligible], backend=pokereval)
                for player, player_result in zip(eligible, result.players, strict=True):
                    expected[player] += player_result.equity * net
        except (EquityUnavailableError, RuntimeError, ValueError):
            log.exception("getAllInEVDraw: no equity for hand %s", hand.handid)
            return
        for player in evaluated:
            self.handsplayers[player]["allInEV"] = int(100 * (expected[player] - paid.get(player, Decimal(0))))
            self.handsplayers[player]["allInEVCalculated"] = True

    def _showdown_draw_hands(
        self, hand: Any, players: list[str], final_range: tuple[int, int]
    ) -> dict[str, list[str]] | None:
        """The final hand of each player at showdown, or None when one of them is unknown.

        One unknown hand at showdown leaves the pot's split unknown.
        """
        start, end = final_range
        hands: dict[str, list[str]] = {}
        for player in players:
            if not self.handsplayers[player].get("sawShowdown"):
                continue
            cards = [str(card) for card in hand.join_holecards(player, asList=True)[start:end]]
            if len(cards) != end - start or not all(Card.encodeCard(card) for card in cards):
                return None
            hands[player] = cards
        return hands

    @staticmethod
    def _paid_into_pot(hand: Any) -> dict[str, Decimal]:
        """What each player put in the pot, blinds and antes included."""
        players = set(hand.pot.committed) | set(hand.pot.common)
        return {
            player: Decimal(hand.pot.committed.get(player, 0)) + Decimal(hand.pot.common.get(player, 0))
            for player in players
        }

    @staticmethod
    def _bets(hand: Any) -> dict[str, Decimal]:
        """What each player bet, blinds included; antes and dead blinds are common money."""
        return {player: Decimal(amount) for player, amount in hand.pot.committed.items()}

    @staticmethod
    def _common_money(hand: Any) -> Decimal:
        """The money every contender can win: antes, dead blinds and the room's (splash)."""
        common = sum((Decimal(amount) for amount in hand.pot.common.values()), Decimal(0))
        return common + Decimal(getattr(hand.pot, "stp", 0) or 0)

    @classmethod
    def _pot_layers(cls, hand: Any, contenders: list[str], bets: dict[str, Decimal]) -> list[tuple[Decimal, list[str]]]:
        """Split the pot into the main pot and side pots, each with the contenders who can win it.

        A short stack all-in can only win what each opponent matched of its
        stake. The parsers that read the pots from the summary leave
        hand.pot.pots empty, so the layers come from what each player bet:
        one per distinct contender stake. The common money (antes, dead
        blinds) and the room's money (splash) go to the main pot, as
        assembleHandsPots and aof_equity.build_pot_layers put them. Bets no
        contender reaches (rounding) stay in the top layer.
        """
        layers: list[tuple[Decimal, list[str]]] = []
        previous = Decimal(0)
        for level in sorted({bets.get(player, Decimal(0)) for player in contenders}):
            amount = sum((min(stake, level) - min(stake, previous) for stake in bets.values()), Decimal(0))
            layers.append((amount, [player for player in contenders if bets.get(player, Decimal(0)) >= level]))
            previous = level
        main_amount, main_eligible = layers[0]
        layers[0] = (main_amount + cls._common_money(hand), main_eligible)
        top_amount, top_eligible = layers[-1]
        layers[-1] = (top_amount + Decimal(hand.totalpot) - sum(amount for amount, _ in layers), top_eligible)
        return layers

    @classmethod
    def _net_pot_layers(
        cls, hand: Any, contenders: list[str], bets: dict[str, Decimal]
    ) -> list[tuple[Decimal, list[str]]]:
        """The pot layers net of the rake, which comes off each in proportion to its size."""
        pot, rake = Decimal(hand.totalpot), Decimal(hand.rake)
        return [
            (amount - rake * amount / pot if pot else amount, eligible)
            for amount, eligible in cls._pot_layers(hand, contenders, bets)
        ]

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
