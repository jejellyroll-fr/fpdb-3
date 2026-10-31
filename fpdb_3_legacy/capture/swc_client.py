#!/usr/bin/env python3
"""Build the SwC tap, load it into the native client, and follow what it captures.

The acquisition half of the native SwC capture (#451): compiling the tap,
injecting it into the running client on Windows or preloading it when SwC is
launched on macOS and Linux, and the command line that does either. Decoding
the archive the tap writes is fpdb's core, in
:mod:`fpdb_3_legacy.swc_native_capture`.

Nothing here runs until the user turned the tap on
(:mod:`fpdb_3_legacy.live_capture_consent`).
"""

from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

from fpdb_3_legacy import live_capture_consent, swc_native_capture

# Compiling the tap lives in its own stdlib-only module, so CI can verify the
# build on every platform without installing the project.
from fpdb_3_legacy.capture.swc_tap_build import SWC_EXECUTABLE, build_tap
from fpdb_3_legacy.loggingFpdb import get_logger
from fpdb_3_legacy.swc_native_capture import (
    follow_dealer_history,
    inspect_archive,
    print_animation_events,
    print_dealer_history,
    print_importability_audit,
    print_normalized_hands,
    print_ofc_summary,
    print_outbound_summary,
    print_session_summary,
    print_stack_history,
)

log = get_logger("swc_client")

#: Platforms that load the tap by library interposition at client launch --
#: DYLD_INSERT_LIBRARIES on macOS, LD_PRELOAD on Linux (see
#: ``native_client_environment``). Windows is deliberately excluded: it has no
#: launch-time interposition, so the tap is instead *injected* into the already
#: running client (see ``attach_to_windows_client``), a different code path.
INTERPOSABLE_SYSTEMS = frozenset({"Darwin", "Linux"})

#: Every platform that can capture live, by whichever mechanism.
SUPPORTED_SYSTEMS = INTERPOSABLE_SYSTEMS | {"Windows"}


def native_capture_supported(system_name: str | None = None) -> bool:
    """Whether the live native capture can be started on this platform."""
    return (system_name or platform.system()) in SUPPORTED_SYSTEMS


class CaptureAttachCancelled(RuntimeError):
    """The attach was abandoned before the tap was injected.

    Injection is the step that cannot be taken back: the tap has no unload path,
    so once ``LoadLibrary`` has run the DLL stays resident in the client and goes
    on writing decrypted traffic to the archive until the client exits. An
    attach spends most of its time before that -- compiling the tap and the
    injector, enumerating processes -- and the user can stop Auto Import during
    any of it. Those are the moments a stop can still mean something, so they are
    the moments the request is read.

    A RuntimeError because that is what every other refusal from
    ``attach_to_windows_client`` already is; callers that only want to report a
    failure keep working unchanged.
    """


def _attach_warnings(
    injector_mod,
    results: list,
    injected: list[int],
    *,
    status_path,
    status_mark: int,
    options_changed: bool,
) -> str:
    """Everything about this attach that a "capture active" line would otherwise hide.

    Each of these is a client whose hands will not arrive, or will arrive under
    settings the user did not ask for, so they are appended to whichever status
    the caller goes on to return rather than logged and forgotten.
    """
    notes: list[str] = []

    # A client the tap could not be injected into produces nothing, and saying
    # only how many succeeded would announce capture for all of them.
    refused = [r for r in results if not r.ok]
    if refused:
        notes.append(" Not injected: " + "; ".join(f"pid {r.pid}: {r.detail}" for r in refused) + ".")

    if options_changed:
        notes.append(
            " Capture options changed: a client that was already running keeps the previous "
            "port/outbound settings until it is restarted."
        )

    # Looked for across every line this attach produced, not only the latest: a
    # client that cannot take the cross-process mutex drops all its records, and
    # writes that warning before the hook status which then supersedes it.
    markers = injector_mod.read_status_markers(status_path, status_mark)
    lockless = [pid for pid in injected if injector_mod.CAPTURE_LOCK_UNAVAILABLE in markers.get(pid, ())]
    if lockless:
        notes.append(
            f" pid(s) {', '.join(str(pid) for pid in lockless)} could not take the shared-archive lock "
            "and are dropping records; restart fpdb and the client."
        )

    return "".join(notes)


def _abort_attach_if_cancelled(should_cancel: Callable[[], bool] | None, stage: str) -> None:
    """Raise when the caller has stopped wanting the attach it asked for."""
    if should_cancel is None or not should_cancel():
        return
    log.info("SwC tap attachment abandoned %s: capture was stopped", stage)
    msg = f"the SwC tap attachment was cancelled {stage}"
    raise CaptureAttachCancelled(msg)


def _stopped_or_turned_off(should_cancel: Callable[[], bool] | None, consent: Path | None) -> Callable[[], bool]:
    """``should_cancel``, also answering True once the user has turned the tap off (#451)."""

    def stopped() -> bool:
        if not live_capture_consent.is_accepted(live_capture_consent.SWC_NATIVE, consent):
            return True
        return should_cancel is not None and should_cancel()

    return stopped


def _inject_into_each_client(
    injector_mod,
    injector: Path,
    tap: Path,
    pids: list[int],
    should_cancel: Callable[[], bool] | None,
) -> list:
    """Load the tap into each client, abandoning the rest if capture is stopped.

    The cancellation is read per client rather than once for the batch. One
    injection runs the injector as a subprocess with a 45-second timeout, so a
    stop arriving during the first would otherwise go on loading the tap into
    every client behind it -- minutes after the user stopped, and each one
    permanent, since the tap has no unload path.

    That same permanence is why the abandonment names the clients already
    holding it: they go on recording until they exit, and nothing here can
    change that, so the least it can do is say so.
    """
    results: list = []
    for pid in pids:
        loaded = [result.pid for result in results if result.ok]
        already = (
            f"; pid(s) {', '.join(str(loaded_pid) for loaded_pid in loaded)} already hold the tap "
            "and go on recording until they exit"
            if loaded
            else ""
        )
        _abort_attach_if_cancelled(should_cancel, f"before injecting pid {pid}{already}")
        results.append(injector_mod.inject_into_pid(injector, tap, pid))
    return results


def attach_to_windows_client(
    *,
    port: int = 0,
    include_outbound: bool = False,
    should_cancel: Callable[[], bool] | None = None,
    consent: Path | None = None,
) -> str:
    """Build the tap, inject it into the running SwC client, and report the result.

    Windows counterpart of ``launch_client``: rather than launching the client
    with an interposition environment (impossible on Windows), it loads the tap
    into ``SwCPoker.exe`` while it runs. The archive is always the DLL-relative
    ``DEFAULT_ARCHIVE`` -- the injected DLL derives its own paths from its
    location and cannot be told a different one through the environment.

    ``should_cancel`` is polled at the points where the work can still be
    abandoned -- after the builds, and again before each client is injected --
    and raises ``CaptureAttachCancelled`` when it answers True. Nothing in here
    can be interrupted mid-step (a compiler run, an injector call), so a caller
    that stops capture gets the guarantee that matters instead: no further tap
    is loaded into a client after the stop.

    Nothing is built or injected unless the user turned the tap on (#451):
    ``consent`` is the answers file, fpdb's own when None, and
    ``LiveCaptureNotAccepted`` -- a RuntimeError -- says how to turn it on.
    The answer is read again wherever ``should_cancel`` is, so turning the tap
    off while it builds stops it before it reaches a client.

    Returns a short human-readable status. Raises RuntimeError when the client
    is not running or no injection succeeded, so the caller can surface why.
    """

    if platform.system() != "Windows":
        msg = "attach_to_windows_client is only valid on Windows"
        raise RuntimeError(msg)
    live_capture_consent.require(live_capture_consent.SWC_NATIVE, consent)
    stopped = _stopped_or_turned_off(should_cancel, consent)
    if not 0 <= port <= 65535:
        raise ValueError("capture port must be 0 (auto) or between 1 and 65535")

    from fpdb_3_legacy.capture import swc_windows_inject as injector_mod
    from fpdb_3_legacy.capture.swc_tap_build import BUILD_DIR, build_injector

    tap = build_tap(check_executable=False)
    injector = build_injector()
    # The compiler is the long pole -- on a cold build it is most of the attach,
    # and it is where a Stop is most likely to land.
    _abort_attach_if_cancelled(stopped, "after building the tap")
    # Checked before the write: a client already holding the tap read its
    # configuration once, in DllMain, and injecting again only bumps the module
    # reference count -- it keeps the old port/outbound filtering until restarted.
    options_changed = injector_mod.capture_config_changed(BUILD_DIR, port=port, include_outbound=include_outbound)
    injector_mod.write_capture_config(BUILD_DIR, port=port, include_outbound=include_outbound)

    archive = swc_native_capture.DEFAULT_ARCHIVE
    archive.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    archive_is_new = not archive.exists() or archive.stat().st_size == 0
    archive.touch(exist_ok=True)

    pids = injector_mod.find_client_pids()
    if not pids:
        msg = (
            f"the SwC client ({injector_mod.SWC_CLIENT_IMAGE}) is not running; "
            "start it and open a table, then start capture again"
        )
        raise RuntimeError(msg)

    if archive_is_new:
        # No record can still refer to a previously assigned id, so the pool is
        # free again -- otherwise it would only ever creep toward its ceiling.
        # The clients still running keep theirs: their DLL is already resident
        # and goes on stamping the id it read at load time.
        injector_mod.reset_stream_ids(BUILD_DIR, keep_pids=pids)

    # Assigned before injection: the tap reads its id at load time.
    injector_mod.write_stream_ids(BUILD_DIR, pids)

    # Marked before injecting, because the DLL starts writing the moment
    # LoadLibrary runs: the status file is append-only and keyed by pid, and
    # Windows reuses pids, so a line left by a previous process would otherwise
    # answer for this attempt -- reporting capture active for a client whose DLL
    # had written nothing yet. Reading from this offset keeps the wait to what
    # this attach produced, and taking it any later would skip the DLL's own
    # first lines and turn every attach into a timeout.
    status_path = archive.with_suffix(".status")
    status_mark = injector_mod.status_file_size(status_path)

    results = _inject_into_each_client(injector_mod, injector, tap, pids, stopped)
    ok = [r for r in results if r.ok]
    if not ok:
        detail = "; ".join(f"pid {r.pid}: {r.detail}" for r in results)
        msg = f"could not inject the SwC tap into any client process ({detail})"
        raise RuntimeError(msg)

    injected = [r.pid for r in ok]
    statuses = injector_mod.wait_for_hooks(status_path, injected, since=status_mark)
    log.info(
        "SwC tap injected into pid(s) %s; DLL status=%s",
        ", ".join(str(pid) for pid in injected),
        ", ".join(f"{pid}:{statuses.get(pid) or 'none yet'}" for pid in injected),
    )

    refused_note = _attach_warnings(
        injector_mod,
        results,
        injected,
        status_path=status_path,
        status_mark=status_mark,
        options_changed=options_changed,
    )

    hooked = [pid for pid in injected if statuses.get(pid) == "tap-hooked"]
    failed = [pid for pid in injected if statuses.get(pid) in injector_mod.HOOK_FAILURE_STATUSES]
    if failed:
        # Named per client: one shared status file means a failure here is a
        # client whose hands will simply never arrive.
        detail = ", ".join(f"pid {pid} reported {statuses[pid]}" for pid in failed)
        return (
            f"SwC tap hooked in {len(hooked)} of {len(injected)} client process(es); {detail}. "
            f"Hands from those clients will be missing.{refused_note}"
        )
    if len(hooked) == len(injected):
        return f"SwC capture active: tap hooked in {len(hooked)} client process(es).{refused_note}"
    if all(statuses.get(pid) in ("", "tap-loaded") for pid in injected):
        return (
            f"SwC tap loaded into {len(injected)} client process(es); it will start capturing "
            f"as soon as the client opens a secure connection (play or reopen a table).{refused_note}"
        )
    pending = ", ".join(str(pid) for pid in injected if pid not in hooked)
    return (
        f"SwC tap hooked in {len(hooked)} of {len(injected)} client process(es); "
        f"pid(s) {pending} have not hooked yet and may start capturing later.{refused_note}"
    )


def running_client_pids() -> list[int]:
    result = subprocess.run(
        ["pgrep", "-f", f"^{SWC_EXECUTABLE}$"],
        check=False,
        capture_output=True,
        text=True,
    )
    return [int(value) for value in result.stdout.split() if value.isdigit()]


def native_client_environment(archive: Path, tap: Path, *, port: int, include_outbound: bool) -> dict[str, str]:
    """Return a Finder-like environment plus the variables required by the tap.

    The old Qt/C++ runtime bundled by SwC aborts while parsing decimal skin
    values such as ``0.45`` when it inherits terminal locale variables (notably
    ``LC_ALL=C.UTF-8`` from uv/Codex shells). Apps started by LaunchServices do
    not normally receive those variables.
    """
    env = os.environ.copy()
    for name in tuple(env):
        if name == "LANG" or name == "LANGUAGE" or name.startswith("LC_"):
            env.pop(name, None)
    system_name = platform.system()
    interpose_var = "DYLD_INSERT_LIBRARIES" if system_name == "Darwin" else "LD_PRELOAD"
    env.update(
        {
            interpose_var: str(tap),
            "SWC_CAPTURE_PATH": str(archive),
            "SWC_CAPTURE_STATUS_PATH": str(archive.with_suffix(".status")),
            "SWC_CAPTURE_PORT": str(port),
            "SWC_CAPTURE_OUTBOUND": "1" if include_outbound else "0",
        }
    )
    return env


def launch_client(
    archive: Path, *, port: int = 0, include_outbound: bool = False, consent: Path | None = None
) -> subprocess.Popen[bytes]:
    # The tap is preloaded into the client: only once the user turned it on (#451).
    live_capture_consent.require(live_capture_consent.SWC_NATIVE, consent)
    if not 0 <= port <= 65535:
        raise ValueError("capture port must be 0 (auto) or between 1 and 65535")
    active_pids = running_client_pids()
    if active_pids:
        joined = ", ".join(str(pid) for pid in active_pids)
        raise RuntimeError(
            f"SwC is already running (pid {joined}). Close it normally, then launch it through this capture command."
        )
    tap = build_tap()
    archive = archive.expanduser().resolve()
    archive.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    archive.touch(mode=0o600, exist_ok=True)
    archive.chmod(0o600)
    status_path = archive.with_suffix(".status")
    status_path.unlink(missing_ok=True)

    env = native_client_environment(archive, tap, port=port, include_outbound=include_outbound)
    # Asked again: the user may have turned the tap off while it compiled.
    live_capture_consent.require(live_capture_consent.SWC_NATIVE, consent)
    return subprocess.Popen([str(SWC_EXECUTABLE)], env=env, cwd=str(Path.home()))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true", help="build the interposer without launching SwC")
    parser.add_argument("--force-build", action="store_true", help="rebuild the interposer")
    parser.add_argument("--inspect", type=Path, help="validate and summarize an existing raw archive")
    parser.add_argument("--dealer-history", type=Path, help="print dealer messages from a raw archive")
    parser.add_argument("--session-summary", type=Path, help="list native tables, hand ids, and snapshot counts")
    parser.add_argument("--outbound-summary", type=Path, help="summarize outbound coverage without credentials")
    parser.add_argument(
        "--stack-history", type=Path, help="list opaque native player-funds changes without inferring amounts"
    )
    parser.add_argument(
        "--animation-events", type=Path, help="list native animation events with opaque player-funds changes"
    )
    parser.add_argument("--normalized-json", type=Path, help="print capture-only normalized native hands as JSON")
    parser.add_argument("--importability-audit", type=Path, help="audit evidence completeness for every native hand")
    parser.add_argument("--ofc-summary", type=Path, help="print compact OFC score/session JSON lines")
    parser.add_argument("--archive", type=Path, default=swc_native_capture.DEFAULT_ARCHIVE)
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="peer port to capture (default: auto-detect SWC game ports and exclude lobby 20001)",
    )
    parser.add_argument(
        "--include-outbound",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="capture client-to-server plaintext (default: enabled; use --no-include-outbound to disable)",
    )
    return parser.parse_args(argv)


def _run_native_report(args: argparse.Namespace) -> bool:
    reports = (
        ("inspect", inspect_archive),
        ("dealer_history", print_dealer_history),
        ("session_summary", print_session_summary),
        ("outbound_summary", print_outbound_summary),
        ("stack_history", print_stack_history),
        ("animation_events", print_animation_events),
        ("normalized_json", print_normalized_hands),
        ("importability_audit", print_importability_audit),
        ("ofc_summary", print_ofc_summary),
    )
    for argument, report in reports:
        if path := getattr(args, argument):
            report(path)
            return True
    return False


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if _run_native_report(args):
        return 0
    if args.build or args.force_build:
        print(build_tap(force=args.force_build))
        return 0
    # Asked here, on the terminal, the way Tools > Live capture asks (#451).
    if not live_capture_consent.confirm_on_terminal(live_capture_consent.SWC_NATIVE):
        return 2

    # Windows injects the tap into the running client rather than launching it
    # with an interposition environment, so it has no process to wait on: inject,
    # then follow the DLL-relative archive the same way the launch path does.
    if platform.system() == "Windows":
        try:
            status = attach_to_windows_client(port=args.port, include_outbound=args.include_outbound)
        except (FileNotFoundError, RuntimeError, ValueError) as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
        archive = swc_native_capture.DEFAULT_ARCHIVE.expanduser().resolve()
        print(status)
        print(f"archive={archive}")
        print("Dealer messages will appear with the [SWC] prefix. Press Ctrl+C to stop following.")
        stop_follower = threading.Event()
        follower = threading.Thread(target=follow_dealer_history, args=(archive, stop_follower), daemon=True)
        follower.start()
        try:
            while True:
                time.sleep(0.5)
        except KeyboardInterrupt:
            return 0
        finally:
            stop_follower.set()
            follower.join(timeout=1)

    try:
        process = launch_client(args.archive, port=args.port, include_outbound=args.include_outbound)
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    direction_mode = "bidirectional" if args.include_outbound else "inbound-only"
    print(
        f"SwC launched with passive capture: pid={process.pid} "
        f"archive={args.archive.expanduser().resolve()} mode={direction_mode}"
    )
    print("Dealer messages will appear with the [SWC] prefix. Close SwC normally to stop capture.")
    stop_follower = threading.Event()
    follower = threading.Thread(
        target=follow_dealer_history,
        args=(args.archive.expanduser().resolve(), stop_follower),
        daemon=True,
    )
    follower.start()
    try:
        return process.wait()
    finally:
        stop_follower.set()
        follower.join(timeout=1)


if __name__ == "__main__":
    sys.exit(main())
