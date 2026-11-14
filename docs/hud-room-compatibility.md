# What the HUD does in each room

Rooms do not rule on "a HUD" as one thing. fpdb tells four capabilities apart,
and decides each one per room, in code
([`hud_room_policy.py`](../fpdb_3_legacy/hud_room_policy.py)):

| Capability | What it means | Changes with the hand being played? |
| --- | --- | --- |
| **Static HUD** | A player's historical statistics, in the grid or blocks of your profile | No |
| **Positional HUD** | Panels bound to a position (SB, BB, BTN…) shown only when the seat is in that position, with the profile's *Positional panels* set to *Only current position* | Yes: the panel changes as the button moves |
| **Dynamic panels** | Which panels show is chosen by the situation: preflop, single-raised pot, facing a c-bet… ([guide](hud-dynamic-guide.md)) | Yes |
| **Live context** | The situation is read from a live source during the hand, rather than from the last imported hand | Yes, within the hand |

Each one changes more with the hand than the one before, so a room that allows
dynamic panels allows a positional HUD, and live context only ever feeds
dynamic panels.

## Room by room

What fpdb does today. **Your room's terms prevail**: this table says what fpdb
allows itself, not what a room permits. The room's own words, and links to
them, are in [what fpdb does while you play](fair-play.md#rooms).

| Room | Static | Positional | Dynamic | Live context | Why |
| --- | --- | --- | --- | --- | --- |
| PokerStars, every regional site (.FR, .ES, .COM, .DE…) | ✔ | — | — | — | Forbids in-game statistics that change automatically with the game state |
| Winamax | ✔ | — | — | — | Prohibits dynamic range software and certain dynamic HUD features; off until its integrity team approves fpdb's |
| iPoker network, under every skin's own name (Betclic Poker, PMU Poker, FDJ Poker, Bet365.fr Poker, Barrière Poker, Unibet Poker…) | ✔ | — | — | — | Positional and dynamic HUDs documented as not allowed on the network |
| Unibet (the 2026 Relax Gaming client, Unibet.fr) | ✔ | — | — | — | Not reviewed: its rules do not mention HUDs, see below |
| Any other room (GGPoker, CoinPoker, WPN/ACR…) | ✔ | — | — | — | Not reviewed: the conservative default |

No room is reviewed as allowing more than the static HUD yet, so **every live
table shows the static HUD**. A room moves to a more permissive row only once
its rules have been read and, where they are unclear, confirmed by the room
itself; a third-party tool's compatibility page is not a room's authorization.

GGPoker and CoinPoker are reported to prohibit HUDs altogether. fpdb keeps their
static HUD available and says so in [fair-play.md](fair-play.md#rooms): the
decision to run one there is yours.

### What a restricted table shows

- **Position panels** are all shown, stacked, as if the profile's *Positional
  panels* were set to *Show all (stacked)*. What a seat displays then does not
  change from one hand to the next. Blocks with no position binding are not
  affected.
- **Dynamic panels** are not resolved: the HUD keeps the profile's static grid.
- **Live sources** (the Winamax log reader, a live capture) may still run, for
  table and seat identification, but nothing they say about the hand in
  progress is used.

Nothing in the configuration lifts a restriction: not the dynamic panels
consent, a HUD package, the pack gallery, a profile switch or a hand edit of
`HUD_config.xml`. A site's `network` attribute in `HUD_config.xml` can make it
*more* restricted, never less. The HUD asks the policy on every update, so a
change applies to tables already open.

Offline, nothing is restricted: Preferences ▸ HUD ▸ Dynamic Panels can set up
and preview panel rules whatever room you play.

## Where the context comes from

Where dynamic panels are allowed, how current they are depends on the source:

- **Live action** — a source that publishes action by action: panels follow the
  current decision.
- **Live street** — the Winamax client log: flop, turn and river as they are
  dealt, and the preflop pot type; not which bet a player faces.
- **Hand refresh** — every other room: the last *assembled* hand. The panels
  change when the hand is imported, not mid-action, and fpdb never presents
  this as live.

A fact the source does not establish stays unknown: rules that need it do not
match, and it is never inferred from a player's historical statistics.

## Unibet.fr

The current client is the `Unibet` site (id 30); `Unibet Poker` (id 87) is the
historical iPoker skin and follows the iPoker row. Hand histories, Auto Import
and the static HUD work ([setup](unibet-setup.md)).

Its rules in force from 21 October 2026 do not mention HUDs. They prohibit
real-time decision assistance and software that compiles and analyses
opponents' game data, and the client offers its own optional opponent-tendency
tool. Hand2Note documents dynamic and positional HUDs on the French pool, but
that is a vendor's statement, not Unibet's. **Positional and dynamic panels stay
off at Unibet tables until Unibet confirms what fpdb may do.** fpdb also cannot
yet tell a Unibet.fr table from an international Unibet one, which a permissive
Unibet.fr policy would need first.
