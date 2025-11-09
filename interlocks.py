# Code from http://ender.snowburst.org:4747/~jjohns/interlocks.py
# Thanks JJ!


import base64
import os
import os.path
import sys
import time

from loggingFpdb import get_logger

# import L10n
# _ = L10n.get_translation()


log = get_logger("interlocks")

InterProcessLock = None

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


class InterProcessLockBase:
    def __init__(self, name=None) -> None:
        self._has_lock = False
        if not name:
            name = sys.argv[0]
        self.name = name
        self.heldBy = None

    def getHashedName(self):
        log.debug(f"Original name: {self.name}")  # debug
        test = base64.b64encode(self.name.encode())
        log.debug(f"Base64 encoded: {test}")
        test = test.replace(b"=", b"")
        log.debug(f"Base64 encoded (without '='): {test}")
        test = test.decode()
        log.debug(f"Final decoded string: {test}")
        return test

    def acquire_impl(self, wait) -> None:
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
                log.debug("Lock acquired successfully")
            except SingleInstanceError:
                if not wait:
                    log.debug("Failed to acquire lock without waiting")
                    return False
                log.debug(f"Retrying to acquire lock in {retry_time} seconds")
                time.sleep(retry_time)
        return True

    def release(self) -> None:
        self.release_impl()
        self._has_lock = False
        self.heldBy = None

    def locked(self) -> bool:
        if self.acquire("locked_check"):
            self.release()
            return False
        return True


LOCK_FILE_DIRECTORY = "/tmp"


class InterProcessLockFcntl(InterProcessLockBase):
    def __init__(self, name=None) -> None:
        InterProcessLockBase.__init__(self, name)
        self.lockfd = 0
        self.lock_file_name = os.path.join(
            LOCK_FILE_DIRECTORY,
            self.getHashedName() + ".lck",
        )
        assert os.path.isdir(LOCK_FILE_DIRECTORY)

    # This is the suggested way to get a safe file name, but I like having a descriptively named lock file.
    def getHashedName(self):
        import re

        bad_filename_character_re = re.compile(r"/\?<>\\\:;\*\|\'\"\^=\.\[\]")
        return bad_filename_character_re.sub("_", self.name)

    def acquire_impl(self, wait) -> None:
        self.lockfd = open(self.lock_file_name, "w")
        fcntrl_options = fcntl.LOCK_EX
        if not wait:
            fcntrl_options |= fcntl.LOCK_NB
        try:
            fcntl.flock(self.lockfd, fcntrl_options)
        except OSError:
            self.lockfd.close()
            self.lockfd = 0
            raise SingleInstanceError(
                "Could not acquire exclusive lock on " + self.lock_file_name,
            )

    def release_impl(self) -> None:
        fcntl.lockf(self.lockfd, fcntl.LOCK_UN)
        self.lockfd.close()
        self.lockfd = 0
        try:
            os.unlink(self.lock_file_name)
        except OSError:
            # We don't care about the existence of the file too much here.  It's the flock() we care about,
            # And that should just go away magically.
            pass


class InterProcessLockWin32(InterProcessLockBase):
    def __init__(self, name=None) -> None:
        InterProcessLockBase.__init__(self, name)
        self.mutex = None

    def acquire_impl(self, wait) -> None:
        self.mutex = win32event.CreateMutex(None, 0, self.getHashedName())
        if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
            self.mutex.Close()
            self.mutex = None
            raise SingleInstanceError(
                "Could not acquire exclusive lock on " + self.name,
            )

    def release_impl(self) -> None:
        self.mutex.Close()


class InterProcessLockSocket(InterProcessLockBase):
    def __init__(self, name=None) -> None:
        InterProcessLockBase.__init__(self, name)
        self.socket = None
        self.portno = 65530 - abs(self.getHashedName().__hash__()) % 32749

    def acquire_impl(self, wait) -> None:
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.socket.bind(("127.0.0.1", self.portno))
        except OSError:
            self.socket.close()
            self.socket = None
            raise SingleInstanceError(
                "Could not acquire exclusive lock on " + self.name,
            )

    def release_impl(self) -> None:
        self.socket.close()
        self.socket = None


# Set InterProcessLock to the correct type given the sysem parameters available
try:
    import fcntl

    InterProcessLock = InterProcessLockFcntl
except ImportError:
    try:
        import win32api
        import win32event
        import winerror

        InterProcessLock = InterProcessLockWin32
    except ImportError:
        import socket

        InterProcessLock = InterProcessLockSocket


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
    import doctest

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
        except Exception as e:
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

        except Exception as e:
            print(f"Error during demo: {e}")
            return 1

    if args.list_locks:
        print("=== Active Lock Files ===")
        # Look for lock files in common locations
        import tempfile

        temp_dir = tempfile.gettempdir()
        lock_files = []

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

        except Exception as e:
            print(f"Error listing locks: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
