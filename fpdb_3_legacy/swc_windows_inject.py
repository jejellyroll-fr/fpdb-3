"""Load the SwC capture tap into the running Windows client.

Windows has no ``LD_PRELOAD``/``DYLD_INSERT_LIBRARIES``: the tap DLL is placed
into the already-running ``SwCPoker.exe`` by a same-bitness injector (built by
``swc_tap_build``). This module finds the client process and runs that injector,
then reports what the DLL's status file says happened.

The whole flow is Windows-only and imports nothing heavy, so it stays testable
and does not drag the capture decoder into a plain injection.
"""

from __future__ import annotations

import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("swc_windows_inject")

#: The SwC Windows client's process image name.
SWC_CLIENT_IMAGE = "SwCPoker.exe"

#: Statuses meaning this client will capture nothing, and so worth naming to the
#: user rather than folding into "capture may be incomplete".
HOOK_FAILURE_STATUSES = ("tap-hook-failed", "tap-ssl-not-found", "tap-load-open-failed")

#: Statuses after which a process writes nothing further, so waiting on it is over.
TERMINAL_STATUSES = ("tap-hooked", *HOOK_FAILURE_STATUSES)

#: Injector exit codes worth naming; see swc_inject.c. Anything else is reported
#: with its raw code.
_INJECTOR_ERRORS = {
    2: "internal error: the injector was called with the wrong arguments",
    3: "internal error: the injector was given an invalid pid",
    4: "could not open the SwC process (is fpdb running as the same Windows user?)",
    5: "the tap and the SwC client are different bitness (the client must be 32-bit)",
    6: "could not allocate memory in the SwC process",
    7: "could not write to the SwC process",
    8: "could not resolve LoadLibrary in the SwC process",
    9: "could not start the loader thread in the SwC process",
    10: "the loader thread did not finish in time",
    11: "the SwC process refused to load the tap DLL",
}


@dataclass(frozen=True)
class InjectionResult:
    """Outcome of injecting the tap into one client process."""

    pid: int
    ok: bool
    detail: str


def find_client_pids(image_name: str = SWC_CLIENT_IMAGE) -> list[int]:
    """PIDs of every running SwC client process, newest first is not guaranteed.

    Uses psutil (already a dependency). Returns an empty list when the client is
    not running, so the caller can tell the user to start it.
    """
    try:
        import psutil
    except ImportError:  # pragma: no cover - psutil is a declared dependency
        log.warning("psutil is not available; cannot find the SwC client process")
        return []

    target = image_name.casefold()
    pids: list[int] = []
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            name = (proc.info.get("name") or "").casefold()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if name == target:
            pids.append(int(proc.info["pid"]))
    return pids


def write_capture_config(build_dir: Path, *, port: int, include_outbound: bool) -> Path:
    """Write the sidecar the injected DLL reads for port/outbound settings.

    The DLL cannot inherit environment variables (it is injected, not launched),
    so the POSIX ``SWC_CAPTURE_PORT``/``SWC_CAPTURE_OUTBOUND`` knobs are passed
    through this file instead. Written next to the DLL, where the DLL looks.
    """
    config_path = build_dir / "swc-native.cfg"
    config_path.write_text(_capture_config_text(port=port, include_outbound=include_outbound), encoding="ascii")
    return config_path


def _capture_config_text(*, port: int, include_outbound: bool) -> str:
    return f"port={int(port)}\noutbound={1 if include_outbound else 0}\n"


def capture_config_changed(build_dir: Path, *, port: int, include_outbound: bool) -> bool:
    """Whether these options differ from the ones already on disk.

    A client that already holds the tap will not pick them up: the DLL reads its
    configuration once, in DllMain, and injecting again only increments the
    module's reference count. Reporting the change lets the caller say so instead
    of announcing success while the old filtering silently stays in force.
    """
    config_path = build_dir / "swc-native.cfg"
    try:
        previous = config_path.read_text(encoding="ascii")
    except OSError:
        return False  # nothing was configured before, so nothing can be stale
    return previous != _capture_config_text(port=port, include_outbound=include_outbound)


def write_stream_ids(build_dir: Path, pids: list[int]) -> dict[int, int]:
    """Give each client a distinct stream id and return the assignment.

    Every injected client appends to one archive, so a record has to say which
    client wrote it or the reassembler splices their plaintext together. The
    launcher is the only party that sees all the clients at once, so it assigns
    the ids; a tap deriving its own could only hash its process id down to the
    byte the header has room for, and a hash collides.

    Ids start at 1: the tap treats 0 as "nothing was assigned" and falls back to
    that hash, which is still better than the constant every client shared.
    """
    # An id already handed out has to stay with its process. LoadLibraryW does
    # not re-run DllMain for a DLL a client already holds, so an attach that
    # renumbered everyone would leave that client using its old id in memory
    # while a newly injected one was handed the same number -- putting their
    # records back on one decoder, which is the splice this exists to prevent.
    existing = _read_stream_ids(build_dir)
    # A pid is not an identity: Windows reuses them, and a sidecar outlives the
    # process it was written for. Keeping an assignment on pid equality alone
    # would hand a new client the id that a *previous* process stamped on records
    # still sitting in the append-only archive -- the splice this scheme exists to
    # prevent. The process start time is what makes the pair unrepeatable.
    assignment = {
        pid: entry.stream_id
        for pid in pids
        if (entry := existing.get(pid)) is not None and _is_the_same_process(pid, entry.started)
    }
    # Reserved against *every* id ever handed out for this archive, not just the
    # ids of clients still running. The archive is append-only: records written
    # by a client that has since exited are still in it, and if that client left
    # a partial message behind, a new process reusing its id would be spliced
    # onto that fragment by the very decoder the id exists to keep apart.
    # reset_stream_ids() releases the pool when the archive itself is new.
    taken = {entry.stream_id for entry in existing.values()}
    free = (n for n in range(1, 256) if n not in taken)

    for pid in sorted(pids):
        if pid in assignment:
            continue
        assignment[pid] = next(free, 0) or _fallback_stream_id(pid)
        taken.add(assignment[pid])

    for pid, stream_id in assignment.items():
        started = process_start_time(pid)
        body = f"stream={stream_id}\n"
        if started is not None:
            body += f"started={started!r}\n"
        (build_dir / f"swc-native-{pid}.cfg").write_text(body, encoding="ascii")
    return assignment


def reset_stream_ids(build_dir: Path, keep_pids: Sequence[int] = ()) -> int:
    """Release the id pool, for use when the archive holds no records yet.

    Ids are reserved for as long as the archive can still contain records that
    carry them. Once it is empty -- a fresh install, or the user rotated it --
    nothing refers to the old ids any more and starting again at 1 keeps the
    pool from creeping toward its 255 ceiling over a long-lived install.

    ``keep_pids`` are the clients still running. Their DLL is already resident
    and keeps the id it read at load time -- reinjecting does not re-run DllMain
    -- so releasing their assignment would let a *different* client be handed a
    number one of them is still stamping on its records, which is the collision
    the whole scheme exists to avoid.
    """
    protected = set(keep_pids)
    removed = 0
    for path in build_dir.glob("swc-native-*.cfg"):
        try:
            pid = int(path.stem.rsplit("-", 1)[1])  # only the per-pid sidecars
        except (ValueError, IndexError):
            continue
        if pid in protected:
            continue
        try:
            path.unlink()
        except OSError:
            continue
        removed += 1
    return removed


@dataclass(frozen=True)
class _StreamAssignment:
    """One sidecar: the id handed out, and which process run it was handed to."""

    stream_id: int
    started: float | None


def process_start_time(pid: int) -> float | None:
    """When this process started, or None if it cannot be read.

    Paired with the pid this is an identity a later process cannot inherit, which
    a pid on its own is not.
    """
    try:
        import psutil

        return float(psutil.Process(pid).create_time())
    except Exception:  # noqa: BLE001 - a pid that is gone or unreadable is simply unknown
        return None


def _is_the_same_process(pid: int, started: float | None) -> bool:
    """Whether the process running as ``pid`` now is the one the id was given to.

    An unrecorded start time cannot disprove identity, and of the two mistakes
    available there, renumbering a client whose DLL is already resident is the
    worse one -- it puts two live clients on one id, while the other risk needs a
    recycled pid to bite. So an assignment with no recorded start time is kept
    (which is also what a sidecar written before start times were recorded has).
    """
    if started is None:
        return True
    current = process_start_time(pid)
    if current is None:
        return False
    # Whole seconds: the value survives a round trip through the sidecar, and two
    # runs of one client are never within a second of each other on one pid.
    return abs(current - started) < 1.0


def _read_stream_ids(build_dir: Path) -> dict[int, _StreamAssignment]:
    """The stream ids already assigned, read back from their sidecars."""
    assigned: dict[int, _StreamAssignment] = {}
    for path in build_dir.glob("swc-native-*.cfg"):
        try:
            pid = int(path.stem.rsplit("-", 1)[1])
            body = path.read_text(encoding="ascii")
            stream_id = int(body.split("stream=", 1)[1].split()[0])
        except (OSError, ValueError, IndexError):
            continue
        started: float | None = None
        if "started=" in body:
            try:
                started = float(body.split("started=", 1)[1].split()[0])
            except (ValueError, IndexError):
                started = None
        if 1 <= stream_id <= 255:
            assigned[pid] = _StreamAssignment(stream_id, started)
    return assigned


def _fallback_stream_id(pid: int) -> int:
    """A last-resort id when all 255 are spoken for -- 255 clients is not a real case."""
    log.warning("All SwC stream ids are in use; reusing one for pid %s", pid)
    return ((pid - 1) % 255) + 1


def inject_into_pid(injector: Path, dll: Path, pid: int) -> InjectionResult:
    """Run the injector to load ``dll`` into ``pid``; never raises."""
    try:
        # A non-literal subprocess call by necessity: this runs the injector that
        # was just compiled. Both paths are module-derived (get_injector_path,
        # get_tap_library_path) and the pid comes from find_client_pids, so no
        # argument originates outside this process; no shell is involved, so a
        # path cannot be interpreted as anything but a path.
        completed = subprocess.run(
            [str(injector), str(pid), str(dll)],
            check=False,
            capture_output=True,
            text=True,
            timeout=45,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return InjectionResult(pid=pid, ok=False, detail=f"could not run the injector: {exc}")

    if completed.returncode == 0:
        return InjectionResult(pid=pid, ok=True, detail="tap DLL loaded")

    detail = _INJECTOR_ERRORS.get(completed.returncode, f"injector exit code {completed.returncode}")
    stderr = completed.stderr.strip()
    if stderr:
        detail = f"{detail} ({stderr})"
    return InjectionResult(pid=pid, ok=False, detail=detail)


def _parse_status_lines(text: str) -> tuple[dict[int, str], str]:
    """Latest status per client pid, and the latest status overall.

    On Windows the DLL prefixes each line with its pid, because every injected
    client appends to the one file. A line without that prefix (a DLL left over
    from before it existed) still counts as the latest overall but cannot be
    attributed to a process.
    """
    by_pid: dict[int, str] = {}
    latest = ""
    for line in text.splitlines():
        status = line.strip()
        if not status:
            continue
        pid_text, _, rest = status.partition(" ")
        if rest and pid_text.isdigit():
            latest = rest.strip()
            by_pid[int(pid_text)] = latest
        else:
            latest = status
    return by_pid, latest


def _read_status_text(status_path: Path) -> str:
    try:
        return status_path.read_text(encoding="ascii", errors="replace")
    except OSError:
        return ""


def read_status(status_path: Path) -> str:
    """The last status any injected DLL wrote, without its pid prefix, or '' if none yet.

    The DLL appends a line per lifecycle step: ``tap-loaded`` on attach,
    ``tap-hooked`` once SSL_read/SSL_write are patched, or a failure marker. The
    last line is the current state.
    """
    return _parse_status_lines(_read_status_text(status_path))[1]


def read_statuses(status_path: Path) -> dict[int, str]:
    """The last status each client pid wrote, keyed by pid."""
    return _parse_status_lines(_read_status_text(status_path))[0]


def wait_for_hooks(status_path: Path, pids: Sequence[int], *, timeout: float = 10.0) -> dict[int, str]:
    """Wait until every injected pid has reported a terminal status, or time out.

    Returns the latest status per pid; one that has written nothing yet maps to
    ``''``.

    ``tap-hooked`` is success. ``tap-loaded`` means the DLL is in but the client
    has not opened a TLS socket yet (the SSL library loads lazily) -- left as
    that pid's best-so-far when the wait elapses, since hooking will still
    happen once the client connects.

    The wait is per pid on purpose. With one shared status file, waiting for the
    first terminal line lets whichever client hooks first speak for all of them:
    a second client that goes on to report ``tap-hook-failed`` was announced as
    capturing, and its hands were then silently missing.
    """
    deadline = time.monotonic() + timeout
    statuses: dict[int, str] = dict.fromkeys(pids, "")
    while True:
        by_pid = read_statuses(status_path)
        for pid, status in statuses.items():
            if status in TERMINAL_STATUSES:
                continue
            latest = by_pid.get(pid, "")
            if latest:
                statuses[pid] = latest
        if all(status in TERMINAL_STATUSES for status in statuses.values()):
            return statuses
        if time.monotonic() >= deadline:
            return statuses
        time.sleep(0.2)
