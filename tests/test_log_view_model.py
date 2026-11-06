"""The Log Messages window's decisions, tested without a window (#456)."""

from __future__ import annotations

import json
import os

import pytest

from fpdb_3_legacy import log_view_model as model
from fpdb_3_legacy.log_view_model import LogEntry


def _line(level: str = "INFO", module: str = "Importer", message: str = "imported 3 hands", **extra: object) -> str:
    record = {
        "asctime": "2026-10-31 18:36:26,147",
        "levelname": level,
        "module": module,
        "funcName": "run",
        "message": message,
        **extra,
    }
    return json.dumps(record) + "\n"


def test_a_record_line_becomes_its_five_columns() -> None:
    entry = model.parse_line(_line("warning", "hud_main", "  table moved  "))

    assert entry == LogEntry("WARNING", "2026-10-31 18:36:26,147", "hud_main", "run", "table moved")
    assert entry.as_row() == ["WARNING", "2026-10-31 18:36:26,147", "hud_main", "run", "table moved"]


@pytest.mark.parametrize("line", ["", "   \n", "Traceback (most recent call last):", "[1, 2]", "{not json"])
def test_what_is_not_a_record_is_skipped(line) -> None:
    assert model.parse_line(line) is None


def test_a_record_with_missing_or_null_fields_still_shows() -> None:
    # The old reader called .strip() on whatever was there: a null field
    # raised inside the loader thread and the window stayed empty.
    entry = model.parse_line(json.dumps({"levelname": "error", "message": None}))

    assert entry == LogEntry("ERROR", "", "", "", "")


def test_only_the_newest_lines_are_read(tmp_path) -> None:
    log = tmp_path / "fpdb-log.txt"
    log.write_text("".join(_line(message=f"line {n}") for n in range(10)) + "garbage\n", encoding="utf-8")

    entries = model.read_tail(log, max_entries=4)

    assert [entry.message for entry in entries] == ["line 7", "line 8", "line 9"]


def test_a_missing_log_reads_as_empty(tmp_path) -> None:
    assert model.read_tail(tmp_path / "gone.txt") == []


def test_undecodable_bytes_do_not_lose_the_log(tmp_path) -> None:
    log = tmp_path / "fpdb-log.txt"
    log.write_bytes(_line(message="before").encode() + b"\xff\xfe broken\n" + _line(message="after").encode())

    assert [entry.message for entry in model.read_tail(log)] == ["before", "after"]


@pytest.mark.parametrize(
    ("level", "module", "levels", "text", "shown"),
    [
        ("INFO", "Importer", {"INFO"}, "", True),
        ("info ", "Importer", {"INFO"}, "", True),
        ("DEBUG", "Importer", {"INFO", "ERROR"}, "", False),
        ("ERROR", "HUD_main", {"ERROR"}, "hud", True),
        ("ERROR", "Importer", {"ERROR"}, "hud", False),
        ("ERROR", None, {"ERROR"}, "", True),
        ("ERROR", None, {"ERROR"}, "hud", False),
        (None, "Importer", set(model.LEVELS), "", False),
    ],
)
def test_the_filters(level, module, levels, text, shown) -> None:
    assert model.matches(level, module, levels, text) is shown


def test_both_logs_are_offered_newest_first(tmp_path) -> None:
    names = ["fpdb-log.txt", "HUD-log.txt", "fpdb-log.txt-30-10-2026-part1.txt", "fpdb-errors.txt", "notes.txt"]
    for age, name in enumerate(names):
        path = tmp_path / name
        path.write_text("{}\n", encoding="utf-8")
        os.utime(path, (1_800_000_000 - age * 60, 1_800_000_000 - age * 60))

    offered = [log.name for log in model.log_files(tmp_path)]

    assert offered == ["fpdb-log.txt", "HUD-log.txt", "fpdb-log.txt-30-10-2026-part1.txt"]


def test_a_missing_log_folder_offers_nothing(tmp_path) -> None:
    assert model.log_files(tmp_path / "absent") == []


def test_rows_are_copied_tab_separated_one_per_line() -> None:
    rows = [["INFO", "t1", "Importer", "run", "a"], ["ERROR", "t2", "HUD", "draw", None]]

    assert model.rows_as_text(rows) == "INFO\tt1\tImporter\trun\ta\nERROR\tt2\tHUD\tdraw\tNone\n"
    assert model.rows_as_text([]) == ""
