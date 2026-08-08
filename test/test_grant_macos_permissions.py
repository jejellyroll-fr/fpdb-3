"""Unit tests for tools.grant_macos_permissions module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from tools import grant_macos_permissions


def test_clear_quarantine_returns_false_for_non_existent_path(tmp_path: Path) -> None:
    non_existent = tmp_path / "non_existent.app"
    assert not grant_macos_permissions.clear_quarantine(non_existent)


def test_re_sign_bundle_returns_false_for_non_existent_path(tmp_path: Path) -> None:
    non_existent = tmp_path / "non_existent.app"
    assert not grant_macos_permissions.re_sign_bundle(non_existent)


def test_setup_app_bundle_does_not_destroy_a_stable_signature_by_default(tmp_path: Path, monkeypatch) -> None:
    app_path = tmp_path / "fpdb.app"
    app_path.mkdir()

    monkeypatch.setattr(grant_macos_permissions, "clear_quarantine", lambda p: True)
    monkeypatch.setattr(grant_macos_permissions, "re_sign_bundle", lambda p: True)

    results = grant_macos_permissions.setup_app_bundle(app_path)
    assert results["quarantine_cleared"] is True
    assert results["signed"] is False


def test_check_and_print_permission_status(monkeypatch, capsys) -> None:
    fake_status = MagicMock(screen_recording=True, accessibility=True)
    monkeypatch.setattr(grant_macos_permissions.permissions, "get_status", lambda: fake_status)
    monkeypatch.setattr(grant_macos_permissions.permissions, "describe_missing", lambda s: [])

    status = grant_macos_permissions.check_and_print_permission_status()
    captured = capsys.readouterr()

    assert status.screen_recording is True
    assert "Granted" in captured.out
    assert "All required macOS permissions are granted!" in captured.out


def test_setup_app_bundle_flags_select_one_step(tmp_path: Path, monkeypatch) -> None:
    app_path = tmp_path / "fpdb.app"
    app_path.mkdir()

    monkeypatch.setattr(grant_macos_permissions, "clear_quarantine", lambda p: True)
    monkeypatch.setattr(grant_macos_permissions, "re_sign_bundle", lambda p: True)

    only_clear = grant_macos_permissions.setup_app_bundle(app_path, sign=False)
    assert only_clear == {"quarantine_cleared": True, "signed": False}

    only_sign = grant_macos_permissions.setup_app_bundle(app_path, clear=False, sign=True)
    assert only_sign == {"quarantine_cleared": False, "signed": True}


def test_main_cli_returns_0(monkeypatch) -> None:
    monkeypatch.setattr(grant_macos_permissions, "_IS_MACOS", False)
    assert grant_macos_permissions.main([]) == 0


def test_main_reports_a_missing_bundle(tmp_path: Path, monkeypatch, capsys) -> None:
    # A path that is not there used to be skipped in silence, which reads as
    # success to whoever typed the path wrong.
    monkeypatch.setattr(grant_macos_permissions, "_IS_MACOS", True)

    exit_code = grant_macos_permissions.main(["--app-path", str(tmp_path / "absent.app")])

    assert exit_code == 1
    assert "No bundle at" in capsys.readouterr().err


def test_main_can_skip_the_status_check(monkeypatch, capsys) -> None:
    monkeypatch.setattr(grant_macos_permissions, "_IS_MACOS", True)
    called = []
    monkeypatch.setattr(
        grant_macos_permissions,
        "check_and_print_permission_status",
        lambda: called.append(True),
    )

    assert grant_macos_permissions.main(["--no-check-status"]) == 0
    assert called == []

    assert grant_macos_permissions.main([]) == 0
    assert called == [True]
