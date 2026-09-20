"""The research browser's shipped preset library (issue #330).

``research_browser`` already has a preset format and a validation path, but the
presets were *user* data in ``research_presets.json``: to get the first useful
answer, a new user had to know a metric, a filter set and a dimension list
before they had seen a single result. This module ships the answers instead.

A **pack** is one JSON document under ``research_presets.d/`` -- data, never
code -- holding named presets expressed in exactly the engine vocabulary
``validate_preset`` already checks (``analytics_query``'s metrics, filters and
dimensions). Nothing here is stored as SQL, and nothing here is executed: a pack
that names a metric the engine does not know is a ``ValueError`` at load time,
which is what makes "invalid shipped presets fail CI" a fact rather than a hope.

What a pack entry adds on top of a query is *product* metadata:

* a localized ``name``/``description`` (a string, or a locale table like the
  declarative stat definitions use);
* a ``category`` from a fixed list, so the picker can group by poker topic
  instead of by file order;
* a ``recommended_view``, the result view the question is best read through
  (the workbench of #331 honours it; today it is metadata);
* a ``min_sample`` guidance, the sample below which the answer means little;
* ``variables`` -- the filters a user is expected to make their own (their
  player, their stake, their date range) before trusting the answer.
* ``tags``, for search.

Built-ins are read-only by construction: they live in this package's directory,
while user presets are written to the user's config directory, so a save can
shadow a built-in but can never overwrite it. ``builtin_presets`` is what the
rest of the app asks for, and it can be switched off explicitly (see
``builtins_enabled``) rather than by deleting files.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from typing import Any, Final, NoReturn

from .research_browser import validate_preset

# The pack schema this module understands. A pack written for a newer schema is
# refused rather than half-read, like every other declarative file in fpdb.
PRESET_LIBRARY_SCHEMA_VERSION: Final = 1

# The poker topics a pack may file a preset under. Fixed so the picker can group
# by them and so a typo is a load-time error.
CATEGORIES: Final[tuple[str, ...]] = (
    "preflop",
    "postflop",
    "pot type",
    "board",
    "range",
    "population",
    "profit",
)

# The result views of the workbench (#331). A preset may nominate one; the
# vocabulary lives here so a pack cannot invent a view that will never exist.
RESULT_VIEWS: Final[tuple[str, ...]] = (
    "summary",
    "table",
    "frequencies",
    "sizing",
    "position",
    "board",
    "range",
    "hand_strength",
    "profit",
    "hands",
)

# The environment flag that turns the library off without deleting it. An
# explicit opt-out, because "Research opens with no presets" should be a choice
# rather than the default state of a fresh install.
DISABLE_BUILTINS_ENV: Final = "FPDB_RESEARCH_NO_BUILTIN_PRESETS"

_PACK_FIELDS: Final[frozenset[str]] = frozenset(
    {"schema_version", "pack", "label", "description", "presets"},
)
_PRESET_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "id",
        "name",
        "description",
        "category",
        "metric",
        "filters",
        "numerator",
        "group_by",
        "recommended_view",
        "min_sample",
        "variables",
        "tags",
    },
)


def _fail(message: str, source: str) -> NoReturn:
    raise ValueError(f"{source}: {message}")


def _localized(value: Any, locale: str, field: str, source: str) -> Any:
    """A name/description as text: either one string or a locale table."""
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        for key, text in value.items():
            if not isinstance(text, str):
                _fail(f"{field}.{key} must be a string", source)
        for candidate in (locale, "en"):
            if candidate in value:
                return value[candidate]
        return next(iter(value.values())) if value else ""
    _fail(f"{field} must be a string or a locale table, got {type(value).__name__}", source)


@dataclass(frozen=True)
class LibraryPreset:
    """One shipped question: its engine vocabulary, plus how to present it.

    ``query`` is the shape ``research_browser`` speaks, so a built-in preset and
    a user preset reach ``execute_preset`` through the same door.
    """

    id: str
    name: str
    description: str
    category: str
    metric: str
    filters: Mapping[str, Any]
    numerator: Mapping[str, Any]
    group_by: tuple[str, ...]
    recommended_view: str
    min_sample: int | None
    variables: tuple[str, ...]
    tags: tuple[str, ...]
    pack: str = ""

    @property
    def query(self) -> dict[str, Any]:
        """The preset as the engine vocabulary a query is built from."""
        return {
            "metric": self.metric,
            "filters": dict(self.filters),
            "numerator": dict(self.numerator),
            "group_by": self.group_by,
            "description": self.description,
        }


@dataclass(frozen=True)
class PresetPack:
    """One shipped document: its identity and the presets it contributes."""

    id: str
    label: str
    description: str
    presets: tuple[LibraryPreset, ...]


def library_dir() -> Path:
    """The package directory the shipped packs live in."""
    return Path(__file__).resolve().parent / "research_presets.d"


def builtins_enabled() -> bool:
    """Whether the shipped library is offered (opt-out via the environment)."""
    value = os.environ.get(DISABLE_BUILTINS_ENV, "").strip().lower()
    return value not in ("1", "true", "yes", "on")


def _validate_pack(raw: Any, source: str) -> PresetPack:
    if not isinstance(raw, Mapping):
        _fail(f"a pack is a mapping, not {type(raw).__name__}", source)
    unknown = sorted(set(raw) - _PACK_FIELDS)
    if unknown:
        _fail(f"unknown pack field(s) {unknown}; known: {sorted(_PACK_FIELDS)}", source)
    if raw.get("schema_version") != PRESET_LIBRARY_SCHEMA_VERSION:
        _fail(
            f"schema_version must be {PRESET_LIBRARY_SCHEMA_VERSION}, "
            f"got {raw.get('schema_version')!r}",
            source,
        )
    pack_id = str(raw.get("pack") or "").strip()
    if not pack_id:
        _fail("pack must be a non-empty id", source)
    entries = raw.get("presets")
    if not isinstance(entries, list) or not entries:
        _fail("presets must be a non-empty list", source)
    presets = tuple(
        replace(_validate_preset(entry, f"{source}[{pack_id}]"), pack=pack_id) for entry in entries
    )
    duplicate = _duplicates(preset.id for preset in presets)
    if duplicate:
        _fail(f"duplicate preset id(s): {duplicate}", source)
    return PresetPack(
        id=pack_id,
        label=str(raw.get("label") or pack_id),
        description=str(raw.get("description") or ""),
        presets=presets,
    )


def _duplicates(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value in seen and value not in out:
            out.append(value)
        seen.add(value)
    return out


def _validate_preset(raw: Any, source: str) -> LibraryPreset:
    if not isinstance(raw, Mapping):
        _fail(f"a preset is a mapping, not {type(raw).__name__}", source)
    unknown = sorted(set(raw) - _PRESET_FIELDS)
    if unknown:
        _fail(f"unknown preset field(s) {unknown}; known: {sorted(_PRESET_FIELDS)}", source)
    preset_id = str(raw.get("id") or "").strip()
    if not preset_id:
        _fail("id must be a non-empty string", source)
    source = f"{source}#{preset_id}"
    category = str(raw.get("category") or "").strip().lower()
    if category not in CATEGORIES:
        _fail(f"unknown category {category!r}; known: {list(CATEGORIES)}", source)
    # The engine vocabulary is checked by the browser's own validator, which is
    # the single place a preset -- shipped or user-written -- can be refused.
    try:
        query = validate_preset(
            {
                "metric": raw.get("metric"),
                "filters": raw.get("filters", {}),
                "numerator": raw.get("numerator", {}),
                "group_by": raw.get("group_by", ()),
            },
        )
    except ValueError as exc:
        _fail(str(exc), source)
    view = str(raw.get("recommended_view") or "summary").strip().lower()
    if view not in RESULT_VIEWS:
        _fail(f"unknown recommended_view {view!r}; known: {list(RESULT_VIEWS)}", source)
    min_sample = raw.get("min_sample")
    if min_sample is not None and (not isinstance(min_sample, int) or isinstance(min_sample, bool) or min_sample < 0):
        _fail(f"min_sample must be a non-negative integer, got {min_sample!r}", source)
    return LibraryPreset(
        id=preset_id,
        name=_localized(raw.get("name", preset_id), "en", "name", source),
        description=_localized(raw.get("description", ""), "en", "description", source),
        category=category,
        metric=query["metric"],
        filters=query["filters"],
        numerator=query["numerator"],
        group_by=query["group_by"],
        recommended_view=view,
        min_sample=min_sample,
        variables=tuple(str(name) for name in raw.get("variables", ()) or ()),
        tags=tuple(str(tag) for tag in raw.get("tags", ()) or ()),
    )


def load_packs(directory: str | Path | None = None) -> tuple[PresetPack, ...]:
    """Every pack file in ``directory``, validated, in file-name order."""
    root = Path(directory) if directory is not None else library_dir()
    if not root.is_dir():
        return ()
    packs: list[PresetPack] = []
    for path in sorted(root.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path} is not valid JSON: {exc}") from exc
        packs.append(_validate_pack(raw, str(path)))
    duplicate = _duplicates(preset.id for pack in packs for preset in pack.presets)
    if duplicate:
        raise ValueError(f"preset id(s) shipped twice across packs: {duplicate}")
    return tuple(packs)


@lru_cache(maxsize=4)
def _cached_presets(directory: str) -> tuple[LibraryPreset, ...]:
    return tuple(preset for pack in load_packs(directory) for preset in pack.presets)


def load_library(directory: str | Path | None = None) -> tuple[LibraryPreset, ...]:
    """Every shipped preset, in pack then file order (no caching, for tests)."""
    root = Path(directory) if directory is not None else library_dir()
    return _cached_presets(str(root))


def builtin_presets(directory: str | Path | None = None) -> tuple[LibraryPreset, ...]:
    """The shipped presets the app offers, or ``()`` when disabled."""
    if not builtins_enabled():
        return ()
    return load_library(directory)


def categories(presets: Iterable[LibraryPreset]) -> tuple[str, ...]:
    """The categories actually present, in the canonical order."""
    present = {preset.category for preset in presets}
    return tuple(category for category in CATEGORIES if category in present)


def find_preset(presets: Iterable[LibraryPreset], preset_id: str) -> LibraryPreset | None:
    """One shipped preset by id, or ``None``."""
    return next((preset for preset in presets if preset.id == preset_id), None)


def is_builtin_name(presets: Iterable[LibraryPreset], name: str) -> bool:
    """Whether ``name`` is a shipped preset's name (so a save would shadow it)."""
    return any(preset.name == name for preset in presets)


__all__ = [
    "CATEGORIES",
    "DISABLE_BUILTINS_ENV",
    "PRESET_LIBRARY_SCHEMA_VERSION",
    "RESULT_VIEWS",
    "LibraryPreset",
    "PresetPack",
    "builtin_presets",
    "builtins_enabled",
    "categories",
    "find_preset",
    "is_builtin_name",
    "library_dir",
    "load_library",
    "load_packs",
]
