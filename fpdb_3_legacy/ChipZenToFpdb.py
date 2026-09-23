#!/usr/bin/env python
"""ChipZen normalized JSONL hand-history converter.

The file format consumed here is deliberately an fpdb-owned normalization of
ChipZen's public v1 transport + NLHE protocol, not a scrape of the website. A
single line is one completed hand and carries the match/round metadata, every
``phase_change`` needed to reconstruct the board, optional ``turn_results`` for
amount validation, and the canonical ``round_result.action_history``.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict, deque
from decimal import Decimal
from typing import Any, ClassVar

from fpdb_3_legacy.HandHistoryConverter import FpdbParseError, HandHistoryConverter
from fpdb_3_legacy.http_capture_hand_builder import CaptureNotImportableError, build_fpdb_hand
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("chipzen_parser")


class ChipZen(HandHistoryConverter):
    """Import ``fpdb-chipzen-hand/v1`` records as normal fpdb Hold'em hands."""

    sitename = "ChipZen"
    siteId = 141
    filetype = "text"
    codepage = ("utf8",)
    copyGameHeader = False
    summaryInFile = False

    re_identify = re.compile(r'"schema"\s*:\s*"fpdb-chipzen-hand/v1"')
    # JSONL: every physical line is one complete normalized hand. The splitter
    # consumes only the newline so the JSON object itself stays intact.
    re_split_hands = re.compile(r"\n+")
    re_SplitHands = re_split_hands

    _PHASE_TO_STREET: ClassVar[dict[str, str]] = {
        "preflop": "PREFLOP",
        "flop": "FLOP",
        "turn": "TURN",
        "river": "RIVER",
    }
    _EXPECTED_BOARD_LEN: ClassVar[dict[str, int]] = {"flop": 3, "turn": 4, "river": 5}
    _SYNTHETIC_ACTIONS: ClassVar[frozenset[str]] = frozenset(
        {"post_small_blind", "post_big_blind", "post_ante"}
    )

    @staticmethod
    def stable_hand_id(match_id: str, round_id: str | None, hand_number: int | str | None) -> int:
        """Return a deterministic positive signed-BIGINT id for one ChipZen hand."""
        discriminator = round_id or str(hand_number or "")
        if not match_id or not discriminator:
            raise FpdbParseError("ChipZen hand is missing match_id/round_id identity")
        raw = f"{match_id}:{discriminator}".encode("utf-8")
        digest = hashlib.blake2b(raw, digest_size=8, person=b"fpdb-cz1").digest()
        return int.from_bytes(digest, "big") & 0x7FFF_FFFF_FFFF_FFFF

    @staticmethod
    def _record(text: str) -> dict[str, Any]:
        try:
            record = json.loads(text)
        except json.JSONDecodeError as exc:
            raise FpdbParseError(f"Invalid ChipZen JSON: {exc}") from exc
        if not isinstance(record, dict) or record.get("schema") != "fpdb-chipzen-hand/v1":
            raise FpdbParseError("Unsupported ChipZen normalized hand schema")
        return record

    @staticmethod
    def _seat_names(record: dict[str, Any]) -> dict[int, str]:
        seats = record.get("match", {}).get("seats") or []
        names: dict[int, str] = {}
        for entry in seats:
            if not isinstance(entry, dict) or not isinstance(entry.get("seat"), int):
                continue
            seat = int(entry["seat"])
            name = entry.get("display_name") or entry.get("name") or f"ChipZen-seat-{seat}"
            names[seat] = str(name)
        return names

    @classmethod
    def _community(cls, record: dict[str, Any]) -> dict[str, list[str]]:
        phase_changes = record.get("phase_changes") or []
        community: dict[str, list[str]] = {}
        seen: set[str] = set()
        all_cards: list[str] = []

        for change in phase_changes:
            state = change.get("state", change) if isinstance(change, dict) else {}
            phase = str(state.get("phase") or "").lower()
            if phase not in cls._EXPECTED_BOARD_LEN:
                continue
            board = state.get("board")
            if not isinstance(board, list) or len(board) != cls._EXPECTED_BOARD_LEN[phase]:
                raise FpdbParseError(
                    f"ChipZen invalid {phase} board: expected {cls._EXPECTED_BOARD_LEN[phase]} cards, got {board!r}"
                )
            board = [str(card) for card in board]
            if len(set(board)) != len(board):
                raise FpdbParseError(f"ChipZen {phase} board contains duplicate cards: {board!r}")

            if phase == "flop":
                community["FLOP"] = board
            elif phase == "turn":
                if "FLOP" not in community or board[:3] != community["FLOP"]:
                    raise FpdbParseError("ChipZen turn board does not extend the recorded flop")
                community["TURN"] = [board[-1]]
            else:
                expected_prefix = community.get("FLOP", []) + community.get("TURN", [])
                if len(expected_prefix) != 4 or board[:4] != expected_prefix:
                    raise FpdbParseError("ChipZen river board does not extend the recorded turn")
                community["RIVER"] = [board[-1]]

            all_cards = board
            seen.add(phase)

        if len(all_cards) != len(set(all_cards)):
            raise FpdbParseError(f"ChipZen board contains duplicate cards: {all_cards!r}")

        # If the action history says a street was reached, its phase_change is
        # mandatory because round_result deliberately does not carry the board.
        actions = record.get("round_result", {}).get("result", {}).get("action_history") or []
        reached = {str(a.get("phase") or "").lower() for a in actions if isinstance(a, dict)}
        for phase in ("flop", "turn", "river"):
            if phase in reached and phase not in seen:
                raise FpdbParseError(f"ChipZen hand reached {phase} but the required phase_change is missing")
        return community

    @staticmethod
    def _turn_result_amounts(record: dict[str, Any]) -> dict[tuple[int, str], deque[Decimal]]:
        """Return chronological authoritative amounts from optional turn results.

        ChipZen's current v1 documentation has a deliberate/legacy mismatch in
        its worked example: ``action_history`` records a preflop BB call as 30
        (the matched street total), while the corresponding ``turn_result``
        records 20 (the chips actually added by that action). ``turn_result``
        explicitly defines calls as incremental and raises as raise-to totals,
        so when it is present we use it to disambiguate the canonical history.
        """
        amounts: dict[tuple[int, str], deque[Decimal]] = defaultdict(deque)
        for item in record.get("turn_results") or []:
            details = item.get("details", item) if isinstance(item, dict) else {}
            if not isinstance(details, dict):
                continue
            try:
                seat = int(details["seat"])
                action = str(details["action"])
                amount = Decimal(str(details.get("amount", 0)))
            except (KeyError, TypeError, ValueError, ArithmeticError):
                continue
            amounts[(seat, action)].append(amount)
        return amounts

    @staticmethod
    def _next_turn_result_amount(
        amounts: dict[tuple[int, str], deque[Decimal]], seat: int, action: str
    ) -> Decimal | None:
        queue = amounts.get((seat, action))
        if not queue:
            return None
        return queue.popleft()

    @staticmethod
    def _highest_contribution(contributions: dict[tuple[str, int], Decimal], phase: str) -> Decimal:
        values = [value for (street_phase, _seat), value in contributions.items() if street_phase == phase]
        return max(values, default=Decimal(0))

    @classmethod
    def _call_increment(
        cls,
        *,
        history_amount: Decimal,
        turn_result_amount: Decimal | None,
        prior: Decimal,
        highest: Decimal,
        player: str,
        phase: str,
    ) -> Decimal:
        """Normalize a ChipZen call to the incremental amount fpdb expects."""
        expected = max(Decimal(0), highest - prior)

        if turn_result_amount is not None:
            if turn_result_amount < 0:
                raise FpdbParseError(f"ChipZen call has negative turn_result amount for {player}")
            if turn_result_amount > expected and expected > 0:
                raise FpdbParseError(
                    f"ChipZen call turn_result amount {turn_result_amount} exceeds {expected} to call for {player} on {phase}"
                )
            if history_amount != turn_result_amount:
                log.debug(
                    "ChipZen call amount normalized from action_history=%s to turn_result=%s for %s on %s",
                    history_amount,
                    turn_result_amount,
                    player,
                    phase,
                )
            return turn_result_amount

        # Current docs contain both conventions in examples. If the canonical
        # history carries the final matched street total, convert it back to the
        # increment. If it already carries the increment, preserve it.
        if history_amount == expected:
            return history_amount
        if expected > 0 and history_amount == highest:
            log.debug(
                "ChipZen call amount %s interpreted as call-to total; importing increment %s for %s on %s",
                history_amount,
                expected,
                player,
                phase,
            )
            return expected
        # A short all-in call can be less than the amount required to match the
        # current bet. Without a turn_result/stack delta this is the only safe
        # additional case we can accept.
        if Decimal(0) <= history_amount < expected:
            return history_amount
        if expected == 0 and history_amount == 0:
            return Decimal(0)
        raise FpdbParseError(
            f"Ambiguous ChipZen call amount {history_amount} for {player} on {phase}; expected increment {expected}"
        )

    @classmethod
    def _actions(cls, record: dict[str, Any], names: dict[int, str]) -> list[dict[str, Any]]:
        history = record.get("round_result", {}).get("result", {}).get("action_history")
        if not isinstance(history, list) or not history:
            raise FpdbParseError("ChipZen round_result.action_history is missing")

        actions: list[dict[str, Any]] = []
        contributions: dict[tuple[str, int], Decimal] = defaultdict(Decimal)
        turn_result_amounts = cls._turn_result_amounts(record)

        for entry in history:
            if not isinstance(entry, dict):
                raise FpdbParseError("ChipZen action_history contains a non-object entry")
            try:
                seat = int(entry["seat"])
                kind = str(entry["action"])
                phase = str(entry["phase"]).lower()
                amount = Decimal(str(entry.get("amount", 0)))
            except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
                raise FpdbParseError(f"Malformed ChipZen action: {entry!r}") from exc
            if seat not in names:
                raise FpdbParseError(f"ChipZen action references unknown seat {seat}")
            if phase not in cls._PHASE_TO_STREET:
                raise FpdbParseError(f"ChipZen action has unknown phase {phase!r}")
            if amount < 0:
                raise FpdbParseError(f"ChipZen action has negative amount: {entry!r}")

            street = cls._PHASE_TO_STREET[phase]
            player = names[seat]
            key = (phase, seat)
            observed = None if kind in cls._SYNTHETIC_ACTIONS else cls._next_turn_result_amount(
                turn_result_amounts, seat, kind
            )

            if kind == "post_small_blind":
                actions.append({"type": "small blind", "player": player, "amount": amount})
                contributions[key] += amount
            elif kind == "post_big_blind":
                actions.append({"type": "big blind", "player": player, "amount": amount})
                contributions[key] += amount
            elif kind == "post_ante":
                actions.append({"type": "ante", "player": player, "amount": amount})
            elif kind == "fold":
                actions.append({"type": "folds", "street": street, "player": player})
            elif kind == "check":
                actions.append({"type": "checks", "street": street, "player": player})
            elif kind == "call":
                prior = contributions[key]
                highest = cls._highest_contribution(contributions, phase)
                increment = cls._call_increment(
                    history_amount=amount,
                    turn_result_amount=observed,
                    prior=prior,
                    highest=highest,
                    player=player,
                    phase=phase,
                )
                actions.append({"type": "calls", "street": street, "player": player, "amount": increment})
                contributions[key] += increment
            elif kind == "raise":
                # turn_result and turn_action both define raises as raise-to
                # totals, which maps directly to Hand.addRaiseTo().
                raise_to = observed if observed is not None else amount
                prior = contributions[key]
                highest = cls._highest_contribution(contributions, phase)
                if raise_to < prior or raise_to <= highest:
                    raise FpdbParseError(
                        f"ChipZen raise-to {raise_to} is not above the current contribution {highest} for {player}"
                    )
                actions.append({"type": "raises", "street": street, "player": player, "to": raise_to})
                contributions[key] = raise_to
            else:
                raise FpdbParseError(f"Unsupported ChipZen NLHE action {kind!r}")

            if entry.get("is_timeout"):
                log.debug("ChipZen timeout action imported: seat=%s phase=%s action=%s", seat, phase, kind)
        return actions

    @classmethod
    def normalize_record(cls, record: dict[str, Any]) -> dict[str, Any]:
        """Translate one ChipZen bundle into fpdb's normalized capture model."""
        match = record.get("match") or {}
        game = match.get("game_config") or {}
        round_start = record.get("round_start") or {}
        start_state = round_start.get("state") or {}
        round_result = record.get("round_result") or {}
        result = round_result.get("result") or {}

        if game.get("variant") not in (None, "nlhe"):
            raise FpdbParseError(f"Unsupported ChipZen variant {game.get('variant')!r}; MVP supports NLHE only")

        names = cls._seat_names(record)
        num_players = int(game.get("num_players") or len(names) or 0)
        if num_players < 2 or num_players > 6 or len(names) < 2:
            raise FpdbParseError(f"Invalid ChipZen table size/seats: num_players={num_players}, seats={names!r}")

        stacks = start_state.get("stacks")
        if not isinstance(stacks, list) or len(stacks) < num_players:
            raise FpdbParseError("ChipZen round_start.state.stacks is missing/incomplete")

        match_id = str(match.get("match_id") or round_start.get("match_id") or round_result.get("match_id") or "")
        round_id = str(round_start.get("round_id") or round_result.get("round_id") or "") or None
        hand_number = start_state.get("hand_number", result.get("hand_number"))
        hand_id = cls.stable_hand_id(match_id, round_id, hand_number)
        short_match = match_id.replace("-", "")[:8] or "unknown"

        players = []
        hero = ""
        for seat in range(num_players):
            name = names.get(seat, f"ChipZen-seat-{seat}")
            players.append({"seat_idx": seat, "name": name, "starting_stack": stacks[seat], "dealt": True})
            seat_meta = next((s for s in match.get("seats") or [] if isinstance(s, dict) and s.get("seat") == seat), {})
            if seat_meta.get("is_self"):
                hero = name

        holecards = []
        hero_cards = start_state.get("your_hole_cards")
        if hero and isinstance(hero_cards, list) and hero_cards:
            holecards.append({"player": hero, "cards": list(hero_cards), "street": "PREFLOP", "dealt": True})

        shown_players: set[str] = set()
        for shown in result.get("showdown") or []:
            if not isinstance(shown, dict) or shown.get("seat") not in names:
                continue
            cards = shown.get("hole_cards")
            if cards:
                player = names[int(shown["seat"])]
                shown_players.add(player)
                holecards.append(
                    {
                        "player": player,
                        "cards": list(cards),
                        "street": "PREFLOP",
                        "shown": True,
                        "dealt": True,
                    }
                )

        # Avoid adding the hero twice when their private cards are also present
        # in showdown. The shown version is richer and should win.
        if hero in shown_players:
            holecards = [entry for entry in holecards if entry.get("player") != hero or entry.get("shown")]

        collections = []
        for payout in result.get("payouts") or []:
            if not isinstance(payout, dict):
                continue
            seat = payout.get("seat")
            if seat not in names:
                raise FpdbParseError(f"ChipZen payout references unknown seat {seat!r}")
            collections.append({"player": names[int(seat)], "pot": payout.get("amount", 0)})
        if not collections:
            raise FpdbParseError("ChipZen completed hand has no payouts")

        sb = game.get("small_blind", 0)
        bb = game.get("big_blind", 0)
        ante = game.get("ante", 0)
        timestamp = round_start.get("server_ts") or round_result.get("server_ts") or match.get("started_at")
        button = start_state.get("dealer_seat")

        return {
            "site": "ChipZen",
            "hand_id": hand_id,
            "table_id": f"ChipZen {short_match}",
            "timestamp": timestamp,
            "hero": hero,
            "buttonpos": int(button) + 1 if button is not None else None,
            "game": {"base": "hold", "category": "holdem", "fpdb_supported": True},
            "gametype": {
                "type": "ring",
                "base": "hold",
                "category": "holdem",
                "limitType": "nl",
                "currency": "play",
                "sb": str(sb),
                "bb": str(bb),
                "ante": str(ante),
                "maxSeats": num_players,
                "mix": "none",
            },
            "players": players,
            "community": cls._community(record),
            "holecards": holecards,
            "actions": cls._actions(record, names),
            "collections": collections,
            "metadata": {
                "source": "chipzen",
                "schema": record["schema"],
                "match_id": match_id,
                "round_id": round_id,
                "hand_number": hand_number,
                "state_model": "event",
            },
        }

    def processHand(self, handText):  # noqa: N802 - legacy API
        record = self._record(handText)
        normalized = self.normalize_record(record)
        try:
            hand = build_fpdb_hand(normalized, config=self.config, hhc=self, hand_text=handText)
        except CaptureNotImportableError as exc:
            raise FpdbParseError(f"ChipZen hand cannot be imported: {exc}") from exc
        hand.rake = Decimal("0")
        self._warn_if_hand_missing_expected_data(hand)
        return hand

    # HandHistoryConverter's normal text-parsing surface is abstract. This
    # converter overrides processHand() because its source is structured JSON;
    # these methods therefore exist only to satisfy the common converter API.
    def readSupportedGames(self):  # noqa: N802
        return [["ring", "hold", "nl"]]

    def determineGameType(self, handText):  # noqa: N802
        return self.normalize_record(self._record(handText))["gametype"]

    def readHandInfo(self, hand):  # noqa: N802
        return None

    def readPlayerStacks(self, hand):  # noqa: N802
        return None

    def compilePlayerRegexs(self, hand):  # noqa: N802
        return None

    def markStreets(self, hand):  # noqa: N802
        return None

    def readBlinds(self, hand):  # noqa: N802
        return None

    def readSTP(self, hand):  # noqa: N802
        return None

    def readAntes(self, hand):  # noqa: N802
        return None

    def readBringIn(self, hand):  # noqa: N802
        return None

    def readButton(self, hand):  # noqa: N802
        return None

    def readHoleCards(self, hand):  # noqa: N802
        return None

    def readAction(self, hand, street):  # noqa: N802
        return None

    def readCollectPot(self, hand):  # noqa: N802
        return None

    def readShownCards(self, hand):  # noqa: N802
        return None

    def readTourneyResults(self, hand):  # noqa: N802
        return None

    def readSummaryInfo(self, summaryInfoList):  # noqa: N802
        return False
