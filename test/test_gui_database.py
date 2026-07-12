#!/usr/bin/env python3
"""Tests for the GuiDatabase panel and DatabaseEditDialog (offscreen, mocked config)."""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

pytest.importorskip("PySide6")

CONFIG_TEMPLATE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "HUD_config.xml"))


def _fake_db(name, server="sqlite", ip="", port="", user="", selected=False):
    return SimpleNamespace(
        db_name=name, db_server=server, db_ip=ip, db_port=port,
        db_user=user, db_pass="", db_path="", db_desc="", db_selected=selected,
    )


def _fake_config(dbs=None):
    config = MagicMock()
    config.supported_databases = {db.db_name: db for db in (dbs or [])}
    config.db_selected = next((d.db_name for d in (dbs or []) if d.db_selected), None)
    config.dir_database = "/tmp/fpdb-db"
    return config


@pytest.fixture(scope="module")
def _qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


# --- GuiDatabase panel -----------------------------------------------------


def test_refresh_lists_configured_databases(_qapp):
    from fpdb_3_legacy.GuiDatabase import GuiDatabase

    config = _fake_config([
        _fake_db("fpdb", "sqlite", selected=True),
        _fake_db("pg", "postgresql", ip="dbhost", user="alice"),
    ])
    panel = GuiDatabase(config)
    assert panel.table.rowCount() == 2
    # Default marker on the selected row.
    names = {panel.table.item(r, 0).text(): panel.table.item(r, 4).text() for r in range(2)}
    assert names["fpdb"] == "✓"
    assert names["pg"] == ""


def test_apply_add_calls_config_and_refreshes(_qapp):
    from fpdb_3_legacy.GuiDatabase import GuiDatabase

    config = _fake_config([_fake_db("fpdb", "sqlite")])
    panel = GuiDatabase(config)
    panel.apply_add({"db_name": "new", "db_server": "sqlite"})
    config.add_db_parameters.assert_called_once_with(db_name="new", db_server="sqlite")
    config.save.assert_called_once()


def test_apply_delete_and_set_default(_qapp):
    from fpdb_3_legacy.GuiDatabase import GuiDatabase

    config = _fake_config([_fake_db("fpdb", "sqlite"), _fake_db("other", "postgresql")])
    panel = GuiDatabase(config)
    panel.apply_delete("fpdb")
    config.del_db_parameters.assert_called_once_with("fpdb")
    panel.apply_set_default("fpdb")
    config.set_db_parameters.assert_called_once_with(db_name="fpdb", default="True")


def test_apply_delete_refuses_last_database(_qapp):
    from fpdb_3_legacy.GuiDatabase import GuiDatabase

    config = _fake_config([_fake_db("only", "sqlite")])
    panel = GuiDatabase(config)
    with pytest.raises(ValueError, match="last database"):
        panel.apply_delete("only")
    config.del_db_parameters.assert_not_called()
    config.save.assert_not_called()


def test_apply_delete_allowed_when_more_than_one(_qapp):
    from fpdb_3_legacy.GuiDatabase import GuiDatabase

    config = _fake_config([_fake_db("a", "sqlite"), _fake_db("b", "postgresql")])
    panel = GuiDatabase(config)
    panel.apply_delete("a")
    config.del_db_parameters.assert_called_once_with("a")


def test_selected_db_name(_qapp):
    from fpdb_3_legacy.GuiDatabase import GuiDatabase

    config = _fake_config([_fake_db("a"), _fake_db("b")])
    panel = GuiDatabase(config)
    panel.table.setCurrentCell(1, 0)
    assert panel.selected_db_name() == "b"


# --- DatabaseEditDialog ----------------------------------------------------


def test_dialog_lists_all_backends(_qapp):
    from fpdb_3_legacy.GuiDatabase import DatabaseEditDialog

    dialog = DatabaseEditDialog(_fake_config())
    servers = {dialog.backendCombo.itemData(i) for i in range(dialog.backendCombo.count())}
    assert servers == {"sqlite", "postgresql", "mysql"}


def test_dialog_hides_server_fields_for_sqlite(_qapp):
    from PySide6.QtWidgets import QWidget

    from fpdb_3_legacy.GuiDatabase import DatabaseEditDialog

    dialog = DatabaseEditDialog(_fake_config())
    dialog.show()  # visibility only meaningful once shown
    idx = dialog.backendCombo.findData("sqlite")
    dialog.backendCombo.setCurrentIndex(idx)
    assert not dialog.hostEdit.isVisible()
    idx = dialog.backendCombo.findData("postgresql")
    dialog.backendCombo.setCurrentIndex(idx)
    assert dialog.hostEdit.isVisible()
    dialog.close()
    assert isinstance(dialog, QWidget)


def test_dialog_values_for_server_backend(_qapp):
    from fpdb_3_legacy.GuiDatabase import DatabaseEditDialog

    dialog = DatabaseEditDialog(_fake_config())
    dialog.nameEdit.setText("mydb")
    dialog.backendCombo.setCurrentIndex(dialog.backendCombo.findData("postgresql"))
    dialog.hostEdit.setText("h")
    dialog.portEdit.setText("5432")
    dialog.userEdit.setText("u")
    dialog.passwordEdit.setText("p")
    vals = dialog.values()
    assert vals == {
        "db_name": "mydb", "db_server": "postgresql",
        "db_ip": "h", "db_port": "5432", "db_user": "u", "db_pass": "p",
    }


def test_dialog_test_connection_routes_to_helper(_qapp):
    from fpdb_3_legacy import GuiDatabase as gui_db_module
    from fpdb_3_legacy.GuiDatabase import DatabaseEditDialog

    dialog = DatabaseEditDialog(_fake_config())
    dialog.nameEdit.setText("fpdb.db3")
    dialog.backendCombo.setCurrentIndex(dialog.backendCombo.findData("sqlite"))

    with patch.object(gui_db_module.db_backends, "test_connection") as mock_test:
        mock_test.return_value = gui_db_module.db_backends.ConnectionResult(ok=True, message="ok")
        dialog._on_test()

    mock_test.assert_called_once()
    assert mock_test.call_args.kwargs["database"] == "fpdb.db3"
    assert "✓" in dialog.testResult.text()


def test_dialog_test_requires_name(_qapp):
    from fpdb_3_legacy.GuiDatabase import DatabaseEditDialog

    dialog = DatabaseEditDialog(_fake_config())
    dialog.nameEdit.setText("")
    result = dialog.test_connection()
    assert result.ok is False
    assert "name is required" in result.message


# --- Phase 3: field validation ---------------------------------------------


def _dialog_for(server, **fields):
    from fpdb_3_legacy.GuiDatabase import DatabaseEditDialog

    config = fields.pop("config", None) or _fake_config()
    dialog = DatabaseEditDialog(config)
    dialog.nameEdit.setText(fields.get("name", "db"))
    dialog.backendCombo.setCurrentIndex(dialog.backendCombo.findData(server))
    dialog.hostEdit.setText(fields.get("host", ""))
    dialog.portEdit.setText(fields.get("port", ""))
    return dialog


def test_validate_requires_name(_qapp):
    dialog = _dialog_for("sqlite", name="")
    ok, message = dialog.validate()
    assert ok is False
    assert "name is required" in message


def test_validate_rejects_duplicate_name_on_add(_qapp):
    config = _fake_config([_fake_db("taken")])
    dialog = _dialog_for("sqlite", name="taken", config=config)
    ok, message = dialog.validate()
    assert ok is False
    assert "already exists" in message


def test_validate_allows_existing_name_on_edit(_qapp):
    from fpdb_3_legacy.GuiDatabase import DatabaseEditDialog

    config = _fake_config([_fake_db("edit_me")])
    dialog = DatabaseEditDialog(config, existing=config.supported_databases["edit_me"])
    ok, _ = dialog.validate()
    assert ok is True  # editing keeps its own name; not a duplicate


def test_validate_requires_host_for_server_backends(_qapp):
    dialog = _dialog_for("postgresql", name="pg", host="")
    ok, message = dialog.validate()
    assert ok is False
    assert "host is required" in message.lower()


def test_validate_rejects_non_numeric_port(_qapp):
    dialog = _dialog_for("postgresql", name="pg", host="h", port="abc")
    ok, message = dialog.validate()
    assert ok is False
    assert "Port must be" in message


def test_validate_rejects_out_of_range_port(_qapp):
    dialog = _dialog_for("postgresql", name="pg", host="h", port="70000")
    ok, message = dialog.validate()
    assert ok is False
    assert "65535" in message


def test_validate_accepts_boundary_ports(_qapp):
    for port in ("1", "65535"):
        dialog = _dialog_for("postgresql", name="pg", host="h", port=port)
        ok, _ = dialog.validate()
        assert ok is True, f"port {port} should be valid"


def test_validate_accepts_valid_server_config(_qapp):
    dialog = _dialog_for("postgresql", name="pg", host="h", port="5432")
    ok, _ = dialog.validate()
    assert ok is True


def test_validate_sqlite_needs_no_host(_qapp):
    dialog = _dialog_for("sqlite", name="fpdb.db3")
    ok, _ = dialog.validate()
    assert ok is True


def test_accept_blocks_on_invalid_input(_qapp):
    from PySide6.QtWidgets import QDialog

    from fpdb_3_legacy import GuiDatabase as m

    dialog = _dialog_for("postgresql", name="pg", host="")  # missing host
    with patch.object(m.QMessageBox, "warning") as warn:
        dialog.accept()
    warn.assert_called_once()
    assert dialog.result() != QDialog.DialogCode.Accepted  # stays open


def test_accept_passes_on_valid_input(_qapp):
    from PySide6.QtWidgets import QDialog

    dialog = _dialog_for("sqlite", name="fpdb.db3")
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted


# --- Phase 2: switch-active prompt + create schema -------------------------


def test_set_default_prompts_restart(_qapp):
    from fpdb_3_legacy import GuiDatabase as m

    config = _fake_config([_fake_db("a"), _fake_db("b")])
    panel = m.GuiDatabase(config)
    panel.table.setCurrentCell(0, 0)
    with patch.object(m.QMessageBox, "information") as info:
        panel._on_set_default()
    config.set_db_parameters.assert_called_once_with(db_name="a", default="True")
    info.assert_called_once()  # user told to restart


def test_create_schema_leaves_existing_tables_untouched(_qapp):
    from fpdb_3_legacy import GuiDatabase as m

    config = _fake_config([_fake_db("db", selected=True)])
    panel = m.GuiDatabase(config)
    with patch.object(m.db_backends, "inspect_database", return_value=(m.db_backends.STATE_INITIALISED, "")), \
            patch.object(m.Database, "Database") as build_db:
        result = panel.create_schema("db")
    assert result.ok is True
    assert "already initialised" in result.message
    build_db.assert_not_called()  # already an fpdb DB: never even connect with Database


def test_create_schema_refuses_foreign_tables(_qapp):
    """The Codex-flagged data-loss case: a DB with non-fpdb tables is left alone."""
    from fpdb_3_legacy import GuiDatabase as m

    config = _fake_config([_fake_db("db", selected=True)])
    panel = m.GuiDatabase(config)
    with patch.object(m.db_backends, "inspect_database", return_value=(m.db_backends.STATE_FOREIGN, "")), \
            patch.object(m.Database, "Database") as build_db:
        result = panel.create_schema("db")
    assert result.ok is False
    assert "non-fpdb tables" in result.message
    build_db.assert_not_called()  # never hand a foreign DB to Database (which could drop it)


def test_create_schema_creates_when_empty(_qapp):
    from fpdb_3_legacy import GuiDatabase as m

    config = _fake_config([_fake_db("db", selected=True)])
    panel = m.GuiDatabase(config)
    fake_db = MagicMock()
    fake_db.get_cursor.return_value.execute.side_effect = Exception("no such table: Players")
    with patch.object(m.db_backends, "inspect_database", return_value=(m.db_backends.STATE_EMPTY, "")), \
            patch.object(m.Database, "Database", return_value=fake_db):
        result = panel.create_schema("db")
    assert result.ok is True
    fake_db.create_tables.assert_called_once()
    fake_db.createAllIndexes.assert_called_once()
    fake_db.close_connection.assert_called_once()


def test_create_schema_reports_unreachable(_qapp):
    from fpdb_3_legacy import GuiDatabase as m

    config = _fake_config([_fake_db("db", selected=True)])
    panel = m.GuiDatabase(config)
    with patch.object(m.db_backends, "inspect_database", return_value=(m.db_backends.STATE_UNREACHABLE, "refused")), \
            patch.object(m.Database, "Database") as build_db:
        result = panel.create_schema("db")
    assert result.ok is False
    assert "Could not connect" in result.message
    build_db.assert_not_called()


def test_create_schema_restores_db_selected(_qapp):
    from fpdb_3_legacy import GuiDatabase as m

    config = _fake_config([_fake_db("main", selected=True), _fake_db("other")])
    config.db_selected = "main"
    panel = m.GuiDatabase(config)
    with patch.object(m.db_backends, "inspect_database", return_value=(m.db_backends.STATE_EMPTY, "")), \
            patch.object(m.Database, "Database", return_value=MagicMock()):
        panel.create_schema("other")
    assert config.db_selected == "main"  # temporary switch was reverted


def test_create_schema_real_sqlite(_qapp, tmp_path):
    """End-to-end: create the schema in a fresh SQLite file, then refuse to redo it."""
    import shutil
    import sqlite3

    from fpdb_3_legacy import Configuration
    from fpdb_3_legacy.GuiDatabase import GuiDatabase

    cfg_path = tmp_path / "HUD_config.xml"
    shutil.copy(CONFIG_TEMPLATE, cfg_path)
    config = Configuration.Config(file=str(cfg_path))
    config.dir_database = str(tmp_path)
    config.add_db_parameters(db_name="fresh.db3", db_server="sqlite")

    panel = GuiDatabase(config)
    result = panel.create_schema("fresh.db3")
    assert result.ok, result.message

    conn = sqlite3.connect(str(tmp_path / "fresh.db3"))
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert {"Players", "Hands", "Sites"} <= tables

    # A second run must be non-destructive (schema already present) and succeed.
    again = panel.create_schema("fresh.db3")
    assert again.ok is True
    assert "already initialised" in again.message


def test_create_schema_refuses_foreign_sqlite_file(_qapp, tmp_path):
    """Codex regression: a non-fpdb SQLite file must be refused, not wiped."""
    import shutil
    import sqlite3

    from fpdb_3_legacy import Configuration
    from fpdb_3_legacy.GuiDatabase import GuiDatabase

    # A user's own SQLite database with unrelated tables and data.
    user_db = tmp_path / "user.db3"
    conn = sqlite3.connect(str(user_db))
    conn.execute("CREATE TABLE important (id INTEGER, note TEXT)")
    conn.execute("INSERT INTO important VALUES (1, 'do not delete me')")
    conn.commit()
    conn.close()

    cfg_path = tmp_path / "HUD_config.xml"
    shutil.copy(CONFIG_TEMPLATE, cfg_path)
    config = Configuration.Config(file=str(cfg_path))
    config.dir_database = str(tmp_path)
    config.add_db_parameters(db_name="user.db3", db_server="sqlite")

    panel = GuiDatabase(config)
    result = panel.create_schema("user.db3")

    assert result.ok is False
    assert "non-fpdb tables" in result.message
    # The user's table and data must be completely intact.
    conn = sqlite3.connect(str(user_db))
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    rows = conn.execute("SELECT note FROM important").fetchall()
    conn.close()
    assert "important" in tables
    assert rows == [("do not delete me",)]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
