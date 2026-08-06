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

## Disabled

Support is switched off in the application, but the code and its tests stay in
the tree:

- CoinPoker (converter, packet-capture pipeline, Unity table detection)

The switch is `DISABLED_SITES` in `fpdb_3_legacy/disabled_sites.py`: the room
is forced off in the configuration, keeps no `<hhc>` converter binding, and its
live-capture tab is hidden. Re-enabling it means removing its name from that
set, not restoring deleted files.
