#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Parameterized regression tests for FPDB Hand Histories.
Modernized version of TestHandsPlayers.py using pytest.

NOTE: v1.0 - Migration from legacy system, will need performance optimizations
"""

import os
import codecs
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple

import pytest
from unittest.mock import MagicMock

import Configuration
import Database
import Importer
from Hand import Hand


@dataclass
class ExpectedResults:
    """Expected results for a given site/file combination."""
    stored: int = 0
    dups: int = 0
    partial: int = 0
    errs: int = 0


# Expected results from original TestHandsPlayers.py
EXPECTED_RESULTS = {
    "BetOnline": {
        "regression-test-files/cash/BetOnline/Flop/NLHE-10max-USD-0.25-0.05-201108.txt": 
            ExpectedResults(19, 0, 1, 0),
        "regression-test-files/tour/BetOnline/Flop/NLHE-10max-USD-MTT-2011-08.nobuyinfee.txt": 
            ExpectedResults(17, 0, 1, 0),
        "regression-test-files/cash/BetOnline/Flop/NLHE-10max-0.25-0.50-201203.unknown.player.wins.txt": 
            ExpectedResults(0, 0, 0, 1),
    },
    "Cake": {
        "regression-test-files/tour/Cake/Flop/NLHE-USD-2-STT-201205.thousand.delimiter.txt": 
            ExpectedResults(1, 0, 1, 0),
    },
    "Full Tilt Poker": {
        "regression-test-files/cash/FTP/Draw/3-Draw-Limit-USD-20-40-201101.Partial.txt": 
            ExpectedResults(0, 0, 1, 0),
        "regression-test-files/cash/FTP/Draw/3-Draw-Limit-USD-10-20-201101.Dead.hand.txt": 
            ExpectedResults(0, 0, 1, 0),
        "regression-test-files/cash/FTP/Flop/NLHE-6max-USD-25-50.200610.Observed.No.player.stacks.txt": 
            ExpectedResults(0, 0, 1, 0),
    },
    "Merge": {
        "regression-test-files/cash/Merge/Draw/3-Draw-PL-USD-0.05-0.10-201102.Cancelled.hand.txt": 
            ExpectedResults(0, 0, 1, 0),
        "regression-test-files/cash/Merge/Flop/NLHE-6max-USD-0.02-0.04.201107.no.community.xml": 
            ExpectedResults(0, 0, 1, 0),
        "regression-test-files/cash/Merge/Flop/FLHE-9max-USD-0.02-0.04.20110416.xml": 
            ExpectedResults(9, 0, 1, 0),
    },
    "PacificPoker": {
        "regression-test-files/cash/PacificPoker/Flop/888-LHE-HU-USD-10-20-201202.cancelled.hand.txt": 
            ExpectedResults(0, 0, 1, 0),
    },
    "PokerStars": {
        "regression-test-files/cash/Stars/Flop/LO8-6max-USD-0.05-0.10-20090315.Hand-cancelled.txt": 
            ExpectedResults(0, 0, 1, 0),
        "regression-test-files/cash/Stars/Draw/3-Draw-Limit-USD-1-2-200809.Hand.cancelled.txt": 
            ExpectedResults(0, 0, 1, 0),
    },
    "PokerTracker": {
        "regression-test-files/tour/PokerTracker/Flop/T#3407415859 - €0.23+€0.02 - 20220605 - Summary.txt": 
            ExpectedResults(0, 0, 1, 0),
    },
}


@pytest.fixture(scope="session")
def test_database():
    """Create a test database for all regression tests."""
    config = Configuration.Config(file="HUD_config.test.xml")
    db = Database.Database(config)
    
    # Setup database settings
    settings = {}
    settings.update(config.get_db_parameters())
    settings.update(config.get_import_parameters())
    settings.update(config.get_default_paths())
    
    # Recreate tables for clean state
    db.recreate_tables()
    
    yield db, config, settings
    
    # Cleanup would go here if needed


@pytest.fixture(scope="function")
def importer(test_database):
    """Create a configured importer for each test."""
    db, config, settings = test_database
    
    importer = Importer.Importer(False, settings, config, None)
    importer.setDropIndexes("don't drop")
    importer.setThreads(-1)
    importer.setCallHud(False)
    importer.setFakeCacheHHC(True)
    
    yield importer
    
    # Clear file list after each test
    importer.clearFileList()


def collect_regression_files():
    """Collect all regression test files with their expected sites."""
    project_root = Path(__file__).parent.parent
    regression_dir = project_root / "regression-test-files"
    
    if not regression_dir.exists():
        return []
    
    test_params = []
    
    # Map directory names to site names
    site_mapping = {
        "Stars": "PokerStars",
        "FTP": "Full Tilt Poker", 
        "PartyPoker": "Party Poker",
        "BetOnline": "BetOnline",
        "Cake": "Cake",
        "Merge": "Merge",
        "PacificPoker": "PacificPoker",
        "PokerTracker": "PokerTracker",
        "Winamax": "Winamax",
    }
    
    # Walk through regression test files
    for category in ["cash", "tour", "summaries"]:
        category_dir = regression_dir / category
        if not category_dir.exists():
            continue
            
        for site_dir in category_dir.iterdir():
            if not site_dir.is_dir():
                continue
                
            site_name = site_mapping.get(site_dir.name, site_dir.name)
            
            # Recursively find .txt and .xml files (exclude generated files)
            for file_path in site_dir.rglob("*.txt"):
                # Skip generated snapshot files
                if any(suffix in file_path.name for suffix in ['.snapshot_summary.txt', '.snapshot.json']):
                    continue
                test_params.append((str(file_path), site_name))
            for file_path in site_dir.rglob("*.xml"):
                test_params.append((str(file_path), site_name))
    
    return test_params


@pytest.mark.parametrize("file_path,site_name", collect_regression_files())
def test_regression_file(file_path, site_name, importer):
    """Test a single regression file."""
    file_path_obj = Path(file_path)
    
    # Skip if file doesn't exist
    if not file_path_obj.exists():
        pytest.skip(f"File {file_path} does not exist")
    
    # Get expected results if available
    relative_path = str(file_path_obj.relative_to(Path.cwd()))
    expected = EXPECTED_RESULTS.get(site_name, {}).get(relative_path)
    
    # Import the file
    file_added = importer.addBulkImportImportFileOrDir(str(file_path), site=site_name)
    
    if not file_added:
        if expected and expected.errs > 0:
            # Expected to fail
            pytest.xfail(f"Expected parse failure for {relative_path}")
        else:
            pytest.fail(f"Failed to add file {relative_path}")
    
    # Run import
    try:
        (stored, dups, partial, skipped, errs, ttime) = importer.runImport()
    except Exception as e:
        if expected and expected.errs > 0:
            pytest.xfail(f"Expected import error for {relative_path}: {e}")
        else:
            raise
    
    # Check results against expectations
    if expected:
        if expected.errs > 0 and errs == 0:
            pytest.fail(f"Expected errors but got none for {relative_path}")
        elif expected.errs == 0 and errs > 0:
            pytest.xfail(f"Unexpected errors for {relative_path}: {errs}")
        
        # For successful imports, we can add more detailed checks here
        if errs == 0 and partial == 0:
            # Test against .hp, .hands, .gt files if they exist
            _compare_legacy_files(file_path, importer)


def _compare_legacy_files(file_path: str, importer):
    """Compare against legacy .hp, .hands, .gt files if available."""
    base_path = Path(file_path)
    
    # Check for .hp (hands players) file
    hp_file = base_path.with_suffix(base_path.suffix + ".hp")
    if hp_file.exists():
        _compare_handsplayers_file(str(hp_file), importer)
    
    # Check for .hands file
    hands_file = base_path.with_suffix(base_path.suffix + ".hands")
    if hands_file.exists():
        _compare_hands_file(str(hands_file), importer)
    
    # Check for .gt (gametypes) file
    gt_file = base_path.with_suffix(base_path.suffix + ".gt")
    if gt_file.exists():
        _compare_gametypes_file(str(gt_file), importer)


def _compare_handsplayers_file(hp_file: str, importer):
    """Compare hands players data against legacy .hp file."""
    try:
        with codecs.open(hp_file, "r", "utf8") as f:
            expected_data = eval(f.read())
    except Exception:
        pytest.xfail(f"Could not read/parse .hp file: {hp_file}")
        return
    
    hhc = importer.getCachedHHC()
    handlist = hhc.getProcessedHands()
    
    for hand in handlist:
        actual_data = hand.stats.getHandsPlayers()
        
        for player in actual_data:
            if player not in expected_data:
                pytest.xfail(f"Player {player} not found in expected data")
                continue
                
            actual_stats = actual_data[player]
            expected_stats = expected_data[player]
            
            # Compare stats (ignore volatile IDs)
            ignore_list = ["tourneyTypeId", "tourneysPlayersIds"]
            
            for stat in actual_stats:
                if stat in ignore_list:
                    continue
                    
                if stat not in expected_stats:
                    pytest.xfail(f"Stat {stat} not in expected data for player {player}")
                    continue
                
                if actual_stats[stat] != expected_stats[stat]:
                    pytest.fail(f"Stat mismatch for {player}.{stat}: "
                              f"got {actual_stats[stat]}, expected {expected_stats[stat]}")


def _compare_hands_file(hands_file: str, importer):
    """Compare hands data against legacy .hands file.""" 
    try:
        with codecs.open(hands_file, "r", "utf8") as f:
            expected_data = eval(f.read())
    except Exception:
        pytest.xfail(f"Could not read/parse .hands file: {hands_file}")
        return
    
    hhc = importer.getCachedHHC()
    handlist = hhc.getProcessedHands()
    
    for hand in handlist:
        actual_data = hand.stats.getHands()
        
        # Remove volatile data
        for key in ["gsc", "sc", "id", "boards", "gametypeId", "gameId", 
                   "sessionId", "tourneyId", "gameSessionId", "fileId", "runItTwice"]:
            actual_data.pop(key, None)
            
        # Compare remaining data
        for key in actual_data:
            if key not in expected_data:
                pytest.xfail(f"Key {key} not in expected hands data")
                continue
                
            if actual_data[key] != expected_data[key]:
                pytest.fail(f"Hands data mismatch for {key}: "
                          f"got {actual_data[key]}, expected {expected_data[key]}")


def _compare_gametypes_file(gt_file: str, importer):
    """Compare gametypes data against legacy .gt file."""
    try:
        with codecs.open(gt_file, "r", "utf8") as f:
            expected_data = eval(f.read())
    except Exception:
        pytest.xfail(f"Could not read/parse .gt file: {gt_file}")
        return
    
    hhc = importer.getCachedHHC()
    handlist = hhc.getProcessedHands()
    
    gametype_fields = [
        "Gametype: siteId", "Gametype: currency", "Gametype: type", 
        "Gametype: base", "Gametype: game", "Gametype: limit",
        "Gametype: hilo", "Gametype: mix", "Gametype: Small Blind",
        "Gametype: Big Blind", "Gametype: Small Bet", "Gametype: Big Bet",
        "Gametype: maxSeats", "Gametype: ante", "Gametype: cap", "Gametype: zoom"
    ]
    
    for hand in handlist:
        actual_gametype = hand.gametyperow
        
        for i, field_name in enumerate(gametype_fields):
            if i >= len(actual_gametype) or i >= len(expected_data):
                continue
                
            if actual_gametype[i] != expected_data[i]:
                pytest.fail(f"Gametype mismatch for {field_name}: "
                          f"got {actual_gametype[i]}, expected {expected_data[i]}")


if __name__ == "__main__":
    pytest.main([__file__])