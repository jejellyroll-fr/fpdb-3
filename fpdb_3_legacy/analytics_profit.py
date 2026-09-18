"""Action profitability and EV reporting (#300).

The query engine (#297) can already sum ``HandsPlayers.totalProfit`` over the
hand-players a filter selects. That single number raises four questions the
engine, on its own, cannot answer -- and answering them wrong is worse than not
answering them:

* **What unit is this money in, and what does it mean?** ``totalProfit`` is the
  *hand's* final result. "Profit when 3-betting the button" therefore means "the
  hand results of the hands in which this player 3-bet the button", not "the
  chips the 3-bet itself won". The two are different questions, and only the
  first one is answerable from a hand history that stops at the last action.
* **What about all-in equity?** ``allInEV`` is initialised to ``totalProfit`` and
  overwritten only for pots the equity engine could price, so summing it yields
  the *EV-adjusted* version of the same hand-level money. Reporting it as
  "realized profit" hides the adjustment; reporting the difference as "profit"
  hides the hands it came from.
* **Where does rake go?** fpdb stores three attributions of the same hand rake
  (dealt, contributed, weighted). They disagree, and none of them is "the rake
  this action paid" -- rake is charged to a hand, not to an action.
* **What is the sample?** "1 200 opportunities" can be one player in 1 200 hands
  or 60 players in twenty each. Money needs a denominator that says which.

So this module is a *reporting* layer: it runs the engine's filters, sums money
once per hand-player, and labels every figure with the semantics it actually
has. It refuses, loudly, to produce the one number the data does not support --
the immediate (theoretical) EV of an action -- rather than letting a hand-level
conditional result be read as a solver figure.

The overlap caveat is worth stating plainly, and it is reported, not just
documented: money is attributed to every group a hand-player's actions fall
into, so grouping by a decision attribute *partitions decisions, not money*.
"Profit by sizing bucket" is a set of overlapping hand-level results, not a
split of the total.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, NoReturn

from .analytics_query import (
    DIMENSIONS,
    FILTERS,
    CompiledQuery,
    Query,
    QueryResult,
    _alias_of,
    _backend_name,
    _expand_sources,
    _from_clause,
    _placeholder,
    compile_filters,
    run_hand_ids,
    run_query,
)

# Money is stored in cents, everywhere in fpdb's HandsPlayers table. Basis
# points of the pot are the engine's sizing unit; cents are the money unit.
MONEY_UNIT: Final = "cents"


# ---------------------------------------------------------------------------
# The four things "profit" can mean, and the one that cannot be computed.
# ---------------------------------------------------------------------------


class NotComputable(ValueError):
    """A figure that the stored data cannot support, asked for explicitly."""


@dataclass(frozen=True)
class Semantics:
    """One meaning of "profit", what it is computed over, and what it is not.

    ``kind`` separates the two families that must never be added up together:
    ``hand_result`` figures are the hand's money (conditioned on the filters),
    ``all_in_adjustment`` figures are the difference between two hand results,
    and ``not_computable`` marks a quantity fpdb has no basis for.
    """

    name: str
    label: str
    unit: str
    kind: str
    definition: str
    caveat: str = ""

    @property
    def computable(self) -> bool:
        return self.kind != "not_computable"

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "unit": self.unit,
            "kind": self.kind,
            "computable": self.computable,
            "definition": self.definition,
            "caveat": self.caveat,
        }


SEMANTICS: Final[dict[str, Semantics]] = {
    "realized": Semantics(
        name="realized",
        label="Realized profit",
        unit=MONEY_UNIT,
        kind="hand_result",
        definition=(
            "The hand's final result, summed once per distinct (hand, player) pair "
            "in the filtered population: the money won or lost in the hands in "
            "which the filtered actions happened."
        ),
        caveat=(
            "A hand-level conditional result. It is not the expected value of the "
            "action, and it cannot be: the outcome of the hand is decided by "
            "everything that happened after the action too."
        ),
    ),
    "ev_adjusted": Semantics(
        name="ev_adjusted",
        label="EV-adjusted profit",
        unit=MONEY_UNIT,
        kind="hand_result",
        definition=(
            "The same hand-level money with the all-in pots marked to their "
            "equity: 'what these hands would have won on average, given the "
            "all-in showdowns that could be priced'."
        ),
        caveat=(
            "Non-all-in hands are unchanged: fpdb stores allInEV = totalProfit for "
            "them, so only the all-in pots move."
        ),
    ),
    "all_in_luck": Semantics(
        name="all_in_luck",
        label="All-in luck",
        unit=MONEY_UNIT,
        kind="all_in_adjustment",
        definition=(
            "Realized profit minus EV-adjusted profit. Positive means the player "
            "won more than the priced all-in equity, negative means less."
        ),
        caveat=(
            "It is a difference between two hand results, not a profit: adding it "
            "to a total, or reading it as a population's win rate, is meaningless."
        ),
    ),
    "immediate_action_ev": Semantics(
        name="immediate_action_ev",
        label="Immediate action EV",
        unit=MONEY_UNIT,
        kind="not_computable",
        definition=(
            "The chips the action itself wins or loses, holding everything after it "
            "at the players' continuing ranges: a solver or equity-model figure."
        ),
        caveat=(
            "Not derivable here. A hand history records what the players actually "
            "held and did, once: it carries no counterfactual range for the hands "
            "that folded, and the outcome of the hand it belongs to is not the "
            "action's value. Computing it needs a model of the ranges, not a "
            "query over results."
        ),
    ),
}

# The money figures a report emits, in the order a reader needs them: the
# hand-level result, its equity-adjusted twin, then the difference.
REPORTED_SEMANTICS: Final[tuple[str, ...]] = ("realized", "ev_adjusted", "all_in_luck")


def semantics(name: str) -> Semantics:
    """One named meaning of profit, refusing an unknown name."""
    try:
        return SEMANTICS[name]
    except KeyError:
        raise KeyError(
            f"Unknown profit semantics {name!r}; known: {sorted(SEMANTICS)}",
        ) from None


def semantics_catalog() -> tuple[Semantics, ...]:
    """Every meaning of profit this module distinguishes, refusals included."""
    return tuple(SEMANTICS[name] for name in (*REPORTED_SEMANTICS, "immediate_action_ev"))


def immediate_action_ev(*_args: Any, **_kwargs: Any) -> NoReturn:
    """Refuse to invent the action's own EV -- the honest answer, worded.

    The acceptance criteria say not to conflate a conditional hand result with
    solver EV. A function that always raises is a blunt way to enforce that, and
    it is the point: there is no filter that makes this number exist, so a
    caller that wants it is told why instead of being handed something that
    looks like it.
    """
    spec = SEMANTICS["immediate_action_ev"]
    raise NotComputable(f"{spec.label} is not computable from fpdb's hand history: {spec.caveat}")


# ---------------------------------------------------------------------------
# The money query: one row per distinct (hand, player) pair, summed per group.
# ---------------------------------------------------------------------------

# The rake attributions fpdb stores, and what each one splits the hand rake by.
RAKE_ATTRIBUTIONS: Final[dict[str, tuple[str, str]]] = {
    "dealt": ("rakeDealt", "the hand rake split evenly between everyone dealt in"),
    "contributed": ("rakeContributed", "the hand rake split between the players who put money in"),
    "weighted": ("rakeWeighted", "the hand rake weighted by what each player put in"),
}

# These dimensions identify one value per hand-player. Grouping by one or a
# combination of them therefore partitions the money instead of overlapping.
_PARTITIONING_DIMENSIONS: Final[frozenset[str]] = frozenset({"player", "position", "site"})


def _rake_alias(name: str) -> str:
    """The SELECT name of one rake attribution in the pair query."""
    return f"rake_{name}"

# Every metric this module reads out of a pair row. Sums of stored columns, so
# the money column is spelled once and the SQL stays legible.
_PAIR_COLUMNS: Final[tuple[tuple[str, str], ...]] = (
    ("realized_cents", "HP.totalProfit"),
    ("ev_adjusted_cents", "HP.allInEV"),
    ("rake_dealt", "HP.rakeDealt"),
    ("rake_contributed", "HP.rakeContributed"),
    ("rake_weighted", "HP.rakeWeighted"),
)


@dataclass(frozen=True)
class ProfitRow:
    """One group's money, its sample and the denominators the sample implies."""

    group: dict[str, Any]
    opportunities: int
    hands: int
    players: int
    hand_players: int
    sample_sufficient: bool
    realized_cents: float
    ev_adjusted_cents: float
    all_in_luck_cents: float
    ev_adjusted_pairs: int
    rake: dict[str, float]
    rake_cents: float
    bb_pairs: int
    bb_profit: float
    bb_per_100: float | None
    ev_bb_per_100: float | None

    @property
    def realized_per_hand_cents(self) -> float | None:
        """Realized profit per distinct hand in the population."""
        return round(self.realized_cents / self.hands, 4) if self.hands else None

    @property
    def realized_per_opportunity_cents(self) -> float | None:
        """Realized profit per decision -- the decision-denominated rate."""
        return round(self.realized_cents / self.opportunities, 4) if self.opportunities else None

    @property
    def rake_per_hand_cents(self) -> float | None:
        return round(self.rake_cents / self.hands, 4) if self.hands else None

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = dict(self.group)
        out.update(
            {
                "opportunities": self.opportunities,
                "hands": self.hands,
                "players": self.players,
                "hand_players": self.hand_players,
                "sample_sufficient": self.sample_sufficient,
                "realized_cents": self.realized_cents,
                "ev_adjusted_cents": self.ev_adjusted_cents,
                "all_in_luck_cents": self.all_in_luck_cents,
                "ev_adjusted_pairs": self.ev_adjusted_pairs,
                "rake_cents": self.rake_cents,
                "rake": dict(self.rake),
                "rake_per_hand_cents": self.rake_per_hand_cents,
                "bb_pairs": self.bb_pairs,
                "bb_profit": self.bb_profit,
                "bb_per_100": self.bb_per_100,
                "ev_bb_per_100": self.ev_bb_per_100,
                "realized_per_hand_cents": self.realized_per_hand_cents,
                "realized_per_opportunity_cents": self.realized_per_opportunity_cents,
            },
        )
        return out


@dataclass(frozen=True)
class ProfitReport:
    """A profit report: the rows, the population total, the hands, the caveats."""

    query: Query
    group_by: tuple[str, ...]
    rake_attribution: str
    min_sample: int
    rows: tuple[ProfitRow, ...]
    total: ProfitRow
    hand_ids: tuple[int, ...]
    notes: tuple[str, ...]
    compiled: tuple[CompiledQuery, ...] = ()
    _lookup: dict[tuple[Any, ...], ProfitRow] = field(default_factory=dict, repr=False)

    @property
    def overlapping_groups(self) -> bool:
        """Whether grouping decisions means the rows share hand results."""
        return bool(self.group_by) and not set(self.group_by).issubset(_PARTITIONING_DIMENSIONS)

    def row(self, **key: Any) -> ProfitRow:
        """One row of the report, by its group values."""
        missing = [name for name in self.group_by if name not in key]
        if missing:
            raise KeyError(f"A row of this report is keyed by {list(self.group_by)}; missing {missing}")
        wanted = tuple(key[name] for name in self.group_by)
        try:
            return self._lookup[wanted]
        except KeyError:
            raise KeyError(f"No {list(self.group_by)}={list(wanted)} in this report") from None

    def as_dict(self) -> dict[str, Any]:
        return {
            "metric": self.query.metric,
            "filters": dict(self.query.filters),
            "numerator": dict(self.query.numerator),
            "group_by": list(self.group_by),
            "rake_attribution": self.rake_attribution,
            "min_sample": self.min_sample,
            "rows": [row.as_dict() for row in self.rows],
            "total": self.total.as_dict(),
            "hand_ids": list(self.hand_ids),
            "notes": list(self.notes),
            "overlapping_groups": self.overlapping_groups,
            "semantics": [spec.as_dict() for spec in semantics_catalog()],
            "sql": [compiled.as_dict() for compiled in self.compiled],
        }

    def render(self, *, limit: int | None = None, hide_small: bool = False) -> str:
        """A readable table: the money, its unit and its sample, per group."""
        header = f"realized profit ({self.rake_attribution} rake) -- money in cents"
        lines = [header]
        if self.group_by:
            lines.append("  " + "  ".join(f"{name:>12}" for name in self.group_by) + f"  {'opps':>7}  {'hands':>6}  {'realized':>10}  {'EV-adj':>10}  {'luck':>9}  {'bb/100':>8}  {'rake':>7}")
        else:
            lines.append(f"  {'opps':>7}  {'hands':>6}  {'realized':>10}  {'EV-adj':>10}  {'luck':>9}  {'bb/100':>8}  {'rake':>7}")

        def line_for(row: ProfitRow, marker: str = " ") -> str:
            bb = "" if row.bb_per_100 is None else format(row.bb_per_100, ".2f")
            prefix = "  " + "  ".join(f"{_cell(row.group.get(name)):>12}" for name in self.group_by) + "  " if self.group_by else "  "
            return (
                f"{marker} {prefix}"
                f"{row.opportunities:>7}  {row.hands:>6}  {row.realized_cents:>10}  "
                f"{row.ev_adjusted_cents:>10}  {row.all_in_luck_cents:>9}  {bb:>8}  {_amount_cell(row.rake_cents):>7}"
            )

        if self.group_by:
            shown = [row for row in self.rows if not (hide_small and not row.sample_sufficient)]
            if limit is not None:
                shown = shown[:limit]
            lines.extend(line_for(row, "*" if not row.sample_sufficient else " ") for row in shown)
            if len(shown) != len(self.rows):
                lines.append(f"  ... {len(self.rows) - len(shown)} row(s) not shown")
            lines.append(line_for(self.total, " "))
            lines.append("  total: the whole population, not the sum of the rows above")
        else:
            # One population, one row: the row *is* the total.
            lines.append(line_for(self.total, "*" if not self.total.sample_sufficient else " "))
            lines.append("  total")
        lines.extend(f"  note: {note}" for note in self.notes)
        return "\n".join(lines)


def _cell(value: Any) -> str:
    return "" if value is None else str(value)


def _money(value: Any) -> int:
    """A stored money column as an integer number of cents."""
    return int(round(float(value or 0)))


def _rake_amount(value: Any) -> float:
    """A rake allocation in cents, retaining fractional-cent attribution."""
    return round(float(value or 0), 8)


def _amount_cell(value: float) -> str:
    """Render integer-valued amounts compactly while keeping fractions visible."""
    return f"{value:.8f}".rstrip("0").rstrip(".")


def _rate(value: Any) -> float:
    return round(float(value or 0), 4)


def _group_expressions(group_by: Sequence[str]) -> list[tuple[str, str]]:
    """The SQL expression of each dimension, refusing an unknown one."""
    out: list[tuple[str, str]] = []
    for name in group_by:
        if name not in DIMENSIONS:
            raise ValueError(f"Unknown group_by dimension {name!r}; known: {sorted(DIMENSIONS)}")
        expression, _aliases = DIMENSIONS[name]
        out.append((name, expression))
    return out


def compile_profit_query(
    query: Query,
    placeholder: str = "%s",
    backend: str = "mysql",
) -> CompiledQuery:
    """The money side of a report: one row per distinct (hand, player) pair.

    The engine's player-scoped metrics do exactly this per metric; a report
    needs six of them per group, so the inner query selects the group values and
    the pair, and the outer one sums the stored money columns once per pair. The
    filters, the joins and the group expressions are the engine's own, so a
    report cannot see a different population from the query it was asked for.
    """
    _spec, filters, numerator = query.resolved()
    del numerator  # a report is a property of the population, not of the numerator
    group_by = tuple(query.group_by)
    where, where_params, aliases = compile_filters(filters, placeholder, backend)
    # The pair's stake lives on the game type, so the money query always joins
    # ``G``: every figure in bb comes from it, and a population that turns out
    # to have no usable stake says so instead of dividing by -1.

    expressions = _group_expressions(group_by)
    # A dimension reads its own sources: grouping by a board feature joins the
    # board table even when no filter mentions it.
    for name, _expression in expressions:
        aliases.update(DIMENSIONS[name][1])
    needed = _expand_sources(aliases | {"A", "G"})
    from_clause = _from_clause(needed)

    inner_select = [f"{expression} AS {_alias_of(name)}" for name, expression in expressions]
    inner_select += ["A.handId AS handId", "A.playerId AS playerId"]

    outer_group = [f"P.{_alias_of(name)}" for name in group_by]
    outer_select = [f"P.{_alias_of(name)} AS {_alias_of(name)}" for name in group_by]
    outer_select += [
        "COUNT(*) AS hand_players",
        "COUNT(DISTINCT P.handId) AS hands",
        "COUNT(DISTINCT P.playerId) AS players",
    ]
    outer_select += [f"SUM({column}) AS {name}" for name, column in _PAIR_COLUMNS]
    # The all-in adjustment is only visible as the difference between the two
    # stored columns: a pair whose adjustment is exactly zero is either a hand
    # that never went all-in or a priced all-in that happened to break even.
    outer_select.append("SUM(CASE WHEN HP.allInEV <> HP.totalProfit THEN 1 ELSE 0 END) AS ev_adjusted_pairs")
    # Big blinds are not per hand: they live on the game type, and fixed-limit
    # rows store -1 there. Only a positive big blind can price a hand in bb.
    outer_select.append("SUM(CASE WHEN G.bigBlind > 0 THEN 1 ELSE 0 END) AS bb_pairs")
    outer_select.append("SUM(CASE WHEN G.bigBlind > 0 THEN HP.totalProfit * 1.0 / G.bigBlind END) AS bb_profit")
    outer_select.append("SUM(CASE WHEN G.bigBlind > 0 THEN HP.allInEV * 1.0 / G.bigBlind END) AS bb_adjusted")

    sql_parts = [
        "SELECT\n  " + ",\n  ".join(outer_select),
        "FROM (",
        "  SELECT DISTINCT\n    " + ",\n    ".join(inner_select),
        "  " + from_clause.replace("\n", "\n  "),
    ]
    if where:
        sql_parts.append("  WHERE " + " AND ".join(f"({condition})" for condition in where))
    sql_parts.append(") P")
    sql_parts.append("JOIN HandsPlayers HP ON HP.handId = P.handId AND HP.playerId = P.playerId")
    sql_parts.append("JOIN Hands H ON H.id = P.handId")
    sql_parts.append("JOIN Gametypes G ON G.id = H.gametypeId")
    if outer_group:
        sql_parts.append("GROUP BY " + ", ".join(outer_group))
        sql_parts.append("ORDER BY " + ", ".join(outer_group))

    params: list[Any] = list(where_params)
    return CompiledQuery(
        sql="\n".join(sql_parts),
        params=tuple(params),
        group_by=group_by,
        metric=f"{query.metric} (profit)",
        description=(
            f"profit over the distinct (hand, player) pairs of the {query.metric} population"
            + (f", grouped by {', '.join(group_by)}" if group_by else "")
        ),
    )


def _row_from_pair_row(
    raw: Mapping[str, Any],
    group: dict[str, Any],
    opportunities: int,
    rake_attribution: str,
    min_sample: int,
) -> ProfitRow:
    """One pair-row of SQL as a :class:`ProfitRow`, with the derived figures."""
    realized = _money(raw["realized_cents"])
    adjusted = _money(raw["ev_adjusted_cents"])
    rake = {name: _rake_amount(raw[_rake_alias(name)]) for name in RAKE_ATTRIBUTIONS}
    bb_pairs = int(raw["bb_pairs"] or 0)
    bb_profit = _rate(raw["bb_profit"])
    bb_adjusted = _rate(raw["bb_adjusted"])
    hand_players = int(raw["hand_players"] or 0)
    return ProfitRow(
        group=group,
        opportunities=opportunities,
        hands=int(raw["hands"] or 0),
        players=int(raw["players"] or 0),
        hand_players=hand_players,
        sample_sufficient=opportunities >= min_sample,
        realized_cents=realized,
        ev_adjusted_cents=adjusted,
        all_in_luck_cents=realized - adjusted,
        ev_adjusted_pairs=int(raw["ev_adjusted_pairs"] or 0),
        rake=rake,
        rake_cents=rake[rake_attribution],
        bb_pairs=bb_pairs,
        bb_profit=bb_profit,
        bb_per_100=round(100 * bb_profit / bb_pairs, 4) if bb_pairs else None,
        ev_bb_per_100=round(100 * bb_adjusted / bb_pairs, 4) if bb_pairs else None,
    )


def _notes(
    report_query: Query,
    group_by: Sequence[str],
    rake_attribution: str,
    min_sample: int,
    total: ProfitRow,
    rows: Sequence[ProfitRow],
) -> tuple[str, ...]:
    """The caveats a reader needs to not misread the table above it."""
    notes = [
        "money is summed once per distinct (hand, player) pair: a hand result belongs to the hand, "
        "not to each decision in it",
        "realized profit is the hand-level result conditioned on the filters; it is not the expected "
        "value of the action",
    ]
    if group_by and set(group_by) - _PARTITIONING_DIMENSIONS:
        notes.append(
            "groups overlap by design: a hand-player is counted in every group its actions fall into, "
            "so the rows do not add up to the total",
        )
    notes.append(
        "EV-adjusted profit marks only the all-in pots fpdb can price "
        f"(non-zero for {total.ev_adjusted_pairs} of {total.hand_players} pairs); every other hand "
        "keeps its realized result",
    )
    if total.hand_players and total.bb_pairs < total.hand_players:
        notes.append(
            f"{total.hand_players - total.bb_pairs} of {total.hand_players} pairs have no usable big "
            "blind (fixed-limit rows store -1); bb figures cover the rest",
        )
    _column, description = RAKE_ATTRIBUTIONS[rake_attribution]
    notes.append(f"rake is attributed by {rake_attribution}: {description}")
    if not total.rake_cents:
        notes.append("no rake is stored for this population (rake-free rows, or a rake-free site)")
    if min_sample:
        small = sum(1 for row in rows if not row.sample_sufficient)
        notes.append(
            f"{small} of {len(rows)} rows hold fewer than {min_sample} decisions; their money is shown "
            "unfiltered, marked with *",
        )
    if report_query.limit is not None:
        notes.append(
            f"the query pages its rows (limit={report_query.limit}); a report covers the whole "
            "population, so paging is ignored here",
        )
    return tuple(notes)


def profit_report(
    db: Any,
    query: Query,
    *,
    rake: str = "contributed",
    min_sample: int = 0,
    with_hand_ids: bool = True,
    hand_id_limit: int | None = None,
) -> ProfitReport:
    """Report the money of a filtered population, labelled and sampled.

    The decision count comes from the engine's own ``opportunities`` metric, so
    the report cannot disagree with the query it was asked for about what the
    population is; the money comes from one pass over the distinct hand-players
    that population touches.
    """
    if rake not in RAKE_ATTRIBUTIONS:
        raise ValueError(f"Unknown rake attribution {rake!r}; known: {sorted(RAKE_ATTRIBUTIONS)}")
    group_by = tuple(query.group_by)
    backend = _backend_name(db)
    placeholder = _placeholder(db)

    money = compile_profit_query(query, placeholder, backend)
    counts_query = Query(
        metric="opportunities",
        filters=dict(query.filters),
        numerator=dict(query.numerator),
        group_by=group_by,
    )
    counts = run_query(db, counts_query)

    cursor = db.get_cursor()
    cursor.execute(money.sql, money.params)  # nosec B608  # nosemgrep
    columns = [description[0] for description in cursor.description]
    pair_rows = [dict(zip(columns, raw)) for raw in cursor.fetchall()]

    opportunities_by_key = {tuple(row.group[name] for name in group_by): row.opportunities for row in counts.rows}
    rows: list[ProfitRow] = []
    lookup: dict[tuple[Any, ...], ProfitRow] = {}
    for raw in pair_rows:
        group = {name: raw[_alias_of(name)] for name in group_by}
        key = tuple(group[name] for name in group_by)
        # A pair row and a count row are the same group by construction: both
        # group the same expression over the same population.
        opportunities = opportunities_by_key.get(key, 0)
        row = _row_from_pair_row(raw, group, opportunities, rake, min_sample)
        rows.append(row)
        lookup[key] = row

    total = _total_row(db, query, money, counts, rake, min_sample)
    hand_ids = tuple(run_hand_ids(db, counts_query)) if with_hand_ids else ()
    if hand_ids and hand_id_limit is not None:
        hand_ids = hand_ids[:hand_id_limit]
    return ProfitReport(
        query=query,
        group_by=group_by,
        rake_attribution=rake,
        min_sample=min_sample,
        rows=tuple(rows),
        total=total,
        hand_ids=hand_ids,
        notes=_notes(query, group_by, rake, min_sample, total, rows),
        compiled=(money, counts.compiled),
        _lookup=lookup,
    )


def _total_row(
    db: Any,
    query: Query,
    money: CompiledQuery,
    counts: QueryResult,
    rake: str,
    min_sample: int,
) -> ProfitRow:
    """The whole population as one row -- never the sum of overlapping groups.

    With no dimensions the money query already *is* the total; with dimensions
    the report runs it once more ungrouped, because summing overlapping groups
    would count a hand result once per group its actions fall into.
    """
    if not query.group_by:
        cursor = db.get_cursor()
        cursor.execute(money.sql, money.params)  # nosec B608  # nosemgrep
        columns = [description[0] for description in cursor.description]
        raw = cursor.fetchone()
        if raw is None:  # pragma: no cover - an aggregate without GROUP BY always returns a row
            raise RuntimeError("the money query returned no summary row")
        return _row_from_pair_row(
            dict(zip(columns, raw)),
            {},
            counts.total_opportunities,
            rake,
            min_sample,
        )
    ungrouped = compile_profit_query(
        Query(metric=query.metric, filters=dict(query.filters), numerator=dict(query.numerator)),
        _placeholder(db),
        _backend_name(db),
    )
    cursor = db.get_cursor()
    cursor.execute(ungrouped.sql, ungrouped.params)  # nosec B608  # nosemgrep
    columns = [description[0] for description in cursor.description]
    raw = cursor.fetchone()
    if raw is None:  # pragma: no cover - an aggregate without GROUP BY always returns a row
        raise RuntimeError("the money query returned no summary row")
    # A population with no matching decision still returns one row of NULLs,
    # which reads as the zeros of an empty sample rather than as an error.
    return _row_from_pair_row(dict(zip(columns, raw)), {}, counts.total_opportunities, rake, min_sample)


def matching_hand_ids(db: Any, query: Query, limit: int | None = None) -> tuple[int, ...]:
    """The hands behind a population, for review -- the drill-down entry point."""
    counts_query = Query(
        metric="opportunities",
        filters=dict(query.filters),
        numerator=dict(query.numerator),
        limit=limit,
    )
    return tuple(run_hand_ids(db, counts_query))


def narrow_query(query: Query, group: Mapping[str, Any]) -> Query:
    """One group of a report as a query of its own, for its hands and its drill-down.

    A grouped value is not always shaped like its corresponding report filter:
    numeric dimensions need a point range, tournament groups need an exact-id
    filter rather than the public tournament boolean, and a NULL board bucket
    needs an explicit left-join presence check.  Keep those translations here
    so drill-down never broadens a row silently.
    """
    filters = dict(query.filters)
    missing: list[str] = []
    for name, value in group.items():
        filter_name = "tournament_id" if name == "tournament" and value is not None else name
        spec = FILTERS.get(filter_name)
        if spec is None:
            missing.append(name)
            continue
        if value is None:
            filters[filter_name] = {"is_null": True}
        elif spec.kind in ("range", "range_pct", "range_low", "range_high"):
            filters[filter_name] = [value, value]
        else:
            filters[filter_name] = value
    if missing:
        raise ValueError(
            f"Cannot narrow a report by {missing}: no filter of that name exists, so the group's "
            "value cannot be asked for on its own",
        )
    return Query(
        metric=query.metric,
        filters=filters,
        numerator=dict(query.numerator),
        group_by=(),
        limit=query.limit,
    )


__all__ = [
    "MONEY_UNIT",
    "RAKE_ATTRIBUTIONS",
    "REPORTED_SEMANTICS",
    "SEMANTICS",
    "NotComputable",
    "ProfitReport",
    "ProfitRow",
    "Semantics",
    "compile_profit_query",
    "immediate_action_ev",
    "matching_hand_ids",
    "narrow_query",
    "profit_report",
    "semantics",
    "semantics_catalog",
]
