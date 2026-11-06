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
from fpdb_3_legacy.equity import EquityUnavailableError, calculate_equity, expected_pot_share, load_poker_eval
from fpdb_3_legacy.loggingFpdb import get_logger

pokereval = load_poker_eval()

log = get_logger("derived_stats")


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
                log.debug("Not enough valid players for EV calculation: %s", valid_players)
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
                                    # Skip fully-unknown hands regardless of card
                                    # count: Omaha's unrevealed hand is
                                    # ["0x","0x","0x","0x"], which the old
                                    # two-card check let through, feeding
                                    # duplicate "0x" cards to the equity engine.
                                    if hole and not all(str(c) in ("0x", "0", "") for c in hole):
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
