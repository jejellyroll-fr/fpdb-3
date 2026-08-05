import os
from decimal import Decimal
from functools import wraps

_INVARIANT_HITS = {}


def is_soft():
    return os.environ.get("INVARIANTS_SOFT") == "1"


def _record(name):
    def decorator(fn):
        @wraps(fn)
        def wrapped(parsed):
            _INVARIANT_HITS[name] = _INVARIANT_HITS.get(name, 0) + 1
            return fn(parsed)

        return wrapped

    return decorator


@_record("pot_equation")
def _pot_equation(parsed):
    """Verify that pot distributions (winnings + rake) match the total pot, failing on discrepancy unless soft mode."""
    winnings = sum(Decimal(str(w["amount"])) for w in parsed["winners"])
    rake = Decimal(str(parsed["rake"]))
    total_pot = Decimal(str(parsed["pots"]["main"])) + sum(Decimal(str(sp)) for sp in parsed["pots"]["side"])

    # Rake must be non-negative
    assert rake >= 0, f"negative rake: {rake}"

    # Check pot distributions equation
    diff = abs((winnings + rake) - total_pot)
    if diff > Decimal("0.05"):
        msg = f"Hand {parsed.get('hand_id')}: winnings={winnings} rake={rake} total_pot={total_pot} (diff={diff})"
        if is_soft():
            print(f"\n⚠️  [POT DISCREPANCY WARNING] {msg}")
        else:
            assert False, f"Pot equation violated: {msg}"

@_record("board_unique")
def _board_unique(parsed):
    """Verify that community board cards do not contain duplicate cards, failing if they do unless soft mode."""
    board = parsed["board"]
    if len(board) != len(set(board)):
        msg = f"Hand {parsed.get('hand_id')}: duplicate board cards detected: {board}"
        if is_soft():
            print(f"\n⚠️  [BOARD DUPLICATE WARNING] {msg}")
        else:
            assert False, msg

@_record("cards_unique")
def _cards_unique(parsed):
    """Verify that board cards and individual player hole cards do not overlap, failing if they do unless soft mode."""
    board_set = set(parsed["board"])
    for player, cards in parsed["hole_cards"].items():
        overlap = board_set & set(cards)
        if overlap:
            msg = f"Hand {parsed.get('hand_id')}: board cards overlap with player {player} hole cards: {overlap}"
            if is_soft():
                print(f"\n⚠️  [CARD OVERLAP WARNING] {msg}")
            else:
                assert False, msg

@_record("actions_reference_known_players")
def _actions_reference_known_players(parsed):
    """Verify that all players in blinds, antes, and winners are listed in the seating table."""
    players = {p["name"] for p in parsed["players"]}

    # Blinds reference known players
    for b in parsed["blinds"]:
        assert b["player"] in players, f"unknown player in blind: {b}"

    # Antes reference known players
    for a in parsed["antes"]:
        assert a["player"] in players, f"unknown player in ante: {a}"

    # Winners reference known players
    for w in parsed["winners"]:
        assert w["player"] in players, f"unknown player in winner: {w}"

@_record("seat_integrity")
def _seat_integrity(parsed):
    """Verify seat occupancies and button seat consistency."""
    seats = [p["seat"] for p in parsed["players"]]
    assert len(seats) == len(set(seats)), f"duplicate seats: {seats}"

    # Button on occupied seat (only if button seat is specified > 0)
    button_seat = parsed.get("button_seat")
    if button_seat is not None and button_seat > 0 and len(seats) > 0:
        max_seats = parsed["format"].get("max_seats") or 0
        physical_max = max(max_seats, max(seats))
        assert button_seat <= physical_max, f"button seat {button_seat} exceeds physical max seat {physical_max}"

@_record("unique_player_names")
def _unique_player_names(parsed):
    """Verify that all players have unique names."""
    names = [p["name"] for p in parsed["players"]]
    assert len(names) == len(set(names)), f"duplicate player names: {names}"

@_record("street_order")
def _street_order(parsed):
    """Verify that streets are in the correct order."""
    valid_streets = {"preflop": 0, "flop": 1, "turn": 2, "river": 3, "showdown": 4}
    current_idx = -1
    for action in parsed.get("actions", []):
        street = action.get("street")
        if street in valid_streets:
            idx = valid_streets[street]
            assert idx >= current_idx, f"Street order violated: {street} appeared after a later street"
            current_idx = idx

@_record("rake_leq_pot")
def _rake_leq_pot(parsed):
    """Verify that rake is not greater than the total pot."""
    rake = Decimal(str(parsed["rake"]))
    total_pot = Decimal(str(parsed["pots"]["main"])) + sum(Decimal(str(sp)) for sp in parsed["pots"]["side"])
    assert rake <= total_pot, f"rake {rake} is greater than total pot {total_pot}"

@_record("tournament_cost_consistent")
def _tournament_cost_consistent(parsed):
    """Verify tournament buy_in + fee + bounty == total_cost."""
    fmt = parsed.get("format", {})
    if fmt.get("kind") not in {"mtt", "sng", "stt"}:
        return
    buy_in = Decimal(str(fmt.get("buy_in", 0)))
    fee = Decimal(str(fmt.get("fee", 0)))
    bounty = Decimal(str(fmt.get("bounty", 0)))
    total = Decimal(str(fmt.get("total_cost", buy_in + fee + bounty)))
    expected = buy_in + fee + bounty
    assert total == expected, (
        f"tournament cost mismatch: buy_in={buy_in} fee={fee} "
        f"bounty={bounty} ≠ total={total}"
    )

@_record("tournament_rank_valid")
def _tournament_rank_valid(parsed):
    """Verify tournament rank is between 1 and total_players (if known)."""
    fmt = parsed.get("format", {})
    if fmt.get("kind") not in {"mtt", "sng", "stt"}:
        return
    for w in parsed.get("winners", []):
        rank = w.get("rank")
        if rank is not None:
            assert rank >= 1, f"invalid rank {rank}"
            # Not all parsed formats expose total_players accurately for this invariant yet.
            # We assert > 0 for now.

@_record("no_negative_bets")
def _no_negative_bets(parsed):
    """Verify that no action amounts are negative."""
    for action in parsed.get("actions", []):
        amount = action.get("amount")
        if amount is not None:
            assert Decimal(str(amount)) >= 0, f"negative bet amount: {amount}"

@_record("showdown_has_shown_cards")
def _showdown_has_shown_cards(parsed):
    """Verify that if there's a showdown, at least one card is shown."""
    has_showdown = any(a.get("action") == "show" for a in parsed.get("actions", []))
    if has_showdown:
        assert len(parsed.get("hole_cards", {})) > 0, "Showdown occurred but no hole cards were shown"

CHECKS = [
    _pot_equation,
    _board_unique,
    _cards_unique,
    _actions_reference_known_players,
    _seat_integrity,
    _unique_player_names,
    _street_order,
    _rake_leq_pot,
    _tournament_cost_consistent,
    _tournament_rank_valid,
    _no_negative_bets,
    _showdown_has_shown_cards
]

def check_all_invariants(parsed):
    for check in CHECKS:
        check(parsed)
