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
from pathlib import Path

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


def test_explicit_empty_database_name_overrides_xml_default(tmp_path):
    cfg_path = tmp_path / "HUD_config.xml"
    config_text = Path(CONFIG_TEMPLATE).read_text(encoding="utf-8")
    default_database = (
        '<database db_server="sqlite" db_name="fpdb.db3" db_ip="localhost" '
        'db_user="fpdb" db_pass="fpdb" db_path="" default="True"/>'
    )
    empty_database = (
        '<database db_server="sqlite" db_name="" db_ip="localhost" '
        'db_user="fpdb" db_pass="fpdb" db_path="" default="False"/>'
    )
    config_text = config_text.replace(
        default_database,
        f"{default_database}\n        {empty_database}",
        1,
    )
    cfg_path.write_text(config_text, encoding="utf-8")

    selected = Configuration.Config(file=str(cfg_path), dbname="")

    assert "" in selected.supported_databases
    assert selected.db_selected == ""


# ---------------------------------------------------------------------------
# Updating a database node the cache never picked up
# ---------------------------------------------------------------------------
#
# Config loads the databases inside <supported_databases>, and only falls back
# to the ones at the top level when that section yields nothing. A file with
# both therefore has a <database> node that get_db_node finds but that never
# reached supported_databases, and that is the one case where
# add_db_parameters updates an existing node instead of creating one.

ORPHANED_CONFIG = """<?xml version="1.0"?>
<FreePokerToolsConfig>
  <general version="{version}"/>
  <supported_databases>
    <database db_name="fpdb" db_server="sqlite" db_ip="" db_user="" db_pass="" db_desc="main"/>
  </supported_databases>
  <database db_name="orphan" db_server="sqlite" db_desc="never loaded"{extra}/>
</FreePokerToolsConfig>
"""


@pytest.fixture
def config_with_orphan(tmp_path, monkeypatch):
    def build(extra=""):
        monkeypatch.setattr(Configuration, "CONFIG_PATH", str(tmp_path / "cfgdir"))
        path = tmp_path / "HUD_config.xml"
        path.write_text(
            ORPHANED_CONFIG.format(version=Configuration.CONFIG_VERSION, extra=extra),
            encoding="utf-8",
        )
        config = Configuration.Config(file=str(path))
        assert "orphan" not in config.supported_databases
        assert config.get_db_node("orphan") is not None
        return config

    return build


def test_the_description_is_stored_when_the_database_is_created(config):
    config.add_db_parameters(db_name="described", db_server="sqlite", db_desc="my laptop")

    assert config.get_db_node("described").getAttribute("db_desc") == "my laptop"
    assert config.supported_databases["described"].db_desc == "my laptop"


def test_an_unloaded_node_is_updated_rather_than_duplicated(config_with_orphan):
    config = config_with_orphan()

    config.add_db_parameters(
        db_name="orphan", db_server="postgresql", db_desc="now filled in",
        db_ip="dbhost", db_port="5432", db_user="alice", db_pass="secret",
    )

    nodes = [
        node for node in config.doc.getElementsByTagName("database")
        if node.getAttribute("db_name") == "orphan"
    ]
    assert len(nodes) == 1
    assert nodes[0].getAttribute("db_server") == "postgresql"
    assert nodes[0].getAttribute("db_ip") == "dbhost"
    assert nodes[0].getAttribute("db_port") == "5432"
    assert nodes[0].getAttribute("db_user") == "alice"
    assert nodes[0].getAttribute("db_pass") == "secret"
    assert nodes[0].getAttribute("db_desc") == "now filled in"


def test_updating_an_unloaded_node_puts_it_in_the_cache(config_with_orphan):
    config = config_with_orphan()

    config.add_db_parameters(db_name="orphan", db_server="mysql")

    assert config.supported_databases["orphan"].db_server == "mysql"


def test_an_unloaded_node_can_be_made_the_default(config_with_orphan):
    config = config_with_orphan()

    config.add_db_parameters(db_name="orphan", db_server="sqlite", default="True")

    assert config.get_db_node("orphan").getAttribute("default") == "True"
    assert config.db_selected == "orphan"


def test_the_default_flag_is_taken_off_an_unloaded_node(config_with_orphan):
    # The file says this one is the default; adding it without asking for that
    # has to clear the attribute, or the file would keep contradicting the
    # selection fpdb is actually using.
    config = config_with_orphan(extra=' default="True"')
    assert config.db_selected != "orphan"

    config.add_db_parameters(db_name="orphan", db_server="sqlite", default="False")

    assert not config.get_db_node("orphan").hasAttribute("default")


def test_the_selected_database_keeps_its_default_flag(config_with_orphan):
    # db_selected can name the node even when it was never cached, and the
    # flag has to follow the selection rather than the argument.
    config = config_with_orphan()
    config.db_selected = "orphan"

    config.add_db_parameters(db_name="orphan", db_server="sqlite", default="False")

    assert config.get_db_node("orphan").getAttribute("default") == "True"


@pytest.mark.parametrize("spelling", ["True", "TRUE", "true"])
def test_the_default_argument_is_read_whatever_its_case(config, spelling):
    config.add_db_parameters(db_name=f"cased{spelling}", db_server="sqlite", default=spelling)

    assert config.db_selected == f"cased{spelling}"


def test_adding_a_default_takes_it_off_every_other_database(config):
    config.add_db_parameters(db_name="first", db_server="sqlite", default="True")

    config.add_db_parameters(db_name="second", db_server="sqlite", default="True")

    assert not config.get_db_node("first").hasAttribute("default")
    assert config.get_db_node("second").getAttribute("default") == "True"


def test_updating_an_unloaded_node_leaves_the_other_defaults_alone(config_with_orphan):
    """The three writers never agreed about clearing the flag elsewhere.

    Creating a database takes the default off every other one, and so does
    set_db_parameters, but updating a node the cache never loaded does not.
    A file can therefore end up naming two defaults. Pinned as it stands so
    that unifying it is a decision rather than an accident.
    """
    config = config_with_orphan()
    # Config flags the database it selects while reading the file.
    assert config.get_db_node("fpdb").getAttribute("default") == "True"

    config.add_db_parameters(db_name="orphan", db_server="sqlite", default="True")

    assert config.get_db_node("orphan").getAttribute("default") == "True"
    assert config.get_db_node("fpdb").getAttribute("default") == "True"


def test_creating_a_database_takes_the_default_off_the_others(config_with_orphan):
    config = config_with_orphan()
    assert config.get_db_node("fpdb").getAttribute("default") == "True"

    config.add_db_parameters(db_name="brand-new", db_server="sqlite", default="True")

    assert not config.get_db_node("fpdb").hasAttribute("default")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
