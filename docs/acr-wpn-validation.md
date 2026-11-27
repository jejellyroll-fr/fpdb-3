# ACR / WPN validation record

This runbook prepares the two external checks still open in
[issue #719](https://github.com/jejellyroll-fr/fpdb-3/issues/719). The safeguards
and regression coverage are already in `development` through #808, #815 and
#820. This document does not claim that ACR has approved fpdb or that the live
HUD has been checked. The [ACR Security & Game Integrity Policies](https://www.acrpoker.eu/security/)
were reviewed on 27 November 2026; confirm the live wording again before
relying on it.

## Written clarification from ACR / WPN

Send the questions below to ACR/WPN support or the game-integrity team. Keep the response, date and support reference with the issue; do not paraphrase an ambiguous answer as approval. Ask whether the answer applies across the WPN network and all skins (Americas Cardroom, BlackChipPoker, TruePoker, Ya Poker and WinningPoker).

### Request text

> Hello,
>
> I am checking the third-party software rules for ACR / Winning Poker Network.
The [Security & Game Integrity Policies](https://www.acrpoker.eu/security/)
appear to say both that certain third-party tools are prohibited (§4.3.0) and
that a HUD displaying numeric statistics from hands the player personally
played is allowed (§4.1.3). Could you clarify how these sections apply together
to fpdb, an open-source hand-history tracker?
>
> In particular:
>
> 1. Is a static HUD showing only historical numeric statistics from completed hands in which that same player participated permitted under §4.1.3, notwithstanding §4.3.0?
> 2. Does §4.2.11 prohibit a separate HUD window placed over the table area if
   it does not cover, replace or alter any ACR table graphics, cards, controls
   or security indicators? Is placement beside the table required?
> 3. Would a panel that selects among historical statistics based on the
   current table situation be prohibited even when it reveals no current-hand
   information? fpdb currently disables dynamic and position-bound panels at
   WPN tables.
> 4. Are these answers the same for every WPN skin, and are there client
   versions, table formats or other conditions that change them?
>
> Please point me to the applicable current policy text and confirm the date or version of your answer. I will treat anything not explicitly confirmed as unresolved.

### Response record

| Field | Record |
| --- | --- |
| Date sent (UTC) | Not sent |
| Channel / ticket reference | Pending |
| Responding team | Pending |
| Date received (UTC) | Pending |
| Response URL or saved reference | Pending |
| Exact response or faithful excerpt | Pending |
| Scope / skins covered | Pending |
| Follow-up needed | Pending |
| Status | **Pending ACR clarification** |

When an answer arrives, preserve its exact wording and link. Update `docs/fair-play.md` only with what the response explicitly covers; retain unresolved questions as pending. Do not use “ACR-approved” or “certified” unless ACR uses that wording expressly.

## Real-table HUD placement check

Run this check on tables and client layouts the maintainer can access. A passing result applies only to the recorded skin, client version, display setup and layout. Repeat it when any of those materially changes. Do not treat a simulator or screenshot mock-up as a real-table check.

For every WPN skin in scope, check both a cash table and a tournament table at the client's default size and at a resized size. Check the static HUD and open each popup type that can appear from it. At each size, confirm that no HUD window or popup covers or obscures:

- cards or card backs;
- action buttons or other controls;
- the pot, bets or stack amounts;
- native table graphics, labels or security / anti-bot indicators.

If any item is covered, record **Fail**, move the HUD clear of the native graphics, and repeat the affected case. Do not try to hide or alter a room security indicator.

### Run metadata

| Field | Record |
| --- | --- |
| Check date and time (UTC) | Not run |
| Tester | Pending |
| fpdb version / commit | Pending |
| Operating system | Pending |
| Display resolution and scaling | Pending |
| WPN client / skin and version | Pending |
| HUD profile and layout | Pending |
| Evidence reference (redact account and hand details) | Pending |

### Results

Create one row per combination. Use **Not run**, **Pass** or **Fail**; do not infer a pass from a different layout.

| Skin | Table type | Size / scaling | HUD blocks clear | Popups clear | Native indicators clear | Result / notes |
| --- | --- | --- | --- | --- | --- | --- |
| Americas Cardroom | Cash | Default | Not run | Not run | Not run | Pending |
| Americas Cardroom | Cash | Resized | Not run | Not run | Not run | Pending |
| Americas Cardroom | Tournament | Default | Not run | Not run | Not run | Pending |
| Americas Cardroom | Tournament | Resized | Not run | Not run | Not run | Pending |
| BlackChipPoker | Cash | Default | Not run | Not run | Not run | Pending |
| BlackChipPoker | Cash | Resized | Not run | Not run | Not run | Pending |
| BlackChipPoker | Tournament | Default | Not run | Not run | Not run | Pending |
| BlackChipPoker | Tournament | Resized | Not run | Not run | Not run | Pending |
| TruePoker | Cash | Default | Not run | Not run | Not run | Pending |
| TruePoker | Cash | Resized | Not run | Not run | Not run | Pending |
| TruePoker | Tournament | Default | Not run | Not run | Not run | Pending |
| TruePoker | Tournament | Resized | Not run | Not run | Not run | Pending |
| Ya Poker | Cash | Default | Not run | Not run | Not run | Pending |
| Ya Poker | Cash | Resized | Not run | Not run | Not run | Pending |
| Ya Poker | Tournament | Default | Not run | Not run | Not run | Pending |
| Ya Poker | Tournament | Resized | Not run | Not run | Not run | Pending |
| WinningPoker | Cash | Default | Not run | Not run | Not run | Pending |
| WinningPoker | Cash | Resized | Not run | Not run | Not run | Pending |
| WinningPoker | Tournament | Default | Not run | Not run | Not run | Pending |
| WinningPoker | Tournament | Resized | Not run | Not run | Not run | Pending |

## Issue status

The documentation and automated tests cover the software-side safeguards, including exclusion of the hand in progress. The written policy clarification and real-table placement results remain external checks and must be recorded before issue #719 can be considered fully closed.
