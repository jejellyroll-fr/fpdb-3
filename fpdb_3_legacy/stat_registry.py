"""Declarative, plug-and-play statistic definitions for FPDB-3 Legacy.

Historically a "stat" in FPDB legacy is spread across several imperative layers:
a per-hand computation (``DerivedStats``), a fixed list of pre-aggregated
``HudCache`` columns, a hand-written Python function in ``Stats.py``, and a
hard-coded column/query in each report and graph view. Adding a stat therefore
means editing three or four files.

PokerTracker 4, by contrast, models a stat as a single declarative object: an
aggregation expression over a fact table plus a format and some metadata. That
is what makes a ``.pt4stat`` file droppable.

This module introduces the missing layer: a :class:`StatDescriptor` is the
single source of truth for one statistic, and a :class:`StatRegistry` loads
descriptors from ``stats.d/`` files. Surface-specific *adapters* (HUD, report
grid, graph) consume the same descriptor and compile it to their native shape.

The descriptor's ``value`` is a small arithmetic expression over named input
columns, evaluated by a sandboxed AST walker (no ``eval``). Loading a descriptor
whose expression references a column that does not exist is refused at load
time, which gives the PT4 importer a clean Tier-2/Tier-3 boundary: if every
input maps onto an existing FPDB column the stat is plug-and-play; otherwise the
importer reports it instead of silently producing a broken stat.
"""

from __future__ import annotations

import ast
import json
import operator
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

try:  # Python 3.11+
    import tomllib as _toml
except ModuleNotFoundError:  # pragma: no cover - exercised only on <3.11
    try:
        import tomli as _toml  # type: ignore[no-redef]
    except ModuleNotFoundError:  # pragma: no cover
        _toml = None  # type: ignore[assignment]

from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("stat_registry")

# --------------------------------------------------------------------------- #
# Vocabulary shared with the descriptor schema.
# --------------------------------------------------------------------------- #

VALID_SCOPES = frozenset({"ring", "tour"})
VALID_AGGREGATES = frozenset({"ratio", "sum", "avg", "last", "none"})
VALID_SERIES = frozenset({"cumulative"})
VALID_DIMENSION_KEYS = frozenset({"seats", "position"})

DESCRIPTOR_SUFFIXES = (".toml", ".json")


class StatDescriptorError(ValueError):
    """Raised when a descriptor is malformed and must be rejected."""


# --------------------------------------------------------------------------- #
# Sandboxed expression evaluator.
# --------------------------------------------------------------------------- #

# Binary / unary operators allowed inside a descriptor ``value`` expression.
_BIN_OPS: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS: dict[type[ast.unaryop], Callable[[Any], Any]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}
# A short, side-effect-free function whitelist. ``coalesce`` mirrors the PT4
# idiom of substituting a default for a missing/zero value.
_ALLOWED_FUNCS: dict[str, Callable[..., Any]] = {
    "min": min,
    "max": max,
    "abs": abs,
    "round": round,
    "coalesce": lambda *args: next((a for a in args if a), args[-1] if args else 0),
}


class SafeExpression:
    """A compiled, sandboxed arithmetic expression over named variables.

    Only numeric literals, the variable names supplied at compile time, the
    whitelisted operators above, and the whitelisted functions are permitted.
    Anything else (attribute access, calls to unknown names, comprehensions,
    lambdas, etc.) raises :class:`StatDescriptorError` at compile time, so an
    untrusted descriptor file can never execute arbitrary code.
    """

    def __init__(self, source: str, allowed_names: frozenset[str]) -> None:
        self.source = source
        self.allowed_names = allowed_names
        try:
            self._tree = ast.parse(source, mode="eval")
        except SyntaxError as exc:  # pragma: no cover - defensive
            raise StatDescriptorError(f"invalid expression {source!r}: {exc}") from exc
        self.referenced_names = self._validate(self._tree.body)

    def _validate(self, node: ast.AST) -> frozenset[str]:
        """Walk the tree, reject anything outside the sandbox, collect names."""
        names: set[str] = set()

        def walk(n: ast.AST) -> None:
            if isinstance(n, ast.BinOp):
                if type(n.op) not in _BIN_OPS:
                    raise StatDescriptorError(f"operator {type(n.op).__name__} not allowed")
                walk(n.left)
                walk(n.right)
            elif isinstance(n, ast.UnaryOp):
                if type(n.op) not in _UNARY_OPS:
                    raise StatDescriptorError(f"unary {type(n.op).__name__} not allowed")
                walk(n.operand)
            elif isinstance(n, ast.Constant):
                if not isinstance(n.value, (int, float)) or isinstance(n.value, bool):
                    raise StatDescriptorError(f"literal {n.value!r} not allowed")
            elif isinstance(n, ast.Name):
                if n.id in _ALLOWED_FUNCS:
                    return
                if n.id not in self.allowed_names:
                    raise StatDescriptorError(
                        f"unknown name {n.id!r}; allowed inputs: {sorted(self.allowed_names)}",
                    )
                names.add(n.id)
            elif isinstance(n, ast.Call):
                if not isinstance(n.func, ast.Name) or n.func.id not in _ALLOWED_FUNCS:
                    raise StatDescriptorError("only whitelisted function calls are allowed")
                for arg in n.args:
                    walk(arg)
                if n.keywords:
                    raise StatDescriptorError("keyword arguments are not allowed")
            else:
                raise StatDescriptorError(f"syntax element {type(n).__name__} not allowed")

        walk(node)
        return frozenset(names)

    def evaluate(self, variables: Mapping[str, Any]) -> float | None:
        """Evaluate against ``variables``; return ``None`` on division by zero.

        Returning ``None`` (rather than raising) lets callers render a
        "no data" placeholder when a denominator is zero, matching how the
        legacy stat functions degrade.
        """
        try:
            return self._eval(self._tree.body, variables)
        except ZeroDivisionError:
            return None

    def _eval(self, node: ast.AST, variables: Mapping[str, Any]) -> Any:
        if isinstance(node, ast.BinOp):
            return _BIN_OPS[type(node.op)](
                self._eval(node.left, variables),
                self._eval(node.right, variables),
            )
        if isinstance(node, ast.UnaryOp):
            return _UNARY_OPS[type(node.op)](self._eval(node.operand, variables))
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id in _ALLOWED_FUNCS:
                return _ALLOWED_FUNCS[node.id]
            value = variables.get(node.id, 0)
            return value if value is not None else 0
        if isinstance(node, ast.Call):
            func = _ALLOWED_FUNCS[node.func.id]  # type: ignore[attr-defined]
            return func(*[self._eval(a, variables) for a in node.args])
        raise StatDescriptorError(f"cannot evaluate {type(node).__name__}")  # pragma: no cover


# --------------------------------------------------------------------------- #
# Descriptor.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class StatDescriptor:
    """A single, surface-agnostic statistic definition.

    Attributes:
        name: Unique identifier (also the report column / HUD stat name).
        label: Human-readable title (tooltips, legends, column headers).
        inputs: Fact columns the stat reads (must exist in the data source).
        value: Arithmetic expression over ``inputs`` producing the raw number.
        scope: Where the stat applies — any of ``{"ring", "tour"}``.
        category: Grouping label (e.g. "Tournament / ChipEV").
        dimension: Optional ``{"seats": int, "position": str|int}`` filter. Used
            by the grid/graph adapters to emit ``CASE WHEN`` predicates.
        aggregate: How rows combine — ``ratio``/``sum``/``avg``/``last``/``none``.
        series: ``"cumulative"`` to expose the stat as a graph curve, else None.
        context: Inputs supplied by the surrounding query (e.g. ``cnt_tourneys``)
            rather than aggregated from the dimensioned fact rows. A subset of
            ``inputs``; the grid adapter does not emit ``SUM(CASE WHEN ...)`` for
            these.
        fmt: printf-style format string for display.
        description: Optional long description (tooltip / docs).
    """

    name: str
    label: str
    inputs: tuple[str, ...]
    value: str
    scope: tuple[str, ...] = ("ring", "tour")
    category: str = "Custom"
    dimension: Mapping[str, int | str] | None = None
    aggregate: str = "ratio"
    series: str | None = None
    context: tuple[str, ...] = ()
    fmt: str = "%s"
    description: str = ""
    expression: SafeExpression = field(repr=False, compare=False, default=None)  # type: ignore[assignment]

    def fact_inputs(self) -> tuple[str, ...]:
        """Inputs that must be aggregated from the fact source (not context)."""
        return tuple(c for c in self.inputs if c not in self.context)

    def applies_to(self, game_type: str) -> bool:
        """Whether this stat is meaningful for ``"ring"`` or ``"tour"`` play."""
        return game_type in self.scope

    def compute(self, columns: Mapping[str, Any]) -> float | None:
        """Evaluate the raw value from a mapping of input column -> number."""
        return self.expression.evaluate(columns)

    def format(self, raw: float | None) -> str:
        """Render the raw value with ``fmt``; ``None`` becomes a placeholder."""
        if raw is None:
            return "-"
        try:
            return self.fmt % raw
        except (TypeError, ValueError):
            return str(raw)


# --------------------------------------------------------------------------- #
# Validation / construction.
# --------------------------------------------------------------------------- #


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise StatDescriptorError(message)


def build_descriptor(data: Mapping[str, Any]) -> StatDescriptor:
    """Validate a raw mapping (parsed from a file) into a :class:`StatDescriptor`.

    Raises :class:`StatDescriptorError` with a precise message for any schema
    violation so the registry can log-and-skip a single bad file without
    affecting the others.
    """
    name = data.get("name")
    _require(isinstance(name, str) and name.isidentifier(), f"name must be an identifier, got {name!r}")
    name = cast(str, name)

    label = data.get("label", name)
    _require(isinstance(label, str), "label must be a string")
    label = cast(str, label)

    inputs = data.get("inputs")
    _require(
        isinstance(inputs, (list, tuple))
        and len(inputs) > 0
        and all(isinstance(c, str) and c.isidentifier() for c in inputs),
        "inputs must be a non-empty list of column identifiers",
    )
    inputs = tuple(cast(list[str] | tuple[str, ...], inputs))

    value = data.get("value")
    _require(isinstance(value, str) and value.strip() != "", "value expression is required")
    value = cast(str, value)

    # Compile + sandbox-check the expression against the declared inputs. This
    # is where an expression referencing a non-existent column is rejected.
    expression = SafeExpression(value, frozenset(inputs))
    unused = set(inputs) - set(expression.referenced_names)
    if unused:
        log.warning("descriptor %s declares unused inputs: %s", name, sorted(unused))

    raw_scope = data.get("scope", ("ring", "tour"))
    _require(isinstance(raw_scope, (list, tuple)), "scope must be a list of game types")
    scope = tuple(cast(list[str] | tuple[str, ...], raw_scope))
    _require(
        len(scope) > 0 and all(s in VALID_SCOPES for s in scope),
        f"scope must be a subset of {sorted(VALID_SCOPES)}",
    )

    aggregate = data.get("aggregate", "ratio")
    _require(aggregate in VALID_AGGREGATES, f"aggregate must be one of {sorted(VALID_AGGREGATES)}")

    series = data.get("series")
    _require(series is None or series in VALID_SERIES, f"series must be null or one of {sorted(VALID_SERIES)}")

    dimension = data.get("dimension")
    if dimension is not None:
        _require(isinstance(dimension, Mapping), "dimension must be a table/object")
        bad = set(dimension) - VALID_DIMENSION_KEYS
        _require(not bad, f"unknown dimension keys {sorted(bad)}; allowed: {sorted(VALID_DIMENSION_KEYS)}")
        if "seats" in dimension:
            _require(isinstance(dimension["seats"], int), "dimension.seats must be an integer")
        if "position" in dimension:
            _require(isinstance(dimension["position"], (int, str)), "dimension.position must be int or str")
        dimension = dict(dimension)

    raw_context = data.get("context", ())
    _require(isinstance(raw_context, (list, tuple)), "context must be a list of input names")
    context = tuple(cast(list[str] | tuple[str, ...], raw_context))
    _require(
        all(isinstance(c, str) for c in context) and set(context) <= set(inputs),
        "context must be a subset of inputs",
    )

    fmt = data.get("format", "%s")
    _require(isinstance(fmt, str), "format must be a string")
    fmt = cast(str, fmt)

    return StatDescriptor(
        name=name,
        label=label,
        inputs=inputs,
        value=value,
        scope=scope,
        category=str(data.get("category", "Custom")),
        dimension=dimension,
        aggregate=aggregate,
        series=series,
        context=context,
        fmt=fmt,
        description=str(data.get("description", "")),
        expression=expression,
    )


# --------------------------------------------------------------------------- #
# File loading.
# --------------------------------------------------------------------------- #


def _load_file(path: Path) -> list[Mapping[str, Any]]:
    """Parse one descriptor file into a list of raw stat mappings.

    Both layouts are accepted: a single ``[stat]`` table, or a top-level
    ``[[stat]]`` array of tables (TOML) / ``{"stats": [...]}`` (JSON).
    """
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        doc = json.loads(text)
    elif path.suffix == ".toml":
        if _toml is None:  # pragma: no cover
            raise StatDescriptorError("TOML support unavailable (install tomli on Python < 3.11)")
        doc = _toml.loads(text)
    else:  # pragma: no cover - filtered by caller
        raise StatDescriptorError(f"unsupported descriptor suffix {path.suffix!r}")

    if "stats" in doc:
        return list(doc["stats"])
    stat = doc.get("stat")
    if isinstance(stat, list):
        return list(stat)
    if isinstance(stat, Mapping):
        return [stat]
    raise StatDescriptorError(f"{path.name}: expected a [stat] table or a 'stats' array")


# --------------------------------------------------------------------------- #
# Registry.
# --------------------------------------------------------------------------- #


class StatRegistry:
    """Holds all descriptor-defined stats and answers surface queries.

    The registry is intentionally additive: it coexists with the ~600 native
    Python stat functions in ``Stats.py`` (which remain the implementation for
    everything it does not define). Adapters merge :meth:`names` with the
    legacy ``STATLIST``.
    """

    def __init__(self) -> None:
        self._by_name: dict[str, StatDescriptor] = {}

    # -- population -------------------------------------------------------- #

    def add(self, descriptor: StatDescriptor) -> None:
        if descriptor.name in self._by_name:
            log.warning("duplicate stat descriptor %r; overriding previous definition", descriptor.name)
        self._by_name[descriptor.name] = descriptor

    def load_directory(self, directory: str | Path) -> int:
        """Load every ``*.toml``/``*.json`` descriptor under ``directory``.

        A malformed file is logged and skipped; it never aborts the load.
        Returns the number of descriptors successfully registered.
        """
        directory = Path(directory)
        if not directory.is_dir():
            log.info("stat descriptor directory %s does not exist; skipping", directory)
            return 0

        loaded = 0
        for path in sorted(directory.iterdir()):
            if path.suffix not in DESCRIPTOR_SUFFIXES or not path.is_file():
                continue
            try:
                for raw in _load_file(path):
                    self.add(build_descriptor(raw))
                    loaded += 1
            except (StatDescriptorError, ValueError, OSError) as exc:
                log.error("skipping stat descriptor file %s: %s", path.name, exc)
        log.info("loaded %d stat descriptor(s) from %s", loaded, directory)
        return loaded

    # -- queries ----------------------------------------------------------- #

    def get(self, name: str) -> StatDescriptor | None:
        return self._by_name.get(name)

    def names(self) -> list[str]:
        return sorted(self._by_name)

    def all(self) -> list[StatDescriptor]:
        return [self._by_name[n] for n in self.names()]

    def for_scope(self, game_type: str) -> list[StatDescriptor]:
        return [d for d in self.all() if d.applies_to(game_type)]

    def series_for_scope(self, game_type: str) -> list[StatDescriptor]:
        """Descriptors that should be drawn as graph curves for ``game_type``."""
        return [d for d in self.for_scope(game_type) if d.series == "cumulative"]

    def __len__(self) -> int:
        return len(self._by_name)

    def __contains__(self, name: object) -> bool:
        return name in self._by_name


# A module-level default registry. The application populates it once at startup
# via :func:`load_default_registry`; adapters import and read it.
_DEFAULT_REGISTRY: StatRegistry | None = None


def default_stats_dir() -> Path:
    """Location of the bundled descriptor directory (``fpdb_3_legacy/stats.d``)."""
    return Path(__file__).resolve().parent / "stats.d"


def load_default_registry(extra_dirs: tuple[str | Path, ...] = ()) -> StatRegistry:
    """Build (once) and return the shared registry from ``stats.d`` + extras."""
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        registry = StatRegistry()
        registry.load_directory(default_stats_dir())
        for extra in extra_dirs:
            registry.load_directory(extra)
        _DEFAULT_REGISTRY = registry
    return _DEFAULT_REGISTRY


def get_registry() -> StatRegistry:
    """Return the shared registry, loading it on first use."""
    return load_default_registry()


def reload_default_registry() -> StatRegistry:
    """Discard and rebuild the shared registry (e.g. after importing new stats)."""
    global _DEFAULT_REGISTRY
    _DEFAULT_REGISTRY = None
    return load_default_registry()
