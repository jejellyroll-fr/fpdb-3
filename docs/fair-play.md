# What fpdb does while you play

Rooms ban real-time assistance and limit which tools may run beside their
client. This page says, feature by feature, what fpdb does during play and
what it only does afterwards, so you can check it against your room's rules
before you risk your account. It is also written for room security teams.

**Your room's terms prevail.** This page describes fpdb; it does not say what
any room allows. Rules change, often without notice: read your room's current
terms, and ask its support or integrity team when a feature is not clearly
covered.

## What fpdb never does

- It never shows a recommended action: no "fold", "call" or "raise", no
  best-play hint, no colour that means "do this".
- It never computes a solver strategy, an equity or an ICM figure for the hand
  you are playing. Equity and EV figures are computed for finished hands, after
  import.
- It never sends a click, a keystroke or any other input to a poker client, and
  never opens, closes, seats or sits out at a table.
- It never sends your hands or statistics anywhere by itself. Your database
  stays on your machine (or on the database server you configured); sharing a
  hand is something you do, from the Replayer's *Share…*. The update check asks
  GitHub for the latest version number, nothing more.

The solver review is a manual export of a finished hand to a separate program,
started from the Replayer or a Hand Viewer. The HUD process cannot start it: a
test (`tests/test_fair_play_guard.py`) fails if anything the HUD loads can reach
the export, or if any fpdb module gains code that sends input to another
program.

## During play

| Feature | What it reads | What it shows |
| --- | --- | --- |
| **Auto Import** | The hand history files your room writes, as they appear | Nothing at the table; the hands go into your database |
| **HUD** (and FastHUD on fast-fold tables) | Your database; the operating system's list of windows, for each table's title and position | Statistics on the players at the table, computed from the hands in your database: rates such as VPIP or 3-bet, sample sizes, notes |
| **Popups** | Your database | More statistics on one player, when you click their HUD |
| **Auto Notes** | Your database | Notes on players, from rules you wrote, built from hands already imported |
| **Dynamic HUD panels** — off until you turn them on, and only in a room whose reviewed rules allow them: none yet | The current hand as fpdb knows it (see below) | Which group of a player's historical statistics shows, chosen by the situation: preflop, single-raised pot, facing a c-bet… |
| **Position panels** | The seat's position in the hand being played | Only in a room whose reviewed rules allow a positional HUD: none yet. Elsewhere every position panel shows, stacked |
| **Winamax live context** | Winamax's own client log, and the table's accessibility tree (the request a screen reader makes) | Seats and the current street, used to place the HUD; the street is not used to pick panels while Winamax has not approved them |
| **Session Guard** | Your imported hands | Your session's result, duration and hands, and an alert when a limit you set is reached. Informational only ([session-guard.md](session-guard.md)) |
| **Live capture** (SwC client tap, CoinPoker packets) — off until you turn it on, and kept in its own package | The client's own traffic | Nothing at the table: it turns the traffic into hands to import ([live-capture.md](live-capture.md)) |

Everything a HUD shows is a player's *history*: what they did in the hands your
database holds. Dynamic panels choose which part of that history to show, but
never show anything about the hand being played that the table does not already
show you. How live each source is, and what fpdb refuses to guess, is in
[the Dynamic HUD guide](hud-dynamic-guide.md#what-is-live-and-what-is-not).

Turning dynamic panels on asks first, with what the rooms below say about them,
and the HUD ignores panel rules until you have said yes, whatever wrote them: a
HUD package, the pack gallery or a hand edit of `HUD_config.xml`. The answer is
kept in `dynamic-panels-consent.json`, beside `HUD_config.xml`; deleting it
turns them off again, at the next update of a table already showing them.

A yes never overrides a room. fpdb decides, room by room and in code, whether
the HUD may show position-bound panels, dynamic panels and live context at its
tables, and a room nobody has reviewed gets the static HUD only. PokerStars on
every regional site, Winamax, the iPoker network under every skin's own name,
and every other room keep the static HUD today:
[what the HUD does in each room](hud-room-compatibility.md).

The All-in or Fold stat set includes averages of the equity and EV players had
in their *past* all-ins (EqK, EqR and their EV stats). They describe finished
hands, but a room that limits which statistics may show in game can still count
them: leave them out of your HUD there.

**Which hands are in your database matters.** The HUD's statistics come from
whatever you imported, including hands you did not play yourself (a bought or
shared database, a public dataset). Rooms that ban datamining, PokerStars and
Winamax among them, also ban using such hands: keep them out of the database
your HUD reads.

## After the session

These never run inside the HUD and have no view of the table:

- **Study Explorer, Research Browser, Range Explorer** — questions over your
  database.
- **Tournament research and ICM** — bubble factors and ICM figures for finished
  tournament hands ([icm.md](icm.md)).
- **Graphs, Replayer, Hand Viewer, leak detector, profitability and EV**.
- **Solver review** — exports one finished hand to
  [PreflopAdvisor](preflop-hand-review.md), a separate program, when you click
  *Solver review…*.

Some rooms forbid study tools, equity calculators or reference material *while
their client is running*, even with no table open. Where that is the rule,
close the client before opening these.

## Rooms

What each room's own page says, as we read it on **31 October 2026**. It is a
pointer, not advice: follow the link and read the current version.

| Room | Its rules | What concerns fpdb |
| --- | --- | --- |
| PokerStars | [Prohibited programs, tools and services](https://www.pokerstars.com/poker/room/prohibited/) | Statistics shown in game may come only from hands you played, and may not change automatically with the game state: fpdb never shows dynamic or position-bound panels at its tables. Equity, ICM and range tools, reference material and GTO solutions are prohibited while PokerStars runs, even with no table open. |
| Winamax | [Règlement poker](https://www.winamax.fr/cgu-poker?LICENSE=FR), "Aide extérieure au jeu" | Trackers that store your own statistics and the opponent statistics you gathered while playing are listed as allowed. Dynamic range software, equity and ICM calculators, solvers and "certain dynamic features of Hand2Note" are listed as prohibited. Anything not listed needs their prior approval: fpdb keeps dynamic and position-bound panels off at Winamax tables until its integrity team approves them. |
| iPoker (Betclic Poker, PMU Poker, FDJ Poker, Bet365.fr Poker, Barrière Poker, Unibet Poker and the other skins) | No official network page reviewed yet | Third-party HUD documentation reports positional and dynamic HUDs as not allowed on the network: fpdb keeps them off under every skin's name. |
| GGPoker | No official page found; [reported 18 October 2026](https://www.pokernews.com/news/2026/10/ggpoker-bans-huds-52622.htm) | Reported to prohibit all third-party poker software, HUDs included, while its client runs. Importing hand histories after the session is a separate question: check with GGPoker. |
| Unibet.fr | [Règlement poker Unibet.fr](https://xauth.unibet.fr/fr/document/4/poker/pdf?operateur=34), article on fair play (read 13 November 2026) | Prohibits real-time assistance (advice, actions, optimal-strategy calculators), "software compiling and analysing opponents' game data (data mining…)" and seating scripts. It does not name trackers or HUDs, and the client itself offers an optional opponent-tendency service. Whether an HUD that shows statistics from your own hands counts as data mining is **not stated: ask Unibet's support before relying on it**. Keep your database to hands you played. fpdb keeps dynamic and position-bound panels off at Unibet tables until Unibet confirms what it may do. Unibet may scan for running software. |
| CoinPoker | No official page found; [reported June 2026](https://www.pokerlistings.com/news/hud-is-done-coinpoker-updated-policies-for-third-party-tools-software) | Reported to prohibit HUD and tracking software while its client runs. fpdb's CoinPoker support is switched off. |
| Any other room | Its terms of service, often a "third-party tools" or "fair play" page | Check before using the HUD or a live capture. Until a room is reviewed, fpdb shows only the static HUD at its tables. |
