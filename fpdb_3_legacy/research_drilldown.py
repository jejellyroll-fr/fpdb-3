"""Both sides of a Hero-versus-Field row, as hands you can open (#366).

A comparison row holds two populations, and the browser used to answer that
by refusing to drill at all: it asked the reader to rerun the question without
the comparison before looking at a single hand. That breaks the one workflow
the whole Study layer exists for -- notice a difference, click it, read the
hands that made it.

The fix is to stop pretending a comparison row has *one* set of hands. It has
four, and this module names them:

* the hero population (the denominator of your number);
* the hero numerator (the decisions where the metric fired);
* the field population;
* the field numerator.

Every one of them is the same :class:`DrillContext` asked again with one
filter changed -- ``hero`` -- so the two sides can differ in the population
identity and in nothing else. That is the property the tests assert, because
it is the only reason the two numbers were ever comparable.

Nothing here is Qt: the browser pane, the study dashboard and the tests all
read the same model.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Final

from .analytics_query import (
    Query,
    _backend_name,
    _expand_sources,
    _from_clause,
    _placeholder,
    compile_filters,
    escape_literal_percent,
    run_hand_ids,
)
from .research_browser import ResultColumn, drill_display_rows

SIDE_HERO: Final = "hero"
SIDE_FIELD: Final = "field"
SIDES: Final[tuple[str, ...]] = (SIDE_HERO, SIDE_FIELD)

#: A page small enough that a field population of a hundred thousand decisions
#: costs one screen of rows rather than a frozen window. The count beside it is
#: over the whole population, so the page never has to pretend to be the total.
DEFAULT_PAGE_SIZE: Final = 100
MAX_PAGE_SIZE: Final = 1000

#: The columns a drill page shows. ``player`` rather than ``hero``: on the
#: field side the row is about somebody else, and calling their column "hero"
#: would be a lie about whose cards are in it.
SIDE_DRILL_COLUMNS: Final[tuple[ResultColumn, ...]] = (
    ResultColumn("handId", "hand", "id"),
    ResultColumn("startTime", "time", "hand"),
    ResultColumn("siteName", "site", "hand"),
    ResultColumn("category", "game", "hand"),
    ResultColumn("bigBlind", "bb", "hand", "cents"),
    ResultColumn("maxSeats", "seats", "hand"),
    ResultColumn("playerName", "player", "hand"),
    ResultColumn("playerProfit", "player profit", "hand", "cents"),
    ResultColumn("playerCards", "player cards", "hand"),
    ResultColumn("board", "board", "hand"),
    ResultColumn("finalPot", "pot", "hand", "cents"),
)


def _check_side(side: str) -> None:
    if side not in SIDES:
        raise ValueError(f"Unknown drill side {side!r}; known sides: {list(SIDES)}")


@dataclass(frozen=True)
class DrillContext:
    """What a comparison row, cell or bucket keeps so both sides can be re-asked.

    ``query`` is the question the panel answered, ``group`` is the row's own
    key (grouping by street makes the flop row ``street='flop'``), and
    ``cross_filters`` is whatever the reader clicked on a chart -- a board
    texture, a sizing bucket, a position. All three narrow *both* sides
    identically; only :meth:`side_query` differs between them, and it differs
    in one filter.
    """

    query: Query
    group: Mapping[str, Any] = field(default_factory=dict)
    cross_filters: Mapping[str, Any] = field(default_factory=dict)
    label: str = ""

    def row_filters(self) -> dict[str, Any]:
        """The narrowing both sides share, with the population identity removed.

        ``hero`` is dropped rather than kept: a context that already picked a
        side would answer itself, and a "comparison" whose two halves are the
        same population is not one.
        """
        filters = {**dict(self.query.filters), **dict(self.group), **dict(self.cross_filters)}
        filters.pop("hero", None)
        return filters

    def side_query(self, side: str, *, numerator_only: bool = False) -> Query:
        """The exact query one side's hands come from."""
        _check_side(side)
        return Query(
            metric=self.query.metric,
            filters={**self.row_filters(), "hero": side == SIDE_HERO},
            numerator=dict(self.query.numerator) if numerator_only else {},
            group_by=(),
        )

    def sides_agree(self, *, numerator_only: bool = False) -> bool:
        """Whether the two sides differ in the population identity alone.

        The invariant the comparison rests on, available to the UI and to the
        tests rather than only asserted in a docstring.
        """
        hero = self.side_query(SIDE_HERO, numerator_only=numerator_only)
        field_side = self.side_query(SIDE_FIELD, numerator_only=numerator_only)
        if hero.metric != field_side.metric or hero.numerator != field_side.numerator:
            return False
        without_identity = (
            {name: value for name, value in hero.filters.items() if name != "hero"},
            {name: value for name, value in field_side.filters.items() if name != "hero"},
        )
        return (
            without_identity[0] == without_identity[1]
            and hero.filters.get("hero") is True
            and field_side.filters.get("hero") is False
        )


@dataclass(frozen=True)
class DrillTarget:
    """One of the four hand sets a comparison row can open."""

    side: str
    numerator_only: bool
    count: int | None = None
    label: str = ""

    @property
    def id(self) -> str:
        return f"{self.side}_{'numerator' if self.numerator_only else 'population'}"


@dataclass(frozen=True)
class DrillCounts:
    """The size of each of the four hand sets, in the metric's own unit."""

    hero_population: int
    hero_numerator: int
    field_population: int
    field_numerator: int
    unit: str = "decisions"

    def count(self, side: str, *, numerator_only: bool = False) -> int:
        _check_side(side)
        if side == SIDE_HERO:
            return self.hero_numerator if numerator_only else self.hero_population
        return self.field_numerator if numerator_only else self.field_population

    def targets(self, *, with_numerator: bool = True) -> tuple[DrillTarget, ...]:
        """The four buttons, in the order the issue's sketch lists them.

        ``with_numerator`` is False for a metric with no numerator to speak of
        -- an average pot has a population but no "the hands where it fired" --
        and then the row offers two sets rather than four.
        """
        labels = {
            (SIDE_HERO, False): "Your population",
            (SIDE_HERO, True): "Your actions",
            (SIDE_FIELD, False): "Field population",
            (SIDE_FIELD, True): "Field actions",
        }
        targets = []
        for side in SIDES:
            for numerator_only in (False, True):
                if numerator_only and not with_numerator:
                    continue
                targets.append(
                    DrillTarget(
                        side=side,
                        numerator_only=numerator_only,
                        count=self.count(side, numerator_only=numerator_only),
                        label=labels[(side, numerator_only)],
                    ),
                )
        return tuple(targets)


@dataclass(frozen=True)
class DrillPage:
    """One page of one side's hands, and the totals it is a page of."""

    side: str
    numerator_only: bool
    hand_ids: tuple[int, ...]
    rows: tuple[Mapping[str, Any], ...]
    total_matches: int
    total_hands: int
    offset: int
    limit: int
    known_cards: int = 0
    label: str = ""
    unit: str = "decisions"

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.hand_ids) < self.total_hands

    @property
    def has_previous(self) -> bool:
        return self.offset > 0

    @property
    def unknown_cards(self) -> int:
        return len(self.rows) - self.known_cards

    @property
    def page_note(self) -> str:
        """Where this page sits in the population, never rounded to "some"."""
        if not self.hand_ids:
            return f"No hands: 0 of {self.total_hands} hands"
        first = self.offset + 1
        last = self.offset + len(self.hand_ids)
        note = f"hands {first}-{last} of {self.total_hands}"
        if self.total_matches != self.total_hands:
            note += f" ({self.total_matches} {self.unit})"
        return note

    @property
    def card_coverage_note(self) -> str:
        """What the database actually recorded, said plainly.

        Hole cards exist for a hand only when they were stored -- which for the
        field means a showdown. Reporting the coverage is the honest form of
        "unknown cards remain unknown": an empty column is a fact about the
        import, not about the player.
        """
        if not self.rows:
            return ""
        if self.known_cards == len(self.rows):
            return "Cards known for every hand on this page."
        return (
            f"Cards known for {self.known_cards} of {len(self.rows)} hands on this page; "
            "the rest were never recorded and are left blank."
        )


def has_numerator(query: Query) -> bool:
    """Whether "the hands where it fired" means anything for this metric.

    An average pot size has a population and no numerator: offering a reader
    "your actions" for it would be two identical buttons.
    """
    _spec, _filters, numerator = query.resolved()
    return bool(numerator)


def _count(db: Any, query: Query, *, numerator_only: bool, distinct_hands: bool) -> int:
    """Count the population the way the metric itself counts it.

    Compiled exactly as ``compile_hand_ids`` compiles its ``WHERE`` -- filters
    and numerator side by side rather than merged -- so a numerator that shares
    a key with the population cannot silently drop one of the two.
    """
    spec, filters, numerator = query.resolved()
    placeholder = _placeholder(db)
    backend = _backend_name(db)
    where, params, aliases = compile_filters(filters, placeholder, backend)
    if numerator_only:
        numerator_where, numerator_params, numerator_aliases = compile_filters(
            numerator, placeholder, backend,
        )
        where = [*where, *numerator_where]
        params = [*params, *numerator_params]
        aliases = aliases | numerator_aliases
    expression = (
        "COUNT(DISTINCT A.handId)" if distinct_hands or spec.distinct_hands else "COUNT(*)"
    )
    sql_parts = [f"SELECT {expression} AS matches", _from_clause(_expand_sources(aliases | {"A"}))]
    if where:
        sql_parts.append("WHERE " + " AND ".join(f"({condition})" for condition in where))
    cursor = db.get_cursor()
    # ``compile_filters`` supplies only allow-listed SQL fragments and keeps
    # every runtime value in ``params``. The SQL text is assembled because the
    # metric chooses COUNT(*) vs COUNT(DISTINCT ...), while the values remain
    # parameterized. Keep the security scanner from mistaking that safe query
    # builder for an interpolated user query.
    cursor.execute(  # nosec B608  # nosemgrep
        escape_literal_percent("\n".join(sql_parts), placeholder),
        tuple(params),
    )
    row = cursor.fetchone()
    return int((row[0] if row else 0) or 0)


def count_side(
    db: Any,
    context: DrillContext,
    side: str,
    *,
    numerator_only: bool = False,
) -> int:
    """The number the comparison displays for that side, asked again.

    Counted with the metric's own expression -- decisions for most frequencies,
    distinct hands for the per-hand classics such as VPIP -- so a drill total
    and the sample beside it are the same number rather than two plausible
    ones.
    """
    return _count(
        db,
        context.side_query(side, numerator_only=numerator_only),
        numerator_only=numerator_only,
        distinct_hands=False,
    )


def count_hands(
    db: Any,
    context: DrillContext,
    side: str,
    *,
    numerator_only: bool = False,
) -> int:
    """How many distinct hands that side's list pages through."""
    return _count(
        db,
        context.side_query(side, numerator_only=numerator_only),
        numerator_only=numerator_only,
        distinct_hands=True,
    )


def drill_counts(db: Any, context: DrillContext, *, unit: str = "decisions") -> DrillCounts:
    """All four sizes, for a row that has no comparison result to read them off."""
    return DrillCounts(
        hero_population=count_side(db, context, SIDE_HERO),
        hero_numerator=count_side(db, context, SIDE_HERO, numerator_only=True),
        field_population=count_side(db, context, SIDE_FIELD),
        field_numerator=count_side(db, context, SIDE_FIELD, numerator_only=True),
        unit=unit,
    )


def counts_from_comparison_row(row: Any, *, unit: str = "decisions") -> DrillCounts:
    """The four sizes a rendered comparison row already knows.

    A comparison that has just been drawn has counted all four; asking the
    database again would be four queries to learn what is on screen.
    """
    return DrillCounts(
        hero_population=int(row.hero_opportunities),
        hero_numerator=int(row.hero_actions),
        field_population=int(row.field_opportunities),
        field_numerator=int(row.field_actions),
        unit=unit,
    )


def run_side_drill(
    db: Any,
    context: DrillContext,
    side: str,
    *,
    numerator_only: bool = False,
    limit: int = DEFAULT_PAGE_SIZE,
    offset: int = 0,
) -> DrillPage:
    """One page of one side's hands, with the totals it is a page of.

    The page is a window over the *hand ids*, taken in the database rather than
    in Python: a field population is routinely six figures, and loading it to
    show a hundred rows is the thing this function exists not to do.
    """
    _check_side(side)
    if limit <= 0 or limit > MAX_PAGE_SIZE:
        raise ValueError(f"page size must be between 1 and {MAX_PAGE_SIZE}")
    if offset < 0:
        raise ValueError("page offset must not be negative")
    query = context.side_query(side, numerator_only=numerator_only)
    paged = replace(query, limit=limit, offset=offset)
    hand_ids = run_hand_ids(db, paged, include_numerator=numerator_only)
    rows = drill_display_rows(db, query, hand_ids, actor=True)
    return DrillPage(
        side=side,
        numerator_only=numerator_only,
        hand_ids=tuple(hand_ids),
        rows=tuple(rows),
        total_matches=_count(db, query, numerator_only=numerator_only, distinct_hands=False),
        total_hands=_count(db, query, numerator_only=numerator_only, distinct_hands=True),
        offset=offset,
        limit=limit,
        known_cards=sum(1 for row in rows if row.get("playerCards")),
        label=context.label,
    )


def context_from_comparison(
    row_query: Query,
    group: Mapping[str, Any] | None = None,
    label: str = "",
) -> DrillContext:
    """The drill context behind one comparison row."""
    return DrillContext(query=row_query, group=dict(group or {}), label=label)


__all__ = [
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "SIDES",
    "SIDE_DRILL_COLUMNS",
    "SIDE_FIELD",
    "SIDE_HERO",
    "DrillContext",
    "DrillCounts",
    "DrillPage",
    "DrillTarget",
    "context_from_comparison",
    "count_hands",
    "count_side",
    "counts_from_comparison_row",
    "drill_counts",
    "has_numerator",
    "run_side_drill",
]
