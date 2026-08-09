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
    path_sync_states = []
    gui.updatePaths.side_effect = lambda: path_sync_states.append(gui.doAutoImportBool)

    # Stop the otherwise-infinite loop after the first sleep.
    with patch.object(sys.modules["fpdb_3_legacy.GuiAutoImport"].time, "sleep", side_effect=KeyboardInterrupt):
        rc = gui.run_headless(launch_hud=False)

    assert rc == 0
    gui.updatePaths.assert_called_once()
    assert path_sync_states == [True]
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
    gui.doAutoImportBool = True

    gui.updatePaths()

    expected = {
        (site, content_type): site_paths[path_key]
        for site, site_paths in paths.items()
        for content_type, path_key in (("hh", "hud-defaultPath"), ("ts", "hud-defaultTSPath"))
    }
    assert gui.importer.addImportDirectory.call_count == 4
    for site_key, path in expected.items():
        gui.importer.addImportDirectory.assert_any_call(path, monitor=True, site=site_key)
    assert [entry.args[0] for entry in config.get_default_paths.call_args_list] == sites


def test_passive_path_refresh_does_not_reload_or_probe_configuration():
    """Opening the tab or receiving a passive observer refresh touches no paths."""
    config = _make_config()
    config.get_supported_sites.side_effect = AssertionError("site paths must remain untouched while stopped")
    gui = _make_gui(_make_settings(MagicMock()), config)
    gui.importer.dirlist = {("Winamax", "hh"): ["/previous/path", "passthrough"]}

    gui.updatePaths()

    config.reload.assert_not_called()
    config.get_supported_sites.assert_not_called()
    config.get_default_paths.assert_not_called()
    gui.importer.addImportDirectory.assert_not_called()
    gui.importer.removeImportDirectory.assert_not_called()


def test_update_paths_resolves_enabled_sites_but_never_disabled_sites(tmp_path):
    """Active path recovery is allowed only for enabled sites."""
    detected_hands = tmp_path / "Winamax" / "accounts" / "Hero" / "history"
    detected_hands.mkdir(parents=True)
    config = _make_config()
    config.get_supported_sites.return_value = ["Winamax", "Disabled", "NoPaths"]
    config.get_site_parameters.side_effect = {
        "Winamax": {
            "enabled": True,
        },
        "Disabled": {
            "enabled": False,
            "HH_path": "~/Downloads/disabled/hands",
            "TS_path": "~/Library/Application Support/disabled/summaries",
        },
        "NoPaths": {"enabled": True},
    }.__getitem__

    def detected_paths(site):
        if site == "Disabled":
            raise AssertionError("disabled site path detection must never run")
        if site == "Winamax":
            return {"hud-defaultPath": str(detected_hands)}
        return {}

    config.get_default_paths.side_effect = detected_paths

    gui = _make_gui(_make_settings(MagicMock()), config)
    gui.importer.dirlist = {}
    gui.addText = MagicMock()
    gui.doAutoImportBool = True

    gui.updatePaths()

    gui.importer.addImportDirectory.assert_called_once_with(
        str(detected_hands),
        monitor=True,
        site=("Winamax", "hh"),
    )
    assert [entry.args[0] for entry in config.get_default_paths.call_args_list] == ["Winamax", "NoPaths"]


def test_active_config_refresh_replaces_only_the_changed_watch(tmp_path):
    """Dynamic path changes still resynchronise an active auto-import session."""
    old_hands = tmp_path / "old" / "hands"
    new_hands = tmp_path / "new" / "hands"
    new_hands.mkdir(parents=True)
    config = _make_config()
    config.get_supported_sites.return_value = ["Winamax"]
    config.get_site_parameters.return_value = {"enabled": True}
    config.get_default_paths.return_value = {"hud-defaultPath": str(new_hands)}
    gui = _make_gui(_make_settings(MagicMock()), config)
    gui.importer.dirlist = {("Winamax", "hh"): [str(old_hands), "passthrough"]}
    gui.addText = MagicMock()
    gui.doAutoImportBool = True

    gui.updatePaths()

    config.reload.assert_called_once_with()
    gui.importer.removeImportDirectory.assert_called_once_with(str(old_hands), site=("Winamax", "hh"))
    gui.importer.addImportDirectory.assert_called_once_with(
        str(new_hands),
        monitor=True,
        site=("Winamax", "hh"),
    )


def test_standalone_main_does_not_resolve_paths_before_headless_start():
    """The standalone entry point must not auto-detect a default site path."""
    from fpdb_3_legacy import GuiAutoImport

    config = _make_config()
    config.get_default_paths.side_effect = AssertionError("default path resolution is not startup work")
    runner = MagicMock()
    runner.run_headless.return_value = 0

    with (
        patch.object(GuiAutoImport.Configuration, "Config", return_value=config),
        patch.object(GuiAutoImport, "GuiAutoImport", return_value=runner) as gui_class,
        patch.object(GuiAutoImport.interlocks, "InterProcessLock", return_value=MagicMock()),
    ):
        assert GuiAutoImport.main(["-q"]) == 0

    config.get_default_paths.assert_not_called()
    gui_class.assert_called_once()
    assert gui_class.call_args.kwargs["cli"] is True


def test_hud_base_path_is_module_dir_and_holds_hud_main():
    """The HUD base path must resolve next to the module (holds HUD_main.pyw),
    independent of sys.path[0]/CWD."""
    from fpdb_3_legacy import GuiAutoImport

    base = GuiAutoImport.GuiAutoImport._hud_base_path()
    assert os.path.basename(base) == "fpdb_3_legacy"
    assert os.path.isfile(os.path.join(base, "HUD_main.pyw"))


@pytest.mark.parametrize(
    ("platform_name", "os_name", "executable_name"),
    [
        ("linux", "posix", "HUD_main"),
        ("win32", "nt", "HUD_main.exe"),
    ],
)
def test_launch_hud_uses_bundled_sibling_executable(monkeypatch, tmp_path, platform_name, os_name, executable_name):
    """Frozen builds launch the HUD next to fpdb, never from sys._MEIPASS."""
    settings = _make_settings(MagicMock())
    settings["cl_options"] = "--config bundled.xml"
    config = _make_config()
    config.install_method = "app" if platform_name == "darwin" else "exe"
    gui = _make_gui(settings, config)

    gui_mod = sys.modules["fpdb_3_legacy.GuiAutoImport"]
    fpdb_executable = tmp_path / ("fpdb.exe" if os_name == "nt" else "fpdb")
    hud_executable = tmp_path / executable_name
    fpdb_executable.touch()
    hud_executable.touch()

    monkeypatch.setattr(gui_mod.sys, "frozen", True, raising=False)
    monkeypatch.setattr(gui_mod.sys, "executable", str(fpdb_executable))
    monkeypatch.setattr(gui_mod.sys, "platform", platform_name)
    monkeypatch.setattr(gui_mod.os, "name", os_name)
    monkeypatch.setattr(gui_mod.sys, "_MEIPASS", str(tmp_path / "wrong-resource-directory"), raising=False)

    with patch.object(gui_mod.subprocess, "Popen", return_value=MagicMock()) as mock_popen:
        gui._launch_hud()

    command = mock_popen.call_args.args[0]
    assert command == [str(hud_executable), "--config", "bundled.xml"]
    popen_kwargs = mock_popen.call_args.kwargs
    assert popen_kwargs["env"]["PYINSTALLER_RESET_ENVIRONMENT"] == "1"


def test_launch_hud_pyinstaller_macos_reuses_the_main_executable(monkeypatch, tmp_path):
    """The macOS HUD must retain the main bundle's privacy identity."""
    settings = _make_settings(MagicMock())
    settings["cl_options"] = "--config bundled.xml"
    config = _make_config()
    config.install_method = "app"
    gui = _make_gui(settings, config)

    gui_mod = sys.modules["fpdb_3_legacy.GuiAutoImport"]
    fpdb_executable = tmp_path / "fpdb"
    fpdb_executable.touch()
    monkeypatch.setattr(gui_mod.sys, "frozen", True, raising=False)
    monkeypatch.setattr(gui_mod.sys, "executable", str(fpdb_executable))
    monkeypatch.setattr(gui_mod.sys, "platform", "darwin")
    monkeypatch.setattr(gui, "_hud_base_path", lambda: str(tmp_path))

    with patch.object(gui_mod.subprocess, "Popen", return_value=MagicMock()) as mock_popen:
        gui._launch_hud()

    command = mock_popen.call_args.args[0]
    assert command == [str(fpdb_executable), "--hud", "--config", "bundled.xml"]
    child_env = mock_popen.call_args.kwargs["env"]
    assert child_env["PYINSTALLER_RESET_ENVIRONMENT"] == "1"


def test_launch_hud_pyoxidizer_reuses_main_executable(monkeypatch, tmp_path):
    """PyOxidizer dispatches HUD mode through its single embedded executable."""
    settings = _make_settings(MagicMock())
    settings["cl_options"] = "--config bundled.xml"
    gui = _make_gui(settings, _make_config())

    gui_mod = sys.modules["fpdb_3_legacy.GuiAutoImport"]
    fpdb_executable = tmp_path / "fpdb"
    monkeypatch.setattr(gui_mod.sys, "frozen", "pyoxidizer", raising=False)
    monkeypatch.setattr(gui_mod.sys, "executable", str(fpdb_executable))
    monkeypatch.setattr(gui_mod.sys, "platform", "darwin")

    with patch.object(gui_mod.subprocess, "Popen", return_value=MagicMock()) as mock_popen:
        gui._launch_hud()

    command = mock_popen.call_args.args[0]
    assert command == [str(fpdb_executable), "--hud", "--config", "bundled.xml"]
    assert "env" not in mock_popen.call_args.kwargs


def test_launch_hud_pyoxidizer_non_macos_does_not_request_macos_permissions(monkeypatch, tmp_path):
    settings = _make_settings(MagicMock())
    settings["cl_options"] = ""
    gui = _make_gui(settings, _make_config())

    gui_mod = sys.modules["fpdb_3_legacy.GuiAutoImport"]
    monkeypatch.setattr(gui_mod.sys, "frozen", "pyoxidizer", raising=False)
    monkeypatch.setattr(gui_mod.sys, "executable", str(tmp_path / "fpdb"))
    monkeypatch.setattr(gui_mod.sys, "platform", "linux")

    with patch.object(gui_mod.subprocess, "Popen", return_value=MagicMock()) as mock_popen:
        gui._launch_hud()

    assert "env" not in mock_popen.call_args.kwargs


def test_check_hud_process_started_clears_terminated_process():
    """A helper that exits during startup is reported and can be relaunched."""
    gui = _make_gui(_make_settings(MagicMock()), _make_config())
    process = MagicMock(pid=1234)
    process.poll.return_value = 7
    gui.pipe_to_hud = process
    gui.addText = MagicMock()

    gui._check_hud_process_started()

    gui.addText.assert_called_once_with("\n*** HUD_main exited during startup with code 7", "error")
    assert gui.pipe_to_hud is None


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
