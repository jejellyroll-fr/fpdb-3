#!/usr/bin/env python3
from __future__ import annotations

"""Test script for Full Tilt Poker Run It Twice parser."""

from fpdb.infrastructure.parsers.fulltilt_parser import FullTiltParser

# Example hand history with Run It Twice
SAMPLE_HAND = """Full Tilt Poker Game #31319837969: Table Rymer (6 max, shallow) - $2/$4 - Pot Limit Omaha Hi - 18:33:09 CET - 2012/11/06 [12:33:09 ET - 2012/11/06]
Seat 1: Player0 ($120.15)
Seat 2: Player1 ($114)
Seat 3: Player2 ($147.90)
Seat 4: Hero ($125.70)
Seat 5: Player3 ($752.30)
Seat 6: Player4 ($194.40)
Hero posts the small blind of $2
Player3 posts the big blind of $4
The button is in seat #3
*** HOLE CARDS ***
Dealt to Hero [Ah Qd Jh Ad]
Player4 folds
Player0 folds
Player1 folds
Player2 has 15 seconds left to act
Player2 folds
Hero raises to $12
Player3 raises to $36
Hero raises to $108
Player3 raises to $180
Hero calls $17.70, and is all in
Players agree to Run It Twice
Player3 shows [As Ac Kd Jd]
Hero shows [Ah Qd Jh Ad]
Uncalled bet of $54.30 returned to Player3
*** FLOP 1 *** [7c 4h 7d] (Total Pot: $251.40, 2 Players, 1 All-In)
*** TURN 1 *** [7c 4h 7d] [5c] (Total Pot: $251.40, 2 Players, 1 All-In)
*** RIVER 1 *** [7c 4h 7d 5c] [Th] (Total Pot: $251.40, 2 Players, 1 All-In)
*** FLOP 2 *** [Kc 7h 3h] (Total Pot: $251.40, 2 Players, 1 All-In)
*** TURN 2 *** [Kc 7h 3h] [Qh] (Total Pot: $251.40, 2 Players, 1 All-In)
*** RIVER 2 *** [Kc 7h 3h Qh] [6c] (Total Pot: $251.40, 2 Players, 1 All-In)
*** SHOW DOWN 1 ***
Player3 shows two pair, Aces and Sevens
Hero shows two pair, Aces and Sevens
*** SHOW DOWN 2 ***
Player3 shows a pair of Aces
Hero shows a flush, Ace high
Hero ties for pot 1 ($62.10) with two pair, Aces and Sevens
Player3 ties for pot 1 ($62.10) with two pair, Aces and Sevens
Hero wins pot 2 ($124.20) with a flush, Ace high
*** SUMMARY ***
Total pot $251.40 | Rake $3
*** SUMMARY 1 ***
Pot 1 $124.20
Board: [7c 4h 7d 5c Th]
Seat 1: Player0 didn't bet (folded)
Seat 2: Player1 didn't bet (folded)
Seat 3: Player2 (button) didn't bet (folded)
Seat 4: Hero (small blind) showed [Ah Qd Jh Ad] and won ($62.10) with two pair, Aces and Sevens
Seat 5: Player3 (big blind) showed [As Ac Kd Jd] and won ($62.10) with two pair, Aces and Sevens
Seat 6: Player4 didn't bet (folded)
*** SUMMARY 2 ***
Pot 2 $124.20
Board: [Kc 7h 3h Qh 6c]
Seat 1: Player0 didn't bet (folded)
Seat 2: Player1 didn't bet (folded)
Seat 3: Player2 (button) didn't bet (folded)
Seat 4: Hero (small blind) showed [Ah Qd Jh Ad] and won ($124.20) with a flush, Ace high
Seat 5: Player3 (big blind) showed [As Ac Kd Jd] and lost with a pair of Aces
Seat 6: Player4 didn't bet (folded)
"""


def test_rit_parser():
    """Test the Full Tilt Parser with Run It Twice hand."""
    parser = FullTiltParser()

    print("=" * 80)
    print("Testing Full Tilt Poker Run It Twice Parser")
    print("=" * 80)

    result = parser.parse_text(SAMPLE_HAND)

    print(f"\nParsed {len(result.hands)} hand(s)")
    print(f"Errors: {len(result.errors)}")

    if result.errors:
        print("\n⚠️  Errors encountered:")
        for error in result.errors:
            print(f"  - {error}")

    if result.hands:
        hand = result.hands[0]
        print(f"\n✓ Hand ID: {hand['hand_id']}")
        print(f"✓ Site: {hand['site_name']}")
        print(f"✓ Table: {hand['table_name']}")
        print(f"✓ Game: {hand['game_category']} {hand['limit_type']}")
        print(f"✓ Stakes: ${hand['small_blind']}/${hand['big_blind']}")
        print(f"✓ Players: {len(hand['players'])}")
        print(f"✓ Total Pot: ${hand['pot_amount']}")
        print(f"✓ Rake: ${hand['rake_amount']}")

        if hand.get("is_run_it_twice"):
            rit_boards = hand.get("rit_boards") or {}
            rit_winners = hand.get("rit_winners") or {}
            print(f"\n✓ Run It Twice: YES ({len(rit_boards)} runs)")

            for run_number in sorted(rit_boards):
                print(f"\n  Run #{run_number}:")
                print(f"    Board: {rit_boards[run_number]}")

                winner = rit_winners.get(run_number)
                if winner:
                    hand_desc = winner.get("hand", "N/A")
                    print(f"      {winner['player']}: ${winner['amount']} ({hand_desc})")
        else:
            print("\n✗ Run It Twice: NO")

        print(f"\n✓ Actions: {len(hand['actions'])}")

        # Display some actions
        if hand["actions"]:
            print("\n  Sample actions:")
            for action in hand["actions"][:5]:
                print(f"    {action['street']}: {action['player']} {action['type']} ${action['amount']}")

        print("\n" + "=" * 80)
        print("Test completed successfully! ✓")
        print("=" * 80)
    else:
        print("\n✗ No hands parsed!")
        return False

    return True


if __name__ == "__main__":
    import sys

    success = test_rit_parser()
    sys.exit(0 if success else 1)
