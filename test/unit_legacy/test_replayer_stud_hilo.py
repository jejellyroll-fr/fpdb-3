"""Regression tests for the Stud Hi/Lo showdown frame and its renderer."""

from decimal import Decimal
from types import MethodType, SimpleNamespace
from unittest.mock import Mock

import pytest

from fpdb_3_legacy import Card
from fpdb_3_legacy.GuiReplayer import GuiReplayer, ReplayPlayer, build_replay_layout, stud_hilo_winners


@pytest.fixture
def stud_replayer():
    players = [
        ReplayPlayer(
            "Hero", 1, Decimal(0), Decimal("23.30"), "collected", True, ["5s", "6d", "7d", "8s", "4s", "Kd", "5h"]
        ),
        ReplayPlayer(
            "Player5", 5, Decimal(0), Decimal("23.30"), "collected", True, ["2h", "Ac", "As", "7c", "Ks", "4c", "8h"]
        ),
    ]
    hand = SimpleNamespace(
        gametype={"base": "stud", "category": "studhilo"},
        collectees={p.name: p.chips for p in players},
        showdownStrings={},
        winningHand={},
    )
    state = SimpleNamespace(
        players={p.name: p for p in players},
        ended=True,
        street="SEVENTH",
        board={},
        renderBoard=set(),
        newpot=Decimal(0),
        computePots=lambda: [],
    )
    replayer = SimpleNamespace(
        replay_model=SimpleNamespace(hand=hand),
        states=[state],
        stateSlider=SimpleNamespace(value=lambda: 0),
        Heroes="Hero",
        showCards=SimpleNamespace(isChecked=lambda: True),
        currency_code="USD",
        height=lambda: 900,
        cardwidth=70,
        cardheight=100,
    )
    for method in ("_normalized_cards", "_frame_from_state", "_visible_cards", "_draw_cards"):
        setattr(replayer, method, MethodType(getattr(GuiReplayer, method), replayer))
    return replayer


@pytest.mark.parametrize("explicit_cards", [False, True])
def test_showdown_frame_uses_only_the_won_half(stud_replayer, explicit_cards):
    state = stud_replayer.states[0]
    if explicit_cards:
        stud_replayer.replay_model.hand.winningHand = {p.name: p.holecards for p in state.players.values()}

    hero, low_winner = stud_replayer._frame_from_state(state).players

    assert hero.hi_winner and not hero.lo_winner
    assert hero.winning_cards == {"5s", "6d", "7d", "8s", "4s"}
    assert low_winner.lo_winner and not low_winner.hi_winner
    assert low_winner.winning_cards == {"8h", "7c", "4c", "2h", "Ac"}
    assert len(low_winner.winning_cards) == 5
    assert low_winner.is_winner


def test_no_winning_highlights_before_showdown(stud_replayer):
    state = stud_replayer.states[0]
    state.ended = False
    for player in stud_replayer._frame_from_state(state).players:
        assert not player.winning_cards
        assert not player.hi_winner and not player.lo_winner


def test_stud_hilo_winners_are_evaluated_for_each_eligible_pot():
    short = ReplayPlayer("Short", 1, Decimal(0), Decimal(0), "calls", False,
                         ["Ks", "Kh", "Kc", "2d", "4h", "7s", "9c"])
    hero = ReplayPlayer("Hero", 2, Decimal(0), Decimal(0), "calls", False,
                        ["As", "Ah", "Qc", "Jd", "9h", "7c", "4s"])
    deep = ReplayPlayer("Deep", 3, Decimal(0), Decimal(0), "calls", False,
                        ["5s", "6d", "7h", "8c", "4d", "2s", "3c"])

    high, low, cards = stud_hilo_winners(
        [short, hero, deep],
        [(Decimal("10"), {"Short", "Hero"}), (Decimal("10"), {"Hero", "Deep"})],
    )

    assert high == {"Short", "Deep"}
    assert low == {"Deep"}
    assert cards["Short"] == {"Ks", "Kh", "Kc", "9c", "7s"}
    assert cards["Deep"] == {"5s", "6d", "7h", "8c", "4d", "2s", "3c"}


def test_stud_hilo_skips_uncontested_singleton_pots():
    survivor = ReplayPlayer(
        "Survivor", 1, Decimal(0), Decimal(0), "collected", True,
        ["As", "Ah", "Ad", "2c", "3d", "4h", "6s"],
    )

    high, low, cards = stud_hilo_winners(
        [survivor],
        [(Decimal("10"), {"Survivor"})],
    )

    assert high == set()
    assert low == set()
    assert cards == {}


@pytest.mark.parametrize(
    ("hero_cards", "opponent_cards", "low_winners", "hero_highlights"),
    [
        # A scoop can legitimately use all seven cards across its two halves.
        (
            ["As", "Ah", "Ad", "2c", "3d", "4h", "6s"],
            ["Ks", "Kh", "Qc", "Jc", "9c", "8d", "7d"],
            {"Hero"},
            {"As", "Ah", "Ad", "2c", "3d", "4h", "6s"},
        ),
        # A tied low belongs to both players, with only one Ace per low hand.
        (
            ["As", "Ah", "Ad", "2c", "3d", "4h", "6s"],
            ["Ac", "2d", "3c", "4d", "6h", "Kd", "Qh"],
            {"Hero", "Player5"},
            {"As", "Ah", "Ad", "2c", "3d", "4h", "6s"},
        ),
        # Without a qualifying low, the high hand takes the whole pot.
        (
            ["As", "Ah", "Ad", "Tc", "9d", "4h", "6s"],
            ["Ks", "Kh", "Qc", "Jc", "9c", "8d", "7d"],
            set(),
            {"As", "Ah", "Ad", "Tc", "9d"},
        ),
    ],
)
def test_frame_handles_scoops_ties_and_no_low(
    stud_replayer,
    hero_cards,
    opponent_cards,
    low_winners,
    hero_highlights,
):
    state = stud_replayer.states[0]
    state.players["Hero"].holecards = hero_cards
    state.players["Player5"].holecards = opponent_cards
    stud_replayer.replay_model.hand.collectees = {name: Decimal("23.30") for name in {"Hero"} | low_winners}

    players = stud_replayer._frame_from_state(state).players

    assert {p.name for p in players if p.hi_winner} == {"Hero"}
    assert {p.name for p in players if p.lo_winner} == low_winners
    assert players[0].winning_cards == hero_highlights
    assert players[1].winning_cards == ({"Ac", "2d", "3c", "4d", "6h"} if "Player5" in low_winners else set())


@pytest.mark.qt
def test_low_winner_render_highlights_five_cards_and_dims_other_two(stud_replayer, qapp):
    player = stud_replayer._frame_from_state(stud_replayer.states[0]).players[1]
    layout = build_replay_layout(1600, 900, ["Hero", "Player5"], hero_name="Hero")
    # Use card tokens as pixmap sentinels to inspect the actual drawing calls.
    stud_replayer.cardImages = {Card.encodeCard(card): card for card in player.holecards}
    cards_painter = Mock()
    draw_cards = stud_replayer._draw_cards
    stud_replayer._draw_cards = Mock(
        side_effect=lambda _painter, *args, **kwargs: draw_cards(cards_painter, *args, **kwargs)
    )
    painter = Mock()

    GuiReplayer._draw_player(
        stud_replayer,
        painter,
        player,
        layout.seats[player.name],
        layout,
        "SEVENTH",
        True,
    )

    kwargs = stud_replayer._draw_cards.call_args.kwargs
    assert kwargs["highlight"] == {"8h", "7c", "4c", "2h", "Ac"}
    assert kwargs["dim_others"] is True
    assert cards_painter.drawRoundedRect.call_count == 5
    dimmed = []
    faded = False
    for call in cards_painter.method_calls:
        if call[0] == "setOpacity":
            faded = call.args[0] < 1
        elif call[0] == "restore":
            faded = False
        elif call[0] == "drawPixmap" and faded:
            dimmed.append(call.args[1])
    assert dimmed == ["As", "Ks"]
    assert any("LO winner" in call.args[-1] for call in painter.drawText.call_args_list)


@pytest.mark.parametrize("with_descriptions", [False, True])
def test_timeline_identifies_each_half_even_without_showdown_descriptions(stud_replayer, with_descriptions):
    if with_descriptions:
        stud_replayer.replay_model.hand.showdownStrings = {
            "Hero": "HI: a straight, Four to Eight; LO: 8,7,6,5,4",
            "Player5": "HI: a pair of Aces; LO: 8,7,4,2,A",
        }

    entries = GuiReplayer._timeline_entries(stud_replayer)

    assert any(entry.startswith("Hero:") and "HI winner" in entry for entry in entries)
    assert any(entry.startswith("Player5:") and "LO winner" in entry for entry in entries)
