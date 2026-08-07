"""Unit tests for WinamaxLiveLogReader real-time log parsing."""

from __future__ import annotations

from unittest.mock import MagicMock

from fpdb_3_legacy.winamax_live_log_reader import WinamaxLiveLogReader


def test_parse_log_line_hand_start() -> None:
    reader = WinamaxLiveLogReader()
    line = "1786129601014 inf [table] 1 gf.cgmatchmaker.gf_1.t22754010.0 hand 22754010-6399-1786129600"
    parsed = reader.parse_log_line(line)

    assert parsed is not None
    assert parsed["event"] == "hand_start"
    assert parsed["table_no"] == "1"
    assert parsed["pool"] == "gf.cgmatchmaker.gf_1.t22754010.0"
    assert parsed["hand_id"] == "22754010-6399-1786129600"


def test_parse_log_line_action() -> None:
    reader = WinamaxLiveLogReader()
    line = '1786129601015 inf [table] 1 gf.cgmatchmaker.gf_1.t22754010.0 action SB login="Player01" amount="0.01"'
    parsed = reader.parse_log_line(line)

    assert parsed is not None
    assert parsed["event"] == "action"
    assert parsed["table_no"] == "1"
    assert parsed["action_type"] == "SB"
    assert parsed["login"] == "Player01"


def test_process_lines_builds_seat_map() -> None:
    callback = MagicMock()
    reader = WinamaxLiveLogReader(on_seat_update=callback)

    lines = [
        "1786129601014 inf [table] 1 gf.cgmatchmaker.gf_1.t22754010.0 hand 22754010-6399-1786129600\n",
        '1786129601015 inf [table] 1 gf.cgmatchmaker.gf_1.t22754010.0 action SB login="Player01" amount="0.01"\n',
        '1786129601015 inf [table] 1 gf.cgmatchmaker.gf_1.t22754010.0 action BB login="Player-_-11" amount="0.02"\n',
        '1786129619117 inf [table] 1 gf.cgmatchmaker.gf_1.t22754010.0 action fold login="Hero"\n',
    ]

    for line in lines:
        reader.process_line(line)

    assert callback.call_count == 3
    last_call_args = callback.call_args_list[-1][0]
    assert last_call_args[0] == "gf.cgmatchmaker.gf_1.t22754010.0"
    assert last_call_args[1] == {1: "Player01", 2: "Player-_-11", 3: "Hero"}
