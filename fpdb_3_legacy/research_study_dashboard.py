"""Synchronized state and execution model for one Poker Study dashboard (#361)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any, Final

from .analytics_query import FILTERS, Query
from .research_studies import CompiledStudyPanel, StudySpec, execute_panel
from .research_study_explorer import StudySelection

COMPARISON_HERO: Final = "hero"
COMPARISON_FIELD: Final = "field"
COMPARISON_HERO_VS_FIELD: Final = "hero_vs_field"
COMPARISON_MODES: Final[tuple[str, ...]] = (
    COMPARISON_HERO,
    COMPARISON_FIELD,
    COMPARISON_HERO_VS_FIELD,
)


@dataclass(frozen=True)
class CrossFilter:
    """One explicit, removable narrowing shared by every dashboard panel."""

    name: str
    value: Any
    label: str


@dataclass(frozen=True)
class DashboardState:
    """The complete navigable state of a Study page."""

    study_id: str
    base_filters: Mapping[str, Any]
    variable_values: Mapping[str, Any]
    comparison: str
    active_panel: str
    cross_filters: tuple[CrossFilter, ...] = ()
    min_sample: int = 0


@dataclass(frozen=True)
class DashboardComparison:
    """The same panel result for Hero and Field, with no ambiguous merge."""

    hero: Any
    field: Any


class StudyDashboardModel:
    """Own one canonical population and derive every panel from it."""

    def __init__(self, selection: StudySelection, *, min_sample: int | None = None) -> None:
        if not selection.available:
            raise ValueError(selection.unavailable_reason or "study is unavailable")
        self.selection = selection
        self._study = replace(selection.study, base_filters=dict(selection.effective_filters))
        default_panel = self._study.default_panel or self._study.panels[0].id
        default_comparison = (
            COMPARISON_HERO_VS_FIELD if self._study.default_comparison else COMPARISON_HERO
        )
        self._state = DashboardState(
            study_id=self._study.id,
            base_filters=dict(self._study.base_filters),
            variable_values=dict(selection.variable_values),
            comparison=default_comparison,
            active_panel=default_panel,
            min_sample=self._study.min_sample or 0 if min_sample is None else min_sample,
        )
        self._cache: dict[str, Any] = {}

    @property
    def study(self) -> StudySpec:
        return self._study

    @property
    def state(self) -> DashboardState:
        return self._state

    @property
    def base_filters(self) -> Mapping[str, Any]:
        """The exact population every panel starts from."""
        return self._state.base_filters

    def panel_ids(self) -> tuple[str, ...]:
        return tuple(panel.id for panel in self._study.panels)

    def panel_titles(self) -> dict[str, str]:
        return {panel.id: panel.title for panel in self._study.panels}

    def panel(self, panel_id: str) -> CompiledStudyPanel:
        """Compile a panel after applying the current explicit cross-filters."""
        compiled = self._study.panel(panel_id)
        filters = dict(compiled.query.filters)
        for cross_filter in self._state.cross_filters:
            if cross_filter.name in filters and filters[cross_filter.name] != cross_filter.value:
                raise ValueError(
                    f"cross-filter {cross_filter.name!r}={cross_filter.value!r} conflicts with "
                    f"the study population {cross_filter.name!r}={filters[cross_filter.name]!r}",
                )
            filters[cross_filter.name] = cross_filter.value
        query = replace(compiled.query, filters=filters)
        return replace(compiled, query=query, base_filters=dict(self._state.base_filters))

    def panel_query(self, panel_id: str) -> Query:
        """Return the query used by a panel, useful for drill-down and tests."""
        return self.panel(panel_id).query

    def population_fingerprint(self) -> str:
        """Identify the shared spot population independently of its panel."""
        return json.dumps(
            {"study_id": self._state.study_id, "base_filters": dict(self._state.base_filters)},
            sort_keys=True,
            default=str,
            separators=(",", ":"),
        )

    def side_query(self, panel_id: str, hero: bool) -> Query:
        """The exact Hero or Field query used by a comparison panel."""
        query = self.panel_query(panel_id)
        return replace(query, filters={**query.filters, "hero": hero})

    def set_active_panel(self, panel_id: str) -> None:
        if panel_id not in self.panel_ids():
            raise KeyError(f"Unknown dashboard panel {panel_id!r}; known: {list(self.panel_ids())}")
        self._state = replace(self._state, active_panel=panel_id)

    def set_comparison(self, comparison: str) -> None:
        if comparison not in COMPARISON_MODES:
            raise ValueError(f"Unknown comparison mode {comparison!r}; known: {list(COMPARISON_MODES)}")
        self._state = replace(self._state, comparison=comparison)

    def set_min_sample(self, min_sample: int) -> None:
        if min_sample < 0:
            raise ValueError("minimum sample must not be negative")
        self._state = replace(self._state, min_sample=min_sample)

    def set_variable(self, name: str, value: Any) -> None:
        """Change one declared variable and invalidate all derived panel work."""
        if name not in self._study.variables:
            raise ValueError(f"Values are not declared by {self._study.id}: {[name]}")
        variables = dict(self._state.variable_values)
        if value in (None, "", "any"):
            variables.pop(name, None)
        else:
            variables[name] = value
        base_filters = dict(self.selection.study.base_filters)
        for context_name, context_value in self.selection.context_filters.items():
            if context_value not in (None, "", "any"):
                base_filters[context_name] = context_value
        base_filters.update(variables)
        self._study = replace(self._study, base_filters=base_filters)
        self._state = replace(
            self._state,
            base_filters=base_filters,
            variable_values=variables,
        )

    def add_cross_filter(self, name: str, value: Any, label: str | None = None) -> CrossFilter:
        """Add a temporary, visible filter; adding the same key replaces it."""
        if name not in FILTERS:
            raise ValueError(f"Unknown cross-filter {name!r}")
        if name in self._state.base_filters and self._state.base_filters[name] != value:
            raise ValueError(
                f"cross-filter {name!r}={value!r} conflicts with the study population "
                f"{name!r}={self._state.base_filters[name]!r}",
            )
        cross_filter = CrossFilter(name, value, label or f"{name}={value}")
        filters = tuple(item for item in self._state.cross_filters if item.name != name)
        self._state = replace(self._state, cross_filters=(*filters, cross_filter))
        return cross_filter

    def remove_cross_filter(self, name: str) -> None:
        self._state = replace(
            self._state,
            cross_filters=tuple(item for item in self._state.cross_filters if item.name != name),
        )

    def clear_cross_filters(self) -> None:
        self._state = replace(self._state, cross_filters=())

    def fingerprint(self, panel_id: str | None = None) -> str:
        """Stable cache key for one panel and the full dashboard context."""
        payload = {
            "study_id": self._state.study_id,
            "panel_id": panel_id or self._state.active_panel,
            "base_filters": dict(self._state.base_filters),
            "variables": dict(self._state.variable_values),
            "comparison": self._state.comparison,
            "cross_filters": [item.__dict__ for item in self._state.cross_filters],
            "min_sample": self._state.min_sample,
        }
        return json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))

    def execute_panel(self, db: Any, panel_id: str | None = None) -> Any:
        """Execute one panel, or both sides when the study is in comparison mode."""
        chosen = panel_id or self._state.active_panel
        compiled = self.panel(chosen)
        if self._state.comparison == COMPARISON_HERO_VS_FIELD:
            return DashboardComparison(
                hero=self._execute_side(db, compiled, True, self._state.min_sample),
                field=self._execute_side(db, compiled, False, self._state.min_sample),
            )
        hero = self._state.comparison == COMPARISON_HERO
        return self._execute_side(db, compiled, hero, self._state.min_sample)

    def execute_cached(self, db: Any, panel_id: str | None = None) -> Any:
        key = self.fingerprint(panel_id)
        if key not in self._cache:
            self._cache[key] = self.execute_panel(db, panel_id)
        return self._cache[key]

    def invalidate_cache(self) -> None:
        self._cache.clear()

    @staticmethod
    def _execute_side(db: Any, compiled: CompiledStudyPanel, hero: bool, min_sample: int) -> Any:
        filters = dict(compiled.query.filters)
        filters["hero"] = hero
        query = replace(compiled.query, filters=filters)
        return execute_panel(
            db,
            replace(compiled, query=query, base_filters=filters),
            min_sample=min_sample,
        )


__all__ = [
    "COMPARISON_FIELD",
    "COMPARISON_HERO",
    "COMPARISON_HERO_VS_FIELD",
    "COMPARISON_MODES",
    "CrossFilter",
    "DashboardComparison",
    "DashboardState",
    "StudyDashboardModel",
]
