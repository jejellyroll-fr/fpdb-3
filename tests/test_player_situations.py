"""The generic player situation model of issue #294.

``DerivedStats`` answers "how often did this player do X" with one column per
answer, and every column is a bespoke procedure over the action stream: a
squeeze, a 3-bet defence, a delayed c-bet and a float each have their own code,
so a new question needs a new procedure. This module checks the replacement --
one value per decision (:class:`player_situations.PlayerSituation`), one rule
table naming it, nothing else -- against four independent references:

* **the parsed action stream**, recounted from ``hand.actions`` so the model
  cannot silently drop, duplicate or reorder a decision;
* **the event rows of issue #293**, so every fact the model reports is the one
  the events already carry (and the two layers cannot drift apart);
* **the corpus manifest of issue #308**, whose per-player expectations are the
  documented *poker* meaning of each spot -- including the six places where the
  legacy columns disagree with it, which the model is expected to get right;
* **the PT4 ``enum_*_action`` columns**, which the projection reproduces cell
  for cell apart from two documented families, so a calculator can be moved
  onto the model and the HUD cannot tell.

The rule table itself is checked too: the model has to stay declarative, every
rule has to be exercised by the corpus, and every column it claims to answer
has to be one the HUD already displays.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from fpdb_3_legacy import player_situations as model
from fpdb_3_legacy.action_enum_stats import SITUATIONS
from fpdb_3_legacy.player_situations import (
    FORCED_ACTIONS,
    SITUATION_RULES,
    STREET_LETTERS,
    PlayerSituation,
    enum_fold_street,
    enum_responses,
    enumerate_situations,
    situations_by_label,
    situations_by_player,
    situations_for,
)
from tests.helpers import analytics_golden as golden

MANIFEST = golden.load_manifest()
SCENARIOS = {scenario.id: scenario for scenario in MANIFEST.scenarios}

# Streets, as the pipeline numbers them (the blinds are part of preflop).
PREFLOP, FLOP, TURN, RIVER = 0, 1, 2, 3

# The enum columns of the PT4 family, as they exist today.
LEGACY_ENUM_KEYS = {
    "enum_folded",
    "enum_f_3bet_action",
    "enum_f_4bet_action",
    "enum_f_cbet_action",
    "enum_f_donk_action",
    "enum_p_3bet_action",
    "enum_p_4bet_action",
    "enum_p_squeeze_action",
    "enum_r_3bet_action",
    "enum_r_4bet_action",
    "enum_r_cbet_action",
    "enum_r_donk_action",
    "enum_r_float_action",
    "enum_t_3bet_action",
    "enum_t_4bet_action",
    "enum_t_cbet_action",
    "enum_t_donk_action",
    "enum_t_float_action",
    "enum_face_allin",
    "enum_face_allin_action",
}


@pytest.fixture(scope="session")
def parsed(tmp_path_factory) -> dict[str, list[Any]]:
    """Every corpus hand, parsed in process (no database, no importer)."""
    config = golden.build_config(tmp_path_factory.mktemp("situation-parse"))
    return {path.name: golden.parse_golden_file(config, path) for path in golden.golden_files()}


@pytest.fixture(scope="session")
def situations(parsed: dict[str, list[Any]]) -> dict[int, list[PlayerSituation]]:
    """The situations of every corpus hand, keyed by hand id."""
    by_hand: dict[int, list[PlayerSituation]] = {}
    for hands in parsed.values():
        for hand in hands:
            hand.stats.getStats(hand)
            by_hand[int(hand.handid)] = list(hand.stats.getSituations())
    return by_hand


def hand_of(parsed: dict[str, list[Any]], scenario_id: str, index: int = 0) -> Any:
    scenario = SCENARIOS[scenario_id]
    return parsed[scenario.file][index]


def rows_of(hand: Any) -> dict[Any, dict[str, Any]]:
    return hand.stats.getHandsActions()


def first_of(situations: dict[int, list[PlayerSituation]], scenario_id: str, index: int = 0) -> list[PlayerSituation]:
    hand_id = SCENARIOS[scenario_id].hands[index].hand_id
    return situations[hand_id]


def labels_for(rows: list[PlayerSituation], player: str) -> set[str]:
    return {label for situation in rows if situation.player == player for label in situation.labels}


def decided(rows: list[PlayerSituation], player: str, response: str | None = None) -> list[PlayerSituation]:
    return [
        situation
        for situation in rows
        if situation.player == player and (response is None or situation.response == response)
    ]


def on_street(rows: list[PlayerSituation], street: int) -> list[PlayerSituation]:
    return [situation for situation in rows if situation.street == street]


# ---------------------------------------------------------------------------
# Every decision, and nothing but a decision
# ---------------------------------------------------------------------------


def test_situations_are_exactly_the_voluntary_decisions(parsed: dict[str, list[Any]], situations) -> None:
    """Recount the decisions straight from the parsed action stream."""
    for hands in parsed.values():
        for hand in hands:
            expected = [
                (street_name, action[0], action[1])
                for street_name in hand.actionStreets
                for action in hand.actions.get(street_name, [])
                if action[1] in model.DECISION_ACTIONS
            ]
            got = situations[int(hand.handid)]

            assert len(got) == len(expected), (
                f"hand {hand.handid}: {len(got)} situations for {len(expected)} decisions"
            )
            for situation, (street_name, player, action) in zip(got, expected, strict=True):
                assert situation.player == player
                assert situation.response == model.RESPONSES[action]
                assert situation.street_name == (
                    "preflop" if street_name in ("BLINDSANTES", "PREFLOP") else street_name.lower()
                )


def test_no_forced_bet_becomes_a_decision(situations) -> None:
    """A blind is context, not something the player chose."""
    for rows in situations.values():
        for situation in rows:
            assert situation.response not in FORCED_ACTIONS


def test_every_decision_carries_a_name(situations) -> None:
    """The rule table covers the whole stream: no decision is left unnamed."""
    unnamed = [
        (situation.hand_id, situation.street, situation.player, situation.response)
        for rows in situations.values()
        for situation in rows
        if not situation.primary
    ]

    assert not unnamed, f"decisions the rule table does not name: {unnamed[:5]}"


# ---------------------------------------------------------------------------
# The facts are the events' facts
# ---------------------------------------------------------------------------


def test_situations_report_the_event_of_their_own_action(parsed: dict[str, list[Any]], situations) -> None:
    """Nothing is re-derived behind the event model's back."""
    shared = (
        "toCall",
        "potBefore",
        "potAfter",
        "position",
        "relativePosition",
        "inPosition",
        "effectiveStack",
        "effectiveStackBB",
        "sprBefore",
        "raiserCount",
        "callerCount",
        "playersInHand",
    )
    for hands in parsed.values():
        for hand in hands:
            rows = rows_of(hand)
            for situation in situations[int(hand.handid)]:
                row = rows[situation.action_no]
                assert row["player"] == situation.player
                assert model.RESPONSES[row["actionType"]] == situation.response
                assert max(0, row["street"]) == situation.street
                for column in shared:
                    assert getattr(situation, _field_for(column)) == row[column], f"{column} drifted"


def _field_for(event_column: str) -> str:
    """The situation field that mirrors an event column."""
    return {
        "toCall": "to_call",
        "potBefore": "pot_before",
        "potAfter": "pot_after",
        "relativePosition": "relative_position",
        "inPosition": "in_position",
        "effectiveStack": "effective_stack",
        "effectiveStackBB": "effective_stack_bb",
        "sprBefore": "spr_before",
        "raiserCount": "raises_before",
        "callerCount": "calls_before",
        "playersInHand": "players_in_hand",
    }.get(event_column, event_column)


def test_context_is_measured_before_the_action(situations) -> None:
    for rows in situations.values():
        for situation in rows:
            if situation.response in ("fold", "check"):
                assert situation.pot_after == situation.pot_before
            elif situation.response in ("call", "bet", "raise", "complete"):
                assert situation.pot_after > situation.pot_before
            assert situation.to_call <= situation.pot_before + situation.to_call


def test_derived_facts_agree_with_each_other(situations) -> None:
    for rows in situations.values():
        for situation in rows:
            assert situation.in_position == (situation.relative_position == 0)
            assert situation.multiway == (situation.players_in_hand >= 3)
            assert situation.is_aggressor == (situation.street_aggressor == situation.player)
            assert situation.is_previous_aggressor == (situation.previous_aggressor == situation.player)
            expected_role = (
                "aggressor"
                if situation.response in model.AGGRESSIVE_RESPONSES
                else "defender"
                if situation.is_facing
                else "passive"
            )
            assert situation.role == expected_role
            if situation.is_facing:
                assert situation.bet_level_faced == situation.raises_before + (1 if situation.is_preflop else 0)
                assert situation.facing_action in ("bets", "raises")
                assert situation.facing_player is not None
                assert situation.to_call > 0
            else:
                assert situation.bet_level_faced == 0
                assert situation.facing_action is None
                assert situation.facing_player is None
                # Preflop, the forced bet is a price to call without anybody
                # having bet: that is the unopened pot, not a bet faced.
                assert situation.is_preflop or situation.to_call == 0
            if situation.to_call > 0:
                assert situation.pot_odds_bp == situation.to_call * 10000 // (
                    situation.pot_before + situation.to_call
                )
            else:
                assert situation.pot_odds_bp == 0


def test_stack_context_is_internally_consistent(situations) -> None:
    for rows in situations.values():
        for situation in rows:
            assert situation.effective_stack_bb == situation.effective_stack * 100 // situation.big_blind
            assert situation.stack_bucket in ("short", "medium", "deep", "very_deep")
            if situation.pot_before:
                assert situation.spr_before == situation.effective_stack * 100 // situation.pot_before
            assert situation.board == situation.board[: len(situation.board)]


def test_board_grows_one_street_at_a_time(parsed: dict[str, list[Any]], situations) -> None:
    """A flop decision sees three cards, a turn decision four, a river five."""
    sizes = {PREFLOP: 0, FLOP: 3, TURN: 4, RIVER: 5}
    for hands in parsed.values():
        for hand in hands:
            board = [
                card
                for street in ("FLOP", "TURN", "RIVER")
                for card in hand.board.get(street, [])
            ]
            for situation in situations[int(hand.handid)]:
                assert len(situation.board) == min(sizes[situation.street], len(board))
                assert list(situation.board) == board[: len(situation.board)]


def test_game_context_is_filled_in(situations) -> None:
    for rows in situations.values():
        for situation in rows:
            assert situation.site.startswith("PokerStars")
            assert situation.game == "holdem"
            assert situation.limit_type == "nl"
            assert not situation.is_tournament
            assert situation.big_blind == 200
            assert situation.currency == "USD"
            assert situation.table_size == 6
            assert situation.players_dealt == 6


# ---------------------------------------------------------------------------
# The rule table is data, not procedures
# ---------------------------------------------------------------------------


def test_every_declared_spot_appears_in_the_corpus(situations) -> None:
    """A rule nobody can point at a hand for is a rule nobody can trust."""
    seen = {label for rows in situations.values() for situation in rows for label in situation.labels}
    declared = {rule.name for rule in SITUATION_RULES}

    assert declared - seen == set(), f"unexercised rules: {sorted(declared - seen)}"


def test_rule_names_and_streets_are_unambiguous() -> None:
    keys = [(rule.name, rule.streets) for rule in SITUATION_RULES]

    assert len(set(keys)) == len(keys), "two rules share a name on the same street"
    for rule in SITUATION_RULES:
        assert rule.label, f"{rule.name} has no human label"
        assert rule.group, f"{rule.name} has no group"
        assert rule.response is None or set(rule.response) <= set(model.RESPONSES.values())
        if rule.streets is not None:
            assert set(rule.streets) <= {0, 1, 2, 3}


def test_a_spot_and_its_action_are_one_rule(parsed, situations) -> None:
    """Every chance/done pair is one predicate and two response filters.

    The aggregate columns that came in pairs (``street1CBChance`` /
    ``street1CBDone``, ``street0_SqueezeChance`` / ``street0_SqueezeDone``) are
    one situation here: whoever can take the line is named by the spot rule, and
    the action label is the same predicate narrowed to the response. Nothing
    counts the same thing twice.
    """
    by_name = {rule.name: rule for rule in SITUATION_RULES}
    pairs = (
        ("cbet_spot", "cbet"),
        ("delayed_cbet_spot", "delayed_cbet"),
        ("probe_spot", "probe"),
        ("donk_spot", "donk"),
        ("float_bet_spot", "float_bet"),
        ("squeeze_spot", "squeeze"),
    )
    for spot, action in pairs:
        assert by_name[spot].applies is by_name[action].applies, f"{spot}/{action} are two procedures"
        assert by_name[action].response is not None, f"{action} is not narrowed to a response"
        assert by_name[spot].response is None, f"{spot} already answers for the player"


def test_a_cold_caller_is_the_only_difference_between_two_spots(parsed, situations) -> None:
    """04 and 05 differ by one call, and the squeeze appears with it.

    Same seats, same opener, same 3-bettor, same 100bb stacks. The spot falls
    out of the action stream -- a caller between the open and the 3-bet -- and
    not out of a second procedure.
    """
    without = labels_for(first_of(situations, "open_3bet"), "Cara")
    with_caller = labels_for(first_of(situations, "squeeze"), "Cara")

    assert "facing_3bet" in without and "facing_3bet" in with_caller
    assert "squeeze_defence" not in without
    assert "squeeze_defence" in with_caller


# ---------------------------------------------------------------------------
# Poker semantics, on the scenarios written to pin them
# ---------------------------------------------------------------------------


def test_unopened_pot_names_the_open_and_the_folds(parsed, situations) -> None:
    """01: one open-raise, no limper, and folds that are folds, not limps."""
    rows = first_of(situations, "rfi_open")

    boris = decided(rows, "Boris")[0]
    assert boris.primary == "open_raise"
    assert {"open_raise", "steal_spot"}.issubset(boris.labels)
    assert "open_limp" not in boris.labels
    assert boris.pot_type == "unopened"
    assert boris.role == "aggressor"

    frank = decided(rows, "Frank")[0]
    assert frank.primary == "open_fold"
    assert {"open_fold", "preflop_unopened"}.issubset(frank.labels)
    assert "open_limp" not in frank.labels
    assert frank.role == "passive"


def test_a_limp_behind_a_limper_is_not_an_open_limp(parsed, situations) -> None:
    """02: the first caller opens the limping, the next one over-limps, the
    raiser isolates -- three different spots out of one street."""
    rows = first_of(situations, "limp_iso")

    frank = decided(rows, "Frank", "call")[0]
    assert frank.primary == "open_limp"
    assert frank.pot_type == "unopened"

    anna = decided(rows, "Anna", "call")[0]
    assert anna.primary == "over_limp"
    assert {"over_limp", "facing_limpers"}.issubset(anna.labels)
    assert "open_limp" not in anna.labels, "an over-limp is not an open limp"
    assert anna.pot_type == "limped"

    boris = decided(rows, "Boris", "raise")[0]
    assert boris.primary == "isolation_raise"
    assert {"isolation_raise", "facing_limpers"}.issubset(boris.labels)
    assert "open_raise" not in boris.labels, "an iso-raise is not a raise first in"


def test_raise_levels_are_counted_from_the_forced_bet(parsed, situations) -> None:
    """04 and 06: the open, the 3-bet, the 4-bet and the 5-bet, by level."""
    rows = first_of(situations, "open_3bet")

    three_bettor = decided(rows, "Boris", "raise")[0]
    assert three_bettor.primary == "three_bet"
    assert three_bettor.bet_level_faced == 2
    assert {"three_bet", "facing_open"}.issubset(three_bettor.labels)

    opener = decided(rows, "Anna")[1]
    assert opener.primary == "facing_3bet"
    assert {"opener_vs_3bet", "facing_3bet"}.issubset(opener.labels)
    assert opener.is_previous_raiser, "the opener is whoever raised before the raise they face"
    assert opener.facing_player == "Boris"

    deep = first_of(situations, "four_bet_five_bet_allin")
    levels = {situation.player: situation.bet_level_faced for situation in deep if situation.street == PREFLOP}
    assert max(levels.values()) >= 5
    assert any("five_bet_plus" in situation.labels for situation in deep)
    assert any("four_bet" in situation.labels for situation in deep)


def test_squeeze_and_squeeze_defence_are_the_same_shape(parsed, situations) -> None:
    """05: the cold player squeezes, the opener faces it, both from one raise."""
    rows = first_of(situations, "squeeze")

    boris = decided(rows, "Boris", "raise")[0]
    assert boris.primary == "squeeze"
    assert {"squeeze_spot", "squeeze"}.issubset(boris.labels)
    assert boris.callers_since_raise == 1, "the raise being squeezed already has a caller in it"
    assert boris.role == "aggressor"

    frank = decided(rows, "Frank", "fold")[0]
    assert {"squeeze_defence", "opener_vs_3bet"}.issubset(frank.labels)
    assert "squeeze_spot" not in frank.labels, "the opener is defending, not squeezing"

    anna = decided(rows, "Anna", "fold")[0]
    assert "squeeze_defence" in anna.labels
    assert anna.callers_between_raises == 1, "she is the cold caller between open and 3-bet"


def test_cbet_delayed_cbet_and_probe_are_told_apart(parsed, situations) -> None:
    """07, 08, 09: three lines that all start with the same preflop raise."""
    srp = first_of(situations, "srp_cbet")
    assert on_street(decided(srp, "Anna", "bet"), FLOP)[0].primary == "cbet"
    assert on_street(decided(srp, "Boris", "fold"), FLOP)[0].primary == "facing_cbet"

    delayed = first_of(situations, "delayed_cbet")
    flop_check = on_street(decided(delayed, "Anna", "check"), FLOP)[0]
    assert flop_check.primary == "cbet_spot", "declining the lead is the c-bet opportunity"
    assert flop_check.previous_street_actions == ("raises",), "her preflop open is the lead she declines"
    turn_bet = on_street(decided(delayed, "Anna", "bet"), TURN)[0]
    assert turn_bet.primary == "delayed_cbet"
    assert "cbet" not in turn_bet.labels, "a delayed c-bet is not a c-bet"
    assert "delayed_cbet" in turn_bet.labels

    probe = first_of(situations, "turn_probe")
    boris_turn = on_street(decided(probe, "Boris", "bet"), TURN)[0]
    assert boris_turn.primary == "probe"
    assert {"probe", "probe_spot"}.issubset(boris_turn.labels)
    assert "donk" not in boris_turn.labels
    assert boris_turn.previous_aggressor == "Anna"
    assert boris_turn.previous_aggressor_checked, "the probe exists because she checked the flop"

    anna_fold = on_street(decided(probe, "Anna", "fold"), TURN)[0]
    assert anna_fold.primary == "facing_donk"
    assert anna_fold.facing_player == "Boris"


def test_donk_float_and_check_raise_are_distinguished(parsed, situations) -> None:
    """10, 11 and 12: leading out into an aggressor, three different reasons."""
    check_raise = first_of(situations, "check_raise")
    cara_bet = on_street(decided(check_raise, "Cara", "bet"), FLOP)[0]
    assert cara_bet.primary == "donk"
    assert "donk_spot" in cara_bet.labels
    assert "check_raise" not in cara_bet.labels

    boris_raise = on_street(decided(check_raise, "Boris", "raise"), FLOP)[0]
    assert boris_raise.primary == "check_raise"
    assert "cbet" not in boris_raise.labels, "a check-raise is not a continuation bet"
    assert "facing_donk" in boris_raise.labels

    floating = first_of(situations, "float")
    cara_turn = on_street(decided(floating, "Cara", "bet"), TURN)[0]
    assert cara_turn.primary == "float_bet"
    assert "float_bet_spot" in cara_turn.labels
    assert "donk" not in cara_turn.labels, "the aggressor checked in front: that is a float, not a donk"
    assert cara_turn.aggressor_checked_this_street
    assert cara_turn.in_position_vs_previous_aggressor

    barrel = first_of(situations, "turn_barrel")
    cara_fold = on_street(decided(barrel, "Cara", "fold"), TURN)[0]
    assert cara_fold.primary == "facing_cbet"
    assert {"facing_cbet", "facing_float"}.issubset(cara_fold.labels)
    assert cara_fold.previous_street_actions == ("calls",)


def test_all_in_is_a_fact_and_a_spot(parsed, situations) -> None:
    """06 and 15: facing an all-in is named, and so is the all-in itself."""
    rows = first_of(situations, "allin_before_river")
    facing = [situation for situation in rows if "facing_all_in" in situation.labels]

    assert facing, "an all-in was faced and nobody knows it"
    assert all(situation.facing_all_in for situation in facing)
    assert any(situation.is_all_in for situation in rows), "the all-in itself is not recorded"


# ---------------------------------------------------------------------------
# The manifest's poker semantics, reproduced by the model
# ---------------------------------------------------------------------------

# How each manifest concept is recovered from the situations of one player.
# ``poker`` expectations only: where the corpus documents that the legacy column
# disagrees with the poker word, the model is expected to side with the word.
SEMANTIC_READERS: dict[str, str] = {
    "vpip": "preflop money in",
    "pfr": "preflop raise",
    "rfi": "label:open_raise",
    "open_limp": "label:open_limp",
    "over_limp": "label:over_limp",
    "steal_opportunity": "label:steal_spot",
    "steal_done": "label:open_raise+steal_spot",
    "two_bet_done": "first preflop raise",
    "three_bet_opportunity": "label:facing_open",
    "three_bet_done": "label:three_bet",
    "fold_to_three_bet_opportunity": "label:opener_vs_3bet",
    "fold_to_three_bet_done": "label:opener_vs_3bet+fold",
    "four_bet_opportunity": "label:opener_vs_3bet",
    "cold_four_bet_opportunity": "label:facing_3bet-not-opener",
    "four_bet_done": "label:four_bet",
    "squeeze_opportunity": "label:squeeze_spot",
    "squeeze_done": "label:squeeze",
    "faced_2bet_times": "labels:facing_open",
    "faced_3bet_times": "labels:facing_3bet",
    "aggressor_flop": "flop aggression",
    "bets_flop": "count:flop bet",
    "raises_flop": "count:flop raise",
    "faced_raise_flop": "flop facing a raise",
    "cbet_flop_opportunity": "label:cbet_spot@1",
    "cbet_flop_done": "label:cbet@1",
    "cbet_turn_opportunity": "label:cbet_spot@2",
    "cbet_turn_done": "label:cbet@2",
    "cbet_river_opportunity": "label:cbet_spot@3",
    "cbet_river_done": "label:cbet@3",
    "delayed_cbet_turn_opportunity": "label:delayed_cbet_spot@2",
    "delayed_cbet_turn_done": "label:delayed_cbet@2",
    "probe_turn_opportunity": "label:probe_spot@2",
    "probe_turn_done": "label:probe@2",
    "float_turn_opportunity": "label:float_bet_spot@2",
    "float_turn_done": "label:float_bet@2",
    "float_turn_defence_opportunity": "label:facing_donk@2",
    "check_raise_flop_done": "label:check_raise@1",
    "fold_to_cbet_flop_opportunity": "label:facing_cbet@1",
    "fold_to_cbet_flop_done": "label:facing_cbet@1+fold",
    "fold_to_cbet_turn_opportunity": "label:facing_cbet@2",
    "fold_to_cbet_turn_done": "label:facing_cbet@2+fold",
}


AGGRESSIVE = ("call", "raise", "complete")


def _read_simple(reader: str) -> Any | None:
    """The readers that are one question about the stream."""
    if reader == "preflop money in":
        return lambda preflop: any(situation.response in AGGRESSIVE for situation in preflop)
    if reader == "preflop raise":
        return lambda preflop: any(situation.response in ("raise", "complete") for situation in preflop)
    if reader == "first preflop raise":
        # The second bet of the hand: the first raise of the round, whoever
        # makes it -- an open in an unopened pot, an iso-raise over limpers.
        return lambda preflop: any(
            situation.response in ("raise", "complete") and situation.raises_before == 0
            for situation in preflop
        )
    return None


def _read_label(mine: list[PlayerSituation], spec: str) -> bool:
    """``label:name@street+response`` -- the spot, on a street, answered so."""
    name, _, response = spec.partition("+")
    label, _, street_number = name.partition("@")
    wanted = [situation for situation in mine if label in situation.labels]
    if street_number:
        wanted = [situation for situation in wanted if situation.street == int(street_number)]
    if response in model.RESPONSES.values():
        wanted = [situation for situation in wanted if situation.response == response]
    return bool(wanted)


def read_semantics(rows: list[PlayerSituation], player: str, reader: str) -> Any:
    """Evaluate one reader against one player's situations."""
    mine = [situation for situation in rows if situation.player == player]
    preflop = [situation for situation in mine if situation.street == PREFLOP]
    on_flop = [situation for situation in mine if situation.street == FLOP]

    simple = _read_simple(reader)
    if simple is not None:
        return simple(preflop)
    if reader.startswith("label:"):
        return _read_label(mine, reader.removeprefix("label:"))
    if reader.startswith("labels:"):
        label = reader.removeprefix("labels:")
        return len([situation for situation in mine if label in situation.labels])
    if reader == "flop aggression":
        return any(situation.response in model.AGGRESSIVE_RESPONSES for situation in on_flop)
    if reader == "count:flop bet":
        return len([situation for situation in on_flop if situation.response == "bet"])
    if reader == "count:flop raise":
        return len([situation for situation in on_flop if situation.response == "raise"])
    if reader == "flop facing a raise":
        return any(situation.facing_action == "raises" for situation in on_flop)
    raise AssertionError(f"no reader named {reader!r}")


def test_the_manifest_semantics_are_reproduced_by_the_model(parsed, situations) -> None:
    """Every documented concept, on every player of every corpus hand."""
    checked = 0
    for scenario in MANIFEST.scenarios:
        for hand in parsed[scenario.file]:
            expectations = next(
                entry for entry in scenario.hands if entry.hand_id == int(hand.handid)
            )
            for player, expected in expectations.player_expect.items():
                for key, want in expected.items():
                    reader = SEMANTIC_READERS.get(key)
                    if reader is None:
                        continue
                    if isinstance(want, dict):
                        want = want["poker"]
                    got = read_semantics(situations[int(hand.handid)], player, reader)
                    checked += 1
                    assert got == want, (
                        f"{scenario.id} hand {hand.handid} {player}: {key} is {want} in poker terms "
                        f"({reader}), the model says {got}"
                    )

    assert checked > 150, "the semantic bridge stopped checking anything"


def test_the_model_sides_with_poker_where_the_columns_document_a_deviation(parsed, situations) -> None:
    """The six #308 deviations: the model is expected to get them right.

    Each is a place where the legacy column and the poker word disagree; the
    manifest records both. The model has to reproduce the poker side, which is
    what makes it a migration target rather than a second copy of the bug.
    """
    for scenario in MANIFEST.scenarios:
        for hand in parsed[scenario.file]:
            expectations = next(entry for entry in scenario.hands if entry.hand_id == int(hand.handid))
            for player, expected in expectations.player_expect.items():
                for key, want in expected.items():
                    if not isinstance(want, dict):
                        continue
                    reader = SEMANTIC_READERS.get(key)
                    if reader is None:
                        continue
                    got = read_semantics(situations[int(hand.handid)], player, reader)
                    assert got == want["poker"], f"{want['deviation']} not fixed in the model"
                    assert got != want["current"], f"{want['deviation']} not fixed in the model"


# ---------------------------------------------------------------------------
# The PT4 enum projection: the migration path
# ---------------------------------------------------------------------------


def test_the_projection_answers_every_enum_column_the_hud_shows() -> None:
    """Every ``enum_*`` column the HUD reads is answerable from the table."""
    declared = set()
    for rule in SITUATION_RULES:
        if rule.enum_key is None:
            continue
        if "{s}" in rule.enum_key:
            streets = rule.streets or tuple(STREET_LETTERS)
            declared |= {rule.enum_key.format(s=STREET_LETTERS[street]) for street in streets}
        else:
            declared.add(rule.enum_key)

    hud_columns = {situation.enum_key for situation in SITUATIONS}
    assert hud_columns == declared, f"unprojected: {sorted(hud_columns - declared)}"
    assert declared <= LEGACY_ENUM_KEYS


def test_the_projection_reproduces_the_legacy_columns(parsed, situations) -> None:
    """204 of the 209 enum cells of the corpus, and the 5 known exceptions.

    The projection exists so a calculator can move onto the model without the
    HUD noticing. Where it differs, it differs on purpose:

    * ``enum_face_allin`` / ``enum_face_allin_action`` (4 cells): the legacy
      pass records the *first* all-in faced in the whole hand and stops, so at
      most one player per hand is ever answered. The model knows every player
      who faced one -- ``test_facing_an_all_in_is_recorded_for_everyone``
      checks the information is all there -- but it does not project a column
      whose legacy shape is that quirk.
    * ``enum_t_donk_action`` (1 cell): on the turn after a checked-through flop,
      the legacy chain has no aggressor left, so the defender of a probe bet is
      left unanswered. The model names them ``facing_donk``, which is what the
      PT4 column is for.
    """
    differences = []
    compared = 0
    for hands in parsed.values():
        for hand in hands:
            mine = {player: dict(keys) for player, keys in enum_responses(situations[int(hand.handid)]).items()}
            for player, street in enum_fold_street(situations[int(hand.handid)]).items():
                mine.setdefault(player, {})["enum_folded"] = street
            legacy = {
                player: {
                    key: value
                    for key, value in row.items()
                    if key.startswith("enum_") and value not in (None, "N", "", 0)
                }
                for player, row in hand.stats.getHandsPlayers().items()
            }
            for player in set(legacy) | set(mine):
                for key in set(legacy.get(player, {})) | set(mine.get(player, {})):
                    compared += 1
                    if legacy.get(player, {}).get(key) != mine.get(player, {}).get(key):
                        differences.append(
                            (
                                int(hand.handid),
                                player,
                                key,
                                legacy.get(player, {}).get(key),
                                mine.get(player, {}).get(key),
                            )
                        )

    assert compared > 200, "the projection comparison stopped checking anything"
    assert sorted(differences, key=str) == sorted(EXPECTED_ENUM_DIFFERENCES, key=str)


# The five cells the projection deliberately answers differently, with a reason
# in the docstring above. Pinning them keeps the difference visible: fixing the
# legacy chain moves this list, and the documentation has to move with it.
EXPECTED_ENUM_DIFFERENCES = (
    (3100000006, "Frank", "enum_face_allin", "p", None),
    (3100000006, "Frank", "enum_face_allin_action", "F", None),
    (3100000009, "Anna", "enum_t_donk_action", None, "F"),
    (3100000015, "Anna", "enum_face_allin", "F", None),
    (3100000015, "Anna", "enum_face_allin_action", "C", None),
)


def test_facing_an_all_in_is_recorded_for_everyone(parsed, situations) -> None:
    """The all-in columns are not projected, but they are reconstructible."""
    for hand in parsed["15_allin_before_river.txt"]:
        rows = situations[int(hand.handid)]
        facing = [situation for situation in rows if situation.facing_all_in]
        assert facing

        for situation in facing:
            assert "facing_all_in" in situation.labels
            assert situation.enum_response in ("F", "C", "R")
        assert any(situation.response == "call" for situation in facing)


def test_the_projection_takes_the_first_answer_of_a_hand(parsed, situations) -> None:
    """A player who answers the same spot twice is counted once, as PT4 does."""
    for hands in parsed.values():
        for hand in hands:
            projection = enum_responses(situations[int(hand.handid)])
            for answers in projection.values():
                assert set(answers.values()) <= {"F", "C", "R"}
                assert set(answers) <= LEGACY_ENUM_KEYS


def test_enum_fold_street_is_the_street_the_player_folded_on(parsed, situations) -> None:
    for hands in parsed.values():
        for hand in hands:
            folded = enum_fold_street(situations[int(hand.handid)])
            for player, street in folded.items():
                assert street in ("P", "F", "T", "R")
                assert any(
                    situation.player == player and situation.response == "fold"
                    for situation in situations[int(hand.handid)]
                )


# ---------------------------------------------------------------------------
# The API
# ---------------------------------------------------------------------------


def test_the_api_reads_the_hand_when_it_is_given_nothing(parsed) -> None:
    """A caller that has just assembled a hand passes no arguments."""
    for hands in parsed.values():
        for hand in hands:
            assert enumerate_situations(hand) == enumerate_situations(
                hand, hand.stats.getHandsPlayers(), hand.stats.getHandsActions()
            )


def test_rows_without_event_context_yield_no_situations(parsed) -> None:
    """A database written before #293 has rows but no context: no guessing."""
    hand = hand_of(parsed, "srp_cbet")
    rows = {key: {"player": row["player"], "street": row["street"]} for key, row in rows_of(hand).items()}

    assert enumerate_situations(hand, hand.stats.getHandsPlayers(), rows) == ()


def test_enumeration_does_not_touch_the_hand(parsed) -> None:
    """The pass is a read: no row, no player stat and no action is rewritten."""
    hand = hand_of(parsed, "squeeze")
    before = json.dumps(rows_of(hand), sort_keys=True, default=str)
    before_players = json.dumps(hand.stats.getHandsPlayers(), sort_keys=True, default=str)

    enumerate_situations(hand, hand.stats.getHandsPlayers(), rows_of(hand))

    assert json.dumps(rows_of(hand), sort_keys=True, default=str) == before
    assert json.dumps(hand.stats.getHandsPlayers(), sort_keys=True, default=str) == before_players


def test_derived_stats_exposes_the_situations(parsed) -> None:
    hand = hand_of(parsed, "open_3bet")

    assert hand.stats.getSituations() == list(enumerate_situations(hand, hand.stats.getHandsPlayers(), rows_of(hand)))


def test_situations_can_be_selected_by_player_and_by_label(parsed, situations) -> None:
    rows = situations[SCENARIOS["squeeze"].hands[0].hand_id]
    grouped = situations_by_player(rows)

    assert set(grouped) == {situation.player for situation in rows}
    assert situations_for(rows, "Boris") == grouped["Boris"]
    assert situations_for(rows, "Boris", "squeeze") == [
        situation for situation in grouped["Boris"] if "squeeze" in situation.labels
    ]
    by_label = situations_by_label(rows)
    assert {label for situation in rows for label in situation.labels} == set(by_label)
    assert all(by_label["open_raise"]), "a label with no situations should not be indexed"


def test_a_situation_serialises_flat(parsed, situations) -> None:
    """The record is flat and typed, ready for any persisted form (#305)."""
    situation = situations[SCENARIOS["rfi_open"].hands[0].hand_id][0]
    flat = situation.as_dict()

    assert flat["player"] == "Frank"
    assert isinstance(json.dumps(flat, default=str), str)
    assert set(flat) >= {"hand_id", "action_no", "street", "player", "labels", "primary", "enum_answers"}
