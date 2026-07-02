"""Workbench for running and inspecting legacy automatic notes."""

from __future__ import annotations

import re
from typing import Any

from PySide6.QtCore import QDate, QObject, Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy import GuiReplayer
from fpdb_3_legacy.AutoNotes import configured_rule_summary
from fpdb_3_legacy.backfill_autonotes import (
    backfill_database_preview,
    backfill_preview,
    backfill_with_optional_import,
    format_rule_counts,
    format_stats_json,
)
from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("gui_autonotes_workbench")


class _AutoNotesWorker(QObject):
    """Run slow autonote work away from the Qt GUI thread."""

    status = Signal(str)
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(self, operation: str, kwargs: dict[str, Any]) -> None:
        super().__init__()
        self.operation = operation
        self.kwargs = kwargs

    def run(self) -> None:
        try:
            status_callback = self.status.emit
            if self.operation == "file_write":
                stats = backfill_with_optional_import(status_callback=status_callback, **self.kwargs)
            elif self.operation == "file_preview":
                stats = backfill_preview(status_callback=status_callback, **self.kwargs)
            elif self.operation == "database":
                stats = backfill_database_preview(status_callback=status_callback, **self.kwargs)
            else:
                raise ValueError(f"Unknown autonote operation: {self.operation}")
        except Exception as e:  # intentional broad catch: surface worker errors in the GUI.
            log.exception("Automatic-note worker failed")
            self.failed.emit(str(e))
            return
        self.finished.emit(stats)


class GuiAutoNotesWorkbench(QWidget):
    """Run existing-hand autonote backfills and inspect candidate notes."""

    TABLE_HEADERS = [
        "Player",
        "Cards",
        "Player ID",
        "Hand ID",
        "Site Hand",
        "Rule Set",
        "Rule",
        "Note",
        "Evidence",
    ]

    def __init__(self, config: Any, parent: Any = None) -> None:
        super().__init__(parent)
        self.config = config
        self.main_window = parent
        self.db: Database | None = None
        self.owns_db = False
        self.replayers: list[Any] = []
        self.run_buttons: list[QPushButton] = []
        self.last_stats: dict[str, Any] | None = None
        self.last_preview: list[dict[str, Any]] = []
        self.worker_thread: QThread | None = None
        self.worker: _AutoNotesWorker | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.run_tab = QWidget()
        self.player_tab = QWidget()
        self.pool_tab = QWidget()
        self.tabs.addTab(self.run_tab, "Run")
        self.tabs.addTab(self.player_tab, "Player Notes")
        self.tabs.addTab(self.pool_tab, "Pool")

        self._build_run_tab(self.run_tab)
        self._build_player_tab(self.player_tab)
        self._build_pool_tab(self.pool_tab)

    def _build_run_tab(self, tab: QWidget) -> None:
        layout = QVBoxLayout(tab)
        source_row = QHBoxLayout()
        source_row.addWidget(QLabel("Hand-history source"))
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("File or directory to re-scan")
        source_row.addWidget(self.path_edit, 1)

        self.browse_dir_button = QPushButton("Folder")
        self.browse_dir_button.clicked.connect(self.browse_folder)
        source_row.addWidget(self.browse_dir_button)

        self.browse_file_button = QPushButton("File")
        self.browse_file_button.clicked.connect(self.browse_file)
        source_row.addWidget(self.browse_file_button)
        layout.addLayout(source_row)

        control_row = QHBoxLayout()
        control_row.addWidget(QLabel("Rule set"))
        self.ruleset_combo = QComboBox()
        self.ruleset_combo.addItem("All configured rule sets", "")
        for rule_set in configured_rule_summary(self.config):
            self.ruleset_combo.addItem(rule_set["ruleSet"], rule_set["ruleSet"])
        control_row.addWidget(self.ruleset_combo, 1)

        self.dry_run_button = QPushButton("Dry Run")
        self.dry_run_button.clicked.connect(self.run_dry_run)
        control_row.addWidget(self.dry_run_button)

        self.write_button = QPushButton("Write Notes")
        self.write_button.clicked.connect(self.run_write)
        control_row.addWidget(self.write_button)
        layout.addLayout(control_row)

        db_row = QHBoxLayout()
        db_row.addWidget(QLabel("Database hands"))
        self.db_limit_spin = QSpinBox()
        self.db_limit_spin.setRange(1, 1_000_000)
        self.db_limit_spin.setValue(1000)
        self.db_limit_spin.setSingleStep(100)
        db_row.addWidget(self.db_limit_spin)

        self.db_dry_run_button = QPushButton("Dry Run DB")
        self.db_dry_run_button.clicked.connect(self.run_database_dry_run)
        db_row.addWidget(self.db_dry_run_button)

        self.db_write_button = QPushButton("Write DB Notes")
        self.db_write_button.clicked.connect(self.run_database_write)
        db_row.addWidget(self.db_write_button)
        db_row.addStretch(1)
        layout.addLayout(db_row)

        self.run_buttons = [
            self.browse_dir_button,
            self.browse_file_button,
            self.dry_run_button,
            self.write_button,
            self.db_dry_run_button,
            self.db_write_button,
        ]

        status_row = QHBoxLayout()
        self.status_label = QLabel("Idle")
        status_row.addWidget(self.status_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        status_row.addWidget(self.progress_bar, 1)
        layout.addLayout(status_row)

        self.summary = QPlainTextEdit()
        self.summary.setReadOnly(True)
        self.summary.setMaximumHeight(120)
        self.summary.setPlainText("Run a dry run from hand-history files or directly from imported database hands.")
        layout.addWidget(self.summary)

        self.table = QTableWidget(0, len(self.TABLE_HEADERS))
        self.table.setHorizontalHeaderLabels(self.TABLE_HEADERS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(8, QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.itemDoubleClicked.connect(lambda item: self.open_replayer_from_table(self.table, item.row(), 3))
        layout.addWidget(self.table, 1)

    def _build_player_tab(self, tab: QWidget) -> None:
        layout = QVBoxLayout(tab)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Player"))
        self.player_search_edit = QLineEdit()
        self.player_search_edit.setPlaceholderText("Name fragment")
        search_row.addWidget(self.player_search_edit, 1)

        search_button = QPushButton("Search")
        search_button.clicked.connect(self.search_players)
        search_row.addWidget(search_button)

        load_button = QPushButton("Load Notes")
        load_button.clicked.connect(self.load_selected_player_notes)
        search_row.addWidget(load_button)
        layout.addLayout(search_row)

        self.players_table = QTableWidget(0, 3)
        self.players_table.setHorizontalHeaderLabels(["Player", "Player ID", "Site ID"])
        self.players_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.players_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.players_table.setAlternatingRowColors(True)
        layout.addWidget(self.players_table)

        overview_row = QHBoxLayout()
        self.player_overview_name = QLabel("Player")
        self.player_overview_notes = QLabel("Notes: 0")
        self.player_overview_top_rule = QLabel("Top rule: -")
        self.player_overview_latest = QLabel("Latest: -")
        for label in (
            self.player_overview_name,
            self.player_overview_notes,
            self.player_overview_top_rule,
            self.player_overview_latest,
        ):
            label.setMinimumWidth(140)
            overview_row.addWidget(label)
        overview_row.addStretch(1)
        layout.addLayout(overview_row)

        self.player_notes_table = QTableWidget(0, 9)
        self.player_notes_table.setHorizontalHeaderLabels(
            ["Created", "Cards", "Rule", "Note", "Evidence", "Hand ID", "Site Hand", "Rule Set", "Version"],
        )
        self.player_notes_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.player_notes_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.player_notes_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.player_notes_table.setAlternatingRowColors(True)
        self.player_notes_table.itemDoubleClicked.connect(
            lambda item: self.open_replayer_from_table(self.player_notes_table, item.row(), 5),
        )
        layout.addWidget(self.player_notes_table, 1)

    def _build_pool_tab(self, tab: QWidget) -> None:
        outer_layout = QVBoxLayout(tab)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer_layout.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)
        layout = QVBoxLayout(content)

        refresh_row = QHBoxLayout()
        refresh_row.addWidget(QLabel("Player"))
        self.pool_player_filter = QLineEdit()
        self.pool_player_filter.setPlaceholderText("Name fragment")
        refresh_row.addWidget(self.pool_player_filter, 1)

        refresh_row.addWidget(QLabel("Site"))
        self.pool_site_filter = QComboBox()
        self.pool_site_filter.addItem("All sites", None)
        for site_name, site_id in sorted((getattr(self.config, "site_ids", {}) or {}).items()):
            self.pool_site_filter.addItem(str(site_name), site_id)
        refresh_row.addWidget(self.pool_site_filter)

        refresh_row.addWidget(QLabel("Limit"))
        self.pool_limit_filter = QComboBox()
        self.pool_limit_filter.addItem("All", "")
        for limit_type in ("nl", "pl", "fl", "cn", "cp"):
            self.pool_limit_filter.addItem(limit_type.upper(), limit_type)
        refresh_row.addWidget(self.pool_limit_filter)
        layout.addLayout(refresh_row)

        date_row = QHBoxLayout()
        date_row.addWidget(QLabel("From"))
        self.pool_from_date = QDateEdit()
        self.pool_from_date.setCalendarPopup(True)
        self.pool_from_date.setDisplayFormat("yyyy-MM-dd")
        self.pool_from_date.setDate(QDate(1970, 1, 1))
        self.pool_from_date.setSpecialValueText("Any")
        self.pool_from_date.setMinimumDate(QDate(1970, 1, 1))
        self.pool_from_date.setCalendarPopup(True)
        date_row.addWidget(self.pool_from_date)

        date_row.addWidget(QLabel("To"))
        self.pool_to_date = QDateEdit()
        self.pool_to_date.setCalendarPopup(True)
        self.pool_to_date.setDisplayFormat("yyyy-MM-dd")
        self.pool_to_date.setDate(QDate.currentDate())
        self.pool_to_date.setMinimumDate(QDate(1970, 1, 1))
        date_row.addWidget(self.pool_to_date)

        refresh_button = QPushButton("Refresh Pool Summary")
        refresh_button.clicked.connect(self.refresh_pool_summary)
        date_row.addWidget(refresh_button)
        date_row.addStretch(1)
        layout.addLayout(date_row)

        self.pool_players_table = QTableWidget(0, 4)
        self.pool_players_table.setHorizontalHeaderLabels(["Player", "Player ID", "Notes", "Last Note"])
        self.pool_players_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.pool_players_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.pool_players_table.setAlternatingRowColors(True)
        self.pool_players_table.setMinimumHeight(220)
        layout.addWidget(QLabel("Top players by generated notes"))
        layout.addWidget(self.pool_players_table)

        self.pool_rules_table = QTableWidget(0, 3)
        self.pool_rules_table.setHorizontalHeaderLabels(["Rule Set", "Rule", "Notes"])
        self.pool_rules_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.pool_rules_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.pool_rules_table.setAlternatingRowColors(True)
        self.pool_rules_table.setMinimumHeight(220)
        layout.addWidget(QLabel("Top rules"))
        layout.addWidget(self.pool_rules_table)

        self.recent_notes_table = QTableWidget(0, 9)
        self.recent_notes_table.setHorizontalHeaderLabels(
            ["Created", "Player", "Cards", "Hand ID", "Rule Set", "Rule", "Note", "Evidence", "Site Hand"],
        )
        self.recent_notes_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.recent_notes_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        self.recent_notes_table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        self.recent_notes_table.setAlternatingRowColors(True)
        self.recent_notes_table.setMinimumHeight(300)
        self.recent_notes_table.itemDoubleClicked.connect(
            lambda item: self.open_replayer_from_table(self.recent_notes_table, item.row(), 3),
        )
        layout.addWidget(QLabel("Recent generated notes"))
        layout.addWidget(self.recent_notes_table, 1)

    def _database(self) -> Database:
        if self.db is None:
            parent_db = getattr(self.main_window, "db", None)
            if parent_db is not None:
                self.db = parent_db
                self.owns_db = False
                return self.db
            self.db = Database(self.config, sql=getattr(self.main_window, "sql", None))
            self.owns_db = True
            if hasattr(self.db, "ensure_feature_tables"):
                self.db.ensure_feature_tables()
        return self.db

    def browse_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select hand-history folder")
        if path:
            self.path_edit.setText(path)

    def browse_file(self) -> None:
        path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Select hand-history file",
            "",
            "Hand histories (*.txt *.xml *.hh *.log);;All files (*)",
        )
        if path:
            self.path_edit.setText(path)

    def run_dry_run(self) -> None:
        self._run(commit=False)

    def run_write(self) -> None:
        if (
            QMessageBox.question(
                self,
                "Write automatic notes",
                "Import missing hand-history hands, then write generated automatic notes to the database?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self._run(commit=True)

    def run_database_dry_run(self) -> None:
        self._run_database(commit=False)

    def run_database_write(self) -> None:
        if (
            QMessageBox.question(
                self,
                "Write automatic notes",
                "Write generated automatic notes for imported database hands?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self._run_database(commit=True)

    def _run(self, commit: bool) -> None:
        path = self.path_edit.text().strip()
        if not path:
            QMessageBox.warning(self, "Automatic notes", "Choose a hand-history file or folder first.")
            return

        rule_set_id = self.ruleset_combo.currentData()
        rule_set_ids = {rule_set_id} if rule_set_id else None
        config_file = getattr(self.config, "file", "HUD_config.xml")
        if commit:
            self._start_worker(
                "file_write",
                {
                    "paths": [path],
                    "commit": True,
                    "config_file": config_file,
                    "rule_set_ids": rule_set_ids,
                    "import_missing": True,
                },
                commit=commit,
                rule_set_ids=rule_set_ids,
                message="Importing missing hands and writing automatic notes...",
            )
            return
        self._start_worker(
            "file_preview",
            {
                "paths": [path],
                "commit": False,
                "config_file": config_file,
                "rule_set_ids": rule_set_ids,
            },
            commit=commit,
            rule_set_ids=rule_set_ids,
            message="Scanning hand-history files...",
        )

    def _run_database(self, commit: bool) -> None:
        rule_set_id = self.ruleset_combo.currentData()
        rule_set_ids = {rule_set_id} if rule_set_id else None
        config_file = getattr(self.config, "file", "HUD_config.xml")
        filters = self._pool_filters()
        self._start_worker(
            "database",
            {
                "commit": commit,
                "config_file": config_file,
                "rule_set_ids": rule_set_ids,
                "limit": self.db_limit_spin.value(),
                "date_from": filters["date_from"],
                "date_to": filters["date_to"],
                "site_id": filters["site_id"],
                "limit_type": filters["limit_type"],
            },
            commit=commit,
            rule_set_ids=rule_set_ids,
            message="Writing automatic notes from database..." if commit else "Scanning database hands...",
        )

    def _start_worker(
        self,
        operation: str,
        kwargs: dict[str, Any],
        commit: bool,
        rule_set_ids: set[str] | None,
        message: str,
    ) -> None:
        if self.worker_thread is not None and self.worker_thread.isRunning():
            QMessageBox.information(self, "Automatic notes", "An automatic-note run is already in progress.")
            return

        self._set_busy(True, message)
        self.table.setRowCount(0)
        self.worker_commit = commit
        self.worker_rule_set_ids = rule_set_ids

        thread = QThread(self)
        worker = _AutoNotesWorker(operation, kwargs)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.status.connect(self._append_status)
        worker.finished.connect(self._on_worker_finished)
        worker.failed.connect(self._worker_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_worker)
        self.worker_thread = thread
        self.worker = worker
        thread.start()

    @Slot(str)
    def _append_status(self, message: str) -> None:
        self.status_label.setText(message)
        self.summary.appendPlainText(message)

    @Slot(dict)
    def _on_worker_finished(self, stats: dict[str, Any]) -> None:
        self._worker_finished(stats, self.worker_commit, self.worker_rule_set_ids)

    def _worker_finished(self, stats: dict[str, Any], commit: bool, rule_set_ids: set[str] | None) -> None:
        self.last_stats = stats
        self.last_preview = list(stats.get("preview", []))
        self._populate_table(self.last_preview)
        self.summary.setPlainText(self._format_summary(stats, commit=commit, rule_set_ids=rule_set_ids))
        if commit:
            self.refresh_pool_summary()
        self._set_busy(False, f"Done: {stats.get('notes', 0)} notes.", reset_summary=False)

    @Slot(str)
    def _worker_failed(self, message: str) -> None:
        QMessageBox.critical(self, "Automatic notes", f"Scan failed: {message}")
        self.summary.appendPlainText(f"Scan failed: {message}")
        self._set_busy(False, "Scan failed.", reset_summary=False)

    @Slot()
    def _clear_worker(self) -> None:
        self.worker_thread = None
        self.worker = None

    def _set_busy(self, busy: bool, message: str, reset_summary: bool = True) -> None:
        self.status_label.setText(message)
        self.progress_bar.setVisible(busy)
        self.progress_bar.setRange(0, 0 if busy else 1)
        self.progress_bar.setValue(0)
        for button in self.run_buttons:
            button.setEnabled(not busy)
        self.path_edit.setEnabled(not busy)
        self.ruleset_combo.setEnabled(not busy)
        self.db_limit_spin.setEnabled(not busy)
        if reset_summary:
            self.summary.setPlainText(message)
        QApplication.processEvents()

    def _populate_table(self, rows: list[dict[str, Any]]) -> None:
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for row_data in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = [
                row_data.get("playerName", ""),
                self._note_cards(row_data),
                row_data.get("playerId", ""),
                row_data.get("handId", ""),
                row_data.get("siteHandNo", ""),
                row_data.get("ruleSet", ""),
                row_data.get("ruleId", ""),
                row_data.get("noteText", ""),
                row_data.get("evidenceText", ""),
            ]
            for column, value in enumerate(values):
                self._set_table_value(self.table, row, column, value, visual_cards=column == 1)
        self.table.setSortingEnabled(True)
        self.table.resizeColumnsToContents()

    def search_players(self) -> None:
        db = self._database()
        players = db.searchPlayersWithAutoNotes(self.player_search_edit.text().strip())
        self._populate_simple_table(
            self.players_table,
            [[player["playerName"], player["playerId"], player["siteId"]] for player in players],
        )

    def load_selected_player_notes(self) -> None:
        selected = self.players_table.selectedItems()
        if not selected:
            QMessageBox.information(self, "Automatic notes", "Select a player first.")
            return
        row = selected[0].row()
        player_id_item = self.players_table.item(row, 1)
        if player_id_item is None:
            return
        player_id = int(player_id_item.text())
        player_name_item = self.players_table.item(row, 0)
        player_name = player_name_item.text() if player_name_item else f"Player {player_id}"
        notes = self._database().getPlayerAutoNotes(player_id, limit=250)
        self._set_player_overview(player_name, notes)
        self._populate_simple_table(
            self.player_notes_table,
            [
                [
                    note.get("createdTs", ""),
                    self._note_cards(note),
                    note.get("ruleId", ""),
                    note.get("noteText", ""),
                    note.get("evidenceText", ""),
                    note.get("handId", ""),
                    note.get("siteHandNo", ""),
                    note.get("ruleSet", ""),
                    note.get("ruleVersion", ""),
                ]
                for note in notes
            ],
        )

    def refresh_pool_summary(self) -> None:
        db = self._database()
        filters = self._pool_filters()
        player_summary = db.getAutoNotePlayerSummary(limit=50, **filters)
        rule_summary = db.getAutoNoteRuleSummary(limit=50, **filters)
        recent_notes = db.getRecentPlayerAutoNotes(limit=200, **filters)
        self._populate_simple_table(
            self.pool_players_table,
            [
                [
                    row.get("playerName", ""),
                    row.get("playerId", ""),
                    row.get("noteCount", ""),
                    row.get("lastNoteTs", ""),
                ]
                for row in player_summary
            ],
        )
        self._populate_simple_table(
            self.pool_rules_table,
            [[row.get("ruleSet", ""), row.get("ruleId", ""), row.get("noteCount", "")] for row in rule_summary],
        )
        self._populate_simple_table(
            self.recent_notes_table,
            [
                [
                    note.get("createdTs", ""),
                    note.get("playerName", ""),
                    self._note_cards(note),
                    note.get("handId", ""),
                    note.get("ruleSet", ""),
                    note.get("ruleId", ""),
                    note.get("noteText", ""),
                    note.get("evidenceText", ""),
                    note.get("siteHandNo", ""),
                ]
                for note in recent_notes
            ],
        )

    def _pool_filters(self) -> dict[str, Any]:
        return {
            "player_filter": self.pool_player_filter.text().strip(),
            "date_from": self.pool_from_date.date().toString("yyyy-MM-dd"),
            "date_to": self.pool_to_date.date().toString("yyyy-MM-dd"),
            "site_id": self.pool_site_filter.currentData(),
            "limit_type": self.pool_limit_filter.currentData() or None,
        }

    def _populate_simple_table(self, table: QTableWidget, rows: list[list[Any]]) -> None:
        table.setSortingEnabled(False)
        table.setRowCount(0)
        card_columns = self._card_columns_for_table(table)
        for values in rows:
            row = table.rowCount()
            table.insertRow(row)
            for column, value in enumerate(values):
                self._set_table_value(table, row, column, value, visual_cards=column in card_columns)
        table.setSortingEnabled(True)
        table.resizeColumnsToContents()

    def _set_table_value(
        self,
        table: QTableWidget,
        row: int,
        column: int,
        value: Any,
        visual_cards: bool = False,
    ) -> None:
        text = "" if value is None else str(value)
        table.setItem(row, column, self._table_item(text))
        if visual_cards and text.strip():
            cards_widget = self._cards_widget(text)
            if cards_widget is not None:
                table.setCellWidget(row, column, cards_widget)
                table.setRowHeight(row, max(table.rowHeight(row), 34))

    def _card_columns_for_table(self, table: QTableWidget) -> set[int]:
        if table is self.player_notes_table:
            return {1}
        if table is self.recent_notes_table:
            return {2}
        return set()

    def _table_item(self, value: Any) -> QTableWidgetItem:
        text = "" if value is None else str(value)
        item = QTableWidgetItem(text)
        if len(text) > 40:
            item.setToolTip(text)
        return item

    def _note_cards(self, note: dict[str, Any]) -> str:
        evidence = note.get("evidence") or {}
        if isinstance(evidence, dict):
            cards = evidence.get("hole_cards") or evidence.get("draw_hand") or evidence.get("door_card")
            if cards:
                return str(cards)
        evidence_text = str(note.get("evidenceText") or "")
        for key in ("hole_cards=", "draw_hand=", "door_card="):
            if key not in evidence_text:
                continue
            tail = evidence_text.split(key, 1)[1]
            return tail.split(";", 1)[0].strip()
        return ""

    def _cards_widget(self, cards_text: str) -> QWidget | None:
        cards = self._parse_cards(cards_text)
        if not cards:
            return None
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(3, 1, 3, 1)
        layout.setSpacing(3)
        for rank, suit in cards:
            label = QLabel(self._card_html(rank, suit))
            label.setTextFormat(Qt.TextFormat.RichText)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setMinimumWidth(28)
            label.setStyleSheet(
                "QLabel { background: #f8fafc; border: 1px solid #64748b; "
                "border-radius: 4px; padding: 2px 4px; font-weight: 700; }",
            )
            label.setToolTip(cards_text)
            layout.addWidget(label)
        layout.addStretch(1)
        return widget

    def _parse_cards(self, cards_text: str) -> list[tuple[str, str]]:
        cards = []
        for match in re.finditer(r"\b(10|[2-9TJQKA])([hdcsHDCS])\b", cards_text):
            rank = "T" if match.group(1) == "10" else match.group(1).upper()
            cards.append((rank, match.group(2).lower()))
        return cards[:7]

    def _card_html(self, rank: str, suit: str) -> str:
        suit_html = {
            "h": ("&hearts;", "#dc2626"),
            "d": ("&diams;", "#2563eb"),
            "c": ("&clubs;", "#16a34a"),
            "s": ("&spades;", "#111827"),
        }.get(suit, ("", "#111827"))
        symbol, color = suit_html
        return f"<span style='color:{color}'>{rank}{symbol}</span>"

    def _set_player_overview(self, player_name: str, notes: list[dict[str, Any]]) -> None:
        rule_counts: dict[str, int] = {}
        for note in notes:
            rule = str(note.get("ruleId") or "-")
            rule_counts[rule] = rule_counts.get(rule, 0) + 1
        top_rule = "-"
        if rule_counts:
            top_rule = max(rule_counts.items(), key=lambda item: (item[1], item[0]))[0]
        latest = str(notes[0].get("createdTs") or "-") if notes else "-"
        self.player_overview_name.setText(player_name)
        self.player_overview_notes.setText(f"Notes: {len(notes)}")
        self.player_overview_top_rule.setText(f"Top rule: {top_rule}")
        self.player_overview_latest.setText(f"Latest: {latest}")

    def open_replayer_from_table(self, table: QTableWidget, row: int, hand_id_column: int) -> None:
        item = table.item(row, hand_id_column)
        if item is None or not item.text().strip():
            return
        try:
            hand_id = int(item.text())
            sql = getattr(self.main_window, "sql", None)
            replayer = GuiReplayer.GuiReplayer(self.config, sql, self.main_window, [hand_id])
            replayer.play_hand(0)
            replayer.raise_()
            replayer.activateWindow()
            self.replayers.append(replayer)
        except Exception as e:  # intentional broad catch: replayer failures should not break the workbench.
            log.exception("Unable to open hand replayer from automatic-note workbench")
            QMessageBox.critical(self, "FPDB Replayer", f"Unable to open hand replayer:\n{e}")

    def _format_summary(self, stats: dict[str, Any], commit: bool, rule_set_ids: set[str] | None) -> str:
        mode = "WROTE" if commit else "DRY RUN"
        lines = [
            f"{mode}: files={stats.get('files', 0)} skipped={stats.get('files_skipped', 0)} "
            f"hands={stats.get('hands', 0)} matched={stats.get('matched_hands', 0)} "
            f"notes={stats.get('notes', 0)}",
        ]
        if stats.get("source") == "database":
            lines[0] = (
                f"{mode} DB: hands={stats.get('hands', 0)} matched={stats.get('matched_hands', 0)} "
                f"notes={stats.get('notes', 0)} without_actions={stats.get('hands_without_actions', 0)}"
            )
        if stats.get("unmatched_hands") or stats.get("matched_by_site_hand_only"):
            lines.append(
                f"Diagnostics: unmatched={stats.get('unmatched_hands', 0)} "
                f"site-hand-only matches={stats.get('matched_by_site_hand_only', 0)}",
            )
        if stats.get("disabled_hands") or stats.get("unsupported_hands") or stats.get("no_note_hands"):
            lines.append(
                f"No-note hands: disabled={stats.get('disabled_hands', 0)} "
                f"unsupported={stats.get('unsupported_hands', 0)} no-rule-match={stats.get('no_note_hands', 0)}",
            )
        if stats.get("raw_unmatched_notes"):
            lines.append(
                f"Raw preview found {stats.get('raw_unmatched_notes', 0)} notes on "
                f"{stats.get('raw_unmatched_hands', 0)} unmatched hands; import those hands before writing notes.",
            )
        if stats.get("import_files"):
            lines.append(
                f"Import: files={stats.get('import_files', 0)} stored={stats.get('import_stored', 0)} "
                f"duplicates={stats.get('import_duplicates', 0)} errors={stats.get('import_errors', 0)}",
            )
        rule_set_counts = format_rule_counts(stats.get("rule_sets", {}))
        if rule_set_counts:
            lines.append(f"Rule sets: {rule_set_counts}")
        rule_counts = format_rule_counts(stats.get("rules", {}))
        if rule_counts:
            lines.append(f"Rules: {rule_counts}")
        lines.append(format_stats_json(stats, commit=commit, rule_set_ids=rule_set_ids))
        return "\n".join(lines)

    def closeEvent(self, event) -> None:
        if self.worker_thread is not None and self.worker_thread.isRunning():
            QMessageBox.information(
                self,
                "Automatic notes",
                "Wait for the automatic-note run to finish before closing.",
            )
            event.ignore()
            return
        if self.db is not None and self.owns_db:
            self.db.close_connection()
        self.db = None
        super().closeEvent(event)
