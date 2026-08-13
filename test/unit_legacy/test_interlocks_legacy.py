"""Unit tests for the legacy interlocks module (inter-process locks).

Runs on Linux where the fcntl-based InterProcessLockFcntl is selected. Uses
unique lock names per test so the real /tmp lock files never collide.
"""

from __future__ import annotations

import os
import time

import pytest

from fpdb_3_legacy import interlocks
from fpdb_3_legacy.interlocks import (
    _LOCK_PORT_BASE,
    _LOCK_PORT_SPAN,
    InterProcessLock,
    InterProcessLockBase,
    InterProcessLockFcntl,
    InterProcessLockSocket,
    SingleInstanceError,
    main,
)


def _unique_name(tag: str) -> str:
    return f"FpdbInterlockTest_{tag}_{os.getpid()}_{time.time()}"


# The fcntl-based lock is only usable on POSIX systems: `fcntl` is not
# importable on Windows and InterProcessLockFcntl also asserts that the POSIX
# "/tmp" directory exists. Skip the fcntl-specific tests where fcntl is absent.
try:
    import fcntl  # noqa: F401

    HAS_FCNTL = True
except ImportError:
    HAS_FCNTL = False

requires_fcntl = pytest.mark.skipif(
    not HAS_FCNTL,
    reason="fcntl is only available on POSIX systems (not Windows)",
)


@requires_fcntl
def test_default_lock_is_fcntl_on_posix() -> None:
    # fcntl is available on POSIX, so the module selects the fcntl implementation.
    assert InterProcessLock is InterProcessLockFcntl


def test_base_get_hashed_name_is_base64_without_padding() -> None:
    lock = InterProcessLockBase(name="hello world")
    hashed = lock.getHashedName()
    assert "=" not in hashed
    assert isinstance(hashed, str)


def test_base_name_defaults_to_argv0() -> None:
    lock = InterProcessLockBase()
    assert lock.name  # falls back to sys.argv[0], which is non-empty


def test_base_acquire_with_stub_impl() -> None:
    lock = InterProcessLockBase(name=_unique_name("base"))
    # acquire_impl is a no-op in the base class; release_impl is only defined
    # on the concrete subclasses, so we exercise acquire semantics only here.
    assert lock.acquire("src") is True
    assert lock._has_lock is True
    assert lock.heldBy == "src"
    # Second acquire in the same process returns False.
    assert lock.acquire("src2") is False


def test_base_release_without_impl_raises() -> None:
    # The base class has no release_impl, so release() raises AttributeError.
    lock = InterProcessLockBase(name=_unique_name("base_rel"))
    lock.acquire("src")
    with pytest.raises(AttributeError):
        lock.release()


def test_base_acquire_none_source_becomes_unknown() -> None:
    lock = InterProcessLockBase(name=_unique_name("none"))
    assert lock.acquire(None) is True
    assert lock.heldBy == "Unknown"


@requires_fcntl
def test_fcntl_hashed_name_strips_characters_a_path_cannot_hold() -> None:
    # This characterized the opposite until the regex was fixed: it was a
    # literal sequence rather than a character class, so it replaced the
    # exact string /?<>\:;*|'"^=.[] and nothing else, leaving every real name
    # untouched. A name carrying a separator then built a path into another
    # directory, where a second process looking for the same lock would not
    # find it -- and a lock that two processes look for in two places
    # excludes neither.
    assert InterProcessLockFcntl(name="plain_name_123").getHashedName() == "plain_name_123"
    assert InterProcessLockFcntl(name="a/b:c").getHashedName() == "a_b_c"


@requires_fcntl
def test_fcntl_acquire_release_and_locked() -> None:
    name = _unique_name("fcntl")
    lock = InterProcessLockFcntl(name=name)
    assert lock.acquire("test") is True
    assert os.path.isfile(lock.lock_file_name)

    # A different instance on the same name cannot acquire while held.
    other = InterProcessLockFcntl(name=name)
    assert other.acquire("test") is False
    assert other.locked() is True

    lock.release()
    # After release the other instance can take it.
    assert other.acquire("test") is True
    other.release()


@requires_fcntl
def test_fcntl_locked_returns_false_when_free() -> None:
    lock = InterProcessLockFcntl(name=_unique_name("free"))
    assert lock.locked() is False


def test_socket_lock_portno_is_deterministic() -> None:
    # On Linux the socket implementation is not the active one (the `socket`
    # module is only imported when fcntl is unavailable), so acquire_impl would
    # raise NameError here. We can still verify the deterministic port mapping
    # computed in __init__.
    name = _unique_name("sock")
    lock = InterProcessLockSocket(name=name)
    # Read from the module rather than repeated as literals: this assertion
    # hard-coded the old 32782-65530 range, which sat inside the ephemeral
    # range the OS allocates from (#259), and had to be edited by hand when the
    # range moved.
    assert _LOCK_PORT_BASE <= lock.portno < _LOCK_PORT_BASE + _LOCK_PORT_SPAN


def test_main_no_args_prints_help_returns_zero(capsys) -> None:
    assert main([]) == 0
    assert "FPDB Inter-process locks" in capsys.readouterr().out


def test_main_demo_acquires_and_releases(capsys) -> None:
    assert main(["--demo"]) == 0
    assert "Lock acquired successfully" in capsys.readouterr().out


def test_main_list_locks_runs(capsys) -> None:
    assert main(["--list-locks"]) == 0
    assert "Active Lock Files" in capsys.readouterr().out


def test_single_instance_error_is_runtime_error() -> None:
    assert issubclass(SingleInstanceError, RuntimeError)


def test_module_exposes_lock_directory() -> None:
    assert interlocks.LOCK_FILE_DIRECTORY == "/tmp"
