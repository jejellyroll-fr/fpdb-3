#!/usr/bin/env python3
"""Tests for the headless (CLI) auto-import mode of GuiAutoImport.

`GuiAutoImport(..., cli=True)` used to raise a bare NotImplementedError. It now
builds a GUI-less importer and `run_headless()` drives the same import engine the
GUI auto-import tab uses (autoSummaryGrab + runUpdated), stepped by a time.sleep
loop instead of a Qt timer. These tests mock the Importer so no database is
required — they cover the driver logic, not the import engine itself.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# GuiAutoImport uses legacy-style bare imports (e.g. ``import interlocks``), so
# the fpdb_3_legacy package directory must be importable directly.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "fpdb_3_legacy")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _make_settings(lock):
    return {
        "db-host": "localhost",
        "db-user": "fpdb",
        "db-password": "",
        "db-databaseName": "fpdb",
        "global_lock": lock,
    }


def _make_config(interval=5):
    config = MagicMock()
    config.get_import_parameters.return_value = {"interval": str(interval)}
    config.get_supported_sites.return_value = []
    config.get_db_parameters.return_value = {}
    return config


def _make_gui(settings, config):
    """Build a headless GuiAutoImport with the Importer mocked out (no DB)."""
    from fpdb_3_legacy import GuiAutoImport

    with patch.object(GuiAutoImport.Importer, "Importer", return_value=MagicMock()):
        return GuiAutoImport.GuiAutoImport(settings, config, cli=True)


def test_cli_constructor_does_not_raise():
    """cli=True must build a headless importer instead of raising."""
    gui = _make_gui(_make_settings(MagicMock()), _make_config())
    assert gui.cli is True
    # Imported hands are fed to the HUD over ZMQ, exactly like the GUI.
    gui.importer.setCallHud.assert_called_with(True)
    gui.importer.setMode.assert_called_with("auto")


def test_addtext_headless_routes_to_logger():
    """In cli mode addText must log instead of emitting a Qt signal."""
    gui = _make_gui(_make_settings(MagicMock()), _make_config())
    with patch.object(sys.modules["fpdb_3_legacy.GuiAutoImport"], "log") as mock_log:
        gui.addText("something went wrong\n", "error")
        gui.addText("just fyi", "info")
    mock_log.error.assert_called_once_with("something went wrong")
    mock_log.info.assert_called_once_with("just fyi")


def test_run_headless_aborts_when_lock_unavailable():
    """If the global lock can't be taken, run_headless returns 1 and imports nothing."""
    lock = MagicMock()
    lock.acquire.return_value = False
    gui = _make_gui(_make_settings(lock), _make_config())

    assert gui.run_headless() == 1
    gui.importer.runUpdated.assert_not_called()
    lock.release.assert_not_called()


def test_run_headless_imports_then_shuts_down_cleanly():
    """A normal run imports at least one cycle then releases the lock on interrupt."""
    lock = MagicMock()
    lock.acquire.return_value = True
    gui = _make_gui(_make_settings(lock), _make_config(interval=1))
    gui.updatePaths = MagicMock()

    # Stop the otherwise-infinite loop after the first sleep.
    with patch.object(sys.modules["fpdb_3_legacy.GuiAutoImport"].time, "sleep", side_effect=KeyboardInterrupt):
        rc = gui.run_headless(launch_hud=False)

    assert rc == 0
    gui.updatePaths.assert_called_once()
    gui.importer.autoSummaryGrab.assert_any_call()  # per-cycle grab
    gui.importer.runUpdated.assert_called_once()
    gui.importer.autoSummaryGrab.assert_called_with(force=True)  # final grab
    lock.release.assert_called_once()


def test_run_headless_survives_a_failing_cycle():
    """One failing import cycle must not kill the loop or leak the lock."""
    lock = MagicMock()
    lock.acquire.return_value = True
    gui = _make_gui(_make_settings(lock), _make_config(interval=1))
    gui.updatePaths = MagicMock()
    gui.importer.runUpdated.side_effect = RuntimeError("boom")

    with patch.object(sys.modules["fpdb_3_legacy.GuiAutoImport"].time, "sleep", side_effect=KeyboardInterrupt):
        rc = gui.run_headless(launch_hud=False)

    assert rc == 0
    gui.importer.runUpdated.assert_called_once()  # cycle ran despite raising
    lock.release.assert_called_once()  # lock still released


def test_update_paths_monitors_multiple_sites_and_content_types(tmp_path):
    config = _make_config()
    sites = ["PokerStars", "Winamax"]
    config.get_supported_sites.return_value = sites
    config.get_site_parameters.side_effect = lambda site: {"enabled": site in sites}

    paths = {}
    for site in sites:
        hh_path = tmp_path / site / "hands"
        ts_path = tmp_path / site / "summaries"
        hh_path.mkdir(parents=True)
        ts_path.mkdir()
        paths[site] = {
            "hud-defaultPath": str(hh_path),
            "hud-defaultTSPath": str(ts_path),
        }
    config.get_default_paths.side_effect = paths.__getitem__

    gui = _make_gui(_make_settings(MagicMock()), config)
    gui.importer.dirlist = {}
    gui.addText = MagicMock()

    gui.updatePaths()

    expected = {
        (site, content_type): site_paths[path_key]
        for site, site_paths in paths.items()
        for content_type, path_key in (("hh", "hud-defaultPath"), ("ts", "hud-defaultTSPath"))
    }
    assert gui.importer.addImportDirectory.call_count == 4
    for site_key, path in expected.items():
        gui.importer.addImportDirectory.assert_any_call(path, monitor=True, site=site_key)


def test_hud_base_path_is_module_dir_and_holds_hud_main():
    """The HUD base path must resolve next to the module (holds HUD_main.pyw),
    independent of sys.path[0]/CWD."""
    from fpdb_3_legacy import GuiAutoImport

    base = GuiAutoImport.GuiAutoImport._hud_base_path()
    assert os.path.basename(base) == "fpdb_3_legacy"
    assert os.path.isfile(os.path.join(base, "HUD_main.pyw"))


@pytest.mark.skipif(sys.platform == "win32", reason="exercises the POSIX/source HUD-launch branch")
def test_launch_hud_uses_module_relative_path(monkeypatch, tmp_path):
    """_launch_hud must find HUD_main.pyw even when sys.path[0]/CWD are unrelated."""
    settings = _make_settings(MagicMock())
    settings["cl_options"] = ""
    config = _make_config()
    config.install_method = "source"
    gui = _make_gui(settings, config)

    gui_mod = sys.modules["fpdb_3_legacy.GuiAutoImport"]
    # Simulate a hostile launch environment.
    monkeypatch.setattr(gui_mod.sys, "path", ["/nowhere", *sys.path])
    monkeypatch.chdir(tmp_path)

    with patch.object(gui_mod.subprocess, "Popen", return_value=MagicMock()) as mock_popen:
        gui._launch_hud()

    command = mock_popen.call_args.args[0]
    hud_path = command[0]
    assert hud_path.endswith(os.path.join("fpdb_3_legacy", "HUD_main.pyw"))
    assert os.path.isfile(hud_path)  # resolved to a real file regardless of CWD/sys.path


@pytest.mark.skipif(sys.platform == "win32", reason="exercises the POSIX/source HUD-launch branch (list command)")
def test_launch_hud_spawns_hud_main():
    """_launch_hud builds a HUD_main command and spawns it via subprocess.Popen."""
    settings = _make_settings(MagicMock())
    settings["cl_options"] = "--config foo.xml"
    config = _make_config()
    config.install_method = "source"  # exercise the Linux/macOS/source branch
    gui = _make_gui(settings, config)

    gui_mod = sys.modules["fpdb_3_legacy.GuiAutoImport"]
    with patch.object(gui_mod.subprocess, "Popen", return_value=MagicMock()) as mock_popen:
        gui._launch_hud()

    mock_popen.assert_called_once()
    command = mock_popen.call_args.args[0]
    # The source/Linux/macOS branch builds a list command ending in HUD_main.pyw + cl_options.
    assert any("HUD_main" in str(part) for part in command)
    assert gui.pipe_to_hud is not None


def test_run_headless_launches_and_stops_hud():
    """With launch_hud=True the HUD subprocess is spawned then terminated on stop."""
    lock = MagicMock()
    lock.acquire.return_value = True
    gui = _make_gui(_make_settings(lock), _make_config(interval=1))
    gui.updatePaths = MagicMock()

    fake_hud = MagicMock()

    def fake_launch():
        gui.pipe_to_hud = fake_hud

    gui._launch_hud = MagicMock(side_effect=fake_launch)

    with patch.object(sys.modules["fpdb_3_legacy.GuiAutoImport"].time, "sleep", side_effect=KeyboardInterrupt):
        rc = gui.run_headless(launch_hud=True)

    assert rc == 0
    gui._launch_hud.assert_called_once()  # HUD was launched
    fake_hud.terminate.assert_called_once()  # HUD was stopped on shutdown
    assert gui.pipe_to_hud is None
    lock.release.assert_called_once()


def test_run_headless_passes_config_not_quiet_flag_to_hud():
    """The HUD must receive the config path, never the auto-import's own -q flag."""
    lock = MagicMock()
    lock.acquire.return_value = True
    settings = _make_settings(lock)
    settings["cl_options"] = "-q"  # what GuiAutoImport.main() would set
    config = _make_config()
    config.file = "/home/user/.fpdb/HUD_config.xml"
    gui = _make_gui(settings, config)
    gui.updatePaths = MagicMock()

    captured = {}

    def fake_launch():
        captured["cl_options"] = gui.settings["cl_options"]
        gui.pipe_to_hud = MagicMock()

    gui._launch_hud = MagicMock(side_effect=fake_launch)

    with patch.object(sys.modules["fpdb_3_legacy.GuiAutoImport"].time, "sleep", side_effect=KeyboardInterrupt):
        gui.run_headless(launch_hud=True)

    assert captured["cl_options"] == "-c /home/user/.fpdb/HUD_config.xml"
    assert "-q" not in captured["cl_options"]


def test_run_headless_survives_hud_launch_failure():
    """A HUD that fails to launch must not stop imports."""
    lock = MagicMock()
    lock.acquire.return_value = True
    gui = _make_gui(_make_settings(lock), _make_config(interval=1))
    gui.updatePaths = MagicMock()
    gui._launch_hud = MagicMock(side_effect=OSError("no HUD_main"))

    with patch.object(sys.modules["fpdb_3_legacy.GuiAutoImport"].time, "sleep", side_effect=KeyboardInterrupt):
        rc = gui.run_headless(launch_hud=True)

    assert rc == 0
    gui._launch_hud.assert_called_once()
    gui.importer.runUpdated.assert_called_once()  # imports ran despite HUD failure
    lock.release.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
