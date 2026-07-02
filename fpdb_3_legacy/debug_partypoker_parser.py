"""
from __future__ import annotationsQuick debug script to see what PartyPokerParser returns.
"""

import sys
from pathlib import Path

sys.path.insert(0, "/home/jd/fpdb-new")

from fpdb.infrastructure.parsers.partypoker_parser import PartyPokerParser

# Load test file
filepath = Path("/home/jd/fpdb-new/regression-test-files/cash/PartyPoker/Flop/NLHE-EUR-0.05-0.10-201011.Sample.txt")
hand_text = filepath.read_text(encoding="utf-8")

print("=" * 60)
print("PartyPoker Parser Output Debug")
print("=" * 60)

parser = PartyPokerParser()
result = parser.parse_text(hand_text)

if result and result.hands:
    hand_dict = result.hands[0]

    print(f"\nHand ID: {hand_dict.get('hand_id')}")
    print(f"Game Type: {hand_dict.get('game_type')}")
    print(f"Limit Type: {hand_dict.get('limit_type')}")
    print(f"\n🔍 BLINDS INFO:")
    print(f"  - SB (from dict): {hand_dict.get('sb')}")
    print(f"  - BB (from dict): {hand_dict.get('bb')}")
    print(f"  - Currency: {hand_dict.get('currency')}")

    print(f"\n🔍 ACTIONS (looking for blind posts):")
    for i, action in enumerate(hand_dict.get("actions", [])[:10]):
        action_type = action.get("type", "")
        if "blind" in action_type.lower():
            print(f"  [{i}] {action.get('player')}: {action_type} = {action.get('amount')}")

    print(f"\n🔍 FULL DICT KEYS:")
    print(f"  {list(hand_dict.keys())}")

    print(f"\n🔍 PLAYERS:")
    for p in hand_dict.get("players", []):
        print(f"  - {p.get('name')}: seat={p.get('seat')}, stack={p.get('stack')}")

else:
    print("ERROR: Parser returned no hands!")
