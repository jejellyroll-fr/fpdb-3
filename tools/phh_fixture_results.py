"""Regenerate the PHH test fixtures, with results computed by PokerKit (#381).

The hands below are written by hand; PokerKit -- the reference implementation of PHH, and
not a dependency of fpdb -- plays each one and supplies what fpdb is then checked against:
the ``winnings`` or ``finishing_stacks`` a fixture carries, and every player's net result
in ``pokerkit_results.json``. Run from the repository root, without installing PokerKit:

    uv run --no-project --with pokerkit python tools/phh_fixture_results.py

It writes ``tests/fixtures/phh/``.
"""

import json
from pathlib import Path

from pokerkit import HandHistory

OUTPUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "phh"
HANDS = {}

HANDS["nl_holdem_dwan_ivey"] = (
    """# PHH's own example: a big pot between Dwan and Ivey (results added by PokerKit).
variant = "NT"
antes = [500, 500, 500]
blinds_or_straddles = [1000, 2000, 0]
min_bet = 2000
starting_stacks = [1125600, 2000000, 553500]
actions = [
  "d dh p1 Ac2d",
  "d dh p2 ????",
  "d dh p3 7h6h",
  "p3 cbr 7000",
  "p1 cbr 23000",
  "p2 f",
  "p3 cc",
  "d db Jc3d5c",
  "p1 cbr 35000",
  "p3 cc",
  "d db 4h",
  "p1 cbr 90000",
  "p3 cbr 232600",
  "p1 cbr 1067100",
  "p3 cc",
  "p1 sm Ac2d",
  "p3 sm 7h6h",
  "d db Jh",
]
author = "Juho Kim"
event = "Million Dollar Cash Game"
year = 2009
players = ["Phil Ivey", "Patrik Antonius", "Tom Dwan"]
currency = "USD"
""",
    "finishing",
)

HANDS["nl_holdem_heads_up"] = (
    """variant = "NT"
antes = [0, 0]
blinds_or_straddles = [1, 2]
min_bet = 2
starting_stacks = [200, 150]
actions = [
  "d dh p1 KsKd",
  "d dh p2 AhQh",
  "p2 cbr 6",
  "p1 cbr 18",
  "p2 cc",
  "d db Qs7c2d",
  "p1 cbr 20",
  "p2 cc",
  "d db 9h",
  "p1 cc",
  "p2 cc",
  "d db 3c",
  "p1 cbr 50",
  "p2 f",
]
players = ["Alice", "Bob"]
seats = [1, 2]
seat_count = 2
table = "Heads-up 1"
year = 2026
month = 9
day = 1
time = 20:00:00
time_zone = "America/New_York"
currency = "USD"
_hero = "Alice"
""",
    None,
)

HANDS["nl_holdem_side_pots"] = (
    """variant = "NT"
antes = [0, 0, 0, 0]
blinds_or_straddles = [5, 10, 0, 0]
min_bet = 10
starting_stacks = [300, 1000, 120, 1000]
actions = [
  "d dh p1 AcAd",
  "d dh p2 KcKd",
  "d dh p3 QcQd",
  "d dh p4 7c2h",
  "p3 cbr 120",
  "p4 f",
  "p1 cbr 300",
  "p2 cc",
  "d db 3s8h9d",
  "d db Th",
  "d db 4s",
  "p1 sm AcAd",
  "p2 sm KcKd",
  "p3 sm QcQd",
]
players = ["Ann", "Ben", "Cid", "Dee"]
""",
    "winnings",
)

HANDS["pl_omaha"] = (
    """variant = "PO"
antes = [0, 0, 0]
blinds_or_straddles = [50, 100, 0]
min_bet = 100
starting_stacks = [10000, 10000, 10000]
actions = [
  "d dh p1 ????????",
  "d dh p2 AsAdKsQh",
  "d dh p3 ????????",
  "p3 cbr 350",
  "p1 f",
  "p2 cbr 1100",
  "p3 cc",
  "d db Ah7c2c",
  "p2 cbr 2250",
  "p3 f",
]
""",
    None,
)

HANDS["fl_omaha_hilo_split"] = (
    """variant = "FO/8"
antes = [0, 0, 0]
blinds_or_straddles = [1, 2, 0]
small_bet = 2
big_bet = 4
starting_stacks = [100, 100, 100]
actions = [
  "d dh p1 As2d9c9h",
  "d dh p2 QsQdJcJh",
  "d dh p3 9s9d8c8h",
  "p3 f",
  "p1 cbr 4",
  "p2 cc",
  "d db Kd5c3h",
  "p1 cbr 2",
  "p2 cc",
  "d db Qc",
  "p1 cbr 4",
  "p2 cc",
  "d db 7d",
  "p1 cc",
  "p2 cbr 4",
  "p1 cc",
  "p1 sm As2d9c9h",
  "p2 sm QsQdJcJh",
]
""",
    "winnings",
)

HANDS["fl_holdem"] = (
    """variant = "FT"
antes = [0, 0, 0, 0]
blinds_or_straddles = [1, 2, 0, 0]
small_bet = 2
big_bet = 4
starting_stacks = [80, 80, 80, 80]
actions = [
  "d dh p1 ????",
  "d dh p2 ????",
  "d dh p3 JsJh",
  "d dh p4 ????",
  "p3 cbr 4",
  "p4 cbr 6",
  "p1 f",
  "p2 f",
  "p3 cc",
  "d db 2c7d9h",
  "p3 cc",
  "p4 cbr 2",
  "p3 cbr 4",
  "p4 f",
]
""",
    None,
)

HANDS["ns_short_deck"] = (
    """variant = "NS"
antes = [1, 1, 1]
blinds_or_straddles = [0, 0, 2]
min_bet = 2
starting_stacks = [100, 100, 100]
actions = [
  "d dh p1 AhKh",
  "d dh p2 ????",
  "d dh p3 TsTd",
  "p1 cbr 6",
  "p2 f",
  "p3 cc",
  "d db 9c8c6h",
  "p1 cc",
  "p3 cbr 10",
  "p1 f",
]
""",
    None,
)

HANDS["stud_hi"] = (
    """variant = "F7S"
antes = [1, 1, 1]
bring_in = 2
small_bet = 5
big_bet = 10
starting_stacks = [200, 200, 200]
actions = [
  "d dh p1 ????2c",
  "d dh p2 AhAd9c",
  "d dh p3 ????Kd",
  "p1 pb",
  "p2 cbr 5",
  "p3 cc",
  "p1 f",
  "d dh p2 4h",
  "d dh p3 Ks",
  "p3 cbr 5",
  "p2 cc",
  "d dh p2 7s",
  "d dh p3 3d",
  "p3 cbr 10",
  "p2 cbr 20",
  "p3 cc",
  "d dh p2 Ac",
  "d dh p3 2h",
  "p3 cc",
  "p2 cbr 10",
  "p3 f",
]
""",
    None,
)

HANDS["stud_hilo_split"] = (
    """variant = "F7S/8"
antes = [1, 1]
bring_in = 2
small_bet = 5
big_bet = 10
starting_stacks = [200, 200]
actions = [
  "d dh p1 Ad2d3c",
  "d dh p2 KsKdQc",
  "p1 pb",
  "p2 cbr 5",
  "p1 cc",
  "d dh p1 4c",
  "d dh p2 Qs",
  "p2 cbr 5",
  "p1 cc",
  "d dh p1 9h",
  "d dh p2 Jc",
  "p2 cbr 10",
  "p1 cc",
  "d dh p1 Th",
  "d dh p2 5d",
  "p2 cc",
  "p1 cc",
  "d dh p1 6h",
  "d dh p2 8d",
  "p2 cbr 10",
  "p1 cc",
  "p2 sm KsKdQcQsJc5d8d",
  "p1 sm Ad2d3c4c9hTh6h",
]
""",
    "finishing",
)

HANDS["razz"] = (
    """variant = "FR"
antes = [1, 1, 1]
bring_in = 2
small_bet = 5
big_bet = 10
starting_stacks = [150, 150, 150]
actions = [
  "d dh p1 ????Ks",
  "d dh p2 Ah2d3c",
  "d dh p3 ????4h",
  "p1 pb",
  "p2 cbr 5",
  "p3 cbr 10",
  "p1 f",
  "p2 cc",
  "d dh p2 5c",
  "d dh p3 Kd",
  "p2 cbr 5",
  "p3 f",
]
""",
    None,
)

HANDS["single_draw"] = (
    """variant = "N2L1D"
antes = [0, 0, 0]
blinds_or_straddles = [5, 10, 0]
min_bet = 10
starting_stacks = [500, 500, 500]
actions = [
  "d dh p1 7h5c4d3s2c",
  "d dh p2 ??????????",
  "d dh p3 9s8h6c3d2h",
  "p3 cbr 30",
  "p1 cbr 90",
  "p2 f",
  "p3 cc",
  "p1 sd",
  "p3 sd 9s",
  "d dh p3 Kh",
  "p1 cbr 100",
  "p3 f",
]
""",
    None,
)

HANDS["triple_draw_yockey_arieh"] = (
    """# PHH's own example: a bad beat between Yockey and Arieh (results added by PokerKit).
variant = "F2L3D"
antes = [0, 0, 0, 0]
blinds_or_straddles = [75000, 150000, 0, 0]
small_bet = 150000
big_bet = 300000
starting_stacks = [1180000, 4340000, 5910000, 10765000]
actions = [
  "d dh p1 7h6c4c3d2c",
  "d dh p2 ??????????",
  "d dh p3 ??????????",
  "d dh p4 AsQs6s5c3c",
  "p3 f",
  "p4 cbr 300000",
  "p1 cbr 450000",
  "p2 f",
  "p4 cc",
  "p1 sd",
  "p4 sd AsQs",
  "d dh p4 2hQh",
  "p1 cbr 150000",
  "p4 cc",
  "p1 sd",
  "p4 sd Qh",
  "d dh p4 4d",
  "p1 cbr 300000",
  "p4 cc",
  "p1 sd",
  "p4 sd 6s",
  "d dh p4 7c",
  "p1 cbr 280000",
  "p4 cc",
  "p1 sm 7h6c4c3d2c",
  "p4 sm 2h4d7c5c3c",
]
author = "Juho Kim"
event = "2019 WSOP Event #58"
day = 28
month = 6
year = 2019
players = ["Bryce Yockey", "Phil Hui", "John Esposito", "Josh Arieh"]
""",
    "finishing",
)

HANDS["badugi"] = (
    """variant = "FB"
antes = [0, 0, 0]
blinds_or_straddles = [1, 2, 0]
small_bet = 2
big_bet = 4
starting_stacks = [100, 100, 100]
actions = [
  "d dh p1 As2d3c4h",
  "d dh p2 ????????",
  "d dh p3 KsKdQcJh",
  "p3 cbr 4",
  "p1 cc",
  "p2 f",
  "p1 sd",
  "p3 sd KdQc",
  "d dh p3 5d6c",
  "p1 cbr 2",
  "p3 cc",
  "p1 sd",
  "p3 sd Ks",
  "d dh p3 7s",
  "p1 cbr 4",
  "p3 cc",
  "p1 sd",
  "p3 sd",
  "p1 cbr 4",
  "p3 cc",
  "p1 sm As2d3c4h",
  "p3 sm 7s5d6cJh",
]
""",
    "winnings",
)

HANDS["nl_holdem_heads_up_bb_ante"] = (
    """# Heads-up with a big-blind ante: both arrays are assigned in reverse heads-up.
variant = "NT"
antes = [0, 3]
blinds_or_straddles = [1, 2]
min_bet = 2
starting_stacks = [200, 200]
actions = [
  "d dh p1 AsKs",
  "d dh p2 7c2d",
  "p2 cbr 6",
  "p1 cbr 20",
  "p2 f",
]
players = ["", ""]
""",
    None,
)

HANDS["triple_draw_all_in_runout"] = (
    """# All in before the first draw: the three draws follow with no betting between them.
variant = "F2L3D"
antes = [0, 0]
blinds_or_straddles = [1, 2]
small_bet = 2
big_bet = 4
starting_stacks = [4, 4]
actions = [
  "d dh p1 7h5c4d3s2c",
  "d dh p2 9s8h6c3d2h",
  "p2 cbr 4",
  "p1 cc",
  "p1 sd",
  "p2 sd 9s",
  "d dh p2 Kh",
  "p1 sd",
  "p2 sd Kh",
  "d dh p2 Qd",
  "p1 sd",
  "p2 sd Qd",
  "d dh p2 7d",
  "p1 sm 7h5c4d3s2c",
  "p2 sm 8h7d6c3d2h",
]
""",
    "winnings",
)

expected = {}
for name, (text, mode) in HANDS.items():
    hh = HandHistory.loads(text)
    try:
        states = list(hh)
    except Exception as error:
        print("FAIL", name, error)
        continue
    final = states[-1]
    if final.status:
        raise SystemExit(f"{name}: the hand is not complete in PokerKit")
    stacks = list(final.stacks)
    won = [0] * len(stacks)
    for op in final.operations:
        if type(op).__name__ == "ChipsPushing":
            won = [w + a for w, a in zip(won, op.amounts)]
    out = text
    if mode == "finishing":
        out += f"finishing_stacks = {stacks}\n"
    elif mode == "winnings":
        out += f"winnings = {won}\n"
    print(name, "stacks", stacks, "won", won, "payoffs", list(final.payoffs))
    (OUTPUT / f"{name}.phh").write_text(out)
    expected[name] = {"payoffs": list(final.payoffs), "collected": won}
(OUTPUT / "pokerkit_results.json").write_text(json.dumps(expected, indent=2, sort_keys=True) + "\n")
