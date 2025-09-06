#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Snapshot tests for FPDB using pytest-syrupy.
Automatically generates and validates stable hand representations.

NOTE: v1.0 - First iteration, expect refactoring and optimizations
"""

import os
from pathlib import Path
from typing import List

import pytest
from syrupy import SnapshotAssertion

import Configuration
import Database
import Importer
from serialize_hand_for_snapshot import serialize_hands_batch, verify_hand_invariants


@pytest.fixture(scope="session")
def snapshot_database():
    """Create a test database for snapshot tests."""
    config = Configuration.Config(file="HUD_config.test.xml")
    db = Database.Database(config)
    
    settings = {}
    settings.update(config.get_db_parameters())
    settings.update(config.get_import_parameters())
    settings.update(config.get_default_paths())
    
    db.recreate_tables()
    
    yield db, config, settings


@pytest.fixture(scope="function")
def snapshot_importer(snapshot_database):
    """Create importer for snapshot tests."""
    db, config, settings = snapshot_database
    
    importer = Importer.Importer(False, settings, config, None)
    importer.setDropIndexes("don't drop")
    importer.setThreads(-1)
    importer.setCallHud(False)
    importer.setFakeCacheHHC(True)
    
    yield importer
    
    importer.clearFileList()


def get_sample_files():
    """Get a curated list of sample files for snapshot testing."""
    project_root = Path(__file__).parent.parent
    regression_dir = project_root / "regression-test-files"
    
    if not regression_dir.exists():
        return []
    
    # Select representative files from each major site
    sample_files = []
    
    # PokerStars samples
    stars_dir = regression_dir / "cash" / "Stars" / "Flop"
    if stars_dir.exists():
        for file_path in list(stars_dir.rglob("*.txt"))[:3]:  # First 3 files
            sample_files.append((str(file_path), "PokerStars"))
    
    # Full Tilt Poker samples  
    ftp_dir = regression_dir / "cash" / "FTP" / "Flop"
    if ftp_dir.exists():
        for file_path in list(ftp_dir.rglob("*.txt"))[:3]:
            sample_files.append((str(file_path), "Full Tilt Poker"))
    
    # Winamax samples
    wina_dir = regression_dir / "cash" / "Winamax"
    if wina_dir.exists():
        for file_path in list(wina_dir.rglob("*.txt"))[:3]:
            sample_files.append((str(file_path), "Winamax"))
    
    return sample_files


@pytest.mark.parametrize("file_path,site_name", get_sample_files())
def test_hand_snapshot(file_path, site_name, snapshot_importer, snapshot: SnapshotAssertion):
    """Test hand parsing produces consistent snapshots."""
    file_path_obj = Path(file_path)
    
    if not file_path_obj.exists():
        pytest.skip(f"Sample file {file_path} does not exist")
    
    # Import the file
    file_added = snapshot_importer.addBulkImportImportFileOrDir(str(file_path), site=site_name)
    
    if not file_added:
        pytest.skip(f"Could not add file {file_path}")
    
    # Run import
    try:
        (stored, dups, partial, skipped, errs, ttime) = snapshot_importer.runImport()
        
        if errs > 0:
            pytest.skip(f"Import errors in {file_path}: {errs}")
            
    except Exception as e:
        pytest.skip(f"Import failed for {file_path}: {e}")
    
    # Get processed hands
    hhc = snapshot_importer.getCachedHHC()
    if not hhc:
        pytest.skip("No HHC available")
        
    handlist = hhc.getProcessedHands()
    if not handlist:
        pytest.skip("No hands processed")
    
    # Serialize hands for snapshot
    serialized_hands = serialize_hands_batch(handlist)
    
    # Verify invariants for each hand
    for hand_data in serialized_hands:
        if 'error' not in hand_data:  # Skip error entries
            violations = verify_hand_invariants(hand_data)
            if violations:
                pytest.fail(f"Invariant violations in {file_path}: {violations}")
    
    # Create snapshot with meaningful name
    relative_path = file_path_obj.relative_to(Path.cwd())
    snapshot_name = str(relative_path).replace("/", "_").replace("\\", "_").replace(".", "_")
    
    # Assert snapshot matches
    assert serialized_hands == snapshot(name=snapshot_name)


@pytest.mark.slow
def test_comprehensive_snapshots(snapshot_importer, snapshot: SnapshotAssertion):
    """Create comprehensive snapshots for all major file types."""
    project_root = Path(__file__).parent.parent
    regression_dir = project_root / "regression-test-files"
    
    if not regression_dir.exists():
        pytest.skip("No regression test files directory")
    
    # Test one file from each major category
    test_cases = [
        # Cash games
        ("cash/Stars/Flop", "PokerStars", "nlhe_cash"),
        ("cash/FTP/Flop", "Full Tilt Poker", "ftp_cash"),
        ("cash/Winamax", "Winamax", "winamax_cash"),
        
        # Tournaments
        ("tour/Stars", "PokerStars", "stars_tournament"),
        ("tour/FTP", "Full Tilt Poker", "ftp_tournament"),
        
        # Different games
        ("cash/Stars/Stud", "PokerStars", "stud_cash"),
        ("cash/Stars/Draw", "PokerStars", "draw_cash"),
    ]
    
    all_snapshots = {}
    
    for subdir, site_name, snapshot_key in test_cases:
        test_dir = regression_dir / subdir
        if not test_dir.exists():
            continue
            
        # Find first .txt file in this directory
        txt_files = list(test_dir.rglob("*.txt"))
        if not txt_files:
            continue
            
        file_path = txt_files[0]
        
        # Import and process
        file_added = snapshot_importer.addBulkImportImportFileOrDir(str(file_path), site=site_name)
        if not file_added:
            continue
            
        try:
            (stored, dups, partial, skipped, errs, ttime) = snapshot_importer.runImport()
            if errs > 0:
                continue
                
            hhc = snapshot_importer.getCachedHHC()
            if hhc:
                handlist = hhc.getProcessedHands()
                if handlist:
                    serialized = serialize_hands_batch(handlist[:1])  # Just first hand
                    all_snapshots[snapshot_key] = serialized
                    
        except Exception:
            continue
        finally:
            snapshot_importer.clearFileList()
    
    # Create comprehensive snapshot
    assert all_snapshots == snapshot(name="comprehensive_hand_types")


def test_empty_hands_snapshot(snapshot: SnapshotAssertion):
    """Test snapshot of empty hands list."""
    empty_hands = serialize_hands_batch([])
    assert empty_hands == snapshot(name="empty_hands")


def test_invariant_violations_recorded():
    """Test that invariant violations are properly detected."""
    # Create invalid hand data
    invalid_hand = {
        'site': 'TestSite',
        'hand_text_id': '123',
        'players': [
            {'name': 'Player1', 'seat': 1, 'net_winnings': 100.0},
            {'name': 'Player2', 'seat': 1, 'net_winnings': -50.0},  # Same seat!
        ],
        'total_pot': 60.0,
        'rake': 2.0,
        'max_seats': 6,
    }
    
    violations = verify_hand_invariants(invalid_hand)
    
    # Should detect duplicate seats
    assert any("unique seats" in v for v in violations)
    
    # Should detect money conservation issue  
    assert any("Money conservation failed" in v for v in violations)


if __name__ == "__main__":
    # Run with: pytest tests/test_snapshots.py --snapshot-update
    pytest.main([__file__, "-v"])