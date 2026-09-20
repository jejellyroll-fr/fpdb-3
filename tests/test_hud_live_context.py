"""Action-by-action live context for the dynamic panels (#336).

These tests assert the *sequence* of contexts and panel selections across the
scenarios the issue names, because a live feed's whole value is that the panels
move at the decision rather than one hand later. Duplicates, out-of-order
events, hand boundaries and the room-specific adapter are covered too.
"""

from __future__ import annotations

from dataclasses import replace

from fpdb_3_legacy import hud_live_context as live
from fpdb_3_legacy import hud_situation as hs


def _action(actor, action, *, street="preflop", amount=0, to=None, all_in=False, seq=0, hand="h1"):
    return live.LiveAction(
        actor=actor,
        action=action,
        street=street,
        amount_cents=amount,
        to_cents=to,
        all_in=all_in,
        hand_id=hand,
        sequence=seq,
    )


def _adapter(**overrides):
    facts = {"site": "PokerStars", "game": "holdem", "limit": "nl", "seats": 6}
    facts.update(overrides)
    adapter = live.ActionStreamAdapter(**facts)
    adapter.reset("h1", seats=["P1", "P2", "P3"])
    return adapter


def _panels(context, resolver, **seat):
    return resolver.resolve(replace(context.to_situation(), **seat)).panels


# ---------------------------------------------------------------------------
# The contract
# ---------------------------------------------------------------------------


class TestContract:
    def test_the_source_sentence_is_honest(self) -> None:
        assert "Live context available" in live.describe_source(live.SOURCE_ACTION_STREAM)
        assert "Hand-refresh" in live.describe_source(live.SOURCE_HAND_REFRESH)
        assert live.is_action_live(live.SOURCE_ACTION_STREAM)
        assert not live.is_action_live(live.SOURCE_HAND_REFRESH)

    def test_only_stated_facts_are_published(self) -> None:
        state = live.context_to_live_state(live.LiveContext(street="flop", street_index=1, players_in_hand=2))
        assert state["street"] == "flop"
        assert state["players_in_hand"] == 2
        assert state["multiway"] is False
        # Nothing the feed did not state is invented.
        assert "site" not in state
        assert "pot_type" not in state
        assert "effective_stack_bb" not in state

    def test_a_stated_ring_game_is_published(self) -> None:
        """``tournament=False`` is a fact, not an absent one."""
        state = live.context_to_live_state(live.LiveContext(street="preflop", tournament=False))
        assert state["tournament"] is False
        # A numeric zero is still absence.
        assert "seats" not in live.context_to_live_state(live.LiveContext(seats=0))

    def test_a_context_projects_onto_the_canonical_model(self) -> None:
        context = live.LiveContext(street="turn", street_index=2, pot_type="three_bet", players_in_hand=4)
        situation = context.to_situation()
        assert isinstance(situation, hs.HudSituationContext)
        assert (situation.street, situation.pot_type, situation.multiway) == ("turn", "three_bet", True)

    def test_describe_names_the_decision_and_the_unknowns(self) -> None:
        context = live.LiveContext(street="flop", pot_type="single_raised", unknown=("board",))
        text = context.describe()
        assert "street=flop" in text
        assert "pot=single_raised" in text
        assert "unknown=board" in text


# ---------------------------------------------------------------------------
# Folding a hand, in the order the issue lists
# ---------------------------------------------------------------------------


class TestFolding:
    def test_unopened_then_open_then_facing_open(self) -> None:
        adapter = _adapter()
        assert adapter.context.pot_type == "unopened"
        adapter.apply(_action("P1", "raises", to=600, seq=1))
        assert adapter.context.pot_type == "single_raised"
        assert adapter.context.preflop_aggressor == "P1"
        adapter.apply(_action("P2", "folds", seq=2))
        assert adapter.context.players_in_hand == 2

    def test_open_then_three_bet_then_facing_three_bet(self) -> None:
        adapter = _adapter()
        adapter.apply(_action("P1", "raises", to=600, seq=1))
        adapter.apply(_action("P2", "raises", to=2000, seq=2))
        assert adapter.context.pot_type == "three_bet"
        assert adapter.context.raise_level == 2
        assert adapter.context.aggressor == "P2"

    def test_open_with_a_call_is_single_raised(self) -> None:
        adapter = _adapter()
        adapter.apply(_action("P1", "raises", to=600, seq=1))
        adapter.apply(_action("P2", "calls", amount=600, seq=2))
        assert adapter.context.pot_type == "single_raised"

    def test_limped_pot(self) -> None:
        adapter = _adapter()
        adapter.apply(_action("P1", "calls", amount=200, seq=1))
        adapter.apply(_action("P2", "calls", amount=200, seq=2))
        assert adapter.context.pot_type == "limped"

    def test_a_four_bet_is_four_bet_plus(self) -> None:
        adapter = _adapter()
        adapter.apply(_action("P1", "raises", to=600, seq=1))
        adapter.apply(_action("P2", "raises", to=2000, seq=2))
        adapter.apply(_action("P1", "raises", to=5000, seq=3))
        assert adapter.context.pot_type == "four_bet_plus"

    def test_a_street_transition_keeps_the_pot_shape_and_clears_the_street(self) -> None:
        adapter = _adapter()
        adapter.apply(_action("P1", "raises", to=600, seq=1))
        adapter.apply(_action("P2", "calls", amount=600, seq=2))
        assert adapter.context.pot_type == "single_raised"
        adapter.apply(_action("P2", "checks", street="flop", seq=3))
        assert adapter.context.street == "flop"
        assert adapter.context.street_index == 1
        assert adapter.context.pot_type == "single_raised"
        assert adapter.context.last_aggressive_action == ""

    def test_a_street_never_goes_backwards(self) -> None:
        adapter = _adapter()
        adapter.apply(_action("P2", "checks", street="flop", seq=1))
        adapter.apply(_action("P1", "calls", street="preflop", amount=200, seq=2))
        assert adapter.context.street == "flop"

    def test_a_limped_pot_stays_limped_on_the_flop(self) -> None:
        """The preflop shape carries: a limped pot is limped postflop."""
        adapter = _adapter()
        adapter.apply(_action("P1", "calls", amount=200, seq=1))
        adapter.apply(_action("P2", "checks", street="flop", seq=2))
        assert adapter.context.street == "flop"
        assert adapter.context.pot_type == "limped"

    def test_a_fold_leaves_the_actionable_context(self) -> None:
        adapter = _adapter()
        adapter.apply(_action("P3", "folds", seq=1))
        assert adapter.context.players_in_hand == 2

    def test_an_all_in_is_recorded(self) -> None:
        adapter = _adapter()
        adapter.apply(_action("P1", "raises", to=10000, all_in=True, seq=1))
        assert adapter.context.all_in_seats == ("P1",)

    def test_sizing_faced_is_the_amount_to_call(self) -> None:
        adapter = _adapter()
        adapter.apply(_action("P1", "raises", to=600, seq=1))
        adapter.apply(_action("P2", "calls", amount=600, seq=2))
        adapter.apply(_action("P3", "calls", amount=600, seq=3))
        adapter.apply(_action("P1", "bets", street="flop", amount=900, seq=4))
        assert adapter.context.to_call_cents == 900


# ---------------------------------------------------------------------------
# Idempotence and hand boundaries
# ---------------------------------------------------------------------------


class TestLifecycle:
    def test_a_duplicate_event_is_ignored(self) -> None:
        adapter = _adapter()
        first = adapter.apply(_action("P1", "raises", to=600, seq=1))
        assert first is not None
        assert adapter.apply(_action("P1", "raises", to=600, seq=1)) is None
        assert adapter.context.raise_level == 1

    def test_an_out_of_order_event_is_ignored(self) -> None:
        adapter = _adapter()
        adapter.apply(_action("P1", "raises", to=600, seq=5))
        assert adapter.apply(_action("P2", "raises", to=2000, seq=2)) is None
        assert adapter.context.pot_type == "single_raised"

    def test_an_action_for_another_hand_is_refused(self) -> None:
        adapter = _adapter()
        adapter.apply(_action("P1", "raises", to=600, seq=1, hand="h1"))
        assert adapter.apply(_action("P2", "raises", to=2000, seq=2, hand="h2")) is None
        assert adapter.context.pot_type == "single_raised"

    def test_a_new_hand_resets_everything(self) -> None:
        adapter = _adapter()
        adapter.apply(_action("P1", "raises", to=600, seq=1))
        adapter.apply(_action("P2", "raises", to=2000, seq=2))
        adapter.reset("h2", seats=["P1", "P2", "P3"])
        assert adapter.context.pot_type == "unopened"
        assert adapter.context.hand_id == "h2"
        assert adapter.context.players_in_hand == 3

    def test_an_empty_actor_is_ignored(self) -> None:
        adapter = _adapter()
        assert adapter.apply(_action("", "raises", to=600, seq=1)) is None


# ---------------------------------------------------------------------------
# The sequence of panel selections
# ---------------------------------------------------------------------------


class TestPanelSequence:
    def test_single_raised_pot_flop_cbet_and_defence(self) -> None:
        """SRP flop -> c-bet -> defender facing c-bet, seat by seat."""
        resolver = hs.load_default_resolver()
        adapter = _adapter()
        adapter.apply(_action("P1", "raises", to=600, seq=1))
        adapter.apply(_action("P2", "calls", amount=600, seq=2))
        adapter.apply(_action("P2", "checks", street="flop", seq=3))
        assert "srp_cbet_ip" in _panels(
            adapter.context, resolver, position="BTN", in_position=True, is_preflop_aggressor=True
        )
        adapter.apply(_action("P1", "bets", street="flop", amount=900, seq=4))
        facing = _panels(
            adapter.context,
            resolver,
            position="BB",
            in_position=False,
            is_preflop_aggressor=False,
            facing_action="bets",
        )
        assert "srp_face_cbet_oop" in facing

    def test_probe_opportunity_after_a_checked_through_flop(self) -> None:
        resolver = hs.load_default_resolver()
        adapter = _adapter()
        adapter.apply(_action("P1", "raises", to=600, seq=1))
        adapter.apply(_action("P2", "calls", amount=600, seq=2))
        adapter.apply(_action("P2", "checks", street="flop", seq=3))
        adapter.apply(_action("P1", "checks", street="flop", seq=4))
        adapter.apply(_action("P2", "checks", street="turn", seq=5))
        probe = _panels(
            adapter.context,
            resolver,
            position="BB",
            in_position=True,
            is_preflop_aggressor=False,
            to_call=0,
        )
        assert "srp_probe_ip" in probe

    def test_a_three_bet_pot_carries_the_shape_to_the_flop(self) -> None:
        resolver = hs.load_default_resolver()
        adapter = _adapter()
        adapter.apply(_action("P1", "raises", to=600, seq=1))
        adapter.apply(_action("P2", "raises", to=2000, seq=2))
        adapter.apply(_action("P1", "calls", amount=2000, seq=3))
        adapter.apply(_action("P2", "checks", street="flop", seq=4))
        assert "threebet_pot_oop" in _panels(
            adapter.context, resolver, position="BB", in_position=False, is_preflop_aggressor=True
        )

    def test_unopened_preflop_is_the_open_panel(self) -> None:
        resolver = hs.load_default_resolver()
        adapter = _adapter()
        panels = _panels(adapter.context, resolver, position="BTN", in_position=True)
        assert "preflop_open" in panels
        adapter.apply(_action("P1", "raises", to=600, seq=1))
        # The shipped rule for a blind facing a raise is the defence panel; the
        # point here is that the live context moved the seat off ``preflop_open``
        # at the raise, not one hand later.
        facing = _panels(adapter.context, resolver, position="BB", in_position=False, facing_action="raises")
        assert "blinds_defence" in facing
        assert "preflop_open" not in facing


# ---------------------------------------------------------------------------
# Observability
# ---------------------------------------------------------------------------


class TestObservability:
    def test_a_trace_names_what_changed_and_what_is_unknown(self) -> None:
        adapter = _adapter(seats=0, site="", game="")
        before = adapter.context
        after = adapter.apply(_action("P1", "raises", to=600, seq=1))
        assert after is not None
        trace = live.trace_update(_action("P1", "raises", to=600, seq=1), before, after)
        assert "pot_type" in trace.changed
        assert "seats" in trace.unknown
        assert "live P1:raises" in trace.describe()

    def test_a_panel_change_is_reported(self) -> None:
        trace = live.LiveTrace(
            action="P1:raises",
            context_key="street=preflop",
            changed=("street",),
            unknown=(),
            panels_before=("core",),
            panels_after=("core", "preflop_facing_open"),
        )
        assert trace.panel_change == ("preflop_facing_open",)


# ---------------------------------------------------------------------------
# The session: publishing into the HUD through the existing hook
# ---------------------------------------------------------------------------


class _FakeHud:
    def __init__(self):
        self.live_state = {}
        self.calls = []

    def set_live_state(self, **state):
        self.calls.append(state)
        for key, value in state.items():
            if value is None:
                self.live_state.pop(key, None)
            else:
                self.live_state[key] = value


class TestSession:
    def test_updates_publish_into_the_hud(self) -> None:
        hud = _FakeHud()
        session = live.LiveContextSession(hud)
        session.start_hand("h1", seats=["P1", "P2"])
        trace = session.update(_action("P1", "raises", to=600, seq=1))
        assert trace is not None
        assert hud.live_state["pot_type"] == "single_raised"
        assert session.source_note.startswith("Live context available")

    def test_a_duplicate_costs_nothing_and_is_counted(self) -> None:
        session = live.LiveContextSession(_FakeHud())
        session.start_hand("h1")
        session.update(_action("P1", "raises", to=600, seq=1))
        assert session.update(_action("P1", "raises", to=600, seq=1)) is None
        assert session.ignored == 1
        assert session.updates == 1

    def test_closing_clears_what_it_published(self) -> None:
        hud = _FakeHud()
        session = live.LiveContextSession(hud)
        session.start_hand("h1")
        session.update(_action("P1", "raises", to=600, seq=1))
        session.close()
        assert "pot_type" not in hud.live_state
        assert session.last_context is None

    def test_a_session_without_a_hud_is_safe(self) -> None:
        session = live.LiveContextSession()
        session.start_hand("h1")
        assert session.update(_action("P1", "raises", to=600, seq=1)) is not None


# ---------------------------------------------------------------------------
# The room adapter: CoinPoker's own action stream
# ---------------------------------------------------------------------------


class TestCoinPokerAdapter:
    def test_a_raise_reads_its_raise_to_total(self) -> None:
        action = live.coinpoker_action(
            {"username": "Ann", "action": "RAISE", "newPlayerAction": "BET", "actionAmount": 600, "roundName": "PREFLOP"}
        )
        assert action is not None
        assert (action.actor, action.action, action.to_cents) == ("Ann", "bets", 600)

    def test_a_fold_and_a_check_carry_no_money(self) -> None:
        fold = live.coinpoker_action({"username": "Ann", "action": "FOLD", "roundName": "FLOP"})
        assert fold is not None and fold.action == "folds" and fold.amount_cents == 0
        check = live.coinpoker_action({"username": "Bob", "action": "CHECK", "roundName": "FLOP"})
        assert check is not None and check.action == "checks"

    def test_an_all_in_is_marked(self) -> None:
        action = live.coinpoker_action(
            {
                "username": "Ann",
                "action": "ALLIN",
                "newPlayerAction": "ALLIN",
                "actionAmount": 10000,
                "roundName": "PREFLOP",
            }
        )
        assert action is not None and action.all_in

    def test_a_record_without_a_player_is_refused(self) -> None:
        assert live.coinpoker_action({"action": "FOLD"}) is None

    def test_two_actions_in_the_same_millisecond_are_both_kept(self) -> None:
        """Distinct actions must not share a sequence and be dropped as duplicates."""
        events = [
            (
                "game.dealer_chat_action",
                "h1",
                {
                    "gameActionMessagesHistory": [
                        {"username": "Ann", "action": "RAISE", "actionAmount": 600, "roundName": "PREFLOP", "initTimestamp": 1},
                        {"username": "Bob", "action": "FOLD", "roundName": "PREFLOP", "initTimestamp": 1},
                    ]
                },
            )
        ]
        actions = list(live.coinpoker_actions(events, hand_id="h1"))
        assert [action.actor for action in actions] == ["Ann", "Bob"]
        assert len({action.sequence for action in actions}) == 2

    def test_a_repeated_record_is_dropped(self) -> None:
        record = {"username": "Ann", "action": "FOLD", "roundName": "FLOP", "initTimestamp": 7}
        events = [("game.dealer_chat_action", "h1", {"gameActionMessagesHistory": [record, dict(record)]})]
        assert len(list(live.coinpoker_actions(events, hand_id="h1"))) == 1

    def test_a_capture_stream_becomes_actions_in_order(self) -> None:
        events = [
            ("game.dealer_chat_action", "h1", {}),
            (
                "game.dealer_chat_action",
                "h1",
                {
                    "gameActionMessagesHistory": [
                        {"username": "Ann", "action": "RAISE", "actionAmount": 600, "roundName": "PREFLOP"},
                        {"username": "Bob", "action": "CALL", "actionAmount": 600, "roundName": "PREFLOP"},
                        {"username": "Cara", "action": "FOLD", "roundName": "PREFLOP"},
                    ]
                },
            ),
        ]
        actions = list(live.coinpoker_actions(events, hand_id="h1"))
        assert [action.actor for action in actions] == ["Ann", "Bob", "Cara"]
        # ``RAISE`` with no ``newPlayerAction`` adapts as a raise; folding it
        # into the adapter's state is what decides it was an opening bet.
        assert [action.action for action in actions] == ["raises", "calls", "folds"]

    def test_the_builder_shape_is_adapted_too(self) -> None:
        rows = [
            {"type": "raises", "player": "Ann", "street": "PREFLOP", "to": "600"},
            {"type": "folds", "player": "Bob", "street": "PREFLOP"},
        ]
        actions = list(live.actions_from_normalized(rows, hand_id="h1"))
        assert actions[0].action == "raises"
        assert actions[0].to_cents == 600
        assert actions[0].street == "PREFLOP"
        # Sequenced from 1, so a replay of the same rows is idempotent.
        assert [action.sequence for action in actions] == [1, 2]
        adapter = _adapter()
        for action in live.actions_from_normalized(rows, hand_id="h1"):
            adapter.apply(action)
        assert [adapter.apply(action) for action in live.actions_from_normalized(rows, hand_id="h1")] == [None, None]
        assert adapter.context.pot_type == "single_raised"

    def test_a_coinpoker_stream_drives_the_panels(self) -> None:
        resolver = hs.load_default_resolver()
        adapter = _adapter()
        events = [
            (
                "game.dealer_chat_action",
                "h1",
                {
                    "gameActionMessagesHistory": [
                        {"username": "P1", "action": "RAISE", "actionAmount": 600, "roundName": "PREFLOP"},
                        {"username": "P2", "action": "CALL", "actionAmount": 600, "roundName": "PREFLOP"},
                    ]
                },
            )
        ]
        for action in live.coinpoker_actions(events, hand_id="h1"):
            adapter.apply(action)
        assert adapter.context.pot_type == "single_raised"
        assert "srp_cbet_ip" in _panels(
            adapter.context, resolver, position="BTN", in_position=True, is_preflop_aggressor=True
        )


# ---------------------------------------------------------------------------
# Fallback: a live feed that stays quiet is not an invented fact
# ---------------------------------------------------------------------------


class TestFallback:
    def test_unknown_stays_unknown_and_is_not_a_value(self) -> None:
        adapter = _adapter(seats=0)
        state = live.context_to_live_state(adapter.context)
        assert "seats" not in state
        assert "seats" in adapter.context.unknown

    def test_a_bare_context_resolves_to_the_fallback_panel(self) -> None:
        resolver = hs.load_default_resolver()
        selection = resolver.resolve(live.LiveContext().to_situation())
        assert selection.panels  # the fallback still draws something

    def test_the_classic_path_is_untouched_when_dynamic_panels_are_off(self) -> None:
        """A resolver with no rules is disabled, exactly as before #336."""
        off = hs.HudSituationResolver([], fallback="core")
        selection = off.resolve(live.LiveContext(street="flop").to_situation())
        assert not selection.enabled
