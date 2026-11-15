"""The #615 probe's offline parts: what it reports, and how it reads PT4's stored text.

The PT4 side needs a real PokerTracker 4 database and stays out of the suite;
these check the parts a wrong report would come from.
"""

from __future__ import annotations

import importlib.util
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_probe():
    spec = importlib.util.spec_from_file_location("pt4_db_probe", ROOT / "tools" / "pt4_db_probe.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["pt4_db_probe"] = module  # dataclasses look their module up while the class is built
    spec.loader.exec_module(module)
    return module


probe = _load_probe()

STARS_HAND = ROOT / "regression-test-files" / "cash" / "Stars" / "Flop" / "2025-NL-uncalled-bet.txt"


def test_the_first_line_keeps_its_shape_without_its_numbers() -> None:
    head = probe.masked_head("﻿\n\nPokerStars Hand #255867983097:  Hold'em No Limit ($0.02/$0.05 USD)")
    assert head == "PokerStars Hand #999999999999:  Hold'em"
    assert probe.masked_head("") == ""


def test_the_history_column_is_found_by_name_first() -> None:
    columns = [probe.Column("id_hand", "integer"), probe.Column("notes", "text"), probe.Column("history", "text")]
    assert probe.pick_history_column(columns).name == "history"
    assert probe.pick_history_column(columns[:2]).name == "notes"
    assert probe.pick_history_column(columns[:1]) is None


def test_an_encoded_history_is_told_from_text() -> None:
    assert probe.encoding_signature("PokerStars Hand #1") == "text"
    assert probe.encoding_signature(b"\x1f\x8b\x08") == "gzip"
    assert probe.encoding_signature(memoryview(b"x\x9c")) == "zlib"
    assert probe.encoding_signature(b"\xff\xfe\x00") == "binary"
    assert probe.as_text(memoryview(b"Hand")) == "Hand"
    assert probe.as_text(None) == ""


def test_a_stored_history_goes_through_the_rooms_own_parser(legacy_config, tmp_path) -> None:
    text = STARS_HAND.read_text(encoding="utf-8-sig")
    rows = [("PokerStars", "255867983097", text), ("PokerStars", "1", "\r\n")]
    sample = probe.parse_room(legacy_config, probe.RoomSample("cash", "PokerStars", 2), rows, tmp_path)

    assert (sample.sampled, sample.parsed, sample.errors, sample.partial) == (1, 1, 0, 0)
    assert sample.identified_as == "PokerStars.COM"
    assert sample.parser == "PokerStars"
    assert sample.same_hand_no == 1
    assert sample.heads == Counter({"PokerStars Hand #999999999999:  Hold'em": 1})


def test_histories_no_parser_knows_are_reported_not_dropped(legacy_config, tmp_path) -> None:
    rows = [("Nowhere", "1", "this is not a hand history")]
    sample = probe.parse_room(legacy_config, probe.RoomSample("cash", "Nowhere", 1), rows, tmp_path)

    assert (sample.sampled, sample.parsed) == (1, 0)
    assert sample.identified_as is None
    assert sample.messages == ["no parser recognises these histories"]


def test_the_report_names_no_player() -> None:
    sample = probe.RoomSample("cash", "PokerStars", 1000, sampled=10, parsed=9, parse_seconds=0.5)
    sample.heads["PokerStars Hand #9999"] = 10
    sample.messages.append("player alice not found")
    report = probe.format_report(
        {"cash_hand_histories": [probe.Column("id_hand", "integer"), probe.Column("history", "text")]},
        {"cash_hand_histories": Counter({"text": 10})},
        {"cash_hand_histories": probe.Stream(rows=1000, chars=2_000_000, seconds=2.0)},
        [sample],
    )
    assert "alice" not in report
    assert "| cash | PokerStars | 1,000 | 10 |" in report
    assert "9 (90%)" in report
    assert "1,000 rows, 2.0 M chars in 2.0 s (500 rows/s)" in report
    assert "Weighted by each room's share of the database: 90.0% of 1,000 hands." in report
