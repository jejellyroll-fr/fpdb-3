#!/usr/bin/env python
"""Generate the HUD Stats Guide data from the code (issue #751).

Writes ``fpdb_3_legacy/stats_guide_data.py`` and ``docs/hud-stats-guide.md``.

Nothing here is inferred from an abbreviation.  Each native stat in
``Stats.STATLIST`` is *run* against a recording stat dictionary: the keys it
reads are the inputs, and a brute-force search over signed sums finds the
numerator and the denominator whose ratio reproduces the value the function
actually returns.  The inputs are then traced to the SQL expressions of the HUD
queries that fill them.  Stats whose logic is not a plain ratio (averages,
estimates, display-only stats, deprecated placeholders) carry a hand-written
entry in :data:`OVERRIDES`, written from the source of the function.

Run from the repository root::

    .venv/bin/python tools/gen_stats_guide.py          # rewrite both files
    .venv/bin/python tools/gen_stats_guide.py --check  # exit 1 when stale
"""

from __future__ import annotations

import ast
import importlib
import inspect
import itertools
import pprint
import re
import sys
import textwrap
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

# The sibling modules are found through the path set just above.
stats_guide_text = importlib.import_module("stats_guide_text")
stats_guide_games = importlib.import_module("stats_guide_games")
OVERRIDES = importlib.import_module("stats_guide_overrides").OVERRIDES

DATA_FILE = ROOT / "fpdb_3_legacy" / "stats_guide_data.py"
DOC_FILE = ROOT / "docs" / "hud-stats-guide.md"

HUD_SQL_FILES = (
    "sql_queries_hud_current_stats.py",
    "sql_queries_hud_aggregated_stats.py",
    "sql_queries_aof.py",
)

# Keys the HUD query does not select under that name, with what they really are.
KEY_NOTES: dict[str, str] = {
    "screen_name": "the player's name (p.name)",
    "currency": "not selected by the HUD queries: always the USD default",
    "3bet": "not selected by any HUD query: always 0",
}

# --------------------------------------------------------------------------- #
# Recording stat dictionary
# --------------------------------------------------------------------------- #


class _Row(dict):  # type: ignore[type-arg]
    """A stat row that records every key read and serves chosen values."""

    def __init__(self, values: dict[str, float], log: list[str]) -> None:
        super().__init__()
        self._values = values
        self._log = log

    def _read(self, key: str) -> float:
        self._log.append(key)
        return self._values.get(key, 1)

    def __getitem__(self, key: str) -> float:
        return self._read(key)

    def get(self, key: str, _default: Any = None) -> float:  # noqa: ANN401
        return self._read(key)

    def __contains__(self, key: object) -> bool:
        self._log.append(str(key))
        return True


def _call(fn: Any, values: dict[str, float]) -> tuple[Any, list[str]]:  # noqa: ANN401
    log: list[str] = []
    try:
        result = fn({1: _Row(values, log)}, 1)
    except Exception:  # noqa: BLE001 - probing helpers that are not stats
        return None, log
    return result, list(dict.fromkeys(log))


_MULTIPLIERS = (1, 100, 0.01, 0.001, 1000, 10, 1e-4, 1e-6)


class _Sequence:
    """Reproducible integers for probing stat functions (a linear congruential generator).

    The guide must be the same on every run, and nothing here is about secrecy.
    """

    def __init__(self, seed: int) -> None:
        self._state = seed

    def randint(self, low: int, high: int) -> int:
        self._state = (self._state * 1103515245 + 12345) % 2**31
        return low + self._state % (high - low + 1)

    def choice(self, items: list[int]) -> int:
        return items[self.randint(0, len(items) - 1)]


def _solve(fn: Any, keys: list[str]) -> tuple[tuple[int, ...], tuple[int, ...], float, Any] | None:  # noqa: ANN401, C901
    """The (numerator, denominator, multiplier) the function's raw value matches."""
    if not keys or len(keys) > 6:
        return None
    rng = _Sequence(751)
    trials = []
    for t in range(4):
        values = {
            k: (1000 if ("face" in k or "opp" in k) else 1)
            * rng.choice([3, 5, 7, 11, 13, 17, 19, 23, 29, 31])
            * rng.randint(1, 9)
            + t * 1000
            for k in keys
        }
        result, _ = _call(fn, values)
        if result is None or not isinstance(result[0], (int, float)):
            return None
        trials.append((values, float(result[0])))
        sample = result
    coefficients = list(itertools.product((1, 0, -1), repeat=len(keys)))
    for num in coefficients:
        if not any(num):
            continue
        for den in coefficients:
            if not any(den):
                continue
            for mult in _MULTIPLIERS:
                good = True
                for values, raw in trials:
                    n = sum(c * values[k] for c, k in zip(num, keys, strict=True))
                    d = sum(c * values[k] for c, k in zip(den, keys, strict=True))
                    if d == 0 or abs(mult * n / d - raw) > 1e-9 * max(1.0, abs(raw)):
                        good = False
                        break
                if good:
                    return num, den, mult, sample
    return None


# --------------------------------------------------------------------------- #
# HUD SQL: alias -> expression
# --------------------------------------------------------------------------- #


def _hud_aliases() -> dict[str, str]:
    """``alias.lower()`` -> SQL expression, from the HUD queries."""
    found: dict[str, str] = {}
    aggregate = re.compile(r"\b(sum|max|avg)\(((?:[^()]|\((?:[^()]|\([^()]*\))*\))*)\)\s+(?:AS|as)\s+(\w+)", re.S)
    plain = re.compile(r"\bhc\.(\w+)\s+AS\s+(\w+)\s*,?\s*$", re.M)
    for name in HUD_SQL_FILES:
        text = (ROOT / "fpdb_3_legacy" / name).read_text(encoding="utf-8")
        for match in aggregate.finditer(text):
            expr = re.sub(r"\s+", " ", match.group(2)).strip()
            found.setdefault(match.group(3).lower(), f"{match.group(1).upper()}({expr.replace('hc.', 'HudCache.')})")
        for match in plain.finditer(text):
            found.setdefault(match.group(2).lower(), f"HudCache.{match.group(1)}")
    return found


def _fmt_key(key: str, aliases: dict[str, str]) -> str:
    expr = aliases.get(key.lower())
    if expr:
        return f"{key} = {expr}"
    note = KEY_NOTES.get(key)
    return f"{key} ({note})" if note else f"{key} (not selected by the HUD queries)"


# The "fold" leg of the PT4 action enums is computed, not stored.
_FOLD_RE = re.compile(r"^(fold_vs_(?!4bet$)|fold_float_)")


def _humanise(num: tuple[int, ...], keys: list[str]) -> str:
    parts = []
    for coeff, key in zip(num, keys, strict=True):
        if coeff == 0:
            continue
        sign = "+" if coeff > 0 else "−"
        parts.append(f"{sign} {key}")
    text = " ".join(parts)
    text = text[2:] if text.startswith("+ ") else "−" + text[2:]
    return f"({text})" if len(parts) > 1 else text


def _percent_display(result: tuple[Any, ...]) -> bool:
    return str(result[2]).endswith("%")


def _native_entry(name: str, fn: Any, aliases: dict[str, str]) -> dict[str, Any] | None:  # noqa: ANN401, C901, PLR0915
    result, keys = _call(fn, {})
    if not (isinstance(result, tuple) and len(result) > 5 and isinstance(result[5], str)):
        return None
    description = result[5].strip()
    abbr = str(result[2]).split("=")[0]
    detail = str(result[3]).split("=")[0]
    entry: dict[str, Any] = {
        "name": name,
        "origin": "native",
        "abbr": abbr,
        "detail_label": detail,
        "description": description,
        "formula": "",
        "sql": "",
        "note": "",
        "status": "active",
    }
    if "deprecated" in description.lower():
        entry["status"] = "deprecated"
    override = OVERRIDES.get(name)
    if override:
        entry.update(override)
        return entry
    if _FOLD_RE.match(name):
        faced = next(k for k in keys if "_face_" in k)
        called, raised = faced.replace("_face_", "_call_"), faced.replace("_face_", "_raise_")
        keys = [faced, called, raised]
        entry["formula"] = f"({faced} − {called} − {raised}) / {faced} × 100"
        entry["sql"] = "; ".join(_fmt_key(k, aliases) for k in keys)
        entry["note"] = (
            "The fold leg is computed as faced − called − raised: a faced spot ends in exactly one of fold, call or raise."
        )
        entry["formula_words"] = (
            stats_guide_text.words([(1, faced), (-1, called), (-1, raised)], [(1, faced)]) + " × 100"
        )
        entry["signature"] = entry["sql"] + "|" + entry["formula"].replace(faced, "F")
        entry["_den_sql"] = _fmt_key(faced, aliases)
        return entry
    solved = _solve(fn, keys)
    if solved is None:
        entry["formula"] = "see the function in Stats.py"
        entry["sql"] = "; ".join(_fmt_key(k, aliases) for k in keys) or "none"
        entry["status"] = "unchecked"
        return entry
    num, den, mult, sample = solved
    ratio = f"{_humanise(num, keys)} / {_humanise(den, keys)}"
    percent = _percent_display(sample)
    if mult == 1 and percent:
        entry["formula"] = f"{ratio} × 100"
    elif mult == 1:
        entry["formula"] = ratio
    elif mult == 100:
        entry["formula"] = f"{ratio} × 100"
    elif mult == 1e-4:
        entry["formula"] = f"({ratio}) / 10 000 × 100"
        entry["note"] = (
            "The numerator is stored in basis points of the pot (10 000 = one pot), so the result is a percentage of the pot."
        )
    else:
        entry["formula"] = f"{mult:g} × {ratio}"
    used = [k for k, c in zip(keys, tuple(a or b for a, b in zip(num, den, strict=True)), strict=True) if c]
    entry["sql"] = "; ".join(_fmt_key(k, aliases) for k in used)
    num_keys = [(c, k) for c, k in zip(num, keys, strict=True) if c]
    den_keys = [(c, k) for c, k in zip(den, keys, strict=True) if c]
    scale = (
        " × 100"
        if percent and mult in (1, 100)
        else (" / 10 000 × 100" if mult == 1e-4 else ("" if mult == 1 else f" × {mult:g}"))
    )
    entry["formula_words"] = stats_guide_text.words(num_keys, den_keys) + scale
    entry["_den_sql"] = "; ".join(_fmt_key(k, aliases) for _c, k in den_keys)
    expr = {k: aliases.get(k.lower(), k) for k in keys}
    entry["signature"] = (
        "+".join(f"{c}{expr[k]}" for c, k in num_keys)
        + "/"
        + "+".join(f"{c}{expr[k]}" for c, k in den_keys)
        + f"*{mult}"
    )
    if "(not selected by the HUD queries)" in entry["sql"]:
        entry["status"] = "input-missing"
        entry["note"] = (
            "An input is read under a name the HUD queries do not select, so the value is computed from a missing column. "
            "Check the HUD queries before relying on it."
        )
    return entry


# --------------------------------------------------------------------------- #
# Ring Player Stats columns (legacy XML titles)
# --------------------------------------------------------------------------- #


def _ring_columns() -> list[dict[str, str]]:
    """The Ring Player Stats table columns: XML title and SQL logic."""
    xml = (ROOT / "fpdb_3_legacy" / "HUD_config.xml.example").read_text(encoding="utf-8")
    titles = dict(re.findall(r'<col col_name="([^"]+)"[^>]*?col_title="([^"]*)"', xml))
    sql = (ROOT / "fpdb_3_legacy" / "sql_queries_player_detailed.py").read_text(encoding="utf-8")
    # first variant only: the three dialects repeat the same columns
    head = sql.split("</pre>")[0]
    columns: dict[str, str] = {}
    for match in re.finditer(r",?\s*(.+?)\s+AS\s+(\w+)\s*\n", head, re.S):
        alias = match.group(2).lower()
        if alias in titles and alias not in columns:
            expr = re.sub(r"cast\(([\w.]+) as SIGNED\)", r"\1", match.group(1))
            expr = re.sub(r"\s+", " ", expr).replace("hp.", "").strip()
            expr = re.sub(r"^[,\s]+", "", re.sub(r"/\*.*?\*/", "", expr)).strip(", ")
            columns[alias] = expr
    rows = []
    for col, title in titles.items():
        rows.append({"col_name": col, "xml_title": title, "sql": columns.get(col, "")})
    return rows


RING_NOTES: dict[str, tuple[str, str]] = {
    # col_name -> (description, closest HUD stat)
    "vpip": ("Voluntarily put money in pot, preflop", "vpip"),
    "pfr": ("Preflop raise", "pfr"),
    "pf3": ("Preflop 3-bet", "three_B"),
    "pf4": ("Preflop 4-bet", "four_B"),
    "pff3": ("Folded to a preflop 3-bet", "f_3bet"),
    "pff4": ("Folded to a preflop 4-bet", "f_4bet"),
    "aggfac": ("Postflop aggression factor", "agg_fact"),
    "aggfrq": ("Postflop aggression frequency, with folds and calls in the base", ""),
    "conbet": ("Continuation bet, all streets pooled", "cbet"),
    "rfi": (
        "Raise first in (raisedFirstIn / raiseFirstInChance); no HUD stat uses this exact count under one name",
        "",
    ),
    "steals": ("Steal attempt", "steal"),
    "car0": ("Called a raise preflop", "car0"),
    "saw_f": ("Saw the flop", "saw_f"),
    "sawsd": ("Saw showdown, over all hands (not over flops seen: that is WtSDwsF)", ""),
    "wtsdwsf": ("Went to showdown when the flop was seen (WTSD)", "wtsd"),
    "wmsf": (
        "Won money when the flop was seen. Title W$wsF: this is the after-seeing-the-flop stat, not a showdown stat",
        "WMsF",
    ),
    "wmsd": ("Won money at showdown (W$SD)", "wmsd"),
    "flafq": ("Flop aggression frequency", "a_freq1"),
    "tuafq": ("Turn aggression frequency", "a_freq2"),
    "rvafq": ("River aggression frequency", "a_freq3"),
    "pofafq": ("Postflop aggression frequency", "a_freq_123"),
}


# --------------------------------------------------------------------------- #
# Registry and analytics entries
# --------------------------------------------------------------------------- #


def _registry_entries(native: set[str]) -> list[dict[str, Any]]:
    from fpdb_3_legacy import stat_registry  # noqa: PLC0415

    entries = []
    for descriptor in stat_registry.get_registry().all():
        if descriptor.name in native:  # Stats.do_stat reaches a descriptor only for a name that is not native
            continue
        entries.append(
            {
                "name": descriptor.name,
                "origin": "registry",
                "abbr": descriptor.label or descriptor.name,
                "detail_label": descriptor.label or descriptor.name,
                "description": descriptor.description or descriptor.label or descriptor.name,
                "formula": f"{descriptor.value}   (aggregate: {descriptor.aggregate})",
                "sql": "inputs (HudCache columns): " + ", ".join(descriptor.inputs),
                "note": "Declarative stat of stats.d/*.toml, drawn by the HUD like a native one.",
                "status": "active",
            }
        )
    return entries


def _analytics_entries() -> list[dict[str, Any]]:
    from fpdb_3_legacy import analytics_definitions, analytics_query  # noqa: PLC0415

    registry = analytics_definitions.get_registry()
    entries = []
    for definition in registry.all():
        filters = dict(analytics_definitions.expand_fragments(definition.fragments, registry.fragments))
        filters.update(definition.filters)
        numerator = dict(analytics_query.IMPLIED_NUMERATORS.get(definition.metric, {}))
        numerator.update(definition.numerator)
        label = definition.display.label_for("en") or definition.name
        if numerator:
            formula = f"decisions matching the numerator {numerator} / decisions matching the filters"
            if definition.display.fmt == "percentage":
                formula += " × 100"
        else:
            formula = f"metric {definition.metric} over the decisions matching the filters"
        group = f"; grouped by {', '.join(definition.group_by)}" if definition.group_by else ""
        entries.append(
            {
                "name": definition.name,
                "origin": "analytics",
                "abbr": label,
                "detail_label": label,
                "description": definition.display.description_for("en") or label,
                "formula": formula,
                "sql": f"analytics engine over the action events (analytics_query): filters {filters}{group}",
                "note": f"Analytics definition (metric {definition.metric}): a HUD cell shows it only with the data_* attributes the editor writes.",
                "status": "active",
                "xml_titles": [],
            }
        )
    return entries


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #


def _alias_target(fn: Any, names: set[str]) -> str | None:  # noqa: ANN401
    """The stat a thin wrapper returns unchanged (``return WMsF(stat_dict, player)``)."""
    try:
        tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    except (OSError, TypeError, SyntaxError):
        return None
    body = tree.body[0].body if tree.body and isinstance(tree.body[0], ast.FunctionDef) else []
    body = [n for n in body if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))]
    if len(body) != 1 or not isinstance(body[0], ast.Return) or not isinstance(body[0].value, ast.Call):
        return None
    func = body[0].value.func
    target = func.id if isinstance(func, ast.Name) else None
    return target if target in names else None


def _add_text_and_aliases(entries: list[dict[str, Any]]) -> None:
    from fpdb_3_legacy import Stats  # noqa: PLC0415

    natives = {e["name"] for e in entries if e["origin"] == "native"}
    by_signature: dict[str, list[str]] = {}
    for entry in entries:
        title, detail = stats_guide_text.describe(entry["name"], entry["origin"], entry["description"])
        entry["title"] = title
        entry["detail"] = detail
        entry.setdefault(
            "formula_words",
            stats_guide_text.OVERRIDE_WORDS.get(entry["name"], "") if entry["origin"] == "native" else "",
        )
        entry["alias_of"] = ""
        if entry["origin"] == "native":
            target = _alias_target(getattr(Stats, entry["name"]), natives - {entry["name"]})
            if target:
                entry["alias_of"] = target
                entry["note"] = (
                    entry["note"] + " " if entry["note"] else ""
                ) + f"Alias: this stat calls `{target}` and returns its value unchanged."
        signature = entry.pop("signature", "")
        if signature:
            by_signature.setdefault(signature, []).append(entry["origin"] + ":" + entry["name"])
    for entry in entries:
        if entry["alias_of"]:
            continue
        key = entry["origin"] + ":" + entry["name"]
        same = [names for names in by_signature.values() if key in names and len(names) > 1]
        others = [n.split(":", 1)[1] for n in (same[0] if same else []) if n != key]
        if others:
            entry["note"] = (
                (entry["note"] + " " if entry["note"] else "")
                + "Gives the same value as "
                + ", ".join(f"`{n}`" for n in others)
                + " (same counters, same formula)."
            )


PT4_COVERAGE = ROOT / "docs" / "pt4-stock-stat-coverage.md"


def pt4_common_stats() -> dict[str, tuple[str, str]]:
    """PT4 title -> (formula over FPDB columns, translator note), from the coverage report."""
    rows: dict[str, tuple[str, str]] = {}
    section = False
    for line in PT4_COVERAGE.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            section = line.startswith("## The common cash stats")
            continue
        match = re.match(r"\| (.+?) \| `(.+?)` \| (.+?) \|$", line) if section else None
        if match:
            status = match.group(3)
            rows[match.group(1)] = (match.group(2), status.split(":", 1)[1].strip() if ":" in status else "")
    return rows


def _column_of(expr: str) -> str | None:
    match = re.fullmatch(r"SUM\(HudCache\.(\w+)\)", expr)
    return match.group(1) if match else None


def pt4_parity(
    fn: Any, pt4_formula: str, aliases: dict[str, str], trials: int = 6
) -> tuple[bool, list[tuple[float, float]]]:  # noqa: ANN401
    """Run the FPDB stat and PT4's formula on the same random HudCache counters.

    Returns whether the displayed FPDB value equals PT4's on every trial, and the pairs.
    """
    from fpdb_3_legacy.stat_registry import SafeExpression  # noqa: PLC0415

    columns_by_alias = {alias: _column_of(expr) for alias, expr in aliases.items()}
    _, keys = _call(fn, {})
    pt4_names = set(re.findall(r"[A-Za-z_]\w*", pt4_formula))
    expression = SafeExpression(pt4_formula, frozenset(pt4_names))
    rng = _Sequence(613)
    pairs = []
    for _ in range(trials):
        values: dict[str, float] = {}
        for column in pt4_names | {c for c in columns_by_alias.values() if c}:
            big = any(word in column for word in ("Chance", "Seen", "sawShowdown", "Calls", "Fold", "fold"))
            values[column] = float(rng.randint(200, 400) if big else rng.randint(1, 150))
        row = {key: values.get(columns_by_alias.get(key.lower()) or "", 0.0) for key in keys}
        result, _ = _call(fn, row)
        fpdb_value = float(str(result[1]).strip())
        pt4_value = float(expression.evaluate(values))
        pairs.append((fpdb_value, pt4_value))
    same = all(abs(a - b) <= 0.051 + 1e-9 * abs(b) for a, b in pairs)
    return same, pairs


def _pt4_tests() -> dict[str, list[str]]:
    """HudCache column -> the derivation tests that check it against PT4's definition."""
    found: dict[str, list[str]] = {}
    for path in sorted((ROOT / "tests").glob("test_*.py")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "PT4" not in text and "pt4" not in text:
            continue
        for column in set(
            re.findall(
                r"\b(street\d\w+|sawShowdown|wonAtSD|wonWhenSeenStreet\d|steal\w*|fold\w+ToSteal\w*|raiseToSteal\w*|success_Steal|cnt_\w+|val_\w+|flg_\w+|amt_\w+)\b",
                text,
            )
        ):
            found.setdefault(column, []).append(path.name)
    return found


def _add_pt4(entries: list[dict[str, Any]], aliases: dict[str, str]) -> None:
    from fpdb_3_legacy import Stats  # noqa: PLC0415

    natives = {e["name"]: e for e in entries if e["origin"] == "native"}
    tests = _pt4_tests()
    for entry in entries:
        entry["pt4"] = {}
        entry["pt4_tests"] = []
        if entry["origin"] != "native":
            continue
        columns = sorted(set(re.findall(r"HudCache\.(\w+)", entry["sql"])))
        entry["pt4_tests"] = sorted({name for column in columns for name in tests.get(column, [])})
    for title, (formula, note) in pt4_common_stats().items():
        name = stats_guide_text.PT4_EQUIVALENTS.get(title)
        if name not in natives:
            continue
        same, _pairs = pt4_parity(getattr(Stats, name), formula, aliases)
        natives[name]["pt4"] = {
            "stat": title,
            "formula": formula,
            "parity": "same formula" if same else "different formula",
            "note": note if same else stats_guide_text.PT4_DIFFERENCES.get(name, note),
        }


# --------------------------------------------------------------------------- #
# Which games and variants a stat applies to, measured on the test corpus
# --------------------------------------------------------------------------- #

BASES = ("hold", "stud", "draw")


def _parsed_hands(parser_class: Any, config: Any, path: Any) -> list[Any]:  # noqa: ANN401
    """The hands a converter reads from one file; none when it refuses the file."""
    try:
        return list(parser_class(config=config, in_path=str(path), autostart=True).getProcessedHands())
    except Exception:  # noqa: BLE001 - a refused fixture is not a stat question
        return []


def _hands_players(hand: Any) -> dict[str, Any]:  # noqa: ANN401
    """DerivedStats' HandsPlayers rows for one hand; empty when the hand cannot be derived."""
    from fpdb_3_legacy.DerivedStats import DerivedStats  # noqa: PLC0415

    try:
        stats = DerivedStats()
        stats.getStats(hand)
        return dict(stats.getHandsPlayers())
    except Exception:  # noqa: BLE001 - one odd fixture must not stop the measurement
        return {}


def measure_corpus() -> dict[str, Any]:
    """Parse every regression hand history and record which HandsPlayers columns get a value.

    The HUD sums these columns per game type, so a column never filled for a game
    family means the stats built on it show no data there.
    """
    import logging  # noqa: PLC0415

    from fpdb_3_legacy.Configuration import Config  # noqa: PLC0415
    from tests.test_live_parser_regression import CASES  # noqa: PLC0415

    logging.disable(logging.CRITICAL)
    try:
        config = Config()
        columns: dict[str, set[str]] = {base: set() for base in BASES}
        hands: dict[str, int] = {}
        categories: dict[str, set[str]] = {base: set() for base in BASES}
        positions: dict[str, set[str]] = {base: set() for base in BASES}
        for _key, parser_class, path in CASES:
            for hand in _parsed_hands(parser_class, config, path):
                base = hand.gametype.get("base")
                rows = _hands_players(hand) if base in columns else {}
                if not rows:
                    continue
                kind = f"{hand.gametype.get('type')}:{base}"
                hands[kind] = hands.get(kind, 0) + 1
                categories[base].add(str(hand.gametype.get("category")))
                for row in rows.values():
                    columns[base].update(c for c, v in row.items() if v and not isinstance(v, str))
                    positions[base].add(str(row.get("position")))
    finally:
        logging.disable(logging.NOTSET)
    return {
        "columns": {base: sorted(cols) for base, cols in columns.items()},
        "hands": dict(sorted(hands.items())),
        "categories": {base: sorted(cats) for base, cats in categories.items()},
        "positions": {base: sorted(pos) for base, pos in positions.items()},
    }


_STREET_COLUMN = re.compile(r"(?:street|Street|OtherRaisedStreet|otherRaisedStreet|WhenSeenStreet)(\d)")


def _street_of(columns: list[str]) -> int | None:
    numbers = {int(m.group(1)) for c in columns for m in [_STREET_COLUMN.search(c)] if m}
    if not numbers:
        letters = {
            m.group(1) for c in columns for m in [re.match(r"(?:cnt|val|flg|amt|amt_bet)_([pftr])(?:_|$)", c)] if m
        }
        if len(letters) == 1:
            return {"p": 0, "f": 1, "t": 2, "r": 3}[letters.pop()]
        if any(c == "amt_blind" for c in columns):
            return 0
        return None
    return min(numbers) if len(numbers) == 1 else None


# HandsPlayers.position -> the HudCache position bucket (database_caches.storeHudCache).
_HUD_BUCKET = {"B": "B", "S": "S", "0": "D", "1": "C", "2": "M", "3": "M", "4": "M"}


def _columns_in(sql: str) -> list[str]:
    """HudCache columns an SQL description names; ``streetN`` stands for streets 1 to 4."""
    found = set()
    for column in re.findall(r"HudCache\.(\w+)", sql):
        if "streetN" in column:
            found.update(column.replace("streetN", f"street{n}") for n in range(1, 5))
        else:
            found.add(column)
    return sorted(found)


def _add_applicability(entries: list[dict[str, Any]], corpus: dict[str, Any]) -> None:
    """Say where each stat has data: every column it reads must be filled for that game family.

    HudCache.n is one per hand everywhere (it is not a HandsPlayers column), and a
    column for a street a family does not have (7th street outside stud) is left out.
    """
    filled = {base: set(cols) | {"n"} for base, cols in corpus["columns"].items()}
    buckets = {base: {_HUD_BUCKET.get(p, "E") for p in pos} for base, pos in corpus["positions"].items()}
    last_street = {"hold": 3, "stud": 4, "draw": 3}
    for entry in entries:
        entry.pop("_den_sql", None)
        fixed = stats_guide_games.applies_override(entry["name"], entry["origin"])
        if fixed is not None:
            entry["applies"] = fixed
            continue
        if entry["status"] in ("input-missing", "deprecated"):
            entry["applies"] = {"games": [], "variants": dict.fromkeys(BASES, "")}
            continue
        columns = _columns_in(entry["sql"])
        needed_positions = set(re.findall(r"HudCache\.position = '(\w)'", entry["sql"]))
        street = _street_of(columns)
        variants = {}
        for base in BASES:
            usable = [c for c in columns if not (m := _STREET_COLUMN.search(c)) or int(m.group(1)) <= last_street[base]]
            if not columns:
                variants[base] = stats_guide_games.street_label(base, None)
            elif usable and all(c in filled[base] for c in usable) and needed_positions <= buckets[base]:
                variants[base] = stats_guide_games.street_label(base, street)
            else:
                variants[base] = ""
        entry["applies"] = {"games": stats_guide_games.games_for(entry), "variants": variants}


def build() -> dict[str, Any]:  # noqa: C901
    from fpdb_3_legacy import Stats  # noqa: PLC0415
    from fpdb_3_legacy.modern_hud_preferences import stat_catalog  # noqa: PLC0415

    aliases = _hud_aliases()
    entries: list[dict[str, Any]] = []
    for name in Stats.STATLIST:
        entry = _native_entry(name, getattr(Stats, name), aliases)
        if entry is not None:
            entries.append(entry)
    for entry in entries:
        entry["xml_titles"] = []
    entries += _registry_entries({e["name"] for e in entries}) + _analytics_entries()
    for entry in entries:
        entry["category"] = stat_catalog.category_for(entry["name"])
        entry.setdefault("xml_titles", [])
    ring = _ring_columns()
    for row in ring:
        note = RING_NOTES.get(row["col_name"])
        row["description"], row["hud_stat"] = note if note else ("", "")
    by_name = {e["name"]: e for e in entries}
    for row in ring:
        target = by_name.get(row["hud_stat"])
        if target is not None and row["xml_title"] not in target["xml_titles"]:
            target["xml_titles"].append(row["xml_title"])
    _add_text_and_aliases(entries)
    _add_pt4(entries, aliases)
    corpus = measure_corpus()
    _add_applicability(entries, corpus)
    shared: dict[str, list[str]] = {}
    for entry in entries:
        shared.setdefault(entry["abbr"], []).append(entry["name"])
    for entry in entries:
        others = [n for n in shared[entry["abbr"]] if n != entry["name"]]
        if others and entry["abbr"] and entry["origin"] == "native":
            entry["note"] = (
                entry["note"] + " " if entry["note"] else ""
            ) + f"The HUD abbreviation `{entry['abbr']}` is shared with: {', '.join(f'`{n}`' for n in others)}."
    entries.sort(
        key=lambda e: (
            list(stat_catalog.CATEGORIES).index(e["category"]) if e["category"] in stat_catalog.CATEGORIES else 99,
            e["name"].casefold(),
        )
    )
    return {
        "categories": dict(stat_catalog.CATEGORIES),
        "stats": entries,
        "ring_columns": ring,
        "corpus": {"hands": corpus["hands"], "categories": corpus["categories"], "positions": corpus["positions"]},
    }


def _render_module(data: dict[str, Any]) -> str:
    body = pprint.pformat(data, width=120, sort_dicts=False)
    return (
        '"""HUD Stats Guide data, generated by ``tools/gen_stats_guide.py`` (issue #751).\n\n'
        "Do not edit by hand: change the code or the overrides in the generator and run it again.\n"
        '"""\n\n'
        "from __future__ import annotations\n\n"
        "from typing import Any\n\n"
        f"GUIDE: dict[str, Any] = {body}\n"
    )


def _render_markdown(data: dict[str, Any]) -> str:  # noqa: C901, PLR0912
    lines = [
        "# HUD Stats Guide",
        "",
        "Generated from the code by `tools/gen_stats_guide.py`; do not edit by hand. The same data feeds the in-app **Stats Guide**.",
        "",
        "## How to read an entry",
        "",
        "- **Code identifier**: the name written in a HUD layout (`<stat stat_name=...>`). It is what the Add/Edit Statistic picker stores.",
        "- **HUD abbreviation**: the short text the HUD draws; it is the first part of the value the stat function returns.",
        "- **XML titles**: the `col_title` of the legacy Ring Player Stats columns that show the same measure. They are display titles only.",
        "- **Formula** and **SQL database field / logic**: the numerator and denominator the stat function really uses, and the HudCache expression that fills each input.",
        "",
        "Stats installed as user stat packs (`stat_packs`) or custom `stats.d` files are extensible and are **not** listed here.",
        "",
        "## Games and variants",
        "",
        "The HUD sums each player's history per game type: cash and tournament hands are never mixed, nor are",
        "two variants. Tournaments are one game type whatever their format, so MTT and SnG hands are counted",
        "together.",
        "",
        "The database numbers the betting rounds, and each stat reads one of those numbers. What a round is",
        "depends on the game family:",
        "",
        "| Round in the database | Hold'em / Omaha | Stud / Razz | Draw |",
        "| --- | --- | --- | --- |",
        "| 0 | preflop | 3rd street | before the first draw |",
        "| 1 | flop | 4th street | after the first draw |",
        "| 2 | turn | 5th street | after the second draw (triple draw only) |",
        "| 3 | river | 6th street | after the third draw (triple draw only) |",
        "| 4 | (none) | 7th street | (none) |",
        "",
        'So a "flop" stat is a 4th-street stat in stud and an after-the-first-draw stat in draw. Two exceptions:',
        "5-card stud starts at 2nd street (round 0 = 2nd street), and All-in or Fold Omaha has no preflop round",
        "(round 0 is its single flop decision).",
        "",
        "Whether a stat has data in a family is measured, not assumed: every regression hand history of the",
        "project is parsed and run through DerivedStats, and a stat applies to a family when all the columns",
        "it reads get a value there. The corpus: "
        + ", ".join(f"{n} {kind.replace(':', ' ')}" for kind, n in data["corpus"]["hands"].items())
        + ' hands. "No data" for a family means those columns stayed empty on every test hand of it.',
        "",
    ]
    by_category: dict[str, list[dict[str, Any]]] = {}
    for entry in data["stats"]:
        by_category.setdefault(entry["category"], []).append(entry)
    for category, entries in by_category.items():
        lines += [f"## {data['categories'].get(category, category)}", ""]
        for entry in entries:
            lines += [f"### {entry['title']} — `{entry['name']}`", ""]
            lines.append(
                f"- **HUD abbreviation**: `{entry['abbr']}`" if entry["abbr"] else "- **HUD abbreviation**: (none)"
            )
            lines.append(f"- **Description**: {entry['detail']}")
            if entry["formula_words"]:
                lines.append(f"- **Formula**: {entry['formula_words']}")
            lines.append(f"- **Formula (code)**: `{entry['formula']}`")
            lines.append(f"- **SQL database field / logic**: {entry['sql']}")
            if entry["description"] != entry["detail"]:
                lines.append(f"- **Tooltip**: {entry['description']}")
            if entry["detail_label"] and entry["detail_label"] != entry["abbr"]:
                lines.append(f"- **Detailed HUD text**: `{entry['detail_label']}`")
            for label, value in stats_guide_games.applies_lines(entry, data["corpus"]):
                lines.append(f"- **{label}**: {value}")
            if entry.get("pt4"):
                pt4 = entry["pt4"]
                lines.append(f"- **PT4 equivalent**: {pt4['stat']} — `{pt4['formula']}` ({pt4['parity']})")
                if pt4["note"]:
                    lines.append(f"- **PT4 difference**: {pt4['note']}")
            if entry.get("pt4_tests"):
                lines.append("- **PT4 derivation tests**: " + ", ".join(f"`{t}`" for t in entry["pt4_tests"]))
            if entry.get("xml_titles"):
                lines.append("- **XML titles**: " + ", ".join(f"`{t}`" for t in entry["xml_titles"]))
            if entry["status"] != "active":
                lines.append(f"- **Status**: {entry['status']}")
            if entry["note"]:
                lines.append(f"- **Note**: {entry['note']}")
            lines.append("")
    lines += ["## Legacy Ring Player Stats columns", "", "| Column | XML title | SQL logic |", "| --- | --- | --- |"]
    for row in data["ring_columns"]:
        lines.append(f"| `{row['col_name']}` | {row['xml_title']} | `{row['sql'] or '—'}` |")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    data = build()
    module, markdown = _render_module(data), _render_markdown(data)
    if "--check" in argv:
        stale = DATA_FILE.read_text(encoding="utf-8") != module or DOC_FILE.read_text(encoding="utf-8") != markdown
        print("stale" if stale else "up to date")
        return 1 if stale else 0
    # LF on every platform: the generated files are compared byte for byte in CI.
    for target, text in ((DATA_FILE, module), (DOC_FILE, markdown)):
        with target.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    print(f"{len(data['stats'])} stats, {len(data['ring_columns'])} ring columns")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
