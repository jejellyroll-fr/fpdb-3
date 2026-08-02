#!/usr/bin/env python
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.loggingFpdb import get_logger
from fpdb_3_legacy.modern_hud_preferences.preview_widgets import ColorPreviewWidget

log = get_logger("modern_hud_preferences.dialogs")

class BlockPropertiesDialog(QDialog):
    """Edit a HUD panel's identity, sizing, position binding, and colours."""

    _POSITIONS = ["", "SB", "BB", "BTN", "CO", "MP", "EP"]
    _COLOR_FIELDS = (
        ("bgcolor", "Panel background"),
        ("fgcolor", "Panel text"),
        ("title_bgcolor", "Title background"),
        ("title_fgcolor", "Title text"),
        ("bordercolor", "Border"),
    )

    def __init__(self, block: dict, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(_("Block Properties"))
        self.setMinimumWidth(360)
        self._colors = {key: block.get(key, "") for key, _ in self._COLOR_FIELDS}

        form = QFormLayout(self)
        self.label_input = QLineEdit(block.get("label", ""))
        form.addRow("Label:", self.label_input)

        self.pos_combo = QComboBox()
        self.pos_combo.addItems(self._POSITIONS)
        cur = block.get("position", "")
        if cur and cur not in self._POSITIONS:
            self.pos_combo.addItem(cur)
        self.pos_combo.setCurrentText(cur)
        self.pos_combo.setToolTip(_("Show this panel only for a villain in this position (blank = always)"))
        form.addRow("Show for position:", self.pos_combo)

        self.cell_width_spin = QSpinBox()
        self.cell_width_spin.setRange(0, 300)
        self.cell_width_spin.setSpecialValueText("Automatic")
        self.cell_width_spin.setSuffix(" px")
        self.cell_width_spin.setValue(int(block.get("cell_width", 0) or 0))
        self.cell_width_spin.setToolTip(_("Minimum width of each statistic cell; Automatic keeps the legacy default"))
        form.addRow("Cell width:", self.cell_width_spin)

        self._btns = {}
        for key, caption in self._COLOR_FIELDS:
            btn = QPushButton()
            btn.clicked.connect(lambda _=False, k=key: self._pick(k))
            self._btns[key] = btn
            self._refresh_btn(key)
            form.addRow(f"{caption}:", btn)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _pick(self, key: str) -> None:

        initial = QColor(self._colors[key]) if self._colors[key] else QColor("#ffffff")
        col = QColorDialog.getColor(initial, self, "Pick colour")
        if col.isValid():
            self._colors[key] = col.name()
            self._refresh_btn(key)

    def _refresh_btn(self, key: str) -> None:
        colour = self._colors[key]
        btn = self._btns[key]
        btn.setText(colour or "(none)")
        btn.setStyleSheet(f"background:{colour};" if colour else "")

    def get_props(self) -> dict:
        return {
            "label": self.label_input.text(),
            "position": self.pos_combo.currentText(),
            "cell_width": self.cell_width_spin.value(),
            **self._colors,
        }


class AddStatDialog(QDialog):
    def __init__(self, stat=None, max_rows=5, max_cols=5, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(_("Add/Edit Statistic"))
        self.setMinimumWidth(600)

        # Initialize color values
        self.locolor = "#ff0000"
        self.midcolor = "#ffff00"
        self.hicolor = "#00ff00"

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(15, 15, 15, 15)

        # Position and statistic section
        position_group = QGroupBox("Position and Statistic")
        position_layout = QGridLayout()
        position_layout.setSpacing(10)

        # Row and column selection
        position_layout.addWidget(QLabel(_("Grid Position:")), 0, 0)

        pos_frame = QFrame()
        pos_layout = QHBoxLayout(pos_frame)
        pos_layout.setContentsMargins(0, 0, 0, 0)

        pos_layout.addWidget(QLabel(_("Row:")))
        self.row_input = QComboBox()
        self.row_input.addItems([str(i) for i in range(max_rows)])
        self.row_input.setMinimumWidth(60)
        pos_layout.addWidget(self.row_input)

        pos_layout.addSpacing(20)
        pos_layout.addWidget(QLabel(_("Column:")))
        self.col_input = QComboBox()
        self.col_input.addItems([str(i) for i in range(max_cols)])
        self.col_input.setMinimumWidth(60)
        pos_layout.addWidget(self.col_input)
        pos_layout.addStretch()

        position_layout.addWidget(pos_frame, 0, 1, 1, 2)

        # Statistic selection
        position_layout.addWidget(QLabel(_("Statistic:")), 1, 0)
        self.stat_input = QComboBox()
        self.stat_input.setEditable(True)
        stat_names = [
            "vpip",
            "pfr",
            "3bet",
            "fold_3bet",
            "wtsd",
            "wmsd",
            "flafq",
            "turn_afq",
            "river_afq",
            "cb1",
            "cb2",
            "cb3",
            "ffreq1",
            "ffreq2",
            "ffreq3",
            "agg",
            "agg_freq",
            "agg_fact",
            "cbet",
            "steal",
            "f_steal",
            "bbvpip",
            "hands",
            "balance",
            "profit100",
            "bb100",
            "rake100",
            "variance100",
            "three_B",
            "three_B_flop",
            "three_B_turn",
            "three_B_river",
            "fold_to_three_B_flop",
            "fold_to_three_B_turn",
            "fold_to_three_B_river",
            "four_B",
            "four_B_flop",
            "four_B_turn",
            "four_B_river",
            "open_flop",
            "open_turn",
            "open_river",
            "float_turn",
            "float_river",
            "face_raise_preflop",
            "face_raise_flop",
            "face_raise_turn",
            "face_raise_river",
            "first_raise_flop",
            "first_raise_turn",
            "first_raise_river",
            "fold_flop",
            "fold_turn",
            "fold_river",
            "fold_to_squeeze",
            "face_limpers",
            "straddle",
            "fold_to_allin",
            "f_bet_facing",
            "t_bet_facing",
            "r_bet_facing",
            "p_2bet_facing",
            "p_3bet_facing",
            "p_4bet_facing",
            "f_bet_made",
            "t_bet_made",
            "r_bet_made",
            "f_spr",
            "t_spr",
            "r_spr",
            "p_raise_made",
            "f_raise_made",
            "t_raise_made",
            "r_raise_made",
            "f_2bet_facing",
            "f_3bet_facing",
            "f_4bet_facing",
            "t_2bet_facing",
            "t_3bet_facing",
            "t_4bet_facing",
            "r_2bet_facing",
            "r_3bet_facing",
            "r_4bet_facing",
            "p_raise_facing",
            "f_raise_facing",
            "t_raise_facing",
            "r_raise_facing",
            "p_raise_made_2",
            "f_raise_made_2",
            "t_raise_made_2",
            "r_raise_made_2",
            "p_5bet_facing",
            "amt_blind",
            "amt_bet_p",
            "amt_bet_f",
            "amt_bet_t",
            "amt_bet_r",
            "amt_bet_ttl",
            "totalprofit",
            "playershort",
            "n",
            "wtsd",
            "wmsd",
            "saw_f",
            "cb_flop",
            "cb_turn",
            "cb_river",
            "f_cb1",
            "f_cb2",
            "f_cb3",
        ]
        self.stat_input.addItems(sorted(stat_names))
        position_layout.addWidget(self.stat_input, 1, 1, 1, 2)

        position_group.setLayout(position_layout)
        main_layout.addWidget(position_group)

        # Actions section
        actions_group = QGroupBox("Actions")
        actions_layout = QGridLayout()
        actions_layout.setSpacing(10)

        actions_layout.addWidget(QLabel(_("Click Action:")), 0, 0)
        self.click_input = QLineEdit()
        self.click_input.setPlaceholderText(_("Optional: Action when stat is clicked"))
        actions_layout.addWidget(self.click_input, 0, 1)

        actions_layout.addWidget(QLabel(_("Popup:")), 1, 0)
        self.popup_input = QLineEdit()
        self.popup_input.setPlaceholderText(_("Optional: Popup to show on hover"))
        actions_layout.addWidget(self.popup_input, 1, 1)

        actions_group.setLayout(actions_layout)
        main_layout.addWidget(actions_group)

        # Color configuration section
        color_group = QGroupBox("Color Configuration")
        color_layout = QVBoxLayout()
        color_layout.setSpacing(10)

        # Color thresholds grid
        threshold_layout = QGridLayout()
        threshold_layout.setSpacing(10)

        # Low threshold row
        threshold_layout.addWidget(QLabel(_("Low Range:")), 0, 0)

        low_frame = QFrame()
        low_layout = QHBoxLayout(low_frame)
        low_layout.setContentsMargins(0, 0, 0, 0)

        low_layout.addWidget(QLabel(_("Values below")))
        self.loth_input = QSpinBox()
        self.loth_input.setRange(0, 100)
        self.loth_input.setValue(20)
        self.loth_input.setMinimumWidth(70)
        self.loth_input.valueChanged.connect(self.update_preview)
        low_layout.addWidget(self.loth_input)
        low_layout.addWidget(QLabel(_("show as")))

        self.locolor_btn = QPushButton()
        self.locolor_btn.setFixedSize(80, 30)
        self.locolor_btn.setStyleSheet(f"background-color: {self.locolor};")
        self.locolor_btn.clicked.connect(lambda: self.choose_color("low"))
        low_layout.addWidget(self.locolor_btn)
        low_layout.addStretch()

        threshold_layout.addWidget(low_frame, 0, 1)

        # High threshold row
        threshold_layout.addWidget(QLabel(_("High Range:")), 1, 0)

        high_frame = QFrame()
        high_layout = QHBoxLayout(high_frame)
        high_layout.setContentsMargins(0, 0, 0, 0)

        high_layout.addWidget(QLabel(_("Values above")))
        self.hith_input = QSpinBox()
        self.hith_input.setRange(0, 100)
        self.hith_input.setValue(60)
        self.hith_input.setMinimumWidth(70)
        self.hith_input.valueChanged.connect(self.update_preview)
        high_layout.addWidget(self.hith_input)
        high_layout.addWidget(QLabel(_("show as")))

        self.hicolor_btn = QPushButton()
        self.hicolor_btn.setFixedSize(80, 30)
        self.hicolor_btn.setStyleSheet(f"background-color: {self.hicolor};")
        self.hicolor_btn.clicked.connect(lambda: self.choose_color("high"))
        high_layout.addWidget(self.hicolor_btn)
        high_layout.addStretch()

        threshold_layout.addWidget(high_frame, 1, 1)

        # Optional middle color
        self.use_midcolor = QCheckBox(_("Use middle color for values between thresholds"))
        self.use_midcolor.toggled.connect(self.toggle_midcolor)
        threshold_layout.addWidget(self.use_midcolor, 2, 0, 1, 2)

        mid_frame = QFrame()
        mid_layout = QHBoxLayout(mid_frame)
        mid_layout.setContentsMargins(20, 0, 0, 0)

        mid_layout.addWidget(QLabel(_("Middle color:")))
        self.midcolor_btn = QPushButton()
        self.midcolor_btn.setFixedSize(80, 30)
        self.midcolor_btn.setStyleSheet(f"background-color: {self.midcolor};")
        self.midcolor_btn.clicked.connect(lambda: self.choose_color("mid"))
        self.midcolor_btn.setEnabled(False)
        mid_layout.addWidget(self.midcolor_btn)
        mid_layout.addStretch()

        threshold_layout.addWidget(mid_frame, 3, 0, 1, 2)

        color_layout.addLayout(threshold_layout)
        color_group.setLayout(color_layout)
        main_layout.addWidget(color_group)

        # Color preview
        preview_group = QGroupBox("Color Preview")
        preview_layout = QVBoxLayout()
        preview_layout.setContentsMargins(10, 10, 10, 5)

        self.color_preview = ColorPreviewWidget()
        self.color_preview.setFixedHeight(60)
        preview_layout.addWidget(self.color_preview)

        preview_info = QLabel(_("Preview shows how statistic colors will change based on values"))
        preview_info.setProperty("class", "caption")
        preview_layout.addWidget(preview_info)

        preview_group.setLayout(preview_layout)
        main_layout.addWidget(preview_group)

        # Dialog buttons
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 10, 0, 0)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.button(QDialogButtonBox.Ok).setText(_("OK"))
        btn_box.button(QDialogButtonBox.Cancel).setText(_("Cancel"))
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        button_layout.addStretch()
        button_layout.addWidget(btn_box)

        main_layout.addLayout(button_layout)

        if stat:
            self.row_input.setCurrentText(str(stat["row"]))
            self.col_input.setCurrentText(str(stat["col"]))
            self.stat_input.setCurrentText(stat["stat"])
            self.click_input.setText(stat.get("click", ""))
            self.popup_input.setText(stat.get("popup", ""))

            # Load color settings if available
            if "stat_loth" in stat and stat["stat_loth"]:
                self.loth_input.setValue(int(float(stat["stat_loth"])))
            if "stat_hith" in stat and stat["stat_hith"]:
                self.hith_input.setValue(int(float(stat["stat_hith"])))
            if stat.get("stat_locolor"):
                self.locolor = stat["stat_locolor"]
                self.locolor_btn.setStyleSheet(f"background-color: {self.locolor};")
            if stat.get("stat_hicolor"):
                self.hicolor = stat["stat_hicolor"]
                self.hicolor_btn.setStyleSheet(f"background-color: {self.hicolor};")
            if stat.get("stat_midcolor"):
                self.midcolor = stat["stat_midcolor"]
                self.midcolor_btn.setStyleSheet(f"background-color: {self.midcolor};")
                self.use_midcolor.setChecked(True)
                self.midcolor_btn.setEnabled(True)

        # Initial preview update
        self.update_preview()

    def choose_color(self, color_type) -> None:
        color = QColorDialog.getColor()
        if color.isValid():
            if color_type == "low":
                self.locolor = color.name()
                self.locolor_btn.setStyleSheet(f"background-color: {self.locolor};")
            elif color_type == "mid":
                self.midcolor = color.name()
                self.midcolor_btn.setStyleSheet(f"background-color: {self.midcolor};")
            elif color_type == "high":
                self.hicolor = color.name()
                self.hicolor_btn.setStyleSheet(f"background-color: {self.hicolor};")
            self.update_preview()

    def toggle_midcolor(self, checked) -> None:
        self.midcolor_btn.setEnabled(checked)
        self.update_preview()

    def update_preview(self) -> None:
        low_threshold = self.loth_input.value()
        high_threshold = self.hith_input.value()
        use_mid_color = self.use_midcolor.isChecked()

        self.color_preview.set_colors(
            self.locolor,
            self.midcolor,
            self.hicolor,
            low_threshold,
            high_threshold,
            use_mid_color,
        )

    def get_stat(self):
        stat = {
            "row": int(self.row_input.currentText()),
            "col": int(self.col_input.currentText()),
            "stat": self.stat_input.currentText(),
            "click": self.click_input.text(),
            "popup": self.popup_input.text(),
            "stat_loth": str(self.loth_input.value()),
            "stat_hith": str(self.hith_input.value()),
            "stat_locolor": self.locolor,
            "stat_hicolor": self.hicolor,
        }

        # Only add midcolor if it's enabled
        if self.use_midcolor.isChecked():
            stat["stat_midcolor"] = self.midcolor
        else:
            stat["stat_midcolor"] = ""

        return stat


# --- Layout Selection Dialog for Exporting ---
class LayoutSelectionDialog(QDialog):
    """Dialog to select which layout sets to include in the HUD export."""

    def __init__(self, layout_sets, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(_("Export Layout Coordinates"))
        self.setMinimumSize(400, 300)

        layout = QVBoxLayout(self)

        info = QLabel(
            _(
                "Select the site layout coordinates you want to include in the package.\n"
                "This will let other users position the HUD boxes exactly like yours."
            )
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.list_widget = QListWidget()
        from PySide6.QtWidgets import QListWidgetItem

        for ls_name in sorted(layout_sets):
            item = QListWidgetItem(ls_name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            # By default, check all layout sets that are not default and not mucked
            if ls_name != "default" and "mucked" not in ls_name:
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)
            self.list_widget.addItem(item)

        layout.addWidget(self.list_widget)

        # Select all / none buttons
        btn_layout = QHBoxLayout()
        select_all_btn = QPushButton(_("Select All"))
        select_all_btn.clicked.connect(self.select_all)
        select_none_btn = QPushButton(_("Select None"))
        select_none_btn.clicked.connect(self.select_none)
        btn_layout.addWidget(select_all_btn)
        btn_layout.addWidget(select_none_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # OK/Cancel buttons
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def select_all(self) -> None:
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(Qt.CheckState.Checked)

    def select_none(self) -> None:
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(Qt.CheckState.Unchecked)

    def get_selected_layouts(self) -> list[str]:
        selected = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected.append(item.text())
        return selected


# --- Main Modern HUD Preferences Dialog ---


class PopupStatEditDialog(QDialog):
    def __init__(self, stat_data=None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(_("Edit Popup Statistic"))
        self.setMinimumWidth(400)

        # Main layout
        layout = QFormLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        # Stat name
        self.stat_name_input = QLineEdit()
        if stat_data:
            self.stat_name_input.setText(stat_data.get("stat_name", ""))
        layout.addRow("Statistic Name:", self.stat_name_input)

        # Submenu (optional)
        self.submenu_input = QLineEdit()
        self.submenu_input.setPlaceholderText(_("Optional: Submenu name for hierarchical popups"))
        if stat_data:
            self.submenu_input.setText(stat_data.get("submenu", ""))
        layout.addRow("Submenu:", self.submenu_input)

        self.category_combo = QComboBox()
        self.category_combo.addItems(
            ["auto", "player_info", "preflop", "flop", "turn", "river", "steal", "aggression", "general"]
        )
        if stat_data and stat_data.get("category"):
            self.category_combo.setCurrentText(stat_data["category"])
        self.category_combo.setToolTip(_("Override the automatic section used by ModernSubmenu"))
        layout.addRow("Section:", self.category_combo)

        # Dialog buttons
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addRow(btn_box)

    def get_stat_data(self):
        """Get the stat data from the dialog."""
        result = {
            "stat_name": self.stat_name_input.text(),
            "submenu": self.submenu_input.text(),
        }
        if self.category_combo.currentText() != "auto":
            result["category"] = self.category_combo.currentText()
        return result


# --- Popup Edit Dialog ---
class PopupEditDialog(QDialog):
    def __init__(self, popup_data=None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(_("Edit Popup Window"))
        self.setMinimumSize(600, 500)

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Basic info section
        info_group = QGroupBox("Popup Information")
        info_layout = QFormLayout()

        # Name input
        self.name_input = QLineEdit()
        if popup_data:
            self.name_input.setText(popup_data["name"])
        info_layout.addRow("Popup Name:", self.name_input)

        # Class selection
        self.class_combo = QComboBox()
        self.class_combo.addItems(["default", "Submenu", "Multicol"])
        if popup_data:
            self.class_combo.setCurrentText(popup_data["class"])
        info_layout.addRow("Popup Class:", self.class_combo)

        info_group.setLayout(info_layout)
        main_layout.addWidget(info_group)

        # Statistics section
        stats_group = QGroupBox("Statistics")
        stats_layout = QVBoxLayout()

        # Stats table
        self.stats_table = QTableWidget(0, 2)
        self.stats_table.setHorizontalHeaderLabels(["Statistic Name", "Submenu"])
        self.stats_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.stats_table.setMinimumHeight(250)
        stats_layout.addWidget(self.stats_table)

        # Stats buttons
        stats_btn_layout = QHBoxLayout()

        add_stat_btn = QPushButton(_("➕ Add Stat"))
        add_stat_btn.clicked.connect(self.add_stat)

        remove_stat_btn = QPushButton(_("➖ Remove Stat"))
        remove_stat_btn.clicked.connect(self.remove_stat)

        stats_btn_layout.addWidget(add_stat_btn)
        stats_btn_layout.addWidget(remove_stat_btn)
        stats_btn_layout.addStretch()

        stats_layout.addLayout(stats_btn_layout)
        stats_group.setLayout(stats_layout)
        main_layout.addWidget(stats_group)

        # Load existing stats if editing
        if popup_data and "stats" in popup_data:
            for stat in popup_data["stats"]:
                row = self.stats_table.rowCount()
                self.stats_table.insertRow(row)
                self.stats_table.setItem(row, 0, QTableWidgetItem(stat["stat_name"]))
                self.stats_table.setItem(row, 1, QTableWidgetItem(stat.get("submenu", "")))

        # Dialog buttons
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 15, 0, 0)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        button_layout.addStretch()
        button_layout.addWidget(btn_box)

        main_layout.addLayout(button_layout)

    def add_stat(self) -> None:
        """Add a new stat to the table."""
        row = self.stats_table.rowCount()
        self.stats_table.insertRow(row)
        self.stats_table.setItem(row, 0, QTableWidgetItem(""))
        self.stats_table.setItem(row, 1, QTableWidgetItem(""))
        # Make the new row editable
        self.stats_table.editItem(self.stats_table.item(row, 0))

    def remove_stat(self) -> None:
        """Remove selected stat from the table."""
        current_row = self.stats_table.currentRow()
        if current_row >= 0:
            self.stats_table.removeRow(current_row)

    def get_popup_data(self):
        """Get the popup data from the dialog."""
        stats = []
        for row in range(self.stats_table.rowCount()):
            stat_name_item = self.stats_table.item(row, 0)
            submenu_item = self.stats_table.item(row, 1)

            if stat_name_item and stat_name_item.text():
                stats.append(
                    {"stat_name": stat_name_item.text(), "submenu": submenu_item.text() if submenu_item else ""},
                )

        return {"name": self.name_input.text(), "class": self.class_combo.currentText(), "stats": stats}
