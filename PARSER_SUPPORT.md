# Parser support matrix

This matrix records the validation tier of every hand-history converter. It
describes test coverage, not a commercial room's availability in every region.

## Golden-covered

These converters have file-by-file semantic snapshots in
`tests/test_live_parser_regression.py`:

- Betclic (the 2025+ in-house client's `*** HEADER ***` text format: Spin & Rush
  lottery sit-and-gos and cash games; the legacy iPoker skin "Betclic Poker" is
  covered under iPoker)
- Bovada/Ignition
- BetOnline
- Cake
- GGPoker
- iPoker
- KingsClub
- PacificPoker/888
- PartyPoker
- PokerStars
- PokerTracker (its own export format, cash and tournaments: Everest, iPoker,
  Merge and Microgaming hands, each filed under the room in its header -- pinned
  by `tests/test_pokertracker_rooms.py`)
- SealsWithClubs
- Unibet (the 2026 Relax Gaming client's `Unibet Hand #` exports and its tournament summaries; setup and limits in [docs/unibet-setup.md](docs/unibet-setup.md))
- Winamax
- Winning Poker Network

## Legacy

Kept for importing historical archives, without a current-format support claim:

- Absolute, Betfair, Boss, Enet, Entraction, Everest, Everleaf
- Full Tilt, Merge, Microgaming, OnGame, PKR

Moving a converter out of this tier requires a representative fixture and a
golden snapshot covering identity, gametype, players, board, actions, winnings,
pot, and rake.

## Import-only

The room's exported hand histories are bulk-imported for review after the
session; nothing runs beside its client:

- CoinPoker (#732): the 2026 text export (`CoinPoker Hand #…`, amounts in ₮,
  stored as USD) -- NLH, PLO 4/5/6, bomb pots on two boards, run it twice,
  Splash and Mega Splash drops, Splash Fee, all-in EV cash-outs. Golden
  snapshots in `tests/test_live_parser_regression.py`, behaviour in
  `tests/test_coinpoker_text_import.py`. Its packet-capture pipeline and table
  detection stay in the tree, unused.

The switch is `IMPORT_ONLY_SITES` in `fpdb_3_legacy/disabled_sites.py`: the
room keeps its `<hhc>` converter binding and can be enabled for Bulk Import,
but no HUD runs at its tables (`aux_enabled` is forced off and the HUD refuses
them), Auto Import does not watch its folder, and its live capture is not
offered. Supporting the file import is not a recommendation to play there: see
[docs/fair-play.md](docs/fair-play.md#rooms).

Opponents in these files are pseudonyms that change from hand to hand, so
opponent statistics from them mean nothing; the import is for your own play.

## Disabled

`DISABLED_SITES`, in the same module, switches a room off entirely while its
code and tests stay in the tree: it is forced off in the configuration, keeps
no `<hhc>` converter binding, and its own tabs are hidden. No room is disabled
today.
