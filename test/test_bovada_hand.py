#!/usr/bin/env python3

import sys

sys.path.insert(0, ".")

import BovadaToFpdb
import Configuration

# Test hand content
hand_text = """Bovada Hand #2902249427 TBL#8747464 OMAHA HiLo Pot Limit - 2014-08-05 01:25:39
Seat 1: UTG ($2.91 in chips)
Seat 2: UTG+1 ($2.56 in chips)
Seat 3: UTG+2 ($3.10 in chips)
Seat 5: UTG+3 ($4.41 in chips)
Seat 6: UTG+4 ($6.55 in chips)
Seat 7: Dealer ($1.15 in chips)
Seat 8: Small Blind ($5.10 in chips)
Seat 9: Big Blind [ME] ($4.98 in chips)
Dealer : Set dealer/Bring in spot [7]
Small Blind : Ante/Small Blind $0.02
Big Blind  [ME] : Big blind/Bring in $0.05
*** HOLE CARDS ***
UTG : Card dealt to a spot [Ad 4c 6s 4d]
UTG+1 : Card dealt to a spot [5c 8c Qh Ah]
UTG+2 : Card dealt to a spot [5h Ac Js Jh]
UTG+3 : Card dealt to a spot [3c 6d Ks 6c]
UTG+4 : Card dealt to a spot [7h Kd 3d 6h]
Dealer : Card dealt to a spot [Kh 2s 2h Qs]
Small Blind : Card dealt to a spot [9d 9h 4h 2d]
Big Blind  [ME] : Card dealt to a spot [As 8d 7d Jc]
UTG : Calls $0.05
UTG+1 : Folds
UTG+2 : Calls $0.05
UTG+3 : Folds
UTG+4 : Calls $0.05
Dealer : Folds
Small Blind : Calls $0.03
Big Blind  [ME] : Checks
*** FLOP *** [Kc 4s 9c]
Small Blind : Bets $0.10
Big Blind  [ME] : Folds
UTG : Calls $0.10
UTG+2 : Folds
UTG+4 : Folds
*** TURN *** [Kc 4s 9c] [9s]
Small Blind : Checks
UTG : Bets $0.38
Small Blind : Calls $0.38
*** RIVER *** [Kc 4s 9c 9s] [Qc]
Small Blind : Checks
UTG : Bets $0.80
Small Blind : Raises $1.60 to $1.60
UTG : Calls $0.80
Small Blind : Showdown [9d 9h Kc 9c 9s] (Four of a kind)
UTG : Mucks [Ad 4c 6s 4d] (Full House)
Small Blind : Hand result $4.19
*** SUMMARY ***
Total Pot($4.41)
Board [Kc 4s 9c 9s Qc]
Seat+1: UTG [Mucked] [Ad 4c 6s 4d   ]
Seat+2: UTG+1 Folded before the FLOP
Seat+3: UTG+2 Folded on the FLOP
Seat+5: UTG+3 Folded before the FLOP
Seat+6: UTG+4 Folded on the FLOP
Seat+7: Dealer Folded before the FLOP
Seat+8: Small Blind HI $4.19  with Four of a kind [9d 9h 4h 2d-9d 9h Kc 9c 9s]
Seat+9: Big Blind Folded on the FLOP
"""

try:
    config = Configuration.Config()
    converter = BovadaToFpdb.Bovada(config)
    converter.setObs(hand_text)

    gametype = converter.determineGameType(hand_text)

    if gametype:
        hand = converter.processHand(hand_text)
    else:
        pass

except Exception:
    import traceback

    traceback.print_exc()
