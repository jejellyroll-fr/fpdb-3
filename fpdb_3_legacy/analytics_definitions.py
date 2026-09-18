"""Declarative stat and filter definitions over the query engine (#306).

The engine (#297) lets a *new* question be asked at call time -- a metric, a
dict of filters, a list of dimensions. This module lets the question be
*stored*: a :class:`StatDefinition` is one stat as data, loaded from JSON (or
YAML when PyYAML is installed), validated before anything runs, and compiled
into exactly the :class:`~fpdb_3_legacy.analytics_query.Query` the engine
already knows how to execute.

A definition keeps three things apart, on purpose:

* **Query semantics** -- ``metric``, ``filters``, ``numerator``,
  ``group_by``. This is the entire meaning of the stat; everything else is
  presentation.
* **Display metadata** -- a ``label`` and ``description`` that may be a
  mapping of locale to text, a ``format`` (``percentage``, ``count``,
  ``bb``, ``currency``, ``decimal``, ``ratio``), a ``precision``, a
  ``category`` and a ``min_sample`` threshold below which a result is not
  shown.
* **Reuse** -- ``fragments`` names reusable filter bundles (``preflop``,
  ``single_raised_pot``, ``in_position``, ``facing_cbet``, ...) so the same
  "single-raised pot, in position" condition is written once and shared.

Everything is looked up in a registry: a metric, filter, dimension, format or
fragment name that does not exist is a ``ValueError`` naming the field and
listing what is allowed. There is no ``eval``, no SQL text and no Python in a
definition -- a definition file can only name things this module already
knows, which is what makes an untrusted ``.json`` safe to load.

The schema carries its own ``schema_version``; a file written for a newer
schema is refused rather than half-understood.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, NoReturn

from .analytics_query import (
    DIMENSIONS,
    FILTERS,
    KNOWN_METRICS,
    CompiledQuery,
    Query,
    QueryResult,
    QueryRow,
    compile_query,
    run_query,
)

# The version of the definition schema this module understands. A definition
# file declares its own; a file from the future is refused, not guessed at.
DEFINITION_SCHEMA_VERSION: Final = 1

# ---------------------------------------------------------------------------
# The vocabulary: friendly names a definition may use, mapped onto the engine.
# ---------------------------------------------------------------------------

# Metric names in the issue's prose ("action_frequency") as well as the
# engine's own. A name the engine already knows passes through unchanged.
METRIC_ALIASES: Final[dict[str, str]] = {
    "action_frequency": "frequency",
    "opportunity_count": "opportunities",
    "sample_size": "opportunities",
    "count": "action_count",
    "profit": "total_profit",
    "ev": "all_in_ev",
    "mean_sizing": "average_sizing",
}

# Filter names whose transport name differs from the engine's.
FILTER_ALIASES: Final[dict[str, str]] = {
    "game_type": "game",
    "tourney": "tournament",
    "blind_level": "big_blind",
    "stake": "big_blind",
    "bet_size_bucket": "sizing_bucket",
    "board_texture_group": "board_suit",
}

# Values that are conventional shorthand in a definition but a different word
# in the stored rows. Whole lists are mapped element by element.
FILTER_VALUE_ALIASES: Final[dict[str, dict[str, str]]] = {
    "pot_type": {
        "srp": "single_raised",
        "single-raised": "single_raised",
        "single-raised-pot": "single_raised",
        "single_raised_pot": "single_raised",
        "3bp": "three_bet",
        "3bet-pot": "three_bet",
        "three_bet_pot": "three_bet",
        "4bp": "four_bet_plus",
        "4bet-plus": "four_bet_plus",
        "four_bet_plus": "four_bet_plus",
        "limped-pot": "limped",
        "unopened-pot": "unopened",
    },
    # ``role`` is the row's role in the current street (who last bet). The
    # *preflop*-aggressor concept is the ``pfr`` / ``pfc`` fragments, not this.
    "role": {
        "pfr": "aggressor",
        "pfc": "defender",
        "caller": "defender",
        "preflop-aggressor": "aggressor",
    },
    "game": {"nlhe": "holdem", "nl-holdem": "holdem", "plo": "omaha"},
}

# Dimension names a definition may use as ``group_by`` entries.
DIMENSION_ALIASES: Final[dict[str, str]] = {
    "dimensions": "dimensions",  # the keyword itself, handled by the parser
    "bet_size_bucket": "sizing_bucket",
    "sizing": "sizing_bucket",
    "board_texture": "board_suit",
    "aggressor": "role",
    "pot": "pot_type",
    "stack": "stack_bucket",
}

# ---------------------------------------------------------------------------
# Reusable named filter fragments.
# ---------------------------------------------------------------------------

# The built-in library. A registry may add more; a definition just names them.
FILTER_FRAGMENTS: Final[dict[str, dict[str, Any]]] = {
    "ring": {"tournament": False},
    "tournament": {"tournament": True},
    "preflop": {"street": "preflop"},
    "flop": {"street": "flop"},
    "turn": {"street": "turn"},
    "river": {"street": "river"},
    "unopened_pot": {"pot_type": "unopened"},
    "limped_pot": {"pot_type": "limped"},
    "single_raised_pot": {"pot_type": "single_raised"},
    "three_bet_pot": {"pot_type": "three_bet"},
    "in_position": {"in_position": True},
    "out_of_position": {"in_position": False},
    "pfr": {"is_preflop_aggressor": True},
    "pfc": {"is_preflop_aggressor": False},
    "facing_3bet": {"situation": "facing_3bet"},
    "facing_4bet": {"situation": "facing_4bet"},
    "facing_cbet": {"situation": "facing_cbet"},
    "facing_raise": {"situation": "facing_raise"},
    "short_stack": {"stack_bucket": "short"},
    "deep_stack": {"stack_bucket": "very_deep"},
}

# ---------------------------------------------------------------------------
# Display metadata.
# ---------------------------------------------------------------------------

VALID_FORMATS: Final[tuple[str, ...]] = ("percentage", "count", "bb", "currency", "decimal", "ratio")

# What "precision" means when the definition does not say: percentages are
# whole, money is to the cent, big blinds and ratios to two decimals.
FORMAT_PRECISION: Final[dict[str, int]] = {
    "percentage": 0,
    "count": 0,
    "bb": 2,
    "currency": 2,
    "decimal": 2,
    "ratio": 2,
}

# The value a format with no data renders, matching StatDescriptor.format.
NO_DATA: Final = "-"


def _localized(value: str | Mapping[str, str], locale: str) -> str:
    """The text for ``locale``, falling back to English then anything."""
    if isinstance(value, str):
        return value
    if locale in value:
        return value[locale]
    if "en" in value:
        return value["en"]
    return next(iter(value.values()), "")


@dataclass(frozen=True)
class DisplaySpec:
    """Presentation only: never affects which rows the metric sees."""

    label: str | Mapping[str, str] = ""
    description: str | Mapping[str, str] = ""
    fmt: str = "decimal"
    precision: int | None = None
    min_sample: int = 0
    category: str = "Custom"
    tags: tuple[str, ...] = ()

    def label_for(self, locale: str = "en") -> str:
        """The label in ``locale``, falling back to English."""
        return _localized(self.label, locale)

    def description_for(self, locale: str = "en") -> str:
        """The description in ``locale``, falling back to English."""
        return _localized(self.description, locale)

    def precision_for(self) -> int:
        """The decimal places to render with."""
        return self.precision if self.precision is not None else FORMAT_PRECISION[self.fmt]

    def has_sample(self, opportunities: int) -> bool:
        """Whether ``opportunities`` clears the definition's minimum sample."""
        return opportunities >= self.min_sample

    def value_of(self, row: QueryRow) -> float | None:
        """The number to display, chosen from the row for this format."""
        if self.fmt == "percentage":
            return None if row.frequency_bp is None else row.frequency_bp / 100.0
        if self.fmt == "count":
            return None if row.value is None else int(row.value)
        return row.value

    def render(self, raw: float | None, big_blind_cents: int | None = None) -> str:
        """Render a raw number the way this format reads."""
        if raw is None:
            return NO_DATA
        places = self.precision_for()
        if self.fmt == "percentage":
            return f"{raw:.{places}f}%"
        if self.fmt == "count":
            return str(int(raw))
        if self.fmt == "currency":
            return f"{raw / 100:.{places}f}"
        if self.fmt == "bb":
            if not big_blind_cents:
                return f"{raw / 100:.{places}f} (chips)"
            return f"{raw / big_blind_cents:.{places}f}"
        return f"{raw:.{places}f}"


# ---------------------------------------------------------------------------
# The definition.
# ---------------------------------------------------------------------------

_SCHEMA_VERSION_FIELD: Final = "schema_version"
_SEMANTIC_FIELDS: Final = ("metric", "filters", "numerator", "group_by", "dimensions", "fragments")
_DISPLAY_FIELDS: Final = ("display", "label", "description", "format", "precision", "min_sample", "category", "tags")
_TOP_LEVEL_FIELDS: Final = ("name", _SCHEMA_VERSION_FIELD, *_SEMANTIC_FIELDS, *_DISPLAY_FIELDS)


@dataclass(frozen=True)
class StatDefinition:
    """One stored stat: what it computes, how it is shown, what it reuses."""

    name: str
    metric: str
    filters: Mapping[str, Any]
    numerator: Mapping[str, Any]
    group_by: tuple[str, ...]
    display: DisplaySpec
    fragments: tuple[str, ...] = ()
    schema_version: int = DEFINITION_SCHEMA_VERSION
    source: str = ""

    def to_query(self, context: Mapping[str, Any] | None = None) -> Query:
        """The engine query this definition compiles to.

        ``context`` is extra filters supplied at call time (a popup's player,
        a research UI's date window). It is merged *over* the definition's
        own filters, so the caller can narrow a stat without editing it.
        """
        filters = dict(self.filters)
        if context:
            filters.update(context)
        return Query(
            metric=self.metric,
            filters=filters,
            numerator=dict(self.numerator),
            group_by=self.group_by,
        )

    def as_dict(self) -> dict[str, Any]:
        """The definition back as data, for round-tripping or display."""
        return {
            "name": self.name,
            "schema_version": self.schema_version,
            "metric": self.metric,
            "filters": dict(self.filters),
            "numerator": dict(self.numerator),
            "group_by": list(self.group_by),
            "fragments": list(self.fragments),
            "display": {
                "label": self.display.label,
                "description": self.display.description,
                "format": self.display.fmt,
                "precision": self.display.precision,
                "min_sample": self.display.min_sample,
                "category": self.display.category,
                "tags": list(self.display.tags),
            },
        }


# ---------------------------------------------------------------------------
# Validation helpers.
# ---------------------------------------------------------------------------


def _fail(message: str, source: str = "") -> NoReturn:
    raise ValueError(f"{source + ': ' if source else ''}{message}")


def _reject_unknown(data: Mapping[str, Any], allowed: Iterable[str], where: str, source: str = "") -> None:
    """Refuse unsupported fields, naming them and what is allowed."""
    unknown = sorted(set(data) - set(allowed))
    if unknown:
        _fail(f"{where}: unsupported field(s) {unknown}; allowed: {sorted(allowed)}", source)


def _resolve_name(
    name: str,
    known: Iterable[str],
    aliases: Mapping[str, str],
    kind: str,
    source: str,
) -> str:
    """Map a friendly name onto a registry name, or explain what is allowed."""
    known_set = set(known)
    if name in known_set:
        return name
    if name in aliases and aliases[name] in known_set:
        return aliases[name]
    _fail(f"unknown {kind} {name!r}; allowed: {sorted(known_set | set(aliases))}", source)
    raise AssertionError  # unreachable: _fail always raises  # pragma: no cover


def resolve_metric(name: str, source: str = "") -> str:
    """The engine metric a definition's ``metric`` names."""
    return _resolve_name(name, KNOWN_METRICS, METRIC_ALIASES, "metric", source)


def _resolve_filter_name(name: str, source: str) -> str:
    return _resolve_name(name, FILTERS, FILTER_ALIASES, "filter", source)


def _resolve_dimension(name: str, source: str) -> str:
    return _resolve_name(name, DIMENSIONS, DIMENSION_ALIASES, "dimension", source)


def _resolve_filter_value(filter_name: str, value: Any, source: str) -> Any:
    """Map shorthand values (``SRP``, ``PFR``) onto the stored words."""
    aliases = FILTER_VALUE_ALIASES.get(filter_name)
    if not aliases:
        return value
    # Shorthand is written in whatever case reads best ("SRP", "PFR"); the
    # alias table is lower-case, so match case-insensitively and keep the
    # original word when it is already the stored one.
    if isinstance(value, (list, tuple)):
        return [aliases.get(str(item).lower(), item) for item in value]
    if isinstance(value, str):
        return aliases.get(value.lower(), value)
    return value


def _validate_filters(filters: Any, where: str, source: str) -> dict[str, Any]:
    if not isinstance(filters, Mapping):
        _fail(f"{where} must be a table/object of filter -> value, got {type(filters).__name__}", source)
    resolved: dict[str, Any] = {}
    for name, value in filters.items():
        engine_name = _resolve_filter_name(str(name), source)
        resolved[engine_name] = _resolve_filter_value(engine_name, value, source)
    return resolved


def _validate_group_by(raw: Any, source: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        _fail("group_by must be a list of dimension names", source)
    return tuple(_resolve_dimension(str(name), source) for name in raw)


def _validate_display(value: str | Mapping[str, Any] | None, where: str, source: str) -> DisplaySpec:
    if value is None:
        return DisplaySpec(label=where)
    if isinstance(value, str):
        return DisplaySpec(label=value)
    if not isinstance(value, Mapping):
        _fail(f"label must be a string or a locale table, got {type(value).__name__}", source)
    for locale, text in value.items():
        if not isinstance(text, str):
            _fail(f"label.{locale} must be a string", source)
    return DisplaySpec(label=dict(value))


def _validate_format(fmt: Any, source: str) -> str:
    if fmt not in VALID_FORMATS:
        _fail(f"unknown format {fmt!r}; allowed: {list(VALID_FORMATS)}", source)
    return str(fmt)


def _validate_precision(precision: Any, source: str) -> int | None:
    if precision is None:
        return None
    if isinstance(precision, bool) or not isinstance(precision, int) or precision < 0:
        _fail("precision must be a non-negative integer", source)
    return precision


def _validate_min_sample(min_sample: Any, source: str) -> int:
    if isinstance(min_sample, bool) or not isinstance(min_sample, int) or min_sample < 0:
        _fail("min_sample must be a non-negative integer", source)
    return min_sample


def _validate_tags(tags: Any, source: str) -> tuple[str, ...]:
    if tags is None:
        return ()
    if not isinstance(tags, (list, tuple)) or not all(isinstance(tag, str) for tag in tags):
        _fail("tags must be a list of strings", source)
    return tuple(tags)


# ---------------------------------------------------------------------------
# Parsing.
# ---------------------------------------------------------------------------


def parse_definition(data: Mapping[str, Any], source: str = "") -> StatDefinition:
    """Validate one raw mapping into a :class:`StatDefinition`.

    Every failure names the field and what is allowed, so a bad definition
    file tells the author what to fix instead of failing later at execution.
    """
    if not isinstance(data, Mapping):
        _fail(f"a definition must be an object, got {type(data).__name__}", source)
    _reject_unknown(data, _TOP_LEVEL_FIELDS, "definition", source)

    name = data.get("name")
    if not isinstance(name, str) or not name:
        _fail("name must be a non-empty string", source)

    schema_version = data.get(_SCHEMA_VERSION_FIELD, DEFINITION_SCHEMA_VERSION)
    if isinstance(schema_version, bool) or not isinstance(schema_version, int) or schema_version < 1:
        _fail(f"{_SCHEMA_VERSION_FIELD} must be a positive integer", source)
    if schema_version > DEFINITION_SCHEMA_VERSION:
        _fail(
            f"definition schema version {schema_version} is newer than supported"
            f" ({DEFINITION_SCHEMA_VERSION}); upgrade fpdb",
            source,
        )

    metric = data.get("metric")
    if not isinstance(metric, str):
        _fail("metric is required", source)
    resolved_metric = resolve_metric(metric, source)

    filters = _validate_filters(data.get("filters", {}), "filters", source)
    numerator = _validate_filters(data.get("numerator", {}), "numerator", source)
    group_by = _validate_group_by(data.get("group_by", data.get("dimensions")), source)

    fragments = data.get("fragments", ())
    if isinstance(fragments, str):
        fragments = [fragments]
    if not isinstance(fragments, (list, tuple)) or not all(isinstance(f, str) for f in fragments):
        _fail("fragments must be a list of names", source)
    fragments = tuple(fragments)

    display_block = data.get("display", {})
    if display_block is None:
        display_block = {}
    if not isinstance(display_block, Mapping):
        _fail("display must be a table/object", source)
    _reject_unknown(display_block, _DISPLAY_FIELDS, "display", source)
    merged = {**display_block, **_display_overrides(data)}
    display = _build_display(name, merged, source)

    return StatDefinition(
        name=name,
        metric=resolved_metric,
        filters=filters,
        numerator=numerator,
        group_by=group_by,
        display=display,
        fragments=fragments,
        schema_version=schema_version,
        source=source,
    )


def _display_overrides(data: Mapping[str, Any]) -> dict[str, Any]:
    """The display fields written at the top level, as a display block."""
    return {key: data[key] for key in _DISPLAY_FIELDS if key != "display" and key in data}


def _build_display(name: str, block: Mapping[str, Any], source: str) -> DisplaySpec:
    fmt = _validate_format(block.get("format", "decimal"), source)
    return DisplaySpec(
        label=_validate_display(block.get("label", name), name, source).label,
        description=_validate_display(block.get("description", ""), "", source).label,
        fmt=fmt,
        precision=_validate_precision(block.get("precision"), source),
        min_sample=_validate_min_sample(block.get("min_sample", 0), source),
        category=str(block.get("category", "Custom")),
        tags=_validate_tags(block.get("tags"), source),
    )


# ---------------------------------------------------------------------------
# Fragments.
# ---------------------------------------------------------------------------


def expand_fragments(
    names: Sequence[str],
    library: Mapping[str, Mapping[str, Any]] | None = None,
    _seen: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Merge named filters, later names overriding earlier ones.

    A fragment may itself reference other fragments through a ``fragments``
    key; a cycle is refused instead of recursing forever.
    """
    sources = FILTER_FRAGMENTS if library is None else library
    merged: dict[str, Any] = {}
    for name in names:
        if name in _seen:
            _fail(f"fragment cycle: {' -> '.join((*_seen, name))}")
        fragment = sources.get(name)
        if fragment is None:
            _fail(f"unknown fragment {name!r}; allowed: {sorted(sources)}")
        nested = fragment.get("fragments", ())
        if nested:
            merged.update(expand_fragments(tuple(nested), sources, (*_seen, name)))
        merged.update({key: value for key, value in fragment.items() if key != "fragments"})
    return merged


def merge_fragments(
    names: Sequence[str],
    filters: Mapping[str, Any],
    library: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """A definition's filters over its fragments: the definition always wins."""
    merged = expand_fragments(names, library)
    merged.update(filters)
    return merged


# ---------------------------------------------------------------------------
# File loading.
# ---------------------------------------------------------------------------

DEFINITION_SUFFIXES: Final = (".json", ".yaml", ".yml")


def _load_text(path: Path) -> Any:
    """Parse a definition document, JSON natively and YAML when available."""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        return json.loads(text)
    if path.suffix in (".yaml", ".yml"):
        try:
            import yaml  # noqa: PLC0415 -- optional dependency, imported on use
        except ModuleNotFoundError as exc:  # pragma: no cover - env-dependent
            raise ValueError(
                f"{path.name}: YAML support requires PyYAML; write the definition as JSON instead",
            ) from exc
        return yaml.safe_load(text)
    raise ValueError(f"{path.name}: unsupported definition suffix {path.suffix!r}")


def _documents(document: Any, path: Path) -> list[Mapping[str, Any]]:
    """The definitions in one document: a list, or a ``{"stats": [...]}`` table."""
    if isinstance(document, Mapping) and "stats" in document:
        document = document["stats"]
    if isinstance(document, Mapping):
        return [document]
    if isinstance(document, list) and all(isinstance(entry, Mapping) for entry in document):
        return list(document)
    raise ValueError(f"{path.name}: expected a definition, a list, or a 'stats' list")


def _check_document_version(document: Any, path: Path) -> None:
    """Refuse a whole file written for a newer schema than this code knows."""
    if not isinstance(document, Mapping):
        return
    if _SCHEMA_VERSION_FIELD not in document:
        return
    version = document[_SCHEMA_VERSION_FIELD]
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        _fail(f"{_SCHEMA_VERSION_FIELD} must be a positive integer", path.name)
    if version > DEFINITION_SCHEMA_VERSION:
        _fail(
            f"definition schema version {version} is newer than supported ({DEFINITION_SCHEMA_VERSION}); upgrade fpdb",
            path.name,
        )


def load_definitions(path: str | Path) -> list[StatDefinition]:
    """Read and validate every definition in one file."""
    path = Path(path)
    document = _load_text(path)
    _check_document_version(document, path)
    return [parse_definition(entry, path.name) for entry in _documents(document, path)]


def load_directory(directory: str | Path) -> list[StatDefinition]:
    """Load every ``*.json``/``*.yaml`` definition directly under ``directory``."""
    directory = Path(directory)
    if not directory.is_dir():
        return []
    definitions: list[StatDefinition] = []
    for path in sorted(directory.iterdir()):
        if path.suffix in DEFINITION_SUFFIXES and path.is_file():
            definitions.extend(load_definitions(path))
    return definitions


# ---------------------------------------------------------------------------
# Registry.
# ---------------------------------------------------------------------------


class DefinitionRegistry:
    """Named definitions plus the fragment library they may reference."""

    def __init__(self, fragments: Mapping[str, Mapping[str, Any]] | None = None) -> None:
        self._by_name: dict[str, StatDefinition] = {}
        self.fragments: dict[str, Mapping[str, Any]] = dict(FILTER_FRAGMENTS)
        if fragments:
            self.fragments.update(fragments)

    def add(self, definition: StatDefinition) -> None:
        """Register one definition, replacing same-named ones."""
        self._by_name[definition.name] = definition

    def get(self, name: str) -> StatDefinition | None:
        return self._by_name.get(name)

    def resolve(self, name: str) -> StatDefinition:
        """The named definition or a ``ValueError`` listing the known names."""
        definition = self._by_name.get(name)
        if definition is None:
            raise ValueError(f"unknown stat definition {name!r}; known: {self.names()}")
        return definition

    def names(self) -> list[str]:
        return sorted(self._by_name)

    def all(self) -> list[StatDefinition]:
        return [self._by_name[name] for name in self.names()]

    def add_fragment(self, name: str, filters: Mapping[str, Any]) -> None:
        """Register a reusable fragment."""
        self.fragments[name] = dict(filters)

    def load(self, definitions: Iterable[StatDefinition]) -> int:
        count = 0
        for definition in definitions:
            self.add(definition)
            count += 1
        return count

    def load_directory(self, directory: str | Path) -> int:
        return self.load(load_directory(directory))

    def __len__(self) -> int:
        return len(self._by_name)

    def __contains__(self, name: object) -> bool:
        return name in self._by_name


def default_definitions_dir() -> Path:
    """The bundled definition library shipped with fpdb."""
    return Path(__file__).resolve().parent / "analytics_definitions.d"


def load_default_registry(extra_dirs: Iterable[str | Path] = ()) -> DefinitionRegistry:
    """Build a registry from the bundled library plus any extra directories."""
    registry = DefinitionRegistry()
    registry.load_directory(default_definitions_dir())
    for extra in extra_dirs:
        registry.load_directory(extra)
    return registry


def get_registry() -> DefinitionRegistry:
    """The shared registry, rebuilt from disk on each call (definitions are data)."""
    return load_default_registry()


# ---------------------------------------------------------------------------
# Compilation, execution and rendering.
# ---------------------------------------------------------------------------


def compile_definition(
    definition: StatDefinition,
    context: Mapping[str, Any] | None = None,
    fragments: Mapping[str, Mapping[str, Any]] | None = None,
    placeholder: str = "%s",
    backend: str = "mysql",
) -> CompiledQuery:
    """Validate and compile a definition without running it.

    Fragments are merged into the filters first, so the compiled SQL is the
    definition's whole meaning and can be inspected.
    """
    return compile_query(_resolved_query(definition, context, fragments), placeholder=placeholder, backend=backend)


def run_definition(
    db: Any,
    definition: StatDefinition,
    context: Mapping[str, Any] | None = None,
    fragments: Mapping[str, Mapping[str, Any]] | None = None,
) -> QueryResult:
    """Compile and execute a definition against a database."""
    query = _resolved_query(definition, context, fragments)
    return run_query(db, query)


def _resolved_query(
    definition: StatDefinition,
    context: Mapping[str, Any] | None = None,
    fragments: Mapping[str, Mapping[str, Any]] | None = None,
) -> Query:
    """The definition as the engine query actually executed: fragments merged in."""
    query = definition.to_query(context)
    return Query(
        metric=query.metric,
        filters=merge_fragments(definition.fragments, query.filters, fragments),
        numerator=query.numerator,
        group_by=query.group_by,
        limit=query.limit,
        offset=query.offset,
    )


def format_row(
    definition: StatDefinition,
    row: QueryRow,
    big_blind_cents: int | None = None,
    locale: str = "en",
) -> str:
    """One result row as the display text, honoring the minimum sample.

    A row below ``min_sample`` renders :data:`NO_DATA` -- a rate on three
    hands is not a number, it is noise, and the definition is where that rule
    belongs.
    """
    if not definition.display.has_sample(row.opportunities):
        return NO_DATA
    return definition.display.render(definition.display.value_of(row), big_blind_cents)


def build_report(
    db: Any,
    definitions: Iterable[StatDefinition],
    context: Mapping[str, Any] | None = None,
    fragments: Mapping[str, Mapping[str, Any]] | None = None,
    big_blind_cents: int | None = None,
    locale: str = "en",
) -> list[dict[str, Any]]:
    """Run definitions and render them as report rows.

    This is the shape a popup or the research UI (#303) consumes: the label
    for the caller's locale, the formatted value, and the sample behind it.
    """
    report: list[dict[str, Any]] = []
    for definition in definitions:
        result = run_definition(db, definition, context, fragments)
        if not result.rows:
            report.append(_report_entry(definition, None, locale, big_blind_cents))
            continue
        for row in result.rows:
            report.append(_report_entry(definition, row, locale, big_blind_cents))
    return report


def _report_entry(
    definition: StatDefinition,
    row: QueryRow | None,
    locale: str,
    big_blind_cents: int | None,
) -> dict[str, Any]:
    """One report line: the localized label, the grouped value and the sample."""
    display = definition.display
    entry: dict[str, Any] = {
        "name": definition.name,
        "label": display.label_for(locale),
        "description": display.description_for(locale),
        "category": display.category,
        "group": dict(row.group) if row is not None else {},
        "value": format_row(definition, row, big_blind_cents, locale) if row is not None else NO_DATA,
        "raw": row.value if row is not None else None,
        "opportunities": row.opportunities if row is not None else 0,
        "actions": row.actions if row is not None else 0,
        "frequency_bp": row.frequency_bp if row is not None else None,
        "unit": row.unit if row is not None else None,
    }
    return entry


__all__ = [
    "DEFINITION_SCHEMA_VERSION",
    "DEFINITION_SUFFIXES",
    "DIMENSION_ALIASES",
    "FILTER_ALIASES",
    "FILTER_FRAGMENTS",
    "FILTER_VALUE_ALIASES",
    "FORMAT_PRECISION",
    "METRIC_ALIASES",
    "NO_DATA",
    "VALID_FORMATS",
    "DefinitionRegistry",
    "DisplaySpec",
    "StatDefinition",
    "build_report",
    "compile_definition",
    "default_definitions_dir",
    "expand_fragments",
    "format_row",
    "get_registry",
    "load_default_registry",
    "load_definitions",
    "load_directory",
    "merge_fragments",
    "parse_definition",
    "resolve_metric",
    "run_definition",
]
