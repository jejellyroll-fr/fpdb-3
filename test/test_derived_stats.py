import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from decimal import Decimal
from DerivedStats import DerivedStats  
from Hand import HoldemOmahaHand
import Hand

class MockConfig:
    def get_import_parameters(self):
        return {'saveActions': True}  

    def get_site_id(self, sitename):
        return 1

@pytest.fixture
def hand():
    config_mock = MockConfig()

    gametype = {
        'base': 'hold',
        'category': 'holdem',
        'limitType': 'nl',
        'sb': '10',
        'bb': '20',
        'currency': 'EUR'
    }
    # Creation of a simulated Hand object with specific actions
    hand = HoldemOmahaHand(
        config_mock, 
        None, 
        "Winamax", 
        gametype, 
        "", 
        builtFrom="Test"
    )
    hand.players = [[1, 'Player1', '10000', 'B', None], [2, 'Player2', '10000', 'S', None]]
    hand.dbid_pids = {'Player1': 1, 'Player2': 2}
    hand.hero = 'Player1'

    # Simulated postflop actions
    hand.actions = {
        'BLINDSANTES': [
            ('Player1', 'big blind', Decimal('20'), False),
            ('Player2', 'small blind', Decimal('10'), False)
        ],
        'PREFLOP': [
            ('Player2', 'raises', Decimal('40'), Decimal('60'), Decimal('20'), False),
            ('Player1', 'calls', Decimal('40'), False)
        ],
        'FLOP': [
            ('Player1', 'checks'),
            ('Player2', 'bets', Decimal('50'), False),
            ('Player1', 'calls', Decimal('50'), False)
        ],
        'TURN': [
            ('Player1', 'bets', Decimal('100'), False),
            ('Player2', 'raises', Decimal('200'), Decimal('300'), Decimal('100'), False),
            ('Player1', 'calls', Decimal('200'), False)
        ],
        'RIVER': [
            ('Player1', 'checks'),
            ('Player2', 'checks')
        ]
    }
    hand.actionStreets = ['BLINDSANTES', 'PREFLOP', 'FLOP', 'TURN', 'RIVER']
    return hand

@pytest.fixture
def stats_calculator():
    return DerivedStats()

def test_action_counters(hand, stats_calculator):
    # Main call that fills stats_calculator.handsplayers
    stats_calculator.getStats(hand)
    player1_stats = stats_calculator.handsplayers['Player1']
    player2_stats = stats_calculator.handsplayers['Player2']

    # Flop checks (street 1)
    assert player1_stats.get('street1Calls', 0) == 1, "Player1 Flop Calls"
    assert not player1_stats.get('street1Aggr', False), "Player1 Flop Aggression"
    assert player2_stats.get('street1Bets', 0) == 1, "Player2 Flop Bets"
    assert player2_stats.get('street1Aggr', False), "Player2 Flop Aggression"

    # Checks for the Turn (street 2)
    assert player1_stats.get('street2Bets', 0) == 1, "Player1 Turn Bets"
    assert player1_stats.get('street2Aggr', False), "Player1 Turn Aggression"
    assert player1_stats.get('street2Calls', 0) == 1, "Player1 Turn Calls"
    assert player2_stats.get('street2Raises', 0) == 1, "Player2 Turn Raises"
    assert player2_stats.get('street2Aggr', False), "Player2 Turn Aggression"

    # Checks for the River (street 3)
    assert player1_stats.get('street3Calls', 0) == 0, "Player1 River Calls"
    assert not player1_stats.get('street3Aggr', False), "Player1 River Aggression"
    assert player2_stats.get('street3Calls', 0) == 0, "Player2 River Calls"
    assert not player2_stats.get('street3Aggr', False), "Player2 River Aggression"




def test_continuation_bet_flop(stats_calculator):
    """Test the calculation of the CBet on the Flop."""
    config_mock = MockConfig()
    gametype = {'base': 'hold', 'category': 'holdem', 'limitType': 'nl', 'sb': '10', 'bb': '20', 'currency': 'EUR'}
    hand_cbet = HoldemOmahaHand(config_mock, None, "Winamax", gametype, "", builtFrom="Test")
    hand_cbet.players = [[1, 'Player1', '10000', 'S', None], [2, 'Player2', '10000', 'B', None]] # P1 on Bouton/CO, P2 on BB
    hand_cbet.dbid_pids = {'Player1': 1, 'Player2': 2}
    hand_cbet.hero = 'Player1' 

    # Player1 raise preflop, Player2 calls
    hand_cbet.actions = {
        'BLINDSANTES': [('Player1', 'small blind', Decimal('10'), False), ('Player2', 'big blind', Decimal('20'), False)],
        'PREFLOP': [('Player1', 'raises', Decimal('40'), Decimal('60'), Decimal('20'), False), ('Player2', 'calls', Decimal('40'), False)],
        'FLOP': [('Player2', 'checks'), ('Player1', 'bets', Decimal('50'), False), ('Player2', 'folds')], # P1 CBet Flop
        'TURN': [],
        'RIVER': []
    }
    hand_cbet.actionStreets = ['BLINDSANTES', 'PREFLOP', 'FLOP', 'TURN', 'RIVER']

    stats_calculator.getStats(hand_cbet)
    player1_stats = stats_calculator.handsplayers['Player1']
    player2_stats = stats_calculator.handsplayers['Player2']

    # Player1 (Agressor Preflop)
    assert player1_stats.get('street1CBChance', False), "Player1 should have CBet chance on Flop"
    assert player1_stats.get('street1CBDone', False), "Player1 should have made a CBet on Flop"

    # Player2 (preflop caller)
    assert not player2_stats.get('street1CBChance', False), "Player2 should not have CBet chance on Flop"
    assert not player2_stats.get('street1CBDone', False), "Player2 did not make a CBet on Flop"

    assert player2_stats.get('foldToStreet1CBChance', False), "Player2 should face a CBet chance on Flop"
    assert player2_stats.get('foldToStreet1CBDone', True), "Player2 should have folded to CBet on Flop"




def test_check_raise_flop(stats_calculator):
    """Test the calculation of the Check-Raise on the Flop."""
    config_mock = MockConfig()
    gametype = {'base': 'hold', 'category': 'holdem', 'limitType': 'nl', 'sb': '10', 'bb': '20', 'currency': 'EUR'}
    hand_cr = HoldemOmahaHand(config_mock, None, "Winamax", gametype, "", builtFrom="Test")
    # P1 SB, P2 BB/Agressor Preflop
    hand_cr.players = [[1, 'Player1', '10000', 'S', None], [2, 'Player2', '10000', 'B', None]]
    hand_cr.dbid_pids = {'Player1': 1, 'Player2': 2}
    hand_cr.hero = 'Player1'

    # Player1 calls, Player2 checks BB preflop.
    hand_cr.actions = {
        'BLINDSANTES': [('Player1', 'small blind', Decimal('10'), False), ('Player2', 'big blind', Decimal('20'), False)],
        'PREFLOP': [('Player1', 'calls', Decimal('10'), False), ('Player2', 'checks')],
        'FLOP': [('Player1', 'checks'), ('Player2', 'bets', Decimal('30'), False), ('Player1', 'raises', Decimal('70'), Decimal('100'), Decimal('30'), False)], # P1 Check-Raise Flop
        'TURN': [],
        'RIVER': []
    }
    hand_cr.actionStreets = ['BLINDSANTES', 'PREFLOP', 'FLOP', 'TURN', 'RIVER']

    stats_calculator.getStats(hand_cr)
    player1_stats = stats_calculator.handsplayers['Player1']
    player2_stats = stats_calculator.handsplayers['Player2']

    # Player1 (those whose Check-Raise)
    assert player1_stats.get('street1CheckCallRaiseChance', False), "Player1 should have Check-Raise chance on Flop"
    assert not player1_stats.get('street1CheckCallDone', False), "Player1 did not Check-Call on Flop"
    assert player1_stats.get('street1CheckRaiseDone', False), "Player1 should have Check-Raised on Flop"

    # Player2 (those who Bet)
    assert not player2_stats.get('street1CheckCallRaiseChance', False), "Player2 did not Check, so no CR chance"



def test_allin_flag_set(stats_calculator):
    """Check that the streetXAllIn flag is set correctly."""
    config_mock = MockConfig()
    gametype = {'base': 'hold', 'category': 'holdem', 'limitType': 'nl', 'sb': '10', 'bb': '20', 'currency': 'EUR'}
    hand_allin = HoldemOmahaHand(config_mock, None, "Winamax", gametype, "", builtFrom="Test")
    hand_allin.players = [[1, 'Player1', '100', 'B', None], [2, 'Player2', '100', 'S', None]]
    hand_allin.dbid_pids = {'Player1': 1, 'Player2': 2}
    hand_allin.hero = 'Player1'
    hand_allin.actions = {
        'BLINDSANTES': [('Player1', 'big blind', Decimal('20'), False), ('Player2', 'small blind', Decimal('10'), False)],
        'PREFLOP': [('Player2', 'calls', Decimal('10'), False), ('Player1', 'raises', Decimal('60'), Decimal('80'), Decimal('20'), False)],
        'FLOP': [('Player1', 'bets', Decimal('20'), True)], # Player1 all-in on the Flop (street1)
        'TURN': [],
        'RIVER': []
    }
    hand_allin.actionStreets = ['BLINDSANTES', 'PREFLOP', 'FLOP', 'TURN', 'RIVER']

    stats_calculator.getStats(hand_allin)
    player1_stats = stats_calculator.handsplayers['Player1']
    player2_stats = stats_calculator.handsplayers['Player2']

    assert player1_stats.get('street1AllIn', False), "Player1 Flop AllIn flag should be True"
    assert not player2_stats.get('street1AllIn', False), "Player2 Flop AllIn flag should be False"
    assert not player1_stats.get('street2AllIn', False), "Player1 Turn AllIn flag should be False" # Check another street

def test_discard_counter(stats_calculator):
    """Check that the streetXDiscards counter is working (Draw Game)."""
    config_mock = MockConfig()
    # Simulate a Draw game
    gametype = {'base': 'draw', 'category': '27_3draw', 'limitType': 'fl', 'sb': '10', 'bb': '20', 'currency': 'EUR'}
    hand_draw = Hand.DrawHand(config_mock, None, "Winamax", gametype, "", builtFrom="Test") 
    hand_draw.players = [[1, 'Player1', '10000', 'B', None], [2, 'Player2', '10000', 'S', None]]
    hand_draw.dbid_pids = {'Player1': 1, 'Player2': 2}
    hand_draw.hero = 'Player1'
    # Add draw streets
    hand_draw.actionStreets = ['BLINDSANTES', 'DEAL', 'DRAWONE', 'DRAWTWO', 'DRAWTHREE'] 

    hand_draw.actions = {
        'BLINDSANTES': [],
        'DEAL': [('Player1', 'bets', Decimal('20'), False), ('Player2', 'calls', Decimal('20'), False)],
        'DRAWONE': [('Player1', 'discards', 2), ('Player2', 'stands pat')], # Street 1 = DRAWONE
        'DRAWTWO': [('Player1', 'bets', Decimal('40'), False), ('Player2', 'calls', Decimal('40'), False)], # Street 2 = DRAWTWO
        'DRAWTHREE': [('Player1', 'stands pat'), ('Player2', 'discards', 1)] # Street 3 = DRAWTHREE
    }


    stats_calculator.getStats(hand_draw)
    player1_stats = stats_calculator.handsplayers['Player1']
    player2_stats = stats_calculator.handsplayers['Player2']

    # Player1 discards 2 cards to DRAWONE (street 1)
    assert player1_stats.get('street1Discards', 0) == 2, "Player1 should have discarded 2 cards on DRAWONE"
    assert player1_stats.get('street2Discards', 0) == 0, "Player1 should have 0 discard actions on DRAWTWO"
    assert player1_stats.get('street3Discards', 0) == 0, "Player1 should have 0 discard actions on DRAWTHREE"

    # Player2 discards 1 card on DRAWTHREE (street 3)
    assert player2_stats.get('street1Discards', 0) == 0, "Player2 should have 0 discard actions on DRAWONE"
    assert player2_stats.get('street2Discards', 0) == 0, "Player2 should have 0 discard actions on DRAWTWO"
    assert player2_stats.get('street3Discards', 0) == 1, "Player2 should have discarded 1 card on DRAWTHREE"


def test_aggression_flag_logic(stats_calculator):
    """Checks the logic of the streetXAggr flag."""
    config_mock = MockConfig()
    gametype = {'base': 'hold', 'category': 'holdem', 'limitType': 'nl', 'sb': '10', 'bb': '20', 'currency': 'EUR'}
    hand_aggr = HoldemOmahaHand(config_mock, None, "Winamax", gametype, "", builtFrom="Test")
    hand_aggr.players = [[1, 'Player1', '10000', 'B', None], [2, 'Player2', '10000', 'S', None]]
    hand_aggr.dbid_pids = {'Player1': 1, 'Player2': 2}
    hand_aggr.hero = 'Player1'
    hand_aggr.actions = {
        'BLINDSANTES': [('Player1', 'big blind', Decimal('20'), False), ('Player2', 'small blind', Decimal('10'), False)],
        'PREFLOP': [('Player2', 'calls', Decimal('10'), False), ('Player1', 'checks')],
        'FLOP': [('Player1', 'bets', Decimal('30'), False), ('Player2', 'calls', Decimal('30'), False), ('Player1', 'checks')], # P1 Bet then Check Flop
        'TURN': [('Player2', 'checks'), ('Player1', 'raises', Decimal('60'), Decimal('90'), Decimal('30'), False), ('Player2', 'folds')], # P1 Raise then P2 Fold Turn
        'RIVER': []
    }
    hand_aggr.actionStreets = ['BLINDSANTES', 'PREFLOP', 'FLOP', 'TURN', 'RIVER']

    stats_calculator.getStats(hand_aggr)
    player1_stats = stats_calculator.handsplayers['Player1']
    player2_stats = stats_calculator.handsplayers['Player2']

    # Flop (Street 1): Player1 bet, even though he checked later
    assert player1_stats.get('street1Aggr', False), "Player1 Flop Aggression should be True (due to bet)"
    # Turn (Street 2): Player1  raise
    assert player1_stats.get('street2Aggr', False), "Player1 Turn Aggression should be True (due to raise)"
    # River (Street 3): No aggressive action
    assert not player1_stats.get('street3Aggr', False), "Player1 River Aggression should be False"

    # Flop (Street 1): Player2 just call
    assert not player2_stats.get('street1Aggr', False), "Player2 Flop Aggression should be False"
    # Turn (Street 2): Player2 fold
    assert not player2_stats.get('street2Aggr', False), "Player2 Turn Aggression should be False"