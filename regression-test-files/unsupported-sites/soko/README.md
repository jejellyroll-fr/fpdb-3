# Historical Sökö excerpts (2005), not win2day hands

Two anonymized hand histories of Sökö (Finnish five-card stud) posted on a
public Swedish poker forum in 2005, collected in issue #891. They are kept to
check that fpdb refuses Sökö instead of importing it as another game.

| File | Source | Notes |
| --- | --- | --- |
| `soko_2005_001_complete_anonymized.txt` | pokerforum.nu, 8 June 2005, topic 5585 page 3 | Original header `Game # 80960594 - Soko Pot Limit`; the game number (`90000001`), table (`Anonymous_Soko_01`) and date (`2005-01-01 12:00:00 UTC`) here are **synthetic** |
| `soko_2005_002_header_missing_anonymized.txt` | pokerforum.nu, 26 November 2005, topic 8505 page 5 | Posted **without a header**: no game number, table, date or game name. Kept as posted; never give it an invented header to make it parse |

What they are, and are not:

- Player names are replaced by `Hero` and `Villain1..N` within each hand;
  cards, bets, actions, seats, winnings and rake are as posted. The winners,
  amounts and rake were not checked by fpdb.
- They predate win2day Poker (launched in 2008 on Boss Media, on iPoker
  since 2015). They are **not** win2day hands, neither of its Boss Media era
  (`BossToFpdb`) nor of its iPoker one (`iPokerToFpdb`, room `Win2day Poker`).
- Their `Game # ... - ` header is the B2B text family `EntractionToFpdb` reads.
  That parser knows only hold'em and Omaha, so the first file is refused as an
  unsupported game, and the second is not recognized at all. Both outcomes are
  tested in `tests/test_win2day_ipoker.py`.
- Sökö ranks a four-card flush and a four-card straight between two pair and
  one pair. fpdb has no evaluator for that order (poker-eval #316), so no
  parser may import Sökö as five-card stud.

A native, anonymized win2day Sökö hand (iPoker XML) is still needed before
Sökö can be supported.
