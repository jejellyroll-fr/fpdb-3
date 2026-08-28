#!/usr/bin/env python3
"""The SwC native capture must not run for a player of another room.

Starting Auto Import compiled the SealsWithClubs TLS tap unconditionally. The
tap is built by shelling out to a C compiler, which a Windows machine almost
never has, so every user got the same line in the Auto Import log on every
Start:

    SwC Native Capture warning: [WinError 2] Le fichier specifie est introuvable

It was reported as a Winamax bug, which is exactly what it looks like from the
outside. SwC is the one room that ships no hand history files -- for every other
room the capture has nothing to do, so it is no longer started at all.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# GuiAutoImport uses legacy-style bare imports, so the package directory itself
# must be importable (same as test_guiautoimport_headless).
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "fpdb_3_legacy")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _make_config(swc_parameters):
    """A config whose get_site_parameters answers for SealsWithClubs only.

    ``swc_parameters`` is the dict to return, or a KeyError to raise -- which is
    what Configuration does for a site that is not in HUD_config.xml at all.
    """
    config = MagicMock()
    config.get_import_parameters.return_value = {"interval": "5"}
    config.get_supported_sites.return_value = []
    config.get_db_parameters.return_value = {}

    def get_site_parameters(site):
        if isinstance(swc_parameters, Exception):
            raise swc_parameters
        return swc_parameters

    config.get_site_parameters.side_effect = get_site_parameters
    return config


def _make_gui(config):
    from fpdb_3_legacy import GuiAutoImport

    settings = {
        "db-host": "localhost",
        "db-user": "fpdb",
        "db-password": "",
        "db-databaseName": "fpdb",
        "global_lock": MagicMock(),
    }
    with patch.object(GuiAutoImport.Importer, "Importer", return_value=MagicMock()):
        return GuiAutoImport.GuiAutoImport(settings, config, cli=True)


def _start_capture(config, *, supported=True):
    """Run start_swc_native_capture with the compiler and thread mocked out."""
    from fpdb_3_legacy import GuiAutoImport, swc_native_capture

    gui = _make_gui(config)
    with (
        patch.object(swc_native_capture, "build_tap") as build_tap,
        patch.object(swc_native_capture, "native_capture_supported", return_value=supported),
        patch.object(GuiAutoImport, "SwCNativeTailingThread") as thread,
    ):
        gui.start_swc_native_capture()
    return build_tap, thread


def test_a_site_that_is_not_configured_builds_nothing() -> None:
    """The reported case: no SealsWithClubs entry, so no compiler is invoked."""
    build_tap, thread = _start_capture(_make_config(KeyError("SealsWithClubs")))
    build_tap.assert_not_called()
    thread.assert_not_called()


def test_a_configured_but_disabled_site_builds_nothing() -> None:
    build_tap, thread = _start_capture(_make_config({"enabled": False}))
    build_tap.assert_not_called()
    thread.assert_not_called()


def test_the_capture_still_starts_for_a_swc_player() -> None:
    build_tap, thread = _start_capture(_make_config({"enabled": True}))
    build_tap.assert_called_once()
    thread.assert_called_once()
    thread.return_value.start.assert_called_once()


def test_nothing_is_built_where_the_tap_could_not_be_loaded() -> None:
    """Windows has no library interposition, so the tap has nothing to be loaded into.

    Building it there was the compiler failure users kept reporting -- for a
    library that nothing on the platform could have loaded even if gcc had been
    installed and it had built.
    """
    build_tap, thread = _start_capture(_make_config({"enabled": True}), supported=False)
    build_tap.assert_not_called()
    thread.assert_not_called()


def test_the_supported_platforms_are_the_ones_that_can_interpose() -> None:
    from fpdb_3_legacy.swc_native_capture import native_capture_supported

    assert native_capture_supported("Darwin") is True
    assert native_capture_supported("Linux") is True
    assert native_capture_supported("Windows") is False


def test_swc_tap_build_uses_the_first_compiler_on_the_path(monkeypatch) -> None:
    from fpdb_3_legacy import swc_tap_build

    monkeypatch.setattr(swc_tap_build.shutil, "which", lambda name: name == "gcc")

    assert swc_tap_build.resolve_compiler("Windows") == "gcc"


def test_swc_tap_build_reports_a_missing_compiler(monkeypatch) -> None:
    """The message users got was the OS's, and named nothing they could act on.

        SwC Native Capture warning: [WinError 2] Le fichier specifie est introuvable
    """
    from fpdb_3_legacy import swc_tap_build

    monkeypatch.setattr(swc_tap_build.shutil, "which", lambda _name: None)

    with pytest.raises(FileNotFoundError) as excinfo:
        swc_tap_build.resolve_compiler("Windows")

    message = str(excinfo.value)
    assert "x86_64-w64-mingw32-gcc" in message
    assert "gcc" in message
    assert "MinGW-w64" in message


def test_the_compiler_is_checked_before_it_is_run(monkeypatch, tmp_path) -> None:
    """No compiler must fail with our message, not with subprocess's."""
    from fpdb_3_legacy import swc_tap_build

    monkeypatch.setattr(swc_tap_build, "BUILD_DIR", tmp_path)
    monkeypatch.setattr(swc_tap_build.shutil, "which", lambda _name: None)
    run = MagicMock()
    monkeypatch.setattr(swc_tap_build.subprocess, "run", run)

    with pytest.raises(FileNotFoundError, match="no C compiler found"):
        swc_tap_build.build_tap(force=True)

    run.assert_not_called()
