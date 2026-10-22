"""Translate PokerTracker 4 ``.pt4stat`` files into FPDB stat descriptors.

A ``.pt4stat`` is PT4's serialized custom-statistic definition: a category, a
set of referenced columns each with its own SQL, a display title, a value
expression, and a ``format_number(...)`` format. The binary uses big-endian,
length-prefixed UTF-16 strings, so the readable fields can be recovered without
fully reversing the container.

This module:

1. :func:`decode_pt4stat` — extract the structured fields from the binary.
2. :func:`translate` — map a decoded stat onto a :class:`StatDescriptor` data
   dict, recognising the PT4 idioms we support and **reporting** (never
   silently mistranslating) the ones we do not. That report is the Tier-2 /
   Tier-3 boundary: if every referenced column maps onto an existing FPDB
   column the stat is plug-and-play; otherwise it needs new derived data.
3. :func:`emit_toml` / :func:`import_directory` — write descriptor files.

Only the tournament ChipEV idioms exercised by the bundled ChipEV-by-position
pack are supported today; everything else is returned as an unsupported report.
"""

from __future__ import annotations

import functools
import json
import re
import struct
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:  # Python 3.11+
    import tomllib as _toml
except ModuleNotFoundError:  # pragma: no cover - exercised only on <3.11
    try:
        import tomli as _toml  # type: ignore[no-redef]
    except ModuleNotFoundError:  # pragma: no cover
        _toml = None  # type: ignore[assignment]

from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("pt4_import")

# --------------------------------------------------------------------------- #
# PT4 -> FPDB legacy translation tables.
# --------------------------------------------------------------------------- #

# PT4 fact column -> (FPDB legacy HandsPlayers column, scale factor). The bulk
# is data-driven from pt4_mapping.d/pt4_legacy_mapping.json (a dedicated PT4 -> legacy
# table, distinct from the modern/Rust pt4_statistics_mapping.json); this
# built-in entry is the always-present fallback. FPDB stores money/chips as
# integer * 100, hence scale 100.
_BUILTIN_COLUMN_MAP: dict[str, tuple[str, float]] = {
    "amt_expected_won": ("allInEV", 100.0),
}


def _legacy_mapping_path() -> Path:
    # Inside the package, like every shipped definition library (*.d): docs/ is in
    # no release artifact, and a missing map leaves every stat unsupported (#622).
    return Path(__file__).resolve().parent / "pt4_mapping.d" / "pt4_legacy_mapping.json"


def load_column_map() -> dict[str, tuple[str, float]]:
    """Build the PT4 -> legacy column map from the JSON file + built-in fallback."""
    mapping = dict(_BUILTIN_COLUMN_MAP)
    path = _legacy_mapping_path()
    try:
        if path.exists():
            doc = json.loads(path.read_text(encoding="utf-8"))
            for pt4_col, spec in doc.get("columns", {}).items():
                # Skip documentation keys ("_note...") and any non-object value.
                if pt4_col.startswith("_") or not isinstance(spec, dict):
                    continue
                mapping[pt4_col] = (spec["fpdb"], float(spec.get("scale", 1)))
    except Exception:  # pragma: no cover - corrupt/missing file: keep fallback
        log.exception("could not load %s; using built-in PT4 column map", path)
    return mapping


PT4_COLUMN_MAP: dict[str, tuple[str, float]] = load_column_map()


def _load_section(section: str) -> dict[str, dict[str, str]]:
    """One of the mapping file's other sections (#613), documentation keys dropped."""
    try:
        doc = json.loads(_legacy_mapping_path().read_text(encoding="utf-8"))
    except Exception:  # pragma: no cover - corrupt/missing file: no extra idioms
        log.exception("could not read the %s section of the PT4 mapping", section)
        return {}
    entries = doc.get(section, {})
    return {key: spec for key, spec in entries.items() if not key.startswith("_") and isinstance(spec, dict)}


# sum(if[<condition>, 1, 0]) with a condition richer than one flag -> FPDB column or sum of columns.
PT4_CONDITION_MAP: dict[str, dict[str, str]] = _load_section("conditions")
# PT4 column name -> FPDB column under another definition, used when its SQL does not translate.
PT4_NAMED_COLUMNS: dict[str, dict[str, str]] = _load_section("named_columns")
# PT4 sub-expression of a value expression -> FPDB column under another definition.
PT4_EXPRESSION_ALIASES: dict[str, dict[str, str]] = _load_section("expressions")

# PT4 aggregate column SQL -> FPDB context input supplied by the query.
PT4_CONTEXT_MAP: dict[str, str] = {
    "count(distinct tourney_summary.id_tourney)": "cnt_tourneys",
}

# PT4 numeric position code -> FPDB logical position (HandsPlayers encoding).
PT4_POSITION_MAP: dict[int, Any] = {
    0: 0,  # Button
    8: "B",  # Big blind
    9: "S",  # Small blind
}

# Tables that mark a stat as tournament-scoped.
TOURNAMENT_TABLES = ("tourney_hand_player_statistics", "tourney_summary")


class PT4TranslationError(ValueError):
    """A decoded PT4 stat uses an idiom this translator does not support."""


# --------------------------------------------------------------------------- #
# Decoding.
# --------------------------------------------------------------------------- #


def _is_clean_latin(text: str) -> bool:
    """Whether every char is newline or printable Latin (ord < 0x250).

    PT4 stat names/SQL/descriptions are English/Spanish/French/Polish — all
    Latin. A candidate containing CJK or other high code points means the
    length-prefix scanner mis-aligned on marker bytes (e.g. ``<i``/``<s`` tags
    decoded as UTF-16BE), so we reject it and let the scanner re-sync.
    """
    return all(c == "\n" or (c.isprintable() and ord(c) < 0x250) for c in text)


def _extract_strings(data: bytes, max_len: int = 4000) -> list[str]:
    """Recover big-endian, length-prefixed UTF-16 strings from the container."""
    out: list[str] = []
    i, n = 0, len(data)
    while i + 4 <= n:
        length = struct.unpack(">I", data[i : i + 4])[0]
        if 0 < length < max_len and i + 4 + 2 * length <= n:
            raw = data[i + 4 : i + 4 + 2 * length]
            try:
                text = raw.decode("utf-16-be")
            except UnicodeDecodeError:
                text = ""
            if text and _is_clean_latin(text):
                out.append(text)
                i += 4 + 2 * length
                continue
        i += 1
    return out


def _looks_like_sql(text: str) -> bool:
    return "(" in text and any(fn in text.lower() for fn in ("sum", "count", "if[", "avg", "min", "max"))


def _is_identifier(text: str) -> bool:
    return bool(re.fullmatch(r"[a-z][a-z0-9_]*", text))


# A printf-style PT4 format directive, e.g. '%.2f', '/%.2f', '%d', '%5.1f%%'.
_PRINTF_RE = re.compile(r"^/?%[#0\- +]*[.\d]*[diouxXeEfFgGs]%*$")


def _find_format_index(strings: list[str]) -> int:
    """Index of the first format directive (format_number(...) or printf-style)."""
    for idx, text in enumerate(strings):
        stripped = text.strip()
        if stripped.startswith("format_number") or _PRINTF_RE.match(stripped):
            return idx
    return -1


@dataclass
class DecodedStat:
    """The fields recovered from a ``.pt4stat`` file."""

    path: Path
    columns: dict[str, str] = field(default_factory=dict)  # column name -> SQL
    value_expr: str = ""
    decimals: int = 2
    label: str = ""
    description: str = ""
    strings: list[str] = field(default_factory=list)
    category: str = ""  # PT4's stat category, e.g. "Cash Player", when known


def decode_pt4stat(path: str | Path) -> DecodedStat:
    """Decode one ``.pt4stat`` file into a :class:`DecodedStat`."""
    path = Path(path)
    strings = _extract_strings(path.read_bytes())
    decoded = DecodedStat(path=path, strings=strings)

    # Referenced columns: an identifier immediately followed by its SQL.
    for first, second in zip(strings, strings[1:], strict=False):
        if _is_identifier(first) and _looks_like_sql(second):
            decoded.columns.setdefault(first, second)

    # The value expression sits just before a format directive. PT4 uses two
    # styles: format_number(<expr>, <decimals>, ...) which embeds the expr, and
    # a printf-style string ('%.2f', '/%.2f', '%d', ...) for which the expr is
    # the preceding string.
    idx = _find_format_index(strings)
    if idx >= 0:
        text = strings[idx]
        fn = re.match(r"\s*format_number\s*\(\s*(.+?)\s*,\s*(\d+)\s*,", text, re.DOTALL)
        if fn:
            decoded.value_expr = fn.group(1).strip()
            decoded.decimals = int(fn.group(2))
        else:
            decoded.value_expr = strings[idx - 1].strip() if idx > 0 else ""
            mdec = re.search(r"%[#0\- +]*\.(\d+)[feEgG]", text)
            decoded.decimals = int(mdec.group(1)) if mdec else 0
        # Display title: the first of the human label run before the value expr.
        decoded.label = _title_before(strings, idx)

    # Longest non-SQL string is the human description.
    non_sql = [s for s in strings if not _looks_like_sql(s) and not _is_identifier(s)]
    if non_sql:
        decoded.description = max(non_sql, key=len).split("\n")[0].strip()

    return decoded


# The stat categories PT4 groups its definitions under; a stat of a player category
# is computed per player, which is what an FPDB descriptor is.
PLAYER_CATEGORIES = ("Cash Player", "Tournament Player")
_DEFINITION_CATEGORIES = frozenset(
    {*PLAYER_CATEGORIES, "Cash Hand", "Tournament Hand", "Cash Sessions", "Tournament Tournaments"}
)
# How PT4 aggregates a column definition; a stat record has a title where a column has one of these.
_COLUMN_AGGREGATIONS = frozenset({"Sum", "Count", "Count Unique", "Average", "Copy", "Max", "Min", "Append"})


def _decimals(display: str) -> int:
    """Decimal places of a PT4 display expression (``/%.2f`` or ``format_number(x, 2, ...)``)."""
    fn = re.search(r"format_number\s*\(.+?,\s*(\d+)\s*,", display, re.DOTALL)
    if fn:
        return int(fn.group(1))
    printf = re.search(r"%[#0\- +]*\.(\d+)[feEgG]", display)
    return int(printf.group(1)) if printf else 2


def read_stat_definitions(path: str | Path) -> list[DecodedStat]:
    """The stats PokerTracker 4 ships, read from its ``StatDefinitions.pt4`` (#613).

    The file sits in the PT4 install (``Data/Stats/StatDefinitions.pt4``, inside
    ``PokerTracker 4.app/Contents/Resources`` on macOS). It is the same
    length-prefixed UTF-16 container as a ``.pt4stat``, holding every column
    definition -- category, name, SQL, aggregation, description -- and every
    stat -- category, title, long title, short title, value expression, display
    expression, description. Each player stat comes back as a
    :class:`DecodedStat` whose columns are the definitions it references.
    """
    path = Path(path)
    strings = _extract_strings(path.read_bytes(), max_len=20000)
    columns: dict[str, dict[str, str]] = {}
    records: list[int] = []
    for i in range(len(strings) - 7):
        category, name = strings[i], strings[i + 1]
        if category not in _DEFINITION_CATEGORIES:
            continue
        if _is_identifier(name) and strings[i + 3] in _COLUMN_AGGREGATIONS:
            columns.setdefault(category, {}).setdefault(name, strings[i + 2])
        elif category in PLAYER_CATEGORIES and not _is_identifier(name) and name not in _DEFINITION_CATEGORIES:
            records.append(i)

    stats = []
    for i in records:
        category, title, value_expr, display = strings[i], strings[i + 1], strings[i + 4], strings[i + 5]
        defined = columns.get(category, {})
        referenced = {n: defined[n] for n in _IDENTIFIER_RE.findall(value_expr) if n in defined}
        description = next(
            (text for text in strings[i + 6 : i + 9] if text not in (display, value_expr) and len(text) > 20), ""
        )
        stats.append(
            DecodedStat(
                path=path,
                columns=referenced,
                value_expr=value_expr.strip(),
                decimals=_decimals(display),
                label=title,
                description=description.split("\n")[0].strip(),
                category=category,
            )
        )
    return stats


def _title_before(strings: list[str], format_idx: int) -> str:
    """Best-effort display title: the label sitting just before the value expr.

    strings[format_idx-1] is the value-expression string and the title cluster
    sits immediately before it. Return the *closest* qualifying display string
    (single line, not SQL/identifier/stopword) and stop — walking further back
    would reach the column description.
    """
    stop = {"Sum", "Information", "Comprehensive", "Tournament Player"}
    run: list[str] = []
    for j in range(format_idx - 2, -1, -1):
        s = strings[j]
        if "\n" in s or _looks_like_sql(s) or _is_identifier(s) or s in stop:
            if run:
                break  # reached the boundary of the title cluster
            continue
        if 0 < len(s) < 60:
            run.append(s)
    # ``run`` is filled walking backward, so its last element is the first title
    # in document order (the canonical, non-localised variant).
    return run[-1] if run else ""


# --------------------------------------------------------------------------- #
# Translation.
# --------------------------------------------------------------------------- #

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(text: str) -> str:
    slug = _SLUG_RE.sub("_", text.strip().lower()).strip("_")
    if slug and slug[0].isdigit():
        slug = "stat_" + slug
    return slug or "pt4_stat"


# sum(if[<t>.position=P AND <t>.cnt_players=C, <t>.<col>, 0])
_SUM_IF_RE = re.compile(
    r"sum\(\s*if\[\s*\w+\.position\s*=\s*(\d+)\s*AND\s*\w+\.cnt_players\s*=\s*(\d+)\s*,\s*\w+\.(\w+)\s*,\s*0\s*\]\s*\)",
    re.IGNORECASE | re.DOTALL,
)
# sum(if[<t>.<col>, 1, 0]) — count of a single boolean flag (no dimension).
_SUM_IF_FLAG_RE = re.compile(
    r"sum\(\s*if\[\s*\w+\.(\w+)\s*,\s*1\s*,\s*0\s*\]\s*\)",
    re.IGNORECASE | re.DOTALL,
)
# sum(<t>.<col>)
_SUM_RE = re.compile(r"sum\(\s*\w+\.(\w+)\s*\)", re.IGNORECASE)
# sum(if[<condition>, 1, 0]) — a count over any condition (#613).
_SUM_IF_COND_RE = re.compile(
    r"^\s*sum\(\s*if\[\s*(?P<cond>.+?)\s*,\s*1\s*,\s*0\s*\]\s*\)\s*$", re.IGNORECASE | re.DOTALL
)
_IDENTIFIER_RE = re.compile(r"[A-Za-z_]\w*")


def _normalise_condition(condition: str) -> str:
    """A condition as the mapping keys it: table prefixes dropped, single spaces around comparisons."""
    text = re.sub(r"\b[A-Za-z_]\w*\.(?=[A-Za-z_])", "", condition)
    text = re.sub(r"\s*(<=|>=|!=|=|<|>)\s*", r" \1 ", text)
    return re.sub(r"\s+", " ", text).strip()


def _inputs_of(fpdb_expr: str) -> list[str]:
    """The FPDB columns an FPDB target names, in order (a column, or a sum such as ``a + b``)."""
    return list(dict.fromkeys(_IDENTIFIER_RE.findall(fpdb_expr)))


@functools.lru_cache(maxsize=1)
def _boolean_columns() -> frozenset[str]:
    """HandsPlayers columns stored as SQL booleans, read from the PostgreSQL DDL.

    Whether an input is boolean follows how FPDB stores it, not the shape of the
    PT4 SQL: a PT4 count of flagged hands can land on an integer FPDB count
    (street1Bets), and summing a boolean needs ``CASE WHEN`` on PostgreSQL while
    ``CASE WHEN`` on an integer is an error there.
    """
    from fpdb_3_legacy.sql_schema_hand_player import hand_player_schema_queries

    ddl = hand_player_schema_queries("postgresql")["createHandsPlayersTable"]
    return frozenset(re.findall(r"^\s*(\w+)\s+BOOLEAN\b", ddl, re.MULTILINE))


def _booleans(inputs: list[str]) -> list[str]:
    """The inputs FPDB stores as booleans, in order."""
    booleans = _boolean_columns()
    return [name for name in dict.fromkeys(inputs) if name in booleans]


@dataclass
class TranslatedStat:
    """Outcome of translating one PT4 stat."""

    descriptor: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)
    # Where the FPDB stat is defined differently from PT4's: translated, but not identical.
    notes: list[str] = field(default_factory=list)

    @property
    def supported(self) -> bool:
        return self.descriptor is not None


def _resolve_fact(col_sql: str) -> tuple[str, dict[str, Any] | None, float]:
    """Resolve one column's SQL to (fpdb_input, dimension, scale).

    Raises :class:`PT4TranslationError` for unsupported column SQL.
    """
    m = _SUM_IF_RE.search(col_sql)
    if m:
        position_code, seats, pt4_col = int(m.group(1)), int(m.group(2)), m.group(3)
        if pt4_col not in PT4_COLUMN_MAP:
            raise PT4TranslationError(f"unmapped PT4 column {pt4_col!r}")
        if position_code not in PT4_POSITION_MAP:
            raise PT4TranslationError(f"unmapped PT4 position code {position_code}")
        fpdb_col, scale = PT4_COLUMN_MAP[pt4_col]
        dimension = {"seats": seats, "position": PT4_POSITION_MAP[position_code]}
        return fpdb_col, dimension, scale

    m = _SUM_IF_FLAG_RE.search(col_sql)
    if m:
        pt4_col = m.group(1)
        if pt4_col not in PT4_COLUMN_MAP:
            raise PT4TranslationError(f"unmapped PT4 column {pt4_col!r}")
        fpdb_col, scale = PT4_COLUMN_MAP[pt4_col]
        return fpdb_col, None, scale

    m = _SUM_IF_COND_RE.match(col_sql)
    if m:
        condition = _normalise_condition(m.group("cond"))
        spec = PT4_CONDITION_MAP.get(condition)
        if spec is None:
            raise PT4TranslationError(f"unmapped PT4 condition {condition!r}")
        return spec["fpdb"], None, 1.0

    m = _SUM_RE.search(col_sql)
    if m:
        pt4_col = m.group(1)
        if pt4_col not in PT4_COLUMN_MAP:
            raise PT4TranslationError(f"unmapped PT4 column {pt4_col!r}")
        fpdb_col, scale = PT4_COLUMN_MAP[pt4_col]
        return fpdb_col, None, scale

    raise PT4TranslationError(f"unsupported column SQL: {col_sql.strip()[:80]}")


def _apply_expression_aliases(expr: str) -> tuple[str, list[str], list[str]]:
    """Replace the PT4 sub-expressions FPDB answers with one column: ``(expr, fpdb inputs, notes)``."""
    inputs: list[str] = []
    notes: list[str] = []
    for alias, spec in PT4_EXPRESSION_ALIASES.items():
        pattern = r"\s*".join(re.escape(token) for token in alias.split())
        if re.search(pattern, expr):
            expr = re.sub(pattern, spec["fpdb"], expr)
            inputs.extend(_inputs_of(spec["fpdb"]))
            if spec.get("note"):
                notes.append(spec["note"])
    return expr, inputs, notes


@dataclass
class _Resolved:
    """The referenced PT4 columns of an expression, resolved to FPDB inputs."""

    facts: dict[str, tuple[str, dict[str, Any] | None, float]] = field(default_factory=dict)
    context: dict[str, str] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _resolve_columns(decoded: DecodedStat, referenced: list[str]) -> _Resolved:
    """Resolve each referenced column by its SQL, else by its PT4 name; collect what blocks it."""
    resolved = _Resolved()
    for col in referenced:
        col_sql = decoded.columns[col]
        ctx = PT4_CONTEXT_MAP.get(col_sql.strip().lower())
        if ctx:
            resolved.context[col] = ctx
            continue
        try:
            resolved.facts[col] = _resolve_fact(col_sql)
        except PT4TranslationError as exc:
            named = PT4_NAMED_COLUMNS.get(col)
            if named is None:
                resolved.failures.append(f"{col} ({exc})")
                continue
            resolved.facts[col] = (named["fpdb"], None, 1.0)
            if named.get("note"):
                resolved.notes.append(named["note"])
    return resolved


def _translate_arithmetic(decoded: DecodedStat, expr: str) -> TranslatedStat:
    """Translate a general arithmetic/ratio value expression into a descriptor.

    Handles the common case the single-column / fact-over-context paths do not:
    an expression like ``(cnt_a / cnt_b) * 100`` over several custom columns.
    Every referenced column must resolve to a non-dimensioned FPDB fact (or a
    context aggregate); otherwise the precise blocker is reported. Each column
    name is rewritten to its FPDB column (with any x100 scaling folded in), so
    the resulting descriptor value is evaluable by the registry.

    A sub-expression FPDB answers with a column of its own (``cnt_hands -
    cnt_walks``) and a column known by name (``cnt_pfr_opp``) translate too,
    under FPDB's definition: their notes say how it differs from PT4's (#613).
    """
    result = TranslatedStat()
    expr, alias_inputs, alias_notes = _apply_expression_aliases(expr)
    referenced = [c for c in decoded.columns if re.search(rf"\b{re.escape(c)}\b", expr)]
    resolved = _resolve_columns(decoded, referenced)

    if resolved.failures:
        result.warnings.append(
            "value expression needs PT4 columns with no FPDB mapping: " + "; ".join(resolved.failures)
        )
        return result
    if not resolved.facts and not alias_inputs:
        result.warnings.append(f"unrecognized value expression: {expr[:80]}")
        return result
    if any(dim is not None for _, dim, _ in resolved.facts.values()):
        result.warnings.append(f"dimensioned columns cannot be combined in an expression: {expr[:80]}")
        return result

    rewritten = expr
    inputs: list[str] = list(alias_inputs)
    for col, (fpdb_expr, _dim, scale) in resolved.facts.items():
        token = fpdb_expr if _IDENTIFIER_RE.fullmatch(fpdb_expr) else f"({fpdb_expr})"
        if scale != 1.0:
            token = f"({token} / {scale:g})"
        rewritten = re.sub(rf"\b{re.escape(col)}\b", token, rewritten)
        inputs.extend(_inputs_of(fpdb_expr))
    for col, ctx_input in resolved.context.items():
        rewritten = re.sub(rf"\b{re.escape(col)}\b", ctx_input, rewritten)
        inputs.append(ctx_input)

    col_sqls = [decoded.columns[col] for col in [*resolved.facts, *resolved.context]]
    notes = list(dict.fromkeys(alias_notes + resolved.notes))
    result.descriptor = _ratio_descriptor(
        decoded, rewritten.strip(), inputs, list(resolved.context.values()), col_sqls, notes
    )
    result.notes = notes
    return result


def _ratio_descriptor(
    decoded: DecodedStat,
    value: str,
    inputs: list[str],
    context: list[str],
    col_sqls: list[str],
    notes: list[str],
) -> dict[str, Any]:
    """The descriptor of a translated ratio stat; ``notes`` say where FPDB's definition differs."""
    tournament = decoded.category.startswith("Tournament") or any(
        any(t in sql for t in TOURNAMENT_TABLES) for sql in col_sqls
    )
    name = _slugify(decoded.label) or "pt4_stat"
    descriptor: dict[str, Any] = {
        "name": name,
        "label": decoded.label or name,
        "category": "Imported (PT4)",
        "scope": ["tour"] if tournament else ["ring", "tour"],
        "inputs": list(dict.fromkeys(inputs)),
        "value": value,
        "aggregate": "ratio",
        "format": f"%0.{decoded.decimals}f",
    }
    if context:
        descriptor["context"] = context
    boolean_inputs = _booleans(inputs)
    if boolean_inputs:
        descriptor["boolean_inputs"] = boolean_inputs
    description = decoded.description
    if notes:
        description = " ".join([description, "Differs from PT4:", *notes]).strip()
    if description:
        descriptor["description"] = description
    return descriptor


def translate(decoded: DecodedStat) -> TranslatedStat:
    """Translate a :class:`DecodedStat` into descriptor data, or report why not."""
    result = TranslatedStat()
    if not decoded.value_expr:
        result.warnings.append("no value expression found")
        return result

    # The value expression references one or more custom columns by name,
    # optionally divided by a context column (e.g. ".../ cnt_tourneys").
    expr = decoded.value_expr
    context_input: str | None = None

    # Detect a trailing division by an aggregate that maps to a context input.
    div = re.match(r"^\s*(\w+)\s*/\s*(\w+)\s*$", expr)
    primary_col = expr.strip()
    if div:
        primary_col = div.group(1)
        ctx_name = div.group(2)
        ctx_sql = decoded.columns.get(ctx_name, "")
        context_input = PT4_CONTEXT_MAP.get(ctx_sql.strip().lower())
        if context_input is None:
            result.warnings.append(f"unmapped context divisor {ctx_name!r} ({ctx_sql.strip()[:60]})")
            return result

    col_sql = decoded.columns.get(primary_col)
    if col_sql is None:
        # Not a single column or fact/context division: try the general
        # arithmetic path (e.g. "(cnt_a / cnt_b) * 100"), which reports the
        # precise blocker if any referenced column has no FPDB mapping.
        return _translate_arithmetic(decoded, expr)

    try:
        fpdb_col, dimension, scale = _resolve_fact(col_sql)
    except PT4TranslationError as exc:
        result.warnings.append(str(exc))
        return result

    # Build the descriptor value expression with the x100 scaling folded in. The
    # FPDB side may be a sum of columns (both blinds' steal defences, #613).
    inputs = _inputs_of(fpdb_col)
    term = fpdb_col if _IDENTIFIER_RE.fullmatch(fpdb_col) else f"({fpdb_col})"
    value = f"{term} / {scale:g}" if scale != 1.0 else term
    if context_input:
        inputs.append(context_input)
        value = f"{value} / {context_input}"

    # Tournament scope is implied by the referenced PT4 tables, or by the stat's PT4 category.
    tournament = decoded.category.startswith("Tournament") or any(t in col_sql for t in TOURNAMENT_TABLES)
    scope = ["tour"] if tournament else ["ring", "tour"]

    name = _slugify(decoded.label) or _slugify(primary_col)
    fmt = f"%0.{decoded.decimals}f"

    descriptor: dict[str, Any] = {
        "name": name,
        "label": decoded.label or name,
        "category": "Tournament / ChipEV",
        "scope": scope,
        "inputs": inputs,
        "value": value,
        "aggregate": "sum",
        "format": fmt,
    }
    if dimension is not None:
        descriptor["dimension"] = dimension
        descriptor["series"] = "cumulative"
    if context_input:
        descriptor["context"] = [context_input]
    if _booleans(inputs):
        descriptor["boolean_inputs"] = _booleans(inputs)
    if decoded.description:
        descriptor["description"] = decoded.description

    result.descriptor = descriptor
    return result


# --------------------------------------------------------------------------- #
# Emitting.
# --------------------------------------------------------------------------- #


def _toml_value(value: Any) -> str:
    if isinstance(value, str):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{k} = {_toml_value(v)}" for k, v in value.items()) + " }"
    raise TypeError(f"cannot serialise {type(value).__name__}")


def emit_toml(descriptor: dict[str, Any]) -> str:
    """Serialise a descriptor data dict to a ``[[stat]]`` TOML fragment."""
    order = [
        "name",
        "label",
        "category",
        "scope",
        "inputs",
        "boolean_inputs",
        "dimension",
        "context",
        "value",
        "aggregate",
        "series",
        "format",
        "description",
    ]
    lines = ["[[stat]]"]
    for key in order:
        if key in descriptor:
            lines.append(f"{key} = {_toml_value(descriptor[key])}")
    return "\n".join(lines) + "\n"


@dataclass
class ImportReport:
    """Summary of importing a directory of ``.pt4stat`` files."""

    imported: list[str] = field(default_factory=list)
    skipped: dict[str, list[str]] = field(default_factory=dict)
    output: Path | None = None
    # Imported under FPDB's own definition (#613): stat name -> how it differs from PT4's.
    differs: dict[str, list[str]] = field(default_factory=dict)

    def summary(self) -> str:
        lines = [f"Imported {len(self.imported)} stat(s): {', '.join(self.imported) or '-'}"]
        if self.output:
            lines.append(f"  -> {self.output}")
        if self.differs:
            lines.append(f"Imported under FPDB's definition, which differs from PT4's ({len(self.differs)}):")
            for name, notes in self.differs.items():
                lines.append(f"  - {name}: {' '.join(notes)}")
        if self.skipped:
            lines.append(f"Skipped {len(self.skipped)} stat(s) (need new derived data / unsupported):")
            for fname, warns in self.skipped.items():
                lines.append(f"  - {fname}: {'; '.join(warns)}")
        return "\n".join(lines)


def _load_existing_descriptors(dest_file: Path) -> dict[str, dict[str, Any]]:
    """Read already-written descriptors from ``dest_file`` keyed by name (for merge)."""
    if not dest_file.exists() or _toml is None:
        return {}
    try:
        doc = _toml.loads(dest_file.read_text(encoding="utf-8"))
        stats = doc.get("stat", [])
        if isinstance(stats, dict):
            stats = [stats]
        return {s["name"]: s for s in stats if "name" in s}
    except Exception:  # pragma: no cover - corrupt file: start fresh
        log.exception("could not read existing descriptors from %s", dest_file)
        return {}


def import_files(paths: list[str | Path], dest_file: str | Path) -> ImportReport:
    """Translate the given ``.pt4stat`` files and merge them into ``dest_file``.

    Existing descriptors in ``dest_file`` are preserved; a re-imported stat with
    the same ``name`` replaces the previous one. Returns an :class:`ImportReport`.
    """
    dest_file = Path(dest_file)
    report = ImportReport(output=dest_file)

    merged = _load_existing_descriptors(dest_file)
    for path in sorted(Path(p) for p in paths):
        translated = translate(decode_pt4stat(path))
        descriptor = translated.descriptor
        if descriptor is not None:
            merged[descriptor["name"]] = descriptor
            report.imported.append(descriptor["name"])
            if translated.notes:
                report.differs[descriptor["name"]] = translated.notes
        else:
            report.skipped[path.name] = translated.warnings or ["unsupported"]

    if report.imported:
        header = (
            "# Auto-generated by fpdb_3_legacy.pt4_import from PT4 .pt4stat files.\n"
            "# Review names/labels before use.\n\n"
        )
        body = "\n".join(emit_toml(merged[name]) for name in sorted(merged))
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        dest_file.write_text(header + body, encoding="utf-8")
    return report


def import_directory(src: str | Path, dest_file: str | Path) -> ImportReport:
    """Translate every ``.pt4stat`` in ``src`` and write descriptors to ``dest_file``."""
    return import_files(list(Path(src).glob("*.pt4stat")), dest_file)


# The common cash stats #613 set out to translate, by their PT4 titles.
COMMON_CASH_STATS = (
    "VPIP",
    "PFR",
    "3Bet Preflop",
    "Fold to PF 3Bet",
    "CBet Flop",
    "Fold to F CBet",
    "WTSD",
    "WSD",
    "Flop AF",
    "Total AF",
    "Flop AFq",
    "Total AFq",
    "Att To Steal",
    "Fold to Steal",
)
# A blocker as the translator words it: "unmapped PT4 column 'x'", "unmapped PT4 condition "..."".
_BLOCKER_RE = re.compile(r"unmapped PT4 (column|condition|position code) (['\"])(.*?)\2(?=[);]|$)")
_BLOCKER_SHOWN = 70


def _blocker_label(kind: str, detail: str) -> str:
    """A blocker for the report: its kind and the start of what PT4 wrote."""
    detail = " ".join(detail.split())
    if len(detail) > _BLOCKER_SHOWN:
        detail = detail[: _BLOCKER_SHOWN - 1] + "…"
    return f"unmapped {kind}: `{detail}`"


@dataclass
class CoverageReport:
    """How much of PT4's stock stat set translates (#613)."""

    results: list[tuple[DecodedStat, TranslatedStat]] = field(default_factory=list)

    def count(self, category: str, *, supported: bool, noted: bool = False) -> int:
        return sum(
            1
            for stat, result in self.results
            if stat.category == category and result.supported == supported and bool(result.notes) == noted
        )

    def blockers(self, top: int = 15) -> list[tuple[str, int]]:
        """What stops the most stats, each blocker counted once per stat it stops."""
        counter: Counter[str] = Counter()
        for _stat, result in self.results:
            if result.supported:
                continue
            text = "; ".join(result.warnings)
            found = {_blocker_label(kind, detail) for kind, _quote, detail in _BLOCKER_RE.findall(text)}
            if "unsupported column SQL" in text:
                found.add("unsupported column SQL (a construct the translator does not parse)")
            if not found:
                found = {result.warnings[0].split(":")[0] if result.warnings else "unsupported"}
            counter.update(found)
        return counter.most_common(top)

    def markdown(self, source: str) -> str:
        lines = [
            "# PT4 stock stat coverage",
            "",
            f"Generated by `python -m fpdb_3_legacy.pt4_import --coverage` from `{source}` (#613).",
            "A stat translates when every column it reads maps onto FPDB data; one that maps under a",
            "different definition says how. Nothing that does not translate is approximated silently.",
            "",
            "| Category | Translated | of which as PT4 defines it | of which under FPDB's definition | Not translated |",
            "|---|---:|---:|---:|---:|",
        ]
        for category in PLAYER_CATEGORIES:
            same = self.count(category, supported=True)
            differs = self.count(category, supported=True, noted=True)
            lines.append(
                f"| {category} | {same + differs} | {same} | {differs} | {self.count(category, supported=False)} |"
            )
        lines += ["", "## The common cash stats", "", "| PT4 stat | FPDB value | Status |", "|---|---|---|"]
        by_title = {stat.label: result for stat, result in self.results if stat.category == "Cash Player"}
        for title in COMMON_CASH_STATS:
            result = by_title.get(title)
            if result is None:
                lines.append(f"| {title} | | not in this PT4 version |")
            elif result.descriptor is not None:
                status = "translated" + (": " + " ".join(result.notes) if result.notes else "")
                lines.append(f"| {title} | `{result.descriptor['value']}` | {status} |")
            else:
                lines.append(f"| {title} | | not translated: {'; '.join(result.warnings)} |")
        lines += ["", "## What blocks the rest", "", "| Blocker | Stats it stops |", "|---|---:|"]
        lines += [f"| {blocker} | {count} |" for blocker, count in self.blockers()]
        return "\n".join(lines) + "\n"


def coverage(path: str | Path) -> CoverageReport:
    """Translate every player stat of a PT4 ``StatDefinitions.pt4`` and report the outcome."""
    return CoverageReport([(stat, translate(stat)) for stat in read_stat_definitions(path)])


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Import PT4 .pt4stat files into FPDB stat descriptors.")
    parser.add_argument("src", help="directory containing .pt4stat files, or StatDefinitions.pt4 with --coverage")
    parser.add_argument("dest", nargs="?", help="output .toml descriptor file (a Markdown report with --coverage)")
    parser.add_argument("--coverage", action="store_true", help="report how much of PT4's stock stat set translates")
    args = parser.parse_args(argv)

    if args.coverage:
        text = coverage(args.src).markdown(Path(args.src).name)
        if args.dest:
            Path(args.dest).write_text(text, encoding="utf-8")
        else:
            print(text)
        return 0
    if not args.dest:
        parser.error("dest is required unless --coverage is given")
    report = import_directory(args.src, args.dest)
    print(report.summary())
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
