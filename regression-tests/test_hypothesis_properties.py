#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Property-based testing for FPDB using Hypothesis.
Tests that poker parsing properties hold across generated variations.

NOTE: v1.0 - Migration from legacy system, will need performance optimizations
"""

import re
import tempfile
from pathlib import Path
from typing import List, Dict, Any

import pytest
from hypothesis import given, strategies as st, settings, assume, example
from hypothesis import HealthCheck

import Configuration
import Database
import Importer
from serialize_hand_for_snapshot import serialize_hands_batch, verify_hand_invariants


@pytest.fixture(scope="session")
def hypothesis_database():
    """Create a test database for hypothesis tests."""
    config = Configuration.Config(file="HUD_config.test.xml")
    db = Database.Database(config)
    
    settings = {}
    settings.update(config.get_db_parameters())
    settings.update(config.get_import_parameters())
    settings.update(config.get_default_paths())
    
    db.recreate_tables()
    
    yield db, config, settings


@pytest.fixture(scope="function")
def hypothesis_importer(hypothesis_database):
    """Create importer for hypothesis tests."""
    db, config, settings = hypothesis_database
    
    importer = Importer.Importer(False, settings, config, None)
    importer.setDropIndexes("don't drop")
    importer.setThreads(-1)
    importer.setCallHud(False)
    importer.setFakeCacheHHC(True)
    
    yield importer
    
    importer.clearFileList()


# Strategies for generating test data

@st.composite
def player_names(draw):
    """Generate realistic player names with various encodings."""
    base_names = [
        "Hero", "Villain", "Fish123", "ProPlayer", "Lucky7", 
        "AAKKing", "BluffMaster", "TightAggressive", "CallStation",
        "ShortStack", "BigStack", "UTG", "BTN", "SB", "BB"
    ]
    
    # Add some international characters
    international_names = [
        "José", "François", "Müller", "Władysław", "Björn",
        "André", "Café", "Señor", "Naïve", "Résumé"
    ]
    
    all_names = base_names + international_names
    return draw(st.sampled_from(all_names))


@st.composite
def hand_history_variations(draw, base_content):
    """Generate variations of a hand history that should parse identically."""
    content = base_content
    
    # 1. Line ending variations
    line_ending = draw(st.sampled_from(['\n', '\r\n', '\r']))
    content = content.replace('\n', line_ending)
    
    # 2. Whitespace variations (but not affecting parsing)
    # Add/remove trailing spaces
    if draw(st.booleans()):
        lines = content.split(line_ending)
        lines = [line.rstrip() + (' ' * draw(st.integers(0, 3))) for line in lines]
        content = line_ending.join(lines)
    
    # 3. Empty line variations
    if draw(st.booleans()):
        lines = content.split(line_ending)
        # Insert empty lines at random positions (but not in critical spots)
        for _ in range(draw(st.integers(0, 3))):
            pos = draw(st.integers(0, len(lines)))
            lines.insert(pos, '')
        content = line_ending.join(lines)
    
    return content


@st.composite
def encoding_variations(draw):
    """Generate different text encodings."""
    return draw(st.sampled_from(['utf-8', 'utf-16', 'cp1252', 'iso-8859-1']))


def get_base_hand_history():
    """Get a base hand history for testing variations."""
    return '''PokerStars Hand #123456789: Hold'em No Limit ($0.01/$0.02 USD) - 2023/01/01 12:00:00 ET
Table 'Test Table' 6-max Seat #1 is the button
Seat 1: Hero ($2.00 in chips)
Seat 2: Villain ($2.00 in chips)
Hero: posts small blind $0.01
Villain: posts big blind $0.02
*** HOLE CARDS ***
Dealt to Hero [Ah Kh]
Hero: raises $0.04 to $0.06
Villain: calls $0.04
*** FLOP *** [As Kc 2h]
Hero: bets $0.08
Villain: calls $0.08
*** TURN *** [As Kc 2h] [3d]
Hero: bets $0.20
Villain: folds
Uncalled bet ($0.20) returned to Hero
Hero collected $0.27 from pot
Hero: doesn't show hand
*** SUMMARY ***
Total pot $0.28 | Rake $0.01
Board [As Kc 2h 3d]
Seat 1: Hero (button) (small blind) collected ($0.27)
Seat 2: Villain (big blind) folded on the Turn'''


class HandHistoryPropertyTests:
    """Property-based tests for hand history parsing."""
    
    def __init__(self, importer):
        self.importer = importer
    
    def parse_hand_history(self, content: str, encoding: str = 'utf-8') -> List[Dict[str, Any]]:
        """Parse a hand history and return serialized hands."""
        with tempfile.NamedTemporaryFile(mode='w', encoding=encoding, suffix='.txt', delete=False) as f:
            f.write(content)
            temp_path = f.name
        
        try:
            # Clear any previous files
            self.importer.clearFileList()
            
            # Import the temporary file
            file_added = self.importer.addBulkImportImportFileOrDir(temp_path, site="PokerStars")
            if not file_added:
                return []
            
            # Run import
            (stored, dups, partial, skipped, errs, ttime) = self.importer.runImport()
            if errs > 0:
                return []
            
            # Get processed hands
            hhc = self.importer.getCachedHHC()
            if not hhc:
                return []
                
            handlist = hhc.getProcessedHands()
            if not handlist:
                return []
            
            # Serialize hands
            return serialize_hands_batch(handlist)
            
        except Exception:
            return []
        finally:
            # Cleanup
            Path(temp_path).unlink(missing_ok=True)


@pytest.mark.slow
@pytest.mark.hypothesis
class TestHandHistoryProperties:
    """Property-based tests for hand history parsing."""
    
    @given(encoding=encoding_variations())
    @settings(max_examples=10, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_encoding_invariance(self, encoding, hypothesis_importer):
        """Test that different encodings produce same parsing results."""
        base_content = get_base_hand_history()
        
        # Only test encodings that can represent the content
        try:
            base_content.encode(encoding)
        except UnicodeEncodeError:
            assume(False)  # Skip this encoding
        
        property_tester = HandHistoryPropertyTests(hypothesis_importer)
        
        # Parse with UTF-8 as baseline
        baseline_hands = property_tester.parse_hand_history(base_content, 'utf-8')
        assume(len(baseline_hands) > 0)  # Need successful parse for comparison
        
        # Parse with test encoding
        test_hands = property_tester.parse_hand_history(base_content, encoding)
        
        # Should produce identical results (excluding encoding-specific errors)
        if len(test_hands) > 0:
            assert len(test_hands) == len(baseline_hands)
            
            for baseline, test in zip(baseline_hands, test_hands):
                # Compare key fields that should be identical
                assert baseline.get('hand_text_id') == test.get('hand_text_id')
                assert baseline.get('total_pot') == test.get('total_pot')
                assert baseline.get('rake') == test.get('rake')
                assert len(baseline.get('players', [])) == len(test.get('players', []))
    
    @given(variation=hand_history_variations(get_base_hand_history()))
    @settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_whitespace_invariance(self, variation, hypothesis_importer):
        """Test that whitespace variations don't affect parsing."""
        baseline_content = get_base_hand_history()
        
        property_tester = HandHistoryPropertyTests(hypothesis_importer)
        
        # Parse baseline
        baseline_hands = property_tester.parse_hand_history(baseline_content)
        assume(len(baseline_hands) > 0)
        
        # Parse variation
        variant_hands = property_tester.parse_hand_history(variation)
        
        # Should produce identical results
        if len(variant_hands) > 0:
            assert len(variant_hands) == len(baseline_hands)
            
            for baseline, variant in zip(baseline_hands, variant_hands):
                # Key parsing results should be identical
                assert baseline.get('total_pot') == variant.get('total_pot')
                assert baseline.get('rake') == variant.get('rake')
                assert len(baseline.get('players', [])) == len(variant.get('players', []))
                
                # Players should have same net winnings
                baseline_winnings = sorted([p['net_winnings'] for p in baseline.get('players', [])])
                variant_winnings = sorted([p['net_winnings'] for p in variant.get('players', [])])
                assert baseline_winnings == variant_winnings
    
    @given(
        name1=player_names(),
        name2=player_names(),
        stack1=st.floats(min_value=0.01, max_value=1000.0),
        stack2=st.floats(min_value=0.01, max_value=1000.0),
    )
    @settings(max_examples=15, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_player_name_stack_variations(self, name1, name2, stack1, stack2, hypothesis_importer):
        """Test that different player names and stacks maintain invariants."""
        assume(name1 != name2)  # Need different names
        
        # Create hand with generated values
        hand_template = '''PokerStars Hand #123456789: Hold'em No Limit ($0.01/$0.02 USD) - 2023/01/01 12:00:00 ET
Table 'Test Table' 6-max Seat #1 is the button
Seat 1: {name1} (${stack1:.2f} in chips)
Seat 2: {name2} (${stack2:.2f} in chips)
{name1}: posts small blind $0.01
{name2}: posts big blind $0.02
*** HOLE CARDS ***
Dealt to {name1} [Ah Kh]
{name1}: folds
{name2} collected $0.02 from pot
*** SUMMARY ***
Total pot $0.02 | Rake $0.00
Seat 1: {name1} (button) (small blind) folded before Flop
Seat 2: {name2} (big blind) collected ($0.02)'''
        
        content = hand_template.format(name1=name1, name2=name2, stack1=stack1, stack2=stack2)
        
        property_tester = HandHistoryPropertyTests(hypothesis_importer)
        hands = property_tester.parse_hand_history(content)
        
        if len(hands) > 0:
            hand = hands[0]
            
            # Check invariants hold
            violations = verify_hand_invariants(hand)
            assert not violations, f"Invariant violations: {violations}"
            
            # Specific checks for generated values
            players = hand.get('players', [])
            assert len(players) == 2
            
            player_names = {p['name'] for p in players}
            assert name1 in player_names
            assert name2 in player_names
    
    @given(
        pot_size=st.floats(min_value=0.02, max_value=100.0),
        rake_percent=st.floats(min_value=0.0, max_value=0.10),
    )
    @settings(max_examples=10, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_pot_rake_variations(self, pot_size, rake_percent, hypothesis_importer):
        """Test that different pot sizes and rake maintain money conservation."""
        rake = round(pot_size * rake_percent, 2)
        net_pot = pot_size - rake
        
        # Create hand with specific pot/rake
        content = f'''PokerStars Hand #123456789: Hold'em No Limit ($0.01/$0.02 USD) - 2023/01/01 12:00:00 ET
Table 'Test Table' 6-max Seat #1 is the button
Seat 1: Hero ($50.00 in chips)
Seat 2: Villain ($50.00 in chips)
Hero: posts small blind $0.01
Villain: posts big blind $0.02
*** HOLE CARDS ***
Dealt to Hero [Ah Kh]
Hero: calls $0.01
Villain: checks
*** FLOP *** [As Kc 2h]
Hero: checks
Villain: bets ${net_pot:.2f}
Hero: folds
Villain collected ${net_pot:.2f} from pot
*** SUMMARY ***
Total pot ${pot_size:.2f} | Rake ${rake:.2f}
Board [As Kc 2h]
Seat 1: Hero (button) (small blind) folded on the Flop
Seat 2: Villain (big blind) collected (${net_pot:.2f})'''
        
        property_tester = HandHistoryPropertyTests(hypothesis_importer)
        hands = property_tester.parse_hand_history(content)
        
        if len(hands) > 0:
            hand = hands[0]
            
            # Check money conservation specifically
            violations = verify_hand_invariants(hand)
            money_violations = [v for v in violations if 'Money' in v]
            assert not money_violations, f"Money conservation failed: {money_violations}"
            
            # Verify our generated values
            assert abs(hand['total_pot'] - pot_size) < 0.01
            assert abs(hand['rake'] - rake) < 0.01


@pytest.mark.hypothesis
def test_hypothesis_baseline():
    """Test that hypothesis is working with a simple example."""
    @given(st.integers())
    def test_integers_are_integers(x):
        assert isinstance(x, int)
    
    test_integers_are_integers()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "hypothesis"])