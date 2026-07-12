"""GuiDatabase — configure the fpdb database backend from the GUI.

Lets the user list, add, edit, delete and select the configured databases and
test a connection before saving, for all supported backends (SQLite, PostgreSQL,
MySQL/MariaDB). The heavy lifting lives elsewhere: connection testing in
``db_backends`` and persistence in ``Configuration`` (``add_db_parameters`` /
``set_db_parameters`` / ``del_db_parameters`` + ``save``).
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy import Database, db_backends
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("gui_database")

# Server fields that only apply to client/server backends (not SQLite).
_SERVER_BACKENDS = ("postgresql", "mysql")


class DatabaseEditDialog(QDialog):
    """Add/edit form for a single database entry, with a connection tester."""

    def __init__(self, config: Any, existing: Any = None, parent: Any = None) -> None:
        super().__init__(parent)
        self.config = config
        self.existing = existing  # a Configuration.Database or None (add mode)
        self.setWindowTitle("Edit database" if existing else "Add database")

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.nameEdit = QLineEdit(getattr(existing, "db_name", ""))
        if existing is not None:
            self.nameEdit.setEnabled(False)  # the name is the identity key
        form.addRow("Name:", self.nameEdit)

        self.backendCombo = QComboBox()
        self._populate_backends(getattr(existing, "db_server", "sqlite"))
        self.backendCombo.currentIndexChanged.connect(self._on_backend_changed)
        form.addRow("Backend:", self.backendCombo)

        self.hostEdit = QLineEdit(getattr(existing, "db_ip", "") or "localhost")
        self.portEdit = QLineEdit(getattr(existing, "db_port", "") or "")
        self.userEdit = QLineEdit(getattr(existing, "db_user", "") or "")
        self.passwordEdit = QLineEdit(getattr(existing, "db_pass", "") or "")
        self.passwordEdit.setEchoMode(QLineEdit.EchoMode.Password)
        self._host_row = ("Host:", self.hostEdit)
        form.addRow(*self._host_row)
        form.addRow("Port:", self.portEdit)
        form.addRow("User:", self.userEdit)
        form.addRow("Password:", self.passwordEdit)
        self._form = form
        layout.addLayout(form)

        # Test connection row.
        test_row = QHBoxLayout()
        self.testButton = QPushButton("Test connection")
        self.testButton.clicked.connect(self._on_test)
        test_row.addWidget(self.testButton)
        self.testResult = QLabel("")
        test_row.addWidget(self.testResult)
        layout.addLayout(test_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._on_backend_changed()

    def _populate_backends(self, selected: str) -> None:
        """Fill the backend combo; disable backends whose driver is missing."""
        available = db_backends.available_backends()
        for server, (label, _driver, _needs) in db_backends.BACKENDS.items():
            display = label if available[server] else f"{label} (driver not installed)"
            self.backendCombo.addItem(display, server)
            index = self.backendCombo.count() - 1
            if not available[server]:
                # Disable the item so an unusable backend cannot be selected.
                self.backendCombo.model().item(index).setEnabled(False)
        idx = self.backendCombo.findData(selected or "sqlite")
        if idx >= 0:
            self.backendCombo.setCurrentIndex(idx)

    def current_backend(self) -> str:
        return self.backendCombo.currentData()

    def _on_backend_changed(self, *_args) -> None:
        """Show host/port/user/password only for client/server backends."""
        is_server = self.current_backend() in _SERVER_BACKENDS
        for widget in (self.hostEdit, self.portEdit, self.userEdit, self.passwordEdit):
            widget.setVisible(is_server)
            label = self._form.labelForField(widget)
            if label is not None:
                label.setVisible(is_server)
        self.testResult.setText("")

    def values(self) -> dict[str, str]:
        """Return the entered values as a dict of Configuration setter kwargs."""
        server = self.current_backend()
        result = {"db_name": self.nameEdit.text().strip(), "db_server": server}
        if server in _SERVER_BACKENDS:
            result["db_ip"] = self.hostEdit.text().strip()
            result["db_port"] = self.portEdit.text().strip()
            result["db_user"] = self.userEdit.text().strip()
            result["db_pass"] = self.passwordEdit.text()
        return result

    def _on_test(self) -> None:
        result = self.test_connection()
        color = "green" if result.ok else "red"
        mark = "✓" if result.ok else "✗"
        self.testResult.setText(f"{mark} {result.message}")
        self.testResult.setStyleSheet(f"color: {color};")

    def test_connection(self) -> db_backends.ConnectionResult:
        """Test the currently entered parameters (used by the Test button and tests)."""
        vals = self.values()
        server = vals["db_server"]
        if not vals["db_name"]:
            return db_backends.ConnectionResult(ok=False, message="A database name is required.")
        if server == "sqlite":
            return db_backends.test_connection(
                "sqlite", database=vals["db_name"], sqlite_dir=getattr(self.config, "dir_database", None),
            )
        return db_backends.test_connection(
            server,
            database=vals["db_name"],
            host=vals.get("db_ip"),
            port=vals.get("db_port"),
            user=vals.get("db_user"),
            password=vals.get("db_pass"),
        )


class GuiDatabase(QWidget):
    """Panel listing configured databases with add/edit/delete/select actions."""

    _COLUMNS = ("Name", "Backend", "Host / Path", "User", "Default")

    def __init__(self, config: Any, parent: Any = None) -> None:
        super().__init__(parent)
        self.config = config

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Configured databases:"))

        self.table = QTableWidget(0, len(self._COLUMNS))
        self.table.setHorizontalHeaderLabels(self._COLUMNS)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        buttons = QHBoxLayout()
        self.addButton = QPushButton("Add...")
        self.editButton = QPushButton("Edit...")
        self.deleteButton = QPushButton("Delete")
        self.defaultButton = QPushButton("Set as default")
        self.createButton = QPushButton("Create tables")
        self.addButton.clicked.connect(self._on_add)
        self.editButton.clicked.connect(self._on_edit)
        self.deleteButton.clicked.connect(self._on_delete)
        self.defaultButton.clicked.connect(self._on_set_default)
        self.createButton.clicked.connect(self._on_create_schema)
        for b in (self.addButton, self.editButton, self.deleteButton, self.defaultButton, self.createButton):
            buttons.addWidget(b)
        layout.addLayout(buttons)

        self.refresh()

    # --- table -------------------------------------------------------------

    def refresh(self) -> None:
        """Rebuild the table from the current config.supported_databases."""
        databases = getattr(self.config, "supported_databases", {})
        selected = getattr(self.config, "db_selected", None)
        self.table.setRowCount(0)
        for db in databases.values():
            row = self.table.rowCount()
            self.table.insertRow(row)
            host_or_path = db.db_ip if db.db_server in _SERVER_BACKENDS else (db.db_path or "(default dir)")
            cells = [
                db.db_name,
                db_backends.BACKENDS.get(db.db_server, (db.db_server,))[0],
                host_or_path or "",
                db.db_user or "",
                "✓" if db.db_name == selected else "",
            ]
            for col, text in enumerate(cells):
                self.table.setItem(row, col, QTableWidgetItem(str(text)))

    def selected_db_name(self) -> str | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.text() if item is not None else None

    # --- actions (config mutation is factored out so it can be unit-tested) ---

    def apply_add(self, values: dict[str, str]) -> None:
        self.config.add_db_parameters(**values)
        self.config.save()
        self.refresh()

    def apply_edit(self, values: dict[str, str]) -> None:
        self.config.set_db_parameters(**values)
        self.config.save()
        self.refresh()

    def apply_delete(self, db_name: str) -> None:
        # fpdb refuses to start with an empty <supported_databases>, so never
        # remove the last configured database.
        if len(getattr(self.config, "supported_databases", {})) <= 1:
            msg = "Cannot delete the last database — fpdb needs at least one."
            raise ValueError(msg)
        self.config.del_db_parameters(db_name)
        self.config.save()
        self.refresh()

    def apply_set_default(self, db_name: str) -> None:
        self.config.set_db_parameters(db_name=db_name, default="True")
        self.config.save()
        self.refresh()

    # --- schema creation ---------------------------------------------------

    @contextmanager
    def _selected(self, db_name: str):
        """Temporarily point the config at ``db_name`` so Database targets it."""
        previous = self.config.db_selected
        self.config.db_selected = db_name
        try:
            yield
        finally:
            self.config.db_selected = previous

    @staticmethod
    def _core_table_present(db: Any) -> bool:
        """True if the target database already has fpdb tables (checks Players)."""
        try:
            cursor = db.get_cursor()
            cursor.execute("SELECT 1 FROM Players LIMIT 1")
            cursor.fetchone()
        except Exception:  # noqa: BLE001 - any error means the table is not usable/absent
            return False
        return True

    def create_schema(self, db_name: str) -> db_backends.ConnectionResult:
        """Ensure the fpdb schema exists on the target database, non-destructively.

        A database that already holds fpdb tables is left untouched (its data is
        never dropped). An empty one is initialised via the same
        create_tables()/createAllIndexes() path as first run. Note that SQLite
        self-initialises on connect, so this mainly benefits PostgreSQL/MySQL.
        """
        with self._selected(db_name):
            try:
                db = Database.Database(self.config)
            except Exception as exc:  # noqa: BLE001 - surface connection errors to the user
                log.exception("create_schema: could not connect to %r", db_name)
                return db_backends.ConnectionResult(ok=False, message=f"Could not connect: {exc}")
            try:
                if self._core_table_present(db):
                    # Already initialised (existing data, or SQLite auto-created
                    # it on connect) — do not touch it.
                    return db_backends.ConnectionResult(ok=True, message=f"'{db_name}' is already initialised.")
                db.create_tables()  # creates tables + fills default data + commits
                db.createAllIndexes()
                db.commit()
                return db_backends.ConnectionResult(ok=True, message=f"Created fpdb schema in '{db_name}'.")
            except Exception as exc:  # noqa: BLE001 - report any schema-creation failure
                log.exception("create_schema: failed for %r", db_name)
                return db_backends.ConnectionResult(ok=False, message=f"Failed to create schema: {exc}")
            finally:
                db.close_connection()

    # --- button handlers ---------------------------------------------------

    def _on_add(self) -> None:
        dialog = DatabaseEditDialog(self.config, existing=None, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            values = dialog.values()
            if not values["db_name"]:
                QMessageBox.warning(self, "Add database", "A database name is required.")
                return
            try:
                self.apply_add(values)
            except ValueError as exc:  # duplicate name
                QMessageBox.warning(self, "Add database", str(exc))

    def _on_edit(self) -> None:
        name = self.selected_db_name()
        if name is None:
            return
        dialog = DatabaseEditDialog(self.config, existing=self.config.supported_databases.get(name), parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.apply_edit(dialog.values())

    def _on_delete(self) -> None:
        name = self.selected_db_name()
        if name is None:
            return
        if len(getattr(self.config, "supported_databases", {})) <= 1:
            QMessageBox.warning(
                self,
                "Delete database",
                "This is the only configured database and cannot be deleted — "
                "fpdb needs at least one. Add another database first.",
            )
            return
        confirm = QMessageBox.question(
            self, "Delete database", f"Remove '{name}' from the configuration?\n(The database itself is not deleted.)",
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.apply_delete(name)

    def _on_set_default(self) -> None:
        name = self.selected_db_name()
        if name is None:
            return
        self.apply_set_default(name)
        QMessageBox.information(
            self,
            "Default database changed",
            f"'{name}' is now the default database.\n\n"
            "Restart fpdb for the change to take effect — the running session "
            "stays connected to the previous database.",
        )

    def _on_create_schema(self) -> None:
        name = self.selected_db_name()
        if name is None:
            return
        confirm = QMessageBox.question(
            self,
            "Create tables",
            f"Create the fpdb tables in '{name}'?\n\n"
            "This only initialises an empty database; a database that already "
            "contains fpdb tables is left untouched.",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        result = self.create_schema(name)
        if result.ok:
            QMessageBox.information(self, "Create tables", result.message)
        else:
            QMessageBox.warning(self, "Create tables", result.message)
