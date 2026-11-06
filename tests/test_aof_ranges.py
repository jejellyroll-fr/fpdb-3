"""Range construction and chronological validation for All-in or Fold."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from fpdb_3_legacy.aof_ranges import (
    OBSERVATION_BIAS,
    ActionObservation,
    CalibrationObservation,
    PlayerSpecificRange,
    PopulationActionModel,
    PopulationObservedRange,
    RangeConditions,
    RangeObservation,
    UniformLegalRange,
    chronological_split,
    evaluate_range_snapshots,
    validate_chronologically,
)
from fpdb_3_legacy.equity import EquityEngine, load_poker_eval


def _conditions(*, player_id: int | None = None) -> RangeConditions:
    return RangeConditions(
        site_id=140,
        category="aof_omaha",
        role="call_shove",
        active_opponents=2,
        before_hand_id=100,
        player_id=player_id,
    )


def _observation(
    hand_id: int,
    cards: str,
    *,
    player_id: int = 7,
    site_id: int = 140,
    category: str = "aof_omaha",
    role: str = "call_shove",
    active_opponents: int = 2,
) -> RangeObservation:
    return RangeObservation(
        hand_id=hand_id,
        player_id=player_id,
        site_id=site_id,
        category=category,
        role=role,
        active_opponents=active_opponents,
        hole_cards=cards,
    )


def _action(
    hand_id: int,
    decision: str,
    *,
    site_id: int = 140,
    role: str = "call_shove",
    active_opponents: int = 2,
) -> ActionObservation:
    return ActionObservation(
        hand_id=hand_id,
        player_id=hand_id + 100,
        site_id=site_id,
        category="aof_omaha",
        role=role,
        active_opponents=active_opponents,
        decision=decision,
    )


def test_uniform_range_is_explicitly_not_an_observed_human_model() -> None:
    snapshot = UniformLegalRange().build(_conditions())

    assert snapshot.status == "ready"
    assert snapshot.uniform
    assert snapshot.pockets == ()
    assert snapshot.metadata.identifier == "uniform_legal"
    assert snapshot.metadata.sample_size == 0
    assert snapshot.metadata.observation_bias == OBSERVATION_BIAS


def test_uniform_range_dispatches_to_native_unknown_pockets() -> None:
    engine = MagicMock()
    expected = object()
    engine.evaluate_uniform_unknown.return_value = expected
    snapshots = [UniformLegalRange().build(_conditions()) for _ in range(2)]

    result = evaluate_range_snapshots(
        engine,
        "omaha",
        ("As", "Ks", "Qh", "Jh"),
        snapshots,
        ("Ts", "9s", "2d"),
        iterations=20_000,
        seed=7,
    )

    assert result is expected
    engine.evaluate_uniform_unknown.assert_called_once_with(
        "omaha",
        ("As", "Ks", "Qh", "Jh"),
        ("Ts", "9s", "2d"),
        opponents=2,
        dead=(),
        iterations=20_000,
        seed=7,
    )
    engine.evaluate_weighted_range.assert_not_called()


def test_observed_range_dispatches_with_its_name_and_version() -> None:
    engine = MagicMock()
    expected = object()
    engine.evaluate_weighted_range.return_value = expected
    snapshot = PopulationObservedRange(minimum_observations=1).build(
        _conditions(),
        [_observation(1, "Ah Ad 7c 6c")],
    )

    result = evaluate_range_snapshots(
        engine,
        "omaha",
        ("As", "Ks", "Qh", "Jh"),
        [snapshot],
        ("Ts", "9s", "2d"),
        iterations=20_000,
        seed=7,
    )

    assert result is expected
    assert engine.evaluate_weighted_range.call_args.kwargs["range_model"] == "population_observed"
    assert engine.evaluate_weighted_range.call_args.kwargs["range_version"] == 1
    engine.evaluate_uniform_unknown.assert_not_called()


def test_uniform_and_observed_ranges_cannot_be_silently_mixed() -> None:
    observed = PopulationObservedRange(minimum_observations=1).build(
        _conditions(),
        [_observation(1, "Ah Ad 7c 6c")],
    )

    with pytest.raises(ValueError, match="cannot be mixed"):
        evaluate_range_snapshots(
            MagicMock(),
            "omaha",
            ("As", "Ks", "Qh", "Jh"),
            [UniformLegalRange().build(_conditions()), observed],
            ("Ts", "9s", "2d"),
            iterations=20_000,
            seed=7,
        )


def test_native_observed_omaha_range_has_a_reproducible_seeded_output() -> None:
    backend = load_poker_eval()
    if backend is None:
        pytest.skip("optional pypoker-eval backend is not installed")
    snapshot = PopulationObservedRange(minimum_observations=1).build(
        _conditions(),
        [_observation(1, "Ah Ad 7c 6c")],
    )

    result = evaluate_range_snapshots(
        EquityEngine(backend),
        "omaha",
        ("As", "Ks", "Qh", "Jh"),
        [snapshot],
        ("Ts", "9s", "2d"),
        iterations=20_000,
        seed=7,
    )

    assert abs(result.players[0].equity - Decimal("0.713")) <= Decimal("0.01")
    assert result.samples == 20_000


def test_population_range_filters_every_condition_and_never_reads_the_future() -> None:
    matching = [
        _observation(10, "As Ks Qh Jh"),
        _observation(11, "Jh Qh Ks As"),
        _observation(12, "2c 3c 4d 5d"),
    ]
    rejected = [
        _observation(100, "6c 7c 8d 9d"),  # current hand
        _observation(101, "6c 7c 8d 9d"),  # future hand
        _observation(13, "6c 7c 8d 9d", site_id=2),
        _observation(14, "6c 7c 8d 9d", category="aof_holdem"),
        _observation(15, "6c 7c 8d 9d", role="open_shove"),
        _observation(16, "6c 7c 8d 9d", active_opponents=1),
        _observation(17, "0x 0x 0x 0x"),
    ]

    snapshot = PopulationObservedRange(minimum_observations=3).build(
        _conditions(),
        [*matching, *rejected],
    )

    assert snapshot.status == "ready"
    assert snapshot.metadata.sample_size == 3
    assert [(entry.cards, entry.weight) for entry in snapshot.pockets] == [
        (("2c", "3c", "4d", "5d"), Decimal(1)),
        (("As", "Jh", "Ks", "Qh"), Decimal(2)),
    ]


def test_population_range_refuses_to_disguise_a_tiny_sample() -> None:
    snapshot = PopulationObservedRange(minimum_observations=3).build(
        _conditions(),
        [_observation(10, "As Ks Qh Jh"), _observation(11, "2c 3c 4d 5d")],
    )

    assert snapshot.status == "insufficient"
    assert snapshot.pockets == ()
    assert snapshot.reason == "population sample 2 is below 3"


def test_population_range_keeps_a_bounded_recent_window() -> None:
    snapshot = PopulationObservedRange(
        minimum_observations=1,
        maximum_observations=2,
    ).build(
        _conditions(),
        [
            _observation(1, "As Ks Qh Jh"),
            _observation(2, "2c 3c 4d 5d"),
            _observation(3, "6c 7c 8d 9d"),
        ],
    )

    assert snapshot.metadata.sample_size == 2
    assert snapshot.metadata.conditions.maximum_observations == 2
    assert {entry.cards for entry in snapshot.pockets} == {
        ("2c", "3c", "4d", "5d"),
        ("6c", "7c", "8d", "9d"),
    }


def test_population_cutoff_uses_play_time_not_import_order() -> None:
    conditions = RangeConditions(
        site_id=140,
        category="aof_omaha",
        role="call_shove",
        active_opponents=2,
        before_hand_id=50,
        before_started_at="2026-07-28 12:00:00",
    )
    observations = [
        replace(
            _observation(10, "As Ks Qh Jh"),
            started_at="2026-07-28 13:00:00",
        ),
        replace(
            _observation(100, "2c 3c 4d 5d"),
            started_at="2026-07-28 11:00:00",
        ),
    ]

    snapshot = PopulationObservedRange(minimum_observations=1).build(
        conditions,
        observations,
    )

    assert [entry.cards for entry in snapshot.pockets] == [("2c", "3c", "4d", "5d")]


def test_action_model_uses_all_decisions_not_only_revealed_pockets() -> None:
    snapshot = PopulationActionModel(minimum_observations=4).build(
        _conditions(),
        [
            _action(1, "fold"),
            _action(2, "fold"),
            _action(3, "fold"),
            _action(4, "allin"),
        ],
    )

    assert snapshot.status == "ready"
    assert (snapshot.fold_count, snapshot.all_in_count, snapshot.sample_size) == (3, 1, 4)
    assert snapshot.all_in_probability == Decimal("0.3")


def test_action_model_filters_context_future_and_caps_the_recent_window() -> None:
    snapshot = PopulationActionModel(
        minimum_observations=2,
        maximum_observations=2,
    ).build(
        _conditions(),
        [
            _action(1, "allin"),
            _action(2, "fold"),
            _action(3, "fold"),
            _action(100, "allin"),
            _action(4, "allin", site_id=2),
            _action(5, "allin", role="overcall"),
            _action(6, "allin", active_opponents=1),
            _action(7, "check"),
        ],
    )

    assert snapshot.status == "ready"
    assert (snapshot.fold_count, snapshot.all_in_count) == (2, 0)
    assert snapshot.all_in_probability == Decimal("0.5") / Decimal(3)


def test_action_model_refuses_a_tiny_sample() -> None:
    snapshot = PopulationActionModel(minimum_observations=3).build(
        _conditions(),
        [_action(1, "fold"), _action(2, "allin")],
    )

    assert snapshot.status == "insufficient"
    assert snapshot.all_in_probability is None
    assert snapshot.reason == "action sample 2 is below 3"


def test_player_range_shrinks_a_small_personal_sample_toward_population() -> None:
    observations = [
        *[_observation(hand, "As Ks Qh Jh", player_id=7) for hand in range(1, 6)],
        *[_observation(hand, "2c 3c 4d 5d", player_id=8) for hand in range(6, 11)],
    ]

    snapshot = PlayerSpecificRange(
        minimum_population=10,
        minimum_player=5,
        prior_strength=5,
    ).build(_conditions(player_id=7), observations)

    assert snapshot.status == "ready"
    assert snapshot.metadata.population_sample_size == 10
    assert snapshot.metadata.player_sample_size == 5
    assert {entry.cards: entry.weight for entry in snapshot.pockets} == {
        ("2c", "3c", "4d", "5d"): Decimal("0.25"),
        ("As", "Jh", "Ks", "Qh"): Decimal("0.75"),
    }


def test_player_range_requires_a_real_personal_sample_before_use() -> None:
    observations = [
        *[_observation(hand, "As Ks Qh Jh", player_id=7) for hand in range(1, 4)],
        *[_observation(hand, "2c 3c 4d 5d", player_id=8) for hand in range(4, 11)],
    ]

    snapshot = PlayerSpecificRange(
        minimum_population=10,
        minimum_player=5,
        prior_strength=5,
    ).build(_conditions(player_id=7), observations)

    assert snapshot.status == "insufficient"
    assert snapshot.pockets == ()
    assert snapshot.reason == "player sample 3 is below 5"


def test_player_range_requires_a_player_scope() -> None:
    with pytest.raises(ValueError, match="player_id"):
        PlayerSpecificRange().build(_conditions(), [])


def test_chronological_split_keeps_the_latest_hands_out_of_training() -> None:
    observations = [CalibrationObservation(hand, 500_000, 1_000_000, True) for hand in (30, 10, 40, 20)]

    train, test = chronological_split(observations, test_fraction=Decimal("0.5"))

    assert [item.hand_id for item in train] == [10, 20]
    assert [item.hand_id for item in test] == [30, 40]


def test_validation_reports_calibration_stability_and_hidden_card_coverage() -> None:
    observations = [
        CalibrationObservation(1, 100_000, 0, True),
        CalibrationObservation(2, 200_000, 0, True),
        CalibrationObservation(3, 400_000, 500_000, True),
        CalibrationObservation(4, 600_000, 500_000, True),
        CalibrationObservation(5, None, None, False),
        CalibrationObservation(6, 800_000, 1_000_000, True),
    ]

    report = validate_chronologically(
        observations,
        bins=2,
        test_fraction=Decimal("0.5"),
    )

    assert (report.train_size, report.test_size, report.evaluated) == (3, 3, 2)
    assert report.observable_coverage_ppm == 666_667
    assert report.predicted_equity_ppm == 700_000
    assert report.realized_equity_ppm == 750_000
    assert report.calibration_error_ppm == 50_000
    assert report.brier_ppm == 25_000
    assert report.stability_gap_ppm == 200_000
    assert [(item.count, item.predicted_ppm, item.realized_ppm) for item in report.bins] == [
        (0, None, None),
        (2, 700_000, 750_000),
    ]


def test_validation_rejects_an_invalid_split_or_bin_count() -> None:
    with pytest.raises(ValueError, match="test_fraction"):
        chronological_split([], test_fraction=Decimal(1))
    with pytest.raises(ValueError, match="bins"):
        validate_chronologically([], bins=0)
