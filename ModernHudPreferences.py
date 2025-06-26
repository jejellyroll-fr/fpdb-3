#!/usr/bin/env python
# -*- coding: utf-8 -*-

from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QComboBox,
    QDialogButtonBox,
    QListWidget,
    QTableWidget,
    QTableWidgetItem,
    QAbstractItemView,
    QGroupBox,
    QFrame,
    QSplitter,
    QGraphicsView,
    QGraphicsScene,
    QGraphicsRectItem,
    QGraphicsSimpleTextItem,
    QHeaderView,
    QMessageBox,
    QFormLayout,
    QSpinBox,
    QCheckBox,
    QColorDialog,
    QWidget,
    QTabWidget,
    QTextEdit,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QBrush, QPen, QFont, QPainter, QLinearGradient

from loggingFpdb import get_logger

log = get_logger("modernhudpreferences")


# --- Color Preview Widget ---
class ColorPreviewWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.low_color = QColor("#ff0000")
        self.mid_color = QColor("#ffff00")
        self.high_color = QColor("#00ff00")
        self.low_threshold = 20
        self.high_threshold = 60
        self.use_mid_color = False

    def set_colors(self, low_color, mid_color, high_color, low_threshold, high_threshold, use_mid_color):
        self.low_color = QColor(low_color)
        self.mid_color = QColor(mid_color)
        self.high_color = QColor(high_color)
        self.low_threshold = low_threshold
        self.high_threshold = high_threshold
        self.use_mid_color = use_mid_color
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        width = self.width()
        height = self.height()

        # Draw gradient background
        gradient = QLinearGradient(0, 0, width, 0)

        if self.use_mid_color:
            # Three color gradient
            gradient.setColorAt(0.0, self.low_color)
            gradient.setColorAt(self.low_threshold / 100.0, self.low_color)
            gradient.setColorAt(self.low_threshold / 100.0 + 0.01, self.mid_color)
            gradient.setColorAt(self.high_threshold / 100.0 - 0.01, self.mid_color)
            gradient.setColorAt(self.high_threshold / 100.0, self.high_color)
            gradient.setColorAt(1.0, self.high_color)
        else:
            # Two color gradient
            gradient.setColorAt(0.0, self.low_color)
            gradient.setColorAt(self.low_threshold / 100.0, self.low_color)
            gradient.setColorAt(self.high_threshold / 100.0, self.high_color)
            gradient.setColorAt(1.0, self.high_color)

        painter.fillRect(0, 0, width, height, gradient)

        # Draw threshold markers
        painter.setPen(QPen(Qt.black, 2))
        low_x = int(width * self.low_threshold / 100)
        high_x = int(width * self.high_threshold / 100)

        painter.drawLine(low_x, 0, low_x, height)
        painter.drawLine(high_x, 0, high_x, height)

        # Draw labels
        painter.setFont(QFont("Arial", 9))
        painter.drawText(5, height - 5, "0")
        painter.drawText(low_x - 15, height - 5, f"{self.low_threshold}")
        painter.drawText(high_x - 15, height - 5, f"{self.high_threshold}")
        painter.drawText(width - 25, height - 5, "100")


# --- Visual HUD Preview Widget ---
class HudPreviewWidget(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        from PyQt5.QtGui import QPainter

        self.setRenderHint(QPainter.Antialiasing)
        self.setMinimumSize(320, 320)
        self.grid_rows = 5
        self.grid_cols = 5
        self.stats = []  # List of dicts: {row, col, stat, click, popup}

    def set_grid(self, rows, cols):
        self.grid_rows = rows
        self.grid_cols = cols
        self.update_preview()

    def set_stats(self, stats):
        self.stats = stats
        self.update_preview()

    def update_preview(self):
        self.scene.clear()
        w, h = 300, 300
        cell_w = w / self.grid_cols
        cell_h = h / self.grid_rows
        # Draw grid
        for r in range(self.grid_rows):
            for c in range(self.grid_cols):
                rect = QGraphicsRectItem(c * cell_w, r * cell_h, cell_w, cell_h)
                rect.setPen(QPen(QColor(180, 180, 180), 1, Qt.DotLine))
                self.scene.addItem(rect)
        # Draw stats
        for stat in self.stats:
            r, c = stat["row"], stat["col"]
            if 0 <= r < self.grid_rows and 0 <= c < self.grid_cols:
                x, y = c * cell_w, r * cell_h
                stat_rect = QGraphicsRectItem(x, y, cell_w, cell_h)
                stat_rect.setBrush(QBrush(QColor(220, 240, 255, 180)))
                stat_rect.setPen(QPen(QColor(80, 120, 200), 2))
                self.scene.addItem(stat_rect)
                label = QGraphicsSimpleTextItem(stat["stat"])
                label.setFont(QFont("Arial", 10, QFont.Bold))
                label.setPos(x + 8, y + 8)
                self.scene.addItem(label)
                # Icons for click/popup
                icon = ""
                if stat.get("click") and stat.get("popup"):
                    icon = "🖱️💬"
                elif stat.get("click"):
                    icon = "🖱️"
                elif stat.get("popup"):
                    icon = "💬"
                if icon:
                    icon_item = QGraphicsSimpleTextItem(icon)
                    icon_item.setFont(QFont("Arial", 12))
                    icon_item.setPos(x + cell_w - 32, y + cell_h - 28)
                    self.scene.addItem(icon_item)
        self.setSceneRect(0, 0, w, h)


# --- Add/Edit Stat Dialog ---
class AddStatDialog(QDialog):
    def __init__(self, stat=None, max_rows=5, max_cols=5, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add/Edit Statistic")
        self.setMinimumWidth(600)
        self.setMaximumHeight(650)

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(15, 15, 15, 15)

        # Position and statistic section
        position_group = QGroupBox("Position and Statistic")
        position_layout = QGridLayout()
        position_layout.setSpacing(10)

        # Row and column selection
        position_layout.addWidget(QLabel("Grid Position:"), 0, 0)

        pos_frame = QFrame()
        pos_layout = QHBoxLayout(pos_frame)
        pos_layout.setContentsMargins(0, 0, 0, 0)

        pos_layout.addWidget(QLabel("Row:"))
        self.row_input = QComboBox()
        self.row_input.addItems([str(i) for i in range(max_rows)])
        self.row_input.setMinimumWidth(60)
        pos_layout.addWidget(self.row_input)

        pos_layout.addSpacing(20)
        pos_layout.addWidget(QLabel("Column:"))
        self.col_input = QComboBox()
        self.col_input.addItems([str(i) for i in range(max_cols)])
        self.col_input.setMinimumWidth(60)
        pos_layout.addWidget(self.col_input)
        pos_layout.addStretch()

        position_layout.addWidget(pos_frame, 0, 1, 1, 2)

        # Statistic selection
        position_layout.addWidget(QLabel("Statistic:"), 1, 0)
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
            "four_B",
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

        actions_layout.addWidget(QLabel("Click Action:"), 0, 0)
        self.click_input = QLineEdit()
        self.click_input.setPlaceholderText("Optional: Action when stat is clicked")
        actions_layout.addWidget(self.click_input, 0, 1)

        actions_layout.addWidget(QLabel("Popup:"), 1, 0)
        self.popup_input = QLineEdit()
        self.popup_input.setPlaceholderText("Optional: Popup to show on hover")
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
        threshold_layout.addWidget(QLabel("Low Range:"), 0, 0)

        low_frame = QFrame()
        low_layout = QHBoxLayout(low_frame)
        low_layout.setContentsMargins(0, 0, 0, 0)

        low_layout.addWidget(QLabel("Values below"))
        self.loth_input = QSpinBox()
        self.loth_input.setRange(0, 100)
        self.loth_input.setValue(20)
        self.loth_input.setMinimumWidth(70)
        self.loth_input.valueChanged.connect(self.update_preview)
        low_layout.addWidget(self.loth_input)
        low_layout.addWidget(QLabel("show as"))

        self.locolor_btn = QPushButton()
        self.locolor_btn.setFixedSize(80, 30)
        self.locolor_btn.setStyleSheet(f"background-color: {self.locolor};")
        self.locolor_btn.clicked.connect(lambda: self.choose_color("low"))
        low_layout.addWidget(self.locolor_btn)
        low_layout.addStretch()

        threshold_layout.addWidget(low_frame, 0, 1)

        # High threshold row
        threshold_layout.addWidget(QLabel("High Range:"), 1, 0)

        high_frame = QFrame()
        high_layout = QHBoxLayout(high_frame)
        high_layout.setContentsMargins(0, 0, 0, 0)

        high_layout.addWidget(QLabel("Values above"))
        self.hith_input = QSpinBox()
        self.hith_input.setRange(0, 100)
        self.hith_input.setValue(60)
        self.hith_input.setMinimumWidth(70)
        self.hith_input.valueChanged.connect(self.update_preview)
        high_layout.addWidget(self.hith_input)
        high_layout.addWidget(QLabel("show as"))

        self.hicolor_btn = QPushButton()
        self.hicolor_btn.setFixedSize(80, 30)
        self.hicolor_btn.setStyleSheet(f"background-color: {self.hicolor};")
        self.hicolor_btn.clicked.connect(lambda: self.choose_color("high"))
        high_layout.addWidget(self.hicolor_btn)
        high_layout.addStretch()

        threshold_layout.addWidget(high_frame, 1, 1)

        # Optional middle color
        self.use_midcolor = QCheckBox("Use middle color for values between thresholds")
        self.use_midcolor.toggled.connect(self.toggle_midcolor)
        threshold_layout.addWidget(self.use_midcolor, 2, 0, 1, 2)

        mid_frame = QFrame()
        mid_layout = QHBoxLayout(mid_frame)
        mid_layout.setContentsMargins(20, 0, 0, 0)

        mid_layout.addWidget(QLabel("Middle color:"))
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

        preview_info = QLabel("Preview shows how statistic colors will change based on values")
        preview_info.setProperty("class", "caption")
        preview_layout.addWidget(preview_info)

        preview_group.setLayout(preview_layout)
        main_layout.addWidget(preview_group)

        # Dialog buttons
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 10, 0, 0)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.button(QDialogButtonBox.Ok).setText("OK")
        btn_box.button(QDialogButtonBox.Cancel).setText("Cancel")
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        button_layout.addStretch()
        button_layout.addWidget(btn_box)

        main_layout.addLayout(button_layout)

        # Initialize color values
        self.locolor = "#ff0000"
        self.midcolor = "#ffff00"
        self.hicolor = "#00ff00"

        if stat:
            self.row_input.setCurrentText(str(stat["row"]))
            self.col_input.setCurrentText(str(stat["col"]))
            self.stat_input.setCurrentText(stat["stat"])
            self.click_input.setText(stat.get("click", ""))
            self.popup_input.setText(stat.get("popup", ""))

            # Load color settings if available
            if "stat_loth" in stat:
                self.loth_input.setValue(int(float(stat["stat_loth"])))
            if "stat_hith" in stat:
                self.hith_input.setValue(int(float(stat["stat_hith"])))
            if "stat_locolor" in stat and stat["stat_locolor"]:
                self.locolor = stat["stat_locolor"]
                self.locolor_btn.setStyleSheet(f"background-color: {self.locolor};")
            if "stat_hicolor" in stat and stat["stat_hicolor"]:
                self.hicolor = stat["stat_hicolor"]
                self.hicolor_btn.setStyleSheet(f"background-color: {self.hicolor};")
            if "stat_midcolor" in stat and stat["stat_midcolor"]:
                self.midcolor = stat["stat_midcolor"]
                self.midcolor_btn.setStyleSheet(f"background-color: {self.midcolor};")
                self.use_midcolor.setChecked(True)
                self.midcolor_btn.setEnabled(True)

        # Initial preview update
        self.update_preview()

    def choose_color(self, color_type):
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

    def toggle_midcolor(self, checked):
        self.midcolor_btn.setEnabled(checked)
        self.update_preview()

    def update_preview(self):
        low_threshold = self.loth_input.value()
        high_threshold = self.hith_input.value()
        use_mid_color = self.use_midcolor.isChecked()

        self.color_preview.set_colors(
            self.locolor, self.midcolor, self.hicolor, low_threshold, high_threshold, use_mid_color
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


# --- Main Modern HUD Preferences Dialog ---
class ModernHudPreferences(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("HUD Preferences")
        self.setMinimumSize(1200, 800)
        self.resize(1400, 900)

        # Main layout with better spacing
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Header section with profile management
        header_frame = QFrame()
        header_frame.setFrameStyle(QFrame.StyledPanel)
        header_layout = QVBoxLayout(header_frame)
        header_layout.setContentsMargins(15, 15, 15, 15)

        # Title
        header_title = QLabel("HUD Profile Configuration")
        header_title.setProperty("class", "h1")
        header_layout.addWidget(header_title)

        # Profile management bar
        profile_bar = QHBoxLayout()
        profile_bar.setSpacing(10)

        profile_label = QLabel("Active Profile:")
        profile_label.setProperty("class", "subtitle")
        profile_bar.addWidget(profile_label)

        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(250)
        # Laisser qt_material gérer le style
        self.profile_combo.currentIndexChanged.connect(self.on_profile_selected)
        profile_bar.addWidget(self.profile_combo)

        profile_bar.addSpacing(20)

        # Profile action buttons with better styling
        self.add_profile_btn = QPushButton("➕ New Profile")
        self.add_profile_btn.setMinimumWidth(120)
        self.add_profile_btn.clicked.connect(self.add_profile)

        self.dup_profile_btn = QPushButton("📋 Duplicate")
        self.dup_profile_btn.setMinimumWidth(120)
        self.dup_profile_btn.clicked.connect(self.duplicate_profile)

        self.del_profile_btn = QPushButton("🗑️ Delete")
        self.del_profile_btn.setMinimumWidth(120)
        self.del_profile_btn.clicked.connect(self.delete_profile)

        profile_bar.addWidget(self.add_profile_btn)
        profile_bar.addWidget(self.dup_profile_btn)
        profile_bar.addWidget(self.del_profile_btn)
        profile_bar.addStretch()

        header_layout.addLayout(profile_bar)
        main_layout.addWidget(header_frame)

        # Main content area with tabs
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)

        # Tab 1: Statistics Configuration
        stats_tab = QWidget()
        stats_layout = QHBoxLayout(stats_tab)
        stats_layout.setContentsMargins(0, 10, 0, 0)

        # Statistics splitter
        stats_splitter = QSplitter(Qt.Horizontal)
        stats_splitter.setHandleWidth(8)

        # Left panel: Statistics table
        left_panel = QFrame()
        left_panel.setFrameStyle(QFrame.StyledPanel)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(15, 15, 15, 15)
        left_layout.setSpacing(10)

        # Statistics header
        stats_header = QHBoxLayout()
        stats_label = QLabel("Statistics Configuration")
        stats_label.setProperty("class", "h2")
        stats_header.addWidget(stats_label)
        stats_header.addStretch()
        left_layout.addLayout(stats_header)

        # Statistics table with better styling
        self.stat_table = QTableWidget(0, 5)
        self.stat_table.setHorizontalHeaderLabels(["Row", "Col", "Statistic", "Click Action", "Popup"])
        self.stat_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.stat_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.stat_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.stat_table.setAlternatingRowColors(True)
        self.stat_table.setMinimumWidth(600)
        left_layout.addWidget(self.stat_table)

        # Statistics action buttons
        stat_btn_frame = QFrame()
        stat_btn_layout = QHBoxLayout(stat_btn_frame)
        stat_btn_layout.setContentsMargins(0, 10, 0, 0)

        self.add_stat_btn = QPushButton("➕ Add Statistic")
        self.add_stat_btn.setMinimumHeight(35)
        self.add_stat_btn.clicked.connect(self.add_stat)

        self.edit_stat_btn = QPushButton("📝 Edit Statistic")
        self.edit_stat_btn.setMinimumHeight(35)
        self.edit_stat_btn.clicked.connect(self.edit_stat)

        self.remove_stat_btn = QPushButton("➖ Remove Statistic")
        self.remove_stat_btn.setMinimumHeight(35)
        self.remove_stat_btn.clicked.connect(self.remove_stat)

        stat_btn_layout.addWidget(self.add_stat_btn)
        stat_btn_layout.addWidget(self.edit_stat_btn)
        stat_btn_layout.addWidget(self.remove_stat_btn)
        stat_btn_layout.addStretch()

        left_layout.addWidget(stat_btn_frame)
        stats_splitter.addWidget(left_panel)

        # Right panel: Visual preview
        right_panel = QFrame()
        right_panel.setFrameStyle(QFrame.StyledPanel)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(15, 15, 15, 15)
        right_layout.setSpacing(10)

        # Preview header
        preview_label = QLabel("HUD Preview")
        preview_label.setProperty("class", "h2")
        right_layout.addWidget(preview_label)

        # Preview widget
        self.preview = HudPreviewWidget()
        self.preview.setMinimumSize(400, 400)
        right_layout.addWidget(self.preview)

        # Preview info
        info_label = QLabel(
            "The preview shows the layout of statistics in the HUD.\nClick and popup actions are indicated by icons."
        )
        info_label.setProperty("class", "caption")
        info_label.setWordWrap(True)
        right_layout.addWidget(info_label)

        right_layout.addStretch()
        stats_splitter.addWidget(right_panel)

        # Set initial splitter sizes (60/40 split)
        stats_splitter.setSizes([700, 500])
        stats_layout.addWidget(stats_splitter)

        # Add stats tab
        self.tabs.addTab(stats_tab, "📊 Statistics")

        # Tab 2: Popup Windows
        popup_tab = QWidget()
        popup_layout = QVBoxLayout(popup_tab)
        popup_layout.setContentsMargins(15, 15, 15, 15)

        # Popup selection bar
        popup_select_frame = QFrame()
        popup_select_frame.setFrameStyle(QFrame.StyledPanel)
        popup_select_layout = QHBoxLayout(popup_select_frame)
        popup_select_layout.setContentsMargins(10, 10, 10, 10)

        popup_select_label = QLabel("Select Popup:")
        popup_select_label.setProperty("class", "subtitle")
        popup_select_layout.addWidget(popup_select_label)

        self.popup_combo = QComboBox()
        self.popup_combo.setMinimumWidth(250)
        self.popup_combo.currentIndexChanged.connect(self.on_popup_selected)
        popup_select_layout.addWidget(self.popup_combo)

        popup_select_layout.addSpacing(20)

        # Popup action buttons
        self.add_popup_btn = QPushButton("➕ New Popup")
        self.add_popup_btn.setMinimumWidth(120)
        self.add_popup_btn.clicked.connect(self.add_popup)

        self.dup_popup_btn = QPushButton("📋 Duplicate")
        self.dup_popup_btn.setMinimumWidth(120)
        self.dup_popup_btn.clicked.connect(self.duplicate_popup)

        self.del_popup_btn = QPushButton("🗑️ Delete")
        self.del_popup_btn.setMinimumWidth(120)
        self.del_popup_btn.clicked.connect(self.delete_popup)

        popup_select_layout.addWidget(self.add_popup_btn)
        popup_select_layout.addWidget(self.dup_popup_btn)
        popup_select_layout.addWidget(self.del_popup_btn)
        popup_select_layout.addStretch()

        popup_layout.addWidget(popup_select_frame)

        # Popup content area
        popup_content_splitter = QSplitter(Qt.Horizontal)
        popup_content_splitter.setHandleWidth(8)

        # Left panel: Statistics list
        left_popup_panel = QFrame()
        left_popup_panel.setFrameStyle(QFrame.StyledPanel)
        left_popup_layout = QVBoxLayout(left_popup_panel)
        left_popup_layout.setContentsMargins(15, 15, 15, 15)

        # Statistics list
        stats_group = QGroupBox("Statistics")
        stats_layout = QVBoxLayout()
        stats_layout.setSpacing(8)

        # Stats buttons at the top
        stats_btn_layout = QHBoxLayout()
        stats_btn_layout.setContentsMargins(0, 0, 0, 5)

        self.add_popup_stat_btn = QPushButton("➕ Add")
        self.add_popup_stat_btn.clicked.connect(self.add_popup_stat)

        self.edit_popup_stat_btn = QPushButton("📝 Edit")
        self.edit_popup_stat_btn.clicked.connect(self.edit_popup_stat)

        self.remove_popup_stat_btn = QPushButton("➖ Remove")
        self.remove_popup_stat_btn.clicked.connect(self.remove_popup_stat)

        self.move_up_btn = QPushButton("↑ Up")
        self.move_up_btn.clicked.connect(self.move_stat_up)

        self.move_down_btn = QPushButton("↓ Down")
        self.move_down_btn.clicked.connect(self.move_stat_down)

        stats_btn_layout.addWidget(self.add_popup_stat_btn)
        stats_btn_layout.addWidget(self.edit_popup_stat_btn)
        stats_btn_layout.addWidget(self.remove_popup_stat_btn)
        stats_btn_layout.addWidget(self.move_up_btn)
        stats_btn_layout.addWidget(self.move_down_btn)
        stats_btn_layout.addStretch()

        stats_layout.addLayout(stats_btn_layout)

        # Statistics list widget
        self.popup_stats_list = QListWidget()
        self.popup_stats_list.setAlternatingRowColors(True)
        self.popup_stats_list.setMinimumHeight(350)
        stats_layout.addWidget(self.popup_stats_list)
        stats_group.setLayout(stats_layout)
        left_popup_layout.addWidget(stats_group)

        popup_content_splitter.addWidget(left_popup_panel)

        # Right panel: Popup info and preview
        right_popup_panel = QFrame()
        right_popup_panel.setFrameStyle(QFrame.StyledPanel)
        right_popup_layout = QVBoxLayout(right_popup_panel)
        right_popup_layout.setContentsMargins(15, 15, 15, 15)

        # Popup info section - moved here
        popup_info_group = QGroupBox("Popup Information")
        popup_info_layout = QGridLayout()
        popup_info_layout.setSpacing(10)
        popup_info_layout.setContentsMargins(15, 15, 15, 15)

        popup_info_layout.addWidget(QLabel("Name:"), 0, 0)
        self.popup_name_edit = QLineEdit()
        self.popup_name_edit.setReadOnly(True)
        self.popup_name_edit.setMinimumHeight(32)
        popup_info_layout.addWidget(self.popup_name_edit, 0, 1)

        popup_info_layout.addWidget(QLabel("Class:"), 0, 2)
        self.popup_class_combo = QComboBox()
        self.popup_class_combo.addItems(["default", "Submenu", "Multicol"])
        self.popup_class_combo.setMinimumHeight(32)
        self.popup_class_combo.currentTextChanged.connect(self.on_popup_class_changed)
        popup_info_layout.addWidget(self.popup_class_combo, 0, 3)

        popup_info_group.setLayout(popup_info_layout)
        popup_info_group.setMinimumHeight(100)
        popup_info_group.setMaximumHeight(120)
        right_popup_layout.addWidget(popup_info_group)

        # Preview section
        preview_label = QLabel("Popup Preview")
        preview_label.setProperty("class", "h3")
        right_popup_layout.addWidget(preview_label)

        # Preview area - reduced size
        self.popup_preview = QTextEdit()
        self.popup_preview.setReadOnly(True)
        # Utiliser les couleurs du thème pour le preview
        palette = self.palette()
        self.popup_preview.setStyleSheet(f"""
            background-color: {palette.base().color().name()};
            border: 1px solid {palette.mid().color().name()};
            padding: 10px;
        """)
        self.popup_preview.setMaximumHeight(400)
        right_popup_layout.addWidget(self.popup_preview)

        popup_content_splitter.addWidget(right_popup_panel)
        popup_content_splitter.setSizes([600, 400])

        popup_layout.addWidget(popup_content_splitter)

        # Add popup tab
        self.tabs.addTab(popup_tab, "💬 Popup Windows")

        # Add tabs to main layout
        main_layout.addWidget(self.tabs)

        # Bottom action bar
        bottom_frame = QFrame()
        bottom_frame.setFrameStyle(QFrame.StyledPanel)
        bottom_layout = QHBoxLayout(bottom_frame)
        bottom_layout.setContentsMargins(15, 10, 15, 10)

        # Status/info area
        self.status_label = QLabel("Ready")
        self.status_label.setProperty("class", "caption")
        bottom_layout.addWidget(self.status_label)

        bottom_layout.addStretch()

        # Dialog buttons
        btn_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btn_box.button(QDialogButtonBox.Save).setText("Save Changes")
        btn_box.button(QDialogButtonBox.Cancel).setText("Cancel")
        btn_box.accepted.connect(self.save_changes)
        btn_box.rejected.connect(self.reject)
        bottom_layout.addWidget(btn_box)

        main_layout.addWidget(bottom_frame)

        # Load profiles
        self.load_profiles()

        # Load popup windows
        self.load_popup_windows()

        # Track changes
        self.original_profiles = self._deep_copy_profiles(self.hud_profiles)
        self.original_popups = self._deep_copy_popups(self.popup_windows)

        # Update status
        self.update_status()

    def update_status(self):
        """Update status label with current profile info"""
        if self.profile_combo.currentIndex() >= 0:
            profile_name = self.profile_combo.currentText()
            profile = self.hud_profiles.get(profile_name, {})
            if isinstance(profile, dict):
                stats = profile.get("stats", [])
                rows = profile.get("rows", 5)
                cols = profile.get("cols", 5)
            else:
                stats = profile
                rows = cols = 5
            self.status_label.setText(f"Profile: {profile_name} | Grid: {rows}×{cols} | Statistics: {len(stats)}")

    def _deep_copy_profiles(self, profiles):
        """Create a deep copy of profiles for change detection"""
        import copy

        return copy.deepcopy(profiles)

    def _deep_copy_popups(self, popups):
        """Create a deep copy of popup windows for change detection"""
        import copy

        return copy.deepcopy(popups)

    def has_unsaved_changes(self):
        """Check if there are unsaved changes"""
        return self.hud_profiles != self.original_profiles or self.popup_windows != self.original_popups

    def closeEvent(self, event):
        """Handle window close event"""
        if self.has_unsaved_changes():
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes. Do you want to save before closing?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            )

            if reply == QMessageBox.Save:
                self.save_changes()
                if self.result() == QDialog.Accepted:
                    event.accept()
                else:
                    event.ignore()
            elif reply == QMessageBox.Discard:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

    def load_profiles(self):
        # Try to load HUD profiles from config (from HUD_config.xml)
        self.hud_profiles = None
        # 1. Try config.hud_profiles (preferred)
        if hasattr(self.config, "hud_profiles") and self.config.hud_profiles:
            self.hud_profiles = self.config.hud_profiles
        # 2. Try config.stat_sets (legacy format)
        elif hasattr(self.config, "stat_sets") and self.config.stat_sets:
            self.hud_profiles = {}
            for set_name, stat_set in self.config.stat_sets.items():
                stats = []
                if hasattr(stat_set, "stats"):
                    for pos, stat in stat_set.stats.items():
                        stat_dict = {
                            "row": pos[0],
                            "col": pos[1],
                            "stat": getattr(stat, "stat_name", "unknown"),
                            "click": getattr(stat, "click", ""),
                            "popup": getattr(stat, "popup", ""),
                        }
                        # Add color attributes if they exist
                        if hasattr(stat, "stat_loth"):
                            stat_dict["stat_loth"] = getattr(stat, "stat_loth", "")
                        if hasattr(stat, "stat_hith"):
                            stat_dict["stat_hith"] = getattr(stat, "stat_hith", "")
                        if hasattr(stat, "stat_locolor"):
                            stat_dict["stat_locolor"] = getattr(stat, "stat_locolor", "")
                        if hasattr(stat, "stat_hicolor"):
                            stat_dict["stat_hicolor"] = getattr(stat, "stat_hicolor", "")
                        if hasattr(stat, "stat_midcolor"):
                            stat_dict["stat_midcolor"] = getattr(stat, "stat_midcolor", "")
                        stats.append(stat_dict)

                # Check if stat_set has rows/cols attributes
                if hasattr(stat_set, "rows") and hasattr(stat_set, "cols"):
                    self.hud_profiles[set_name] = {"rows": stat_set.rows, "cols": stat_set.cols, "stats": stats}
                else:
                    # Old format without rows/cols - use default
                    self.hud_profiles[set_name] = stats
        # 3. Fallback to demo profile if nothing found
        if not self.hud_profiles:
            self.hud_profiles = {
                "Default": [
                    {"row": 0, "col": 0, "stat": "vpip", "click": "", "popup": ""},
                    {"row": 0, "col": 1, "stat": "pfr", "click": "", "popup": ""},
                    {"row": 1, "col": 0, "stat": "3bet", "click": "", "popup": ""},
                ]
            }
        self.profile_combo.clear()
        self.profile_combo.addItems(list(self.hud_profiles.keys()))
        if self.profile_combo.count() > 0:
            self.profile_combo.setCurrentIndex(0)

    def load_popup_windows(self):
        """Load popup window definitions from config"""
        self.popup_windows = {}

        if hasattr(self.config, "popup_windows") and self.config.popup_windows:
            for popup_name, popup_obj in self.config.popup_windows.items():
                popup_data = {"name": popup_name, "class": popup_obj.pu_class, "stats": []}

                # Extract stats and submenus
                for i, stat_name in enumerate(popup_obj.pu_stats):
                    stat_info = {"stat_name": stat_name, "submenu": ""}

                    # Check if there's a submenu for this stat
                    if i < len(popup_obj.pu_stats_submenu):
                        stat_tuple = popup_obj.pu_stats_submenu[i]
                        if len(stat_tuple) > 1 and stat_tuple[1]:
                            stat_info["submenu"] = stat_tuple[1]

                    popup_data["stats"].append(stat_info)

                self.popup_windows[popup_name] = popup_data

        # Update popup combo
        self.popup_combo.clear()
        self.popup_combo.addItems(sorted(self.popup_windows.keys()))
        if self.popup_combo.count() > 0:
            self.popup_combo.setCurrentIndex(0)

    def on_popup_selected(self, index):
        """Handle popup selection from combo box"""
        if index < 0 or index >= self.popup_combo.count():
            self.popup_name_edit.clear()
            self.popup_class_combo.setCurrentIndex(0)
            self.popup_stats_list.clear()
            self.popup_preview.clear()
            return

        popup_name = self.popup_combo.currentText()
        popup_data = self.popup_windows.get(popup_name, {})

        # Update popup info
        self.popup_name_edit.setText(popup_name)
        self.popup_class_combo.setCurrentText(popup_data.get("class", "default"))

        # Update stats list
        self.popup_stats_list.clear()
        for stat in popup_data.get("stats", []):
            stat_text = stat["stat_name"]
            if stat.get("submenu"):
                stat_text += f" → {stat['submenu']}"
            self.popup_stats_list.addItem(stat_text)

        # Update preview
        self.update_popup_preview()

    def on_popup_class_changed(self, new_class):
        """Handle popup class change"""
        if self.popup_combo.currentIndex() >= 0:
            popup_name = self.popup_combo.currentText()
            if popup_name in self.popup_windows:
                self.popup_windows[popup_name]["class"] = new_class
                self.update_popup_preview()

    def update_popup_preview(self):
        """Update the popup preview display"""
        if self.popup_combo.currentIndex() < 0:
            return

        popup_name = self.popup_combo.currentText()
        popup_data = self.popup_windows.get(popup_name, {})
        popup_class = popup_data.get("class", "default")
        stats = popup_data.get("stats", [])

        # Obtenir les couleurs du thème actuel
        palette = self.palette()
        bg_color = palette.window().color().name()
        text_color = palette.windowText().color().name()
        border_color = palette.mid().color().name()
        highlight_color = palette.highlight().color().name()
        alt_bg_color = palette.alternateBase().color().name()

        # CSS styling for realistic popup appearance using theme colors
        css = f"""
        <style>
            body {{ font-family: Arial, sans-serif; margin: 10px; color: {text_color}; }}
            .popup-window {{ 
                background-color: {bg_color}; 
                color: {text_color}; 
                border: 2px solid {border_color}; 
                border-radius: 5px; 
                padding: 10px;
                margin-top: 10px;
            }}
            .popup-title {{
                font-size: 14px;
                font-weight: bold;
                color: {highlight_color};
                margin-bottom: 10px;
                text-align: center;
                border-bottom: 1px solid {border_color};
                padding-bottom: 5px;
            }}
            .stat-row {{
                padding: 3px 5px;
                margin: 2px 0;
                font-size: 12px;
            }}
            .stat-row:hover {{
                background-color: {alt_bg_color};
            }}
            .stat-name {{
                color: {highlight_color};
                font-weight: bold;
            }}
            .stat-value {{
                color: {text_color};
                float: right;
            }}
            .submenu-header {{
                color: {highlight_color};
                font-weight: bold;
                margin-top: 8px;
                margin-bottom: 4px;
                font-size: 12px;
            }}
            .multicol-container {{
                display: flex;
                gap: 20px;
            }}
            .multicol-column {{
                flex: 1;
                min-width: 120px;
            }}
        </style>
        """

        preview_text = css + f"<h3 style='margin-top: 0;'>Preview: {popup_name}</h3>\n"
        preview_text += "<div class='popup-window'>\n"
        preview_text += f"<div class='popup-title'>{popup_name}</div>\n"

        if popup_class == "Submenu":
            # Group stats by submenu
            submenus = {}
            no_submenu = []
            for stat in stats:
                if stat.get("submenu"):
                    if stat["submenu"] not in submenus:
                        submenus[stat["submenu"]] = []
                    submenus[stat["submenu"]].append(stat)
                else:
                    no_submenu.append(stat)

            # Display stats without submenu first
            for stat in no_submenu:
                preview_text += f"<div class='stat-row'><span class='stat-name'>{stat['stat_name']}</span><span class='stat-value'>--</span></div>\n"

            # Display submenus
            for submenu_name, submenu_stats in submenus.items():
                preview_text += f"<div class='submenu-header'>▼ {submenu_name}</div>\n"
                for stat in submenu_stats:
                    preview_text += f"<div class='stat-row' style='padding-left: 15px;'><span class='stat-name'>{stat['stat_name']}</span><span class='stat-value'>--</span></div>\n"

        elif popup_class == "Multicol":
            # Display in multiple columns
            preview_text += "<div class='multicol-container'>\n"

            # Split stats into columns (3 columns max)
            cols = min(3, max(1, len(stats) // 5 + 1))
            stats_per_col = len(stats) // cols + (1 if len(stats) % cols else 0)

            for col in range(cols):
                preview_text += "<div class='multicol-column'>\n"
                start_idx = col * stats_per_col
                end_idx = min(start_idx + stats_per_col, len(stats))

                for i in range(start_idx, end_idx):
                    if i < len(stats):
                        stat = stats[i]
                        preview_text += f"<div class='stat-row'><span class='stat-name'>{stat['stat_name']}</span><span class='stat-value'>--</span></div>\n"

                preview_text += "</div>\n"

            preview_text += "</div>\n"

        else:  # default class
            # Simple list format
            for stat in stats:
                preview_text += f"<div class='stat-row'><span class='stat-name'>{stat['stat_name']}</span><span class='stat-value'>--</span></div>\n"

        preview_text += "</div>\n"

        # Add description
        caption_color = palette.text().color()
        caption_color.setAlpha(150)  # Rendre le texte un peu plus transparent
        caption_color_str = caption_color.name(QColor.HexArgb)

        if popup_class == "Submenu":
            preview_text += f"<p style='font-size: 11px; color: {caption_color_str}; margin-top: 10px;'><i>Hierarchical menu with collapsible sections</i></p>"
        elif popup_class == "Multicol":
            preview_text += f"<p style='font-size: 11px; color: {caption_color_str}; margin-top: 10px;'><i>Multi-column layout for better space utilization</i></p>"
        else:
            preview_text += f"<p style='font-size: 11px; color: {caption_color_str}; margin-top: 10px;'><i>Simple list format with stat names and values</i></p>"

        self.popup_preview.setHtml(preview_text)

    def on_profile_selected(self, index):
        if index < 0 or index >= self.profile_combo.count():
            self.stat_table.setRowCount(0)
            self.preview.set_stats([])
            self.update_status()
            return
        name = self.profile_combo.currentText()
        profile = self.hud_profiles.get(name, {})

        # Handle both old format (list) and new format (dict with rows/cols/stats)
        if isinstance(profile, list):
            # Old format - just a list of stats
            stats = profile
            rows = 5
            cols = 5
        else:
            # New format - dict with rows, cols, stats
            stats = profile.get("stats", [])
            rows = profile.get("rows", 5)
            cols = profile.get("cols", 5)

        # Update grid size
        self.preview.set_grid(rows, cols)

        # Update table
        self.stat_table.setRowCount(len(stats))
        for i, stat in enumerate(stats):
            # Create items with better formatting
            row_item = QTableWidgetItem(str(stat["row"]))
            row_item.setTextAlignment(Qt.AlignCenter)
            self.stat_table.setItem(i, 0, row_item)

            col_item = QTableWidgetItem(str(stat["col"]))
            col_item.setTextAlignment(Qt.AlignCenter)
            self.stat_table.setItem(i, 1, col_item)

            stat_item = QTableWidgetItem(stat["stat"])
            self.stat_table.setItem(i, 2, stat_item)

            click_item = QTableWidgetItem(stat.get("click", ""))
            self.stat_table.setItem(i, 3, click_item)

            popup_item = QTableWidgetItem(stat.get("popup", ""))
            self.stat_table.setItem(i, 4, popup_item)

            # Add color indicator if colors are configured
            if stat.get("stat_locolor") or stat.get("stat_hicolor"):
                stat_item.setToolTip(
                    f"Colors configured: Low={stat.get('stat_locolor', 'none')}, High={stat.get('stat_hicolor', 'none')}"
                )

        self.preview.set_stats(stats)
        self.update_status()

    def add_profile(self):
        # Create custom dialog for profile creation
        dialog = QDialog(self)
        dialog.setWindowTitle("New Profile")
        layout = QFormLayout(dialog)

        # Name input
        name_input = QLineEdit()
        layout.addRow("Profile name:", name_input)

        # Rows input
        rows_input = QSpinBox()
        rows_input.setMinimum(1)
        rows_input.setMaximum(10)
        rows_input.setValue(3)
        layout.addRow("Rows:", rows_input)

        # Columns input
        cols_input = QSpinBox()
        cols_input.setMinimum(1)
        cols_input.setMaximum(10)
        cols_input.setValue(2)
        layout.addRow("Columns:", cols_input)

        # Buttons
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(dialog.accept)
        btn_box.rejected.connect(dialog.reject)
        layout.addRow(btn_box)

        if dialog.exec_() == QDialog.Accepted:
            name = name_input.text()
            if name and name not in self.hud_profiles:
                rows = rows_input.value()
                cols = cols_input.value()
                # Store profile with matrix size info
                self.hud_profiles[name] = {"rows": rows, "cols": cols, "stats": []}
                self.profile_combo.addItem(name)
                self.profile_combo.setCurrentIndex(self.profile_combo.count() - 1)
                # Update preview grid size
                self.preview.set_grid(rows, cols)

    def duplicate_profile(self):
        if self.profile_combo.currentIndex() < 0:
            return
        name = self.profile_combo.currentText()
        from PyQt5.QtWidgets import QInputDialog

        new_name, ok = QInputDialog.getText(self, "Duplicate Profile", "New profile name:")
        if ok and new_name and new_name not in self.hud_profiles:
            import copy

            self.hud_profiles[new_name] = copy.deepcopy(self.hud_profiles[name])
            self.profile_combo.addItem(new_name)
            self.profile_combo.setCurrentIndex(self.profile_combo.count() - 1)

    def delete_profile(self):
        if self.profile_combo.currentIndex() < 0:
            return
        name = self.profile_combo.currentText()
        if (
            QMessageBox.question(self, "Delete Profile", f"Delete profile '{name}'?", QMessageBox.Yes | QMessageBox.No)
            == QMessageBox.Yes
        ):
            current_index = self.profile_combo.currentIndex()
            del self.hud_profiles[name]
            self.profile_combo.removeItem(current_index)
            if self.profile_combo.count() > 0:
                self.profile_combo.setCurrentIndex(0)
            else:
                self.stat_table.setRowCount(0)
                self.preview.set_stats([])

    def get_current_profile(self):
        if self.profile_combo.currentIndex() < 0:
            return None, None
        name = self.profile_combo.currentText()
        profile = self.hud_profiles[name]

        # Handle both old and new format
        if isinstance(profile, list):
            # Old format - return the list directly
            return name, profile
        else:
            # New format - return the stats list
            return name, profile.get("stats", [])

    def add_stat(self):
        name, stats = self.get_current_profile()
        if stats is None:
            return

        # Get grid size for current profile
        profile = self.hud_profiles[name]
        if isinstance(profile, dict):
            max_rows = profile.get("rows", 5)
            max_cols = profile.get("cols", 5)
        else:
            max_rows = max_cols = 5

        dlg = AddStatDialog(max_rows=max_rows, max_cols=max_cols, parent=self)
        if dlg.exec_():
            stat = dlg.get_stat()
            stats.append(stat)
            self.on_profile_selected(self.profile_combo.currentIndex())

    def edit_stat(self):
        name, stats = self.get_current_profile()
        if stats is None:
            return
        row = self.stat_table.currentRow()
        if row < 0 or row >= len(stats):
            return

        # Get grid size for current profile
        profile = self.hud_profiles[name]
        if isinstance(profile, dict):
            max_rows = profile.get("rows", 5)
            max_cols = profile.get("cols", 5)
        else:
            max_rows = max_cols = 5

        dlg = AddStatDialog(stat=stats[row], max_rows=max_rows, max_cols=max_cols, parent=self)
        if dlg.exec_():
            stats[row] = dlg.get_stat()
            self.on_profile_selected(self.profile_combo.currentIndex())

    def remove_stat(self):
        name, stats = self.get_current_profile()
        if stats is None:
            return
        row = self.stat_table.currentRow()
        if row < 0 or row >= len(stats):
            return
        del stats[row]
        self.on_profile_selected(self.profile_combo.currentIndex())

    def save_changes(self):
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

                # For each profile, update or create the stat set in XML
                for profile_name, profile_data in self.hud_profiles.items():
                    # Find or create the stat set node
                    stat_set_node = None
                    for ss_node in self.config.doc.getElementsByTagName("ss"):
                        if ss_node.getAttribute("name") == profile_name:
                            stat_set_node = ss_node
                            break

                    if stat_set_node is None:
                        # Create new stat set node if it doesn't exist
                        # Add newline and indentation before the new node
                        indent = self.config.doc.createTextNode("\n        ")
                        stat_sets_node.appendChild(indent)

                        stat_set_node = self.config.doc.createElement("ss")
                        stat_set_node.setAttribute("name", profile_name)
                        stat_sets_node.appendChild(stat_set_node)

                    # Handle both old and new format
                    if isinstance(profile_data, list):
                        # Old format - list of stats
                        stats = profile_data
                        rows = 5
                        cols = 5
                    else:
                        # New format - dict with rows/cols/stats
                        stats = profile_data.get("stats", [])
                        rows = profile_data.get("rows", 5)
                        cols = profile_data.get("cols", 5)

                    # Update rows and cols
                    stat_set_node.setAttribute("rows", str(rows))
                    stat_set_node.setAttribute("cols", str(cols))

                    # Remove all existing stat nodes and text nodes
                    while stat_set_node.firstChild:
                        stat_set_node.removeChild(stat_set_node.firstChild)

                    # Add new stat nodes with proper formatting
                    for i, stat in enumerate(stats):
                        # Add newline and indentation before each stat
                        indent = self.config.doc.createTextNode("\n            ")
                        stat_set_node.appendChild(indent)

                        stat_node = self.config.doc.createElement("stat")

                        # Set all attributes
                        stat_node.setAttribute("_rowcol", f"({stat['row']+1},{stat['col']+1})")
                        stat_node.setAttribute("_stat_name", stat.get("stat", ""))
                        stat_node.setAttribute("click", stat.get("click", ""))
                        stat_node.setAttribute("popup", stat.get("popup", "default"))
                        stat_node.setAttribute("tip", stat.get("tip", ""))
                        stat_node.setAttribute("hudprefix", stat.get("hudprefix", ""))
                        stat_node.setAttribute("hudsuffix", stat.get("hudsuffix", ""))
                        stat_node.setAttribute("hudcolor", stat.get("hudcolor", ""))
                        stat_node.setAttribute("stat_loth", stat.get("stat_loth", ""))
                        stat_node.setAttribute("stat_hith", stat.get("stat_hith", ""))
                        stat_node.setAttribute("stat_locolor", stat.get("stat_locolor", ""))
                        stat_node.setAttribute("stat_hicolor", stat.get("stat_hicolor", ""))
                        stat_node.setAttribute("stat_midcolor", stat.get("stat_midcolor", ""))

                        stat_set_node.appendChild(stat_node)

                    # Add final newline and proper indentation
                    if stats:
                        final_indent = self.config.doc.createTextNode("\n        ")
                        stat_set_node.appendChild(final_indent)

                # Add final newline after all stat sets
                if (
                    stat_sets_node.lastChild
                    and stat_sets_node.lastChild.nodeType == stat_sets_node.lastChild.ELEMENT_NODE
                ):
                    final_indent = self.config.doc.createTextNode("\n    ")
                    stat_sets_node.appendChild(final_indent)

                # Also update the config.stat_sets for consistency
                self.config.stat_sets = {}
                for profile_name, profile_data in self.hud_profiles.items():
                    # Create a new stat set
                    stat_set = type("StatSet", (), {})()
                    stat_set.name = profile_name

                    # Handle both old and new format
                    if isinstance(profile_data, list):
                        stats = profile_data
                        stat_set.rows = 5
                        stat_set.cols = 5
                    else:
                        stats = profile_data.get("stats", [])
                        stat_set.rows = profile_data.get("rows", 5)
                        stat_set.cols = profile_data.get("cols", 5)

                    # Convert stats to config format
                    stat_set.stats = {}
                    for stat in stats:
                        pos = (stat["row"], stat["col"])
                        stat_obj = type("Stat", (), {})()
                        stat_obj.stat_name = stat["stat"]
                        stat_obj.click = stat.get("click", "")
                        stat_obj.popup = stat.get("popup", "")
                        stat_obj.tip = stat.get("tip", "")
                        stat_obj.hudprefix = stat.get("hudprefix", "")
                        stat_obj.hudsuffix = stat.get("hudsuffix", "")
                        stat_obj.hudcolor = stat.get("hudcolor", "")
                        stat_obj.stat_loth = stat.get("stat_loth", "")
                        stat_obj.stat_hith = stat.get("stat_hith", "")
                        stat_obj.stat_locolor = stat.get("stat_locolor", "")
                        stat_obj.stat_hicolor = stat.get("stat_hicolor", "")
                        stat_obj.stat_midcolor = stat.get("stat_midcolor", "")
                        stat_set.stats[pos] = stat_obj

                    self.config.stat_sets[profile_name] = stat_set

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

                    # Add stats
                    for stat in popup_data["stats"]:
                        stat_indent = self.config.doc.createTextNode("\n            ")
                        pu_node.appendChild(stat_indent)

                        pu_stat_node = self.config.doc.createElement("pu_stat")
                        pu_stat_node.setAttribute("pu_stat_name", stat["stat_name"])
                        if stat.get("submenu"):
                            pu_stat_node.setAttribute("pu_stat_submenu", stat["submenu"])

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

            # Save to file
            if hasattr(self.config, "save"):
                self.config.save()
                # Update original profiles and popups after successful save
                self.original_profiles = self._deep_copy_profiles(self.hud_profiles)
                self.original_popups = self._deep_copy_popups(self.popup_windows)
                QMessageBox.information(self, "Success", "HUD configuration saved successfully!")
            else:
                QMessageBox.warning(self, "Warning", "Could not save to file. Config save method not available.")

            self.accept()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save HUD profiles:\n{str(e)}")

    def add_popup(self):
        """Add a new popup window"""
        from PyQt5.QtWidgets import QInputDialog

        name, ok = QInputDialog.getText(self, "New Popup", "Enter popup name:")
        if ok and name and name not in self.popup_windows:
            self.popup_windows[name] = {"name": name, "class": "default", "stats": []}
            self.popup_combo.addItem(name)
            self.popup_combo.setCurrentText(name)

    def duplicate_popup(self):
        """Duplicate current popup"""
        if self.popup_combo.currentIndex() < 0:
            return
        current_name = self.popup_combo.currentText()
        from PyQt5.QtWidgets import QInputDialog

        new_name, ok = QInputDialog.getText(self, "Duplicate Popup", "New popup name:")
        if ok and new_name and new_name not in self.popup_windows:
            import copy

            self.popup_windows[new_name] = copy.deepcopy(self.popup_windows[current_name])
            self.popup_windows[new_name]["name"] = new_name
            self.popup_combo.addItem(new_name)
            self.popup_combo.setCurrentText(new_name)

    def delete_popup(self):
        """Delete current popup"""
        if self.popup_combo.currentIndex() < 0:
            return
        popup_name = self.popup_combo.currentText()
        reply = QMessageBox.question(
            self,
            "Delete Popup",
            f"Are you sure you want to delete the popup '{popup_name}'?",
            QMessageBox.Yes | QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            current_index = self.popup_combo.currentIndex()
            del self.popup_windows[popup_name]
            self.popup_combo.removeItem(current_index)
            if self.popup_combo.count() > 0:
                self.popup_combo.setCurrentIndex(0)

    def add_popup_stat(self):
        """Add a stat to current popup"""
        if self.popup_combo.currentIndex() < 0:
            return

        dialog = PopupStatEditDialog(parent=self)
        if dialog.exec_():
            stat_data = dialog.get_stat_data()
            popup_name = self.popup_combo.currentText()
            self.popup_windows[popup_name]["stats"].append(stat_data)
            self.on_popup_selected(self.popup_combo.currentIndex())

    def edit_popup_stat(self):
        """Edit selected stat in current popup"""
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
        if dialog.exec_():
            stats[current_row] = dialog.get_stat_data()
            self.on_popup_selected(self.popup_combo.currentIndex())

    def remove_popup_stat(self):
        """Remove selected stat from current popup"""
        if self.popup_combo.currentIndex() < 0:
            return

        current_row = self.popup_stats_list.currentRow()
        if current_row < 0:
            return

        popup_name = self.popup_combo.currentText()
        self.popup_windows[popup_name]["stats"].pop(current_row)
        self.on_popup_selected(self.popup_combo.currentIndex())

    def move_stat_up(self):
        """Move selected stat up in the list"""
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

    def move_stat_down(self):
        """Move selected stat down in the list"""
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
class PopupStatEditDialog(QDialog):
    def __init__(self, stat_data=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Popup Statistic")
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
        self.submenu_input.setPlaceholderText("Optional: Submenu name for hierarchical popups")
        if stat_data:
            self.submenu_input.setText(stat_data.get("submenu", ""))
        layout.addRow("Submenu:", self.submenu_input)

        # Dialog buttons
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addRow(btn_box)

    def get_stat_data(self):
        """Get the stat data from the dialog"""
        return {"stat_name": self.stat_name_input.text(), "submenu": self.submenu_input.text()}


# --- Popup Edit Dialog ---
class PopupEditDialog(QDialog):
    def __init__(self, popup_data=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Popup Window")
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
        self.stats_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.stats_table.setMinimumHeight(250)
        stats_layout.addWidget(self.stats_table)

        # Stats buttons
        stats_btn_layout = QHBoxLayout()

        add_stat_btn = QPushButton("➕ Add Stat")
        add_stat_btn.clicked.connect(self.add_stat)

        remove_stat_btn = QPushButton("➖ Remove Stat")
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

    def add_stat(self):
        """Add a new stat to the table"""
        row = self.stats_table.rowCount()
        self.stats_table.insertRow(row)
        self.stats_table.setItem(row, 0, QTableWidgetItem(""))
        self.stats_table.setItem(row, 1, QTableWidgetItem(""))
        # Make the new row editable
        self.stats_table.editItem(self.stats_table.item(row, 0))

    def remove_stat(self):
        """Remove selected stat from the table"""
        current_row = self.stats_table.currentRow()
        if current_row >= 0:
            self.stats_table.removeRow(current_row)

    def get_popup_data(self):
        """Get the popup data from the dialog"""
        stats = []
        for row in range(self.stats_table.rowCount()):
            stat_name_item = self.stats_table.item(row, 0)
            submenu_item = self.stats_table.item(row, 1)

            if stat_name_item and stat_name_item.text():
                stats.append(
                    {"stat_name": stat_name_item.text(), "submenu": submenu_item.text() if submenu_item else ""}
                )

        return {"name": self.name_input.text(), "class": self.class_combo.currentText(), "stats": stats}
