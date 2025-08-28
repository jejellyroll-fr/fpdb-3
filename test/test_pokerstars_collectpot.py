"""Comprehensive tests for PokerStars readCollectPot functionality."""

import pytest
from unittest.mock import Mock, MagicMock
from decimal import Decimal
import re

from PokerStarsToFpdb import PokerStars


class MockConfig:
    """Mock configuration for testing."""

    def get_import_parameters(self) -> dict:
        """Return import parameters for testing."""
        return {
            "saveActions": True, 
            "callFpdbHud": False, 
            "cacheSessions": False, 
            "publicDB": False,
            "importFilters": ["holdem", "omahahi", "omahahilo", "studhi", "studlo", "razz", "27_1draw", "27_3draw", "fivedraw", "badugi", "baduci"],
            "handCount": 0,
            "fastFold": False
        }

    def get_site_id(self, sitename: str) -> int:
        """Return the site ID for the given site name."""
        return 32  # PokerStars.COM


class TestPokerStarsCollectPot:
    """Test suite for readCollectPot method."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = MockConfig()
        self.parser = PokerStars(config=self.config)
        self.parser.substitutions = {}
        self.parser.clearMoneyString = Mock(side_effect=lambda x: x.replace(",", ""))
        
    def create_mock_hand(self, hand_text="", run_it_times=0, cashed_out=False):
        """Helper to create mock hand object."""
        hand = Mock()
        hand.handText = hand_text
        hand.runItTimes = run_it_times
        hand.cashedOut = cashed_out
        hand.addCollectPot = Mock()
        hand.players = []  # Add default empty players list
        hand.walk_adjustments = {}  # Add default empty walk_adjustments
        hand.cashOutFees = {}  # Add default empty cashOutFees dict
        return hand

    def test_basic_pot_collection_from_summary(self):
        """Test basic pot collection from summary section."""
        hand_text = """PokerStars Hand #123456789:  Hold'em No Limit ($0.05/$0.10 USD)
Table 'Test' 6-max Seat #1 is the button
Seat 1: Hero ($10.00 in chips)
Seat 2: Villain ($10.00 in chips)

*** SUMMARY ***
Total pot $1.10 | Rake $0.05
Board [Ah 7c 3d 9h 2s]
Seat 1: Hero showed [As Ks] and won ($1.05) with a pair of Aces
"""
        
        hand = self.create_mock_hand(hand_text)
        
        # Mock regex matches for summary section
        collect_match = Mock()
        collect_match.group.side_effect = lambda x: {
            "SEAT": "1", "PNAME": "Hero", "POT": "1.05"
        }.get(x)
        
        self.parser.re_collect_pot = Mock()
        self.parser.re_collect_pot.finditer = Mock(return_value=[collect_match])
        self.parser.re_cashed_out = Mock()
        self.parser.re_cashed_out.search = Mock(return_value=None)
        self.parser._calculateBovadaAdjustments = Mock(return_value=(False, False, 0, 0))
        self.parser._addCollectPotWithAdjustment = Mock()
        
        self.parser.readCollectPot(hand)
        
        assert hand.cashedOut is False
        self.parser._addCollectPotWithAdjustment.assert_called_once_with(hand, collect_match, (False, False, 0, 0))

    def test_pot_collection_from_pre_summary_when_no_summary_collections(self):
        """Test fallback to pre-summary section when no summary collections found."""
        hand_text = """PokerStars Hand #123456789:  Hold'em No Limit ($0.05/$0.10 USD)
Table 'Test' 6-max Seat #1 is the button
Seat 1: Hero ($10.00 in chips)
Seat 2: Villain ($10.00 in chips)
Hero collected $1.05 from pot

*** SUMMARY ***
Total pot $1.10 | Rake $0.05
Board [Ah 7c 3d 9h 2s]
"""
        
        hand = self.create_mock_hand(hand_text)
        
        # Mock no matches in summary section
        self.parser.re_collect_pot = Mock()
        self.parser.re_collect_pot.finditer = Mock(return_value=[])
        
        # Mock match in pre-summary section
        pre_collect_match = Mock()
        pre_collect_match.group.side_effect = lambda x: {
            "PNAME": "Hero", "POT": "1.05"
        }.get(x)
        
        self.parser.re_collect_pot2 = Mock()
        self.parser.re_collect_pot2.finditer = Mock(return_value=[pre_collect_match])
        self.parser.re_collect_pot3 = Mock()
        self.parser.re_collect_pot3.finditer = Mock(return_value=[])
        
        self.parser.re_cashed_out = Mock()
        self.parser.re_cashed_out.search = Mock(return_value=None)
        self.parser._calculateBovadaAdjustments = Mock(return_value=(False, False, 0, 0))
        self.parser._addCollectPotWithAdjustment = Mock()
        
        self.parser.readCollectPot(hand)
        
        self.parser._addCollectPotWithAdjustment.assert_called_once_with(hand, pre_collect_match, (False, False, 0, 0))

    def test_cash_out_detection(self):
        """Test cash out detection."""
        hand_text = """PokerStars Hand #123456789:  Hold'em No Limit ($0.05/$0.10 USD)
Table 'Test' 6-max Seat #1 is the button
Seat 1: Hero ($10.00 in chips)
Hero cashed out the hand

*** SUMMARY ***
Total pot $1.10 | Rake $0.05
"""
        
        hand = self.create_mock_hand(hand_text)
        
        # Mock cash out detection
        cash_out_match = Mock()
        self.parser.re_cashed_out = Mock()
        self.parser.re_cashed_out.search = Mock(return_value=cash_out_match)
        self.parser._calculateBovadaAdjustments = Mock(return_value=(False, False, 0, 0))
        
        self.parser.readCollectPot(hand)
        
        assert hand.cashedOut is True

    def test_cash_out_with_fee_collection(self):
        """Test cash out with fee pattern collection."""
        hand_text = """PokerStars Hand #123456789:  Hold'em No Limit ($0.05/$0.10 USD)
Table 'Test' 6-max Seat #1 is the button
Seat 1: Hero ($10.00 in chips)
Hero collected $1.00 and was charged $0.05 fee

*** SUMMARY ***
Total pot $1.10 | Rake $0.05
"""
        
        hand = self.create_mock_hand(hand_text)
        
        # Mock no matches in summary and re_collect_pot2
        self.parser.re_collect_pot = Mock()
        self.parser.re_collect_pot.finditer = Mock(return_value=[])
        self.parser.re_collect_pot2 = Mock()
        self.parser.re_collect_pot2.finditer = Mock(return_value=[])
        
        # Mock cash out with fee match
        fee_collect_match = Mock()
        fee_collect_match.group.side_effect = lambda x: {
            "PNAME": "Hero", "POT": "1.00", "FEE": "0.05"
        }.get(x)
        
        self.parser.re_collect_pot3 = Mock()
        self.parser.re_collect_pot3.finditer = Mock(return_value=[fee_collect_match])
        
        self.parser.re_cashed_out = Mock()
        self.parser.re_cashed_out.search = Mock(return_value=None)
        self.parser._calculateBovadaAdjustments = Mock(return_value=(False, False, 0, 0))
        self.parser._addCashOutPotWithAdjustment = Mock()
        
        self.parser.readCollectPot(hand)
        
        # Check that cash out fee is stored
        assert hasattr(hand, 'cashOutFees')
        assert hand.cashOutFees["Hero"] == Decimal("0.05")
        self.parser._addCashOutPotWithAdjustment.assert_called_once_with(hand, fee_collect_match, (False, False, 0, 0))

    def test_walk_scenario_detection(self):
        """Test walk scenario detection and handling."""
        hand_text = """PokerStars Hand #123456789:  Hold'em No Limit ($0.05/$0.10 USD)
Table 'Test' 6-max Seat #1 is the button
Seat 1: Hero ($10.00 in chips)
Hero collected $1.05 from pot

*** SUMMARY ***
Total pot $1.10 | Rake $0.05
"""
        
        hand = self.create_mock_hand(hand_text)
        hand.walk_adjustments = {"Hero": True}  # Simulate walk scenario detected in readAction
        
        # Mock no matches in summary section
        self.parser.re_collect_pot = Mock()
        self.parser.re_collect_pot.finditer = Mock(return_value=[])
        
        # Mock match in pre-summary section
        pre_collect_match = Mock()
        pre_collect_match.group.side_effect = lambda x: {
            "PNAME": "Hero", "POT": "1.05"
        }.get(x)
        
        self.parser.re_collect_pot2 = Mock()
        self.parser.re_collect_pot2.finditer = Mock(return_value=[pre_collect_match])
        self.parser.re_collect_pot3 = Mock()
        self.parser.re_collect_pot3.finditer = Mock(return_value=[])
        
        self.parser.re_cashed_out = Mock()
        self.parser.re_cashed_out.search = Mock(return_value=None)
        self.parser._calculateBovadaAdjustments = Mock(return_value=(False, False, 0, 0))
        self.parser._addCollectPotWithAdjustment = Mock()
        
        self.parser.readCollectPot(hand)
        
        # Should still process the collection even in walk scenario
        self.parser._addCollectPotWithAdjustment.assert_called_once()

    def test_run_it_times_scenario(self):
        """Test that collections are skipped when runItTimes > 0."""
        hand_text = """PokerStars Hand #123456789:  Hold'em No Limit ($0.05/$0.10 USD)
Table 'Test' 6-max Seat #1 is the button

*** SUMMARY ***
Total pot $1.10 | Rake $0.05
Seat 1: Hero showed [As Ks] and won ($1.05) with a pair of Aces
"""
        
        hand = self.create_mock_hand(hand_text, run_it_times=2)
        
        self.parser.re_cashed_out = Mock()
        self.parser.re_cashed_out.search = Mock(return_value=None)
        self.parser._calculateBovadaAdjustments = Mock(return_value=(False, False, 0, 0))
        self.parser.re_collect_pot = Mock()
        self.parser.re_collect_pot.finditer = Mock()
        
        self.parser.readCollectPot(hand)
        
        # Should not process summary collections when runItTimes > 0
        self.parser.re_collect_pot.finditer.assert_not_called()

    def test_multiple_collections_from_summary(self):
        """Test multiple pot collections from summary section."""
        hand_text = """PokerStars Hand #123456789:  Hold'em No Limit ($0.05/$0.10 USD)

*** SUMMARY ***
Total pot $2.10 | Rake $0.10
Seat 1: Hero showed [As Ks] and won ($1.05) with a pair of Aces
Seat 2: Villain showed [Qh Qd] and won ($1.05) with a pair of Queens
"""
        
        hand = self.create_mock_hand(hand_text)
        
        # Mock multiple matches in summary section
        collect_match1 = Mock()
        collect_match1.group.side_effect = lambda x: {
            "SEAT": "1", "PNAME": "Hero", "POT": "1.05"
        }.get(x)
        
        collect_match2 = Mock()
        collect_match2.group.side_effect = lambda x: {
            "SEAT": "2", "PNAME": "Villain", "POT": "1.05"
        }.get(x)
        
        self.parser.re_collect_pot = Mock()
        self.parser.re_collect_pot.finditer = Mock(return_value=[collect_match1, collect_match2])
        self.parser.re_cashed_out = Mock()
        self.parser.re_cashed_out.search = Mock(return_value=None)
        self.parser._calculateBovadaAdjustments = Mock(return_value=(False, False, 0, 0))
        self.parser._addCollectPotWithAdjustment = Mock()
        
        self.parser.readCollectPot(hand)
        
        # Should call _addCollectPotWithAdjustment twice
        assert self.parser._addCollectPotWithAdjustment.call_count == 2

    def test_bovada_adjustments_integration(self):
        """Test integration with Bovada adjustments."""
        hand_text = """PokerStars Hand #123456789:  Hold'em No Limit ($0.05/$0.10 USD)

*** SUMMARY ***
Total pot $1.10 | Rake $0.05
Seat 1: Hero showed [As Ks] and won ($1.05) with a pair of Aces
"""
        
        hand = self.create_mock_hand(hand_text)
        
        collect_match = Mock()
        collect_match.group.side_effect = lambda x: {
            "SEAT": "1", "PNAME": "Hero", "POT": "1.05"
        }.get(x)
        
        self.parser.re_collect_pot = Mock()
        self.parser.re_collect_pot.finditer = Mock(return_value=[collect_match])
        self.parser.re_cashed_out = Mock()
        self.parser.re_cashed_out.search = Mock(return_value=None)
        
        # Mock specific Bovada adjustments
        bovada_adjustments = (True, True, 0.5, 1.0)
        self.parser._calculateBovadaAdjustments = Mock(return_value=bovada_adjustments)
        self.parser._addCollectPotWithAdjustment = Mock()
        
        self.parser.readCollectPot(hand)
        
        # Verify adjustments are passed correctly
        self.parser._addCollectPotWithAdjustment.assert_called_once_with(hand, collect_match, bovada_adjustments)

    def test_comma_handling_in_amounts(self):
        """Test handling of comma-separated amounts."""
        hand_text = """PokerStars Hand #123456789:  Hold'em No Limit ($0.05/$0.10 USD)
Hero collected $1,234.56 and was charged $12.34 fee

*** SUMMARY ***
Total pot $1,250.00 | Rake $0.05
"""
        
        hand = self.create_mock_hand(hand_text)
        
        # Mock no matches in summary and re_collect_pot2
        self.parser.re_collect_pot = Mock()
        self.parser.re_collect_pot.finditer = Mock(return_value=[])
        self.parser.re_collect_pot2 = Mock()
        self.parser.re_collect_pot2.finditer = Mock(return_value=[])
        
        # Mock cash out with fee match with commas
        fee_collect_match = Mock()
        fee_collect_match.group.side_effect = lambda x: {
            "PNAME": "Hero", "POT": "1,234.56", "FEE": "12.34"
        }.get(x)
        
        self.parser.re_collect_pot3 = Mock()
        self.parser.re_collect_pot3.finditer = Mock(return_value=[fee_collect_match])
        
        self.parser.re_cashed_out = Mock()
        self.parser.re_cashed_out.search = Mock(return_value=None)
        self.parser._calculateBovadaAdjustments = Mock(return_value=(False, False, 0, 0))
        self.parser._addCashOutPotWithAdjustment = Mock()
        
        self.parser.readCollectPot(hand)
        
        # Check that commas are properly handled in fee amount
        assert hand.cashOutFees["Hero"] == Decimal("12.34")

    def test_no_summary_section_handling(self):
        """Test handling when there's no summary section."""
        hand_text = """PokerStars Hand #123456789:  Hold'em No Limit ($0.05/$0.10 USD)
Table 'Test' 6-max Seat #1 is the button
Hero collected $1.05 from pot
"""
        
        hand = self.create_mock_hand(hand_text)
        
        # Should raise ValueError due to missing "*** SUMMARY ***" section
        with pytest.raises(ValueError):
            self.parser.readCollectPot(hand)

    def test_empty_hand_text(self):
        """Test handling of empty hand text."""
        hand = self.create_mock_hand("")
        
        # Should raise ValueError due to missing "*** SUMMARY ***" section
        with pytest.raises(ValueError):
            self.parser.readCollectPot(hand)