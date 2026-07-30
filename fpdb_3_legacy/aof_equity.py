"""All-in or Fold equity and decision EV on immutable post-import snapshots."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass, replace
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal
from math import sqrt
from typing import Any

from fpdb_3_legacy.aof_ranges import (
    ACTION_MODEL_VERSION,
    POPULATION_ACTION_MODEL,
    POPULATION_RANGE_MODEL,
    RANGE_MODEL_VERSION,
    ActionSnapshot,
    PopulationActionModel,
    PopulationObservedRange,
    RangeConditions,
    RangeObservation,
    RangeSnapshot,
    evaluate_range_snapshots,
)
from fpdb_3_legacy.autonotes_aof import (
    AOF_HOLDEM_CATEGORY,
    AOF_OMAHA_CATEGORY,
    KNOWN_BACKEND_VERSION,
    AofDecision,
    AofDecisionAnalysis,
)
from fpdb_3_legacy.equity import EquityEngine, EquityUnavailableError
from fpdb_3_legacy.equity_async import AsyncEquityService, EquityAnalysisJob, EquitySubmission
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("aof_equity")

KNOWN_ANALYSIS_VERSION = 1
KNOWN_RANGE_MODEL = "actual_known"
KNOWN_RANGE_VERSION = 1
KNOWN_BACKEND = "pypoker-eval"
RANGE_ANALYSIS_VERSION = 1
RANGE_ITERATIONS = 20_000
DECISION_EV_RANGE_MODEL = "population_decision_ev_prerake"
DECISION_EV_RANGE_VERSION = 1
DECISION_EV_ANALYSIS_VERSION = 1
DECISION_CONFIDENCE_Z = Decimal("1.96")
_PPM = Decimal(1_000_000)
_CENTS = Decimal(100)
_GAME_BY_CATEGORY = {
    AOF_OMAHA_CATEGORY: "omaha",
    AOF_HOLDEM_CATEGORY: "holdem",
}
_POCKET_SIZE_BY_CATEGORY = {
    AOF_OMAHA_CATEGORY: 4,
    AOF_HOLDEM_CATEGORY: 2,
}


@dataclass(frozen=True)
class PotLayer:
    """One gross/net pot layer and the players still entitled to win it."""

    gross_cents: int
    net_cents: int
    contributors: tuple[str, ...]
    eligible: tuple[str, ...]


@dataclass(frozen=True)
class RangeOpponent:
    """One other actor and the context of their actual AoF decision."""

    player: str
    player_id: int
    role: str
    active_opponents: int
    decision: str
    blind_committed: int
    amount_to_commit: int
    action_index: int


class _RangeIncompleteError(ValueError):
    """A modeled result cannot be produced from the available evidence."""


@dataclass(frozen=True)
class KnownDecisionRequest:
    """Immutable data needed to analyze one all-in after import returns."""

    decision_id: int
    hand_id: int
    player: str
    player_id: int
    category: str
    role: str
    active_opponents: int
    pot_before: int
    amount_to_commit: int
    blind_committed: int
    big_blind_cents: int
    action_index: int
    flop: tuple[str, ...]
    pockets: tuple[tuple[str, tuple[str, ...]], ...]
    layers: tuple[PotLayer, ...]
    opponents: tuple[RangeOpponent, ...]


@dataclass(frozen=True)
class KnownCardsHandRequest:
    """Every exact-card decision belonging to one committed hand."""

    hand_id: int
    decisions: tuple[KnownDecisionRequest, ...]


@dataclass(frozen=True)
class KnownCardsHandResult:
    """Analysis rows produced and persisted together for one hand."""

    hand_id: int
    analyses: tuple[AofDecisionAnalysis, ...]


@dataclass(frozen=True)
class ModeledCaller:
    """One opponent who reaches an all-in branch in the decision model."""

    player: str
    role: str
    active_opponents: int
    total_commitment: int


@dataclass(frozen=True)
class DecisionScenario:
    """One complete branch of the future fold/call tree."""

    probability: Decimal
    callers: tuple[ModeledCaller, ...]
    action_sample: int | None


@dataclass(frozen=True)
class ScenarioValue:
    """The conditional payoff and estimation variance of one branch."""

    payoff_cents: Decimal
    estimation_variance: Decimal
    evidence_sample: int | None


def build_known_cards_hand_request(
    hand: Any,
    decisions: Sequence[AofDecision],
    decision_ids: Sequence[int],
) -> KnownCardsHandRequest | None:
    """Snapshot a committed hand without retaining its mutable DB objects."""
    if len(decisions) != len(decision_ids):
        msg = "AoF decision ids do not match the extracted decisions"
        raise ValueError(msg)
    all_ins = [
        (decision, int(decision_id))
        for decision, decision_id in zip(decisions, decision_ids, strict=True)
        if decision.decision == "allin"
    ]
    if not all_ins:
        return None

    category = all_ins[0][0].category
    try:
        pocket_size = _POCKET_SIZE_BY_CATEGORY[category]
    except KeyError:
        return None
    player_ids = getattr(hand, "playerIds", {}) or {}
    names_by_id = {int(player_id): str(name) for name, player_id in player_ids.items()}
    indexed_decisions = tuple(enumerate(decisions))
    decisions_by_player = {int(decision.player_id): (index, decision) for index, decision in indexed_decisions}
    pockets = tuple((name, _known_pocket(hand, name, pocket_size)) for name in sorted(player_ids))
    layers = build_pot_layers(hand)
    flop = _decision_flop(hand)
    big_blind_cents = _money_to_cents((getattr(hand, "gametype", {}) or {}).get("bb", 0))
    requests = []
    for decision, decision_id in all_ins:
        try:
            player = names_by_id[int(decision.player_id)]
        except KeyError:
            msg = f"No hand player matches AoF player id {decision.player_id}"
            raise ValueError(msg) from None
        action_index = decisions_by_player[int(decision.player_id)][0]
        opponents = []
        for opponent_index, opponent_decision in indexed_decisions:
            if opponent_decision.player_id == decision.player_id:
                continue
            opponent_id = int(opponent_decision.player_id)
            try:
                opponent = names_by_id[opponent_id]
            except KeyError:
                msg = f"No hand player matches AoF player id {opponent_id}"
                raise ValueError(msg) from None
            opponents.append(
                RangeOpponent(
                    player=opponent,
                    player_id=opponent_id,
                    role=opponent_decision.role,
                    active_opponents=int(opponent_decision.active_opponents),
                    decision=opponent_decision.decision,
                    blind_committed=int(opponent_decision.blind_committed),
                    amount_to_commit=int(opponent_decision.amount_to_commit),
                    action_index=opponent_index,
                ),
            )
        requests.append(
            KnownDecisionRequest(
                decision_id=decision_id,
                hand_id=int(decision.hand_id),
                player=player,
                player_id=int(decision.player_id),
                category=decision.category,
                role=decision.role,
                active_opponents=int(decision.active_opponents),
                pot_before=int(decision.pot_before),
                amount_to_commit=int(decision.amount_to_commit),
                blind_committed=int(decision.blind_committed),
                big_blind_cents=big_blind_cents,
                action_index=action_index,
                flop=flop,
                pockets=pockets,
                layers=layers,
                opponents=tuple(opponents),
            ),
        )
    return KnownCardsHandRequest(hand_id=int(all_ins[0][0].hand_id), decisions=tuple(requests))


def build_pot_layers(hand: Any) -> tuple[PotLayer, ...]:
    """Rebuild bounded side-pot layers, retaining folded players' dead money.

    ``Hand.pot.pots`` names contributors, including folders. It therefore
    cannot be used directly as the eligibility set for equity. The commitment
    levels are inexpensive to rebuild and ``pot.contenders`` supplies the
    final, fold-aware eligibility.
    """
    pot = getattr(hand, "pot", None)
    if pot is None:
        msg = "The hand has no pot"
        raise ValueError(msg)
    committed = {
        str(player): _money_to_cents(amount)
        for player, amount in (getattr(pot, "committed", {}) or {}).items()
        if _money_to_cents(amount) > 0
    }
    common = {
        str(player): _money_to_cents(amount)
        for player, amount in (getattr(pot, "common", {}) or {}).items()
        if _money_to_cents(amount) > 0
    }
    contenders = _contenders(hand)
    levels = sorted(set(committed.values()))
    previous = 0
    gross_layers: list[tuple[int, set[str]]] = []
    for level in levels:
        contributors = {player for player, amount in committed.items() if amount >= level}
        gross_layers.append(((level - previous) * len(contributors), contributors))
        previous = level

    common_total = sum(common.values()) + _money_to_cents(getattr(pot, "stp", 0))
    if gross_layers:
        gross, contributors = gross_layers[0]
        gross_layers[0] = (gross + common_total, contributors | set(common))
    elif common_total:
        gross_layers.append((common_total, set(common) | contenders))
    if not gross_layers:
        return ()

    expected_total = _money_to_cents(getattr(hand, "totalpot", 0))
    rebuilt_total = sum(gross for gross, _contributors in gross_layers)
    if expected_total and rebuilt_total != expected_total:
        msg = f"Pot commitments rebuild to {rebuilt_total} cents, final pot is {expected_total}"
        raise ValueError(msg)
    total = expected_total or rebuilt_total
    rake = _money_to_cents(getattr(hand, "rake", 0))
    net_amounts = _net_after_proportional_rake([gross for gross, _contributors in gross_layers], rake, total)
    layers = []
    for (gross, contributors), net in zip(gross_layers, net_amounts, strict=True):
        eligible = contributors & contenders
        if not eligible:
            msg = "A pot layer has dead money but no eligible player"
            raise ValueError(msg)
        layers.append(
            PotLayer(
                gross_cents=gross,
                net_cents=net,
                contributors=tuple(sorted(contributors)),
                eligible=tuple(sorted(eligible)),
            ),
        )
    return tuple(layers)


def analyze_known_cards_hand(
    request: KnownCardsHandRequest,
    engine: EquityEngine,
) -> KnownCardsHandResult:
    """Evaluate every exact-card all-in in one hand."""
    return KnownCardsHandResult(
        hand_id=request.hand_id,
        analyses=tuple(analyze_known_decision(decision, engine) for decision in request.decisions),
    )


def analyze_known_decision(
    request: KnownDecisionRequest,
    engine: EquityEngine,
) -> AofDecisionAnalysis:
    """Return exact conditional equity/EV, or a durable incomplete status."""
    base = _analysis_base(request.decision_id)
    if len(request.flop) != 3:
        return replace(base, status="incomplete", error_text="the decision flop is incomplete")
    pocket_map = dict(request.pockets)
    hero_layers = [layer for layer in request.layers if request.player in layer.eligible]
    if not hero_layers:
        return replace(base, status="incomplete", error_text="the player is not eligible for a final pot")
    contested = [layer for layer in hero_layers if len(layer.eligible) > 1]
    if not contested:
        return replace(base, status="no_callers", error_text="no actual caller remained eligible")
    if request.big_blind_cents <= 0:
        return replace(base, status="incomplete", error_text="the big blind is unavailable")

    required = {player for layer in hero_layers for player in layer.eligible}
    missing = sorted(player for player in required if not pocket_map.get(player))
    if missing:
        return replace(
            base,
            status="incomplete",
            error_text=f"eligible pocket cards are hidden: {', '.join(missing)}",
        )

    game = _GAME_BY_CATEGORY[request.category]
    expected_payout = Decimal(0)
    eligible_net_pot = 0
    sample_counts = []
    all_known = {player: cards for player, cards in request.pockets if cards}
    for layer in hero_layers:
        eligible_net_pot += layer.net_cents
        if len(layer.eligible) == 1:
            expected_payout += layer.net_cents
            continue
        opponents = sorted(set(layer.eligible) - {request.player})
        ordered_players = [request.player, *opponents]
        dead = [card for player, cards in all_known.items() if player not in layer.eligible for card in cards]
        result = engine.evaluate_exact(
            game,
            [pocket_map[player] for player in ordered_players],
            request.flop,
            dead=dead,
        )
        expected_payout += result.players[0].equity * layer.net_cents
        sample_counts.append(result.samples)

    equity = expected_payout / Decimal(eligible_net_pot)
    ev_cents = expected_payout - request.amount_to_commit
    return replace(
        base,
        equity_ppm=_scaled_int(equity, _PPM),
        ev_chips=_rounded_int(ev_cents),
        ev_bb_ppm=(_scaled_int(ev_cents / request.big_blind_cents, _PPM) if request.big_blind_cents > 0 else None),
        break_even_ppm=_scaled_int(Decimal(request.amount_to_commit) / eligible_net_pot, _PPM),
        samples=min(sample_counts) if sample_counts else 0,
        stderr_ppm=0,
        status="complete",
    )


def analyze_population_hand(
    request: KnownCardsHandRequest,
    engine: EquityEngine,
    source: Any,
    model: PopulationObservedRange,
) -> KnownCardsHandResult:
    """Evaluate all-in equities against strictly earlier population pockets."""
    get_scope = getattr(source, "getAofDecisionScope", None)
    scope = get_scope(request.decisions[0].decision_id) if callable(get_scope) else None
    if scope is None:
        site_id = source.getAofDecisionSite(request.decisions[0].decision_id)
        scope = (site_id, None) if site_id is not None else None
    if scope is None:
        analyses = tuple(
            _incomplete_population(decision.decision_id, "the decision room is unavailable")
            for decision in request.decisions
        )
        return KnownCardsHandResult(request.hand_id, analyses)
    site_id, before_started_at = scope
    cache: dict[tuple[str, str, int], RangeSnapshot] = {}
    analyses = tuple(
        analyze_population_decision(
            decision,
            engine,
            source,
            model,
            int(site_id),
            before_started_at,
            cache,
        )
        for decision in request.decisions
    )
    return KnownCardsHandResult(request.hand_id, analyses)


def analyze_population_decision(
    request: KnownDecisionRequest,
    engine: EquityEngine,
    source: Any,
    model: PopulationObservedRange,
    site_id: int,
    before_started_at: str | None,
    cache: dict[tuple[str, str, int], RangeSnapshot] | None = None,
) -> AofDecisionAnalysis:
    """Return flop equity against observed historical ranges, never future data."""
    base = _analysis_base(
        request.decision_id,
        range_model=POPULATION_RANGE_MODEL,
        range_version=RANGE_MODEL_VERSION,
        analysis_version=RANGE_ANALYSIS_VERSION,
    )
    if len(request.flop) != 3:
        return replace(base, status="incomplete", error_text="the decision flop is incomplete")
    pocket_map = dict(request.pockets)
    hero = pocket_map.get(request.player, ())
    if not hero:
        return replace(base, status="incomplete", error_text="the player's pocket cards are hidden")
    hero_layers = [layer for layer in request.layers if request.player in layer.eligible]
    if not hero_layers:
        return replace(base, status="incomplete", error_text="the player is not eligible for a final pot")
    if not any(len(layer.eligible) > 1 for layer in hero_layers):
        return replace(base, status="no_callers", error_text="no actual caller remained eligible")

    try:
        opponents = _range_opponents(request, hero_layers)
    except (_RangeIncompleteError, EquityUnavailableError) as exc:
        return replace(base, status="incomplete", error_text=str(exc))

    snapshots = cache if cache is not None else {}
    game = _GAME_BY_CATEGORY[request.category]
    expected_payout = Decimal(0)
    eligible_net_pot = sum(layer.net_cents for layer in hero_layers)
    sample_counts = []
    variance = Decimal(0)
    all_known = {player: cards for player, cards in request.pockets if cards}
    for layer_index, layer in enumerate(hero_layers):
        if len(layer.eligible) == 1:
            expected_payout += layer.net_cents
            continue
        layer_opponents = sorted(set(layer.eligible) - {request.player})
        try:
            range_snapshots = _population_ranges(
                request,
                layer_opponents,
                opponents,
                source,
                model,
                site_id,
                before_started_at,
                snapshots,
            )
        except (_RangeIncompleteError, EquityUnavailableError) as exc:
            return replace(base, status="incomplete", error_text=str(exc))
        dead = [card for player, cards in all_known.items() if player not in layer.eligible for card in cards]
        try:
            result = evaluate_range_snapshots(
                engine,
                game,
                hero,
                range_snapshots,
                request.flop,
                dead=dead,
                iterations=RANGE_ITERATIONS,
                seed=request.decision_id * 1009 + layer_index,
            )
        except EquityUnavailableError as exc:
            return replace(base, status="incomplete", error_text=str(exc))
        layer_equity = result.players[0].equity
        expected_payout += layer_equity * layer.net_cents
        sample_counts.append(result.samples)
        layer_weight = Decimal(layer.net_cents) / eligible_net_pot
        variance += layer_weight**2 * layer_equity * (Decimal(1) - layer_equity) / result.samples

    equity = expected_payout / Decimal(eligible_net_pot)
    return replace(
        base,
        equity_ppm=_scaled_int(equity, _PPM),
        break_even_ppm=_scaled_int(
            Decimal(request.amount_to_commit) / eligible_net_pot,
            _PPM,
        ),
        samples=min(sample_counts) if sample_counts else 0,
        stderr_ppm=_scaled_int(Decimal(str(sqrt(float(variance)))), _PPM),
        status="complete",
    )


def analyze_decision_ev_hand(
    request: KnownCardsHandRequest,
    engine: EquityEngine,
    source: Any,
    range_model: PopulationObservedRange,
    action_model: PopulationActionModel,
) -> KnownCardsHandResult:
    """Evaluate the original all-in decision, including every future answer."""
    get_scope = getattr(source, "getAofDecisionScope", None)
    scope = get_scope(request.decisions[0].decision_id) if callable(get_scope) else None
    if scope is None:
        analyses = tuple(
            _incomplete_decision_ev(decision.decision_id, "the decision room is unavailable")
            for decision in request.decisions
        )
        return KnownCardsHandResult(request.hand_id, analyses)
    site_id, before_started_at = scope
    range_cache: dict[tuple[str, str, int], RangeSnapshot] = {}
    action_cache: dict[tuple[str, str, int], ActionSnapshot] = {}
    analyses = tuple(
        analyze_decision_ev(
            decision,
            engine,
            source,
            range_model,
            action_model,
            int(site_id),
            before_started_at,
            range_cache,
            action_cache,
        )
        for decision in request.decisions
    )
    return KnownCardsHandResult(request.hand_id, analyses)


def analyze_decision_ev(
    request: KnownDecisionRequest,
    engine: EquityEngine,
    source: Any,
    range_model: PopulationObservedRange,
    action_model: PopulationActionModel,
    site_id: int,
    before_started_at: str | None,
    range_cache: dict[tuple[str, str, int], RangeSnapshot] | None = None,
    action_cache: dict[tuple[str, str, int], ActionSnapshot] | None = None,
) -> AofDecisionAnalysis:
    """Return pre-rake decision EV and its conservative 95% classification."""
    base = _analysis_base(
        request.decision_id,
        range_model=DECISION_EV_RANGE_MODEL,
        range_version=DECISION_EV_RANGE_VERSION,
        analysis_version=DECISION_EV_ANALYSIS_VERSION,
    )
    if len(request.flop) != 3:
        return replace(base, status="incomplete", error_text="the decision flop is incomplete")
    if request.big_blind_cents <= 0:
        return replace(base, status="incomplete", error_text="the big blind is unavailable")
    hero = dict(request.pockets).get(request.player, ())
    if not hero:
        return replace(base, status="incomplete", error_text="the player's pocket cards are hidden")

    ranges = range_cache if range_cache is not None else {}
    actions = action_cache if action_cache is not None else {}
    try:
        scenarios = _decision_scenarios(
            request,
            source,
            action_model,
            site_id,
            before_started_at,
            actions,
        )
        values = tuple(
            _scenario_value(
                request,
                scenario,
                engine,
                source,
                range_model,
                site_id,
                before_started_at,
                ranges,
            )
            for scenario in scenarios
        )
    except (_RangeIncompleteError, EquityUnavailableError) as exc:
        return replace(base, status="incomplete", error_text=str(exc))

    ev_cents = sum(
        (scenario.probability * value.payoff_cents for scenario, value in zip(scenarios, values, strict=True)),
        start=Decimal(0),
    )
    estimation_variance = sum(
        (
            scenario.probability**2 * value.estimation_variance
            for scenario, value in zip(scenarios, values, strict=True)
        ),
        start=Decimal(0),
    )
    action_samples = [scenario.action_sample for scenario in scenarios if scenario.action_sample is not None]
    if action_samples:
        mixture_variance = sum(
            (
                scenario.probability * (value.payoff_cents - ev_cents) ** 2
                for scenario, value in zip(scenarios, values, strict=True)
            ),
            start=Decimal(0),
        )
        estimation_variance += mixture_variance / min(action_samples)
    stderr_cents = Decimal(str(sqrt(float(estimation_variance))))
    margin = DECISION_CONFIDENCE_Z * stderr_cents
    if ev_cents + margin < 0:
        status = "weak"
    elif ev_cents - margin > 0:
        status = "strong"
    else:
        status = "uncertain"
    evidence_samples = [
        sample
        for scenario, value in zip(scenarios, values, strict=True)
        for sample in (scenario.action_sample, value.evidence_sample)
        if sample is not None
    ]
    return replace(
        base,
        ev_chips=_rounded_int(ev_cents),
        ev_bb_ppm=_scaled_int(ev_cents / request.big_blind_cents, _PPM),
        samples=min(evidence_samples) if evidence_samples else 0,
        stderr_ppm=_scaled_int(stderr_cents / request.big_blind_cents, _PPM),
        status=status,
    )


def _decision_scenarios(
    request: KnownDecisionRequest,
    source: Any,
    model: PopulationActionModel,
    site_id: int,
    before_started_at: str | None,
    cache: dict[tuple[str, str, int], ActionSnapshot],
) -> tuple[DecisionScenario, ...]:
    prior = sorted(
        (
            opponent
            for opponent in request.opponents
            if opponent.action_index < request.action_index and opponent.decision == "allin"
        ),
        key=lambda opponent: opponent.action_index,
    )
    future = sorted(
        (opponent for opponent in request.opponents if opponent.action_index > request.action_index),
        key=lambda opponent: opponent.action_index,
    )
    if len(prior) + len(future) != request.active_opponents:
        msg = "the acting order is incomplete at the decision point"
        raise _RangeIncompleteError(msg)
    callers = tuple(
        ModeledCaller(
            player=opponent.player,
            role=opponent.role,
            active_opponents=opponent.active_opponents,
            total_commitment=opponent.blind_committed + opponent.amount_to_commit,
        )
        for opponent in prior
    )
    states: list[tuple[Decimal, tuple[ModeledCaller, ...], int, int, int | None]] = [
        (
            Decimal(1),
            callers,
            request.active_opponents + 1,
            len(prior) + 1,
            None,
        ),
    ]
    # The current ``aof_omaha`` category is the equal-stack CoinPoker format.
    # A room with unequal stacks must supply a distinct ruleset/category (Lot
    # 8) rather than silently inheriting this future-caller commitment.
    target_commitment = request.blind_committed + request.amount_to_commit
    for actor in future:
        next_states: list[tuple[Decimal, tuple[ModeledCaller, ...], int, int, int | None]] = []
        for probability, branch_callers, active_players, all_ins, sample in states:
            role = _role_for_all_ins(all_ins)
            active_opponents = active_players - 1
            snapshot = _action_snapshot(
                request,
                role,
                active_opponents,
                source,
                model,
                site_id,
                before_started_at,
                cache,
            )
            assert snapshot.all_in_probability is not None
            all_in_probability = snapshot.all_in_probability
            branch_sample = snapshot.sample_size if sample is None else min(sample, snapshot.sample_size)
            next_states.append(
                (
                    probability * (Decimal(1) - all_in_probability),
                    branch_callers,
                    active_players - 1,
                    all_ins,
                    branch_sample,
                ),
            )
            if actor.blind_committed > target_commitment:
                msg = f"{actor.player}'s forced commitment exceeds the modeled stack"
                raise _RangeIncompleteError(msg)
            next_states.append(
                (
                    probability * all_in_probability,
                    (
                        *branch_callers,
                        ModeledCaller(
                            player=actor.player,
                            role=role,
                            active_opponents=active_opponents,
                            total_commitment=target_commitment,
                        ),
                    ),
                    active_players,
                    all_ins + 1,
                    branch_sample,
                ),
            )
        states = next_states
    return tuple(
        DecisionScenario(probability=probability, callers=branch_callers, action_sample=sample)
        for probability, branch_callers, _active_players, _all_ins, sample in states
    )


def _action_snapshot(
    request: KnownDecisionRequest,
    role: str,
    active_opponents: int,
    source: Any,
    model: PopulationActionModel,
    site_id: int,
    before_started_at: str | None,
    cache: dict[tuple[str, str, int], ActionSnapshot],
) -> ActionSnapshot:
    key = (request.category, role, active_opponents)
    snapshot = cache.get(key)
    if snapshot is None:
        conditions = RangeConditions(
            site_id=site_id,
            category=request.category,
            role=role,
            active_opponents=active_opponents,
            before_hand_id=request.hand_id,
            before_started_at=before_started_at,
            maximum_observations=model.maximum_observations,
        )
        observations = source.getAofActionObservations(
            site_id,
            request.category,
            role,
            active_opponents,
            request.hand_id,
            model.maximum_observations,
        )
        snapshot = model.build(conditions, observations)
        cache[key] = snapshot
    if snapshot.status != "ready":
        msg = f"{role} action model unavailable: {snapshot.reason}"
        raise _RangeIncompleteError(msg)
    return snapshot


def _scenario_value(
    request: KnownDecisionRequest,
    scenario: DecisionScenario,
    engine: EquityEngine,
    source: Any,
    model: PopulationObservedRange,
    site_id: int,
    before_started_at: str | None,
    cache: dict[tuple[str, str, int], RangeSnapshot],
) -> ScenarioValue:
    if not scenario.callers:
        return ScenarioValue(
            payoff_cents=Decimal(request.pot_before),
            estimation_variance=Decimal(0),
            evidence_sample=None,
        )
    layers = _modeled_pot_layers(request, scenario.callers)
    hero = dict(request.pockets)[request.player]
    game = _GAME_BY_CATEGORY[request.category]
    expected_payout = Decimal(0)
    variance = Decimal(0)
    evidence: list[int] = []
    callers = {caller.player: caller for caller in scenario.callers}
    for layer_index, layer in enumerate(layer for layer in layers if request.player in layer.eligible):
        if len(layer.eligible) == 1:
            expected_payout += layer.net_cents
            continue
        layer_callers = [callers[player] for player in layer.eligible if player != request.player]
        snapshots = tuple(
            _population_snapshot(
                request,
                caller.role,
                caller.active_opponents,
                source,
                model,
                site_id,
                before_started_at,
                cache,
            )
            for caller in layer_callers
        )
        result = evaluate_range_snapshots(
            engine,
            game,
            hero,
            snapshots,
            request.flop,
            iterations=RANGE_ITERATIONS,
            seed=request.decision_id * 2017 + layer_index,
        )
        equity = result.players[0].equity
        expected_payout += equity * layer.net_cents
        range_sample = min(snapshot.metadata.sample_size for snapshot in snapshots)
        variance += (
            Decimal(layer.net_cents) ** 2
            * equity
            * (Decimal(1) - equity)
            * (Decimal(1) / result.samples + Decimal(1) / range_sample)
        )
        evidence.extend((result.samples, range_sample))
    return ScenarioValue(
        payoff_cents=expected_payout - request.amount_to_commit,
        estimation_variance=variance,
        evidence_sample=min(evidence) if evidence else None,
    )


def _population_snapshot(
    request: KnownDecisionRequest,
    role: str,
    active_opponents: int,
    source: Any,
    model: PopulationObservedRange,
    site_id: int,
    before_started_at: str | None,
    cache: dict[tuple[str, str, int], RangeSnapshot],
) -> RangeSnapshot:
    key = (request.category, role, active_opponents)
    snapshot = cache.get(key)
    if snapshot is None:
        conditions = RangeConditions(
            site_id=site_id,
            category=request.category,
            role=role,
            active_opponents=active_opponents,
            before_hand_id=request.hand_id,
            before_started_at=before_started_at,
            maximum_observations=model.maximum_observations,
        )
        observations = source.getAofRangeObservations(
            site_id,
            request.category,
            role,
            active_opponents,
            request.hand_id,
            model.maximum_observations,
        )
        snapshot = model.build(conditions, observations)
        cache[key] = snapshot
    if snapshot.status != "ready":
        msg = f"{role} range unavailable: {snapshot.reason}"
        raise _RangeIncompleteError(msg)
    return snapshot


def _modeled_pot_layers(
    request: KnownDecisionRequest,
    callers: Sequence[ModeledCaller],
) -> tuple[PotLayer, ...]:
    contributions = {request.player: request.blind_committed}
    contributions.update({opponent.player: opponent.blind_committed for opponent in request.opponents})
    for opponent in request.opponents:
        if opponent.action_index < request.action_index and opponent.decision == "allin":
            contributions[opponent.player] = opponent.blind_committed + opponent.amount_to_commit
    base_total = sum(contributions.values())
    if base_total > request.pot_before:
        msg = "modeled forced and prior commitments exceed the pot at the decision"
        raise _RangeIncompleteError(msg)
    dead_common = request.pot_before - base_total
    contributions[request.player] = request.blind_committed + request.amount_to_commit
    for caller in callers:
        contributions[caller.player] = caller.total_commitment
    levels = sorted({amount for amount in contributions.values() if amount > 0})
    previous = 0
    eligible_players = {request.player, *(caller.player for caller in callers)}
    layers = []
    pending_dead = dead_common
    for level in levels:
        contributors = {player for player, amount in contributions.items() if amount >= level}
        gross = (level - previous) * len(contributors)
        eligible = contributors & eligible_players
        if eligible:
            gross += pending_dead
            pending_dead = 0
            layers.append(
                PotLayer(
                    gross_cents=gross,
                    net_cents=gross,
                    contributors=tuple(sorted(contributors)),
                    eligible=tuple(sorted(eligible)),
                ),
            )
        else:
            pending_dead += gross
        previous = level
    return tuple(layers)


def _role_for_all_ins(all_ins: int) -> str:
    if all_ins <= 0:
        return "open_shove"
    if all_ins == 1:
        return "call_shove"
    return "overcall"


def _range_opponents(
    request: KnownDecisionRequest,
    hero_layers: Sequence[PotLayer],
) -> dict[str, RangeOpponent]:
    opponents = {opponent.player: opponent for opponent in request.opponents}
    missing = sorted(
        player
        for layer in hero_layers
        for player in layer.eligible
        if player != request.player and (player not in opponents or not opponents[player].role)
    )
    if missing:
        msg = f"opponent action context is unavailable: {', '.join(missing)}"
        raise _RangeIncompleteError(msg)
    return opponents


def _population_ranges(
    request: KnownDecisionRequest,
    players: Sequence[str],
    opponents: dict[str, RangeOpponent],
    source: Any,
    model: PopulationObservedRange,
    site_id: int,
    before_started_at: str | None,
    cache: dict[tuple[str, str, int], RangeSnapshot],
) -> tuple[RangeSnapshot, ...]:
    ranges = []
    for player in players:
        opponent = opponents[player]
        key = (request.category, opponent.role, opponent.active_opponents)
        snapshot = cache.get(key)
        if snapshot is None:
            conditions = RangeConditions(
                site_id=site_id,
                category=request.category,
                role=opponent.role,
                active_opponents=opponent.active_opponents,
                before_hand_id=request.hand_id,
                before_started_at=before_started_at,
                maximum_observations=model.maximum_observations,
            )
            observations: Sequence[RangeObservation] = source.getAofRangeObservations(
                site_id,
                request.category,
                opponent.role,
                opponent.active_opponents,
                request.hand_id,
                model.maximum_observations,
            )
            snapshot = model.build(conditions, observations)
            cache[key] = snapshot
        if snapshot.status != "ready":
            msg = f"{opponent.role} range unavailable: {snapshot.reason}"
            raise _RangeIncompleteError(msg)
        ranges.append(snapshot)
    return tuple(ranges)


class KnownCardsAnalysisCoordinator:
    """Queue all AoF analyses for one hand and persist them on an isolated DB."""

    def __init__(
        self,
        service: AsyncEquityService,
        db_factory: Callable[[], Any],
        *,
        notify_hand: Callable[[int], None] | None = None,
        population_model: PopulationObservedRange | None = None,
        action_model: PopulationActionModel | None = None,
    ) -> None:
        self._service = service
        self._db_factory = db_factory
        self._notify_hand = notify_hand
        self._population_model = population_model
        self._action_model = action_model

    def submit_hand(
        self,
        hand: Any,
        decisions: Sequence[AofDecision],
        decision_ids: Sequence[int],
    ) -> EquitySubmission | None:
        """Snapshot and submit without blocking the import/capture thread."""
        try:
            request = build_known_cards_hand_request(hand, decisions, decision_ids)
        except Exception:
            log.exception("could not prepare known-card equity for hand %s", getattr(hand, "dbid_hands", "?"))
            return None
        if request is None:
            return None
        job = EquityAnalysisJob(
            key=(
                KNOWN_RANGE_MODEL,
                KNOWN_ANALYSIS_VERSION,
                POPULATION_RANGE_MODEL if self._population_model is not None else None,
                self._population_model.version if self._population_model is not None else None,
                POPULATION_ACTION_MODEL if self._action_model is not None else None,
                ACTION_MODEL_VERSION if self._action_model is not None else None,
                request.hand_id,
            ),
            evaluate=lambda engine: self._analyze(request, engine),
            persist=self._persist,
            notify=self._notify,
        )
        submission = self._service.submit(job)
        if submission is EquitySubmission.FULL:
            log.warning("AoF analysis queue is full; hand %s can be backfilled later", request.hand_id)
        return submission

    def close(self, *, timeout: float = 30.0) -> None:
        """Drain and stop the owned worker."""
        self._service.close(wait=True, timeout=timeout)

    def _analyze(
        self,
        request: KnownCardsHandRequest,
        engine: EquityEngine,
    ) -> KnownCardsHandResult:
        known = analyze_known_cards_hand(request, engine)
        if self._population_model is None:
            return known
        try:
            modeled = self._analyze_modeled(request, engine)
        except Exception as exc:
            log.exception("modeled AoF analysis failed for hand %s", request.hand_id)
            population = tuple(
                _incomplete_population(decision.decision_id, f"range analysis failed: {exc}")
                for decision in request.decisions
            )
            decision_ev = (
                tuple(
                    _incomplete_decision_ev(decision.decision_id, f"range analysis failed: {exc}")
                    for decision in request.decisions
                )
                if self._action_model is not None
                else ()
            )
            analyses = (*population, *decision_ev)
            modeled = KnownCardsHandResult(request.hand_id, analyses)
        return KnownCardsHandResult(request.hand_id, (*known.analyses, *modeled.analyses))

    def _analyze_modeled(
        self,
        request: KnownCardsHandRequest,
        engine: EquityEngine,
    ) -> KnownCardsHandResult:
        db = self._db_factory()
        try:
            assert self._population_model is not None
            population = analyze_population_hand(request, engine, db, self._population_model)
            if self._action_model is None:
                return population
            try:
                decision_ev = analyze_decision_ev_hand(
                    request,
                    engine,
                    db,
                    self._population_model,
                    self._action_model,
                )
            except Exception as exc:
                log.exception("decision EV analysis failed for hand %s", request.hand_id)
                analyses = tuple(
                    _incomplete_decision_ev(decision.decision_id, f"decision EV analysis failed: {exc}")
                    for decision in request.decisions
                )
                decision_ev = KnownCardsHandResult(request.hand_id, analyses)
            return KnownCardsHandResult(
                request.hand_id,
                (*population.analyses, *decision_ev.analyses),
            )
        finally:
            rollback = getattr(db, "rollback", None)
            if callable(rollback):
                with suppress(Exception):
                    rollback()
            close = getattr(db, "close_connection", None)
            if callable(close):
                with suppress(Exception):
                    close()

    def _persist(self, result: KnownCardsHandResult) -> None:
        db = self._db_factory()
        try:
            db.storeAofDecisionAnalyses(result.analyses, doinsert=True)
            db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                log.exception("known-card equity rollback also failed for hand %s", result.hand_id)
            raise
        finally:
            close = getattr(db, "close_connection", None)
            if callable(close):
                close()

    def _notify(self, result: KnownCardsHandResult) -> None:
        if self._notify_hand is not None:
            self._notify_hand(result.hand_id)


def _analysis_base(
    decision_id: int,
    *,
    range_model: str = KNOWN_RANGE_MODEL,
    range_version: int = KNOWN_RANGE_VERSION,
    analysis_version: int = KNOWN_ANALYSIS_VERSION,
) -> AofDecisionAnalysis:
    return AofDecisionAnalysis(
        decision_id=decision_id,
        backend=KNOWN_BACKEND,
        backend_version=KNOWN_BACKEND_VERSION,
        range_model=range_model,
        range_version=range_version,
        analysis_version=analysis_version,
        equity_ppm=None,
        ev_chips=None,
        ev_bb_ppm=None,
        break_even_ppm=None,
        samples=None,
        stderr_ppm=None,
        status="incomplete",
        error_text=None,
    )


def _incomplete_population(decision_id: int, error_text: str) -> AofDecisionAnalysis:
    return replace(
        _analysis_base(
            decision_id,
            range_model=POPULATION_RANGE_MODEL,
            range_version=RANGE_MODEL_VERSION,
            analysis_version=RANGE_ANALYSIS_VERSION,
        ),
        status="incomplete",
        error_text=error_text,
    )


def _incomplete_decision_ev(decision_id: int, error_text: str) -> AofDecisionAnalysis:
    return replace(
        _analysis_base(
            decision_id,
            range_model=DECISION_EV_RANGE_MODEL,
            range_version=DECISION_EV_RANGE_VERSION,
            analysis_version=DECISION_EV_ANALYSIS_VERSION,
        ),
        status="incomplete",
        error_text=error_text,
    )


def _known_pocket(hand: Any, player: str, size: int) -> tuple[str, ...]:
    try:
        cards = tuple(
            str(card) for card in hand.join_holecards(player, asList=True) if card and str(card) not in {"0x", "__"}
        )
    except (AttributeError, KeyError, TypeError, ValueError):
        return ()
    return cards[:size] if len(cards) >= size else ()


def _decision_flop(hand: Any) -> tuple[str, ...]:
    board = getattr(hand, "board", {}) or {}
    return tuple(str(card) for card in board.get("FLOP", ()) if card and str(card) != "0x")[:3]


def _contenders(hand: Any) -> set[str]:
    pot = getattr(hand, "pot", None)
    raw = getattr(pot, "contenders", None)
    if isinstance(raw, (set, frozenset, list, tuple)):
        return {str(player) for player in raw}
    players = {
        str(player[1])
        for player in (getattr(hand, "players", ()) or ())
        if isinstance(player, (tuple, list)) and len(player) > 1
    }
    return players - {str(player) for player in (getattr(hand, "folded", ()) or ())}


def _net_after_proportional_rake(gross: Sequence[int], rake: int, total: int) -> tuple[int, ...]:
    if total < 0 or rake < 0 or rake > total or sum(gross) != total:
        msg = "The final pot and rake must be consistent with the pot layers"
        raise ValueError(msg)
    exact = [Decimal(rake) * amount / total for amount in gross]
    rake_shares = [int(value.to_integral_value(rounding=ROUND_FLOOR)) for value in exact]
    remaining = rake - sum(rake_shares)
    order = sorted(
        range(len(gross)),
        key=lambda index: (exact[index] - rake_shares[index], gross[index], -index),
        reverse=True,
    )
    for index in order[:remaining]:
        rake_shares[index] += 1
    return tuple(amount - share for amount, share in zip(gross, rake_shares, strict=True))


def _money_to_cents(value: Any) -> int:
    return _rounded_int(Decimal(str(value or 0)) * _CENTS)


def _scaled_int(value: Decimal, scale: Decimal) -> int:
    return _rounded_int(value * scale)


def _rounded_int(value: Decimal) -> int:
    return int(Decimal(value).to_integral_value(rounding=ROUND_HALF_UP))
