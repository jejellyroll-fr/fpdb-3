"""Tests for the improved Replayer decision analysis panel (#872).

Verifies:
- Context-aware sections: Cash Game, MTT, ICM, and Knockout (KO/PKO)
- Common decision summary layout with aligned labels and values
- Elimination of misleading equity duplication (single "Estimated hand equity")
- Short-stack all-in effective-pot arithmetic (e.g. PLO5 hand scenario)
- Multiway / side-pot handling
- MTT chip EV vs ICM prize equity separation
- Explicit reasons for unavailable or table-only ICM and bounty states
- Progressive disclosure (compact vs detailed modes)
- Educational tooltips and neutral informational styling (no green/red action guidance)
- PySide6 replayer overlay drawing and resize tolerance
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter

from fpdb_3_legacy.GuiReplayer import GuiReplayer, ReplayFrame, ReplayLayout, ReplayPlayer
from fpdb_3_legacy.hand_bounty import AllInBounty, HandBounty
from fpdb_3_legacy.hand_icm import AllInIcm, HandIcm
from fpdb_3_legacy.replayer_decision import HeroDecision
from fpdb_3_legacy.replayer_decision_panel import (
    EDUCATIONAL_TOOLTIPS,
    build_decision_panel_model,
)

D = Decimal


def _make_replayer(*, hand: Any = None, states: list[Any] | None = None, hero: str = "Hero", currency: str = "USD") -> GuiReplayer:
    replayer = cast(Any, GuiReplayer).__new__(GuiReplayer)
    replayer.Heroes = hero
    replayer.currency_code = currency
    replayer.replay_blind = None
    replayer.replay_model = SimpleNamespace(hand=hand or SimpleNamespace(gametype={"category": "holdem", "type": "ring"}))
    replayer.states = states or []
    replayer.all_decisions = SimpleNamespace(isChecked=lambda: False)
    replayer.detailed_analysis = SimpleNamespace(isChecked=lambda: False)
    replayer.hand_icm = None
    replayer.hand_bounty = None
    replayer._summary_hit_targets = []
    replayer._toggle_rect = QRectF()
    replayer._summary_rect = QRectF()
    return replayer


def _make_frame(*players, pot: Decimal = Decimal(100), street: str = "FLOP") -> ReplayFrame:
    p_objs = [
        ReplayPlayer(name=n, seat=i + 1, stack=D(s), chips=D(c), action=act, justacted=False, holecards=cards, allin=allin)
        for i, (n, c, s, act, allin, cards) in enumerate(players)
    ]
    frame = SimpleNamespace(
        players=p_objs,
        pot=pot,
        street=street,
        board={street: ["2c", "3d", "4h"]},
        render_board={street},
    )
    return cast(ReplayFrame, frame)


def test_educational_tooltips_coverage():
    """All required concepts have clear, translatable educational explanations."""
    for key in (
        "pot_odds",
        "spr",
        "mdf",
        "fold_equity",
        "chip_ev",
        "icm_ev",
        "icm_result",
        "bubble_factor",
        "hand_equity",
        "equity_diff",
        "effective_pot",
        "bounty_ev",
        "bounty_chip_ev",
        "model_status",
    ):
        assert key in EDUCATIONAL_TOOLTIPS
        text = EDUCATIONAL_TOOLTIPS[key]
        assert len(text) > 20
        # MDF & fold equity explicitly state they apply to simplified heads-up model
        if key in {"mdf", "fold_equity"}:
            assert "heads-up" in text.lower() or "zero-equity" in text.lower()


def test_heads_up_cash_call_compact_and_detailed():
    """Cash game call shows aligned key-value pairs without ICM or bounty sections."""
    replayer = _make_replayer()
    frame = _make_frame(
        ("Hero", 0, 50, "calls", False, ["As", "Kd"]),
        ("Villain", 25, 75, "bets", False, ["Qh", "Qc"]),
        pot=Decimal(50),
    )
    decision = HeroDecision(
        street="FLOP",
        mode="call",
        action="",
        call_amount=Decimal(25),
        pot_odds_pct=Decimal("33.3"),
        street_pot=Decimal(50),
        effective=(("Villain", Decimal(75)),),
        effective_pot=Decimal(75),
        pot_before_call=Decimal(50),
        uncalled_excess=Decimal(0),
    )
    metrics = {
        "facing_call": True,
        "call_amount": Decimal(25),
        "pot_odds_pct": Decimal("33.3"),
        "pot_odds_ratio": Decimal("2.0"),
        "effective_pot": Decimal(75),
        "pot_before_call": Decimal(50),
        "uncalled_excess": Decimal(0),
        "hand_equity_pct": Decimal("45.0"),
        "equity_diff_pts": Decimal("11.7"),
    }

    # Compact mode
    model_compact = build_decision_panel_model(
        header="Villain bets $25.00",
        frame=frame,
        metrics=metrics,
        decision=decision,
        hand=replayer.replay_model.hand,
        currency_code="USD",
        amount_formatter=replayer._amount,
        actor_name="Hero",
        hero_name="Hero",
        shows_spr=True,
        is_detailed=False,
    )

    sec_ids = [s.id for s in model_compact.visible_sections(detailed=False)]
    assert sec_ids == ["summary"]  # Only summary in compact cash
    summary_rows = {r.key: r.value for r in model_compact.visible_sections(detailed=False)[0].rows}
    assert summary_rows["call_amount"] == "$25.00"
    assert summary_rows["effective_pot"] == "$75.00"
    assert summary_rows["required_equity"] == "33.3%"
    assert summary_rows["hand_equity"] == "45.0%"
    assert summary_rows["equity_diff"] == "+11.7 pts"
    assert summary_rows["spr"] == "1.5"

    # Detailed mode reveals pot breakdown and ratio
    model_detailed = build_decision_panel_model(
        header="Villain bets $25.00",
        frame=frame,
        metrics=metrics,
        decision=decision,
        hand=replayer.replay_model.hand,
        currency_code="USD",
        amount_formatter=replayer._amount,
        actor_name="Hero",
        hero_name="Hero",
        shows_spr=True,
        is_detailed=True,
    )
    det_sec_ids = [s.id for s in model_detailed.visible_sections(detailed=True)]
    assert "summary" in det_sec_ids
    assert "pot_breakdown" in det_sec_ids
    # Neither ICM nor Bounty appear for Cash Game
    assert "icm" not in det_sec_ids
    assert "bounty" not in det_sec_ids


def test_effective_pot_arithmetic_plo5_hand_scenario():
    """Short-stack all-in with unmatched raise (PokerStars PLO5 scenario).

    Displayed pot before call: $150.75
    Hero's additional call:    $29.65
    Effective final pot:      $135.05
    Required chip equity:      22.0%
    Uncalled excess:           $45.35
    Effective pot before call: $105.40
    """
    replayer = _make_replayer()
    frame = _make_frame(
        ("Hero", 0, Decimal("29.65"), "calls", True, ["As", "Kd", "Qc", "Jh", "Ts"]),
        ("Villain", Decimal("93.75"), Decimal("100"), "raises", False, ["Ah", "Kh", "Qh", "Jh", "9h"]),
        pot=Decimal("150.75"),
    )
    decision = HeroDecision(
        street="FLOP",
        mode="call",
        action="",
        call_amount=Decimal("29.65"),
        pot_odds_pct=Decimal("22.0"),
        street_pot=Decimal("57.00"),
        effective=(("Villain", Decimal("29.65")),),
        effective_pot=Decimal("135.05"),
        pot_before_call=Decimal("150.75"),
        uncalled_excess=Decimal("45.35"),
    )
    metrics = {
        "facing_call": True,
        "call_amount": Decimal("29.65"),
        "pot_odds_pct": Decimal("22.0"),
        "pot_odds_ratio": Decimal("3.55"),
        "effective_pot": Decimal("135.05"),
        "pot_before_call": Decimal("150.75"),
        "uncalled_excess": Decimal("45.35"),
        "hand_equity_pct": Decimal("52.1"),
        "equity_diff_pts": Decimal("30.1"),
    }

    model = build_decision_panel_model(
        header="Villain raises to $93.75",
        frame=frame,
        metrics=metrics,
        decision=decision,
        hand=replayer.replay_model.hand,
        currency_code="USD",
        amount_formatter=replayer._amount,
        actor_name="Hero",
        hero_name="Hero",
        shows_spr=True,
        is_detailed=True,
    )

    pot_section = next(s for s in model.visible_sections(detailed=True) if s.id == "pot_breakdown")
    rows = {r.key: r.value for r in pot_section.rows}
    assert rows["displayed_pot_before"] == "$150.75"
    assert rows["hero_additional_call"] == "$29.65"
    assert rows["uncalled_excess"] == "$45.35"
    assert rows["effective_pot_before"] == "$105.40"
    assert rows["effective_final_pot"] == "$135.05"


def test_elimination_of_misleading_equity_duplication():
    """In _hero_decision_metrics and panel, equity is presented once as 'Estimated hand equity'."""
    replayer = _make_replayer()
    frame = _make_frame(
        ("Hero", 0, 50, "calls", False, ["As", "Ah"]),
        ("Villain", 10, 50, "bets", False, ["Ks", "Kh"]),
        pot=Decimal(40),
    )
    # Mock calculate_equity
    replayer._equity_cache = {}
    metrics = {
        "facing_call": True,
        "call_amount": Decimal(10),
        "pot_odds_pct": Decimal(20),
        "effective_pot": Decimal(50),
        "hand_equity_pct": Decimal(80),
        "equity_diff_pts": Decimal(60),
        # Legacy duplicate fields should still match hand_equity_pct
        "call_equity_pct": Decimal(80),
        "push_equity_pct": Decimal(80),
        "call_edge_pts": Decimal(60),
    }

    model = build_decision_panel_model(
        header="Villain bets $10.00",
        frame=frame,
        metrics=metrics,
        decision=None,
        hand=replayer.replay_model.hand,
        currency_code="USD",
        amount_formatter=replayer._amount,
        actor_name="Hero",
        hero_name="Hero",
        is_detailed=False,
    )

    summary = model.visible_sections(detailed=False)[0]
    labels = [r.label for r in summary.rows]
    assert "Estimated hand equity" in labels
    # "Call Eq" and "Push Eq" are not duplicated
    assert "Call Eq" not in labels
    assert "Push Eq" not in labels


def test_mtt_with_valid_heads_up_icm():
    """MTT displays separate chip equity and ICM prize equity without confusing them."""
    hand = SimpleNamespace(gametype={"category": "holdem", "type": "tour", "base": "hold"})
    replayer = _make_replayer(hand=hand)

    frame = _make_frame(
        ("Hero", 0, 1000, "calls", True, ["As", "Ks"]),
        ("Villain", 1000, 2000, "raises", True, ["Qh", "Qc"]),
        pot=Decimal(2000),
    )
    allin_icm = AllInIcm(
        street="PREFLOP",
        players=("Hero", "Villain"),
        equity={"Hero": 0.46, "Villain": 0.54},
        chip_ev={"Hero": Decimal("-148"), "Villain": Decimal("348")},
        icm_ev={"Hero": -1.29, "Villain": -2.05},
        icm_result={"Hero": -10.52, "Villain": 9.68},
        table_only=False,
    )
    replayer.hand_icm = HandIcm(allin_icm)

    metrics = {
        "facing_call": True,
        "call_amount": Decimal(1000),
        "pot_odds_pct": Decimal("50.0"),
        "effective_pot": Decimal(2000),
        "hand_equity_pct": Decimal("46.0"),
        "equity_diff_pts": Decimal("-4.0"),
        "is_allin": True,
    }

    model = build_decision_panel_model(
        header="Villain raises all-in",
        frame=frame,
        metrics=metrics,
        decision=None,
        hand=hand,
        currency_code="USD",
        amount_formatter=replayer._amount,
        hand_icm=replayer.hand_icm,
        actor_name="Hero",
        hero_name="Hero",
        is_detailed=False,
    )

    sections = {s.id: s for s in model.visible_sections(detailed=False)}
    assert "summary" in sections
    assert "icm" in sections

    summary_rows = {r.key: r for r in sections["summary"].rows}
    assert summary_rows["required_equity"].label == "Required chip equity"  # explicitly labeled as chip equity

    icm_rows = {r.key: r.value for r in sections["icm"].rows}
    assert icm_rows["chip_ev"] == "-148 chips"
    assert icm_rows["icm_ev"] == "-$1.29"
    assert icm_rows["icm_result"] == "-$10.52"
    assert icm_rows["icm_status"] == "Available"


def test_mtt_icm_table_only_and_unavailable_states():
    """Missing payouts, field larger than table, and table-only field are explicitly reported."""
    hand = SimpleNamespace(gametype={"category": "holdem", "type": "tour", "base": "hold"})
    replayer = _make_replayer(hand=hand)
    frame = _make_frame(("Hero", 0, 1000, "calls", True, ["As", "Ks"]), pot=Decimal(2000))

    # Case 1: Table-only field assumption
    allin_table_only = AllInIcm(
        street="PREFLOP",
        players=("Hero", "Villain"),
        equity={"Hero": 0.46, "Villain": 0.54},
        chip_ev={"Hero": Decimal("-148"), "Villain": Decimal("348")},
        icm_ev={"Hero": -1.29, "Villain": -2.05},
        icm_result={"Hero": -10.52, "Villain": 9.68},
        table_only=True,
    )
    model1 = build_decision_panel_model(
        header="All-in",
        frame=frame,
        metrics={"is_allin": True},
        decision=None,
        hand=hand,
        currency_code="USD",
        amount_formatter=replayer._amount,
        hand_icm=HandIcm(allin_table_only),
        actor_name="Hero",
        hero_name="Hero",
    )
    icm_sec1 = next(s for s in model1.visible_sections() if s.id == "icm")
    assert "table-only" in next(r.value for r in icm_sec1.rows if r.key == "icm_status")

    # Case 2: Missing payouts
    model2 = build_decision_panel_model(
        header="All-in",
        frame=frame,
        metrics={"is_allin": True},
        decision=None,
        hand=hand,
        currency_code="USD",
        amount_formatter=replayer._amount,
        hand_icm=HandIcm(None, reason="no payout structure known for this tournament"),
        actor_name="Hero",
        hero_name="Hero",
    )
    icm_sec2 = next(s for s in model2.visible_sections() if s.id == "icm")
    status_row = next(r for r in icm_sec2.rows if r.key == "icm_status")
    assert "Unavailable" in status_row.value
    assert "no payout structure known" in status_row.value


def test_knockout_bounty_ev_and_covering_status():
    """Knockout all-in shows bounty EV and adjusted chip EV, and reports non-busts accurately."""
    hand = SimpleNamespace(gametype={"category": "holdem", "type": "tour", "knockout": True, "base": "hold"})
    replayer = _make_replayer(hand=hand)
    frame = _make_frame(
        ("Hero", 0, 1500, "calls", True, ["As", "Kd"]),
        ("Villain", 1000, 1000, "raises", True, ["Qh", "Qc"]),
        pot=Decimal(2000),
    )

    pko = AllInBounty(
        players=("Hero", "Villain"),
        win={"Hero": 0.46, "Villain": 0.54},
        collects={"Hero": Decimal("7.50"), "Villain": Decimal(0)},
        cash={"Hero": Decimal("3.75"), "Villain": Decimal(0)},
        bounty_ev={"Hero": Decimal("1.725"), "Villain": Decimal(0)},
        head_ev={"Hero": Decimal("1.725"), "Villain": Decimal(0)},
        chip_ev={"Hero": Decimal("-148"), "Villain": Decimal("348")},
        adjusted_chip_ev={"Hero": Decimal("3772"), "Villain": Decimal("348")},
        currency="USD",
    )

    model = build_decision_panel_model(
        header="Villain shoves",
        frame=frame,
        metrics={"is_allin": True},
        decision=None,
        hand=hand,
        currency_code="USD",
        amount_formatter=replayer._amount,
        hand_bounty=HandBounty(pko),
        actor_name="Hero",
        hero_name="Hero",
        is_detailed=True,
    )

    bounty_sec = next(s for s in model.visible_sections(detailed=True) if s.id == "bounty")
    rows = {r.key: r.value for r in bounty_sec.rows}
    assert rows["bounty_ev"] == "+$1.72" or rows["bounty_ev"] == "+$1.73"
    assert rows["bounty_chip_ev"] == "+3,772 chips"
    assert rows["bounty_status"] == "Available"

    # Villain's perspective: winning does not bust Hero
    model_villain = build_decision_panel_model(
        header="Villain shoves",
        frame=frame,
        metrics={"is_allin": True},
        decision=None,
        hand=hand,
        currency_code="USD",
        amount_formatter=replayer._amount,
        hand_bounty=HandBounty(pko),
        actor_name="Villain",
        hero_name="Hero",
        is_detailed=True,
    )
    bounty_sec_v = next(s for s in model_villain.visible_sections(detailed=True) if s.id == "bounty")
    rows_v = {r.key: r.value for r in bounty_sec_v.rows}
    assert rows_v["bounty_status"] == "Winning does not bust opponent"


def test_neutral_informational_styling():
    """Equity difference uses neutral informational styling, not red/green 'do this' advice."""
    replayer = _make_replayer()
    frame = _make_frame(("Hero", 0, 50, "calls", False, ["As", "Kd"]))
    metrics = {
        "facing_call": True,
        "call_amount": Decimal(10),
        "pot_odds_pct": Decimal(20),
        "hand_equity_pct": Decimal(15),
        "equity_diff_pts": Decimal(-5),  # Negative difference
    }
    model = build_decision_panel_model(
        header="Call",
        frame=frame,
        metrics=metrics,
        decision=None,
        hand=replayer.replay_model.hand,
        currency_code="USD",
        amount_formatter=replayer._amount,
        actor_name="Hero",
        hero_name="Hero",
    )
    summary = model.visible_sections()[0]
    row = next(r for r in summary.rows if r.key == "equity_diff")
    # Neutral color: no aggressive red ("#ff6b6b") or green ("#4ade80")
    assert row.neutral_color != "#ff6b6b"
    assert row.neutral_color != "#4ade80"


def test_replayer_draw_summary_paints_without_error(qtbot):
    """QPainter rendering tests narrow, wide, compact and detailed overlay drawing."""
    replayer = _make_replayer()
    frame = _make_frame(
        ("Hero", 0, 50, "calls", False, ["As", "Kd"]),
        ("Villain", 25, 75, "bets", False, ["Qh", "Qc"]),
        pot=Decimal(50),
    )
    replayer.states = [
        SimpleNamespace(street="FLOP", players={}),
        SimpleNamespace(street="FLOP", players={"Hero": SimpleNamespace(name="Hero", justacted=True, action="calls")}),
    ]

    layout_wide = ReplayLayout(
        table_rect=QRectF(0, 0, 1000, 700),
        board_rect=QRectF(300, 250, 400, 100),
        pot_rect=QRectF(400, 200, 200, 40),
        timeline_rect=QRectF(750, 40, 240, 600),
        card_width=60,
        card_height=84,
        card_spacing=10,
    )
    layout_narrow = ReplayLayout(
        table_rect=QRectF(0, 0, 600, 500),
        board_rect=QRectF(150, 180, 300, 80),
        pot_rect=QRectF(200, 140, 200, 30),
        timeline_rect=QRectF(),  # Null timeline on narrow screen
        card_width=45,
        card_height=63,
        card_spacing=8,
    )

    image = QImage(1024, 768, QImage.Format.Format_ARGB32)
    image.fill(QColor("#1a1a1a"))
    painter = QPainter(image)

    try:
        # Draw compact wide
        replayer.detailed_analysis.isChecked = lambda: False
        replayer._draw_summary(painter, frame, layout_wide, 0)
        assert len(replayer._summary_hit_targets) > 0
        assert not replayer._toggle_rect.isNull()

        # Draw detailed narrow
        replayer.detailed_analysis.isChecked = lambda: True
        replayer._draw_summary(painter, frame, layout_narrow, 0)
        assert len(replayer._summary_hit_targets) > 0
    finally:
        painter.end()


def test_multiway_and_side_pot_metrics_and_icm_refusal():
    """Multiway pots show SPR ranges, suppress heads-up MDF, and report ICM side-pot/multiway refusals."""
    hand = SimpleNamespace(gametype={"category": "holdem", "type": "tour", "base": "hold"})
    replayer = _make_replayer(hand=hand)
    frame = _make_frame(
        ("Hero", 0, 50, "calls", True, ["As", "Kd"]),
        ("Short", 10, 0, "bets", True, ["Qh", "Qc"]),
        ("Deep", 30, 70, "raises", False, ["Jh", "Jc"]),
        pot=Decimal(90),
    )

    decision_bet = HeroDecision(
        street="FLOP",
        mode="bet",
        action="bets",
        bet_amount=Decimal(30),
        bet_pct=Decimal(50),
        effective=(("Short", Decimal(10)), ("Deep", Decimal(70))),
        street_pot=Decimal(40),
    )

    # Multiway MDF: heads-up only note
    model_bet = build_decision_panel_model(
        header="Hero bets $30.00",
        frame=frame,
        metrics={},
        decision=decision_bet,
        hand=hand,
        currency_code="USD",
        amount_formatter=replayer._amount,
        actor_name="Hero",
        hero_name="Hero",
        is_detailed=True,
    )
    summary_sec = next(s for s in model_bet.visible_sections(detailed=True) if s.id == "bet_summary")
    rows = {r.key: r.value for r in summary_sec.rows}
    assert rows["mdf_multiway"] == "Heads-up only"
    assert rows["spr"] == "0.25–1.75"

    # Multiway ICM refusal
    multiway_refusal = HandIcm(None, reason="multiway all-in: ICM $EV is priced heads-up only")
    model_icm = build_decision_panel_model(
        header="All-in",
        frame=frame,
        metrics={"is_allin": True},
        decision=None,
        hand=hand,
        currency_code="USD",
        amount_formatter=replayer._amount,
        hand_icm=multiway_refusal,
        actor_name="Hero",
        hero_name="Hero",
    )
    icm_sec = next(s for s in model_icm.visible_sections() if s.id == "icm")
    assert "multiway all-in" in next(r.value for r in icm_sec.rows if r.key == "icm_status")

    # Side pot ICM refusal
    side_pot_refusal = HandIcm(None, reason="side pot: ICM $EV is priced for a single pot only")
    model_side_pot = build_decision_panel_model(
        header="All-in",
        frame=frame,
        metrics={"is_allin": True},
        decision=None,
        hand=hand,
        currency_code="USD",
        amount_formatter=replayer._amount,
        hand_icm=side_pot_refusal,
        actor_name="Hero",
        hero_name="Hero",
    )
    icm_sec_side = next(s for s in model_side_pot.visible_sections() if s.id == "icm")
    assert "side pot" in next(r.value for r in icm_sec_side.rows if r.key == "icm_status")


def test_odds_for_all_players_toggle():
    """Odds for all players prices the opponent's decision when active."""
    replayer = _make_replayer()
    replayer.Heroes = "Hero"
    replayer.all_decisions.isChecked = lambda: True

    # State where Villain is about to act facing a Hero bet
    state1 = SimpleNamespace(street="FLOP", players={})
    state2 = SimpleNamespace(
        street="FLOP",
        players={
            "Hero": SimpleNamespace(name="Hero", stack=Decimal(80), chips=Decimal(20), action="bets", justacted=True, folded=False),
            "Villain": SimpleNamespace(name="Villain", stack=Decimal(80), chips=Decimal(0), action="calls", justacted=False, folded=False),
        },
        ended=False,
    )
    state3 = SimpleNamespace(
        street="FLOP",
        players={
            "Hero": SimpleNamespace(name="Hero", stack=Decimal(80), chips=Decimal(20), action="bets", justacted=False, folded=False),
            "Villain": SimpleNamespace(name="Villain", stack=Decimal(60), chips=Decimal(20), action="calls", justacted=True, folded=False),
        },
        ended=False,
    )
    replayer.states = [state1, state2, state3]

    frame = _make_frame(
        ("Hero", 20, 80, "bets", False, ["As", "Kd"]),
        ("Villain", 0, 80, "checks", False, ["Qh", "Qc"]),
        pot=Decimal(40),
    )

    model = replayer._summary_model(frame, 1)
    assert model.actor_name == "Villain"
    summary_sec = model.visible_sections()[0]
    call_row = next((r for r in summary_sec.rows if r.key == "call_amount"), None)
    assert call_row is not None
    assert call_row.value == "$20.00"


def test_interactive_toggle_click_and_tooltip_hit_test():
    """Clicking the toggle button toggles detailed mode, and tooltip event hits targets."""
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QHelpEvent, QMouseEvent

    replayer = _make_replayer()
    checked_state = [False]
    replayer.detailed_analysis = SimpleNamespace(
        isChecked=lambda: checked_state[0],
        setChecked=lambda val: checked_state.__setitem__(0, val),
    )

    frame = _make_frame(
        ("Hero", 0, 50, "calls", False, ["As", "Kd"]),
        ("Villain", 25, 75, "bets", False, ["Qh", "Qc"]),
        pot=Decimal(50),
    )
    layout = ReplayLayout(
        table_rect=QRectF(0, 0, 1000, 700),
        board_rect=QRectF(300, 250, 400, 100),
        pot_rect=QRectF(400, 200, 200, 40),
        timeline_rect=QRectF(750, 40, 240, 600),
        card_width=60,
        card_height=84,
        card_spacing=10,
    )
    image = QImage(1024, 768, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    try:
        replayer._draw_summary(painter, frame, layout, 0)
    finally:
        painter.end()

    # Hit test toggle button
    toggle_pt = replayer._toggle_rect.center().toPoint()
    click_event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(toggle_pt),
        QPointF(toggle_pt),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    replayer.mousePressEvent(click_event)
    assert checked_state[0] is True  # Toggle was clicked and changed state

    # Tooltip hit test
    first_target_rect, first_tooltip = replayer._summary_hit_targets[0]
    help_pt = first_target_rect.center().toPoint()
    help_event = QHelpEvent(QEvent.Type.ToolTip, help_pt, help_pt)
    assert replayer.event(help_event) is True


def test_long_translated_strings_layout_resilience():
    """Elongated strings in German/French or long descriptions do not raise errors or disrupt layout."""
    replayer = _make_replayer()
    frame = _make_frame(
        ("Hero", 0, 50, "calls", False, ["As", "Kd"]),
        ("Villain", 25, 75, "bets", False, ["Qh", "Qc"]),
        pot=Decimal(50),
    )
    decision = HeroDecision(
        street="FLOP",
        mode="call",
        action="",
        call_amount=Decimal(25),
        pot_odds_pct=Decimal("33.3"),
        street_pot=Decimal(50),
        effective=(("Villain", Decimal(75)),),
        effective_pot=Decimal(75),
        pot_before_call=Decimal(50),
        uncalled_excess=Decimal(0),
    )
    metrics = {
        "facing_call": True,
        "call_amount": Decimal(25),
        "pot_odds_pct": Decimal("33.3"),
        "pot_odds_ratio": Decimal("2.0"),
        "effective_pot": Decimal(75),
        "pot_before_call": Decimal(50),
        "uncalled_excess": Decimal(0),
        "hand_equity_pct": Decimal("45.0"),
        "equity_diff_pts": Decimal("11.7"),
    }
    model = build_decision_panel_model(
        header="SehrLangerSpielerNameErhebtAuf1234567890EuroInEinemExtremGrossenTopf",
        frame=frame,
        metrics=metrics,
        decision=decision,
        hand=replayer.replay_model.hand,
        currency_code="EUR",
        amount_formatter=lambda v: f"{v} EuroSehrLangeWaehrungsBezeichnung",
        actor_name="SehrLangerSpielerName",
        hero_name="Hero",
        shows_spr=True,
        is_detailed=True,
    )
    lines = model.to_summary_lines(detailed=True)
    assert len(lines) > 5

    # Paint with narrow layout
    layout_narrow = ReplayLayout(
        table_rect=QRectF(0, 0, 480, 400),
        board_rect=QRectF(100, 150, 200, 60),
        pot_rect=QRectF(150, 100, 150, 30),
        timeline_rect=QRectF(),
        card_width=35,
        card_height=49,
        card_spacing=6,
    )
    image = QImage(480, 400, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    try:
        replayer.detailed_analysis.isChecked = lambda: True
        replayer._draw_summary(painter, frame, layout_narrow, 0)
    finally:
        painter.end()


def test_unsupported_equity_states_compact_and_detailed():
    """Unsupported equity states (missing cards, unsupported variant) display explicit reasons in detailed mode."""
    replayer = _make_replayer()
    frame = _make_frame(
        ("Hero", 0, 50, "calls", False, ["As", "Kd"]),
        ("Villain", 25, 75, "bets", False, None),  # Villain cards unknown/mucked
        pot=Decimal(50),
    )
    decision = HeroDecision(
        street="FLOP",
        mode="call",
        action="",
        call_amount=Decimal(25),
        pot_odds_pct=Decimal("33.3"),
        street_pot=Decimal(50),
        effective=(("Villain", Decimal(75)),),
        effective_pot=Decimal(75),
        pot_before_call=Decimal(50),
        uncalled_excess=Decimal(0),
    )

    # Case 1: Missing opponent cards
    metrics_missing_cards = {
        "facing_call": True,
        "call_amount": Decimal(25),
        "pot_odds_pct": Decimal("33.3"),
        "pot_odds_ratio": Decimal("2.0"),
        "effective_pot": Decimal(75),
        "pot_before_call": Decimal(50),
        "uncalled_excess": Decimal(0),
        "hand_equity_pct": None,
        "equity_diff_pts": None,
        "equity_reason": "missing cards",
    }

    # Compact mode: no hand equity row to avoid cluttering compact view
    model_compact = build_decision_panel_model(
        header="Villain bets $25.00",
        frame=frame,
        metrics=metrics_missing_cards,
        decision=decision,
        hand=replayer.replay_model.hand,
        currency_code="USD",
        amount_formatter=replayer._amount,
        is_detailed=False,
    )
    compact_rows = {r.key: r.value for r in model_compact.visible_sections(detailed=False)[0].rows}
    assert "hand_equity" not in compact_rows
    assert "equity_diff" not in compact_rows
    assert compact_rows["required_equity"] == "33.3%"

    # Detailed mode: displays explicit reason for unavailable equity
    model_detailed = build_decision_panel_model(
        header="Villain bets $25.00",
        frame=frame,
        metrics=metrics_missing_cards,
        decision=decision,
        hand=replayer.replay_model.hand,
        currency_code="USD",
        amount_formatter=replayer._amount,
        is_detailed=True,
    )
    det_sec = model_detailed.visible_sections(detailed=True)[0]
    det_rows = {r.key: r.value for r in det_sec.rows}
    assert "hand_equity" in det_rows
    assert "Unavailable: missing cards" in det_rows["hand_equity"]
    assert any("Hand equity unavailable: missing cards" in note for note in det_sec.notes)

    # Case 2: Unsupported variant
    metrics_unsupported = dict(metrics_missing_cards, equity_reason="unsupported variant")
    model_variant = build_decision_panel_model(
        header="Villain bets $25.00",
        frame=frame,
        metrics=metrics_unsupported,
        decision=decision,
        hand=replayer.replay_model.hand,
        currency_code="USD",
        amount_formatter=replayer._amount,
        is_detailed=True,
    )
    var_rows = {r.key: r.value for r in model_variant.visible_sections(detailed=True)[0].rows}
    assert "Unavailable: unsupported variant" in var_rows["hand_equity"]

