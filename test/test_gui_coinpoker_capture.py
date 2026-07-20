"""Lifecycle regression tests for the CoinPoker capture GUI."""

from __future__ import annotations

import signal
from types import SimpleNamespace
from unittest.mock import Mock

from fpdb_3_legacy.GuiCoinPokerCapture import GuiCoinPokerCapture


def _widget(qtbot, monkeypatch):
    monkeypatch.setattr(GuiCoinPokerCapture, "_populate_ifaces", lambda self: None)
    widget = GuiCoinPokerCapture(SimpleNamespace(file=None))
    qtbot.addWidget(widget)
    return widget


def test_start_rejects_existing_capture_before_launching_helpers(qtbot, monkeypatch) -> None:
    widget = _widget(qtbot, monkeypatch)
    launch = Mock()
    monkeypatch.setattr(widget, "_launch_elevated", launch)
    monkeypatch.setattr(
        "fpdb_3_legacy.coinpoker_live_capture._acquire_instance_lock",
        Mock(side_effect=RuntimeError("another CoinPoker live capture is already running (PID 123)")),
    )

    widget._start()

    launch.assert_not_called()
    assert "PID 123" in widget.status.text()
    assert widget.start_button.isEnabled()


def test_start_recovers_stopped_orphaned_macos_reader(qtbot, monkeypatch, tmp_path) -> None:
    widget = _widget(qtbot, monkeypatch)
    widget.stop_file = tmp_path / "capture.stop"
    widget.stop_file.write_text("stop")
    kill = Mock()
    retry = Mock()
    monkeypatch.setattr("fpdb_3_legacy.GuiCoinPokerCapture.platform.system", lambda: "Darwin")
    monkeypatch.setattr("fpdb_3_legacy.GuiCoinPokerCapture.os.kill", kill)
    monkeypatch.setattr("fpdb_3_legacy.GuiCoinPokerCapture.QTimer.singleShot", retry)
    monkeypatch.setattr("pathlib.Path.read_text", lambda self: "5869")
    monkeypatch.setattr(
        "fpdb_3_legacy.coinpoker_live_capture._acquire_instance_lock",
        Mock(side_effect=RuntimeError("another CoinPoker live capture is already running (PID 5869)")),
    )

    widget._start()

    kill.assert_called_once_with(5869, signal.SIGTERM)
    retry.assert_called_once_with(500, widget._start)
    assert widget.status.text() == "Finishing previous capture…"


def test_close_terminates_blocked_stdin_reader_and_hud(qtbot, monkeypatch, tmp_path) -> None:
    widget = _widget(qtbot, monkeypatch)
    widget.stop_file = tmp_path / "capture.stop"
    reader = Mock()
    reader.poll.return_value = None
    hud = Mock()
    hud.poll.return_value = None
    widget.proc = reader
    widget.hud_proc = hud
    widget.stop_button.setEnabled(True)

    widget.close()

    reader.terminate.assert_called_once()
    hud.terminate.assert_called_once()
    assert widget.stop_file.read_text() == "stop"
