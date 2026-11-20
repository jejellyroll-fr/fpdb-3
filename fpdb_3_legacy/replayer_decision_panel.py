"""Structured presentation model and educational tooltips for the replayer decision panel (#872).

Refactors decision analysis into clean, context-aware sections:
- Common decision summary (Cash Game or Tournament chip-EV view)
- Expanded details (progressive disclosure: pot breakdown, ratios, sizing, MDF/FE model)
- Tournament ICM section (heads-up all-ins, payouts, chip EV vs prize $EV)
- Tournament Bounty section (knockout/PKO bounty EV, bounty-adjusted chip EV)

Independent of PySide6 widget hierarchy; post-session only (docs/fair-play.md).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any

from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.localized_formats import format_currency, format_number

# Educational tooltips explaining metrics, assumptions, and scope limits (#872).
EDUCATIONAL_TOOLTIPS: dict[str, str] = {
    "pot_odds": _(
        "Required chip equity (pot odds): The percentage of the final contestable pot your call represents: "
        "call / (effective pot after call). Under pure chip-EV, your hand needs at least this much showdown equity "
        "against the opponent's range to break even on a direct call."
    ),
    "spr": _(
        "Stack-to-Pot Ratio (SPR): Effective stack divided by the pot at the start of the street. "
        "Measures remaining depth and commitment: low (<3) indicates high commitment, "
        "medium (3–6), high (>6) leaves room for postflop maneuvers."
    ),
    "mdf": _(
        "Minimum Defence Frequency (MDF): The portion of your range required to continue to make a zero-equity bluff "
        "indifferent: pot / (pot + bet). Applies to a simplified heads-up, zero-equity-bluff model—not a universal solver prescription."
    ),
    "fold_equity": _(
        "Fold equity needed: The percentage of opponent folds required for a zero-equity bluff to break even immediately: "
        "bet / (pot + bet). Simplified heads-up model; real bluffs often retain some showdown equity when called."
    ),
    "chip_ev": _(
        "Chip EV: Expected chip return of the confrontation: (equity × pot) - call. "
        "In tournaments, chips won are worth less in real prize money than chips lost."
    ),
    "icm_ev": _(
        "ICM $EV: Expected change in tournament prize equity according to the Independent Chip Model. "
        "Accounts for payouts and the declining marginal value of chips."
    ),
    "icm_result": _(
        "ICM result: The actual change in tournament prize equity that occurred as a result of the showdown outcome."
    ),
    "bubble_factor": _(
        "Bubble factor: Ratio of prize equity lost if busted to prize equity gained if doubling up. "
        "Values above 1.0 indicate chips lost hurt more than chips gained, requiring higher equity to call."
    ),
    "hand_equity": _(
        "Estimated hand equity: Estimated showdown win/tie percentage based on known cards. "
        "Monte Carlo simulation (20,000 boards) or exact evaluation against known hole cards; not an action recommendation."
    ),
    "equity_diff": _(
        "Equity difference: Descriptive percentage-point difference between estimated hand equity and required chip equity. "
        "A positive difference indicates an equity edge over pot odds; not an ICM threshold or a strategic recommendation."
    ),
    "effective_pot": _(
        "Effective pot after call: Total contestable pot hero can win if calling, excluding uncalled bets "
        "and side pot money that hero's stack cannot contest."
    ),
    "pot_breakdown": _(
        "Effective-pot arithmetic: Explains nominal vs contestable pot sizes when an all-in stack faces a larger raise."
    ),
    "bounty_ev": _(
        "Bounty EV: Expected cash bounty won from knocking out an opponent. "
        "In progressive knockouts (PKO), the half added to hero's own bounty is reported separately."
    ),
    "bounty_chip_ev": _(
        "Bounty-adjusted chip EV: Chip EV plus cash bounty converted into chips (using prize buy-in per starting stack). "
        "Assumes constant chip valuation."
    ),
    "model_status": _(
        "Model status: Availability and scope limits of the analytical model "
        "(e.g. heads-up all-in, known payout structure, table-only field assumption)."
    ),
}


@dataclass(frozen=True)
class DecisionMetricRow:
    key: str
    label: str
    value: str
    tooltip: str = ""
    detail_only: bool = False
    is_note: bool = False
    neutral_color: str = "#eef3f7"


@dataclass(frozen=True)
class DecisionPanelSection:
    id: str
    title: str
    rows: tuple[DecisionMetricRow, ...]
    notes: tuple[str, ...] = ()
    detail_only: bool = False


@dataclass(frozen=True)
class DecisionPanelModel:
    header: str
    game_type: str  # "cash" or "tour"
    is_tourney: bool
    is_ko: bool
    actor_name: str
    sections: tuple[DecisionPanelSection, ...]
    is_detailed: bool = False
    guidance: str = ""

    def visible_sections(self, detailed: bool | None = None) -> list[DecisionPanelSection]:
        is_det = self.is_detailed if detailed is None else detailed
        result = []
        for section in self.sections:
            if section.detail_only and not is_det:
                continue
            visible_rows = tuple(r for r in section.rows if not (r.detail_only and not is_det))
            notes = section.notes if is_det else ()
            if visible_rows or notes:
                result.append(replace(section, rows=visible_rows, notes=notes))
        return result

    def to_summary_lines(self, detailed: bool | None = None) -> list[tuple[str, str]]:
        """Backwards-compatible text rendering of visible sections with neutral informational styling."""
        lines: list[tuple[str, str]] = []
        visible = self.visible_sections(detailed)
        if not visible and self.guidance:
            return [(self.guidance, "#9aa5ad")]

        for section in visible:
            if section.title and section.id not in {"summary", "bet_summary"}:
                lines.append((section.title, "#74b9ff"))
            for row in section.rows:
                if row.is_note:
                    lines.append((row.label, "#9aa5ad"))
                else:
                    color = row.neutral_color or "#eef3f7"
                    lines.append((f"{row.label}: {row.value}", color))
            for note in section.notes:
                lines.append((note, "#9aa5ad"))
        return lines


def format_panel_spr(values: tuple[Decimal, ...] | None) -> str:
    """Format SPR values into a single number or a range for multiway pots."""
    if not values:
        return ""
    non_zero = tuple(v for v in values if v > 0)
    if not non_zero:
        return ""

    def short(value: Decimal) -> str:
        return format_number(value, 2).rstrip("0").rstrip(".,")

    low, high = short(min(non_zero)), short(max(non_zero))
    return low if low == high else f"{low}–{high}"


def _format_currency_ev(value: float, currency_code: str) -> str:
    ev_str = format_number(value, 2, show_plus=True)
    if currency_code and currency_code not in {"", "T$", "play"}:
        sign = "+" if value >= 0 else ""
        return sign + format_currency(value, currency_code)
    return ev_str


def _format_bounty_money(val: Decimal | float | int, currency: str | None) -> str:
    sign = "+" if val >= 0 else ""
    if currency and currency not in {"", "T$", "play"}:
        return sign + format_currency(val, currency)
    return sign + format_number(val, 2)


def _build_equity_metrics(metrics: dict[str, Any]) -> tuple[tuple[DecisionMetricRow, ...], tuple[str, ...]]:
    rows: list[DecisionMetricRow] = []
    notes: list[str] = []
    hand_eq = metrics.get("hand_equity_pct")
    if hand_eq is None:
        hand_eq = metrics.get("call_equity_pct")
    diff_pts = metrics.get("equity_diff_pts")
    if diff_pts is None:
        diff_pts = metrics.get("call_edge_pts")

    if hand_eq is not None:
        rows.append(
            DecisionMetricRow(
                key="hand_equity",
                label=_("Estimated hand equity"),
                value=f"{format_number(hand_eq, 1)}%",
                tooltip=EDUCATIONAL_TOOLTIPS["hand_equity"],
            )
        )
        if diff_pts is not None:
            rows.append(
                DecisionMetricRow(
                    key="equity_diff",
                    label=_("Equity difference"),
                    value=f"{format_number(diff_pts, 1, show_plus=True)} pts",
                    tooltip=EDUCATIONAL_TOOLTIPS["equity_diff"],
                    neutral_color="#74b9ff",
                )
            )
        notes.append(
            _("Equity difference is a descriptive percentage-point difference, not a strategic recommendation.")
        )
        notes.append(
            _("Equity estimation: Monte Carlo simulation (20,000 boards) against known cards.")
        )
    else:
        equity_reason = metrics.get("equity_reason") or _("missing cards")
        rows.append(
            DecisionMetricRow(
                key="hand_equity",
                label=_("Estimated hand equity"),
                value=_("Unavailable: %s") % equity_reason,
                tooltip=EDUCATIONAL_TOOLTIPS["hand_equity"],
                detail_only=True,
                neutral_color="#9aa5ad",
            )
        )
        notes.append(_("Hand equity unavailable: %s.") % equity_reason)

    return tuple(rows), tuple(notes)


def _build_facing_call_summary(
    metrics: dict[str, Any],
    decision: Any | None,
    shows_spr: bool,
    is_tourney: bool,
    amount_formatter: Callable[[Decimal | int | float], str],
) -> tuple[tuple[DecisionMetricRow, ...], tuple[str, ...]]:
    rows: list[DecisionMetricRow] = []
    call_amt = metrics.get("call_amount", Decimal(0))
    rows.append(
        DecisionMetricRow(
            key="call_amount",
            label=_("Call amount"),
            value=amount_formatter(call_amt),
            tooltip=EDUCATIONAL_TOOLTIPS["pot_odds"],
        )
    )

    eff_pot = metrics.get("effective_pot")
    if eff_pot is not None and eff_pot > 0:
        rows.append(
            DecisionMetricRow(
                key="effective_pot",
                label=_("Effective pot after call"),
                value=amount_formatter(eff_pot),
                tooltip=EDUCATIONAL_TOOLTIPS["effective_pot"],
            )
        )

    odds_pct = metrics.get("pot_odds_pct")
    if odds_pct is not None:
        label = _("Required chip equity") if is_tourney else _("Required equity")
        rows.append(
            DecisionMetricRow(
                key="required_equity",
                label=label,
                value=f"{format_number(odds_pct, 1)}%",
                tooltip=EDUCATIONAL_TOOLTIPS["pot_odds"],
            )
        )

    eq_rows, eq_notes = _build_equity_metrics(metrics)
    rows.extend(eq_rows)

    if shows_spr and decision and decision.spr:
        spr_text = format_panel_spr(decision.spr)
        if spr_text:
            rows.append(
                DecisionMetricRow(
                    key="spr",
                    label=_("SPR"),
                    value=spr_text,
                    tooltip=EDUCATIONAL_TOOLTIPS["spr"],
                )
            )

    ratio = metrics.get("pot_odds_ratio")
    if ratio is not None:
        rows.append(
            DecisionMetricRow(
                key="pot_odds_ratio",
                label=_("Pot odds ratio"),
                value=f"{format_number(ratio, 1)}:1",
                tooltip=EDUCATIONAL_TOOLTIPS["pot_odds"],
                detail_only=True,
            )
        )

    if decision and decision.bet_pct is not None:
        rows.append(
            DecisionMetricRow(
                key="facing_bet_pct",
                label=_("Facing bet size"),
                value=f"{format_number(decision.bet_pct, 0)}% of pot",
                tooltip=EDUCATIONAL_TOOLTIPS["pot_odds"],
                detail_only=True,
            )
        )

    return tuple(rows), eq_notes


def _build_pot_breakdown(
    metrics: dict[str, Any],
    amount_formatter: Callable[[Decimal | int | float], str],
) -> DecisionPanelSection | None:
    call_amt = metrics.get("call_amount", Decimal(0))
    pot_before = metrics.get("pot_before_call")
    eff_final = metrics.get("effective_pot")
    uncalled_excess = metrics.get("uncalled_excess", Decimal(0))
    if pot_before is None or eff_final is None:
        return None

    eff_before = max(Decimal(0), eff_final - call_amt)
    pot_rows = [
        DecisionMetricRow(
            key="displayed_pot_before",
            label=_("Displayed pot before call"),
            value=amount_formatter(pot_before),
            tooltip=EDUCATIONAL_TOOLTIPS["pot_breakdown"],
        ),
        DecisionMetricRow(
            key="hero_additional_call",
            label=_("Additional call"),
            value=amount_formatter(call_amt),
            tooltip=EDUCATIONAL_TOOLTIPS["pot_breakdown"],
        ),
    ]
    if uncalled_excess and uncalled_excess > Decimal(0):
        pot_rows.append(
            DecisionMetricRow(
                key="uncalled_excess",
                label=_("Uncalled excess"),
                value=amount_formatter(uncalled_excess),
                tooltip=EDUCATIONAL_TOOLTIPS["pot_breakdown"],
            )
        )
        pot_rows.append(
            DecisionMetricRow(
                key="effective_pot_before",
                label=_("Effective pot before call"),
                value=amount_formatter(eff_before),
                tooltip=EDUCATIONAL_TOOLTIPS["pot_breakdown"],
            )
        )
    pot_rows.append(
        DecisionMetricRow(
            key="effective_final_pot",
            label=_("Effective final pot"),
            value=amount_formatter(eff_final),
            tooltip=EDUCATIONAL_TOOLTIPS["effective_pot"],
        )
    )
    return DecisionPanelSection(
        id="pot_breakdown",
        title=_("POT BREAKDOWN"),
        rows=tuple(pot_rows),
        detail_only=True,
    )


def _build_bet_summary(
    decision: Any,
    shows_spr: bool,
    amount_formatter: Callable[[Decimal | int | float], str],
) -> DecisionPanelSection:
    bet_rows = [
        DecisionMetricRow(
            key="bet_amount",
            label=_("Bet amount"),
            value=amount_formatter(decision.bet_amount),
        ),
    ]
    if decision.bet_pct is not None:
        bet_rows.append(
            DecisionMetricRow(
                key="bet_pct",
                label=_("Bet sizing"),
                value=f"{format_number(decision.bet_pct, 0)}% of the pot",
            )
        )
    if shows_spr and decision.spr:
        spr_text = format_panel_spr(decision.spr)
        if spr_text:
            bet_rows.append(
                DecisionMetricRow(
                    key="spr",
                    label=_("SPR"),
                    value=spr_text,
                    tooltip=EDUCATIONAL_TOOLTIPS["spr"],
                )
            )

    bet_notes: list[str] = []
    if decision.mdf_pct is not None and decision.fold_equity_pct is not None:
        bet_rows.append(
            DecisionMetricRow(
                key="mdf_pct",
                label=_("MDF (heads-up)"),
                value=f"{format_number(decision.mdf_pct, 1)}%",
                tooltip=EDUCATIONAL_TOOLTIPS["mdf"],
                detail_only=True,
            )
        )
        bet_rows.append(
            DecisionMetricRow(
                key="fold_equity_pct",
                label=_("Fold equity needed"),
                value=f"{format_number(decision.fold_equity_pct, 1)}%",
                tooltip=EDUCATIONAL_TOOLTIPS["fold_equity"],
                detail_only=True,
            )
        )
        bet_notes.append(
            _("MDF and fold equity apply to the simplified heads-up, zero-equity-bluff model—not a universal solver prescription.")
        )
    elif len(decision.effective) > 1:
        bet_rows.append(
            DecisionMetricRow(
                key="mdf_multiway",
                label=_("MDF / fold equity"),
                value=_("Heads-up only"),
                tooltip=EDUCATIONAL_TOOLTIPS["mdf"],
                detail_only=True,
            )
        )

    return DecisionPanelSection(
        id="bet_summary",
        title=_("DECISION SUMMARY"),
        rows=tuple(bet_rows),
        notes=tuple(bet_notes),
    )


def _build_icm_section(
    hand_icm: Any | None,
    actor_name: str,
    currency_code: str,
    is_allin: bool,
    is_detailed: bool,
) -> DecisionPanelSection | None:
    if hand_icm is None or not (is_allin or is_detailed):
        return None

    icm_rows: list[DecisionMetricRow] = []
    icm_notes: list[str] = []
    allin = getattr(hand_icm, "allin", None)
    if allin is not None and actor_name in allin.players:
        chip_ev_val = allin.chip_ev.get(actor_name, Decimal(0))
        icm_ev_val = allin.icm_ev.get(actor_name, 0.0)
        icm_res_val = allin.icm_result.get(actor_name, 0.0)
        payout_currency = getattr(allin, "currency", None) or currency_code

        icm_rows.append(
            DecisionMetricRow(
                key="chip_ev",
                label=_("Chip EV"),
                value=f"{format_number(chip_ev_val, 0, show_plus=True)} chips",
                tooltip=EDUCATIONAL_TOOLTIPS["chip_ev"],
            )
        )
        icm_rows.append(
            DecisionMetricRow(
                key="icm_ev",
                label=_("ICM $EV"),
                value=_format_currency_ev(icm_ev_val, payout_currency),
                tooltip=EDUCATIONAL_TOOLTIPS["icm_ev"],
            )
        )
        icm_rows.append(
            DecisionMetricRow(
                key="icm_result",
                label=_("ICM result"),
                value=_format_currency_ev(icm_res_val, payout_currency),
                tooltip=EDUCATIONAL_TOOLTIPS["icm_result"],
            )
        )

        status_label = _("Available (table-only field assumption)") if allin.table_only else _("Available")
        icm_rows.append(
            DecisionMetricRow(
                key="icm_status",
                label=_("Model status"),
                value=status_label,
                tooltip=EDUCATIONAL_TOOLTIPS["model_status"],
                neutral_color="#9aa5ad",
            )
        )
        if allin.table_only:
            icm_notes.append(_("Field stacks unknown: table taken as whole tournament field."))
    else:
        reason = getattr(hand_icm, "reason", "") or _("no all-in in this hand")
        quiet = {"not a tournament hand"}
        if not is_detailed:
            quiet.add("no all-in in this hand")
        if reason not in quiet:
            icm_rows.append(
                DecisionMetricRow(
                    key="icm_status",
                    label=_("Model status"),
                    value=_("Unavailable: %s") % reason,
                    tooltip=EDUCATIONAL_TOOLTIPS["model_status"],
                    neutral_color="#9aa5ad",
                )
            )

    if not icm_rows and not icm_notes:
        return None
    return DecisionPanelSection(
        id="icm",
        title=_("TOURNAMENT — ICM"),
        rows=tuple(icm_rows),
        notes=tuple(icm_notes),
    )


def _build_active_bounty_rows(allin: Any, actor_name: str, currency_code: str) -> list[DecisionMetricRow]:
    collects = allin.collects.get(actor_name, Decimal(0))
    b_ev = allin.bounty_ev.get(actor_name, Decimal(0))
    h_ev = allin.head_ev.get(actor_name, Decimal(0))
    b_currency = getattr(allin, "currency", None) or currency_code

    if not collects:
        return [
            DecisionMetricRow(
                key="bounty_ev",
                label=_("Bounty EV"),
                value=_format_bounty_money(0, b_currency),
                tooltip=EDUCATIONAL_TOOLTIPS["bounty_ev"],
            ),
            DecisionMetricRow(
                key="bounty_status",
                label=_("Model status"),
                value=_("Winning does not bust opponent"),
                tooltip=EDUCATIONAL_TOOLTIPS["model_status"],
                neutral_color="#9aa5ad",
            ),
        ]

    rows = [
        DecisionMetricRow(
            key="bounty_ev",
            label=_("Bounty EV"),
            value=_format_bounty_money(b_ev, b_currency),
            tooltip=EDUCATIONAL_TOOLTIPS["bounty_ev"],
        ),
    ]
    if h_ev:
        rows.append(
            DecisionMetricRow(
                key="head_ev",
                label=_("To own bounty"),
                value=_format_bounty_money(h_ev, b_currency),
                tooltip=EDUCATIONAL_TOOLTIPS["bounty_ev"],
                detail_only=True,
            )
        )
    if allin.adjusted_chip_ev is not None:
        adj_val = allin.adjusted_chip_ev.get(actor_name)
        if adj_val is not None:
            rows.append(
                DecisionMetricRow(
                    key="bounty_chip_ev",
                    label=_("Bounty-adjusted chip EV"),
                    value=f"{format_number(adj_val, 0, show_plus=True)} chips",
                    tooltip=EDUCATIONAL_TOOLTIPS["bounty_chip_ev"],
                )
            )
    rows.append(
        DecisionMetricRow(
            key="bounty_status",
            label=_("Model status"),
            value=_("Available"),
            tooltip=EDUCATIONAL_TOOLTIPS["model_status"],
            neutral_color="#9aa5ad",
        )
    )
    return rows


def _build_bounty_section(
    hand_bounty: Any | None,
    actor_name: str,
    currency_code: str,
    is_allin: bool,
    is_detailed: bool,
) -> DecisionPanelSection | None:
    if hand_bounty is None or not (is_allin or is_detailed):
        return None

    bounty_rows: list[DecisionMetricRow] = []
    allin = getattr(hand_bounty, "allin", None)
    if allin is not None and actor_name in allin.players:
        bounty_rows.extend(_build_active_bounty_rows(allin, actor_name, currency_code))
    else:
        reason = getattr(hand_bounty, "reason", "") or _("no all-in in this hand")
        quiet = {"not a tournament hand", "not a knockout tournament"}
        if not is_detailed:
            quiet.add("no all-in in this hand")
        if reason not in quiet:
            bounty_rows.append(
                DecisionMetricRow(
                    key="bounty_status",
                    label=_("Model status"),
                    value=_("Unavailable: %s") % reason,
                    tooltip=EDUCATIONAL_TOOLTIPS["model_status"],
                    neutral_color="#9aa5ad",
                )
            )

    if not bounty_rows:
        return None
    return DecisionPanelSection(
        id="bounty",
        title=_("TOURNAMENT — BOUNTY"),
        rows=tuple(bounty_rows),
    )


def build_decision_panel_model(
    *,
    header: str,
    frame: Any,
    metrics: dict[str, Any],
    decision: Any | None,
    hand: Any | None,
    currency_code: str,
    amount_formatter: Callable[[Decimal | int | float], str],
    hand_icm: Any | None = None,
    hand_bounty: Any | None = None,
    actor_name: str = "Hero",
    hero_name: str = "Hero",
    shows_spr: bool = True,
    is_detailed: bool = False,
    guidance: str = "",
) -> DecisionPanelModel:
    """Construct a clean, structured DecisionPanelModel context-aware for Cash, MTT, ICM, and Bounty."""
    gametype = getattr(hand, "gametype", {}) or {}
    game_type = gametype.get("type", "ring")
    is_tourney = game_type == "tour"
    is_ko = bool(gametype.get("knockout") or getattr(hand, "bounties", None) or (hand_bounty and hand_bounty.allin))

    sections: list[DecisionPanelSection] = []
    facing_call = bool(metrics.get("facing_call"))
    is_allin = bool(metrics.get("is_allin") or any(p.allin for p in frame.players if getattr(p, "action", "") != "folds"))

    if facing_call:
        summary_rows, summary_notes = _build_facing_call_summary(
            metrics, decision, shows_spr, is_tourney, amount_formatter
        )
        sections.append(
            DecisionPanelSection(
                id="summary",
                title=_("DECISION SUMMARY"),
                rows=summary_rows,
                notes=summary_notes,
            )
        )
        pot_section = _build_pot_breakdown(metrics, amount_formatter)
        if pot_section is not None:
            sections.append(pot_section)
    elif decision and decision.mode == "bet":
        sections.append(_build_bet_summary(decision, shows_spr, amount_formatter))
    elif shows_spr and decision and decision.spr:
        spr_text = format_panel_spr(decision.spr)
        if spr_text:
            sections.append(
                DecisionPanelSection(
                    id="summary",
                    title=_("DECISION SUMMARY"),
                    rows=(
                        DecisionMetricRow(
                            key="spr",
                            label=_("%s SPR") % actor_name,
                            value=spr_text,
                            tooltip=EDUCATIONAL_TOOLTIPS["spr"],
                        ),
                    ),
                )
            )

    if is_tourney:
        icm_section = _build_icm_section(hand_icm, actor_name, currency_code, is_allin, is_detailed)
        if icm_section is not None:
            sections.append(icm_section)

    if is_tourney and (is_ko or (hand_bounty and getattr(hand_bounty, "allin", None))):
        bounty_section = _build_bounty_section(hand_bounty, actor_name, currency_code, is_allin, is_detailed)
        if bounty_section is not None:
            sections.append(bounty_section)

    return DecisionPanelModel(
        header=header,
        game_type="tour" if is_tourney else "cash",
        is_tourney=is_tourney,
        is_ko=is_ko,
        actor_name=actor_name,
        sections=tuple(sections),
        is_detailed=is_detailed,
        guidance=guidance or _("Use arrows/space to review decisions"),
    )
