#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stable hand serialization for snapshot testing.
Produces deterministic output regardless of database schema changes.

NOTE: v1.0 - Foundation established, ready for refactoring iterations
"""

from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass, asdict, field
from decimal import Decimal
import json

# Import Card module for proper card conversion
try:
    from Card import valueSuitFromCard
except ImportError:
    # Fallback if Card module not available
    def valueSuitFromCard(card_num):
        if card_num is None or card_num == 0:
            return ""
        # Fallback implementation
        suits = ["s", "h", "d", "c"]
        ranks = ["2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K", "A"]
        rank = (card_num - 1) // 4
        suit = (card_num - 1) % 4
        if 0 <= rank < len(ranks) and 0 <= suit < len(suits):
            return ranks[rank] + suits[suit]
        return ""


@dataclass
class SerializedPlayer:
    """Stable representation of a player in a hand."""

    name: str
    seat: int
    stack_start: Optional[float]
    stack_end: Optional[float]
    net_winnings: float
    eff_stack: Optional[float] = None  # Effective stack at hand start (after blinds)
    cards: Optional[List[str]] = None
    position: Optional[str] = None
    # Additional poker stats
    saw_showdown: Optional[bool] = None
    went_all_in: Optional[bool] = None
    street0_vpi: Optional[bool] = None  # Voluntarily Put money In preflop
    rake_paid: Optional[float] = None
    total_profit: Optional[float] = None

    def __post_init__(self):
        # Normalize floats to avoid precision issues
        if self.stack_start is not None:
            self.stack_start = round(float(self.stack_start), 2)
        if self.stack_end is not None:
            self.stack_end = round(float(self.stack_end), 2)
        if self.eff_stack is not None:
            self.eff_stack = round(float(self.eff_stack), 2)
        self.net_winnings = round(float(self.net_winnings), 2)
        if self.rake_paid is not None:
            self.rake_paid = round(float(self.rake_paid), 2)
        if self.total_profit is not None:
            self.total_profit = round(float(self.total_profit), 2)


@dataclass
class SerializedAction:
    """Stable representation of a betting action."""

    street: str  # preflop, flop, turn, river
    player: str
    action: str  # fold, check, call, bet, raise, all-in
    amount: Optional[float] = None

    def __post_init__(self):
        if self.amount is not None:
            self.amount = round(float(self.amount), 2)


@dataclass
class SerializedHand:
    """Stable representation of a poker hand for snapshot testing."""

    # Basic hand info (exclude volatile DB IDs)
    site: str
    hand_text_id: str  # Original hand ID from site
    game_type: str  # e.g., "holdem", "omahahi", "razz", "fivedraw"
    game_variant: str  # e.g., "4-card", "5-card", "6-card" for PLO
    limit_type: str  # e.g., "nl", "pl", "fl"
    stakes: str  # e.g., "$0.05/$0.10", "$25/$50"

    # Timing (normalized)
    datetime_utc: str  # ISO format, normalized to UTC

    # Players and seating
    players: List[SerializedPlayer]
    max_seats: int

    # Betting rounds
    actions: List[SerializedAction]

    # Community cards
    board_cards: Dict[str, List[str]]  # street -> cards

    # Financial summary
    total_pot: float
    rake: float

    # Hand conclusion
    winners: List[str]  # Player names who won
    showdown: bool

    # Additional database fields (optional)
    final_pot: Optional[float] = None  # From Hands.finalPot

    # Pot progression by street (from Hands table)
    street0_pot: Optional[float] = None  # Preflop pot
    street1_pot: Optional[float] = None  # Flop pot
    street2_pot: Optional[float] = None  # Turn pot
    street3_pot: Optional[float] = None  # River pot
    street4_pot: Optional[float] = None  # Showdown pot

    # HandsPots data (collected/returned amounts per player)
    pots_collected: Dict[str, float] = field(default_factory=dict)  # {player: amount_collected}

    # Uncalled bets (calculated from actions)
    uncalled_bets: Dict[str, float] = field(default_factory=dict)  # {player: amount_returned}

    def __post_init__(self):
        # Normalize monetary amounts
        self.total_pot = round(float(self.total_pot), 2)
        self.rake = round(float(self.rake), 2)
        if self.final_pot is not None:
            self.final_pot = round(float(self.final_pot), 2)
        if self.street0_pot is not None:
            self.street0_pot = round(float(self.street0_pot), 2)
        if self.street1_pot is not None:
            self.street1_pot = round(float(self.street1_pot), 2)
        if self.street2_pot is not None:
            self.street2_pot = round(float(self.street2_pot), 2)
        if self.street3_pot is not None:
            self.street3_pot = round(float(self.street3_pot), 2)
        if self.street4_pot is not None:
            self.street4_pot = round(float(self.street4_pot), 2)

        # Normalize pot collections and uncalled bets
        self.pots_collected = {k: round(float(v), 2) for k, v in self.pots_collected.items()}
        self.uncalled_bets = {k: round(float(v), 2) for k, v in self.uncalled_bets.items()}

        # Sort players by seat for deterministic output
        self.players.sort(key=lambda p: p.seat)

        # Sort actions by street order, then chronologically
        street_order = {"preflop": 0, "flop": 1, "turn": 2, "river": 3}
        # Handle both SerializedAction objects and dicts
        self.actions.sort(
            key=lambda a: (
                street_order.get(a.street if hasattr(a, "street") else a.get("street"), 99),
                a.player if hasattr(a, "player") else a.get("player"),
            )
        )


def serialize_hand_for_snapshot(hand) -> Dict[str, Any]:
    """
    Serialize a Hand object to a stable dict for snapshot testing.

    Args:
        hand: A Hand object from FPDB

    Returns:
        Dict containing stable, serializable representation
    """
    # Extract basic hand information
    site = getattr(hand, "sitename", "Unknown")
    hand_id = getattr(hand, "handid", "Unknown")

    # Game type info
    game_type = getattr(hand, "gametype", {})
    limit_type = game_type.get("limitType", "Unknown")
    game_category = game_type.get("category", "Unknown")

    # Determine game variant based on category
    game_variant_map = {
        # Hold'em variants
        "holdem": "hold'em",
        "2_holdem": "short deck hold'em",
        "6_holdem": "6-max hold'em",
        # Omaha variants
        "omahahi": "omaha 4-card",
        "omahahilo": "omaha 4-card hi-lo",
        "5_omahahi": "omaha 5-card",
        "5_omahahilo": "omaha 5-card hi-lo",
        "5_omaha8": "omaha 5-card hi-lo",
        "6_omahahi": "omaha 6-card",
        "6_omahahilo": "omaha 6-card hi-lo",
        "6_omaha8": "omaha 6-card hi-lo",
        # Mixed Hold'em/Omaha variants
        "fusion": "fusion",
        "irish": "irish",
        "cour_hi": "courchevel",
        "cour_hilo": "courchevel hi-lo",
        "aof_omaha": "all-or-fold omaha",
        # Stud variants
        "razz": "razz",
        "studhilo": "7-stud hi-lo",
        "studhi": "7-stud",
        "5_studhi": "5-stud",
        # Draw variants
        "fivedraw": "5-card draw",
        "drawmaha": "draw maha",
        "badugi": "badugi",
        "badacey": "badacey",
        "badeucey": "badeucey",
        "27_razz": "2-7 single draw",
        "27_1draw": "2-7 single draw",
        "27_3draw": "2-7 triple draw",
        "a5_1draw": "a-5 single draw",
        "a5_3draw": "a-5 triple draw",
    }
    game_variant = game_variant_map.get(game_category, "unknown")

    stakes = f"${game_type.get('sb', 0)}/{game_type.get('bb', 0)}"

    # Timing
    datetime_str = str(getattr(hand, "startTime", "Unknown"))

    # Use DIRECT database values from HandsPlayers stats (no calculations!)
    players = []
    players_stats = {}
    if hasattr(hand, "stats"):
        try:
            players_stats = hand.stats.getHandsPlayers()
        except Exception:
            players_stats = {}

    if hasattr(hand, "players"):
        for player_data in hand.players:
            player_name = player_data[1]
            stats = players_stats.get(player_name, {})

            # Use DIRECT database values (all in cents, convert to dollars)
            stack_start_cents = stats.get("startCash", 0)
            stack_start = float(stack_start_cents) / 100.0 if stack_start_cents is not None else None

            total_profit_cents = stats.get("totalProfit", 0)
            total_profit = float(total_profit_cents) / 100.0 if total_profit_cents is not None else None

            # Calculate stack_end from database values
            stack_end = None
            if stack_start is not None and total_profit is not None:
                stack_end = stack_start + total_profit

            # Use DIRECT database winnings (not calculated)
            net_winnings_cents = stats.get("winnings", 0)
            net_winnings = float(net_winnings_cents) / 100.0 if net_winnings_cents is not None else 0.0

            # Use DIRECT database effective stack
            eff_stack_cents = stats.get("effStack", 0)
            eff_stack = float(eff_stack_cents) / 100.0 if eff_stack_cents is not None else None

            # Use DIRECT database rake
            rake_cents = stats.get("rake", 0)
            rake_paid = float(rake_cents) / 100.0 if rake_cents is not None else None

            # Get player cards from database - support for all game types
            player_cards = []

            # Get game category to determine how many cards to fetch
            game_category = game_type.get("category", "holdem")

            # Define card count by game type
            card_counts = {
                # Hold'em variants
                "holdem": 2,  # Texas Hold'em: 2 hole cards
                "2_holdem": 2,  # Short deck Hold'em: 2 hole cards
                "6_holdem": 2,  # 6-max Hold'em: 2 hole cards
                # Omaha variants
                "omahahi": 4,  # PLO 4-card: 4 hole cards
                "omahahilo": 4,  # PLO Hi-Lo 4-card: 4 hole cards
                "5_omahahi": 5,  # PLO 5-card: 5 hole cards
                "5_omahahilo": 5,  # PLO Hi-Lo 5-card: 5 hole cards
                "5_omaha8": 5,  # PLO Hi-Lo 5-card: 5 hole cards (alternative name)
                "6_omahahi": 6,  # PLO 6-card: 6 hole cards
                "6_omahahilo": 6,  # PLO Hi-Lo 6-card: 6 hole cards
                "6_omaha8": 6,  # PLO Hi-Lo 6-card: 6 hole cards (alternative name)
                # Mixed Hold'em/Omaha variants
                "fusion": 4,  # Fusion: starts with 2 cards, +1 after flop finish with 4 like omaha
                "irish": 4,  # Irish: starts with 4 cards, discards 2 after flop
                "cour_hi": 5,  # Courchevel: 5 cards + pre-flop board card
                "cour_hilo": 5,  # Courchevel Hi-Lo: 5 cards + pre-flop board card
                "aof_omaha": 4,  # All-or-Fold Omaha: 4 hole cards
                # Stud variants
                "razz": 7,  # Razz: up to 7 cards
                "studhilo": 7,  # 7-Stud Hi-Lo: up to 7 cards
                "studhi": 7,  # 7-Stud: up to 7 cards
                "5_studhi": 5,  # 5-Stud: up to 5 cards
                # Draw variants
                "fivedraw": 5,  # 5-Card Draw: 5 cards
                "drawmaha": 5,  # Draw Maha: 5 cards
                "badugi": 4,  # Badugi: 4 cards
                "badacey": 7,  # Badacey: 7 cards (Badugi + A-5 lowball)
                "badeucey": 7,  # Badeucey: 7 cards (Badugi + 2-7 lowball)
                "27_razz": 5,  # 2-7 Single Draw: 5 cards
                "27_1draw": 5,  # 2-7 Single Draw: 5 cards
                "27_3draw": 5,  # 2-7 Triple Draw: 5 cards
                "a5_1draw": 5,  # A-5 Single Draw: 5 cards
                "a5_3draw": 5,  # A-5 Triple Draw: 5 cards
            }

            max_cards = card_counts.get(game_category, 2)  # Default to 2 for unknown games

            # Fetch all relevant cards from database
            for i in range(1, max_cards + 1):
                card_value = stats.get(f"card{i}")
                if card_value is not None and card_value > 0:
                    card_str = valueSuitFromCard(card_value)
                    if card_str:
                        player_cards.append(card_str)

            # Only set player_cards if we have valid cards
            if not player_cards:
                player_cards = None

            player = SerializedPlayer(
                name=player_name,
                seat=player_data[0],  # Seat number from hand.players
                stack_start=stack_start,  # DIRECT from database
                stack_end=stack_end,  # Calculated from DB values
                net_winnings=net_winnings,  # DIRECT from database
                eff_stack=eff_stack,  # DIRECT from database
                cards=player_cards,  # DIRECT from database
                position=stats.get("position"),  # DIRECT from database
                saw_showdown=bool(stats.get("sawShowdown", 0)),  # DIRECT from database
                went_all_in=bool(stats.get("wentAllIn", 0)),  # DIRECT from database
                street0_vpi=bool(stats.get("street0VPI", 0)),  # DIRECT from database
                rake_paid=rake_paid,  # DIRECT from database
                total_profit=total_profit,  # DIRECT from database
            )
            players.append(player)

    # Process actions - use handsactions from database to get ALL actions
    actions = []

    # First try to get all actions from hand.handsactions (database source)

    if hasattr(hand, "handsactions") and hand.handsactions:
        # Convert database actions to serialized format - adapt street names by game type
        game_category = game_type.get("category", "holdem")

        # Define street mappings by game type
        if game_category in ["razz", "studhilo", "studhi", "5_studhi"]:
            # Stud games: antes, bring-in, 3rd, 4th, 5th, 6th, 7th street
            street_map = {
                -1: "antes",
                0: "bring_in",
                1: "third_street",
                2: "fourth_street",
                3: "fifth_street",
                4: "sixth_street",
                5: "seventh_street",
            }
        elif game_category in [
            "fivedraw",
            "drawmaha",
            "badugi",
            "badacey",
            "badeucey",
            "27_razz",
            "27_1draw",
            "27_3draw",
            "a5_1draw",
            "a5_3draw",
        ]:
            # Draw games: antes, draw1, draw2, draw3, draw4
            street_map = {-1: "antes", 0: "predraw", 1: "draw_one", 2: "draw_two", 3: "draw_three", 4: "draw_four"}
        else:
            # Hold'em/Omaha/Fusion/Irish/Courchevel: blinds, preflop, flop, turn, river
            street_map = {-1: "blinds", 0: "preflop", 1: "flop", 2: "turn", 3: "river"}
        action_map = {
            1: "ante",
            2: "small blind",
            3: "secondsb",
            4: "big blind",
            5: "both",
            6: "calls",
            7: "raises",
            8: "bets",
            9: "stands pat",
            10: "folds",
            11: "checks",
            12: "discards",
            13: "bringin",
            14: "completes",
            15: "straddle",
            16: "button blind",
            17: "cashout",
        }

        db_actions = []
        for action_id, action_data in hand.handsactions.items():
            street_name = street_map.get(action_data["street"], f"street{action_data['street']}")
            action_name = action_map.get(action_data["actionId"], f"action{action_data['actionId']}")

            # Convert amount from cents to dollars
            amount = None
            if action_data.get("amount") is not None and action_data["amount"] > 0:
                amount = float(action_data["amount"]) / 100.0

            serialized_action = {
                "actionId": action_data["actionId"],
                "actionName": action_map.get(action_data["actionId"], f"unknown_{action_data['actionId']}"),
                "actionNo": action_data["actionNo"],
                "allIn": bool(action_data.get("allIn", False)),
                "amount": int(action_data.get("amount", 0)),  # Keep in cents for snapshot
                "amountCalled": int(action_data.get("amountCalled", 0)),  # Keep in cents
                "cardsDiscarded": action_data.get("cardsDiscarded"),
                "numDiscarded": action_data.get("numDiscarded", 0),
                "player": action_data["player"],
                "raiseTo": int(action_data.get("raiseTo", 0)),  # Keep in cents
                "street": action_data["street"],  # Keep as number for snapshot
                "streetName": street_map.get(action_data["street"], f"street_{action_data['street']}"),
                "streetActionNo": action_data["streetActionNo"],
            }
            db_actions.append(serialized_action)

        # Sort by actionNo to maintain chronological order
        db_actions.sort(key=lambda x: x["actionNo"])
        actions = db_actions

        # IMMEDIATELY save our processed actions before they can be modified
        processed_db_actions = db_actions.copy()

    # Fallback to hand.actions if handsactions not available
    elif hasattr(hand, "actions"):
        for street, street_actions in hand.actions.items():
            for action in street_actions:
                serialized_action = SerializedAction(
                    street=street,
                    player=action[0],  # Player name
                    action=action[1],  # Action type
                    amount=action[2] if len(action) > 2 and action[2] is not None else None,
                )
                actions.append(serialized_action)
        processed_db_actions = None  # No processed actions from DB

    # Process community cards - only for Hold'em/Omaha games
    board_cards = {}
    game_category = game_type.get("category", "holdem")

    # Community cards are relevant for Hold'em, Omaha, and mixed variants
    games_with_board = [
        "holdem", "2_holdem", "6_holdem",  # Hold'em variants
        "omahahi", "omahahilo", "5_omahahi", "5_omahahilo", "5_omaha8",  # Omaha variants
        "6_omahahi", "6_omahahilo", "6_omaha8",
        "fusion", "irish", "cour_hi", "cour_hilo", "aof_omaha"  # Mixed variants
    ]

    if game_category in games_with_board:
        if hasattr(hand, "board"):
            for street, cards in hand.board.items():
                if cards:
                    board_cards[street] = cards
    # For Stud and Draw games, there are typically no community cards
    # Players have individual cards only (already handled in player_cards above)

    # Financial data - use DIRECT database values where available
    total_pot = float(getattr(hand, "totalpot", 0))
    rake = float(getattr(hand, "rake", 0))

    # Get additional pot data from database if available
    final_pot = None
    street_pots = {}
    pots_collected = {}
    uncalled_bets = {}

    # Extract collected amounts from hand.collectees
    if hasattr(hand, "collectees") and hand.collectees:
        for player_name, amount in hand.collectees.items():
            pots_collected[player_name] = float(amount)

    # Get uncalled bets DIRECTLY from HandsActions database via hand.handsactions
    if hasattr(hand, "handsactions"):
        # Build a map of actions by street and order
        street_actions = {}
        for action_id, action_data in hand.handsactions.items():
            street = action_data["street"]
            if street not in street_actions:
                street_actions[street] = []
            street_actions[street].append(action_data)

        # Sort actions by actionNo within each street
        for street in street_actions:
            street_actions[street].sort(key=lambda x: x["actionNo"])

        # Look for uncalled bets: bet followed by smaller all-in call
        for street, actions in street_actions.items():
            for i, action in enumerate(actions):
                if action["actionId"] == 8:  # bets
                    bet_amount = action["amount"] / 100.0  # Convert cents to dollars
                    bet_player = action["player"]

                    # Check if next action is an all-in call for less
                    if i + 1 < len(actions):
                        next_action = actions[i + 1]
                        if (
                            next_action["actionId"] == 6  # calls
                            and next_action["allIn"] == True
                        ):
                            call_amount = next_action["amount"] / 100.0
                            if call_amount < bet_amount:
                                uncalled_amount = bet_amount - call_amount
                                uncalled_bets[bet_player] = uncalled_amount

    if hasattr(hand, "stats"):
        try:
            # Try to get hand-level data from stats
            hands_data = getattr(hand.stats, "getHands", lambda: {})()
            if hands_data:
                final_pot = float(hands_data.get("finalPot", 0)) / 100.0 if hands_data.get("finalPot") else None
                street_pots["street0_pot"] = (
                    float(hands_data.get("street0Pot", 0)) / 100.0 if hands_data.get("street0Pot") else None
                )
                street_pots["street1_pot"] = (
                    float(hands_data.get("street1Pot", 0)) / 100.0 if hands_data.get("street1Pot") else None
                )
                street_pots["street2_pot"] = (
                    float(hands_data.get("street2Pot", 0)) / 100.0 if hands_data.get("street2Pot") else None
                )
                street_pots["street3_pot"] = (
                    float(hands_data.get("street3Pot", 0)) / 100.0 if hands_data.get("street3Pot") else None
                )
                street_pots["street4_pot"] = (
                    float(hands_data.get("street4Pot", 0)) / 100.0 if hands_data.get("street4Pot") else None
                )
        except Exception:
            pass

    # Winners and showdown - use database values instead of hand.pot.contenders
    winners = []
    showdown = False

    # Get real winners from player stats (those with net_winnings > 0)
    for player in players:
        if player.net_winnings > 0:
            winners.append(player.name)

    # Check if there was a showdown (players saw showdown according to database)
    showdown = any(player.saw_showdown for player in players)

    # NOTE: net_winnings are now taken DIRECTLY from database (HandsPlayers.winnings)
    # No need to calculate from collectees/posted - database already has final values

    # Store our processed actions before SerializedHand potentially modifies them
    processed_actions = actions.copy() if isinstance(actions, list) else actions

    # Create the serialized hand (THIS MIGHT MODIFY actions via __post_init__)
    serialized = SerializedHand(
        site=site,
        hand_text_id=str(hand_id),
        game_type=game_category,
        game_variant=game_variant,
        limit_type=limit_type,
        stakes=stakes,
        datetime_utc=datetime_str,
        players=players,
        max_seats=int(getattr(hand, "maxseats", 0)),
        actions=actions,
        board_cards=board_cards,
        total_pot=total_pot,
        rake=rake,
        final_pot=final_pot,
        street0_pot=street_pots.get("street0_pot"),
        street1_pot=street_pots.get("street1_pot"),
        street2_pot=street_pots.get("street2_pot"),
        street3_pot=street_pots.get("street3_pot"),
        street4_pot=street_pots.get("street4_pot"),
        pots_collected=pots_collected,
        uncalled_bets=uncalled_bets,
        winners=list(set(winners)),  # Remove duplicates
        showdown=showdown,
    )

    # Convert to dict and ensure JSON serializable - but handle actions specially
    result = asdict(serialized)

    # Keep database actions in their original dict format (not SerializedAction converted)
    # Use our immediately saved processed_db_actions if available
    if (
        hasattr(hand, "handsactions")
        and hand.handsactions
        and "processed_db_actions" in locals()
        and processed_db_actions
    ):
        result["actions"] = processed_db_actions

    # Ensure all Decimal/float values are converted to float
    def normalize_values(obj):
        if isinstance(obj, dict):
            return {k: normalize_values(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [normalize_values(item) for item in obj]
        elif isinstance(obj, Decimal):
            return float(obj)
        else:
            return obj

    return normalize_values(result)


def serialize_hands_batch(hands: List) -> List[Dict[str, Any]]:
    """
    Serialize multiple hands for batch snapshot testing.

    Args:
        hands: List of Hand objects

    Returns:
        List of serialized hand dicts, sorted by hand_text_id for deterministic output
    """
    serialized_hands = []

    for hand in hands:
        try:
            # Debug: print what we're getting
            print(f"DEBUG: Processing hand {getattr(hand, 'handid', 'Unknown')}")
            print(f"DEBUG: Has handsactions? {hasattr(hand, 'handsactions')}")
            if hasattr(hand, "handsactions"):
                print(f"DEBUG: handsactions count: {len(hand.handsactions) if hand.handsactions else 0}")
            print(f"DEBUG: Has actions? {hasattr(hand, 'actions')}")
            if hasattr(hand, "actions"):
                total_actions = sum(len(street_actions) for street_actions in hand.actions.values())
                print(f"DEBUG: actions count: {total_actions}")
            print(f"DEBUG: Has stats? {hasattr(hand, 'stats')}")

            serialized = serialize_hand_for_snapshot(hand)
            serialized_hands.append(serialized)
        except Exception as e:
            # Add error information for debugging
            import traceback

            print(f"ERROR in serialize_hand_for_snapshot: {e}")
            traceback.print_exc()
            error_hand = {
                "error": str(e),
                "hand_id": getattr(hand, "handid", "Unknown"),
                "site": getattr(hand, "sitename", "Unknown"),
            }
            serialized_hands.append(error_hand)

    # Sort by hand_text_id for deterministic output
    serialized_hands.sort(key=lambda h: h.get("hand_text_id", h.get("hand_id", "")))

    return serialized_hands


def verify_hand_invariants(serialized_hand: Dict[str, Any]) -> List[str]:
    """
    Verify basic poker hand invariants on serialized hand data.

    Args:
        serialized_hand: Dict from serialize_hand_for_snapshot

    Returns:
        List of invariant violations (empty if all good)
    """
    violations = []

    # Check basic structure
    required_keys = ["site", "hand_text_id", "players", "total_pot", "rake"]
    for key in required_keys:
        if key not in serialized_hand:
            violations.append(f"Missing required key: {key}")

    if violations:  # Don't continue if basic structure is broken
        return violations

    players = serialized_hand["players"]
    total_pot = serialized_hand["total_pot"]
    rake = serialized_hand["rake"]

    # Invariant 1: Each player has unique seat
    seats = [p["seat"] for p in players]
    if len(seats) != len(set(seats)):
        violations.append("Players do not have unique seats")

    # Invariant 2: Total winnings + rake should equal total pot
    total_winnings = sum(p["net_winnings"] for p in players)
    if abs(total_winnings + rake - total_pot) > 0.01:  # Allow for rounding
        violations.append(f"Money conservation failed: winnings({total_winnings}) + rake({rake}) != pot({total_pot})")

    # Invariant 3: Rake should not be negative
    if rake < 0:
        violations.append(f"Negative rake: {rake}")

    # Invariant 4: At least one winner if pot > 0
    if total_pot > 0:
        winners = [p["name"] for p in players if p["net_winnings"] > 0]
        if not winners:
            violations.append("No winners despite non-zero pot")

    # Invariant 5: Seat numbers should be reasonable
    max_seats = serialized_hand.get("max_seats", 10)
    for player in players:
        if player["seat"] < 1 or player["seat"] > max_seats:
            violations.append(f"Invalid seat number {player['seat']} for {player['name']}")

    return violations


if __name__ == "__main__":
    # Example usage
    import sys

    print("This module provides hand serialization for snapshot testing.")
    print("Use serialize_hand_for_snapshot(hand) to serialize a single hand.")
    print("Use serialize_hands_batch(hands) to serialize multiple hands.")
    print("Use verify_hand_invariants(serialized) to check poker invariants.")
