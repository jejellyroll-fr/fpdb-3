#!/usr/bin/env python3
from __future__ import annotations

"""
Simple test script to verify PartyPoker parser doesn't block.
This tests the fix for re.DOTALL blocking issue.
"""

import os
import signal
import sys
import tempfile
from pathlib import Path

# Add project to path
sys.path.insert(0, os.getcwd())

# Disable all logging to prevent blocking
import logging

logging.disable(logging.CRITICAL)

# Mock GUI dependencies only when PySide6 is not installed. Installing mocks
# unconditionally pollutes sys.modules during pytest collection and breaks
# later PySide6/matplotlib compatibility tests.
try:
    import PySide6  # noqa: F401
except ImportError:
    from unittest.mock import MagicMock

    sys.modules["PySide6"] = MagicMock()
    sys.modules["PySide6.QtCore"] = MagicMock()
    sys.modules["PySide6.QtGui"] = MagicMock()
    sys.modules["PySide6.QtWidgets"] = MagicMock()

# Import after mocking
from fpdb_3_legacy import Configuration, PartyPokerToFpdb
from fpdb_3_legacy import Hand as LegacyHandModule


def timeout_handler(signum, frame):
    raise TimeoutError("Parser timeout - likely blocking issue!")


def test_partypoker_parser():
    """Test that PartyPoker parser doesn't block during Hand creation."""

    # Read test file
    test_file = Path("regression-test-files/cash/PartyPoker/Flop/NLHE-EUR-0.05-0.10-201011.Sample.txt")

    if not test_file.exists():
        print(f"❌ Test file not found: {test_file}")
        return False

    hand_text = test_file.read_text(encoding="utf-8")

    print(f"✓ Loaded test file: {test_file.name}")
    print(f"  Size: {len(hand_text)} bytes")

    # Create config with actual HUD_config.xml file
    config_path = Path("HUD_config.xml")
    if config_path.exists():
        config = Configuration.Config(file=str(config_path))
    else:
        config = Configuration.Config()
        # If no config file, we can't proceed as site IDs are needed
        print(f"❌ Config file not found: {config_path}")
        return False

    # Test 1: determineGameType (should be fast)
    print("\n1️⃣  Testing determineGameType()...")
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(5)  # 5 second timeout

    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write(hand_text)
            filepath = f.name

        try:
            converter = PartyPokerToFpdb.PartyPoker(config, in_path=filepath, sitename="PartyPoker", autostart=False)

            gametype = converter.determineGameType(hand_text)
            signal.alarm(0)

            if gametype is None:
                print("   ❌ determineGameType returned None")
                return False

            print("   ✅ determineGameType succeeded")
            print(f"      Game: {gametype.get('category')}, Limit: {gametype.get('limitType')}")
            print(f"      Blinds: {gametype.get('sb')}/{gametype.get('bb')}, Currency: {gametype.get('currency')}")

            # Add missing 'split' key
            if "split" not in gametype:
                gametype["split"] = False

            # Test 2: HoldemOmahaHand creation (this is where blocking occurred)
            print("\n2️⃣  Testing HoldemOmahaHand creation...")
            signal.alarm(10)  # 10 second timeout for full parsing

            legacy_hand: LegacyHandModule.Hand
            if gametype["base"] == "hold":
                legacy_hand = LegacyHandModule.HoldemOmahaHand(
                    config, converter, "PartyPoker", gametype, hand_text, builtFrom="HHC"
                )
            elif gametype["base"] == "stud":
                legacy_hand = LegacyHandModule.StudHand(
                    config, converter, "PartyPoker", gametype, hand_text, builtFrom="HHC"
                )
            elif gametype["base"] == "draw":
                legacy_hand = LegacyHandModule.DrawHand(
                    config, converter, "PartyPoker", gametype, hand_text, builtFrom="HHC"
                )
            else:
                print(f"   ❌ Unknown base: {gametype['base']}")
                return False

            signal.alarm(0)

            print("   ✅ Hand creation succeeded!")
            print(f"      Hand ID: {legacy_hand.handid}")
            print(f"      Players: {len(legacy_hand.players)}")
            print(f"      Button: {legacy_hand.buttonpos}")

            print("\n✨ ALL TESTS PASSED! ✨")
            print("   The re.DOTALL fix resolved the blocking issue.")
            return True

        finally:
            os.remove(filepath)

    except TimeoutError as e:
        signal.alarm(0)
        print(f"   ❌ TIMEOUT: {e}")
        print("   Parser is still blocking - fix incomplete.")
        return False
    except Exception as e:
        signal.alarm(0)
        print(f"   ❌ ERROR: {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        signal.alarm(0)


if __name__ == "__main__":
    print("=" * 60)
    print("PartyPoker Parser Blocking Test")
    print("Testing fix for re.DOTALL issue in readHandInfo()")
    print("=" * 60)

    success = test_partypoker_parser()

    sys.exit(0 if success else 1)
