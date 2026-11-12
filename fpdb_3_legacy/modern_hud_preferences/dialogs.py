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
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from fpdb_3_legacy.i18n import N_
from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.loggingFpdb import get_logger
from fpdb_3_legacy.modern_hud_preferences import stat_catalog, stat_edit
from fpdb_3_legacy.modern_hud_preferences.preview_widgets import ColorPreviewWidget
from fpdb_3_legacy.modern_hud_preferences.stat_catalog_widget import PopupChoiceCombo, StatChoiceCombo

log = get_logger("modern_hud_preferences.dialogs")

class BlockPropertiesDialog(QDialog):
    """Edit a HUD panel's identity, sizing, position binding, and colours."""

    _POSITIONS = ["", "SB", "BB", "BTN", "CO", "MP", "EP"]
    _COLOR_FIELDS = (
        ("bgcolor", N_("Panel background:")),
        ("fgcolor", N_("Panel text:")),
        ("title_bgcolor", N_("Title background:")),
        ("title_fgcolor", N_("Title text:")),
        ("bordercolor", N_("Border:")),
    )

    def __init__(self, block: dict, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(_("Block Properties"))
        self.setMinimumWidth(360)
        self._colors = {key: block.get(key, "") for key, _ in self._COLOR_FIELDS}

        form = QFormLayout(self)
        self.label_input = QLineEdit(block.get("label", ""))
        form.addRow(_("Label:"), self.label_input)

        self.pos_combo = QComboBox()
        self.pos_combo.addItems(self._POSITIONS)
        cur = block.get("position", "")
        if cur and cur not in self._POSITIONS:
            self.pos_combo.addItem(cur)
        self.pos_combo.setCurrentText(cur)
        self.pos_combo.setToolTip(_("Show this panel only for a villain in this position (blank = always)"))
        form.addRow(_("Show for position:"), self.pos_combo)

        self.cell_width_spin = QSpinBox()
        self.cell_width_spin.setRange(0, 300)
        self.cell_width_spin.setSpecialValueText(_("Automatic"))
        self.cell_width_spin.setSuffix(_(" px"))
        self.cell_width_spin.setValue(int(block.get("cell_width", 0) or 0))
        self.cell_width_spin.setToolTip(_("Minimum width of each statistic cell; Automatic keeps the legacy default"))
        form.addRow(_("Cell width:"), self.cell_width_spin)

        self._btns = {}
        for key, caption in self._COLOR_FIELDS:
            btn = QPushButton()
            btn.clicked.connect(lambda _=False, k=key: self._pick(k))
            self._btns[key] = btn
            self._refresh_btn(key)
            form.addRow(_(caption), btn)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _pick(self, key: str) -> None:

        initial = QColor(self._colors[key]) if self._colors[key] else QColor("#ffffff")
        col = QColorDialog.getColor(initial, self, _("Pick colour"))
        if col.isValid():
            self._colors[key] = col.name()
            self._refresh_btn(key)

    def _refresh_btn(self, key: str) -> None:
        colour = self._colors[key]
        btn = self._btns[key]
        btn.setText(colour or _("(none)"))
        btn.setStyleSheet(f"background:{colour};" if colour else "")

    def get_props(self) -> dict:
        return {
            "label": self.label_input.text(),
            "position": self.pos_combo.currentText(),
            "cell_width": self.cell_width_spin.value(),
            **self._colors,
        }


class AddStatDialog(QDialog):
    def __init__(  # noqa: PLR0915 - one form, built in order
        self, stat=None, parent=None, *, catalog=None, popup_names=None
    ) -> None:
        super().__init__(parent)
        # The stat and the popup are picked from lists (B15): the catalogue of
        # stats, and the popups the configuration defines.
        self.catalog = catalog if catalog is not None else stat_catalog.build_catalog()
        self.popup_names = list(popup_names or [])
        self.setWindowTitle(_("Add/Edit Statistic"))
        self.setMinimumWidth(600)

        # The stat as it was, and its colours: "" is "not set", which an edit
        # must keep (B1). Turning a colour range on fills in the usual ones.
        self._stored = dict(stat or {})
        self.locolor = self._stored.get("stat_locolor") or ""
        self.midcolor = self._stored.get("stat_midcolor") or ""
        self.hicolor = self._stored.get("stat_hicolor") or ""

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(15, 15, 15, 15)

        # The statistic. Its cell is the Design canvas's business: a new stat
        # takes the first free cell there, and is dragged from it.
        position_group = QGroupBox(_("Statistic"))
        position_layout = QGridLayout()
        position_layout.setSpacing(10)
        position_layout.addWidget(QLabel(_("Statistic:")), 0, 0)
        self.stat_input = StatChoiceCombo(self.catalog)
        position_layout.addWidget(self.stat_input, 0, 1, 1, 2)

        position_group.setLayout(position_layout)
        main_layout.addWidget(position_group)

        # Actions section
        actions_group = QGroupBox(_("Actions"))
        actions_layout = QGridLayout()
        actions_layout.setSpacing(10)

        actions_layout.addWidget(QLabel(_("Click Action:")), 0, 0)
        self.click_input = QLineEdit()
        self.click_input.setPlaceholderText(_("Optional: Action when stat is clicked"))
        actions_layout.addWidget(self.click_input, 0, 1)

        actions_layout.addWidget(QLabel(_("Popup:")), 1, 0)
        self.popup_input = PopupChoiceCombo()
        self.popup_input.setToolTip(_("The popup a click on the stat opens"))
        actions_layout.addWidget(self.popup_input, 1, 1)

        actions_group.setLayout(actions_layout)
        main_layout.addWidget(actions_group)

        # Color configuration section
        color_group = QGroupBox(_("Color Configuration"))
        color_layout = QVBoxLayout()
        color_layout.setSpacing(10)

        # Colour ranges are optional: a stat without thresholds keeps its
        # plain text colour, and editing it must not give it one.
        self.use_thresholds = QCheckBox(_("Colour the value by thresholds"))
        self.use_thresholds.setToolTip(
            _("Below the low threshold the value takes the low colour, above the high one the high colour")
        )
        color_layout.addWidget(self.use_thresholds)

        # Color thresholds grid
        threshold_layout = QGridLayout()
        threshold_layout.setSpacing(10)

        # Low threshold row
        threshold_layout.addWidget(QLabel(_("Low Range:")), 0, 0)

        low_frame = QFrame()
        low_layout = QHBoxLayout(low_frame)
        low_layout.setContentsMargins(0, 0, 0, 0)

        low_layout.addWidget(QLabel(_("Values below")))
        self.loth_input = self._threshold_input(stat_edit.DEFAULT_LOW)
        low_layout.addWidget(self.loth_input)
        low_layout.addWidget(QLabel(_("show as")))

        self.locolor_btn = QPushButton()
        self.locolor_btn.setFixedSize(80, 30)
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
        self.hith_input = self._threshold_input(stat_edit.DEFAULT_HIGH)
        high_layout.addWidget(self.hith_input)
        high_layout.addWidget(QLabel(_("show as")))

        self.hicolor_btn = QPushButton()
        self.hicolor_btn.setFixedSize(80, 30)
        self.hicolor_btn.clicked.connect(lambda: self.choose_color("high"))
        high_layout.addWidget(self.hicolor_btn)
        high_layout.addStretch()

        threshold_layout.addWidget(high_frame, 1, 1)

        # Optional middle color
        self.use_midcolor = QCheckBox(_("Use middle color for values between thresholds"))
        threshold_layout.addWidget(self.use_midcolor, 2, 0, 1, 2)

        mid_frame = QFrame()
        mid_layout = QHBoxLayout(mid_frame)
        mid_layout.setContentsMargins(20, 0, 0, 0)

        mid_layout.addWidget(QLabel(_("Middle color:")))
        self.midcolor_btn = QPushButton()
        self.midcolor_btn.setFixedSize(80, 30)
        self.midcolor_btn.clicked.connect(lambda: self.choose_color("mid"))
        mid_layout.addWidget(self.midcolor_btn)
        mid_layout.addStretch()

        threshold_layout.addWidget(mid_frame, 3, 0, 1, 2)

        self._threshold_widgets = (
            self.loth_input,
            self.hith_input,
            self.locolor_btn,
            self.hicolor_btn,
            self.use_midcolor,
        )

        color_layout.addLayout(threshold_layout)
        color_group.setLayout(color_layout)
        main_layout.addWidget(color_group)

        # Color preview
        preview_group = QGroupBox(_("Color Preview"))
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

        # A new stat opens the usual popup when the configuration has it.
        default_popup = "default" if "default" in self.popup_names else ""
        self.popup_input.set_options(self.popup_names, stat.get("popup", "") if stat else default_popup)
        if stat:
            self.stat_input.show_item(stat)
            self.click_input.setText(stat.get("click", ""))
            self.use_thresholds.setChecked(stat_edit.has_thresholds(stat))
            self.loth_input.setValue(stat_edit.shown_value(stat.get("stat_loth"), stat_edit.DEFAULT_LOW))
            self.hith_input.setValue(stat_edit.shown_value(stat.get("stat_hith"), stat_edit.DEFAULT_HIGH))
            self.use_midcolor.setChecked(bool(self.midcolor))
        self._shown_at_load = (self.loth_input.value(), self.hith_input.value())

        for colour_type in ("low", "mid", "high"):
            self._show_color(colour_type)
        self._enable_threshold_widgets()
        self.loth_input.valueChanged.connect(self.update_preview)
        self.hith_input.valueChanged.connect(self.update_preview)
        self.use_thresholds.toggled.connect(self.toggle_thresholds)
        self.use_midcolor.toggled.connect(self.toggle_midcolor)

        # What the form says before the user touches it: get_stat() returns
        # only what differs from it.
        self._at_load = self._form_values()

        # Initial preview update
        self.update_preview()

    @staticmethod
    def _threshold_input(value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setDecimals(stat_edit.DECIMALS)
        spin.setRange(stat_edit.MINIMUM, stat_edit.MAXIMUM)
        spin.setValue(value)
        spin.setMinimumWidth(90)
        return spin

    def _show_color(self, colour_type: str) -> None:
        colour, btn = {
            "low": (self.locolor, self.locolor_btn),
            "mid": (self.midcolor, self.midcolor_btn),
            "high": (self.hicolor, self.hicolor_btn),
        }[colour_type]
        btn.setText("" if colour else _("(none)"))
        btn.setStyleSheet(f"background-color: {colour};" if colour else "")

    def _enable_threshold_widgets(self) -> None:
        on = self.use_thresholds.isChecked()
        for widget in self._threshold_widgets:
            widget.setEnabled(on)
        self.midcolor_btn.setEnabled(on and self.use_midcolor.isChecked())

    def choose_color(self, color_type) -> None:
        current = {"low": self.locolor, "mid": self.midcolor, "high": self.hicolor}[color_type]
        color = QColorDialog.getColor(QColor(current) if current else QColor("#ffffff"), self)
        if color.isValid():
            if color_type == "low":
                self.locolor = color.name()
            elif color_type == "mid":
                self.midcolor = color.name()
            elif color_type == "high":
                self.hicolor = color.name()
            self._show_color(color_type)
            self.update_preview()

    def toggle_thresholds(self, checked) -> None:
        """Turning colour ranges on gives a stat without colours the usual red and green."""
        if checked:
            if not self.locolor:
                self.locolor = stat_edit.DEFAULT_LOW_COLOR
                self._show_color("low")
            if not self.hicolor:
                self.hicolor = stat_edit.DEFAULT_HIGH_COLOR
                self._show_color("high")
        self._enable_threshold_widgets()
        self.update_preview()

    def toggle_midcolor(self, checked) -> None:
        if checked and not self.midcolor:
            self.midcolor = stat_edit.DEFAULT_MID_COLOR
            self._show_color("mid")
        self._enable_threshold_widgets()
        self.update_preview()

    def update_preview(self) -> None:
        self.color_preview.set_colors(
            self.locolor or stat_edit.DEFAULT_LOW_COLOR,
            self.midcolor or stat_edit.DEFAULT_MID_COLOR,
            self.hicolor or stat_edit.DEFAULT_HIGH_COLOR,
            self.loth_input.value(),
            self.hith_input.value(),
            self.use_midcolor.isChecked(),
        )

    def _form_values(self) -> dict:
        """Every attribute the form shows, as the stat would store it."""
        values = {
            "click": self.click_input.text(),
            "popup": self.popup_input.value(),
        }
        values.update(self._stat_values())
        values.update(
            stat_edit.threshold_values(
                self._stored,
                self.use_thresholds.isChecked(),
                self._shown_at_load,
                (self.loth_input.value(), self.hith_input.value()),
            )
        )
        values["stat_locolor"] = self.locolor
        values["stat_hicolor"] = self.hicolor
        values["stat_midcolor"] = self.midcolor if self.use_midcolor.isChecked() else ""
        return values

    def _stat_values(self) -> dict:
        """The stat's name, and its data_* attributes when the catalogue knows it."""
        entry = self.stat_input.chosen_entry()
        if entry is not None:
            return stat_catalog.stat_values(entry)
        return {"stat": self.stat_input.currentText().strip()}

    def accept(self) -> None:
        """Refuse a stat the catalogue does not know, unless the stat already had it."""
        text = self.stat_input.currentText().strip()
        known = self.stat_input.chosen_entry() is not None
        if not known and (not text or text != self._stored.get("stat", "")):
            QMessageBox.warning(
                self,
                _("Unknown statistic"),
                _("There is no statistic called \"{name}\". Pick one from the list.").format(name=text)
                if text
                else _("Pick a statistic from the list."),
            )
            return
        super().accept()

    def get_stat(self) -> dict:
        """What the user set.

        Editing a stat returns only the attributes the user changed, so that
        applying them leaves everything else -- unset colours, a threshold
        written ``12.5`` or ``140`` -- as it was. Adding one returns its name,
        click and popup, plus the colour range when the user set one; the
        editor gives it its cell.
        """
        values = self._form_values()
        if self._stored:
            changed = stat_edit.changes(self._at_load, values)
            # Another stat takes its whole binding: the data_* values the cell
            # held were the old stat's, even where they match the new entry's
            # catalogue defaults. The same stat keeps the cell's own values.
            entry = self.stat_input.chosen_entry()
            if entry is not None and entry != self.catalog.entry_for_item(self._stored):
                changed.update(stat_catalog.stat_values(entry))
            return changed
        return {key: value for key, value in values.items() if value != "" or key in ("click", "popup")}


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
        layout.addRow(_("Statistic Name:"), self.stat_name_input)

        # Submenu (optional)
        self.submenu_input = QLineEdit()
        self.submenu_input.setPlaceholderText(_("Optional: Submenu name for hierarchical popups"))
        if stat_data:
            self.submenu_input.setText(stat_data.get("submenu", ""))
        layout.addRow(_("Submenu:"), self.submenu_input)

        self.category_combo = QComboBox()
        self.category_combo.addItems(
            ["auto", "player_info", "preflop", "flop", "turn", "river", "steal", "aggression", "general"]
        )
        if stat_data and stat_data.get("category"):
            self.category_combo.setCurrentText(stat_data["category"])
        self.category_combo.setToolTip(_("Override the automatic section used by ModernSubmenu"))
        layout.addRow(_("Section:"), self.category_combo)

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
        info_group = QGroupBox(_("Popup Information"))
        info_layout = QFormLayout()

        # Name input
        self.name_input = QLineEdit()
        if popup_data:
            self.name_input.setText(popup_data["name"])
        info_layout.addRow(_("Popup Name:"), self.name_input)

        # Class selection
        self.class_combo = QComboBox()
        self.class_combo.addItems(["default", "Submenu", "Multicol"])
        if popup_data:
            self.class_combo.setCurrentText(popup_data["class"])
        info_layout.addRow(_("Popup Class:"), self.class_combo)

        info_group.setLayout(info_layout)
        main_layout.addWidget(info_group)

        # Statistics section
        stats_group = QGroupBox(_("Statistics"))
        stats_layout = QVBoxLayout()

        # Stats table
        self.stats_table = QTableWidget(0, 2)
        self.stats_table.setHorizontalHeaderLabels([_("Statistic Name"), _("Submenu")])
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
