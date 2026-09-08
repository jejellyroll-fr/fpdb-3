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
from dataclasses import dataclass
from pathlib import Path

from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("swc_windows_inject")

#: The SwC Windows client's process image name.
SWC_CLIENT_IMAGE = "SwCPoker.exe"

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
    config_path.write_text(f"port={int(port)}\noutbound={1 if include_outbound else 0}\n", encoding="ascii")
    return config_path


def inject_into_pid(injector: Path, dll: Path, pid: int) -> InjectionResult:
    """Run the injector to load ``dll`` into ``pid``; never raises."""
    try:
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


def read_status(status_path: Path) -> str:
    """The last status line the DLL wrote, or '' if none yet.

    The DLL appends a line per lifecycle step: ``tap-loaded`` on attach,
    ``tap-hooked`` once SSL_read/SSL_write are patched, or a failure marker. The
    last line is the current state.
    """
    try:
        lines = [line.strip() for line in status_path.read_text(encoding="ascii", errors="replace").splitlines() if line.strip()]
    except OSError:
        return ""
    return lines[-1] if lines else ""


def wait_for_hook(status_path: Path, *, timeout: float = 10.0) -> str:
    """Wait until the DLL reports it hooked SSL, or time out; return the status.

    ``tap-hooked`` is success. ``tap-loaded`` means the DLL is in but the client
    has not opened a TLS socket yet (the SSL library loads lazily) -- returned as
    the best-so-far when the wait elapses, since hooking will still happen once
    the client connects.
    """
    deadline = time.monotonic() + timeout
    latest = ""
    while time.monotonic() < deadline:
        latest = read_status(status_path)
        if latest in ("tap-hooked", "tap-hook-failed", "tap-ssl-not-found", "tap-load-open-failed"):
            return latest
        time.sleep(0.2)
    return latest
