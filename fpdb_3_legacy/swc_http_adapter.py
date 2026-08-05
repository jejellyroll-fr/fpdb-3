"""SwC Poker HTTP/WebSocket adapter for canonical capture envelopes."""

from __future__ import annotations

import datetime
import json
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from fpdb_3_legacy.http_capture_actions import _decimal, _money, infer_snapshot_street, reconstruct_snapshot_actions
from fpdb_3_legacy.http_capture_diff import diff_snapshot_steps
from fpdb_3_legacy.http_capture_importability import evaluate_capture_importability
from fpdb_3_legacy.http_capture_models import CapturedGameDefinition, swc_game_definition
from fpdb_3_legacy.http_capture_ofc import normalize_ofc_capture

SUITS = ["c", "d", "h", "s"]
RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]


def utc_now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")


def card_id_to_str(card_id: int) -> str:
    if card_id < 0 or card_id > 51:
        return "--"
    return f"{RANKS[card_id // 4]}{SUITS[card_id % 4]}"


def parse_cards_string(d_str: str, is_ofc: bool = True) -> tuple[list[str], list[str], list[str], list[str]]:
    if not d_str:
        return [], [], [], []
    try:
        parts = d_str.split("-")
        cards_part = parts[0]
        if not cards_part:
            return [], [], [], []
        card_ids = [int(x) for x in cards_part.split(";") if x]

        if not is_ofc:
            return [], [], [], [card_id_to_str(c) for c in card_ids]

        if len(parts) >= 4:
            t_count = int(parts[1])
            m_count = int(parts[2])
            b_count = int(parts[3])

            top_cards = [card_id_to_str(c) for c in card_ids[:t_count]]
            mid_cards = [card_id_to_str(c) for c in card_ids[t_count : t_count + m_count]]
            bot_cards = [card_id_to_str(c) for c in card_ids[t_count + m_count : t_count + m_count + b_count]]

            placed_sum = t_count + m_count + b_count
            active_cards = [card_id_to_str(c) for c in card_ids[placed_sum:]]

            while len(top_cards) < 3:
                top_cards.append("--")
            while len(mid_cards) < 5:
                mid_cards.append("--")
            while len(bot_cards) < 5:
                bot_cards.append("--")
            return top_cards, mid_cards, bot_cards, active_cards

        return [], [], [], [card_id_to_str(c) for c in card_ids]
    except (TypeError, ValueError):
        return ["--"] * 3, ["--"] * 5, ["--"] * 5, []


def parse_board_cards(board_str: str) -> list[str]:
    if not board_str:
        return []
    try:
        return [card_id_to_str(int(card_id)) for card_id in board_str.split(";") if card_id]
    except (TypeError, ValueError):
        return []


def seat_is_folded(seat: dict[str, Any]) -> bool:
    """Return a best-effort folded flag from known/probable SwC seat fields."""

    for key in ("folded", "f", "fd", "fo"):
        value = seat.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)) and value:
            return True
        if isinstance(value, str) and value.lower() in {"1", "true", "folded", "fold"}:
            return True
    status = str(seat.get("st", seat.get("status", ""))).lower()
    return status in {"folded", "fold"}


def extract_socketio_proxy_message(payload: str) -> dict[str, Any] | None:
    """Extract a generic SwC Socket.IO proxy-message envelope."""

    if not isinstance(payload, str) or not payload.startswith("42/poker/,"):
        return None
    try:
        arr = json.loads(payload[10:])
        if not arr or arr[0] != "proxy-message":
            return None
        inner = json.loads(arr[1])
        if not isinstance(inner, dict):
            return None
        return inner
    except (IndexError, TypeError, json.JSONDecodeError):
        return None


def describe_socketio_frame(payload: str) -> dict[str, Any]:
    """Return best-effort metadata for any SwC Socket.IO frame."""

    if not isinstance(payload, str):
        return {"message_type": "binary_or_unknown"}
    if not payload.startswith("42/poker/,"):
        return {"message_type": f"socketio_opcode_{payload[:2] or 'unknown'}"}
    try:
        arr = json.loads(payload[10:])
    except json.JSONDecodeError:
        return {"message_type": "socketio_unparsed"}
    event_name = arr[0] if arr else "unknown"
    if event_name == "proxy-message":
        proxy_message = extract_socketio_proxy_message(payload)
        if proxy_message:
            return {
                "message_type": proxy_message.get("t", "proxy-message"),
                "socketio_event": event_name,
                "proxy_id": proxy_message.get("id"),
                "src_msg_id": proxy_message.get("srcMsgId"),
            }
    return {"message_type": f"socketio:{event_name}", "socketio_event": event_name}


def extract_game_state_from_socketio(payload: str) -> dict[str, Any] | None:
    """Extract a SwC GameState dict from a Socket.IO websocket frame."""

    inner = extract_socketio_proxy_message(payload)
    if not inner or inner.get("t") != "GameState":
        return None
    game_state = inner.get("gameState")
    return game_state if isinstance(game_state, dict) else None


def extract_swc_game_state_message(payload: str) -> dict[str, Any] | None:
    """Extract the complete SwC GameState proxy message, including events."""

    inner = extract_socketio_proxy_message(payload)
    if not inner or inner.get("t") != "GameState":
        return None
    game_state = inner.get("gameState")
    if not isinstance(game_state, dict):
        return None
    events = inner.get("events")
    if not isinstance(events, list):
        events = []
    return {"gameState": game_state, "events": events, "proxy": inner}


@dataclass
class SwCProcessResult:
    """Result of feeding one SwC state into the adapter."""

    hand_id: str | int | None = None
    current_hand: dict[str, Any] | None = None
    finalized_hands: list[dict[str, Any]] = field(default_factory=list)
    game: CapturedGameDefinition | None = None


class SwCHttpAdapter:
    """Normalize SwC GameState snapshots into FPDB-aligned capture envelopes."""

    site = "SealsWithClubs"

    def __init__(self) -> None:
        self.active_hands: dict[Any, dict[str, Any]] = {}
        self.last_hand_id: Any = None
        self.last_hand_id_by_table: dict[Any, Any] = {}

    def identify_message(self, payload: Any) -> bool:
        return bool(extract_game_state_from_socketio(payload)) if isinstance(payload, str) else False

    def extract_hand_id(self, payload: Any) -> str | int | None:
        if isinstance(payload, dict):
            return payload.get("gi")
        game_state = extract_game_state_from_socketio(payload) if isinstance(payload, str) else None
        return game_state.get("gi") if game_state else None

    def extract_game_definition(self, payload: Any) -> CapturedGameDefinition | None:
        game_state = payload if isinstance(payload, dict) else extract_game_state_from_socketio(payload)
        if not game_state:
            return None
        return swc_game_definition(game_state.get("gt"))

    def process_socketio_frame(
        self,
        payload: str,
        *,
        captured_at: str | None = None,
        raw_ref: str | None = None,
    ) -> SwCProcessResult:
        message = extract_swc_game_state_message(payload)
        if not message:
            return SwCProcessResult()
        return self.process_game_state(
            message["gameState"],
            captured_at=captured_at,
            raw_ref=raw_ref,
            events=message.get("events", []),
        )

    def process_game_state(
        self,
        gs: dict[str, Any],
        *,
        captured_at: str | None = None,
        raw_ref: str | None = None,
        events: list[dict[str, Any]] | None = None,
    ) -> SwCProcessResult:
        captured_at = captured_at or utc_now_iso()
        gi = gs.get("gi")
        if not gi:
            return SwCProcessResult()

        gt_code = gs.get("gt", 74)
        game_definition = swc_game_definition(gt_code)
        game_name = game_definition.label if game_definition.label != "Unknown" else f"Poker (Type {gt_code})"
        is_ofc = game_definition.base == "ofc" or "ofc" in game_name.lower()

        finalized_hands = []
        table_key = gs.get("ti", "__unknown_table__")
        previous_table_hand_id = self.last_hand_id_by_table.get(table_key)
        if previous_table_hand_id and previous_table_hand_id != gi and previous_table_hand_id in self.active_hands:
            finalized_hands.append(self.active_hands[previous_table_hand_id])
            self.active_hands.pop(previous_table_hand_id, None)

        self.last_hand_id_by_table[table_key] = gi
        self.last_hand_id = gi

        if gi not in self.active_hands:
            self.active_hands[gi] = self._new_hand(gs, game_definition, game_name, captured_at)

        hand_data = self.active_hands[gi]
        if raw_ref:
            hand_data.setdefault("raw_refs", []).append(raw_ref)

        was_finalized = bool(hand_data.get("_finalized"))
        self._populate_players_once(hand_data, gs)
        self._append_step_if_changed(hand_data, gs, is_ofc)
        self._append_events(hand_data, events or [], raw_ref=raw_ref)
        self._refresh_gametype_from_snapshot(hand_data)
        self._finalize_showdown_if_complete(hand_data, gs)
        if hand_data.get("swc_events"):
            self._extract_collections_from_events(hand_data)
        if is_ofc:
            normalize_ofc_capture(hand_data)
        else:
            reconstruct_snapshot_actions(hand_data)
            if hand_data.get("swc_events"):
                self._reconstruct_actions_from_events(hand_data)
        self._refresh_importability(hand_data)

        if hand_data.get("_finalized") and not was_finalized and hand_data not in finalized_hands:
            finalized_hands.append(hand_data)

        return SwCProcessResult(
            hand_id=gi,
            current_hand=hand_data,
            finalized_hands=finalized_hands,
            game=game_definition,
        )

    def _new_hand(
        self,
        gs: dict[str, Any],
        game_definition: CapturedGameDefinition,
        game_name: str,
        captured_at: str,
    ) -> dict[str, Any]:
        seats = [seat for seat in gs.get("s", []) if seat]
        return {
            "site": self.site,
            "hand_id": gs.get("gi"),
            "game_type": game_name,
            "game": game_definition.to_capture_dict(),
            "gametype": game_definition.gametype(currency="mBTC", max_seats=len(seats)),
            "streets": game_definition.street_profile.to_dict(),
            "table_id": gs.get("ti"),
            "timestamp": captured_at,
            "dealer_idx": gs.get("m", {}).get("di", -1),
            "sb_idx": gs.get("m", {}).get("sb", -1),
            "bb_idx": gs.get("m", {}).get("bb", -1),
            "players": [],
            "steps": [],
            "actions": [],
            "swc_events": [],
            "showdown": None,
            "raw_refs": [],
            "metadata": {
                "adapter": "swc_http",
                "state_model": "snapshot",
                "importability": {
                    "importable": False,
                    "status": "capture_only",
                    "reasons": ["normalization not evaluated yet"],
                },
            },
            "_last_state": None,
            "_swc_event_keys": set(),
            "_finalized": False,
        }

    def _append_events(self, hand_data: dict[str, Any], events: list[dict[str, Any]], *, raw_ref: str | None = None) -> None:
        if not events:
            return

        step = hand_data["steps"][-1] if hand_data.get("steps") else {}
        previous_step = hand_data["steps"][-2] if len(hand_data.get("steps", [])) > 1 else None
        current_street = step.get("street", "UNKNOWN")
        previous_street = previous_step.get("street") if previous_step else None
        street_transition = previous_street and previous_street != current_street

        for event_idx, event in enumerate(events):
            if not isinstance(event, dict):
                continue
            key = (
                raw_ref,
                step.get("step_num"),
                event_idx,
                event.get("type"),
                event.get("action"),
                event.get("amount"),
                event.get("seat-idx"),
                event.get("table-msg"),
            )
            if key in hand_data["_swc_event_keys"]:
                continue
            hand_data["_swc_event_keys"].add(key)
            action_code = event.get("action")
            street = current_street
            if event.get("type") == 9 and action_code in {1, 2, 3, 8, 9, 25} and street_transition:
                street = previous_street
            if event.get("type") == 9 and action_code in {4, 6, 7}:
                street = "BLINDSANTES"
            hand_data["swc_events"].append(
                {
                    "step_num": step.get("step_num"),
                    "street": street,
                    "raw_ref": raw_ref,
                    "event": dict(event),
                }
            )

    def _reconstruct_actions_from_events(self, hand_data: dict[str, Any]) -> None:
        players_by_seat = {
            int(player["seat_idx"]): player["name"]
            for player in hand_data.get("players", [])
            if player.get("seat_idx") is not None and player.get("name")
        }
        steps_by_num = {step.get("step_num"): step for step in hand_data.get("steps", [])}

        actions: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []
        collections = list(hand_data.get("collections", []))
        collection_keys = {(item.get("player"), item.get("pot"), item.get("step_num")) for item in collections}
        ignored = 0

        for entry in hand_data.get("swc_events", []):
            event = entry.get("event", {})
            if event.get("type") == 15 and "wins" in str(event.get("table-msg", "")).lower():
                collection = self._collection_from_table_message(entry, event, players_by_seat)
                if collection:
                    key = (collection.get("player"), collection.get("pot"), collection.get("step_num"))
                    if key not in collection_keys:
                        collections.append(collection)
                        collection_keys.add(key)
                continue
            if event.get("type") != 9:
                continue

            action_code = event.get("action")
            seat_idx = event.get("seat-idx")
            try:
                player = players_by_seat[int(seat_idx)]
            except (KeyError, TypeError, ValueError):
                ignored += 1
                continue

            amount = _money(_decimal(event.get("amount", 0)) / Decimal("100"))
            base_action = {
                "street": entry.get("street", "UNKNOWN"),
                "player": player,
                "source": "swc_game_state_event",
                "swc_event_type": event.get("type"),
                "swc_action": action_code,
                "step_num": entry.get("step_num"),
                "fpdb_action": True,
            }

            if action_code == 4:
                actions.append({**base_action, "type": "ante", "amount": amount})
            elif action_code == 6:
                actions.append({**base_action, "type": "small blind", "amount": amount})
            elif action_code == 7:
                actions.append({**base_action, "type": "big blind", "amount": amount})
            elif action_code == 1:
                actions.append({**base_action, "type": "folds"})
            elif action_code == 2:
                actions.append({**base_action, "type": "checks"})
            elif action_code == 3:
                actions.append({**base_action, "type": "calls", "amount": amount})
            elif action_code == 8:
                actions.append({**base_action, "type": "bets", "amount": amount})
            elif action_code in {9, 25}:
                step = steps_by_num.get(entry.get("step_num"), {})
                to_amount = _money(step.get("bets", {}).get(player, amount))
                actions.append({**base_action, "type": "raises", "amount": amount, "to": to_amount})
            elif action_code in {10, 11, 16, 21, 26}:
                ignored += 1
            else:
                evidence.append(
                    {
                        "type": "swc_unmapped_player_action",
                        "street": entry.get("street", "UNKNOWN"),
                        "player": player,
                        "amount": amount,
                        "swc_action": action_code,
                        "step_num": entry.get("step_num"),
                    }
                )

        snapshot_state_evidence = hand_data.get("state_evidence", [])
        hand_data["actions"] = actions
        hand_data["action_evidence"] = evidence
        hand_data["state_evidence"] = snapshot_state_evidence
        if collections:
            hand_data["collections"] = collections
        status = "none"
        if actions and not evidence:
            status = "complete"
        elif actions or evidence:
            status = "partial"
        hand_data.setdefault("metadata", {})["action_reconstruction"] = {
            "status": status,
            "source": "swc_game_state_events",
            "safe_actions": len(actions),
            "evidence_items": len(evidence),
            "state_evidence_items": len(snapshot_state_evidence),
            "ignored_event_items": ignored,
        }

    def _extract_collections_from_events(self, hand_data: dict[str, Any]) -> None:
        players_by_seat = {
            int(player["seat_idx"]): player["name"]
            for player in hand_data.get("players", [])
            if player.get("seat_idx") is not None and player.get("name")
        }
        collections = list(hand_data.get("collections", []))
        collection_keys = {(item.get("player"), item.get("pot"), item.get("step_num")) for item in collections}
        for entry in hand_data.get("swc_events", []):
            event = entry.get("event", {})
            if event.get("type") != 15 or "wins" not in str(event.get("table-msg", "")).lower():
                continue
            collection = self._collection_from_table_message(entry, event, players_by_seat)
            if not collection:
                continue
            key = (collection.get("player"), collection.get("pot"), collection.get("step_num"))
            if key in collection_keys:
                continue
            collections.append(collection)
            collection_keys.add(key)
        if collections:
            hand_data["collections"] = collections

    def _collection_from_table_message(
        self,
        entry: dict[str, Any],
        event: dict[str, Any],
        players_by_seat: dict[int, str],
    ) -> dict[str, Any] | None:
        seat_idx = event.get("seat-idx")
        if seat_idx is None:
            return None
        try:
            player = players_by_seat[int(seat_idx)]
        except (KeyError, TypeError, ValueError):
            return None

        table_msg = str(event.get("table-msg", ""))
        money_match = re.search(r'<money\s+[^>]*a="(?P<amount>\d+)"', table_msg)
        if money_match:
            amount = money_match.group("amount")
        else:
            amount = event.get("amount", 0)
        pot = _money(_decimal(amount) / Decimal("100"))
        if _decimal(pot) <= 0:
            return None
        return {
            "player": player,
            "pot": pot,
            "street": entry.get("street", "UNKNOWN"),
            "source": "swc_game_state_event",
            "step_num": entry.get("step_num"),
        }

    def _populate_players_once(self, hand_data: dict[str, Any], gs: dict[str, Any]) -> None:
        if hand_data["players"]:
            return
        for seat_idx, seat in enumerate(gs.get("s", [])):
            if seat:
                hand_data["players"].append(
                    {
                        "name": seat.get("n"),
                        "starting_stack": seat.get("c", 0) / 100.0,
                        "seat_idx": seat_idx,
                    }
                )

    def _refresh_gametype_from_snapshot(self, hand_data: dict[str, Any]) -> None:
        if not hand_data.get("steps"):
            return

        first_step = hand_data["steps"][0]
        bets = first_step.get("bets", {})
        players_by_seat = {
            int(player["seat_idx"]): player["name"]
            for player in hand_data.get("players", [])
            if player.get("seat_idx") is not None and player.get("name")
        }

        sb_idx = hand_data.get("sb_idx", -1)
        bb_idx = hand_data.get("bb_idx", -1)
        sb_player = players_by_seat.get(int(sb_idx)) if sb_idx != -1 else None
        bb_player = players_by_seat.get(int(bb_idx)) if bb_idx != -1 else None
        sb = Decimal(str(bets.get(sb_player, 0))) if sb_player else Decimal("0")
        bb = Decimal(str(bets.get(bb_player, 0))) if bb_player else Decimal("0")

        hand_data["gametype"]["currency"] = "mBTC"
        hand_data["gametype"]["maxSeats"] = len([player for player in hand_data.get("players", []) if player.get("name")])
        if sb > 0:
            hand_data["gametype"]["sb"] = sb
        if bb > 0:
            hand_data["gametype"]["bb"] = bb

        hand_data.setdefault("metadata", {})["gametype_inference"] = {
            "currency": "mBTC",
            "small_blind_player": sb_player,
            "big_blind_player": bb_player,
            "small_blind": str(sb.normalize()),
            "big_blind": str(bb.normalize()),
            "max_seats": hand_data["gametype"]["maxSeats"],
        }

    def _current_state_key(self, gs: dict[str, Any]) -> dict[str, Any]:
        current_state = {
            "board": gs.get("d", {}).get("c", ""),
            "pot": gs.get("d", {}).get("p", 0),
            "ts": gs.get("ts"),
            "ss_hc": gs.get("ss", {}).get("hc", ""),
            "seats": [],
        }
        for seat in gs.get("s", []):
            if seat:
                current_state["seats"].append(
                    {
                        "n": seat.get("n"),
                        "c": seat.get("c"),
                        "b": seat.get("b"),
                        "d": seat.get("d"),
                    }
                )
        return current_state

    def _append_step_if_changed(self, hand_data: dict[str, Any], gs: dict[str, Any], is_ofc: bool) -> None:
        current_state = self._current_state_key(gs)
        if hand_data["steps"] and hand_data["_last_state"] == current_state:
            return

        hand_data["_last_state"] = current_state
        step_placed = {}
        step_bets = {}
        step_stacks = {}
        step_folded = []

        for seat in gs.get("s", []):
            if not seat:
                continue
            name = seat.get("n")
            step_bets[name] = seat.get("b", 0) / 100.0
            step_stacks[name] = seat.get("c", 0) / 100.0
            if seat_is_folded(seat):
                step_folded.append(name)

            d_str = seat.get("d", "")
            has_no_cards = not d_str or not d_str.split("-")[0]
            if has_no_cards and hand_data["steps"] and is_ofc:
                prev_placed = hand_data["steps"][-1]["placed"].get(name, {})
                top = prev_placed.get("top", [])
                mid = prev_placed.get("middle", [])
                bot = prev_placed.get("bottom", [])
                active = prev_placed.get("active", [])
            else:
                top, mid, bot, active = parse_cards_string(d_str, is_ofc=is_ofc)

            if is_ofc:
                step_placed[name] = {
                    "top": top,
                    "middle": mid,
                    "bottom": bot,
                    "active": active,
                    "hcnu": seat.get("hcnu", ""),
                    "lcnu": seat.get("lcnu", ""),
                    "points": seat.get("p", 0),
                    "points_breakdown": seat.get("chihr", []),
                }
            else:
                step_placed[name] = {"cards": active}

        previous_step = hand_data["steps"][-1] if hand_data["steps"] else None
        step = {
            "step_num": len(hand_data["steps"]) + 1,
            "placed": step_placed,
            "board": parse_board_cards(gs.get("d", {}).get("c", "")),
            "pot": gs.get("d", {}).get("p", 0) / 100.0,
            "rake": gs.get("d", {}).get("r", 0) / 100.0,
            "bets": step_bets,
            "stacks": step_stacks,
            "folded": step_folded,
            "ts": gs.get("ts"),
        }
        step["street"] = infer_snapshot_street(hand_data, step)
        step["diff"] = diff_snapshot_steps(previous_step, step)
        hand_data["steps"].append(step)

    def _finalize_showdown_if_complete(self, hand_data: dict[str, Any], gs: dict[str, Any]) -> None:
        ss = gs.get("ss")
        is_hand_done = (ss and ss.get("hc")) or (gs.get("ts") == 0 and len(hand_data["steps"]) > 2)
        if not is_hand_done or hand_data["showdown"]:
            return

        showdown_desc = {}
        if ss and ss.get("hc"):
            hc_lines = [line.strip() for line in ss["hc"].split("\n") if line.strip()]
            for idx, seat in enumerate(gs.get("s", [])):
                if seat and idx < len(hc_lines):
                    parts = hc_lines[idx].split("\t")
                    showdown_desc[seat["n"]] = {
                        "top": parts[0].strip() if len(parts) > 0 else "FOUL",
                        "mid": parts[1].strip() if len(parts) > 1 else "FOUL",
                        "bot": parts[2].strip() if len(parts) > 2 else "FOUL",
                    }

        showdown_points_desc = {}
        for seat in gs.get("s", []):
            if not seat:
                continue
            name = seat.get("n")
            ch = seat.get("chihr", [])
            if ch and isinstance(ch, list):
                line_pts = 0
                top_roy = 0
                mid_roy = 0
                bot_roy = 0
                for comp in ch:
                    line_pts += comp.get("e", 0)
                    for row_info in comp.get("h", []):
                        r_idx = row_info.get("h")
                        if r_idx == 0:
                            top_roy += row_info.get("b", 0)
                        elif r_idx == 1:
                            mid_roy += row_info.get("b", 0)
                        elif r_idx == 2:
                            bot_roy += row_info.get("b", 0)

                showdown_points_desc[name] = {
                    "lines": line_pts,
                    "top_royalty": top_roy,
                    "middle_royalty": mid_roy,
                    "bottom_royalty": bot_roy,
                    "total": line_pts + top_roy + mid_roy + bot_roy,
                }

        hand_data["showdown"] = {
            "points_settled": {seat["n"]: seat.get("p", 0) for seat in gs.get("s", []) if seat},
            "rows": showdown_desc,
            "points_breakdown": showdown_points_desc,
        }
        hand_data["_finalized"] = True

    def _refresh_importability(self, hand_data: dict[str, Any]) -> None:
        hand_data["metadata"]["importability"] = evaluate_capture_importability(hand_data).to_dict()
