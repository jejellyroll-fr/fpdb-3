# win2day on the iPoker network, and Sökö

win2day, the Austrian lottery's online casino, opened its poker room in **2008
on Boss Media** and moved to **Playtech's iPoker network** (agreement in 2015,
cross-border pool in 2017). The two eras write different files, and fpdb keeps
them apart by **format**, never by room name:

| Era | Files | Parser | Room in fpdb | Site id |
| --- | --- | --- | --- | --- |
| Boss Media (2008 to the move) | `<HISTORY ID="..." SESSION=...>` | `BossToFpdb` | `Boss` | 4 |
| iPoker (since the move) | iPoker XML (`<session>`, `<game gamecode=...>`) | `iPokerToFpdb` | `Win2day Poker` | 151 |

- A Boss Media file is read as Boss wherever it is kept, a win2day folder
  included; the `Win2day` alias still names the Boss parser.
- An iPoker file in a folder whose name contains `win2day` is filed under
  `Win2day Poker`. Elsewhere, as for every iPoker skin, the room is the one
  configured for its folder or for its hero's screen name.
- Neither parser identifies the other era's files, so there is no fallback
  from one to the other.

## Status

- **No authentic win2day iPoker export is in the test corpus yet.** The tests
  run iPoker's own fixtures from a folder naming win2day: they check how hands
  are *filed*, and that the shared iPoker parser reads them.
- **The client's folders are not confirmed.** fpdb ships the room off, with no
  folder, and its installed-sites detection does not look for it. Set the
  `Win2day Poker` hand-history and tournament-summary paths in *Sites* to the
  folders the client saves to (Wine on Linux included).
- **HUD**: the iPoker network's policy applies, static HUD only. win2day's own
  rules on third-party HUDs have not been reviewed; a HUD built into the client
  is no permission for another one.
- win2day's GDPR/CSV account exports are not hand histories and are not
  imported.

## Sökö is refused

win2day deals **Pot Limit Sökö**, a Finnish five-card stud. Its rules rank a
**four-card flush** and a **four-card straight** between two pair and one pair.
fpdb has no evaluator for that order (poker-eval #316): read as ordinary
five-card stud its winners, hand names and results would be wrong without a
warning. Until now a Sökö `<gametype>` was read with no game at all (no
base, no category), left for later steps to trip over.

So a session whose `<gametype>` names Sökö (`Sökö`, `Soko`, `Soekoe`, or the
same with mangled umlauts) is **refused with an error**, every hand of it, and
nothing is stored. Supporting it needs a native, anonymized win2day Sökö export
(full actions, showdown and pots), a distinct game category and its own
evaluator.

The two 2005 Sökö excerpts in `regression-test-files/unsupported-sites/soko/`
predate win2day Poker: they are B2B-era text of the family `EntractionToFpdb`
reads, not win2day hands of either era. The first is refused as an unsupported
game; the second, posted without a header, is recognized by no parser. See the
folder's README for their provenance.

Tests: `tests/test_win2day_ipoker.py`.
