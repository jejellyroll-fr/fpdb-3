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

    config = _fake_config([_fake_db("fpdb", "sqlite")])
    panel = GuiDatabase(config)
    panel.apply_delete("fpdb")
    config.del_db_parameters.assert_called_once_with("fpdb")
    panel.apply_set_default("fpdb")
    config.set_db_parameters.assert_called_once_with(db_name="fpdb", default="True")


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
