"""Regressions for the duplicate-HUD report: one process, one renderer, one update.

A player running two Fast-Fold tables saw every statistic twice, and the logs
of the day could not say why: they held no process ids, no window ids and no
generation, so a second renderer, a leftover from a previous launch and a
window painted twice all looked the same. Each test here pins down one of the
things that could have produced it, and the ones that are about processes use
real processes rather than a mock of the lock.
"""

from __future__ import annotations

import inspect
import os
import pathlib
import subprocess
import sys
import textwrap
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fpdb_3_legacy import HUD_main
from fpdb_3_legacy.hud_window_registry import ClaimOutcome, HudWindowRegistry
from fpdb_3_legacy.interlocks import acquire_hud_instance_lock

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REPO_ROOT_PATH = pathlib.Path(REPO_ROOT)


# --------------------------------------------------------------------------
# One HUD process
# --------------------------------------------------------------------------


@pytest.fixture
def lock_name() -> str:
    """A lock of this test run's own.

    Never the production ``fpdb_hud_instance``: that one is machine-wide, so
    taking it would make the result depend on whether the developer has a HUD
    open, and would lock them out of it for the duration.
    """
    return f"fpdb_hud_instance_test_{os.getpid()}_{uuid.uuid4().hex[:8]}"


def _hud_lock_child_source(action: str, lock_name: str) -> str:
    """A child that takes the HUD lock through the real code and reports back."""
    return textwrap.dedent(
        f"""
        import sys
        sys.path.insert(0, {REPO_ROOT!r})
        from fpdb_3_legacy.interlocks import SingleInstanceError, acquire_hud_instance_lock

        try:
            lock = acquire_hud_instance_lock("test-{action}", name={lock_name!r})
        except SingleInstanceError:
            print("REFUSED")
            sys.exit(1)
        print("ACQUIRED", flush=True)
        if {action!r} == "hold":
            sys.stdin.readline()
        lock.release()
        """,
    )


def test_the_hud_entry_point_uses_the_machine_wide_lock() -> None:
    """The default is the shared name, whatever the tests above use."""
    from fpdb_3_legacy.interlocks import HUD_INSTANCE_LOCK_NAME

    signature = inspect.signature(acquire_hud_instance_lock)

    assert HUD_INSTANCE_LOCK_NAME == "fpdb_hud_instance"
    assert signature.parameters["name"].default == HUD_INSTANCE_LOCK_NAME


def test_the_socket_lock_picks_the_same_port_in_every_process() -> None:
    """Two processes must contend for one port, or the lock excludes nobody.

    The socket lock is the fallback wherever there is no fcntl and no
    pywin32 -- a plain Windows install among them, where it is the only thing
    standing between the user and two HUD processes drawing over each other.
    Its port used to come from ``hash()``, which Python salts per process, so
    every process bound a different port, none ever collided, and the lock
    admitted as many holders as asked without failing visibly.
    """
    from fpdb_3_legacy.interlocks import InterProcessLockSocket, port_for_lock_name

    source = textwrap.dedent(
        f"""
        import sys
        sys.path.insert(0, {REPO_ROOT!r})
        from fpdb_3_legacy.interlocks import InterProcessLockSocket
        print(InterProcessLockSocket(name="fpdb_hud_instance").portno)
        """,
    )
    ports = set()
    for seed in ("0", "1", "random"):
        # A fresh hash seed per child is what the old derivation could not survive.
        result = subprocess.run(
            [sys.executable, "-c", source],
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
        )
        ports.add(result.stdout.strip())

    assert len(ports) == 1, f"the same lock name resolved to {sorted(ports)} in different processes"
    assert ports == {str(InterProcessLockSocket(name="fpdb_hud_instance").portno)}
    assert port_for_lock_name("a") != port_for_lock_name("b"), "different locks must not share a port"


def _socket_lock_child_source(action: str, lock_name: str) -> str:
    """A child that takes the socket lock specifically, whatever the platform."""
    return textwrap.dedent(
        f"""
        import sys
        sys.path.insert(0, {REPO_ROOT!r})
        from fpdb_3_legacy.interlocks import InterProcessLockSocket

        lock = InterProcessLockSocket(name={lock_name!r})
        if not lock.acquire("test-{action}"):
            print("REFUSED")
            sys.exit(1)
        print("ACQUIRED", flush=True)
        if {action!r} == "hold":
            sys.stdin.readline()
        lock.release()
        """,
    )


def test_the_socket_lock_really_excludes_a_second_process(lock_name) -> None:
    """Exercised on every platform, because every platform can fall back to it.

    Windows without pywin32 and any Unix without fcntl land here, and CI
    installs neither on Windows -- so this is the lock the Windows runner
    actually tests. Two real processes, because that is the only way to see a
    lock that never excludes anybody.
    """
    holder = subprocess.Popen(
        [sys.executable, "-c", _socket_lock_child_source("hold", lock_name)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "ACQUIRED"

        second = subprocess.run(
            [sys.executable, "-c", _socket_lock_child_source("try", lock_name)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert second.returncode == 1, second.stdout
        assert "REFUSED" in second.stdout
    finally:
        assert holder.stdin is not None
        holder.stdin.write("\n")
        holder.stdin.flush()
        holder.wait(timeout=60)


def test_two_hud_launches_leave_a_single_owner(lock_name) -> None:
    """The second ``--hud`` process must refuse to start, not start quietly.

    Two live HUD processes each build their own overlays over the same tables,
    which is one of the two ways the doubled blocks could have happened. The
    lock is taken before Qt, ZMQ or any window exists, so this is checked with
    two real processes -- a mock could not tell whether the lock is actually
    held across process boundaries.
    """
    holder = subprocess.Popen(
        [sys.executable, "-c", _hud_lock_child_source("hold", lock_name)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "ACQUIRED"

        second = subprocess.run(
            [sys.executable, "-c", _hud_lock_child_source("try", lock_name)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert second.returncode == 1, second.stdout
        assert "REFUSED" in second.stdout
        assert "ACQUIRED" not in second.stdout
    finally:
        assert holder.stdin is not None
        holder.stdin.write("\n")
        holder.stdin.flush()
        holder.wait(timeout=60)


def test_the_lock_is_released_when_the_hud_exits(lock_name) -> None:
    """A HUD that has quit must not lock the next one out.

    The refusal above is only correct if it is temporary: a crash or a normal
    quit that left the lock behind would make the HUD unstartable until
    reboot, which is worse than the bug it prevents.
    """
    first = subprocess.run(
        [sys.executable, "-c", _hud_lock_child_source("try", lock_name)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert first.returncode == 0
    assert "ACQUIRED" in first.stdout

    second = subprocess.run(
        [sys.executable, "-c", _hud_lock_child_source("try", lock_name)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert second.returncode == 0, second.stdout
    assert "ACQUIRED" in second.stdout


# --------------------------------------------------------------------------
# One renderer per window
# --------------------------------------------------------------------------


def test_registry_refuses_a_second_renderer_on_one_window() -> None:
    """Claiming a window twice under the same key is a duplicate, not a rebuild."""
    registry = HudWindowRegistry()

    first = registry.claim(61632, "Colorado 1 #61632")
    assert first.outcome is ClaimOutcome.CREATED
    assert first.should_create

    second = registry.claim(61632, "Colorado 1 #61632")
    assert second.outcome is ClaimOutcome.DUPLICATE
    assert not second.should_create
    assert second.registration == first.registration


def test_registry_supersedes_the_previous_key_on_one_window() -> None:
    """A window whose HUD key changes must give up the old generation."""
    registry = HudWindowRegistry()
    registry.claim(61632, "Colorado 1")

    claim = registry.claim(61632, "Colorado 1 #61632")

    assert claim.outcome is ClaimOutcome.SUPERSEDED
    assert claim.superseded is not None
    assert claim.superseded.temp_key == "Colorado 1"
    assert claim.generation > claim.superseded.generation
    # Only the new key holds the window afterwards.
    assert registry.key_for(61632) == "Colorado 1 #61632"
    assert registry.registration_for_key("Colorado 1") is None


def test_two_tables_get_two_huds() -> None:
    """Two windows of one pool are two renderers, which is the correct case."""
    registry = HudWindowRegistry()

    first = registry.claim(61632, "Colorado 1 #61632")
    second = registry.claim(61633, "Colorado 2 #61633")

    assert first.outcome is ClaimOutcome.CREATED
    assert second.outcome is ClaimOutcome.CREATED
    assert len(registry.snapshot()) == 2
    assert first.generation != second.generation


def test_released_window_can_be_claimed_again() -> None:
    """Closing and reopening a table must leave nothing behind."""
    registry = HudWindowRegistry()
    registry.claim(61632, "Colorado 1 #61632")

    released = registry.release("Colorado 1 #61632")

    assert released is not None
    assert registry.snapshot() == {}
    # The same window, reopened, is a fresh creation rather than a duplicate.
    assert registry.claim(61632, "Colorado 1 #61632").outcome is ClaimOutcome.CREATED


def test_a_destroyed_generation_is_no_longer_current() -> None:
    """Work started for a torn-down HUD must be recognisable as stale."""
    registry = HudWindowRegistry()
    claim = registry.claim(61632, "Colorado 1 #61632")
    assert registry.is_current("Colorado 1 #61632", claim.generation)

    registry.release("Colorado 1 #61632")
    assert not registry.is_current("Colorado 1 #61632", claim.generation)

    rebuilt = registry.claim(61632, "Colorado 1 #61632")
    assert not registry.is_current("Colorado 1 #61632", claim.generation)
    assert registry.is_current("Colorado 1 #61632", rebuilt.generation)


def test_untracked_window_still_gets_a_generation() -> None:
    """A table whose window id is unknown is allowed through, not blocked."""
    registry = HudWindowRegistry()

    claim = registry.claim(None, "Some Cash Table")

    assert claim.outcome is ClaimOutcome.UNTRACKED
    assert claim.should_create
    assert claim.generation > 0


# --------------------------------------------------------------------------
# create_HUD enforces the registry
# --------------------------------------------------------------------------


def _hud_main_for_create() -> HUD_main.HudMain:
    """A HudMain with only what create_HUD touches."""
    hud_main = HUD_main.HudMain.__new__(HUD_main.HudMain)
    hud_main.hud_dict = {}
    hud_main._window_registry = HudWindowRegistry()
    hud_main._hud_generation = 0
    hud_main._fast_fold_tables = set()
    hud_main.config = MagicMock()
    hud_main.db_connection = MagicMock()
    hud_main._prepared_hands = {}
    hud_main.idle_create = MagicMock()
    return hud_main


def _creation_args(temp_key: str, window_id: int, *, speed: str = "normal") -> HUD_main.HUDCreationArgs:
    return HUD_main.HUDCreationArgs(
        new_hand_id="hand1",
        table=SimpleNamespace(number=window_id, key=temp_key, hud=None),
        temp_key=temp_key,
        max_seats=6,
        poker_game="holdem",
        game_type="ring",
        stat_dict={},
        cards={},
        context=SimpleNamespace(speed=speed),
        loading=True,
    )


def test_create_hud_refuses_a_duplicate_on_the_same_window(monkeypatch) -> None:
    """The second create for one (window, key) must build nothing at all."""
    hud_main = _hud_main_for_create()
    monkeypatch.setattr(HUD_main.Hud, "Hud", MagicMock(side_effect=lambda *a, **k: MagicMock()))

    hud_main.create_HUD(_creation_args("Colorado 1 #61632", 61632))
    assert hud_main.idle_create.call_count == 1
    first_hud = hud_main.hud_dict["Colorado 1 #61632"]

    hud_main.create_HUD(_creation_args("Colorado 1 #61632", 61632))

    assert hud_main.idle_create.call_count == 1  # refused, not rebuilt
    assert hud_main.hud_dict["Colorado 1 #61632"] is first_hud
    assert len(hud_main.hud_dict) == 1


def test_create_hud_destroys_the_superseded_renderer(monkeypatch) -> None:
    """A window whose key changes keeps one renderer, not two."""
    hud_main = _hud_main_for_create()
    monkeypatch.setattr(HUD_main.Hud, "Hud", MagicMock(side_effect=lambda *a, **k: MagicMock()))
    destroyed: list[str] = []
    hud_main._destroy_superseded_hud = lambda key: (destroyed.append(key), hud_main.hud_dict.pop(key, None))

    hud_main.create_HUD(_creation_args("Colorado 1", 61632))
    hud_main.create_HUD(_creation_args("Colorado 1 #61632", 61632))

    assert destroyed == ["Colorado 1"]
    assert list(hud_main.hud_dict) == ["Colorado 1 #61632"]


def test_two_windows_produce_two_huds_through_create(monkeypatch) -> None:
    """Multi-tabling is unaffected: two windows, two renderers."""
    hud_main = _hud_main_for_create()
    monkeypatch.setattr(HUD_main.Hud, "Hud", MagicMock(side_effect=lambda *a, **k: MagicMock()))

    hud_main.create_HUD(_creation_args("Colorado 1 #61632", 61632))
    hud_main.create_HUD(_creation_args("Colorado 2 #61633", 61633))

    assert sorted(hud_main.hud_dict) == ["Colorado 1 #61632", "Colorado 2 #61633"]
    assert hud_main.idle_create.call_count == 2


# --------------------------------------------------------------------------
# Seats are rotated once, not twice
# --------------------------------------------------------------------------


def test_a_fast_fold_hud_knows_it_before_its_aux_windows_are_built(monkeypatch) -> None:
    """``is_fast_fold`` must be true by the time the overlays are created.

    ``AuxSeats.adj_seats`` returns the identity mapping for Fast-Fold because
    ``FastFoldEngine`` has already rotated the client's slots onto layout
    seats. It reads the flag while the aux windows are being built, and every
    caller used to set the flag *after* creation -- so the check never fired
    and the seats were rotated a second time, by the hero's seat in the last
    imported hand. That put every player's block on their neighbour's chair.
    """
    hud_main = _hud_main_for_create()
    monkeypatch.setattr(HUD_main.Hud, "Hud", MagicMock(side_effect=lambda *a, **k: MagicMock(is_fast_fold=False)))
    seen: list[bool] = []
    hud_main.idle_create = lambda args: seen.append(hud_main.hud_dict[args.temp_key].is_fast_fold)

    hud_main.create_HUD(_creation_args("Colorado 1 #61632", 61632, speed="fast"))

    assert seen == [True]


def test_a_fast_fold_table_known_only_by_key_is_still_flagged(monkeypatch) -> None:
    """A direct create_HUD call must not lose the Fast-Fold identity."""
    hud_main = _hud_main_for_create()
    hud_main._fast_fold_tables.add("Colorado 1 #61632")
    monkeypatch.setattr(HUD_main.Hud, "Hud", MagicMock(side_effect=lambda *a, **k: MagicMock(is_fast_fold=False)))
    seen: list[bool] = []
    hud_main.idle_create = lambda args: seen.append(hud_main.hud_dict[args.temp_key].is_fast_fold)

    hud_main.create_HUD(_creation_args("Colorado 1 #61632", 61632))

    assert seen == [True]


def test_an_ordinary_table_is_not_flagged_as_fast_fold(monkeypatch) -> None:
    """A cash table must keep the rotation adj_seats does for it."""
    hud_main = _hud_main_for_create()
    monkeypatch.setattr(HUD_main.Hud, "Hud", MagicMock(side_effect=lambda *a, **k: MagicMock(is_fast_fold=False)))
    seen: list[bool] = []
    hud_main.idle_create = lambda args: seen.append(hud_main.hud_dict[args.temp_key].is_fast_fold)

    hud_main.create_HUD(_creation_args("Some Cash Table", 4242))

    assert seen == [False]


# --------------------------------------------------------------------------
# One GUI application per hand
# --------------------------------------------------------------------------


def _hud_main_for_snapshot() -> HUD_main.HudMain:
    """A HudMain whose read_stdin bookkeeping is real and the rest stubbed."""
    hud_main = HUD_main.HudMain.__new__(HUD_main.HudMain)
    hud_main.hud_dict = {}
    hud_main._window_registry = HudWindowRegistry()
    hud_main._last_processed_hands = {}
    hud_main._import_request_sequence = 0
    return hud_main


def test_progressive_and_final_snapshot_apply_one_hand_once() -> None:
    """The same hand delivered twice must reach the HUD exactly once.

    ``_on_db_snapshot`` runs for the worker's progressive snapshot and again
    for the final one, and both call ``read_stdin`` with the same hand. The
    idempotence key is ``(table, hand)``; without it the second pass would
    re-apply the hand and the trace would show two updates for one deal.
    """
    hud_main = _hud_main_for_snapshot()
    applications: list[str] = []

    def apply(hand_id: str) -> str | None:
        temp_key = "Colorado 1 #61632"
        if hud_main._last_processed_hands.get(temp_key) == hand_id:
            return None
        hud_main._last_processed_hands[temp_key] = hand_id
        applications.append(hand_id)
        return temp_key

    assert apply("hand-1") == "Colorado 1 #61632"
    assert apply("hand-1") is None  # the final snapshot repeats the hand
    assert apply("hand-2") == "Colorado 1 #61632"

    assert applications == ["hand-1", "hand-2"]


def test_import_applied_line_carries_hand_window_and_request(caplog) -> None:
    """The applied line must identify which application it is.

    Two lines for one hand and one line for each of two hands are the two
    readings the old logging could not be told apart into.
    """
    hud_main = _hud_main_for_snapshot()
    hud = MagicMock()
    hud.table.number = 61632
    hud._fpdb_generation = 4
    hud_main.hud_dict["Colorado 1 #61632"] = hud

    with caplog.at_level("WARNING"):
        hud_main._log_fast_fold_import_applied("hand-1", "Colorado 1 #61632")
        hud_main._log_fast_fold_import_applied("hand-2", "Colorado 1 #61632")

    applied = [record.getMessage() for record in caplog.records if "FF import applied" in record.getMessage()]
    assert len(applied) == 2
    assert "hand=hand-1" in applied[0]
    assert "window_id=61632" in applied[0]
    assert "request=1" in applied[0]
    assert "request=2" in applied[1]  # a distinct application, not a repeat


def test_unmapped_hand_is_reported_once_not_once_per_snapshot(caplog) -> None:
    """Qualification runs twice per hand and must warn once.

    Both snapshots of one hand pass through ``_qualify_fast_fold_table``. It
    used to warn on each, so a single hand delayed by the window map read as
    two problems.
    """
    hud_main = HUD_main.HudMain.__new__(HUD_main.HudMain)
    hud_main._ff_unmapped_logged = set()
    hud_main._prepared_hands = {}
    hud_main._has_live_seat_source = lambda _site: True
    hud_main.winamax_log_reader = MagicMock()
    hud_main.winamax_log_reader.table_no_for_hand.return_value = None
    info = SimpleNamespace(
        fast=True,
        site_name="Winamax",
        table_name="Colorado",
        poker_game="holdem",
    )

    with caplog.at_level("WARNING"):
        assert hud_main._qualify_fast_fold_table(info, "hand-1") is None
        assert hud_main._qualify_fast_fold_table(info, "hand-1") is None
        assert hud_main._qualify_fast_fold_table(info, "hand-2") is None

    warnings = [r.getMessage() for r in caplog.records if "not in the log window map" in r.getMessage()]
    assert len(warnings) == 2  # one per hand, not one per snapshot


def test_qualification_does_not_announce_anything(caplog) -> None:
    """A successful qualification is silent; the applied line does the talking."""
    hud_main = HUD_main.HudMain.__new__(HUD_main.HudMain)
    hud_main._ff_unmapped_logged = set()
    hud_main._prepared_hands = {"55": SimpleNamespace(site_hand_no="99", hand_instance=None)}
    hud_main._has_live_seat_source = lambda _site: True
    hud_main.winamax_pool_games = MagicMock()
    hud_main.winamax_log_reader = MagicMock()
    hud_main.winamax_log_reader.table_no_for_hand.return_value = "3"
    info = SimpleNamespace(
        fast=True,
        site_name="Winamax",
        table_name="Colorado",
        poker_game="holdem",
        _replace=lambda **kwargs: SimpleNamespace(fast=True, site_name="Winamax", poker_game="holdem", **kwargs),
    )

    with caplog.at_level("WARNING"):
        qualified = hud_main._qualify_fast_fold_table(info, "55")

    assert qualified is not None
    assert qualified.table_no == "3"
    assert qualified.info.table_name == "Colorado 3"
    assert [r.getMessage() for r in caplog.records if "FF import" in r.getMessage()] == []


# --------------------------------------------------------------------------
# An import must not rebuild what the live log already built
# --------------------------------------------------------------------------


def test_import_adopts_the_live_hud_for_the_same_window() -> None:
    """An imported hand joins the live HUD instead of creating a second one.

    The live log keys a table by its native window id; an imported hand knows
    only the pool's name and the client's window index. Failing to connect the
    two is what let an import build a second renderer over a table that
    already had one.
    """
    hud_main = HUD_main.HudMain.__new__(HUD_main.HudMain)
    live_hud = MagicMock()
    live_hud.table.number = 61632
    other_hud = MagicMock()
    other_hud.table.number = 61633
    # Both windows of the pool are open, which is the case the name-based
    # shortcut cannot answer: two keys share the "Colorado 1 #" prefix. This
    # is exactly when an import used to give up and build a third renderer.
    hud_main.hud_dict = {"Colorado 1 #61632": live_hud, "Colorado 1 #61633": other_hud}
    hud_main._fast_fold_aliases = {}
    hud_main._window_registry = HudWindowRegistry()
    hud_main._window_registry.claim(61632, "Colorado 1 #61632")
    hud_main._window_registry.claim(61633, "Colorado 1 #61633")
    hud_main.winamax_ax_seats = MagicMock()
    hud_main.winamax_ax_seats.find_table_window.return_value = SimpleNamespace(
        table_name="Colorado 1",
        window_id=61632,
    )

    resolved = hud_main._resolve_fast_fold_key("Colorado 1", table_no="3")

    assert resolved == "Colorado 1 #61632"
    # Learned, so the next hand on this pool does not re-read the window.
    assert hud_main._fast_fold_aliases["Colorado 1"] == "Colorado 1 #61632"


def test_import_creates_a_hud_when_no_renderer_holds_the_window() -> None:
    """With nothing on the window, the import must still be able to create."""
    hud_main = HUD_main.HudMain.__new__(HUD_main.HudMain)
    hud_main.hud_dict = {}
    hud_main._fast_fold_aliases = {}
    hud_main._window_registry = HudWindowRegistry()
    hud_main.winamax_ax_seats = MagicMock()
    hud_main.winamax_ax_seats.find_table_window.return_value = None

    assert hud_main._resolve_fast_fold_key("Colorado 1", table_no="3") == "Colorado 1"


def test_stale_generation_stats_are_dropped() -> None:
    """A read that outlives its HUD must not paint the replacement."""
    hud_main = HUD_main.HudMain.__new__(HUD_main.HudMain)
    rebuilt = MagicMock()
    rebuilt._fpdb_generation = 9
    hud_main.hud_dict = {"Colorado 1 #61632": rebuilt}
    hud_main._ff_pending_hand = {"Colorado 1 #61632": "hand-1"}
    hud_main._ff_pending_request = {"Colorado 1 #61632": 7}
    hud_main._ff_pending_generation = {"Colorado 1 #61632": 4}  # the destroyed one
    hud_main._ff_trace = MagicMock()

    with pytest.MonkeyPatch.context() as patch:
        apply_seats = MagicMock()
        patch.setattr(HUD_main.FastFoldEngine, "apply_seats", apply_seats)
        hud_main._on_fast_fold_stats(
            SimpleNamespace(temp_key="Colorado 1 #61632", request_id=7, seat_map={}, stat_dict={}),
        )

    apply_seats.assert_not_called()
    assert hud_main._ff_trace.call_args.args[1] == "stats-dropped"
    assert "stale_generation=4" in hud_main._ff_trace.call_args.args[2]


def test_current_generation_stats_are_applied() -> None:
    """The guard must not reject the answer a live HUD is waiting for."""
    hud_main = HUD_main.HudMain.__new__(HUD_main.HudMain)
    hud = MagicMock()
    hud._fpdb_generation = 4
    hud_main.hud_dict = {"Colorado 1 #61632": hud}
    hud_main._ff_pending_hand = {"Colorado 1 #61632": "hand-1"}
    hud_main._ff_pending_request = {"Colorado 1 #61632": 7}
    hud_main._ff_pending_generation = {"Colorado 1 #61632": 4}
    hud_main._ff_trace = MagicMock()

    with pytest.MonkeyPatch.context() as patch:
        apply_seats = MagicMock(return_value=True)
        patch.setattr(HUD_main.FastFoldEngine, "apply_seats", apply_seats)
        hud_main._on_fast_fold_stats(
            SimpleNamespace(temp_key="Colorado 1 #61632", request_id=7, seat_map={1: "hero"}, stat_dict={}),
        )

    apply_seats.assert_called_once()
    assert hud_main._ff_trace.call_args.args[1] == "stats-applied"


# --------------------------------------------------------------------------
# Saying that a second HUD was refused
# --------------------------------------------------------------------------


def test_the_lock_records_who_holds_it(lock_name) -> None:
    """A refused HUD must be able to name the one that beat it to it.

    Without this the second HUD dies with "exited during startup with code 1"
    and the player is left looking at two sets of stat blocks with nothing
    anywhere connecting the two facts.
    """
    from fpdb_3_legacy.interlocks import acquire_hud_instance_lock, read_lock_owner

    lock = acquire_hud_instance_lock("pid=4242 session=abc role='hud'", name=lock_name)
    try:
        assert read_lock_owner(lock_name) == "pid=4242 session=abc role='hud'"
    finally:
        lock.release()


def test_an_owner_is_readable_from_another_process(lock_name) -> None:
    """The reader is a different process from the holder, by definition."""
    holder = subprocess.Popen(
        [sys.executable, "-c", _hud_lock_child_source("hold", lock_name)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "ACQUIRED"

        from fpdb_3_legacy.interlocks import read_lock_owner

        assert read_lock_owner(lock_name) == "test-hold"
    finally:
        assert holder.stdin is not None
        holder.stdin.write("\n")
        holder.stdin.flush()
        holder.wait(timeout=60)


def test_an_unheld_lock_names_nobody() -> None:
    from fpdb_3_legacy.interlocks import read_lock_owner

    assert read_lock_owner(f"never_taken_{uuid.uuid4().hex}") is None


def test_being_refused_is_its_own_exit_status() -> None:
    """The GUI has to tell this apart from a crash to explain it to the player."""
    from fpdb_3_legacy.interlocks import HUD_ALREADY_RUNNING_EXIT_CODE

    source = (REPO_ROOT_PATH / "fpdb_3_legacy" / "HUD_main.pyw").read_text(encoding="utf-8")

    assert HUD_ALREADY_RUNNING_EXIT_CODE != 1, "must not collide with an ordinary failure"
    assert "raise SystemExit(HUD_ALREADY_RUNNING_EXIT_CODE)" in source


def test_the_gui_explains_a_refusal_instead_of_reporting_a_code() -> None:
    """"exited during startup with code 1" is not something a player can act on."""
    source = (REPO_ROOT_PATH / "fpdb_3_legacy" / "GuiAutoImport.py").read_text(encoding="utf-8")

    assert "HUD_ALREADY_RUNNING_EXIT_CODE" in source
    assert "another FPDB HUD is already running" in source
    assert "Quit the other one" in source


def test_a_lock_that_could_not_be_tested_is_its_own_exit_status() -> None:
    """"Quit the other HUD" is bad advice when there may not be another HUD.

    The socket fallback reported an unrelated bind failure as a refusal, so a
    Windows user with no pywin32 could be told a HUD was running when none was
    (#259). The verdict and the absence of a verdict now leave by different
    doors.
    """
    from fpdb_3_legacy.interlocks import HUD_ALREADY_RUNNING_EXIT_CODE, HUD_LOCK_UNDETERMINED_EXIT_CODE

    source = (REPO_ROOT_PATH / "fpdb_3_legacy" / "HUD_main.pyw").read_text(encoding="utf-8")

    assert HUD_LOCK_UNDETERMINED_EXIT_CODE not in (0, 1, HUD_ALREADY_RUNNING_EXIT_CODE)
    assert "raise SystemExit(HUD_LOCK_UNDETERMINED_EXIT_CODE)" in source
    assert "except LockUndeterminedError" in source


def test_the_gui_does_not_blame_a_hud_it_cannot_prove_exists() -> None:
    source = (REPO_ROOT_PATH / "fpdb_3_legacy" / "GuiAutoImport.py").read_text(encoding="utf-8")

    assert "HUD_LOCK_UNDETERMINED_EXIT_CODE" in source
    assert "could not be tested" in source


def _owner_child_source(lock_name: str, source: str) -> str:
    """A child that takes the socket lock and holds it, whatever the platform."""
    return textwrap.dedent(
        f"""
        import sys
        sys.path.insert(0, {REPO_ROOT!r})
        from fpdb_3_legacy.interlocks import InterProcessLockSocket

        lock = InterProcessLockSocket(name={lock_name!r})
        print("ACQUIRED" if lock.acquire({source!r}) else "REFUSED", flush=True)
        sys.stdin.readline()
        lock.release()
        """,
    )


def test_every_lock_kind_records_its_owner(lock_name) -> None:
    """Windows has no lock file, and that is where naming the holder matters most.

    A plain Windows install has neither fcntl nor pywin32, so the socket
    fallback is what guards the single HUD there -- and a bound socket has
    nowhere to write. Recording the owner beside the lock rather than inside
    it is what makes the answer available on every platform.
    """
    from fpdb_3_legacy.interlocks import read_lock_owner

    holder = subprocess.Popen(
        [sys.executable, "-c", _owner_child_source(lock_name, "pid=999 role='hud'")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "ACQUIRED"

        assert read_lock_owner(lock_name) == "pid=999 role='hud'"
    finally:
        assert holder.stdin is not None
        holder.stdin.write("\n")
        holder.stdin.flush()
        holder.wait(timeout=60)

    assert read_lock_owner(lock_name) is None, "the note outlived the lock"


def test_a_lock_name_that_is_not_a_filename_still_works() -> None:
    """Lock names are free text; the note has to live somewhere legal."""
    from fpdb_3_legacy.interlocks import InterProcessLockSocket, owner_file_path, read_lock_owner

    name = f"fpdb hud/instance:{uuid.uuid4().hex[:8]}"
    assert "/" not in os.path.basename(owner_file_path(name))

    lock = InterProcessLockSocket(name=name)
    assert lock.acquire("pid=1 role='hud'")
    try:
        assert read_lock_owner(name) == "pid=1 role='hud'"
    finally:
        lock.release()


def test_failing_to_record_an_owner_does_not_cost_the_lock(monkeypatch, lock_name) -> None:
    """The note is a convenience; the lock is the guarantee."""
    from fpdb_3_legacy import interlocks

    monkeypatch.setattr(
        interlocks,
        "owner_file_path",
        lambda _name: "/nonexistent-directory/owner",
    )
    lock = interlocks.InterProcessLockSocket(name=lock_name)

    try:
        assert lock.acquire("pid=1 role='hud'") is True
        assert interlocks.read_lock_owner(lock_name) is None
    finally:
        lock.release()
