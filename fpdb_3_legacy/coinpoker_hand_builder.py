#!/usr/bin/env python3
"""Build normalized fpdb hand dicts from decoded CoinPoker game events.

Consumes the ``game.*`` event stream produced by ``coinpoker_protocol`` and
emits the normalized ``hand_data`` dicts consumed by
``http_capture_hand_builder.build_fpdb_hand`` (players / actions / community /
holecards / collections). Currently targets ring Hold'em and Omaha (PLO).
"""

from __future__ import annotations

import datetime
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

# CoinPoker game hints (the GUI dropdown) -> (fpdb base, category). Used as a
# fallback when the variant can't be read from the hand itself. SHORTDECK == 6+
# Hold'em (fpdb category 6_holdem).
_CATEGORY = {
    "PLO4": ("hold", "omahahi"),
    "PLO5": ("hold", "5_omahahi"),
    "PLO6": ("hold", "6_omahahi"),
    "NLH": ("hold", "holdem"),
    "NLHE": ("hold", "holdem"),
    "SHORTDECK": ("hold", "6_holdem"),
}

# Hole-card count -> (fpdb base, category), for the counts that are unambiguous.
# CoinPoker's hand events carry no explicit game variant, but the number of cards
# dealt to the hero identifies the Omaha family, so it is detected per hand: a
# PLO5 hand keeps its 5th card even when the session hint says PLO4. Two-card
# games (Hold'em vs short-deck) are handled separately since the count is equal.
_HOLE_COUNT_CATEGORY = {
    4: ("hold", "omahahi"),
    5: ("hold", "5_omahahi"),
    6: ("hold", "6_omahahi"),
}


def _decimal_or_none(value: Any) -> Decimal | None:
    """Return a finite protocol money value, or None for blank/invalid fields."""
    try:
        amount = Decimal(str(value))
    except (ValueError, ArithmeticError):
        return None
    return amount if amount.is_finite() else None

# Card ranks removed from a short deck (6+ Hold'em uses 6..A only). Seeing any of
# them proves a full 52-card deck, i.e. regular Hold'em.
_LOW_RANKS = frozenset({"TWO", "THREE", "FOUR", "FIVE"})

# Real size of each community street. Run-it-twice can stack extra cards under a
# street key; capping keeps every board at five cards (and avoids duplicate-card
# equity errors downstream).
_STREET_LEN = {"FLOP": 3, "TURN": 1, "RIVER": 1}


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



def _hero_hole_count(evs: list[tuple]) -> int:
    """Number of cards dealt to the hero, or 0 if they weren't captured."""
    for name in ("game.hole_cards", "game.player_info"):
        ev = _first(evs, name)
        if isinstance(ev, dict):
            cards = ev.get("holeCards") or ev.get("playerCards")
            if cards:
                return len(cards)
    return 0


def _all_dealt_cards(evs: list[tuple]) -> list[dict]:
    """Every card visible in the hand: the hero's hole cards plus the board."""
    hole = _first(evs, "game.hole_cards")
    cards = list(hole.get("holeCards") or []) if isinstance(hole, dict) else []
    for name, _h, d in evs:
        if name == "game.dealer_cards" and isinstance(d, dict):
            for street_cards in (d.get("dealerCards") or {}).values():
                cards.extend(street_cards or [])
    return [c for c in cards if isinstance(c, dict)]


def _detect_category(evs: list[tuple], table_category: str) -> tuple[str, str]:
    """Pick (base, category) from the hand itself, else the GUI hint.

    The hero's hole-card count identifies the Omaha family unambiguously (4/5/6),
    so it wins. Hold'em and short-deck both deal two cards, so the count can't
    tell them apart: trust the session hint, but a 2-5 rank anywhere proves a full
    deck and rules out short-deck even under a wrong hint. The ``table_category``
    dropdown is the fallback when the hero's cards aren't captured (e.g. observing).
    """
    count = _hero_hole_count(evs)
    if count in _HOLE_COUNT_CATEGORY:
        return _HOLE_COUNT_CATEGORY[count]
    if count == 2:
        _, hinted = _CATEGORY.get(table_category.upper(), ("hold", "holdem"))
        low_card_seen = any(c.get("value") in _LOW_RANKS for c in _all_dealt_cards(evs))
        if hinted == "6_holdem" and not low_card_seen:
            return ("hold", "6_holdem")
        return ("hold", "holdem")
    return _CATEGORY.get(table_category.upper(), ("hold", "omahahi"))


def _hand_start_time(info: dict) -> datetime.datetime | None:
    """Convert the event's initTimeStamp (epoch ms) to a UTC-naive datetime.

    Preferring the protocol's own clock over the import wall-clock keeps replayed
    or backlogged captures on their real dates in the GUI graphs/filters.
    """
    raw = info.get("initTimeStamp")
    try:
        return datetime.datetime.fromtimestamp(int(raw) / 1000, tz=datetime.timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _board_from_dealer(dealer: dict) -> dict[str, list[str]]:
    """Turn a ``dealerCards`` street->cards map into a capped board dict."""
    board: dict[str, list[str]] = {}
    for street in ("FLOP", "TURN", "RIVER"):
        if dealer.get(street):
            board[street] = _cards(dealer[street])[: _STREET_LEN[street]]
    return board


def _extract_boards(evs: list[tuple]) -> tuple[list[dict[str, list[str]]], int, bool]:
    """Return ``(boards, run_it_times, double_board)`` from the dealer snapshots.

    ``boards[0]`` is the primary run. Run-it-twice adds ``dealerCardsRit`` /
    ``dealerCardsRit2`` boards, which share the primary flop (only the turn/river
    are re-dealt after an all-in). A bomb pot's ``dealerCardsDoubleBoard`` is an
    independent second board dealt from its own flop. ``run_it_times`` counts the
    RIT runs only (1 when not run multiple times); a double board is not RIT.
    """
    primary: dict[str, list[str]] = {}
    rit1: dict[str, list[str]] = {}
    rit2: dict[str, list[str]] = {}
    dbl: dict[str, list[str]] = {}
    for name, _h, d in evs:
        if name != "game.dealer_cards" or not isinstance(d, dict):
            continue
        if d.get("dealerCards"):
            primary = _board_from_dealer(d["dealerCards"])
        if d.get("dealerCardsRit"):
            rit1 = _board_from_dealer(d["dealerCardsRit"])
        if d.get("dealerCardsRit2"):
            rit2 = _board_from_dealer(d["dealerCardsRit2"])
        if d.get("dealerCardsDoubleBoard"):
            dbl = _board_from_dealer(d["dealerCardsDoubleBoard"])

    win = _first(evs, "game.winnerInfo") or {}
    rit_flag = bool(win.get("rit")) or bool(rit1) or bool(rit2)
    double_flag = bool(win.get("doubleBoard")) or bool(dbl)

    boards: list[dict[str, list[str]]] = [primary] if primary else []
    for run in (rit1, rit2):
        if run:
            merged = dict(run)
            if not merged.get("FLOP") and primary.get("FLOP"):
                merged["FLOP"] = list(primary["FLOP"])  # RIT runs share the flop
            boards.append(merged)
    if dbl:
        boards.append(dbl)

    run_it_times = len([b for b in (primary, rit1, rit2) if b]) if rit_flag else 1
    return boards, run_it_times, double_flag


def _extract_splash(evs: list[tuple]) -> tuple[int, bool]:
    """Return ``(splash_pot_cents, is_mega_splash)`` from cumulativeWinnerInfo."""
    cum = _first(evs, "game.cumulativeWinnerInfo") or {}
    try:
        amount = int(round(float(cum.get("splashPotAmount", 0) or 0) * 100))
    except (TypeError, ValueError):
        amount = 0
    return amount, bool(cum.get("isMegaSplash"))


def _extract_cashout(evs: list[tuple]) -> list[dict[str, str]]:
    """Return per-player EV cashout (insurance) entries from winnerInfo.

    A winner who took insurance is flagged ``isInsured``: ``actualWinAmount`` is
    what they were actually paid, ``winAmountFromPot`` what the pot owed them, so
    the difference is the insurance fee they gave up.
    """
    cashout: list[dict[str, str]] = []
    for name, _h, d in evs:
        if name != "game.winnerInfo" or not isinstance(d, dict):
            continue
        for w in d.get("winnerDataList", []) or []:
            for det in (w.get("winnerDetails") or {}).get("winnerList") or []:
                if not det.get("isInsured"):
                    continue
                player = det.get("playerName")
                if not player:
                    continue
                paid = _decimal_or_none(det.get("actualWinAmount"))
                pot = _decimal_or_none(det.get("winAmountFromPot"))
                if paid is None:
                    continue
                # Some insured results omit the theoretical pot entitlement.
                # Keep the exact payout and leave the unknown fee at zero.
                if pot is None:
                    pot = paid
                fee = pot - paid
                cashout.append({
                    "player": player,
                    "amount": str(paid),
                    "fee": str(fee if fee > 0 else Decimal(0)),
                })
    return cashout


def _build_one(hid: str, evs: list[tuple], table_category: str) -> dict[str, Any] | None:
    info = _first(evs, "game.pre_hand_start_info")
    if not info:
        return None

    base, category = _detect_category(evs, table_category)
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

    # Boards from the last cumulative dealer_cards snapshot. ``boards[0]`` is the
    # primary run, kept as ``community`` so single-board hands are unchanged; the
    # full list carries run-it-twice runs and bomb-pot double boards.
    boards, run_it_times, double_board = _extract_boards(evs)
    community: dict[str, list[str]] = dict(boards[0]) if boards else {}

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
                # For EV cashout CoinPoker may leave winAmountFromPot blank;
                # actualWinAmount is the amount really paid to the player.
                preferred = det.get("actualWinAmount") if det.get("isInsured") else det.get("winAmountFromPot")
                amt = _decimal_or_none(preferred)
                if amt is None:
                    amt = _decimal_or_none(w.get("potAmountAfterRake"))
                if nm and amt is not None:
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

    # Bomb pot: every player is forced to ante and the deal jumps straight to a
    # (typically double) board. CoinPoker's bomb pots are always dealt two boards,
    # so an ante paired with a double board is the reliable signal. The stored
    # amount is the total forced antes, in cents.
    splash_pot, mega_splash = _extract_splash(evs)
    cashout = _extract_cashout(evs)
    bomb_pot = int(ante * 100 * len(players)) if ante > 0 and double_board else 0

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
        "timestamp": _hand_start_time(info),
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
        "boards": boards,
        "run_it_times": run_it_times,
        "double_board": double_board,
        "bomb_pot": bomb_pot,
        "splash_pot": splash_pot,
        "mega_splash": mega_splash,
        "cashout": cashout,
        "holecards": holecards,
        "collections": collections,
    }
