"""The switch that keeps a process from notifying a running HUD.

A HUD looks every id it receives up in its own database. The suite imports into
throwaway databases whose ids start at 1, and those ids, pushed to a HUD left
running, named months-old hands of tables long closed: it froze searching for
their windows. These tests open no real socket to the HUD port.
"""

from __future__ import annotations

import os
from unittest.mock import Mock

import pytest

from fpdb_3_legacy import Importer as ImporterModule
from fpdb_3_legacy.Importer import HUD_NOTIFY_ENV, ZMQSender


def test_the_suite_runs_with_hud_notifications_off() -> None:
    assert os.environ.get(HUD_NOTIFY_ENV) == "0"


def test_a_disabled_sender_connects_to_nothing_and_sends_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(HUD_NOTIFY_ENV, "0")
    context = Mock()
    monkeypatch.setattr(ImporterModule.zmq, "Context", Mock(return_value=context))

    sender = ZMQSender()
    sender.send_hand_id(1)
    sender.send_live_action({"hand_id": 1})
    sender.close()

    context.socket.assert_not_called()


def test_an_enabled_sender_still_connects_to_the_hud(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(HUD_NOTIFY_ENV, raising=False)
    socket = Mock()
    context = Mock()
    context.socket.return_value = socket
    monkeypatch.setattr(ImporterModule.zmq, "Context", Mock(return_value=context))

    sender = ZMQSender()
    sender.send_hand_id(7)

    socket.connect.assert_called_once_with("tcp://127.0.0.1:5555")
    socket.send_string.assert_called_once()
    assert socket.send_string.call_args[0][0] == "7"
