"""Declarative poker studies built on top of the Research query engine.

The Research Browser answers one query at a time.  A study names the poker
spot once and coordinates several readings of that same population: a
frequency, a breakdown, a range, a composition, money and the source hands.
This module is deliberately Qt-free.  It validates plain mappings before a
future Study Explorer loads them, then compiles panels into the existing query,
range, composition, profitability and hand-drill APIs.

Study definitions contain vocabulary, never SQL or Python expressions.  The
query engine remains the authority for metrics, filters, dimensions and their
semantics; this module only composes those existing pieces.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Final

from . import research_browser as rb
from .analytics_profit import profit_report
from .analytics_query import (
    DIMENSIONS,
    FILTERS,
    KNOWN_METRICS,
    Query,
    compile_query,
    run_query,
)
from .hand_state_composition import DIMENSIONS as COMPOSITION_DIMENSIONS
from .hand_state_composition import compose
from .holdem_ranges import build_range
from .player_situations import SITUATION_RULES

PANEL_KINDS: Final[tuple[str, ...]] = (
    "headline",
    "frequency",
    "response_distribution",
    "sizing_distribution",
    "position_matrix",
    "board_matrix",
    "range_grid",
    "hand_strength",
    "profit",
    "hands",
)

_QUERY_KINDS: Final[frozenset[str]] = frozenset(PANEL_KINDS[:6])
_PROFIT_METRICS: Final[frozenset[str]] = frozenset(
    {"total_profit", "profit_per_opportunity", "all_in_ev", "ev_per_opportunity"},
)


class StudyValidationError(ValueError):
    """A study definition is invalid before it reaches a UI or database."""


class StudyUnavailable(ValueError):
    """A valid panel cannot answer for the study's declared game."""


def _as_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    """Canonicalise a string-or-sequence field and reject empty names."""
    if isinstance(value, str):
        values = (value,)
    elif isinstance(value, Sequence):
        values = tuple(value)
    else:
        raise StudyValidationError(f"{field_name} must be a string or sequence")
    if any(not isinstance(item, str) or not item.strip() for item in values):
        raise StudyValidationError(f"{field_name} must contain non-empty strings")
    return tuple(item.strip() for item in values)


def _tokens(value: Any) -> set[str]:
    """Read a scalar or set-like filter as comparable response tokens."""
    if isinstance(value, str):
        return {value}
    if isinstance(value, Sequence):
        return {str(item) for item in value}
    return {str(value)}


def _outcome_responses(situation: str) -> set[str]:
    """Return the responses already encoded by a named situation rule."""
    return {
        response
        for rule in SITUATION_RULES
        if rule.name == situation and rule.response
        for response in rule.response
    }


def _validate_opportunity_metric(query: Query) -> None:
    """Reject a frequency whose population already is its numerator.

    A study panel should measure an opportunity (for example ``cbet_spot``),
    then count the outcome (``response=bet``).  Measuring ``bet_frequency``
    over ``cbet`` would be structurally self-selecting and always read 100%.
    The same rule applies to an explicit response filter.
    """
    metric_spec, filters, numerator = query.resolved()
    if not metric_spec.frequency:
        return

    responses = _tokens(numerator.get("response")) if "response" in numerator else set()
    if query.metric == "frequency" and not responses:
        raise StudyValidationError(
            "frequency panels must declare a response numerator or use a named frequency metric",
        )

    for name in ("response", "action_taken"):
        selected = _tokens(filters[name]) if name in filters else set()
        if selected and responses and selected <= responses:
            raise StudyValidationError(
                f"{query.metric} measures response {sorted(responses)!r} over a population "
                f"already restricted to {name}={filters[name]!r}; use the opportunity spot instead",
            )

    situations = _tokens(filters["primary_situation"]) if "primary_situation" in filters else set()
    for situation in situations:
        encoded = _outcome_responses(situation)
        if encoded and responses and encoded <= responses:
            raise StudyValidationError(
                f"{query.metric} measures {sorted(responses)!r} over the outcome situation "
                f"{situation!r}; use its opportunity variant instead",
            )


def _merge_filters(base: Mapping[str, Any], extra: Mapping[str, Any]) -> dict[str, Any]:
    """Add panel narrowing without silently changing the study population."""
    merged = dict(base)
    for name, value in extra.items():
        if name in merged and merged[name] != value:
            raise StudyValidationError(
                f"panel filter {name!r}={value!r} conflicts with the study population "
                f"{name!r}={merged[name]!r}",
            )
        merged[name] = value
    return merged


@dataclass(frozen=True)
class StudyPanelSpec:
    """One declarative reading of a study's canonical population."""

    id: str
    title: str
    kind: str
    metric: str = "opportunities"
    group_by: tuple[str, ...] = ()
    filters: Mapping[str, Any] = field(default_factory=dict)
    numerator: Mapping[str, Any] = field(default_factory=dict)
    dimension: str = "made_hand"
    holdem_only: bool = False

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise StudyValidationError("panel id must not be empty")
        if not self.title.strip():
            raise StudyValidationError(f"{self.id}: panel title must not be empty")
        if self.kind not in PANEL_KINDS:
            raise StudyValidationError(
                f"{self.id}: unknown panel kind {self.kind!r}; known: {list(PANEL_KINDS)}",
            )
        object.__setattr__(self, "group_by", _as_tuple(self.group_by, f"{self.id}.group_by"))
        if not isinstance(self.filters, Mapping):
            raise StudyValidationError(f"{self.id}.filters must be a mapping")
        if not isinstance(self.numerator, Mapping):
            raise StudyValidationError(f"{self.id}.numerator must be a mapping")

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> StudyPanelSpec:
        """Build one panel from a JSON-shaped mapping."""
        if not isinstance(payload, Mapping):
            raise StudyValidationError("a study panel must be a mapping")
        missing = [name for name in ("id", "title", "kind") if name not in payload]
        if missing:
            raise StudyValidationError(f"panel is missing {missing}")
        return cls(
            id=str(payload["id"]),
            title=str(payload["title"]),
            kind=str(payload["kind"]),
            metric=str(payload.get("metric", "opportunities")),
            group_by=payload.get("group_by", ()),
            filters=payload.get("filters", {}),
            numerator=payload.get("numerator", {}),
            dimension=str(payload.get("dimension", "made_hand")),
            holdem_only=bool(payload.get("holdem_only", False)),
        )

    def as_dict(self) -> dict[str, Any]:
        """Return a serialisable definition containing no executable code."""
        return {
            "id": self.id,
            "title": self.title,
            "kind": self.kind,
            "metric": self.metric,
            "group_by": list(self.group_by),
            "filters": dict(self.filters),
            "numerator": dict(self.numerator),
            "dimension": self.dimension,
            "holdem_only": self.holdem_only,
        }


@dataclass(frozen=True)
class CompiledStudyPanel:
    """A validated panel ready for one of the existing analytics APIs."""

    study_id: str
    panel_id: str
    kind: str
    query: Query
    base_filters: Mapping[str, Any]
    adapter: str
    dimension: str = "made_hand"
    unavailable_reason: str | None = None

    @property
    def available(self) -> bool:
        """Whether this panel can answer for the declared study game."""
        return self.unavailable_reason is None


@dataclass(frozen=True)
class StudySpec:
    """One poker spot and the coordinated panels that read it."""

    id: str
    title: str
    path: tuple[str, ...]
    base_filters: Mapping[str, Any]
    variables: tuple[str, ...]
    panels: tuple[StudyPanelSpec, ...]
    game: str | None = None

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise StudyValidationError("study id must not be empty")
        if not self.title.strip():
            raise StudyValidationError(f"{self.id}: study title must not be empty")
        object.__setattr__(self, "path", _as_tuple(self.path, f"{self.id}.path"))
        object.__setattr__(self, "variables", _as_tuple(self.variables, f"{self.id}.variables"))
        if not isinstance(self.base_filters, Mapping):
            raise StudyValidationError(f"{self.id}.base_filters must be a mapping")
        panels = tuple(self.panels)
        if not panels:
            raise StudyValidationError(f"{self.id}: a study needs at least one panel")
        if any(not isinstance(panel, StudyPanelSpec) for panel in panels):
            raise StudyValidationError(f"{self.id}.panels must contain StudyPanelSpec values")
        object.__setattr__(self, "panels", panels)
        if self.game is not None and not self.game.strip():
            raise StudyValidationError(f"{self.id}.game must not be empty")
        self.validate()

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> StudySpec:
        """Build and validate a study from a declarative mapping."""
        if not isinstance(payload, Mapping):
            raise StudyValidationError("a study must be a mapping")
        missing = [name for name in ("id", "title", "base_filters", "panels") if name not in payload]
        if missing:
            raise StudyValidationError(f"study is missing {missing}")
        raw_panels = payload["panels"]
        if not isinstance(raw_panels, Sequence) or isinstance(raw_panels, (str, bytes)):
            raise StudyValidationError("study.panels must be a sequence")
        return cls(
            id=str(payload["id"]),
            title=str(payload["title"]),
            path=payload.get("path", ()),
            base_filters=payload["base_filters"],
            variables=payload.get("variables", ()),
            panels=tuple(StudyPanelSpec.from_mapping(panel) for panel in raw_panels),
            game=str(payload["game"]) if payload.get("game") is not None else None,
        )

    def validate(self) -> StudySpec:
        """Validate every definition against the existing engine vocabulary."""
        unknown_variables = sorted(set(self.variables) - set(FILTERS))
        if unknown_variables:
            raise StudyValidationError(
                f"{self.id}: unknown study variables {unknown_variables}; known filters are {sorted(FILTERS)}",
            )
        if len(set(self.variables)) != len(self.variables):
            raise StudyValidationError(f"{self.id}: study variables must be unique")
        if len({panel.id for panel in self.panels}) != len(self.panels):
            raise StudyValidationError(f"{self.id}: panel ids must be unique")

        for panel in self.panels:
            query = self._panel_query(panel)
            self._validate_panel_query(panel, query)
        return self

    def bind(self, values: Mapping[str, Any]) -> StudySpec:
        """Return the same study with declared variable values applied."""
        unknown = sorted(set(values) - set(self.variables))
        if unknown:
            raise StudyValidationError(f"{self.id}: values are not declared variables: {unknown}")
        filters = dict(self.base_filters)
        filters.update(values)
        return replace(self, base_filters=filters)

    def population_query(self) -> Query:
        """The canonical population query shared by all panels."""
        return Query(metric="opportunities", filters=dict(self.base_filters))

    def panel(self, panel_id: str) -> CompiledStudyPanel:
        """Compile one named panel without executing it."""
        try:
            spec = next(panel for panel in self.panels if panel.id == panel_id)
        except StopIteration:
            raise KeyError(f"Unknown panel {panel_id!r}; known: {[panel.id for panel in self.panels]}") from None
        query = self._panel_query(spec)
        unavailable_reason = None
        if (spec.holdem_only or spec.kind == "range_grid") and self.game is not None:
            if "holdem" not in self.game.lower() or "omaha" in self.game.lower():
                unavailable_reason = (
                    f"{spec.title} is a Hold'em-only panel and is unavailable for game {self.game!r}"
                )
        return CompiledStudyPanel(
            study_id=self.id,
            panel_id=spec.id,
            kind=spec.kind,
            query=query,
            base_filters=dict(self.base_filters),
            adapter=_adapter_for(spec.kind),
            dimension=spec.dimension,
            unavailable_reason=unavailable_reason,
        )

    def panels_compiled(self) -> tuple[CompiledStudyPanel, ...]:
        """Compile every panel in display order."""
        return tuple(self.panel(panel.id) for panel in self.panels)

    def as_dict(self) -> dict[str, Any]:
        """Return the declarative study definition for storage or inspection."""
        out: dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "path": list(self.path),
            "base_filters": dict(self.base_filters),
            "variables": list(self.variables),
            "panels": [panel.as_dict() for panel in self.panels],
        }
        if self.game is not None:
            out["game"] = self.game
        return out

    def _panel_query(self, panel: StudyPanelSpec) -> Query:
        return Query(
            metric=panel.metric,
            filters=_merge_filters(self.base_filters, panel.filters),
            numerator=dict(panel.numerator),
            group_by=panel.group_by,
        )

    @staticmethod
    def _validate_panel_query(panel: StudyPanelSpec, query: Query) -> None:
        if query.metric not in KNOWN_METRICS:
            raise StudyValidationError(
                f"{panel.id}: unknown metric {query.metric!r}; known: {sorted(KNOWN_METRICS)}",
            )
        StudySpec._validate_panel_vocabulary(panel, query)
        StudySpec._validate_panel_shape(panel, query)

        try:
            rb.validate_preset(
                {
                    "metric": query.metric,
                    "filters": query.filters,
                    "numerator": query.numerator,
                    "group_by": query.group_by,
                },
            )
            compile_query(query, "?", "sqlite")
        except ValueError as exc:
            raise StudyValidationError(f"{panel.id}: {exc}") from exc
        _validate_opportunity_metric(query)

    @staticmethod
    def _validate_panel_vocabulary(panel: StudyPanelSpec, query: Query) -> None:
        unknown_filters = sorted((set(query.filters) | set(query.numerator)) - set(FILTERS))
        if unknown_filters:
            raise StudyValidationError(f"{panel.id}: unknown filters {unknown_filters}")
        unknown_dimensions = sorted(set(query.group_by) - set(DIMENSIONS))
        if unknown_dimensions:
            raise StudyValidationError(f"{panel.id}: unknown dimensions {unknown_dimensions}")

    @staticmethod
    def _validate_panel_shape(panel: StudyPanelSpec, query: Query) -> None:
        if panel.kind == "hand_strength":
            if query.group_by:
                raise StudyValidationError("hand_strength panels use dimension, not group_by")
            if panel.dimension not in COMPOSITION_DIMENSIONS:
                raise StudyValidationError(
                    f"{panel.id}: unknown hand-strength dimension {panel.dimension!r}; "
                    f"known: {sorted(COMPOSITION_DIMENSIONS)}",
                )
        if panel.kind in {"range_grid", "hands", "hand_strength"} and query.group_by:
            raise StudyValidationError(f"{panel.id}: {panel.kind} panels cannot declare group_by")
        if panel.kind == "profit" and query.metric not in _PROFIT_METRICS:
            raise StudyValidationError(
                f"{panel.id}: profit panels need one of {sorted(_PROFIT_METRICS)}, not {query.metric!r}",
            )
        if panel.kind == "range_grid" and not panel.holdem_only:
            raise StudyValidationError(f"{panel.id}: range_grid must declare holdem_only=true")


def _adapter_for(kind: str) -> str:
    if kind in _QUERY_KINDS:
        return "query"
    return {
        "range_grid": "range",
        "hand_strength": "composition",
        "profit": "profit",
        "hands": "hands",
    }[kind]


def execute_panel(
    db: Any,
    compiled: CompiledStudyPanel,
    *,
    min_sample: int = 0,
    hand_limit: int = 200,
) -> Any:
    """Execute a compiled panel through its existing analytics owner."""
    if not compiled.available:
        raise StudyUnavailable(compiled.unavailable_reason or "panel unavailable")
    if compiled.adapter == "query":
        return run_query(db, compiled.query)
    if compiled.adapter == "range":
        return build_range(db, compiled.query, min_sample=min_sample, require_holdem=True)
    if compiled.adapter == "composition":
        return compose(db, compiled.query, dimension=compiled.dimension, min_sample=min_sample)
    if compiled.adapter == "profit":
        return profit_report(db, compiled.query, min_sample=min_sample, with_hand_ids=False)
    if compiled.adapter == "hands":
        return rb.run_drill_down(db, compiled.query, limit=hand_limit)
    raise StudyValidationError(f"Unknown compiled adapter {compiled.adapter!r}")


@dataclass(frozen=True)
class StudyRegistry:
    """Small immutable catalogue used by a future Study Explorer."""

    studies: tuple[StudySpec, ...]

    def __post_init__(self) -> None:
        if len({study.id for study in self.studies}) != len(self.studies):
            raise StudyValidationError("study ids must be unique")
        for study in self.studies:
            study.validate()

    @classmethod
    def from_mappings(cls, payloads: Sequence[Mapping[str, Any]]) -> StudyRegistry:
        """Load and validate a sequence of JSON-shaped study definitions."""
        return cls(tuple(StudySpec.from_mapping(payload) for payload in payloads))

    def get(self, study_id: str) -> StudySpec:
        """Find a study by stable id."""
        try:
            return next(study for study in self.studies if study.id == study_id)
        except StopIteration:
            raise KeyError(f"Unknown study {study_id!r}; known: {[study.id for study in self.studies]}") from None


__all__ = [
    "PANEL_KINDS",
    "CompiledStudyPanel",
    "StudyPanelSpec",
    "StudyRegistry",
    "StudySpec",
    "StudyUnavailable",
    "StudyValidationError",
    "execute_panel",
]
