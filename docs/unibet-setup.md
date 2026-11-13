# Unibet.fr (2026 client): hand history, Auto Import and HUD

This covers the 2026 Unibet.fr client (Relax Gaming, observed on
UnibetPoker v3.58.0). It is the `Unibet` site (id 30), not the historical
`Unibet Poker` iPoker skin (id 87): the two never share a converter.

## 1. Make the client write hand histories

The client saves one text file per table or tournament, and the tournament
summaries, to:

```
Documents/Unibet Poker/History/Exports/Automatic
```

on Windows and macOS (on Windows, OneDrive's `Documents` is found too). Hands
you request from the client's History tab go to the `Exports/Manual` folder:
Auto Import does not watch it, import those with *Bulk Import*.

Check that the folder fills up while you play before going further.

## 2. Auto Import

1. Open *Import → Auto Import*. fpdb's site detection offers the `Automatic`
   folder; if your client is installed elsewhere, add that folder yourself
   under the **Unibet** site, not Unibet Poker.
2. Start Auto Import. New hands are read as the client appends them, across
   several tables at once. Restarting fpdb resumes where it stopped, and a hand
   already in the database is never stored twice.
3. If the client recreates or truncates a file, fpdb re-reads it from the
   start; hands already stored are skipped.

Your hero is the player written with your account token,
`name[Unibet_<hex>]`. Power Spins are filed as lotteries.

## 3. HUD

The HUD finds a table's window by the id in its title, `Omaha - PL5 (99465067)`:
the table id for cash games, the tournament id for tournaments and Power Spins.
The lobby window, which carries no id, is ignored.

* **macOS** needs the permissions described in the main HUD guide: Screen
  Recording, or Automation for the AppleScript fallback.
* **Troubleshooting:** no HUD → check that Auto Import saw a hand from this
  table (the log names the file); HUD on the wrong table → check the window
  title still ends with an id in parentheses; no stats yet → the HUD shows
  after the first *completed* hand.

## What is verified

| | Status |
| --- | --- |
| Cash (NLHE, PLO), Banzai, Power Spins, summaries | parsed; golden-tested on anonymised real hands |
| Auto Import on macOS, several tables, restarts | verified live |
| HUD on macOS: cash, spins, several tables | verified live |
| File truncation / rotation | covered by a test (`tests/test_unibet_export_rotation.py`) |
| **Windows** HUD window detection | window-title matching is tested; **not yet validated with a real Windows client** |
| **Regular MTTs** | window title assumed to carry the tournament id as spins do; only spins tested live |
| HUD latency and CPU with many tables | **not measured** |

## Room rules

Unibet.fr's poker rules (read 13 November 2026) prohibit real-time assistance,
seating scripts and "software that compiles and analyses opponents' game data
(data mining)". They do not name trackers or HUDs. fpdb never advises an action
and never sends input to the client ([fair-play.md](fair-play.md)), but whether a
HUD on your own hands counts as data mining is the room's call, not ours: ask
Unibet's support, and keep dynamic panels off. The same page lists what else to
check. A tracker working on this client is not an authorisation.
