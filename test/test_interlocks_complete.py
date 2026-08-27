"""The lock machinery in full: every mechanism, every failure, every platform.

``interlocks`` carries the single-HUD guarantee. Two HUD processes each draw
their own stat blocks over every table, so a lock that quietly admits both is
not a nuisance -- it is the bug, and it already shipped once: the socket
fallback derived its port from ``hash()``, which Python salts per process, so
every process bound a different port and none ever collided.

Three mechanisms are chosen at import time by what the platform can import,
which means two of the three are dead code on any given machine. They are all
exercised here against stand-in bindings, so a macOS developer sees a Windows
mutex regression and a Windows developer sees an fcntl one.
"""

from __future__ import annotations

import doctest
import errno
import os
import socket
import sys
import types
import uuid
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fpdb_3_legacy import interlocks


@pytest.fixture
def restore_bindings():
    """Put the real platform bindings back.

    ``select_lock_class`` writes what it imported into the module's globals,
    because each lock class reads them there. Calling it with a stand-in
    would otherwise leave the module holding that stand-in for every test
    after it.
    """
    names = ("fcntl", "win32api", "win32event", "winerror")
    saved = {attribute: getattr(interlocks, attribute) for attribute in names}
    yield
    for attribute, value in saved.items():
        setattr(interlocks, attribute, value)


@pytest.fixture
def name() -> str:
    """A lock nobody else is contending for."""
    return f"fpdb_interlocks_test_{os.getpid()}_{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# The single-HUD entry point
# ---------------------------------------------------------------------------


def test_acquiring_a_free_hud_lock_hands_it_over(name) -> None:
    lock = interlocks.acquire_hud_instance_lock("pid=1 role='hud'", name=name)
    try:
        assert lock.locked() is True
    finally:
        lock.release()


def test_acquiring_a_held_hud_lock_is_refused(name) -> None:
    """The refusal is an exception, not a falsy return: callers must not miss it."""
    held = interlocks.acquire_hud_instance_lock("pid=1 role='hud'", name=name)
    try:
        with pytest.raises(interlocks.SingleInstanceError, match="already running"):
            interlocks.acquire_hud_instance_lock("pid=2 role='hud'", name=name)
    finally:
        held.release()


# ---------------------------------------------------------------------------
# Waiting rather than failing
# ---------------------------------------------------------------------------


def test_a_waiting_caller_retries_until_the_lock_is_free(monkeypatch, name) -> None:
    """``wait=True`` is used by the importer's global lock, not by the HUD."""
    lock = interlocks.InterProcessLock(name=name)
    attempts = {"n": 0}
    real_acquire_impl = lock.acquire_impl

    def busy_twice(wait):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise interlocks.SingleInstanceError(name)
        real_acquire_impl(wait)

    monkeypatch.setattr(lock, "acquire_impl", busy_twice)
    monkeypatch.setattr(interlocks.time, "sleep", lambda _seconds: None)

    try:
        assert lock.acquire("waiting", wait=True, retry_time=0) is True
        assert attempts["n"] == 3
    finally:
        lock.release()


def test_a_waiting_caller_does_not_retry_a_lock_it_could_not_test(monkeypatch, name) -> None:
    """Waiting for an untestable lock waits for nothing.

    ``SingleInstanceError`` means "taken", and taken locks get given back, so
    retrying is sound. ``LockUndeterminedError`` means the mechanism never
    answered -- a bind failing with ENETDOWN does not become a free port
    because a second elapsed. Retrying it spins until the user gives up.
    """
    lock = interlocks.InterProcessLock(name=name)
    attempts = {"n": 0}

    def never_answers(_wait):
        attempts["n"] += 1
        raise interlocks.LockUndeterminedError("the mechanism is broken")

    monkeypatch.setattr(lock, "acquire_impl", never_answers)
    monkeypatch.setattr(interlocks.time, "sleep", lambda _seconds: None)

    with pytest.raises(interlocks.LockUndeterminedError):
        lock.acquire("waiting", wait=True, retry_time=0)

    assert attempts["n"] == 1


def test_a_refusal_keeps_the_reason_the_mechanism_gave(monkeypatch, name) -> None:
    """``acquire`` reports refusal as a bare False, which throws the reason away."""
    lock = interlocks.InterProcessLock(name=name)

    def refuse(_wait):
        raise interlocks.SingleInstanceError("port 20001 is already bound")

    monkeypatch.setattr(lock, "acquire_impl", refuse)

    assert lock.acquire("refused") is False
    assert lock.last_error == "port 20001 is already bound"


def test_a_later_success_clears_the_previous_reason(name) -> None:
    lock = interlocks.InterProcessLock(name=name)
    lock.last_error = "stale"

    assert lock.acquire("first") is True
    try:
        assert lock.last_error is None
    finally:
        lock.release()


def test_the_hud_refusal_names_the_port_rather_than_only_the_verdict(monkeypatch, name) -> None:
    """The user is shown "already running"; the reason has to travel with it.

    Without this the improved bind messages reach the debug log and nowhere
    else, and every refusal reads identically whatever caused it (#259).
    """

    def refuse(_self, _wait):
        raise interlocks.SingleInstanceError(f"Could not acquire exclusive lock on {name}: port 20001 is already bound")

    monkeypatch.setattr(interlocks.InterProcessLock, "acquire_impl", refuse)

    with pytest.raises(interlocks.SingleInstanceError) as excinfo:
        interlocks.acquire_hud_instance_lock("pid=2 role='hud'", name=name)

    message = str(excinfo.value)
    assert "already running" in message
    assert "port 20001" in message


def test_an_untestable_lock_reaches_the_hud_entry_point_as_its_own_error(monkeypatch, name) -> None:
    """The HUD exits on a different code for it, so the GUI can say something true."""

    def never_answers(_self, _wait):
        raise interlocks.LockUndeterminedError("binding port 20001 failed (Network is down)")

    monkeypatch.setattr(interlocks.InterProcessLock, "acquire_impl", never_answers)

    with pytest.raises(interlocks.LockUndeterminedError):
        interlocks.acquire_hud_instance_lock("pid=2 role='hud'", name=name)


def test_the_two_refusals_stay_distinguishable() -> None:
    """A subclass, so old callers keep refusing; distinct, so new ones can tell."""
    assert issubclass(interlocks.LockUndeterminedError, interlocks.SingleInstanceError)
    assert interlocks.HUD_LOCK_UNDETERMINED_EXIT_CODE != interlocks.HUD_ALREADY_RUNNING_EXIT_CODE


def test_the_same_process_cannot_take_a_lock_twice(name) -> None:
    """Re-entering would let one process believe it is two."""
    lock = interlocks.InterProcessLock(name=name)
    assert lock.acquire("first") is True
    try:
        assert lock.acquire("second") is False
    finally:
        lock.release()


def test_an_unnamed_lock_falls_back_to_the_program_name() -> None:
    lock = interlocks.InterProcessLockBase()

    assert lock.name == sys.argv[0]


def test_a_source_of_none_is_still_recorded_as_something(name) -> None:
    lock = interlocks.InterProcessLock(name=name)
    assert lock.acquire(None) is True
    try:
        assert lock.heldBy == "Unknown"
    finally:
        lock.release()


# ---------------------------------------------------------------------------
# Recording who holds it
# ---------------------------------------------------------------------------


def test_the_owner_note_lives_somewhere_legal(name) -> None:
    path = interlocks.owner_file_path("fpdb hud/instance:1")

    assert os.path.dirname(path)
    assert "/" not in os.path.basename(path)
    assert os.path.basename(path).endswith(".owner")


def test_an_empty_note_reads_as_nobody(name) -> None:
    """A truncated write must not be reported as an owner called ''."""
    with open(interlocks.owner_file_path(name), "w", encoding="utf-8") as handle:
        handle.write("   ")
    try:
        assert interlocks.read_lock_owner(name) is None
    finally:
        os.unlink(interlocks.owner_file_path(name))


def test_forgetting_a_note_that_is_not_there_is_harmless(name) -> None:
    interlocks.InterProcessLock(name=name)._forget_owner()


# ---------------------------------------------------------------------------
# The fcntl mechanism
# ---------------------------------------------------------------------------


@pytest.fixture
def fcntl_lock(monkeypatch, tmp_path, name):
    """A file lock driven by stand-in fcntl bindings, on any platform.

    Windows has no fcntl and no ``/tmp``, so these methods used to be skipped
    there -- which left the class uncovered on the one platform that cannot
    run it for real, exactly the asymmetry this file exists to remove. The
    bindings and the lock directory are both supplied, so the class runs
    everywhere and a Windows developer sees an fcntl regression.
    """
    calls: list[tuple[str, int]] = []

    def flock(_fd, options):
        calls.append(("flock", options))

    def lockf(_fd, options):
        calls.append(("lockf", options))

    fake = types.ModuleType("fcntl")
    fake.LOCK_EX, fake.LOCK_NB, fake.LOCK_UN = 2, 4, 8
    fake.flock, fake.lockf = flock, lockf
    monkeypatch.setattr(interlocks, "fcntl", fake)
    monkeypatch.setattr(interlocks, "LOCK_FILE_DIRECTORY", str(tmp_path))

    return types.SimpleNamespace(
        lock=interlocks.InterProcessLockFcntl(name=name),
        fake=fake,
        calls=calls,
        directory=tmp_path,
    )


def test_the_lock_file_is_named_after_the_lock(fcntl_lock, name) -> None:
    assert fcntl_lock.lock.lock_file_name.startswith(str(fcntl_lock.directory))
    assert name in fcntl_lock.lock.lock_file_name
    assert fcntl_lock.lock.lock_file_name.endswith(".lck")


def test_characters_a_filename_cannot_hold_are_replaced(fcntl_lock) -> None:
    fcntl_lock.lock.name = "a/b?c<d>e:f;g*h|i'j\"k^l=m.n[o]p"

    assert set(fcntl_lock.lock.getHashedName()) <= set("abcdefghijklmnop_")


def test_taking_the_lock_asks_for_an_exclusive_non_blocking_flock(fcntl_lock) -> None:
    """Non-blocking is what turns "already held" into a refusal, not a hang."""
    assert fcntl_lock.lock.acquire("test") is True

    assert fcntl_lock.calls == [("flock", fcntl_lock.fake.LOCK_EX | fcntl_lock.fake.LOCK_NB)]
    assert os.path.isfile(fcntl_lock.lock.lock_file_name)


def test_waiting_for_the_lock_drops_the_non_blocking_flag(fcntl_lock) -> None:
    fcntl_lock.lock.acquire_impl(wait=True)

    assert fcntl_lock.calls == [("flock", fcntl_lock.fake.LOCK_EX)]


def test_a_refused_flock_closes_the_file_it_opened(fcntl_lock) -> None:
    """Leaving the descriptor open would leak one per refused attempt."""
    fcntl_lock.fake.flock = MagicMock(side_effect=OSError("would block"))

    with pytest.raises(interlocks.SingleInstanceError, match="Could not acquire"):
        fcntl_lock.lock.acquire_impl(wait=False)

    assert fcntl_lock.lock.lockfd is None


def test_releasing_unlocks_closes_and_removes_the_file(fcntl_lock) -> None:
    fcntl_lock.lock.acquire("test")
    path = fcntl_lock.lock.lock_file_name

    fcntl_lock.lock.release()

    assert ("lockf", fcntl_lock.fake.LOCK_UN) in fcntl_lock.calls
    assert fcntl_lock.lock.lockfd is None
    assert not os.path.exists(path)


def test_a_lock_file_that_vanished_does_not_break_release(fcntl_lock, monkeypatch) -> None:
    """The flock is the guarantee; the file is bookkeeping."""
    fcntl_lock.lock.acquire("test")
    monkeypatch.setattr(interlocks.os, "unlink", MagicMock(side_effect=OSError("gone")))

    fcntl_lock.lock.release()

    assert fcntl_lock.lock._has_lock is False


def test_a_missing_lock_directory_is_refused_at_construction(monkeypatch, name) -> None:
    """Silently writing the lock somewhere else would exclude nobody."""
    monkeypatch.setattr(interlocks, "LOCK_FILE_DIRECTORY", "/nonexistent-lock-directory")

    with pytest.raises(AssertionError):
        interlocks.InterProcessLockFcntl(name=name)


# ---------------------------------------------------------------------------
# The Windows mutex, on any platform
# ---------------------------------------------------------------------------


@pytest.fixture
def win32(monkeypatch):
    """Stand-in pywin32 bindings, so the mutex path runs anywhere."""
    api = types.SimpleNamespace(GetLastError=MagicMock(return_value=0), CloseHandle=MagicMock())
    event = types.SimpleNamespace(CreateMutex=MagicMock(return_value="handle"), ReleaseMutex=MagicMock())
    error = types.SimpleNamespace(ERROR_ALREADY_EXISTS=183)
    monkeypatch.setattr(interlocks, "win32api", api, raising=False)
    monkeypatch.setattr(interlocks, "win32event", event, raising=False)
    monkeypatch.setattr(interlocks, "winerror", error, raising=False)
    return types.SimpleNamespace(api=api, event=event, error=error)


def test_a_free_mutex_is_acquired(win32, name) -> None:
    lock = interlocks.InterProcessLockWin32(name=name)

    assert lock.acquire("test") is True
    assert lock.mutex == "handle"


def test_an_existing_mutex_refuses_and_closes_its_handle(win32, name) -> None:
    """Leaking the handle would keep the mutex alive after the refusal."""
    win32.api.GetLastError.return_value = win32.error.ERROR_ALREADY_EXISTS
    lock = interlocks.InterProcessLockWin32(name=name)

    assert lock.acquire("test") is False
    assert lock.mutex is None
    win32.api.CloseHandle.assert_called_once_with("handle")


def test_a_refusal_with_no_handle_closes_nothing(win32, name) -> None:
    win32.api.GetLastError.return_value = win32.error.ERROR_ALREADY_EXISTS
    win32.event.CreateMutex.return_value = None
    lock = interlocks.InterProcessLockWin32(name=name)

    assert lock.acquire("test") is False
    win32.api.CloseHandle.assert_not_called()


def test_releasing_a_mutex_gives_it_back_and_closes_it(win32, name) -> None:
    lock = interlocks.InterProcessLockWin32(name=name)
    lock.acquire("test")

    lock.release()

    win32.event.ReleaseMutex.assert_called_once_with("handle")
    win32.api.CloseHandle.assert_called_once_with("handle")
    assert lock.mutex is None


def test_releasing_a_mutex_that_will_not_go_is_survived(win32, name) -> None:
    """A handle the OS has already reclaimed must not take the process down."""
    win32.event.ReleaseMutex.side_effect = OSError("invalid handle")
    win32.api.CloseHandle.side_effect = OSError("invalid handle")
    lock = interlocks.InterProcessLockWin32(name=name)
    lock.acquire("test")

    lock.release()

    assert lock.mutex is None


def test_releasing_a_mutex_never_taken_is_harmless(win32, name) -> None:
    interlocks.InterProcessLockWin32(name=name).release_impl()


# ---------------------------------------------------------------------------
# The socket mechanism
# ---------------------------------------------------------------------------


def test_a_second_socket_lock_in_one_process_is_refused(name) -> None:
    """Binding the port twice is what the refusal is made of."""
    first = interlocks.InterProcessLockSocket(name=name)
    second = interlocks.InterProcessLockSocket(name=name)
    assert first.acquire("first") is True
    try:
        assert second.acquire("second") is False
        assert second.socket is None
    finally:
        first.release()


def test_a_released_socket_lock_can_be_taken_again(name) -> None:
    lock = interlocks.InterProcessLockSocket(name=name)
    assert lock.acquire("first") is True
    lock.release()

    assert lock.acquire("second") is True
    lock.release()


def test_a_busy_port_is_reported_as_a_busy_port(name, monkeypatch) -> None:
    """A bound port is reported as contention, not an unexplained failure."""
    lock = interlocks.InterProcessLockSocket(name=name)

    def refuse(_address):
        raise OSError(errno.EADDRINUSE, "Address already in use")

    monkeypatch.setattr(socket.socket, "bind", lambda self, addr: refuse(addr))

    with pytest.raises(interlocks.SingleInstanceError) as excinfo:
        lock.acquire_impl(wait=False)

    assert str(lock.portno) in str(excinfo.value)
    assert "already bound" in str(excinfo.value)


def test_a_bind_that_fails_for_another_reason_is_not_called_a_second_hud(name, monkeypatch) -> None:
    """A broken socket environment is reported distinctly from contention."""
    lock = interlocks.InterProcessLockSocket(name=name)

    def refuse(_address):
        raise OSError(errno.ENETDOWN, "Network is down")

    monkeypatch.setattr(socket.socket, "bind", lambda self, addr: refuse(addr))

    with pytest.raises(interlocks.LockUndeterminedError) as excinfo:
        lock.acquire_impl(wait=False)

    message = str(excinfo.value)
    assert "could not test the lock" in message.lower()
    assert "Network is down" in message


def test_a_busy_port_is_not_reported_as_an_untestable_lock(name, monkeypatch) -> None:
    """EADDRINUSE is an answer, and the only one the lock can act on."""
    lock = interlocks.InterProcessLockSocket(name=name)

    def refuse(_address):
        raise OSError(errno.EADDRINUSE, "Address already in use")

    monkeypatch.setattr(socket.socket, "bind", lambda self, addr: refuse(addr))

    with pytest.raises(interlocks.SingleInstanceError) as excinfo:
        lock.acquire_impl(wait=False)

    assert not isinstance(excinfo.value, interlocks.LockUndeterminedError)


def test_the_socket_asks_windows_for_a_bind_that_means_something(name, monkeypatch) -> None:
    """Without SO_EXCLUSIVEADDRUSE a Windows bind is not proof the port was free.

    Another process asking for SO_REUSEADDR can bind a port this lock already
    holds, which would let a second HUD through the one guard a plain Windows
    install has. The option exists only on Windows, so it is injected here to
    be exercised on every runner.
    """
    monkeypatch.setattr(socket, "SO_EXCLUSIVEADDRUSE", 4, raising=False)
    options: list[tuple[int, int, int]] = []
    real_setsockopt = socket.socket.setsockopt

    def record(self, level, option, value) -> None:
        options.append((level, option, value))
        if option != 4:  # the stand-in is not a real option on this platform
            real_setsockopt(self, level, option, value)

    monkeypatch.setattr(socket.socket, "setsockopt", record)

    lock = interlocks.InterProcessLockSocket(name=name)
    lock.acquire_impl(wait=False)
    try:
        assert (socket.SOL_SOCKET, 4, 1) in options
    finally:
        lock.release_impl()


def test_a_platform_without_the_option_still_binds(name, monkeypatch) -> None:
    """Everywhere but Windows there is no such option, and no need for one."""
    monkeypatch.delattr(socket, "SO_EXCLUSIVEADDRUSE", raising=False)

    lock = interlocks.InterProcessLockSocket(name=name)
    assert lock.acquire("only-holder") is True
    lock.release()


def test_the_port_stays_inside_the_range_it_declares() -> None:
    for candidate in ("a", "fpdb_hud_instance", "x" * 200, ""):
        port = interlocks.port_for_lock_name(candidate)
        assert interlocks._LOCK_PORT_BASE <= port < interlocks._LOCK_PORT_BASE + interlocks._LOCK_PORT_SPAN


def test_the_port_never_lands_in_the_range_the_os_allocates_from() -> None:
    """The lock must not contend with the OS for its own identifier."""
    for i in range(5000):
        port = interlocks.port_for_lock_name(f"fpdb_hud_instance_test_{i}_{i * 7919:x}")
        assert 1024 < port < 32768


# ---------------------------------------------------------------------------
# Which mechanism the platform gets
# ---------------------------------------------------------------------------


def test_the_chosen_mechanism_is_one_of_the_three() -> None:
    assert interlocks.InterProcessLock in (
        interlocks.InterProcessLockFcntl,
        interlocks.InterProcessLockWin32,
        interlocks.InterProcessLockSocket,
    )


@pytest.mark.parametrize(
    ("present", "expected"),
    [
        (("fcntl",), "InterProcessLockFcntl"),
        (("win32api", "win32event", "winerror"), "InterProcessLockWin32"),
        ((), "InterProcessLockSocket"),
    ],
    ids=["unix", "windows-with-pywin32", "windows-without-pywin32"],
)
def test_the_platform_picks_the_first_mechanism_it_can_import(present, expected, monkeypatch, restore_bindings) -> None:
    """Two of the three branches are dead code on any given machine.

    Every binding is supplied or withheld explicitly rather than left to the
    host: an earlier version only blocked what should be absent, so the
    "unix" case passed on macOS and picked the Windows mutex on Windows,
    where ``import fcntl`` really does fail.

    The case that matters most is the last one. A plain Windows install has
    neither fcntl nor pywin32 and lands on the socket lock -- the branch a
    developer is least likely to be running, and the one that shipped a lock
    which excluded nobody.
    """
    for binding in ("fcntl", "win32api", "win32event", "winerror"):
        monkeypatch.setitem(sys.modules, binding, types.ModuleType(binding) if binding in present else None)

    assert interlocks.select_lock_class().__name__ == expected


def test_the_windows_bindings_land_where_the_mutex_reads_them(monkeypatch, restore_bindings) -> None:
    """InterProcessLockWin32 reads them as module globals, not as locals."""
    monkeypatch.setitem(sys.modules, "fcntl", None)
    modules = {name: types.ModuleType(name) for name in ("win32api", "win32event", "winerror")}
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    assert interlocks.select_lock_class() is interlocks.InterProcessLockWin32
    assert interlocks.win32api is modules["win32api"]


# ---------------------------------------------------------------------------
# The command line
# ---------------------------------------------------------------------------


def test_no_arguments_prints_the_help(capsys) -> None:
    assert interlocks.main([]) == 0

    assert "FPDB Inter-process locks utility" in capsys.readouterr().out


def test_the_doctest_suite_can_be_run(monkeypatch, capsys) -> None:
    monkeypatch.setattr(doctest, "testmod", lambda **_kwargs: types.SimpleNamespace(failed=0, attempted=7))

    assert interlocks.main(["--test"]) == 0
    assert "All 7 doctests passed" in capsys.readouterr().out


def test_a_failing_doctest_is_a_failing_command(monkeypatch, capsys) -> None:
    monkeypatch.setattr(doctest, "testmod", lambda **_kwargs: types.SimpleNamespace(failed=2, attempted=7))

    assert interlocks.main(["--interactive"]) == 1
    assert "2/7 doctests failed" in capsys.readouterr().out


def test_a_crashing_doctest_is_reported_not_raised(monkeypatch, capsys) -> None:
    def explode(**_kwargs):
        msg = "no such attribute"
        raise ValueError(msg)

    monkeypatch.setattr(doctest, "testmod", explode)

    assert interlocks.main(["--test"]) == 1
    assert "Doctests crashed" in capsys.readouterr().out


def test_the_demo_takes_and_gives_back_a_lock(monkeypatch, capsys) -> None:
    monkeypatch.setattr(interlocks.time, "sleep", lambda _seconds: None)

    assert interlocks.main(["--demo"]) == 0

    out = capsys.readouterr().out
    assert "Lock acquired successfully" in out
    assert "Lock released" in out


def test_the_demo_says_so_when_the_lock_is_held(monkeypatch, capsys) -> None:
    monkeypatch.setattr(interlocks, "InterProcessLock", lambda _name: MagicMock(acquire=lambda *a, **k: False))

    assert interlocks.main(["--demo"]) == 0
    assert "Could not acquire lock" in capsys.readouterr().out


def test_a_demo_that_raises_is_a_failing_command(monkeypatch, capsys) -> None:
    def explode(_name):
        msg = "no lock directory"
        raise OSError(msg)

    monkeypatch.setattr(interlocks, "InterProcessLock", explode)

    assert interlocks.main(["--demo"]) == 1
    assert "Error during demo" in capsys.readouterr().out


def test_listing_shows_the_lock_files_it_finds(monkeypatch, tmp_path, capsys) -> None:
    (tmp_path / "fpdb_global_lock.lck").write_text("")
    (tmp_path / "fpdb_hud_instance.lck").write_text("")  # no "lock" in the name
    (tmp_path / "unrelated.txt").write_text("")
    monkeypatch.setattr(interlocks.tempfile, "gettempdir", lambda: str(tmp_path))

    assert interlocks.main(["--list-locks"]) == 0

    out = capsys.readouterr().out
    assert "fpdb_global_lock.lck" in out
    assert "unrelated.txt" not in out
    assert "fpdb_hud_instance.lck" not in out, "the filter wants 'lock' in the name"


def test_listing_says_so_when_there_are_none(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(interlocks.tempfile, "gettempdir", lambda: str(tmp_path))

    assert interlocks.main(["--list-locks"]) == 0
    assert "No FPDB lock files found" in capsys.readouterr().out


def test_a_temp_directory_that_cannot_be_read_is_reported(monkeypatch, capsys) -> None:
    monkeypatch.setattr(interlocks.os, "listdir", MagicMock(side_effect=OSError("permission denied")))

    assert interlocks.main(["--list-locks"]) == 0
    assert "Error listing locks" in capsys.readouterr().out


def test_the_module_runs_its_own_command_line() -> None:
    """``python -m fpdb_3_legacy.interlocks`` has to reach main()."""
    source = (
        __import__("pathlib").Path(__file__).resolve().parent.parent / "fpdb_3_legacy" / "interlocks.py"
    ).read_text(encoding="utf-8")

    assert 'if __name__ == "__main__":' in source
    assert "sys.exit(main())" in source


# ---------------------------------------------------------------------------
# The last corners
# ---------------------------------------------------------------------------


def test_a_note_that_cannot_be_read_names_nobody(monkeypatch, name) -> None:
    """A permissions problem on the temp directory is not an owner."""
    monkeypatch.setattr(interlocks, "owner_file_path", lambda _n: "/nonexistent-directory/x.owner")

    assert interlocks.read_lock_owner(name) is None


def test_a_note_that_cannot_be_written_is_shrugged_off(monkeypatch, name) -> None:
    """Best-effort: losing the note must not cost the caller the lock.

    The write is attempted after the lock is already held, so an exception
    escaping here would hand back a failure for a lock the caller owns.
    """
    monkeypatch.setattr(interlocks, "owner_file_path", lambda _n: "/nonexistent-directory/x.owner")
    lock = interlocks.InterProcessLock(name=name)

    try:
        assert lock.acquire("pid=1 role='hud'") is True
        assert lock.heldBy == "pid=1 role='hud'"
    finally:
        lock.release()


def test_the_base_class_locks_nothing_by_itself(name) -> None:
    """acquire_impl is the hook each mechanism fills in."""
    assert interlocks.InterProcessLockBase(name=name).acquire_impl(wait=False) is None


def test_an_unheld_lock_reports_itself_unlocked(name) -> None:
    """``locked`` answers by trying, so it must give back what it took."""
    lock = interlocks.InterProcessLock(name=name)

    assert lock.locked() is False
    assert lock.acquire("after the check") is True
    lock.release()


def test_the_command_line_defaults_to_the_real_argv(monkeypatch, capsys) -> None:
    monkeypatch.setattr(interlocks.sys, "argv", ["interlocks.py"])

    assert interlocks.main() == 0
    assert "FPDB Inter-process locks utility" in capsys.readouterr().out


def test_a_directory_entry_that_is_not_a_file_is_skipped(monkeypatch, tmp_path, capsys) -> None:
    """A directory called fpdb-lock-something is not a lock."""
    (tmp_path / "fpdb_lock_dir").mkdir()
    monkeypatch.setattr(interlocks.tempfile, "gettempdir", lambda: str(tmp_path))

    assert interlocks.main(["--list-locks"]) == 0
    assert "No FPDB lock files found" in capsys.readouterr().out


def test_running_the_module_as_a_command_exits_with_its_status(monkeypatch) -> None:
    """``python -m fpdb_3_legacy.interlocks`` must carry the status out."""
    import runpy

    monkeypatch.setattr(interlocks.sys, "argv", ["interlocks.py"])
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("fpdb_3_legacy.interlocks", run_name="__main__")

    assert exit_info.value.code == 0
