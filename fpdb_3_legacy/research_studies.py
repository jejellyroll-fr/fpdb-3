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

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
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
from .hand_state import CLASSIFIED_GAMES
from .hand_state_composition import DIMENSIONS as COMPOSITION_DIMENSIONS
from .hand_state_composition import compose
from .holdem_ranges import build_range
from .player_situations import SITUATION_RULES
from .research_presets import RESULT_VIEWS

STUDY_PACK_SCHEMA_VERSION: Final[int] = 1
STUDY_PACK_FIELDS: Final[frozenset[str]] = frozenset(
    {"schema_version", "pack", "label", "description", "studies"},
)
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
    min_sample: int | None = None
    recommended_view: str = "summary"
    tags: tuple[str, ...] = ()

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
        if self.min_sample is not None and (
            not isinstance(self.min_sample, int) or isinstance(self.min_sample, bool) or self.min_sample < 0
        ):
            raise StudyValidationError(f"{self.id}.min_sample must be a non-negative integer")
        if self.recommended_view not in RESULT_VIEWS:
            raise StudyValidationError(
                f"{self.id}: unknown recommended view {self.recommended_view!r}; known: {list(RESULT_VIEWS)}",
            )
        object.__setattr__(self, "tags", _as_tuple(self.tags, f"{self.id}.tags"))

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
            min_sample=payload.get("min_sample"),
            recommended_view=str(payload.get("recommended_view", "summary")),
            tags=payload.get("tags", ()),
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
            "min_sample": self.min_sample,
            "recommended_view": self.recommended_view,
            "tags": list(self.tags),
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
    min_sample: int = 0
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
    description: str = ""
    table_size: int | None = 6
    min_sample: int | None = None
    tags: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    default_panel: str | None = None
    default_comparison: bool = False
    pack: str = ""

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
        if self.table_size is not None and (
            not isinstance(self.table_size, int) or isinstance(self.table_size, bool) or self.table_size < 2
        ):
            raise StudyValidationError(f"{self.id}.table_size must be at least 2")
        if self.min_sample is not None and (
            not isinstance(self.min_sample, int) or isinstance(self.min_sample, bool) or self.min_sample < 0
        ):
            raise StudyValidationError(f"{self.id}.min_sample must be a non-negative integer")
        object.__setattr__(self, "tags", _as_tuple(self.tags, f"{self.id}.tags"))
        object.__setattr__(self, "aliases", _as_tuple(self.aliases, f"{self.id}.aliases"))
        self.validate()
        if self.default_panel is not None and self.default_panel not in {panel.id for panel in panels}:
            raise StudyValidationError(f"{self.id}: default panel {self.default_panel!r} is not present")

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
            description=str(payload.get("description", "")),
            table_size=payload.get("table_size", 6),
            min_sample=payload.get("min_sample"),
            tags=payload.get("tags", ()),
            aliases=payload.get("aliases", ()),
            default_panel=str(payload["default_panel"]) if payload.get("default_panel") is not None else None,
            default_comparison=bool(payload.get("default_comparison", False)),
            pack=str(payload.get("pack", "")),
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
        return CompiledStudyPanel(
            study_id=self.id,
            panel_id=spec.id,
            kind=spec.kind,
            query=query,
            base_filters=dict(self.base_filters),
            adapter=_adapter_for(spec.kind),
            dimension=spec.dimension,
            min_sample=spec.min_sample if spec.min_sample is not None else (self.min_sample or 0),
            unavailable_reason=panel_unavailable_reason(spec, self.game),
        )

    def panels_compiled(self) -> tuple[CompiledStudyPanel, ...]:
        """Compile every panel in display order."""
        return tuple(self.panel(panel.id) for panel in self.panels)

    def as_dict(self) -> dict[str, Any]:
        """Return the declarative study definition for storage or inspection."""
        out: dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "path": list(self.path),
            "base_filters": dict(self.base_filters),
            "variables": list(self.variables),
            "panels": [panel.as_dict() for panel in self.panels],
            "table_size": self.table_size,
            "min_sample": self.min_sample,
            "tags": list(self.tags),
            "aliases": list(self.aliases),
            "default_panel": self.default_panel,
            "default_comparison": self.default_comparison,
        }
        if self.game is not None:
            out["game"] = self.game
        if self.pack:
            out["pack"] = self.pack
        return out

    @property
    def tournament(self) -> bool | None:
        """Whether this study is about tournament hands, cash hands or either.

        Read off the population rather than declared twice: a study that pins
        ``tournament`` in its base filters *is* a tournament study, and one
        that does not applies to both (#369).
        """
        value = self.base_filters.get("tournament")
        return None if value is None else bool(value)

    @property
    def search_terms(self) -> tuple[str, ...]:
        """Searchable poker language for a future Study Explorer."""
        return tuple(dict.fromkeys((self.title, *self.aliases, *self.tags, *self.path)))

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


def panel_unavailable_reason(spec: StudyPanelSpec, game: str | None) -> str | None:
    """Why a valid panel cannot answer for a given game, or ``None``.

    Two rules, both about not showing a Hold'em answer for a four-card hand:

    * a 13x13 starting-hand grid describes two hole cards, so it has no
      meaning for Omaha -- there is no 13x13 representation of a four-card
      holding to fall back on (#368);
    * a hand-state panel asks the classifier, and the classifier is explicit
      about which games it reads. Rather than restate that rule here, the
      check is membership of :data:`hand_state.CLASSIFIED_GAMES`, so a variant
      the classifier learns later becomes available without a second edit.

    An undeclared game (``None``) means the study did not claim one, and a
    panel is not disabled on a guess.
    """
    if game is None:
        return None
    if spec.holdem_only or spec.kind == "range_grid":
        lowered = game.lower()
        if "holdem" not in lowered or "omaha" in lowered:
            return (
                f"{spec.title} reads two hole cards, so it is a Hold'em-only panel "
                f"and is unavailable for game {game!r}"
            )
    if spec.kind == "hand_strength" and game not in CLASSIFIED_GAMES:
        return (
            f"{spec.title} needs the postflop hand-state classifier, which reads "
            f"{sorted(CLASSIFIED_GAMES)} only: a {game!r} hand is never classified by "
            "its best two cards"
        )
    return None


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
    min_sample: int | None = None,
    hand_limit: int = 200,
) -> Any:
    """Execute a compiled panel through its existing analytics owner."""
    if not compiled.available:
        raise StudyUnavailable(compiled.unavailable_reason or "panel unavailable")
    sample = compiled.min_sample if min_sample is None else min_sample
    if compiled.adapter == "query":
        return run_query(db, compiled.query)
    if compiled.adapter == "range":
        return build_range(db, compiled.query, min_sample=sample, require_holdem=True)
    if compiled.adapter == "composition":
        return compose(db, compiled.query, dimension=compiled.dimension, min_sample=sample)
    if compiled.adapter == "profit":
        return profit_report(db, compiled.query, min_sample=sample, with_hand_ids=False)
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


@dataclass(frozen=True)
class StudyPack:
    """One declarative pack of hierarchical studies."""

    id: str
    label: str
    description: str
    studies: tuple[StudySpec, ...]

    def registry(self) -> StudyRegistry:
        """Expose the pack through the same catalogue API as other studies."""
        return StudyRegistry(self.studies)


def study_library_dir() -> Path:
    """The directory containing shipped study packs."""
    return Path(__file__).resolve().parent / "research_studies.d"


def _load_pack(raw: Any, source: str) -> StudyPack:
    if not isinstance(raw, Mapping):
        raise ValueError(f"{source}: a study pack must be a mapping")
    unknown = sorted(set(raw) - STUDY_PACK_FIELDS)
    if unknown:
        raise ValueError(f"{source}: unknown pack field(s) {unknown}")
    if raw.get("schema_version") != STUDY_PACK_SCHEMA_VERSION:
        raise ValueError(
            f"{source}: schema_version must be {STUDY_PACK_SCHEMA_VERSION}, "
            f"got {raw.get('schema_version')!r}",
        )
    pack_id = str(raw.get("pack") or "").strip()
    if not pack_id:
        raise ValueError(f"{source}: pack must be a non-empty id")
    entries = raw.get("studies")
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"{source}: studies must be a non-empty list")
    studies: list[StudySpec] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise ValueError(f"{source}[{pack_id}]: a study must be a mapping")
        payload = dict(entry)
        payload["pack"] = pack_id
        try:
            studies.append(StudySpec.from_mapping(payload))
        except StudyValidationError as exc:
            raise ValueError(f"{source}[{pack_id}]: {exc}") from exc
    ids = [study.id for study in studies]
    if len(set(ids)) != len(ids):
        raise ValueError(f"{source}: duplicate study ids")
    return StudyPack(
        id=pack_id,
        label=str(raw.get("label") or pack_id),
        description=str(raw.get("description") or ""),
        studies=tuple(studies),
    )


def load_study_packs(directory: str | Path | None = None) -> tuple[StudyPack, ...]:
    """Load every JSON study pack and validate it before it reaches the UI."""
    root = Path(directory) if directory is not None else study_library_dir()
    if not root.is_dir():
        return ()
    packs = []
    for path in sorted(root.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path} is not valid JSON: {exc}") from exc
        packs.append(_load_pack(raw, str(path)))
    ids = [pack.id for pack in packs]
    if len(set(ids)) != len(ids):
        raise ValueError(f"duplicate study pack ids: {ids}")
    return tuple(packs)


def load_study_registry(directory: str | Path | None = None) -> StudyRegistry:
    """Load all studies from all packs into one catalogue."""
    studies = tuple(study for pack in load_study_packs(directory) for study in pack.studies)
    return StudyRegistry(studies)


def builtin_studies(directory: str | Path | None = None) -> StudyRegistry:
    """The shipped Study Explorer catalogue."""
    return load_study_registry(directory)


__all__ = [
    "PANEL_KINDS",
    "STUDY_PACK_SCHEMA_VERSION",
    "CompiledStudyPanel",
    "StudyPack",
    "StudyPanelSpec",
    "StudyRegistry",
    "StudySpec",
    "StudyUnavailable",
    "StudyValidationError",
    "execute_panel",
    "builtin_studies",
    "load_study_packs",
    "load_study_registry",
    "panel_unavailable_reason",
    "study_library_dir",
]
