from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

import fpdb_3_legacy.equity as equity_module
from fpdb_3_legacy import Card, derived_stats_allin
from fpdb_3_legacy.DerivedStats import DerivedStats, _chip_increment
from fpdb_3_legacy.equity import (
    EquityEngine,
    EquityUnavailableError,
    WeightedPocket,
    calculate_equity,
    expected_pot_share,
    load_poker_eval,
)
from fpdb_3_legacy.HandDataReporter import HandDataReporter


class FakePokerEval:
    def __init__(self) -> None:
        self.arguments = None

    def poker_eval(self, **kwargs) -> dict:
        self.arguments = kwargs
        return {
            "info": (2000, 0, 1),
            "eval": [
                {"ev": 825, "winhi": 1600, "tiehi": 100, "losehi": 300},
                {"ev": 175, "winhi": 300, "tiehi": 100, "losehi": 1600},
            ],
        }


class RecordingPokerEval:
    def __init__(self) -> None:
        self.calls = []

    def poker_eval(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        samples = int(kwargs.get("iterations", 820))
        opponent = kwargs["pockets"][1]
        hero_ev = 800 if set(opponent) == {"Ah", "Ad", "7c", "6c"} else 600
        if opponent[0] == "__":
            hero_ev = 700
        opponent_count = len(kwargs["pockets"]) - 1
        opponent_ev = (1000 - hero_ev) // opponent_count

        def item(ev: int) -> dict:
            return {
                "ev": ev,
                "winhi": samples * ev // 1000,
                "tiehi": 0,
                "losehi": samples * (1000 - ev) // 1000,
            }

        return {
            "info": (samples, 0, 1),
            "eval": [item(hero_ev), *[item(opponent_ev) for _ in range(opponent_count)]],
        }


class SeededRecordingPokerEval(RecordingPokerEval):
    """A pypoker-eval 1.3.2+ backend: poker_eval takes seed= (#301)."""

    @staticmethod
    def base_seed() -> int:
        return 0


def test_split_pot_chip_increment_stays_decimal() -> None:
    """Odd split pots must not multiply Decimal by a float during auto-import."""
    assert _chip_increment(100) == Decimal("0.01")
    assert _chip_increment(1) == Decimal("1")


def test_calculate_equity_normalizes_backend_permille() -> None:
    backend = FakePokerEval()

    result = calculate_equity(
        "holdem",
        [["As", "Ah"], ["Ks", "Kh"]],
        ["2c", "3d", "4h"],
        iterations=2000,
        backend=backend,
    )

    assert result.samples == 2000
    assert result.exhaustive is False
    assert [player.equity for player in result.players] == [Decimal("0.825"), Decimal("0.175")]
    assert result.players[0].wins == 1600
    assert result.players[0].ties == 100
    assert backend.arguments["iterations"] == 2000
    assert backend.arguments["board"] == ["2c", "3d", "4h", "__", "__"]


def test_calculate_equity_rejects_duplicate_cards_before_calling_backend() -> None:
    with pytest.raises(ValueError, match="more than once"):
        calculate_equity("holdem", [["As", "Ah"], ["As", "Kh"]], backend=FakePokerEval())


def test_calculate_equity_reports_missing_optional_backend(monkeypatch) -> None:
    monkeypatch.setattr("fpdb_3_legacy.equity.load_poker_eval", lambda: None)

    with pytest.raises(EquityUnavailableError, match="not installed"):
        calculate_equity("holdem", [["As", "Ah"], ["Ks", "Kh"]])


def test_calculate_equity_passes_the_seed_to_a_backend_that_takes_one(monkeypatch) -> None:
    # pypoker-eval 1.3.2 samples from its own PCG stream, out of srand()'s reach.
    monkeypatch.setattr(equity_module, "_seed_native_rng", lambda seed: pytest.fail("srand() is not used"))
    backend = SeededRecordingPokerEval()

    calculate_equity("holdem", [["As", "Ah"], ["Kd", "Kc"]], iterations=500, backend=backend, seed=7)

    assert backend.calls[0]["seed"] == 7


def test_calculate_equity_seeds_srand_for_an_older_backend(monkeypatch) -> None:
    seeded: list[int] = []
    monkeypatch.setattr(equity_module, "_seed_native_rng", seeded.append)
    backend = RecordingPokerEval()

    calculate_equity("holdem", [["As", "Ah"], ["Kd", "Kc"]], iterations=500, backend=backend, seed=7)

    assert "seed" not in backend.calls[0]
    assert seeded == [7]


@pytest.mark.skipif(equity_module.load_poker_eval() is None, reason="pypoker-eval is not installed")
def test_native_seeded_sample_does_not_depend_on_earlier_samples() -> None:
    backend = load_poker_eval()
    pockets = [["6d", "3h"], ["7s", "3s"]]

    def sample(seed: int | None) -> tuple:
        return calculate_equity(
            "fusion", pockets, iterations=equity_module.DEFAULT_EQUITY_ITERATIONS, backend=backend, seed=seed
        ).players

    first = sample(818)
    sample(None)
    calculate_equity("holdem", [["As", "Ah"], ["Kd", "Kc"]], iterations=777, backend=backend)

    assert sample(818) == first
    assert sample(819) != first


def test_expected_pot_share_uses_net_pot() -> None:
    assert expected_pot_share(Decimal("0.4"), Decimal("100"), Decimal("5")) == Decimal("38.0")


@pytest.mark.parametrize(
    ("equity", "pot", "rake"),
    [(Decimal("1.1"), Decimal("10"), Decimal(0)), (Decimal("0.5"), Decimal("10"), Decimal("11"))],
)
def test_expected_pot_share_rejects_invalid_inputs(equity: Decimal, pot: Decimal, rake: Decimal) -> None:
    with pytest.raises(ValueError):
        expected_pot_share(equity, pot, rake)


def test_native_backend_enumerates_missing_turn_and_river() -> None:
    backend = load_poker_eval()
    if backend is None:
        pytest.skip("optional pypoker-eval backend is not installed")

    result = calculate_equity(
        "holdem",
        [["As", "Ah"], ["Ks", "Kh"]],
        ["2c", "3d", "4h"],
        backend=backend,
    )

    assert result.exhaustive is True
    assert result.samples == 990
    assert result.players[0].equity == Decimal("0.912")
    assert result.players[1].equity == Decimal("0.087")


def test_equity_engine_exact_omaha_uses_only_the_decision_flop() -> None:
    backend = RecordingPokerEval()
    engine = EquityEngine(backend)

    result = engine.evaluate_exact(
        "omaha",
        [
            ["as", "Ks", "Qh", "Jh"],
            ["Ah", "Ad", "7c", "6c"],
        ],
        ["Ts", "9s", "2d"],
    )

    assert result.exhaustive
    assert result.players[0].equity == Decimal("0.8")
    assert backend.calls == [
        {
            "game": "omaha",
            "pockets": [["As", "Ks", "Qh", "Jh"], ["Ah", "Ad", "7c", "6c"]],
            "board": ["Ts", "9s", "2d", "__", "__"],
            "dead": [],
        },
    ]


def test_equity_engine_uniform_omaha_uses_native_unknown_pockets_and_cache() -> None:
    backend = RecordingPokerEval()
    engine = EquityEngine(backend)

    first = engine.evaluate_uniform_unknown(
        "omaha",
        ["As", "Ks", "Qh", "Jh"],
        ["Ts", "9s", "2d"],
        opponents=2,
        iterations=5_000,
    )
    second = engine.evaluate_uniform_unknown(
        "omaha",
        ["As", "Ks", "Qh", "Jh"],
        ["Ts", "9s", "2d"],
        opponents=2,
        iterations=5_000,
    )

    assert first is second
    assert len(first.players) == 3
    assert len(backend.calls) == 1
    assert backend.calls[0]["pockets"] == [
        ["As", "Ks", "Qh", "Jh"],
        ["__", "__", "__", "__"],
        ["__", "__", "__", "__"],
    ]
    assert backend.calls[0]["iterations"] == 5_000


def test_equity_engine_cache_is_bounded() -> None:
    backend = RecordingPokerEval()
    engine = EquityEngine(backend, cache_size=1)
    arguments = ("omaha", ["As", "Ks", "Qh", "Jh"], ["Ts", "9s", "2d"])

    engine.evaluate_uniform_unknown(*arguments, iterations=100)
    engine.evaluate_uniform_unknown(*arguments, iterations=200)
    engine.evaluate_uniform_unknown(*arguments, iterations=100)

    assert len(backend.calls) == 3


def test_equity_engine_reports_a_missing_backend_only_once(monkeypatch) -> None:
    loads = []
    warnings = []
    monkeypatch.setattr(equity_module, "load_poker_eval", lambda: loads.append(True))
    monkeypatch.setattr(equity_module.log, "warning", lambda *args: warnings.append(args))
    engine = EquityEngine()

    assert engine.available is False
    assert engine.available is False
    assert len(loads) == 1
    assert len(warnings) == 1


def test_equity_engine_apportions_a_weighted_range_before_native_calls() -> None:
    backend = RecordingPokerEval()
    engine = EquityEngine(backend)
    opponent_range = [
        WeightedPocket(("Ah", "Ad", "7c", "6c"), Decimal(1)),
        WeightedPocket(("Tc", "Td", "8c", "8d"), Decimal(3)),
    ]

    result = engine.evaluate_weighted_range(
        "omaha",
        ["As", "Ks", "Qh", "Jh"],
        [opponent_range],
        ["2c", "3d", "4h"],
        iterations=40,
    )

    assert result.samples == 40
    assert result.players[0].equity == Decimal("0.65")
    assert sorted(call["iterations"] for call in backend.calls) == [10, 30]


def test_equity_engine_removes_blocked_range_pockets_and_rejects_impossible_ranges() -> None:
    backend = RecordingPokerEval()
    engine = EquityEngine(backend)
    blocked = WeightedPocket(("As", "Ad", "7c", "6c"))
    legal = WeightedPocket(("Tc", "Td", "8c", "8d"))

    result = engine.evaluate_weighted_range(
        "omaha",
        ["As", "Ks", "Qh", "Jh"],
        [[blocked, legal]],
        ["2c", "3d", "4h"],
        iterations=20,
    )

    assert result.players[0].equity == Decimal("0.6")
    assert backend.calls[0]["pockets"][1] == sorted(legal.cards)
    with pytest.raises(ValueError, match="No legal range pocket"):
        engine.evaluate_weighted_range(
            "omaha",
            ["As", "Ks", "Qh", "Jh"],
            [[blocked]],
            ["2c", "3d", "4h"],
        )


def test_weighted_ranges_reject_cross_opponent_card_collisions() -> None:
    engine = EquityEngine(RecordingPokerEval())
    same_pocket = WeightedPocket(("Ah", "Ad", "7c", "6c"))

    with pytest.raises(ValueError, match="no collision-free combination"):
        engine.evaluate_weighted_range(
            "omaha",
            ["As", "Ks", "Qh", "Jh"],
            [[same_pocket], [same_pocket]],
            ["2c", "3d", "4h"],
            iterations=20,
        )


@pytest.mark.parametrize(
    "operation",
    [
        lambda engine: engine.evaluate_exact(
            "omaha",
            [["As", "Ks", "Qh", "__"], ["Ah", "Ad", "7c", "6c"]],
            ["2c", "3d", "4h"],
        ),
        lambda engine: engine.evaluate_uniform_unknown(
            "omaha",
            ["As", "Ks", "Qh", "Jh"],
            opponents=0,
        ),
        lambda engine: engine.evaluate_uniform_unknown(
            "bad-game",
            ["As", "Ks", "Qh", "Jh"],
        ),
        lambda engine: engine.evaluate_weighted_range(
            "omaha",
            ["As", "Ks", "Qh", "Jh"],
            [],
        ),
        lambda engine: engine.evaluate_weighted_range(
            "omaha",
            ["As", "Ks", "Qh", "Jh"],
            [[WeightedPocket(("Ah", "Ad", "7c", "__"))]],
        ),
        lambda engine: engine.evaluate_weighted_range(
            "omaha",
            ["As", "Ks", "Qh", "Jh"],
            [[WeightedPocket(("Ah", "Ad", "7c", "6c"), Decimal(0))]],
        ),
        lambda engine: engine.evaluate_uniform_unknown(
            "omaha",
            ["As", "Ks", "Qh", "Jh"],
            opponents=1,
            iterations=0,
        ),
        lambda engine: engine.evaluate_uniform_unknown(
            "omaha",
            ["As", "Ks", "Qh", "__"],
        ),
    ],
)
def test_equity_engine_rejects_invalid_requests(operation) -> None:
    with pytest.raises(ValueError):
        operation(EquityEngine(RecordingPokerEval()))


def test_large_multiway_ranges_are_sampled_reproducibly_and_grouped() -> None:
    first_backend = RecordingPokerEval()
    second_backend = RecordingPokerEval()
    first_engine = EquityEngine(first_backend, range_enumeration_limit=1)
    second_engine = EquityEngine(second_backend, range_enumeration_limit=1)
    ranges = [
        [
            WeightedPocket(("Ah", "Ad", "7c", "6c"), Decimal(1)),
            WeightedPocket(("Tc", "Td", "8c", "8d"), Decimal(2)),
        ],
        [
            WeightedPocket(("2h", "2s", "3h", "3s"), Decimal(3)),
            WeightedPocket(("4c", "4d", "5c", "5d"), Decimal(1)),
        ],
    ]

    first = first_engine.evaluate_weighted_range(
        "omaha",
        ["As", "Ks", "Qh", "Jh"],
        ranges,
        ["9c", "9d", "6h"],
        iterations=200,
        seed=81499,
        range_model="population",
        range_version=2,
    )
    second = second_engine.evaluate_weighted_range(
        "omaha",
        ["As", "Ks", "Qh", "Jh"],
        ranges,
        ["9c", "9d", "6h"],
        iterations=200,
        seed=81499,
        range_model="population",
        range_version=2,
    )

    assert len(first.players) == 3
    assert first.players == second.players
    assert sum(call["iterations"] for call in first_backend.calls) == 200
    assert [(call["pockets"], call["iterations"]) for call in first_backend.calls] == [
        (call["pockets"], call["iterations"]) for call in second_backend.calls
    ]


def test_native_backend_supports_uniform_unknown_omaha_pockets() -> None:
    backend = load_poker_eval()
    if backend is None:
        pytest.skip("optional pypoker-eval backend is not installed")

    engine = EquityEngine(backend)
    exact = engine.evaluate_exact(
        "omaha",
        [
            ["As", "Ks", "Qh", "Jh"],
            ["Ah", "Ad", "7c", "6c"],
        ],
        ["Ts", "9s", "2d"],
    )
    result = engine.evaluate_uniform_unknown(
        "omaha",
        ["As", "Ks", "Qh", "Jh"],
        ["Ts", "9s", "2d"],
        opponents=2,
        iterations=10_000,
    )

    assert exact.samples == 820
    assert [player.equity for player in exact.players] == [Decimal("0.714"), Decimal("0.285")]
    assert result.samples == 10_000
    assert len(result.players) == 3
    assert Decimal("0.55") < result.players[0].equity < Decimal("0.68")


def test_derived_stats_stores_expected_all_in_profit_x100(monkeypatch) -> None:
    backend = FakePokerEval()
    monkeypatch.setattr("fpdb_3_legacy.derived_stats_allin.pokereval", backend)
    stats = DerivedStats()
    stats.handsplayers = {
        "hero": {"sawShowdown": True, "wentAllIn": True, "allInEV": 0},
        "villain": {"sawShowdown": True, "wentAllIn": True, "allInEV": 0},
    }
    hand = SimpleNamespace(
        handid="all-in-1",
        gametype={"base": "hold"},
        totalpot=Decimal("200"),
        rake=Decimal(0),
        pot=SimpleNamespace(
            committed={"hero": Decimal("100"), "villain": Decimal("100")},
            common={},
        ),
    )

    stats.getAllInEV(
        hand,
        "holdem",
        ["hero", "villain"],
        {"FLOP": {"allin": True, "board": [["2c", "3d", "4h"]]}},
        {},
        {"hero": {"hole": ["As", "Ah"]}, "villain": {"hole": ["Ks", "Kh"]}},
    )

    assert stats.handsplayers["hero"]["allInEV"] == 6500
    assert stats.handsplayers["villain"]["allInEV"] == -6500


def test_hand_report_exposes_readable_all_in_ev() -> None:
    hand = SimpleNamespace(
        handid="reported-all-in",
        players=[(1, "hero", Decimal("100"))],
        handsplayers={"hero": {"allInEV": 6500}},
        gametype={"currency": "USD", "limitType": "nl", "category": "holdem"},
    )

    data = HandDataReporter("detailed")._extract_hand_data(hand)

    assert data["players"]["hero"]["all_in_ev_x100"] == 6500
    assert data["players"]["hero"]["all_in_ev"] == "65"


def test_boards_dict_detects_real_all_in_and_accumulates_board() -> None:
    hand = SimpleNamespace(
        handid="board-all-in",
        board={"FLOP": ["2c", "3d", "4h"], "TURN": ["5s"], "RIVER": ["6c"]},
        actions={
            "PREFLOP": [("hero", "calls", Decimal("2"), False)],
            "FLOP": [("villain", "raises", Decimal("98"), Decimal("100"), Decimal(0), True)],
            "TURN": [],
            "RIVER": [],
        },
    )

    boards = DerivedStats().getBoardsDict(
        hand,
        "holdem",
        {"PREFLOP": 0, "FLOP": 1, "TURN": 2, "RIVER": 3},
    )

    assert boards["PREFLOP"] == {"board": [[]], "allin": False}
    assert boards["FLOP"] == {"board": [["2c", "3d", "4h"]], "allin": True}
    assert boards["TURN"] == {"board": [["2c", "3d", "4h", "5s"]], "allin": False}
    assert boards["RIVER"] == {"board": [["2c", "3d", "4h", "5s", "6c"]], "allin": False}


@pytest.mark.skipif(equity_module.load_poker_eval() is None, reason="pypoker-eval is not installed")
def test_every_eval_game_evaluates_its_own_complete_hands() -> None:
    # Card.games' second field goes to poker-eval as is. A name it lists but
    # does not enumerate failed only at import time: "fusion" before #818,
    # "5draw" (pyenum error code 1) before poker-eval 1.3.3 (#831).
    engine = equity_module.load_poker_eval()
    failures = {}
    for category, (base, evalgame, _hilo, _streets, _last, hrange) in Card.games.items():
        if not evalgame:
            continue
        start, end = hrange[-1]
        deck = iter(f"{rank}{suit}" for rank in "AKQJT98765432" for suit in "shdc")
        pockets = [[next(deck) for _ in range(end - start)] for _ in range(2)]
        board = [next(deck) for _ in range(5)] if base == "hold" else []
        try:
            engine.winners(game=evalgame, pockets=pockets, board=board)
        except RuntimeError as error:
            failures[category] = f"{evalgame}: {error}"
    assert not failures, failures


def _fusion_all_in_hand() -> SimpleNamespace:
    return SimpleNamespace(
        handid="fusion-all-in",
        gametype={"base": "hold", "category": "fusion"},
        holeStreets=["PREFLOP", "FLOP", "TURN"],
        totalpot=Decimal("200"),
        rake=Decimal(0),
        pot=SimpleNamespace(
            committed={"hero": Decimal("100"), "villain": Decimal("100")},
            common={},
        ),
    )


def _fusion_stats() -> DerivedStats:
    stats = DerivedStats()
    stats.handsplayers = {
        "hero": {"sawShowdown": True, "wentAllIn": True, "allInEV": 0},
        "villain": {"sawShowdown": True, "wentAllIn": True, "allInEV": 0},
    }
    return stats


FUSION_STREETS = {"PREFLOP": 0, "FLOP": 1, "TURN": 2, "RIVER": 3}
FUSION_HOLECARDS = {
    "hero": {"hole": ["As", "Kd", "Qc", "Jh"]},
    "villain": {"hole": ["Td", "Tc", "3h", "4h"]},
}


def test_fusion_all_in_on_the_flop_samples_the_turn_hole_card(monkeypatch) -> None:
    # On the flop the fourth hole card is not dealt yet: the engine gets the
    # three cards each player held and deals the rest itself (#818). Exact
    # enumeration is far too slow multiway, so it is sampled.
    backend = SeededRecordingPokerEval()
    monkeypatch.setattr("fpdb_3_legacy.derived_stats_allin.pokereval", backend)
    stats = _fusion_stats()

    stats.getAllInEV(
        _fusion_all_in_hand(),
        Card.games["fusion"][1],
        ["hero", "villain"],
        {"FLOP": {"allin": True, "board": [["2s", "5s", "8s"]]}},
        FUSION_STREETS,
        FUSION_HOLECARDS,
    )

    (call,) = backend.calls
    assert call["game"] == "fusion"
    assert call["pockets"] == [["As", "Kd", "Qc"], ["Td", "Tc", "3h"]]
    assert call["board"] == ["2s", "5s", "8s", "__", "__"]
    assert call["iterations"] == equity_module.DEFAULT_EQUITY_ITERATIONS
    # Seeded, so a re-import stores the same EV whatever was sampled before.
    assert call["seed"] == derived_stats_allin.ALL_IN_EV_SEED
    assert stats.handsplayers["hero"]["allInEVCalculated"] is True


def test_fusion_pockets_keep_the_cards_held_with_the_board() -> None:
    pockets = [["As", "Kd", "Qc", "Jh"], ["Td", "Tc", "3h", "4h"]]

    assert equity_module.fusion_pockets(pockets, []) == [["As", "Kd"], ["Td", "Tc"]]
    assert equity_module.fusion_pockets(pockets, ["2s", "5s", "8s"]) == [["As", "Kd", "Qc"], ["Td", "Tc", "3h"]]
    assert equity_module.fusion_pockets(pockets, ["2s", "5s", "8s", "9s", "2d"]) == pockets
    with pytest.raises(ValueError, match="0, 3, 4 or 5"):
        equity_module.fusion_pockets(pockets, ["2s"])


@pytest.mark.skipif(equity_module.load_poker_eval() is None, reason="pypoker-eval is not installed")
def test_fusion_all_in_on_the_turn_is_exact_under_omaha_rules() -> None:
    # Four spades on board, one in the hero's hand: a flush under hold'em rules,
    # nothing under Fusion's (exactly two hole cards), so the tens are ahead.
    stats = _fusion_stats()

    stats.getAllInEV(
        _fusion_all_in_hand(),
        Card.games["fusion"][1],
        ["hero", "villain"],
        {"TURN": {"allin": True, "board": [["2s", "5s", "8s", "9s"]]}},
        FUSION_STREETS,
        FUSION_HOLECARDS,
    )

    assert stats.handsplayers["hero"]["allInEV"] == -4500
    assert stats.handsplayers["villain"]["allInEV"] == 4500
