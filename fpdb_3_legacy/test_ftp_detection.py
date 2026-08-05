#!/usr/bin/env python3
from __future__ import annotations

"""Test Full Tilt Poker site detection."""

from fpdb.infrastructure.parsers.parser_factory import ParserFactory

# Example FTP hand history
SAMPLE_HAND = """Full Tilt Poker Game #31319837969: Table Rymer (6 max, shallow) - $2/$4 - Pot Limit Omaha Hi - 18:33:09 CET - 2012/11/06 [12:33:09 ET - 2012/11/06]
Seat 1: Player0 ($120.15)
Seat 2: Player1 ($114)
Seat 3: Player2 ($147.90)
Seat 4: Hero ($125.70)
Hero posts the small blind of $2
Player3 posts the big blind of $4
*** HOLE CARDS ***
Dealt to Hero [Ah Qd Jh Ad]
Player4 folds
"""


def test_detection():
    """Test Full Tilt detection."""
    factory = ParserFactory()

    print("Testing Full Tilt Poker detection...")
    print("=" * 60)

    detected_site = factory.auto_detect_site(SAMPLE_HAND)

    print(f"Detected site: {detected_site}")

    if detected_site:
        if detected_site.lower().replace(" ", "") in ["fulltilt", "full"]:
            print("✓ Full Tilt detected correctly!")

            # Try to get parser
            try:
                parser = factory.get_parser(detected_site)
                print(f"✓ Parser retrieved: {type(parser).__name__}")
                return True
            except Exception as e:
                print(f"✗ Failed to get parser: {e}")
                return False
        else:
            print(f"✗ Wrong site detected: {detected_site}")
            return False
    else:
        print("✗ No site detected")
        return False


if __name__ == "__main__":
    import sys

    success = test_detection()
    sys.exit(0 if success else 1)
