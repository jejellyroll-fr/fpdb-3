# Reading hands straight from a PokerTracker 4 database (#615)

**Verdict: go for PokerTracker 4. Holdem Manager 3: not measured.**

PT4 keeps every imported hand as the room's own text, fpdb's room parsers read 99.5% of it unchanged,
and reading it takes a fraction of a second. The remaining gaps are known and bounded, and the
importer has to handle them (see [What the importer must handle](#what-the-importer-must-handle)).
No HM3 database was available, so HM3 stays on the archive route described in
[migrate-from-pt4-hm3.md](migrate-from-pt4-hm3.md).

Measured on 2026-11-14 on a real PT4 database (37,657 hands, 24 rooms) with
`python tools/pt4_db_probe.py --per-room 300`. The connection was read-only and the password was typed
by its owner. Most of the small rooms' hands come from fpdb's own `regression-test-files`, so the
rooms that count as independent evidence are GG Poker, iPoker, Winamax and PokerStars.

## The spike's three questions

### 1. What does PT4 store?

PT4's schema (`PokerTracker 4.app/Contents/Resources/Data/Schemas/schema.postgres.sql`) and the
database agree:

| Table | Columns | Rows |
|---|---|---:|
| `cash_hand_histories` | `id_hand` integer (primary key), `history` text | 33,074 |
| `tourney_hand_histories` | `id_hand` integer (primary key), `history` text | 4,583 |

`id_hand` joins `cash_hand_summary` / `tourney_hand_summary`, whose `id_site` names the room in
`lookup_sites.site_name` and whose `hand_no` is PT4's hand number.

Every sampled history (4,564) is plain text, not compressed or encoded. It is the room's own hand
history, with two exceptions:

- **iPoker** is rewritten in PokerTracker's `GAME #…` text, as PT4's *Export Hands* does. The room's
  XML is not kept. `PokerTrackerToFpdb` reads that text, and the iPoker skin is placed from the
  hero, as for an export (#704).
- **Text PT4 decoded as Mac Roman.** On macOS PT4 read cp1252 files as Mac Roman, so `€` (byte
  0x80) is stored as `Ä`: `Tournament #122715, Ä4.69+Ä0.31`. Applying PT4's decoding to fpdb's
  RunItOnce fixtures reproduces the parse failure seen in the database, and
  `text.encode("mac_roman").decode("cp1252")` makes them read again.

### 2. Do the room parsers read it unchanged?

Yes, for 99.5% of the database's hands: each room's sample rate, weighted by the room's share of the
database. Over the raw sample it is 4,408 of 4,564 hands (96.6%), because small rooms with failures
weigh as much as GG in a fixed-size sample.

| Room | Hands in PT4 | Read from the sample |
|---|---:|---|
| GG Poker, cash | 26,680 | 300 / 300 |
| iPoker, cash | 3,230 | 298 / 300 |
| Winamax, cash | 2,000 | 300 / 300 |
| PokerStars, tournaments | 1,054 | 300 / 300 |
| Winamax, tournaments | 875 | 300 / 300 |
| iPoker, tournaments | 806 | 298 / 300 |

The hands that do not read:

| Cause | Rooms | Database-only? |
|---|---|---|
| No fpdb parser | Boss Media (GTech G9, 54 hands), PPPoker (1) | No: files fail too |
| Stored as Mac Roman | RunItOnce tournaments (2 of 3) | Yes; repairable (above) |
| `decimal.ConversionSyntax`, whole room stops | Merge tournaments (78) | Yes: the Merge fixtures read from their files; cause not found |
| Parser reads the tournament from the file name | Winning / Yatahay tournaments (7 of 10 partial) | Yes: a history has no file name |
| `PokerTracker.determineGameType` fails | iPoker, 2 of 300 cash and 2 of 300 tournament hands | Not established |
| Partially anonymised fixture hands, single errors | Party, OnGame, Cake, SWC, Pacific, Everest | No: fixture or parser issues |

**Hand numbers.** fpdb stores the number it parses from the text, so a hand imported from the
database and the same hand imported from a file are duplicates of each other, as they should be.
PT4's own `hand_no` differs for GG (letter prefix kept), Winamax (padding) and OnGame. Only a tool
that joins fpdb rows to PT4 rows, such as `pt4_adapter`'s per-hand comparison, has to map them.

### 3. How fast, on a large database?

Streaming every history once through a server-side cursor took about 0.1 s for 37,657 rows
(43 M characters), about 300,000 rows/s. Even 1,000,000 hands would take seconds to read, so the PT4
side is not the bottleneck. Parsing runs at 230 to 6,000 hands/s depending on the room (GG 1,430,
PokerStars about 300), and fpdb's own storage comes after it: the same costs as importing files.
The importer must stream rather than load a whole table, since 1,000,000 hands is about 1 GB of text.

### Credentials and connection defaults

`fpdb_3_legacy/pt4_adapter/connection.py` stays the connection: `localhost`, `5432`, database
`PT4 DB`, user `postgres`, and `default_transaction_read_only=on`, so the server refuses any write.
Its `dbpass` default is a placeholder: the database measured here did not accept it. The importer
should pre-fill host, port, database and user, ask for the password, and keep it in memory only. It
must never read the password from PT4's settings. `default_transaction_read_only` protects against
mistakes, not against a hostile client. A user who wants a hard guarantee can create a PostgreSQL
role with `SELECT` rights only.

## What the importer must handle

The importer is a follow-up to #615, as a third source in *Import ▸ From Another Tracker…*:

- Stream histories room by room and hand them to the normal `Importer`, so duplicates, hero and
  iPoker room placement, sessions and the HUD cache behave as for files, with the same preview and
  summary.
- Repair Mac Roman text, only where the round trip is what happened.
- Bring tournament results over from PT4's tournament tables, or say they do not come over: the
  database holds no summary files.
- Rebuild the file name for parsers that read it (Winning / Yatahay tournaments), or list those
  hands as not imported.
- Remember the last `id_hand` per table, so a second run reads only new hands.
- Investigate the iPoker `GAME #` and Merge tournament failures above.

## Rerunning the probe

```bash
python tools/pt4_db_probe.py --per-room 300 --details pt4_probe_details.json
```

It asks for the password unless `PT4_PASSWORD` is set (`PT4_HOST`, `PT4_PORT`, `PT4_USER`,
`PT4_DATABASE` override the defaults). The printed report holds counts, rates and the first line of
each room's hands with every digit masked. `--details` writes the parsers' messages, which can name
players: keep that file local.

## Full probe output (2026-11-14)

| kind | room | hands in PT4 | sampled | identified as | parser | read | partial | errors | same hand no | hands/s | first line |
|---|---|---:|---:|---|---|---:|---:|---:|---:|---:|---|
| cash | GG Poker | 26,680 | 300 | GGPoker | GGPoker | 300 (100%) | 0 | 0 | 0 | 1,430 | `Poker Hand #OM999999999: PLO ($9.99/$9.9` / `Poker Hand #RC999999999: Omaha Pot Limit` |
| cash | iPoker | 3,230 | 300 | iPoker | PokerTracker | 298 (99%) | 0 | 2 | 297 | 3,166 | `GAME #9999999999 Version:99.9.9.99 Uncal` / `GAME #9999999999 Version:99.9.9.9 Uncall` |
| cash | Winamax | 2,000 | 300 | Winamax | Winamax | 300 (100%) | 0 | 0 | 52 | 741 | `Winamax Poker - ESCAPE "Bucarest" - Hand` / `Winamax Poker - CashGame - HandId: #9999` |
| cash | PokerStars | 315 | 300 | PokerStars.EU | PokerStars | 300 (100%) | 0 | 0 | 300 | 340 | `PokerStars Game #99999999999:  Hold'em N` / `PokerStars Hand #999999999999:  Omaha Po` |
| cash | Entraction | 289 | 289 | Entraction | Entraction | 289 (100%) | 0 | 0 | 289 | 3,157 | `Game # 9999999999 - Omaha High Pot Limit` / `Game # 9999999999 - Texas Hold'em No Lim` |
| cash | Pacific Poker | 155 | 155 | PacificPoker | PacificPoker | 155 (100%) | 0 | 0 | 155 | 3,874 | `***** Cassava Hand History for Game 9999` / `***** 999poker Snap Poker Hand History f` |
| cash | Everleaf | 115 | 115 | Everleaf | Everleaf | 115 (100%) | 0 | 0 | 115 | 6,180 | `Everleaf Gaming Game #999999999` |
| cash | Party | 64 | 64 | PartyPoker | PartyPoker | 62 (97%) | 2 | 0 | 61 | 1,281 | `***** Hand History for Game 99999999999` / `***** Hand History for Game 9999999999 *` |
| cash | SWCPoker | 54 | 54 | SealsWithClubs | SealsWithClubs | 54 (100%) | 0 | 0 | 54 | 4,317 | `SwCPoker Hand #999999999:  Omaha Pot Lim` / `SwCPoker Hand #999999999:  Hold'em No Li` |
| cash | PKR | 51 | 51 | PKR | Pkr | 51 (100%) | 0 | 0 | 51 | 2,261 | `Table #99999999 - Pink Paisley` / `Table #99999999 - Eumelus` |
| cash | Cake | 26 | 26 | Sun Poker | Cake | 26 (100%) | 0 | 0 | 26 | 4,538 | `Hand#9999999999999999 - Paris (9-max) 99` / `Hand#9999999999999999 - New Castle (Turb` |
| cash | Merge | 21 | 21 | iPoker | PokerTracker | 20 (95%) | 0 | 1 | 0 | 3,348 | `Merge Game #99999999-999 | Holdem Limit` / `Merge Game #99999999-999 | Holdem NL ($9` |
| cash | OnGame | 20 | 20 | OnGame | OnGame | 20 (100%) | 0 | 0 | 0 | 1,469 | `***** History for hand R9-99999999-999 *` / `***** History for hand R9-99999-9999 ***` |
| cash | Unibet | 16 | 16 | Unibet | Unibet | 16 (100%) | 0 | 0 | 16 | 320 | `Unibet Hand #9999999999 - 9.99/9.99 - Po` |
| cash | Boss Media | 12 | 12 | - | - | 0 (0%) | 0 | 0 | 0 | 0 | `GTech G9 Game #9999999: Table TH Micro 9` / `GTech G9 Game #9999999999: Table Table O` |
| cash | Full Tilt | 6 | 6 | Full Tilt Poker | Fulltilt | 6 (100%) | 0 | 0 | 6 | 769 | `Full Tilt Poker Game #99999999999: Table` |
| cash | MicroGaming | 5 | 5 | PokerTracker | PokerTracker | 5 (100%) | 0 | 0 | 5 | 2,873 | `** Game ID 9999999999 Version:9 starting` / `** Game ID 9999999999 starting - 9999-99` |
| cash | Yatahay Network | 4 | 4 | Ya Poker | Winning | 4 (100%) | 0 | 0 | 4 | 1,112 | `Hand #999999999 - Holdem(No Limit) - $9.` / `Hand #99999999 - Holdem(No Limit) - $9.9` |
| cash | Cereus Network | 4 | 4 | UltimateBet | Absolute | 4 (100%) | 0 | 0 | 1 | 918 | `Stage #C999999999: Holdem  No Limit $9.9` / `Stage #C999999999: Holdem  Normal $9.99/` |
| cash | Everest | 2 | 2 | PokerTracker | PokerTracker | 1 (50%) | 0 | 1 | 1 | 1,865 | `EverestPoker Game #9999999999: Table Kit` / `EverestPoker Game #9999999999: Table Van` |
| cash | RunItOnce | 2 | 2 | PokerStars.EU | PokerStars | 2 (100%) | 0 | 0 | 2 | 227 | `Run It Once Poker Hand #99999999:  Hold'` / `Run It Once Poker Hand #99999999:  Omaha` |
| cash | Betfair | 1 | 1 | Betfair | Betfair | 1 (100%) | 0 | 0 | 1 | 866 | `***** Betfair Poker Hand History for Gam` |
| cash | PPPoker | 1 | 1 | - | - | 0 (0%) | 0 | 0 | 0 | 0 | `PPPoker Hand #999999999999999: Hold'em N` |
| cash | Ignition | 1 | 1 | Bovada | Bovada | 1 (100%) | 0 | 0 | 1 | 1,075 | `Bovada Hand #9999999999 TBL#99999999 HOL` |
| tourney | PokerStars | 1,054 | 300 | PokerStars.COM | PokerStars | 300 (100%) | 0 | 0 | 300 | 278 | `PokerStars Game #99999999999: Tournament` / `PokerStars Hand #999999999999: Tournamen` |
| tourney | Winamax | 875 | 300 | Winamax | Winamax | 300 (100%) | 0 | 0 | 0 | 954 | `Winamax Poker - Tournament "Expresso Nit` / `Winamax Poker - Tournament "Expresso" bu` |
| tourney | iPoker | 806 | 300 | iPoker | PokerTracker | 298 (99%) | 0 | 2 | 240 | 3,586 | `GAME #9999999999 Version:99.9.9.99 Uncal` / `GAME #9999999999 Texas Hold'em NL  Tourn` |
| tourney | Ignition | 533 | 300 | Bovada | Bovada | 300 (100%) | 0 | 0 | 300 | 1,816 | `Ignition Hand #9999999999: HOLDEM Tourna` / `Bovada Hand #9999999999: HOLDEM Tourname` |
| tourney | OnGame | 192 | 192 | OnGame | OnGame | 191 (99%) | 1 | 0 | 0 | 1,146 | `***** History for hand T9-99999999-99 (T` / `***** History for hand T9-99999999-9 (TO` |
| tourney | Full Tilt | 186 | 186 | Full Tilt Poker | Fulltilt | 186 (100%) | 0 | 0 | 186 | 4,181 | `Full Tilt Poker Game #99999999999: $99 S` / `Full Tilt Poker Game #99999999999: $9 Si` |
| tourney | Pacific Poker | 151 | 151 | PacificPoker | PacificPoker | 150 (99%) | 0 | 1 | 150 | 3,694 | `***** Cassava Hand History for Game 9999` / `***** 999poker Hand History for Game 999` |
| tourney | SWCPoker | 144 | 144 | SealsWithClubs | SealsWithClubs | 142 (99%) | 0 | 2 | 142 | 2,659 | `SwCPoker Hand #999999999: Tournament (NL` / `SwCPoker Hand #999999999: Tournament (HO` |
| tourney | Party | 111 | 111 | PartyPoker | PartyPoker | 111 (100%) | 0 | 0 | 108 | 2,207 | `***** Hand History for Game 99999999999` / `***** Hand History for Game 999999999999` |
| tourney | Everleaf | 90 | 90 | Everleaf | Everleaf | 90 (100%) | 0 | 0 | 90 | 4,376 | `Everleaf Gaming Game #999999999` |
| tourney | Cereus Network | 87 | 87 | UltimateBet | Absolute | 87 (100%) | 0 | 0 | 87 | 3,023 | `Stage #999999999 Tourney ID 9999999 Hold` |
| tourney | GG Poker | 81 | 81 | GGPoker | GGPoker | 81 (100%) | 0 | 0 | 0 | 2,104 | `Poker Hand #TM999999999: Tournament #999` / `Poker Hand #SG9999999999: Tournament #99` |
| tourney | Merge | 78 | 78 | PokerTracker | PokerTracker | 0 (0%) | 0 | 0 | 0 | 0 | `Merge Game #99999999-9 (Tournament) | Ho` / `Merge Game #99999999-99 (Tournament) | H` |
| tourney | Everest | 69 | 69 | PokerTracker | PokerTracker | 68 (99%) | 0 | 1 | 68 | 4,088 | `EverestPoker Game #9999999999: Tourney I` |
| tourney | PKR | 43 | 43 | PKR | Pkr | 43 (100%) | 0 | 0 | 43 | 2,396 | `Table #99999999 - Tournament #99999999 T` / `Table #99999999 - STT # 99999999` |
| tourney | Boss Media | 42 | 42 | - | - | 0 (0%) | 0 | 0 | 0 | 0 | `GTech G9 Game #9999999: Table (9999999),` / `GTech G9 Game #999999999: Table (9999999` |
| tourney | Cake | 15 | 15 | Sun Poker | Cake | 14 (93%) | 1 | 0 | 1 | 3,709 | `Hand#9999AB99EA999999 - $9 Bounty T99999` / `Hand#9999E999C9999999 - $9 Heads-up PL O` |
| tourney | Yatahay Network | 10 | 10 | Ya Poker | Winning | 3 (30%) | 7 | 0 | 3 | 980 | `Game started at: 9999/9/9 99:9:99 Tourna` / `Game started at: 9999/9/99 99:99:99 Tour` |
| tourney | MicroGaming | 7 | 7 | PokerTracker | PokerTracker | 7 (100%) | 0 | 0 | 7 | 4,214 | `** Game ID 9999999999 Version:9 starting` |
| tourney | Unibet | 4 | 4 | Unibet | Unibet | 4 (100%) | 0 | 0 | 4 | 332 | `Unibet Hand #9999999999, Tournament #999` |
| tourney | RunItOnce | 3 | 3 | PokerStars.COM | PokerStars | 1 (33%) | 0 | 2 | 1 | 235 | `Run It Once Poker Hand #99999999: Tourna` |
| tourney | Entraction | 2 | 2 | Entraction | Entraction | 2 (100%) | 0 | 0 | 2 | 2,868 | `Game # 9999999999 - Texas Hold'em No Lim` |

Sample: 4,408 of 4,564 hands read (96.6%). Weighted by each room's share of the database: 99.5% of 37,657 hands.
