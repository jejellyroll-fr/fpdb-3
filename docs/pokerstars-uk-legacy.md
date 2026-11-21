# PokerStars.UK: historical imports only

The standalone **PokerStars UK** client was retired on **7 October 2026**, when
its players moved to **PokerStars on Betfair**. fpdb keeps the hands that client
dealt in a legacy room of their own, **PokerStars.UK** (site 145), apart from
PokerStars.COM and from PokerStars on Betfair (site 143, #733). Nothing live is
supported: there is no client left to play on.

## What files a hand under PokerStars.UK

A UK history is an ordinary PokerStars history: no line in it names the skin.
fpdb only files a hand under PokerStars.UK when its provenance says so:

1. **The client's folder.** A file read from a `PokerStars.UK` folder, for
   instance `%LOCALAPPDATA%\PokerStars.UK\HandHistory\<you>\` or
   `...\PokerStars.UK\TournSummary\<you>\`, under Windows or Wine. The folder
   name must match whole: a screen name or Windows user that merely contains
   `PokerStars.UK` does not count. The installed-sites detector looks for this
   folder on Windows and Wine; no macOS folder name is known, so none is
   guessed.
2. **An explicit hero mapping**, for files copied out of that folder. Map the
   screen name in `pokerstars_skin_mapping.conf`, next to `PokerStarsToFpdb.py`:

   ```ini
   [hero_mapping]
   yourname = PokerStars.UK
   ```

   The mapping files every hand that screen name was dealt, so use it only on
   files you know came from the UK client.

Either way, **a hand dated after 7 October 2026 is never filed under
PokerStars.UK**: the client no longer existed. UK players kept their screen
names at PokerStars on Betfair, so neither a mapping nor a folder those later
hands were saved into can move them here. A hand is judged by the earliest date
in its header, so a late-evening hand whose local date has already turned is
still the UK client's.

## What never does

- **GBP stakes.** PokerStars.COM and PokerStars on Betfair players play in GBP
  too. A GBP hand outside the UK folder stays where it would have gone before
  (PokerStars.COM by default).
- **A screen name** ending in `.uk`, `_uk` or the like.
- **An ordinary `PokerStars Hand #` header**, which every PokerStars client writes.

## Hands already in the database

Nothing is moved. Hands imported before this room existed stay under
PokerStars.COM (or wherever they were filed): fpdb has no reliable way to tell
which of them came from the UK client. To file them under PokerStars.UK,
re-import them from the client's folder, or with a hero mapping, into a fresh
database.

An existing database gains the PokerStars.UK `Sites` row the next time fpdb
connects to it; a new one is created with it.

## Evidence

No authentic, privacy-safe UK export is in the regression corpus yet. The tests
in `tests/test_pokerstars_uk.py` run PokerStars' own fixtures from a UK folder:
they pin how hands are **filed**, not that every UK-specific line is read. Real
UK cash histories, tournament histories and tournament summaries are welcome
(#889).

The `PokerStars.UK` folder name is the one UK players reported for the client's
histories and summaries; the 7 October 2026 date is PokerStars' own migration
notice.
