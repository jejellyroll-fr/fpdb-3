"""Composable stat/filter query engine over the analytics rows (#297).

The analytics epic stores, per decision: the normalized event (#293), the
named situation (#294), the board it was made against (#295) and the sizing
distribution (#296). What it does not have -- and what this module is -- is a
way to *ask a question* of those rows without writing a dedicated Python
function and a dedicated SQL string per stat.

The engine has three composable pieces:

* **Filters** name a condition on one of the joined tables -- ``street``,
  ``position``, ``facing_3bet``, ``board_texture``, ``effective_stack_bb`` and
  so on -- and every filter carries its own SQL translation. A query is a
  dict of them, and they AND together.
* **Metrics** name what to compute over the filtered population. A frequency
  metric returns its numerator *and* denominator (the issue is explicit that a
  frequency without its sample size is a lie); profit metrics sum the
  per-hand-player money over the distinct players in the population.
* **Dimensions** name what to group by, from the same vocabulary as the
  filters.

The engine compiles that to parameterized SQL. Values never become SQL text --
every one is bound through the backend's placeholder -- and identifiers come
only from the registries in this file, so a filter or dimension name that is
not declared is a ``ValueError``, not a query. The compiled statement (and a
readable description of it) is returned for inspection, which is what #303's
research browser will show and what makes a result explainable.

Units are the event model's: money in cents, sizing and frequencies in basis
points, effective stack in hundredths of a big blind (``docs/action-event-model.md``).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from .board_features import FLAG_BITS
from .hand_state import BLOCKER_BITS, DRAW_BITS
from .holdem_classes import class_ids as holdem_class_ids
from .holdem_classes import holdem_class_expression
from .sizing_buckets import bucket_case_expression
from .spr_buckets import spr_bucket_expression
from .stack_depth_buckets import stack_bucket_expression

# ---------------------------------------------------------------------------
# Sources: the tables a query can join, and how.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Source:
    """One table in the FROM clause, its alias and its join clause.

    ``join`` is relative to the fact alias ``A`` (``HandsActions``); an empty
    join means the source *is* the base. ``requires`` names the sources that
    must be joined first -- board features join on the situation's street, so
    they cannot be added without it.
    """

    alias: str
    table: str
    join: str = ""
    requires: tuple[str, ...] = ()


# Declaration order is join order: a source is only ever appended after the
# sources it requires, which is why ``requires`` pointing at SI is enough.
SOURCES: Final[dict[str, _Source]] = {
    "A": _Source("A", "HandsActions"),
    "H": _Source("H", "Hands", "JOIN Hands H ON H.id = A.handId", ("A",)),
    "G": _Source("G", "Gametypes", "JOIN Gametypes G ON G.id = H.gametypeId", ("H",)),
    "S": _Source("S", "Sites", "JOIN Sites S ON S.id = G.siteId", ("G",)),
    "P": _Source("P", "Players", "JOIN Players P ON P.id = A.playerId", ("A",)),
    "HP": _Source(
        "HP",
        "HandsPlayers",
        "LEFT JOIN HandsPlayers HP ON HP.handId = A.handId AND HP.playerId = A.playerId",
        ("A",),
    ),
    "SI": _Source(
        "SI",
        "HandsSituations",
        "LEFT JOIN HandsSituations SI ON SI.handId = A.handId AND SI.actionNo = A.actionNo",
        ("A",),
    ),
    # The postflop hand state of the acting player (#302), on the same key as the
    # situation: one row per *classified* decision, so the join is LEFT and a
    # decision with no cards shown simply has no state. That is the whole of
    # "unknown opponent cards are never classified": absence, not a bucket.
    "HS": _Source(
        "HS",
        "HandStates",
        "LEFT JOIN HandStates HS ON HS.handId = A.handId AND HS.actionNo = A.actionNo",
        ("A",),
    ),
    # The first board only: a run-it-twice hand stores a second set of rows and
    # joining it would double every decision. ``board_run`` can be added later
    # without changing this: the primary board is boardId 1.
    "BF": _Source(
        "BF",
        "BoardFeatures",
        "LEFT JOIN BoardFeatures BF ON BF.handId = A.handId AND BF.boardId = 1"
        " AND BF.streetName = SI.streetName",
        ("SI",),
    ),
}

BASE_ALIAS: Final = "A"


def _expand_sources(aliases: Iterable[str]) -> list[str]:
    """Close a set of aliases under ``requires``, in declaration order."""
    needed: set[str] = set()
    stack = list(aliases)
    while stack:
        alias = stack.pop()
        if alias in needed:
            continue
        if alias not in SOURCES:
            raise ValueError(f"Unknown query source: {alias!r}")
        needed.add(alias)
        stack.extend(SOURCES[alias].requires)
    return [alias for alias in SOURCES if alias in needed]


def _from_clause(needed: Sequence[str]) -> str:
    """The FROM clause for a closed alias set, base first and joins in order."""
    parts = [f"FROM {SOURCES[BASE_ALIAS].table} A"]
    for alias in needed:
        join = SOURCES[alias].join
        if join:
            parts.append(join)
    return "\n  ".join(parts)


# ---------------------------------------------------------------------------
# Value coercion: what a caller may write, and the shape it takes in SQL.
# ---------------------------------------------------------------------------


def _as_list(value: Any) -> list[Any]:
    """One value or a collection of values, as a list (strings stay whole)."""
    if isinstance(value, (str, bytes)):
        return [value]
    if isinstance(value, (list, tuple, set, frozenset)):
        return list(value)
    return [value]


def _as_range(value: Any) -> tuple[Any, Any]:
    """A ``[low, high]`` pair, either end optional (``None`` means unbounded)."""
    if isinstance(value, Mapping):
        return value.get("min"), value.get("max")
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return value[0], value[1]
    raise ValueError(f"A range filter needs [low, high] or {{min, max}}, not {value!r}")


# Button-relative seat names, as the hand viewer spells them: 0 is the button,
# the numbers count backwards through the late seats, and the blinds are the
# two negatives the event model already uses.
POSITION_CODES: Final[dict[str, int]] = {
    "btn": 0,
    "bu": 0,
    "button": 0,
    "d": 0,
    "co": 1,
    "cutoff": 1,
    "hj": 2,
    "hijack": 2,
    "lj": 3,
    "lojack": 3,
    "mp": 4,
    "mp1": 4,
    "mp2": 5,
    "utg": 6,
    "sb": -1,
    "small blind": -1,
    "smallblind": -1,
    "bb": -2,
    "big blind": -2,
    "bigblind": -2,
}

# The words a sizing filter may be written in. Per cent of the pot is what a
# player says out loud; basis points are what the rows store.
_PCT_TO_BP: Final = 100


def _positions(values: Any) -> list[int]:
    """Position names or codes to the integer codes the rows store."""
    out: list[int] = []
    for value in _as_list(values):
        if isinstance(value, bool):
            raise ValueError(f"Not a position: {value!r}")
        if isinstance(value, int):
            out.append(value)
            continue
        text = str(value).strip().lower()
        if text in POSITION_CODES:
            out.append(POSITION_CODES[text])
            continue
        try:
            out.append(int(text))
        except ValueError:
            raise ValueError(
                f"Unknown position {value!r}; use a code or one of {sorted(POSITION_CODES)}",
            ) from None
    return out


def _to_bp(values: Any) -> list[int]:
    """Per-cent sizing bounds to the basis points the rows store."""
    out: list[int] = []
    for value in values:
        if value is None:
            out.append(None)  # type: ignore[arg-type]  # an unbounded range end
            continue
        out.append(int(round(float(value) * _PCT_TO_BP)))
    return out


# ---------------------------------------------------------------------------
# Filters.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Filter:
    """One composable condition: where it reads, and how a value becomes SQL.

    ``kind`` picks the translation: ``scalar`` (equality), ``set`` (IN),
    ``range`` (inclusive bounds, either optional), ``bool`` (a boolean column),
    ``null_check`` (a foreign key: True means "set", False "null"),
    ``hero`` (a nullable situation boolean where False keeps unknown rows),
    ``identity_set`` (an OR of site/name pairs),
    ``flagset``/``flagset_all``/``flagset_none`` (a bitmask column matched
    against named flags -- any, all or none of them) and ``pattern``
    (JSON text containing a quoted word, e.g. a situation label).
    """

    column: str
    aliases: tuple[str, ...]
    kind: str = "scalar"
    coerce: Any = None
    # The flag vocabulary a ``flagset`` filter matches against, and what to call
    # it when a name is not in it. ``None`` means the board texture flags.
    bits: Mapping[str, int] | None = None
    vocabulary: str = "board flag"


def _flag_bits(names: Any, bits: Mapping[str, int] | None = None, vocabulary: str = "board flag") -> list[int]:
    """Named texture/runout flags to their bits, refusing unknown names.

    ``bits`` is the vocabulary the column was written with -- the board texture
    flags (#295) or the draw and blocker flags of a hand state (#302). A filter
    that guessed the wrong vocabulary would match bits that mean something else
    entirely, so an unknown name is refused rather than silently zero.
    """
    known = bits if bits is not None else FLAG_BITS
    out: list[int] = []
    for name in _as_list(names):
        key = str(name).strip().lower()
        if key not in known:
            raise ValueError(f"Unknown {vocabulary} {name!r}; known: {sorted(known)}")
        out.append(known[key])
    return out


FILTERS: Final[dict[str, _Filter]] = {
    # -- hand / game identity ----------------------------------------------
    "site": _Filter("S.name", ("S",), "set"),
    "game": _Filter("G.category", ("G",), "set"),
    "limit": _Filter("G.limitType", ("G",), "set"),
    "currency": _Filter("G.currency", ("G",), "set"),
    "tournament": _Filter("H.tourneyId", ("H",), "null_check"),
    "tournament_id": _Filter("H.tourneyId", ("H",), "set"),
    "big_blind": _Filter("G.bigBlind", ("G",), "range"),
    "stake_bb": _Filter("G.bigBlind", ("G",), "range"),
    "seats": _Filter("H.seats", ("H",), "range"),
    "max_seats": _Filter("G.maxSeats", ("G",), "range"),
    "session": _Filter("H.sessionId", ("H",), "set"),
    "hand_id": _Filter("A.handId", ("A",), "set"),
    # A hand-id range, for callers that scan forward from a watermark instead
    # of naming every id: the incremental aggregate cache (#304) does exactly
    # that after an import.
    "hand_id_from": _Filter("A.handId", ("A",), "range_low"),
    "hand_id_to": _Filter("A.handId", ("A",), "range_high"),
    "date_from": _Filter("H.startTime", ("H",), "range_low"),
    "date_to": _Filter("H.startTime", ("H",), "range_high"),
    # -- who ---------------------------------------------------------------
    "player": _Filter("P.name", ("P",), "set"),
    "players": _Filter("P.name", ("P",), "set"),
    # A linked identity is a (site, alias) pair, not a bare name: the same
    # screen name on two rooms is two different people. The filter is an OR of
    # pairs, which is why it needs its own kind rather than the ``set`` shape.
    "identity": _Filter("P.name", ("P", "S"), "identity_set"),
    "hero": _Filter("SI.isHero", ("SI",), "hero"),
    # -- seat / stack ------------------------------------------------------
    "position": _Filter("A.position", ("A",), "set", _positions),
    "opponent_position": _Filter("SI.facingPosition", ("SI",), "set", _positions),
    "relative_position": _Filter("A.relativePosition", ("A",), "range"),
    "in_position": _Filter("A.inPosition", ("A",), "bool"),
    "effective_stack_bb": _Filter("A.effectiveStackBB", ("A",), "range"),
    "effective_stack": _Filter("A.effectiveStack", ("A",), "range"),
    "stack_bucket": _Filter("SI.stackBucket", ("SI",), "set"),
    # The tournament bands over the same effective stack the range filter
    # reads: a depth is a band in an MTT, and short/medium/deep is too
    # coarse to tell 12 big blinds from 22 (#369).
    "effective_stack_bucket": _Filter(stack_bucket_expression("A."), ("A",), "set"),
    "spr": _Filter("A.sprBefore", ("A",), "range"),
    # The banded form of the same column: a panel groups by bands, a query
    # narrows by them, and both read the one CASE expression (#368).
    "spr_bucket": _Filter(spr_bucket_expression("A."), ("A",), "set"),
    "players_in_hand": _Filter("A.playersInHand", ("A",), "range"),
    "multiway": _Filter("SI.multiway", ("SI",), "bool"),
    # -- street / pot ------------------------------------------------------
    "street": _Filter("SI.streetName", ("SI",), "set"),
    "street_index": _Filter("A.street", ("A",), "range"),
    "pot_type": _Filter("SI.potType", ("SI",), "set"),
    "pot_before": _Filter("A.potBefore", ("A",), "range"),
    "to_call": _Filter("A.toCall", ("A",), "range"),
    "pot_odds_bp": _Filter("SI.potOddsBp", ("SI",), "range"),
    # -- role / aggressor --------------------------------------------------
    "role": _Filter("SI.role", ("SI",), "set"),
    "is_aggressor": _Filter("SI.isAggressor", ("SI",), "bool"),
    "is_preflop_aggressor": _Filter("SI.isPreflopAggressor", ("SI",), "bool"),
    "is_previous_aggressor": _Filter("SI.isPreviousAggressor", ("SI",), "bool"),
    "in_position_vs_previous_aggressor": _Filter(
        "SI.inPositionVsPreviousAggressor", ("SI",), "bool",
    ),
    "in_position_vs_facing": _Filter("SI.inPositionVsFacing", ("SI",), "bool"),
    "facing_all_in": _Filter("SI.facingAllIn", ("SI",), "bool"),
    # -- actions -----------------------------------------------------------
    "action_taken": _Filter("A.actionType", ("A",), "set"),
    "action_faced": _Filter("A.facingActionType", ("A",), "set"),
    "response": _Filter("SI.response", ("SI",), "set"),
    "all_in": _Filter("A.allIn", ("A",), "bool"),
    "situation": _Filter("SI.labels", ("SI",), "label"),
    "primary_situation": _Filter("SI.primaryLabel", ("SI",), "set"),
    "situation_group": _Filter("SI.groupName", ("SI",), "set"),
    "enum_key": _Filter("SI.enumKey", ("SI",), "set"),
    "enum_response": _Filter("SI.enumResponse", ("SI",), "set"),
    "raisers_before": _Filter("SI.raisesBefore", ("SI",), "range"),
    # -- hole cards --------------------------------------------------------
    # The 169 Hold'em classes, as the canonical id of ``Card.twoStartCards``
    # (#301). The filter takes labels or ids, and the same expression answers
    # both, so a grid cell and a drill-down cannot disagree about a class.
    "starting_hand": _Filter(holdem_class_expression("HP."), ("HP",), "set", holdem_class_ids),
    # Whether the pot-winning hand was shown at all. A range over hands whose
    # cards were never revealed is not a range: this is how a caller says "only
    # the cards that actually exist", without the engine inventing any.
    "hole_cards_known": _Filter("(HP.card1 > 0 AND HP.card2 > 0)", ("HP",), "bool"),
    # -- sizing ------------------------------------------------------------
    "sizing_bp": _Filter("A.sizingBp", ("A",), "range"),
    "facing_sizing_bp": _Filter("A.facingSizingBp", ("A",), "range"),
    # The bucket *names* #296 groups by, as filters. Grouping by a bucket and
    # then asking for the hands in one row is the drill-down of a sizing
    # distribution (#300), and it must select the same rows the histogram
    # counted, so the two read the same CASE expression.
    "sizing_bucket": _Filter(bucket_case_expression("sizingBp", qualifier="A."), ("A",), "set"),
    "facing_sizing_bucket": _Filter(
        bucket_case_expression("facingSizingBp", qualifier="A."), ("A",), "set",
    ),
    "bet_sizing_pct": _Filter("A.sizingBp", ("A",), "range_pct"),
    "facing_sizing_pct": _Filter("A.facingSizingBp", ("A",), "range_pct"),
    # -- board -------------------------------------------------------------
    "board_rank": _Filter("BF.rankBucket", ("BF",), "set"),
    "board_suit": _Filter("BF.suitStructure", ("BF",), "set"),
    "board_pairing": _Filter("BF.pairing", ("BF",), "set"),
    "board_connectivity": _Filter("BF.connectivity", ("BF",), "set"),
    "board_present": _Filter("BF.handId", ("BF",), "null_check"),
    "board_texture": _Filter("BF.textureMask", ("BF",), "flagset"),
    "board_texture_all": _Filter("BF.textureMask", ("BF",), "flagset_all"),
    "board_runout": _Filter("BF.runoutMask", ("BF",), "flagset"),
    "board_street": _Filter("BF.street", ("BF",), "range"),
    # -- hand state (#302) -------------------------------------------------
    # What the acting player was holding, from the classifier's own vocabulary.
    # The two masks read the same bits the stored rows were written with, so a
    # filter and the composition report over the same column cannot disagree
    # about which decisions a draw contains.
    "made_hand": _Filter("HS.madeHand", ("HS",), "set"),
    "made_hand_rank": _Filter("HS.madeHandRank", ("HS",), "range"),
    "pair_detail": _Filter("HS.pairDetail", ("HS",), "set"),
    "nutness": _Filter("HS.nutness", ("HS",), "set"),
    "nutness_beats": _Filter("HS.nutnessBeats", ("HS",), "range"),
    "nutness_holdings": _Filter("HS.nutnessHoldings", ("HS",), "range"),
    "draw": _Filter("HS.drawsMask", ("HS",), "flagset", bits=DRAW_BITS, vocabulary="draw"),
    "draw_all": _Filter("HS.drawsMask", ("HS",), "flagset_all", bits=DRAW_BITS, vocabulary="draw"),
    "draw_none": _Filter("HS.drawsMask", ("HS",), "flagset_none", bits=DRAW_BITS, vocabulary="draw"),
    "blocker": _Filter("HS.blockersMask", ("HS",), "flagset", bits=BLOCKER_BITS, vocabulary="blocker"),
    "blocker_all": _Filter("HS.blockersMask", ("HS",), "flagset_all", bits=BLOCKER_BITS, vocabulary="blocker"),
    "blocker_none": _Filter("HS.blockersMask", ("HS",), "flagset_none", bits=BLOCKER_BITS, vocabulary="blocker"),
    "hand_state_street": _Filter("HS.streetName", ("HS",), "set"),
    # Whether this decision was classified at all. False is "the cards were never
    # known, or there was no board yet" -- one fact, and the population an
    # honest range-composition has to report rather than hide.
    "hand_state_known": _Filter("HS.madeHand", ("HS",), "null_check"),
}

# Filters whose value is a label present in the situation's JSON ``labels``
# text. The pattern is bound as a parameter -- the word is never concatenated
# into the SQL -- so a label name cannot smuggle syntax.
_LABEL_PATTERN: Final = '%"{}"%'


def _set_fragment(column: str, values: list[Any], placeholder: str) -> tuple[list[str], list[Any]]:
    """Equality for one value, ``IN`` for several, no rows for an empty set."""
    if not values:
        return ["1=0"], []
    if len(values) == 1:
        return [f"{column} = {placeholder}"], [values[0]]
    marks = ", ".join(placeholder for _ in values)
    return [f"{column} IN ({marks})"], list(values)


def _range_fragment(column: str, low: Any, high: Any, placeholder: str) -> tuple[list[str], list[Any]]:
    """Inclusive bounds, either end optional."""
    fragments: list[str] = []
    params: list[Any] = []
    if low is not None:
        fragments.append(f"{column} >= {placeholder}")
        params.append(low)
    if high is not None:
        fragments.append(f"{column} <= {placeholder}")
        params.append(high)
    return (["(" + " AND ".join(fragments) + ")"] if fragments else []), params


def _range_for(
    kind: str,
    column: str,
    value: Any,
    placeholder: str,
) -> tuple[list[str], list[Any]]:
    """A range filter in its four shapes: pair, pair of per cents, or one bound."""
    if kind == "range_low":
        return _range_fragment(column, value, None, placeholder)
    if kind == "range_high":
        return _range_fragment(column, None, value, placeholder)
    low, high = _as_range(value)
    if kind == "range_pct":
        low, high = _to_bp((low, high))
    return _range_fragment(column, low, high, placeholder)


def _flag_fragment(
    column: str,
    kind: str,
    value: Any,
    spec: _Filter | None = None,
) -> tuple[list[str], list[Any]]:
    """Named flags matched against a bitmask column, in the filter's vocabulary.

    Three shapes: any of the named bits, all of them, or none of them. ``None``
    is what a caller asks for with ``True`` -- "no draw at all" is a real
    population, and it is the one a share of *something* has to be subtracted
    from, so it is a filter rather than arithmetic on two other results.
    """
    spec = spec or _Filter(column, ())
    known = spec.bits if spec.bits is not None else FLAG_BITS
    bits = list(known.values()) if kind == "flagset_none" and value is True else _flag_bits(
        value,
        spec.bits,
        spec.vocabulary,
    )
    if not bits:
        # Nothing named: "any of nothing" matches nothing, "none of nothing"
        # excludes nothing.
        return (["1=1"], []) if kind == "flagset_none" else (["1=0"], [])
    if kind == "flagset_none":
        mask = 0
        for bit in bits:
            mask |= bit
        return [f"({column} & {mask}) = 0"], []
    joiner = " AND " if kind == "flagset_all" else " OR "
    fragments = [f"({column} & {bit}) <> 0" for bit in bits]
    return ["(" + joiner.join(fragments) + ")"], []


def _label_fragment(column: str, value: Any, placeholder: str) -> tuple[list[str], list[Any]]:
    """A word present in the situation's JSON list, matched with quotes."""
    fragments: list[str] = []
    params: list[Any] = []
    for label in _as_list(value):
        fragments.append(f"{column} LIKE {placeholder}")
        params.append(_LABEL_PATTERN.format(label))
    if not fragments:
        return ["1=0"], []
    return ["(" + " OR ".join(fragments) + ")"], params


def _identity_pairs(value: Any) -> list[tuple[str, str]]:
    """``(site, alias)`` pairs from a mapping, ``"Site:alias"`` or 2-sequences."""
    if isinstance(value, Mapping):
        return [(str(site), str(alias)) for site, alias in value.items()]
    pairs: list[tuple[str, str]] = []
    for entry in _as_list(value):
        if isinstance(entry, str):
            site, separator, alias = entry.partition(":")
            if not separator or not site.strip() or not alias.strip():
                raise ValueError(f"An identity {entry!r} must read 'Site:alias'")
            pairs.append((site.strip(), alias.strip()))
        elif isinstance(entry, (list, tuple)) and len(entry) == 2:
            pairs.append((str(entry[0]), str(entry[1])))
        else:
            raise ValueError(f"An identity must be a 'Site:alias' or a (site, alias) pair, got {entry!r}")
    return pairs


def _identity_fragment(value: Any, placeholder: str) -> tuple[list[str], list[Any]]:
    """Compile linked identities as parameterized site/name pairs."""
    pairs = _identity_pairs(value)
    if not pairs:
        return ["1=0"], []
    fragments = [f"(S.name = {placeholder} AND P.name = {placeholder})" for _site, _alias in pairs]
    params = [part for pair in pairs for part in pair]
    return ["(" + " OR ".join(fragments) + ")"], params


def _compile_filter(
    name: str,
    value: Any,
    placeholder: str,
    backend: str,
) -> tuple[list[str], list[Any]]:
    """One filter to (SQL fragments, bound parameters)."""
    spec = FILTERS.get(name)
    if spec is None:
        raise ValueError(f"Unknown filter {name!r}; known filters: {sorted(FILTERS)}")
    column = spec.column
    # ``None`` traditionally means "no filter" to callers. Drill-downs need
    # an explicit null predicate, so they use this structured value instead of
    # changing that public convention.
    if isinstance(value, Mapping) and set(value) == {"is_null"}:
        if name == "pair_detail" and value["is_null"]:
            # A NULL pair detail is a real "no pair" classification only when
            # the hand-state join exists. Unknown cards have no HandStates row
            # and must not be pulled into the no-pair bucket (#364).
            return [f"{column} IS NULL", "HS.madeHand IS NOT NULL"], []
        return [f"{column} IS {'NULL' if value['is_null'] else 'NOT NULL'}"], []
    if spec.kind in ("scalar", "set"):
        values = _as_list(value)
        values = spec.coerce(values) if spec.coerce is not None else values
        return _set_fragment(spec.column, values, placeholder)
    if spec.kind in ("range", "range_pct", "range_low", "range_high"):
        return _range_for(spec.kind, column, value, placeholder)
    return _compile_condition_filter(name, spec, value, placeholder, backend)


# The kinds whose value is not a set or a range: booleans, flags, labels and
# identities. Split from the shape dispatch above so neither function has to
# know every kind the other one handles.
_FLAG_KINDS: Final = ("flagset", "flagset_all", "flagset_none")


def _compile_condition_filter(
    name: str,
    spec: _Filter,
    value: Any,
    placeholder: str,
    backend: str,
) -> tuple[list[str], list[Any]]:
    """The condition-shaped filter kinds, not the set or range shapes."""
    column = spec.column
    if spec.kind in ("bool", "hero"):
        return _boolean_fragment(column, bool(value), spec.kind == "hero", backend)
    if spec.kind == "null_check":
        return ([f"{column} IS NOT NULL"] if value else [f"{column} IS NULL"]), []
    if spec.kind in _FLAG_KINDS:
        return _flag_fragment(column, spec.kind, value, spec)
    if spec.kind == "identity_set":
        return _identity_fragment(value, placeholder)
    if spec.kind == "label":
        return _label_fragment(column, value, placeholder)
    raise ValueError(f"Unknown filter kind for {name!r}: {spec.kind!r}")


def _boolean_fragment(column: str, value: bool, keep_unknown: bool, backend: str) -> tuple[list[str], list[Any]]:
    """A boolean condition, optionally keeping rows the join could not classify.

    ``keep_unknown`` is what makes ``hero: False`` usable for a population: the
    situation join is a ``LEFT JOIN``, and "we do not know this actor" is not
    "this actor is the hero". ``hero: True`` still requires the situation row.
    """
    literal = "1" if backend == "sqlite" else "TRUE"
    if value:
        return [f"{column} = {literal}"], []
    if keep_unknown:
        return [f"({column} IS NULL OR NOT {column} = {literal})"], []
    return [f"(NOT {column} = {literal})"], []


def compile_filters(
    filters: Mapping[str, Any],
    placeholder: str = "%s",
    backend: str = "mysql",
) -> tuple[list[str], list[Any], set[str]]:
    """Translate a filter dict to (conditions, parameters, needed sources)."""
    conditions: list[str] = []
    params: list[Any] = []
    aliases: set[str] = set()
    for name, value in filters.items():
        if value is None:
            continue
        fragments, values = _compile_filter(name, value, placeholder, backend)
        conditions.extend(fragments)
        params.extend(values)
        aliases.update(FILTERS[name].aliases)
    return conditions, params, aliases


def filter_sources(filters: Mapping[str, Any]) -> set[str]:
    """The sources a filter dict reads, for callers planning joins."""
    return {alias for name in filters for alias in FILTERS[name].aliases}


# ---------------------------------------------------------------------------
# Dimensions.
# ---------------------------------------------------------------------------

# A dimension is a grouped expression plus the sources it reads. The bucket
# dimensions reuse #296's CASE expression, so a histogram from Python and one
# from the database group by exactly the same boundaries.
DIMENSIONS: Final[dict[str, tuple[str, tuple[str, ...]]]] = {
    "street": ("SI.streetName", ("SI",)),
    "position": ("A.position", ("A",)),
    "opponent_position": ("SI.facingPosition", ("SI",)),
    "relative_position": ("A.relativePosition", ("A",)),
    "in_position": ("A.inPosition", ("A",)),
    "stack_bucket": ("SI.stackBucket", ("SI",)),
    "effective_stack_bb": ("A.effectiveStackBB", ("A",)),
    "effective_stack_bucket": (stack_bucket_expression("A."), ("A",)),
    "spr": ("A.sprBefore", ("A",)),
    "spr_bucket": (spr_bucket_expression("A."), ("A",)),
    "pot_type": ("SI.potType", ("SI",)),
    "role": ("SI.role", ("SI",)),
    "response": ("SI.response", ("SI",)),
    "action_taken": ("A.actionType", ("A",)),
    "action_faced": ("A.facingActionType", ("A",)),
    "all_in": ("A.allIn", ("A",)),
    "multiway": ("SI.multiway", ("SI",)),
    "player": ("P.name", ("P",)),
    "site": ("S.name", ("S",)),
    "game": ("G.category", ("G",)),
    "limit": ("G.limitType", ("G",)),
    "tournament": ("H.tourneyId", ("H",)),
    "session": ("H.sessionId", ("H",)),
    # Qualified with the fact alias: ``facingSizingBp`` exists on the situation
    # table too, so an unqualified reference is ambiguous once it is joined.
    "sizing_bucket": (bucket_case_expression("sizingBp", qualifier="A."), ("A",)),
    "facing_sizing_bucket": (bucket_case_expression("facingSizingBp", qualifier="A."), ("A",)),
    "board_rank": ("BF.rankBucket", ("BF",)),
    "board_suit": ("BF.suitStructure", ("BF",)),
    "board_pairing": ("BF.pairing", ("BF",)),
    "board_connectivity": ("BF.connectivity", ("BF",)),
    "primary_situation": ("SI.primaryLabel", ("SI",)),
    "enum_key": ("SI.enumKey", ("SI",)),
    # The starting-hand class of the acting player's own cards: the 13x13 grid's
    # dimension (#301). It is the class *id* -- the ``StartCards`` primary key,
    # 170 for "cards not known" -- because a label-valued dimension would need
    # 169 SQL branches to agree with ``Card.twoStartCardString``.
    "starting_hand_id": (holdem_class_expression("HP."), ("HP",)),
    # The hand state dimensions (#302): what the acting player held. Grouped
    # straight off the stored columns, so a composition and a drill-down group
    # the same rows the classifier wrote.
    "made_hand": ("HS.madeHand", ("HS",)),
    "made_hand_rank": ("HS.madeHandRank", ("HS",)),
    "pair_detail": ("HS.pairDetail", ("HS",)),
    "nutness": ("HS.nutness", ("HS",)),
    "hand_state_street": ("HS.streetName", ("HS",)),
}


def _dimension(name: str) -> tuple[str, tuple[str, ...]]:
    if name not in DIMENSIONS:
        raise ValueError(f"Unknown group_by dimension {name!r}; known: {sorted(DIMENSIONS)}")
    return DIMENSIONS[name]


_RESERVED_DIMENSION_NAMES: Final[frozenset[str]] = frozenset({"limit", "offset", "order", "group"})


def _alias_of(name: str) -> str:
    """The safe result-column name used for a grouped dimension."""
    return f"{name}_" if name in _RESERVED_DIMENSION_NAMES else name


def _dimension_alias(name: str) -> str:
    """The SQL alias for a grouped dimension."""
    return _alias_of(name)


# ---------------------------------------------------------------------------
# Metrics.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Metric:
    """What a metric computes over the filtered population.

    ``value_sql`` is an aggregate over the fact rows (``None`` means "count the
    rows matching the numerator filters"). ``player_expression`` marks a
    metric whose money is per hand-player: it is summed over the *distinct*
    (handId, playerId) pairs in the filtered population, so three decisions by
    one player do not triple their profit. ``per_opportunity`` divides that
    sum by the decision count, which is what "profit per opportunity" means.

    ``distinct_hands`` marks a frequency whose population is counted in *hands*
    rather than in decisions. The two disagree exactly when a player acts more
    than once in the street being counted -- call a raise preflop and you made
    two decisions but entered one hand -- which is why the classic rates (VPIP,
    PFR) are per hand: counting their decisions would report a player who
    called a raise after limping as two voluntary entries.
    """

    name: str
    unit: str
    value_sql: str | None = None
    frequency: bool = False
    distinct_hands: bool = False
    player_expression: str | None = None
    per_opportunity: bool = False
    ready: bool = True


METRICS: Final[dict[str, _Metric]] = {
    "opportunities": _Metric("opportunities", "count", value_sql="COUNT(*)"),
    # The population spread of a filtered set (#307): the decision count is the
    # engine's native denominator, but a population is also described by how
    # many hands and how many distinct players those decisions came from. Both
    # are distinct counts, so they must not be read as the row count.
    "hands": _Metric("hands", "count", value_sql="COUNT(DISTINCT A.handId)"),
    "players": _Metric("players", "count", value_sql="COUNT(DISTINCT A.playerId)"),
    "action_count": _Metric("action_count", "count"),
    "frequency": _Metric("frequency", "bp", frequency=True),
    # The per-hand frequency: the same numerator as ``frequency``, but over the
    # hands it happened in rather than over the decisions it happened on. It is
    # what a rate means when a player can act twice in the counted street --
    # VPIP and PFR, the two stats every HUD has shown this way for twenty years.
    "hand_frequency": _Metric("hand_frequency", "bp", frequency=True, distinct_hands=True),
    "average_sizing": _Metric(
        "average_sizing",
        "bp",
        value_sql="AVG(CASE WHEN A.sizingBp > 0 THEN A.sizingBp END)",
    ),
    "average_facing_sizing": _Metric(
        "average_facing_sizing",
        "bp",
        value_sql="AVG(CASE WHEN A.facingSizingBp > 0 THEN A.facingSizingBp END)",
    ),
    "average_spr": _Metric("average_spr", "centi", value_sql="AVG(A.sprBefore)"),
    "average_pot": _Metric("average_pot", "cents", value_sql="AVG(A.potBefore)"),
    "total_profit": _Metric("total_profit", "cents", player_expression="HP.totalProfit"),
    "profit_per_opportunity": _Metric(
        "profit_per_opportunity", "cents", player_expression="HP.totalProfit", per_opportunity=True,
    ),
    "all_in_ev": _Metric("all_in_ev", "cents", player_expression="HP.allInEV"),
    "ev_per_opportunity": _Metric(
        "ev_per_opportunity", "cents", player_expression="HP.allInEV", per_opportunity=True,
    ),
}

# Named frequency metrics carry their numerator so the caller does not have to
# restate it. ``frequency`` itself takes the numerator from the query, which is
# how an unanticipated split ("fold to a check-raise by a short stack") stays
# expressible without a new metric.
IMPLIED_NUMERATORS: Final[dict[str, dict[str, Any]]] = {
    "fold_frequency": {"response": "fold"},
    "call_frequency": {"response": "call"},
    "raise_frequency": {"response": ["raise", "complete"]},
    "bet_frequency": {"response": "bet"},
    "check_frequency": {"response": "check"},
    # How often a decision went all-in. The numerator is the act rather than a
    # response token, because a shove can be a bet, a raise or a call and all
    # three are the same event to a tournament player (#369).
    "all_in_frequency": {"all_in": True},
}

KNOWN_METRICS: Final[tuple[str, ...]] = tuple(
    sorted(set(METRICS) | set(IMPLIED_NUMERATORS)),
)


# ---------------------------------------------------------------------------
# The query and its compiled form.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Query:
    """A metric, its filters, the dimensions to group by and a page window."""

    metric: str
    filters: Mapping[str, Any] = field(default_factory=dict)
    numerator: Mapping[str, Any] = field(default_factory=dict)
    group_by: tuple[str, ...] = ()
    limit: int | None = None
    offset: int = 0

    def resolved(self) -> tuple[_Metric, dict[str, Any], dict[str, Any]]:
        """The metric spec, the filters and the numerator, with implied parts added."""
        if self.metric in IMPLIED_NUMERATORS:
            spec = METRICS["frequency"]
            numerator = {**IMPLIED_NUMERATORS[self.metric], **self.numerator}
        elif self.metric in METRICS:
            spec = METRICS[self.metric]
            numerator = dict(self.numerator)
        else:
            raise ValueError(f"Unknown metric {self.metric!r}; known metrics: {list(KNOWN_METRICS)}")
        return spec, dict(self.filters), numerator


@dataclass(frozen=True)
class CompiledQuery:
    """A compiled query: the SQL, its parameters and a readable description."""

    sql: str
    params: tuple[Any, ...]
    group_by: tuple[str, ...]
    metric: str
    player_sql: str | None = None
    player_params: tuple[Any, ...] = ()
    description: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "group_by": list(self.group_by),
            "sql": self.sql,
            "params": list(self.params),
            "player_sql": self.player_sql,
            "player_params": list(self.player_params),
            "description": self.description,
        }


def _describe(
    metric: str,
    filters: Mapping[str, Any],
    numerator: Mapping[str, Any],
    group_by: tuple[str, ...],
    limit: int | None,
    offset: int,
) -> str:
    """A readable rendering of what the query asks, for logs and the browser."""
    lines = [f"metric: {metric}"]
    if filters:
        rendered = ", ".join(f"{name}={value!r}" for name, value in sorted(filters.items()))
        lines.append(f"filters: {rendered}")
    if numerator:
        rendered = ", ".join(f"{name}={value!r}" for name, value in sorted(numerator.items()))
        lines.append(f"numerator: {rendered}")
    lines.append(f"group_by: {', '.join(group_by) if group_by else '(none)'}")
    if limit is not None:
        lines.append(f"page: limit={limit} offset={offset}")
    return "\n".join(lines)


def compile_query(
    query: Query,
    placeholder: str = "%s",
    backend: str = "mysql",
) -> CompiledQuery:
    """Translate a :class:`Query` into parameterized SQL, nothing executed."""
    if backend not in ("mysql", "postgresql", "sqlite"):
        raise ValueError(f"Unknown backend {backend!r}")
    spec, filters, numerator = query.resolved()

    where, where_params, aliases = compile_filters(filters, placeholder, backend)
    # The numerator's own filters are part of the join graph: ``fold_frequency``
    # counts ``SI.response`` even when the caller's filters never mention the
    # situation table, and a condition on an unjoined alias is invalid SQL.
    numerator_conditions, numerator_params, numerator_aliases = compile_filters(numerator, placeholder, backend)
    aliases.update(numerator_aliases)
    for dimension in query.group_by:
        _expression, dimension_aliases = _dimension(dimension)
        aliases.update(dimension_aliases)

    needed = _expand_sources(aliases | {"A"})
    from_clause = _from_clause(needed)

    params: list[Any] = []
    select: list[str] = []
    group_expressions: list[str] = []
    for dimension in query.group_by:
        expression, _ = _dimension(dimension)
        select.append(f"{expression} AS {_dimension_alias(dimension)}")
        group_expressions.append(expression)

    select.append(
        "COUNT(DISTINCT A.handId) AS opportunities" if spec.distinct_hands else "COUNT(*) AS opportunities",
    )

    case_conditions = [f"({condition})" for condition in numerator_conditions]
    case_condition = " AND ".join(case_conditions) if case_conditions else "1=1"
    params.extend(numerator_params)
    if spec.value_sql is not None:
        select.append(f"{spec.value_sql} AS value")
    elif spec.distinct_hands:
        select.append(f"COUNT(DISTINCT CASE WHEN {case_condition} THEN A.handId END) AS actions")
    else:
        select.append(f"SUM(CASE WHEN {case_condition} THEN 1 ELSE 0 END) AS actions")

    sql_parts = ["SELECT\n  " + ",\n  ".join(select), from_clause]
    if where:
        sql_parts.append("WHERE " + " AND ".join(f"({condition})" for condition in where))
    if group_expressions:
        sql_parts.append("GROUP BY " + ", ".join(group_expressions))
        sql_parts.append("ORDER BY " + ", ".join(_dimension_alias(name) for name in query.group_by))
    params.extend(where_params)
    if query.limit is not None:
        sql_parts.append(f"LIMIT {placeholder}")
        params.append(int(query.limit))
        sql_parts.append(f"OFFSET {placeholder}")
        params.append(int(query.offset))
    sql = "\n".join(sql_parts)
    player_sql: str | None = None
    player_params: list[Any] = []
    if spec.player_expression is not None:
        # Sum the money over the distinct (handId, playerId) pairs the filters
        # select: a player's hand profit is a property of the hand, not of each
        # decision they made in it.
        inner_group = [f"{_dimension(name)[0]} AS {name}" for name in query.group_by]
        inner_select = ", ".join([*inner_group, "A.handId AS handId", "A.playerId AS playerId"])
        inner_where = " AND ".join(f"({condition})" for condition in where) or "1=1"
        player_columns = [f"P.{name}" for name in query.group_by]
        player_sql = "\n".join(
            [
                "SELECT\n  " + (",\n  ".join(player_columns + [f"SUM(HP.{_player_column(spec)}) AS value"]))
                if player_columns
                else f"SELECT SUM(HP.{_player_column(spec)}) AS value",
                "FROM (",
                f"  SELECT DISTINCT {inner_select}",
                f"  {from_clause}",
                f"  WHERE {inner_where}",
                ") P",
                "JOIN HandsPlayers HP ON HP.handId = P.handId AND HP.playerId = P.playerId",
                ("GROUP BY " + ", ".join(player_columns)) if player_columns else "",
            ],
        )
        player_params.extend(where_params)

    return CompiledQuery(
        sql=escape_literal_percent(sql, placeholder),
        params=tuple(params),
        group_by=tuple(query.group_by),
        metric=query.metric,
        player_sql=escape_literal_percent(player_sql, placeholder) if player_sql is not None else None,
        player_params=tuple(player_params),
        description=_describe(query.metric, filters, numerator, tuple(query.group_by), query.limit, query.offset),
    )


def _player_column(spec: _Metric) -> str:
    """The HandsPlayers column a player-scoped metric sums."""
    if spec.player_expression is None:
        raise ValueError(f"Metric {spec.name!r} has no player expression")
    return spec.player_expression.split(".", 1)[1]


def escape_literal_percent(sql: str, placeholder: str) -> str:
    """Double a literal ``%`` when the driver reads ``%`` as a placeholder.

    psycopg and MySQLdb take pyformat/format parameters, so every ``%`` in a
    statement starts a placeholder unless it is doubled. The Hold'em class
    dimension is written with the modulo operator -- ``(card - 1) % 13`` -- so
    any query grouped by starting hand, which is the range explorer's whole
    purpose, reached psycopg as::

        ProgrammingError: incomplete placeholder: '%'

    SQLite's ``?`` parameters leave ``%`` alone, which is why this only ever
    failed against a real PostgreSQL database and never in the test suite.

    The placeholders the compiler inserted are protected first, so only the
    operators around them are doubled.
    """
    if "%" not in placeholder:
        return sql
    marker = "\x00"
    return sql.replace(placeholder, marker).replace("%", "%%").replace(marker, placeholder)


def compile_hand_ids(
    query: Query,
    placeholder: str = "%s",
    backend: str = "mysql",
    include_numerator: bool = False,
) -> CompiledQuery:
    """The matching hand ids, distinct and ordered -- the drill-down query.

    The hands behind a result row are the *population* the metric was computed
    over (the denominator), not only the hands where the numerator fired: a
    fold frequency is "these hands, of which N folds". Pass
    ``include_numerator=True`` to narrow to the numerator.
    """
    _spec, filters, numerator = query.resolved()
    if include_numerator:
        filter_where, filter_params, filter_aliases = compile_filters(filters, placeholder, backend)
        numerator_where, numerator_params, numerator_aliases = compile_filters(numerator, placeholder, backend)
        where = [*filter_where, *numerator_where]
        where_params = [*filter_params, *numerator_params]
        aliases = filter_aliases | numerator_aliases
        combined = {**filters, **numerator}
    else:
        combined = dict(filters)
        where, where_params, aliases = compile_filters(combined, placeholder, backend)
    needed = _expand_sources(aliases | {"A"})
    sql_parts = [
        "SELECT DISTINCT A.handId AS handId",
        _from_clause(needed),
    ]
    if where:
        sql_parts.append("WHERE " + " AND ".join(f"({condition})" for condition in where))
    sql_parts.append("ORDER BY A.handId")
    params = list(where_params)
    if query.limit is not None:
        sql_parts.append(f"LIMIT {placeholder}")
        params.append(int(query.limit))
        sql_parts.append(f"OFFSET {placeholder}")
        params.append(int(query.offset))
    return CompiledQuery(
        sql=escape_literal_percent("\n".join(sql_parts), placeholder),
        params=tuple(params),
        group_by=(),
        metric=f"{query.metric} (hand ids)",
        description=_describe(f"{query.metric} (hand ids)", combined, {}, (), query.limit, query.offset),
    )


# ---------------------------------------------------------------------------
# Execution.
# ---------------------------------------------------------------------------


@dataclass
class QueryRow:
    """One grouped result: the numerator, the denominator and the metric."""

    group: dict[str, Any]
    opportunities: int
    actions: int
    value: float | None
    unit: str
    frequency_bp: int | None = None

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = dict(self.group)
        out["opportunities"] = self.opportunities
        out["actions"] = self.actions
        out["value"] = self.value
        out["unit"] = self.unit
        if self.frequency_bp is not None:
            out["frequency_bp"] = self.frequency_bp
        return out


@dataclass
class QueryResult:
    """A query's rows, plus the statement and description that produced them."""

    rows: list[QueryRow]
    compiled: CompiledQuery

    def as_dicts(self) -> list[dict[str, Any]]:
        return [row.as_dict() for row in self.rows]

    @property
    def total_opportunities(self) -> int:
        return sum(row.opportunities for row in self.rows)

    @property
    def total_actions(self) -> int:
        return sum(row.actions for row in self.rows)


def _backend_name(db: Any) -> str:
    """The Database backend constant as the compiler's name."""
    backend = getattr(db, "backend", None)
    names: dict[int, str] = {2: "mysql", 3: "postgresql", 4: "sqlite"}
    return names[backend] if isinstance(backend, int) and backend in names else "mysql"


def _placeholder(db: Any) -> str:
    try:
        return str(db.sql.query["placeholder"])
    except (AttributeError, KeyError):
        return "%s"


def run_query(db: Any, query: Query) -> QueryResult:
    """Compile and execute a query against a Database, merging player money."""
    backend = _backend_name(db)
    placeholder = _placeholder(db)
    compiled = compile_query(query, placeholder, backend)
    cursor = db.get_cursor()
    cursor.execute(compiled.sql, compiled.params)  # nosec B608  # nosemgrep
    columns = [description[0] for description in cursor.description]
    rows = [dict(zip(columns, raw)) for raw in cursor.fetchall()]

    player_totals: dict[tuple[Any, ...], float] = {}
    if compiled.player_sql is not None:
        cursor.execute(compiled.player_sql, compiled.player_params)  # nosec B608  # nosemgrep
        player_columns = [description[0] for description in cursor.description]
        for raw in cursor.fetchall():
            row = dict(zip(player_columns, raw))
            key = tuple(row[_alias_of(name)] for name in query.group_by)
            player_totals[key] = float(row["value"] or 0)

    spec, _filters, _numerator = query.resolved()
    result_rows: list[QueryRow] = []
    for row in rows:
        key = tuple(row[_alias_of(name)] for name in query.group_by)
        group = {name: row[_alias_of(name)] for name in query.group_by}
        opportunities = int(row["opportunities"] or 0)
        actions = int(row.get("actions") or 0)
        value: float | None
        if spec.player_expression is not None:
            total = player_totals.get(key, 0.0)
            value = round(total / opportunities, 4) if spec.per_opportunity and opportunities else total
        elif spec.frequency:
            value = actions
        elif spec.value_sql is None:
            value = actions
        else:
            value = row.get("value")
        frequency_bp = actions * 10000 // opportunities if spec.frequency and opportunities else None
        result_rows.append(
            QueryRow(
                group=group,
                opportunities=opportunities,
                actions=actions,
                value=value,
                unit=spec.unit,
                frequency_bp=frequency_bp,
            ),
        )
    return QueryResult(rows=result_rows, compiled=compiled)


def run_hand_ids(db: Any, query: Query, include_numerator: bool = False) -> list[int]:
    """The matching hand ids, the drill-down entry point of a result row."""
    compiled = compile_hand_ids(query, _placeholder(db), _backend_name(db), include_numerator)
    cursor = db.get_cursor()
    cursor.execute(compiled.sql, compiled.params)
    return [int(row[0]) for row in cursor.fetchall()]


__all__ = [
    "BASE_ALIAS",
    "DIMENSIONS",
    "FILTERS",
    "IMPLIED_NUMERATORS",
    "KNOWN_METRICS",
    "METRICS",
    "POSITION_CODES",
    "SOURCES",
    "CompiledQuery",
    "Query",
    "QueryResult",
    "QueryRow",
    "compile_filters",
    "compile_hand_ids",
    "escape_literal_percent",
    "compile_query",
    "filter_sources",
    "run_hand_ids",
    "run_query",
]
