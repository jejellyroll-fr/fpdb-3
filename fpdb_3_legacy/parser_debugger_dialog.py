"""Tools > Parser Debugger: everything a converter did with a hand history (#903).

Paste a hand history or open a file, pick a site or let the importer's
detection choose, and read the report of :mod:`parser_debug`:

* **Summary** -- the verdict, the site and converter, and the diagnostics; a
  diagnostic that names a line selects it in the text on the left;
* **Detection** -- every converter tried, the one chosen, and the closest ones
  when none recognised the text;
* **Steps** -- each step of the converter's pipeline on the selected hand,
  what it added to the hand and which regexes matched;
* **Contract** -- the generic parser contract, step by step, and the
  whole-hand checks;
* **Hand** -- what was extracted, field by field;
* **Lines** -- which regex read each line of the hand, and the lines none read;
* **Expected** -- the regression sidecars, when the file has some;
* **Log** and **JSON**.

The text on the left is coloured after a run: lines no regex read, lines a
hand failed on. Nothing is written to a database or to the configuration.
"""

from __future__ import annotations

import html
import json
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QPainter, QTextCursor, QTextFormat
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy import parser_debug
from fpdb_3_legacy.failed_hand_debug import failed_hands
from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.parser_debug import Diagnostic, HandResult, ParseDebugReport

# Keep the status colours subtle enough for the dark theme while giving every
# status table the same meaning. A text label remains beside every colour.
_STATUS_BACKGROUNDS = {
    "ok": QColor("#164b38"),
    "warning": QColor("#503914"),
    "error": QColor("#542b30"),
}
_STATUS_FOREGROUNDS = {
    "ok": QColor("#78e2a1"),
    "warning": QColor("#ffd080"),
    "error": QColor("#ff9292"),
}
_STATUS_WORDS = {
    "ok": {"ok", "pass", "passed", "met", "yes", "read", "redundant", "every value matches"},
    "warning": {"warning", "unread", "not reached", "not called", "missing", "skipped"},
    "error": {"error", "failed", "fail", "raised", "mismatch", "bug"},
}
_STATUS_ROLE = Qt.ItemDataRole.UserRole + 1
# Background of a line in the input, by what the report says of it.
_LINE_COLOURS = {
    "read": _STATUS_BACKGROUNDS["ok"],
    "redundant": _STATUS_BACKGROUNDS["ok"],
    "unread": _STATUS_BACKGROUNDS["warning"],
    "not reached": _STATUS_BACKGROUNDS["warning"],
    "error": _STATUS_BACKGROUNDS["error"],
}
_SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}
_LINE_ROLE = Qt.ItemDataRole.UserRole


def _standalone_fixture_text(report: ParseDebugReport, hand: HandResult) -> str:
    """Keep Merge's file-level game description when exporting one game node."""
    if report.detection.converter != "Merge" or not report.source_text:
        return hand.text
    header = re.match(r"\s*(<description\b[^>]*/>\s*)", report.source_text, re.IGNORECASE)
    if header and not hand.text.lstrip().startswith("<description"):
        return header.group(1) + hand.text
    return hand.text


class _LineNumberArea(QWidget):
    """Editor gutter with source line numbers and parser coverage colours."""

    def __init__(self, editor: _TraceTextEdit) -> None:
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API, pylint: disable=invalid-name
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event):  # noqa: N802 - Qt API, pylint: disable=invalid-name
        self.editor.paint_line_number_area(event)


class _TraceTextEdit(QPlainTextEdit):
    """Plain text editor that paints the line coverage beside the input."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.coverage: dict[int, str] = {}
        self.line_number_area = _LineNumberArea(self)
        self.blockCountChanged.connect(self._update_line_number_area_width)
        self.updateRequest.connect(self._update_line_number_area)
        self._update_line_number_area_width(0)

    def line_number_area_width(self) -> int:
        digits = len(str(max(1, self.blockCount())))
        return 12 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_line_number_area_width(self, _new_block_count: int) -> None:
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_line_number_area(self, rect, dy: int) -> None:
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_line_number_area_width(0)

    def resizeEvent(self, event):  # noqa: N802 - Qt API, pylint: disable=invalid-name
        super().resizeEvent(event)
        contents = self.contentsRect()
        self.line_number_area.setGeometry(
            contents.left(), contents.top(), self.line_number_area_width(), contents.height()
        )

    def paint_line_number_area(self, event) -> None:
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor("#081322"))
        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                line = block_number + 1
                kind = _status_kind(self.coverage.get(line, ""))
                if kind:
                    painter.fillRect(0, top, 4, self.fontMetrics().height(), _STATUS_BACKGROUNDS[kind])
                painter.setPen(QColor("#8393a8"))
                painter.drawText(
                    7,
                    top,
                    self.line_number_area.width() - 9,
                    self.fontMetrics().height(),
                    int(Qt.AlignmentFlag.AlignRight),
                    str(line),
                )
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1

    def set_coverage(self, coverage: dict[int, str]) -> None:
        self.coverage = coverage
        self.line_number_area.update()


def _monospace() -> QFont:
    return QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)


def _tree(
    headers: Iterable[str],
    *,
    widths: tuple[int, ...] = (),
) -> QTreeWidget:
    tree = QTreeWidget()
    labels = list(headers)
    tree.setColumnCount(len(labels))
    tree.setHeaderLabels(labels)
    header = tree.header()
    header.setStretchLastSection(False)
    header.setSectionsMovable(True)
    header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    for column, width in enumerate(widths):
        tree.setColumnWidth(column, width)
    tree.setAlternatingRowColors(True)
    tree.setUniformRowHeights(True)
    tree.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    tree.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    tree.setItemDelegate(_StatusColorDelegate(tree))
    return tree


class _StatusColorDelegate(QStyledItemDelegate):
    """Paint status rows above qt_material's item stylesheet."""

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        kind = index.siblingAtColumn(0).data(_STATUS_ROLE)
        if kind not in _STATUS_BACKGROUNDS:
            super().paint(painter, option, index)
            return
        text_option = QStyleOptionViewItem(option)
        text_option.text = ""
        super().paint(painter, text_option, index)
        painter.save()
        painter.fillRect(option.rect, _STATUS_BACKGROUNDS[kind])
        value = index.data(Qt.ItemDataRole.DisplayRole)
        if value is not None and str(value):
            text_rect = option.rect.adjusted(8, 0, -8, 0)
            text = option.fontMetrics.elidedText(str(value), option.textElideMode, text_rect.width())
            painter.setFont(option.font)
            painter.setPen(_STATUS_FOREGROUNDS[kind])
            painter.drawText(text_rect, int(option.displayAlignment), text)
        painter.restore()


def _status_kind(status: str) -> str | None:
    """Map the parser's varied status vocabulary to the UI's three colours."""
    normalized = status.casefold().strip()
    return next((kind for kind, words in _STATUS_WORDS.items() if normalized in words), None)


def _colour_status_row(item: QTreeWidgetItem, status: str) -> None:
    """Tint a whole table row and its status text according to the outcome."""
    kind = _status_kind(status)
    if kind is None:
        return
    item.setData(0, _STATUS_ROLE, kind)
    for column in range(item.columnCount()):
        item.setBackground(column, _STATUS_BACKGROUNDS[kind])
        item.setForeground(column, _STATUS_FOREGROUNDS[kind])


def _status_legend(parent: QWidget) -> QLabel:
    legend = QLabel(parent)
    legend.setObjectName("status_legend")
    legend.setTextFormat(Qt.TextFormat.RichText)
    legend.setAccessibleName(_("Status colours"))
    legend.setText(
        " &nbsp; ".join(
            f"<span style='color:{_STATUS_FOREGROUNDS[kind].name()}'><b>●</b> {html.escape(label)}</span>"
            for kind, label in (("ok", _("OK")), ("warning", _("Missing / not reached")), ("error", _("Error")))
        )
    )
    legend.setAlignment(Qt.AlignmentFlag.AlignRight)
    return legend


def _fill_value(parent: QTreeWidgetItem, value: Any) -> None:
    """Show a nested value under ``parent``: one child per key or item."""
    if isinstance(value, Mapping):
        for key, item in value.items():
            _add_value(parent, str(key), item)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _add_value(parent, f"[{index}]", item)


def _add_value(parent: QTreeWidgetItem, key: str, value: Any) -> None:
    if isinstance(value, (Mapping, list)):
        child = QTreeWidgetItem(parent, [key, "" if value else _("(empty)")])
        _fill_value(child, value)
    else:
        QTreeWidgetItem(parent, [key, "" if value is None else str(value)])


class ParserDebuggerDialog(QDialog):  # pylint: disable=too-many-instance-attributes  # one per widget
    """The Parser Debugger window."""

    clear_button: QPushButton

    def __init__(self, config: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self.report: ParseDebugReport | None = None
        self.loaded_path: Path | None = None
        self.loaded_text = ""
        self.fixture_button: QPushButton
        self.parser_label: QLabel
        self.detection_tree: QTreeWidget
        self.failed_hands_table: QTableWidget
        self._failed_hand_keys: list[str] = []
        self._failed_hands_signature: tuple[tuple[str, int], ...] | None = None
        self.setWindowTitle(_("Parser Debugger"))
        self.resize(1160, 780)
        self.setMinimumSize(900, 620)
        self.setMaximumSize(1320, 1000)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.setHandleWidth(10)
        splitter.setChildrenCollapsible(False)
        splitter.setStyleSheet(
            "QSplitter::handle:horizontal { background: #172b45; }"
            "QSplitter::handle:horizontal:hover { background: #00c78a; }"
        )
        input_panel = self._input_panel()
        report_panel = self._report_panel()
        input_panel.setMinimumWidth(340)
        report_panel.setMinimumWidth(420)
        splitter.addWidget(input_panel)
        splitter.addWidget(report_panel)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)

        layout = QVBoxLayout(self)
        layout.addWidget(splitter)

    # -- layout ---------------------------------------------------------------

    def _input_panel(self) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        controls = QHBoxLayout()
        controls.addWidget(QLabel(_("Site")))
        self.site_combo = QComboBox(panel)
        self.site_combo.addItem(_("Auto-detect"), None)
        for site in parser_debug.available_sites(self.config):
            label = site if parser_debug._site_enabled(self.config, site) else _("{site} (disabled)").format(site=site)
            self.site_combo.addItem(label, site)
        controls.addWidget(self.site_combo, 1)
        self.open_button = QPushButton(_("Open file…"), panel)
        self.open_button.clicked.connect(self.open_file)
        controls.addWidget(self.open_button)
        self.run_button = QPushButton(_("Debug parse"), panel)
        self.run_button.setDefault(True)
        self.run_button.clicked.connect(self.run)
        controls.addWidget(self.run_button)
        self.clear_button = QPushButton(_("Clear"), panel)
        self.clear_button.setToolTip(_("Clear the raw hand and its analysis"))
        self.clear_button.clicked.connect(self.clear_debugger)
        controls.addWidget(self.clear_button)
        layout.addLayout(controls)

        options = QHBoxLayout()
        self.trace_check = QCheckBox(_("Trace lines"), panel)
        self.trace_check.setChecked(True)
        self.trace_check.setToolTip(_("Parse a second time to tell which regex read each line"))
        options.addWidget(self.trace_check)
        self.derived_check = QCheckBox(_("Derived stats"), panel)
        self.derived_check.setToolTip(_("Add what fpdb would store for each hand (Hands, HandsPlayers)"))
        options.addWidget(self.derived_check)
        options.addStretch(1)
        layout.addLayout(options)

        self.input = _TraceTextEdit(panel)
        self.input.setFont(_monospace())
        self.input.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.input.setPlaceholderText(_("Paste a hand history here, or open a file"))
        layout.addWidget(self.input, 1)
        return panel

    def _fixture_action(self, parent: QWidget) -> QPushButton:
        """Build the anonymized-fixture action without crowding the report layout."""
        self.fixture_button = QPushButton(_("Save anonymized fixture…"), parent)
        self.fixture_button.clicked.connect(self.save_fixture)
        return self.fixture_button

    def _detection_panel(self, parent: QWidget) -> QWidget:
        """Show the instantiated parser above the converter probe table."""
        panel = QWidget(parent)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        self.parser_label = QLabel(_("Parser not determined yet"), panel)
        self.parser_label.setFont(_monospace())
        self.parser_label.setWordWrap(True)
        self.parser_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.parser_label.setToolTip(_("The Python class instantiated to parse the selected file."))
        layout.addWidget(self.parser_label)
        self.detection_tree = _tree(
            [_("Converter"), _("Site"), _("Recognised"), _("Line"), _("Lines read"), _("Note")],
            widths=(180, 120, 105, 70, 95, 180),
        )
        layout.addWidget(self.detection_tree, 1)
        return panel

    def _failed_hands_panel(self, parent: QWidget) -> QWidget:
        """Show the session queue inside the Parser Debugger."""
        panel = QWidget(parent)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        self.failed_hands_table = QTableWidget(0, 7, panel)
        self.failed_hands_table.setHorizontalHeaderLabels(
            [
                _("Site / converter"),
                _("Source file"),
                _("Mode"),
                _("Hand"),
                _("Failure"),
                _("Time"),
                _("Parser message"),
            ]
        )
        self.failed_hands_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.failed_hands_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.failed_hands_table.setWordWrap(False)
        header = self.failed_hands_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionsMovable(True)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for column, width in enumerate((180, 230, 90, 100, 100, 165)):
            self.failed_hands_table.setColumnWidth(column, width)
        self.failed_hands_table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.failed_hands_table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.failed_hands_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.failed_hands_table.itemDoubleClicked.connect(lambda _item: self.replay_failed_hand())
        layout.addWidget(self.failed_hands_table, 1)

        actions = QHBoxLayout()
        self.replay_failed_hand_button = QPushButton(_("Replay selected hand"), panel)
        self.remove_failed_hand_button = QPushButton(_("Remove"), panel)
        self.clear_failed_hands_button = QPushButton(_("Clear list"), panel)
        self.replay_failed_hand_button.clicked.connect(self.replay_failed_hand)
        self.remove_failed_hand_button.clicked.connect(self.remove_failed_hand)
        self.clear_failed_hands_button.clicked.connect(self.clear_failed_hands)
        actions.addWidget(self.replay_failed_hand_button)
        actions.addWidget(self.remove_failed_hand_button)
        actions.addWidget(self.clear_failed_hands_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.refresh_failed_hands()
        self.failed_hands_timer = QTimer(self)
        self.failed_hands_timer.timeout.connect(self.refresh_failed_hands)
        self.failed_hands_timer.start(1500)
        return panel

    def _report_panel(self) -> QWidget:  # noqa: PLR0915 - one tab for each parser report view
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        header = QHBoxLayout()
        self.verdict_label = QLabel(_("Paste a hand history and press Debug parse."), panel)
        self.verdict_label.setTextFormat(Qt.TextFormat.RichText)
        self.verdict_label.setWordWrap(True)
        self.verdict_label.setMinimumWidth(0)
        self.verdict_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        header.addWidget(self.verdict_label, 1)
        self.failed_hands_button = QPushButton(_("Hands to debug ({count})").format(count=0), panel)
        self.failed_hands_button.setMaximumWidth(190)
        self.failed_hands_button.clicked.connect(self.show_failed_hands)
        header.addWidget(self.failed_hands_button)
        header.addWidget(QLabel(_("Hand")))
        self.hand_combo = QComboBox(panel)
        self.hand_combo.setMaximumWidth(150)
        self.hand_combo.currentIndexChanged.connect(self._show_hand)
        header.addWidget(self.hand_combo)
        layout.addLayout(header)

        layout.addWidget(_status_legend(panel))

        self.tabs = QTabWidget(panel)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.setElideMode(Qt.TextElideMode.ElideNone)
        self.tabs.setMovable(True)
        self.tabs.tabBar().setExpanding(False)
        self.summary = QTextBrowser(panel)
        self.summary.setOpenLinks(False)
        self.summary.anchorClicked.connect(lambda url: self.go_to_line(int(url.toString().removeprefix("line:"))))
        detection_panel = self._detection_panel(panel)
        self.steps_tree = _tree(
            [_("Step"), _("Status"), _("ms"), _("What it did"), _("Regexes")],
            widths=(125, 90, 60, 280, 200),
        )
        self.contract_tree = _tree(
            [_("Step / check"), _("Status"), _("Field"), _("Message"), _("Expected"), _("Found")],
            widths=(160, 90, 120, 260, 140, 140),
        )
        self.hand_tree = _tree([_("Field"), _("Value")], widths=(180, 300))
        self.lines_tree = _tree(
            [_("Line"), _("Status"), _("Text"), _("Read by"), _("Regex match spans"), _("Reason")],
            widths=(55, 90, 300, 180, 220, 260),
        )
        self.lines_tree.itemActivated.connect(self._line_item_activated)
        self.expected_tree = _tree(
            [_("Sidecar"), _("Field"), _("Player"), _("Expected"), _("Actual")],
            widths=(150, 140, 140, 200, 200),
        )
        self.log_view = QPlainTextEdit(panel)
        self.log_view.setReadOnly(True)
        self.log_view.setFont(_monospace())
        self.json_view = QPlainTextEdit(panel)
        self.json_view.setReadOnly(True)
        self.json_view.setFont(_monospace())
        self.changes_view = QPlainTextEdit(panel)
        self.changes_view.setReadOnly(True)
        for widget, title in (
            (self.summary, _("Summary")),
            (detection_panel, _("Detection")),
            (self.steps_tree, _("Steps")),
            (self.contract_tree, _("Contract")),
            (self.hand_tree, _("Hand")),
            (self.lines_tree, _("Lines")),
            (self.expected_tree, _("Expected")),
            (self.log_view, _("Log")),
            (self.json_view, _("JSON")),
            (self.changes_view, _("Changes")),
        ):
            tab_index = self.tabs.addTab(widget, title)
            self.tabs.setTabToolTip(tab_index, title)
        self.failed_hands_panel = self._failed_hands_panel(panel)
        failed_hands_index = self.tabs.addTab(self.failed_hands_panel, _("Hands to debug"))
        self.tabs.setTabToolTip(failed_hands_index, _("Hands to debug"))
        layout.addWidget(self.tabs, 1)

        buttons = QGridLayout()
        self.copy_button = QPushButton(_("Copy bug report"), panel)
        self.copy_button.setToolTip(_("Markdown for a GitHub issue, player names replaced"))
        self.copy_button.clicked.connect(self.copy_bug_report)
        self.save_button = QPushButton(_("Save report…"), panel)
        self.save_button.clicked.connect(self.save_report)
        self.compare_button = QPushButton(_("Compare with…"), panel)
        self.compare_button.setToolTip(_("What changed since a report saved earlier on the same text"))
        self.compare_button.clicked.connect(self.compare_report)
        action_buttons = (self.copy_button, self.save_button, self.compare_button, self._fixture_action(panel))
        for index, button in enumerate(action_buttons):
            button.setEnabled(False)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            buttons.addWidget(button, index // 2, index % 2)
        buttons.setColumnStretch(0, 1)
        buttons.setColumnStretch(1, 1)
        self.status_label = QLabel(panel)
        self.status_label.setMinimumWidth(0)
        self.status_label.setMaximumWidth(560)
        self.status_label.setWordWrap(True)
        buttons.addWidget(self.status_label, 2, 0, 1, 2)
        layout.addLayout(buttons)
        return panel

    # -- actions --------------------------------------------------------------

    def clear_debugger(self) -> None:
        """Clear the raw hand and all analysis produced for it."""
        self.input.clear()
        self.input.set_coverage({})
        self.input.setExtraSelections([])
        self.loaded_path = None
        self.loaded_text = ""
        self.report = None
        self.verdict_label.setText(_("Paste a hand history and press Debug parse."))
        self.parser_label.setText(_("Parser not determined yet"))
        self.hand_combo.blockSignals(True)
        self.hand_combo.clear()
        self.hand_combo.blockSignals(False)
        self.summary.clear()
        for tree in (
            self.detection_tree,
            self.steps_tree,
            self.contract_tree,
            self.hand_tree,
            self.lines_tree,
            self.expected_tree,
        ):
            tree.clear()
        for view in (self.log_view, self.json_view, self.changes_view):
            view.clear()
        self.status_label.clear()
        for button in (self.copy_button, self.save_button, self.compare_button, self.fixture_button):
            button.setEnabled(False)
        self.tabs.setCurrentWidget(self.summary)

    def open_file(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(self, _("Open a hand history"))
        if path:
            self.load_file(Path(path))

    def load_file(self, path: Path) -> None:
        """Show ``path`` and debug it as a file, so its name and encoding count as at import."""
        from fpdb_3_legacy.IdentifySite import IdentifySite

        text, encoding = IdentifySite(self.config).read_file(str(path))
        text = text or ""
        self.input.setPlainText(text)
        self.loaded_path, self.loaded_text = path, self.input.toPlainText()
        self.status_label.setText(
            _("{name} · {encoding}").format(name=path.name, encoding=encoding or _("unknown encoding"))
        )

    def load_import_failure(self, text: str, site: str, source: str) -> None:
        """Load a captured hand without consulting its original source file."""
        self.input.setPlainText(text)
        self.loaded_path = None
        self.loaded_text = ""
        site_index = self.site_combo.findData(site)
        if site_index >= 0:
            self.site_combo.setCurrentIndex(site_index)
        self.status_label.setText(_("Captured from {source} · {site}").format(source=source, site=site))

    def show_failed_hands(self) -> None:
        """Focus the import-failure list embedded in the debugger."""
        self.refresh_failed_hands()
        self.tabs.setCurrentWidget(self.failed_hands_panel)

    def refresh_failed_hands(self) -> None:
        entries = failed_hands.entries()
        self.failed_hands_button.setText(_("Hands to debug ({count})").format(count=len(entries)))
        signature = tuple((entry.key, entry.attempts) for entry in entries)
        if signature == self._failed_hands_signature:
            return
        self._failed_hands_signature = signature
        self._failed_hand_keys = [entry.key for entry in entries]
        self.failed_hands_table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            hand = entry.hand_identifier or str(entry.hand_index)
            if entry.attempts > 1:
                hand = _("{hand} · {attempts} attempts").format(hand=hand, attempts=entry.attempts)
            values = (
                f"{entry.site} · {entry.converter}",
                entry.source,
                entry.mode,
                hand,
                entry.failure_type,
                entry.timestamp.strftime("%Y-%m-%d %H:%M:%S %Z"),
                entry.message,
            )
            for column, value in enumerate(values):
                self.failed_hands_table.setItem(row, column, QTableWidgetItem(value))
        has_entries = bool(entries)
        self.replay_failed_hand_button.setEnabled(has_entries)
        self.remove_failed_hand_button.setEnabled(has_entries)
        self.clear_failed_hands_button.setEnabled(has_entries)

    def _selected_failed_hand_key(self) -> str | None:
        rows = self.failed_hands_table.selectionModel().selectedRows()
        if rows and rows[0].row() < len(self._failed_hand_keys):
            return self._failed_hand_keys[rows[0].row()]
        return None

    def replay_failed_hand(self) -> None:
        key = self._selected_failed_hand_key()
        if key is None:
            return
        entry = next((candidate for candidate in failed_hands.entries() if candidate.key == key), None)
        if entry is None:
            self.refresh_failed_hands()
            return
        self.load_import_failure(entry.replay_text, entry.site, entry.source)
        self.run()

    def remove_failed_hand(self) -> None:
        key = self._selected_failed_hand_key()
        if key is not None:
            failed_hands.remove(key)
            self.refresh_failed_hands()

    def clear_failed_hands(self) -> None:
        failed_hands.clear()
        self.refresh_failed_hands()

    def run(self) -> None:
        text = self.input.toPlainText()
        if not text.strip():
            self.verdict_label.setText(_("Nothing to parse: paste a hand history or open a file."))
            return
        site = self.site_combo.currentData()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            if self.loaded_path is not None and text == self.loaded_text:
                report = parser_debug.debug_parse_file(
                    self.loaded_path,
                    self.config,
                    site,
                    trace_lines=self.trace_check.isChecked(),
                    derived=self.derived_check.isChecked(),
                )
            else:
                report = parser_debug.debug_parse_text(
                    text,
                    self.config,
                    site,
                    trace_lines=self.trace_check.isChecked(),
                    derived=self.derived_check.isChecked(),
                )
        finally:
            QApplication.restoreOverrideCursor()
        self.show_report(report)

    def copy_bug_report(self) -> None:
        if self.report is None:
            return
        QGuiApplication.clipboard().setText(parser_debug.bug_report(self.report, self._current_hand_index()))
        self.status_label.setText(_("Bug report copied"))

    def save_report(self) -> None:
        if self.report is None:
            return
        path, _filter = QFileDialog.getSaveFileName(self, _("Save the report"), "parser-report.json", "JSON (*.json)")
        if path:
            Path(path).write_text(self.report.to_json(), encoding="utf-8")
            self.status_label.setText(_("Report saved"))

    def compare_report(self) -> None:
        if self.report is None:
            return
        path, _filter = QFileDialog.getOpenFileName(self, _("Compare with a saved report"), "", "JSON (*.json)")
        if not path:
            return
        previous = json.loads(Path(path).read_text(encoding="utf-8"))
        self.show_changes(parser_debug.diff_reports(previous, self.report.to_dict()))

    def save_fixture(self) -> None:
        """Save the selected hand as a text fixture after reviewing its names."""
        hand = self._current_hand()
        if hand is None:
            return
        players = hand.extracted.get("players", [])
        names = list(dict.fromkeys(str(player.get("name", "")) for player in players if player.get("name")))
        default_names = "\n".join(names)
        names_text, accepted = QInputDialog.getMultiLineText(
            self,
            _("Anonymize fixture"),
            _("Player names to replace, one per line. Review the list and add any names the parser missed."),
            default_names,
        )
        if not accepted:
            return
        names = list(
            dict.fromkeys(
                [str(player.get("name", "")).strip() for player in players if player.get("name")]
                + [name.strip() for name in names_text.splitlines() if name.strip()]
            )
        )
        if not names:
            QMessageBox.warning(self, _("Cannot anonymize fixture"), _("Add at least one player name to replace."))
            return
        hero = hand.extracted.get("header", {}).get("hero")
        room = self.report.detection.converter if self.report is not None else ""
        from fpdb_3_legacy.anonymize_hh import anonymize_text

        fixture_text = _standalone_fixture_text(self.report, hand) if self.report is not None else hand.text
        anonymized, leftovers = anonymize_text(fixture_text, room or "", names, hero if hero in names else None)
        if leftovers:
            QMessageBox.warning(
                self,
                _("Anonymization incomplete"),
                _(
                    "These real names or account tokens are still present: {values}. Add them to the list or review the text."
                ).format(values=", ".join(leftovers)),
            )
            return
        validation = parser_debug.debug_parse_text(
            anonymized,
            self.config,
            self.report.detection.site if self.report is not None else None,
            trace_lines=False,
        )
        if len(validation.hands) != 1 or validation.hands[0].status != hand.status:
            actual = validation.hands[0].status if len(validation.hands) == 1 else f"{len(validation.hands)} hands"
            QMessageBox.warning(
                self,
                _("Fixture validation failed"),
                _("The saved text does not reproduce this hand ({expected}); validation returned {actual}.").format(
                    expected=hand.status, actual=actual
                ),
            )
            return
        path, _filter = QFileDialog.getSaveFileName(
            self,
            _("Save anonymized hand history fixture"),
            self._fixture_default_path(hand),
            "Text files (*.txt);;All files (*)",
        )
        if path:
            try:
                target = Path(path)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(anonymized, encoding="utf-8", newline="")
            except OSError as exc:
                QMessageBox.warning(self, _("Could not save fixture"), str(exc))
                return
            self.status_label.setText(_("Anonymized fixture saved; review privacy before commit"))
            QMessageBox.information(
                self,
                _("Fixture saved"),
                _(
                    "Fixture saved to {path}. Review the anonymized text before committing it. If it changes generated statistics, regenerate the stats guide."
                ).format(path=path),
            )

    def _fixture_default_path(self, hand: HandResult) -> str:
        """Suggest a repository fixture location and a descriptive anonymized name."""
        site = self.report.detection.site if self.report is not None else None
        site = site or "unknown-site"
        safe_site = re.sub(r"[^A-Za-z0-9_-]+", "-", site).strip("-") or "unknown-site"
        root = Path(__file__).resolve().parents[1] / "regression-test-files"
        gametype = hand.extracted.get("gametype", {})
        base = str(gametype.get("base", "unknown")).lower()
        if hand.status != "ok":
            directory = root / "unsupported-sites" / safe_site
        else:
            header = hand.extracted.get("header", {})
            street = "Stud" if base == "stud" else "Draw" if base in {"draw", "badugi"} else "Flop"
            folder = "tour" if header.get("tournament") or header.get("buyin") else "cash"
            directory = root / folder / safe_site / street
        return str(directory / f"{safe_site}-{base}-parser-debug-hand-{hand.index + 1}-anonymized.txt")

    def show_changes(self, changes: list[str]) -> None:
        self.changes_view.setPlainText("\n".join(changes) if changes else _("No change."))
        self.tabs.setCurrentWidget(self.changes_view)

    def go_to_line(self, line: int) -> None:
        """Select ``line`` (1-based) of the input."""
        block = self.input.document().findBlockByNumber(max(line - 1, 0))
        if not block.isValid():
            return
        cursor = QTextCursor(block)
        cursor.select(QTextCursor.SelectionType.LineUnderCursor)
        self.input.setTextCursor(cursor)
        self.input.centerCursor()

    # -- rendering ------------------------------------------------------------

    def show_report(self, report: ParseDebugReport) -> None:
        self.report = report
        counts = ", ".join(f"{count} {status}" for status, count in report.counts().items() if count) or _("no hand")
        colour = "#2e7d32" if report.verdict == "ok" else "#c62828"
        detection = report.detection
        site = html.escape(detection.site or _("not recognised"))
        self.verdict_label.setText(
            f"<b style='color:{colour}'>{html.escape(report.verdict.upper())}</b> &nbsp; "
            f"{site} ({html.escape(detection.converter or '-')}) &nbsp; {html.escape(counts)} &nbsp; "
            f"{report.duration_ms:.0f} ms"
        )
        self.summary.setHtml(self._summary_html(report))
        self._fill_detection(report)
        self.json_view.setPlainText(report.to_json())
        self.hand_combo.blockSignals(True)
        self.hand_combo.clear()
        no_id = _("no id")
        for hand in report.hands:
            handid = hand.handid or no_id
            self.hand_combo.addItem(f"{hand.index}: {handid} ({hand.status})", hand.index)
        self.hand_combo.blockSignals(False)
        self._show_hand()
        self._colour_input(report)
        for button in (self.copy_button, self.save_button, self.compare_button, self.fixture_button):
            button.setEnabled(True)
        self.tabs.setCurrentWidget(self.summary)

    def _summary_html(self, report: ParseDebugReport) -> str:
        detection = report.detection
        title = html.escape(_("Detection"))
        parts = [f"<h3>{title}</h3><p>"]
        if detection.site:
            parts.append(
                html.escape(
                    _("Read by the {converter} converter as {site}.").format(
                        converter=detection.converter, site=detection.site
                    )
                )
            )
            if detection.marker:
                parts.append(
                    "<br>"
                    + html.escape(_("Recognised on line {line} by")).format(line=detection.marker_line)
                    + f" <code>{html.escape(detection.marker)}</code>"
                )
        if detection.message:
            parts.append(f"<br>{html.escape(detection.message)}")
        if detection.encoding:
            parts.append("<br>" + html.escape(_("File encoding: {encoding}").format(encoding=detection.encoding)))
        closest = html.escape(_("Closest"))
        parts += [f"<br>{closest}: {html.escape(item)}" for item in detection.closest]
        parts.append("</p>")
        diagnostics = sorted(report.diagnostics, key=lambda item: _SEVERITY_ORDER.get(item.severity, 3))
        if diagnostics:
            title = html.escape(_("Diagnostics"))
            parts.append(f"<h3>{title}</h3><ul>")
            parts += [f"<li>{_diagnostic_html(diagnostic)}</li>" for diagnostic in diagnostics]
            parts.append("</ul>")
        else:
            nothing = html.escape(_("Nothing to report."))
            parts.append(f"<p>{nothing}</p>")
        return "".join(parts)

    def _fill_detection(self, report: ParseDebugReport) -> None:
        self.detection_tree.clear()
        parser_used = _("Parser used")
        archive_flags = _("Archive: {archive}; head: {head}; divider: {divider}").format(
            archive=report.detection.archive,
            head=report.detection.archive_head,
            divider=report.detection.archive_divider,
        )
        self.parser_label.setText(
            f"{parser_used}: {report.detection.parser_class} · {archive_flags}"
            if report.detection.parser_class
            else _("No hand parser was created for this file")
        )
        chosen = report.detection.converter
        disabled = _("disabled")
        for probe in sorted(report.detection.probes, key=lambda item: (not item.identified, -item.body_score)):
            item = QTreeWidgetItem(
                self.detection_tree,
                [
                    probe.converter,
                    probe.site + ("" if probe.enabled else f" ({disabled})"),
                    _("yes") if probe.identified else _("no"),
                    "" if probe.line is None else str(probe.line),
                    str(probe.body_score),
                    probe.hint or probe.pattern,
                ],
            )
            if probe.converter == chosen:
                font = item.font(0)
                font.setBold(True)
                for column in range(item.columnCount()):
                    item.setFont(column, font)
            if probe.identified:
                _colour_status_row(item, "yes")
        for column in range(5):
            self.detection_tree.resizeColumnToContents(column)

    def _current_hand_index(self) -> int | None:
        data = self.hand_combo.currentData()
        return int(data) if data is not None else None

    def _current_hand(self) -> HandResult | None:
        if self.report is None:
            return None
        index = self._current_hand_index()
        return next((hand for hand in self.report.hands if hand.index == index), None)

    def _show_hand(self, *_args: Any) -> None:
        for tree in (self.steps_tree, self.contract_tree, self.hand_tree, self.lines_tree, self.expected_tree):
            tree.clear()
        self.log_view.clear()
        hand = self._current_hand()
        if hand is None:
            self.fixture_button.setEnabled(False)
            return
        self.fixture_button.setEnabled(True)
        self._fill_steps(hand)
        self._fill_contract(hand)
        root = QTreeWidgetItem(self.hand_tree, [_("Hand"), hand.handid])
        _fill_value(root, hand.extracted)
        self.hand_tree.expandToDepth(1)
        self.hand_tree.resizeColumnToContents(0)
        self._fill_lines(hand)
        self._fill_expected(hand)
        log = [f"{record.level:<8} {record.logger}: {record.message}" for record in hand.logs]
        if self.report is not None:
            log.extend(
                f"{diagnostic.severity.upper():<8} parser_debugger [{diagnostic.kind}]: {diagnostic.message}"
                for diagnostic in self.report.diagnostics
                if diagnostic.hand_index == hand.index
            )
        if hand.traceback:
            log += ["", hand.traceback]
        if not log:
            log.append(_("No warnings or logs were emitted during this parse."))
        self.log_view.setPlainText("\n".join(log))

    def _fill_steps(self, hand: HandResult) -> None:
        for step in hand.steps:
            changes = ", ".join(f"{key} {value}" for key, value in step.changes.items())
            regexes = ", ".join(f"{name} ×{count}" for name, count in step.matches.items())
            item = QTreeWidgetItem(
                self.steps_tree,
                [
                    step.label or step.step,
                    step.status,
                    f"{step.duration_ms:.2f}",
                    step.error or step.result or changes,
                    regexes,
                ],
            )
            _colour_status_row(item, step.status)
        for column in range(4):
            self.steps_tree.resizeColumnToContents(column)
        self.steps_tree.setColumnWidth(3, min(self.steps_tree.columnWidth(3), 380))

    def _fill_contract(self, hand: HandResult) -> None:
        for violation in hand.violations:
            item = QTreeWidgetItem(
                self.contract_tree,
                [
                    violation["step"],
                    violation["severity"],
                    violation["field"],
                    violation["message"],
                    violation["expected"],
                    violation["found"],
                ],
            )
            _colour_status_row(item, violation["severity"])
        if not hand.violations and hand.ok:
            item = QTreeWidgetItem(
                self.contract_tree, [_("contract"), _("met"), "", _("Every step produced what it must")]
            )
            _colour_status_row(item, "met")
        for check in hand.checks:
            item = QTreeWidgetItem(self.contract_tree, [check["name"], check["status"], "", check["message"]])
            _colour_status_row(item, check["status"])
            for detail in check["details"]:
                detail_item = QTreeWidgetItem(item, ["", "", "", detail])
                _colour_status_row(detail_item, check["status"])
        for column in range(3):
            self.contract_tree.resizeColumnToContents(column)

    def _fill_lines(self, hand: HandResult) -> None:
        for mark in hand.lines:
            line = hand.start_line + mark.number - 1
            spans = "; ".join(
                f"{span['regex']} [{span['start']}:{span['end']}] {span['text']!r}" for span in mark.spans
            )
            item = QTreeWidgetItem(
                self.lines_tree,
                [str(line), mark.status, mark.text, ", ".join(mark.regexes), spans, mark.reason],
            )
            item.setData(0, _LINE_ROLE, line)
            _colour_status_row(item, mark.status)
        for column in range(4):
            self.lines_tree.resizeColumnToContents(column)
        self.lines_tree.setColumnWidth(2, min(self.lines_tree.columnWidth(2), 460))
        self.lines_tree.setColumnWidth(4, min(self.lines_tree.columnWidth(4), 500))

    def _fill_expected(self, hand: HandResult) -> None:
        if hand.fingerprint is not None:
            item = QTreeWidgetItem(
                self.expected_tree,
                [_("Hand fingerprint"), "", "", json.dumps(hand.fingerprint, ensure_ascii=False, sort_keys=True), ""],
            )
            item.setToolTip(3, json.dumps(hand.fingerprint, ensure_ascii=False, indent=2, sort_keys=True))
        if self.report is not None and self.report.snapshot and hand.index == 0:
            snapshot = self.report.snapshot
            snapshot_status = _("matches") if snapshot.get("passed") else _("differs")
            item = QTreeWidgetItem(
                self.expected_tree,
                [
                    _("Live parser snapshot"),
                    snapshot_status,
                    "",
                    snapshot.get("key", ""),
                    snapshot.get("actual_sha256", snapshot.get("error", "")),
                ],
            )
            item.setToolTip(3, json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True))
            _colour_status_row(item, "ok" if snapshot.get("passed") else "error")
        if not hand.sidecars:
            item = QTreeWidgetItem(self.expected_tree, [_("This file has no regression sidecar (.hands, .hp, .gt)")])
            _colour_status_row(item, "missing")
            return
        if hand.sidecars.get("error"):
            item = QTreeWidgetItem(self.expected_tree, [_("error"), hand.sidecars["error"]])
            _colour_status_row(item, "error")
        if hand.sidecars["passed"]:
            item = QTreeWidgetItem(self.expected_tree, [", ".join(hand.sidecars["compared"]), _("every value matches")])
            _colour_status_row(item, "every value matches")
        for issue in hand.sidecars["issues"]:
            item = QTreeWidgetItem(
                self.expected_tree,
                [
                    issue["sidecar"],
                    issue["field"],
                    issue.get("player") or "",
                    repr(issue["expected"]),
                    repr(issue["actual"]),
                ],
            )
            _colour_status_row(item, "mismatch")

    def _line_item_activated(self, item: QTreeWidgetItem, _column: int) -> None:
        line = item.data(0, _LINE_ROLE)
        if line:
            self.go_to_line(int(line))

    def _colour_input(self, report: ParseDebugReport) -> None:
        selections = []
        coverage: dict[int, str] = {}
        failed_lines = {hand.start_line for hand in report.hands if not hand.ok}
        failed_lines |= {
            diagnostic.line for diagnostic in report.diagnostics if diagnostic.severity == "error" and diagnostic.line
        }
        for hand in report.hands:
            for mark in hand.lines:
                line = hand.start_line + mark.number - 1
                coverage[line] = mark.status
                if mark.status == "unread":
                    selections.append(self._line_selection(line, _LINE_COLOURS["unread"]))
        selections += [self._line_selection(line, _LINE_COLOURS["error"]) for line in sorted(failed_lines)]
        for diagnostic in report.diagnostics:
            if diagnostic.line and diagnostic.severity in {"warning", "error"}:
                coverage[diagnostic.line] = diagnostic.severity
        if isinstance(self.input, _TraceTextEdit):
            self.input.set_coverage(coverage)
        self.input.setExtraSelections([selection for selection in selections if selection is not None])

    def _line_selection(self, line: int, colour: QColor) -> QTextEdit.ExtraSelection | None:
        block = self.input.document().findBlockByNumber(line - 1)
        if not block.isValid():
            return None
        selection = QTextEdit.ExtraSelection()
        selection.format.setBackground(colour)
        selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        selection.cursor = QTextCursor(block)
        return selection


def _diagnostic_html(diagnostic: Diagnostic) -> str:
    colour = {"error": "#c62828", "warning": "#ef6c00"}.get(diagnostic.severity, "#607d8b")
    where = parser_debug.diagnostic_location(diagnostic)
    text = f"<b style='color:{colour}'>{html.escape(diagnostic.kind)}</b> "
    if where:
        text += f"<i>[{html.escape(where)}]</i> "
    text += html.escape(diagnostic.message)
    if diagnostic.line:
        quoted = html.escape(diagnostic.line_text) if diagnostic.line_text else _("go to line")
        text += f"<br><a href='line:{diagnostic.line}'><code>{quoted}</code></a>"
    return text


def show_parser_debugger(config: Any, parent: QWidget | None = None) -> ParserDebuggerDialog:
    """Open the Parser Debugger, modeless."""
    dialog = ParserDebuggerDialog(config, parent)
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    dialog.show()
    return dialog
