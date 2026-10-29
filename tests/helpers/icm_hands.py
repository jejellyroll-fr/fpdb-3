"""A sit-and-go bubble all-in for the ICM tests (#446).

Three left of a 9-max, in PokerStars format: Hero shoves AsKs for 4000, Villain
calls with QhQd for 3000, Short folds the big blind; Villain wins.
"""

from __future__ import annotations

from types import SimpleNamespace

SNG_ALLIN = """PokerStars Hand #200000000001: Tournament #3000000001, $10+$1 USD Hold'em No Limit - Level V (100/200) - 2026/10/26 12:00:00 ET
Table '3000000001 1' 9-max Seat #1 is the button
Seat 1: Hero (4000 in chips)
Seat 3: Villain (3000 in chips)
Seat 5: Short (1000 in chips)
Villain: posts small blind 100
Short: posts big blind 200
*** HOLE CARDS ***
Dealt to Hero [As Ks]
Hero: raises 3800 to 4000 and is all-in
Villain: calls 2900 and is all-in
Short: folds
Uncalled bet (1000) returned to Hero
*** FLOP *** [2c 7d 9h]
*** TURN *** [2c 7d 9h] [Jc]
*** RIVER *** [2c 7d 9h Jc] [3s]
*** SHOW DOWN ***
Hero: shows [As Ks] (high card Ace)
Villain: shows [Qh Qd] (a pair of Queens)
Villain collected 6200 from pot
*** SUMMARY ***
Total pot 6200 | Rake 0
Board [2c 7d 9h Jc 3s]
Seat 1: Hero (button) showed [As Ks] and lost with high card Ace
Seat 3: Villain (small blind) showed [Qh Qd] and won (6200) with a pair of Queens
Seat 5: Short (big blind) folded before Flop



"""
PAYOUTS = [50.0, 30.0, 20.0]


def parse(tmp_path, text: str = SNG_ALLIN):
    from fpdb_3_legacy.Configuration import Config
    from fpdb_3_legacy.PokerStarsToFpdb import PokerStars

    path = tmp_path / "hand.txt"
    path.write_text(text, encoding="utf-8")
    parser = PokerStars(config=Config(file="HUD_config.xml"), in_path=str(path), autostart=True)
    (hand,) = parser.getProcessedHands()
    return hand, path


def fixed_equity(wins_a: int, wins_b: int, ties: int = 0):
    """An equity engine answer: A wins, B wins and ties out of their total."""

    def engine(_game, _pockets, _board, **_kwargs):
        samples = wins_a + wins_b + ties
        return SimpleNamespace(
            samples=samples,
            players=(
                SimpleNamespace(wins=wins_a, ties=ties, losses=wins_b),
                SimpleNamespace(wins=wins_b, ties=ties, losses=wins_a),
            ),
        )

    return engine


# The same hand as a PokerStars progressive knockout (#447): Hero ($5) covers Villain ($7.50).
PKO = (
    SNG_ALLIN.replace(
        "200000000001: Tournament #3000000001, $10+$1 USD",
        "200000000101: Tournament #3000000101, $4.40+$5.00+$0.60 USD",
    )
    .replace("Table '3000000001 1'", "Table '3000000101 1'")
    .replace("Hero (4000 in chips)", "Hero (4000 in chips, $5 bounty)")
    .replace("Villain (3000 in chips)", "Villain (3000 in chips, $7.50 bounty)")
    .replace("Short (1000 in chips)", "Short (1000 in chips, $5 bounty)")
)
