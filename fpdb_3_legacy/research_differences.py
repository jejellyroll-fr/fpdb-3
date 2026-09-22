"""Hero-versus-Field discovery for the spot-first Research Explorer (#365).

This module deliberately stays frequency-first.  It turns the curated,
declarative study panels into a bounded set of reviewable differences; it does
not try to infer leaks, optimal play or EV loss from an observed gap.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Final

from .analytics_query import FILTERS, QueryResult
from .research_matrices import POSITION_LABELS
from .research_studies import CompiledStudyPanel, StudyRegistry, execute_panel
from .research_study_dashboard import StudyDashboardModel
from .research_study_explorer import StudyExplorerModel, StudySelection

DIFFERENCE_PANEL_KINDS: Final[frozenset[str]] = frozenset({"frequency", "response_distribution"})
DEFAULT_MIN_SAMPLE: Final[int] = 20
DEFAULT_MAX_ROWS: Final[int] = 25


@dataclass(frozen=True)
class DifferenceFilters:
    """Inputs that apply to both Hero and Field sides of the comparison."""

    context_filters: Mapping[str, Any] = field(default_factory=dict)
    min_hero_sample: int = DEFAULT_MIN_SAMPLE
    min_field_sample: int = DEFAULT_MIN_SAMPLE
    include_low_sample: bool = False
    category_id: str | None = None
    max_rows: int = DEFAULT_MAX_ROWS

    def __post_init__(self) -> None:
        if self.context_filters is None:
            object.__setattr__(self, "context_filters", {})
        for name in ("min_hero_sample", "min_field_sample", "max_rows"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.max_rows == 0:
            raise ValueError("max_rows must be greater than zero")


@dataclass(frozen=True)
class DifferenceCandidate:
    """One curated study panel that can produce comparable frequencies."""

    study_id: str
    study_title: str
    panel_id: str
    panel_title: str
    panel_kind: str
    metric: str
    group_by: tuple[str, ...]
    recommended_view: str
    category_id: str

    @property
    def id(self) -> str:
        return f"{self.study_id}:{self.panel_id}"

    @property
    def label(self) -> str:
        return f"{self.study_title} · {self.panel_title}"


@dataclass(frozen=True)
class DifferenceRow:
    """One comparable group, with enough information to open it again."""

    candidate_id: str
    study_id: str
    panel_id: str
    spot: str
    context: str
    hero_value_bp: int
    field_value_bp: int
    gap_bp: int
    hero_sample: int
    field_sample: int
    score: int
    unit: str
    context_filters: Mapping[str, Any]
    cross_filters: Mapping[str, Any]
    low_sample: bool = False
    focus_filters: Mapping[str, Any] = field(default_factory=dict)

    @property
    def label(self) -> str:
        return f"{self.spot} · {self.context}" if self.context else self.spot

    @property
    def sample_warning(self) -> str | None:
        if not self.low_sample:
            return None
        return "Small sample: treat this as a review lead, not a conclusion."


@dataclass(frozen=True)
class DifferenceSelection:
    """Deep-link payload from a difference row into the synchronized dashboard."""

    selection: StudySelection
    panel_id: str
    cross_filters: Mapping[str, Any]
    row: DifferenceRow
    focus_filters: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DifferenceReport:
    """A ranked, frequency-only discovery result."""

    rows: tuple[DifferenceRow, ...]
    candidates_evaluated: int
    panels_executed: int
    low_sample_groups: int
    errors: tuple[str, ...] = ()

    @property
    def heuristic_description(self) -> str:
        return "Review priority = absolute Hero–Field gap (basis points) × smaller sample. It is not EV loss or significance."


@dataclass(frozen=True)
class _SeriesPoint:
    value_bp: int
    sample: int


def curated_difference_candidates(
    registry: StudyRegistry,
    *,
    category_id: str | None = None,
) -> tuple[DifferenceCandidate, ...]:
    """Return the finite candidate universe exposed by shipped Study packs.

    A grouped panel is executed once and can yield many rows.  This is the
    important performance boundary: the dashboard never generates arbitrary
    filter permutations or scans once for every displayed row.
    """

    candidates: list[DifferenceCandidate] = []
    explorer = StudyExplorerModel(registry)
    studies = registry.studies
    if category_id is not None:
        studies = explorer.studies_for_category(category_id)
    for study in studies:
        category = _category_id(study.path)
        for panel in study.panels:
            if panel.kind not in DIFFERENCE_PANEL_KINDS:
                continue
            candidates.append(
                DifferenceCandidate(
                    study_id=study.id,
                    study_title=study.title,
                    panel_id=panel.id,
                    panel_title=panel.title,
                    panel_kind=panel.kind,
                    metric=panel.metric,
                    group_by=panel.group_by,
                    recommended_view=panel.recommended_view,
                    category_id=category,
                ),
            )
    return tuple(candidates)


def build_difference_report(
    db: Any,
    registry: StudyRegistry,
    filters: DifferenceFilters | None = None,
) -> DifferenceReport:
    """Execute the curated comparison and rank reviewable frequency gaps."""

    settings = filters or DifferenceFilters()
    candidates = curated_difference_candidates(registry, category_id=settings.category_id)
    explorer = StudyExplorerModel(registry)
    rows: list[DifferenceRow] = []
    errors: list[str] = []
    executed = 0
    low_sample_groups = 0
    context = {key: value for key, value in settings.context_filters.items() if value not in (None, "", "any")}
    context.pop("hero", None)

    for candidate in candidates:
        try:
            selection = explorer.open_study(candidate.study_id, context_filters=context, remember=False)
            if not selection.available:
                continue
            dashboard = StudyDashboardModel(selection, min_sample=0)
            compiled = dashboard.panel(candidate.panel_id)
            hero = _execute_side(db, compiled, True)
            field = _execute_side(db, compiled, False)
            executed += 1
        except Exception as exc:  # noqa: BLE001 - one unavailable spot must not hide all others.
            errors.append(f"{candidate.label}: {exc}")
            continue

        hero_series = _series(hero, candidate)
        field_series = _series(field, candidate)
        for key in sorted(set(hero_series) | set(field_series), key=str):
            hero_point = hero_series.get(key, _SeriesPoint(0, 0))
            field_point = field_series.get(key, _SeriesPoint(0, 0))
            if hero_point.sample <= 0 or field_point.sample <= 0:
                low_sample_groups += 1
                continue
            if hero_point.sample < settings.min_hero_sample or field_point.sample < settings.min_field_sample:
                low_sample_groups += 1
                if not settings.include_low_sample:
                    continue
            gap = hero_point.value_bp - field_point.value_bp
            score = abs(gap) * min(hero_point.sample, field_point.sample)
            group_filters = {
                name: value
                for name, value in zip(candidate.group_by, key)
                if name in FILTERS and value is not None
            }
            # A response distribution's selected response is a chart group,
            # not a new population.  Applying it as a dashboard filter would
            # make the reopened chart's denominator equal the selected bin,
            # so its bar would read 100%. Keep it as a drill-down focus while
            # leaving the panel population intact.
            population_filters = group_filters
            focus_filters: Mapping[str, Any] = {}
            if candidate.panel_kind == "response_distribution":
                population_filters = {}
                focus_filters = group_filters
            rows.append(
                DifferenceRow(
                    candidate_id=candidate.id,
                    study_id=candidate.study_id,
                    panel_id=candidate.panel_id,
                    spot=candidate.study_title,
                    context=_group_label(candidate.group_by, key),
                    hero_value_bp=hero_point.value_bp,
                    field_value_bp=field_point.value_bp,
                    gap_bp=gap,
                    hero_sample=hero_point.sample,
                    field_sample=field_point.sample,
                    score=score,
                    unit="frequency",
                    context_filters=dict(context),
                    cross_filters=population_filters,
                    low_sample=(
                        hero_point.sample < settings.min_hero_sample
                        or field_point.sample < settings.min_field_sample
                    ),
                    focus_filters=focus_filters,
                ),
            )

    rows.sort(key=lambda row: (-row.score, -abs(row.gap_bp), row.label))
    return DifferenceReport(
        rows=tuple(rows[: settings.max_rows]),
        candidates_evaluated=len(candidates),
        panels_executed=executed,
        low_sample_groups=low_sample_groups,
        errors=tuple(errors),
    )


def _execute_side(db: Any, compiled: CompiledStudyPanel, hero: bool) -> QueryResult:
    filters = dict(compiled.query.filters)
    filters["hero"] = hero
    result = execute_panel(
        db,
        replace(compiled, query=replace(compiled.query, filters=filters), base_filters=filters),
    )
    if not isinstance(result, QueryResult):
        raise TypeError("difference candidates must use query-backed frequency panels")
    return result


def _series(result: QueryResult, candidate: DifferenceCandidate) -> dict[tuple[Any, ...], _SeriesPoint]:
    if not result.rows:
        return {}
    if candidate.panel_kind == "response_distribution":
        denominator = result.total_opportunities
        if denominator <= 0:
            return {}
        return {
            tuple(row.group.get(name) for name in candidate.group_by): _SeriesPoint(
                value_bp=row.opportunities * 10000 // denominator,
                sample=denominator,
            )
            for row in result.rows
        }
    return {
        tuple(row.group.get(name) for name in candidate.group_by): _SeriesPoint(
            value_bp=row.frequency_bp or 0,
            sample=row.opportunities,
        )
        for row in result.rows
    }


def _group_label(group_by: tuple[str, ...], key: tuple[Any, ...]) -> str:
    if not group_by:
        return "All matching decisions"
    return " · ".join(
        f"{name.replace('_', ' ').title()}: {_value_label(name, value)}" for name, value in zip(group_by, key)
    )


def _value_label(name: str, value: Any) -> str:
    if name in {"position", "opponent_position"}:
        return POSITION_LABELS.get(value, str(value))
    if name == "in_position" and value in (0, 1, False, True):
        return "IP" if bool(value) else "OOP"
    if value is None:
        return "Unknown"
    return str(value).replace("_", " ").title()


def _category_id(path: tuple[str, ...]) -> str:
    if path and path[0] == "postflop" and len(path) > 1:
        return path[1]
    return path[0] if path else "population"


__all__ = [
    "DEFAULT_MAX_ROWS",
    "DEFAULT_MIN_SAMPLE",
    "DIFFERENCE_PANEL_KINDS",
    "DifferenceCandidate",
    "DifferenceFilters",
    "DifferenceReport",
    "DifferenceRow",
    "DifferenceSelection",
    "build_difference_report",
    "curated_difference_candidates",
]
