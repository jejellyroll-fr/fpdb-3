"""Spot-first Study Explorer landing page (#360)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGridLayout,
        QGroupBox,
        QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy.research_studies import StudyRegistry, StudySpec
from fpdb_3_legacy.research_study_explorer import StudyExplorerModel, StudySelection
from fpdb_3_legacy.ring_stats.styles import get_theme_palette


class GuiStudyExplorer(QWidget):
    """Find a poker spot before exposing metrics and engine filters."""

    study_opened = Signal(object)
    advanced_requested = Signal()

    def __init__(
        self,
        config: Any = None,
        querylist: Any = None,
        mainwin: Any = None,
        db: Any = None,
        *,
        registry: StudyRegistry | None = None,
        state_path: str | Path | None = None,
    ) -> None:
        super().__init__()
        self.conf = config
        self.sql = querylist
        self.main_window = mainwin
        self.db = db
        self.model = StudyExplorerModel(registry, state_path)
        self._category_id: str | None = None
        self._selected: StudySpec | None = None
        self.opened_selection: StudySelection | None = None
        self._build_ui()
        self._refresh_categories()
        self._refresh_studies()
        self._refresh_recent()

    def _build_ui(self) -> None:  # noqa: PLR0915 - the landing page is one cohesive widget tree
        colors = get_theme_palette()
        muted = colors.get("muted_text", "#a0aec0")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)

        title = QLabel("Research · Study Explorer")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(title)
        subtitle = QLabel("What do you want to study? Choose a poker spot first; the panels share its population.")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"color: {muted}; font-size: 12px;")
        layout.addWidget(subtitle)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Search studies"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Try: c-bet, 3bet, BB defend, opening range…")
        self.search_edit.textChanged.connect(self._refresh_studies)
        search_row.addWidget(self.search_edit, 1)
        layout.addLayout(search_row)

        context = QGroupBox("Context (applied when you open a study)")
        context_layout = QFormLayout(context)
        self.game_combo = QComboBox()
        self.game_combo.addItem("Any game", None)
        self.game_combo.addItem("Hold'em", "holdem")
        self.game_combo.addItem("Omaha", "omaha")
        self.format_combo = QComboBox()
        self.format_combo.addItem("Any format", None)
        self.format_combo.addItem("Cash games", False)
        self.format_combo.addItem("Tournaments", True)
        self.table_combo = QComboBox()
        self.table_combo.addItem("Any table size", None)
        self.table_combo.addItem("6-max", [6, 6])
        self.subject_combo = QComboBox()
        self.subject_combo.addItem("Any player", None)
        self.subject_combo.addItem("Hero", True)
        self.subject_combo.addItem("Field", False)
        self.player_edit = QLineEdit()
        self.player_edit.setPlaceholderText("Any player name")
        self.stake_min_edit = QLineEdit()
        self.stake_min_edit.setPlaceholderText("min BB")
        self.stake_max_edit = QLineEdit()
        self.stake_max_edit.setPlaceholderText("max BB")
        stake_row = QHBoxLayout()
        stake_row.addWidget(self.stake_min_edit)
        stake_row.addWidget(self.stake_max_edit)
        self.date_from_edit = QLineEdit()
        self.date_from_edit.setPlaceholderText("YYYY-MM-DD")
        self.date_to_edit = QLineEdit()
        self.date_to_edit.setPlaceholderText("YYYY-MM-DD")
        date_row = QHBoxLayout()
        date_row.addWidget(self.date_from_edit)
        date_row.addWidget(self.date_to_edit)
        for label, widget in (
            ("Game", self.game_combo),
            ("Format", self.format_combo),
            ("Table", self.table_combo),
            ("Subject", self.subject_combo),
        ):
            context_layout.addRow(label, widget)
            widget.currentIndexChanged.connect(self._refresh_selection)
        context_layout.addRow("Player", self.player_edit)
        context_layout.addRow("Stake (BB)", stake_row)
        context_layout.addRow("Dates", date_row)
        for widget in (
            self.player_edit,
            self.stake_min_edit,
            self.stake_max_edit,
            self.date_from_edit,
            self.date_to_edit,
        ):
            widget.textChanged.connect(self._refresh_selection)
        layout.addWidget(context)

        self.category_box = QGroupBox("Study spots")
        self.category_grid = QGridLayout(self.category_box)
        layout.addWidget(self.category_box)

        splitter = QSplitter()
        self.study_list = QListWidget()
        self.study_list.setMinimumWidth(310)
        self.study_list.currentItemChanged.connect(self._on_study_changed)
        splitter.addWidget(self.study_list)

        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        self.breadcrumb_label = QLabel("")
        self.breadcrumb_label.setStyleSheet(f"color: {muted}; font-size: 11px;")
        detail_layout.addWidget(self.breadcrumb_label)
        self.study_title = QLabel("Select a spot")
        self.study_title.setWordWrap(True)
        self.study_title.setStyleSheet("font-size: 18px; font-weight: bold;")
        detail_layout.addWidget(self.study_title)
        self.study_description = QLabel("Pick a card or search for a poker situation.")
        self.study_description.setWordWrap(True)
        detail_layout.addWidget(self.study_description)
        self.study_meta = QLabel("")
        self.study_meta.setWordWrap(True)
        self.study_meta.setStyleSheet(f"color: {muted};")
        detail_layout.addWidget(self.study_meta)
        self.availability_label = QLabel("")
        self.availability_label.setWordWrap(True)
        detail_layout.addWidget(self.availability_label)
        detail_layout.addStretch(1)
        actions = QHBoxLayout()
        self.favorite_button = QPushButton("☆ Favorite")
        self.favorite_button.clicked.connect(self._toggle_favorite)
        self.open_button = QPushButton("Open study")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self._open_selected)
        actions.addWidget(self.favorite_button)
        actions.addWidget(self.open_button)
        actions.addStretch(1)
        detail_layout.addLayout(actions)
        splitter.addWidget(detail)
        splitter.setSizes([360, 620])
        layout.addWidget(splitter, 1)

        recent_box = QGroupBox("Recent studies")
        recent_layout = QVBoxLayout(recent_box)
        self.recent_list = QListWidget()
        self.recent_list.setMaximumHeight(100)
        self.recent_list.currentItemChanged.connect(self._on_recent_changed)
        recent_layout.addWidget(self.recent_list)
        layout.addWidget(recent_box)

        self.advanced_button = QPushButton("Custom / Advanced Research")
        self.advanced_button.setToolTip("Open the existing metric/filter query builder.")
        self.advanced_button.clicked.connect(self._open_advanced)
        layout.addWidget(self.advanced_button)

    def _refresh_categories(self) -> None:
        while self.category_grid.count():
            item = self.category_grid.takeAt(0)
            if item is not None and item.widget() is not None:
                item.widget().deleteLater()
        for index, category in enumerate(self.model.categories()):
            button = QPushButton(f"{category.label}\n{category.study_count} studies")
            button.setToolTip(category.description)
            button.setMinimumHeight(54)
            button.clicked.connect(lambda _checked=False, category_id=category.id: self._choose_category(category_id))
            self.category_grid.addWidget(button, index // 3, index % 3)

    def _choose_category(self, category_id: str) -> None:
        self._category_id = category_id
        self._refresh_studies()

    def _refresh_studies(self) -> None:
        selected_id = self._selected.id if self._selected else None
        self.study_list.clear()
        studies = self.model.search(self.search_edit.text(), self._category_id)
        for study in studies:
            item = QListWidgetItem(study.title)
            item.setData(256, study.id)
            item.setToolTip(study.description)
            self.study_list.addItem(item)
        if studies:
            index = next((index for index, study in enumerate(studies) if study.id == selected_id), 0)
            self.study_list.setCurrentRow(index)
        else:
            self._selected = None
            self._render_empty_search()

    def _render_empty_search(self) -> None:
        self.breadcrumb_label.setText("")
        self.study_title.setText("No matching studies")
        self.study_description.setText("Try a poker term such as c-bet, 3bet, BB defend or opening range.")
        self.study_meta.setText("")
        self.availability_label.setText("")
        self.open_button.setEnabled(False)

    def _on_study_changed(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is None:
            self._selected = None
            self._render_empty_search()
            return
        self._selected = self.model.registry.get(str(current.data(256)))
        self._render_selected()

    def _context_filters(self) -> dict[str, Any]:
        stake_min = self._number_or_none(self.stake_min_edit.text())
        stake_max = self._number_or_none(self.stake_max_edit.text())
        stake = [stake_min, stake_max] if stake_min is not None or stake_max is not None else None
        return {
            "game": self.game_combo.currentData(),
            "tournament": self.format_combo.currentData(),
            "max_seats": self.table_combo.currentData(),
            "hero": self.subject_combo.currentData(),
            "player": self.player_edit.text().strip() or None,
            "stake_bb": stake,
            "date_from": self.date_from_edit.text().strip() or None,
            "date_to": self.date_to_edit.text().strip() or None,
        }

    @staticmethod
    def _number_or_none(value: str) -> float | None:
        try:
            return float(value.strip()) if value.strip() else None
        except ValueError:
            return None

    def _preview_selection(self) -> StudySelection | None:
        if self._selected is None:
            return None
        return self.model.open_study(
            self._selected.id,
            context_filters=self._context_filters(),
            remember=False,
        )

    def _refresh_selection(self) -> None:
        if self._selected is not None:
            self._render_selected()

    def _render_selected(self) -> None:
        if self._selected is None:
            self._render_empty_search()
            return
        study = self._selected
        selection = self._preview_selection()
        self.breadcrumb_label.setText("  ›  ".join(self.model.breadcrumbs(study)))
        self.study_title.setText(study.title)
        self.study_description.setText(study.description)
        panel_names = ", ".join(panel.title for panel in study.panels[:5])
        if len(study.panels) > 5:
            panel_names += f" and {len(study.panels) - 5} more"
        self.study_meta.setText(
            f"{study.min_sample or 'No'} decision minimum · {len(study.panels)} panels\n"
            f"{panel_names}\n"
            f"Tags: {', '.join(study.tags)}",
        )
        if selection is not None and not selection.available:
            self.availability_label.setText(f"Unavailable: {selection.unavailable_reason}")
            self.availability_label.setStyleSheet("color: #e06c75; font-weight: bold;")
            self.open_button.setEnabled(False)
        else:
            self.availability_label.setText("Ready. The selected context will be inherited by every panel.")
            self.availability_label.setStyleSheet("color: #98c379;")
            self.open_button.setEnabled(True)
        self.favorite_button.setText("★ Favorite" if self.model.is_favorite(study.id) else "☆ Favorite")

    def _open_selected(self) -> None:
        if self._selected is None:
            return
        selection = self.model.open_study(self._selected.id, context_filters=self._context_filters())
        if not selection.available:
            self._render_selected()
            return
        self.opened_selection = selection
        self.study_opened.emit(selection)
        self._refresh_recent()
        self.availability_label.setText(
            f"Opened: {'  ›  '.join(self.model.breadcrumbs(self._selected))}. "
            "The study dashboard can now consume this selection.",
        )

    def _toggle_favorite(self) -> None:
        if self._selected is not None:
            self.model.toggle_favorite(self._selected.id)
            self._render_selected()

    def _refresh_recent(self) -> None:
        self.recent_list.clear()
        for study in self.model.recent_studies():
            item = QListWidgetItem(study.title)
            item.setData(256, study.id)
            self.recent_list.addItem(item)

    def _on_recent_changed(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is None:
            return
        study_id = str(current.data(256))
        for row in range(self.study_list.count()):
            if self.study_list.item(row).data(256) == study_id:
                self.study_list.setCurrentRow(row)
                return
        self._category_id = None
        self.search_edit.clear()
        self._refresh_studies()
        for row in range(self.study_list.count()):
            if self.study_list.item(row).data(256) == study_id:
                self.study_list.setCurrentRow(row)
                return

    def _open_advanced(self) -> None:
        self.advanced_requested.emit()
        if self.main_window is not None and hasattr(self.main_window, "tab_research_browser"):
            self.main_window.tab_research_browser(None)


__all__ = ["GuiStudyExplorer"]
