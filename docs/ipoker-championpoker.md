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
- **Folder detection** (*Sites* > ChampionPoker > Detect):
  - **macOS** (confirmed on a real install): the client is the sandboxed
    *Championpoker Poker* app. Its hands are in
    `~/Library/Containers/com.championpoker.poker/Data/Library/Application Support/Championpoker Poker/<account>/History/Data/Tables`,
    its tournament summaries in `.../History/Data/Tournaments`. macOS lets
    fpdb check that folder but not list it: type your screen name in the card
    before clicking Detect, and give the app that runs fpdb *Full Disk Access*
    (System Settings > Privacy & Security), or nothing can be imported.
  - **Windows**: the classic iPoker layout,
    `%LOCALAPPDATA%\Championpoker Poker\data\<account>\History\Data\Tables`
    (also `ChampionPoker`, `Championpoker` and any folder of `%LOCALAPPDATA%`
    or `%APPDATA%` naming the brand, and the install folder its uninstall
    entry records). Not yet confirmed on a real Windows install.
  - The room still ships off with no folder, since the folders hold the
    account name.
- **HUD**: the iPoker network's policy applies, static HUD only. ChampionPoker's
  own rules on third-party HUDs have not been reviewed.
