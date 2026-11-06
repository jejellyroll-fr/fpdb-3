"""The ICM engine (#446): Malmuth-Harville equities, all-in $EV, bubble factor.

Checked three ways: a 3-handed example worked out by hand with exact fractions,
an independent brute force over every finishing order for 6- and 9-handed
tables, and the properties any ICM must keep (prizes add up, equal stacks are
equal, more chips never means less equity, units do not matter).
"""

from __future__ import annotations

from fractions import Fraction
from itertools import permutations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from fpdb_3_legacy.icm import (
    MAX_CELLS,
    MAX_WORK,
    AllInOutcome,
    ICMError,
    ICMTooLarge,
    allin_icm_ev,
    bubble_factor,
    exact_cost,
    icm_equities,
    outcome_equities,
)


def brute_force(stacks: list[float], payouts: list[float]) -> list[float]:
    """Every order the paid places can be filled in, each weighted by Harville's probability."""
    players = [i for i, stack in enumerate(stacks) if stack > 0]
    paid = min(len(payouts), len(players))
    equities = [0.0] * len(stacks)
    for order in permutations(players, paid):
        probability = 1.0
        remaining = sum(stacks[i] for i in players)
        for player in order:
            probability *= stacks[player] / remaining
            remaining -= stacks[player]
        for place, player in enumerate(order):
            equities[player] += probability * payouts[place]
    return equities


# --- reference values -------------------------------------------------------------


def test_the_classic_three_handed_example_matches_the_hand_computation() -> None:
    # Stacks 5000/3000/2000 for 50/30/20. First place goes with the chip share
    # (1/2, 3/10, 1/5); second place is drawn among the two left, e.g. for A:
    # 3/10 * 5/7 + 1/5 * 5/8 = 19/56; third is what remains.
    a1, b1, c1 = Fraction(1, 2), Fraction(3, 10), Fraction(1, 5)
    a2 = b1 * Fraction(5, 7) + c1 * Fraction(5, 8)
    b2 = a1 * Fraction(3, 5) + c1 * Fraction(3, 8)
    c2 = a1 * Fraction(2, 5) + b1 * Fraction(2, 7)
    expected = [
        50 * first + 30 * second + 20 * (1 - first - second) for first, second in ((a1, a2), (b1, b2), (c1, c2))
    ]

    assert icm_equities([5000, 3000, 2000], [50, 30, 20]) == pytest.approx([float(x) for x in expected], abs=1e-9)
    assert [round(float(x), 4) for x in expected] == [38.3929, 32.75, 28.8571]


@pytest.mark.parametrize(
    ("stacks", "payouts"),
    [
        ([2500, 1800, 1500, 1200, 700, 300], [65, 35]),  # 6-max SNG, two paid
        ([4200, 900, 3100, 2000, 1500, 600], [50, 30, 20]),
        ([12000, 9500, 7300, 6100, 5000, 4200, 3300, 2100, 500], [50, 30, 20]),  # 9-handed SNG
        ([15000, 11000, 9000, 8000, 7000, 5000, 3000, 1500, 500], [30, 20, 14, 10, 8, 6, 5, 4, 3]),  # FT
    ],
)
def test_matches_a_brute_force_over_every_finishing_order(stacks, payouts) -> None:
    assert icm_equities(stacks, payouts) == pytest.approx(brute_force(stacks, payouts), rel=1e-12)


def test_winner_take_all_is_chip_share() -> None:
    assert icm_equities([6000, 3000, 1000], [100]) == pytest.approx([60, 30, 10])


# --- properties -----------------------------------------------------------------

stacks_strategy = st.lists(st.integers(min_value=1, max_value=50_000), min_size=2, max_size=8)
payouts_strategy = st.lists(st.integers(min_value=0, max_value=1_000), min_size=1, max_size=8).map(
    lambda prizes: sorted(prizes, reverse=True)
)


@settings(max_examples=150, deadline=None)
@given(stacks=stacks_strategy, payouts=payouts_strategy)
def test_equities_add_up_to_the_prizes_left(stacks, payouts) -> None:
    assert sum(icm_equities(stacks, payouts)) == pytest.approx(sum(payouts[: len(stacks)]))


@settings(max_examples=100, deadline=None)
@given(stack=st.integers(min_value=1, max_value=50_000), players=st.integers(2, 8), payouts=payouts_strategy)
def test_equal_stacks_share_equally(stack, players, payouts) -> None:
    equities = icm_equities([stack] * players, payouts)

    assert equities == pytest.approx([sum(payouts[:players]) / players] * players)


@settings(max_examples=150, deadline=None)
@given(stacks=stacks_strategy, payouts=payouts_strategy)
def test_more_chips_never_means_less_equity(stacks, payouts) -> None:
    equities = icm_equities(stacks, payouts)

    for i, j in permutations(range(len(stacks)), 2):
        if stacks[i] > stacks[j]:
            assert equities[i] >= equities[j] - 1e-9


@settings(max_examples=100, deadline=None)
@given(stacks=stacks_strategy, payouts=payouts_strategy, factor=st.integers(2, 1000))
def test_the_chip_unit_does_not_matter(stacks, payouts, factor) -> None:
    assert icm_equities([s * factor for s in stacks], payouts) == pytest.approx(icm_equities(stacks, payouts))


@settings(max_examples=100, deadline=None)
@given(stacks=stacks_strategy, payouts=payouts_strategy)
def test_the_seat_order_does_not_matter(stacks, payouts) -> None:
    reversed_equities = icm_equities(list(reversed(stacks)), payouts)

    assert list(reversed(reversed_equities)) == pytest.approx(icm_equities(stacks, payouts))


@settings(max_examples=100, deadline=None)
@given(stacks=stacks_strategy, payouts=payouts_strategy)
def test_nobody_is_worth_more_than_first_or_less_than_the_last_prize_they_are_sure_of(stacks, payouts) -> None:
    equities = icm_equities(stacks, payouts)
    paid = payouts[: len(stacks)]
    floor = paid[-1] if len(paid) == len(stacks) else 0

    assert all(floor - 1e-9 <= equity <= paid[0] + 1e-9 for equity in equities)


# --- edges and refusals ---------------------------------------------------------------


def test_a_busted_player_wins_nothing_more() -> None:
    assert icm_equities([0, 5000, 5000], [50, 30, 20]) == pytest.approx([0.0, 40.0, 40.0])


def test_the_last_player_standing_takes_first_prize() -> None:
    assert icm_equities([0, 10000, 0], [50, 30, 20]) == pytest.approx([0.0, 50.0, 0.0])


def test_no_paid_place_means_no_equity() -> None:
    assert icm_equities([3000, 2000], [0, 0]) == [0.0, 0.0]


@pytest.mark.parametrize(
    ("stacks", "payouts"),
    [([1000, -5], [50, 50]), ([1000, 500], [50, -1]), ([0, 0], [10])],
    ids=["negative-stack", "negative-payout", "prizes-but-no-chips"],
)
def test_stacks_and_payouts_that_make_no_sense_are_refused(stacks, payouts) -> None:
    with pytest.raises(ICMError):
        icm_equities(stacks, payouts)


def test_a_whole_field_paying_deep_is_refused_rather_than_slow() -> None:
    steps, cells = exact_cost(30, 15)
    assert steps > MAX_WORK and cells > MAX_CELLS

    with pytest.raises(ICMTooLarge):
        icm_equities([1000] * 30, list(range(15, 0, -1)))


def test_a_large_field_paying_few_places_is_computed_without_caching_unpaid_sets() -> None:
    # Codex (#623): 1000 players for [60, 40] used to pass the guard and cache
    # 500,501 sets of 1000 values (~4 GB). Sets past the last paid place are now
    # neither walked nor cached: 1001 sets, about a million values.
    steps, cells = exact_cost(1000, 2)
    assert (steps, cells) == (1_999_000, 1_001_000)

    equities = icm_equities([1000] * 1000, [60, 40])

    assert equities == pytest.approx([0.1] * 1000)


@pytest.mark.parametrize(
    ("players", "paid", "expected"),
    [
        (3, 3, (3**2 + 3 * 2**2 + 3 * 1, 7 * 3)),  # 1 + 3 + 3 sets still awarding, of 3 values
        (4, 1, (4, 4)),  # winner-take-all: only the full table, one step per winner
        (5, 2, (25 + 5 * 4, 6 * 5)),
    ],
)
def test_the_cost_counts_only_the_sets_that_still_award_a_prize(players, paid, expected) -> None:
    assert exact_cost(players, paid) == expected


def test_a_final_table_paying_every_place_is_computed() -> None:
    assert sum(icm_equities([1000 * (i + 1) for i in range(10)], list(range(10, 0, -1)))) == pytest.approx(55)


# --- all-in $EV --------------------------------------------------------------------


def test_winner_take_all_icm_ev_is_chip_ev_in_prize_terms() -> None:
    # With one prize, equity is the chip share: a 60/40 flip for 2000 chips of a
    # 10000-chip table gains 0.2 * 2000 / 10000 of the prize.
    before = {"hero": 4000, "villain": 6000}
    outcomes = [
        AllInOutcome(0.6, {"hero": 8000, "villain": 2000}),
        AllInOutcome(0.4, {"hero": 0, "villain": 10000}),
    ]

    assert allin_icm_ev(before, outcomes, [100], "hero") == pytest.approx(0.6 * 8000 / 100 - 4000 / 100)


def test_a_chip_neutral_flip_on_the_bubble_loses_money() -> None:
    # Four left, three paid: an exact coinflip between two equal stacks gains
    # nothing in chips but costs equity (ICM's risk premium).
    before = {"hero": 3000, "villain": 3000, "short": 1000, "other": 3000}
    win = {"hero": 6000, "villain": 0, "short": 1000, "other": 3000}
    lose = {"hero": 0, "villain": 6000, "short": 1000, "other": 3000}

    ev = allin_icm_ev(before, [AllInOutcome(0.5, win), AllInOutcome(0.5, lose)], [50, 30, 20], "hero")

    assert ev < 0


def test_an_all_in_must_describe_its_outcomes_fully() -> None:
    before = {"hero": 1000, "villain": 1000}
    with pytest.raises(ICMError):
        allin_icm_ev(before, [AllInOutcome(0.7, {"hero": 2000, "villain": 0})], [100], "hero")
    with pytest.raises(ICMError):
        allin_icm_ev(before, [AllInOutcome(1.0, {"hero": 2000})], [100], "hero")
    with pytest.raises(ICMError):
        allin_icm_ev(before, [], [100], "hero")


# --- bubble factor -----------------------------------------------------------------


def test_winner_take_all_has_no_bubble() -> None:
    assert bubble_factor({"h": 3000, "v": 5000, "o": 2000}, [100], "h", "v") == pytest.approx(1.0)


def test_the_bubble_makes_losing_cost_more_than_winning_gains() -> None:
    stacks = {"h": 3000, "v": 3000, "s": 1000, "o": 3000}

    factor = bubble_factor(stacks, [50, 30, 20], "h", "v")

    assert factor > 1.0
    required = factor / (1 + factor)
    assert 0.5 < required < 1.0  # a call needs better than a coinflip


def test_a_player_cannot_be_all_in_against_themself_or_without_chips() -> None:
    with pytest.raises(ICMError):
        bubble_factor({"h": 1000, "v": 1000}, [100], "h", "h")
    with pytest.raises(ICMError):
        bubble_factor({"h": 0, "v": 1000, "o": 500}, [60, 40], "h", "v")


# --- prizes won by busting in the hand (#623) -------------------------------------------


def test_a_heads_up_coinflip_is_neutral_because_the_loser_still_takes_second_prize() -> None:
    # Codex's example: losing earns 40, so the flip is worth 0, and its bubble factor 1.
    before = {"hero": 5000, "villain": 5000}
    outcomes = [
        AllInOutcome(0.5, {"hero": 10000, "villain": 0}),
        AllInOutcome(0.5, {"hero": 0, "villain": 10000}),
    ]

    assert allin_icm_ev(before, outcomes, [60, 40], "hero") == pytest.approx(0.0)
    assert bubble_factor(before, [60, 40], "hero", "villain") == pytest.approx(1.0)


def test_a_player_busted_in_the_hand_takes_the_place_below_the_survivors() -> None:
    equities = outcome_equities({"a": 4000, "b": 3500, "c": 2500}, {"a": 10000, "b": 0, "c": 0}, [50, 30, 20])

    assert equities == pytest.approx({"a": 50.0, "b": 30.0, "c": 20.0})  # b started bigger, finishes higher


def test_players_who_bust_together_from_equal_stacks_share_their_places() -> None:
    equities = outcome_equities({"a": 4000, "b": 3000, "c": 3000}, {"a": 10000, "b": 0, "c": 0}, [50, 30, 20])

    assert equities == pytest.approx({"a": 50.0, "b": 25.0, "c": 25.0})


def test_busting_outside_the_paid_places_wins_nothing() -> None:
    equities = outcome_equities(
        {"a": 3000, "b": 3000, "c": 2000, "d": 2000}, {"a": 6000, "b": 0, "c": 2000, "d": 2000}, [50, 30, 20]
    )

    assert equities["b"] == 0.0
    assert sum(equities.values()) == pytest.approx(100.0)


def test_a_player_already_out_before_the_hand_stays_at_nothing() -> None:
    equities = outcome_equities({"a": 5000, "b": 5000, "gone": 0}, {"a": 10000, "b": 0, "gone": 0}, [50, 30, 20])

    assert equities == pytest.approx({"a": 50.0, "b": 30.0, "gone": 0.0})


@settings(max_examples=150, deadline=None)
@given(
    stacks=st.lists(st.integers(min_value=1, max_value=50_000), min_size=2, max_size=7),
    payouts=payouts_strategy,
    pair=st.tuples(st.integers(0, 6), st.integers(0, 6)),
)
def test_an_all_in_neither_creates_nor_destroys_prize_money(stacks, payouts, pair) -> None:
    winner, loser = (index % len(stacks) for index in pair)
    if winner == loser:
        return
    names = [f"p{i}" for i in range(len(stacks))]
    before = dict(zip(names, stacks, strict=True))
    after = dict(before)
    moved = min(before[names[winner]], before[names[loser]])
    after[names[winner]] += moved
    after[names[loser]] -= moved

    assert sum(outcome_equities(before, after, payouts).values()) == pytest.approx(sum(payouts[: len(stacks)]))
