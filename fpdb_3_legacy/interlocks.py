# Code from http://ender.snowburst.org:4747/~jjohns/interlocks.py
from __future__ import annotations

# Thanks JJ!
import base64
import doctest
import errno
import os
import os.path
import re
import socket
import sys
import tempfile
import time
import zlib
from typing import Any

from fpdb_3_legacy.loggingFpdb import get_logger

# import L10n
# _ = L10n.get_translation()


log = get_logger("interlocks")

INTERLOCK_CLI_ERRORS = (AssertionError, OSError, RuntimeError, TypeError, ValueError)
INTERLOCK_LIST_ERRORS = (OSError,)

InterProcessLock: Any = None

# The platform bindings each lock class needs, declared here so they are
# visible to a reader and to static analysis. select_lock_class() fills in
# whichever ones this platform can import; the rest stay None, and the class
# that would have used them is never the one selected.
fcntl: Any = None
win32api: Any = None
win32event: Any = None
winerror: Any = None

"""
Just use me like a thread lock.  acquire() / release() / locked()

Differences compared to thread locks:
1. By default, acquire()'s wait parameter is false.
2. When acquire fails, SingleInstanceError is thrown instead of simply returning false.
3. acquire() can take a 3rd parameter retry_time, which, if wait is True, tells the locking
   mechanism how long to sleep between retrying the lock.  Has no effect for unix/InterProcessLockFcntl.

Differences in fpdb version to JJ's original:
1. Changed acquire() to return false like other locks
2. Made acquire fail if same process already has the lock
"""


class SingleInstanceError(RuntimeError):
    """Thrown when you try to acquire an InterProcessLock and another version of the process is already running."""


HUD_INSTANCE_LOCK_NAME = "fpdb_hud_instance"
"""Name of the machine-wide lock that admits exactly one HUD process."""

HUD_ALREADY_RUNNING_EXIT_CODE = 3
"""Exit status a HUD uses when another one already owns the instance lock.

Distinct from a crash so the GUI can tell the user what actually happened.
"HUD_main exited during startup with code 1" sent an investigation into two
HUDs drawing over every table down several wrong paths, because nothing
anywhere said that a second HUD had been refused.
"""


def owner_file_path(name: str) -> str:
    """Where the holder of ``name`` leaves a note saying who it is.

    A file of its own rather than the lock itself, because only one of the
    three lock mechanisms is a file: a Windows mutex and a bound socket have
    nowhere to write. Recording the owner beside the lock instead makes the
    answer available on every platform -- which matters most on Windows,
    where the socket fallback is what a plain install uses.
    """
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", name)
    return os.path.join(tempfile.gettempdir(), f"{safe}.owner")  # noqa: PTH118 - plain paths, no Path elsewhere here


def read_lock_owner(name: str = HUD_INSTANCE_LOCK_NAME) -> str | None:
    """Who holds this lock, as they described themselves when taking it.

    Returns None when nothing recorded an owner -- nobody holds it, or an
    older build that did not leave a note.
    """
    try:
        with open(owner_file_path(name), encoding="utf-8") as handle:  # noqa: PTH123 - see owner_file_path
            return handle.read().strip() or None
    except OSError:
        return None


def acquire_hud_instance_lock(source: str, name: str = HUD_INSTANCE_LOCK_NAME) -> Any:
    """Acquire the single process lock used by the HUD entry point.

    The GUI can start the HUD through more than one launch path (normal
    auto-import, a frozen executable, or a manual restart).  A dedicated lock
    makes a second HUD fail before it binds ZMQ or creates any Qt windows.
    The caller owns the returned lock and must release it when the event loop
    exits.

    ``name`` exists so a test can exercise the mutual exclusion on a lock of
    its own. Taking the real one would make the test's result depend on
    whether a HUD happens to be running on the machine, and would lock the
    user out of their own HUD while it ran.
    """
    lock = InterProcessLock(name=name)
    if not lock.acquire(source):
        raise SingleInstanceError("The FPDB HUD process is already running")
    return lock


class InterProcessLockBase:
    def __init__(self, name=None) -> None:
        self._has_lock = False
        if not name:
            name = sys.argv[0]
        self.name = name
        self.heldBy = None

    def getHashedName(self):
        log.debug(f"Original name: {self.name}")  # debug
        encoded_name = base64.b64encode(self.name.encode())
        log.debug("Base64 encoded: %r", encoded_name)
        encoded_name = encoded_name.replace(b"=", b"")
        log.debug("Base64 encoded (without '='): %r", encoded_name)
        hashed_name = encoded_name.decode()
        log.debug(f"Final decoded string: {hashed_name}")
        return hashed_name

    def acquire_impl(self, wait) -> None:
        pass

    def _record_owner(self, source: str) -> None:
        """Leave a note saying who took the lock, for whoever is refused next.

        Best-effort by design: failing to leave the note must never cost the
        caller the lock it has already acquired. A refused caller then simply
        cannot name the holder, which is the situation this exists to improve
        on, not to depend on.
        """
        try:
            with open(owner_file_path(self.name), "w", encoding="utf-8") as handle:  # noqa: PTH123
                handle.write(source)
        except OSError:
            log.debug("Could not record the owner of lock %s", self.name, exc_info=True)

    def _forget_owner(self) -> None:
        """Remove the note when the lock is given back."""
        try:
            os.unlink(owner_file_path(self.name))  # noqa: PTH108 - see owner_file_path
        except OSError:
            pass

    def acquire(self, source, wait=False, retry_time=1) -> bool:
        if source is None:
            source = "Unknown"
        if self._has_lock:  # make sure 2nd acquire in the same process fails
            log.warning(f"Lock already held by: {self.heldBy}")
            return False
        while not self._has_lock:
            try:
                self.acquire_impl(wait)
                self._has_lock = True
                self.heldBy = source
                self._record_owner(source)
                log.debug("Lock acquired successfully")
            except SingleInstanceError:
                if not wait:
                    log.debug("Failed to acquire lock without waiting")
                    return False
                log.debug(f"Retrying to acquire lock in {retry_time} seconds")
                time.sleep(retry_time)
        return True

    def release(self) -> None:
        self.release_impl()  # type: ignore[attr-defined]  # implemented by platform-specific lock subclasses
        self._forget_owner()
        self._has_lock = False
        self.heldBy = None

    def locked(self) -> bool:
        if self.acquire("locked_check"):
            self.release()
            return False
        return True


LOCK_FILE_DIRECTORY = "/tmp"

#: Characters that must not reach a lock file's name. A separator among them
#: would send two processes looking for one lock to two different places.
_BAD_FILENAME_CHARACTERS = re.compile(r"[/?<>\\:;*|'\"^=.\[\]]")

#: Port range the socket lock picks from. Keep it strictly below 32768 so it
#: does not contend with the dynamic range that the OS allocates to outbound
#: connections (49152-65535 on Windows and modern Linux).
_LOCK_PORT_BASE = 20000
_LOCK_PORT_SPAN = 12768  # -> 20000..32767


def port_for_lock_name(name: str) -> int:
    """The port two processes must agree on to contend for the same lock.

    Uses a stable digest rather than ``hash()``. Python salts string hashing
    per process (PYTHONHASHSEED), so the old derivation gave every process a
    different port for the same name: each bound its own, none ever collided,
    and the lock admitted as many holders as asked. Nothing failed visibly --
    it simply never excluded anybody, which on Windows is what stood between
    the user and two HUD processes drawing over each other.
    """
    digest = zlib.crc32(name.encode("utf-8"))
    return _LOCK_PORT_BASE + digest % _LOCK_PORT_SPAN


class InterProcessLockFcntl(InterProcessLockBase):
    def __init__(self, name=None) -> None:
        InterProcessLockBase.__init__(self, name)
        self.lockfd: Any = None
        self.lock_file_name = os.path.join(
            LOCK_FILE_DIRECTORY,
            self.getHashedName() + ".lck",
        )
        assert os.path.isdir(LOCK_FILE_DIRECTORY)

    # This is the suggested way to get a safe file name, but I like having a descriptively named lock file.
    def getHashedName(self):
        # A character class. Without the brackets this was a literal sequence
        # -- it replaced the exact string /?<>\:;*|'"^=.[] and nothing else --
        # so it sanitised no name anybody would ever use. A name carrying a
        # separator then built a path into another directory, where a second
        # process looking for the same lock would not find it.
        return _BAD_FILENAME_CHARACTERS.sub("_", self.name)

    def acquire_impl(self, wait) -> None:
        self.lockfd = open(self.lock_file_name, "w")
        fcntrl_options = fcntl.LOCK_EX
        if not wait:
            fcntrl_options |= fcntl.LOCK_NB
        try:
            fcntl.flock(self.lockfd, fcntrl_options)
        except OSError:
            self.lockfd.close()
            self.lockfd = None
            raise SingleInstanceError(
                "Could not acquire exclusive lock on " + self.lock_file_name,
            )

    def release_impl(self) -> None:
        fcntl.lockf(self.lockfd, fcntl.LOCK_UN)
        self.lockfd.close()
        self.lockfd = None
        try:
            os.unlink(self.lock_file_name)
        except OSError:
            # We don't care about the existence of the file too much here.  It's the flock() we care about,
            # And that should just go away magically.
            pass


class InterProcessLockWin32(InterProcessLockBase):
    def __init__(self, name=None) -> None:
        InterProcessLockBase.__init__(self, name)
        self.mutex: Any = None

    def acquire_impl(self, wait) -> None:
        self.mutex = win32event.CreateMutex(None, 1, self.getHashedName())
        if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
            if self.mutex:
                win32api.CloseHandle(self.mutex)
                self.mutex = None
            raise SingleInstanceError(
                "Could not acquire exclusive lock on " + self.name,
            )

    def release_impl(self) -> None:
        if self.mutex:
            try:
                win32event.ReleaseMutex(self.mutex)
            except Exception:
                log.debug("Could not release the Windows mutex", exc_info=True)
            try:
                win32api.CloseHandle(self.mutex)
            except Exception:
                log.debug("Could not close the Windows mutex handle", exc_info=True)
            self.mutex = None


class InterProcessLockSocket(InterProcessLockBase):
    """Mutual exclusion by binding a port derived from the lock's name.

    The fallback for platforms with neither fcntl nor pywin32 -- which
    includes a Windows install without pywin32, where this is what guards the
    single HUD process.
    """

    def __init__(self, name=None) -> None:
        InterProcessLockBase.__init__(self, name)
        self.socket: Any = None
        self.portno = port_for_lock_name(self.getHashedName())

    def acquire_impl(self, wait) -> None:
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.socket.bind(("127.0.0.1", self.portno))
        except OSError as exc:
            self.socket.close()
            self.socket = None
            if exc.errno in (errno.EADDRINUSE, errno.EACCES):
                raise SingleInstanceError(
                    f"Could not acquire exclusive lock on {self.name}: port {self.portno} is already bound",
                ) from exc
            log.error(
                "Lock %s could not be tested: binding port %d failed with %s",
                self.name,
                self.portno,
                exc,
            )
            raise SingleInstanceError(
                f"Could not test the lock on {self.name}: binding port {self.portno} failed ({exc})",
            ) from exc

    def release_impl(self) -> None:
        self.socket.close()
        self.socket = None


def select_lock_class() -> Any:
    """The locking mechanism this platform can actually use.

    A function rather than a bare try/except at module scope so the choice can
    be exercised: two of the three branches are unreachable on any given
    machine, and the one that matters most -- a Windows install with no
    pywin32, which falls through to the socket -- is the one a developer is
    least likely to be running.
    """
    # Each lock class reads its bindings as module globals, so an import that
    # stayed local to this function would leave the class raising NameError
    # the moment it was used. socket already cost that once: it was imported
    # only in the branch that selects the socket lock, so the fallback could
    # not run anywhere it was not already the only choice.
    global fcntl, win32api, win32event, winerror  # noqa: PLW0603 - see the module-level declarations

    try:
        import fcntl as _fcntl
    except ImportError:
        pass
    else:
        fcntl = _fcntl
        return InterProcessLockFcntl

    try:
        import win32api as _win32api
        import win32event as _win32event
        import winerror as _winerror
    except ImportError:
        return InterProcessLockSocket

    win32api, win32event, winerror = _win32api, _win32event, _winerror
    return InterProcessLockWin32


InterProcessLock = select_lock_class()


def test_construct() -> None:
    r"""# Making the name of the test unique so it can be executed my multiple users on the same machine.
    >>> import subprocess
    >>> test_name = 'InterProcessLockTest' +str(os.getpid()) + str(time.time())

    >>> lock1 = InterProcessLock(name=test_name)
    >>> lock1.acquire("test")
    True

    >>> lock2 = InterProcessLock(name=test_name)
    >>> lock3 = InterProcessLock(name=test_name)

    # Since lock1 is locked, other attempts to acquire it fail.
    >>> lock2.acquire("test")
    False

    >>> lock3.acquire("test")
    False

    # Release the lock and let lock2 have it.
    >>> lock1.release()
    >>> lock2.acquire("test")
    True

    >>> lock3.acquire("test")
    False

    # Release it and give it back to lock1
    >>> lock2.release()
    >>> lock1.acquire("test")
    True

    >>> lock2.acquire("test")
    False

    # Test lock status
    >>> lock2.locked()
    True
    >>> lock3.locked()
    True
    >>> lock1.locked()
    True

    >>> lock1.release()

    >>> lock2.locked()
    False
    >>> lock3.locked()
    False
    >>> lock1.locked()
    False

    >>> if os.name == 'posix':
    ...    def os_independent_kill(pid):
    ...        import signal
    ...        os.kill(pid, signal.SIGKILL)
    ... else:
    ...        assert(os.name == 'nt')
    ...        def os_independent_kill(pid):
    ...            ''' http://www.python.org/doc/faq/windows/#how-do-i-emulate-os-kill-in-windows '''
    ...            import win32api
    ...            import win32con
    ...            import pywintypes
    ...            handle = win32api.OpenProcess(win32con.PROCESS_TERMINATE , pywintypes.FALSE, pid)
    ...            #return (0 != win32api.TerminateProcess(handle, 0))

    # Test to acquire the lock in another process.
    >>> def execute(cmd):
    ...    cmd = 'import time;' + cmd + 'time.sleep(10);'
    ...    process = subprocess.Popen([sys.executable, '-c', cmd])
    ...    pid = process.pid
    ...    time.sleep(2) # quick hack, but we test synchronization in the end
    ...    return pid

    >>> pid = execute('import interlocks;a=interlocks.InterProcessLock(name=\"'+test_name+ '\");a.acquire(\"test\");')

    >>> lock1.acquire("test")
    False

    >>> os_independent_kill(pid)

    >>> time.sleep(1)

    >>> lock1.acquire("test")
    True
    >>> lock1.release()

    # Testing wait

    >>> pid = execute('import interlocks;a=interlocks.InterProcessLock(name=\"'+test_name+ '\");a.acquire(\"test\");')

    >>> lock1.acquire("test")
    False

    >>> os_independent_kill(pid)

    >>> lock1.acquire("test", True)
    True
    >>> lock1.release()

    """


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    import argparse
    parser = argparse.ArgumentParser(description="FPDB Inter-process locks utility")
    parser.add_argument("--test", action="store_true", help="Run doctest suite")
    parser.add_argument("--demo", action="store_true", help="Demo inter-process lock functionality")
    parser.add_argument("--list-locks", action="store_true", help="List active lock files (if any)")
    parser.add_argument("--interactive", action="store_true", help="Run original doctest (same as --test)")

    args = parser.parse_args(argv)

    if not any(vars(args).values()):
        parser.print_help()
        return 0

    if args.test or args.interactive:
        print("Running doctest suite for interlocks module...")
        try:
            result = doctest.testmod(optionflags=doctest.IGNORE_EXCEPTION_DETAIL)
            if result.failed == 0:
                print(f"✓ All {result.attempted} doctests passed")
                return 0
            else:
                print(f"✗ {result.failed}/{result.attempted} doctests failed")
                return 1
        except INTERLOCK_CLI_ERRORS as e:
            print(f"✗ Doctests crashed: {e}")
            return 1

    if args.demo:
        print("=== Inter-Process Lock Demo ===")
        try:
            print("Creating test lock 'demo_lock'...")
            lock = InterProcessLock("demo_lock")

            print("Attempting to acquire lock...")
            if lock.acquire("demo", wait=False):
                print("✓ Lock acquired successfully")
                print("Lock is now held. Other processes would wait.")
                time.sleep(1)
                print("Releasing lock...")
                lock.release()
                print("✓ Lock released")
            else:
                print("✗ Could not acquire lock (may be held by another process)")

        except INTERLOCK_CLI_ERRORS as e:
            print(f"Error during demo: {e}")
            return 1

    if args.list_locks:
        print("=== Active Lock Files ===")
        # Look for lock files in common locations. tempfile is imported at
        # module scope; a second import here would shadow it and make the
        # directory impossible to point elsewhere.
        temp_dir = tempfile.gettempdir()
        lock_files: list[str] = []

        try:
            for filename in os.listdir(temp_dir):
                if "fpdb" in filename.lower() and ("lock" in filename.lower() or filename.endswith(".lock")):
                    full_path = os.path.join(temp_dir, filename)
                    if os.path.isfile(full_path):
                        lock_files.append(full_path)

            if lock_files:
                for lock_file in lock_files:
                    stat = os.stat(lock_file)
                    mtime = time.ctime(stat.st_mtime)
                    print(f"  {lock_file} (modified: {mtime})")
            else:
                print("  No FPDB lock files found in temp directory")

        except INTERLOCK_LIST_ERRORS as e:
            print(f"Error listing locks: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
