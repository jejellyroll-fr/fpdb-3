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
import inspect
import itertools
import pprint
import random
import re
import sys
import textwrap
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import stats_guide_text  # noqa: E402

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

    def get(self, key: str, default: Any = None) -> float:  # noqa: ANN401
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


def _solve(fn: Any, keys: list[str]) -> tuple[tuple[int, ...], tuple[int, ...], float, Any] | None:  # noqa: ANN401, C901
    """The (numerator, denominator, multiplier) the function's raw value matches."""
    if not keys or len(keys) > 6:
        return None
    rng = random.Random(751)  # noqa: S311 - reproducible probing, not security
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
        text = (ROOT / "fpdb_3_legacy" / name).read_text()
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


# --------------------------------------------------------------------------- #
# Hand-written entries (read from the source of each function)
# --------------------------------------------------------------------------- #

# name -> dict(formula=..., sql=..., note=..., status=...)
OVERRIDES: dict[str, dict[str, str]] = {
    "BBper100": dict(
        formula="50 × net / bigblind   (net in cents, bigblind = Σ big blind × hands)",
        sql="net = SUM(HudCache.totalProfit); bigblind = SUM(Gametypes.bigblind * HudCache.n)",
        note="Big *bets* per 100 hands: the 50 factor counts a big bet as two big blinds. `bbper100` is the big-blind version.",
    ),
    "bbper100": dict(
        formula="100 × net / bigblind   (net in cents, bigblind = Σ big blind × hands)",
        sql="net = SUM(HudCache.totalProfit); bigblind = SUM(Gametypes.bigblind * HudCache.n)",
        note="Big blinds won per 100 hands.",
    ),
    "agg_fact": dict(
        formula="(Σ aggr_1..4) / (Σ call_1..4); the numerator alone when there is no call",
        sql="aggr_N = SUM(HudCache.streetNAggr); call_N = SUM(HudCache.streetNCalls) for streets 1 to 4 (flop to 7th street)",
        note="Postflop aggression factor, raw ratio.",
    ),
    "agg_fact_pct": dict(
        formula="(Σ aggr_1..4) / (Σ call_1..4 + Σ aggr_1..4)",
        sql="aggr_N = SUM(HudCache.streetNAggr); call_N = SUM(HudCache.streetNCalls) for streets 1 to 4",
        note="Despite its name the result is a 0..1 fraction (aggression / (aggression + calls)), not multiplied by 100.",
    ),
    "cbet": dict(
        formula="(Σ cb_1..4) / (Σ cb_opp_1..4) × 100",
        sql="cb_N = SUM(HudCache.streetNCBDone); cb_opp_N = SUM(HudCache.streetNCBChance) for streets 1 to 4",
        note="Continuation bet across all four streets pooled; `cb1`..`cb4` give one street each.",
    ),
    "cb_ip": dict(
        formula="(cb_1 × r) / (cb_opp_1 × r) × 100 with r = street1InPosition / saw_f; r cancels, so = cb_1 / cb_opp_1 × 100",
        sql="cb_1 = SUM(HudCache.street1CBDone); cb_opp_1 = SUM(HudCache.street1CBChance); saw_f = SUM(HudCache.street1Seen); street1InPosition = SUM(HudCache.street1InPosition)",
        note="Not split by position: both counts are scaled by the same in-position share of flops seen, which cancels out, so the value always equals `cb1`. HudCache has no c-bet count by position.",
        status="estimate",
    ),
    "cb_oop": dict(
        formula="(cb_1 × r) / (cb_opp_1 × r) × 100 with r = (saw_f − street1InPosition) / saw_f; r cancels, so = cb_1 / cb_opp_1 × 100",
        sql="cb_1 = SUM(HudCache.street1CBDone); cb_opp_1 = SUM(HudCache.street1CBChance); saw_f = SUM(HudCache.street1Seen); street1InPosition = SUM(HudCache.street1InPosition)",
        note="Not split by position: both counts are scaled by the same out-of-position share of flops seen, which cancels out, so the value always equals `cb1`. HudCache has no c-bet count by position.",
        status="estimate",
    ),
    "fbr": dict(
        formula="(fb_0 / fb_opp_0) × (pfr / n) × 100",
        sql="fb_0 = SUM(HudCache.street0_4BDone); fb_opp_0 = SUM(HudCache.street0_4BChance); pfr = SUM(HudCache.street0Aggr); n = SUM(HudCache.n)",
        note="Historical estimate of the four-bet range: the four-bet rate multiplied by the share of hands that were preflop raises.",
    ),
    "probe_bet": dict(
        formula="min(street1Bets, saw_f − cb_1) / (saw_f − cb_1) × 100",
        sql="saw_f = SUM(HudCache.street1Seen); cb_1 = SUM(HudCache.street1CBDone); street1Bets = SUM(HudCache.street1Bets)",
        note="Flop probe: bets over the flops seen where the player did not c-bet. Reads `street1Bets`, which the HUD queries expose as `bet_1`.",
        status="input-missing",
    ),
    "probe_bet_turn": dict(
        formula="min(street2Bets, saw_t − cb_2) / (saw_t − cb_2) × 100",
        sql="saw_t = SUM(HudCache.street2Seen); cb_2 = SUM(HudCache.street2CBDone); street2Bets = SUM(HudCache.street2Bets)",
        note="Turn probe. The HUD queries name the turn-seen count `saw_2` and the bet count `bet_2`, not the keys this stat reads.",
        status="input-missing",
    ),
    "probe_bet_river": dict(
        formula="min(street3Bets, saw_r − cb_3) / (saw_r − cb_3) × 100",
        sql="saw_r = SUM(HudCache.street3Seen); cb_3 = SUM(HudCache.street3CBDone); street3Bets = SUM(HudCache.street3Bets)",
        note="River probe. The HUD queries name the river-seen count `saw_3` and the bet count `bet_3`, not the keys this stat reads.",
        status="input-missing",
    ),
    "float_bet": dict(
        formula="min(street2Bets, opp) / opp × 100 with opp = min(street1InPosition, street1Calls, saw_t)",
        sql="street1InPosition = SUM(HudCache.street1InPosition); street1Calls = SUM(HudCache.street1Calls); saw_t = SUM(HudCache.street2Seen); street2Bets = SUM(HudCache.street2Bets)",
        note="An estimate from totals, not the same hands: the opportunities are the smallest of flops in position, flop calls and turns seen. Several inputs use names the HUD queries expose differently (`call_1`, `saw_2`, `bet_2`).",
        status="input-missing",
    ),
    "triple_barrel": dict(
        formula="min(cb_opp_1..3) × Π (cb_N / cb_opp_N) / min(cb_opp_1..3) × 100 = Π (cb_N / cb_opp_N) × 100",
        sql="cb_N = SUM(HudCache.streetNCBDone); cb_opp_N = SUM(HudCache.streetNCBChance) for streets 1 to 3",
        note="An estimate: the product of the three street c-bet rates, assuming the streets are independent. It does not follow the same hands through the three streets.",
    ),
    "overbet_frequency": dict(
        formula="constant 15 %, shown once any bet has been seen (Σ street1..3Bets > 0)",
        sql="street1Bets, street2Bets, street3Bets = SUM(HudCache.streetNBets) (exposed by the HUD queries as bet_1..3)",
        note="Not measured. The function returns a fixed 15 % estimate; it is kept for old layouts.",
        status="estimate",
    ),
    "resteal": dict(
        formula="(0.7 × tb_0) / (0.6 × tb_opp_0) × 100",
        sql="tb_0 = SUM(HudCache.street0_3BDone); tb_opp_0 = SUM(HudCache.street0_3BChance)",
        note="An estimate built from the 3-bet counts with fixed 0.7 and 0.6 factors (the share assumed to be from the blinds); it is not a count of re-steals. Use `raiseToSteal` for the measured value.",
        status="estimate",
    ),
    "rfi_total": dict(
        formula="max(0, pfr − 3bet) / pfr_opp × 100",
        sql="pfr = SUM(HudCache.street0Aggr); pfr_opp = SUM(HudCache.street0AggrChance); 3bet is not selected by any HUD query, so it is always 0",
        note="In practice this equals PFR. The measured raise-first-in rate is `rfi_early_position`, `rfi_middle_position` and `rfi_late_position` pooled by the position queries.",
    ),
    "vpip_pfr_ratio": dict(
        formula="(vpip / vpip_opp) / (pfr / pfr_opp)",
        sql="vpip = SUM(HudCache.street0VPI); vpip_opp = SUM(HudCache.street0VPIChance); pfr = SUM(HudCache.street0Aggr); pfr_opp = SUM(HudCache.street0AggrChance)",
        note="A plain ratio of the two percentages (not multiplied by 100); shows infinity when PFR is 0.",
    ),
    "profit100": dict(
        formula="net / n  (net in cents, so cents per hand, shown as per 100 hands in the label)",
        sql="net = SUM(HudCache.totalProfit); n = SUM(HudCache.n)",
        note="The label says per 100 hands but the formula is the average profit per hand, in cents.",
    ),
    "totalprofit": dict(
        formula="net / 100, formatted with the game's currency",
        sql="net = SUM(HudCache.totalProfit); currency is not selected by the HUD queries, so the USD default is used",
    ),
    "n": dict(
        formula="n (hand count; shown as 12.3k from 10 000)",
        sql="n = SUM(HudCache.n)",
    ),
    "bbstack": dict(
        formula="end stack of the player at the current hand / big blind of that hand",
        sql="not a HudCache aggregate: reconstructed from the hand being displayed (Hand object)",
        note="Last-hand value, not aggregated over the history.",
    ),
    "m_ratio": dict(
        formula="end stack / (antes + blinds posted in the hand + small blind + big blind)",
        sql="not a HudCache aggregate: reconstructed from the hand being displayed (Hand object)",
        note="Last-hand value, not aggregated over the history.",
    ),
    "stack_amount": dict(
        formula="reconstructed stack of the player, in the table's currency",
        sql="not a HudCache aggregate: reconstructed from the hand being displayed (Hand object)",
        note="Last-hand value.",
    ),
    "stack_bb": dict(
        formula="reconstructed stack / big blind",
        sql="not a HudCache aggregate: reconstructed from the hand being displayed (Hand object)",
        note="Last-hand value.",
    ),
    "stack_native_bb": dict(
        formula="reconstructed stack, followed by the stack / big blind",
        sql="not a HudCache aggregate: reconstructed from the hand being displayed (Hand object)",
        note="Last-hand value.",
    ),
    "bounty": dict(
        formula="the player's current bounty after the last hand",
        sql="not a HudCache aggregate: read from the hand being displayed (Hand object)",
        note="Knockout tournaments only.",
    ),
    "covers": dict(
        formula="compares the player's end stack with the hero's: +1 you cover, −1 covers you, 0 even",
        sql="not a HudCache aggregate: read from the hand being displayed (Hand object)",
    ),
    "starthands": dict(
        formula="lists the hands the player voluntarily played in the current history file, grouped as limped, raised, called a raise, defended the BB",
        sql="SELECT DISTINCT startCards, street0Aggr, street0CalledRaiseDone, position FROM Hands, HandsPlayers, Gametypes WHERE street0VPI AND fileId = the current file",
        note="Meant for popups: it reads one history file, not the cache, so it ignores the HUD's aggregation settings.",
    ),
    "playerprofile": dict(
        formula="player type (for example nit, TAG, LAG, fish) chosen by PlayerProfiler.classify_player from VPIP, PFR and aggression",
        sql="uses the HUD stat row of the player (VPIP, PFR, aggression inputs)",
        note="A label, not a number.",
    ),
    "playername": dict(formula="the player's name", sql="screen_name = Players.name"),
    "playershort": dict(formula="the player's name, shortened to fit the cell", sql="screen_name = Players.name"),
    "player_note": dict(
        formula="an icon when the player has a note",
        sql="screen_name = Players.name; the note is read from the notes of that player",
    ),
    "game_abbr": dict(
        formula="abbreviation of the game being played (for example Hold'em NL)",
        sql="read from the game type of the table; not a HudCache aggregate",
    ),
    "blank": dict(formula="an empty cell, used as a spacer in layouts", sql="none"),
    "call_vs_steal": dict(
        formula="no data (deprecated)",
        sql="none: needs data about other players that HudCache cannot aggregate",
        status="deprecated",
    ),
    "iso": dict(
        formula="no data (deprecated)",
        sql="none: isolation raises cannot be aggregated from HudCache",
        status="deprecated",
    ),
    "three_bet_vs_steal": dict(
        formula="no data (deprecated)",
        sql="none: needs data about other players that HudCache cannot aggregate",
        status="deprecated",
    ),
    "avg_bet_size_flop": dict(formula="no data (deprecated); see `f_bet_made`", sql="none", status="deprecated"),
    "avg_bet_size_turn": dict(formula="no data (deprecated); see `t_bet_made`", sql="none", status="deprecated"),
    "avg_bet_size_river": dict(formula="no data (deprecated); see `r_bet_made`", sql="none", status="deprecated"),
    "aof_observed": dict(
        formula="aof_obs (a count)",
        sql="aof_obs = count of all-or-fold decisions with decision = 'allin' and cardsObservable (sql_queries_aof.py)",
    ),
    "aof_showdowns": dict(
        formula="sd (a count, with n as the sample)",
        sql="sd = SUM(HudCache.sawShowdown); n = SUM(HudCache.n)",
        note="Hands that reached showdown, not hands whose cards were captured.",
    ),
    "aof_splash_won": dict(
        formula="aof_splash_cents / 100",
        sql="aof_splash_cents, aof_splash_seen and aof_splash_hit from sql_queries_aof.py (splash pot winnings)",
        note="Money the room adds to the pot from outside; read it together with profit.",
    ),
    "aof_summary": dict(
        formula="the markers seen over the observed all-ins, for example NFD×10 W9×8 air×4",
        sql="aof_obs and one counter per marker (aof_nfd, aof_wrap9, aof_pair…) from sql_queries_aof.py",
    ),
}

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
    xml = (ROOT / "fpdb_3_legacy" / "HUD_config.xml.example").read_text()
    titles = dict(re.findall(r'<col col_name="([^"]+)"[^>]*?col_title="([^"]*)"', xml))
    sql = (ROOT / "fpdb_3_legacy" / "sql_queries_player_detailed.py").read_text()
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
    for line in PT4_COVERAGE.read_text().splitlines():
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
    rng = random.Random(613)  # noqa: S311 - reproducible probing
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
        text = path.read_text(errors="ignore")
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


def measure_corpus() -> dict[str, Any]:
    """Parse every regression hand history and record which HandsPlayers columns get a value.

    The HUD sums these columns per game type, so a column never filled for a game
    family means the stats built on it show no data there.
    """
    import logging  # noqa: PLC0415

    from fpdb_3_legacy.Configuration import Config  # noqa: PLC0415
    from fpdb_3_legacy.DerivedStats import DerivedStats  # noqa: PLC0415
    from tests.test_live_parser_regression import CASES  # noqa: PLC0415

    logging.disable(logging.CRITICAL)
    try:
        config = Config()
        columns: dict[str, set[str]] = {base: set() for base in BASES}
        hands: dict[str, int] = {}
        categories: dict[str, set[str]] = {base: set() for base in BASES}
        positions: dict[str, set[str]] = {base: set() for base in BASES}
        for _key, parser_class, path in CASES:
            try:
                parsed = parser_class(config=config, in_path=str(path), autostart=True).getProcessedHands()
            except Exception:  # noqa: BLE001, S112 - a refused fixture is not a stat question
                continue
            for hand in parsed:
                base = hand.gametype.get("base")
                if base not in columns:
                    continue
                try:
                    stats = DerivedStats()
                    stats.getStats(hand)
                    rows = stats.getHandsPlayers()
                except Exception:  # noqa: BLE001, S112
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
        fixed = stats_guide_text.applies_override(entry["name"], entry["origin"])
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
                variants[base] = stats_guide_text.street_label(base, None)
            elif usable and all(c in filled[base] for c in usable) and needed_positions <= buckets[base]:
                variants[base] = stats_guide_text.street_label(base, street)
            else:
                variants[base] = ""
        entry["applies"] = {"games": stats_guide_text.games_for(entry), "variants": variants}


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
        "categories": {k: v for k, v in stat_catalog.CATEGORIES.items()},
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
        f"GUIDE = {body}\n"
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
            for label, value in stats_guide_text.applies_lines(entry, data["corpus"]):
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
        stale = DATA_FILE.read_text() != module or DOC_FILE.read_text() != markdown
        print("stale" if stale else "up to date")
        return 1 if stale else 0
    DATA_FILE.write_text(module)
    DOC_FILE.write_text(markdown)
    print(f"{len(data['stats'])} stats, {len(data['ring_columns'])} ring columns")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
