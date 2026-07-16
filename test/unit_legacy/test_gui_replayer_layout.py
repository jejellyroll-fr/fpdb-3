from decimal import Decimal
from types import SimpleNamespace

from fpdb_3_legacy.GuiReplayer import (
    CONTROL_RESERVED_HEIGHT,
    HEADER_HEIGHT,
    MIN_CARD_SCALE,
    TIMELINE_MIN_WINDOW_WIDTH,
    ReplayPlayer,
    TableState,
    action_colors,
    build_replay_layout,
    format_replay_amount,
    hidden_card_count,
    order_players_clockwise,
    replay_hero_equity,
    seat_anchors,
    visible_hole_card_count,
)
from fpdb_3_legacy.localized_formats import get_format_locale, set_format_locale


class _FakeEquityBackend:
    def poker_eval(self, **kwargs):
        assert kwargs["board"] == ["2c", "3d", "4h", "__", "__"]
        return {
            "info": (1000, 0, 1),
            "eval": [
                {"ev": 750, "winhi": 700, "tiehi": 100, "losehi": 200},
                {"ev": 250, "winhi": 200, "tiehi": 100, "losehi": 700},
            ],
        }


def test_replay_amount_distinguishes_money_and_chips() -> None:
    previous = get_format_locale()
    try:
        set_format_locale("fr_FR")
        assert format_replay_amount(Decimal("12.50"), "EUR") == "12,50\u00a0€"
        assert format_replay_amount(Decimal("12.50"), "mBTC") == "12,50\u00a0ⓑ"
        assert format_replay_amount(Decimal("1250"), "T$") == "1\u202f250,00"
    finally:
        set_format_locale(previous)


def test_replay_equity_uses_visible_board_and_known_live_pockets():
    frame = SimpleNamespace(
        players=[
            ReplayPlayer("hero", 1, Decimal(0), Decimal(0), "calls", False, ["As", "Ah"]),
            ReplayPlayer("villain", 2, Decimal(0), Decimal(0), "raises", False, ["Ks", "Kh"]),
        ],
        board={"FLOP": ["2c", "3d", "4h"], "TURN": ["5s"]},
        render_board={"FLOP"},
    )

    equity = replay_hero_equity(frame, "hero", "holdem", backend=_FakeEquityBackend(), iterations=1000)

    assert equity == Decimal("0.75")


def test_replay_equity_hides_when_a_live_pocket_is_unknown():
    frame = SimpleNamespace(
        players=[
            ReplayPlayer("hero", 1, Decimal(0), Decimal(0), "calls", False, ["As", "Ah"]),
            ReplayPlayer("villain", 2, Decimal(0), Decimal(0), "raises", False, ["0", "0"]),
        ],
        board={},
        render_board=set(),
    )

    assert replay_hero_equity(frame, "hero", "holdem", backend=_FakeEquityBackend()) is None


class _FakeHand:
    """Minimal stand-in for a parsed Hand, enough to build a TableState."""

    def __init__(self, players, stacks):
        self.board = {}
        self.maxseats = len(players)
        self.gametype = {"category": "omahahi", "base": "hold"}
        # hand.players rows are (seat, name, stack, ...)
        self.players = [[i + 1, name, stacks[name]] for i, name in enumerate(players)]

    def join_holecards(self, name, asList=False, street=None):
        return [] if asList else ""


def test_hidden_card_count_matches_poker_variants():
    assert hidden_card_count("holdem", ["As", "Kd"]) == 2
    assert hidden_card_count("fusion", ["As", "Kd"]) == 2
    assert hidden_card_count("2_holdem", ["As", "Kd", "Qc"]) == 3
    assert hidden_card_count("omahahi", ["As", "Kd", "Qc", "Jh"]) == 4
    assert hidden_card_count("5_omahahi", ["As", "Kd", "Qc", "Jh", "Ts"]) == 5
    assert hidden_card_count("6_omahahi", ["As", "Kd", "Qc", "Jh", "Ts", "9c"]) == 6


def test_unknown_hidden_card_count_falls_back_to_known_cards():
    assert hidden_card_count("badugi", ["As", "Kd", "Qc", "Jh"]) == 4
    assert hidden_card_count("unknown", []) == 0


def test_fusion_visible_cards_progress_by_street():
    assert visible_hole_card_count("fusion", "PREFLOP") == 2
    assert visible_hole_card_count("fusion", "FLOP") == 3
    assert visible_hole_card_count("fusion", "TURN") == 4
    assert visible_hole_card_count("fusion", "RIVER") == 4
    assert visible_hole_card_count("fusion", "PREFLOP", final_frame=True) == 4


def test_stud_visible_cards_progress_by_street():
    assert visible_hole_card_count("studhi", "THIRD") == 3
    assert visible_hole_card_count("studhi", "FOURTH") == 4
    assert visible_hole_card_count("studhi", "FIFTH") == 5
    assert visible_hole_card_count("studhi", "SIXTH") == 6
    assert visible_hole_card_count("studhi", "SEVENTH") == 7
    assert visible_hole_card_count("5_studhi", "SECOND") == 2
    assert visible_hole_card_count("5_studhi", "FIFTH") == 5


def test_action_colors_distinguish_main_action_types():
    assert action_colors("folds")[2].name() == "#ff6f79"
    assert action_colors("raises")[2].name() == "#ffe769"
    assert action_colors("calls")[2].name() == "#9ee8b6"
    assert action_colors("small blind")[2].name() == "#a9d1ff"


def test_seat_anchors_put_first_player_at_bottom():
    anchors = seat_anchors(6)

    assert len(anchors) == 6
    assert round(anchors[0].x, 6) == 0
    assert round(anchors[0].y, 6) == 1
    assert anchors[1].x < 0
    assert anchors[1].y > 0
    assert anchors[3].y < -0.99


def test_players_are_ordered_by_seat_and_rotated_to_hero():
    players = [
        ReplayPlayer("seat5", 5, 0, 0, None, False, []),
        ReplayPlayer("hero", 3, 0, 0, None, False, []),
        ReplayPlayer("seat1", 1, 0, 0, None, False, []),
        ReplayPlayer("seat4", 4, 0, 0, None, False, []),
    ]

    ordered = order_players_clockwise(players, "hero")

    assert [player.name for player in ordered] == ["hero", "seat4", "seat5", "seat1"]


def test_layout_reserves_header_controls_and_timeline():
    players = [f"p{i}" for i in range(6)]
    layout = build_replay_layout(1600, 900, players, hero_name="p3")
    control_top = 900 - CONTROL_RESERVED_HEIGHT

    assert layout.table_rect.top() >= HEADER_HEIGHT
    assert layout.table_rect.bottom() <= control_top
    assert not layout.timeline_rect.isNull()
    assert set(layout.seats) == set(players)
    for seat in layout.seats.values():
        assert seat.panel_rect.top() >= HEADER_HEIGHT
        assert seat.panel_rect.bottom() <= control_top
        assert seat.cards_rect.top() >= HEADER_HEIGHT
        assert seat.cards_rect.bottom() <= control_top
        assert not seat.panel_rect.intersects(seat.cards_rect)
        assert not seat.panel_rect.intersects(layout.board_rect)


def test_layout_keeps_short_windows_above_controls():
    players = [f"p{i}" for i in range(9)]
    layout = build_replay_layout(1366, 768, players, hero_name="p0")
    control_top = 768 - CONTROL_RESERVED_HEIGHT

    assert layout.table_rect.bottom() <= control_top
    assert len(layout.seats) == 9
    assert layout.timeline_rect.isNull()
    for seat in layout.seats.values():
        assert seat.panel_rect.bottom() <= control_top
        assert seat.cards_rect.bottom() <= control_top
        assert not seat.panel_rect.intersects(seat.cards_rect)
        assert abs(seat.cards_rect.center().x() - seat.panel_rect.center().x()) < 1


def test_layout_scales_cards_down_for_compact_windows():
    compact = build_replay_layout(1080, 760, [f"p{i}" for i in range(5)], hero_name="p0")
    full = build_replay_layout(2048, 1152, [f"p{i}" for i in range(5)], hero_name="p0")

    assert compact.card_width < full.card_width
    assert compact.card_width >= int(70 * MIN_CARD_SCALE)


def test_timeline_appears_only_when_width_allows_readability():
    compact = build_replay_layout(TIMELINE_MIN_WINDOW_WIDTH - 1, 900, [f"p{i}" for i in range(6)])
    wide = build_replay_layout(TIMELINE_MIN_WINDOW_WIDTH, 900, [f"p{i}" for i in range(6)])

    assert compact.timeline_rect.isNull()
    assert not wide.timeline_rect.isNull()
    assert wide.timeline_rect.width() >= 260


def test_updateforaction_flags_allin_when_stack_empties():
    hand = _FakeHand(["hero", "villain"], {"hero": "1.00", "villain": "1.00"})
    state = TableState(hand)
    state.street = "PREFLOP"

    # Villain commits their whole stack -> all-in.
    state.updateForAction(("villain", "raises", Decimal("1.00"), Decimal("1.00"), Decimal("0"), True))

    assert state.players["villain"].allin is True
    assert state.players["villain"].stack == Decimal("0")
    assert state.players["hero"].allin is False


def test_updateforaction_does_not_flag_allin_on_fold():
    hand = _FakeHand(["hero", "villain"], {"hero": "0.00", "villain": "1.00"})
    state = TableState(hand)
    state.street = "PREFLOP"

    # Hero already has an empty stack but only folds; must not be flagged all-in.
    state.updateForAction(("hero", "folds"))

    assert state.players["hero"].allin is False


def test_computepots_single_pot_when_allin_is_fully_matched():
    hand = _FakeHand(["p1", "p2", "p3"], {"p1": "1.00", "p2": "5.00", "p3": "5.00"})
    state = TableState(hand)

    state.startPhase("PREFLOP")
    state.updateForAction(("p1", "raises", Decimal("1.00"), Decimal("1.00"), Decimal("0"), True))
    state.updateForAction(("p2", "calls", Decimal("1.00"), False))
    state.updateForAction(("p3", "calls", Decimal("1.00"), False))

    # p1 is all-in but everyone matched the $1.00 -> a single pot, no side pot.
    assert state.computePots() == [("Pot", Decimal("3.00"))]


def test_computepots_splits_main_and_side_pot():
    hand = _FakeHand(["p1", "p2", "p3"], {"p1": "1.00", "p2": "5.00", "p3": "5.00"})
    state = TableState(hand)

    state.startPhase("PREFLOP")
    state.updateForAction(("p1", "raises", Decimal("1.00"), Decimal("1.00"), Decimal("0"), True))
    state.updateForAction(("p2", "calls", Decimal("1.00"), False))
    state.updateForAction(("p3", "calls", Decimal("1.00"), False))

    state.startPhase("FLOP")
    state.updateForAction(("p2", "bets", Decimal("4.00"), True))
    state.updateForAction(("p3", "calls", Decimal("4.00"), False))

    # Main pot: $1.00 x 3 = $3.00 (all eligible). Side pot: $4.00 x 2 = $8.00 (p2/p3 only).
    assert state.computePots() == [
        ("Main pot", Decimal("3.00")),
        ("Side pot 1", Decimal("8.00")),
    ]


def test_computepots_excludes_uncalled_bet():
    hand = _FakeHand(["p1", "p2"], {"p1": "5.00", "p2": "2.00"})
    state = TableState(hand)

    state.startPhase("PREFLOP")
    # p2 shoves $2 all-in, p1 raises to $5 (the extra $3 is uncalled).
    state.updateForAction(("p2", "raises", Decimal("2.00"), Decimal("2.00"), Decimal("0"), True))
    state.updateForAction(("p1", "raises", Decimal("3.00"), Decimal("5.00"), Decimal("2.00"), False))

    # Only the matched $2.00 from each player forms a pot; p1's uncalled $3 is excluded.
    assert state.computePots() == [("Pot", Decimal("4.00"))]


def test_computepots_is_empty_after_hand_ends():
    hand = _FakeHand(["p1", "p2", "p3"], {"p1": "1.00", "p2": "5.00", "p3": "5.00"})
    state = TableState(hand)

    state.startPhase("PREFLOP")
    state.updateForAction(("p1", "raises", Decimal("1.00"), Decimal("1.00"), Decimal("0"), True))
    state.updateForAction(("p2", "calls", Decimal("1.00"), False))
    state.updateForAction(("p3", "calls", Decimal("1.00"), False))

    # Before the hand ends the pot is still on the table...
    assert state.computePots() == [("Pot", Decimal("3.00"))]

    # ...but once the money is pushed to the winner the central pot is empty.
    state.endHand({"p2": Decimal("3.00")}, {})
    assert state.computePots() == [("Pot", Decimal(0))]
