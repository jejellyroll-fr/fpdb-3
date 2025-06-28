#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Summary of functional coverage tests for DerivedStats methods

This file provides an overview of all the test files created to cover
the previously untested methods in DerivedStats.
"""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def print_test_coverage_summary():
    """Print a summary of all DerivedStats test coverage"""
    
    print("=" * 80)
    print("DERIVED STATS FUNCTIONAL COVERAGE TEST SUMMARY")
    print("=" * 80)
    print()
    
    test_files = [
        {
            "file": "test_assemble_hands.py",
            "method": "assembleHands",
            "description": "Tests the assembly of hand-level statistics",
            "key_scenarios": [
                "Basic hand assembly with standard holdem hand",
                "Tournament hand handling",
                "No hero hand",
                "Incomplete board (all-in preflop)",
                "Run it twice scenarios",
                "Split pot games",
                "Empty actions",
                "Special board cards (FLOPET)",
            ],
        },
        {
            "file": "test_players_at_street.py",
            "method": "playersAtStreetX",
            "description": "Tests counting players at each street",
            "key_scenarios": [
                "Basic player counting through streets",
                "All fold preflop",
                "Heads-up scenarios",
                "Position tracking (first to act, in position)",
                "All-in blind players",
                "No action on streets",
                "Multiway fold to last aggressor",
            ],
        },
        {
            "file": "test_street_raises.py",
            "method": "streetXRaises",
            "description": "Tests counting raises/bets/completes per street",
            "key_scenarios": [
                "Basic raise counting",
                "No betting streets",
                "Completes counted as raises",
                "Multiple bets same street",
                "Empty streets",
                "All-in not counted",
                "Stud game streets",
            ],
        },
        {
            "file": "test_effective_stack.py",
            "method": "calcEffectiveStack",
            "description": "Tests effective stack calculation",
            "key_scenarios": [
                "Basic effective stack calculation",
                "Heads-up scenarios",
                "Folded players excluded",
                "Sitting out players excluded",
                "All equal stacks",
                "Single player action",
                "No actions",
                "Decimal stack sizes",
            ],
        },
        {
            "file": "test_set_positions.py",
            "method": "setPositions",
            "description": "Tests position assignment for players",
            "key_scenarios": [
                "Basic 6-max positions",
                "Heads-up positions",
                "Stud game positions",
                "Button blind positions",
                "Straddle positions",
                "Missing small blind",
                "All fold to big blind",
            ],
        },
        {
            "file": "test_calc_steals.py",
            "method": "calcSteals",
            "description": "Tests steal attempts and fold to steal stats",
            "key_scenarios": [
                "Button steal success",
                "Cutoff steal called by BB",
                "SB steal in full ring",
                "No steal from early position",
                "Limp then raise not steal",
                "BB re-raise steal attempt",
                "Stud steal positions",
                "Button blind steal positions",
                "Sitting out player ignored",
            ],
        },
        {
            "file": "test_calc_34bet_street0.py",
            "method": "calc34BetStreet0",
            "description": "Tests 3-bet and 4-bet calculations",
            "key_scenarios": [
                "Simple 3-bet",
                "4-bet scenario",
                "Squeeze opportunity",
                "Cold 4-bet (C4B)",
                "All-in stops action",
                "Stud betting levels",
                "Heads-up aggression chance",
                "Sitting out player",
                "Fold to 2-bet",
            ],
        },
        {
            "file": "test_calc_called_raise_street0.py",
            "method": "calcCalledRaiseStreet0",
            "description": "Tests called raise statistics",
            "key_scenarios": [
                "Simple call of raise",
                "Multiple raises and calls",
                "Complete counts as raise",
                "No raises no chances",
                "All fold to raise",
                "Re-raise resets tracking",
                "Heads-up scenario",
                "Limp-reraise scenario",
            ],
        },
    ]
    
    # Existing test files that were already present
    existing_tests = [
        {
            "file": "test_street0_aggr_vpip.py",
            "methods": ["vpip", "street0Aggr"],
            "description": "Tests VPIP and street0 aggression calculations",
        },
        {
            "file": "test_derived_stats.py",
            "methods": ["assembleHandsPlayers", "calcCBets", "calcCheckCallRaise"],
            "description": "Tests various player statistics calculations",
        },
    ]
    
    print("NEW TEST FILES CREATED:")
    print("-" * 80)
    for test in test_files:
        print(f"\nFile: {test['file']}")
        print(f"Method: {test['method']}")
        print(f"Description: {test['description']}")
        print(f"Key scenarios tested ({len(test['key_scenarios'])}):")
        for scenario in test['key_scenarios']:
            print(f"  - {scenario}")
    
    print("\n" + "=" * 80)
    print("EXISTING TEST FILES:")
    print("-" * 80)
    for test in existing_tests:
        print(f"\nFile: {test['file']}")
        print(f"Methods: {', '.join(test['methods'])}")
        print(f"Description: {test['description']}")
    
    print("\n" + "=" * 80)
    print("METHODS STILL REQUIRING TEST COVERAGE:")
    print("-" * 80)
    
    untested_methods = [
        "assembleHandsStove",
        "assembleHandsPots", 
        "getAllInEV",
        "getBoardsList",
        "getBoardsDict",
        "awardPots",
        "countPlayers",
        "pfba",
        "pfbao",
        "firstsBetOrRaiser",
        "lastBetOrRaiser",
        "noBetsBefore",
        "assembleHudCache",
    ]
    
    print("\nMethods that may still need test coverage:")
    for method in untested_methods:
        print(f"  - {method}")
    
    print("\n" + "=" * 80)
    print("RUNNING ALL TESTS:")
    print("-" * 80)
    print("\nTo run all DerivedStats tests:")
    print("  pytest test/test_*derived*.py test/test_*street*.py test/test_*calc*.py test/test_*effective*.py test/test_*players*.py test/test_*assemble*.py test/test_*set*.py -v")
    print("\nTo run a specific test file:")
    print("  pytest test/<filename> -v")
    print("\nTo run with coverage report:")
    print("  pytest --cov=DerivedStats test/test_*.py")
    print("\n" + "=" * 80)


if __name__ == "__main__":
    print_test_coverage_summary()
    
    # Optional: Check if test files exist
    print("\nCHECKING TEST FILE EXISTENCE:")
    print("-" * 80)
    test_dir = os.path.dirname(os.path.abspath(__file__))
    
    test_files = [
        "test_assemble_hands.py",
        "test_players_at_street.py",
        "test_street_raises.py",
        "test_effective_stack.py",
        "test_set_positions.py",
        "test_calc_steals.py",
        "test_calc_34bet_street0.py",
        "test_calc_called_raise_street0.py",
    ]
    
    all_exist = True
    for test_file in test_files:
        path = os.path.join(test_dir, test_file)
        exists = os.path.exists(path)
        status = "✓" if exists else "✗"
        print(f"{status} {test_file}")
        if not exists:
            all_exist = False
    
    if all_exist:
        print("\n✓ All test files created successfully!")
    else:
        print("\n✗ Some test files are missing!")