# Parser support matrix

This matrix records the validation tier of every hand-history converter. It
describes test coverage, not a commercial room's availability in every region.

## Golden-covered

These converters have file-by-file semantic snapshots in
`test/test_live_parser_regression.py`:

- Bovada/Ignition
- BetOnline
- Cake
- GGPoker
- iPoker
- KingsClub
- PacificPoker/888
- PartyPoker
- PokerStars
- SealsWithClubs
- Unibet
- Winamax
- Winning Poker Network

## Legacy

Kept for importing historical archives, without a current-format support claim:

- Absolute, Betfair, Boss, Enet, Entraction, Everest, Everleaf
- Full Tilt, Merge, Microgaming, OnGame, PKR, PokerTracker

Moving a converter out of this tier requires a representative fixture and a
golden snapshot covering identity, gametype, players, board, actions, winnings,
pot, and rake.
