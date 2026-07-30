"""Known-card, range and decision EV analyses for All-in or Fold."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from threading import Event
from types import SimpleNamespace

import pytest

from fpdb_3_legacy.aof_equity import (
    KnownCardsAnalysisCoordinator,
    analyze_decision_ev,
    analyze_known_cards_hand,
    analyze_population_hand,
    build_known_cards_hand_request,
    build_pot_layers,
)
from fpdb_3_legacy.aof_ranges import (
    ActionObservation,
    PopulationActionModel,
    PopulationObservedRange,
    RangeObservation,
)
from fpdb_3_legacy.autonotes_aof import AofDecision, extract_decisions
from fpdb_3_legacy.equity import EquityEngine, load_poker_eval
from fpdb_3_legacy.equity_async import AsyncEquityService, EquitySubmission


class LayerBackend:
    def __init__(self, *, heads_up: int = 600, multiway: int = 300) -> None:
        self.heads_up = heads_up
        self.multiway = multiway
        self.calls = []

    def poker_eval(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        players = len(kwargs["pockets"])
        hero = self.heads_up if players == 2 else self.multiway
        other = (1000 - hero) // (players - 1)

        def result(equity: int) -> dict:
            return {"ev": equity, "winhi": equity, "tiehi": 0, "losehi": 1000 - equity}

        return {
            "info": (990, 0, 1),
            "eval": [result(hero), *[result(other) for _ in range(players - 1)]],
        }


def _decision(player_id: int, *, hand_id: int = 9, amount: int = 175) -> AofDecision:
    return AofDecision(
        hand_id=hand_id,
        player_id=player_id,
        category="aof_omaha",
        decision="allin",
        role="call_shove",
        active_opponents=1,
        pot_before=225,
        amount_to_commit=amount,
        blind_committed=25,
        cards_observable=True,
        hole_cards="As Ks Qh Jh",
        flop_cards="Ts 9s 2d",
        made_hand="no made hand",
        flush_draw="nut flush draw",
        straight_outs=13,
    )


def _hand(
    commitments: dict[str, int],
    *,
    contenders: set[str] | None = None,
    folded: set[str] | None = None,
    common: dict[str, int] | None = None,
    rake: int = 0,
    cards: dict[str, tuple[str, ...]] | None = None,
):
    names = list(commitments)
    common = common or {}
    total = sum(commitments.values()) + sum(common.values())
    folded = folded or set()
    contenders = contenders if contenders is not None else set(names) - folded
    cards = cards or {
        "hero": ("As", "Ks", "Qh", "Jh"),
        "villain": ("Ah", "Ad", "7c", "6c"),
        "short": ("Tc", "Td", "8c", "8d"),
        "folder": ("2c", "3c", "4c", "5c"),
        "deep": ("Kh", "Kd", "9c", "9d"),
    }
    hand = SimpleNamespace(
        dbid_hands=9,
        gametype={"category": "aof_omaha", "bb": Decimal("0.25")},
        playerIds={name: index for index, name in enumerate(names, start=1)},
        players=[(index, name, Decimal("2.00")) for index, name in enumerate(names, start=1)],
        folded=folded,
        board={"FLOP": ["Ts", "9s", "2d"], "TURN": ["3h"], "RIVER": ["4h"]},
        totalpot=Decimal(total) / 100,
        rake=Decimal(rake) / 100,
        pot=SimpleNamespace(
            committed={name: Decimal(amount) / 100 for name, amount in commitments.items()},
            common={name: Decimal(common.get(name, 0)) / 100 for name in names},
            stp=0,
            contenders=contenders,
        ),
    )
    hand.join_holecards = lambda player, asList=False: list(cards.get(player, ()))
    return hand


def _request(hand, decisions: list[AofDecision] | None = None, ids: list[int] | None = None):
    decisions = decisions or [_decision(hand.playerIds["hero"])]
    ids = ids or list(range(101, 101 + len(decisions)))
    request = build_known_cards_hand_request(hand, decisions, ids)
    assert request is not None
    return request


def test_heads_up_ev_uses_the_final_pot_after_rake_and_only_the_flop() -> None:
    backend = LayerBackend(heads_up=500)
    request = _request(_hand({"hero": 200, "villain": 200}, rake=6))

    (analysis,) = analyze_known_cards_hand(request, EquityEngine(backend)).analyses

    assert (analysis.status, analysis.equity_ppm) == ("complete", 500_000)
    assert analysis.ev_chips == 22
    assert analysis.ev_bb_ppm == 880_000
    assert analysis.break_even_ppm == 444_162
    assert backend.calls[0]["board"] == ["Ts", "9s", "2d", "__", "__"]
    assert "3h" not in backend.calls[0]["board"]
    assert "4h" not in backend.calls[0]["board"]


def test_multiway_side_pots_are_evaluated_with_their_own_eligible_players() -> None:
    hand = _hand({"short": 100, "hero": 200, "deep": 200})
    backend = LayerBackend(heads_up=600, multiway=300)

    (analysis,) = analyze_known_cards_hand(_request(hand), EquityEngine(backend)).analyses

    assert [(layer.gross_cents, layer.eligible) for layer in build_pot_layers(hand)] == [
        (300, ("deep", "hero", "short")),
        (200, ("deep", "hero")),
    ]
    assert analysis.equity_ppm == 420_000
    assert analysis.ev_chips == 35
    assert len(backend.calls) == 2
    heads_up = next(call for call in backend.calls if len(call["pockets"]) == 2)
    assert set(heads_up["dead"]) == {"Tc", "Td", "8c", "8d"}


def test_rake_is_allocated_proportionally_across_side_pots() -> None:
    hand = _hand({"short": 100, "hero": 200, "deep": 200}, rake=5)

    (analysis,) = analyze_known_cards_hand(
        _request(hand),
        EquityEngine(LayerBackend(heads_up=600, multiway=300)),
    ).analyses

    assert [(layer.gross_cents, layer.net_cents) for layer in build_pot_layers(hand)] == [
        (300, 297),
        (200, 198),
    ]
    assert analysis.equity_ppm == 420_000
    assert analysis.ev_chips == 33


def test_a_folder_is_dead_money_and_never_an_equity_participant() -> None:
    hand = _hand(
        {"folder": 50, "hero": 200, "villain": 200},
        contenders={"hero", "villain"},
        folded={"folder"},
    )
    backend = LayerBackend(heads_up=500)

    (analysis,) = analyze_known_cards_hand(_request(hand), EquityEngine(backend)).analyses

    assert [(layer.gross_cents, layer.eligible) for layer in build_pot_layers(hand)] == [
        (150, ("hero", "villain")),
        (300, ("hero", "villain")),
    ]
    assert analysis.ev_chips == 50
    assert len(backend.calls) == 1  # identical layers share the exact-equity cache
    assert set(backend.calls[0]["dead"]) == {"2c", "3c", "4c", "5c"}
    assert len(backend.calls[0]["pockets"]) == 2


def test_split_pots_are_carried_by_the_backend_equity() -> None:
    backend = LayerBackend(heads_up=500)

    (analysis,) = analyze_known_cards_hand(
        _request(_hand({"hero": 200, "villain": 200})),
        EquityEngine(backend),
    ).analyses

    assert analysis.equity_ppm == 500_000
    assert analysis.ev_chips == 25


def test_partially_hidden_eligible_pockets_are_not_guessed() -> None:
    hand = _hand(
        {"hero": 200, "villain": 200},
        cards={"hero": ("As", "Ks", "Qh", "Jh"), "villain": ("0x", "0x", "0x", "0x")},
    )
    backend = LayerBackend()

    (analysis,) = analyze_known_cards_hand(_request(hand), EquityEngine(backend)).analyses

    assert analysis.status == "incomplete"
    assert analysis.equity_ppm is None
    assert analysis.error_text == "eligible pocket cards are hidden: villain"
    assert backend.calls == []


def test_an_uncalled_shove_is_not_presented_as_ev_against_actual_callers() -> None:
    hand = _hand({"hero": 200}, contenders={"hero"})

    (analysis,) = analyze_known_cards_hand(_request(hand), EquityEngine(LayerBackend())).analyses

    assert analysis.status == "no_callers"
    assert analysis.equity_ppm is None


def test_a_missing_big_blind_does_not_turn_an_unknown_ev_into_zero() -> None:
    hand = _hand({"hero": 200, "villain": 200})
    hand.gametype["bb"] = Decimal(0)
    backend = LayerBackend()

    (analysis,) = analyze_known_cards_hand(_request(hand), EquityEngine(backend)).analyses

    assert analysis.status == "incomplete"
    assert analysis.ev_bb_ppm is None
    assert analysis.error_text == "the big blind is unavailable"
    assert backend.calls == []


class RangeSource:
    def __init__(
        self,
        observations: list[RangeObservation],
        actions: list[ActionObservation] | None = None,
    ) -> None:
        self.observations = observations
        self.actions = actions or []
        self.calls = []
        self.action_calls = []

    def getAofDecisionSite(self, decision_id: int) -> int:
        assert decision_id > 0
        return 140

    def getAofDecisionScope(self, decision_id: int) -> tuple[int, None]:
        assert decision_id > 0
        return (140, None)

    def getAofRangeObservations(
        self,
        site_id: int,
        category: str,
        role: str,
        active_opponents: int,
        before_hand_id: int,
        maximum_observations: int = 5_000,
    ) -> tuple[RangeObservation, ...]:
        self.calls.append(
            (
                site_id,
                category,
                role,
                active_opponents,
                before_hand_id,
                maximum_observations,
            ),
        )
        return tuple(self.observations[:maximum_observations])

    def getAofActionObservations(
        self,
        site_id: int,
        category: str,
        role: str,
        active_opponents: int,
        before_hand_id: int,
        maximum_observations: int = 5_000,
    ) -> tuple[ActionObservation, ...]:
        self.action_calls.append(
            (
                site_id,
                category,
                role,
                active_opponents,
                before_hand_id,
                maximum_observations,
            ),
        )
        return tuple(self.actions[:maximum_observations])


def _range_observations() -> list[RangeObservation]:
    return [
        RangeObservation(
            hand_id=hand_id,
            player_id=20 + hand_id,
            site_id=140,
            category="aof_omaha",
            role=role,
            active_opponents=1,
            hole_cards=cards,
        )
        for hand_id, role, cards in (
            (1, "open_shove", "Ah Ad 7c 6c"),
            (2, "open_shove", "Kh Kd 8c 8d"),
            (3, "call_shove", "2c 3c 4d 5d"),
            (4, "call_shove", "6c 7d 8h 9c"),
        )
    ]


def _many_range_observations(
    role: str,
    active_opponents: int,
    *,
    count: int = 100,
    cards: str = "Ah Ad 7c 6c",
) -> list[RangeObservation]:
    return [
        RangeObservation(
            hand_id=index + 1,
            player_id=index + 100,
            site_id=140,
            category="aof_omaha",
            role=role,
            active_opponents=active_opponents,
            hole_cards=cards,
        )
        for index in range(count)
    ]


def _many_action_observations(
    role: str,
    active_opponents: int,
    *,
    all_ins: int,
    folds: int,
) -> list[ActionObservation]:
    decisions = ["allin"] * all_ins + ["fold"] * folds
    return [
        ActionObservation(
            hand_id=index + 1,
            player_id=index + 100,
            site_id=140,
            category="aof_omaha",
            role=role,
            active_opponents=active_opponents,
            decision=decision,
        )
        for index, decision in enumerate(decisions)
    ]


def test_population_equity_uses_opponents_roles_and_strictly_earlier_samples() -> None:
    hand = _hand({"hero": 200, "villain": 200})
    decisions = [
        _decision(hand.playerIds["hero"], hand_id=9),
        replace(
            _decision(hand.playerIds["villain"], hand_id=9),
            role="open_shove",
        ),
    ]
    source = RangeSource(_range_observations())
    request = _request(hand, decisions, [101, 102])

    result = analyze_population_hand(
        request,
        EquityEngine(LayerBackend(heads_up=600)),
        source,
        PopulationObservedRange(minimum_observations=2),
    )

    assert [analysis.status for analysis in result.analyses] == ["complete", "complete"]
    assert [analysis.range_model for analysis in result.analyses] == [
        "population_observed",
        "population_observed",
    ]
    assert [analysis.equity_ppm for analysis in result.analyses] == [600_000, 600_000]
    assert all(analysis.ev_chips is None for analysis in result.analyses)
    assert set(source.calls) == {
        (140, "aof_omaha", "open_shove", 1, 9, 5_000),
        (140, "aof_omaha", "call_shove", 1, 9, 5_000),
    }


def test_population_equity_stays_incomplete_below_the_sample_floor() -> None:
    hand = _hand({"hero": 200, "villain": 200})
    decisions = [
        _decision(hand.playerIds["hero"], hand_id=9),
        replace(
            _decision(hand.playerIds["villain"], hand_id=9),
            role="open_shove",
        ),
    ]
    backend = LayerBackend()

    result = analyze_population_hand(
        _request(hand, decisions, [101, 102]),
        EquityEngine(backend),
        RangeSource(_range_observations()[:1]),
        PopulationObservedRange(minimum_observations=2),
    )

    assert result.analyses[0].status == "incomplete"
    assert "population sample 1 is below 2" in str(result.analyses[0].error_text)
    assert backend.calls == []


def test_call_decision_ev_uses_the_prior_shovers_range_and_remaining_cost() -> None:
    hand = _hand({"hero": 200, "villain": 200})
    decisions = [
        replace(
            _decision(hand.playerIds["villain"], hand_id=1_000, amount=190),
            role="open_shove",
            pot_before=35,
            blind_committed=10,
        ),
        replace(
            _decision(hand.playerIds["hero"], hand_id=1_000),
            role="call_shove",
            pot_before=225,
            blind_committed=25,
        ),
    ]
    request = _request(hand, decisions, [101, 102]).decisions[1]
    backend = LayerBackend(heads_up=900)

    analysis = analyze_decision_ev(
        request,
        EquityEngine(backend),
        RangeSource(_many_range_observations("open_shove", 1, count=500)),
        PopulationObservedRange(minimum_observations=25),
        PopulationActionModel(minimum_observations=25),
        140,
        None,
    )

    assert analysis.range_model == "population_decision_ev_prerake"
    assert analysis.status == "strong"
    assert analysis.ev_chips == 185
    assert analysis.ev_bb_ppm == 7_400_000
    assert analysis.equity_ppm is None
    assert backend.calls[0]["board"] == ["Ts", "9s", "2d", "__", "__"]


def test_hidden_hero_cards_never_become_a_modeled_decision() -> None:
    hand = _hand(
        {"villain": 200, "hero": 200},
        cards={"villain": ("Ah", "Ad", "7c", "6c"), "hero": ("0x", "0x", "0x", "0x")},
    )
    decisions = [
        replace(
            _decision(hand.playerIds["villain"], hand_id=1_000, amount=190),
            role="open_shove",
            pot_before=35,
            blind_committed=10,
        ),
        replace(_decision(hand.playerIds["hero"], hand_id=1_000), pot_before=225),
    ]
    request = _request(hand, decisions, [101, 102]).decisions[1]
    backend = LayerBackend()

    analysis = analyze_decision_ev(
        request,
        EquityEngine(backend),
        RangeSource(_many_range_observations("open_shove", 1)),
        PopulationObservedRange(),
        PopulationActionModel(),
        140,
        None,
    )

    assert analysis.status == "incomplete"
    assert analysis.error_text == "the player's pocket cards are hidden"
    assert backend.calls == []


def test_weak_requires_even_the_upper_95_percent_ev_bound_to_be_negative() -> None:
    hand = _hand({"hero": 200, "villain": 200})
    decisions = [
        replace(
            _decision(hand.playerIds["villain"], hand_id=1_000, amount=190),
            role="open_shove",
            pot_before=35,
            blind_committed=10,
        ),
        replace(
            _decision(hand.playerIds["hero"], hand_id=1_000),
            pot_before=225,
        ),
    ]
    request = _request(hand, decisions, [101, 102]).decisions[1]

    analysis = analyze_decision_ev(
        request,
        EquityEngine(LayerBackend(heads_up=100)),
        RangeSource(_many_range_observations("open_shove", 1, count=500)),
        PopulationObservedRange(minimum_observations=25),
        PopulationActionModel(minimum_observations=25),
        140,
        None,
    )

    assert analysis.ev_chips == -135
    assert analysis.status == "weak"
    assert analysis.stderr_ppm is not None
    assert analysis.ev_bb_ppm + 1_960_000 * analysis.stderr_ppm // 1_000_000 < 0


def test_a_negative_point_estimate_is_uncertain_when_its_interval_crosses_zero() -> None:
    hand = _hand({"hero": 200, "villain": 200})
    decisions = [
        replace(
            _decision(hand.playerIds["villain"], hand_id=1_000, amount=190),
            role="open_shove",
            pot_before=35,
            blind_committed=10,
        ),
        replace(_decision(hand.playerIds["hero"], hand_id=1_000), pot_before=225),
    ]
    request = _request(hand, decisions, [101, 102]).decisions[1]

    analysis = analyze_decision_ev(
        request,
        EquityEngine(LayerBackend(heads_up=400)),
        RangeSource(_many_range_observations("open_shove", 1, count=25)),
        PopulationObservedRange(minimum_observations=25),
        PopulationActionModel(minimum_observations=25),
        140,
        None,
    )

    assert analysis.ev_chips == -15
    assert analysis.status == "uncertain"
    assert analysis.stderr_ppm is not None
    assert analysis.ev_bb_ppm + 1_960_000 * analysis.stderr_ppm // 1_000_000 > 0


def test_open_shove_ev_includes_the_all_fold_and_called_branches() -> None:
    hand = _hand({"hero": 200, "villain": 200})
    decisions = [
        replace(
            _decision(hand.playerIds["hero"], hand_id=2_000, amount=190),
            role="open_shove",
            pot_before=35,
            blind_committed=10,
        ),
        replace(
            _decision(hand.playerIds["villain"], hand_id=2_000, amount=0),
            decision="fold",
            role="call_shove",
            pot_before=225,
            blind_committed=25,
            cards_observable=False,
            hole_cards=None,
        ),
    ]
    request = _request(hand, decisions, [101, 102]).decisions[0]
    source = RangeSource(
        _many_range_observations("call_shove", 1, count=1_000),
        _many_action_observations("call_shove", 1, all_ins=250, folds=750),
    )

    analysis = analyze_decision_ev(
        request,
        EquityEngine(LayerBackend(heads_up=600)),
        source,
        PopulationObservedRange(minimum_observations=25),
        PopulationActionModel(minimum_observations=25),
        140,
        None,
    )

    # Jeffreys smoothing gives p(call)=250.5/1001.  The all-fold branch is
    # +35 cents; the called branch is 60% * 400 - 190 = +50 cents.
    assert analysis.ev_chips == 39
    assert analysis.status == "strong"
    assert source.action_calls == [(140, "aof_omaha", "call_shove", 1, 2_000, 5_000)]


def test_multiway_open_shove_builds_every_sequential_response_context() -> None:
    hand = _hand({"hero": 200, "villain": 200, "deep": 200})
    decisions = [
        replace(
            _decision(hand.playerIds["hero"], hand_id=2_000, amount=190),
            role="open_shove",
            active_opponents=2,
            pot_before=35,
            blind_committed=10,
        ),
        replace(
            _decision(hand.playerIds["villain"], hand_id=2_000, amount=0),
            decision="fold",
            role="call_shove",
            active_opponents=2,
            blind_committed=25,
            cards_observable=False,
            hole_cards=None,
        ),
        replace(
            _decision(hand.playerIds["deep"], hand_id=2_000, amount=0),
            decision="fold",
            role="call_shove",
            active_opponents=1,
            blind_committed=0,
            cards_observable=False,
            hole_cards=None,
        ),
    ]
    request = _request(hand, decisions, [101, 102, 103]).decisions[0]
    contexts = (
        ("call_shove", 2),
        ("call_shove", 1),
        ("overcall", 2),
    )
    source = RangeSource(
        [
            observation
            for role, opponents in contexts
            for observation in _many_range_observations(
                role,
                opponents,
                count=100,
                cards="Kc Kd 8c 8d" if role == "overcall" else "Ah Ad 7c 6c",
            )
        ],
        [
            observation
            for role, opponents in contexts
            for observation in _many_action_observations(role, opponents, all_ins=50, folds=50)
        ],
    )
    backend = LayerBackend(heads_up=600, multiway=400)

    analysis = analyze_decision_ev(
        request,
        EquityEngine(backend),
        source,
        PopulationObservedRange(minimum_observations=25),
        PopulationActionModel(minimum_observations=25),
        140,
        None,
    )

    assert analysis.status in {"weak", "strong", "uncertain"}
    assert {(call[2], call[3]) for call in source.action_calls} == set(contexts)
    assert {len(call["pockets"]) for call in backend.calls} == {2, 3}


def test_open_shove_stays_incomplete_when_one_action_context_is_too_small() -> None:
    hand = _hand({"hero": 200, "villain": 200})
    decisions = [
        replace(
            _decision(hand.playerIds["hero"], hand_id=2_000, amount=190),
            role="open_shove",
            pot_before=35,
            blind_committed=10,
        ),
        replace(
            _decision(hand.playerIds["villain"], hand_id=2_000, amount=0),
            decision="fold",
            cards_observable=False,
            hole_cards=None,
        ),
    ]
    request = _request(hand, decisions, [101, 102]).decisions[0]
    backend = LayerBackend()

    analysis = analyze_decision_ev(
        request,
        EquityEngine(backend),
        RangeSource(
            _many_range_observations("call_shove", 1),
            _many_action_observations("call_shove", 1, all_ins=1, folds=1),
        ),
        PopulationObservedRange(minimum_observations=25),
        PopulationActionModel(minimum_observations=25),
        140,
        None,
    )

    assert analysis.status == "incomplete"
    assert "action sample 2 is below 25" in str(analysis.error_text)
    assert backend.calls == []


def test_overcall_decision_ev_respects_hypothetical_side_pot_eligibility() -> None:
    hand = _hand({"short": 100, "villain": 200, "hero": 200})
    decisions = [
        replace(
            _decision(hand.playerIds["short"], hand_id=2_000, amount=100),
            role="open_shove",
            active_opponents=2,
            pot_before=35,
            blind_committed=0,
        ),
        replace(
            _decision(hand.playerIds["villain"], hand_id=2_000, amount=190),
            role="call_shove",
            active_opponents=2,
            pot_before=135,
            blind_committed=10,
        ),
        replace(
            _decision(hand.playerIds["hero"], hand_id=2_000),
            role="overcall",
            active_opponents=2,
            pot_before=325,
            blind_committed=25,
        ),
    ]
    request = _request(hand, decisions, [101, 102, 103]).decisions[2]
    source = RangeSource(
        [
            *_many_range_observations("open_shove", 2, cards="Ah Ad 7c 6c"),
            *_many_range_observations("call_shove", 2, cards="Kc Kd 8c 8d"),
        ],
    )
    backend = LayerBackend(heads_up=600, multiway=300)

    analysis = analyze_decision_ev(
        request,
        EquityEngine(backend),
        source,
        PopulationObservedRange(minimum_observations=25),
        PopulationActionModel(minimum_observations=25),
        140,
        None,
    )

    # Main pot: 30% * 300. Side pot: 60% * 200. Cost: 175.
    assert analysis.ev_chips == 35
    assert {len(call["pockets"]) for call in backend.calls} == {2, 3}


def test_the_real_capture_is_complete_because_both_pockets_were_shown() -> None:
    from test.test_aof_hud import _real_aof_hand

    hand = _real_aof_hand()
    hand.totalPot()
    hand.playerIds = {player[1]: seat for seat, player in enumerate(hand.players, start=1)}
    hand.dbid_hands = 41
    decisions = extract_decisions(hand)
    request = build_known_cards_hand_request(hand, decisions, [1, 2, 3])
    assert request is not None
    backend = LayerBackend()

    result = analyze_known_cards_hand(request, EquityEngine(backend))

    # Both shovers were turned face up at showdown, so every live pocket is
    # known and the equity is a fact rather than an estimate.
    assert [analysis.status for analysis in result.analyses] == ["complete", "complete"]
    # Nothing is missing any more, so nothing is reported missing.
    assert all(not analysis.error_text for analysis in result.analyses)
    # And the equity was actually computed rather than declined.
    assert backend.calls


def test_native_known_holdem_output_matches_poker_eval() -> None:
    backend = load_poker_eval()
    if backend is None:
        pytest.skip("optional pypoker-eval backend is not installed")
    hand = _hand(
        {"hero": 200, "villain": 200},
        cards={"hero": ("As", "Ah"), "villain": ("Ks", "Kh")},
    )
    hand.gametype = {"category": "aof_holdem", "bb": Decimal("0.25")}
    hand.board = {"FLOP": ["2c", "3d", "4h"], "TURN": ["5c"], "RIVER": ["6c"]}
    decision = _decision(hand.playerIds["hero"])
    decision = AofDecision(**{**decision.__dict__, "category": "aof_holdem"})

    (analysis,) = analyze_known_cards_hand(
        _request(hand, [decision], [101]),
        EquityEngine(backend),
    ).analyses

    assert analysis.status == "complete"
    assert analysis.equity_ppm == 912_000
    assert analysis.samples == 990


def test_native_known_omaha_output_matches_poker_eval() -> None:
    backend = load_poker_eval()
    if backend is None:
        pytest.skip("optional pypoker-eval backend is not installed")

    (analysis,) = analyze_known_cards_hand(
        _request(_hand({"hero": 200, "villain": 200})),
        EquityEngine(backend),
    ).analyses

    assert analysis.status == "complete"
    assert analysis.equity_ppm == 714_000
    assert analysis.ev_chips == 111
    assert analysis.samples == 820


def test_native_decision_ev_uses_the_observed_range_not_the_final_runout() -> None:
    backend = load_poker_eval()
    if backend is None:
        pytest.skip("optional pypoker-eval backend is not installed")
    hand = _hand({"hero": 200, "villain": 200})
    decisions = [
        replace(
            _decision(hand.playerIds["villain"], hand_id=1_000, amount=190),
            role="open_shove",
            pot_before=35,
            blind_committed=10,
        ),
        replace(
            _decision(hand.playerIds["hero"], hand_id=1_000),
            pot_before=225,
        ),
    ]
    request = _request(hand, decisions, [101, 102]).decisions[1]

    analysis = analyze_decision_ev(
        request,
        EquityEngine(backend),
        RangeSource(_many_range_observations("open_shove", 1, count=100)),
        PopulationObservedRange(minimum_observations=25),
        PopulationActionModel(minimum_observations=25),
        140,
        None,
    )

    assert analysis.status == "strong"
    assert analysis.ev_chips == 109
    assert analysis.ev_bb_ppm == 4_376_000
    assert analysis.samples == 100


class RecordingDatabase:
    def __init__(self, stored: list) -> None:
        self.stored = stored
        self.committed = False
        self.closed = False

    def storeAofDecisionAnalyses(self, analyses, doinsert: bool = False) -> None:
        assert doinsert
        self.stored.append(tuple(analyses))

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        raise AssertionError("the successful analysis must not roll back")

    def close_connection(self) -> None:
        self.closed = True


def test_the_worker_persists_one_hand_transaction_and_notifies_once() -> None:
    stored = []
    databases = []
    notified = Event()

    def database() -> RecordingDatabase:
        db = RecordingDatabase(stored)
        databases.append(db)
        return db

    service = AsyncEquityService(EquityEngine(LayerBackend(heads_up=500)))
    coordinator = KnownCardsAnalysisCoordinator(
        service,
        database,
        notify_hand=lambda hand_id: notified.set() if hand_id == 9 else None,
    )
    hand = _hand({"hero": 200, "villain": 200})
    decisions = [_decision(1), _decision(2)]
    try:
        assert coordinator.submit_hand(hand, decisions, [101, 102]) is EquitySubmission.QUEUED
        assert notified.wait(2)
    finally:
        coordinator.close()

    assert len(databases) == 1
    assert databases[0].committed and databases[0].closed
    assert len(stored) == 1
    assert [analysis.decision_id for analysis in stored[0]] == [101, 102]


class RangeReadDatabase(RangeSource):
    def __init__(
        self,
        observations: list[RangeObservation],
        actions: list[ActionObservation] | None = None,
    ) -> None:
        super().__init__(observations, actions)
        self.rolled_back = False
        self.closed = False

    def rollback(self) -> None:
        self.rolled_back = True

    def close_connection(self) -> None:
        self.closed = True


def test_known_range_and_decision_ev_share_one_job_one_write_and_one_notification() -> None:
    stored = []
    read_db = RangeReadDatabase(
        _range_observations(),
        _many_action_observations("call_shove", 1, all_ins=1, folds=1),
    )
    write_db = RecordingDatabase(stored)
    databases = iter((read_db, write_db))
    notifications = []
    notified = Event()
    service = AsyncEquityService(EquityEngine(LayerBackend(heads_up=600)))
    coordinator = KnownCardsAnalysisCoordinator(
        service,
        lambda: next(databases),
        notify_hand=lambda hand_id: (notifications.append(hand_id), notified.set()),
        population_model=PopulationObservedRange(minimum_observations=2),
        action_model=PopulationActionModel(minimum_observations=2),
    )
    hand = _hand({"hero": 200, "villain": 200})
    decisions = [
        replace(
            _decision(hand.playerIds["villain"], hand_id=9, amount=190),
            role="open_shove",
            pot_before=35,
            blind_committed=10,
        ),
        replace(
            _decision(hand.playerIds["hero"], hand_id=9),
            role="call_shove",
            pot_before=225,
            blind_committed=25,
        ),
    ]
    try:
        assert coordinator.submit_hand(hand, decisions, [101, 102]) is EquitySubmission.QUEUED
        assert notified.wait(2)
    finally:
        coordinator.close()

    assert read_db.rolled_back and read_db.closed
    assert write_db.committed and write_db.closed
    assert len(stored) == 1
    assert [analysis.range_model for analysis in stored[0]] == [
        "actual_known",
        "actual_known",
        "population_observed",
        "population_observed",
        "population_decision_ev_prerake",
        "population_decision_ev_prerake",
    ]
    assert notifications == [9]
