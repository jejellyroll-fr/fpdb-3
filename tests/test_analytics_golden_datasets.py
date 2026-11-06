"""End-to-end semantics for the golden analytics corpus (#308).

The analytics epic (#310) adds an event model, a situation model, a query
engine and several reports on top of the hand pipeline. Each of those layers
is only worth as much as the poker semantics underneath it, so this module
pins those semantics on a small hand-written corpus before the new layers
exist, and keeps pinning them afterwards.

Three kinds of check live here:

* **Manifest checks** -- the corpus, the manifest and the deviations have to
  stay in step, so a scenario cannot be added without saying what it means.
* **Money and board checks** -- what a hand cost, what it paid and which cards
  came out, straight from the database rows.
* **Semantic checks** -- the per-player expectations, cross-validated against
  an independent recomputation from the parsed action stream
  (:func:`analytics_golden.oracle_semantics`) and against the HudCache
  aggregates the HUD actually reads.

Where the pipeline disagrees with the poker word, the manifest says so
explicitly (a ``poker`` / ``current`` pair plus a deviation id) instead of the
test enshrining the disagreement silently: fixing the rule fails the test and
forces the documentation to move with it.
"""

from __future__ import annotations

import pytest

from tests.helpers import analytics_golden as golden

MANIFEST = golden.load_manifest()
SCENARIOS = MANIFEST.scenarios

# Sub-issues of the epic that golden scenarios claim to cover.
COVERABLE_ISSUES = {
    "#293", "#294", "#295", "#296", "#297", "#298", "#299", "#300",
    "#301", "#302", "#303", "#304", "#305", "#306", "#307", "#308", "#309",
}

# Scenarios #308 requires the corpus to contain, keyed by the tag that marks them.
REQUIRED_TAGS = {
    "unopened",
    "limp",
    "over-limp",
    "open-call",
    "open-3bet",
    "squeeze",
    "4bet",
    "5bet",
    "single-raised-pot",
    "cbet",
    "delayed-cbet",
    "probe",
    "check-raise",
    "float",
    "turn-barrel",
    "river-barrel",
    "multiway",
    "all-in",
    "board-texture",
    "buckets",
}

# Columns cross-checked between the per-hand rows and the HudCache the HUD reads.
CACHE_COLUMNS = (
    "street0VPIChance",
    "street0VPI",
    "street0AggrChance",
    "street0Aggr",
    "raisedFirstIn",
    "street1Seen",
    "street2Seen",
    "street3Seen",
    "street1CBDone",
    "street1CBChance",
    "street0_3BDone",
    "street0_SqueezeDone",
    "totalProfit",
    "winnings",
    "committed",
)


@pytest.fixture(scope="session")
def corpus(tmp_path_factory) -> golden.GoldenCorpus:
    """Import the whole golden corpus once for the whole module."""
    return golden.import_golden_corpus(tmp_path_factory.mktemp("golden-corpus"))


@pytest.fixture(scope="session")
def reparsed_corpus(tmp_path_factory) -> golden.GoldenCorpus:
    """A second, independent import of the same files."""
    return golden.import_golden_corpus(tmp_path_factory.mktemp("golden-corpus-again"))


@pytest.fixture(scope="session")
def parsed_hands(tmp_path_factory) -> dict[str, list]:
    """The corpus parsed without a database, for the independent oracle."""
    config = golden.build_config(tmp_path_factory.mktemp("golden-parse"))
    return {
        path.name: golden.parse_golden_file(config, path)
        for path in golden.golden_files()
    }


# ---------------------------------------------------------------------------
# The manifest describes the corpus
# ---------------------------------------------------------------------------


def test_every_corpus_file_is_exactly_one_scenario() -> None:
    on_disk = [path.name for path in golden.golden_files()]
    declared = [scenario.file for scenario in SCENARIOS]

    assert sorted(declared) == sorted(on_disk), "the corpus and the manifest have drifted apart"
    assert len(set(declared)) == len(declared), "two scenarios claim the same file"


def test_scenario_ids_and_hand_ids_are_unique() -> None:
    ids = [scenario.id for scenario in SCENARIOS]
    hand_ids = [hand.hand_id for scenario in SCENARIOS for hand in scenario.hands]

    assert len(set(ids)) == len(ids)
    assert len(set(hand_ids)) == len(hand_ids)


def test_every_scenario_says_which_issues_it_covers() -> None:
    for scenario in SCENARIOS:
        assert scenario.covers, f"{scenario.id} covers no sub-issue"
        unknown = set(scenario.covers) - COVERABLE_ISSUES
        assert not unknown, f"{scenario.id} claims unknown issues: {unknown}"


def test_scenarios_cover_the_spots_the_quality_issue_requires() -> None:
    tags = {tag for scenario in SCENARIOS for tag in scenario.tags}

    assert REQUIRED_TAGS <= tags, f"missing golden spots: {sorted(REQUIRED_TAGS - tags)}"


def test_every_scenario_explains_its_poker_logic() -> None:
    for scenario in SCENARIOS:
        assert len(scenario.logic) >= 2, f"{scenario.id} does not explain the spot"
        for hand in scenario.hands:
            assert hand.player_expect, f"{scenario.id}: hand {hand.hand_id} has no players"


def test_expectations_use_the_documented_vocabulary() -> None:
    for scenario in SCENARIOS:
        for hand in scenario.hands:
            for name, expectation in hand.player_expect.items():
                for key in expectation:
                    assert key in golden.SEMANTIC_FIELDS, f"{scenario.id}: {name} has unknown key {key}"
            unknown = set(hand.hand_expect) - set(golden.HAND_KEYS)
            assert not unknown, f"{scenario.id}: unknown hand keys {unknown}"


def test_every_documented_deviation_is_used_and_every_use_is_documented() -> None:
    used = set()
    for scenario in SCENARIOS:
        for hand in scenario.hands:
            for expectation in hand.player_expect.values():
                for value in expectation.values():
                    if isinstance(value, dict):
                        used.add(value["deviation"])

    assert used <= set(MANIFEST.deviations), f"undeclared deviations: {sorted(used - set(MANIFEST.deviations))}"
    assert set(MANIFEST.deviations) <= used, (
        f"deviations nobody exercises: {sorted(set(MANIFEST.deviations) - used)}"
    )


def test_documented_deviation_row_counts_still_hold(corpus: golden.GoldenCorpus) -> None:
    """A deviation carries the blast radius it was documented with.

    When the underlying rule is fixed the count moves, which is the point:
    the change lands with the documentation rather than behind it.
    """
    for deviation in MANIFEST.deviations.values():
        if deviation.column is None or deviation.observed_true_rows is None:
            continue
        observed = sum(
            1
            for hand_rows in corpus.players.values()
            for row in hand_rows.values()
            if row[deviation.column]
        )
        assert observed == deviation.observed_true_rows, (
            f"deviation {deviation.id}: {deviation.column} is true in {observed} rows, "
            f"the manifest documents {deviation.observed_true_rows}"
        )


# ---------------------------------------------------------------------------
# Money, cards and counts
# ---------------------------------------------------------------------------


def test_the_whole_corpus_imported(corpus: golden.GoldenCorpus) -> None:
    declared_hands = [hand.hand_id for scenario in SCENARIOS for hand in scenario.hands]

    assert corpus.hand_count == len(declared_hands)
    assert corpus.player_count == len(declared_hands) * 6


def test_every_declared_hand_is_in_the_database(corpus: golden.GoldenCorpus) -> None:
    for scenario in SCENARIOS:
        for hand in scenario.hands:
            assert hand.hand_id in corpus.hands, f"{scenario.id}: hand {hand.hand_id} missing"
            assert set(corpus.players[hand.hand_id]) == {
                "Anna", "Boris", "Cara", "Dave", "Erin", "Frank"
            }


def test_declared_pot_and_rake_are_what_the_hand_cost(corpus: golden.GoldenCorpus) -> None:
    for scenario in SCENARIOS:
        for hand in scenario.hands:
            row = corpus.hands[hand.hand_id]
            assert int(row["finalPot"]) == hand.pot_cents, f"{scenario.id}: pot"
            assert int(row["rake"]) == hand.rake_cents, f"{scenario.id}: rake"


def test_money_is_conserved_in_every_hand(corpus: golden.GoldenCorpus) -> None:
    """Committed chips become the pot, the pot becomes winnings, profit sums to zero.

    The corpus is rake free on purpose: with rake in play the identity is
    ``winnings + rake == pot`` and the players' profits no longer sum to zero,
    which would make a wrong number ambiguous between a rake and a mistake.
    """
    for hand_id, rows in corpus.players.items():
        hand = corpus.hands[hand_id]
        assert sum(row["committed"] for row in rows.values()) == hand["finalPot"], hand_id
        assert sum(row["winnings"] or 0 for row in rows.values()) + hand["rake"] == hand["finalPot"], hand_id
        assert sum(row["totalProfit"] or 0 for row in rows.values()) == 0, hand_id
        for name, row in rows.items():
            assert (row["winnings"] or 0) - row["committed"] == row["totalProfit"], (hand_id, name)


def test_every_player_keeps_their_seat_role(corpus: golden.GoldenCorpus) -> None:
    """The button never moves in this corpus, which is what makes per-player
    aggregates reviewable by eye."""
    roles = {"Anna": "2", "Boris": "1", "Cara": "0", "Dave": "S", "Erin": "B", "Frank": "3"}

    for hand_id, rows in corpus.players.items():
        for name, row in rows.items():
            assert row["position"] == roles[name], (hand_id, name)


def test_declared_board_is_what_the_hand_dealt(corpus: golden.GoldenCorpus) -> None:
    for scenario in SCENARIOS:
        for hand in scenario.hands:
            row = corpus.hands[hand.hand_id]
            dealt = golden.decode_board(row)
            declared = [card for street in golden.BOARD_KEYS for card in hand.board[street]]

            assert dealt == declared, f"{scenario.id}: board {dealt} != {declared}"


def test_declared_board_features_are_what_the_classifier_stored(corpus: golden.GoldenCorpus) -> None:
    """Every board expectation is checked against the row #295 persisted.

    The manifest states the poker reading of the cards (``ace-high rainbow``,
    ``monotone connected``, ``runout_brick``); the classifier has to agree with
    that sentence, street by street, on the same cards -- and the corpus declares
    every street it saw, so a street cannot be stored without being described.
    """
    failures: list[str] = []
    for scenario in SCENARIOS:
        for hand in scenario.hands:
            rows = {row["streetName"]: row for row in corpus.board_rows(hand.hand_id)}
            for street, expectation in hand.board_feature_expect.items():
                if street not in rows:
                    failures.append(f"{scenario.id} hand {hand.hand_id}: no {street} row stored")
                    continue
                for mismatch in golden.board_feature_mismatches(rows[street], expectation):
                    failures.append(f"{scenario.id} hand {hand.hand_id} {street}: {mismatch}")
            undeclared = set(rows) - set(hand.board_feature_expect)
            if undeclared:
                failures.append(f"{scenario.id} hand {hand.hand_id}: undeclared {sorted(undeclared)} rows")
    assert not failures, "\n".join(failures)


def test_board_features_cover_exactly_the_streets_that_were_dealt(corpus: golden.GoldenCorpus) -> None:
    """A street row exists for every street with cards, and only for those.

    A preflop-only hand stores nothing; a hand that reached the turn has a flop
    row and a turn row, in that order, its card count cumulated the way the
    runout flags need it, and its turn and river carry a runout verdict while
    the flop -- which changed nothing, having no previous street -- does not.
    """
    for scenario in SCENARIOS:
        for hand in scenario.hands:
            rows = corpus.board_rows(hand.hand_id)
            dealt = [street for street in golden.BOARD_KEYS if hand.board[street]]

            assert [row["streetName"] for row in rows] == dealt, (scenario.id, hand.hand_id)
            assert [row["street"] for row in rows] == list(range(1, len(dealt) + 1))
            assert all(row["boardId"] == 1 for row in rows), (scenario.id, hand.hand_id)
            cumulative = 0
            for street, row in zip(dealt, rows, strict=True):
                cumulative += len(hand.board[street])
                assert row["cardCount"] == cumulative, (scenario.id, hand.hand_id, street)
                assert (row["runoutMask"] == 0) == (street == "flop"), (scenario.id, hand.hand_id, street)


def test_hands_texture_is_the_flop_mask_and_zero_means_no_flop(corpus: golden.GoldenCorpus) -> None:
    """``Hands.texture`` is the flop mask, and 0 means "no flop".

    Every flop sets at least a suit structure flag, so 0 cannot mean "a flop
    with no features" -- which is what makes the redefined column safe to read
    as the cheap texture filter the epic's example queries start with.
    """
    for hand_id, hand in corpus.hands.items():
        flop = corpus.board_rows(hand_id, street=1)
        assert int(hand["texture"]) == (int(flop[0]["textureMask"]) if flop else 0), hand_id
        assert bool(flop) == bool(hand["texture"]), hand_id


def test_declared_player_counts_match(corpus: golden.GoldenCorpus) -> None:
    for scenario in SCENARIOS:
        for hand in scenario.hands:
            row = corpus.hands[hand.hand_id]
            rows = corpus.players[hand.hand_id]

            assert row["seats"] == hand.hand_expect["players_dealt"], f"{scenario.id}: seats"
            assert row["playersVpi"] == hand.hand_expect["players_vpip"], f"{scenario.id}: vpip count"
            for street, key in (
                ("street1Seen", "players_at_flop"),
                ("street2Seen", "players_at_turn"),
                ("street3Seen", "players_at_river"),
            ):
                if key not in hand.hand_expect:
                    continue
                reached = sum(1 for player_row in rows.values() if player_row[street])
                assert reached == hand.hand_expect[key], f"{scenario.id}: {key}"


def test_hand_raise_counts_are_indexed_from_the_blinds_street(corpus: golden.GoldenCorpus) -> None:
    """Hands.street{N}Raises and HandsPlayers.street{N}Raises are offset by one.

    Hands carries the preflop raise count in ``street1Raises`` because its
    street 0 is the BLINDSANTES pseudo-street (``actionStreets[0]``), which is
    why a preflop-only hand reports ``street0Raises == 0, street1Raises == 1``.
    The per-player columns are preflop-first. Anything joining the two has to
    know this, so the corpus states it.
    """
    for hand_id, rows in corpus.players.items():
        hand = corpus.hands[hand_id]
        assert hand["street0Raises"] == 0, hand_id
        for street in range(4):
            # Hands counts bets and raises together, the per-player columns split them.
            per_player = sum(
                (row[f"street{street}Raises"] or 0) + (row[f"street{street}Bets"] or 0)
                for row in rows.values()
            )
            assert hand[f"street{street + 1}Raises"] == per_player, (hand_id, street)


# ---------------------------------------------------------------------------
# The semantics the analytics layers will build on
# ---------------------------------------------------------------------------


def _resolve(field_name: str, expectation: object) -> tuple[object, str | None, golden.Field]:
    field = golden.SEMANTIC_FIELDS[field_name]
    value, deviation = golden.expectation_value(expectation, field)  # type: ignore[arg-type]
    return value, deviation, field


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda scenario: scenario.id)
def test_scenario_semantics(scenario: golden.GoldenScenario, corpus: golden.GoldenCorpus) -> None:
    failures: list[str] = []
    for hand in scenario.hands:
        for name, expectation in hand.player_expect.items():
            row = corpus.player_row(hand.hand_id, name)
            for field_name, expected in expectation.items():
                value, deviation, field = _resolve(field_name, expected)
                stored = golden.coerce(field, row[field.column])
                wanted = golden.expected_form(field, value)
                if stored != wanted:
                    note = f" [documented deviation: {deviation}]" if deviation else ""
                    failures.append(
                        f"hand {hand.hand_id} {name} {field_name} ({field.column}) "
                        f"= {stored!r}, expected {wanted!r} -- {field.meaning}{note}"
                    )
    assert not failures, f"{scenario.id}:\n" + "\n".join(failures)


def test_the_oracle_agrees_with_the_stored_semantics(
    corpus: golden.GoldenCorpus, parsed_hands: dict[str, list]
) -> None:
    """Two independent readings of each hand history must agree.

    ``oracle_semantics`` walks the parsed action stream with naive poker rules;
    the stored flags come out of DerivedStats. A disagreement is either a bug
    in the pipeline or a bug in the oracle, and both are worth failing on --
    except where the manifest already documents the disagreement.
    """
    columns = {
        "vpip": "street0VPI",
        "pfr": "street0Aggr",
        "rfi": "raisedFirstIn",
        "three_bet_done": "street0_3BDone",
        "saw_flop": "street1Seen",
        "cbet_flop_done": "street1CBDone",
    }
    exempt = _documented_disagreements()
    failures: list[str] = []

    for scenario in SCENARIOS:
        for hand in parsed_hands[scenario.file]:
            hand_id = int(hand.handid)
            oracle = golden.oracle_semantics(hand)
            for name, facts in oracle.items():
                row = corpus.player_row(hand_id, name)
                for fact, column in columns.items():
                    stored = bool(row[column])
                    if stored == bool(facts[fact]):
                        continue
                    if (hand_id, name, column) in exempt:
                        continue
                    failures.append(
                        f"hand {hand_id} {name} {fact} ({column}): oracle says "
                        f"{facts[fact]}, pipeline stored {stored}"
                    )

    assert not failures, "\n".join(failures)


def _documented_disagreements() -> set[tuple[int, str, str]]:
    exempt = set()
    for scenario in SCENARIOS:
        for hand in scenario.hands:
            for name, expectation in hand.player_expect.items():
                for field_name, expected in expectation.items():
                    if isinstance(expected, dict) and "deviation" in expected:
                        exempt.add((hand.hand_id, name, golden.SEMANTIC_FIELDS[field_name].column))
    return exempt


def test_the_hud_cache_holds_what_the_hand_rows_say(corpus: golden.GoldenCorpus) -> None:
    """The HUD reads HudCache, never HandsPlayers, so the two have to agree.

    This is the aggregate contract the analytics caches will join: the same
    facts, accumulated per player and position bucket.
    """
    failures: list[str] = []
    # Driven by the players the hands know about, not by the cache: a writer
    # that skips a player -- or writes nothing at all -- has to fail here
    # rather than leave nothing to compare.
    played = {player for hand_rows in corpus.players.values() for player in hand_rows}
    assert played, "the corpus produced no player rows"
    missing = sorted(played - set(corpus.hud_cache))
    assert not missing, f"no HudCache row for {missing}"

    for name in sorted(played):
        cache = corpus.hud_cache[name]
        rows = [row for hand_rows in corpus.players.values() for player, row in hand_rows.items() if player == name]
        for column in CACHE_COLUMNS:
            per_hand = sum(row[column] or 0 for row in rows)
            if int(cache.get(column, 0) or 0) != per_hand:
                failures.append(
                    f"{name} {column}: HudCache {cache.get(column)} vs HandPlayers sum {per_hand}"
                )

    assert not failures, "\n".join(failures)


def test_the_corpus_derives_the_same_way_twice(
    corpus: golden.GoldenCorpus, reparsed_corpus: golden.GoldenCorpus
) -> None:
    """Importing the same hands twice must produce the same derived data.

    Determinism is a precondition for the cached analytics the epic adds; a
    rebuild that lands on different numbers than the original import is not a
    rebuild.
    """
    assert corpus.hand_count == reparsed_corpus.hand_count
    columns = tuple(golden.SEMANTIC_FIELDS[key].column for key in sorted(golden.SEMANTIC_FIELDS))
    failures: list[str] = []

    for hand_id, rows in corpus.players.items():
        for name, row in rows.items():
            other = reparsed_corpus.player_row(hand_id, name)
            for column in columns:
                if row[column] != other[column]:
                    failures.append(f"hand {hand_id} {name} {column}: {row[column]} != {other[column]}")
        if corpus.hands[hand_id]["finalPot"] != reparsed_corpus.hands[hand_id]["finalPot"]:
            failures.append(f"hand {hand_id}: finalPot")
        # The board features are derived, not accumulated, so a second import
        # has to classify every street exactly as the first one did.
        if corpus.boards[hand_id] != reparsed_corpus.boards[hand_id]:
            failures.append(f"hand {hand_id}: board features differ between two imports")

    assert not failures, "\n".join(failures)


def test_no_scenario_asserts_nothing() -> None:
    """A scenario that asserts nothing is documentation that cannot fail."""
    for scenario in SCENARIOS:
        asserted = sum(
            len(expectation) for hand in scenario.hands for expectation in hand.player_expect.values()
        )
        assert asserted >= 6, f"{scenario.id} asserts only {asserted} facts"
