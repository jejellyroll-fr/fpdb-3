#!/usr/bin/env python3
"""Tests for falling back to a detected hand-history directory.

A configured HH_path routinely points nowhere: the shipped defaults are Windows
paths ("C:/Program Files/SealsWithClubs/handhistories"), and a config carried
between machines keeps the previous home directory. get_default_paths() then
returned "** ERROR DEFAULT PATH IN CONFIG DOES NOT EXIST **" and auto-import
silently skipped the site.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fpdb_3_legacy import Configuration


def _config(hh_path, screen_name="hero", ts_path=""):
    cfg = Configuration.Config.__new__(Configuration.Config)  # bypass the heavy __init__
    site = MagicMock()
    site.HH_path = hh_path
    site.TS_path = ts_path
    site.screen_name = screen_name
    cfg.supported_sites = {"SealsWithClubs": site}
    cfg.imp = MagicMock()
    cfg.imp.hhBulkPath = ""
    return cfg


@pytest.fixture
def swc_tree(tmp_path, monkeypatch):
    """A SwC layout: <base>/Hand History/<account>."""
    base = tmp_path / "Documents" / "SwC Poker" / "Hand History"
    (base / "hero").mkdir(parents=True)
    (base / "villain").mkdir()
    monkeypatch.setitem(
        Configuration.HH_PATH_CANDIDATES["SealsWithClubs"],
        Configuration.sysPlatform,
        (str(base),),
    )
    return base


def test_detects_the_account_folder_of_the_hero(swc_tree):
    cfg = _config(hh_path="/Users/someone-else/SwC Poker/Hand History/hero")

    assert cfg.detect_hh_path("SealsWithClubs") == str(swc_tree / "hero")


def test_falls_back_to_the_base_when_the_account_folder_is_absent(swc_tree):
    cfg = _config(hh_path="/nope", screen_name="never-played-yet")

    assert cfg.detect_hh_path("SealsWithClubs") == str(swc_tree)


def test_a_broken_configured_path_resolves_to_the_detected_one(swc_tree):
    cfg = _config(hh_path="/Users/someone-else/SwC Poker/Hand History/hero")

    paths = cfg.get_default_paths("SealsWithClubs")

    assert paths["hud-defaultPath"] == str(swc_tree / "hero")
    assert os.path.isdir(paths["hud-defaultPath"])


def test_a_working_configured_path_is_left_alone(swc_tree):
    configured = str(swc_tree / "villain")
    cfg = _config(hh_path=configured)

    assert cfg.get_default_paths("SealsWithClubs")["hud-defaultPath"] == configured


def test_an_unknown_site_still_reports_the_error(tmp_path):
    cfg = _config(hh_path=str(tmp_path / "gone"))
    cfg.supported_sites = {"NoSuchSite": cfg.supported_sites["SealsWithClubs"]}

    paths = cfg.get_default_paths("NoSuchSite")

    assert paths["hud-defaultPath"] == "** ERROR DEFAULT PATH IN CONFIG DOES NOT EXIST **"


def test_detection_returns_none_when_nothing_is_installed(monkeypatch, tmp_path):
    monkeypatch.setitem(
        Configuration.HH_PATH_CANDIDATES["SealsWithClubs"],
        Configuration.sysPlatform,
        (str(tmp_path / "absent"),),
    )
    cfg = _config(hh_path="/nope")

    assert cfg.detect_hh_path("SealsWithClubs") is None


# ── Americas Cardroom / WPN JSON config detection ──


def _acr_config(screen_name="edinapoker"):
    """Minimal Config stub for an ACR Poker site."""
    cfg = Configuration.Config.__new__(Configuration.Config)
    site = MagicMock()
    site.HH_path = "C:\\ACR Poker\\handHistory\\"
    site.TS_path = "C:\\ACR Poker\\TournamentSummary"
    site.screen_name = screen_name
    cfg.supported_sites = {"ACR Poker": site}
    cfg.imp = MagicMock()
    cfg.imp.hhBulkPath = ""
    return cfg


@pytest.fixture
def acr_json_tree(tmp_path, monkeypatch):
    """Simulate the ACR Electron client's local-storage JSON files."""
    storage = tmp_path / "Library" / "Application Support" / "Loading" / "storage"
    storage.mkdir(parents=True)

    hh_base = tmp_path / "Downloads" / "AmericasCardroom" / "handHistory"
    (hh_base / "edinapoker").mkdir(parents=True)

    ts_base = tmp_path / "Downloads" / "AmericasCardroom" / "TournamentSummary"
    ts_base.mkdir(parents=True)

    import json

    (storage / "hhDirPath_AmericasCardroom.json").write_text(
        json.dumps({"path": str(hh_base)}), encoding="utf-8"
    )
    (storage / "tsDirPath_AmericasCardroom.json").write_text(
        json.dumps({"path": str(ts_base)}), encoding="utf-8"
    )

    # Patch _read_acr_json_path to use our tmp storage instead of ~/Library/...
    def patched_read(acr_key, kind, screen_name):
        prefix = "hhDirPath" if kind == "hh" else "tsDirPath"
        from pathlib import Path
        import json as _json

        json_path = storage / f"{prefix}_{acr_key}.json"
        if not json_path.is_file():
            return None
        try:
            data = _json.loads(json_path.read_text(encoding="utf-8"))
            base = Path(data["path"])
            if screen_name and (base / screen_name).is_dir():
                return str(base / screen_name)
            if base.is_dir():
                return str(base)
        except (_json.JSONDecodeError, KeyError, OSError):
            pass
        return None

    monkeypatch.setattr(Configuration.Config, "_read_acr_json_path", staticmethod(patched_read))
    monkeypatch.setattr(Configuration, "sysPlatform", "Darwin")
    return tmp_path


def test_acr_detect_hh_path_reads_json_config(acr_json_tree):
    cfg = _acr_config(screen_name="edinapoker")
    result = cfg.detect_hh_path("ACR Poker")
    assert result is not None
    assert result.endswith("edinapoker")
    assert "AmericasCardroom/handHistory" in result


def test_acr_detect_hh_path_falls_back_to_base_if_no_account_folder(acr_json_tree):
    cfg = _acr_config(screen_name="nobody")
    result = cfg.detect_hh_path("ACR Poker")
    assert result is not None
    assert result.endswith("handHistory")


def test_acr_detect_ts_path_reads_json_config(acr_json_tree):
    cfg = _acr_config(screen_name="edinapoker")
    result = cfg.detect_ts_path("ACR Poker")
    assert result is not None
    assert "TournamentSummary" in result


def test_acr_detect_returns_none_when_json_missing(monkeypatch):
    monkeypatch.setattr(Configuration, "sysPlatform", "Darwin")
    # Patch to always return None (simulating missing JSON files)
    monkeypatch.setattr(
        Configuration.Config, "_read_acr_json_path", staticmethod(lambda *a: None)
    )
    cfg = _acr_config()
    assert cfg.detect_ts_path("ACR Poker") is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
