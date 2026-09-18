# Board texture and runout features

`fpdb_3_legacy/board_features.py` classifies a board once, at import time, and
`BoardFeatures` stores the answer. The epic's example query —

```
flop A-high rainbow
```

— is therefore a `WHERE` clause rather than a re-classification of every hand
in range, and the same classifier is what AutoNotes reads when it writes "raises
c-bet on a wet flop" (#295).

## Where it lives

| Piece | What it owns |
| --- | --- |
| `board_features.py` | the flag catalogue, the classifier, the runout deltas, the AutoNotes projections |
| `BoardFeatures` table | one row per board and community street, written by the importer |
| `DerivedStats._assembleBoardFeatures` | calls the classifier once per hand and hands the rows to the importer |
| `Hands.texture` | the flop's texture mask, for the commonest filter of all (redefined, see below) |
| `AutoNotes` / `user_autonotes_parser` | their flop vocabulary, delegated to this module |

Nothing else decides what a board is. `AutoNotes._flop_texture` and the
`board.flop_texture` rule field both call `autonote_flop_texture` /
`autonote_flop_texture_word`, so a note and a filter cannot disagree about the
same flop.

## Two projections of one classification

A filter wants flags it can `&` together; a report wants names it can `GROUP BY`;
a popup wants a sentence. All three come out of the same functions:

* **`textureMask` / `runoutMask`** — orthogonal flags, one bit per fact. Bits are
  append-only: a stored mask has to keep meaning what it meant when written, so a
  flag may be added but never renumbered or reused.
* **`suitStructure`, `pairing`, `rankBucket`, `connectivity`** — the same
  classification as mutually exclusive words, because bit arithmetic is not a
  `GROUP BY` key and `1 << 4` is not a label.
* **`describe()`** — `"ace-high, rainbow, disconnected"`, with the runout flags
  appended after a `--` when a street changed something.

## The flags

**Texture, about the board as it stands:**

| Flag | True when |
| --- | --- |
| `rainbow` | a three-card board holds three suits |
| `two_tone` | exactly two cards of one suit |
| `monotone` | a three-card board holds one suit |
| `flush_possible` | the board holds three or more of a suit |
| `four_flush` | the board holds four or more of a suit |
| `unpaired` | every card a different rank |
| `paired` | some rank appears twice or more (also set by trips, quads, two pair) |
| `two_pair_board` | exactly two ranks are paired |
| `trips` | a rank appears exactly three times |
| `full_house_board` | a triple plus a separate pair |
| `quads` | a rank appears four times |
| `broadway_heavy` | three or more Broadway cards (T, J, Q, K, A) |
| `connected` | the board's ranks fit one five-rank window |
| `semi_connected` | some five-rank window holds three board ranks, but the whole board does not cluster |
| `disconnected` | no five-rank window holds three board ranks: no two hole cards make a straight |
| `four_straight` | four or more board ranks inside one five-rank window |

**Runout, about the cards the street just dealt** — every flag is about what to
do with the new card, which is what makes "what did the turn do" a query:

| Flag | True when |
| --- | --- |
| `runout_paired_board` | the new card paired a rank already on the board |
| `runout_flush_completed` | the new card is of the suit the board now holds three or more of — it opened the flush or deepened one that was already live |
| `runout_straight_completed` | the new card sits in a five-rank window that now holds three or more board ranks, so it is part of a straight draw, whether it opened it or joined one |
| `runout_overcard` | the new card is higher than every card of the previous board |
| `runout_undercard` | lower than every card of the previous board |
| `runout_brick` | none of the above: it paired nothing, brought no draw, and moved neither end of the board |

The split matters and is deliberate. *Depth* is a state and lives in the texture
mask (`four_flush`, `four_straight`); *the card's role* is a fact about one
street and lives in the runout mask. So a fourth heart on the river sets
`four_flush` (the board is a four-flush) and `runout_flush_completed` (the river
card is a flush card), while a blank that happens to be lower than the board sets
`runout_undercard` and nothing else.

`runout_brick` is defined by exclusion, so it can never be set beside another
runout flag — `test_board_features` asserts that over its whole table.

## The words

| Column | Values |
| --- | --- |
| `suitStructure` | `rainbow`, `two-tone`, `monotone` (three cards), `three-flush`, `four-flush` (four or five cards) |
| `pairing` | `unpaired`, `paired`, `two-pair`, `trips`, `full-house`, `quads` |
| `rankBucket` | from the highest board card: `ace-high`, `king-high`, `broadway` (T/Q/J-high), `middle` (8/9-high), `low` (7-high or lower) |
| `connectivity` | `connected`, `semi-connected`, `disconnected` |

An ace reads high or low but not both at once: `A-2-3` is `connected` with a span
of two, and the same three cards are an `ace-high` board. Wheel-aware rank
arithmetic is what keeps `A-2-3` and `7-6-5` in the same bucket of "the flop has
three to a straight" while `K-9-3` is `disconnected`.

## Columns and units

One row per board and community street, so at most three rows per Hold'em or
Omaha hand (stud, razz and the draw games deal no community cards and store
nothing):

| Column | Meaning |
| --- | --- |
| `handId` | foreign key to `Hands` |
| `boardId` | the run: 1 unless the hand was run several times, then 1..n |
| `street` | position of the street in the hand's own round list: 1 = flop, 3 = river |
| `streetName` | `flop`, `turn`, `river` — from the hand's own round names |
| `cardCount` | cards visible entering the street, i.e. the cumulative board |
| `textureMask`, `runoutMask` | the two flag sets |
| `topRank` | 2..14, the highest rank on the board |
| `suitStructure`, `pairing`, `rankBucket`, `connectivity` | the words above |

Cards are the pipeline's own two-character strings, ranks are 2..14, and there is
no money in this table at all: it is a dimension, not a result.

A hand run twice gets one board per run (`boardId`), because running it twice
deals onto numbered streets (`TURN1`/`TURN2`) while a shared flop keeps its plain
name. The fallback from `TURN2` to `TURN` is the one
`DerivedStats.getBoardsList` already uses to rebuild complete boards for equity,
so the two agree on what each run was dealt.

## Reading it

The five textures of the #308 corpus, in one query:

```sql
SELECT h.siteHandNo, bf.textureMask, bf.suitStructure, bf.pairing,
       bf.rankBucket, bf.connectivity
FROM BoardFeatures bf
JOIN Hands h ON h.id = bf.handId
WHERE bf.street = 1
ORDER BY h.siteHandNo;
```

Hands whose flop is an ace-high rainbow, using the mask rather than the words:

```sql
SELECT COUNT(*)
FROM BoardFeatures
WHERE street = 1
  AND textureMask & (1 << 0)   -- rainbow
  AND textureMask & (1 << 14)  -- disconnected
  AND rankBucket = 'ace-high';
```

Rivers that brought the flush:

```sql
SELECT COUNT(*)
FROM BoardFeatures
WHERE street = 3 AND runoutMask & (1 << 17);  -- runout_flush_completed
```

`Hands.texture` answers the first question without the join, which is why it
exists.

## `Hands.texture`, formally redefined

The column was declared `smallint` in the original schema and written `NULL` on
every hand ever imported: nothing derived it and nothing read it. It is now
**the flop's texture mask**, the same integer as `BoardFeatures.textureMask` for
`street = 1` on `boardId = 1`, and `0` means "no flop was dealt".

`0` is unambiguous because every three-card board sets at least a suit structure
flag (`rainbow`, `two-tone` or `monotone`), so "no feature" cannot be confused
with "no flop". `test_board_features` and the golden corpus both assert the two
columns agree.

Nothing in the codebase read the old NULL, so no caller changes. A third-party
reader that saw `NULL` now sees a mask; that is the point of redefining it rather
than leaving a dead column behind. The board features of *already imported* hands
need a rebuild to appear, which is #305's business, exactly as for the action
events of #293.

## Schema migration and indexes

The table is created with a fresh database and added to an existing one on its
next connection (`DatabaseSchemaMixin.ensure_feature_tables`, under the same
bounded lock wait as every other migration). Nothing is dropped and no rows are
rewritten; `DB_VERSION` is deliberately not bumped, because that flag means
"recreate and re-import everything".

Two indexes, and only two:

* `boardfeatures_hand_idx (handId)` — the join every drill-down and replayer read
  needs;
* `boardfeatures_texture_idx (textureMask)` — the commonest filter.

The word columns are low-cardinality names that a `GROUP BY` scans acceptably, so
they are left unindexed until #304 profiles a real database and shows otherwise.

## What is deliberately not here

* **Hand strength.** Whether a *player's* hand is a flush draw, a set or a
  blocker needs their hole cards and belongs to #302. This table is about the
  board alone, and never infers anything about the unknowns.
* **Opponent ranges.** No flag is derived from what anyone might hold.
* **Textures in the HUD.** No stat column reads these yet; #297 and #299 are
  where a filter and a popup start asking for them.
* **Rebuilding the past.** The backfill ships with #305, together with the rest
  of the derived-data lifecycle.

## What the tests check

`tests/test_board_features.py`:

* the flag catalogue is append-only, powers of two, and its two halves do not
  overlap through the `FLAG_NAMES`/`FLAG_BITS` round trip;
* cards arrive as strings, as the 1..52 integers the database stores, as
  `(rank, suit)` pairs and as every spelling of "no card", and all of them
  classify;
* seventeen reviewed boards cover the five corpus textures, both readings of an
  ace, the rank buckets at their boundaries, and each pairing from pair to quads;
* classification is order-free and repeatable: the same cards in any order give
  the same row;
* nine runout cases cover pairing, a flush opened and a flush deepened, a
  straight opened and a straight joined, overcard, undercard and brick, and that
  a brick is never raised beside anything else;
* the AutoNotes dict, the AutoNotes word and the custom-rule field all equal the
  shared classifier's output on the same cards;
* the DDL for all three backends, the insert statement and the in-memory upgrade
  agree column for column, and the bulk store fills a partial row from
  `BOARD_FEATURE_DEFAULTS`;
* a hand run twice carries one board per run, classified on its own cards.

`tests/test_analytics_golden_datasets.py` adds the corpus: every declaration in
the manifest's `board_features` block (thirty hands, one street at a time) is
checked against the stored row, every stored row is re-classified from the cards
a database-free parse produced for the same street, and the streets stored are
exactly the streets the hand dealt.
