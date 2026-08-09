"""Unit test for FastFold log line coalescing and display optimization."""

from unittest.mock import MagicMock

from fpdb_3_legacy.winamax_live_log_reader import WinamaxLiveLogReader, WinamaxTableUpdate


def test_coalesced_log_line_processing():
    """Verify that process_line with notify=False defers notification until _flush_pending is called."""
    mock_listener = MagicMock()
    reader = WinamaxLiveLogReader(on_table_update=mock_listener)

    # Process hand start line with notify=False
    hand_start_line = '[table] 1 gf.cgmatchmaker.gf_1.t22754010.0 hand 22754010-6356-1786128858\n'
    reader.process_line(hand_start_line, notify=False)

    # Should not have emitted yet
    mock_listener.assert_not_called()

    # Process cards and action lines
    cards_line = '[table] 1 gf.cgmatchmaker.gf_1.t22754010.0 cards login="hero"\n'
    action1 = '[table] 1 gf.cgmatchmaker.gf_1.t22754010.0 action SB login="hero"\n'
    action2 = '[table] 1 gf.cgmatchmaker.gf_1.t22754010.0 action BB login="player2"\n'
    reader.process_line(cards_line, notify=False)
    reader.process_line(action1, notify=False)
    reader.process_line(action2, notify=False)

    mock_listener.assert_not_called()

    # Flush pending notifications
    reader._flush_pending()

    # Should be called once with the coalesced state
    assert mock_listener.call_count == 1
    update = mock_listener.call_args[0][0]
    assert isinstance(update, WinamaxTableUpdate)
    assert update.hero == "hero"
    assert update.ring == ["hero", "player2"]
