"""The Research workbench's named views (#331). Qt-free.

#303 gave the analytics engine a browser: express a query, read a table. That is
one presentation, and the questions this epic exists for are not all tables.
"Where do I open from?" is a per-seat breakdown, "which hands do I open?" is a
13x13 grid, "what am I holding when I call?" is a composition, and "did I win,
or was I lucky?" is two money columns that only mean something read together.

This module is the catalogue. One entry per view, carrying the question in poker
words, the preset it starts from in engine vocabulary, and the *shape* of the
answer -- ``table``, ``grid``, ``composition``, ``money`` or ``hands``. It holds
no Qt and runs no query of its own: it asks the modules that already own that
question (``holdem_ranges``, ``hand_state_composition``, ``analytics_profit``,
``research_browser``) and hands the widget something to draw. So the workbench
is a renderer of what this says, and everything that decides anything is
testable without a window.

Two honesty rules live here rather than in the widget:

* a view that cannot answer for a population says *why* -- a grid over Omaha
  cards is not an empty grid, it is an unavailable one (``Unavailable``), the
  same contract the browser's empty state has;
* the money view carries the realized result *and* the EV-adjusted one, with
  the sentence that says which is which, because a single unlabelled "profit"
  is the reading the analytics epic refuses to ship.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from . import research_browser as rb
from .analytics_profit import ProfitReport, profit_report
from .analytics_query import DIMENSIONS, Query
from .hand_state_composition import Composition, compose
from .holdem_ranges import NotHoldem, RangeMatrix, build_range

# The shapes an answer can take. The workbench draws one widget per shape, and a
# view that names a shape nobody implements is refused at import (see
# ``_check_catalogue``) rather than rendered as a blank page.
TABLE: Final = "table"
GRID: Final = "grid"
COMPOSITION: Final = "composition"
MONEY: Final = "money"
HANDS: Final = "hands"
KINDS: Final = (TABLE, GRID, COMPOSITION, MONEY, HANDS)

# The hand-state dimension a composition falls back to when a view does not name
# one: what the acting player held. Named here so the UI and the model agree.
DEFAULT_COMPOSITION_DIMENSION: Final = "made_hand"


class Unavailable(Exception):
    """A view this population cannot answer, with the reason in the message.

    Distinct from an empty result: an empty result is a real answer ("nobody
    did this"), and this is "this question does not apply here" -- grouping a
    Hold'em range over a game whose two cards are not a Hold'em hand, for one.
    """


@dataclass(frozen=True)
class ViewSpec:
    """One named view: what it asks, what it starts from, and how to draw it."""

    id: str
    label: str
    question: str
    metric: str
    group_by: tuple[str, ...]
    kind: str
    how_to_read: str
    filters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"{self.id}: unknown view kind {self.kind!r}; known: {list(KINDS)}")


# The catalogue, in the order a reader meets the questions: the headline, then
# the breakdowns, then the shapes that are not tables.
VIEWS: Final[tuple[ViewSpec, ...]] = (
    ViewSpec(
        id="summary",
        label="Summary",
        question="How often does a player fold when facing a three-bet?",
        metric="fold_frequency",
        group_by=(),
        kind=TABLE,
        how_to_read=(
            "One number over one population: the denominator is how many times a player faced a "
            "three-bet, the numerator how many of those they folded."
        ),
        filters={"primary_situation": "facing_3bet"},
    ),
    ViewSpec(
        id="table",
        label="Table",
        question="Folding to a continuation bet, street by street.",
        metric="fold_frequency",
        group_by=("street",),
        kind=TABLE,
        how_to_read=(
            "One row per street. A row with a small denominator is a hint, not a reading: the "
            "sample column is there for exactly that."
        ),
        filters={"primary_situation": "facing_cbet"},
    ),
    ViewSpec(
        id="frequencies",
        label="Frequencies",
        question="Every kind of decision the players made, and how often.",
        metric="opportunities",
        group_by=("primary_situation",),
        kind=TABLE,
        how_to_read=(
            "The decision map: one row per named spot, so an empty feature shows up as a missing "
            "row rather than as a blank screen."
        ),
    ),
    ViewSpec(
        id="sizing",
        label="Sizing",
        question="How often a flop continuation bet is folded to, by how big it was.",
        metric="fold_frequency",
        group_by=("facing_sizing_bucket",),
        kind=TABLE,
        how_to_read=(
            "One row per size bucket, measured in per cent of the pot. Bets are bucketed, so a "
            "row is a range of sizes, not one size."
        ),
        filters={"street": "flop", "primary_situation": "facing_cbet"},
    ),
    ViewSpec(
        id="position",
        label="Position",
        question="Three-betting by seat, against a single raise.",
        metric="raise_frequency",
        group_by=("position",),
        kind=TABLE,
        how_to_read=(
            "One row per seat. Seats are stored as the codes the parser wrote, so the row labels "
            "are seat names rather than numbers."
        ),
        filters={"primary_situation": "facing_open"},
    ),
    ViewSpec(
        id="board",
        label="Board",
        question="Continuation betting by board suit and pairing.",
        metric="bet_frequency",
        group_by=("board_suit", "board_pairing"),
        kind=TABLE,
        how_to_read=(
            "One row per board texture, classified by the flop alone. The denominator is every "
            "flop where the player had the lead and nobody had bet, so a check is a declined "
            "c-bet rather than a missing row. Boards the classifier could not read are absent "
            "rather than guessed at."
        ),
        # ``cbet_spot``, not ``cbet``: the named c-bet rule already requires the
        # response to be a bet, so a bet frequency over it would read 100% on
        # every board with data. The spot is the opportunity -- the lead with no
        # bet in front -- which the c-bet may be taken from or declined.
        filters={"primary_situation": "cbet_spot"},
    ),
    ViewSpec(
        id="range",
        label="Range 13x13",
        question="Which starting hands get opened.",
        metric="raise_frequency",
        group_by=(),
        kind=GRID,
        how_to_read=(
            "One cell per starting hand, coloured by how often it was opened when it was first "
            "to enter. A cell under the sample threshold stays uncoloured: the count it carries "
            "is the only fact there."
        ),
        # ``open_raise`` would be the outcome again: the rule is only assigned
        # when the response was a raise, so every populated cell would read
        # 100%. The unopened pot is what a hand was actually opened *from*.
        filters={"pot_type": "unopened"},
    ),
    ViewSpec(
        id="hand_strength",
        label="Hand strength",
        question="What players hold when they call a turn bet.",
        metric="opportunities",
        group_by=("made_hand",),
        kind=COMPOSITION,
        how_to_read=(
            "The made hands behind the decisions. Cards nobody saw are counted apart, never "
            "assigned to a category."
        ),
        filters={"street": "turn", "response": "call"},
    ),
    ViewSpec(
        id="profit",
        label="Profit & EV",
        question="Realized and EV-adjusted profit by seat, for the players who opened.",
        metric="total_profit",
        group_by=("position",),
        kind=MONEY,
        how_to_read=(
            "Two columns of the same money: realized is what the hands actually won, EV-adjusted "
            "marks the priced all-ins to equity and leaves every other hand untouched. Read them "
            "together; the difference is luck, not skill."
        ),
        filters={"primary_situation": "open_raise"},
    ),
    ViewSpec(
        id="hands",
        label="Hands",
        question="The hands behind one row of any view.",
        metric="opportunities",
        group_by=(),
        kind=HANDS,
        how_to_read=(
            "The population the current query selected, newest last, with the hero's cards and the "
            "board as they were stored."
        ),
    ),
)

VIEW_IDS: Final[tuple[str, ...]] = tuple(spec.id for spec in VIEWS)


def _check_catalogue() -> None:
    """Refuse a catalogue the engine or the widgets could not serve.

    Import-time, so a view naming a metric, a filter or a dimension the engine
    does not have is a broken import with the reason, not an empty screen a
    user finds later.
    """
    seen: set[str] = set()
    for spec in VIEWS:
        if spec.id in seen:
            raise ValueError(f"Duplicate view id {spec.id!r}")
        seen.add(spec.id)
        if spec.kind in (GRID, HANDS):
            # Neither is a grouped query: the grid fixes its own dimension and
            # the hands view is the drill-down of whatever query is loaded.
            continue
        rb.validate_preset(preset(spec))
        if spec.kind == COMPOSITION:
            # ``compose`` takes the dimension by name and the query ungrouped,
            # so the name is the one thing the preset validation does not see.
            dimension = spec.group_by[0] if spec.group_by else DEFAULT_COMPOSITION_DIMENSION
            if dimension not in DIMENSIONS:
                raise ValueError(f"{spec.id}: unknown composition dimension {dimension!r}")


def view(view_id: str) -> ViewSpec:
    """One view by id, refusing an unknown name with the ones that exist."""
    for spec in VIEWS:
        if spec.id == view_id:
            return spec
    raise KeyError(f"Unknown view {view_id!r}; known: {list(VIEW_IDS)}")


def preset(
    spec: ViewSpec,
    extra_filters: Mapping[str, Any] | None = None,
    *,
    replace_filters: bool = False,
) -> dict[str, Any]:
    """A view as a preset, in the vocabulary the browser and the engine share.

    ``replace_filters`` says the given filters *are* the population rather than
    an addition to the view's own. The workbench loads a view's question into
    its controls and then runs what the controls say, so a filter the user
    removed has to stay removed: with the merge, deleting the situation from a
    shaped view still ran that situation while the builder and the
    plain-language summary promised otherwise.
    """
    given = dict(extra_filters or {})
    filters = given if replace_filters else {**dict(spec.filters), **given}
    return rb.validate_preset(
        {
            "metric": spec.metric,
            "filters": filters,
            "group_by": spec.group_by,
            "description": spec.question,
        },
    )


def query(
    spec: ViewSpec,
    extra_filters: Mapping[str, Any] | None = None,
    *,
    replace_filters: bool = False,
) -> Query:
    """A view as the engine's ``Query``."""
    return rb.preset_to_query(preset(spec, extra_filters, replace_filters=replace_filters))


def range_matrix(
    db: Any,
    spec: ViewSpec,
    *,
    extra_filters: Mapping[str, Any] | None = None,
    replace_filters: bool = False,
    min_sample: int = 0,
) -> RangeMatrix:
    """The 13x13 grid of a grid view's population (#301, reused).

    A population that is not Hold'em is ``Unavailable``: the grid's cells are
    Hold'em starting hands, so drawing anything for two cards that are not a
    Hold'em hand would be inventing the axis.
    """
    if spec.kind != GRID:
        raise Unavailable(f"{spec.label} is not a grid view")
    try:
        return build_range(
            db, query(spec, extra_filters, replace_filters=replace_filters), min_sample=min_sample,
        )
    except NotHoldem as exc:
        raise Unavailable(str(exc)) from exc


def hand_composition(
    db: Any,
    spec: ViewSpec,
    *,
    extra_filters: Mapping[str, Any] | None = None,
    replace_filters: bool = False,
    dimension: str | None = None,
    min_sample: int = 0,
) -> Composition:
    """The composition of a composition view's population (#302, reused).

    The population is the view's filters, unchanged: a composition of the
    decisions that called is the composition of those decisions, not of the
    hands they happened in. The dimension comes from the view -- the engine
    refuses a query that both groups and composes, so it is passed separately.
    """
    if spec.kind != COMPOSITION:
        raise Unavailable(f"{spec.label} is not a composition view")
    chosen = dimension or (spec.group_by[0] if spec.group_by else DEFAULT_COMPOSITION_DIMENSION)
    given = dict(extra_filters or {})
    ungrouped = Query(
        metric=spec.metric,
        filters=given if replace_filters else {**dict(spec.filters), **given},
        numerator={},
        group_by=(),
    )
    return compose(db, ungrouped, chosen, min_sample=min_sample)


def money_report(
    db: Any,
    spec: ViewSpec,
    *,
    extra_filters: Mapping[str, Any] | None = None,
    replace_filters: bool = False,
    min_sample: int = 0,
) -> ProfitReport:
    """A money view's realized and EV-adjusted report (#300, reused)."""
    if spec.kind != MONEY:
        raise Unavailable(f"{spec.label} is not a money view")
    return profit_report(
        db, query(spec, extra_filters, replace_filters=replace_filters), min_sample=min_sample,
    )


@dataclass(frozen=True)
class ViewSummary:
    """The reading a view reports above its table or grid, and its caveats."""

    sample_text: str
    value_text: str
    notes: tuple[str, ...]


def summarize(result: rb.ResearchResult, spec: ViewSpec) -> ViewSummary:
    """One line about what a result says, and why it might mislead.

    Built from the result rather than from the controls, so the headline and
    the table underneath it cannot disagree; the notes are the view's own
    "how to read this" plus the numerator/denominator sentence when there is a
    single row to state it on.
    """
    if not result.rows or result.empty_reason is not None:
        # An ungrouped query always comes back with one row, zeros and all, so
        # the engine's own ``empty_reason`` -- not the row count -- is what says
        # "nobody did this". A row of zeros presented as a reading is the exact
        # empty state the browser exists to avoid.
        reason = result.empty_reason or "The query matched nothing."
        return ViewSummary(result.sample_text, "no result", (spec.how_to_read, reason))

    if len(result.rows) > 1:
        # A grouped result has as many numbers as rows, so the headline is the
        # shape of the answer rather than one arbitrary row's value.
        return ViewSummary(result.sample_text, f"{len(result.rows)} groups", (spec.how_to_read,))

    row = result.rows[0]
    notes = [spec.how_to_read]
    frequency = row.get("frequency_bp")
    if frequency is not None:
        value_text = f"{float(frequency) / 100:.1f}%"
        numerator = row.get("actions")
        if numerator is not None:
            notes.insert(0, f"{numerator} of {row.get('opportunities')} decisions.")
    else:
        value_text = str(row.get("value", ""))
    return ViewSummary(result.sample_text, value_text, tuple(notes))


_check_catalogue()


__all__ = [
    "COMPOSITION",
    "DEFAULT_COMPOSITION_DIMENSION",
    "GRID",
    "HANDS",
    "KINDS",
    "MONEY",
    "TABLE",
    "VIEWS",
    "VIEW_IDS",
    "Unavailable",
    "ViewSpec",
    "ViewSummary",
    "hand_composition",
    "money_report",
    "preset",
    "query",
    "range_matrix",
    "summarize",
    "view",
]
