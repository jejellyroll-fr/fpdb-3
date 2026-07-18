#!/usr/bin/env python3
"""Build normalized fpdb hand dicts from decoded CoinPoker game events.

Consumes the ``game.*`` event stream produced by ``coinpoker_protocol`` and
emits the normalized ``hand_data`` dicts consumed by
``http_capture_hand_builder.build_fpdb_hand`` (players / actions / community /
holecards / collections). Currently targets ring Hold'em and Omaha (PLO).
"""

from __future__ import annotations

import re
from collections import defaultdict
from decimal import Decimal
from typing import Any

from fpdb_3_legacy.coinpoker_protocol import iter_game_events

_VALUE = {
    "TWO": "2", "THREE": "3", "FOUR": "4", "FIVE": "5", "SIX": "6", "SEVEN": "7",
    "EIGHT": "8", "NINE": "9", "TEN": "T", "JACK": "J", "QUEEN": "Q", "KING": "K", "ACE": "A",
}
_SUIT = {"SPADES": "s", "HEARTS": "h", "DIAMONDS": "d", "CLUBS": "c"}
_NUM_RANK = {10: "T", 11: "J", 12: "Q", 13: "K", 14: "A"}

# CoinPoker categories -> (fpdb base, category). PLO4 == 4-card Omaha high.
_CATEGORY = {
    "PLO4": ("hold", "omahahi"),
    "PLO5": ("hold", "5_omahahi"),
    "PLO6": ("hold", "6_omahahi"),
    "NLH": ("hold", "holdem"),
    "NLHE": ("hold", "holdem"),
}


def _card(c: dict) -> str:
    return _VALUE[c["value"]] + _SUIT[c["suit"]]


def _cards(lst: list[dict]) -> list[str]:
    return [_card(c) for c in lst or []]


def _chat_card(tok: str) -> str:
    tok = tok.strip()
    suit = tok[-1].lower()
    num = int(tok[:-1])
    return _NUM_RANK.get(num, str(num)) + suit


def _first(evs: list[tuple], name: str) -> Any:
    return next((d for n, _h, d in evs if n == name and isinstance(d, dict)), None)


def build_hands_from_stream(s2c: bytes, table_category: str = "PLO4") -> list[dict[str, Any]]:
    return build_hands(list(iter_game_events(s2c)), table_category)


def build_hands(events: list[tuple[str, str | None, Any]], table_category: str = "PLO4") -> list[dict[str, Any]]:
    """Group decoded events by hand id and build a normalized dict per hand."""
    order: list[str] = []
    groups: dict[str, list[tuple]] = defaultdict(list)
    for name, hid, data in events:
        if hid is None:
            if order:
                groups[order[-1]].append((name, hid, data))
            continue
        if hid not in groups:
            order.append(hid)
        groups[hid].append((name, hid, data))

    hands = []
    for hid in order:
        built = _build_one(hid, groups[hid], table_category)
        if built:
            hands.append(built)
    return hands


def _collect_players(evs: list[tuple]) -> dict[str, dict]:
    """Return {name: {seat, stack}}, stack = chips before the player acted.

    Each seat maps to exactly one player: if a seat changes occupants within the
    captured window (a player leaves, another sits down), the first occupant seen
    wins, so fpdb never receives two players in the same seat.
    """
    players: dict[str, dict] = {}
    used_seats: set = set()

    def note(entry: dict) -> None:
        name = entry.get("userName")
        seat = entry.get("seatId")
        if not name or name in players or seat is None or seat in used_seats:
            return
        chips = Decimal(str(entry.get("userChips", 0) or 0))
        bet = Decimal(str(entry.get("betAmout", 0) or 0))
        players[name] = {"seat": seat, "stack": chips + bet}
        used_seats.add(seat)

    info = _first(evs, "game.seatInfo")
    if info:
        for s in info.get("seatResponseDataList", []) or []:
            note(s)
    for name, _h, d in evs:
        if name in ("game.seat", "game.seatInfo") and isinstance(d, dict):
            if name == "game.seatInfo":
                for s in d.get("seatResponseDataList", []) or []:
                    note(s)
            else:
                note(d)
    return players



def _build_one(hid: str, evs: list[tuple], table_category: str) -> dict[str, Any] | None:
    info = _first(evs, "game.pre_hand_start_info")
    if not info:
        return None

    base, category = _CATEGORY.get(table_category.upper(), ("hold", "omahahi"))
    sb = Decimal(str(info.get("sbAmount", 0)))
    bb = Decimal(str(info.get("bbAmount", 0)))
    ante = Decimal(str(info.get("anteAmount", 0)))

    players = _collect_players(evs)
    seat2name = {p["seat"]: n for n, p in players.items()}

    actions: list[dict] = []
    # Blinds first (addBlind ignores street).
    if info.get("anteAmount"):
        for nm in players:
            if ante > 0:
                actions.append({"type": "ante", "player": nm, "amount": str(ante)})
    sb_name = seat2name.get(info.get("sbSeatId"))
    bb_name = seat2name.get(info.get("bbSeatId"))
    if sb_name:
        actions.append({"type": "small blind", "player": sb_name, "amount": str(sb)})
    if bb_name:
        actions.append({"type": "big blind", "player": bb_name, "amount": str(bb)})

    # Board from the last cumulative dealer_cards snapshot.
    community: dict[str, list[str]] = {}
    # Cap each street to its real size: run-it-twice can put extra cards under a
    # street key, which would make an invalid 6+ card board (and duplicate-card
    # equity errors). We keep the primary run only.
    street_len = {"FLOP": 3, "TURN": 1, "RIVER": 1}
    for name, _h, d in evs:
        if name == "game.dealer_cards" and isinstance(d, dict):
            dealer = d.get("dealerCards") or {}
            for street in ("FLOP", "TURN", "RIVER"):
                if dealer.get(street):
                    community[street] = _cards(dealer[street])[: street_len[street]]

    # Hero hole cards.
    holecards: list[dict] = []
    hero = None
    for name, _h, d in evs:
        if name == "game.dealer_chat" and isinstance(d, dict):
            m = re.match(r"^(?P<p>.+?) My Hole Cards ", d.get("dealerMessage", ""))
            if m:
                hero = m.group("p")
    hole = _first(evs, "game.hole_cards")
    if hero and hole and hole.get("holeCards"):
        holecards.append({
            "player": hero, "closed": _cards(hole["holeCards"]),
            "dealt": True, "shown": False, "mucked": False,
        })

    # Reconstruct actions from game.seat events (interleaved with the dealer-chat
    # street markers). betAmout is the player's authoritative total commitment on
    # the current street, which reconciles pot math for every action type,
    # including all-ins and side pots, unlike parsing the chat narrative.
    street = "PREFLOP"
    street_has_bet = {"PREFLOP": True, "FLOP": False, "TURN": False, "RIVER": False}
    committed: dict[str, Decimal] = {}  # player -> chips already in this street
    if sb_name:
        committed[sb_name] = sb
    if bb_name:
        committed[bb_name] = bb
    non_actions = {None, "", "Inuse", "SB", "BB", "Waiting", "SitOut", "Muck"}
    for name, _h, d in evs:
        if not isinstance(d, dict):
            continue
        if name == "game.dealer_chat":
            msg = (d.get("dealerMessage") or "").strip()
            if msg == "PREFLOP":
                street = "PREFLOP"
            else:
                m = re.match(r"^(FLOP|TURN|RIVER) \[", msg)
                if m:
                    street = m.group(1)
                    committed.clear()  # new street: reset per-street commitments
            continue
        if name != "game.seat":
            continue
        # Use caption (current state) not lastAction: end-of-hand/return-chips
        # updates keep a stale lastAction like "Raise" while caption is "Inuse".
        action = d.get("caption")
        player = d.get("userName")
        if not player or action in non_actions:
            continue
        bet = Decimal(str(d.get("betAmout", 0) or 0))
        if action == "Fold":
            actions.append({"type": "folds", "player": player, "street": street})
        elif action == "Check":
            actions.append({"type": "checks", "player": player, "street": street})
        elif action == "Call":
            actions.append({"type": "calls", "player": player, "street": street, "amount": str(bet - committed.get(player, Decimal(0)))})
            committed[player] = bet
        else:  # Raise / Bet / Pot / Allin / Straddle -> aggressive: bet to `bet`
            if street_has_bet[street]:
                actions.append({"type": "raises", "player": player, "street": street, "to": str(bet)})
            else:
                actions.append({"type": "bets", "player": player, "street": street, "amount": str(bet)})
            street_has_bet[street] = True
            committed[player] = bet

    # Winners -> collections (use post-rake amount actually paid out).
    collections: list[dict] = []
    win = _first(evs, "game.winnerInfo")
    if win:
        for w in win.get("winnerDataList", []) or []:
            winner_list = (w.get("winnerDetails") or {}).get("winnerList") or []
            for det in winner_list:
                nm = det.get("playerName")
                amt = det.get("winAmountFromPot", w.get("potAmountAfterRake", 0))
                if nm:
                    collections.append({"player": nm, "pot": str(amt)})
    if not collections:
        cum = _first(evs, "game.cumulativeWinnerInfo")
        if cum:
            for w in cum.get("winnersData", []) or []:
                nm = w.get("userName")
                amt = w.get("amount", w.get("winAmount", 0))
                if nm:
                    collections.append({"player": nm, "pot": str(amt)})

    players_list = [
        {"seat_idx": p["seat"], "name": n, "starting_stack": str(p["stack"])}
        for n, p in sorted(players.items(), key=lambda kv: kv[1]["seat"] or 0)
    ]

    # The table id is the hand id without its trailing 5-digit hand counter
    # (gameId 91426500343 -> table 914265), which also matches the number shown
    # in the CoinPoker window title ("PLO4 914265 ..."). This gives each table a
    # distinct, stable name so the HUD creates one window per table.
    try:
        table_id = str(int(hid) // 100000)
    except (ValueError, TypeError):
        table_id = str(info.get("tableId", "") or hid)

    return {
        "site": "CoinPoker",
        "hand_id": str(hid),
        "hero": hero,
        "table_id": table_id,
        "timestamp": None,
        "buttonpos": info.get("dealerSeatId"),
        "game": {"base": base, "category": category, "fpdb_supported": True},
        "gametype": {
            "base": base, "category": category, "type": "ring",
            "limitType": "pl" if base == "hold" and "omaha" in category else "nl",
            "currency": "USD", "sb": str(sb), "bb": str(bb), "ante": str(ante),
            "maxSeats": 6,
        },
        "players": players_list,
        "actions": actions,
        "community": community,
        "holecards": holecards,
        "collections": collections,
    }
