"""The replayer's decision panel: sections of labelled rows for cash, MTT, ICM and bounty (#872)."""

from __future__ import annotations

import copy
from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

from fpdb_3_legacy.GuiReplayer import GuiReplayer, ReplayPlayer, TableState
from fpdb_3_legacy.hand_bounty import AllInBounty, HandBounty
from fpdb_3_legacy.hand_icm import AllInIcm, HandIcm
from fpdb_3_legacy.replayer_panel import (
    CallFigures,
    DecisionPanel,
    PanelRow,
    PanelSection,
    actor_section,
    bounty_section,
    icm_section,
    tip,
)

D = Decimal

ICM = HandIcm(
    AllInIcm(
        street="PREFLOP",
        players=("Hero", "Villain"),
        equity={"Hero": 0.46, "Villain": 0.54},
        chip_ev={"Hero": D("-148"), "Villain": D("348")},
        icm_ev={"Hero": -1.29, "Villain": -2.05},
        icm_result={"Hero": -10.52, "Villain": 9.68},
    )
)

PKO = AllInBounty(
    players=("Hero", "Villain"),
    win={"Hero": 0.46, "Villain": 0.54},
    collects={"Hero": D("7.50"), "Villain": D(0)},
    cash={"Hero": D("3.75"), "Villain": D(0)},
    bounty_ev={"Hero": D("1.725"), "Villain": D(0)},
    head_ev={"Hero": D("1.725"), "Villain": D(0)},
    chip_ev={"Hero": D("-148"), "Villain": D("348")},
    currency="USD",
)


def rows(section: PanelSection | None, *, detailed: bool = False) -> dict[str, str]:
    assert section is not None
    shown = section.visible(detailed)
    assert shown is not None
    return {row.label: row.value for row in shown.rows}


def notes(section: PanelSection | None, *, detailed: bool = True) -> list[str]:
    assert section is not None
    return [row.label for row in section.rows if row.is_note and (detailed or not row.detail)]


def money(value: Any) -> str:
    return f"${value}"


# --- the call ---------------------------------------------------------------


def test_one_hand_equity_and_its_difference_are_shown_once() -> None:
    call = CallFigures(
        call_amount=D("29.65"),
        pot_odds_pct=D("29.65") / D("135.05") * 100,
        pot_before_call=D("150.75"),
        final_pot=D("135.05"),
        equity_pct=D("52.1"),
        equity_exhaustive=True,
    )

    compact = rows(actor_section("Hero", amount=money, call=call, spr="1.27"))

    assert compact == {
        "Call amount": "$29.65",
        "Effective pot after call": "$135.05",
        "Required equity": "22.0%",
        "Estimated hand equity": "52.1%",
        "Equity difference": "+30.1 pts",
        "SPR": "1.27",
    }
    assert not any("Call Eq" in label or "Push" in label for label in compact)


def test_the_equity_basis_says_how_it_was_computed() -> None:
    def basis(exhaustive: bool | None) -> list[str]:
        call = CallFigures(call_amount=D(1), pot_odds_pct=D(25), equity_pct=D(50), equity_exhaustive=exhaustive)
        return notes(actor_section("Hero", amount=money, call=call))

    assert any("enumerated" in note for note in basis(True))
    assert any("simulated" in note for note in basis(False))
    # Only in the detailed view.
    call = CallFigures(call_amount=D(1), pot_odds_pct=D(25), equity_pct=D(50))
    assert not notes(actor_section("Hero", amount=money, call=call), detailed=False)


def test_a_tournament_call_is_chip_equity_never_an_icm_threshold() -> None:
    call = CallFigures(call_amount=D(40), pot_odds_pct=D(25), final_pot=D(160), pot_before_call=D(120))
    section = actor_section("Hero", amount=money, call=call, tournament=True)

    assert "Required chip equity" in rows(section)
    assert "Required equity" not in rows(section)
    assert "Chip pot odds: not an ICM threshold." in notes(section)
    assert "not an ICM calling threshold" in tip("required_chips")


def test_a_hero_to_act_without_a_call_shows_equity_and_spr_only() -> None:
    section = actor_section("Hero", amount=money, equity_pct=D(60), spr="3.5")

    assert section is not None and section.title == "Hero to act"
    assert rows(section) == {"Estimated hand equity": "60.0%", "SPR": "3.5"}
    assert actor_section("Hero", amount=money) is None


def test_every_figure_is_explained_and_mdf_states_its_model() -> None:
    call = CallFigures(
        call_amount=D(9),
        pot_odds_pct=D(45),
        pot_before_call=D(52),
        final_pot=D(20),
        facing_pct=D(2500),
        equity_pct=D(30),
    )
    section = actor_section("Hero", amount=money, call=call, spr="4.5")
    assert section is not None
    for row in section.rows:
        assert row.is_note or row.tooltip, row.label
    assert "heads-up" in tip("mdf") and "not a solver prescription" in tip("mdf")
    assert "not a solver prescription" in tip("fold_equity")
    assert "not a fold, call or raise recommendation" in tip("difference")


# --- PokerStars PLO5 hand 262648475894: a short all-in against a larger raise ---


def _plo5_states() -> list[Any]:
    hand = SimpleNamespace(
        board={},
        maxseats=6,
        gametype={"category": "5_omahahi", "base": "hold", "type": "ring"},
        actionStreets=["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"],
        players=[[1, "Player1", "84.27"], [2, "Player2", "115.99"], [5, "Hero", "66.65"]],
        join_holecards=lambda *_args, **_kwargs: [],
    )
    streets = [
        (
            "PREFLOP",
            [
                ("Player1", "small blind", D("0.25")),
                ("Player2", "big blind", D("0.50")),
                ("Hero", "raises", D("1.25")),
                ("Player1", "calls", D("1.50")),
                ("Player2", "raises", D("3.75")),
                ("Hero", "raises", D("12.75")),
                ("Player1", "folds"),
                ("Player2", "calls", D("12.75")),
            ],
        ),
        (
            "FLOP",
            [
                ("Player2", "checks"),
                ("Hero", "bets", D("18.75")),
                ("Player2", "raises", D(75)),
                ("Hero", "calls", D("29.65")),
            ],
        ),
    ]
    state = TableState(hand)
    states = []
    for street, actions in streets:
        state = copy.deepcopy(state)
        state.startPhase(street)
        states.append(state)
        for action in actions:
            state = copy.deepcopy(state)
            state.updateForAction(action)
            states.append(state)
    return states


def _replayer(states: list[Any], *, gametype: dict[str, str] | None = None) -> Any:
    replayer = cast(Any, GuiReplayer).__new__(GuiReplayer)  # pylint: disable=no-value-for-parameter
    replayer.Heroes = "Hero"
    replayer.currency_code = "USD"
    replayer.states = states
    hand = SimpleNamespace(
        gametype=gametype or {"category": "5_omahahi", "base": "hold", "type": "ring"},
        actionStreets=["BLINDSANTES", "PREFLOP", "FLOP", "TURN", "RIVER"],
    )
    replayer.replay_model = SimpleNamespace(hand=hand)
    replayer.all_decisions = SimpleNamespace(isChecked=lambda: False)
    replayer.hand_icm = replayer.hand_bounty = None
    return replayer


def _frame(state: Any) -> Any:
    return cast(
        Any,
        SimpleNamespace(
            players=[
                ReplayPlayer(p.name, p.seat, p.stack, p.chips, p.action, p.justacted, [], p.allin)
                for p in state.players.values()
            ],
            pot=state.newpot,
            board={},
            render_board=set(),
            street=state.street,
        ),
    )


def test_plo5_short_all_in_call_explains_the_effective_pot() -> None:
    states = _plo5_states()
    replayer = _replayer(states)
    raise_index = len(states) - 2  # Player2's raise to $93.75, before the hero's call

    panel = replayer._decision_panel(_frame(states[raise_index]), raise_index)
    section = panel.visible(True)[0]

    assert section.title == "Hero to call"
    detail = rows(section, detailed=True)
    assert detail["Call amount"] == "$29.65"
    assert detail["Effective pot after call"] == "$135.05"
    assert detail["Required equity"] == "22.0%"
    assert detail["Pot on the table"] == "$150.75"
    assert detail["Uncalled or side money"] == "$45.35"
    assert detail["Effective pot before call"] == "$105.40"
    assert detail["Pot odds"] == "3.6:1"
    # The compact view keeps the call and its price, not the breakdown.
    assert set(rows(section)) == {"Call amount", "Effective pot after call", "Required equity", "SPR"}


# --- ICM ----------------------------------------------------------------------


def test_icm_section_keeps_chip_ev_icm_ev_and_result_apart() -> None:
    section = icm_section(ICM, "Hero")

    assert section is not None and section.title == "Tournament — ICM"
    assert rows(section) == {
        "Chip EV": "-148 chips",
        "ICM $EV": "-1.29",
        "ICM result": "-10.52",
        "Model status": "Available",
    }
    assert rows(section, detailed=True)["Equity at the all-in"] == "46.0%"
    # Neutral: no row is flagged as a gain or a loss to act on.
    assert all(not row.muted for row in section.rows if not row.is_note)


def test_icm_priced_from_this_table_only_says_so_in_the_compact_view() -> None:
    table_only = HandIcm(replace(ICM.allin, table_only=True))

    assert any("whole field" in note for note in notes(icm_section(table_only, "Hero"), detailed=False))


def test_icm_that_cannot_be_priced_says_why_and_a_cash_hand_says_nothing() -> None:
    reason = "no payout structure known: import the summary, enter one or apply a preset"
    section = icm_section(HandIcm(None, reason), "Hero")

    assert rows(section)["Model status"] == "Unavailable"
    assert reason in notes(section, detailed=False)
    assert icm_section(HandIcm(None, "not a tournament hand"), "Hero") is None
    assert icm_section(None, "Hero") is None
    # A player outside the priced all-in has nothing to read.
    assert icm_section(ICM, "Short") is None


# --- bounty -------------------------------------------------------------------


def test_bounty_section_shows_its_cash_ev_own_bounty_and_status() -> None:
    section = bounty_section(HandBounty(PKO), "Hero")

    shown = rows(section)
    assert section is not None and section.title == "Knockout bounty"
    assert shown["Bounty EV"].startswith("+") and "1.7" in shown["Bounty EV"]
    assert "Added to own bounty" in shown
    assert "Bounty-adjusted chip EV" not in shown
    assert shown["Model status"] == "Available"
    assert "Not added to ICM $EV: this is not a complete PKO model." in notes(section)


def test_a_known_chip_value_adds_the_bounty_adjusted_chip_ev() -> None:
    adjusted = replace(PKO, adjusted_chip_ev={"Hero": D("3772"), "Villain": D("348")})

    assert rows(bounty_section(HandBounty(adjusted), "Hero"))["Bounty-adjusted chip EV"].startswith("+3")


def test_an_all_in_that_busts_nobody_says_so() -> None:
    section = bounty_section(HandBounty(PKO), "Villain")

    assert any("does not bust" in note for note in notes(section, detailed=False))


def test_a_freezeout_says_nothing_and_an_unpriced_knockout_says_why() -> None:
    hidden = "the bounty in play is not in the hand history"

    assert bounty_section(HandBounty(None, "not a knockout tournament"), "Hero") is None
    assert bounty_section(None, "Hero") is None
    section = bounty_section(HandBounty(None, hidden), "Hero")
    assert rows(section)["Model status"] == "Unavailable"
    assert hidden in notes(section, detailed=False)


# --- the panel ---------------------------------------------------------------


def _all_in_frame(*players: tuple[str, bool, str]) -> Any:
    return cast(
        Any,
        SimpleNamespace(
            players=[
                ReplayPlayer(name, seat, D(0), D(10), action, True, [], allin)
                for seat, (name, allin, action) in enumerate(players, start=1)
            ],
            pot=D(20),
            board={},
            render_board=set(),
            street="PREFLOP",
        ),
    )


def test_icm_and_bounty_have_their_own_sections_once_the_hero_is_all_in() -> None:
    replayer = _replayer([], gametype={"category": "holdem", "base": "hold", "type": "tour"})
    replayer.hand_icm, replayer.hand_bounty = ICM, HandBounty(PKO)
    all_in = _all_in_frame(("Hero", True, "raises"), ("Villain", True, "calls"), ("Short", False, "folds"))

    panel = replayer._decision_panel(all_in, 0)

    assert [section.title for section in panel.sections] == ["Tournament — ICM", "Knockout bounty"]
    assert not panel.hint


def test_nothing_is_priced_before_the_all_in_or_for_a_folded_hero() -> None:
    replayer = _replayer([], gametype={"category": "holdem", "base": "hold", "type": "tour"})
    replayer.hand_icm, replayer.hand_bounty = ICM, HandBounty(PKO)
    before = _all_in_frame(("Hero", False, "raises"), ("Villain", False, "calls"))
    folded = _all_in_frame(("Hero", False, "folds"), ("Villain", True, "raises"), ("Short", True, "calls"))

    for frame in (before, folded):
        panel = replayer._decision_panel(frame, 0)
        assert not panel.sections
        assert panel.hint


def test_panel_visibility_drops_sections_left_empty_in_the_compact_view() -> None:
    detail_only = PanelSection("Detail", (PanelRow("Only in detail", "1", detail=True),))
    panel = DecisionPanel("Hero bets", (detail_only,))

    assert not panel.visible(False)
    assert [section.title for section in panel.visible(True)] == ["Detail"]
