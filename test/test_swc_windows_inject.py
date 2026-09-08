"""The Windows tap-injection helpers.

These orchestrate loading the capture DLL into the running SwC client: find the
client process, write the config the injected DLL reads, run the injector, and
read back the DLL's status file. They are plain Python (psutil + subprocess), so
they are exercised here on every platform with those two boundaries mocked.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from fpdb_3_legacy import swc_windows_inject as inj


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
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    with patch.object(inj.subprocess, "run", return_value=completed):
        result = inj.inject_into_pid(Path("inj.exe"), Path("tap.dll"), 4321)
    assert result.ok is True
    assert result.pid == 4321


def test_inject_into_pid_maps_known_error_codes() -> None:
    completed = subprocess.CompletedProcess(args=[], returncode=5, stdout="", stderr="bitness mismatch")
    with patch.object(inj.subprocess, "run", return_value=completed):
        result = inj.inject_into_pid(Path("inj.exe"), Path("tap.dll"), 1)
    assert result.ok is False
    assert "32-bit" in result.detail
    assert "bitness mismatch" in result.detail


def test_inject_into_pid_reports_unknown_code() -> None:
    completed = subprocess.CompletedProcess(args=[], returncode=99, stdout="", stderr="")
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
    status = tmp_path / "swc-native.status"
    status.write_text("tap-loaded\ntap-hooked\n", encoding="ascii")
    assert inj.read_status(status) == "tap-hooked"


def test_read_status_missing_file_is_empty(tmp_path: Path) -> None:
    assert inj.read_status(tmp_path / "nope.status") == ""


def test_wait_for_hook_returns_on_terminal_status(tmp_path: Path) -> None:
    status = tmp_path / "swc-native.status"
    status.write_text("tap-loaded\ntap-hooked\n", encoding="ascii")
    assert inj.wait_for_hook(status, timeout=1.0) == "tap-hooked"


def test_wait_for_hook_times_out_on_loaded_but_unhooked(tmp_path: Path) -> None:
    """tap-loaded is not terminal: the client may not have opened TLS yet."""
    status = tmp_path / "swc-native.status"
    status.write_text("tap-loaded\n", encoding="ascii")
    # A short timeout so the test does not linger; the best-so-far is returned.
    assert inj.wait_for_hook(status, timeout=0.4) == "tap-loaded"


@pytest.mark.parametrize("code", list(inj._INJECTOR_ERRORS))
def test_every_named_injector_error_has_a_message(code: int) -> None:
    completed = subprocess.CompletedProcess(args=[], returncode=code, stdout="", stderr="")
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
