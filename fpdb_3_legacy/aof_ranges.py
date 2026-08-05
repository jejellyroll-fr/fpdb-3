"""Versioned, chronologically safe range models for All-in or Fold."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

from fpdb_3_legacy.autonotes_aof import AOF_HOLDEM_CATEGORY, AOF_OMAHA_CATEGORY
from fpdb_3_legacy.equity import EquityEngine, EquityResult, WeightedPocket

UNIFORM_RANGE_MODEL = "uniform_legal"
POPULATION_RANGE_MODEL = "population_observed"
PLAYER_RANGE_MODEL = "player_specific"
POPULATION_ACTION_MODEL = "population_action_frequency"
RANGE_MODEL_VERSION = 1
ACTION_MODEL_VERSION = 1
DEFAULT_POPULATION_MINIMUM = 25
DEFAULT_ACTION_MINIMUM = 25
DEFAULT_PLAYER_MINIMUM = 5
DEFAULT_PLAYER_PRIOR = 25
DEFAULT_RANGE_MAXIMUM = 5_000
OBSERVATION_BIAS = "showdown-biased: hidden folds and unshown all-ins are absent from the card distribution"
_PPM = Decimal(1_000_000)
_POCKET_SIZE = {AOF_OMAHA_CATEGORY: 4, AOF_HOLDEM_CATEGORY: 2}
_RANKS = frozenset("23456789TJQKA")
_SUITS = frozenset("cdhs")


@dataclass(frozen=True)
class RangeConditions:
    """The room/game/action population one model is allowed to learn from."""

    site_id: int
    category: str
    role: str
    active_opponents: int
    before_hand_id: int
    player_id: int | None = None
    before_started_at: str | None = None
    maximum_observations: int = DEFAULT_RANGE_MAXIMUM


@dataclass(frozen=True)
class RangeObservation:
    """One revealed all-in pocket available as historical training evidence."""

    hand_id: int
    player_id: int
    site_id: int
    category: str
    role: str
    active_opponents: int
    hole_cards: str
    started_at: str | None = None


@dataclass(frozen=True)
class ActionObservation:
    """One historical fold/all-in answer available to the behavior model."""

    hand_id: int
    player_id: int
    site_id: int
    category: str
    role: str
    active_opponents: int
    decision: str
    started_at: str | None = None


@dataclass(frozen=True)
class RangeMetadata:
    """Auditable provenance carried by every produced range."""

    identifier: str
    version: int
    built_at: datetime
    sample_size: int
    population_sample_size: int
    player_sample_size: int
    conditions: RangeConditions
    observation_bias: str


@dataclass(frozen=True)
class RangeSnapshot:
    """A legal uniform range or an explicit weighted pocket distribution."""

    metadata: RangeMetadata
    pockets: tuple[WeightedPocket, ...]
    status: str
    uniform: bool = False
    reason: str | None = None


@dataclass(frozen=True)
class ActionSnapshot:
    """A bounded historical estimate of one fold-versus-all-in response."""

    identifier: str
    version: int
    conditions: RangeConditions
    sample_size: int
    all_in_count: int
    fold_count: int
    all_in_probability: Decimal | None
    status: str
    reason: str | None = None


class RangeModel(Protocol):
    """Common construction contract for AoF range models."""

    identifier: str
    version: int

    def build(
        self,
        conditions: RangeConditions,
        observations: Sequence[RangeObservation],
    ) -> RangeSnapshot: ...


class UniformLegalRange:
    """All legal unknown pockets, delegated to poker-eval's native unknowns."""

    identifier = UNIFORM_RANGE_MODEL
    version = RANGE_MODEL_VERSION

    def build(
        self,
        conditions: RangeConditions,
        observations: Sequence[RangeObservation] = (),
    ) -> RangeSnapshot:
        del observations
        return RangeSnapshot(
            metadata=_metadata(self.identifier, conditions),
            pockets=(),
            status="ready",
            uniform=True,
        )


class PopulationObservedRange:
    """Empirical pocket frequencies for one room/game/role/table state."""

    identifier = POPULATION_RANGE_MODEL
    version = RANGE_MODEL_VERSION

    def __init__(
        self,
        *,
        minimum_observations: int = DEFAULT_POPULATION_MINIMUM,
        maximum_observations: int = DEFAULT_RANGE_MAXIMUM,
    ) -> None:
        if minimum_observations <= 0 or maximum_observations < minimum_observations:
            msg = "range observation bounds are inconsistent"
            raise ValueError(msg)
        self.minimum_observations = minimum_observations
        self.maximum_observations = maximum_observations

    def build(
        self,
        conditions: RangeConditions,
        observations: Sequence[RangeObservation],
    ) -> RangeSnapshot:
        conditions = replace(
            conditions,
            maximum_observations=self.maximum_observations,
        )
        pockets = _matching_pockets(conditions, observations)[: self.maximum_observations]
        counts = Counter(pocket for _player_id, pocket in pockets)
        metadata = _metadata(
            self.identifier,
            conditions,
            sample_size=len(pockets),
            population_sample_size=len(pockets),
        )
        if len(pockets) < self.minimum_observations:
            return RangeSnapshot(
                metadata=metadata,
                pockets=(),
                status="insufficient",
                reason=f"population sample {len(pockets)} is below {self.minimum_observations}",
            )
        return RangeSnapshot(
            metadata=metadata,
            pockets=tuple(
                WeightedPocket(cards=cards, weight=Decimal(count)) for cards, count in sorted(counts.items())
            ),
            status="ready",
        )


class PlayerSpecificRange:
    """Shrink one player's observed range toward the matching population."""

    identifier = PLAYER_RANGE_MODEL
    version = RANGE_MODEL_VERSION

    def __init__(
        self,
        *,
        minimum_population: int = DEFAULT_POPULATION_MINIMUM,
        minimum_player: int = DEFAULT_PLAYER_MINIMUM,
        prior_strength: int = DEFAULT_PLAYER_PRIOR,
        maximum_observations: int = DEFAULT_RANGE_MAXIMUM,
    ) -> None:
        if min(minimum_population, minimum_player, prior_strength) <= 0 or maximum_observations < minimum_population:
            msg = "range sample bounds and prior_strength are inconsistent"
            raise ValueError(msg)
        self.minimum_population = minimum_population
        self.minimum_player = minimum_player
        self.prior_strength = prior_strength
        self.maximum_observations = maximum_observations

    def build(
        self,
        conditions: RangeConditions,
        observations: Sequence[RangeObservation],
    ) -> RangeSnapshot:
        if conditions.player_id is None:
            msg = "PlayerSpecificRange requires conditions.player_id"
            raise ValueError(msg)
        conditions = replace(
            conditions,
            maximum_observations=self.maximum_observations,
        )
        pockets = _matching_pockets(conditions, observations)[: self.maximum_observations]
        player_pockets = [cards for player_id, cards in pockets if player_id == conditions.player_id]
        metadata = _metadata(
            self.identifier,
            conditions,
            sample_size=len(pockets),
            population_sample_size=len(pockets),
            player_sample_size=len(player_pockets),
        )
        if len(pockets) < self.minimum_population:
            return RangeSnapshot(
                metadata=metadata,
                pockets=(),
                status="insufficient",
                reason=f"population sample {len(pockets)} is below {self.minimum_population}",
            )
        if len(player_pockets) < self.minimum_player:
            return RangeSnapshot(
                metadata=metadata,
                pockets=(),
                status="insufficient",
                reason=f"player sample {len(player_pockets)} is below {self.minimum_player}",
            )

        population_counts = Counter(cards for _player_id, cards in pockets)
        player_counts = Counter(player_pockets)
        player_weight = Decimal(len(player_pockets)) / Decimal(len(player_pockets) + self.prior_strength)
        population_weight = Decimal(1) - player_weight
        cards_seen = sorted(set(population_counts) | set(player_counts))
        population_total = Decimal(len(pockets))
        player_total = Decimal(len(player_pockets))
        weighted = []
        for cards in cards_seen:
            probability = (
                population_weight * Decimal(population_counts[cards]) / population_total
                + player_weight * Decimal(player_counts[cards]) / player_total
            )
            if probability > 0:
                weighted.append(WeightedPocket(cards=cards, weight=probability))
        return RangeSnapshot(metadata=metadata, pockets=tuple(weighted), status="ready")


class PopulationActionModel:
    """Jeffreys-smoothed action frequency for one historical table state."""

    identifier = POPULATION_ACTION_MODEL
    version = ACTION_MODEL_VERSION

    def __init__(
        self,
        *,
        minimum_observations: int = DEFAULT_ACTION_MINIMUM,
        maximum_observations: int = DEFAULT_RANGE_MAXIMUM,
    ) -> None:
        if minimum_observations <= 0 or maximum_observations < minimum_observations:
            msg = "action observation bounds are inconsistent"
            raise ValueError(msg)
        self.minimum_observations = minimum_observations
        self.maximum_observations = maximum_observations

    def build(
        self,
        conditions: RangeConditions,
        observations: Sequence[ActionObservation],
    ) -> ActionSnapshot:
        """Return a finite posterior even when one action has not been seen."""
        conditions = replace(
            conditions,
            maximum_observations=self.maximum_observations,
        )
        decisions = _matching_actions(conditions, observations)[: self.maximum_observations]
        all_ins = decisions.count("allin")
        folds = decisions.count("fold")
        sample_size = len(decisions)
        if sample_size < self.minimum_observations:
            return ActionSnapshot(
                identifier=self.identifier,
                version=self.version,
                conditions=conditions,
                sample_size=sample_size,
                all_in_count=all_ins,
                fold_count=folds,
                all_in_probability=None,
                status="insufficient",
                reason=f"action sample {sample_size} is below {self.minimum_observations}",
            )
        alpha = Decimal(all_ins) + Decimal("0.5")
        beta = Decimal(folds) + Decimal("0.5")
        total = alpha + beta
        return ActionSnapshot(
            identifier=self.identifier,
            version=self.version,
            conditions=conditions,
            sample_size=sample_size,
            all_in_count=all_ins,
            fold_count=folds,
            all_in_probability=alpha / total,
            status="ready",
        )


def evaluate_range_snapshots(
    engine: EquityEngine,
    game: str,
    hero: Sequence[str],
    snapshots: Sequence[RangeSnapshot],
    board: Sequence[str],
    *,
    dead: Sequence[str] = (),
    iterations: int,
    seed: int,
) -> EquityResult:
    """Dispatch one or more model snapshots through the matching engine API."""
    if not snapshots:
        msg = "at least one opponent range is required"
        raise ValueError(msg)
    unavailable = [snapshot for snapshot in snapshots if snapshot.status != "ready"]
    if unavailable:
        msg = unavailable[0].reason or "an opponent range is unavailable"
        raise ValueError(msg)
    uniform = [snapshot.uniform for snapshot in snapshots]
    if all(uniform):
        return engine.evaluate_uniform_unknown(
            game,
            hero,
            board,
            opponents=len(snapshots),
            dead=dead,
            iterations=iterations,
            seed=seed,
        )
    if any(uniform):
        msg = "uniform and explicit opponent ranges cannot be mixed in one evaluation"
        raise ValueError(msg)
    identifiers = {snapshot.metadata.identifier for snapshot in snapshots}
    versions = {snapshot.metadata.version for snapshot in snapshots}
    if len(identifiers) != 1 or len(versions) != 1:
        msg = "all opponent range snapshots must use one model and version"
        raise ValueError(msg)
    return engine.evaluate_weighted_range(
        game,
        hero,
        [snapshot.pockets for snapshot in snapshots],
        board,
        dead=dead,
        iterations=iterations,
        seed=seed,
        range_model=next(iter(identifiers)),
        range_version=next(iter(versions)),
    )


@dataclass(frozen=True)
class CalibrationObservation:
    """One out-of-sample prediction and its realized share of the pot."""

    hand_id: int
    predicted_equity_ppm: int | None
    realized_share_ppm: int | None
    cards_observable: bool


@dataclass(frozen=True)
class CalibrationBin:
    """Predicted and realized equity within one equal-width probability bin."""

    lower_ppm: int
    upper_ppm: int
    count: int
    predicted_ppm: int | None
    realized_ppm: int | None
    error_ppm: int | None


@dataclass(frozen=True)
class RangeValidationReport:
    """Chronological holdout diagnostics; it never enables Weak AI by itself."""

    train_size: int
    test_size: int
    evaluated: int
    observable_coverage_ppm: int
    predicted_equity_ppm: int | None
    realized_equity_ppm: int | None
    calibration_error_ppm: int | None
    brier_ppm: int | None
    stability_gap_ppm: int | None
    bins: tuple[CalibrationBin, ...]


def chronological_split(
    observations: Sequence[CalibrationObservation],
    *,
    test_fraction: Decimal = Decimal("0.25"),
) -> tuple[tuple[CalibrationObservation, ...], tuple[CalibrationObservation, ...]]:
    """Split by hand id so no future result can train an earlier prediction."""
    if not Decimal(0) < test_fraction < Decimal(1):
        msg = "test_fraction must be between zero and one"
        raise ValueError(msg)
    ordered = tuple(sorted(observations, key=lambda item: item.hand_id))
    if len(ordered) < 2:
        return ordered, ()
    test_size = max(1, _rounded_int(Decimal(len(ordered)) * test_fraction))
    test_size = min(test_size, len(ordered) - 1)
    return ordered[:-test_size], ordered[-test_size:]


def validate_chronologically(
    observations: Sequence[CalibrationObservation],
    *,
    bins: int = 5,
    test_fraction: Decimal = Decimal("0.25"),
) -> RangeValidationReport:
    """Measure calibration, stability and visible-card coverage on the holdout."""
    if bins <= 0:
        msg = "bins must be positive"
        raise ValueError(msg)
    train, test = chronological_split(observations, test_fraction=test_fraction)
    eligible = tuple(
        item
        for item in test
        if item.cards_observable and item.predicted_equity_ppm is not None and item.realized_share_ppm is not None
    )
    coverage = _ratio_ppm(len(eligible), len(test))
    predicted = _mean(item.predicted_equity_ppm for item in eligible)
    realized = _mean(item.realized_share_ppm for item in eligible)
    binned = _calibration_bins(eligible, bins)
    calibration_error = (
        _rounded_int(
            sum(
                (Decimal(item.count * int(item.error_ppm or 0)) for item in binned if item.count),
                start=Decimal(0),
            )
            / Decimal(len(eligible)),
        )
        if eligible
        else None
    )
    brier = (
        _rounded_int(
            sum(
                (_squared_error(item) for item in eligible),
                start=Decimal(0),
            )
            / Decimal(len(eligible))
            / _PPM,
        )
        if eligible
        else None
    )
    midpoint = len(eligible) // 2
    early = _mean(item.predicted_equity_ppm for item in eligible[:midpoint])
    late = _mean(item.predicted_equity_ppm for item in eligible[midpoint:])
    stability = abs(early - late) if early is not None and late is not None else None
    return RangeValidationReport(
        train_size=len(train),
        test_size=len(test),
        evaluated=len(eligible),
        observable_coverage_ppm=coverage,
        predicted_equity_ppm=predicted,
        realized_equity_ppm=realized,
        calibration_error_ppm=calibration_error,
        brier_ppm=brier,
        stability_gap_ppm=stability,
        bins=binned,
    )


def _matching_pockets(
    conditions: RangeConditions,
    observations: Sequence[RangeObservation],
) -> list[tuple[int, tuple[str, ...]]]:
    matches: list[tuple[str, int, int, tuple[str, ...]]] = []
    for observation in observations:
        if (
            _is_current_or_future(observation, conditions)
            or observation.site_id != conditions.site_id
            or observation.category != conditions.category
            or observation.role != conditions.role
            or observation.active_opponents != conditions.active_opponents
        ):
            continue
        cards = _canonical_pocket(observation.hole_cards, conditions.category)
        if cards:
            matches.append(
                (
                    observation.started_at or "",
                    observation.hand_id,
                    observation.player_id,
                    cards,
                ),
            )
    ordered = sorted(
        matches,
        key=lambda item: (item[0], item[1]),
        reverse=True,
    )
    return [(player_id, cards) for _started_at, _hand_id, player_id, cards in ordered]


def _matching_actions(
    conditions: RangeConditions,
    observations: Sequence[ActionObservation],
) -> list[str]:
    matches: list[tuple[str, int, str]] = []
    for observation in observations:
        if (
            _is_current_or_future(observation, conditions)
            or observation.site_id != conditions.site_id
            or observation.category != conditions.category
            or observation.role != conditions.role
            or observation.active_opponents != conditions.active_opponents
            or observation.decision not in {"allin", "fold"}
        ):
            continue
        matches.append(
            (
                observation.started_at or "",
                observation.hand_id,
                observation.decision,
            ),
        )
    ordered = sorted(matches, key=lambda item: (item[0], item[1]), reverse=True)
    return [decision for _started_at, _hand_id, decision in ordered]


def _is_current_or_future(
    observation: RangeObservation | ActionObservation,
    conditions: RangeConditions,
) -> bool:
    if conditions.before_started_at is not None:
        if observation.started_at is None:
            return True
        return (observation.started_at, observation.hand_id) >= (
            conditions.before_started_at,
            conditions.before_hand_id,
        )
    return observation.hand_id >= conditions.before_hand_id


def _canonical_pocket(value: str, category: str) -> tuple[str, ...]:
    expected = _POCKET_SIZE.get(category)
    cards = tuple(str(value or "").split())
    if (
        expected is None
        or len(cards) != expected
        or len(set(cards)) != expected
        or any(len(card) != 2 or card[0] not in _RANKS or card[1] not in _SUITS for card in cards)
    ):
        return ()
    return tuple(sorted(cards))


def _metadata(
    identifier: str,
    conditions: RangeConditions,
    *,
    sample_size: int = 0,
    population_sample_size: int = 0,
    player_sample_size: int = 0,
) -> RangeMetadata:
    return RangeMetadata(
        identifier=identifier,
        version=RANGE_MODEL_VERSION,
        built_at=datetime.now(UTC),
        sample_size=sample_size,
        population_sample_size=population_sample_size,
        player_sample_size=player_sample_size,
        conditions=conditions,
        observation_bias=OBSERVATION_BIAS,
    )


def _calibration_bins(
    observations: Sequence[CalibrationObservation],
    bins: int,
) -> tuple[CalibrationBin, ...]:
    width = 1_000_000 // bins
    groups: list[list[CalibrationObservation]] = [[] for _ in range(bins)]
    for observation in observations:
        predicted = min(max(int(observation.predicted_equity_ppm or 0), 0), 1_000_000)
        index = min(predicted * bins // 1_000_001, bins - 1)
        groups[index].append(observation)
    result = []
    for index, group in enumerate(groups):
        bin_predicted = _mean(item.predicted_equity_ppm for item in group)
        bin_realized = _mean(item.realized_share_ppm for item in group)
        lower = index * width
        upper = 1_000_000 if index == bins - 1 else (index + 1) * width
        result.append(
            CalibrationBin(
                lower_ppm=lower,
                upper_ppm=upper,
                count=len(group),
                predicted_ppm=bin_predicted,
                realized_ppm=bin_realized,
                error_ppm=(
                    abs(bin_predicted - bin_realized)
                    if bin_predicted is not None and bin_realized is not None
                    else None
                ),
            ),
        )
    return tuple(result)


def _squared_error(observation: CalibrationObservation) -> Decimal:
    assert observation.predicted_equity_ppm is not None
    assert observation.realized_share_ppm is not None
    return (Decimal(observation.predicted_equity_ppm) - observation.realized_share_ppm) ** 2


def _mean(values) -> int | None:
    materialized = [int(value) for value in values if value is not None]
    if not materialized:
        return None
    return _rounded_int(Decimal(sum(materialized)) / len(materialized))


def _ratio_ppm(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        return 0
    return _rounded_int(Decimal(numerator) * _PPM / denominator)


def _rounded_int(value: Decimal) -> int:
    return int(Decimal(value).to_integral_value(rounding=ROUND_HALF_UP))
