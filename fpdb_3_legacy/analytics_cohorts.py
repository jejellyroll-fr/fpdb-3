"""Player populations, cohorts and comparison groups (#307).

Every stat so far has been asked *about a player*. This module asks it about a
**group**: all opponents, the regulars, one room, one stake, a saved set of
tagged players, the last 90 days versus the 90 before it.

A :class:`Cohort` is a reusable, saved filter object -- never a copy of hand
ids. It carries an engine filter dict (#297), an explicit hero-exclusion flag,
an optional relative date window, and presentation metadata, and it composes
with the caller's own filters at query time. Two cohorts can be run against the
*same* metric and filter definition and compared side by side, each with its
own sample size.

Three things this module is careful about:

* **Hero exclusion is explicit.** It is a field on the cohort, visible in
  :meth:`Cohort.resolved_filters`, never an accident of a filter dict that
  happens to mention ``hero``. ``exclude_hero`` compiles to the engine's
  ``hero: False`` filter, which drops the decisions whose *actor* is the hero;
  an opponent's decision in a hand the hero played is still an opponent
  decision and stays.
* **Weighting is named, not implied.** A frequency pooled over decisions is a
  different number from the mean of the players' frequencies -- a regular with
  900 decisions should not outweigh a stranger with 9, unless you say so.
  :func:`population_stat` takes ``weighting`` explicitly, reports which players
  its sample actually used, and the per-player breakdown is always available.
* **A sample size is three numbers.** Decisions, distinct hands and distinct
  players are all reported: "1,200 opportunities" hides whether that is 40
  players or one.

Cohorts are saved as data (``analytics_cohorts.d/*.json``), validated before
anything runs -- an unknown filter name is a ``ValueError`` naming the field
and listing what is allowed, and there is no SQL, ``eval`` or Python in a file.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Final, NoReturn

from .analytics_query import (
    FILTERS,
    Query,
    QueryResult,
    QueryRow,
    run_query,
)

# The cohort file schema this module understands. A file written for a newer
# schema is refused rather than half-read.
COHORT_SCHEMA_VERSION: Final = 1

# How a metric is pooled over a population.
#
# ``decision`` is the engine's native aggregation: every decision in the
# population is one observation, so a player with many hands dominates the
# number -- "what happens in a typical spot between these players".
# ``player`` is the mean of the players' own values, each player one vote --
# "what does a typical player in this population do". Both are legitimate and
# they are genuinely different numbers, which is why the caller must choose.
WEIGHTINGS: Final[tuple[str, ...]] = ("decision", "player")

# Weightings a money metric cannot use: an average of averages of *money*
# answers no question anyone asks, and the issue asks only that the two be
# distinguishable. Refusing is better than quietly returning a number.
_PLAYER_WEIGHTED_UNSUPPORTED: Final[frozenset[str]] = frozenset({"all_in_ev", "total_profit", "hands", "players"})


def _fail(message: str, source: str = "") -> NoReturn:
    raise ValueError(f"{message} [{source}]" if source else message)


# ---------------------------------------------------------------------------
# The cohort object.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Cohort:
    """A saved population: engine filters plus its own explicit semantics."""

    name: str
    filters: Mapping[str, Any] = field(default_factory=dict)
    exclude_hero: bool = False
    # A relative date window in days, resolved against "now" (or an injected
    # reference date) when the cohort is applied. Stored as an offset so a
    # saved cohort does not go stale, which a frozen date range would.
    window_days: int | None = None
    window_offset_days: int = 0
    description: str = ""
    label: Mapping[str, str] | str = ""
    tags: tuple[str, ...] = ()
    source: str = ""

    def __post_init__(self) -> None:
        if not self.name or not isinstance(self.name, str):
            _fail("A cohort needs a name", "cohort")
        if self.window_days is not None and self.window_days <= 0:
            _fail(f"Cohort {self.name!r}: window_days must be positive", self.source)
        if self.window_offset_days < 0:
            _fail(f"Cohort {self.name!r}: window_offset_days must not be negative", self.source)

    def resolved_filters(self, reference: datetime | None = None) -> dict[str, Any]:
        """The engine filter dict this cohort contributes, hero exclusion included.

        Explicit and testable: :meth:`as_dict` shows the same dict, and
        ``hero: False`` appears only because ``exclude_hero`` is set.
        """
        filters = dict(self.filters)
        if self.window_days is not None:
            anchor = reference or datetime.now()
            end = anchor - timedelta(days=self.window_offset_days)
            start = end - timedelta(days=self.window_days)
            # A window narrows the hand date range; an explicit date in the
            # cohort itself is a hard error rather than one silently winning.
            if "date_from" in filters or "date_to" in filters:
                _fail(f"Cohort {self.name!r} has both a window and explicit dates", self.source)
            filters["date_from"] = start
            filters["date_to"] = end
        if self.exclude_hero:
            if filters.get("hero") is True:
                _fail(f"Cohort {self.name!r} excludes the hero and requires it", self.source)
            filters["hero"] = False
        return filters

    def apply(self, filters: Mapping[str, Any] | None = None, reference: datetime | None = None) -> AppliedCohort:
        """Combine this cohort with other analytics filters.

        The caller's filters win on a collision so a cohort never silently
        overrides an explicit request; the overridden names are returned
        rather than dropped in silence.
        """
        base = self.resolved_filters(reference)
        supplied = {name: value for name, value in (filters or {}).items() if value is not None}
        overridden = tuple(sorted(name for name in base if name in supplied))
        merged = {**base, **supplied}
        for name in merged:
            if name not in FILTERS:
                _fail(f"Cohort {self.name!r}: unknown filter {name!r}", self.source)
        return AppliedCohort(cohort=self, filters=merged, overridden=overridden)

    def combine(self, *others: Cohort, name: str | None = None) -> Cohort:
        """The intersection of several cohorts, as one cohort.

        Two cohort definitions meeting on the same filter is an error, not a
        coin toss: "NL50" and "NL200" composed by accident must not quietly
        produce one of them.
        """
        merged: dict[str, Any] = dict(self.filters)
        exclude_hero = self.exclude_hero
        for other in others:
            for key, value in other.filters.items():
                if key in merged and merged[key] != value:
                    _fail(
                        f"Cohorts {self.name!r} and {other.name!r} disagree on {key!r}: "
                        f"{merged[key]!r} vs {value!r}",
                    )
                merged[key] = value
            exclude_hero = exclude_hero or other.exclude_hero
        window_days = self.window_days
        window_offset = self.window_offset_days
        for other in others:
            if other.window_days is not None:
                if window_days is not None and other.window_days != window_days:
                    _fail(f"Cohorts {self.name!r} and {other.name!r} disagree on window_days")
                window_days = other.window_days
                window_offset = other.window_offset_days
        combined_last = others[-1] if others else self
        return Cohort(
            name=name or "+".join([self.name, *(other.name for other in others)]),
            filters=merged,
            exclude_hero=exclude_hero,
            window_days=window_days,
            window_offset_days=window_offset,
            description=f"Combination of {', '.join([self.name, *(o.name for o in others)])}",
            label=combined_last.label or self.label,
            tags=tuple(dict.fromkeys([*self.tags, *(tag for other in others for tag in other.tags)])),
            source="combined",
        )

    def as_dict(self) -> dict[str, Any]:
        """The cohort as data, for saving and for inspection in a UI."""
        out: dict[str, Any] = {
            "name": self.name,
            "filters": dict(self.filters),
            "exclude_hero": self.exclude_hero,
        }
        if self.window_days is not None:
            out["window_days"] = self.window_days
            out["window_offset_days"] = self.window_offset_days
        if self.description:
            out["description"] = self.description
        if self.label:
            out["label"] = dict(self.label) if isinstance(self.label, Mapping) else self.label
        if self.tags:
            out["tags"] = list(self.tags)
        if self.source:
            out["source"] = self.source
        return out


@dataclass(frozen=True)
class AppliedCohort:
    """A cohort's filters merged with a caller's; ``overridden`` is named."""

    cohort: Cohort
    filters: dict[str, Any]
    overridden: tuple[str, ...]

    def query(self, **kwargs: Any) -> Query:
        """The caller's query with the cohort's filters merged in."""
        return Query(filters=self.filters, **kwargs)


# ---------------------------------------------------------------------------
# Population sources.
#
# Thin, named constructors over the engine's filters, so a population reads as
# the sentence it is. Each one returns a Cohort and can be the base of a
# ``combine``.
# ---------------------------------------------------------------------------


def all_opponents(name: str = "all_opponents") -> Cohort:
    """Every decision in the database, the hero's own excluded."""
    return Cohort(
        name=name,
        exclude_hero=True,
        description="Every player's decisions, with the hero's own rows excluded.",
        label={"en": "All opponents", "fr": "Tous les adversaires"},
        source="builtin",
    )


def players(names: Sequence[str], name: str = "selected_players") -> Cohort:
    """A manually selected set of players."""
    chosen = [str(entry) for entry in names if entry]
    if not chosen:
        _fail("A player cohort needs at least one name")
    return Cohort(
        name=name,
        filters={"player": chosen},
        exclude_hero=True,
        description=f"Decisions by the selected players: {', '.join(chosen)}.",
        source="builtin",
    )


def linked_identities(config: Any, profile: str | None = None, name: str = "") -> Cohort:
    """A hero identity spanning rooms, as ``(site, alias)`` pairs (#307).

    Reads the ``<hero_profile>`` links from the configuration. The filter is an
    explicit list of pairs, so the same screen name on two rooms stays two
    different people.
    """
    hero_profile = _hero_profile(config, profile)
    links: list[tuple[str, str]] = list(getattr(hero_profile, "links", ()))
    if not links:
        _fail("The hero profile has no <link> entries to build a cohort from")
    return Cohort(
        name=name or f"identities_{getattr(hero_profile, 'name', 'hero')}",
        filters={"identity": links},
        exclude_hero=False,
        description="A linked hero identity across rooms: "
        + ", ".join(f"{site}:{alias}" for site, alias in links),
        label={"en": f"Identity {getattr(hero_profile, 'name', 'hero')}"},
        source="linked",
    )


def _hero_profile(config: Any, profile: str | None) -> Any:
    """The named or default :class:`HeroProfile`, or a clear error."""
    try:
        profiles = config.get_hero_profiles()
    except AttributeError:
        _fail("This configuration exposes no hero profiles")
    if profile is not None:
        if profile not in profiles:
            _fail(f"Unknown hero profile {profile!r}; known: {sorted(profiles)}")
        return profiles[profile]
    chosen = config.get_default_hero_profile() if hasattr(config, "get_default_hero_profile") else None
    if chosen is None:
        _fail("No hero profile is configured")
    return chosen


def sites(names: Sequence[str], name: str = "sites") -> Cohort:
    """One or more rooms."""
    chosen = [str(entry) for entry in names if entry]
    if not chosen:
        _fail("A site cohort needs at least one site")
    return Cohort(
        name=name,
        filters={"site": chosen},
        description=f"Decisions on {', '.join(chosen)}.",
        source="builtin",
    )


def stakes(big_blind_cents: int | Sequence[int], name: str = "stakes") -> Cohort:
    """A stake, or an inclusive range of them, by big blind in **cents**.

    The unit is the engine's (``Gametypes.bigBlind`` is cents, like every other
    money column): ``stakes(50)`` is NL50, ``stakes((50, 200))`` is NL50 through
    NL200. Named for its unit so a caller cannot pass dollars by accident.
    """
    if isinstance(big_blind_cents, int):
        filters: dict[str, Any] = {"big_blind": big_blind_cents}
    else:
        values = [int(entry) for entry in big_blind_cents]
        if len(values) != 2:
            _fail("A stake range needs exactly two big blinds")
        filters = {"big_blind": (min(values), max(values))}
    return Cohort(
        name=name,
        filters=filters,
        description=f"Decisions at big blind {filters['big_blind']} cents.",
        source="builtin",
    )


def table_size(seats: int | Sequence[int], name: str = "table_size") -> Cohort:
    """A table size, or an inclusive range of them, by seat count."""
    value: Any = int(seats) if isinstance(seats, int) else (min(seats), max(seats))
    return Cohort(
        name=name,
        filters={"seats": value},
        description=f"Decisions at tables of {value} seats.",
        source="builtin",
    )


def date_window(days: int, offset_days: int = 0, name: str = "") -> Cohort:
    """A relative window: the last ``days``, or the ``days`` before the last ``offset_days``."""
    label = f"last_{days}_days" if not offset_days else f"days_{offset_days}_to_{offset_days + days}_ago"
    return Cohort(
        name=name or label,
        window_days=days,
        window_offset_days=offset_days,
        description=f"Decisions in the {days} days ending {offset_days} days ago.",
        source="builtin",
    )


def regular_tables_only(name: str = "regular_tables_only") -> Cohort:
    """Cash tables: tournaments excluded, which the engine expresses as ``tournament: False``."""
    return Cohort(
        name=name,
        filters={"tournament": False},
        description="Cash-game decisions only; tournaments are excluded.",
        source="builtin",
    )


# ---------------------------------------------------------------------------
# Sample sizes and population statistics.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PopulationSample:
    """What a population's number was computed over, in three counts."""

    decisions: int
    hands: int
    players: int

    def as_dict(self) -> dict[str, int]:
        return {"decisions": self.decisions, "hands": self.hands, "players": self.players}


@dataclass(frozen=True)
class PopulationStat:
    """One metric over one cohort, with its sample and its per-player breakdown."""

    cohort: str
    metric: str
    weighting: str
    unit: str
    value: float | None
    frequency_bp: int | None
    sample: PopulationSample
    players_used: int
    players_skipped: int
    min_player_sample: int
    per_player: tuple[QueryRow, ...] = ()

    @property
    def value_label(self) -> str:
        """The metric rendered for a label: a rate as a percentage, else the value."""
        if self.frequency_bp is not None:
            return f"{self.frequency_bp / 100:.2f}%"
        return "-" if self.value is None else f"{self.value:g} {self.unit}".strip()

    def as_dict(self) -> dict[str, Any]:
        return {
            "cohort": self.cohort,
            "metric": self.metric,
            "weighting": self.weighting,
            "unit": self.unit,
            "value": self.value,
            "frequency_bp": self.frequency_bp,
            "value_label": self.value_label,
            "sample": self.sample.as_dict(),
            "players_used": self.players_used,
            "players_skipped": self.players_skipped,
            "min_player_sample": self.min_player_sample,
            "per_player": [row.as_dict() for row in self.per_player],
        }


def population_sample(db: Any, applied: AppliedCohort, with_details: bool = True) -> PopulationSample:
    """Decisions, distinct hands and distinct players behind a cohort.

    The decision count is one query -- the engine's own denominator. The other
    two are distinct counts, which no single statement returns alongside it, so
    they cost two more small index-backed scans; ``with_details=False`` skips
    them for a caller that already knows it only needs a decision count.
    """
    decisions = run_query(db, applied.query(metric="opportunities")).total_opportunities
    if not with_details:
        return PopulationSample(decisions=decisions, hands=0, players=0)
    hands = run_query(db, applied.query(metric="hands")).rows
    players = run_query(db, applied.query(metric="players")).rows
    return PopulationSample(
        decisions=decisions,
        hands=int(hands[0].value or 0) if hands else 0,
        players=int(players[0].value or 0) if players else 0,
    )


def _pooled_value(result: QueryResult) -> tuple[float | None, int | None]:
    """The decision-weighted value, pooled numerators-over-denominators.

    Pooling grouped rows is not averaging their rates: with a breakdown by
    position the population's fold frequency is the total number of folds over
    the total number of decisions, so a group of nine decisions cannot swing
    the answer the way an unweighted mean would let it.
    """
    if not result.rows:
        return None, None
    if len(result.rows) == 1:
        row = result.rows[0]
        if row.opportunities == 0:
            # An aggregate over an empty population still returns one row; it
            # is not a number, and must not read as a rate of zero.
            return None, None
        return (row.frequency_bp if row.frequency_bp is not None else row.value), row.frequency_bp
    opportunities = result.total_opportunities
    if opportunities == 0:
        return None, None
    if all(row.frequency_bp is not None for row in result.rows):
        bp = result.total_actions * 10000 // opportunities
        return bp, bp
    weighted = sum((row.value or 0) * row.opportunities for row in result.rows)
    return weighted / opportunities, None


def population_stat(
    db: Any,
    query: Query,
    cohort: Cohort,
    weighting: str = "decision",
    min_player_sample: int = 0,
    reference: datetime | None = None,
    with_sample: bool = True,
) -> PopulationStat:
    """One metric over one cohort, pooled by an explicit weighting.

    ``decision`` runs the engine's native aggregation. ``player`` runs the same
    metric per player and averages the players, optionally dropping players
    below ``min_player_sample`` decisions -- the sample a rate needs before it
    is a rate. Which players were used and which were skipped is reported, so
    a mean over four regulars cannot pass for a population.
    """
    if weighting not in WEIGHTINGS:
        raise ValueError(f"Unknown weighting {weighting!r}; known: {list(WEIGHTINGS)}")
    if min_player_sample < 0:
        raise ValueError("min_player_sample must not be negative")
    applied = cohort.apply(query.filters, reference)
    metric = query.metric
    # The unit comes from the metric's own definition, so an empty population
    # still reports the unit its number would have had.
    unit = query.resolved()[0].unit

    if weighting == "player":
        if metric in _PLAYER_WEIGHTED_UNSUPPORTED:
            raise ValueError(
                f"Metric {metric!r} cannot be pooled per player; use weighting='decision' "
                f"or a frequency/rate metric",
            )
        per_player_query = applied.query(
            metric=metric,
            numerator=dict(query.numerator),
            group_by=("player",),
        )
        per_player = run_query(db, per_player_query).rows
        used = [row for row in per_player if row.opportunities >= min_player_sample]
        skipped = len(per_player) - len(used)
        values = [row.frequency_bp for row in used if row.frequency_bp is not None]
        frequency_bp: int | None
        value: float | None
        if values and len(values) == len(used):
            frequency_bp = round(sum(values) / len(values))
            value = float(frequency_bp)
        else:
            rates = [row.value for row in used if row.value is not None]
            value = round(sum(rates) / len(rates), 4) if rates else None
            frequency_bp = None
        # Grouping by player already tells us how many players there are and
        # how many decisions they made; only the distinct-hand count costs one
        # more query.
        decisions = sum(row.opportunities for row in per_player)
        sample = PopulationSample(
            decisions=decisions,
            hands=int(run_query(db, applied.query(metric="hands")).rows[0].value or 0) if with_sample else 0,
            players=len(per_player),
        )
        return PopulationStat(
            cohort=cohort.name,
            metric=metric,
            weighting=weighting,
            unit=unit,
            value=value,
            frequency_bp=frequency_bp,
            sample=sample,
            players_used=len(used),
            players_skipped=skipped,
            min_player_sample=min_player_sample,
            per_player=tuple(per_player),
        )

    # One number per cohort: the caller's ``group_by`` is deliberately not
    # applied here -- a breakdown of a population is a ``run_query`` over the
    # cohort's filters, which :meth:`Cohort.apply` hands over directly.
    result = run_query(db, applied.query(metric=metric, numerator=dict(query.numerator)))
    value, frequency_bp = _pooled_value(result)
    return PopulationStat(
        cohort=cohort.name,
        metric=metric,
        weighting=weighting,
        unit=unit,
        value=value,
        frequency_bp=frequency_bp,
        sample=population_sample(db, applied) if with_sample else PopulationSample(result.total_opportunities, 0, 0),
        players_used=0,
        players_skipped=0,
        min_player_sample=min_player_sample,
        per_player=(),
    )


# ---------------------------------------------------------------------------
# Comparison groups.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CohortComparison:
    """Two cohorts measured with the same metric and filter definition."""

    metric: str
    weighting: str
    filters: Mapping[str, Any]
    a: PopulationStat
    b: PopulationStat

    @property
    def frequency_delta_bp(self) -> int | None:
        """The rate difference in basis points, when both sides are rates."""
        if self.a.frequency_bp is None or self.b.frequency_bp is None:
            return None
        return self.b.frequency_bp - self.a.frequency_bp

    @property
    def value_delta(self) -> float | None:
        """The value difference (B minus A); ``None`` unless both sides have one."""
        if self.a.value is None or self.b.value is None:
            return None
        return round(self.b.value - self.a.value, 4)

    def as_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "weighting": self.weighting,
            "filters": dict(self.filters),
            "a": self.a.as_dict(),
            "b": self.b.as_dict(),
            "frequency_delta_bp": self.frequency_delta_bp,
            "value_delta": self.value_delta,
        }


def compare_cohorts(
    db: Any,
    query: Query,
    cohort_a: Cohort,
    cohort_b: Cohort,
    weighting: str = "decision",
    min_player_sample: int = 0,
    reference: datetime | None = None,
) -> CohortComparison:
    """Measure two populations with one metric, filter set and weighting.

    The same ``query`` is used for both sides by construction, so a difference
    between the two numbers can only come from the cohorts.
    """
    a = population_stat(
        db, query, cohort_a, weighting=weighting, min_player_sample=min_player_sample, reference=reference,
    )
    b = population_stat(
        db, query, cohort_b, weighting=weighting, min_player_sample=min_player_sample, reference=reference,
    )
    return CohortComparison(
        metric=query.metric,
        weighting=weighting,
        filters=dict(query.filters),
        a=a,
        b=b,
    )


def format_comparison(comparison: CohortComparison) -> str:
    """A readable side-by-side block, sample sizes included."""
    lines = [
        f"metric: {comparison.metric} (weighting: {comparison.weighting})",
    ]
    if comparison.filters:
        rendered = ", ".join(f"{name}={value!r}" for name, value in sorted(comparison.filters.items()))
        lines.append(f"filters: {rendered}")
    for stat in (comparison.a, comparison.b):
        sample = stat.sample
        lines.append(
            f"  {stat.cohort}: {stat.value_label} "
            f"[{sample.decisions} decisions, {sample.hands} hands, {sample.players} players]",
        )
    if comparison.frequency_delta_bp is not None:
        lines.append(f"  delta (b - a): {comparison.frequency_delta_bp / 100:+.2f} pp")
    elif comparison.value_delta is not None:
        lines.append(f"  delta (b - a): {comparison.value_delta:+g}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Loading, validating and saving cohort files.
# ---------------------------------------------------------------------------


def _cohort_name(data: Mapping[str, Any], source: str) -> str:
    name = data.get("name")
    if not isinstance(name, str) or not name:
        _fail("A cohort needs a name", source)
    return name


def _cohort_filters(data: Mapping[str, Any], name: str, source: str) -> dict[str, Any]:
    """The filter dict, with every name checked against the engine's registry."""
    raw = data.get("filters", {})
    if not isinstance(raw, Mapping):
        _fail(f"Cohort {name!r}: filters must be an object", source)
    for key in raw:
        if key not in FILTERS:
            _fail(f"Cohort {name!r}: unknown filter {key!r}; known: {sorted(FILTERS)}", source)
    return dict(raw)


def _cohort_window(data: Mapping[str, Any], name: str, source: str) -> tuple[int | None, int]:
    """The relative window a cohort may carry, as (days, offset)."""
    window_days = data.get("window_days")
    if window_days is not None and (not isinstance(window_days, int) or isinstance(window_days, bool)):
        _fail(f"Cohort {name!r}: window_days must be an integer", source)
    offset = data.get("window_offset_days", 0)
    if not isinstance(offset, int) or isinstance(offset, bool):
        _fail(f"Cohort {name!r}: window_offset_days must be an integer", source)
    return window_days, offset


def _validate_cohort(data: Mapping[str, Any], source: str = "") -> Cohort:
    """One cohort document to a :class:`Cohort`, refusing anything unknown."""
    if not isinstance(data, Mapping):
        _fail(f"A cohort must be an object, got {type(data).__name__}", source)
    name = _cohort_name(data, source)
    filters = _cohort_filters(data, name, source)
    exclude_hero = data.get("exclude_hero", False)
    if not isinstance(exclude_hero, bool):
        _fail(f"Cohort {name!r}: exclude_hero must be a boolean", source)
    window_days, offset = _cohort_window(data, name, source)
    tags = data.get("tags", ())
    if not isinstance(tags, (list, tuple)) or not all(isinstance(tag, str) for tag in tags):
        _fail(f"Cohort {name!r}: tags must be a list of strings", source)
    label = data.get("label", "")
    if not isinstance(label, (str, Mapping)):
        _fail(f"Cohort {name!r}: label must be text or a locale mapping", source)
    cohort = Cohort(
        name=name,
        filters=filters,
        exclude_hero=exclude_hero,
        window_days=window_days,
        window_offset_days=offset,
        description=str(data.get("description", "")),
        label=label,
        tags=tuple(tags),
        source=str(data.get("source", source)),
    )
    # Validate the resolved dict too: an explicit ``hero: True`` next to
    # ``exclude_hero`` is a contradiction, and it must fail at load time.
    cohort.resolved_filters()
    return cohort


def _documents(document: Any, path: Path) -> list[Mapping[str, Any]]:
    """The cohort documents in one file: a single object or a ``cohorts`` list."""
    if isinstance(document, Mapping) and "cohorts" in document:
        raw = document["cohorts"]
        if not isinstance(raw, list):
            _fail(f"{path}: 'cohorts' must be a list", str(path))
        return list(raw)
    if isinstance(document, list):
        return list(document)
    if isinstance(document, Mapping):
        return [document]
    _fail(f"{path}: expected an object or a list of cohorts", str(path))


def _check_version(document: Any, path: Path) -> None:
    if not isinstance(document, Mapping):
        return
    version = document.get("schema_version", COHORT_SCHEMA_VERSION)
    if not isinstance(version, int) or isinstance(version, bool):
        _fail(f"{path}: schema_version must be an integer", str(path))
    if version > COHORT_SCHEMA_VERSION:
        _fail(
            f"{path}: cohort schema {version} is newer than {COHORT_SCHEMA_VERSION}; "
            "upgrade fpdb-3 rather than reading it half-way",
            str(path),
        )


def _load_text(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_cohorts(path: str | Path) -> list[Cohort]:
    """Every cohort in one ``.json`` file, validated."""
    source = Path(path)
    document = _load_text(source)
    _check_version(document, source)
    return [_validate_cohort(entry, str(source)) for entry in _documents(document, source)]


def load_directory(directory: str | Path) -> list[Cohort]:
    """Every cohort in every ``.json`` file of a directory, name-sorted."""
    root = Path(directory)
    if not root.is_dir():
        return []
    cohorts: list[Cohort] = []
    for path in sorted(root.glob("*.json")):
        cohorts.extend(load_cohorts(path))
    return cohorts


@dataclass
class CohortRegistry:
    """Cohorts by name, from the built-in directory plus any extra ones."""

    cohorts: dict[str, Cohort] = field(default_factory=dict)
    sources: dict[str, str] = field(default_factory=dict)

    def add(self, cohort: Cohort, source: str = "") -> None:
        self.cohorts[cohort.name] = cohort
        if source:
            self.sources[cohort.name] = source

    def names(self) -> list[str]:
        return sorted(self.cohorts)

    def get(self, name: str) -> Cohort:
        if name not in self.cohorts:
            _fail(f"Unknown cohort {name!r}; known: {self.names()}")
        return self.cohorts[name]

    def save(self, cohort: Cohort, path: str | Path) -> Path:
        """Write one cohort to a file as a single validated document.

        The cohort is validated first, so a file this module writes is a file
        it can read back -- ``CohortRegistry.save`` then ``load_cohorts`` is a
        round trip, and an edited file is refused with the field named.
        """
        validated = _validate_cohort(cohort.as_dict(), str(path))
        target = Path(path)
        document = {"schema_version": COHORT_SCHEMA_VERSION, "cohorts": [validated.as_dict()]}
        target.write_text(json.dumps(document, indent=2, sort_keys=False, default=str) + "\n", encoding="utf-8")
        return target


def default_cohorts_dir() -> Path:
    """The packaged cohort library."""
    return Path(__file__).resolve().parent / "analytics_cohorts.d"


def load_default_registry(extra_dirs: Iterable[str | Path] = ()) -> CohortRegistry:
    """The built-in cohorts plus every ``.json`` in ``extra_dirs``."""
    registry = CohortRegistry()
    for cohort in load_directory(default_cohorts_dir()):
        registry.add(cohort, "builtin")
    for directory in extra_dirs:
        for cohort in load_directory(directory):
            registry.add(cohort, str(directory))
    return registry


_registry: CohortRegistry | None = None


def get_registry() -> CohortRegistry:
    """The process-wide registry, built once from the packaged cohorts."""
    global _registry
    if _registry is None:
        _registry = load_default_registry()
    return _registry


def format_cohort(cohort: Cohort, reference: datetime | None = None) -> str:
    """A readable rendering of a cohort and the filters it resolves to."""
    lines = [f"{cohort.name}: {cohort.description or '(no description)'}"]
    if cohort.label:
        label = cohort.label.get("en") if isinstance(cohort.label, Mapping) else cohort.label
        if label:
            lines.append(f"  label: {label}")
    filters = cohort.resolved_filters(reference)
    rendered = ", ".join(f"{name}={value!r}" for name, value in sorted(filters.items()))
    lines.append(f"  filters: {rendered or '(none)'}")
    lines.append(f"  excludes hero: {'yes' if cohort.exclude_hero else 'no'}")
    if cohort.tags:
        lines.append(f"  tags: {', '.join(cohort.tags)}")
    return "\n".join(lines)


def comparison_group(cohort: Cohort, other: Cohort) -> tuple[Cohort, Cohort]:
    """Two cohorts as a comparison pair, with an explicit hero-exclusion check.

    A comparison is only meaningful when both sides agree on whether the hero
    is in the population; a pair that does not is refused rather than silently
    comparing "all opponents" against "everyone including hero".
    """
    if cohort.exclude_hero != other.exclude_hero:
        _fail(
            f"Comparison groups must agree on hero exclusion: {cohort.name!r} "
            f"({'excludes' if cohort.exclude_hero else 'includes'}) vs {other.name!r} "
            f"({'excludes' if other.exclude_hero else 'includes'})",
        )
    return cohort, other


__all__ = [
    "COHORT_SCHEMA_VERSION",
    "WEIGHTINGS",
    "AppliedCohort",
    "Cohort",
    "CohortComparison",
    "CohortRegistry",
    "PopulationSample",
    "PopulationStat",
    "all_opponents",
    "compare_cohorts",
    "comparison_group",
    "date_window",
    "default_cohorts_dir",
    "format_cohort",
    "format_comparison",
    "get_registry",
    "linked_identities",
    "load_cohorts",
    "load_default_registry",
    "load_directory",
    "players",
    "population_sample",
    "population_stat",
    "regular_tables_only",
    "sites",
    "stakes",
    "table_size",
]
