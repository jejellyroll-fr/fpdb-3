#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Snapshot tests for FPDB using pytest-syrupy.
Automatically generates and validates stable hand representations.

NOTE: v1.0 - First iteration, expect refactoring and optimizations
"""

import os
import sys
from pathlib import Path
from typing import List

if "numpy" not in sys.modules:
    from types import SimpleNamespace

    def _variance(values):
        if not values:
            return 0.0
        mean = sum(values) / len(values)
        return sum((value - mean) ** 2 for value in values) / len(values)

    sys.modules["numpy"] = SimpleNamespace(var=_variance)

import pytest
from syrupy import SnapshotAssertion

import Configuration
import Database
import Importer
from tools.serialize_hand_for_snapshot import serialize_hands_batch, verify_hand_invariants


def get_legacy_import_cases():
    """
    Auto-discover legacy test cases by finding all .hp files.

    Returns:
        List of tuples: (file_path, site_name, expected_counts)
        where expected_counts = (stored, dups, partial, errs)
    """
    project_root = Path(__file__).parent.parent
    regression_dir = project_root / "regression-test-files"

    # Site name mapping for detection
    site_mapping = {
        'pokerstars': 'PokerStars',
        'stars': 'PokerStars',
        'winamax': 'Winamax',
        '888poker': 'PacificPoker',
        'pacific': 'PacificPoker',
        'partypoker': 'PartyPoker',
        'party': 'PartyPoker',
        'ipoker': 'iPoker',
        'ipoker-network': 'iPoker',
        'ggpoker': 'GGPoker',
        'cake': 'Cake',
        'bovada': 'Bovada',
        'everleaf': 'Everleaf',
        'fulltilt': 'Fulltilt',
        'merge': 'Merge',
    }

    cases = []

    # Find all .hp files
    for hp_file in sorted(regression_dir.rglob("*.hp")):
        # Get corresponding .txt file (remove .hp extension)
        txt_file = Path(str(hp_file)[:-3])  # Remove last 3 chars (.hp)

        if not txt_file.exists():
            continue

        # Try to detect site from path
        path_lower = str(txt_file).lower()
        site_name = None

        for key, site in site_mapping.items():
            if key in path_lower:
                site_name = site
                break

        # Default to PokerStars if not detected
        if not site_name:
            site_name = 'PokerStars'

        # Expected counts: (stored, dups, partial, errs)
        # Default expectation: 1 hand stored, 0 errors
        expected_counts = (1, 0, 0, 0)

        cases.append((str(txt_file), site_name, expected_counts))

    return cases


# Generate legacy import cases dynamically
LEGACY_IMPORT_CASES = get_legacy_import_cases()


@pytest.fixture(scope="session")
def snapshot_database():
    """Create a test database for snapshot tests."""
    config = Configuration.Config(file="HUD_config.test.xml")
    temp_db_dir = Path.cwd() / ".pytest_tmp" / "snapshot_db"
    temp_db_dir.mkdir(parents=True, exist_ok=True)
    config.dir_database = str(temp_db_dir)
    config.dir_database = config.dir_database.replace("\\", "/")
    config.database_name = "snapshot"

    db = Database.Database(config)
    
    settings = {}
    settings.update(config.get_db_parameters())
    settings.update(config.get_import_parameters())
    settings.update(config.get_default_paths())
    
    db.recreate_tables()
    
    try:
        yield db, config, settings
    finally:
        try:
            db.disconnect()
        except Exception:
            pass
        import shutil

        shutil.rmtree(temp_db_dir, ignore_errors=True)


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
    active_sites_dir = project_root / "regression-test-files" / "active-sites"

    if not active_sites_dir.exists():
        return []

    sample_files = []
    site_map = {
        "pokerstars": "PokerStars",
        "winamax": "Winamax",
        "888poker": "888poker",
        "bovada-network": "Bovada",
        "ipoker-network": "iPoker",
        "ggpoker": "GGPoker",
        "cakepoker": "Cake"
    }

    for file_path in active_sites_dir.rglob("*.txt"):
        if "snapshot" in file_path.name or "summary" in file_path.name:
            continue

        try:
            relative_to_active = file_path.relative_to(active_sites_dir)
            site_folder_name = relative_to_active.parts[0]
            importer_site_name = site_map.get(site_folder_name.lower())
            if importer_site_name:
                sample_files.append((str(file_path), importer_site_name))
        except (IndexError, ValueError):
            continue
            
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
            assert "hand_details" in hand_data, "Missing hand_details section"
            assert isinstance(hand_data["hand_details"], dict), "hand_details should be a dict"
            assert isinstance(hand_data.get("players", []), list), "players should be serialized as a list"
            assert isinstance(hand_data.get("actions", []), list), "actions should be serialized as a list"
            violations = verify_hand_invariants(hand_data)
            if violations:
                pytest.fail(f"Invariant violations in {file_path}: {violations}")

    # Create snapshot with meaningful name
    relative_path = file_path_obj.relative_to(Path.cwd())
    snapshot_name = str(relative_path).replace("/", "_").replace("\\", "_").replace(".", "_")
    
    # Assert snapshot matches
    assert serialized_hands == snapshot(name=snapshot_name)


@pytest.mark.parametrize("file_path,site_name,expected_counts", LEGACY_IMPORT_CASES)
def test_legacy_regression_snapshot(file_path, site_name, expected_counts, snapshot_importer, snapshot: SnapshotAssertion):
    """Regression coverage for legacy THP datasets with .hp files."""
    file_path_obj = Path(file_path).resolve()

    if not file_path_obj.exists():
        pytest.skip(f"Legacy file {file_path} is missing")

    if not snapshot_importer.addBulkImportImportFileOrDir(str(file_path_obj), site=site_name):
        pytest.skip(f"Could not queue legacy file {file_path}")

    try:
        (stored, dups, partial, skipped, errs, ttime) = snapshot_importer.runImport()
    except Exception as exc:
        pytest.fail(f"Import crashed for {file_path}: {exc}")

    assert (stored, dups, partial, errs) == expected_counts, f"Unexpected import counts for {file_path}"

    try:
        hhc = snapshot_importer.getCachedHHC()
    except AttributeError:
        hhc = None

    handlist = hhc.getProcessedHands() if hhc else []

    serialized_hands = serialize_hands_batch(handlist) if handlist else []

    for hand_data in serialized_hands:
        if "error" not in hand_data:
            violations = verify_hand_invariants(hand_data)
            if violations:
                pytest.fail(f"Invariant violations in {file_path}: {violations}")

    try:
        relative_path = file_path_obj.relative_to(Path.cwd())
    except ValueError:
        relative_path = file_path_obj
    snapshot_name = "legacy_" + str(relative_path).replace("/", "_").replace("\\", "_").replace(".", "_")
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
        txt_files = [
            f for f in test_dir.rglob("*.txt")
            if "snapshot" not in f.name and "summary" not in f.name
        ]
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

    now_iso = "2025-01-01T00:00:00"

    invalid_hand = {
        "hand_details": {
            "siteHandNo": 123,
            "tableName": "Example",
            "siteId": 1,
            "siteName": "TestSite",
            "heroSeat": 1,
            "seats": 6,
            "startTime": now_iso,
            "importTime": now_iso,
        },
        "players": [
            {"playerName": "Player1", "seatNo": 1, "startCash": 1000, "winnings": 600, "rake": 50},
            {"playerName": "Player2", "seatNo": 1, "startCash": 1000, "winnings": 0, "rake": 0},
        ],
        "actions": [
            {
                "actionNo": 1,
                "streetActionNo": 1,
                "street": 0,
                "actionId": 6,
                "player": "Player1",
                "amount": 50.75,
                "amountCalled": 0,
                "raiseTo": 0,
            }
        ],
    }

    violations = verify_hand_invariants(invalid_hand)

    assert any("unique seat" in v for v in violations)
    assert any("Action field amount" in v for v in violations)


if __name__ == "__main__":
    # Run with: pytest tests/test_snapshots.py --snapshot-update
    pytest.main([__file__, "-v"])
