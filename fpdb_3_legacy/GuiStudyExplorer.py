"""Spot-first Study Explorer landing page (#360)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy.research_studies import StudyRegistry, StudySpec
from fpdb_3_legacy.research_study_explorer import StudyExplorerModel, StudySelection
from fpdb_3_legacy.responsive_layout import (
    CollapsibleSection,
    PaneSwitcher,
    ReflowGrid,
    ResponsiveSplitter,
    cap_context_block,
    column_count,
    labelled_field,
    wrap_in_scroll,
)
from fpdb_3_legacy.ring_stats.styles import get_theme_palette

#: Width below which the study list and its detail pane stop fitting side by
#: side and are stacked instead. Measured from the two panes' own minimums with
#: the production theme, plus room for the splitter handle.
STACK_BELOW_WIDTH = 900

#: The page's own left and right margins, which the splitter does not get.
PAGE_MARGIN = 16

#: The window width below which the splitter's two panes no longer fit side by
#: side. Derived from the splitter's own threshold so the two cannot drift, and
#: measured on the window rather than read from the splitter: while the context
#: block is the zone on screen the splitter is hidden, and a widget the layout
#: skips keeps the width -- and so the orientation -- it had before it was.
STACK_BELOW_WINDOW_WIDTH = STACK_BELOW_WIDTH + 2 * PAGE_MARGIN

#: The heights the page's zones want in order to be read at the same time,
#: measured from their own content with the production theme: the context block
#: asks for 357 px, and the studies pane for 213 -- one region for the two panes
#: that sit side by side, so the taller of the list and the detail, not their
#: sum. Below their total the page shows one zone at a time, because a share of
#: a short window is a context form of three rows.
ZONE_HEIGHTS: Final[tuple[int, int]] = (357, 213)

#: The zone the bar opens on: the studies, not the context block. The reader
#: came for the studies; the block above is how they are narrowed.
DEFAULT_ZONE = 1

#: What the page spends outside the zones: the bar, the layout's margins and the
#: two entry-point buttons pinned at the bottom.
ZONE_CHROME_HEIGHT = 31 + 28 + 40

#: Measured on the window, because the context block is a zone of its own and
#: the page is what decides.
SWITCH_BELOW_HEIGHT = sum(ZONE_HEIGHTS) + ZONE_CHROME_HEIGHT

#: ``(minimum width, columns)`` for the spot cards. Three cards across is the
#: layout the page was designed for; below that the labels wrap badly.
CATEGORY_BREAKPOINTS = ((1080, 3), (720, 2))

#: ``(minimum width, columns)`` for the four context fields, and for the
#: advanced fields folded under "More filters".
CONTEXT_BREAKPOINTS = ((1000, 4), (700, 2))
ADVANCED_BREAKPOINTS = ((1000, 3), (680, 2))


class GuiStudyExplorer(QWidget):
    """Find a poker spot before exposing metrics and engine filters."""

    study_opened = Signal(object)
    differences_requested = Signal()
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
        self._refresh_advanced_summary()

    def _build_ui(self) -> None:
        colors = get_theme_palette()
        muted = colors.get("muted_text", "#a0aec0")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(PAGE_MARGIN, 14, PAGE_MARGIN, 14)

        # The page is two blocks: what the reader is looking for, and the
        # studies themselves. Only the second one grows, and the first is a zone
        # of its own in the bar below. The first one scrolls, because seven
        # context rows stacked above the spot grid asked for more height than a
        # laptop screen has and pushed the study list -- the reason the page
        # exists -- below the fold.
        upper = QWidget()
        upper_layout = QVBoxLayout(upper)
        upper_layout.setContentsMargins(0, 0, 0, 0)
        self._build_header(upper_layout, muted)
        upper_layout.addWidget(self._build_context_box(muted))
        upper_layout.addWidget(self._build_categories_box())
        upper_layout.addWidget(self._build_recent_box())
        self.upper_area = wrap_in_scroll(upper)
        layout.addWidget(self.upper_area)

        self.splitter = self._build_studies_splitter(muted)
        self.splitter.set_narrow_below(STACK_BELOW_WIDTH)
        self.splitter.set_narrow_sizes([220, 380])
        # One bar for the page, not one per region. The context block is a zone
        # like the studies are: on a window too short for both, a reader wants to
        # choose between them rather than have a slice of each, and the studies
        # then get the height that the context form was taking. It stays hidden
        # while the whole page fits, where the splitter is the better tool.
        # ``sizes`` is the splitter's own arrangement -- the studies and their
        # detail -- not one entry per zone; the block above is not its child.
        self.pane_switcher = PaneSwitcher(
            self,
            self.splitter,
            [self.upper_area, self.study_list, self.study_detail],
            ("Filters", "Studies", "Detail"),
            sizes=(360, 620),
        )
        self.pane_switcher.set_active(DEFAULT_ZONE)
        layout.addWidget(self.pane_switcher.bar)
        layout.addWidget(self.splitter, 1)

        # The two alternative entry points are pinned to the bottom: they were
        # the first controls pushed out of view when the page ran out of room,
        # and they lead to the same research as the list above.
        footer = QHBoxLayout()
        self.advanced_button = QPushButton("Custom / Advanced Research")
        self.advanced_button.setToolTip("Open the existing metric/filter query builder.")
        self.advanced_button.clicked.connect(self._open_advanced)
        self.differences_button = QPushButton("Biggest Differences vs Field")
        self.differences_button.setToolTip(
            "Rank observed Hero-versus-Field frequency gaps and open the matching study."
        )
        self.differences_button.clicked.connect(self._open_differences)
        footer.addWidget(self.advanced_button)
        footer.addWidget(self.differences_button)
        footer.addStretch(1)
        layout.addLayout(footer)

        # Place the fields once before the first resize event: ``set_items``
        # only records them, and a widget that is never shown would otherwise
        # keep an empty grid.
        self._reflow(self.width())

    def showEvent(self, event) -> None:  # noqa: ANN001 - Qt signature
        super().showEvent(event)
        self._reflow(self.width())
        # A window that opens short is put into its one-zone-at-a-time shape
        # here: the switcher hides nothing while the widget is off screen.
        self._sync_zones()

    def _sync_zones(self) -> None:
        """One zone at a time when the window is short, or the panes no longer fit.

        Either condition is enough. The list and the detail stop being readable
        side by side long before the window is short, and the context block is
        taller than what is left once the splitter has taken its share.

        Both are read from the page rather than from the splitter. While the
        context block is the zone on screen the splitter is hidden, and a widget
        the layout skips keeps the width, and so the orientation, it had before
        it was hidden -- which would hold the page in one-zone mode on a window
        that has since grown wide enough for both panes again.
        """
        switching = self.width() < STACK_BELOW_WINDOW_WIDTH or self.height() < SWITCH_BELOW_HEIGHT
        self.pane_switcher.set_switching(switching)
        cap_context_block(self.upper_area, self, capped=not switching)

    def _reveal_detail(self, _item: QListWidgetItem) -> None:
        """Show the detail of the study the reader just picked.

        Driven by ``itemClicked`` and ``itemActivated`` rather than by
        ``currentItemChanged``: the page selects a row itself every time the list
        is rebuilt -- on a search, a category, a game change -- and the detail
        would then take the screen without anyone having asked for it. Arrow-key
        browsing stays on the list for the same reason: scanning is not choosing.
        """
        self.pane_switcher.set_active(2)

    def _build_header(self, upper_layout: QVBoxLayout, muted: str) -> None:
        title = QLabel("Research · Study Explorer")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        upper_layout.addWidget(title)
        subtitle = QLabel("What do you want to study? Choose a poker spot first; the panels share its population.")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"color: {muted}; font-size: 12px;")
        upper_layout.addWidget(subtitle)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Search studies"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Try: c-bet, 3bet, BB defend, opening range…")
        self.search_edit.textChanged.connect(self._refresh_studies)
        search_row.addWidget(self.search_edit, 1)
        upper_layout.addLayout(search_row)

    def _build_context_box(self, muted: str) -> QGroupBox:
        context = QGroupBox("Context (applied when you open a study)")
        context_layout = QVBoxLayout(context)

        self.game_combo = QComboBox()
        # The entries come from the shipped studies themselves, keyed by the
        # game token the database stores. The old list offered "Omaha" as
        # ``omaha``, which is not a category any hand carries, so the filter
        # could only ever match nothing (#368).
        self.game_combo.addItem("Any game", None)
        for game in self.model.games():
            self.game_combo.addItem(f"{game.label} ({game.study_count})", game.id)
        self.format_combo = QComboBox()
        # Cash and tournament are different libraries, not one library with a
        # filter: a tournament hand is played at a depth a cash study never
        # sees, so the format decides which studies exist (#369).
        self.format_combo.addItem("Any format", None)
        for study_format in self.model.formats():
            self.format_combo.addItem(
                f"{study_format.label} ({study_format.study_count})", study_format.tournament,
            )
        self.table_combo = QComboBox()
        self.table_combo.addItem("Any table size", None)
        self.table_combo.addItem("6-max", [6, 6])
        self.subject_combo = QComboBox()
        self.subject_combo.addItem("Any player", None)
        self.subject_combo.addItem("Hero", True)
        self.subject_combo.addItem("Field", False)

        # The four fields that decide what the page shows, on one reflowing row
        # instead of four stacked form rows: a form row per field is what made
        # the context taller than the content it filters.
        self.context_grid = ReflowGrid()
        self.context_grid.set_items(
            [
                labelled_field("Game", self.game_combo, muted),
                labelled_field("Format", self.format_combo, muted),
                labelled_field("Table", self.table_combo, muted),
                labelled_field("Subject", self.subject_combo, muted),
            ],
        )
        for widget in (self.game_combo, self.format_combo, self.table_combo, self.subject_combo):
            widget.currentIndexChanged.connect(self._refresh_selection)
        # Neither the game nor the format is only context for the study that
        # opens: each decides which studies exist at all, so both redraw the
        # spots and the list.
        self.game_combo.currentIndexChanged.connect(self._scope_changed)
        self.format_combo.currentIndexChanged.connect(self._scope_changed)
        context_layout.addLayout(self.context_grid)

        # Player, stakes and dates narrow the population but are not the choice
        # the page is about. Folding them keeps the four fields above -- and the
        # spot cards below -- on screen, while the summary in the folded header
        # still says when one of them is set.
        self.advanced_fields = CollapsibleSection(
            "More filters",
            expanded=False,
            tooltip="Narrow the population by player, stake and dates.",
        )
        self.player_edit = QLineEdit()
        self.player_edit.setPlaceholderText("Any player name")
        self.stake_min_edit = QLineEdit()
        self.stake_min_edit.setPlaceholderText("min BB")
        self.stake_max_edit = QLineEdit()
        self.stake_max_edit.setPlaceholderText("max BB")
        stake_row = QWidget()
        stake_layout = QHBoxLayout(stake_row)
        stake_layout.setContentsMargins(0, 0, 0, 0)
        stake_layout.addWidget(self.stake_min_edit)
        stake_layout.addWidget(self.stake_max_edit)
        self.date_from_edit = QLineEdit()
        self.date_from_edit.setPlaceholderText("YYYY-MM-DD")
        self.date_to_edit = QLineEdit()
        self.date_to_edit.setPlaceholderText("YYYY-MM-DD")
        date_row = QWidget()
        date_layout = QHBoxLayout(date_row)
        date_layout.setContentsMargins(0, 0, 0, 0)
        date_layout.addWidget(self.date_from_edit)
        date_layout.addWidget(self.date_to_edit)

        self.advanced_grid = ReflowGrid()
        self.advanced_grid.set_items(
            [
                labelled_field("Player", self.player_edit, muted),
                labelled_field("Stake (BB)", stake_row, muted),
                labelled_field("Dates", date_row, muted),
            ],
        )
        advanced_layout = QVBoxLayout(self.advanced_fields.body())
        advanced_layout.setContentsMargins(0, 0, 0, 0)
        advanced_layout.addLayout(self.advanced_grid)
        context_layout.addWidget(self.advanced_fields)

        for widget in (
            self.player_edit,
            self.stake_min_edit,
            self.stake_max_edit,
            self.date_from_edit,
            self.date_to_edit,
        ):
            widget.textChanged.connect(self._refresh_selection)
            widget.textChanged.connect(self._refresh_advanced_summary)
        return context

    def _build_categories_box(self) -> QGroupBox:
        self.category_box = QGroupBox("Study spots")
        category_layout = QVBoxLayout(self.category_box)
        self.category_grid = ReflowGrid()
        category_layout.addLayout(self.category_grid)
        return self.category_box

    def _build_recent_box(self) -> QGroupBox:
        recent_box = QGroupBox("Recent studies")
        recent_layout = QVBoxLayout(recent_box)
        self.recent_list = QListWidget()
        self.recent_list.setMaximumHeight(100)
        self.recent_list.currentItemChanged.connect(self._on_recent_changed)
        recent_layout.addWidget(self.recent_list)
        return recent_box

    def _build_studies_splitter(self, muted: str) -> ResponsiveSplitter:
        splitter = ResponsiveSplitter()
        self.study_list = QListWidget()
        # Narrow enough to share a laptop width with the detail pane; the pane
        # is stacked below this list before the titles stop being readable.
        self.study_list.setMinimumWidth(240)
        self.study_list.currentItemChanged.connect(self._on_study_changed)
        # Picking a study is what the detail pane answers, so a click or an
        # Enter brings it on screen; see ``_reveal_detail`` for why the
        # selection signal itself is not the trigger.
        self.study_list.itemClicked.connect(self._reveal_detail)
        self.study_list.itemActivated.connect(self._reveal_detail)
        splitter.addWidget(self.study_list)

        detail = QWidget()
        self.study_detail = detail
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
        return splitter

    def resizeEvent(self, event) -> None:  # noqa: ANN001 - Qt signature
        """Reflow the grids for the new width, and follow the new shape."""
        super().resizeEvent(event)
        self._reflow(event.size().width())
        # The page's own size decides both questions -- whether the panes still
        # fit and whether the window is short -- so this covers the arrangement
        # already in force, and is a no-op when nothing changed.
        self._sync_zones()

    def _reflow(self, width: int) -> None:
        """Lay the fields out in as many columns as ``width`` can hold."""
        self.context_grid.reflow(column_count(width, CONTEXT_BREAKPOINTS))
        self.advanced_grid.reflow(column_count(width, ADVANCED_BREAKPOINTS))
        if self.category_grid.items():
            self.category_grid.reflow(column_count(width, CATEGORY_BREAKPOINTS))

    def _refresh_advanced_summary(self) -> None:
        """Say what the folded "More filters" section currently holds."""
        parts = []
        if self.player_edit.text().strip():
            parts.append(f"player {self.player_edit.text().strip()}")
        low = self.stake_min_edit.text().strip()
        high = self.stake_max_edit.text().strip()
        if low or high:
            parts.append(f"stake {low or '…'}-{high or '…'} BB")
        start = self.date_from_edit.text().strip()
        end = self.date_to_edit.text().strip()
        if start or end:
            parts.append(f"dates {start or '…'} to {end or '…'}")
        self.advanced_fields.set_summary(" · ".join(parts) if parts else "none set")

    def _refresh_categories(self) -> None:
        # Reparent before deleting: ``deleteLater`` alone leaves the old buttons
        # as children of the box until the event loop runs, and a lookup for the
        # spot cards would then find every generation of them.
        for stale in self.category_grid.items():
            stale.setParent(None)
            stale.deleteLater()
        buttons: list[QWidget] = []
        for category in self.model.categories(self._game(), self._tournament()):
            button = QPushButton(f"{category.label}\n{category.study_count} studies")
            button.setToolTip(category.description)
            button.setMinimumHeight(54)
            button.setEnabled(category.study_count > 0)
            if not category.study_count:
                button.setToolTip(f"{category.description}\nNo study covers this spot for the chosen game.")
            button.clicked.connect(lambda _checked=False, category_id=category.id: self._choose_category(category_id))
            buttons.append(button)
        self.category_grid.set_items(buttons)
        self.category_grid.reflow(column_count(self.width(), CATEGORY_BREAKPOINTS))

    def _game(self) -> str | None:
        """The game currently chosen, or ``None`` for every game."""
        return self.game_combo.currentData()

    def _tournament(self) -> bool | None:
        """The format currently chosen, or ``None`` for both."""
        return self.format_combo.currentData()

    def _scope_changed(self) -> None:
        """A different game or format: different spots, different studies."""
        if self._category_id is not None and not self.model.studies_for_category(
            self._category_id, self._game(), self._tournament(),
        ):
            self._category_id = None
        self._refresh_categories()
        self._refresh_studies()

    def _choose_category(self, category_id: str) -> None:
        self._category_id = category_id
        self._refresh_studies()

    def _refresh_studies(self) -> None:
        selected_id = self._selected.id if self._selected else None
        self.study_list.clear()
        studies = self.model.search(
            self.search_edit.text(), self._category_id, self._game(), self._tournament(),
        )
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

    def _open_differences(self) -> None:
        self.differences_requested.emit()


__all__ = ["GuiStudyExplorer"]
