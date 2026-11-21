"""The replayer's decision panel as data: sections of labelled rows (#872).

The replayer used to write its decision analysis as dense lines of text. This
module turns the figures the replayer already computes -- the call and its pot
odds (``replayer_decision``), the hand's equity, the ICM pricing of an all-in
(``hand_icm``) and its bounty (``hand_bounty``) -- into a small presentation
model the widget only has to paint:

- a :class:`DecisionPanel` holds :class:`PanelSection` groups, each of
  :class:`PanelRow` label/value pairs with an explanatory tooltip;
- a row with a ``key`` is one of a section's few key figures, shown first and
  larger as a tile: the key is a stable semantic id (``call_amount``,
  ``required_equity``, ``pot_odds``...), so the colours and the layout never
  depend on the translated label, and ``accent`` sets the one the section is
  about apart;
- a row marked ``detail`` is only shown in the detailed view;
- a row without a value is a note, wrapped across the panel's width.

What it says, and what it does not:

- chip pot odds are the equity a call needs in chips; in a tournament they are
  labelled chip equity and never presented as an ICM threshold;
- the equity difference is a description in percentage points, not a
  recommendation, and the equity is the hand's against the cards shown;
- ICM $EV, chip EV and bounty EV keep their own sections and units, and are
  never added together;
- an all-in the ICM or bounty pricing refuses says why.

No widget or painting here: the rows are tested without a window. The
replayer is a post-session review screen (``docs/fair-play.md``).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.localized_formats import format_currency, format_number

__all__ = [
    "CallFigures",
    "DecisionPanel",
    "PanelRow",
    "PanelSection",
    "actor_section",
    "bet_section",
    "bounty_section",
    "cash_allin_section",
    "icm_section",
    "spr_section",
    "spr_tone",
    "tip",
]

# ICM and bounty pricing reasons that only mean the hand has nothing to price.
_QUIET_ICM = frozenset({"not a tournament hand", "no all-in in this hand"})
_QUIET_BOUNTY = frozenset({"not a tournament hand", "not a knockout tournament", "no all-in in this hand"})
_QUIET_ALLIN = frozenset({"not a tournament hand", "no all-in in this hand"})

# Descriptive SPR bands, not advice: below 3 the stack is shallow against the pot,
# above 10 it is deep.
SPR_LOW = Decimal(3)
SPR_HIGH = Decimal(10)


def spr_tone(values: tuple[Decimal, ...]) -> str:
    """The functional band of an SPR range: "low" when shallow, "high" when deep, else "".

    The range spans the per-opponent effective stacks; the band follows the largest,
    which is the hero's own stack when at least one opponent covers it.
    """
    usable = [value for value in values if value > 0]
    if not usable:
        return ""
    spr = max(usable)
    if spr < SPR_LOW:
        return "low"
    if spr > SPR_HIGH:
        return "high"
    return ""


@dataclass(frozen=True)
class PanelRow:
    """A label and its value; without a value, a note across the panel."""

    label: str
    value: str = ""
    tooltip: str = ""
    detail: bool = False  # only in the detailed view
    muted: bool = False  # an unavailable state or an assumption, drawn quieter
    key: str = ""  # semantic id of a key figure ("call_amount", "pot_odds"), shown first and as a tile
    accent: bool = False  # the key figure the section is about, set apart without implying a verdict
    tone: str = ""  # functional band ("low", "high"), drawn in its own colour; never a verdict

    @property
    def is_note(self) -> bool:
        return not self.value


@dataclass(frozen=True)
class PanelSection:
    """A titled group of rows: one player's decision, the ICM pricing, the bounty."""

    title: str
    rows: tuple[PanelRow, ...]
    tooltip: str = ""

    def visible(self, detailed: bool) -> PanelSection | None:
        rows = tuple(row for row in self.rows if detailed or not row.detail)
        return PanelSection(self.title, rows, self.tooltip) if rows else None


@dataclass(frozen=True)
class DecisionPanel:
    """The summary under the action: its sections, or a hint when there is nothing to show."""

    headline: str
    sections: tuple[PanelSection, ...] = field(default_factory=tuple)
    hint: str = ""

    def visible(self, detailed: bool) -> tuple[PanelSection, ...]:
        shown = (section.visible(detailed) for section in self.sections)
        return tuple(section for section in shown if section is not None)


@dataclass(frozen=True)
class CallFigures:  # pylint: disable=too-many-instance-attributes  # one flat record of a call
    """A call and what it can win, with the hand's equity when it is known."""

    call_amount: Decimal
    pot_odds_pct: Decimal | None
    pot_before_call: Decimal | None = None  # the pot drawn on the table
    final_pot: Decimal | None = None  # what the call can win, the call included
    facing_pct: Decimal | None = None  # the bet faced, in % of the pot before it
    equity_pct: Decimal | None = None
    equity_exhaustive: bool | None = None  # True: every board enumerated; False: simulated
    opponents: int = 1  # live opponents the actor faces: the call is multiway past one

    @property
    def ratio(self) -> Decimal | None:
        """Pot odds as a ratio: what the call can win from the others, per unit called."""
        if self.call_amount <= 0:
            return None
        if self.final_pot is not None and self.final_pot > 0:
            return max(Decimal(0), self.final_pot - self.call_amount) / self.call_amount
        if self.pot_odds_pct:
            return (Decimal(100) - self.pot_odds_pct) / self.pot_odds_pct
        return None

    @property
    def uncontested(self) -> Decimal:
        """Money on the table the call cannot win: an uncalled excess, side money."""
        if self.pot_before_call is None or not self.final_pot:
            return Decimal(0)
        return max(Decimal(0), self.pot_before_call + self.call_amount - self.final_pot)


def tip(key: str) -> str:
    """The explanation of a figure, translated when it is shown."""
    texts = {
        "call_amount": _("What the player still has to put in to call, capped at their stack."),
        "final_pot": _(
            "Everything the call can win, the call included. An all-in caller only wins as much of each "
            "bet as they match: the rest is returned uncalled or goes to a side pot."
        ),
        "required": _(
            "Pot odds: the share of the final pot the call costs. A hand that wins at least this often "
            "breaks even in chips if it goes to showdown with no more betting."
        ),
        "required_chips": _(
            "Pot odds in chips: the share of the final pot the call costs. In a tournament chips are not "
            "prize money, so this is not an ICM calling threshold."
        ),
        "equity": _(
            "How often the hand wins the pot, ties counted as shares, against the other hands shown in "
            "this history if every card were dealt now. Known only after the hand: these cards were hidden "
            "at the table."
        ),
        "difference": _(
            "Estimated hand equity less the required equity, in percentage points. It describes the "
            "spot; it is not a fold, call or raise recommendation, and it leaves out later betting and "
            "prize equity."
        ),
        "ratio": _("What the call can win from the others against what it costs: 3:1 wins three times the call."),
        "pot_before_call": _(
            "The pot drawn on the table: every chip put in so far, including any bet the caller cannot match."
        ),
        "uncontested": _(
            "Money on the table the call cannot win: the part of a bet larger than the caller's stack, "
            "which goes back uncalled, or a side pot between other players."
        ),
        "effective_pot": _("The pot on the table less the money the call cannot win."),
        "facing": _("The bet faced, in percent of the pot before it."),
        "bet_size": _("The bet or raise, in percent of the pot before it."),
        "spr": _(
            "Stack-to-pot ratio: the effective stack at the start of the street divided by the pot then. "
            "A range when the opponents' stacks differ. Below 3 the stack is shallow against the pot, "
            "above 10 it is deep: descriptive bands, not advice."
        ),
        "mdf": _(
            "Minimum defence frequency: how often the opponent must continue so that a bet that never wins "
            "when called makes no profit. Simplified heads-up model, not a solver prescription."
        ),
        "fold_equity": _(
            "How often the opponent must fold for a bet that never wins when called to break even. Same "
            "simplified heads-up model as MDF, not a solver prescription."
        ),
        "chip_ev": _(
            "The hand's equity share of the pot less what the player put in, in chips. Chip EV is not tournament money."
        ),
        "icm_ev": _(
            "Independent Chip Model: the prize equity expected after the all-in less the prize equity the "
            "stacks held before the hand, in the payout's unit."
        ),
        "icm_result": _(
            "The prize equity the hand actually moved: read it next to ICM $EV as winnings next to chip EV."
        ),
        "model": _("Whether the hand could be priced, and under which assumptions."),
        "bounty_ev": _(
            "The bounty cash the all-in wins on average: the chance to win the whole pot times the bounty paid now."
        ),
        "head_ev": _(
            "Progressive knockout: what winning adds to the player's own bounty on average, paid later if at all."
        ),
        "adjusted_chip_ev": _("Chip EV plus the bounty EV converted to chips at the buy-in's chip value."),
        "icm_section": _(
            "Prize equity of the all-in under the Independent Chip Model, with the existing payout "
            "structure and stacks. Separate from chip EV and from any bounty."
        ),
        "bounty_section": _("The bounty the all-in can win. Separate from ICM $EV: the two are not added."),
    }
    return texts.get(key, "")


def _pct(value: Decimal) -> str:
    return _("%(value)s%%") % {"value": format_number(value, 1)}


def _pts(value: Decimal) -> str:
    return _("%(value)s pts") % {"value": format_number(value, 1, show_plus=True)}


def _chips(value: Any) -> str:
    return _("%(chips)s chips") % {"chips": format_number(value, 0, show_plus=True)}


def _of_pot(value: Decimal) -> str:
    return _("%(size)s%% of the pot") % {"size": format_number(value, 0)}


def _equity_basis(exhaustive: bool | None) -> str:
    if exhaustive:
        return _("Equity against the hands shown, every remaining board enumerated.")
    if exhaustive is False:
        return _("Equity against the hands shown, estimated from simulated boards.")
    return _("Equity against the hands shown.")


def _pot_breakdown(call: CallFigures, amount: Callable[[Any], str]) -> list[PanelRow]:
    """In detail: the pot on the table, what the call cannot win of it, and what it can (#872)."""
    if call.pot_before_call is None or not call.final_pot:
        return []
    rows = [PanelRow(_("Pot on the table"), amount(call.pot_before_call), tip("pot_before_call"), detail=True)]
    if call.uncontested > 0:
        rows.append(PanelRow(_("Uncalled or side money"), amount(call.uncontested), tip("uncontested"), detail=True))
        effective = call.final_pot - call.call_amount
        rows.append(PanelRow(_("Effective pot before call"), amount(effective), tip("effective_pot"), detail=True))
    return rows


def _call_rows(call: CallFigures, amount: Callable[[Any], str], *, tournament: bool) -> list[PanelRow]:
    rows = [PanelRow(_("Call amount"), amount(call.call_amount), tip("call_amount"), key="call_amount")]
    if call.final_pot:
        rows.append(PanelRow(_("Effective pot after call"), amount(call.final_pot), tip("final_pot")))
    if call.pot_odds_pct is not None:
        if tournament:
            label, row_key, tip_key = _("Required chip equity"), "required_chip_equity", "required_chips"
        else:
            label, row_key, tip_key = _("Required equity"), "required_equity", "required"
        rows.append(PanelRow(label, _pct(call.pot_odds_pct), tip(tip_key), key=row_key, accent=True))
    if call.equity_pct is not None:
        rows.append(PanelRow(_("Estimated hand equity"), _pct(call.equity_pct), tip("equity")))
        if call.pot_odds_pct is not None:
            rows.append(PanelRow(_("Equity difference"), _pts(call.equity_pct - call.pot_odds_pct), tip("difference")))
            # The equity is against the cards shown in the history, which were hidden at the
            # table: say so next to the difference, never a "call is profitable" verdict.
            rows.append(PanelRow(_("Against the shown hands only; not an action recommendation."), muted=True))
    ratio = call.ratio
    if ratio is not None:
        rows.append(
            PanelRow(_("Pot odds"), _("%(ratio)s:1") % {"ratio": format_number(ratio, 1)}, tip("ratio"), key="pot_odds")
        )
    if call.facing_pct is not None:
        rows.append(PanelRow(_("Facing"), _of_pot(call.facing_pct), tip("facing"), detail=True))
    rows.extend(_pot_breakdown(call, amount))
    if call.equity_pct is not None:
        rows.append(PanelRow(_equity_basis(call.equity_exhaustive), detail=True, muted=True))
    rows.extend(_multiway_note(call))
    if tournament:
        rows.append(PanelRow(_("Chip pot odds: not an ICM threshold."), detail=True, muted=True))
    return rows


def _multiway_note(call: CallFigures) -> list[PanelRow]:
    """The note of a call into a multiway pot: the odds already count every chip in."""
    if call.opponents <= 1:
        return []
    # The call needs the same share of the whole pot, against all the hands still
    # in, not one of them.
    return [
        PanelRow(
            _("Multiway pot: %(n)s opponents live; the odds and equity are against all of them.")
            % {"n": call.opponents},
            muted=True,
        )
    ]


def actor_section(  # noqa: PLR0913 - the figures of one decision, all keyword-only
    name: str,
    *,
    amount: Callable[[Any], str],
    call: CallFigures | None = None,
    equity_pct: Decimal | None = None,
    equity_exhaustive: bool | None = None,
    spr: str = "",
    spr_values: tuple[Decimal, ...] = (),
    tournament: bool = False,
) -> PanelSection | None:
    """The decision of the player about to act: the call they face, or only their equity and SPR."""
    if call is not None:
        rows = _call_rows(call, amount, tournament=tournament)
        title = _("%(name)s to call") % {"name": name}
    else:
        rows = []
        if equity_pct is not None:
            rows.append(PanelRow(_("Estimated hand equity"), _pct(equity_pct), tip("equity")))
            rows.append(PanelRow(_equity_basis(equity_exhaustive), detail=True, muted=True))
        title = _("%(name)s to act") % {"name": name}
    if spr:
        rows.append(PanelRow(_("SPR"), spr, tip("spr"), tone=spr_tone(spr_values)))
    # The key figures first, then the summary, then what the detailed view adds.
    rows.sort(key=lambda row: (not row.key, row.detail))
    return PanelSection(title, tuple(rows)) if rows else None


def spr_section(name: str, spr: str, *, spr_values: tuple[Decimal, ...] = ()) -> PanelSection | None:
    """The player's street SPR while someone else acts."""
    if not spr:
        return None
    row = PanelRow(_("SPR"), spr, tip("spr"), tone=spr_tone(spr_values))
    return PanelSection(name, (row,))


def bet_section(
    name: str,
    action: str,
    *,
    bet_pct: Decimal,
    mdf_pct: Decimal | None,
    fold_equity_pct: Decimal | None,
    multiway: bool,
) -> PanelSection:
    """The bet or raise just made: its size, and in detail what it asks of a lone opponent."""
    rows = [PanelRow(_("Bet size"), _of_pot(bet_pct), tip("bet_size"), key="bet_size")]
    if mdf_pct is not None and fold_equity_pct is not None:
        rows.append(PanelRow(_("MDF (heads-up)"), _pct(mdf_pct), tip("mdf"), detail=True))
        rows.append(
            PanelRow(_("Fold equity needed (heads-up)"), _pct(fold_equity_pct), tip("fold_equity"), detail=True)
        )
        rows.append(
            PanelRow(_("Simplified model: one opponent, a bluff that never wins when called."), detail=True, muted=True)
        )
    elif multiway:
        rows.append(PanelRow(_("MDF and fold equity: heads-up only."), detail=True, muted=True))
    return PanelSection(_("%(name)s %(action)s") % {"name": name, "action": action}, tuple(rows))


def _unavailable(title: str, reason: str, tooltip: str) -> PanelSection:
    return PanelSection(
        title,
        (
            PanelRow(_("Model status"), _("Unavailable"), tip("model"), muted=True),
            PanelRow(reason, muted=True),
        ),
        tooltip,
    )


def icm_section(priced: Any, hero: str) -> PanelSection | None:
    """The hero's all-in in prize equity (#446), or why it is not priced; None when there is nothing to say.

    The caller only asks once the hero is in an all-in, not folded.
    """
    title = _("Tournament — ICM")
    if priced is None:
        return None
    allin = priced.allin
    if allin is None:
        if priced.reason in _QUIET_ICM:
            return None
        return _unavailable(title, priced.reason, tip("icm_section"))
    if hero not in allin.players:
        return None
    rows = [
        PanelRow(_("Chip EV"), _chips(allin.chip_ev[hero]), tip("chip_ev"), key="chip_ev"),
        PanelRow(_("ICM $EV"), format_number(allin.icm_ev[hero], 2, show_plus=True), tip("icm_ev"), key="icm_ev"),
        PanelRow(
            _("ICM result"),
            format_number(allin.icm_result[hero], 2, show_plus=True),
            tip("icm_result"),
            key="icm_result",
        ),
        PanelRow(_("Model status"), _("Available"), tip("model")),
    ]
    if allin.table_only:
        rows.append(
            PanelRow(_("Priced as if this table were the whole field: the other stacks are unknown."), muted=True)
        )
    equity = allin.equity.get(hero)
    if equity is not None:
        rows.append(PanelRow(_("Equity at the all-in"), _pct(Decimal(str(equity)) * 100), tip("equity"), detail=True))
    if len(allin.players) > 2:
        rows.append(
            PanelRow(
                _("Multiway all-in on a single pot: split pots are split evenly among the players left."),
                detail=True,
                muted=True,
            )
        )
    else:
        rows.append(PanelRow(_("Heads-up all-in, priced with the stored payouts."), detail=True, muted=True))
    return PanelSection(title, tuple(rows), tip("icm_section"))


def cash_allin_section(allin: Any, hero: str, amount: Callable[[Any], str], *, reason: str = "") -> PanelSection | None:
    """The hero's all-in in a cash hand, priced in chips (money): the cash twin of the ICM section.

    In a cash game the pot itself is the prize, so the all-in is priced in chips --
    equity share of the pot less what was put in -- with no ICM on top. Multiway
    all-ins on a single pot are priced like the tournament ones; None when the
    hero is not in the all-in or there is nothing to say.
    """
    title = _("Cash — all-in")
    if allin is None:
        if reason in _QUIET_ALLIN:
            return None
        return _unavailable(title, reason, tip("cash_allin_section"))
    if hero not in allin.players:
        return None
    rows = [
        PanelRow(_("All-in EV"), amount(allin.chip_ev[hero]), tip("chip_ev"), key="chip_ev"),
        PanelRow(_("Equity at the all-in"), _pct(Decimal(str(allin.equity[hero])) * 100), tip("equity"), detail=True),
        PanelRow(_("Cash game: priced in chips, no ICM."), detail=True, muted=True),
    ]
    if len(allin.players) > 2:
        rows.append(
            PanelRow(
                _("Multiway all-in on a single pot: split pots are split evenly among the players left."),
                detail=True,
                muted=True,
            )
        )
    else:
        rows.append(PanelRow(_("Heads-up all-in, priced in chips."), detail=True, muted=True))
    return PanelSection(title, tuple(rows), tip("cash_allin_section"))


def bounty_section(priced: Any, hero: str) -> PanelSection | None:
    """The bounty the hero's all-in can win (#447), or why it is not priced; None when there is nothing to say.

    The caller only asks once the hero is in an all-in, not folded.
    """
    title = _("Knockout bounty")
    if priced is None:
        return None
    allin = priced.allin
    if allin is None:
        if priced.reason in _QUIET_BOUNTY:
            return None
        return _unavailable(title, priced.reason, tip("bounty_section"))
    if hero not in allin.players:
        return None

    def money(value: Any) -> str:
        if allin.currency:
            return format_currency(value, allin.currency, show_plus=True)
        return format_number(value, 2, show_plus=True)

    if not allin.collects[hero]:
        rows = [
            PanelRow(_("Bounty EV"), money(0), tip("bounty_ev"), key="bounty_ev"),
            PanelRow(_("Winning does not bust the opponent: there is no bounty to win."), muted=True),
        ]
        return PanelSection(title, tuple(rows), tip("bounty_section"))
    rows = [PanelRow(_("Bounty EV"), money(allin.bounty_ev[hero]), tip("bounty_ev"), key="bounty_ev")]
    if allin.head_ev[hero]:
        rows.append(PanelRow(_("Added to own bounty"), money(allin.head_ev[hero]), tip("head_ev"), key="head_ev"))
    if allin.adjusted_chip_ev is not None:
        rows.append(
            PanelRow(
                _("Bounty-adjusted chip EV"),
                _chips(allin.adjusted_chip_ev[hero]),
                tip("adjusted_chip_ev"),
                key="adjusted_chip_ev",
            )
        )
    rows.append(PanelRow(_("Model status"), _("Available"), tip("model")))
    rows.append(PanelRow(_("Not added to ICM $EV: this is not a complete PKO model."), detail=True, muted=True))
    return PanelSection(title, tuple(rows), tip("bounty_section"))
