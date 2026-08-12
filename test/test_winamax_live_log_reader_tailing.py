"""Finding, priming and following the Winamax client log.

The parsing side of this reader is already well covered; the part that touches
the filesystem and the watcher thread was not, and it is the part every
platform has its own answer for -- macOS keeps the logs under Application
Support, Linux under ~/.config, Windows under APPDATA. A Linux or Windows
build that gets the directory wrong has no live seat data at all, and the
symptom is a HUD that silently never appears rather than an error.

So the location rules are pinned per platform, and the tail loop is exercised
against real files in a temporary directory: rotation, a log that appears
after the reader started, a read that fails midway, and shutdown.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fpdb_3_legacy import winamax_live_log_reader as reader_module
from fpdb_3_legacy.winamax_live_log_reader import (
    WinamaxLiveLogReader,
    fpdb_hand_id,
    get_latest_winamax_log_file,
    get_winamax_log_dir,
)

#: One hand-start line, in the shape the client really writes.
HAND_START = (
    "1786488466123 [table] 4 gf.cgmatchmaker.gf_1.t22754010.3 hand 22754010-17407-1786488466\n"
)


def _wait_until(predicate, timeout: float = 5.0) -> bool:
    """Poll a background thread's effect rather than sleeping a fixed time."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


# ---------------------------------------------------------------------------
# Where each platform keeps the log
# ---------------------------------------------------------------------------


def test_macos_logs_live_under_application_support(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(reader_module.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    expected = tmp_path / "Library" / "Application Support" / "winamax" / "logs"
    expected.mkdir(parents=True)

    assert get_winamax_log_dir() == expected


@pytest.mark.parametrize("relative", [(".config", "winamax", "logs"), (".winamax", "logs")])
def test_linux_logs_live_under_the_home_directory(monkeypatch, tmp_path, relative) -> None:
    """Two conventions are in use; both must be found."""
    monkeypatch.setattr(reader_module.platform, "system", lambda: "Linux")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    expected = tmp_path.joinpath(*relative)
    expected.mkdir(parents=True)

    assert get_winamax_log_dir() == expected


@pytest.mark.parametrize("variable", ["APPDATA", "LOCALAPPDATA"])
def test_windows_logs_live_under_the_appdata_variables(monkeypatch, tmp_path, variable) -> None:
    monkeypatch.setattr(reader_module.platform, "system", lambda: "Windows")
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setenv(variable, str(tmp_path))
    expected = tmp_path / "Winamax" / "logs"
    expected.mkdir(parents=True)

    assert get_winamax_log_dir() == expected


def test_windows_without_its_environment_finds_nothing(monkeypatch) -> None:
    """A service account may have neither variable set."""
    monkeypatch.setattr(reader_module.platform, "system", lambda: "Windows")
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)

    assert get_winamax_log_dir() is None


def test_a_directory_that_does_not_exist_is_not_returned(monkeypatch, tmp_path) -> None:
    """The client not being installed is the ordinary case, not an error."""
    monkeypatch.setattr(reader_module.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))

    assert get_winamax_log_dir() is None


def test_an_unknown_platform_has_no_log_directory(monkeypatch) -> None:
    monkeypatch.setattr(reader_module.platform, "system", lambda: "FreeBSD")

    assert get_winamax_log_dir() is None


# ---------------------------------------------------------------------------
# Choosing the live file among the rotated ones
# ---------------------------------------------------------------------------


def test_the_newest_log_file_is_the_live_one(tmp_path) -> None:
    """The client rotates its logs; only the newest is still being written."""
    old = tmp_path / "old.log"
    new = tmp_path / "new.log"
    old.write_text("old\n")
    new.write_text("new\n")
    os.utime(old, (1, 1))
    os.utime(new, (2, 2))

    assert get_latest_winamax_log_file(tmp_path) == new


def test_a_directory_with_no_logs_yields_nothing(tmp_path) -> None:
    (tmp_path / "notes.txt").write_text("not a log\n")

    assert get_latest_winamax_log_file(tmp_path) is None


def test_a_missing_directory_yields_nothing(tmp_path) -> None:
    assert get_latest_winamax_log_file(tmp_path / "absent") is None


def test_the_default_directory_is_used_when_none_is_given(monkeypatch, tmp_path) -> None:
    log_file = tmp_path / "current.log"
    log_file.write_text("x\n")
    monkeypatch.setattr(reader_module, "get_winamax_log_dir", lambda: tmp_path)

    assert get_latest_winamax_log_file() == log_file


def test_no_directory_anywhere_yields_no_file(monkeypatch) -> None:
    monkeypatch.setattr(reader_module, "get_winamax_log_dir", lambda: None)

    assert get_latest_winamax_log_file() is None


# ---------------------------------------------------------------------------
# Matching a log hand id to an imported one
# ---------------------------------------------------------------------------


def test_a_log_hand_id_is_reduced_the_way_the_importer_reduces_it() -> None:
    """WinamaxToFpdb keeps the first two fields and joins them."""
    assert fpdb_hand_id("22754010-17407-1786488466") == "2275401017407"


def test_leading_zeroes_are_dropped_as_the_importer_drops_them() -> None:
    assert fpdb_hand_id("22754010-0006356-1786128858") == "227540106356"


@pytest.mark.parametrize("value", ["22754010", "", "notanid-abc-1", "abc-def"])
def test_an_id_that_cannot_be_reduced_is_refused(value) -> None:
    """Guessing here would key a HUD on the wrong window."""
    assert fpdb_hand_id(value) is None


# ---------------------------------------------------------------------------
# Priming from the end of an existing log
# ---------------------------------------------------------------------------


def test_priming_learns_pairings_without_reporting_a_finished_table(tmp_path) -> None:
    """Hands played just before startup are still waiting to be imported.

    Without their window they cannot be given a HUD, so each costs the table a
    hand's delay. Reporting them as current instead would put a finished
    table's players on screen.
    """
    log_file = tmp_path / "winamax.log"
    log_file.write_text(HAND_START)
    seen: list = []
    reader = WinamaxLiveLogReader(on_table_update=seen.append)

    with log_file.open(encoding="utf-8") as handle:
        reader._prime_from_tail(handle)

    assert reader.table_no_for_hand("22754010-17407-1786488466") == "4"
    assert seen == []


def test_priming_reads_only_the_end_of_a_long_log(tmp_path) -> None:
    """A client log runs to megabytes; reading it whole would stall startup."""
    log_file = tmp_path / "winamax.log"
    filler = "x" * (WinamaxLiveLogReader.PRIME_BYTES + 5000)
    log_file.write_text(f"{filler}\n{HAND_START}")
    reader = WinamaxLiveLogReader()

    with log_file.open(encoding="utf-8") as handle:
        reader._prime_from_tail(handle)

    assert reader.table_no_for_hand("22754010-17407-1786488466") == "4"


def test_a_priming_failure_leaves_the_reader_usable(tmp_path) -> None:
    """A truncated or locked file must not stop the reader from tailing."""
    reader = WinamaxLiveLogReader()
    broken = MagicMock()
    broken.seek.side_effect = OSError("bad file descriptor")

    reader._prime_from_tail(broken)

    assert reader._priming is False


# ---------------------------------------------------------------------------
# The watcher thread
# ---------------------------------------------------------------------------


@pytest.fixture
def tailing(monkeypatch, tmp_path):
    """A reader tailing ``tmp_path``, stopped when the test ends."""
    monkeypatch.setattr(reader_module, "get_winamax_log_dir", lambda: tmp_path)
    readers: list[WinamaxLiveLogReader] = []

    def start(**kwargs) -> WinamaxLiveLogReader:
        reader = WinamaxLiveLogReader(poll_interval=0.01, **kwargs)
        readers.append(reader)
        reader.start()
        return reader

    yield start
    for reader in readers:
        reader.stop()


def test_a_hand_written_while_tailing_is_reported(tailing, tmp_path) -> None:
    log_file = tmp_path / "winamax.log"
    log_file.write_text("")
    seen: list = []
    reader = tailing(on_table_update=seen.append)
    assert _wait_until(lambda: reader.is_tailing)

    with log_file.open("a", encoding="utf-8") as handle:
        handle.write(HAND_START)

    assert _wait_until(lambda: bool(seen)), "the hand was never reported"
    assert seen[0].table_no == "4"


def test_a_log_that_appears_later_is_picked_up(tailing, tmp_path) -> None:
    """The HUD may start before the client has opened a table."""
    reader = tailing()
    assert _wait_until(lambda: reader._running)
    assert not reader.is_tailing

    (tmp_path / "winamax.log").write_text(HAND_START)

    assert _wait_until(lambda: reader.is_tailing)


def test_rotation_is_followed(tailing, tmp_path) -> None:
    """The client starts a new file; the old one stops being written."""
    first = tmp_path / "first.log"
    first.write_text("")
    seen: list = []
    reader = tailing(on_table_update=seen.append)
    assert _wait_until(lambda: reader.is_tailing)

    second = tmp_path / "second.log"
    second.write_text(HAND_START)
    os.utime(second, (time.time() + 10, time.time() + 10))

    assert _wait_until(lambda: reader._tailing == second)


def test_a_read_failure_is_recovered_from(tailing, tmp_path, monkeypatch) -> None:
    """A file replaced under the reader must not end the watcher thread."""
    log_file = tmp_path / "winamax.log"
    log_file.write_text("")
    calls = {"n": 0}
    real = reader_module.get_latest_winamax_log_file

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("file vanished")
        return real(tmp_path)

    monkeypatch.setattr(reader_module, "get_latest_winamax_log_file", flaky)
    reader = tailing()

    assert _wait_until(lambda: calls["n"] > 3), "the loop stopped after the failure"
    assert reader._running


def test_stopping_closes_the_file_and_ends_the_thread(tailing, tmp_path) -> None:
    (tmp_path / "winamax.log").write_text(HAND_START)
    reader = tailing()
    assert _wait_until(lambda: reader.is_tailing)

    reader.stop()

    assert reader._running is False
    assert reader.is_tailing is False
    assert reader._thread is None


def test_starting_twice_runs_one_thread(tailing, tmp_path) -> None:
    """A second start would tail the same file twice and double every update."""
    (tmp_path / "winamax.log").write_text("")
    reader = tailing()
    assert _wait_until(lambda: reader.is_tailing)
    thread = reader._thread

    reader.start()

    assert reader._thread is thread


def test_stopping_a_reader_that_never_started_is_harmless() -> None:
    reader = WinamaxLiveLogReader()

    reader.stop()

    assert reader._running is False


# ---------------------------------------------------------------------------
# Lines the parser must recognise, and lines it must not
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "1786488466123 [core] some message without a table\n",
        "1786488466123 [table] 4 pool.name something-else unrecognised\n",
        "",
    ],
    ids=["not-a-table-line", "unknown-table-event", "empty"],
)
def test_a_line_that_says_nothing_about_seats_is_ignored(line) -> None:
    assert WinamaxLiveLogReader().parse_log_line(line) is None


def test_an_unparsed_line_changes_no_table_state() -> None:
    reader = WinamaxLiveLogReader()

    reader.process_line("1786488466123 [core] nothing here\n")

    assert reader.get_table("gf.cgmatchmaker.gf_1.t22754010.3") is None


def test_a_callback_that_raises_does_not_stop_the_reader() -> None:
    """The GUI thread's handler is not this reader's to trust."""
    reader = WinamaxLiveLogReader(on_table_update=MagicMock(side_effect=RuntimeError("GUI is gone")))

    reader.process_line(HAND_START)

    assert reader.get_table("gf.cgmatchmaker.gf_1.t22754010.3") is not None


def test_flushing_with_nothing_pending_is_harmless() -> None:
    reader = WinamaxLiveLogReader(on_table_update=MagicMock(side_effect=AssertionError("nothing to flush")))

    reader._flush_pending()


def test_a_hand_over_line_is_recorded_once() -> None:
    """The pot being awarded ends the hand, and repeating it changes nothing."""
    seen: list = []
    reader = WinamaxLiveLogReader(on_table_update=seen.append)
    reader.process_line(HAND_START)
    gain = "1786488470000 [table] 4 gf.cgmatchmaker.gf_1.t22754010.3 gain 5\n"

    reader.process_line(gain)
    before = len(seen)
    reader.process_line(gain)

    assert reader.get_table("gf.cgmatchmaker.gf_1.t22754010.3").hand_over is True
    assert len(seen) == before, "a repeated hand-over must not re-notify"


def test_the_hero_is_learned_from_their_own_cards_once() -> None:
    seen: list = []
    reader = WinamaxLiveLogReader(on_table_update=seen.append)
    reader.process_line(HAND_START)
    cards = '1786488467000 [table] 4 gf.cgmatchmaker.gf_1.t22754010.3 cards login="jejellyroll"\n'

    reader.process_line(cards)
    before = len(seen)
    reader.process_line(cards)

    assert reader.get_table("gf.cgmatchmaker.gf_1.t22754010.3").hero == "jejellyroll"
    assert len(seen) == before


def test_a_player_acting_twice_joins_the_ring_once() -> None:
    """The ring is who is at the table, not how often each of them acted."""
    reader = WinamaxLiveLogReader()
    reader.process_line(HAND_START)
    action = '1786488467500 [table] 4 gf.cgmatchmaker.gf_1.t22754010.3 action call login="villain"\n'

    reader.process_line(action)
    reader.process_line(action)

    assert reader.get_table("gf.cgmatchmaker.gf_1.t22754010.3").ring == ["villain"]


def test_the_hero_folding_ends_the_table_for_them() -> None:
    """Fast-Fold moves the hero on at once; the overlay must stop describing it."""
    reader = WinamaxLiveLogReader()
    reader.process_line(HAND_START)
    reader.process_line('1786488467000 [table] 4 gf.cgmatchmaker.gf_1.t22754010.3 cards login="jejellyroll"\n')

    reader.process_line('1786488468000 [table] 4 gf.cgmatchmaker.gf_1.t22754010.3 action fold login="jejellyroll"\n')

    table = reader.get_table("gf.cgmatchmaker.gf_1.t22754010.3")
    assert table.hero_left is True
    assert table.finished is True


def test_an_opponent_folding_leaves_the_table_running() -> None:
    reader = WinamaxLiveLogReader()
    reader.process_line(HAND_START)
    reader.process_line('1786488467000 [table] 4 gf.cgmatchmaker.gf_1.t22754010.3 cards login="jejellyroll"\n')

    reader.process_line('1786488468000 [table] 4 gf.cgmatchmaker.gf_1.t22754010.3 action fold login="villain"\n')

    assert reader.get_table("gf.cgmatchmaker.gf_1.t22754010.3").hero_left is False


def test_a_log_directory_that_holds_no_file_leaves_the_reader_idle(tailing, tmp_path) -> None:
    """The loop must keep polling for a log rather than settling on nothing."""
    reader = tailing()

    assert _wait_until(lambda: reader._running)
    assert reader.is_tailing is False


# ---------------------------------------------------------------------------
# The tail loop, driven a fixed number of turns
# ---------------------------------------------------------------------------


def _run_loop(reader: WinamaxLiveLogReader, monkeypatch, turns: int) -> None:
    """Run ``_watch_loop`` in this thread for a set number of polls.

    The loop's own sleep is what ends it, so replacing that is enough to make
    a background loop deterministic -- no waiting, and no race to lose.
    """
    remaining = {"turns": turns}

    def stop_after_a_turn(_seconds: float) -> None:
        remaining["turns"] -= 1
        if remaining["turns"] <= 0:
            reader._running = False

    monkeypatch.setattr(reader_module.time, "sleep", stop_after_a_turn)
    reader._running = True
    reader._watch_loop()


def test_a_log_that_disappears_stops_the_tail(monkeypatch, tmp_path) -> None:
    """The client can delete its log; the reader must report it is not tailing.

    is_tailing is what tells the HUD whether live seats exist at all, so
    leaving it true over a deleted file makes every table wait for seats that
    can no longer come.
    """
    log_file = tmp_path / "winamax.log"
    log_file.write_text(HAND_START)
    monkeypatch.setattr(reader_module, "get_winamax_log_dir", lambda: tmp_path)
    reader = WinamaxLiveLogReader(poll_interval=0)
    seen_tailing: list = []

    original = reader_module.get_latest_winamax_log_file

    def vanishing(*args, **kwargs):
        found = original(tmp_path)
        seen_tailing.append(reader._tailing)
        return None if len(seen_tailing) > 1 else found

    monkeypatch.setattr(reader_module, "get_latest_winamax_log_file", vanishing)
    _run_loop(reader, monkeypatch, turns=3)

    assert seen_tailing[1] == log_file, "the first poll should have opened it"
    assert reader._tailing is None


def test_a_poll_with_no_new_lines_notifies_nobody(monkeypatch, tmp_path) -> None:
    """The log is polled several times a second and is usually unchanged.

    The hand already in the file is consumed by priming, which is silent on
    purpose, so a run over an unchanging log must report nothing at all --
    not the same finished hand once per poll.
    """
    (tmp_path / "winamax.log").write_text(HAND_START)
    monkeypatch.setattr(reader_module, "get_winamax_log_dir", lambda: tmp_path)
    seen: list = []
    reader = WinamaxLiveLogReader(poll_interval=0, on_table_update=seen.append)

    _run_loop(reader, monkeypatch, turns=4)

    assert seen == [], "an unchanging log must not report anything"


def test_an_event_the_reader_does_not_know_changes_nothing() -> None:
    """Defensive: a new log event must not be folded in by accident."""
    from fpdb_3_legacy.winamax_live_log_reader import WinamaxTableUpdate

    table = WinamaxTableUpdate(pool="pool", table_no="4", hand_id="h1", hero=None)

    assert WinamaxLiveLogReader._apply_event(table, "seat_change", {"login": "villain"}) is False
    assert table.ring == []
    assert table.hero is None


def test_a_failure_before_any_file_is_open_is_survived(monkeypatch, tmp_path) -> None:
    """The very first poll can fail, with no file yet to close.

    A HUD started before the client, or without permission to read its log
    directory, meets this on turn one; the loop has to keep polling so the
    table appears when the client finally does.
    """
    monkeypatch.setattr(reader_module, "get_winamax_log_dir", lambda: tmp_path)
    polls = {"n": 0}

    def failing(*args, **kwargs):
        polls["n"] += 1
        if polls["n"] == 1:
            raise PermissionError("log directory not readable")
        return None

    monkeypatch.setattr(reader_module, "get_latest_winamax_log_file", failing)
    reader = WinamaxLiveLogReader(poll_interval=0)

    _run_loop(reader, monkeypatch, turns=3)

    assert polls["n"] >= 2, "the loop gave up after the first failure"
    assert reader._tailing is None
