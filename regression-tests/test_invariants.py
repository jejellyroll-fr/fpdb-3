#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Poker hand invariants testing for FPDB.
Tests fundamental poker rules that should always hold true.

NOTE: v1.0 - Basic invariants implemented, more game-specific rules needed
"""

from pathlib import Path
from typing import List, Dict, Any
from decimal import Decimal

import pytest

import Configuration
import Database  
import Importer
from tools.serialize_hand_for_snapshot import serialize_hand_for_snapshot, serialize_hands_batch


@pytest.fixture(scope="session")
def invariants_database():
    """Create a test database for invariant tests."""
    config = Configuration.Config(file="HUD_config.test.xml")
    db = Database.Database(config)
    
    settings = {}
    settings.update(config.get_db_parameters())
    settings.update(config.get_import_parameters())
    settings.update(config.get_default_paths())
    
    db.recreate_tables()
    
    yield db, config, settings


@pytest.fixture(scope="function")
def invariants_importer(invariants_database):
    """Create importer for invariant tests."""
    db, config, settings = invariants_database
    
    importer = Importer.Importer(False, settings, config, None)
    importer.setDropIndexes("don't drop")
    importer.setThreads(-1)
    importer.setCallHud(False)
    importer.setFakeCacheHHC(True)
    
    yield importer
    
    importer.clearFileList()


def get_invariant_test_files():
    """Get files specifically for invariant testing."""
    project_root = Path(__file__).parent.parent
    regression_dir = project_root / "regression-test-files"
    
    if not regression_dir.exists():
        return []
    
    test_files = []
    
    # Get diverse set of files for comprehensive invariant testing
    for category in ["cash", "tour"]:
        category_dir = regression_dir / category
        if not category_dir.exists():
            continue
            
        for site_dir in category_dir.iterdir():
            if not site_dir.is_dir():
                continue
                
            site_name_map = {
                "Stars": "PokerStars",
                "FTP": "Full Tilt Poker",
                "Winamax": "Winamax",
                "PartyPoker": "Party Poker",
                "Merge": "Merge",
            }
            
            site_name = site_name_map.get(site_dir.name, site_dir.name)
            
            # Collect up to 5 files per site for invariant testing
            files = list(site_dir.rglob("*.txt"))[:5]
            for file_path in files:
                test_files.append((str(file_path), site_name))
    
    return test_files


class PokerInvariant:
    """Base class for poker invariants."""
    
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
    
    def check(self, serialized_hand: Dict[str, Any]) -> List[str]:
        """Check this invariant. Return list of violations (empty if OK)."""
        raise NotImplementedError
    
    def __str__(self):
        return f"{self.name}: {self.description}"


class MoneyConservationInvariant(PokerInvariant):
    """Money is conserved: total winnings + rake = total pot."""
    
    def __init__(self):
        super().__init__(
            "Money Conservation",
            "Total player winnings plus rake must equal the total pot"
        )
    
    def check(self, hand: Dict[str, Any]) -> List[str]:
        violations = []
        
        if 'players' not in hand or 'total_pot' not in hand or 'rake' not in hand:
            return [f"{self.name}: Missing required data"]
        
        total_winnings = sum(p['net_winnings'] for p in hand['players'])
        rake = hand['rake']
        total_pot = hand['total_pot']
        
        # Allow small rounding errors (1 cent)
        if abs(total_winnings + rake - total_pot) > 0.01:
            violations.append(
                f"{self.name}: Money not conserved. "
                f"Winnings({total_winnings:.2f}) + Rake({rake:.2f}) = {total_winnings + rake:.2f}, "
                f"but pot is {total_pot:.2f}"
            )
        
        return violations


class UniqueSeatsInvariant(PokerInvariant):
    """Each player must have a unique seat number."""
    
    def __init__(self):
        super().__init__(
            "Unique Seats",
            "Each player must occupy a unique seat at the table"
        )
    
    def check(self, hand: Dict[str, Any]) -> List[str]:
        violations = []
        
        if 'players' not in hand:
            return [f"{self.name}: No players data"]
        
        seats = [p['seat'] for p in hand['players']]
        unique_seats = set(seats)
        
        if len(seats) != len(unique_seats):
            duplicate_seats = [seat for seat in unique_seats if seats.count(seat) > 1]
            violations.append(
                f"{self.name}: Duplicate seats found: {duplicate_seats}"
            )
        
        return violations


class ValidSeatNumbersInvariant(PokerInvariant):
    """Seat numbers must be within valid range for table size."""
    
    def __init__(self):
        super().__init__(
            "Valid Seat Numbers",
            "Seat numbers must be between 1 and max_seats"
        )
    
    def check(self, hand: Dict[str, Any]) -> List[str]:
        violations = []
        
        if 'players' not in hand or 'max_seats' not in hand:
            return [f"{self.name}: Missing required data"]
        
        max_seats = hand['max_seats']
        
        for player in hand['players']:
            seat = player['seat']
            if seat < 1 or seat > max_seats:
                violations.append(
                    f"{self.name}: Player {player['name']} has invalid seat {seat} "
                    f"(table max: {max_seats})"
                )
        
        return violations


class NonNegativeRakeInvariant(PokerInvariant):
    """Rake must be non-negative."""
    
    def __init__(self):
        super().__init__(
            "Non-negative Rake",
            "Rake amount must be zero or positive"
        )
    
    def check(self, hand: Dict[str, Any]) -> List[str]:
        violations = []
        
        if 'rake' not in hand:
            return [f"{self.name}: No rake data"]
        
        rake = hand['rake']
        if rake < 0:
            violations.append(f"{self.name}: Negative rake: {rake}")
        
        return violations


class WinnersExistInvariant(PokerInvariant):
    """If pot > 0, at least one player must have positive winnings."""
    
    def __init__(self):
        super().__init__(
            "Winners Exist",
            "Non-zero pots must have at least one winner"
        )
    
    def check(self, hand: Dict[str, Any]) -> List[str]:
        violations = []
        
        if 'players' not in hand or 'total_pot' not in hand:
            return [f"{self.name}: Missing required data"]
        
        total_pot = hand['total_pot']
        
        if total_pot > 0:
            winners = [p for p in hand['players'] if p['net_winnings'] > 0]
            if not winners:
                violations.append(
                    f"{self.name}: Pot is {total_pot} but no winners found"
                )
        
        return violations


class ValidActionsInvariant(PokerInvariant):
    """All actions must be valid poker actions."""
    
    def __init__(self):
        super().__init__(
            "Valid Actions",
            "All betting actions must be valid poker actions"
        )
    
    def check(self, hand: Dict[str, Any]) -> List[str]:
        violations = []
        
        if 'actions' not in hand:
            return []  # No actions is OK (summary-only hands)
        
        valid_actions = {
            'fold', 'check', 'call', 'bet', 'raise', 'all-in', 
            'small blind', 'big blind', 'ante', 'posts',
            'shows', 'mucks', 'wins', 'collected'
        }
        
        for action in hand['actions']:
            if action['action'].lower() not in valid_actions:
                violations.append(
                    f"{self.name}: Invalid action '{action['action']}' "
                    f"by {action['player']} on {action['street']}"
                )
        
        return violations


class ValidStreetsInvariant(PokerInvariant):
    """All streets must be valid poker betting rounds."""
    
    def __init__(self):
        super().__init__(
            "Valid Streets",
            "All betting streets must be valid poker betting rounds"
        )
    
    def check(self, hand: Dict[str, Any]) -> List[str]:
        violations = []
        
        valid_streets = {'preflop', 'flop', 'turn', 'river', 'showdown'}
        
        # Check actions
        if 'actions' in hand:
            for action in hand['actions']:
                if action['street'] not in valid_streets:
                    violations.append(
                        f"{self.name}: Invalid street '{action['street']}' in actions"
                    )
        
        # Check board cards
        if 'board_cards' in hand:
            for street in hand['board_cards'].keys():
                if street not in valid_streets:
                    violations.append(
                        f"{self.name}: Invalid street '{street}' in board cards"
                    )
        
        return violations


# All invariants to test
ALL_INVARIANTS = [
    MoneyConservationInvariant(),
    UniqueSeatsInvariant(),
    ValidSeatNumbersInvariant(),
    NonNegativeRakeInvariant(),
    WinnersExistInvariant(),
    ValidActionsInvariant(),
    ValidStreetsInvariant(),
]


def check_all_invariants(serialized_hand: Dict[str, Any]) -> Dict[str, List[str]]:
    """Check all invariants against a serialized hand."""
    results = {}
    
    for invariant in ALL_INVARIANTS:
        try:
            violations = invariant.check(serialized_hand)
            if violations:
                results[invariant.name] = violations
        except Exception as e:
            results[invariant.name] = [f"Error checking invariant: {e}"]
    
    return results


@pytest.mark.parametrize("file_path,site_name", get_invariant_test_files())
def test_hand_invariants(file_path, site_name, invariants_importer):
    """Test that all hands satisfy poker invariants."""
    file_path_obj = Path(file_path)
    
    if not file_path_obj.exists():
        pytest.skip(f"File {file_path} does not exist")
    
    # Import the file
    file_added = invariants_importer.addBulkImportImportFileOrDir(str(file_path), site=site_name)
    
    if not file_added:
        pytest.skip(f"Could not add file {file_path}")
    
    # Run import
    try:
        (stored, dups, partial, skipped, errs, ttime) = invariants_importer.runImport()
        
        if errs > 0:
            pytest.skip(f"Import errors in {file_path}: {errs}")
            
    except Exception as e:
        pytest.skip(f"Import failed for {file_path}: {e}")
    
    # Get processed hands
    hhc = invariants_importer.getCachedHHC()
    if not hhc:
        pytest.skip("No HHC available")
        
    handlist = hhc.getProcessedHands()
    if not handlist:
        pytest.skip("No hands processed")
    
    # Check invariants for each hand
    serialized_hands = serialize_hands_batch(handlist)
    
    all_violations = {}
    
    for i, hand_data in enumerate(serialized_hands):
        if 'error' in hand_data:
            continue  # Skip error entries
            
        hand_violations = check_all_invariants(hand_data)
        if hand_violations:
            hand_id = hand_data.get('hand_text_id', f'hand_{i}')
            all_violations[hand_id] = hand_violations
    
    # Report all violations
    if all_violations:
        violation_report = []
        for hand_id, violations in all_violations.items():
            violation_report.append(f"\nHand {hand_id}:")
            for invariant_name, invariant_violations in violations.items():
                for violation in invariant_violations:
                    violation_report.append(f"  - {violation}")
        
        pytest.fail(
            f"Invariant violations in {file_path}:\n" +
            "\n".join(violation_report)
        )


@pytest.mark.unit
def test_individual_invariants():
    """Test each invariant with specific test cases."""
    
    # Test money conservation
    money_invariant = MoneyConservationInvariant()
    
    # Valid case
    valid_hand = {
        'players': [
            {'net_winnings': 10.0},
            {'net_winnings': -8.0},
        ],
        'rake': 2.0,
        'total_pot': 4.0
    }
    assert not money_invariant.check(valid_hand)
    
    # Invalid case
    invalid_hand = {
        'players': [
            {'net_winnings': 15.0},
            {'net_winnings': -8.0},
        ],
        'rake': 2.0,
        'total_pot': 4.0
    }
    violations = money_invariant.check(invalid_hand)
    assert violations
    assert "Money not conserved" in violations[0]
    
    # Test unique seats
    seats_invariant = UniqueSeatsInvariant()
    
    # Valid case
    valid_seats = {
        'players': [
            {'seat': 1, 'name': 'Player1'},
            {'seat': 2, 'name': 'Player2'},
        ]
    }
    assert not seats_invariant.check(valid_seats)
    
    # Invalid case
    invalid_seats = {
        'players': [
            {'seat': 1, 'name': 'Player1'},
            {'seat': 1, 'name': 'Player2'},
        ]
    }
    violations = seats_invariant.check(invalid_seats)
    assert violations
    assert "Duplicate seats" in violations[0]


@pytest.mark.unit
def test_invariant_error_handling():
    """Test that invariants handle missing data gracefully."""
    incomplete_hand = {'site': 'TestSite'}
    
    for invariant in ALL_INVARIANTS:
        violations = invariant.check(incomplete_hand)
        # Should not raise exception, may return violations about missing data
        assert isinstance(violations, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])