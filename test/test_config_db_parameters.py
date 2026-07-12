#!/usr/bin/env python3
"""Round-trip tests for the Configuration database-parameter API.

Covers add_db_parameters / set_db_parameters / del_db_parameters against a real
Config backed by a temporary copy of HUD_config.xml — including the in-memory
supported_databases cache (which previously had a dp_/db_ typo) and persistence
across reload.
"""

from __future__ import annotations

import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fpdb_3_legacy import Configuration

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_TEMPLATE = os.path.join(REPO_ROOT, "HUD_config.xml")


@pytest.fixture
def config(tmp_path):
    cfg_path = tmp_path / "HUD_config.xml"
    shutil.copy(CONFIG_TEMPLATE, cfg_path)
    return Configuration.Config(file=str(cfg_path))


def test_add_database_appears_in_supported(config):
    config.add_db_parameters(
        db_name="pgtest", db_server="postgresql",
        db_ip="dbhost", db_port="5432", db_user="alice", db_pass="secret",
    )
    assert "pgtest" in config.supported_databases
    db = config.supported_databases["pgtest"]
    assert db.db_server == "postgresql"
    assert db.db_ip == "dbhost"
    assert db.db_user == "alice"


def test_add_duplicate_name_raises(config):
    config.add_db_parameters(db_name="dup", db_server="sqlite")
    with pytest.raises(ValueError, match="unique"):
        config.add_db_parameters(db_name="dup", db_server="sqlite")


def test_set_updates_in_memory_cache(config):
    """set_db_parameters must update supported_databases (regression: dp_/db_ typo)."""
    config.add_db_parameters(
        db_name="edit_me", db_server="mysql", db_ip="old", db_user="olduser",
    )
    config.set_db_parameters(db_name="edit_me", db_ip="newhost", db_user="newuser")
    db = config.supported_databases["edit_me"]
    assert db.db_ip == "newhost"
    assert db.db_user == "newuser"


def test_set_default_switches_selection(config):
    config.add_db_parameters(db_name="other", db_server="sqlite")
    config.set_db_parameters(db_name="other", default="True")
    assert config.db_selected == "other"
    assert config.supported_databases["other"].db_selected is True


def test_delete_removes_database(config):
    config.add_db_parameters(db_name="temp", db_server="sqlite")
    assert "temp" in config.supported_databases
    config.del_db_parameters("temp")
    assert "temp" not in config.supported_databases


def test_delete_selected_reassigns_selection(config):
    config.add_db_parameters(db_name="willgo", db_server="sqlite", default="True")
    assert config.db_selected == "willgo"
    config.del_db_parameters("willgo")
    # Selection must fall back to some remaining database, not dangle.
    assert config.db_selected != "willgo"
    assert config.db_selected in set(config.supported_databases) | {None}


def test_changes_persist_after_save_and_reload(config, tmp_path):
    config.add_db_parameters(
        db_name="persisted", db_server="postgresql", db_ip="h", db_user="u", db_pass="p",
    )
    config.save()
    reloaded = Configuration.Config(file=config.file)
    assert "persisted" in reloaded.supported_databases
    assert reloaded.supported_databases["persisted"].db_server == "postgresql"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
