"""The receiving half of the live-action wiring (#336).

The capture publishes each action as it is played; these tests cover what
happens on the HUD's side of that socket -- telling a live payload from a bare
hand id, routing it to the HUD whose table it names, and surviving both a bad
packet and a HUD that refuses it. The format the two halves share is asserted
end to end here, because it is the one thing neither process can check alone.

Deliberately free of Qt: everything under test is a module function or a method
that touches nothing but two dicts, so these run in the default suite rather
than behind the ``qt`` marker.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from fpdb_3_legacy import hud_live_context as live
from fpdb_3_legacy.Importer import LIVE_ACTION_PREFIX, ZMQSender


def _load_hud_main():
    """HUD_main is a ``.pyw``, so it is loaded by path, as test_HUD_main does."""
    if "HUD_main" in sys.modules:
        return sys.modules["HUD_main"]
    source_file = Path(__file__).parent.parent / "fpdb_3_legacy" / "HUD_main.pyw"
    win_tables = types.ModuleType("WinTables")
    win_tables.Table = MagicMock()
    sys.modules.setdefault("WinTables", win_tables)
    loader = importlib.machinery.SourceFileLoader("HUD_main", str(source_file))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules["HUD_main"] = module
    try:
        loader.exec_module(module)
    except (ImportError, ModuleNotFoundError) as exc:  # pragma: no cover - env-dependent
        del sys.modules["HUD_main"]
        pytest.skip(f"HUD_main could not be loaded: {exc}", allow_module_level=True)
    return module


HUD_main = _load_hud_main()


def _payload(**overrides) -> dict:
    payload = {
        "table": "914265",
        "hand_id": "91426500343",
        "sequence": 4,
        "record": {"username": "P1", "action": "RAISE", "roundName": "preflop", "actionAmount": "6"},
    }
    payload.update(overrides)
    return payload


def _hud_main():
    """A HudMain with only the two dicts the live routing reads."""
    main = HUD_main.HudMain.__new__(HUD_main.HudMain)
    main._live_tables = {}
    main.hud_dict = {}
    return main


# --- telling the two kinds of message apart ----------------------------------


def test_a_bare_hand_id_is_not_read_as_a_live_action() -> None:
    # Both travel on one socket; the prefix is the only thing separating them.
    assert HUD_main.parse_live_message("91426500343") is None


def test_a_prefixed_message_parses_into_its_payload() -> None:
    payload = _payload()
    assert HUD_main.parse_live_message(LIVE_ACTION_PREFIX + json.dumps(payload)) == payload


def test_a_malformed_live_message_is_dropped_rather_than_raised() -> None:
    # One bad packet must not take the receiver thread down with it.
    assert HUD_main.parse_live_message(LIVE_ACTION_PREFIX + "{not json") is None
    assert HUD_main.parse_live_message(LIVE_ACTION_PREFIX + "[1, 2]") is None  # JSON, but no payload


def test_the_capture_and_the_receiver_agree_on_the_wire_format() -> None:
    """What the capture sends is what the HUD reads back.

    The halves live in different processes and different modules, so this is
    the only place their shared format is checked end to end.
    """
    sent: list[str] = []
    sender = SimpleNamespace(socket=SimpleNamespace(send_string=lambda message, _flag: sent.append(message)))

    ZMQSender.send_live_action(sender, _payload())

    assert sent, "the sender published nothing"
    assert HUD_main.parse_live_message(sent[0]) == _payload()


def test_a_send_that_fails_costs_the_action_and_nothing_else() -> None:
    # Actions arrive many per hand and the capture never stops for them: a
    # failing socket drops the action, it does not raise into the import loop.
    def _explode(_message, _flag) -> None:
        msg = "the HUD went away"
        raise TypeError(msg)

    sender = SimpleNamespace(socket=SimpleNamespace(send_string=_explode))

    ZMQSender.send_live_action(sender, _payload())  # must not raise


# --- routing to the right HUD ------------------------------------------------


def test_a_live_action_routes_to_the_hud_serving_its_table() -> None:
    hud = object()
    assert HUD_main.route_live_action(_payload(), {"914265": "key"}, {"key": hud}) is hud


def test_a_live_action_for_a_table_with_no_hud_is_dropped() -> None:
    # Before a table's first hand is imported there is no HUD to route to, and
    # the panels fall back to the hand-refresh path rather than guess a table.
    hud = object()
    assert HUD_main.route_live_action(_payload(), {}, {"key": hud}) is None
    assert HUD_main.route_live_action(_payload(table=""), {"914265": "key"}, {"key": hud}) is None


def test_a_table_is_remembered_by_the_id_the_capture_names_it_by() -> None:
    """A cash table is its own number; a tournament's is the title's last token."""
    main = _hud_main()

    main._remember_live_table("cash_key", "914265")
    main._remember_live_table("tour_key", "Twister 0.25 1200531183")

    assert main._live_tables == {"914265": "cash_key", "1200531183": "tour_key"}


def test_a_nameless_window_teaches_the_routing_nothing() -> None:
    main = _hud_main()

    main._remember_live_table("key", "   ")
    main._remember_live_table("key", None)

    assert main._live_tables == {}


def test_a_routed_action_reaches_the_hud_as_a_live_action() -> None:
    seen: list[tuple] = []

    class _Hud:
        def accept_live_action(self, action, hand_id=""):
            seen.append((action, hand_id))

    main = _hud_main()
    main._live_tables = {"914265": "key"}
    main.hud_dict = {"key": _Hud()}

    main.handle_live_action(_payload())

    assert len(seen) == 1
    action, hand_id = seen[0]
    assert isinstance(action, live.LiveAction)
    assert (action.actor, action.action, action.sequence, hand_id) == ("P1", "raises", 4, "91426500343")


def test_a_hud_that_refuses_an_action_never_breaks_the_loop() -> None:
    # A closed table or a half-built panel can raise; losing the live update is
    # a degradation, losing the HUD's message loop is not acceptable.
    class _Angry:
        def accept_live_action(self, action, hand_id=""):
            msg = "this HUD is gone"
            raise RuntimeError(msg)

    main = _hud_main()
    main._live_tables = {"914265": "key"}
    main.hud_dict = {"key": _Angry()}

    main.handle_live_action(_payload())  # must not raise


def test_a_payload_without_a_record_is_dropped_before_the_hud() -> None:
    seen: list[tuple] = []

    class _Hud:
        def accept_live_action(self, action, hand_id=""):
            seen.append((action, hand_id))

    main = _hud_main()
    main._live_tables = {"914265": "key"}
    main.hud_dict = {"key": _Hud()}

    main.handle_live_action(_payload(record=None))

    assert seen == []


# --- the live stream and the import path meeting at a hand boundary ----------


def _hud_following(hand_id: str):
    """A bare HUD whose live session is already following ``hand_id``."""
    from fpdb_3_legacy.Hud import Hud

    hud = Hud.__new__(Hud)
    hud.live_state = {}
    hud.aux_windows = []
    hud.cards = {}
    hud.db_hud_connection = None
    hud.hand_instance = None
    session = hud.live_context_session()
    session.start_hand(hand_id)
    return hud, session


def test_an_import_of_the_hand_being_played_leaves_the_live_context_alone() -> None:
    hud, session = _hud_following("91426500343")
    session.update(live.LiveAction(actor="P1", action="raises", to_cents=600, hand_id="91426500343", sequence=1))

    hud.update(91426500343, config=None, prepared=True, hand_instance=None)

    assert session.adapter.hand_id == "91426500343"
    assert session.adapter.context.raise_level == 1  # the live pot survived its own import


def test_winamax_import_compares_site_hand_id_not_database_row_id(monkeypatch) -> None:
    from types import SimpleNamespace

    from fpdb_3_legacy import hud_situation

    site_hand_id = "91426500343"
    hud, session = _hud_following(site_hand_id)
    hud._winamax_live_hand_id = site_hand_id
    hud.hand_instance = SimpleNamespace(handid=site_hand_id)
    monkeypatch.setattr(
        hud_situation,
        "live_state_from_hand",
        lambda hand: {"source": "assembled_import"},
    )

    # Hud.update receives a DB row id, not the site's hand id.
    hud._update_live_state_from_import(771)

    assert hud.live_state == {"source": "assembled_import"}
    assert session.adapter.hand_id == site_hand_id
    assert session.adapter.context.raise_level == 0


def test_an_import_of_a_finished_hand_does_not_restart_it() -> None:
    """The live stream runs ahead of the import, so a late notification arrives.

    Actions are published before the hand is even built, so the table can
    already be playing the next hand when the finished one is imported. Starting
    it again would show the panels a pot nobody is in.
    """
    hud, session = _hud_following("91426500343")
    session.update(live.LiveAction(actor="P1", action="raises", to_cents=600, hand_id="91426500344", sequence=2))
    assert session.adapter.hand_id == "91426500344"  # the table moved on

    hud.update(91426500343, config=None, prepared=True, hand_instance=None)

    assert session.adapter.hand_id == "91426500344"
    assert session.adapter.context.raise_level == 1


def test_an_import_of_a_hand_the_stream_has_not_seen_starts_it() -> None:
    # With no live feed behind it this is the only thing that sets the hand, so
    # the guard must not cost the classic path its reset.
    hud, session = _hud_following("91426500343")

    hud.update(91426500399, config=None, prepared=True, hand_instance=None)

    assert session.adapter.hand_id == "91426500399"
