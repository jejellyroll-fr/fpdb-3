"""Qt-free navigation model for the spot-first Study Explorer (#360)."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from .analytics_query import FILTERS
from .Configuration import CONFIG_PATH
from .research_studies import StudyRegistry, StudySpec, builtin_studies

HISTORY_VERSION: Final[int] = 1
MAX_RECENT: Final[int] = 8
GLOBAL_CONTEXT_FILTERS: Final[frozenset[str]] = frozenset(
    {"game", "tournament", "max_seats", "hero", "player", "stake_bb", "date_from", "date_to"},
)

_CATEGORY_LABELS: Final[dict[str, str]] = {
    "preflop": "Preflop",
    "single-raised": "Single-Raised Pots",
    "three-bet-pot": "3-bet Pots",
    "four-bet-pot": "4-bet Pots",
    "population": "Database / Population",
}
_CATEGORY_DESCRIPTIONS: Final[dict[str, str]] = {
    "preflop": "Opening, defending, 3-betting and squeezing before the flop.",
    "single-raised": "Study the raiser and caller across common SRP streets.",
    "three-bet-pot": "Understand aggression and defence after a 3-bet.",
    "four-bet-pot": "Keep rare 4-bet-pot decisions compact and interpretable.",
    "population": "Compare your decisions with the wider database population.",
}
_CATEGORY_ORDER: Final[tuple[str, ...]] = (
    "preflop",
    "single-raised",
    "three-bet-pot",
    "four-bet-pot",
    "population",
)


def _search_key(value: str) -> str:
    """Make ``3bet`` and ``3-bet`` search as the same poker term."""
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _category_id(study: StudySpec) -> str:
    if study.path and study.path[0] == "postflop" and len(study.path) > 1:
        return study.path[1]
    return study.path[0] if study.path else "population"


def _segment_label(segment: str) -> str:
    if segment in _CATEGORY_LABELS:
        return _CATEGORY_LABELS[segment]
    return segment.replace("-", " ").title()


@dataclass(frozen=True)
class StudyCategory:
    """One landing-page card generated from study paths."""

    id: str
    label: str
    description: str
    study_count: int


@dataclass(frozen=True)
class StudyGame:
    """One game the shipped study library covers, for the landing page."""

    id: str
    label: str
    study_count: int


#: The games the shipped packs declare, named the way a player says them
#: rather than the way the database stores them. The key is the stored
#: ``Gametypes.category`` token, so choosing one narrows the query as well as
#: the list; an unlisted token falls back to its own spelling rather than
#: being hidden.
GAME_LABELS: Final[dict[str, str]] = {
    "holdem": "Hold'em",
    "omahahi": "Pot-Limit Omaha",
    "omahahilo": "Omaha Hi/Lo",
    "5_omahahi": "5-card PLO",
    "6_omahahi": "6-card PLO",
}


def game_label(game: str) -> str:
    """The readable name of one stored game category."""
    return GAME_LABELS.get(game, game.replace("_", " ").title())


@dataclass(frozen=True)
class StudySelection:
    """A study opened with the context the user chose on the landing page."""

    study: StudySpec
    context_filters: Mapping[str, Any] = field(default_factory=dict)
    variable_values: Mapping[str, Any] = field(default_factory=dict)
    effective_filters: Mapping[str, Any] = field(default_factory=dict)
    unavailable_reason: str | None = None

    @property
    def available(self) -> bool:
        return self.unavailable_reason is None


class StudyHistory:
    """Small persistent state: IDs and variable choices, never query results."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else Path(CONFIG_PATH) / "research_study_history.json"
        self.recent: list[dict[str, Any]] = []
        self.favorites: list[str] = []
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(raw, Mapping) or raw.get("version") != HISTORY_VERSION:
            return
        recent = raw.get("recent", [])
        favorites = raw.get("favorites", [])
        if isinstance(recent, list):
            self.recent = [
                {"study_id": str(item["study_id"]), "variables": dict(item.get("variables", {}))}
                for item in recent
                if isinstance(item, Mapping) and item.get("study_id")
            ][:MAX_RECENT]
        if isinstance(favorites, list):
            self.favorites = [str(study_id) for study_id in favorites if study_id]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": HISTORY_VERSION, "recent": self.recent[:MAX_RECENT], "favorites": self.favorites}
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def remember(self, study_id: str, variables: Mapping[str, Any]) -> None:
        entry = {"study_id": study_id, "variables": dict(variables)}
        self.recent = [item for item in self.recent if item.get("study_id") != study_id]
        self.recent.insert(0, entry)
        self.recent = self.recent[:MAX_RECENT]
        self.save()

    def toggle_favorite(self, study_id: str) -> bool:
        if study_id in self.favorites:
            self.favorites.remove(study_id)
            favorite = False
        else:
            self.favorites.append(study_id)
            favorite = True
        self.save()
        return favorite


class StudyExplorerModel:
    """Navigation, search and context logic independent of Qt."""

    def __init__(self, registry: StudyRegistry | None = None, state_path: str | Path | None = None) -> None:
        self.registry = registry or builtin_studies()
        self.history = StudyHistory(state_path)

    def games(self) -> tuple[StudyGame, ...]:
        """The games the shipped studies declare, with how many each has.

        A study declares the game it is about, so the landing page can offer
        the ones this library actually has rather than a hard-coded pair of
        names. Studies that declare no game apply to any of them and are
        counted in every entry (#368).
        """
        declared: dict[str, int] = {}
        for study in self.registry.studies:
            if study.game:
                declared[study.game] = declared.get(study.game, 0) + 1
        shared = sum(1 for study in self.registry.studies if not study.game)
        return tuple(
            StudyGame(id=game, label=game_label(game), study_count=count + shared)
            for game, count in sorted(declared.items(), key=lambda item: (-item[1], item[0]))
        )

    def studies_for_game(self, game: str | None) -> tuple[StudySpec, ...]:
        """Every study that applies to one game, or all of them for ``None``."""
        if game in (None, "", "any"):
            return self.registry.studies
        return tuple(study for study in self.registry.studies if not study.game or study.game == game)

    def categories(self, game: str | None = None) -> tuple[StudyCategory, ...]:
        studies = self.studies_for_game(game)
        counts: dict[str, int] = {}
        for study in studies:
            counts[_category_id(study)] = counts.get(_category_id(study), 0) + 1
        return tuple(
            StudyCategory(
                id=category_id,
                label=_CATEGORY_LABELS[category_id],
                description=_CATEGORY_DESCRIPTIONS[category_id],
                study_count=counts.get(category_id, 0),
            )
            for category_id in _CATEGORY_ORDER
        )

    def studies_for_category(self, category_id: str, game: str | None = None) -> tuple[StudySpec, ...]:
        return tuple(
            study for study in self.studies_for_game(game) if _category_id(study) == category_id
        )

    def search(
        self,
        text: str = "",
        category_id: str | None = None,
        game: str | None = None,
    ) -> tuple[StudySpec, ...]:
        wanted = [_search_key(token) for token in text.split() if token.strip()]
        studies = self.studies_for_game(game)
        if category_id is not None:
            studies = self.studies_for_category(category_id, game)
        matches = []
        for study in studies:
            haystack = " ".join(
                (
                    study.title,
                    study.description,
                    *study.search_terms,
                    *(panel.title for panel in study.panels),
                    *(tag for panel in study.panels for tag in panel.tags),
                ),
            )
            normalized = _search_key(haystack)
            if all(token in normalized for token in wanted):
                matches.append(study)
        return tuple(matches)

    def breadcrumbs(self, study: StudySpec) -> tuple[str, ...]:
        return tuple(_segment_label(segment) for segment in study.path) + (study.title,)

    def open_study(
        self,
        study_id: str,
        *,
        context_filters: Mapping[str, Any] | None = None,
        variable_values: Mapping[str, Any] | None = None,
        remember: bool = True,
    ) -> StudySelection:
        study = self.registry.get(study_id)
        context = dict(context_filters or {})
        variables = dict(variable_values or {})
        unknown_context = sorted(set(context) - GLOBAL_CONTEXT_FILTERS)
        if unknown_context:
            raise ValueError(f"Unknown Study Explorer context filters: {unknown_context}")
        unknown_variables = sorted(set(variables) - set(study.variables))
        if unknown_variables:
            raise ValueError(f"Values are not declared by {study_id}: {unknown_variables}")

        effective = dict(study.base_filters)
        unavailable: str | None = None
        for name, value in {**context, **variables}.items():
            if value in (None, "", "any"):
                continue
            if name in effective and effective[name] != value:
                unavailable = (
                    f"{study.title} is not available for {name}={value!r}; "
                    f"this study requires {name}={effective[name]!r}"
                )
                continue
            if name not in FILTERS:
                raise ValueError(f"Unknown Study Explorer filter {name!r}")
            effective[name] = value
        selection = StudySelection(
            study=study,
            context_filters=context,
            variable_values=variables,
            effective_filters=effective,
            unavailable_reason=unavailable,
        )
        if selection.available and remember:
            self.history.remember(study.id, variables)
        return selection

    def recent_studies(self) -> tuple[StudySpec, ...]:
        by_id = {study.id: study for study in self.registry.studies}
        return tuple(by_id[item["study_id"]] for item in self.history.recent if item["study_id"] in by_id)

    def is_favorite(self, study_id: str) -> bool:
        return study_id in self.history.favorites

    def toggle_favorite(self, study_id: str) -> bool:
        return self.history.toggle_favorite(study_id)


__all__ = [
    "GAME_LABELS",
    "GLOBAL_CONTEXT_FILTERS",
    "HISTORY_VERSION",
    "MAX_RECENT",
    "StudyCategory",
    "StudyExplorerModel",
    "StudyGame",
    "StudyHistory",
    "StudySelection",
    "game_label",
]
