# Native SwC Poker capture on macOS

The downloaded SwC macOS client does not write hand-history files for every
game family. Stud, draw, mixed games such as Drawmaha, and OFC therefore need a
capture path independent from the normal FPDB auto-import directory.

## Why this capture path

The SwC 2.0 macOS application is a native x86_64 Qt client. It connects to the
lobby on TCP 20001 and assigns tables to varying game-server ports (observed
20013 and 20020) using its bundled OpenSSL 1.0.
Packet capture sees encrypted TLS and requires elevated BPF access. The client
binary is unsigned and imports `SSL_read` and `SSL_write` directly, so FPDB can
passively observe plaintext after decryption without modifying the application
bundle or network traffic.

The tap defaults are intentionally narrow:

- server-to-client data only;
- SWC game-server ports are detected automatically;
- archive permissions `0600` under `~/.fpdb/swc-native-capture`;
- the lobby/login port 20001 is explicitly excluded.

Outbound capture is diagnostic-only because it can contain session-sensitive
messages.

## Build and run

First close SwC normally. An already-running process cannot inherit the tap.
The launcher also removes terminal `LANG`/`LC_*` variables because the older
Qt/C++ runtime bundled by SwC otherwise aborts while parsing decimal skin
values. This mirrors the environment used when the application starts from
Finder.

```bash
uv run python fpdb_3_legacy/swc_native_capture.py --build
uv run python fpdb_3_legacy/swc_native_capture.py
```

New native dealer messages are printed live with an `[SWC]` prefix. Qt window
diagnostics may still appear on stderr; they are unrelated to the capture.

Play one complete hand, close SwC normally, then validate the archive:

```bash
uv run python fpdb_3_legacy/swc_native_capture.py \
  --inspect ~/.fpdb/swc-native-capture/swc-native.raw
```

Dealer messages can be rendered separately while native state-snapshot decoding
is being developed:

```bash
uv run python fpdb_3_legacy/swc_native_capture.py \
  --dealer-history ~/.fpdb/swc-native-capture/swc-native.raw
```

Stable table ids, hand ids, round numbers, player identities, and snapshot
counts can be inspected without guessing undecoded action fields:

```bash
uv run python fpdb_3_legacy/swc_native_capture.py \
  --session-summary ~/.fpdb/swc-native-capture/swc-native.raw
```

Opaque changes in the native player-funds field can be inspected separately.
They are useful for correlating a seat with a player, but they are not monetary
amounts and must not be used as bets, stacks, or collections:

```bash
uv run python fpdb_3_legacy/swc_native_capture.py \
  --stack-history ~/.fpdb/swc-native-capture/swc-native.raw
```

The class-22 snapshot suffix also carries native animation events. These are
useful evidence for action decoding, but they are still reported as native
fields rather than FPDB actions:

```bash
uv run python fpdb_3_legacy/swc_native_capture.py \
  --animation-events ~/.fpdb/swc-native-capture/swc-native.raw
```

The confirmed fields can also be rendered as FPDB-aligned capture envelopes.
They include raw payload hashes, snapshot diffs, and per-snapshot native
animation events, but remain explicitly `capture_only`:

```bash
uv run python fpdb_3_legacy/swc_native_capture.py \
  --normalized-json ~/.fpdb/swc-native-capture/swc-native.raw
```

The archive is an append-only sequence of records. Each record preserves its
timestamp, direction, peer port, and the exact plaintext buffer returned by
OpenSSL. Do not publish an archive without reviewing it for player or session
data.

The adjacent `swc-native.status` file contains `tap-loaded` when dyld loaded
the interposer successfully. This separates injection failures from sessions
where no matching game-server buffer was received.

## Confirmed protocol fields

The native stream uses unsigned 32-bit little-endian message framing. Message
class 34 supplies table name/id and tournament id; class 22 supplies state
snapshots. Across the captured Hold'em, Omaha, OFC, and tournament sessions,
the snapshot decoder has confirmed hand id, table id, round number, and each
length-prefixed player id/name. The full payload remains attached to every
snapshot while the variable card/action suffix is decoded.

Observed Hold'em and Omaha round values are `0` reset, `1` preflop, `2` flop,
`3` turn, `4` river, `5` showdown, and `6` settlement. Player records contain
an opaque three-byte funds value and have two observed
layouts because an optional byte precedes their flag word; the decoder anchors
the value relative to that flag word. Its changes do not match the known blind
amounts, so normalized metadata explicitly marks it as non-monetary. A unique
decrease aligned with one type-9 event was tested as player evidence, then
rejected: in complete Hold'em hand `298328340` it produces an action sequence
whose apparent winner contradicts the explicit Dealer settlement.

Native type-15 settlement events are decoded separately. They provide the
winner roster index/name and the exact integer from `<money a="…">`; normalized hands
store it as `amount_native`. The same tag proves the settlement scale:
real-money marker `mt="R"` uses 100 native units per displayed unit (`120` →
`1.20`, `280` → `2.80`, `48` → `0.48`), while tournament marker `mt="T"`
uses one (`125` → `125`, `325` → `325`). Collections also preserve
`amount_displayed`, `money_type`, and `native_units_per_display_unit`. This
scale is not applied to action bytes until their full-width encoding is
confirmed.

Snapshot player order is exposed as `roster_index`, never as an FPDB seat.
Likewise, type-15 `<nick s="…">` is `player_index`; all four captured examples
match the winner's roster position. Both normalized player and collection
`seat_idx` fields remain null until the separate animation/table-seat mapping
is decoded.

Normalized animation and action evidence likewise exposes the raw fourth byte
as `native_index`; `seat_idx` stays null even when a player identity is proven.
The client changes other candidate index bytes during a hand, so physical table
seat semantics are not claimed.

Dealer-chat winner lines are correlated with the latest native hand id already
observed on the same table. They supplement type-15 events only when the same
player/native amount is absent and carry `seat_idx: null` rather than inventing
a seat. On `test3.raw`, this recovers 11 additional exact settlements, bringing
settlement coverage from 4 to 15 of 24 normalized hands. Parenthesized
Hold'em/Omaha winner lines are accepted; OFC summary lines use a different
grammar and remain outside this settlement path.

Dealer lines shaped `Uncalled bet (…) returned to …` are stored separately in
the normalized `returned` array with the same exact cash/tournament scaling.
They are not collections and are not silently subtracted from action amounts;
future pot construction can apply them explicitly.

For cash games only, a returned amount can anchor a player to a native action
index when the final type-9 bet has the identical native byte. This proves
`index 8 → unebu` in Hold'em hand `298328340` and `index 0 → CAAD1` in PLO hand
`298328350`. Raises and tournament bytes are excluded from this rule.

A no-show winner supplies a second conservative anchor when every dealt index
has exactly the expected number of type-1 events (two Hold'em, four Omaha,
five Drawmaha), all fold indices are removed, and exactly one dealt index
remains. Ambiguous or showdown hands do not use this elimination.

Other in-hand Dealer lines are retained chronologically in `dealer_events`,
including timeouts and `Hand complete`. The audit exposes the latter as
`dealer_hand_complete`; timeout text is evidence only because captured examples
do not map unambiguously to an adjacent fold action.

The exact Hold'em/Omaha line `New hand started` is also retained and exposed as
`dealer_hand_started`. Numbered OFC lines (`New hand started (n of m)`) have a
different ordering and are deliberately excluded from this start marker.

Observed native animation-event lists are encoded as a little-endian event
count followed by compact records. Type 9 carries action-like bytes in the
shape `type/action/funds/seat` plus zero card-mnemonic bytes, and type 15
carries the dealer table message text. The capture for `test3.raw` currently
decodes 952 ordered animation events across 255 snapshots. Type-9 `funds` values match observed cash blinds
(`2`/`4` displays as `0.02`/`0.04`), while type-15 winner amounts preserve the
exact native integer and formatted dealer text. Actions remain capture evidence
until seat coverage and every amount rule are validated.

Variable type-10 events now preserve and decode evaluated-card mnemonics. For
example, `D.47;46;45;26;24.O.H` becomes `Ks Kh Kd 8h 8c`, matching the dealer's
full-house description. This is showdown-combination evidence; it is not yet
split into board and private cards.

Hold'em/Omaha snapshots also expose the cumulative community board immediately
before the table footer. The observed PLO hand progresses from `9h 8c 5h` to
`9h 8c 5h Ks`, then `9h 8c 5h Ks Kh`; the normalized step `board` field now
contains these confirmed cards.

When a hand has exactly one native winner and one evaluated type-10
combination, the decoder also derives only the private cards actually used by
subtracting the board as a multiset. The confirmed PLO example yields `Kd 8h`
for CAAD1. This does not claim the player's complete four-card Omaha hand.

The normalized evidence labels the confirmed native action codes (`1` fold,
`2` check, `3` call, `6` small blind, `7` big blind, `8` bet, `9` raise). On
`test3.raw` contains 242 type-9 events, including 183 carrying a confirmed
poker action code. Returned-bet and unique foldout-winner anchors prove a
player for 13 type-9 events and 10 recognized poker actions. All others retain
their native index, code, funds byte, and raw bytes without an invented player.

The type-9 funds field is preserved as `funds_byte`, not as an FPDB amount.
Small cash blinds happen to match their native units, but hand `298328344`
contains a final bet byte of `80` followed by an exact return of `48`, proving
that direct amount semantics do not generalize. No action byte is summed into a
pot or labelled contribution/raise-to.

When an unknown animation prevents decoding the enclosing list, one uniquely
shaped 12-byte type-9 record can still be retained. This recovers observed
calls to 16, a bet of 80, and a call of 20 that were formerly hidden in
`test3.raw`.

Auxiliary animation types 1, 2, 3, and 25 have an observed fixed four-byte
shape. Their poker meaning remains intentionally unnamed, but decoding their
length restores complete event lists and preserves their exact order.

For Hold'em/Omaha, type 1 is confirmed as the private-card deal animation: it
appears twice per active Hold'em seat and four times per active Omaha seat.
Type 2 appears three times on the flop and once on both turn and river, while
type 3 opens that community-card transition. A type-9 action preceding these
events is therefore assigned to the previous FPDB street in normalized
evidence.

The normalized `action_evidence` chronology requires both a proven player and
native action label. It currently contains only the six returned-bet-anchored
actions; all ordered native events stay in `steps[].native_events`. The FPDB
`actions` array remains empty until player identity and amount semantics are
complete for the entire hand.

An evidence audit can be printed without expanding the full normalized JSON:

```bash
uv run python fpdb_3_legacy/swc_native_capture.py \
  --importability-audit ~/.fpdb/swc-native-capture/test3.raw
```

For every hand it reports resolved/total native player correlations,
resolved/total poker actions, unresolved action labels, observed blinds, and
settlement. The same fields live under
`metadata.importability` in normalized JSON. A hand remains `capture_only` if
even one player attribution is unresolved or its beginning/settlement is not
present; this also makes captures that started mid-hand explicit.

The player flag word exposes an observed active-player bit, but it is not used
as seat evidence. Pairing it with type 6 or type 9 produces contradictions, so
neither animation index can safely be treated as a stable player seat.

The complete observed native status byte is also preserved per player as
`native_status_values`. Only bit `0x40` currently has a confirmed meaning; the
other bits remain raw evidence until positive and negative examples establish
their semantics.

The former funds-based propagation and within-hand elimination experiments are
retained only in private diagnostic code; normalized output does not consume
them.

## Importability policy

Capturing a game does not make it importable. Raw captures are decoded into the
existing SwC normalization envelope first. A variant is enabled for `Hand.py`
only when actions, forced bets, street transitions, cards, collections, and
settlement can be represented truthfully. OFC and incomplete mixed-game hands
remain `capture_only`.

OFC Dealer lines shaped `Hand #n finished - player: ±points` and `TOTAL - …`
are decoded into `ofc_result` and `ofc_total`. Signed point values and the OFC
hand number are preserved exactly; they are scoring evidence, not Hold'em-style
actions or monetary collections.

A compact JSON-lines export avoids parsing the full snapshot envelope:

```bash
uv run python fpdb_3_legacy/swc_native_capture.py \
  --ofc-summary ~/.fpdb/swc-native-capture/test3.raw
```

Each line includes table/hand ids, resolved variant, hand scores, totals,
fantasy land, payouts, session start/completion markers, and the evaluated
showdown rows described below.

The OFC settlement snapshot reveals each shown board as evaluated rows shaped
`<X>.<card;ids>.<Y>.<Z>` (for example `H.42;19;16;14;13.M.H` decodes to
`Qh 6s 6c 5h 5d`). The richest such snapshot is decoded into `ofc_showdown_rows`:
each row keeps its exact cards and card count, and a three-card row is labelled
`row: top` because an OFC top row is always three cards. Five-card rows keep
`row: null` — middle and bottom are not distinguished, and rows are not grouped
into per-player boards, because the token order does not reliably match player
identity (grouping a captured example sequentially produces fouled boards and
dealer descriptions that contradict the assignment). The decode is rejected
outright if any card id repeats across rows, guarding against false-positive
byte matches. These rows are showdown-card evidence only; OFC stays
`capture_only` and no seat or per-round placement is claimed.

Final OFC lines shaped `player wins 82.56` are stored in `ofc_payouts` with
their exact two-decimal cash value and 100-unit scale. They remain separate
from per-hand point scores and ordinary poker collections.

Fantasy-land transitions are stored per player in `ofc_fantasy_land`, including
the explicit rule that the button is not moved. The captured table payloads use
opaque names (`Scimitar #3`, `Attard #1`) and contain no Pineapple marker, so
the name alone does not identify the variant. Attard nevertheless has a repeated
five-card initial deal followed by three-card deals in rounds 1–4, proving
`ofc_variant: pineapple`. Scimitar remains `unresolved` because its capture
begins at the end. Type-1 events are labelled `ofc_card_deal` and native action
code 21 is retained as OFC `turn_commit` evidence; the final placed rows are
decoded at settlement (see `ofc_showdown_rows` below), but the per-round
placement sequence and the discarded Pineapple card are not.

An explicit `Game complete, n hands played` marker is stored as
`ofc_game_complete` on the final captured hand, preserving the session hand
count independently from scores and payouts.

`New game started (n hands)` arrives before the first snapshot and is queued
until that next hand id, then stored as `ofc_game_start.planned_hands`. It is an
initial plan rather than an expected final count because fantasy land can add
hands to the session.

The captured table `No-Rake Micro Stakes 2-7 Single Draw` maps to FPDB
`base=draw`, `category=27_1draw`, `limitType=nl` with streets
`BLINDSANTES/DEAL/DRAWONE`. Its archive contains only one empty round-0
snapshot and no played hand, so no Draw action or discard semantics are claimed.

`Drawmaha` is classified separately as FPDB `base=draw`,
`category=drawmaha`, with the existing five-street DrawHand profile. Its limit
type remains unknown and its four captured hands remain `capture_only`; the
generic word `draw` no longer misclassifies them as 2-7 Single Draw.

Observed Drawmaha native rounds map as `0` blinds, `1` deal/first action round,
`2` `DRAWONE`, `3` `DRAWTWO`, `4` `DRAWTHREE`, `6` showdown, and `7`
settlement. Three complete captured hands end during round 1; the only round
3/4 hand starts mid-hand. Street placement is therefore available; per-player
draw counts are decoded from the dealer draw lines (see below) when present,
while the specific discarded and replacement cards remain undecoded.

The five-card deal count plus a unique no-show survivor identifies five
Drawmaha actions across the three complete hands: FoxPoker at native index 3,
and Rekegutt at native index 1. The partial round-3/4 hand receives no player
attribution.

## Draw-game discards

The dealer announces every draw exactly — `First draw: <player> draws 2`,
`Second draw: <player> stands pat`, `Final draw: <player> draws 1` — so the
per-player discard count is decoded from that text (never from action bytes)
into `native_draws`. Each entry keeps the dealer's own round ordinal
(`first`/`second`/`final`), the exact `cards_drawn` (zero for `stands pat`), and
`seat_idx: null`. A single-draw game shows only `final`; triple-draw games
(2-7 Triple Draw, Badugi, Badeucy, Badacey) show all three. The specific
discarded and replacement cards are still not decoded — only how many each
player drew.

## Mixed-game per-hand identification

A mixed-game table name never states the current game, and the native
game-type code is not carried at a fixed offset in the class-22 snapshot or the
class-34 table header. The rotation is instead announced in a class-26 message
shaped `Game changes to <NL|PL|FL> <game> <small>/<big>` (e.g. `Game changes to
FL 2-7 Triple Draw 40/80`). The game label matches a `SWC_GAME_DEFINITIONS`
label exactly, so `parse_native_game_change` resolves the FPDB base/category
through that shared HTTP-adapter table and the `NL`/`PL`/`FL` prefix gives the
limit type.

Each hand is bound to the most recent announced game at its first snapshot
(`native_game`), which then drives `family`, `base`, `category` and `limit_type`
instead of the table-name heuristic. On the captured `Sunday Mini 12-Game Mix`
this identifies 42 hands across all twelve games — Hold'em, Omaha, Omaha H/L,
Stud, Stud H/L, Razz, 2-7 Single Draw, 2-7 Triple Draw, Badugi, Badeucy and
Badacey — and each classification is corroborated by the observed round span
(max round 6 for flop games, 7 for stud, 9 for triple draw, 5 for single draw).
Hands captured before the first announcement keep the name-based family. The
hands stay `capture_only`: identification does not by itself decode every action
or resolve seats.

## Per-game streets

Once the exact game is known, `streets.allStreets` and each step's `street` are
resolved by FPDB category instead of family, so stud and the two draw depths no
longer share one profile:

- stud / stud H/L / razz: `BLINDSANTES, THIRD, FOURTH, FIFTH, SIXTH, SEVENTH`;
- 2-7 Single Draw: `BLINDSANTES, DEAL, DRAWONE`;
- 2-7 Triple Draw / Badugi / Badeucy / Badacey: `BLINDSANTES, DEAL, DRAWONE,
  DRAWTWO, DRAWTHREE`.

The native round -> street maps are anchored on the observed round span and, for
draw games, on the dealer-announced draw rounds (first/second/final at native
rounds 2/4/6); settlement is the last round and showdown the one before it.
Hold'em/Omaha keep their existing family profile and the community-card
round-before-reveal shift; stud and draw never take that shift.

## Stud up cards

Stud up cards are visible to the whole table and are stored in each player
record as a `<total-cards> 0xFF 0xFF <board slots>` block: `total-cards` counts
the two hole cards plus the shown board, and the slots run from the third-street
door card onward (`0xFF` marks a hidden card — an opponent's hole card or an
un-revealed seventh street). `extract_native_stud_upcards` reads the snapshot
that exposes the most up cards and maps the slots to `THIRD, FOURTH, FIFTH,
SIXTH, SEVENTH`, leaving hidden slots `null`, into `native_stud_cards`. A decode
is rejected outright if any card repeats across players, guarding against a
false block match. On `test4.raw` this recovers 52 up cards across the ten stud
hands (studhi/studhilo/razz), each street's door and later up cards in order.
Third-street hole cards and hidden seventh-street cards are not claimed, and no
seat is resolved.
