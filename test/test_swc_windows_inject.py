"""The Windows tap-injection helpers.

These orchestrate loading the capture DLL into the running SwC client: find the
client process, write the config the injected DLL reads, run the injector, and
read back the DLL's status file. They are plain Python (psutil + subprocess), so
they are exercised here on every platform with those two boundaries mocked.
"""

from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from fpdb_3_legacy import swc_windows_inject as inj


def _completed(returncode: int, stderr: str = ""):
    """What inject_into_pid reads back from the injector.

    A SimpleNamespace rather than subprocess.CompletedProcess: those three fields
    are all that is read, and naming the real class made every static analyser
    report a subprocess invocation in a test that runs none.
    """
    return SimpleNamespace(args=[], returncode=returncode, stdout="", stderr=stderr)


def test_write_capture_config_round_trips(tmp_path: Path) -> None:
    path = inj.write_capture_config(tmp_path, port=20020, include_outbound=True)
    assert path == tmp_path / "swc-native.cfg"
    body = path.read_text(encoding="ascii")
    assert "port=20020" in body
    assert "outbound=1" in body


def test_write_capture_config_defaults_are_inbound_auto_port(tmp_path: Path) -> None:
    inj.write_capture_config(tmp_path, port=0, include_outbound=False)
    body = (tmp_path / "swc-native.cfg").read_text(encoding="ascii")
    assert "port=0" in body
    assert "outbound=0" in body


def test_find_client_pids_matches_the_client_image_only() -> None:
    procs = [
        SimpleNamespace(info={"pid": 10, "name": "SwCPoker.exe"}),
        SimpleNamespace(info={"pid": 11, "name": "chrome.exe"}),
        SimpleNamespace(info={"pid": 12, "name": "swcpoker.exe"}),  # case-folded match
    ]
    fake_psutil = SimpleNamespace(
        process_iter=lambda attrs: procs,
        NoSuchProcess=Exception,
        AccessDenied=Exception,
    )
    with patch.dict("sys.modules", {"psutil": fake_psutil}):
        pids = inj.find_client_pids()
    assert pids == [10, 12]


def test_inject_into_pid_success() -> None:
    completed = _completed(0)
    with patch.object(inj.subprocess, "run", return_value=completed):
        result = inj.inject_into_pid(Path("inj.exe"), Path("tap.dll"), 4321)
    assert result.ok is True
    assert result.pid == 4321


def test_inject_into_pid_maps_known_error_codes() -> None:
    completed = _completed(5, "bitness mismatch")
    with patch.object(inj.subprocess, "run", return_value=completed):
        result = inj.inject_into_pid(Path("inj.exe"), Path("tap.dll"), 1)
    assert result.ok is False
    assert "32-bit" in result.detail
    assert "bitness mismatch" in result.detail


def test_inject_into_pid_reports_unknown_code() -> None:
    completed = _completed(99)
    with patch.object(inj.subprocess, "run", return_value=completed):
        result = inj.inject_into_pid(Path("inj.exe"), Path("tap.dll"), 1)
    assert result.ok is False
    assert "99" in result.detail


def test_inject_into_pid_survives_a_launch_failure() -> None:
    with patch.object(inj.subprocess, "run", side_effect=OSError("no such file")):
        result = inj.inject_into_pid(Path("missing.exe"), Path("tap.dll"), 1)
    assert result.ok is False
    assert "could not run the injector" in result.detail


def test_read_status_returns_the_last_line(tmp_path: Path) -> None:
    """A line with no pid prefix still reads as the latest status."""
    status = tmp_path / "swc-native.status"
    status.write_text("tap-loaded\ntap-hooked\n", encoding="ascii")
    assert inj.read_status(status) == "tap-hooked"


def test_read_statuses_attributes_each_line_to_its_client(tmp_path: Path) -> None:
    status = tmp_path / "swc-native.status"
    status.write_text("100 tap-loaded\n200 tap-loaded\n100 tap-hooked\n", encoding="ascii")
    assert inj.read_statuses(status) == {100: "tap-hooked", 200: "tap-loaded"}
    assert inj.read_status(status) == "tap-hooked"


def test_a_cross_process_lock_warning_does_not_mask_the_hook_status(tmp_path: Path) -> None:
    """The DLL reports a missing named mutex before tap-loaded, so the wait still ends on the hook."""
    status = tmp_path / "swc-native.status"
    status.write_text("100 tap-cross-process-lock-unavailable\n100 tap-loaded\n100 tap-hooked\n", encoding="ascii")
    assert inj.wait_for_hooks(status, [100], timeout=1.0) == {100: "tap-hooked"}


def test_read_status_missing_file_is_empty(tmp_path: Path) -> None:
    assert inj.read_status(tmp_path / "nope.status") == ""
    assert inj.read_statuses(tmp_path / "nope.status") == {}


def test_wait_for_hooks_returns_once_every_client_is_terminal(tmp_path: Path) -> None:
    status = tmp_path / "swc-native.status"
    status.write_text("100 tap-loaded\n200 tap-loaded\n100 tap-hooked\n200 tap-hook-failed\n", encoding="ascii")
    assert inj.wait_for_hooks(status, [100, 200], timeout=1.0) == {100: "tap-hooked", 200: "tap-hook-failed"}


def test_wait_for_hooks_does_not_let_one_client_speak_for_another(tmp_path: Path) -> None:
    """Waiting on the first terminal line reported capture for a client that never hooked."""
    status = tmp_path / "swc-native.status"
    status.write_text("100 tap-hooked\n", encoding="ascii")

    started = time.monotonic()
    statuses = inj.wait_for_hooks(status, [100, 200], timeout=0.4)

    assert time.monotonic() - started >= 0.4
    assert statuses == {100: "tap-hooked", 200: ""}


def test_wait_for_hooks_times_out_on_loaded_but_unhooked(tmp_path: Path) -> None:
    """tap-loaded is not terminal: the client may not have opened TLS yet."""
    status = tmp_path / "swc-native.status"
    status.write_text("100 tap-loaded\n", encoding="ascii")
    # A short timeout so the test does not linger; the best-so-far is returned.
    assert inj.wait_for_hooks(status, [100], timeout=0.4) == {100: "tap-loaded"}


@pytest.mark.parametrize("code", list(inj._INJECTOR_ERRORS))
def test_every_named_injector_error_has_a_message(code: int) -> None:
    completed = _completed(code)
    with patch.object(inj.subprocess, "run", return_value=completed):
        result = inj.inject_into_pid(Path("i.exe"), Path("t.dll"), 1)
    assert result.ok is False
    assert result.detail  # non-empty, human-readable


def test_attach_requires_a_running_client(monkeypatch) -> None:
    """attach_to_windows_client raises a clear error when the client is absent."""
    from fpdb_3_legacy import swc_native_capture, swc_tap_build

    monkeypatch.setattr(swc_native_capture.platform, "system", lambda: "Windows")
    monkeypatch.setattr(swc_native_capture, "build_tap", lambda **_: Path("tap.dll"))
    monkeypatch.setattr(swc_tap_build, "build_injector", lambda **_: Path("inj.exe"))
    monkeypatch.setattr(inj, "write_capture_config", lambda *_a, **_k: Path("swc-native.cfg"))
    monkeypatch.setattr(inj, "find_client_pids", lambda *_a, **_k: [])

    with pytest.raises(RuntimeError, match="not running"):
        swc_native_capture.attach_to_windows_client()


def _attach_with_statuses(tmp_path: Path, monkeypatch, statuses: dict[int, str], pids=(100, 200)) -> str:
    """Run attach_to_windows_client with the build, injection and status wait mocked out."""
    from fpdb_3_legacy import swc_native_capture, swc_tap_build

    monkeypatch.setattr(swc_native_capture.platform, "system", lambda: "Windows")
    monkeypatch.setattr(swc_native_capture, "build_tap", lambda **_: Path("tap.dll"))
    monkeypatch.setattr(swc_native_capture, "DEFAULT_ARCHIVE", tmp_path / "swc-native.raw")
    monkeypatch.setattr(swc_tap_build, "build_injector", lambda **_: Path("inj.exe"))
    monkeypatch.setattr(inj, "write_capture_config", lambda *_a, **_k: Path("swc-native.cfg"))
    monkeypatch.setattr(inj, "find_client_pids", lambda *_a, **_k: list(pids))
    monkeypatch.setattr(
        inj,
        "inject_into_pid",
        lambda _injector, _dll, pid: inj.InjectionResult(pid=pid, ok=True, detail="tap DLL loaded"),
    )
    monkeypatch.setattr(
        inj, "wait_for_hooks", lambda _p, injected, **_k: {pid: statuses.get(pid, "") for pid in injected}
    )

    return swc_native_capture.attach_to_windows_client()


def test_attach_reports_capture_active_when_every_client_hooked(tmp_path: Path, monkeypatch) -> None:
    message = _attach_with_statuses(tmp_path, monkeypatch, {100: "tap-hooked", 200: "tap-hooked"})
    assert "capture active" in message
    assert "2 client process(es)" in message


def test_attach_names_the_client_that_failed_to_hook(tmp_path: Path, monkeypatch) -> None:
    """All clients share one status file, so one failure must not be announced as capture for both."""
    message = _attach_with_statuses(tmp_path, monkeypatch, {100: "tap-hooked", 200: "tap-hook-failed"})
    assert "1 of 2 client process(es)" in message
    assert "pid 200 reported tap-hook-failed" in message
    assert "missing" in message


def test_attach_reports_a_client_still_waiting_for_tls(tmp_path: Path, monkeypatch) -> None:
    message = _attach_with_statuses(tmp_path, monkeypatch, {100: "tap-hooked", 200: "tap-loaded"})
    assert "1 of 2 client process(es)" in message
    assert "200" in message
    assert "capture active" not in message


def test_attach_keeps_the_lazy_tls_message_when_no_client_connected(tmp_path: Path, monkeypatch) -> None:
    message = _attach_with_statuses(tmp_path, monkeypatch, {100: "tap-loaded", 200: ""})
    assert "as soon as the client opens a secure connection" in message


def test_native_windows_sources_cover_review_safety_contracts() -> None:
    source_dir = Path(inj.__file__).resolve().parent
    injector_source = (source_dir / "swc_inject.c").read_text(encoding="utf-8")
    tap_source = (source_dir / "swc_native_tap.c").read_text(encoding="utf-8")

    assert "CommandLineToArgvW" in injector_source
    assert 'GetProcAddress(kernel32, "LoadLibraryW")' in injector_source
    assert "SuspendThread" in tap_source
    assert "GetThreadContext" in tap_source
    assert "CreateToolhelp32Snapshot" in tap_source
    assert "for (int i = 0; i < 600; i++)" not in tap_source

    # A timed-out remote LoadLibraryW may still be dereferencing the path.
    # The injector must not release that allocation unless the thread finished.
    assert "int release_remote_path = 1;" in injector_source
    timeout_start = injector_source.index("if (wait_result == WAIT_TIMEOUT)")
    timeout_end = injector_source.index("} else if", timeout_start)
    assert "release_remote_path = 0;" in injector_source[timeout_start:timeout_end]
    assert "if (release_remote_path)" in injector_source

    # Header + payload form one archive record and therefore need one Windows
    # critical section when SSL_read/SSL_write complete on different threads.
    assert "static SRWLOCK g_capture_lock = SRWLOCK_INIT;" in tap_source
    windows_record = tap_source.index("AcquireSRWLockExclusive(&g_capture_lock);")
    header_write = tap_source.index("write_all(capture_fd, &header, sizeof(header));", windows_record)
    payload_write = tap_source.index("write_all(capture_fd, buffer, (size_t)size);", header_write)
    unlock = tap_source.index("ReleaseSRWLockExclusive(&g_capture_lock);", payload_write)
    assert windows_record < header_write < payload_write < unlock

    # Every running client is injected and they all append to the same archive,
    # so that pair also needs an inter-process lock: the SRWLOCK orders threads
    # of one process only, and an interleaved header desynchronises the reader
    # for the rest of the session.
    assert "CreateMutexW(NULL, FALSE, SWC_CAPTURE_MUTEX_NAME)" in tap_source
    cross_process_wait = tap_source.index("WaitForSingleObject(g_capture_mutex, SWC_CAPTURE_LOCK_TIMEOUT_MS)")
    cross_process_release = tap_source.index("ReleaseMutex(g_capture_mutex);", unlock)
    assert cross_process_wait < windows_record < unlock < cross_process_release
    # A wedged peer must not stall the client's network thread indefinitely.
    assert "SWC_CAPTURE_LOCK_TIMEOUT_MS" in tap_source

    # Those same clients append to one status file, so a line carries its pid:
    # without it, whichever client hooks first speaks for all of them and one
    # that failed to hook is announced as capturing. The line is built without a
    # format function -- _snprintf leaves the buffer unterminated when it
    # truncates, so a caller has no safe way to measure what it produced -- and
    # the builder returns the length for the write that follows.
    assert "swc_status_line(line, sizeof(line), (unsigned long)GetCurrentProcessId(), message)" in tap_source
    assert "_snprintf(" not in tap_source
    assert "_write(fd, text, (unsigned int)text_length);" in tap_source

    # Lengths of strings from outside the function are bounded: strlen cannot
    # stop, so one that is not terminated reads off the end of its buffer.
    assert "strlen(" not in tap_source.split("#else", 1)[0] or "swc_bounded_length" in tap_source
    assert "swc_bounded_length(env_path, MAX_PATH)" in tap_source
    assert "while (path_length < SWC_MAX_PATH_CHARS" in injector_source
    assert "wcslen(" not in injector_source

    # A thread snapshot is a fixed list: a thread created after it was taken is
    # invisible to it and would run through the half-written entry point, so
    # suspension repeats until a whole pass finds nothing new.
    passes = tap_source.index("for (DWORD pass = 0; pass < SWC_MAX_SUSPEND_PASSES; pass++)")
    settled = tap_source.index("if (suspended_this_pass == 0)", passes)
    assert passes < settled

    # The trampoline pointer must be visible before any suspended SSL caller can
    # run through the newly patched entry point.
    publish = tap_source.index("*published_trampoline = (ssl_rw_cdecl_fn)tramp;")
    resume = tap_source.index("swc_resume_threads(&suspended);", publish)
    assert publish < resume
