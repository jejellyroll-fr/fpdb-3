#!/usr/bin/env python
from __future__ import annotations

from functools import partial
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy import Configuration, dynamic_panels_consent
from fpdb_3_legacy.hud_profiles import HudContext, HudProfileResolver, HudProfileRule
from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.i18n import translate_hud_category
from fpdb_3_legacy.loggingFpdb import get_logger
from fpdb_3_legacy.modern_hud_preferences import (
    editor_state,
    layout_model,
    presentation,
    profile_io,
    stat_catalog,
    stat_edit,
    undo,
)
from fpdb_3_legacy.modern_hud_preferences.design_canvas import HudDesignCanvas
from fpdb_3_legacy.modern_hud_preferences.dialogs import (
    AddStatDialog,
    BlockPropertiesDialog,
    LayoutSelectionDialog,
    PopupStatEditDialog,
)
from fpdb_3_legacy.modern_hud_preferences.preview_widgets import (
    HudPreviewWidget,
    PopupPreviewWidget,
    PopupZoomDialog,
)
from fpdb_3_legacy.modern_hud_preferences.stat_catalog_widget import (
    PopupChoiceCombo,
    StatCatalogWidget,
    StatChoiceCombo,
)
from fpdb_3_legacy.PopupIcons import AVAILABLE_PROVIDERS
from fpdb_3_legacy.PopupThemes import AVAILABLE_THEMES
from fpdb_3_legacy.responsive_layout import (
    CollapsibleSection,
    ReflowGrid,
    column_count,
    fit_window,
    labelled_field,
    wrap_in_scroll,
)

log = get_logger("modern_hud_preferences.main_dialog")

#: ``(minimum width, columns)`` for the Dynamic Panels field grids. Four across
#: is the layout the tab was designed for; three once a caption would start to
#: wrap, two once two combos side by side stop being readable, and a single
#: column at the end so no selector is ever squeezed out of view.
PANEL_FIELD_BREAKPOINTS = ((1000, 4), (840, 3), (600, 2))

#: Width below which the six profile buttons of the header give way to a single
#: menu. The six buttons and the profile combo are what set the dialog's
#: minimum width, at 986 px with the macOS fonts, so the swap has to happen
#: above that or the window could never be narrowed to the width that needs
#: it. It stays below 1024 so a 1024-wide window still shows the buttons.
NARROW_HEADER_WIDTH = 1010


def confirm_dynamic_panels(parent: QWidget | None, path: Any) -> bool:
    """Ask before dynamic panels are turned on (#647); record and return a yes."""
    if dynamic_panels_consent.is_confirmed(path):
        return True
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(_("Turn on dynamic panels?"))
    box.setText(_(dynamic_panels_consent.DYNAMIC_PANELS.title))
    box.setInformativeText(dynamic_panels_consent.statement())
    turn_on = box.addButton(_("I understand, turn them on"), QMessageBox.ButtonRole.AcceptRole)
    box.addButton(QMessageBox.StandardButton.Cancel)
    box.setDefaultButton(QMessageBox.StandardButton.Cancel)
    box.exec()
    if box.clickedButton() is not turn_on:
        return False
    dynamic_panels_consent.confirm(path)
    return True


class ModernHudPreferences(QDialog):
    #: The selected item of the current profile, by identity (B11). The Design
    #: canvas shows it; nothing else holds the selection.
    _selected_item: dict | None = None

    def __init__(self, config, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.setWindowTitle(_("HUD Preferences"))
        # The size is applied at the end of __init__, once the content is known;
        # see the ``fit_window`` call there.

        # Main layout with better spacing
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Header section with profile management
        header_frame = QFrame()
        header_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        header_layout = QVBoxLayout(header_frame)
        header_layout.setContentsMargins(15, 15, 15, 15)

        # Title
        header_title = QLabel(_("HUD Profile Configuration"))
        header_title.setProperty("class", "h1")
        header_layout.addWidget(header_title)

        # Profile management bar
        profile_bar = QHBoxLayout()
        profile_bar.setSpacing(10)

        profile_label = QLabel(_("Active Profile:"))
        profile_label.setProperty("class", "subtitle")
        profile_bar.addWidget(profile_label)

        self.profile_combo = QComboBox()
        # Wide enough to read a profile name, small enough that the six action
        # buttons beside it still fit a 1024-wide window. The buttons below take
        # their natural width instead of a 120 px floor each: five floors were
        # the single largest contributor to the dialog's minimum width.
        self.profile_combo.setMinimumWidth(180)
        # Let qt_material manage the style
        self.profile_combo.currentIndexChanged.connect(self.on_profile_selected)
        profile_bar.addWidget(self.profile_combo)

        # Push the action buttons to the right so a short profile name doesn't
        # leave them crowding the combo.
        profile_bar.addStretch()

        # Profile action buttons with better styling
        self.add_profile_btn = QPushButton(_("➕ New Profile"))
        self.add_profile_btn.clicked.connect(self.add_profile)

        self.dup_profile_btn = QPushButton(_("📋 Duplicate"))
        self.dup_profile_btn.clicked.connect(self.duplicate_profile)

        self.rename_profile_btn = QPushButton(_("✏️ Rename"))
        self.rename_profile_btn.clicked.connect(self.rename_profile)

        self.del_profile_btn = QPushButton(_("🗑️ Delete"))
        self.del_profile_btn.clicked.connect(self.delete_profile)

        self.export_profile_btn = QPushButton(_("📤 Export HUD"))
        self.export_profile_btn.clicked.connect(self.export_profile)

        self.import_profile_btn = QPushButton(_("📥 Import HUD"))
        self.import_profile_btn.clicked.connect(self.import_profile)

        profile_bar.addWidget(self.add_profile_btn)
        profile_bar.addWidget(self.dup_profile_btn)
        profile_bar.addWidget(self.rename_profile_btn)
        profile_bar.addWidget(self.del_profile_btn)
        profile_bar.addWidget(self.export_profile_btn)
        profile_bar.addWidget(self.import_profile_btn)

        # The same six actions behind one button, for a window too narrow to
        # hold them. Six buttons are what set the dialog's minimum width at
        # 986 px, so a reader who wants the preferences beside their table could
        # not narrow the window. ``_fit_profile_actions`` swaps between the two
        # as the width changes.
        self.profile_actions_btn = QToolButton()
        self.profile_actions_btn.setText(_("Profile actions"))
        self.profile_actions_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.profile_actions_menu = QMenu(self.profile_actions_btn)
        for button in self._profile_action_buttons():
            action = self.profile_actions_menu.addAction(button.text())
            action.triggered.connect(lambda _checked=False, source=button: source.click())
        self.profile_actions_btn.setMenu(self.profile_actions_menu)
        self.profile_actions_btn.setVisible(False)
        profile_bar.addWidget(self.profile_actions_btn)

        header_layout.addLayout(profile_bar)

        # Second row: per-profile HUD display options, kept off the (already
        # crowded) profile/buttons row so they never overlap it.
        hud_options_bar = QHBoxLayout()
        hud_options_bar.setSpacing(10)

        # Positional-panel mode for multi-block HUDs. "current" shows the panel
        # matching the estimated live position; "all" is an explicit diagnostic
        # or preference that stacks SB/BB/BU together.
        self.positional_mode_label = QLabel(_("Positional panels:"))
        self.positional_mode_label.setProperty("class", "subtitle")
        hud_options_bar.addWidget(self.positional_mode_label)
        self.positional_mode_combo = QComboBox()
        self.positional_mode_combo.addItem(_("Only current position"), "current")
        self.positional_mode_combo.addItem(_("Show all (stacked)"), "all")
        self.positional_mode_combo.setMinimumWidth(180)
        self.positional_mode_combo.currentIndexChanged.connect(self._on_positional_mode_changed)
        hud_options_bar.addWidget(self.positional_mode_combo)

        hud_options_bar.addSpacing(24)

        # Whether the hero's own stat windows are drawn (multi-block HUDs are
        # usually hero-hidden; this exposes the toggle per profile).
        self.show_hero_checkbox = QCheckBox(_("Show hero HUD"))
        self.show_hero_checkbox.toggled.connect(self._on_show_hero_changed)
        hud_options_bar.addWidget(self.show_hero_checkbox)

        hud_options_bar.addStretch()
        header_layout.addLayout(hud_options_bar)

        main_layout.addWidget(header_frame)

        # Main content area with tabs
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)

        # Tab 1: Statistics Configuration
        stats_tab = QWidget()
        stats_layout = QHBoxLayout(stats_tab)
        stats_layout.setContentsMargins(0, 10, 0, 0)

        # Three panes, as in a design tool (#780): what can go on the HUD on
        # the left, the panel being edited and the HUD as drawn in the middle,
        # the selection's properties on the right.
        stats_splitter = QSplitter(Qt.Orientation.Horizontal)
        stats_splitter.setHandleWidth(8)
        stats_splitter.setChildrenCollapsible(False)
        self.stats_splitter = stats_splitter

        self._loading_group = False
        self._current_block_index = 0
        # The one selected item (B11), by identity: the canvas marks it.
        self._selected_item = None
        # Renamed profiles: current name -> name of its <ss> in the file.
        self._renamed: editor_state.Renames = {}
        self._loading_item = False

        # --- Sources: the profile's panels and the stat catalogue ---------------
        sources = QFrame()
        sources.setFrameStyle(QFrame.Shape.StyledPanel)
        sources_layout = QVBoxLayout(sources)
        sources_layout.setContentsMargins(10, 10, 10, 10)
        sources_layout.setSpacing(8)
        glh = QHBoxLayout()
        glabel = QLabel(_("Panels"))
        glabel.setProperty("class", "h2")
        glh.addWidget(glabel)
        glh.addStretch()
        self.group_new_btn = QPushButton(_("New"))
        self.group_new_btn.setFixedHeight(26)
        self.group_new_btn.clicked.connect(self._group_new)
        self.group_del_btn = QPushButton(_("Delete"))
        self.group_del_btn.setFixedHeight(26)
        self.group_del_btn.clicked.connect(self._group_delete)
        glh.addWidget(self.group_new_btn)
        glh.addWidget(self.group_del_btn)
        sources_layout.addLayout(glh)
        self.group_list = QListWidget()
        self.group_list.setMinimumHeight(60)
        self.group_list.setMaximumHeight(120)
        self.group_list.currentRowChanged.connect(self._on_group_selected)
        sources_layout.addWidget(self.group_list)
        ilabel = QLabel(_("Available Stats"))
        ilabel.setProperty("class", "h2")
        sources_layout.addWidget(ilabel)
        # Double-click or Enter adds a stat to the first free cell of the panel
        # shown in Design; a drag drops it on the cell under the pointer.
        self.stat_catalog_widget = StatCatalogWidget(self._stat_catalog())
        self.stat_catalog_widget.setMinimumWidth(180)
        self.stat_catalog_widget.setMinimumHeight(100)
        self.stat_catalog_widget.setToolTip(_("Double-click a stat to add it to the panel shown in Design."))
        self.stat_catalog_widget.stat_activated.connect(self._add_catalog_stat)
        # The pane is narrow: the stat names get its width, and each
        # description stays in the stat's tooltip.
        self.stat_catalog_widget.tree.setColumnHidden(1, True)
        sources_layout.addWidget(self.stat_catalog_widget, 1)
        sources.setMinimumWidth(190)
        stats_splitter.addWidget(sources)

        # --- Work surface: the panel shown in Design, then the HUD as drawn ------
        design_pane = QWidget()
        design_layout = QVBoxLayout(design_pane)
        design_layout.setContentsMargins(10, 10, 10, 6)
        design_layout.setSpacing(6)
        # PT4-style design canvas: shows the SELECTED panel only (box-by-box).
        self.design_label = QLabel(_("Design"))
        self.design_label.setProperty("class", "h2")
        design_header = QHBoxLayout()
        design_header.setContentsMargins(0, 0, 0, 0)
        design_header.addWidget(self.design_label)
        design_header.addStretch()
        # The grid of the panel shown below, and the history of the profile (#775).
        self.add_row_btn = QPushButton(_("+ Row"))
        self.add_row_btn.setToolTip(_("Add an empty row at the bottom of the panel"))
        self.add_row_btn.clicked.connect(lambda: self._canvas_grid_edit("insert_row", -1))
        self.add_col_btn = QPushButton(_("+ Column"))
        self.add_col_btn.setToolTip(_("Add an empty column on the right of the panel"))
        self.add_col_btn.clicked.connect(lambda: self._canvas_grid_edit("insert_col", -1))
        self.undo_btn = QPushButton(_("Undo"))
        self.undo_btn.setToolTip(_("Undo the last change to this profile (Ctrl+Z)"))
        self.undo_btn.clicked.connect(self.undo_edit)
        self.redo_btn = QPushButton(_("Redo"))
        self.redo_btn.setToolTip(_("Redo the change just undone (Ctrl+Shift+Z)"))
        self.redo_btn.clicked.connect(self.redo_edit)
        for button in (self.add_row_btn, self.add_col_btn, self.undo_btn, self.redo_btn):
            button.setFixedHeight(26)
            design_header.addWidget(button)
        design_layout.addLayout(design_header)

        # What to do with the panel: add an item, edit or remove the selected
        # one, grow the grid. Adding is one menu, so the row stays narrow.
        self.add_item_btn = QToolButton()
        self.add_item_btn.setText(_("Add"))
        self.add_item_btn.setToolTip(_("Add a stat, a text label, a separator line or a panel"))
        self.add_item_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.add_item_btn.setFixedHeight(26)
        self.add_item_btn.setMinimumWidth(72)
        add_menu = QMenu(self.add_item_btn)
        self.add_stat_action = add_menu.addAction(_("Statistic…"), self.add_stat)
        self.add_label_action = add_menu.addAction(_("Text label…"), self.add_text_label)
        self.add_label_action.setToolTip(_("Add a text label (column/row header or caption) to a panel"))
        self.add_hline_action = add_menu.addAction(_("Separator line"), self.add_hline)
        self.add_hline_action.setToolTip(_("Add a horizontal separator line (PT4 'Horz Line') to a panel"))
        add_menu.addSeparator()
        self.add_block_action = add_menu.addAction(_("Panel…"), self.add_block)
        self.add_block_action.setToolTip(_("Add a new panel (block) to a multi-panel HUD"))
        add_menu.setToolTipsVisible(True)
        self.add_item_btn.setMenu(add_menu)
        self.edit_stat_btn = QPushButton(_("Edit"))
        self.edit_stat_btn.setFixedHeight(26)
        self.edit_stat_btn.clicked.connect(self.edit_stat)

        self.remove_stat_btn = QPushButton(_("Remove"))
        self.remove_stat_btn.setFixedHeight(26)
        self.remove_stat_btn.clicked.connect(self.remove_stat)
        self.block_props_btn = QPushButton(_("Block Props"))
        self.block_props_btn.setFixedHeight(26)
        self.block_props_btn.setToolTip(_("Edit the selected panel's title/border colours, position and label"))
        self.block_props_btn.clicked.connect(self.edit_block_properties)
        design_actions = QHBoxLayout()
        design_actions.setContentsMargins(0, 0, 0, 0)
        design_actions.addWidget(self.add_item_btn)
        for button in (self.edit_stat_btn, self.remove_stat_btn):
            design_actions.addWidget(button)
        design_actions.addStretch()
        design_actions.addWidget(self.block_props_btn)
        design_layout.addLayout(design_actions)
        self.design_hint = QLabel(
            _(
                "Drag an item to move it, onto another to swap them. Drop a stat from Available Stats "
                "on an empty cell. Arrows select, Alt+arrows move, Delete removes; right-click a cell "
                "for rows and columns."
            )
        )
        self.design_hint.setWordWrap(True)
        self.design_hint.setProperty("class", "caption")
        design_layout.addWidget(self.design_hint)
        self.design_scroll = QScrollArea()
        self.design_scroll.setWidgetResizable(True)
        self.design_scroll.setMinimumHeight(110)
        self.design_scroll.setStyleSheet("QScrollArea{border:1px solid #2c3e46;background:#1d282e;}")
        self._design_host = QWidget()
        self._design_host.setStyleSheet("background:#1d282e;")
        self._design_layout = QVBoxLayout(self._design_host)
        self._design_layout.setContentsMargins(6, 6, 6, 6)
        self._design_layout.setSpacing(10)
        self.design_scroll.setWidget(self._design_host)
        design_layout.addWidget(self.design_scroll, 1)
        self._design_canvases: list = []

        # The HUD as the table draws it, right under the panel being edited.
        preview_pane = QWidget()
        preview_layout = QVBoxLayout(preview_pane)
        preview_layout.setContentsMargins(10, 6, 10, 10)
        preview_layout.setSpacing(6)
        preview_label = QLabel(_("HUD Preview"))
        preview_label.setProperty("class", "h2")
        preview_layout.addWidget(preview_label)
        # In a scroll area so a large HUD (many stats/columns) scrolls instead
        # of overflowing the strip.
        self.preview = HudPreviewWidget()
        self.preview.content_floor = (160, 60)
        self.preview.setMinimumSize(160, 60)
        preview_scroll = QScrollArea()
        preview_scroll.setWidgetResizable(True)
        preview_scroll.setFrameShape(QFrame.Shape.NoFrame)
        preview_scroll.setWidget(self.preview)
        preview_layout.addWidget(preview_scroll, 1)
        # What the preview is, on its title rather than in a caption that
        # would take the strip's height.
        preview_label.setToolTip(
            _(
                "The preview uses the same compact label grid as the in-game HUD.\n"
                "Spacing, font, colors and HUD cell values come from the selected profile.",
            ),
        )

        workspace = QSplitter(Qt.Orientation.Vertical)
        workspace.setChildrenCollapsible(False)
        workspace.addWidget(design_pane)
        workspace.addWidget(preview_pane)
        workspace.setStretchFactor(0, 3)
        workspace.setStretchFactor(1, 1)
        workspace.setSizes([560, 220])
        self.workspace_splitter = workspace
        stats_splitter.addWidget(workspace)

        # --- Inspector: the selected item, its panel, the profile's presentation
        inspector_body = QWidget()
        inspector_layout = QVBoxLayout(inspector_body)
        inspector_layout.setContentsMargins(10, 10, 10, 10)
        inspector_layout.setSpacing(10)
        item_label = QLabel(_("Selection"))
        item_label.setProperty("class", "h2")
        inspector_layout.addWidget(item_label)
        self.item_props_tabs = QTabWidget()
        self._item_color_btns: dict[str, QPushButton] = {}
        # --- Item tab ---
        item_tab = QWidget()
        itf = QFormLayout(item_tab)
        itf.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        itf.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.item_props_form = itf
        # A stat is picked from the catalogue, a label keeps its free text (B15).
        self.ip_stat = StatChoiceCombo(self._stat_catalog())
        self.ip_stat.activated.connect(lambda _i: self._item_prop_changed())
        self.ip_stat.lineEdit().editingFinished.connect(self._item_prop_changed)
        itf.addRow(_("Statistic:"), self.ip_stat)
        self.ip_text = QLineEdit()
        self.ip_text.editingFinished.connect(self._item_prop_changed)
        itf.addRow(_("Text:"), self.ip_text)
        self.ip_popup = PopupChoiceCombo()
        self.ip_popup.setToolTip(_("The popup a click on the stat opens"))
        self.ip_popup.currentIndexChanged.connect(lambda _i: self._item_prop_changed())
        itf.addRow(_("Popup:"), self.ip_popup)
        self.ip_colspan = QSpinBox()
        self.ip_colspan.setRange(1, 12)
        self.ip_colspan.valueChanged.connect(lambda _v: self._item_prop_changed())
        itf.addRow(_("Span:"), self.ip_colspan)
        self.ip_align = QComboBox()
        self.ip_align.addItems(["center", "left", "right"])
        self.ip_align.currentIndexChanged.connect(lambda _i: self._item_prop_changed())
        itf.addRow(_("Align:"), self.ip_align)
        self.ip_fg = self._item_color_btn("fg")
        itf.addRow(_("Text col:"), self.ip_fg)
        self.ip_bg = self._item_color_btn("bg")
        itf.addRow(_("Cell bg:"), self.ip_bg)
        self.item_props_tabs.addTab(item_tab, _("Item Properties"))
        # --- Color Ranges tab ---
        cr_tab = QWidget()
        crf = QFormLayout(cr_tab)
        crf.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        crf.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.ip_use_thresholds = QCheckBox(_("Use thresholds"))
        self.ip_use_thresholds.toggled.connect(self._item_thresholds_toggled)
        crf.addRow(self.ip_use_thresholds)
        self.ip_loth = self._item_threshold_input()
        crf.addRow(_("Lo th:"), self.ip_loth)
        self.ip_hith = self._item_threshold_input()
        crf.addRow(_("Hi th:"), self.ip_hith)
        # The stat's thresholds when it was selected, and what the tab showed
        # for them then: an edit writes back only what the user changed (B3).
        self._item_thresholds_original: dict = {}
        self._item_thresholds_at_load: dict = {}
        self._item_thresholds_shown = (0.0, 0.0)
        self.ip_locolor = self._item_color_btn("lo")
        crf.addRow(_("Lo col:"), self.ip_locolor)
        self.ip_midcolor = self._item_color_btn("mid")
        crf.addRow(_("Mid col:"), self.ip_midcolor)
        self.ip_hicolor = self._item_color_btn("hi")
        crf.addRow(_("Hi col:"), self.ip_hicolor)
        self.item_props_tabs.addTab(cr_tab, _("Color Ranges"))
        # The inspector is narrow: a combo sized to its longest entry (some stat
        # labels are long) would push the form past its right edge. An editable
        # combo reports that width as its minimum whatever its size policy, so
        # the minimum is set outright.
        for combo in (self.ip_stat, self.ip_popup, self.ip_align):
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(8)
            combo.setMinimumWidth(100)
        inspector_layout.addWidget(self.item_props_tabs)
        # A panel's own settings: shown only for a profile made of panels.
        self.group_props_box = QGroupBox(_("Group Properties"))
        gp = QFormLayout(self.group_props_box)
        gp.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        gp.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.gp_name = QLineEdit()
        self.gp_name.editingFinished.connect(self._group_prop_changed)
        gp.addRow(_("Name:"), self.gp_name)
        self.gp_position = QComboBox()
        self.gp_position.addItems(["", "SB", "BB", "BTN", "CO", "MP", "EP"])
        self.gp_position.currentIndexChanged.connect(lambda _i: self._group_prop_changed())
        gp.addRow(_("Position:"), self.gp_position)
        self.gp_titlebg = self._group_color_btn("title_bgcolor")
        gp.addRow(_("Title bg:"), self.gp_titlebg)
        self.gp_titlefg = self._group_color_btn("title_fgcolor")
        gp.addRow(_("Title fg:"), self.gp_titlefg)
        self.gp_border = self._group_color_btn("bordercolor")
        gp.addRow(_("Border:"), self.gp_border)
        self.gp_bg = self._group_color_btn("bgcolor")
        gp.addRow(_("Panel bg:"), self.gp_bg)
        self.gp_opacity = QSlider(Qt.Orientation.Horizontal)
        self.gp_opacity.setRange(0, 255)
        self.gp_opacity.setValue(178)
        self.gp_opacity.valueChanged.connect(lambda _v: self._group_opacity_changed())
        gp.addRow(_("Opacity:"), self.gp_opacity)
        inspector_layout.addWidget(self.group_props_box)
        # Set once per profile: folded, with what it holds in its header.
        self.presentation_section = CollapsibleSection(
            _("Presentation"), expanded=False, tooltip=_("How this profile's cells are drawn")
        )
        presentation_layout = QVBoxLayout(self.presentation_section.body())
        presentation_layout.setContentsMargins(0, 0, 0, 0)
        presentation_layout.addWidget(self._create_presentation_box())
        inspector_layout.addWidget(self.presentation_section)
        inspector_layout.addStretch()
        inspector = QScrollArea()
        inspector.setWidgetResizable(True)
        inspector.setFrameShape(QFrame.Shape.StyledPanel)
        inspector.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inspector.setWidget(inspector_body)
        inspector.setMinimumWidth(270)
        stats_splitter.addWidget(inspector)

        # Ctrl+Z / Ctrl+Shift+Z for the profile; a text field keeps its own undo.
        for sequence, slot in (
            (QKeySequence(QKeySequence.StandardKey.Undo), self.undo_edit),
            (QKeySequence(QKeySequence.StandardKey.Redo), self.redo_edit),
            (QKeySequence("Ctrl+Shift+Z"), self.redo_edit),
        ):
            shortcut = QShortcut(sequence, stats_tab)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(slot)

        # The canvas takes the extra width; the sources and the inspector keep
        # theirs.
        stats_splitter.setStretchFactor(0, 0)
        stats_splitter.setStretchFactor(1, 1)
        stats_splitter.setStretchFactor(2, 0)
        stats_splitter.setSizes([280, 780, 340])
        stats_layout.addWidget(stats_splitter)

        # Add stats tab
        self.tabs.addTab(stats_tab, _("📊 Statistics"))

        # Tab 2: Popup Windows
        popup_tab = QWidget()
        popup_layout = QVBoxLayout(popup_tab)
        popup_layout.setContentsMargins(12, 10, 12, 10)
        popup_layout.setSpacing(8)

        # Popup selection bar
        popup_select_frame = QFrame()
        popup_select_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        popup_select_frame.setMaximumHeight(72)
        popup_select_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        popup_select_layout = QHBoxLayout(popup_select_frame)
        popup_select_layout.setContentsMargins(12, 6, 12, 6)
        popup_select_layout.setSpacing(10)

        popup_select_label = QLabel(_("Select Popup:"))
        popup_select_label.setProperty("class", "subtitle")
        popup_select_layout.addWidget(popup_select_label)

        self.popup_combo = QComboBox()
        # The 360 px floor plus three 120 px buttons was the widest row in the
        # dialog and set its minimum width on its own.
        self.popup_combo.setMinimumWidth(220)
        self.popup_combo.setMinimumHeight(30)
        self.popup_combo.currentIndexChanged.connect(self.on_popup_selected)
        popup_select_layout.addWidget(self.popup_combo)

        popup_select_layout.addSpacing(20)

        # Popup action buttons
        self.add_popup_btn = QPushButton(_("➕ New Popup"))
        self.add_popup_btn.setFixedHeight(34)
        self.add_popup_btn.clicked.connect(self.add_popup)

        self.dup_popup_btn = QPushButton(_("📋 Duplicate"))
        self.dup_popup_btn.setFixedHeight(34)
        self.dup_popup_btn.clicked.connect(self.duplicate_popup)

        self.del_popup_btn = QPushButton(_("🗑️ Delete"))
        self.del_popup_btn.setFixedHeight(34)
        self.del_popup_btn.clicked.connect(self.delete_popup)

        popup_select_layout.addWidget(self.add_popup_btn)
        popup_select_layout.addWidget(self.dup_popup_btn)
        popup_select_layout.addWidget(self.del_popup_btn)
        popup_select_layout.addStretch()

        popup_layout.addWidget(popup_select_frame)

        # Popup content area
        popup_content_splitter = QSplitter(Qt.Orientation.Horizontal)
        popup_content_splitter.setHandleWidth(8)

        # Left panel: Statistics list
        left_popup_panel = QFrame()
        left_popup_panel.setFrameStyle(QFrame.Shape.StyledPanel)
        # Same reasoning as the statistics editor: the scroll area added below
        # covers a narrow window, so the floor only has to keep the statistics
        # list and the item properties readable side by side.
        left_popup_panel.setMinimumWidth(560)
        left_popup_layout = QVBoxLayout(left_popup_panel)
        left_popup_layout.setContentsMargins(12, 12, 12, 12)
        left_popup_layout.setSpacing(8)

        popup_top_splitter = QSplitter(Qt.Orientation.Horizontal)
        popup_top_splitter.setChildrenCollapsible(False)
        popup_top_splitter.setMaximumHeight(270)
        popup_top_splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        # Statistics list
        stats_group = QGroupBox(_("Statistics"))
        stats_layout = QVBoxLayout()
        stats_layout.setSpacing(6)

        # Stats buttons at the top
        stats_btn_layout = QHBoxLayout()
        stats_btn_layout.setContentsMargins(0, 8, 0, 0)
        stats_btn_layout.setSpacing(10)

        self.add_popup_stat_btn = QPushButton(_("➕ Add"))
        self.add_popup_stat_btn.setMinimumHeight(34)
        self.add_popup_stat_btn.clicked.connect(self.add_popup_stat)

        self.edit_popup_stat_btn = QPushButton(_("📝 Edit"))
        self.edit_popup_stat_btn.setMinimumHeight(34)
        self.edit_popup_stat_btn.clicked.connect(self.edit_popup_stat)

        self.remove_popup_stat_btn = QPushButton(_("➖ Remove"))
        self.remove_popup_stat_btn.setMinimumHeight(34)
        self.remove_popup_stat_btn.clicked.connect(self.remove_popup_stat)

        self.move_up_btn = QPushButton(_("↑ Up"))
        self.move_up_btn.setMinimumHeight(34)
        self.move_up_btn.clicked.connect(self.move_stat_up)

        self.move_down_btn = QPushButton(_("↓ Down"))
        self.move_down_btn.setMinimumHeight(34)
        self.move_down_btn.clicked.connect(self.move_stat_down)

        # PT4-style design canvas: the popup's stats as a vertical chip stack,
        # synced with the list below and the live preview.
        design_lbl = QLabel(_("Design"))
        design_lbl.setProperty("class", "h2")
        stats_layout.addWidget(design_lbl)
        self.popup_canvas = HudDesignCanvas()
        self.popup_canvas.setMinimumHeight(380)
        self.popup_canvas.item_selected.connect(self._on_popup_canvas_selected)
        self.popup_canvas.add_to_row.connect(lambda _r: self.add_popup_stat())
        self.popup_canvas.remove_from_row.connect(self._popup_canvas_remove_row)
        stats_layout.addWidget(self.popup_canvas, 2)

        stats_btn_layout.addWidget(self.add_popup_stat_btn)
        stats_btn_layout.addWidget(self.edit_popup_stat_btn)
        stats_btn_layout.addWidget(self.remove_popup_stat_btn)
        stats_btn_layout.addWidget(self.move_up_btn)
        stats_btn_layout.addWidget(self.move_down_btn)
        stats_btn_layout.addStretch()
        stats_layout.addLayout(stats_btn_layout)

        # Statistics list: kept for selection state + add/edit/remove/reorder
        # logic, but hidden — the design canvas above (with submenu labels) is the
        # visible surface, so the two no longer overlap.
        self.popup_stats_list = QListWidget()
        self.popup_stats_list.setAlternatingRowColors(True)
        self.popup_stats_list.hide()
        stats_layout.addWidget(self.popup_stats_list)
        stats_group.setLayout(stats_layout)

        popup_info_group = QGroupBox(_("Popup Information"))
        popup_info_layout = QGridLayout()
        popup_info_layout.setSpacing(6)
        popup_info_layout.setContentsMargins(8, 8, 8, 8)

        popup_info_layout.addWidget(QLabel(_("Name:")), 0, 0)
        self.popup_name_edit = QLineEdit()
        self.popup_name_edit.setReadOnly(True)
        self.popup_name_edit.setMinimumHeight(28)
        popup_info_layout.addWidget(self.popup_name_edit, 0, 1)

        popup_info_layout.addWidget(QLabel(_("Class:")), 1, 0)
        self.popup_class_combo = QComboBox()
        self.popup_class_combo.addItems(
            [
                "default",
                "Submenu",
                "Multicol",
                "ModernSubmenu",
                "ModernSubmenuLight",
                "ModernSubmenuClassic",
                "CategorizedPopup",
                "RangeChartPopup",
                "BlockPopup",
            ]
        )
        self.popup_class_combo.setMinimumHeight(28)
        self.popup_class_combo.currentTextChanged.connect(self.on_popup_class_changed)
        popup_info_layout.addWidget(self.popup_class_combo, 1, 1)

        popup_info_layout.addWidget(QLabel(_("Theme:")), 2, 0)
        self.popup_theme_combo = QComboBox()
        self.popup_theme_combo.addItem(_("Default"), "")
        for theme_name in sorted(AVAILABLE_THEMES):
            self.popup_theme_combo.addItem(theme_name, theme_name)
        self.popup_theme_combo.currentIndexChanged.connect(self.on_popup_theme_changed)
        popup_info_layout.addWidget(self.popup_theme_combo, 2, 1)

        popup_info_layout.addWidget(QLabel(_("Icons:")), 3, 0)
        self.popup_icon_provider_combo = QComboBox()
        self.popup_icon_provider_combo.addItem(_("Default"), "")
        for provider_name in sorted(AVAILABLE_PROVIDERS):
            self.popup_icon_provider_combo.addItem(provider_name, provider_name)
        self.popup_icon_provider_combo.currentIndexChanged.connect(self.on_popup_icon_provider_changed)
        popup_info_layout.addWidget(self.popup_icon_provider_combo, 3, 1)

        popup_info_group.setLayout(popup_info_layout)
        popup_info_group.setMinimumWidth(300)
        popup_top_splitter.addWidget(popup_info_group)

        # PT4-style Item Properties for the selected popup item/cell.
        self._popup_group: dict | None = None  # loaded BlockPopup group (editable cells)
        self._popup_item_cell: dict[str, Any] | None = None  # the selected cell dict
        self._popup_item_mode: str | None = None
        self.pi_props_box = QGroupBox(_("Item Properties"))
        self.pi_props_box.setMinimumWidth(360)
        pif = QFormLayout(self.pi_props_box)
        pif.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        pif.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        pif.setVerticalSpacing(5)
        pif.setContentsMargins(8, 8, 8, 8)
        self.pi_text = QLineEdit()
        self.pi_text.editingFinished.connect(self._popup_item_changed)
        pif.addRow(_("Text / Stat:"), self.pi_text)
        self.pi_submenu = QLineEdit()
        self.pi_submenu.editingFinished.connect(self._popup_item_changed)
        pif.addRow(_("Submenu:"), self.pi_submenu)
        self.pi_category = QComboBox()
        self.pi_category.addItems(
            ["auto", "player_info", "preflop", "flop", "turn", "river", "steal", "aggression", "general"]
        )
        self.pi_category.currentTextChanged.connect(self._popup_item_changed)
        pif.addRow(_("Section:"), self.pi_category)
        self.pi_type = QLabel(_("—"))
        pif.addRow(_("Type:"), self.pi_type)
        self.pi_pos = QLabel(_("—"))
        pif.addRow(_("Position:"), self.pi_pos)
        self._popup_item_color_btns: dict[str, QPushButton] = {}
        self.pi_fg = self._popup_item_color_btn("fg")
        pif.addRow(_("Foreground:"), self.pi_fg)
        self.pi_bg = self._popup_item_color_btn("bg")
        pif.addRow(_("Background:"), self.pi_bg)
        self.pi_props_box.setEnabled(False)
        popup_top_splitter.addWidget(self.pi_props_box)
        popup_top_splitter.setStretchFactor(0, 1)
        popup_top_splitter.setStretchFactor(1, 2)
        popup_top_splitter.setSizes([360, 520])
        left_popup_layout.addWidget(popup_top_splitter)
        left_popup_layout.addWidget(stats_group, 1)

        left_popup_scroll = QScrollArea()
        left_popup_scroll.setWidgetResizable(True)
        left_popup_scroll.setFrameShape(QFrame.Shape.NoFrame)
        left_popup_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        left_popup_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        left_popup_scroll.setWidget(left_popup_panel)
        popup_content_splitter.addWidget(left_popup_scroll)

        # Right panel: Popup preview
        right_popup_panel = QFrame()
        right_popup_panel.setFrameStyle(QFrame.Shape.StyledPanel)
        right_popup_panel.setMinimumWidth(240)
        right_popup_layout = QVBoxLayout(right_popup_panel)
        right_popup_layout.setContentsMargins(12, 12, 12, 12)
        right_popup_layout.setSpacing(8)

        # Preview section
        preview_header_layout = QHBoxLayout()
        preview_label = QLabel(_("Popup Preview"))
        preview_label.setProperty("class", "h3")
        preview_header_layout.addWidget(preview_label)

        preview_header_layout.addStretch()
        self.zoom_popup_btn = QPushButton(_("🔍 Real Size"))
        self.zoom_popup_btn.setToolTip(_("Open preview at 100% real size in a new window"))
        self.zoom_popup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.zoom_popup_btn.clicked.connect(self.open_popup_zoom_window)
        preview_header_layout.addWidget(self.zoom_popup_btn)

        right_popup_layout.addLayout(preview_header_layout)

        self.popup_preview = PopupPreviewWidget()
        self.popup_preview.setMinimumHeight(220)
        self.popup_preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.popup_preview.double_clicked_callback = self.open_popup_zoom_window
        right_popup_layout.addWidget(self.popup_preview, 1)

        right_popup_scroll = QScrollArea()
        right_popup_scroll.setWidgetResizable(True)
        right_popup_scroll.setFrameShape(QFrame.Shape.NoFrame)
        right_popup_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        right_popup_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        right_popup_scroll.setWidget(right_popup_panel)
        popup_content_splitter.addWidget(right_popup_scroll)
        popup_content_splitter.setStretchFactor(0, 6)
        popup_content_splitter.setStretchFactor(1, 1)
        popup_content_splitter.setSizes([1280, 260])

        popup_layout.addWidget(popup_content_splitter)

        # Add popup tab
        self.tabs.addTab(popup_tab, _("💬 Popup Windows"))

        # PT-style persistent rules selecting a HUD profile from the table
        # context (room/game/format/seats/etc.).
        self._create_profile_select_tab()
        self._create_dynamic_panels_tab()
        self._create_reference_hud_tab()

        # Tab 3: General Settings
        general_tab = QWidget()
        general_layout = QVBoxLayout(general_tab)
        general_layout.setContentsMargins(30, 30, 30, 30)
        general_layout.setSpacing(20)

        # Title
        general_title = QLabel(_("General HUD and Profiling Settings"))
        general_title.setProperty("class", "h2")
        general_layout.addWidget(general_title)

        # Form / Group Container
        general_card = QFrame()
        general_card.setFrameStyle(QFrame.Shape.StyledPanel)
        general_card_layout = QVBoxLayout(general_card)
        general_card_layout.setContentsMargins(25, 25, 25, 25)
        general_card_layout.setSpacing(20)

        # 1. Profiling checkbox
        self.profiling_checkbox = QCheckBox(_("Enable Player Profiling (Categorization)"))
        self.profiling_checkbox.setToolTip(
            _("Enable auto-classification of players into Nit, Calling Station, Fish, Maniac, LAG, Reg, TAG.")
        )
        general_card_layout.addWidget(self.profiling_checkbox)

        # 2. Profile in name checkbox
        self.profile_in_name_checkbox = QCheckBox(_("Show profile emoji and color code directly on player name labels"))
        self.profile_in_name_checkbox.setToolTip(
            _("Append the profile emoji (e.g. 🐟, 🐌, 🎯) and color the player's name in the HUD.")
        )
        general_card_layout.addWidget(self.profile_in_name_checkbox)

        # 3. Min hands setting (SpinBox)
        hands_layout = QHBoxLayout()
        hands_label = QLabel(_("Minimum hands required for profiling:"))
        hands_label.setToolTip(_("The minimum number of hands tracked on an opponent before profiling is computed."))
        self.profile_min_hands_spin = QSpinBox()
        self.profile_min_hands_spin.setRange(1, 10000)
        self.profile_min_hands_spin.setSingleStep(5)
        self.profile_min_hands_spin.setMinimumWidth(100)
        hands_layout.addWidget(hands_label)
        hands_layout.addWidget(self.profile_min_hands_spin)
        hands_layout.addStretch()
        general_card_layout.addLayout(hands_layout)

        general_layout.addWidget(general_card)
        general_layout.addStretch()

        # Add tab
        self.tabs.addTab(general_tab, _("⚙️ General Settings"))

        # Add tabs to main layout
        main_layout.addWidget(self.tabs)

        # Bottom action bar
        bottom_frame = QFrame()
        bottom_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        bottom_layout = QHBoxLayout(bottom_frame)
        bottom_layout.setContentsMargins(15, 10, 15, 10)

        # Status/info area
        self.status_label = QLabel(_("Ready"))
        self.status_label.setProperty("class", "caption")
        bottom_layout.addWidget(self.status_label)

        # Says that Save has something to write, and what (in the tooltip).
        self.unsaved_label = QLabel()
        self.unsaved_label.setProperty("class", "caption")
        self.unsaved_label.setStyleSheet("font-weight: bold;")
        self.unsaved_label.setVisible(False)
        bottom_layout.addWidget(self.unsaved_label)

        bottom_layout.addStretch()

        # Dialog buttons
        btn_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btn_box.button(QDialogButtonBox.Save).setText(_("Save Changes"))
        btn_box.button(QDialogButtonBox.Cancel).setText(_("Cancel"))
        btn_box.accepted.connect(self.save_changes)
        btn_box.rejected.connect(self.reject)
        bottom_layout.addWidget(btn_box)

        main_layout.addWidget(bottom_frame)

        # Load profiles
        self.load_profiles()

        # Load popup windows
        self.load_popup_windows()

        # Load and track general profiling settings
        hud_params = self.config.get_hud_ui_parameters()
        self.original_player_profiling = hud_params.get("player_profiling", "True") == "True"
        self.original_profile_in_name = hud_params.get("profile_in_name", "True") == "True"
        try:
            self.original_profile_min_hands = int(hud_params.get("profile_min_hands", 10))
        except (ValueError, TypeError):
            self.original_profile_min_hands = 10

        self.profiling_checkbox.setChecked(self.original_player_profiling)
        self.profile_in_name_checkbox.setChecked(self.original_profile_in_name)
        self.profile_min_hands_spin.setValue(self.original_profile_min_hands)
        self.profiling_checkbox.toggled.connect(self._refresh_unsaved_indicator)
        self.profile_in_name_checkbox.toggled.connect(self._refresh_unsaved_indicator)
        self.profile_min_hands_spin.valueChanged.connect(self._refresh_unsaved_indicator)

        # Track changes: what Save would write, as it stands now.
        self._saved_state = self._editor_state(keep=True)

        # Update status
        self.update_status()

        # Size the dialog last, once the content is known. The dialog used to
        # demand 1200 x 800 and open at 1400 x 900 without ever asking the screen
        # how much room it had, so on a laptop the bottom of a tab sat below the
        # visible area and the window could not be made smaller.
        fit_window(self, 1400, 900)

    def update_status(self) -> None:
        """Update status label with current profile info."""
        if self.profile_combo.currentIndex() < 0:
            return
        profile_name = self.profile_combo.currentText()
        profile = self.hud_profiles.get(profile_name, {})
        count = len(profile_io.profile_stats(profile))
        blocks = profile.get("blocks") if isinstance(profile, dict) else None
        if blocks:
            layout = _("Panels: {count}").format(count=len(blocks))
        else:
            rows, cols = profile_io.stat_set_size(profile)
            layout = _("Grid: {rows}×{cols}").format(rows=rows, cols=cols)
        self.status_label.setText(
            _("Profile: {name} | {layout} | Statistics: {count}").format(name=profile_name, layout=layout, count=count)
        )
        self._refresh_unsaved_indicator()

    def _general_settings(self) -> tuple[Any, ...]:
        """The General Settings tab's values, in the order they are compared."""
        widgets = (
            getattr(self, "profiling_checkbox", None),
            getattr(self, "profile_in_name_checkbox", None),
            getattr(self, "profile_min_hands_spin", None),
        )
        return tuple(None if w is None else (w.isChecked() if isinstance(w, QCheckBox) else w.value()) for w in widgets)

    def _editor_state(self, *, keep: bool) -> editor_state.EditorState:
        """Everything Save writes; ``keep`` copies it to compare against later."""
        enabled = getattr(self, "panel_rules_enabled", None)
        return editor_state.EditorState.capture(
            profiles=getattr(self, "hud_profiles", None),
            popups=getattr(self, "popup_windows", None),
            settings=self._general_settings(),
            profile_rules=getattr(self, "profile_rules", ()),
            panel_rules=getattr(self, "panel_rules", ()),
            panel_rules_enabled=enabled.isChecked() if enabled is not None else False,
            panel_fallback=getattr(self, "panel_rules_fallback", ""),
            keep=keep,
        )

    def _unsaved_parts(self) -> list[str]:
        """What changed since the editor opened or last saved."""
        saved = getattr(self, "_saved_state", None)
        if saved is None:
            return []
        return editor_state.differences(saved, self._editor_state(keep=False))

    def _refresh_unsaved_indicator(self, *_args: Any) -> None:
        """Show or hide the "unsaved changes" mark of the status bar."""
        label = getattr(self, "unsaved_label", None)
        if label is None or getattr(self, "_saved_state", None) is None:
            return
        parts = self._unsaved_parts()
        label.setVisible(bool(parts))
        label.setText(_("● Unsaved changes") if parts else "")
        label.setToolTip(
            _("Changed since the last save: {parts}").format(parts=editor_state.describe_differences(parts))
            if parts
            else ""
        )

    def _deep_copy_profiles(self, profiles):
        """Create a deep copy of profiles for change detection."""
        import copy

        return copy.deepcopy(profiles)

    def _deep_copy_popups(self, popups):
        """Create a deep copy of popup windows for change detection."""
        import copy

        return copy.deepcopy(popups)

    def has_unsaved_changes(self) -> bool:
        """Whether Save would write anything: profiles, popups, settings or rules (B8)."""
        return bool(self._unsaved_parts())

    def _hud_preview_params(self) -> dict[str, str]:
        ui = getattr(self.config, "ui", None)
        return {
            "bgcolor": getattr(ui, "hudbgcolor", "") or getattr(ui, "bgcolor", "#000000"),
            "fgcolor": getattr(ui, "hudfgcolor", "") or getattr(ui, "fgcolor", "#ffffff"),
            "font": getattr(ui, "font", "Sans") or "Sans",
            "font_size": getattr(ui, "font_size", "8") or "8",
        }

    def _settle_unsaved_changes(self) -> str:
        """Ask what to do with unsaved changes before the editor closes.

        ``"clean"`` (nothing to ask), ``"saved"`` (saved, and the dialog
        accepted), ``"discard"``, or ``"stay"`` (Cancel, or a failed save).
        """
        if not self.has_unsaved_changes():
            return "clean"
        reply = QMessageBox.question(
            self,
            _("Unsaved Changes"),
            _("You have unsaved changes. Do you want to save before closing?"),
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
        )
        if reply == QMessageBox.Save:
            return "saved" if self.save_changes() else "stay"
        if reply == QMessageBox.Discard:
            return "discard"
        return "stay"

    def reject(self) -> None:
        """Cancel and Esc ask before losing edits, like closing the window (B7)."""
        if self._settle_unsaved_changes() in ("clean", "discard"):
            super().reject()

    def closeEvent(self, event) -> None:
        """Handle window close event."""
        if self._settle_unsaved_changes() == "stay":
            event.ignore()
        else:
            event.accept()

    @staticmethod
    def _stat_to_dict(stat, row: int, col: int, panel: str = "") -> dict:
        """Convert a Configuration.Stat into the editor's flat stat dict."""
        return profile_io.stat_to_dict(stat, row, col, panel)

    def _profile_from_stat_set(self, stat_set) -> Any:
        """Convert a Configuration.Stat_sets object into the editor profile."""
        return profile_io.profile_from_stat_set(stat_set)

    def load_profiles(self) -> None:
        # Try to load HUD profiles from config (from HUD_config.xml)
        self.hud_profiles = None
        self._histories: dict[int, tuple[dict, undo.History]] = {}
        # Prefer stat_sets: this is the canonical HUD_config.xml representation
        # and preserves PT4 multi-block <block> panels. Some callers also expose
        # flattened hud_profiles, but those lose the block metadata needed by the
        # visual preview.
        if hasattr(self.config, "stat_sets") and self.config.stat_sets:
            self.hud_profiles = {}
            for set_name, stat_set in self.config.stat_sets.items():
                self.hud_profiles[set_name] = self._profile_from_stat_set(stat_set)
        elif hasattr(self.config, "hud_profiles") and self.config.hud_profiles:
            self.hud_profiles = self.config.hud_profiles
        # 3. Fallback to demo profile if nothing found
        if not self.hud_profiles:
            self.hud_profiles = {
                "Default": [
                    {"row": 0, "col": 0, "stat": "vpip", "click": "", "popup": ""},
                    {"row": 0, "col": 1, "stat": "pfr", "click": "", "popup": ""},
                    {"row": 1, "col": 0, "stat": "3bet", "click": "", "popup": ""},
                ],
            }
        self.profile_combo.clear()
        self.profile_combo.addItems(list(self.hud_profiles.keys()))
        if self.profile_combo.count() > 0:
            self.profile_combo.setCurrentIndex(0)

    def load_popup_windows(self) -> None:
        """Load popup window definitions from config."""
        self.popup_windows = {}

        if hasattr(self.config, "popup_windows") and self.config.popup_windows:
            for popup_name, popup_obj in self.config.popup_windows.items():
                _params = getattr(popup_obj, "pu_class_params", {}) or {}
                popup_data = {
                    "name": popup_name,
                    "class": popup_obj.pu_class,
                    "stats": [],
                    "source": _params.get("source", ""),
                    "group": _params.get("group", ""),
                    "theme": _params.get("theme", ""),
                    "icon_provider": _params.get("icon_provider", ""),
                    "title": _params.get("title", ""),
                    "width": _params.get("width", ""),
                    "max_height": _params.get("max_height", ""),
                }

                # Extract stats and submenus
                for i, stat_name in enumerate(popup_obj.pu_stats):
                    stat_info = {"stat_name": stat_name, "submenu": ""}

                    # Check if there's a submenu for this stat
                    if i < len(popup_obj.pu_stats_submenu):
                        stat_tuple = popup_obj.pu_stats_submenu[i]
                        if len(stat_tuple) > 1 and stat_tuple[1]:
                            stat_info["submenu"] = stat_tuple[1]
                    categories = getattr(popup_obj, "pu_stats_category", [])
                    if i < len(categories) and categories[i]:
                        stat_info["category"] = categories[i]
                    labels = getattr(popup_obj, "pu_stats_label", [])
                    if i < len(labels) and labels[i]:
                        stat_info["label"] = labels[i]
                    colors = getattr(popup_obj, "pu_stats_color", [])
                    if i < len(colors) and colors[i]:
                        stat_info["color"] = colors[i]

                    popup_data["stats"].append(stat_info)

                self.popup_windows[popup_name] = popup_data

        # Update popup combo
        self.popup_combo.clear()
        self.popup_combo.addItems(sorted(self.popup_windows.keys()))
        if self.popup_combo.count() > 0:
            self.popup_combo.setCurrentIndex(0)

    def on_popup_selected(self, index) -> None:
        """Handle popup selection from combo box."""
        if index < 0 or index >= self.popup_combo.count():
            self.popup_name_edit.clear()
            self.popup_class_combo.setCurrentIndex(0)
            self.popup_stats_list.clear()
            self.popup_preview.clear_preview()
            return

        popup_name = self.popup_combo.currentText()
        popup_data = self.popup_windows.get(popup_name, {})

        # Update popup info (guard the class combo so loading doesn't fire
        # on_popup_class_changed and overwrite the real class).
        self.popup_name_edit.setText(popup_name)
        self._loading_popup = True
        self.popup_class_combo.setCurrentText(popup_data.get("class", "default"))
        self.popup_theme_combo.setCurrentIndex(max(0, self.popup_theme_combo.findData(popup_data.get("theme", ""))))
        self.popup_icon_provider_combo.setCurrentIndex(
            max(0, self.popup_icon_provider_combo.findData(popup_data.get("icon_provider", "")))
        )
        self._loading_popup = False

        # Update stats list
        self.popup_stats_list.clear()
        for stat in popup_data.get("stats", []):
            stat_text = stat["stat_name"]
            if stat.get("category"):
                stat_text = f"[{translate_hud_category(stat['category'])}] {stat_text}"
            if stat.get("submenu"):
                stat_text += f" → {stat['submenu']}"
            self.popup_stats_list.addItem(stat_text)

        # Update the WYSIWYG chip canvas + preview.
        self._rebuild_popup_canvas(popup_data)
        self.update_popup_preview()

    def _rebuild_popup_canvas(self, popup_data) -> None:
        """Render the popup as a WYSIWYG chip canvas.

        For an imported BlockPopup the canvas mirrors the PT4 grid (text + stat
        cells at their row/col); for a classic popup it's a vertical stat stack.
        """
        if not hasattr(self, "popup_canvas"):
            return
        self._popup_group = None
        self._popup_item_cell = None
        self._popup_item_mode = None
        if hasattr(self, "pi_props_box"):
            self.pi_props_box.setEnabled(False)
            self.pi_text.clear()
            if hasattr(self, "pi_submenu"):
                self.pi_submenu.clear()
                self.pi_submenu.setEnabled(True)
            self.pi_type.setText(_("—"))
            self.pi_pos.setText(_("—"))
            self._style_color_btn(self.pi_fg, "")
            self._style_color_btn(self.pi_bg, "")
            self.pi_fg.setEnabled(True)
            self.pi_bg.setEnabled(True)
        if popup_data.get("class") == "BlockPopup" and popup_data.get("source") and popup_data.get("group"):
            from fpdb_3_legacy.BlockPopup import load_block_popup

            try:
                group = load_block_popup(popup_data["source"], popup_data["group"])
            except (KeyError, OSError, TypeError, ValueError):
                log.warning(
                    "Unable to load block popup %s/%s", popup_data["source"], popup_data["group"], exc_info=True
                )
                group = None
            if group:
                # Keep the loaded group + its source so Item Properties edits the
                # real cells and can be saved back to the JSON sidecar.
                self._popup_group = group
                self._popup_group_source = popup_data["source"]
                block = {
                    "label": "",
                    "rows": max(1, int(group.get("rows", 1))),
                    "cols": max(1, int(group.get("cols", 1))),
                    "hlines": [],
                    "stats": [
                        {
                            "row": c["row"],
                            "col": c["col"],
                            "stat": c["text"],
                            "hudcolor": c.get("fg", ""),
                            "hudbgcolor": c.get("bg", ""),
                        }
                        for c in group.get("cells", [])
                        if c["kind"] == "stat"
                    ],
                    "texts": [
                        {
                            "rowcol": (c["row"], c["col"]),
                            "label": c["text"],
                            "colspan": 1,
                            "align": "center",
                            "fgcolor": c.get("fg", ""),
                            "bgcolor": c.get("bg", ""),
                        }
                        for c in group.get("cells", [])
                        if c["kind"] == "text"
                    ],
                }
                # Keep the imported grid editor aligned with the Statistics tab:
                # full chips plus per-row +/- controls, even for dense PT4 grids.
                self.popup_canvas.compact = False
                self.popup_canvas.set_block(0, block)
                return

        stats = popup_data.get("stats", [])

        def _label(s):
            name = s.get("stat_name", "")
            if s.get("category"):
                name = f"[{translate_hud_category(s['category'])}] {name}"
            return f"{name}  →  {s['submenu']}" if s.get("submenu") else name

        block = {
            "label": "",
            "rows": max(1, len(stats)),
            "cols": 1,
            "stats": [{"row": i, "col": 0, "stat": _label(s), "_popup_stat": s} for i, s in enumerate(stats)],
            "texts": [],
            "hlines": [],
        }
        self.popup_canvas.compact = False
        self.popup_canvas.set_block(0, block)

    def _on_popup_canvas_selected(self, payload) -> None:
        """A popup chip was clicked -> select the list row and, for a BlockPopup,
        load the cell into the Item Properties panel."""
        _bi, kind, ref = payload
        if kind == "text" and "rowcol" in ref:
            row, col = ref["rowcol"]
        else:
            row, col = ref.get("row"), ref.get("col")
        if row is not None and 0 <= row < self.popup_stats_list.count():
            self.popup_stats_list.setCurrentRow(row)
        # BlockPopup: edit the real grid cell at (row, col).
        if self._popup_group is not None and row is not None and col is not None:
            cell = next((c for c in self._popup_group.get("cells", []) if c["row"] == row and c["col"] == col), None)
            self._load_popup_item(cell)
            return
        stat = ref.get("_popup_stat") if isinstance(ref, dict) else None
        if stat is not None:
            self._load_popup_stat_item(stat, row)

    # --- popup Item Properties ------------------------------------------
    def _popup_item_color_btn(self, role: str) -> QPushButton:
        btn = QPushButton(_("(none)"))
        btn.setFixedHeight(24)
        btn.clicked.connect(lambda _=False, r=role: self._pick_popup_item_color(r))
        if not hasattr(self, "_popup_item_color_btns"):
            self._popup_item_color_btns = {}
        self._popup_item_color_btns[role] = btn
        return btn

    def _load_popup_item(self, cell) -> None:
        self._popup_item_cell = cell
        self._popup_item_mode = "block"
        if cell is None:
            self.pi_props_box.setEnabled(False)
            return
        self._loading_popup_item = True
        self.pi_props_box.setEnabled(True)
        self.pi_text.setText(str(cell.get("text", "")))
        self.pi_submenu.clear()
        self.pi_submenu.setEnabled(False)
        self.pi_category.setCurrentText("auto")
        self.pi_category.setEnabled(False)
        self.pi_type.setText(_("Stat") if cell.get("kind") == "stat" else _("Text"))
        self.pi_pos.setText(_("row {row}, col {col}").format(row=cell.get("row", 0), col=cell.get("col", 0)))
        self.pi_fg.setEnabled(True)
        self.pi_bg.setEnabled(True)
        self._style_color_btn(self.pi_fg, cell.get("fg", ""))
        self._style_color_btn(self.pi_bg, cell.get("bg", ""))
        self._loading_popup_item = False

    def _load_popup_stat_item(self, stat: dict, row: int | None) -> None:
        self._popup_item_cell = stat
        self._popup_item_mode = "stat"
        self._loading_popup_item = True
        self.pi_props_box.setEnabled(True)
        self.pi_text.setText(str(stat.get("stat_name", "")))
        self.pi_submenu.setEnabled(True)
        self.pi_submenu.setText(str(stat.get("submenu", "")))
        self.pi_category.setEnabled(True)
        category = str(stat.get("category", "") or "auto")
        self.pi_category.setCurrentText(category if self.pi_category.findText(category) >= 0 else "auto")
        self.pi_type.setText(_("Stat"))
        self.pi_pos.setText(_("row {row}, col {col}").format(row="—" if row is None else row, col=0))
        self.pi_fg.setEnabled(False)
        self.pi_bg.setEnabled(False)
        self._style_color_btn(self.pi_fg, "")
        self._style_color_btn(self.pi_bg, "")
        self._loading_popup_item = False

    def _popup_item_changed(self) -> None:
        if getattr(self, "_loading_popup_item", False):
            return
        cell = self._popup_item_cell
        if cell is None:
            return
        if getattr(self, "_popup_item_mode", None) == "stat":
            cell["stat_name"] = self.pi_text.text()
            cell["submenu"] = self.pi_submenu.text()
            if self.pi_category.currentText() == "auto":
                cell.pop("category", None)
            else:
                cell["category"] = self.pi_category.currentText()
            self._after_popup_stat_edit()
        else:
            cell["text"] = self.pi_text.text()
            self._after_popup_item_edit()

    def _pick_popup_item_color(self, role: str) -> None:

        cell = self._popup_item_cell
        if cell is None or getattr(self, "_popup_item_mode", None) == "stat":
            return
        key = "fg" if role == "fg" else "bg"
        current = cell.get(key, "")
        col = QColorDialog.getColor(QColor(current) if current else QColor("#ffffff"), self, _("Pick colour"))
        if not col.isValid():
            return
        cell[key] = col.name()
        self._style_color_btn(self._popup_item_color_btns[role], col.name())
        self._after_popup_item_edit()

    def _after_popup_item_edit(self) -> None:
        """Write the edited group back to its JSON sidecar and re-render the canvas
        + preview (which both reload from that JSON)."""
        import json

        src = getattr(self, "_popup_group_source", "")
        grp = self._popup_group
        if src and grp:
            try:
                with open(src, encoding="utf-8") as fh:
                    data = json.load(fh)
                for i, g in enumerate(data.get("popup_groups", [])):
                    if g.get("name") == grp.get("name"):
                        data["popup_groups"][i] = grp
                        break
                with open(src, "w", encoding="utf-8") as fh:
                    json.dump(data, fh, indent=2)
            except Exception:
                log.exception("popup item edit: failed to write %s", src)
        name = self.popup_combo.currentText()
        self._rebuild_popup_canvas(self.popup_windows.get(name, {}))
        self.update_popup_preview()

    def _after_popup_stat_edit(self) -> None:
        name = self.popup_combo.currentText()
        popup_data = self.popup_windows.get(name, {})
        current_row = self.popup_stats_list.currentRow()
        self.popup_stats_list.clear()
        for stat in popup_data.get("stats", []):
            stat_text = stat.get("stat_name", "")
            if stat.get("category"):
                stat_text = f"[{stat['category']}] {stat_text}"
            if stat.get("submenu"):
                stat_text += f" → {stat['submenu']}"
            self.popup_stats_list.addItem(stat_text)
        self._rebuild_popup_canvas(popup_data)
        if 0 <= current_row < len(popup_data.get("stats", [])):
            self.popup_stats_list.setCurrentRow(current_row)
            self.popup_canvas.select_ref(popup_data["stats"][current_row])
            self._load_popup_stat_item(popup_data["stats"][current_row], current_row)
        self.update_popup_preview()

    def _popup_canvas_remove_row(self, row) -> None:
        """- on a popup chip row: remove that stat."""
        if self.popup_combo.currentIndex() < 0:
            return
        popup_name = self.popup_combo.currentText()
        stats = self.popup_windows.get(popup_name, {}).get("stats", [])
        if 0 <= row < len(stats):
            stats.pop(row)
            self.on_popup_selected(self.popup_combo.currentIndex())

    def on_popup_class_changed(self, new_class) -> None:
        """Handle popup class change (ignored while loading to avoid corrupting
        the class when navigating between popups)."""
        if getattr(self, "_loading_popup", False):
            return
        if self.popup_combo.currentIndex() >= 0:
            popup_name = self.popup_combo.currentText()
            if popup_name in self.popup_windows:
                self.popup_windows[popup_name]["class"] = new_class
                self.update_popup_preview()

    def on_popup_theme_changed(self, _index: int) -> None:
        """Store the optional per-popup theme selected in the editor."""
        if getattr(self, "_loading_popup", False) or self.popup_combo.currentIndex() < 0:
            return
        popup_name = self.popup_combo.currentText()
        if popup_name in self.popup_windows:
            self.popup_windows[popup_name]["theme"] = self.popup_theme_combo.currentData() or ""
            self.update_popup_preview()

    def on_popup_icon_provider_changed(self, _index: int) -> None:
        """Store the optional per-popup icon provider selected in the editor."""
        if getattr(self, "_loading_popup", False) or self.popup_combo.currentIndex() < 0:
            return
        popup_name = self.popup_combo.currentText()
        if popup_name in self.popup_windows:
            self.popup_windows[popup_name]["icon_provider"] = self.popup_icon_provider_combo.currentData() or ""
            self.update_popup_preview()

    def update_popup_preview(self) -> None:
        self._refresh_unsaved_indicator()
        """Update the popup preview display."""
        if self.popup_combo.currentIndex() < 0:
            return

        popup_name = self.popup_combo.currentText()
        popup_data = self.popup_windows.get(popup_name, {})
        popup_class = popup_data.get("class", "default")
        stats = popup_data.get("stats", [])
        source = popup_data.get("source", "")
        group = popup_data.get("group", "")
        self.popup_preview.set_popup(
            popup_name,
            popup_class,
            stats,
            source,
            group,
            popup_data.get("theme", ""),
            popup_data.get("icon_provider", ""),
        )

    def open_popup_zoom_window(self) -> None:
        """Open the currently selected popup preview at real size in a new window."""
        if self.popup_combo.currentIndex() < 0:
            return

        popup_name = self.popup_combo.currentText()
        popup_data = self.popup_windows.get(popup_name, {})
        if not popup_data:
            return

        dlg = PopupZoomDialog(
            popup_name=popup_name,
            popup_class=popup_data.get("class", "default"),
            stats=popup_data.get("stats", []),
            source=popup_data.get("source", ""),
            group=popup_data.get("group", ""),
            theme_name=popup_data.get("theme", ""),
            icon_provider_name=popup_data.get("icon_provider", ""),
            parent=self,
        )
        dlg.exec()

    def _on_positional_mode_changed(self, _index: int) -> None:
        """Store the chosen positional-panel mode on the current profile."""
        name = self.profile_combo.currentText()
        profile = self.hud_profiles.get(name) if self.hud_profiles else None
        if isinstance(profile, dict):
            profile["positional_mode"] = self.positional_mode_combo.currentData() or "current"
        self._refresh_unsaved_indicator()
        self._record_history()

    def _on_show_hero_changed(self, checked: bool) -> None:
        """Store the hero-HUD visibility on the current profile."""
        name = self.profile_combo.currentText()
        profile = self.hud_profiles.get(name) if self.hud_profiles else None
        if isinstance(profile, dict):
            profile["show_hero_hud"] = "true" if checked else "false"
        self._refresh_unsaved_indicator()
        self._record_history()

    # --- Profile presentation (#764) ------------------------------------------
    def _create_presentation_box(self) -> QGroupBox:
        """The profile's presentation controls and its read-only HUD window.

        One field per row: the box sits in the narrow inspector, under the
        "Presentation" section that titles it.
        """
        box = QGroupBox()
        self.presentation_box = box
        grid = QGridLayout(box)
        grid.setHorizontalSpacing(10)

        self.presentation_mode_combo = QComboBox()
        self.presentation_mode_combo.addItem(_("Standard"), presentation.MODE_STANDARD)
        self.presentation_mode_combo.addItem(_("Rich text"), presentation.MODE_RICH)
        self.presentation_mode_combo.setToolTip(
            _("Rich text draws each value in bold with a smaller, dimmed prefix and suffix.")
        )
        self.presentation_mode_combo.currentIndexChanged.connect(self._on_presentation_mode_changed)
        grid.addWidget(QLabel(_("Mode:")), 0, 0)
        grid.addWidget(self.presentation_mode_combo, 0, 1)

        self.font_size_label = QLabel(_("Font size:"))
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(0, presentation.FONT_SIZE_MAX)
        self.font_size_spin.setSuffix(_(" pt"))
        self.font_size_spin.setToolTip(
            _("Point size of this profile's cells. The lowest value uses the HUD window's size.")
        )
        self.font_size_spin.valueChanged.connect(self._on_presentation_font_size_changed)
        grid.addWidget(self.font_size_label, 1, 0)
        grid.addWidget(self.font_size_spin, 1, 1)

        # xpad / ypad: pixels the HUD adds to its default gaps (#770).
        self.padding_labels: dict[str, QLabel] = {}
        self.padding_spins: dict[str, QSpinBox] = {}
        for offset, (attr, label, tip) in enumerate(
            (
                ("xpad", _("Column gap:"), _("Pixels added to the HUD's default gap between columns.")),
                ("ypad", _("Row gap:"), _("Pixels added to the HUD's default gap between rows.")),
            )
        ):
            spin = QSpinBox()
            spin.setRange(0, presentation.PADDING_MAX)
            spin.setPrefix("+")
            spin.setSuffix(_(" px"))
            spin.setToolTip(tip)
            spin.valueChanged.connect(partial(self._on_presentation_padding_changed, attr))
            caption = QLabel(label)
            caption.setToolTip(tip)
            grid.addWidget(caption, 2 + offset, 0)
            grid.addWidget(spin, 2 + offset, 1)
            self.padding_labels[attr] = caption
            self.padding_spins[attr] = spin

        self.hud_handler_label = QLabel()
        self.hud_handler_label.setWordWrap(True)
        self.hud_handler_label.setProperty("class", "caption")
        grid.addWidget(self.hud_handler_label, 4, 0, 1, 2)

        self.rich_text_support_label = QLabel()
        self.rich_text_support_label.setWordWrap(True)
        self.rich_text_support_label.setProperty("class", "caption")
        self.rich_text_support_label.hide()
        grid.addWidget(self.rich_text_support_label, 5, 0, 1, 2)

        grid.setColumnStretch(1, 1)
        self._loading_presentation = False
        self._presentation_handlers: list[presentation.HandlerUse] = []
        return box

    def _profile_handlers(self, name: str) -> list[presentation.HandlerUse]:
        return presentation.hud_handlers_for(getattr(self, "config", None), name)

    def _profile_preview_params(self, name: str, profile: Any) -> dict[str, Any]:
        """The preview's HUD parameters, with this profile's mode and font size."""
        params: dict[str, Any] = dict(self._hud_preview_params())
        size = presentation.font_size_of(profile)
        if not size:
            try:
                fallback = int(params.get("font_size") or 8)
            except (TypeError, ValueError):
                fallback = 8
            size = presentation.handler_font_size(self._profile_handlers(name), fallback)
        params["font_size"] = size
        params["rich_text"] = presentation.mode_of(profile) == presentation.MODE_RICH
        return params

    def _describe_handlers(self, uses: list[presentation.HandlerUse]) -> str:
        if not uses:
            return _(
                "HUD window: no game is mapped to this profile (a profile rule may still pick it). "
                "The window handler is set per game, not here."
            )
        handlers = "; ".join(f"{use.name} ({', '.join(use.games)})" for use in uses)
        return _("HUD window: {handlers}. The window handler is set per game, not here.").format(handlers=handlers)

    def _load_presentation_controls(self, name: str, profile: Any) -> None:
        """Show ``profile``'s presentation settings without marking an edit."""
        if getattr(self, "presentation_box", None) is None:
            return
        uses = self._profile_handlers(name)
        self._presentation_handlers = uses
        default_size = self._profile_preview_params(name, {})["font_size"]
        self._loading_presentation = True
        try:
            mode = presentation.mode_of(profile)
            self.presentation_mode_combo.setCurrentIndex(max(0, self.presentation_mode_combo.findData(mode)))
            self.font_size_spin.setSpecialValueText(_("Default ({size} pt)").format(size=default_size))
            size = presentation.font_size_of(profile)
            # A size above the usual bound is still one the HUD draws: widen the
            # range rather than show (and later save) a clamped value.
            self.font_size_spin.setMaximum(max(presentation.FONT_SIZE_MAX, size))
            self.font_size_spin.setValue(size)
            for attr, spin in self.padding_spins.items():
                pixels = presentation.padding_of(profile, attr)
                spin.setMaximum(max(presentation.PADDING_MAX, pixels))
                spin.setValue(pixels)
        finally:
            self._loading_presentation = False
        self.hud_handler_label.setText(self._describe_handlers(uses))
        self.presentation_box.setEnabled(isinstance(profile, dict))
        self._apply_presentation_visibility(mode)
        self._refresh_presentation_summary()

    def _refresh_presentation_summary(self) -> None:
        """Say in the folded section's header what the presentation is set to."""
        section = getattr(self, "presentation_section", None)
        if section is None:
            return
        parts = [self.presentation_mode_combo.currentText()]
        if not self.font_size_spin.isHidden():
            parts.append(self.font_size_spin.text())
        section.set_summary(" · ".join(part for part in parts if part))

    def _apply_presentation_visibility(self, mode: str) -> None:
        """Hide what has no effect in ``mode``."""
        fields = presentation.visible_fields(mode)
        self.font_size_label.setVisible("font_size" in fields)
        self.font_size_spin.setVisible("font_size" in fields)
        for attr, spin in self.padding_spins.items():
            self.padding_labels[attr].setVisible(attr in fields)
            spin.setVisible(attr in fields)
        plain = presentation.handlers_without_rich_text(self._presentation_handlers)
        show_support = "rich_text_support" in fields and bool(plain)
        if show_support:
            self.rich_text_support_label.setText(
                _("Only {rich} draws rich text: {handlers} will show this profile as standard text.").format(
                    rich=presentation.RICH_TEXT_CLASS, handlers=", ".join(plain)
                )
            )
        self.rich_text_support_label.setVisible(show_support)

    def _edited_presentation_profile(self) -> tuple[str, dict[str, Any]] | None:
        """The current profile, unless the controls are only being loaded."""
        if getattr(self, "_loading_presentation", False):
            return None
        name = self.profile_combo.currentText()
        profile = self.hud_profiles.get(name) if self.hud_profiles else None
        return (name, profile) if isinstance(profile, dict) else None

    def _on_presentation_mode_changed(self, _index: int) -> None:
        """Store the mode alone: the other fields keep what they hold."""
        edited = self._edited_presentation_profile()
        if edited is None:
            return
        mode = self.presentation_mode_combo.currentData() or presentation.MODE_STANDARD
        presentation.set_mode(edited[1], mode)
        self._apply_presentation_visibility(mode)
        self._redraw_presentation_preview(*edited)

    def _on_presentation_font_size_changed(self, value: int) -> None:
        """Store the font size alone."""
        edited = self._edited_presentation_profile()
        if edited is None:
            return
        presentation.set_font_size(edited[1], value)
        self._redraw_presentation_preview(*edited)

    def _on_presentation_padding_changed(self, attr: str, value: int) -> None:
        """Store one of the two paddings alone."""
        edited = self._edited_presentation_profile()
        if edited is None:
            return
        presentation.set_padding(edited[1], attr, value)
        self._redraw_presentation_preview(*edited)

    def _redraw_presentation_preview(self, name: str, profile: dict[str, Any]) -> None:
        """Redraw the preview after an edit and update the "unsaved changes" mark."""
        self.preview.set_hud_params(
            xpad=profile.get("xpad", 0),
            ypad=profile.get("ypad", 0),
            **self._profile_preview_params(name, profile),
        )
        self._refresh_presentation_summary()
        self._refresh_unsaved_indicator()
        self._record_history()

    def on_profile_selected(self, index) -> None:
        if index < 0 or index >= self.profile_combo.count():
            self._selected_item = None
            self.preview.set_stats([])
            self.update_status()
            return
        name = self.profile_combo.currentText()
        profile = self.hud_profiles.get(name, {})
        # The history starts from the profile as first shown, before any edit.
        self._history(profile)
        self._refresh_panel_stat_blocks()

        # Reflect this profile's positional-panel mode in the combo (multi-block
        # only). Block the signal so setting it here doesn't mark a fake edit.
        # Guarded: some code paths build a bare dialog without this control.
        if getattr(self, "positional_mode_combo", None) is not None:
            is_multiblock = isinstance(profile, dict) and profile.get("multiblock")
            self.positional_mode_combo.setEnabled(bool(is_multiblock))
            self.positional_mode_label.setEnabled(bool(is_multiblock))
            mode = profile.get("positional_mode", "current") if isinstance(profile, dict) else "current"
            self.positional_mode_combo.blockSignals(True)
            self.positional_mode_combo.setCurrentIndex(max(0, self.positional_mode_combo.findData(mode)))
            self.positional_mode_combo.blockSignals(False)

        if getattr(self, "show_hero_checkbox", None) is not None:
            # Interpret the stored value; empty defaults to hidden for multi-block
            # HUDs (their convention) and shown otherwise.
            raw = str(profile.get("show_hero_hud", "")).strip().lower() if isinstance(profile, dict) else ""
            if raw in ("true", "yes", "1", "on"):
                show_hero = True
            elif raw in ("false", "no", "0", "off"):
                show_hero = False
            else:
                show_hero = profile_io.hero_shown_by_default(profile)
            self.show_hero_checkbox.blockSignals(True)
            self.show_hero_checkbox.setChecked(show_hero)
            self.show_hero_checkbox.blockSignals(False)

        # Handle both old format (list) and new format (dict with rows/cols/stats)
        if isinstance(profile, list):
            # Old format - just a list of stats
            stats = profile
            rows = 5
            cols = 5
            xpad = ypad = 0
        else:
            # New format - dict with rows, cols, stats
            stats = profile.get("stats", [])
            rows = profile.get("rows", 5)
            cols = profile.get("cols", 5)
            xpad = profile.get("xpad", 0)
            ypad = profile.get("ypad", 0)

        self._load_presentation_controls(name, profile)

        # Update grid size
        self.preview.set_hud_params(xpad=xpad, ypad=ypad, **self._profile_preview_params(name, profile))
        self.preview.set_grid(rows, cols)

        # Multi-panel profile -> render stacked, coloured, titled boxes; otherwise
        # the classic single grid. Never let a preview failure leave it blank:
        # fall back to the flat grid, then to an empty grid, logging the cause.
        blocks = profile.get("blocks") if isinstance(profile, dict) else None
        try:
            if blocks:
                self.preview.set_blocks(blocks)
            else:
                self.preview.set_stats(stats)
        except Exception:
            log.exception("HUD preview rendering failed; falling back to flat grid")
            try:
                self.preview.set_stats(stats)
            except Exception:
                log.exception("HUD preview flat fallback also failed")
                self.preview.set_stats([])
        # PT4-style design canvas (chip grid per panel).
        try:
            self._rebuild_design_canvas(profile)
        except Exception:
            log.exception("HUD design canvas rebuild failed")
        # PT4-style panel list + Group Properties.
        try:
            if hasattr(self, "group_list"):
                self._populate_group_list(profile)
        except Exception:
            log.exception("HUD group list rebuild failed")
        self.update_status()
        self._refresh_history_buttons()

    def _rebuild_design_canvas(self, profile) -> None:
        """Render the design canvas for the *currently selected* panel only.

        Mirrors PT4: clicking a panel in the Panels list shows that panel's grid
        on the canvas (box-by-box), not every panel stacked. The live preview
        (right) still shows the whole HUD.
        """
        if not hasattr(self, "_design_layout"):
            return
        # A keyboard edit redraws the canvas: the new one takes the focus back so
        # the next arrow, Alt+arrow or Delete still reaches it.
        focused = QApplication.focusWidget()
        had_focus = focused is not None and any(
            old is focused or old.isAncestorOf(focused) for old in getattr(self, "_design_canvases", [])
        )
        # Clear previous canvas. Detach AND delete so an old canvas never lingers
        # as a stray top-level window (setParent(None) alone leaves it floating).
        self._design_canvases = []
        while self._design_layout.count():
            item = self._design_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                # Hidden first: the show a layout queues for a widget just added
                # would otherwise pop the detached canvas up as its own window.
                w.hide()
                w.setParent(None)
                w.deleteLater()
        blocks = profile.get("blocks") if isinstance(profile, dict) else None
        if blocks:
            bi = self._current_block_index if 0 <= self._current_block_index < len(blocks) else 0
            block = blocks[bi]
            canvas_index = bi
        else:
            # The profile itself: what the canvas shows is what an edit changes.
            block = self._item_container(profile, None)
            canvas_index = 0
        # Keep the section header in sync with the selected panel.
        if hasattr(self, "design_label"):
            label = block.get("label", "")
            self.design_label.setText(_("Design — {label}").format(label=label) if label else _("Design"))
        canvas = HudDesignCanvas(editable=True)
        canvas.selected_ref = self._selected_item
        canvas.set_block(canvas_index, block)
        canvas.item_selected.connect(self._on_canvas_item_selected)
        canvas.item_moved.connect(self._canvas_item_moved)
        canvas.stat_dropped.connect(self._canvas_stat_dropped)
        canvas.item_removed.connect(self._canvas_item_removed)
        canvas.item_activated.connect(self._canvas_item_activated)
        canvas.grid_edit.connect(self._canvas_grid_edit)
        canvas.drop_refused.connect(self._show_status)
        self._design_layout.addWidget(canvas)
        self._design_canvases.append(canvas)
        self._design_layout.addStretch()
        if had_focus:
            # A widget added to a shown layout appears only later, and a hidden
            # one cannot take the focus.
            canvas.show()
            canvas.setFocus(Qt.FocusReason.OtherFocusReason)

    def _refresh_profile(self, select: dict | None = None, *, record: bool = True) -> None:
        """Redraw the current profile after an edit, keeping the selection (B11).

        ``select`` makes another item the selection, typically the one just
        added. The panel that holds the selected item is shown, and the item is
        selected again by identity once the views are rebuilt.
        """
        if select is not None:
            self._selected_item = select
        _name, profile = self._current_profile()
        where = editor_state.locate(profile, self._selected_item)
        if where is not None and where[0] is not None:
            self._current_block_index = where[0]
        self.on_profile_selected(self.profile_combo.currentIndex())
        if record:
            self._record_history()
        else:
            self._refresh_history_buttons()

    def _select_item(self, ref) -> None:
        """Make ``ref`` the selection: the canvas marks it, Item Properties shows it."""
        if ref is None or ref is self._selected_item:
            return
        _name, profile = self._current_profile()
        where = editor_state.locate(profile, ref)
        if where is None:
            return
        self._selected_item = ref
        block_index, kind = where
        if block_index is not None and block_index != self._current_block_index and hasattr(self, "group_list"):
            # Showing another panel redraws the canvas, which marks the item.
            self.group_list.setCurrentRow(block_index)
            return
        self._show_selected_item(kind, ref)

    def _on_canvas_item_selected(self, payload) -> None:
        """A chip was clicked -> it becomes the selection everywhere."""
        _bi, _kind, ref = payload
        self._select_item(ref)

    # --- Design canvas edits (#775) ------------------------------------------
    def _shown_container(self):
        """The panel the Design canvas shows, as ``(profile, container)``."""
        _name, profile = self._current_profile()
        if profile is None:
            return None, None
        blocks = profile.get("blocks") if isinstance(profile, dict) else None
        block_index = min(max(self._current_block_index, 0), len(blocks) - 1) if blocks else None
        return profile, self._item_container(profile, block_index)

    def _canvas_item_moved(self, ref, row: int, col: int) -> None:
        """A chip was dropped on a cell, or moved with Alt+arrow."""
        _profile, container = self._shown_container()
        if container is None:
            return
        if layout_model.move(container, ref, row, col) == "refused":
            self._show_status(_("No room there: the items would overlap."))
            return
        self._refresh_profile(select=ref)

    def _canvas_stat_dropped(self, key: str, row: int, col: int) -> None:
        """A stat of Available Stats was dropped on a cell."""
        entry = self._stat_catalog().get(key)
        _profile, container = self._shown_container()
        if entry is None or container is None:
            return
        stat = entry.new_item(row, col)
        if "default" in self._popup_names():
            stat["popup"] = "default"
        if not layout_model.add(container, "stat", stat, row, col):
            self._show_status(_("Cell already used: drop the stat on an empty cell."))
            return
        self._refresh_profile(select=stat)

    def _canvas_item_removed(self, ref) -> None:
        """Delete on the canvas: the selected item goes."""
        _profile, container = self._shown_container()
        if container is None or not layout_model.remove(container, ref):
            return
        self._selected_item = None
        self._refresh_profile()

    def _canvas_item_activated(self, ref) -> None:
        """Double-click or Enter on a chip: edit it."""
        self._select_item(ref)
        self.edit_stat()

    def _canvas_grid_edit(self, operation: str, index: int) -> None:
        """Insert or delete a row or column of the shown panel; -1 is past the last one."""
        _profile, container = self._shown_container()
        if container is None or operation not in ("insert_row", "insert_col", "delete_row", "delete_col"):
            return
        if index < 0:
            index = int(container.get("rows" if operation == "insert_row" else "cols", 1) or 1)
        if not getattr(layout_model, operation)(container, index):
            self._show_status(_("Only an empty row or column can be deleted."))
            return
        self._refresh_profile()

    def _show_status(self, text: str) -> None:
        """A message in the status bar, until the next redraw."""
        label = getattr(self, "status_label", None)
        if label is not None and text:
            label.setText(text)

    # --- Undo and redo (#775) ------------------------------------------------
    def _history(self, profile) -> undo.History | None:
        """The history of a profile, started from how it is now.

        Histories follow the profile dict, not its name: a rename keeps them,
        and a profile deleted, reloaded or created again under the same name
        starts afresh. Each entry holds its profile so its id is never reused.
        """
        if not isinstance(profile, dict):
            return None
        histories = self.__dict__.setdefault("_histories", {})
        entry = histories.get(id(profile))
        if entry is None or entry[0] is not profile:
            entry = histories[id(profile)] = (profile, undo.History(profile))
        return entry[1]

    def _forget_history(self, profile) -> None:
        self.__dict__.get("_histories", {}).pop(id(profile), None)

    def _record_history(self) -> None:
        """Note the current profile as a step to undo, if it changed."""
        _name, profile = self._current_profile()
        history = self._history(profile)
        if history is not None:
            history.record(profile)
        self._refresh_history_buttons()

    def _refresh_history_buttons(self) -> None:
        _name, profile = self._current_profile()
        history = self._history(profile)
        for button, enabled in (
            (getattr(self, "undo_btn", None), history is not None and history.can_undo),
            (getattr(self, "redo_btn", None), history is not None and history.can_redo),
        ):
            if button is not None:
                button.setEnabled(bool(enabled))

    def _restore_profile(self, state) -> None:
        """Put a state of the history back, keeping the profile dict itself."""
        name, profile = self._current_profile()
        path = editor_state.item_path(profile, self._selected_item)
        profile.clear()
        profile.update(state)
        self._selected_item = editor_state.item_at(profile, path)
        self._refresh_profile(record=False)

    def undo_edit(self) -> None:
        _name, profile = self._current_profile()
        history = self._history(profile)
        state = history.undo(profile) if history is not None else None
        if state is None:
            self._show_status(_("Nothing to undo."))
            return
        self._restore_profile(state)

    def redo_edit(self) -> None:
        _name, profile = self._current_profile()
        history = self._history(profile)
        state = history.redo(profile) if history is not None else None
        if state is None:
            self._show_status(_("Nothing to redo."))
            return
        self._restore_profile(state)

    # --- PT4-style group (panel) list + Group Properties -----------------
    def _group_color_btn(self, attr: str) -> QPushButton:
        btn = QPushButton(_("(none)"))
        btn.setFixedHeight(24)
        btn.clicked.connect(lambda _=False, a=attr: self._pick_group_color(a))
        if not hasattr(self, "_group_color_btns"):
            self._group_color_btns = {}
        self._group_color_btns[attr] = btn
        return btn

    @staticmethod
    def _style_color_btn(btn: QPushButton, colour: str) -> None:
        btn.setText(colour or _("(none)"))
        btn.setStyleSheet(f"background:{colour};" if colour else "")

    @staticmethod
    def _rgb_of(colour: str) -> tuple[int, int, int]:
        c = (colour or "").strip()
        if c.startswith("rgba") or c.startswith("rgb"):
            nums = [int(float(x)) for x in c[c.find("(") + 1 : c.find(")")].split(",")[:3]]
            if len(nums) == 3:
                return tuple(nums)  # type: ignore[return-value]
        if c.startswith("#") and len(c) >= 7:
            return int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)
        return 0, 0, 0

    @staticmethod
    def _opacity_of(colour: str):
        c = (colour or "").strip()
        if c.startswith("rgba"):
            parts = c[c.find("(") + 1 : c.find(")")].split(",")
            if len(parts) == 4:
                try:
                    return int(float(parts[3]))
                except ValueError:
                    return None
        return None

    def _populate_group_list(self, profile) -> None:
        self._loading_group = True
        self.group_list.clear()
        self.group_list.addItems(editor_state.panel_labels(profile))
        count = self.group_list.count()
        bi = self._current_block_index if 0 <= self._current_block_index < count else 0
        self.group_list.setCurrentRow(bi)
        self._loading_group = False
        self._on_group_selected(bi)

    def _show_group_props(self, shown: bool) -> None:
        """Group Properties holds a panel's settings: none for a single grid (#780)."""
        self.group_props_box.setEnabled(shown)
        self.group_props_box.setVisible(shown)

    def _on_group_selected(self, row) -> None:
        if row is None or row < 0:
            self._show_group_props(False)
            return
        self._current_block_index = row
        _name, profile = self._current_profile()
        blocks = profile.get("blocks") if isinstance(profile, dict) else None
        if blocks and row < len(blocks):
            self._show_group_props(True)
            self._load_group_props(blocks[row])
            self._sync_item_selection(blocks[row])
        else:
            self._show_group_props(False)
            flat = {"stats": profile.get("stats", []) if isinstance(profile, dict) else [], "texts": [], "hlines": []}
            self._sync_item_selection(flat)
        # Show the selected panel's grid on the design canvas + preview (box-by-box).
        if profile is not None:
            try:
                self._rebuild_design_canvas(profile)
            except Exception:
                log.exception("design canvas rebuild on panel select failed")
            self._preview_selected_block()

    def _load_group_props(self, block: dict) -> None:
        self._loading_group = True
        self.gp_name.setText(block.get("label", ""))
        idx = self.gp_position.findText(block.get("position", ""))
        self.gp_position.setCurrentIndex(idx if idx >= 0 else 0)
        for attr, btn in getattr(self, "_group_color_btns", {}).items():
            self._style_color_btn(btn, block.get(attr, ""))
        op = self._opacity_of(block.get("bgcolor", ""))
        self.gp_opacity.setValue(op if op is not None else 178)
        self._loading_group = False

    def _selected_block(self):
        _name, profile = self._current_profile()
        blocks = profile.get("blocks") if isinstance(profile, dict) else None
        bi = self._current_block_index
        if blocks and 0 <= bi < len(blocks):
            return bi, blocks[bi]
        return None, None

    def _pick_group_color(self, attr: str) -> None:

        _bi, block = self._selected_block()
        if block is None:
            return
        initial = QColor(*self._rgb_of(block.get(attr, "")))
        col = QColorDialog.getColor(initial, self, _("Pick colour"))
        if not col.isValid():
            return
        if attr == "bgcolor":
            r, g, b, _a = col.getRgb()
            block[attr] = f"rgba({r}, {g}, {b}, {self.gp_opacity.value()})"
        else:
            block[attr] = col.name()
        self._style_color_btn(self._group_color_btns[attr], block[attr])
        self._refresh_after_group_edit()

    def _group_prop_changed(self) -> None:
        if self._loading_group:
            return
        _bi, block = self._selected_block()
        if block is None:
            return
        block["label"] = self.gp_name.text()
        block["position"] = self.gp_position.currentText()
        self._refresh_after_group_edit()

    def _group_opacity_changed(self) -> None:
        """The opacity slider: the alpha of the panel background, and only that."""
        if self._loading_group:
            return
        _bi, block = self._selected_block()
        if block is None:
            return
        r, g, b = self._rgb_of(block.get("bgcolor", ""))
        block["bgcolor"] = f"rgba({r}, {g}, {b}, {self.gp_opacity.value()})"
        self._refresh_after_group_edit()

    def _refresh_after_group_edit(self) -> None:
        """Light refresh after editing a group: list label + canvas + preview,
        without rebuilding the table or resetting the group selection."""
        _name, profile = self._current_profile()
        item = self.group_list.currentItem()
        labels = editor_state.panel_labels(profile)
        row = self.group_list.currentRow()
        if item is not None and 0 <= row < len(labels):
            # From the profile, not the name field: a flat profile has no
            # panel name, and its entry stays "(single grid)" (B12).
            item.setText(labels[row])
        try:
            self._rebuild_design_canvas(profile)
        except Exception:
            log.exception("design canvas refresh failed")
        self._preview_selected_block()
        self.update_status()
        self._record_history()

    def _preview_selected_block(self) -> None:
        """Show only the selected panel in the HUD preview (matches the canvas)."""
        _name, profile = self._current_profile()
        blocks = profile.get("blocks") if isinstance(profile, dict) else None
        try:
            if blocks:
                bi = self._current_block_index if 0 <= self._current_block_index < len(blocks) else 0
                self.preview.set_blocks([blocks[bi]])
            else:
                self.preview.set_stats(profile.get("stats", []) if isinstance(profile, dict) else [])
        except Exception:
            log.exception("preview refresh failed")

    def _group_new(self) -> None:
        self.add_block()
        _name, profile = self._current_profile()
        blocks = profile.get("blocks") if isinstance(profile, dict) else None
        if blocks:
            self._current_block_index = len(blocks) - 1
            self.group_list.setCurrentRow(self._current_block_index)

    def _group_delete(self) -> None:
        _name, profile = self._current_profile()
        blocks = profile.get("blocks") if isinstance(profile, dict) else None
        bi = self._current_block_index
        if not blocks or not (0 <= bi < len(blocks)):
            return
        if len(blocks) <= 1:
            QMessageBox.information(self, _("Delete Panel"), _("A profile needs at least one panel."))
            return
        del blocks[bi]
        self._current_block_index = max(0, bi - 1)
        self._refresh_profile()

    # --- PT4-style Group Items list + Item Properties --------------------
    def _item_color_btn(self, role: str) -> QPushButton:
        btn = QPushButton(_("(none)"))
        btn.setFixedHeight(24)
        btn.clicked.connect(lambda _=False, r=role: self._pick_item_color(r))
        if not hasattr(self, "_item_color_btns"):
            self._item_color_btns = {}
        self._item_color_btns[role] = btn
        return btn

    @staticmethod
    def _set_combo(combo: QComboBox, text: str) -> None:
        idx = combo.findText(text or "center")
        combo.setCurrentIndex(idx if idx >= 0 else 0)

    @staticmethod
    def _item_color_key(kind: str, role: str):
        if kind == "stat":
            return {
                "fg": "hudcolor",
                "bg": "hudbgcolor",
                "lo": "stat_locolor",
                "mid": "stat_midcolor",
                "hi": "stat_hicolor",
            }.get(role)
        if kind == "text":
            return {"fg": "fgcolor", "bg": "bgcolor"}.get(role)
        if kind == "hline":
            return {"bg": "color"}.get(role)
        return None

    def _item_threshold_input(self) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setDecimals(stat_edit.DECIMALS)
        spin.setRange(stat_edit.MINIMUM, stat_edit.MAXIMUM)
        spin.valueChanged.connect(lambda _v: self._item_prop_changed())
        return spin

    def _item_threshold_values(self) -> dict:
        """``stat_loth`` / ``stat_hith`` as the Color Ranges tab now reads them."""
        return stat_edit.threshold_values(
            self._item_thresholds_original,
            self.ip_use_thresholds.isChecked(),
            self._item_thresholds_shown,
            (self.ip_loth.value(), self.ip_hith.value()),
        )

    def _enable_item_thresholds(self, is_stat: bool) -> None:
        on = is_stat and self.ip_use_thresholds.isChecked()
        self.ip_use_thresholds.setEnabled(is_stat)
        for w in (self.ip_loth, self.ip_hith, self.ip_locolor, self.ip_midcolor, self.ip_hicolor):
            w.setEnabled(on)

    def _item_thresholds_toggled(self, checked: bool) -> None:
        self._enable_item_thresholds(True)
        if self._loading_item:
            return
        kind, ref = self._current_item()
        if kind == "stat" and checked:
            # A colour range needs its two colours: give a stat that has none
            # the usual red and green, as the Edit Stat dialog does.
            for role, key, colour in (
                ("lo", "stat_locolor", stat_edit.DEFAULT_LOW_COLOR),
                ("hi", "stat_hicolor", stat_edit.DEFAULT_HIGH_COLOR),
            ):
                if not ref.get(key):
                    ref[key] = colour
                    self._style_color_btn(self._item_color_btns[role], colour)
        self._item_prop_changed()

    def _sync_item_selection(self, block) -> None:
        """Keep the selection when the shown panel holds it, else select its first item."""
        items = sorted(
            layout_model.items(block or {}),
            key=lambda found: layout_model.position(found[0], found[1]),
        )
        keep = next(((kind, ref) for kind, ref in items if ref is self._selected_item), None)
        if keep is None and items:
            keep = items[0]
        if keep is None:
            self._selected_item = None
            if self._has_item_props():
                self._clear_item_props()
            return
        self._selected_item = keep[1]
        self._show_selected_item(*keep)

    def _current_item(self):
        """``(kind, ref)`` of the selected item; ``(None, None)`` when there is none."""
        _name, profile = self._current_profile()
        where = editor_state.locate(profile, self._selected_item)
        if where is None:
            return None, None
        return where[1], self._selected_item

    def _has_item_props(self) -> bool:
        """False for a dialog built without the Item Properties form (headless tests)."""
        return getattr(self, "ip_text", None) is not None

    def _show_selected_item(self, kind: str, ref: dict) -> None:
        """Show the selected item in Item Properties and mark it on the canvas."""
        if self._has_item_props():
            self._load_item_props(kind, ref)
        for cv in getattr(self, "_design_canvases", []):
            cv.select_ref(ref)

    def _clear_item_props(self) -> None:
        self._loading_item = True
        self.ip_text.clear()
        self.ip_popup.clear()
        if getattr(self, "ip_stat", None) is not None:
            self.ip_stat.setCurrentText("")
        for btn in getattr(self, "_item_color_btns", {}).values():
            self._style_color_btn(btn, "")
        self._loading_item = False

    def _load_item_props(self, kind: str, ref: dict) -> None:
        self._loading_item = True
        for w in (self.ip_text, self.ip_popup, self.ip_align, self.ip_colspan, self.ip_fg, self.ip_bg):
            w.setEnabled(True)
        self._show_stat_or_text_row(kind == "stat")
        # Keep the Color Ranges tab itself clickable; only its controls are
        # stat-specific (disabled for text/line items, which have no thresholds).
        is_stat = kind == "stat"
        self.item_props_tabs.setTabEnabled(1, True)
        if not is_stat:
            self.ip_use_thresholds.setChecked(False)
            for v in (self.ip_loth, self.ip_hith):
                v.setValue(0)
            for b in (self.ip_locolor, self.ip_midcolor, self.ip_hicolor):
                self._style_color_btn(b, "")
        if kind == "stat":
            if getattr(self, "ip_stat", None) is not None:
                self.ip_stat.show_item(ref)
            self.ip_text.setText(ref.get("stat", ""))
            self._show_popup(ref.get("popup", ""))
            self.ip_colspan.setValue(int(ref.get("colspan", 1) or 1))
            self._set_combo(self.ip_align, ref.get("align", "center"))
            self._style_color_btn(self.ip_fg, ref.get("hudcolor", ""))
            self._style_color_btn(self.ip_bg, ref.get("hudbgcolor", ""))
            self.ip_use_thresholds.setChecked(stat_edit.has_thresholds(ref))
            self.ip_loth.setValue(stat_edit.shown_value(ref.get("stat_loth"), stat_edit.DEFAULT_LOW))
            self.ip_hith.setValue(stat_edit.shown_value(ref.get("stat_hith"), stat_edit.DEFAULT_HIGH))
            self._item_thresholds_original = {key: ref.get(key, "") for key in stat_edit.THRESHOLD_KEYS}
            self._item_thresholds_shown = (self.ip_loth.value(), self.ip_hith.value())
            self._item_thresholds_at_load = self._item_threshold_values()
            self._style_color_btn(self.ip_locolor, ref.get("stat_locolor", ""))
            self._style_color_btn(self.ip_midcolor, ref.get("stat_midcolor", ""))
            self._style_color_btn(self.ip_hicolor, ref.get("stat_hicolor", ""))
        elif kind == "text":
            self.ip_text.setText(ref.get("label", ""))
            self._show_popup("")
            self.ip_popup.setEnabled(False)
            self.ip_colspan.setValue(int(ref.get("colspan", 1) or 1))
            self._set_combo(self.ip_align, ref.get("align", "center"))
            self._style_color_btn(self.ip_fg, ref.get("fgcolor", ""))
            self._style_color_btn(self.ip_bg, ref.get("bgcolor", ""))
        else:  # hline
            self.ip_text.setText(_("Horz Line"))
            self.ip_text.setEnabled(False)
            self._show_popup("")
            self.ip_popup.setEnabled(False)
            self.ip_align.setEnabled(False)
            self.ip_colspan.setValue(max(1, int(ref.get("colspan", 0) or 1)))
            self._style_color_btn(self.ip_fg, "")
            self._style_color_btn(self.ip_bg, ref.get("color", ""))
        self._enable_item_thresholds(is_stat)
        self._loading_item = False

    def _item_prop_changed(self) -> None:
        if self._loading_item:
            return
        kind, ref = self._current_item()
        if ref is None:
            return
        if kind == "stat":
            if not self._apply_item_stat(ref):
                return
            stat_edit.apply_changes(ref, {"popup": self._popup_value()})
            self._apply_item_layout(ref)
            stat_edit.apply_changes(
                ref,
                stat_edit.edit_target(
                    self._item_thresholds_original, self._item_thresholds_at_load, self._item_threshold_values()
                ),
            )
        elif kind == "text":
            ref["label"] = self.ip_text.text()
            self._apply_item_layout(ref)
        else:  # hline
            ref["colspan"] = self.ip_colspan.value()
        self._refresh_after_group_edit()

    def _apply_item_layout(self, ref: dict) -> None:
        """Write the span and alignment only when they differ from what the item draws.

        A field left without a change (focus moving through the form) must not
        add ``colspan="1"`` or ``align="center"`` and count as an unsaved edit.
        """
        if self.ip_colspan.value() != int(ref.get("colspan", 1) or 1):
            ref["colspan"] = self.ip_colspan.value()
        if self.ip_align.currentText() != (ref.get("align") or "center"):
            ref["align"] = self.ip_align.currentText()

    # --- Stat and popup lists (B15) ----------------------------------------
    def _stat_catalog(self) -> stat_catalog.StatCatalog:
        """The catalogue of stats, built once per dialog."""
        catalog = getattr(self, "_catalog", None)
        if catalog is None:
            catalog = stat_catalog.build_catalog()
            self._catalog = catalog
        return catalog

    def _popup_names(self) -> list[str]:
        return sorted(getattr(self, "popup_windows", None) or {})

    def _stat_dialog_lists(self) -> dict[str, Any]:
        """What Add/Edit Statistic offers: the catalogue and the configuration's popups."""
        return {"catalog": self._stat_catalog(), "popup_names": self._popup_names()}

    def _show_stat_or_text_row(self, is_stat: bool) -> None:
        """A stat shows the Statistic list, a label or line the Text field."""
        form = getattr(self, "item_props_form", None)
        if form is None or getattr(self, "ip_stat", None) is None:
            return
        form.setRowVisible(self.ip_stat, is_stat)
        form.setRowVisible(self.ip_text, not is_stat)

    def _show_popup(self, current: str) -> None:
        if isinstance(self.ip_popup, PopupChoiceCombo):
            self.ip_popup.set_options(self._popup_names(), current)
        else:
            self.ip_popup.setText(current)

    def _popup_value(self) -> str:
        if isinstance(self.ip_popup, PopupChoiceCombo):
            return self.ip_popup.value()
        return self.ip_popup.text()

    def _apply_item_stat(self, ref: dict) -> bool:
        """Write the Statistic list's choice into the stat; False when it names no stat.

        A name the catalogue lacks is refused and the list shows the stat again,
        unless it is the name the stat already had, which is kept as it is.
        """
        combo = getattr(self, "ip_stat", None)
        if combo is None:
            return True
        entry = combo.chosen_entry()
        if entry is not None:
            # The same stat again (focus left the list, say) keeps the cell's own
            # data_* values: an analytics cell may carry its own format.
            if entry != self._stat_catalog().entry_for_item(ref):
                stat_edit.apply_changes(ref, stat_catalog.stat_values(entry))
            return True
        typed = combo.currentText().strip()
        if typed == ref.get("stat", ""):
            return True
        self._loading_item = True
        try:
            combo.show_item(ref)
        finally:
            self._loading_item = False
        self.status_label.setText(
            _("There is no statistic called \"{name}\". Pick one from the list.").format(name=typed)
        )
        return False

    def _add_catalog_stat(self, key: str) -> None:
        """Put the catalogue's stat in the first free cell of the panel shown in Design."""
        entry = self._stat_catalog().get(key)
        name, profile = self._current_profile()
        if entry is None or profile is None:
            return
        blocks = profile.get("blocks") if isinstance(profile, dict) else None
        block_index = min(max(self._current_block_index, 0), len(blocks) - 1) if blocks else None
        container = self._item_container(profile, block_index)
        row, col = layout_model.first_free_cell(container)
        stat = entry.new_item(row, col)
        if "default" in self._popup_names():
            stat["popup"] = "default"
        layout_model.add(container, "stat", stat, row, col)
        self._refresh_profile(select=stat)

    def _pick_item_color(self, role: str) -> None:

        kind, ref = self._current_item()
        if ref is None:
            return
        key = self._item_color_key(kind, role)
        if key is None:
            return
        current = ref.get(key, "")
        col = QColorDialog.getColor(QColor(current) if current else QColor("#ffffff"), self, _("Pick colour"))
        if not col.isValid():
            return
        ref[key] = col.name()
        self._style_color_btn(self._item_color_btns[role], col.name())
        self._refresh_after_group_edit()

    def add_profile(self) -> None:
        # Create custom dialog for profile creation
        dialog = QDialog(self)
        dialog.setWindowTitle(_("New Profile"))
        layout = QFormLayout(dialog)

        # Name input
        name_input = QLineEdit()
        layout.addRow(_("Profile name:"), name_input)

        # Rows input
        rows_input = QSpinBox()
        rows_input.setMinimum(1)
        rows_input.setMaximum(10)
        rows_input.setValue(3)
        layout.addRow(_("Rows:"), rows_input)

        # Columns input
        cols_input = QSpinBox()
        cols_input.setMinimum(1)
        cols_input.setMaximum(10)
        cols_input.setValue(2)
        layout.addRow(_("Columns:"), cols_input)

        # Buttons
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(dialog.accept)
        btn_box.rejected.connect(dialog.reject)
        layout.addRow(btn_box)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            name = name_input.text().strip()
            if self._refuse_profile_name(name, _("Cannot create the profile")):
                return
            rows = rows_input.value()
            cols = cols_input.value()
            # Store profile with matrix size info
            self.hud_profiles[name] = {"rows": rows, "cols": cols, "stats": []}
            self.profile_combo.addItem(name)
            self.profile_combo.setCurrentIndex(self.profile_combo.count() - 1)
            # Update preview grid size
            self.preview.set_grid(rows, cols)

    def _refuse_profile_name(self, name: str, title: str, current: str | None = None) -> bool:
        """Say why ``name`` cannot name a profile and return True; False when it can (B17)."""
        problem = editor_state.name_problem(name, self.hud_profiles, current=current)
        if problem is None:
            return False
        QMessageBox.warning(self, title, problem)
        return True

    def duplicate_profile(self) -> None:
        if self.profile_combo.currentIndex() < 0:
            return
        name = self.profile_combo.currentText()
        from PySide6.QtWidgets import QInputDialog

        new_name, ok = QInputDialog.getText(self, _("Duplicate Profile"), _("New profile name:"))
        if not ok:
            return
        new_name = new_name.strip()
        if self._refuse_profile_name(new_name, _("Cannot duplicate the profile")):
            return
        import copy

        self.hud_profiles[new_name] = copy.deepcopy(self.hud_profiles[name])
        self.profile_combo.addItem(new_name)
        self.profile_combo.setCurrentIndex(self.profile_combo.count() - 1)

    def rename_profile(self) -> None:
        """Give the current profile another name; the rules that name it follow.

        The profile keeps its place, its ``<ss>`` is renamed on Save, and the
        game defaults that name it are pointed at the new name then too.
        """
        from PySide6.QtWidgets import QInputDialog

        index = self.profile_combo.currentIndex()
        if index < 0:
            return
        old = self.profile_combo.currentText()
        new_name, ok = QInputDialog.getText(self, _("Rename Profile"), _("New profile name:"), text=old)
        if not ok:
            return
        new = new_name.strip()
        if new == old or self._refuse_profile_name(new, _("Cannot rename the profile"), current=old):
            return
        editor_state.rename_profile(self.hud_profiles, old, new)
        editor_state.record_rename(self._renamed, old, new)
        for attribute in ("profile_rules", "panel_rules"):
            rules = getattr(self, attribute, None)
            if rules is not None:
                rules[:] = editor_state.rename_in_rules(rules, old, new)
        self.profile_combo.setItemText(index, new)
        for combo in (getattr(self, "rule_profile_combo", None), getattr(self, "panel_rule_profile_combo", None)):
            found = combo.findData(old) if combo is not None else -1
            if combo is not None and found >= 0:
                combo.setItemText(found, new)
                combo.setItemData(found, new)
        if hasattr(self, "profile_rules_table"):
            self._refresh_profile_rules_table()
        if hasattr(self, "panel_rules_table"):
            self._refresh_panel_rules_table()
        self.update_status()

    def delete_profile(self) -> None:
        if self.profile_combo.currentIndex() < 0:
            return
        name = self.profile_combo.currentText()
        if (
            QMessageBox.question(
                self,
                _("Delete Profile"),
                _("Delete profile '{name}'?").format(name=name),
                QMessageBox.Yes | QMessageBox.No,
            )
            == QMessageBox.Yes
        ):
            current_index = self.profile_combo.currentIndex()
            self._forget_history(self.hud_profiles[name])
            del self.hud_profiles[name]
            editor_state.forget_profile(self._renamed, name)
            self.profile_combo.removeItem(current_index)
            if self.profile_combo.count() > 0:
                self.profile_combo.setCurrentIndex(0)
            else:
                self._selected_item = None
                self.preview.set_stats([])

    def find_popup_node(self, name):
        if not hasattr(self.config, "doc") or not self.config.doc:
            return None
        for pu in self.config.doc.getElementsByTagName("pu"):
            if pu.getAttribute("pu_name") == name:
                return pu
        return None

    def find_layout_set_node(self, name):
        if not hasattr(self.config, "doc") or not self.config.doc:
            return None
        for ls in self.config.doc.getElementsByTagName("ls"):
            if ls.getAttribute("name") == name:
                return ls
        return None

    def export_profile(self) -> None:
        if self.profile_combo.currentIndex() < 0:
            return
        profile_name = self.profile_combo.currentText()

        import os

        from PySide6.QtWidgets import QFileDialog, QMessageBox

        filename, _filter = QFileDialog.getSaveFileName(
            self,
            _("Export HUD Profile"),
            os.path.expanduser(f"~/{profile_name}.xml"),
            _("XML Files (*.xml);;FPDB HUD Files (*.fpdbhud)"),
        )

        if not filename:
            return

        try:
            import xml.dom.minidom

            impl = xml.dom.minidom.getDOMImplementation()
            pkg_doc = impl.createDocument(None, "fpdb_hud_package", None)
            root = pkg_doc.documentElement
            assert root is not None
            root.setAttribute("version", "1.0")

            # 1. Export active profile (Stat Set)
            ss_node = None
            if hasattr(self.config, "doc") and self.config.doc:
                for ss in self.config.doc.getElementsByTagName("ss"):
                    if ss.getAttribute("name") == profile_name:
                        ss_node = ss
                        break

            if ss_node is None:
                QMessageBox.warning(
                    self,
                    _("Export Warning"),
                    _(
                        "The current profile is not saved to the configuration yet. "
                        "Please save your changes before exporting.",
                    ),
                )
                return

            root.appendChild(pkg_doc.importNode(ss_node, True))

            # 2. Gather referenced Popups
            popup_names = set()
            for stat_node in ss_node.getElementsByTagName("stat"):
                p_name = stat_node.getAttribute("popup")
                if p_name and p_name != "default":
                    popup_names.add(p_name)

            collected_popups = {}
            to_process = list(popup_names)
            while to_process:
                p_name = to_process.pop(0)
                if p_name in collected_popups:
                    continue
                pu_node = self.find_popup_node(p_name)
                if pu_node:
                    collected_popups[p_name] = pu_node
                    # Check for submenus recursively
                    for pu_stat in pu_node.getElementsByTagName("pu_stat"):
                        sub = pu_stat.getAttribute("pu_stat_submenu")
                        if sub and sub != "default" and sub not in collected_popups:
                            to_process.append(sub)

            if collected_popups:
                popups_container = pkg_doc.createElement("popup_windows")
                for p_name, pu_node in sorted(collected_popups.items()):
                    popups_container.appendChild(pkg_doc.importNode(pu_node, True))
                root.appendChild(popups_container)

            # 3. Export selected Layout Sets
            layout_sets = []
            if hasattr(self.config, "layout_sets"):
                layout_sets = list(self.config.layout_sets.keys())

            selected_layouts = []
            if layout_sets:
                reply = QMessageBox.question(
                    self,
                    _("Export Layout Coordinates"),
                    _("Do you want to include custom table coordinates (Layout Sets) in this HUD package?"),
                    QMessageBox.Yes | QMessageBox.No,
                )
                if reply == QMessageBox.Yes:
                    dlg = LayoutSelectionDialog(layout_sets, self)
                    if dlg.exec() == QDialog.DialogCode.Accepted:
                        selected_layouts = dlg.get_selected_layouts()

            if selected_layouts:
                layouts_container = pkg_doc.createElement("layout_sets")
                for ls_name in sorted(selected_layouts):
                    ls_node = self.find_layout_set_node(ls_name)
                    if ls_node:
                        layouts_container.appendChild(pkg_doc.importNode(ls_node, True))
                root.appendChild(layouts_container)

            with open(filename, "w", encoding="utf-8") as f:
                f.write(pkg_doc.toprettyxml(indent="    "))

            QMessageBox.information(
                self,
                _("Export Successful"),
                _("HUD profile '{name}' exported successfully to:\n{path}").format(name=profile_name, path=filename),
            )
        except Exception as e:  # intentional broad catch
            QMessageBox.critical(
                self,
                _("Export Error"),
                _("An error occurred while exporting HUD profile:\n{error}").format(error=e),
            )

    def import_profile(self) -> None:
        import os

        import defusedxml.minidom
        from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

        from fpdb_3_legacy.hud_package import (
            merge_package_game_bindings,
            merge_package_panel_rules,
            merge_package_profile_rules,
        )

        filename, _filter = QFileDialog.getOpenFileName(
            self,
            _("Import HUD Profile"),
            os.path.expanduser("~"),
            _("PT4 HUD Layouts (*.pt4hud);;XML Files (*.xml);;FPDB HUD Files (*.fpdbhud);;All Files (*)"),
        )

        if not filename:
            return

        # PokerTracker 4 layouts use a different (binary) format and a dedicated
        # importer that builds a multi-panel stat-set + range-chart popup.
        if filename.lower().endswith(".pt4hud"):
            self._import_pt4hud(filename)
            return

        try:
            import_doc = defusedxml.minidom.parse(filename)
            root = import_doc.documentElement
            assert root is not None
            if root.tagName != "fpdb_hud_package":
                QMessageBox.critical(
                    self, _("Import Error"), _("Invalid package file. The root element must be <fpdb_hud_package>.")
                )
                return

            # 1. Process ss (Stat Set)
            ss_nodes = root.getElementsByTagName("ss")
            if not ss_nodes:
                QMessageBox.critical(self, _("Import Error"), _("No HUD profile (stat set) found in the package."))
                return

            ss_node = ss_nodes[0]
            imported_name = ss_node.getAttribute("name")
            if not imported_name:
                QMessageBox.critical(self, _("Import Error"), _("Imported HUD profile has no name."))
                return

            overwrite_profile = False
            new_profile_name = imported_name

            # Check for conflict
            if imported_name in self.hud_profiles:
                msg_box = QMessageBox(self)
                msg_box.setWindowTitle(_("Profile Conflict"))
                msg_box.setText(_("A HUD profile named '{name}' already exists.").format(name=imported_name))

                overwrite_btn = msg_box.addButton(_("Overwrite"), QMessageBox.ButtonRole.DestructiveRole)
                rename_btn = msg_box.addButton(_("Rename"), QMessageBox.ButtonRole.ActionRole)
                cancel_btn = msg_box.addButton(QMessageBox.StandardButton.Cancel)

                msg_box.setDefaultButton(rename_btn)
                msg_box.exec()

                clicked_btn = msg_box.clickedButton()
                if clicked_btn == cancel_btn:
                    return
                elif clicked_btn == rename_btn:
                    new_name, ok = QInputDialog.getText(
                        self,
                        _("Rename Imported Profile"),
                        _("Enter new name for imported profile '{name}':").format(name=imported_name),
                        text=f"{imported_name}_imported",
                    )
                    if not ok or not new_name:
                        return
                    while new_name in self.hud_profiles:
                        new_name, ok = QInputDialog.getText(
                            self,
                            _("Rename Imported Profile"),
                            _("Name '{name}' already exists. Enter another name:").format(name=new_name),
                            text=f"{new_name}_1",
                        )
                        if not ok or not new_name:
                            return
                    new_profile_name = new_name
                elif clicked_btn == overwrite_btn:
                    overwrite_profile = True

            # 2. Process pu (Popup Windows)
            pu_nodes = root.getElementsByTagName("pu")
            overwrite_popups = {}  # pu_name -> bool
            overwrite_all_popups = False
            skip_all_popups = False

            for pu_node in pu_nodes:
                pu_name = pu_node.getAttribute("pu_name")
                existing_pu = self.find_popup_node(pu_name)

                if existing_pu:
                    if overwrite_all_popups:
                        overwrite_popups[pu_name] = True
                    elif skip_all_popups:
                        overwrite_popups[pu_name] = False
                    else:
                        msg_box = QMessageBox(self)
                        msg_box.setWindowTitle(_("Popup Conflict"))
                        msg_box.setText(_("Popup window '{name}' already exists.").format(name=pu_name))

                        yes_btn = msg_box.addButton(QMessageBox.StandardButton.Yes)
                        yes_to_all_btn = msg_box.addButton(QMessageBox.StandardButton.YesToAll)
                        no_btn = msg_box.addButton(QMessageBox.StandardButton.No)
                        no_to_all_btn = msg_box.addButton(QMessageBox.StandardButton.NoToAll)
                        cancel_btn = msg_box.addButton(QMessageBox.StandardButton.Cancel)

                        msg_box.setDefaultButton(yes_btn)
                        msg_box.exec()

                        clicked_btn = msg_box.clickedButton()
                        if clicked_btn == cancel_btn:
                            return
                        elif clicked_btn == yes_to_all_btn:
                            overwrite_all_popups = True
                            overwrite_popups[pu_name] = True
                        elif clicked_btn == yes_btn:
                            overwrite_popups[pu_name] = True
                        elif clicked_btn == no_to_all_btn:
                            skip_all_popups = True
                            overwrite_popups[pu_name] = False
                        elif clicked_btn == no_btn:
                            overwrite_popups[pu_name] = False
                else:
                    overwrite_popups[pu_name] = True

            # 3. Process ls (Layout Sets)
            ls_nodes = root.getElementsByTagName("ls")
            overwrite_layouts = {}  # ls_name -> bool
            overwrite_all_layouts = False
            skip_all_layouts = False

            for ls_node in ls_nodes:
                ls_name = ls_node.getAttribute("name")
                existing_ls = self.find_layout_set_node(ls_name)

                if existing_ls:
                    if overwrite_all_layouts:
                        overwrite_layouts[ls_name] = True
                    elif skip_all_layouts:
                        overwrite_layouts[ls_name] = False
                    else:
                        msg_box = QMessageBox(self)
                        msg_box.setWindowTitle(_("Layout Conflict"))
                        msg_box.setText(_("Layout coordinates for site layout '{name}' already exist.").format(name=ls_name))
                        msg_box.setInformativeText(
                            _(
                                "Do you want to overwrite your existing layout coordinates "
                                "for this site with the imported ones?",
                            ),
                        )

                        yes_btn = msg_box.addButton(QMessageBox.StandardButton.Yes)
                        yes_to_all_btn = msg_box.addButton(QMessageBox.StandardButton.YesToAll)
                        no_btn = msg_box.addButton(QMessageBox.StandardButton.No)
                        no_to_all_btn = msg_box.addButton(QMessageBox.StandardButton.NoToAll)
                        cancel_btn = msg_box.addButton(QMessageBox.StandardButton.Cancel)

                        msg_box.setDefaultButton(yes_btn)
                        msg_box.exec()

                        clicked_btn = msg_box.clickedButton()
                        if clicked_btn == cancel_btn:
                            return
                        elif clicked_btn == yes_to_all_btn:
                            overwrite_all_layouts = True
                            overwrite_layouts[ls_name] = True
                        elif clicked_btn == yes_btn:
                            overwrite_layouts[ls_name] = True
                        elif clicked_btn == no_to_all_btn:
                            skip_all_layouts = True
                            overwrite_layouts[ls_name] = False
                        elif clicked_btn == no_btn:
                            overwrite_layouts[ls_name] = False
                else:
                    overwrite_layouts[ls_name] = True

            # All prompts passed with no cancellation. Now perform actual DOM changes.

            # A. Overwrite or append Profile (ss_node)
            stat_sets_nodes = self.config.doc.getElementsByTagName("stat_sets")
            if not stat_sets_nodes:
                stat_sets_node = self.config.doc.createElement("stat_sets")
                self.config.doc.documentElement.appendChild(stat_sets_node)
            else:
                stat_sets_node = stat_sets_nodes[0]

            if overwrite_profile:
                existing_ss_node = None
                for ss in self.config.doc.getElementsByTagName("ss"):
                    if ss.getAttribute("name") == new_profile_name:
                        existing_ss_node = ss
                        break
                if existing_ss_node:
                    existing_ss_node.parentNode.removeChild(existing_ss_node)
            else:
                ss_node.setAttribute("name", new_profile_name)

            # Append the primary profile. Additional profiles carried by a
            # package (for example AoF compact + advanced) are installed below
            # when missing; an existing secondary profile is a user choice and
            # is therefore preserved.
            indent = self.config.doc.createTextNode("\n        ")
            stat_sets_node.appendChild(indent)
            merged_ss = self.config.doc.importNode(ss_node, True)
            stat_sets_node.appendChild(merged_ss)
            for secondary_ss in ss_nodes[1:]:
                secondary_name = secondary_ss.getAttribute("name")
                if not secondary_name or secondary_name in self.hud_profiles:
                    continue
                indent = self.config.doc.createTextNode("\n        ")
                stat_sets_node.appendChild(indent)
                stat_sets_node.appendChild(self.config.doc.importNode(secondary_ss, True))

            # B. Apply Popups
            popup_windows_nodes = self.config.doc.getElementsByTagName("popup_windows")
            if not popup_windows_nodes:
                pw_node = self.config.doc.createElement("popup_windows")
                self.config.doc.documentElement.appendChild(pw_node)
            else:
                pw_node = popup_windows_nodes[0]

            for pu_node in pu_nodes:
                pu_name = pu_node.getAttribute("pu_name")
                if overwrite_popups.get(pu_name):
                    existing_pu = self.find_popup_node(pu_name)
                    if existing_pu:
                        existing_pu.parentNode.removeChild(existing_pu)

                    indent = self.config.doc.createTextNode("\n        ")
                    pw_node.appendChild(indent)
                    merged_pu = self.config.doc.importNode(pu_node, True)
                    pw_node.appendChild(merged_pu)

            # C. Apply Layout Sets
            layout_sets_nodes = self.config.doc.getElementsByTagName("layout_sets")
            if not layout_sets_nodes:
                lss_node = self.config.doc.createElement("layout_sets")
                self.config.doc.documentElement.appendChild(lss_node)
            else:
                lss_node = layout_sets_nodes[0]

            for ls_node in ls_nodes:
                ls_name = ls_node.getAttribute("name")
                if overwrite_layouts.get(ls_name):
                    existing_ls = self.find_layout_set_node(ls_name)
                    if existing_ls:
                        existing_ls.parentNode.removeChild(existing_ls)

                    indent = self.config.doc.createTextNode("\n        ")
                    lss_node.appendChild(indent)
                    merged_ls = self.config.doc.importNode(ls_node, True)
                    lss_node.appendChild(merged_ls)

            # D. Apply game bindings carried by package version 1.1. A stat set
            # alone is inert for a new category: without this mapping the
            # profile appears in Preferences, but the HUD still cannot select
            # it when the table opens. Repoint the binding when a conflicting
            # profile was renamed during this import.
            merge_package_game_bindings(
                self.config.doc,
                root,
                profile_names={imported_name: new_profile_name},
                overwrite=True,
            )

            # E. Apply any profile rules the package carries. A package meant
            # for one kind of table -- Fast-Fold, say -- selects itself with a
            # rule rather than by taking over the game's binding, which every
            # ordinary table of that game would otherwise inherit.
            merge_package_profile_rules(
                self.config.doc,
                root,
                profile_names={imported_name: new_profile_name},
                overwrite=True,
            )

            # F. Apply the dynamic-panel section a package carries, if any. The
            # reference Dynamic HUD (#332) ships the blocks the built-in
            # resolver selects and the section that enables them for its own
            # profile; a configuration that already has panel rules keeps them,
            # because those are the user's. The section is scoped to a profile
            # by name, so a renamed import has to repoint it here -- otherwise
            # the panels turn on for the profile that already existed and the
            # one the user just imported resolves nothing.
            merge_package_panel_rules(
                self.config.doc,
                root,
                overwrite=False,
                profile_names={imported_name: new_profile_name},
            )

            # Save configuration and reload
            self.config.save()
            self.config.reload()

            # Importing a Dynamic package can replace the disabled placeholder
            # with an enabled source. Keep the editor's draft in sync, or the
            # next Save silently writes its old empty/disabled draft over the
            # newly imported source.
            if hasattr(self, "panel_rules_enabled"):
                self.panel_rules: list[Any] = list(self.config.get_hud_panel_rules())
                self.panel_rules_fallback = str(getattr(self.config, "hud_panel_fallback", "") or "")
                self.panel_rules_enabled.setChecked(bool(self.config.hud_panel_rules_enabled))
                self._refresh_panel_rules_table()

            # Reload HUD profiles and popups in the UI
            self.load_profiles()
            self.load_popup_windows()

            # Select the imported profile
            self.profile_combo.setCurrentText(new_profile_name)
            self.on_profile_selected(self.profile_combo.currentIndex())

            # Reload parent config to apply changes live
            self.reload_parent_config()

            from fpdb_3_legacy.pt4hud_dialogs import show_package_import

            # A package converted from PT4 names the stats it left out (#614).
            show_package_import(self, new_profile_name, root)

        except Exception as e:  # intentional broad catch
            QMessageBox.critical(
                self,
                _("Import Error"),
                _("An error occurred while importing HUD profile:\n{error}").format(error=e),
            )

    def _import_pt4hud(self, filename: str) -> None:
        """Import a PokerTracker 4 .pt4hud layout into the config and refresh the UI."""
        from PySide6.QtWidgets import QMessageBox

        try:
            from fpdb_3_legacy import pt4hud

            summary = pt4hud.import_to_config(filename, self.config)
            self.config.save()
            self.config.reload()

            # Reload profiles/popups and select the freshly imported stat-set.
            self.load_profiles()
            self.load_popup_windows()
            self.profile_combo.setCurrentText(summary["name"])
            self.on_profile_selected(self.profile_combo.currentIndex())
            self.reload_parent_config()
        except Exception as e:  # intentional broad catch
            log.exception("PT4 .pt4hud import failed")
            QMessageBox.critical(
                self,
                _("Import Error"),
                _("Could not import {path}:\n{error}").format(path=filename, error=e),
            )
            return

        from fpdb_3_legacy.pt4hud_dialogs import show_import_summary

        show_import_summary(self, summary)

    def reload_parent_config(self) -> None:
        """Ask the host to apply an import that has already been saved.

        Standalone editors have no host to refresh. A host refresh failure
        must not report a failed import: the package is already on disk and
        loaded in this dialog, and importing it again would create conflicts.
        """
        try:
            reload_config = getattr(self.parent(), "reload_config", None)
            if callable(reload_config):
                reload_config()
        except Exception:  # intentional broad catch: optional host callback after a successful save
            log.exception("HUD import saved, but parent configuration refresh failed")
            QMessageBox.warning(
                self,
                _("HUD imported — refresh required"),
                _(
                    "The HUD profile was imported and saved, but the application could not "
                    "refresh its configuration. Restart fpdb to apply it. "
                    "You do not need to import the file again."
                ),
            )

    def get_current_profile(self):
        if self.profile_combo.currentIndex() < 0:
            return None, None
        name = self.profile_combo.currentText()
        return name, profile_io.profile_stats(self.hud_profiles[name])

    def _current_profile(self):
        """Return (name, profile) for the selected profile, or (None, None)."""
        if self.profile_combo.currentIndex() < 0:
            return None, None
        name = self.profile_combo.currentText()
        return name, self.hud_profiles.get(name)

    def _item_container(self, profile, block_index):
        """The dict whose 'stats'/'texts' lists hold a row's items.

        For a multi-panel profile that is the targeted ``<block>``; for a flat
        profile it is the profile itself (so edits go where Save reads them).
        """
        blocks = profile.get("blocks") if isinstance(profile, dict) else None
        if blocks and block_index is not None and 0 <= block_index < len(blocks):
            return blocks[block_index]
        if isinstance(profile, dict):
            return profile
        return {"stats": profile}

    def _selected_row_item(self):
        """``(block_index, kind, ref)`` of the selected item, or None."""
        _name, profile = self._current_profile()
        where = editor_state.locate(profile, self._selected_item)
        if where is None:
            return None
        return where[0], where[1], self._selected_item

    def add_stat(self) -> None:
        """Add a stat to the first free cell of the panel shown in Design.

        The canvas places it: drag it, or move it with Alt+arrows, from there.
        """
        _profile, container = self._shown_container()
        if container is None:
            return
        dlg = AddStatDialog(parent=self, **self._stat_dialog_lists())
        if dlg.exec():
            stat = dlg.get_stat()
            row, col = layout_model.first_free_cell(container)
            layout_model.add(container, "stat", stat, row, col)
            self._refresh_profile(select=stat)

    def edit_stat(self) -> None:
        sel = self._selected_row_item()
        if sel is None:
            return
        _block_index, kind, ref = sel
        if kind == "text":
            from PySide6.QtWidgets import QInputDialog

            new_label, ok = QInputDialog.getText(self, _("Edit Text Label"), _("Label:"), text=ref.get("label", ""))
            if ok:
                ref["label"] = new_label
                self._refresh_profile()
            return
        if kind == "hline":
            from PySide6.QtGui import QColor
            from PySide6.QtWidgets import QColorDialog

            col = QColorDialog.getColor(QColor(ref.get("color") or "#d7b500"), self, _("Line colour"))
            if col.isValid():
                ref["color"] = col.name()
                self._refresh_profile()
            return
        dlg = AddStatDialog(stat=ref, parent=self, **self._stat_dialog_lists())
        if dlg.exec():
            # Only what the user changed (B1); the cell stays where the canvas put it.
            stat_edit.apply_changes(ref, dlg.get_stat())
            self._refresh_profile()

    def remove_stat(self) -> None:
        name, profile = self._current_profile()
        if profile is None:
            return
        sel = self._selected_row_item()
        if sel is None:
            return
        block_index, kind, ref = sel
        container = self._item_container(profile, block_index)
        lst = container.get({"text": "texts", "hline": "hlines"}.get(kind, "stats"), [])
        if ref in lst:
            lst.remove(ref)
        self._refresh_profile()

    def _next_free_cell(self, container) -> tuple[int, int]:
        """First free (row, col) in a block/profile container."""
        return layout_model.first_free_cell(container)

    def _block_container(self, profile, block_index):
        """The block that receives a new label or line.

        Labels and lines exist only inside a ``<block>``: a flat profile is
        turned into a one-block profile first, so the item is shown and saved
        instead of landing in a list nothing reads.
        """
        if isinstance(profile, dict) and not profile.get("blocks"):
            self._current_block_index = 0
            return profile_io.ensure_blocks(profile)[0]
        return self._item_container(profile, block_index)

    def add_text_label(self) -> None:
        from PySide6.QtWidgets import QInputDialog

        name, profile = self._current_profile()
        if profile is None:
            return
        sel = self._selected_row_item()
        block_index = sel[0] if sel else (0 if isinstance(profile, dict) and profile.get("blocks") else None)
        label, ok = QInputDialog.getText(self, _("Add Text Label"), _("Label text (e.g. column header, caption):"))
        if not ok or not label.strip():
            return
        container = self._block_container(profile, block_index)
        r, cc = layout_model.first_free_cell(container)
        text = {"label": label.strip(), "colspan": 1, "align": "center", "fgcolor": "", "bgcolor": ""}
        layout_model.add(container, "text", text, r, cc)
        self._refresh_profile(select=text)

    def add_hline(self) -> None:
        name, profile = self._current_profile()
        if profile is None:
            return
        sel = self._selected_row_item()
        block_index = sel[0] if sel else (0 if isinstance(profile, dict) and profile.get("blocks") else None)
        container = self._block_container(profile, block_index)
        # A separator takes its own row and spans the whole panel width (colspan 0).
        hline = {"colspan": 0, "color": ""}
        layout_model.add(container, "hline", hline, layout_model.first_free_row(container), 0)
        self._refresh_profile(select=hline)

    def add_block(self) -> None:
        from PySide6.QtWidgets import QInputDialog

        name, profile = self._current_profile()
        if not isinstance(profile, dict):
            return
        label, ok = QInputDialog.getText(self, _("Add Block"), _("New panel (block) name:"))
        if not ok:
            return
        cols = int(profile.get("cols", 4)) or 4
        blocks = profile.setdefault("blocks", [])
        if not blocks:
            # Promote the existing flat grid to the first block so the profile
            # becomes a genuine multi-panel set.
            blocks.append(
                {
                    "label": "Main",
                    "position": "",
                    "rows": int(profile.get("rows", 1)),
                    "cols": cols,
                    "bgcolor": "",
                    "fgcolor": "",
                    "title_bgcolor": "",
                    "title_fgcolor": "",
                    "bordercolor": "",
                    "cell_width": 0,
                    "x": 0,
                    "y": 0,
                    "stats": [dict(s) for s in profile.get("stats", [])],
                    "texts": [],
                }
            )
        blocks.append(
            {
                "label": label.strip() or f"Block {len(blocks) + 1}",
                "position": "",
                "rows": 1,
                "cols": cols,
                "bgcolor": "",
                "fgcolor": "",
                "title_bgcolor": "",
                "title_fgcolor": "",
                "bordercolor": "",
                "cell_width": 0,
                "x": 0,
                "y": 0,
                "stats": [],
                "texts": [],
            }
        )
        profile["multiblock"] = True
        self._refresh_profile()

    def edit_block_properties(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        name, profile = self._current_profile()
        if not isinstance(profile, dict):
            return
        blocks = profile.get("blocks")
        if not blocks:
            QMessageBox.information(self, _("Block Properties"), _("This profile has no panels. Use Add Block first."))
            return
        sel = self._selected_row_item()
        bi = sel[0] if sel and sel[0] is not None else 0
        dlg = BlockPropertiesDialog(blocks[bi], parent=self)
        if dlg.exec():
            blocks[bi].update(dlg.get_props())
            self._refresh_profile()

    def _append_stat_node(self, parent_node, stat: dict, row: int, col: int) -> None:
        profile_io.append_stat_node(self.config.doc, parent_node, stat, row, col)

    def _append_hline_node(self, parent_node, hline: dict) -> None:
        """Write a PT4-style <hline> separator item within a block."""
        profile_io.append_hline_node(self.config.doc, parent_node, hline)

    def _append_text_node(self, parent_node, text: dict) -> None:
        """Write a PT4-style <text> label item within a block."""
        profile_io.append_text_node(self.config.doc, parent_node, text)

    def _write_profile_stats(self, stat_set_node, profile_data, rows: int, cols: int) -> None:
        """Write a profile as flat <stat> nodes or PT4-style <block> nodes."""
        profile_io.write_profile_items(self.config.doc, stat_set_node, profile_data, rows, cols)

    @staticmethod
    def _fill_rule_combo(combo: QComboBox, values: list[str]) -> None:
        combo.addItem(_("ANY"), "all")
        for value in values:
            if value and str(value).casefold() != "all":
                combo.addItem(str(value), str(value))

    def _create_profile_select_tab(self) -> None:
        tab = QWidget()
        outer = QVBoxLayout(tab)
        outer.setContentsMargins(12, 10, 12, 10)

        selector = QGroupBox(_("Add Profile Definition"))
        grid = QGridLayout(selector)
        self.rule_site_combo = QComboBox()
        self.rule_game_combo = QComboBox()
        self.rule_type_combo = QComboBox()
        self.rule_limit_combo = QComboBox()
        self.rule_seats_combo = QComboBox()
        self.rule_players_combo = QComboBox()
        self.rule_speed_combo = QComboBox()
        self.rule_profile_combo = QComboBox()

        self._fill_rule_combo(self.rule_site_combo, sorted(getattr(self.config, "supported_sites", {})))
        self._fill_rule_combo(self.rule_game_combo, sorted(getattr(self.config, "supported_games", {})))
        self._fill_rule_combo(self.rule_type_combo, ["ring", "tour"])
        self._fill_rule_combo(self.rule_limit_combo, ["nl", "pl", "fl", "cn"])
        self._fill_rule_combo(self.rule_seats_combo, [str(value) for value in range(2, 11)])
        self._fill_rule_combo(self.rule_players_combo, [str(value) for value in range(2, 11)])
        self._fill_rule_combo(self.rule_speed_combo, ["normal", "fast"])
        for profile in sorted(getattr(self.config, "stat_sets", {})):
            self.rule_profile_combo.addItem(profile, profile)

        fields = [
            (_("Site"), self.rule_site_combo),
            (_("Game"), self.rule_game_combo),
            (_("Format"), self.rule_type_combo),
            (_("Limit"), self.rule_limit_combo),
            (_("Seats"), self.rule_seats_combo),
            (_("Players"), self.rule_players_combo),
            (_("Speed"), self.rule_speed_combo),
            (_("HUD Profile"), self.rule_profile_combo),
        ]
        for index, (label, combo) in enumerate(fields):
            combo.setMinimumHeight(34)
            row, column = divmod(index, 2)
            grid.addWidget(QLabel(label), row, column * 2)
            grid.addWidget(combo, row, column * 2 + 1)
        add_button = QPushButton(_("Add"))
        add_button.clicked.connect(self._add_profile_rule)
        grid.addWidget(add_button, 4, 3)
        outer.addWidget(selector)

        # Rules interact through specificity and priority, so which one a given
        # table ends up on is not obvious from reading the list. This answers it
        # with the resolver the HUD itself uses.
        preview = QGroupBox(_("Effective profile for these selectors"))
        preview_layout = QVBoxLayout(preview)
        self.profile_preview_label = QLabel()
        self.profile_preview_label.setWordWrap(True)
        preview_layout.addWidget(self.profile_preview_label)
        outer.addWidget(preview)
        for combo in (
            self.rule_site_combo,
            self.rule_game_combo,
            self.rule_type_combo,
            self.rule_limit_combo,
            self.rule_seats_combo,
            self.rule_players_combo,
            self.rule_speed_combo,
        ):
            combo.currentIndexChanged.connect(self._update_profile_preview)

        active = QGroupBox(_("Active Profile Definitions"))
        active_layout = QVBoxLayout(active)
        self.profile_rules_table = QTableWidget(0, 8)
        self.profile_rules_table.setHorizontalHeaderLabels(
            [_("Site"), _("Game"), _("Format"), _("Limit"), _("Seats"), _("Players"), _("Speed"), _("HUD Profile")]
        )
        self.profile_rules_table.verticalHeader().hide()
        self.profile_rules_table.verticalHeader().setDefaultSectionSize(36)
        self.profile_rules_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.profile_rules_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.profile_rules_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.profile_rules_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.profile_rules_table.setAlternatingRowColors(True)
        self.profile_rules_table.setMinimumHeight(180)
        active_layout.addWidget(self.profile_rules_table)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        delete_button = QPushButton(_("Delete"))
        delete_button.clicked.connect(self._delete_profile_rule)
        btn_layout.addWidget(delete_button)
        active_layout.addLayout(btn_layout)
        outer.addWidget(active, 1)

        self.profile_rules = list(getattr(self.config, "get_hud_profile_rules", lambda: [])())
        self._refresh_profile_rules_table()
        # The selector grid, the preview and the rules table together ask for
        # more height than a laptop screen has; scrolling keeps the Add button
        # and the rules table reachable instead of pushing them below the fold.
        self.tabs.addTab(wrap_in_scroll(tab), _("🎯 Profile Select"))

    def _add_profile_rule(self) -> None:
        if self.rule_profile_combo.currentIndex() < 0:
            return
        values = {
            "id": f"rule-{len(self.profile_rules) + 1}",
            "site": self.rule_site_combo.currentData(),
            "game": self.rule_game_combo.currentData(),
            "game_type": self.rule_type_combo.currentData(),
            "limit": self.rule_limit_combo.currentData(),
            "seats": self.rule_seats_combo.currentData(),
            "players": self.rule_players_combo.currentData(),
            "speed": self.rule_speed_combo.currentData(),
            "profile": self.rule_profile_combo.currentData(),
        }
        rule = HudProfileRule.from_mapping(values, len(self.profile_rules))
        if rule.selector() in {existing.selector() for existing in self.profile_rules}:
            QMessageBox.warning(
                self, _("Duplicate rule"), _("A profile definition with these selectors already exists.")
            )
            return
        self.profile_rules.append(rule)
        self._refresh_profile_rules_table()

    def _delete_profile_rule(self) -> None:
        row = self.profile_rules_table.currentRow()
        if 0 <= row < len(self.profile_rules):
            self.profile_rules.pop(row)
            self.profile_rules = [
                HudProfileRule.from_mapping(rule.as_xml_attributes(), order)
                for order, rule in enumerate(self.profile_rules)
            ]
            self._refresh_profile_rules_table()

    def _known_profile_names(self) -> set[str]:
        """The profiles a rule may name: the editor's, renames and all, once loaded."""
        return set(getattr(self, "hud_profiles", None) or getattr(self.config, "stat_sets", {}) or {})

    def _refresh_profile_rules_table(self) -> None:
        known_profiles = self._known_profile_names()
        self.profile_rules_table.setRowCount(len(self.profile_rules))
        for row, rule in enumerate(self.profile_rules):
            self.profile_rules_table.setRowHeight(row, 36)
            values = [
                rule.site,
                rule.game,
                rule.game_type,
                rule.limit_type,
                _("ANY") if rule.seats is None else str(rule.seats),
                _("ANY") if rule.players is None else str(rule.players),
                rule.speed,
                rule.profile,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(_("ANY") if value == "all" else value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                # A hand-edited config can name a profile that was since
                # renamed or deleted; such a rule matches but selects nothing,
                # which is invisible unless it is said here.
                if column == len(values) - 1 and known_profiles and rule.profile not in known_profiles:
                    item.setText(f"{rule.profile}  ⚠")
                    item.setToolTip(_("No HUD profile of this name exists; this rule will be ignored."))
                self.profile_rules_table.setItem(row, column, item)
        self._update_profile_preview()

    def _preview_context(self) -> HudContext:
        """The table context described by the selector combos."""

        def seats(combo: QComboBox) -> int:
            value = str(combo.currentData() or "")
            return int(value) if value.isdigit() else 0

        return HudContext(
            site=str(self.rule_site_combo.currentData() or "all"),
            game=str(self.rule_game_combo.currentData() or "all"),
            game_type=str(self.rule_type_combo.currentData() or "all"),
            limit_type=str(self.rule_limit_combo.currentData() or "all"),
            max_seats=seats(self.rule_seats_combo),
            players=seats(self.rule_players_combo),
            speed=str(self.rule_speed_combo.currentData() or "normal"),
        )

    def _default_profile_for(self, context: HudContext) -> str | None:
        """The profile <supported_games> gives this game, ignoring the rules."""
        getter = getattr(self.config, "get_supported_games_parameters", None)
        if getter is None:
            return None
        try:
            params = getter(context.game, context.game_type)
        except Exception:  # intentional broad catch: a preview must never break the dialog
            log.debug("Could not read the default profile for %s", context, exc_info=True)
            return None
        if not isinstance(params, dict):
            return None
        return getattr(params.get("game_stat_set"), "name", None)

    @staticmethod
    def _describe_rule(rule: HudProfileRule) -> str:
        parts = [
            f"{label}={value}"
            for label, value in (
                ("site", rule.site),
                ("game", rule.game),
                ("format", rule.game_type),
                ("limit", rule.limit_type),
                ("seats", rule.seats),
                ("players", rule.players),
                ("speed", rule.speed),
            )
            if value not in ("all", None)
        ]
        return ", ".join(parts) or _("ANY table")

    def _update_profile_preview(self) -> None:
        """Say which profile the selectors would resolve to, and why."""
        if not hasattr(self, "profile_preview_label"):
            return
        context = self._preview_context()
        winner = HudProfileResolver(self.profile_rules).matching_rule(context)
        known_profiles = self._known_profile_names()

        if winner is not None:
            text = _("{profile} — from the rule {selectors}").format(
                profile=winner.profile, selectors=self._describe_rule(winner)
            )
            if known_profiles and winner.profile not in known_profiles:
                text += "\n⚠ " + _("No HUD profile of this name exists; the game default will be used instead.")
        else:
            default = self._default_profile_for(context)
            text = _("{profile} — no rule matches, so the game default applies").format(profile=default or "—")
            if default is None:
                text += "\n" + _("Pick a Game (and Format) to see the default that would apply.")
        self.profile_preview_label.setText(text)
        self._refresh_unsaved_indicator()

    # ------------------------------------------------------------------ #
    # Dynamic panels (#309): the panel rules of #298, editable.
    # ------------------------------------------------------------------ #

    def _open_help(self, topic: str) -> None:
        """Open a user guide from a Help affordance (#334), never raising."""
        try:
            from fpdb_3_legacy import help_links

            help_links.open_help(topic)
        except Exception:  # intentional broad catch: Help must not break the dialog
            log.exception("Could not open the help topic %r", topic)

    def _create_reference_hud_tab(self) -> None:
        """The three shipped HUDs, inspectable without a poker table (#370).

        Read-only on purpose: this tab answers "what do these look like, and
        where does each number live" before a reader commits to one. Choosing
        a profile is still the Profile Select tab's job.
        """
        from fpdb_3_legacy.modern_hud_preferences.reference_preview import ReferenceHudPreview

        tab = QWidget()
        layout = QVBoxLayout(tab)
        intro = QLabel(
            _(
                "The HUDs fpdb ships, as a seat would see them. Pick a context to watch the "
                "Dynamic package change panel, and read the popup paths to find where a "
                "number lives before you go looking for it at a table.",
            ),
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.reference_preview = ReferenceHudPreview()
        # Inside a scroll area the preview keeps the height it needs to show a
        # seat; a window shorter than that scrolls rather than clipping the HUD.
        self.reference_preview.setMinimumHeight(320)
        layout.addWidget(self.reference_preview, 1)
        self.tabs.addTab(wrap_in_scroll(tab), _("🃏 Reference HUDs"))

    def _create_dynamic_panels_tab(self) -> None:
        """The tab that writes the ``<hud_panel_rules>`` section of #298.

        The selectors are the conditions a rule may state, and they come from
        ``hud_panel_editor``, which validates them against the query engine's own
        vocabulary: this tab cannot offer a condition the HUD would refuse. The
        preview below runs the production resolver on the context the selectors
        describe, so what is shown here is what a table would show.
        """
        from fpdb_3_legacy import hud_panel_editor as editor
        from fpdb_3_legacy.ring_stats.styles import get_theme_palette

        # The captions above the fields follow the active theme's muted colour,
        # the same one the Study Explorer uses, so a caption never competes with
        # the value it labels.
        muted = get_theme_palette().get("muted_text", "#a0aec0")

        # The state first: the widget builders below ask for the known panels and
        # the stat choices, and both read it.
        self.panel_rules = list(getattr(self.config, "get_hud_panel_rules", lambda: [])())
        self.panel_rules_fallback = str(getattr(self.config, "hud_panel_fallback", "") or "")
        self.panel_stat_choices: tuple[Any, ...] = ()

        tab = QWidget()
        outer = QVBoxLayout(tab)
        outer.setContentsMargins(12, 10, 12, 10)

        # In-app help (#334): the dynamic-panel guide, opened from here so the
        # reader does not have to know the file name.
        help_row = QHBoxLayout()
        help_row.addStretch()
        self.dynamic_help_button = QLabel(_("?"))
        self.dynamic_help_button.setToolTip(_("Open the Dynamic HUD guide"))
        self.dynamic_help_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dynamic_help_button.setStyleSheet("font-weight: bold;")
        self.dynamic_help_button.mousePressEvent = lambda _event: self._open_help("hud-dynamic")  # type: ignore[assignment]
        help_row.addWidget(self.dynamic_help_button)
        outer.addLayout(help_row)

        self.panel_rules_enabled = QCheckBox(_("Show the panels that fit the hand"))
        self.panel_rules_enabled.setToolTip(
            _(
                "Off by default. When it is on, the panels a rule names are shown and every "
                "other block keeps the position rule it has always had."
            )
        )
        outer.addWidget(self.panel_rules_enabled)
        rooms_note = QLabel(
            _(
                "Some rooms forbid statistics that change with the hand: fpdb asks once before turning "
                "them on, and never shows them at PokerStars tables."
            )
        )
        rooms_note.setWordWrap(True)
        outer.addWidget(rooms_note)

        selectors = QGroupBox(_("When this is the spot"))
        selectors_layout = QVBoxLayout(selectors)
        # The selector captions used to be cells of their own in a fixed
        # four-column grid (``row * 2`` for the caption, ``row * 2 + 1`` for the
        # field), inside a second scroll area that kept the group at 190 px of
        # minimum height. A reflowing grid of caption-above-field blocks says the
        # same thing, follows the window width, and needs no inner scroller now
        # that the whole tab scrolls.
        self.panel_selector_grid = ReflowGrid()
        self.panel_selector_widgets: dict[str, Any] = {}
        selector_blocks: list[QWidget] = []
        for field in editor.fill_choices(editor.selector_fields(), **self._panel_vocabularies()):
            widget = self._panel_selector_widget(field)
            self.panel_selector_widgets[field.name] = widget
            self._panel_selector_hook(widget, field.name)
            selector_blocks.append(labelled_field(field.label, widget, muted))
        self.panel_selector_grid.set_items(selector_blocks)
        selectors_layout.addLayout(self.panel_selector_grid)
        outer.addWidget(selectors)

        behaviour = QGroupBox(_("Then show"))
        behaviour_layout = QVBoxLayout(behaviour)
        self.panel_rule_panel_combo = QComboBox()
        self.panel_rule_panel_combo.setEditable(True)
        self.panel_rule_panel_combo.addItems(self._known_panel_names())
        self.panel_rule_profile_combo = QComboBox()
        self.panel_rule_profile_combo.addItem(_("all profiles"), "all")
        for profile in sorted(getattr(self.config, "stat_sets", {}) or {}):
            self.panel_rule_profile_combo.addItem(profile, profile)
        self.panel_rule_fallback_combo = QComboBox()
        self.panel_rule_fallback_combo.addItem(_("(none)"), "")
        self.panel_rule_fallback_combo.addItems(self._known_panel_names())
        self.panel_rule_priority = QSpinBox()
        self.panel_rule_priority.setRange(-100, 100)
        self.panel_rule_min_sample = QSpinBox()
        self.panel_rule_min_sample.setRange(0, 1000000)
        self.panel_rule_min_sample.setToolTip(_("Below this many hands the panel is withheld and the fallback shows."))
        self.panel_rule_sample = QLineEdit("n")
        self.panel_rule_id = QLineEdit()
        self.panel_rule_id.setPlaceholderText(_("optional name"))
        self.panel_rule_enabled = QCheckBox(_("Enabled"))
        self.panel_rule_enabled.setChecked(True)
        # Same treatment as the selectors: the caption above its field, in a
        # grid that reflows. The seven fields were two fixed rows of
        # caption/field pairs before, and "Enabled" was parked in the leftover
        # cell at (1, 6) -- which the grid silently dropped once the row was
        # full, so the checkbox is now in a row of its own where nothing can
        # take its place.
        self.panel_behaviour_grid = ReflowGrid()
        self.panel_behaviour_grid.set_items(
            [
                labelled_field(_("Panel"), self.panel_rule_panel_combo, muted),
                labelled_field(_("HUD profile"), self.panel_rule_profile_combo, muted),
                labelled_field(_("Priority"), self.panel_rule_priority, muted),
                labelled_field(_("Min sample"), self.panel_rule_min_sample, muted),
                labelled_field(_("Sample column"), self.panel_rule_sample, muted),
                labelled_field(_("Fallback"), self.panel_rule_fallback_combo, muted),
                labelled_field(_("Rule name"), self.panel_rule_id, muted),
            ]
        )
        behaviour_layout.addLayout(self.panel_behaviour_grid)
        enabled_row = QHBoxLayout()
        enabled_row.addWidget(self.panel_rule_enabled)
        enabled_row.addStretch()
        behaviour_layout.addLayout(enabled_row)
        outer.addWidget(behaviour)

        buttons = QHBoxLayout()
        for label, slot in (
            (_("Add"), self._add_panel_rule),
            (_("Update selected"), self._update_panel_rule),
            (_("Delete"), self._delete_panel_rule),
            (_("Move up"), lambda: self._move_panel_rule(-1)),
            (_("Move down"), lambda: self._move_panel_rule(1)),
        ):
            button = QPushButton(label)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        buttons.addStretch()
        for label, slot in ((_("Import…"), self._import_panel_rules), (_("Export…"), self._export_panel_rules)):
            button = QPushButton(label)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        outer.addLayout(buttons)

        active = QGroupBox(_("Panel rules"))
        active_layout = QVBoxLayout(active)
        self.panel_rules_table = QTableWidget(0, 8)
        self.panel_rules_table.setHorizontalHeaderLabels(
            [
                _("#"),
                _("Panel"),
                _("Conditions"),
                _("HUD profile"),
                _("Priority"),
                _("Min sample"),
                _("Fallback"),
                _("Issues"),
            ]
        )
        self.panel_rules_table.verticalHeader().hide()
        self.panel_rules_table.verticalHeader().setDefaultSectionSize(34)
        self.panel_rules_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.panel_rules_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.panel_rules_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.panel_rules_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.panel_rules_table.setAlternatingRowColors(True)
        self.panel_rules_table.setMinimumHeight(150)
        self.panel_rules_table.itemSelectionChanged.connect(self._load_panel_rule_into_form)
        active_layout.addWidget(self.panel_rules_table)
        outer.addWidget(active, 1)

        preview = QGroupBox(_("Preview, by the same resolver the HUD uses"))
        preview_layout = QVBoxLayout(preview)
        self.panel_preview_sample = QSpinBox()
        self.panel_preview_sample.setRange(0, 1000000)
        self.panel_preview_sample.setValue(500)
        self.panel_preview_sample.valueChanged.connect(self._update_panel_preview)
        sample_row = QHBoxLayout()
        sample_row.addWidget(QLabel(_("Hands for this seat")))
        sample_row.addWidget(self.panel_preview_sample)
        sample_row.addStretch()
        preview_layout.addLayout(sample_row)
        self.panel_preview_label = QLabel()
        self.panel_preview_label.setWordWrap(True)
        self.panel_preview_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        preview_layout.addWidget(self.panel_preview_label)
        outer.addWidget(preview)

        self._create_panel_stat_picker(outer)

        # Ticked only when the HUD would act on it: rules nobody said yes to are
        # off at every table, so the box says so instead of asking on opening.
        self.panel_rules_enabled.setChecked(
            bool(getattr(self.config, "hud_panel_rules_enabled", False))
            and dynamic_panels_consent.is_confirmed(self._dynamic_panels_answers())
        )
        self.panel_rules_enabled.toggled.connect(self._dynamic_panels_toggled)
        if self.panel_rules_fallback:
            index = self.panel_rule_fallback_combo.findText(self.panel_rules_fallback)
            if index >= 0:
                self.panel_rule_fallback_combo.setCurrentIndex(index)
        self._refresh_panel_rules_table()
        # This tab stacked seven sections and measured 880 px of minimum height,
        # which alone set the height of the whole dialog. It scrolls now, so the
        # rules table and the preview stay reachable on a short screen.
        self.tabs.addTab(wrap_in_scroll(tab), _("🧩 Dynamic Panels"))
        # The grids are laid out once here so the tab is never shown empty; the
        # width the dialog ends up with arrives with the resize event below.
        self._reflow_panel_fields(self.width())

    def _profile_action_buttons(self) -> tuple[QPushButton, ...]:
        """The header's profile actions, in the order the menu shows them."""
        return (
            self.add_profile_btn,
            self.dup_profile_btn,
            self.rename_profile_btn,
            self.del_profile_btn,
            self.export_profile_btn,
            self.import_profile_btn,
        )

    def _fit_profile_actions(self, width: int) -> None:
        """Six buttons, or one menu when the window cannot hold them.

        Both arrangements carry the same six actions; the menu only changes how
        many clicks they cost, and it is what lets the dialog be narrowed past
        the width the buttons need.
        """
        wide = width >= NARROW_HEADER_WIDTH
        for button in self._profile_action_buttons():
            button.setVisible(wide)
        self.profile_actions_btn.setVisible(not wide)

    def _reflow_panel_fields(self, width: int) -> None:
        """Lay the Dynamic Panels fields out for ``width``.

        The selectors and the "Then show" fields are the same widgets at every
        width; only how many fit on a row changes. Four across is the design,
        two once the captions would wrap, one when even two combos side by side
        would be unreadable.
        """
        columns = column_count(width, PANEL_FIELD_BREAKPOINTS)
        for grid in (
            getattr(self, "panel_selector_grid", None),
            getattr(self, "panel_behaviour_grid", None),
        ):
            if grid is not None:
                grid.reflow(columns)

    def resizeEvent(self, event) -> None:  # noqa: ANN001 - Qt signature
        super().resizeEvent(event)
        width = event.size().width()
        self._reflow_panel_fields(width)
        self._fit_profile_actions(width)

    def showEvent(self, event) -> None:  # noqa: ANN001 - Qt signature
        super().showEvent(event)
        self._reflow_panel_fields(self.width())
        self._fit_profile_actions(self.width())

    def _create_panel_stat_picker(self, outer: QVBoxLayout) -> None:
        """The stat picker: the column-backed stats and the analytics ones.

        The analytics entries of #306 carry what the issue asks the picker to
        show -- the filters they apply, the format, the sample threshold and the
        popups that already bind them -- and adding one to a block writes those
        attributes into the configuration, so the block says where its number
        comes from instead of depending on what the code knew that day.

        It is folded by default: the catalogue runs to every analytics stat the
        app knows, and unfolded it pushed the rules table below the fold of the
        tab. The header keeps the count in view, so a folded section still says
        what it holds.
        """
        self.panel_stat_section = CollapsibleSection(
            _("Analytics-backed stats"),
            expanded=False,
            tooltip=_("Stats whose value comes from the analytics layer rather than a column."),
        )
        layout = QVBoxLayout(self.panel_stat_section.body())
        layout.setContentsMargins(0, 0, 0, 0)
        self.panel_stat_combo = QComboBox()
        self.panel_stat_combo.setMinimumWidth(0)
        self.panel_stat_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.panel_stat_combo.setMinimumContentsLength(18)
        self.panel_stat_combo.currentIndexChanged.connect(self._update_panel_stat_detail)
        self.panel_stat_detail = QLabel()
        self.panel_stat_detail.setWordWrap(True)
        self.panel_stat_block_combo = QComboBox()
        self.panel_stat_add_button = QPushButton(_("Add to block"))
        self.panel_stat_add_button.clicked.connect(self._add_panel_stat_to_block)
        row = QHBoxLayout()
        row.addWidget(self.panel_stat_combo, 1)
        row.addWidget(self.panel_stat_block_combo)
        row.addWidget(self.panel_stat_add_button)
        layout.addLayout(row)
        layout.addWidget(self.panel_stat_detail)
        outer.addWidget(self.panel_stat_section)
        self._refresh_panel_stat_choices()

    def _panel_vocabularies(self) -> dict[str, list[str]]:
        """The selector values only the loaded configuration knows."""
        limits = {"nl", "pl", "fl", "cn"}
        seats = {str(value) for value in range(2, 11)}
        for game in (getattr(self.config, "supported_games", {}) or {}):
            for game_type in ("ring", "tour"):
                try:
                    params = self.config.get_supported_games_parameters(game, game_type)
                except Exception:  # intentional broad catch: a missing game is not a broken tab
                    continue
                if not isinstance(params, dict):
                    continue
                limit = str(params.get("limitType") or params.get("limit_type") or "").strip()
                if limit:
                    limits.add(limit)
                max_seats = params.get("maxSeats") or params.get("max_seats")
                if max_seats:
                    seats.add(str(max_seats))
        return {
            "site": sorted(getattr(self.config, "supported_sites", {}) or {}),
            "game": sorted(getattr(self.config, "supported_games", {}) or {}),
            "limit": sorted(limits),
            "seats": sorted(seats, key=int),
            "profile": sorted(getattr(self.config, "stat_sets", {}) or {}),
            "situation": list(self._situation_words()),
            "situation_group": list(self._situation_words(groups=True)),
            "primary_situation": list(self._situation_words()),
        }

    @staticmethod
    def _situation_words(*, groups: bool = False) -> tuple[str, ...]:
        """The situation vocabulary of #294, so the labels are not typed by hand."""
        try:
            from fpdb_3_legacy import player_situations
        except Exception:  # intentional broad catch: a missing layer must not break the tab
            return ()
        attribute = "group" if groups else "label"
        return tuple(sorted({str(getattr(rule, attribute, "") or "") for rule in player_situations.SITUATION_RULES} - {""}))

    def _panel_selector_widget(self, field) -> Any:
        if field.kind == "bool":
            combo = QComboBox()
            combo.addItem(_("ANY"), None)
            combo.addItem(_("Yes"), True)
            combo.addItem(_("No"), False)
            return combo
        if field.kind == "range":
            holder = QWidget()
            layout = QHBoxLayout(holder)
            layout.setContentsMargins(0, 0, 0, 0)
            holder.low_edit = QLineEdit()
            holder.high_edit = QLineEdit()
            for entry in (holder.low_edit, holder.high_edit):
                entry.setMaximumWidth(64)
                entry.setPlaceholderText("—")
                layout.addWidget(entry)
                entry.textChanged.connect(self._update_panel_preview)
            return holder
        combo = QComboBox()
        combo.setEditable(not field.choices)
        combo.addItem(_("ANY"), "")
        for choice in field.choices:
            combo.addItem(str(choice), str(choice))
        return combo

    def _panel_selector_hook(self, widget, name: str = "") -> None:
        """Repreview whenever a selector moves."""
        if isinstance(widget, QComboBox):
            widget.currentIndexChanged.connect(self._update_panel_preview)
            if name:
                widget.currentIndexChanged.connect(
                    lambda _index, selector=name: getattr(self, "_preserved_selector_values", {}).pop(selector, None)
                )

    def _known_panel_names(self) -> list[str]:
        """The panels a block can actually carry: the library, then the config's.

        The library's names come first because they are what a rule means by
        default -- a user who has not drawn the block yet still has to be able to
        name the panel, and only the shipped rules know those names.

        The panels the current rules name are deliberately **not** in here: this
        list is what a rule is checked against, and a rule validating itself
        would make every typo a known block.
        """
        names: list[str] = []
        try:
            from fpdb_3_legacy import hud_situation

            for rule in hud_situation.load_source("builtin")[0]:
                if rule.panel not in names:
                    names.append(rule.panel)
        except (OSError, ValueError):  # a broken library must not break the tab
            log.debug("the shipped panel library could not be read", exc_info=True)
        for name, profile in (getattr(self, "hud_profiles", None) or {}).items():
            blocks = profile.get("blocks") if isinstance(profile, dict) else None
            for block in blocks or []:
                for key in ("id", "label"):
                    value = str(block.get(key, "") or "").strip()
                    if value and value not in names:
                        names.append(value)
            if name and name not in names:
                names.append(name)
        return names

    def _panel_selector_values(self) -> dict[str, Any]:
        """The conditions the selector widgets state, in the engine's vocabulary.

        A selector left on ANY states nothing, which is what an unconstrained
        dimension is: a rule that does not mention the street is a rule about
        every street.
        """
        from fpdb_3_legacy import hud_panel_editor as editor

        values: dict[str, Any] = {}
        for name, widget in self.panel_selector_widgets.items():
            field = editor.selector_field(name)
            if field is None or name == "profile":
                continue
            if field.kind == "bool":
                value = widget.currentData()
            elif field.kind == "range":
                low = widget.low_edit.text().strip()
                high = widget.high_edit.text().strip()
                if not low and not high:
                    continue
                try:
                    value = [int(low) if low else None, int(high) if high else None]
                except ValueError:
                    continue
            else:
                preserved = getattr(self, "_preserved_selector_values", {}).get(name)
                if preserved is not None:
                    values[name] = list(preserved) if isinstance(preserved, tuple) else preserved
                    continue
                text = (widget.currentText() if widget.isEditable() else str(widget.currentData() or "")).strip()
                if not text:
                    continue
                value = [text] if name == "situation" else text
            if value is None:
                continue
            values[name] = value
        return values

    def _panel_behaviour(self) -> dict[str, Any]:
        return {
            "panel": self.panel_rule_panel_combo.currentText().strip(),
            "profile": str(self.panel_rule_profile_combo.currentData() or "all"),
            "rule_id": self.panel_rule_id.text().strip(),
            "min_sample": int(self.panel_rule_min_sample.value()),
            "sample": self.panel_rule_sample.text().strip() or "n",
            "fallback": str(self.panel_rule_fallback_combo.currentText() or "").strip(),
            "priority": int(self.panel_rule_priority.value()),
            "enabled": self.panel_rule_enabled.isChecked(),
        }

    def _panel_draft(self):
        from fpdb_3_legacy import hud_panel_editor as editor

        behaviour = self._panel_behaviour()
        return editor.PanelRuleDraft(conditions=self._panel_selector_values(), **behaviour)

    def _add_panel_rule(self) -> None:
        draft = self._panel_draft()
        try:
            rule = draft.to_rule(len(self.panel_rules))
        except ValueError as error:
            QMessageBox.warning(self, _("Cannot add this rule"), str(error))
            return
        if any(existing.selector() == rule.selector() for existing in self.panel_rules):
            QMessageBox.warning(
                self, _("Duplicate rule"), _("A panel rule with these conditions and this profile already exists.")
            )
            return
        self.panel_rules.append(rule)
        self._refresh_panel_rules_table()

    def _update_panel_rule(self) -> None:
        row = self.panel_rules_table.currentRow()
        if not 0 <= row < len(self.panel_rules):
            QMessageBox.information(self, _("Update rule"), _("Select a rule to update first."))
            return
        draft = self._panel_draft()
        try:
            replaced = draft.to_rule(row)
        except ValueError as error:
            QMessageBox.warning(self, _("Cannot update this rule"), str(error))
            return
        self.panel_rules[row] = replaced
        self._refresh_panel_rules_table()
        self.panel_rules_table.setCurrentCell(row, 0)

    def _delete_panel_rule(self) -> None:
        row = self.panel_rules_table.currentRow()
        if not 0 <= row < len(self.panel_rules):
            return
        self.panel_rules.pop(row)
        self._renumber_panel_rules()

    def _move_panel_rule(self, delta: int) -> None:
        """Reordering matters: file order is the last tie-breaker of the resolver."""
        row = self.panel_rules_table.currentRow()
        target = row + delta
        if not 0 <= row < len(self.panel_rules) or not 0 <= target < len(self.panel_rules):
            return
        self.panel_rules[row], self.panel_rules[target] = self.panel_rules[target], self.panel_rules[row]
        self._renumber_panel_rules()
        self.panel_rules_table.setCurrentCell(target, 0)

    def _renumber_panel_rules(self) -> None:
        from fpdb_3_legacy import hud_situation

        self.panel_rules = hud_situation.number_rules(self.panel_rules)
        self._refresh_panel_rules_table()

    def _load_panel_rule_into_form(self) -> None:
        """Put the selected row back in the form, so editing is not retyping."""
        from fpdb_3_legacy import hud_panel_editor as editor

        row = self.panel_rules_table.currentRow()
        if not 0 <= row < len(self.panel_rules):
            return
        draft = editor.PanelRuleDraft.from_rule(self.panel_rules[row])
        for name, widget in self.panel_selector_widgets.items():
            field = editor.selector_field(name)
            value = draft.conditions.get(name)
            if field is None or field.kind == "range":
                if field is not None and field.kind == "range":
                    pair = value if isinstance(value, (list, tuple)) else [value, value]
                    widget.low_edit.setText("" if pair[0] is None else str(pair[0]))
                    widget.high_edit.setText("" if len(pair) < 2 or pair[1] is None else str(pair[1]))
                continue
            if field.kind == "bool":
                index = widget.findData(value if value is not None else None)
                widget.setCurrentIndex(max(0, index))
                continue
            text = "" if value is None else (value[0] if isinstance(value, (list, tuple)) and value else str(value))
            index = widget.findText(str(text))
            widget.setCurrentIndex(index if index >= 0 else 0)
            # Set the widget first: currentIndexChanged clears preserved
            # values when a selector changes. Store the full collection after
            # that signal so updating a rule does not collapse e.g.
            # street=["turn", "river"] to only its first item.
            if isinstance(value, (list, tuple)):
                if not hasattr(self, "_preserved_selector_values"):
                    self._preserved_selector_values = {}
                self._preserved_selector_values[name] = list(value)
        self.panel_rule_panel_combo.setCurrentText(draft.panel)
        self.panel_rule_profile_combo.setCurrentIndex(max(0, self.panel_rule_profile_combo.findData(draft.profile)))
        self.panel_rule_priority.setValue(int(draft.priority))
        self.panel_rule_min_sample.setValue(int(draft.min_sample))
        self.panel_rule_sample.setText(draft.sample or "n")
        self.panel_rule_id.setText(draft.rule_id)
        self.panel_rule_enabled.setChecked(bool(draft.enabled))
        index = self.panel_rule_fallback_combo.findText(draft.fallback)
        self.panel_rule_fallback_combo.setCurrentIndex(index if index >= 0 else 0)

    def _refresh_panel_rules_table(self) -> None:
        from fpdb_3_legacy import hud_panel_editor as editor

        issues = editor.issues_by_index(self.panel_rules, self._known_panel_names())
        self.panel_rules_table.blockSignals(True)
        self.panel_rules_table.setRowCount(len(self.panel_rules))
        for row, rule in enumerate(self.panel_rules):
            self.panel_rules_table.setRowHeight(row, 34)
            conditions = " ".join(f"{name}={editor.readable(value)}" for name, value in sorted(rule.when.items()))
            values = [
                str(row + 1),
                rule.panel,
                conditions or _("always"),
                rule.profile,
                str(rule.priority),
                str(rule.min_sample) if rule.min_sample else "",
                rule.fallback,
                "",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.panel_rules_table.setItem(row, column, item)
            row_issues = issues.get(row, ())
            if row_issues:
                issue_item = self.panel_rules_table.item(row, 7)
                severity = "⚠" if any(issue.severity == "duplicate" for issue in row_issues) else "!"
                if issue_item is not None:
                    issue_item.setText(severity)
                    issue_item.setToolTip("\n".join(issue.message for issue in row_issues))
            if not rule.enabled:
                row_item = self.panel_rules_table.item(row, 0)
                if row_item is not None:
                    row_item.setToolTip(_("Disabled: this rule never matches."))
        self.panel_rules_table.blockSignals(False)
        self._update_panel_preview()

    def _panel_preview_rules(self) -> list[Any]:
        """The rules as the preview resolves them, including the form's draft."""
        return list(self.panel_rules)

    def _update_panel_preview(self, *_args: Any) -> None:
        """Say which panel wins for the selectors, and why the others did not."""
        from fpdb_3_legacy import hud_panel_editor as editor

        if not hasattr(self, "panel_preview_label"):
            return
        fallback = str(self.panel_rule_fallback_combo.currentText() or "").strip()
        hands = int(self.panel_preview_sample.value())
        preview = editor.preview(
            self._panel_selector_values(),
            self._panel_preview_rules(),
            profile=str(self.panel_rule_profile_combo.currentData() or "all"),
            fallback=fallback,
            samples={"n": hands, "opportunities": hands},
            panels=self._known_panel_names(),
            enabled=self.panel_rules_enabled.isChecked() or bool(self.panel_rules),
        )
        lines = [preview.describe(), ""]
        for outcome in preview.outcomes:
            if outcome.matched or outcome.reason.startswith("condition"):
                mark = "✔" if outcome.shown else ("∅" if not outcome.matched else "⊘")
                lines.append(f"{mark} {outcome.panel}: {outcome.reason}")
        self.panel_preview_label.setText("\n".join(lines))
        self._refresh_unsaved_indicator()

    def _refresh_panel_stat_choices(self) -> None:
        from fpdb_3_legacy import hud_panel_editor as editor

        try:
            from fpdb_3_legacy import popup_packs

            packs = popup_packs.get_registry()
        except Exception:  # intentional broad catch: a missing pack library must not break the tab
            log.debug("popup packs unavailable", exc_info=True)
            packs = None
        self.panel_stat_choices = editor.stat_choices(config=self.config, packs=packs)
        self.panel_stat_combo.clear()
        for choice in self.panel_stat_choices:
            # The source is part of the key: a registry stat and a declarative one
            # can share a name, and a picker that cannot tell them apart would
            # silently add the wrong one.
            self.panel_stat_combo.addItem(f"{choice.label} [{choice.origin()}]", editor.choice_key(choice))
        section = getattr(self, "panel_stat_section", None)
        if section is not None:
            section.set_summary(_("{count} available").format(count=len(self.panel_stat_choices)))
        self._refresh_panel_stat_blocks()
        self._update_panel_stat_detail()

    def _current_panel_choice(self):
        from fpdb_3_legacy import hud_panel_editor as editor

        key = self.panel_stat_combo.currentData()
        return next((choice for choice in self.panel_stat_choices if editor.choice_key(choice) == key), None)

    def _update_panel_stat_detail(self, *_args: Any) -> None:
        if not hasattr(self, "panel_stat_detail"):
            return
        choice = self._current_panel_choice()
        self.panel_stat_detail.setText(choice.describe() if choice else "")

    def _refresh_panel_stat_blocks(self) -> None:
        """The blocks the current profile has, as targets for a new stat."""
        if not hasattr(self, "panel_stat_block_combo"):
            return
        self.panel_stat_block_combo.clear()
        _name, profile = self._current_profile()
        blocks = profile.get("blocks") if isinstance(profile, dict) else None
        if blocks:
            for index, block in enumerate(blocks):
                label = str(block.get("label") or block.get("id") or f"#{index + 1}")
                self.panel_stat_block_combo.addItem(label, index)
        else:
            self.panel_stat_block_combo.addItem(_("the profile grid"), None)

    def _add_panel_stat_to_block(self) -> None:
        """Put the chosen stat in the chosen block, declarative attributes and all."""
        from fpdb_3_legacy import hud_panel_editor as editor

        choice = self._current_panel_choice()
        _name, profile = self._current_profile()
        if choice is None or profile is None:
            QMessageBox.information(self, _("Add stat"), _("Pick a HUD profile first."))
            return
        block_index = self.panel_stat_block_combo.currentData()
        container = self._item_container(profile, block_index)
        row, col = layout_model.first_free_cell(container)
        attributes = editor.stat_entry_attributes(choice, grid=(row, col))
        item = {
            "row": row,
            "col": col,
            "stat": choice.name,
            "click": "",
            "popup": "",
        }
        for key, value in attributes.items():
            item[key if key != "name" else "stat"] = value
        layout_model.add(container, "stat", item, row, col)
        self._refresh_profile(select=item)

    def _import_panel_rules(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        from fpdb_3_legacy import hud_panel_editor as editor

        path, _selected = QFileDialog.getOpenFileName(
            self, _("Import panel rules"), "", _("Panel documents (*.json)")
        )
        if not path:
            return
        try:
            document = editor.load_document(path)
            imported = editor.import_document(
                document, known_stats=[choice.name for choice in getattr(self, "panel_stat_choices", ())]
            )
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, _("Cannot import"), str(error))
            return
        self.panel_rules = list(imported.rules)
        self._apply_imported_panel_stats(imported.stats)
        if imported.fallback:
            self.panel_rules_fallback = imported.fallback
            index = self.panel_rule_fallback_combo.findText(imported.fallback)
            if index >= 0:
                self.panel_rule_fallback_combo.setCurrentIndex(index)
        self.panel_rules_enabled.setChecked(True)
        self._refresh_panel_rules_table()
        message = _("Imported {count} rule(s).").format(count=len(self.panel_rules))
        if imported.warnings:
            message += "\n" + "\n".join(imported.warnings)
        QMessageBox.information(self, _("Import panel rules"), message)

    def _export_panel_rules(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        from fpdb_3_legacy import hud_panel_editor as editor

        path, _selected = QFileDialog.getSaveFileName(
            self, _("Export panel rules"), "hud-panels.json", _("Panel documents (*.json)")
        )
        if not path:
            return
        try:
            document = editor.export_document(
                self.panel_rules,
                fallback=self.panel_rules_fallback,
                stats=self._panel_stat_bindings(),
            )
            editor.save_document(document, path)
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, _("Cannot export"), str(error))
            return
        QMessageBox.information(self, _("Export panel rules"), _("Wrote {path}").format(path=path))

    def _panel_stat_bindings(self) -> list[dict[str, Any]]:
        """Serialize analytics-backed bindings with their profile location."""
        bindings: list[dict[str, Any]] = []
        for profile_name, profile in (getattr(self, "hud_profiles", {}) or {}).items():
            blocks = profile.get("blocks") if isinstance(profile, dict) else None
            containers = enumerate(blocks) if blocks else [(None, profile)]
            for block_index, container in containers:
                for stat in container.get("stats", []):
                    if stat.get("data_source") != "analytics":
                        continue
                    entry = {
                        "name": stat.get("stat", ""),
                        "source": stat.get("data_source", "analytics"),
                        "profile": profile_name,
                        "row": stat.get("row", 0),
                        "col": stat.get("col", 0),
                    }
                    if block_index is not None:
                        entry["block"] = block_index
                    entry.update({key: value for key, value in stat.items() if key.startswith("data_")})
                    bindings.append(entry)
        return bindings

    def _apply_imported_panel_stats(self, entries: tuple[dict[str, Any], ...]) -> None:
        """Place imported stat bindings in the selected or named profiles."""
        from fpdb_3_legacy import hud_panel_editor as editor

        choices = {(choice.source, choice.name): choice for choice in getattr(self, "panel_stat_choices", ())}
        for entry in entries:
            name = str(entry.get("name", "")).strip()
            source = str(entry.get("source", "analytics")).strip() or "analytics"
            choice = choices.get((source, name)) or choices.get(("analytics", name))
            if choice is None:
                continue
            profile_name = str(entry.get("profile") or self.profile_combo.currentText())
            profile = self.hud_profiles.get(profile_name)
            if profile is None:
                continue
            block = entry.get("block")
            try:
                block_index = int(block) if block is not None else None
            except (TypeError, ValueError):
                block_index = None
            container = self._item_container(profile, block_index)
            # The file's cell when it is free, else the first free one: a taken
            # cell would hold two stats, and the HUD keeps only one of them.
            try:
                row, col = int(entry["row"]), int(entry["col"])
            except (KeyError, TypeError, ValueError):
                row, col = -1, -1
            if not layout_model.can_place(container, row, col):
                row, col = layout_model.first_free_cell(container)
            item = {"row": row, "col": col, "stat": choice.name, "click": "", "popup": ""}
            item.update(editor.stat_entry_attributes(choice, grid=(row, col)))
            item.update({key: value for key, value in entry.items() if key.startswith("data_")})
            layout_model.add(container, "stat", item, row, col)
        self._refresh_profile()

    def _dynamic_panels_answers(self) -> Any:
        return dynamic_panels_consent.consent_path(getattr(self.config, "file", None))

    def _dynamic_panels_toggled(self, on: bool) -> None:
        """Ticking -- or importing rules, which ticks -- asks first; a no unticks."""
        if on and not confirm_dynamic_panels(self, self._dynamic_panels_answers()):
            self.panel_rules_enabled.blockSignals(True)
            self.panel_rules_enabled.setChecked(False)
            self.panel_rules_enabled.blockSignals(False)
        self._refresh_unsaved_indicator()

    def _persist_panel_rules(self) -> None:
        """Hand the rules to the configuration, or leave it exactly as it was.

        Untouched means untouched: a user who never opens the tab does not get a
        section rewritten on every save, which keeps the static HUD static.
        """
        from fpdb_3_legacy import hud_panel_editor as editor

        setter = getattr(self.config, "set_hud_panel_rules", None)
        if setter is None:
            return
        enabled = self.panel_rules_enabled.isChecked()
        touched = enabled or self.panel_rules or bool(getattr(self.config, "hud_panel_rules_enabled", False))
        if not touched:
            return
        duplicates = [issue for issue in editor.rule_issues(self.panel_rules) if issue.severity == "duplicate"]
        if duplicates:
            raise ValueError(duplicates[0].message)
        setter(self.panel_rules, fallback=self.panel_rules_fallback, enabled=enabled)

    def save_changes(self) -> bool:
        """Write everything and close; False (and a message) when it failed."""
        try:
            # We need to update the XML directly for the stat sets
            if hasattr(self.config, "doc") and self.config.doc:
                # Find the stat_sets parent node
                stat_sets_nodes = self.config.doc.getElementsByTagName("stat_sets")
                if not stat_sets_nodes:
                    # Create stat_sets node if it doesn't exist
                    root = self.config.doc.documentElement
                    stat_sets_node = self.config.doc.createElement("stat_sets")
                    root.appendChild(stat_sets_node)
                else:
                    stat_sets_node = stat_sets_nodes[0]

                # A renamed profile keeps its <ss>, renamed in place, and the
                # game defaults that named it follow. The nodes are found by
                # their names in the file before any of them is renamed.
                renames = getattr(self, "_renamed", {})
                existing: dict[str, Any] = {}
                for ss_node in self.config.doc.getElementsByTagName("ss"):
                    existing.setdefault(ss_node.getAttribute("name"), ss_node)
                editor_state.follow_renames(self.config.doc, renames)
                editor_state.follow_renames_in_games(getattr(self.config, "supported_games", None), renames)

                # For each profile, update or create the stat set in XML
                for profile_name, profile_data in self.hud_profiles.items():
                    source = editor_state.file_name_for(profile_name, renames)
                    stat_set_node = existing.get(source) if source is not None else None
                    if stat_set_node is not None:
                        stat_set_node.setAttribute("name", profile_name)

                    if stat_set_node is None:
                        # Create new stat set node if it doesn't exist
                        # Add newline and indentation before the new node
                        indent = self.config.doc.createTextNode("\n        ")
                        stat_sets_node.appendChild(indent)

                        stat_set_node = self.config.doc.createElement("ss")
                        stat_set_node.setAttribute("name", profile_name)
                        stat_sets_node.appendChild(stat_set_node)

                    profile_io.write_stat_set_attributes(stat_set_node, profile_data)
                    rows, cols = profile_io.stat_set_size(profile_data)
                    self._write_profile_stats(stat_set_node, profile_data, rows, cols)
                self._renamed = {}

                # Add final newline after all stat sets
                if (
                    stat_sets_node.lastChild
                    and stat_sets_node.lastChild.nodeType == stat_sets_node.lastChild.ELEMENT_NODE
                ):
                    final_indent = self.config.doc.createTextNode("\n    ")
                    stat_sets_node.appendChild(final_indent)

                # Also update the config.stat_sets for consistency
                self.config.stat_sets = {}
                for ss_node in stat_sets_node.getElementsByTagName("ss"):
                    profile_name = ss_node.getAttribute("name")
                    self.config.stat_sets[profile_name] = Configuration.Stat_sets(ss_node)

                # Prune <ss> nodes (and the parsed cache) for deleted profiles so
                # deletions actually persist instead of leaving orphan stat-sets.
                for ss_node in list(stat_sets_node.getElementsByTagName("ss")):
                    if ss_node.getAttribute("name") not in self.hud_profiles:
                        ss_node.parentNode.removeChild(ss_node)
                for stale in [n for n in getattr(self.config, "stat_sets", {}) if n not in self.hud_profiles]:
                    self.config.stat_sets.pop(stale, None)

            # Save popup windows
            if hasattr(self.config, "doc") and self.config.doc:
                # Find or create popup_windows section
                popup_windows_nodes = self.config.doc.getElementsByTagName("popup_windows")
                if popup_windows_nodes:
                    popup_windows_node = popup_windows_nodes[0]
                    # Clear existing popup nodes
                    while popup_windows_node.firstChild:
                        popup_windows_node.removeChild(popup_windows_node.firstChild)
                else:
                    # Create popup_windows section
                    root = self.config.doc.documentElement
                    popup_windows_node = self.config.doc.createElement("popup_windows")
                    root.appendChild(popup_windows_node)

                # Add new popup nodes
                for popup_name, popup_data in sorted(self.popup_windows.items()):
                    # Add newline and indentation
                    indent = self.config.doc.createTextNode("\n        ")
                    popup_windows_node.appendChild(indent)

                    # Create popup node
                    pu_node = self.config.doc.createElement("pu")
                    pu_node.setAttribute("pu_name", popup_name)
                    pu_node.setAttribute("pu_class", popup_data["class"])
                    # Preserve the data-source attributes of imported popups
                    # (RangeChartPopup / BlockPopup) so they survive a save.
                    if popup_data.get("source"):
                        pu_node.setAttribute("pu_source", popup_data["source"])
                    if popup_data.get("group"):
                        pu_node.setAttribute("pu_group", popup_data["group"])
                    if popup_data.get("theme"):
                        pu_node.setAttribute("pu_theme", popup_data["theme"])
                    if popup_data.get("icon_provider"):
                        pu_node.setAttribute("pu_icon_provider", popup_data["icon_provider"])
                    if popup_data.get("title"):
                        pu_node.setAttribute("pu_title", popup_data["title"])
                    if popup_data.get("width"):
                        pu_node.setAttribute("pu_width", str(popup_data["width"]))
                    if popup_data.get("max_height"):
                        pu_node.setAttribute("pu_max_height", str(popup_data["max_height"]))

                    # Add stats
                    for stat in popup_data["stats"]:
                        stat_indent = self.config.doc.createTextNode("\n            ")
                        pu_node.appendChild(stat_indent)

                        pu_stat_node = self.config.doc.createElement("pu_stat")
                        pu_stat_node.setAttribute("pu_stat_name", stat["stat_name"])
                        if stat.get("submenu"):
                            pu_stat_node.setAttribute("pu_stat_submenu", stat["submenu"])
                        if stat.get("category"):
                            pu_stat_node.setAttribute("pu_stat_category", stat["category"])
                        if stat.get("label"):
                            pu_stat_node.setAttribute("pu_stat_label", stat["label"])
                        if stat.get("color"):
                            pu_stat_node.setAttribute("pu_stat_color", stat["color"])

                        pu_node.appendChild(pu_stat_node)

                    # Add final indent for popup
                    if popup_data["stats"]:
                        final_indent = self.config.doc.createTextNode("\n        ")
                        pu_node.appendChild(final_indent)

                    popup_windows_node.appendChild(pu_node)

                # Add final newline
                if self.popup_windows:
                    final_indent = self.config.doc.createTextNode("\n    ")
                    popup_windows_node.appendChild(final_indent)

            # Save general profiling settings
            hud_params = {
                "player_profiling": "True" if self.profiling_checkbox.isChecked() else "False",
                "profile_in_name": "True" if self.profile_in_name_checkbox.isChecked() else "False",
                "profile_min_hands": str(self.profile_min_hands_spin.value()),
            }
            if hasattr(self.config, "set_hud_ui_parameters"):
                self.config.set_hud_ui_parameters(hud_params)

            if hasattr(self.config, "set_hud_profile_rules"):
                # Use the same resolver here to keep duplicate detection and
                # runtime precedence semantics tied to one implementation.
                duplicates = HudProfileResolver(self.profile_rules).duplicate_selectors()
                if duplicates:
                    raise ValueError(_("Duplicate HUD profile selectors"))
                self.config.set_hud_profile_rules(self.profile_rules)

            self._persist_panel_rules()

            # Save to file
            if hasattr(self.config, "save"):
                self.config.save()
                # What is on disk now is what later edits are compared with.
                self._saved_state = self._editor_state(keep=True)
                self._refresh_unsaved_indicator()
                QMessageBox.information(self, _("Success"), _("HUD configuration saved successfully!"))
            else:
                QMessageBox.warning(
                    self,
                    _("Warning"),
                    _("Could not save to file. Config save method not available."),
                )

            self.accept()
            return True

        except Exception as e:  # intentional broad catch: GUI save-profiles boundary surfaces failure in a dialog
            QMessageBox.critical(self, _("Error"), _("Failed to save HUD profiles:\n{error}").format(error=e))
            return False

    def add_popup(self) -> None:
        """Add a new popup window."""
        from PySide6.QtWidgets import QInputDialog

        name, ok = QInputDialog.getText(self, _("New Popup"), _("Enter popup name:"))
        if ok and name and name not in self.popup_windows:
            self.popup_windows[name] = {
                "name": name,
                "class": "default",
                "theme": "",
                "icon_provider": "",
                "stats": [],
            }
            self.popup_combo.addItem(name)
            self.popup_combo.setCurrentText(name)

    def duplicate_popup(self) -> None:
        """Duplicate current popup."""
        if self.popup_combo.currentIndex() < 0:
            return
        current_name = self.popup_combo.currentText()
        from PySide6.QtWidgets import QInputDialog

        new_name, ok = QInputDialog.getText(self, _("Duplicate Popup"), _("New popup name:"))
        if ok and new_name and new_name not in self.popup_windows:
            import copy

            self.popup_windows[new_name] = copy.deepcopy(self.popup_windows[current_name])
            self.popup_windows[new_name]["name"] = new_name
            self.popup_combo.addItem(new_name)
            self.popup_combo.setCurrentText(new_name)

    def delete_popup(self) -> None:
        """Delete current popup."""
        if self.popup_combo.currentIndex() < 0:
            return
        popup_name = self.popup_combo.currentText()
        reply = QMessageBox.question(
            self,
            _("Delete Popup"),
            _("Are you sure you want to delete the popup '{name}'?").format(name=popup_name),
            QMessageBox.Yes | QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            current_index = self.popup_combo.currentIndex()
            del self.popup_windows[popup_name]
            self.popup_combo.removeItem(current_index)
            if self.popup_combo.count() > 0:
                self.popup_combo.setCurrentIndex(0)

    def add_popup_stat(self) -> None:
        """Add a stat to current popup."""
        if self.popup_combo.currentIndex() < 0:
            return

        dialog = PopupStatEditDialog(parent=self)
        if dialog.exec():
            stat_data = dialog.get_stat_data()
            popup_name = self.popup_combo.currentText()
            self.popup_windows[popup_name]["stats"].append(stat_data)
            self.on_popup_selected(self.popup_combo.currentIndex())

    def edit_popup_stat(self) -> None:
        """Edit selected stat in current popup."""
        if self.popup_combo.currentIndex() < 0:
            return

        current_row = self.popup_stats_list.currentRow()
        if current_row < 0:
            return

        popup_name = self.popup_combo.currentText()
        stats = self.popup_windows[popup_name]["stats"]
        if current_row >= len(stats):
            return

        dialog = PopupStatEditDialog(stats[current_row], parent=self)
        if dialog.exec():
            stats[current_row] = dialog.get_stat_data()
            self.on_popup_selected(self.popup_combo.currentIndex())

    def remove_popup_stat(self) -> None:
        """Remove selected stat from current popup."""
        if self.popup_combo.currentIndex() < 0:
            return

        current_row = self.popup_stats_list.currentRow()
        if current_row < 0:
            return

        popup_name = self.popup_combo.currentText()
        self.popup_windows[popup_name]["stats"].pop(current_row)
        self.on_popup_selected(self.popup_combo.currentIndex())

    def move_stat_up(self) -> None:
        """Move selected stat up in the list."""
        if self.popup_combo.currentIndex() < 0:
            return

        current_row = self.popup_stats_list.currentRow()
        if current_row <= 0:
            return

        popup_name = self.popup_combo.currentText()
        stats = self.popup_windows[popup_name]["stats"]
        stats[current_row], stats[current_row - 1] = stats[current_row - 1], stats[current_row]
        self.on_popup_selected(self.popup_combo.currentIndex())
        self.popup_stats_list.setCurrentRow(current_row - 1)

    def move_stat_down(self) -> None:
        """Move selected stat down in the list."""
        if self.popup_combo.currentIndex() < 0:
            return

        current_row = self.popup_stats_list.currentRow()
        popup_name = self.popup_combo.currentText()
        stats = self.popup_windows[popup_name]["stats"]

        if current_row < 0 or current_row >= len(stats) - 1:
            return

        stats[current_row], stats[current_row + 1] = stats[current_row + 1], stats[current_row]
        self.on_popup_selected(self.popup_combo.currentIndex())
        self.popup_stats_list.setCurrentRow(current_row + 1)


# --- Popup Stat Edit Dialog ---
