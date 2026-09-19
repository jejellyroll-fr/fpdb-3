# Postflop hand state: strength, draws, nutness, blockers (#302)

The analytics layers before this one describe the *action*: what happened
(#293), in what spot (#294), against what board (#295), for how much (#296).
This one describes the *hand*: what the player holding two known cards had on
the street they acted — and it stores the answer, one row per classified
decision, so a population can be composed by strength instead of by frequency.

| Piece | Module | Stored as |
| --- | --- | --- |
| The classifier | `fpdb_3_legacy/hand_state.py` | — |
| Its persistence | `fpdb_3_legacy/hand_state_store.py` | `HandStates` |
| Its composition | `fpdb_3_legacy/hand_state_composition.py` | — |
| Its CLI | `tools/hand_composition.py` | — |

```
uv run tools/hand_composition.py --dimension nutness --filter street=flop
uv run tools/hand_composition.py --dimension made_hand --as-of face_cbet --json
uv run tools/hand_composition.py --dimension draw --hands -        # the no-draw hands
uv run tools/hand_composition.py --dimensions
```

## The one rule this layer never breaks

**Unknown cards are never classified.** A hand history stores the cards of the
hero and of whoever reached a showdown; everyone else's are simply not in the
database. Those decisions get *no row at all* in `HandStates` — absence, not a
bucket — and the composition reports them as their own number:

```
Made hand composition: 35 classified decisions of 326 (10.7%), 291 not classified
```

Structural, not best-effort: `HandsPlayers.card1`/`card2` are zero for a player
who never showed, the classifier refuses a placeholder card, and no row is
written. A preflop decision has no row either — a hand state needs a board.
That is also why the `hand_state_known` filter is a `NULL` check and why a
composition of 26 flop decisions out of 56 says so.

## The classifier

`classify(hole_cards, board)` returns a frozen `HandState`: the street, the made
hand, its label, the pair detail, the draws, the nutness band and the blockers,
with the raw counts behind them. It refuses anything it cannot honestly
classify — fewer than three board cards, more than five, duplicate cards, a card
it cannot read, or a game whose hand this is (two Omaha cards are not a Hold'em
hand). `classify_known_cards(...)` returns `None` for unknown cards instead,
which is what the extractor uses.

The made hand comes from the project's own evaluator: `pokereval`
(`pypoker-eval`), the same library `equity` and `DerivedStats` use for all-in
equity, named through `Card.hands` and `Card.names`. There is deliberately no
second evaluator. When the native library cannot load, `classify` raises
`EvaluatorUnavailable` — deriving nothing is better than deriving something else.

### Made hand

`high_card`, `one_pair`, `two_pair`, `three_of_a_kind`, `straight`, `flush`,
`full_house`, `four_of_a_kind`, `straight_flush` — deterministic, because the
evaluator is. `made_hand_rank` is the position in that list.

### Pair detail

A pair's name is a statement about the board, so the board decides:

* the board's highest rank in the hole is **top pair**, its lowest is **bottom
  pair**, anything between is **middle pair**;
* a pocket pair above the whole board is an **overpair**, below it is a
  **pocket pair below the board** — very different hands;
* holding the pocket pair that hits the board is a **set**; holding the third
  card of a paired board is **trips**;
* with two pair, the higher pair decides **top two**, the lower decides
  **bottom two**, and a pair that is neither the board's highest nor its lowest
  is **middle two** — named rather than folded into a band it does not belong
  to. The board's own pairs count: kings over an aces-and-kings board is top
  two just as much as ace-king is.

A made hand with no pair detail (high card, straight, flush, quads) has
`NULL` — which the pair-detail dimension reports as a category of its own.

### Draws

Read off the ranks and suits that are visible, and only on the street being
played: **nothing draws on the river**, and a backdoor needs two cards to come,
so it exists only on the flop.

| Draw | Definition |
| --- | --- |
| `flush_draw` | four cards of one suit are visible, at least one in the hole |
| `nut_flush_draw` | a flush draw whose ace — the highest card of that suit — is in the hole |
| `backdoor_flush_draw` | on the flop, exactly three of one suit, at least one in the hole |
| `open_ended_straight_draw` | four consecutive ranks with **both** ends drawable |
| `gutshot` | exactly one rank completes a straight |
| `double_gutshot` | two or more completing ranks, without a live four-run |
| `backdoor_straight_draw` | on the flop, no draw yet but two ranks would complete a straight |
| `combo_draw` | a straight draw and a flush draw at once |

*Both ends* is what makes a draw open-ended rather than one-way: 8-9-T-J draws
to a seven or a queen; A-K-Q-J draws only to a ten and is a gutshot however
consecutive it looks. The low end of 2-3-4-5 is the ace, which plays there as it
does in a real wheel.

### Nutness

The bands are statements about **the hands an opponent can actually hold**, not
about a solver's range. On a board with `n` cards left over, every two-card
holding the deck allows is evaluated once (cached per board), and one player's
own two cards remove exactly 95 of them — so the denominator is the honest
C(47,2) = 1081 on a flop, 1035 on the turn, 990 on the river.

| Band | Definition |
| --- | --- |
| `nuts` | no available holding beats it |
| `near_nuts` | only the nuts beats it |
| `strong` | beats at least 90% of the available holdings |
| `medium` | beats at least 50% |
| `weak` | below that |

`nuts` and `near_nuts` are exact statements, and the raw `beats`/`holdings`
travel with every row, so a label can always be audited.

**Cost.** The per-board distribution is cached (`lru_cache(128)`), so a decision
costs ~0.2 ms once its board has been seen and ~1.1 ms when the board is new
(the 990–1176 evaluations). A board repeats across the players in a hand and
across hands on the same table, which is what makes the cache worth its
memory — a population of decisions is not paid for once per decision, and a
rebuild re-derives it per hand like every other subsystem.

Subtracting the player's own cards is not a detail: without it, quad aces on a
three-ace board came out as merely `strong`, because the best "opponent" hand the
evaluator could find was one holding the fourth ace — the one the player was
holding.

### Blockers

Each is a rule about the cards held, never about an opponent's range:

| Blocker | Rule |
| --- | --- |
| `nut_flush_blocker` | the ace of a suit that has at least three cards visible |
| `straight_blocker` | a hole rank that would complete a straight for the board's own ranks (the board's outs) |
| `paired_board_blocker` | a hole card matching a rank the board has paired — the card that blocks their quads and full houses |
| `overcard_blocker` | a hole card above every board card |

A straight blocker needs a board that is four cards into a straight; a three-card
board is nobody's out, so nothing is blocked there.

## The table

`HandStates` — one row per classified decision, keyed `(handId, actionNo)` like
`HandsActions` and `HandsSituations`:

```
handId, playerId, actionNo, street, streetName,
madeHand, madeHandRank, madeHandLabel, pairDetail,
drawsMask, nutness, nutnessBeats, nutnessHoldings, blockersMask,
stateVersion
```

The draws and blockers are **bitmasks** with the vocabulary in
`hand_state.DRAW_BITS` / `BLOCKER_BITS`, for the same reason the board texture
flags are (#295): one flat column answers "any of these" and "all of these" with
the same portable `&`, and the filter and the composition read the same bits.
The cards are deliberately *not* copied into the table — the board is on the
situation row it joins to and the hole cards on `HandsPlayers`, and a second copy
is a second truth.

In the query engine (#297), all of it is filterable and groupable:

```
--filter nutness=near_nuts      --filter draw=flush_draw,combo_draw
--filter draw_all=flush_draw,gutshot   --filter draw_none=true
--filter made_hand=two_pair     --filter pair_detail=top_two
--group-by made_hand            --group-by nutness
```

`hand_state_known=true/false` is the classified / not-classified split, and the
two are a partition of the population. `draw_none` and `blocker_none` exist
because "no draw at all" is the population a share of *something* has to be
subtracted from, and computing it as "classified minus the flags" would subtract
a decision with two draws twice.

A flag name from the wrong vocabulary is refused: `--filter draw=rainbow` is an
error, because `rainbow` is a board flag and the bits of two vocabularies are not
the same bits.

## Composition

`compose(db, query, dimension)` groups the query's population by one dimension
and reports each category with its count and its share of the **classified**
population (basis points, like every frequency in these layers):

* **partition** dimensions (`made_hand`, `made_hand_rank`, `nutness`,
  `hand_state_street`) add up to the classified population, exactly — the
  rounding remainder is allocated so the shares sum to 10000 rather than 10001;
* **subset** (`pair_detail`) has a bucket that is a real answer, not a gap;
* **multi** (`draw`, `blocker`) counts a decision under every flag it has, so the
  rows *overlap*, the shares sum to well over 100%, and the report says so.

Every count comes from `run_query` with the engine's own filter, one per flag for
a multi dimension — so a category's drill-down hands are the decisions the row
counted, by construction. `compose_hands(db, dimension, key)` returns them.

## Consumers

* the research browser (#303) groups a population by these dimensions and drills
  into the hands;
* `tools/hand_composition.py` is the same answer from a shell;
* the classifier's API (`classify`, `classify_known_cards`, `categories()`,
  `draw_definitions()`) is what AutoNotes and hand review call — it is a pure
  function of the cards, with no database and no session behind it.

## What is deliberately not here

* **Any inference of unknown cards.** A range for a hand nobody showed is a
  model, and this layer states facts.
* **Theoretical equity.** That is `equity`'s job; nutness here is a count of the
  hands the deck allows, not an equity calculation.
* **Multi-street state.** A row describes one street. A hand that was a draw on
  the flop and a pair on the river has two rows, and neither rewrites the other.
