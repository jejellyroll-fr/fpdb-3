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
    game_type: str     # e.g., "NLHE", "PLO", "FLHE"
    limit_type: str    # e.g., "nl", "pl", "fl"
    stakes: str        # e.g., "$0.05/$0.10", "$25/$50"
    
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
    final_pot: Optional[float] = None   # From Hands.finalPot
    
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
        self.actions.sort(key=lambda a: (
            street_order.get(a.street if hasattr(a, 'street') else a.get('street'), 99),
            a.player if hasattr(a, 'player') else a.get('player')
        ))


def serialize_hand_for_snapshot(hand) -> Dict[str, Any]:
    """
    Serialize a Hand object to a stable dict for snapshot testing.
    
    Args:
        hand: A Hand object from FPDB
        
    Returns:
        Dict containing stable, serializable representation
    """
    # Extract basic hand information
    site = getattr(hand, 'sitename', 'Unknown')
    hand_id = getattr(hand, 'handid', 'Unknown')
    
    # Game type info
    game_type = getattr(hand, 'gametype', {})
    limit_type = game_type.get('limitType', 'Unknown')
    game_name = game_type.get('category', 'Unknown') 
    stakes = f"${game_type.get('sb', 0)}/{game_type.get('bb', 0)}"
    
    # Timing
    datetime_str = str(getattr(hand, 'startTime', 'Unknown'))
    
    # Use DIRECT database values from HandsPlayers stats (no calculations!)
    players = []
    players_stats = {}
    if hasattr(hand, 'stats'):
        try:
            players_stats = hand.stats.getHandsPlayers()
        except Exception:
            players_stats = {}
    
    if hasattr(hand, 'players'):
        for player_data in hand.players:
            player_name = player_data[1]
            stats = players_stats.get(player_name, {})
            
            # Use DIRECT database values (all in cents, convert to dollars)
            stack_start_cents = stats.get('startCash', 0)
            stack_start = float(stack_start_cents) / 100.0 if stack_start_cents is not None else None
            
            total_profit_cents = stats.get('totalProfit', 0) 
            total_profit = float(total_profit_cents) / 100.0 if total_profit_cents is not None else None
            
            # Calculate stack_end from database values  
            stack_end = None
            if stack_start is not None and total_profit is not None:
                stack_end = stack_start + total_profit
            
            # Use DIRECT database winnings (not calculated)
            net_winnings_cents = stats.get('winnings', 0)
            net_winnings = float(net_winnings_cents) / 100.0 if net_winnings_cents is not None else 0.0
            
            # Use DIRECT database effective stack
            eff_stack_cents = stats.get('effStack', 0)
            eff_stack = float(eff_stack_cents) / 100.0 if eff_stack_cents is not None else None
            
            # Use DIRECT database rake
            rake_cents = stats.get('rake', 0)
            rake_paid = float(rake_cents) / 100.0 if rake_cents is not None else None
            
            player = SerializedPlayer(
                name=player_name,
                seat=player_data[0],   # Seat number from hand.players
                stack_start=stack_start,    # DIRECT from database
                stack_end=stack_end,        # Calculated from DB values
                net_winnings=net_winnings,  # DIRECT from database
                eff_stack=eff_stack,        # DIRECT from database  
                cards=None,  # Will be filled if available
                position=stats.get('position'),      # DIRECT from database
                saw_showdown=bool(stats.get('sawShowdown', 0)),     # DIRECT from database
                went_all_in=bool(stats.get('wentAllIn', 0)),        # DIRECT from database
                street0_vpi=bool(stats.get('street0VPI', 0)),       # DIRECT from database
                rake_paid=rake_paid,        # DIRECT from database
                total_profit=total_profit,  # DIRECT from database
            )
            players.append(player)
    
    # Process actions
    actions = []
    if hasattr(hand, 'actions'):
        for street, street_actions in hand.actions.items():
            for action in street_actions:
                serialized_action = SerializedAction(
                    street=street,
                    player=action[0],  # Player name
                    action=action[1],  # Action type
                    amount=action[2] if len(action) > 2 and action[2] is not None else None
                )
                actions.append(serialized_action)
    
    # Process community cards
    board_cards = {}
    if hasattr(hand, 'board'):
        for street, cards in hand.board.items():
            if cards:
                board_cards[street] = cards
    
    # Financial data - use DIRECT database values where available
    total_pot = float(getattr(hand, 'totalpot', 0))
    rake = float(getattr(hand, 'rake', 0))
    
    # Get additional pot data from database if available
    final_pot = None
    street_pots = {}
    pots_collected = {}
    uncalled_bets = {}
    
    # Extract collected amounts from hand.collectees  
    if hasattr(hand, 'collectees') and hand.collectees:
        for player_name, amount in hand.collectees.items():
            pots_collected[player_name] = float(amount)
    
    # Get uncalled bets DIRECTLY from HandsActions database via hand.handsactions
    if hasattr(hand, 'handsactions'):
        # Build a map of actions by street and order
        street_actions = {}
        for action_id, action_data in hand.handsactions.items():
            street = action_data['street']
            if street not in street_actions:
                street_actions[street] = []
            street_actions[street].append(action_data)
        
        # Sort actions by actionNo within each street
        for street in street_actions:
            street_actions[street].sort(key=lambda x: x['actionNo'])
        
        # Look for uncalled bets: bet followed by smaller all-in call
        for street, actions in street_actions.items():
            for i, action in enumerate(actions):
                if action['actionId'] == 8:  # bets
                    bet_amount = action['amount'] / 100.0  # Convert cents to dollars
                    bet_player = action['player']
                    
                    # Check if next action is an all-in call for less
                    if i + 1 < len(actions):
                        next_action = actions[i + 1]
                        if (next_action['actionId'] == 6 and  # calls
                            next_action['allIn'] == True):
                            call_amount = next_action['amount'] / 100.0
                            if call_amount < bet_amount:
                                uncalled_amount = bet_amount - call_amount
                                uncalled_bets[bet_player] = uncalled_amount
    
    if hasattr(hand, 'stats'):
        try:
            # Try to get hand-level data from stats
            hands_data = getattr(hand.stats, 'getHands', lambda: {})()
            if hands_data:
                final_pot = float(hands_data.get('finalPot', 0)) / 100.0 if hands_data.get('finalPot') else None
                street_pots['street0_pot'] = float(hands_data.get('street0Pot', 0)) / 100.0 if hands_data.get('street0Pot') else None
                street_pots['street1_pot'] = float(hands_data.get('street1Pot', 0)) / 100.0 if hands_data.get('street1Pot') else None  
                street_pots['street2_pot'] = float(hands_data.get('street2Pot', 0)) / 100.0 if hands_data.get('street2Pot') else None
                street_pots['street3_pot'] = float(hands_data.get('street3Pot', 0)) / 100.0 if hands_data.get('street3Pot') else None
                street_pots['street4_pot'] = float(hands_data.get('street4Pot', 0)) / 100.0 if hands_data.get('street4Pot') else None
        except Exception:
            pass
    
    # Winners and showdown
    winners = []
    showdown = False
    if hasattr(hand, 'pot') and hasattr(hand.pot, 'contenders'):
        # Extract winners from pot contenders
        if isinstance(hand.pot.contenders, set):
            # contenders is a set of player names (simple case)
            winners = list(hand.pot.contenders)
        elif isinstance(hand.pot.contenders, (list, tuple)):
            # contenders is a list/tuple of dicts or objects
            for side_pot in hand.pot.contenders:
                if isinstance(side_pot, dict):
                    for player, amount in side_pot.items():
                        if amount > 0:
                            winners.append(player)
                else:
                    # Handle other formats
                    winners.append(str(side_pot))
        showdown = len(winners) > 1 or hasattr(hand, 'shown')
    
    # NOTE: net_winnings are now taken DIRECTLY from database (HandsPlayers.winnings)
    # No need to calculate from collectees/posted - database already has final values
    
    # Create the serialized hand
    serialized = SerializedHand(
        site=site,
        hand_text_id=str(hand_id),
        game_type=game_name,
        limit_type=limit_type,
        stakes=stakes,
        datetime_utc=datetime_str,
        players=players,
        max_seats=int(getattr(hand, 'maxseats', 0)),
        actions=actions,
        board_cards=board_cards,
        total_pot=total_pot,
        rake=rake,
        final_pot=final_pot,
        street0_pot=street_pots.get('street0_pot'),
        street1_pot=street_pots.get('street1_pot'),
        street2_pot=street_pots.get('street2_pot'),
        street3_pot=street_pots.get('street3_pot'),
        street4_pot=street_pots.get('street4_pot'),
        pots_collected=pots_collected,
        uncalled_bets=uncalled_bets,
        winners=list(set(winners)),  # Remove duplicates
        showdown=showdown,
    )
    
    # Convert to dict and ensure JSON serializable
    result = asdict(serialized)
    
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
            serialized = serialize_hand_for_snapshot(hand)
            serialized_hands.append(serialized)
        except Exception as e:
            # Add error information for debugging
            error_hand = {
                'error': str(e),
                'hand_id': getattr(hand, 'handid', 'Unknown'),
                'site': getattr(hand, 'sitename', 'Unknown'),
            }
            serialized_hands.append(error_hand)
    
    # Sort by hand_text_id for deterministic output
    serialized_hands.sort(key=lambda h: h.get('hand_text_id', h.get('hand_id', '')))
    
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
    required_keys = ['site', 'hand_text_id', 'players', 'total_pot', 'rake']
    for key in required_keys:
        if key not in serialized_hand:
            violations.append(f"Missing required key: {key}")
    
    if violations:  # Don't continue if basic structure is broken
        return violations
    
    players = serialized_hand['players']
    total_pot = serialized_hand['total_pot']
    rake = serialized_hand['rake']
    
    # Invariant 1: Each player has unique seat
    seats = [p['seat'] for p in players]
    if len(seats) != len(set(seats)):
        violations.append("Players do not have unique seats")
    
    # Invariant 2: Total winnings + rake should equal total pot
    total_winnings = sum(p['net_winnings'] for p in players)
    if abs(total_winnings + rake - total_pot) > 0.01:  # Allow for rounding
        violations.append(f"Money conservation failed: winnings({total_winnings}) + rake({rake}) != pot({total_pot})")
    
    # Invariant 3: Rake should not be negative
    if rake < 0:
        violations.append(f"Negative rake: {rake}")
    
    # Invariant 4: At least one winner if pot > 0
    if total_pot > 0:
        winners = [p['name'] for p in players if p['net_winnings'] > 0]
        if not winners:
            violations.append("No winners despite non-zero pot")
    
    # Invariant 5: Seat numbers should be reasonable
    max_seats = serialized_hand.get('max_seats', 10)
    for player in players:
        if player['seat'] < 1 or player['seat'] > max_seats:
            violations.append(f"Invalid seat number {player['seat']} for {player['name']}")
    
    return violations


if __name__ == "__main__":
    # Example usage
    import sys
    print("This module provides hand serialization for snapshot testing.")
    print("Use serialize_hand_for_snapshot(hand) to serialize a single hand.")
    print("Use serialize_hands_batch(hands) to serialize multiple hands.")
    print("Use verify_hand_invariants(serialized) to check poker invariants.")