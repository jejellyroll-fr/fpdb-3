# ChampionPoker on the iPoker network

ChampionPoker is a crypto-oriented room on Playtech's iPoker network. Its
client writes the network's XML hand histories (`<session>`, `<game
gamecode=...>`), read by the shared iPoker parser; fpdb files its hands under a
room of their own:

| Room in fpdb | Network | Parser | Site id |
| --- | --- | --- | --- |
| `ChampionPoker` | iPoker (`IP`) | `iPokerToFpdb` / `iPokerSummary` | 152 |

- An iPoker file in a folder whose name contains `ChampionPoker` (one word or
  two, any case, joined by a space, `_` or `-`) is filed under `ChampionPoker`.
  A folder named only `champion` is not claimed.
- Elsewhere, as for every iPoker skin, the room is the one configured for its
  folder or for its hero's screen name.

## Status

- **A real cash session is in the test corpus**: PLO €0.02/€0.04 from client
  26.7.1.32, anonymized
  (`regression-test-files/cash/iPoker/Flop/PLO-EUR-0.02-0.04-202611.ChampionPoker.anonymous.seats.xml`).
  Its eight hands import with pots, rake and uncalled bets balanced. Five of
  them were played while the hero was not dealt in: the client lists those
  players as `Player <seat>`, and fpdb names them from the session's other
  hands, as on every iPoker skin.
- **No tournament export yet**: tournaments and their summaries are expected to
  follow the iPoker format but are not checked.
- **The client's folders are not confirmed.** fpdb ships the room off, with no
  folder, and its installed-sites detection does not look for it. Set the
  `ChampionPoker` hand-history and tournament-summary paths in *Sites* to the
  folders the client saves to.
- **HUD**: the iPoker network's policy applies, static HUD only. ChampionPoker's
  own rules on third-party HUDs have not been reviewed.
