#!/usr/bin/env python
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
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
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy import Configuration
from fpdb_3_legacy.Aux_Hud import SimpleLabel
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("modern_hud_preferences")

# PT4-style item alignment names -> Qt flags (preview cells).
_PREVIEW_ALIGN = {
    "left": Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
    "center": Qt.AlignmentFlag.AlignCenter,
    "right": Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
}


# --- Color Preview Widget ---
class ColorPreviewWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.low_color = QColor("#ff0000")
        self.mid_color = QColor("#ffff00")
        self.high_color = QColor("#00ff00")
        self.low_threshold = 20
        self.high_threshold = 60
        self.use_mid_color = False

    def set_colors(self, low_color, mid_color, high_color, low_threshold, high_threshold, use_mid_color) -> None:
        self.low_color = QColor(low_color)
        self.mid_color = QColor(mid_color)
        self.high_color = QColor(high_color)
        self.low_threshold = low_threshold
        self.high_threshold = high_threshold
        self.use_mid_color = use_mid_color
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

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
class HudPreviewWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(360, 320)
        self.grid_rows = 5
        self.grid_cols = 5
        self.xpad = 0
        self.ypad = 0
        self.hud_bgcolor = "#000000"
        self.hud_fgcolor = "#ffffff"
        self.hud_font = "Sans"
        self.hud_font_size = 8
        self.preview_scale = 1.45
        self.stats = []  # List of dicts: {row, col, stat, click, popup}
        self.blocks = []  # Multi-panel layout: list of block dicts (styled boxes)
        self.sample_values = {
            "playershort": "trips.",
            "playernote": "📝",
            "player_note": "📝",
            "totalprofit": "$-4.14",
            "profit100": "-37.64",
            "vpip": "33",
            "pfr": "22",
            "threeb": "4.4",
            "three_b": "4.4",
            "ffreq1": "48",
            "fold3b": "27.3",
            "fold_3b": "27.3",
            "fold_3bet": "27.3",
            "n": "11",
            "wtsd": "29",
            "wmsd": "52",
            "3bet": "8",
            "f3bet": "61",
            "steal": "38",
            "agg": "2.4",
            "aggfact": "2.00",
            "agg_fact": "2.00",
            "cb1": "50.0",
            "cb2": "50.0",
            "cb3": "33.3",
            "fcb1": "80.0",
            "f_cb1": "80.0",
            "fcb2": "100.0",
            "f_cb2": "100.0",
            "fcb3": "--",
            "f_cb3": "--",
            # imported PT4 / GenerationPoker stats
            "agg_fact_pct": "55",
            "squeeze": "6.2",
            "iso": "31",
            "cold_call": "9",
            "float_bet": "24",
            "float_turn": "18",
            "float_river": "12",
            "gp_2x": "78",
            "gp_os": "8",
            "gp_limp": "14",
        }
        self.sample_colors = {
            "vpip": "#ff3333",
            "pfr": "#ffb000",
            "threeb": "#ff3333",
            "three_b": "#ff3333",
            "fold3b": "#ffb000",
            "fold_3b": "#ffb000",
            "fold_3bet": "#ffb000",
            "cb1": "#ffb000",
            "cb2": "#ffb000",
            "cb3": "#ffb000",
            "fcb1": "#ff3333",
            "f_cb1": "#ff3333",
            "fcb2": "#ff3333",
            "f_cb2": "#ff3333",
            "n": "#00c853",
        }
        self.hud_window = QWidget(self)
        self.hud_window.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        # Outer vertical layout holds either a single flat grid (classic profile)
        # or several stacked panel boxes (multi-panel PT4 layout).
        self.hud_outer = QVBoxLayout(self.hud_window)
        self.hud_outer.setContentsMargins(2, 2, 2, 2)
        self.hud_window.setLayout(self.hud_outer)
        self._rebuild_hud_window()

    def set_grid(self, rows, cols) -> None:
        self.grid_rows = rows
        self.grid_cols = cols
        self._rebuild_hud_window()

    def set_stats(self, stats) -> None:
        self.stats = stats
        self.blocks = []
        self._rebuild_hud_window()

    def set_blocks(self, blocks) -> None:
        """Render a multi-panel layout: each block as a bordered, titled box."""
        self.blocks = blocks or []
        self._rebuild_hud_window()

    def set_hud_params(
        self,
        *,
        xpad: int = 0,
        ypad: int = 0,
        bgcolor: str = "#000000",
        fgcolor: str = "#ffffff",
        font: str = "Sans",
        font_size: int | str = 8,
    ) -> None:
        self.xpad = int(xpad or 0)
        self.ypad = int(ypad or 0)
        self.hud_bgcolor = bgcolor or "#000000"
        self.hud_fgcolor = fgcolor or "#ffffff"
        self.hud_font = font or "Sans"
        self.hud_font_size = int(font_size or 8)
        self._rebuild_hud_window()

    def _clear_hud_outer(self) -> None:
        while self.hud_outer.count():
            item = self.hud_outer.takeAt(0)
            widget = item.widget()
            if widget:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

    def _sample_value_for(self, stat_name: str) -> str:
        key = self._stat_key(stat_name)
        return self.sample_values.get(key, "--")

    def _stat_key(self, stat_name: str) -> str:
        return stat_name.lower().strip()

    def _style_for_stat(self, stat: dict) -> str:
        stat_name = stat.get("stat", "")
        key = self._stat_key(stat_name)
        fg = stat.get("hudcolor") or self.sample_colors.get(key) or stat.get("stat_hicolor") or self.hud_fgcolor
        font_size = max(8, round(self.hud_font_size * self.preview_scale))
        return (
            f"QLabel{{font-family: {self.hud_font};font-size: {font_size}pt;"
            f"font-weight: 700;color: {fg};background: transparent;padding: 0px 3px;}}"
        )

    def _qss_color(self, color: str, fallback: str) -> str:
        color = (color or "").strip()
        return color if color and not color.lower().startswith("rgba") else fallback

    def _cell_label(self, stat: dict) -> SimpleLabel:
        """Build a single styled value cell (text colour, optional bg colour)."""
        scaled = max(8, round(self.hud_font_size * self.preview_scale))
        stat_name = stat.get("stat", "")
        lab = SimpleLabel("---")
        lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lab.setFont(QFont(self.hud_font, scaled))
        key = self._stat_key(stat_name)
        fg = stat.get("hudcolor") or self.sample_colors.get(key) or stat.get("stat_hicolor") or self.hud_fgcolor
        bg = stat.get("hudbgcolor")
        bg_rule = f"background:{bg};" if bg else "background: transparent;"
        lab.setStyleSheet(
            f"QLabel{{font-family:{self.hud_font};font-size:{scaled}pt;font-weight:700;"
            f"color:{fg};{bg_rule}padding:0px 3px;border:none;}}",
        )
        value = self._sample_value_for(stat_name) if stat_name else "---"
        if stat_name:
            value = f"{stat.get('hudprefix', '')}{value}{stat.get('hudsuffix', '')}"
        lab.setText(value)
        lab.setToolTip(stat_name)
        lab.setMinimumWidth(max(38, scaled * 4))
        lab.setMinimumHeight(max(20, round(scaled * 1.5)))
        return lab

    def _build_flat_grid(self) -> QWidget:
        host = QWidget()
        bg = self._qss_color(self.hud_bgcolor, "#000000")
        host.setStyleSheet(
            f"QWidget{{background-color:{bg};color:{self.hud_fgcolor};"
            "border:1px solid #4b335e;}QLabel{border:none;}QToolTip{}",
        )
        grid = QGridLayout(host)
        grid.setHorizontalSpacing(round(4 * self.preview_scale))
        grid.setVerticalSpacing(max(1, round(self.preview_scale)))
        grid.setContentsMargins(round(2 * self.preview_scale), round(2 * self.preview_scale),
                                round(2 * self.preview_scale), round(2 * self.preview_scale))
        stat_by_pos = {
            (s.get("row", 0), s.get("col", 0)): s
            for s in self.stats
            if 0 <= s.get("row", 0) < self.grid_rows and 0 <= s.get("col", 0) < self.grid_cols
        }
        for row in range(max(1, self.grid_rows)):
            for col in range(max(1, self.grid_cols)):
                grid.addWidget(self._cell_label(stat_by_pos.get((row, col), {})), row, col)
        return host

    def _build_block_box(self, block: dict) -> QWidget:
        """A bordered panel with a coloured title header and its stat grid."""
        scaled = max(8, round(self.hud_font_size * self.preview_scale))
        border = self._qss_color(block.get("bordercolor", ""), "#4b335e")
        bg = self._qss_color(self.hud_bgcolor, "#000000")
        box = QWidget()
        box.setStyleSheet(f"QWidget{{background-color:{bg};border:2px solid {border};}}QLabel{{border:none;}}")
        vbox = QVBoxLayout(box)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        label = block.get("label", "")
        if label:
            title = SimpleLabel(label)
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title.setFont(QFont(self.hud_font, scaled, QFont.Weight.Bold))
            t_bg = self._qss_color(block.get("title_bgcolor", ""), border)
            t_fg = self._qss_color(block.get("title_fgcolor", ""), "#111111")
            title.setStyleSheet(
                f"QLabel{{background:{t_bg};color:{t_fg};font-weight:800;"
                f"font-size:{scaled}pt;padding:1px 4px;border:none;}}",
            )
            vbox.addWidget(title)

        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setHorizontalSpacing(round(4 * self.preview_scale))
        grid.setVerticalSpacing(max(1, round(self.preview_scale)))
        grid.setContentsMargins(2, 2, 2, 2)
        bstats = block.get("stats", [])
        btexts = block.get("texts", [])
        nrows = block.get("rows") or (max([s.get("row", 0) for s in bstats]
                                          + [t["rowcol"][0] for t in btexts], default=-1) + 1)
        ncols = block.get("cols") or (max([s.get("col", 0) for s in bstats]
                                          + [t["rowcol"][1] for t in btexts], default=-1) + 1)
        # Text-label items first (column/row headers, captions) at their position.
        for t in btexts:
            r, c = t["rowcol"]
            grid.addWidget(self._text_item_label(t), r, c, 1, max(1, int(t.get("colspan", 1))))
        by_pos = {(s.get("row", 0), s.get("col", 0)): s for s in bstats}
        for r in range(max(1, nrows)):
            for c in range(max(1, ncols)):
                if (r, c) in by_pos:
                    s = by_pos[(r, c)]
                    cell = self._cell_label(s)
                    align = s.get("align", "")
                    if align in _PREVIEW_ALIGN:
                        cell.setAlignment(_PREVIEW_ALIGN[align])
                    grid.addWidget(cell, r, c, 1, max(1, int(s.get("colspan", 1) or 1)))
        # Horizontal-line separators (PT4 "Horz Line" items).
        for h in block.get("hlines", []):
            r, c = h["rowcol"]
            line = QFrame()
            line.setFrameShape(QFrame.Shape.HLine)
            line.setFixedHeight(1)
            color = self._qss_color(h.get("color", ""), self.hud_fgcolor)
            line.setStyleSheet(f"QFrame{{color:{color};background:{color};border:none;}}")
            grid.addWidget(line, r, c, 1, max(1, h.get("colspan") or ncols))
        vbox.addWidget(grid_host)
        return box

    def _text_item_label(self, text: dict) -> SimpleLabel:
        """A non-data header/caption label inside a block."""
        scaled = max(8, round(self.hud_font_size * self.preview_scale))
        lab = SimpleLabel(text.get("label", ""))
        lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lab.setFont(QFont(self.hud_font, scaled, QFont.Weight.Bold))
        fg = self._qss_color(text.get("fgcolor", ""), self.hud_fgcolor)
        bg = text.get("bgcolor", "")
        bg_rule = f"background:{bg};" if bg else "background: transparent;"
        lab.setStyleSheet(
            f"QLabel{{font-family:{self.hud_font};font-size:{scaled}pt;font-weight:800;"
            f"color:{fg};{bg_rule}padding:0px 3px;border:none;}}",
        )
        return lab

    def _rebuild_hud_window(self) -> None:
        if not hasattr(self, "hud_outer"):
            return
        self._clear_hud_outer()
        self.hud_outer.setSpacing(max(2, round(3 * self.preview_scale)))
        if self.blocks:
            for block in self.blocks:
                self.hud_outer.addWidget(self._build_block_box(block))
        else:
            self.hud_outer.addWidget(self._build_flat_grid())
        self.hud_outer.activate()
        self.hud_window.updateGeometry()
        self.hud_window.adjustSize()
        self.hud_window.show()
        self._position_hud_window()
        QTimer.singleShot(0, self._position_hud_window)
        self.update()

    def _position_hud_window(self) -> None:
        if self.width() <= 0 or self.height() <= 0:
            return
        # The HUD keeps its natural size; the widget grows to fit it so a wrapping
        # scroll area shows scrollbars instead of clipping/overlapping a large HUD.
        size = self.hud_window.sizeHint()
        content_w = max(size.width(), self.hud_window.width(), 1)
        content_h = max(size.height(), self.hud_window.height(), 1)
        margin = 16
        self.setMinimumSize(max(280, content_w + margin), max(240, content_h + margin))
        avail_w = max(self.width(), content_w + margin)
        avail_h = max(self.height(), content_h + margin)
        self.hud_window.setGeometry(
            (avail_w - content_w) // 2,
            (avail_h - content_h) // 2,
            content_w,
            content_h,
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_hud_window()

    def showEvent(self, event) -> None:
        # The first profile is often loaded before the pane has a real size, so
        # re-position once we are actually shown to avoid a blank preview.
        super().showEvent(event)
        self._position_hud_window()
        QTimer.singleShot(0, self._position_hud_window)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#1d282e"))
        painter.drawRect(self.rect())


class PopupPreviewWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.sample_values = {
            "playername": "trips.",
            "playershort": "trips.",
            "player_note": "📝",
            "n": "11",
            "vpip": "44.4",
            "pfr": "27.3",
            "three_b": "33.3",
            "3bet": "33.3",
            "f_3bet": "50.0",
            "f3bet": "50.0",
            "cb1": "50.0",
            "cb2": "33.3",
            "cb3": "--",
            "f_cb1": "80.0",
            "f_cb2": "100.0",
            "f_cb3": "--",
            "rfi_early_position": "80.0",
            "rfi_middle_position": "100.0",
            "rfi_late_position": "33.3",
            "agg_fact": "2.00",
            "wtsd": "29",
            "wmsd": "52",
            "totalprofit": "$-4.14",
            "profit100": "-37.64",
        }
        self.sample_colors = {
            "vpip": "#ff3333",
            "pfr": "#ffb000",
            "three_b": "#ff3333",
            "3bet": "#ff3333",
            "f_3bet": "#ffb000",
            "f3bet": "#ffb000",
            "cb1": "#ffb000",
            "cb2": "#ffb000",
            "f_cb1": "#ff3333",
            "f_cb2": "#ff3333",
            "rfi_early_position": "#ff3333",
            "rfi_middle_position": "#ff3333",
            "rfi_late_position": "#ffb000",
            "agg_fact": "#ffb000",
            "n": "#00c853",
        }

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.viewport = QFrame()
        self.viewport.setStyleSheet("QFrame{background:#1d282e;border:none;}")
        viewport_layout = QVBoxLayout(self.viewport)
        viewport_layout.setContentsMargins(8, 8, 8, 8)

        self.popup_frame = QFrame()
        self.popup_frame.setObjectName("popupPreviewFrame")
        self.popup_layout = QVBoxLayout(self.popup_frame)
        self.popup_layout.setContentsMargins(6, 5, 6, 5)
        self.popup_layout.setSpacing(2)

        self.scroll_area = QScrollArea()
        # Legacy previews should fill the viewport; imported PT4 grids switch this
        # off so their full natural canvas remains reachable with scrollbars.
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.scroll_area.setWidget(self.popup_frame)
        # Fill the available preview space (scroll when the popup is larger)
        # instead of staying at a fixed small box in a big empty pane.
        self.scroll_area.setMinimumSize(300, 220)
        self.scroll_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.scroll_area.setStyleSheet("""
            QScrollArea{background:transparent;border:none;}
            QScrollBar:vertical{background:#11161c;width:14px;margin:0;}
            QScrollBar:horizontal{background:#11161c;height:14px;margin:0;}
            QScrollBar::handle{background:#7b6f99;min-height:30px;min-width:30px;border-radius:5px;}
            QScrollBar::handle:hover{background:#9a8bc0;}
            QScrollBar::add-line,QScrollBar::sub-line{height:0px;width:0px;}
        """)
        viewport_layout.addWidget(self.scroll_area)
        outer.addWidget(self.viewport)

    def clear_preview(self) -> None:
        self._clear_layout(self.popup_layout)
        self.popup_frame.setMinimumSize(0, 0)  # reset before the next popup sizes it
        self.popup_frame.resize(0, 0)

    def set_popup(self, popup_name: str, popup_class: str, stats: list[dict],
                  source: str = "", group: str = "") -> None:
        self.clear_preview()
        self.popup_frame.setStyleSheet("""
            QFrame#popupPreviewFrame{
                background:#050509;
                border:1px solid #4b335e;
            }
            QLabel{background:transparent;border:none;}
        """)
        self.scroll_area.setWidgetResizable(True)

        # BlockPopup (imported PT4 popup group): render its text/stat grid.
        if popup_class == "BlockPopup" or (group and source):
            self.scroll_area.setWidgetResizable(False)
            self._build_block_popup(popup_name, source, group)
            self._finalize_popup_frame()
            return

        # Range-chart popups (imported PT4 push/fold Nash grids) render their
        # 13x13 coloured matrices rather than a stat list. Trigger on the chart
        # source too, so the chart still shows if the class was overwritten.
        if popup_class == "RangeChartPopup" or (source and str(source).endswith(".json")):
            self.scroll_area.setWidgetResizable(False)
            self._build_range_charts(popup_name, source)
            self._finalize_popup_frame()
            return

        if not stats:
            self._add_empty_state(popup_name)
            return

        if popup_class == "Submenu":
            self._build_submenu(stats)
        elif popup_class == "Multicol":
            self._build_multicol(stats)
        else:
            self._build_default(stats)

        self._finalize_popup_frame()

    def _finalize_popup_frame(self) -> None:
        """Lay out and show the rendered popup at its full natural extent."""
        self.popup_layout.activate()
        hint = self.popup_frame.sizeHint()
        min_size = self.popup_frame.minimumSize()
        viewport = self.scroll_area.viewport().size()
        if self.scroll_area.widgetResizable():
            width = max(hint.width(), min_size.width(), viewport.width(), 1)
            height = max(hint.height(), min_size.height(), viewport.height(), 1)
            self.popup_frame.setMinimumSize(width, height)
        else:
            width = max(hint.width(), min_size.width(), 1)
            height = max(hint.height(), min_size.height(), 1)
        self.popup_frame.resize(width, height)
        self.popup_frame.show()

    def _clear_layout(self, layout: QVBoxLayout | QGridLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if child_layout := item.layout():
                self._clear_layout(child_layout)
            if widget := item.widget():
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

    def _add_empty_state(self, popup_name: str) -> None:
        label = QLabel(f"{popup_name}\nNo popup stats configured")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color:#ffffff;font-weight:700;padding:18px;")
        self.popup_layout.addWidget(label)
        label.show()

    def _build_range_charts(self, popup_name: str, source: str) -> None:
        """Render the imported 13x13 PT4 range charts as coloured matrices."""
        from fpdb_3_legacy.RangeChartPopup import build_grid_widget, load_charts

        charts = []
        if source:
            try:
                charts = load_charts(source)
            except Exception:
                log.exception("popup preview: failed to load charts from %s", source)
        if not charts:
            self._add_empty_state(f"{popup_name}\n(range chart data unavailable)")
            return
        for chart in charts:
            self.popup_layout.addWidget(build_grid_widget(chart, cell_px=28))
        # Guarantee the frame is tall/wide enough so the whole grid is scrollable.
        cell_pitch = 29
        chart_height = 13 * cell_pitch + 30
        self.popup_frame.setMinimumSize(13 * cell_pitch + 28, len(charts) * chart_height + 18)

    def _build_block_popup(self, popup_name: str, source: str, group: str) -> None:
        """Render an imported PT4 popup group (text/stat grid) in the preview."""
        from fpdb_3_legacy.BlockPopup import build_block_popup_widget, load_block_popup

        data = None
        if source and group:
            try:
                data = load_block_popup(source, group)
            except Exception:
                log.exception("popup preview: failed to load group %s from %s", group, source)
        if not data:
            self._add_empty_state(f"{popup_name}\n(popup group data unavailable)")
            return
        cell_px = 22 if int(data.get("cols", 1) or 1) >= 10 else 26
        self.popup_layout.addWidget(build_block_popup_widget(data, cell_px=cell_px))
        # Force the frame to the grid's real extent. Use the highest row index,
        # not just the number of occupied rows, because PT4 grids can contain gaps.
        cells = data.get("cells", [])
        occupied_rows = max([int(c.get("row", 0)) for c in cells] + [int(data.get("rows", 1) or 1) - 1]) + 1
        cols = max(1, int(data.get("cols", 1)))
        cell_w = (cell_px + 22) if cols >= 10 else 100
        cell_pitch = cell_px + 2
        self.popup_frame.setMinimumSize(cols * cell_w + 28, occupied_rows * cell_pitch + 44)

    def _build_default(self, stats: list[dict]) -> None:
        for stat in stats:
            self.popup_layout.addWidget(self._row_label(stat))

    def _build_submenu(self, stats: list[dict]) -> None:
        grouped: dict[str, list[dict]] = {}
        loose = []
        for stat in stats:
            submenu = stat.get("submenu", "")
            if submenu:
                grouped.setdefault(submenu, []).append(stat)
            else:
                loose.append(stat)

        for stat in loose:
            self.popup_layout.addWidget(self._row_label(stat))

        for submenu, submenu_stats in grouped.items():
            header = QLabel(f"> {submenu}")
            header.setStyleSheet("color:#d65aff;font-weight:800;padding:5px 4px 2px 4px;")
            self.popup_layout.addWidget(header)
            header.show()
            for stat in submenu_stats:
                self.popup_layout.addWidget(self._row_label(stat, indent=True))

    def _build_multicol(self, stats: list[dict]) -> None:
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(1)
        columns = max(1, min(3, (len(stats) + 11) // 12))
        rows_per_col = (len(stats) + columns - 1) // columns
        for index, stat in enumerate(stats):
            col = index // rows_per_col
            row = index % rows_per_col
            grid.addWidget(self._row_label(stat), row, col)
        self.popup_layout.addLayout(grid)

    def _row_label(self, stat: dict, *, indent: bool = False) -> QLabel:
        stat_name = stat.get("stat_name", "")
        key = stat_name.lower()
        value = self.sample_values.get(key, "--")
        color = self.sample_colors.get(key, "#ffffff")
        left_padding = 16 if indent else 4
        label = QLabel(f"{stat_name:<18} {value:>7}")
        label.setStyleSheet(
            f"color:{color};font-family:Menlo, Monaco, monospace;font-size:12pt;"
            f"font-weight:800;padding:1px 4px 1px {left_padding}px;",
        )
        label.setMinimumHeight(22)
        label.show()
        return label


# --- PT4-style design canvas (typed coloured chips in a grid) ---
class _CanvasChip(QFrame):
    """A single clickable item chip on the design canvas."""

    clicked = Signal()

    def __init__(self, kind: str, item_ref: dict, parent=None) -> None:
        super().__init__(parent)
        self.kind = kind
        self.item_ref = item_ref

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self.clicked.emit()
        super().mousePressEvent(event)


class HudDesignCanvas(QScrollArea):
    """PT4-style WYSIWYG design canvas for one panel (block).

    Renders the panel's items — stats, text labels, horizontal lines — as typed
    coloured chips placed in their grid positions (honouring colspan). Clicking a
    chip selects it; each occupied row carries +/- buttons. Mirrors the
    bottom-left design area of PokerTracker 4's Hud Profile Editor.
    """

    item_selected = Signal(object)   # (block_index, kind, item_ref)
    add_to_row = Signal(int)         # row index
    remove_from_row = Signal(int)    # row index

    # kind -> (icon letter, icon colour, chip background). Chip backgrounds are
    # dark theme tints; the type is conveyed by the coloured icon, not a light fill.
    TYPE = {
        "stat":  ("S", "#3b6fd4", "#20303c"),
        "text":  ("T", "#d79a2e", "#2e2a20"),
        "hline": ("H", "#d7b500", "#2e2a20"),
        "notes": ("N", "#3a9a3a", "#1f2d20"),
    }

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        # Transparent so the canvas follows the active theme's background.
        self.setStyleSheet("QScrollArea{background:transparent;border:1px solid #2c3e46;}")
        self._host = QWidget()
        self._host.setStyleSheet("background:transparent;")
        self.setWidget(self._host)
        self._grid = QGridLayout(self._host)
        self._grid.setContentsMargins(6, 6, 6, 6)
        self._grid.setHorizontalSpacing(4)
        self._grid.setVerticalSpacing(4)
        self.block_index = 0
        self.chips: list[_CanvasChip] = []
        self.selected_ref = None
        # Compact mode packs cells tightly (no icon/row buttons) for dense grids
        # such as 13x13 push-chart popups; off for normal HUD/popup editing.
        self.compact = False

    def _clear(self) -> None:
        self.chips = []
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def set_block(self, block_index: int, block: dict | None) -> None:
        self._clear()
        self.block_index = block_index
        if not block:
            return
        cols = max(1, int(block.get("cols", 1)))
        rows = max(1, int(block.get("rows", 1)))
        items = []  # (row, col, span, kind, ref, label)
        for s in block.get("stats", []):
            items.append((s.get("row", 0), s.get("col", 0), int(s.get("colspan", 1) or 1),
                          "stat", s, s.get("stat", "") or "(stat)"))
        for t in block.get("texts", []):
            if not (t.get("label", "") or "").strip():
                continue  # empty placeholder cell -> leave blank like PT4
            r, c = t["rowcol"]
            items.append((r, c, int(t.get("colspan", 1) or 1), "text", t, t["label"]))
        for h in block.get("hlines", []):
            r, c = h["rowcol"]
            items.append((r, c, int(h.get("colspan") or cols), "hline", h, "Horz Line"))
        spacing = 1 if self.compact else 4
        self._grid.setHorizontalSpacing(spacing)
        self._grid.setVerticalSpacing(spacing)
        for r, c, span, kind, ref, label in items:
            chip = self._make_chip(kind, label, ref)
            self._grid.addWidget(chip, r, c, 1, max(1, span))
            self.chips.append(chip)
        # Per-row add/remove buttons in a trailing column (PT4 layout). Dense
        # compact grids (push charts) omit them — you edit cells, not rows.
        if not self.compact:
            for r in range(rows):
                self._grid.addWidget(self._row_buttons(r), r, cols)
        for c in range(cols):
            self._grid.setColumnStretch(c, 1)

    def _make_chip(self, kind: str, label: str, ref: dict) -> _CanvasChip:
        letter, icon_col, _chip_bg = self.TYPE.get(kind, self.TYPE["stat"])
        chip = _CanvasChip(kind, ref)
        chip.setStyleSheet(self._chip_qss(kind, selected=False))
        lay = QHBoxLayout(chip)
        chip.clicked.connect(lambda c=chip: self._select(c))
        if self.compact:
            # Dense matrix cell: no icon, small centred text, tight padding.
            lay.setContentsMargins(2, 1, 2, 1)
            lay.setSpacing(0)
            name = QLabel(label)
            name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name.setStyleSheet(
                f"color:#e6f0ee;font-size:8pt;font-weight:700;border:none;background:transparent;"
                f"border-left:3px solid {icon_col};padding-left:3px;",
            )
            name.setMinimumWidth(34)
            lay.addWidget(name)
            return chip
        lay.setContentsMargins(3, 2, 6, 2)
        lay.setSpacing(4)
        icon = QLabel(letter)
        icon.setFixedSize(16, 16)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(f"background:{icon_col};color:white;font-weight:800;border-radius:3px;border:none;")
        name = QLabel(label)
        name.setStyleSheet("color:#e6f0ee;font-weight:600;border:none;background:transparent;")
        lay.addWidget(icon)
        lay.addWidget(name)
        lay.addStretch()
        return chip

    def _chip_qss(self, kind: str, selected: bool) -> str:
        _letter, _icon, bg = self.TYPE.get(kind, self.TYPE["stat"])
        border = "2px solid #19e3a0" if selected else "1px solid #3a4a52"
        return f"_CanvasChip{{background:{bg};border:{border};border-radius:5px;}}"

    _ROW_BTN_QSS = (
        "QPushButton{color:#e6f0ee;background:#2c3e46;border:1px solid #3d5a52;"
        "border-radius:3px;font-weight:800;padding:0;}"
        "QPushButton:hover{background:#37505a;}"
    )

    def _row_buttons(self, row: int) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(2, 0, 0, 0)
        h.setSpacing(2)
        plus = QPushButton("+")
        plus.setFixedSize(22, 22)
        plus.setStyleSheet(self._ROW_BTN_QSS)
        plus.setToolTip("Add an item to this row")
        plus.clicked.connect(lambda _=False, r=row: self.add_to_row.emit(r))
        minus = QPushButton("−")
        minus.setFixedSize(22, 22)
        minus.setStyleSheet(self._ROW_BTN_QSS)
        minus.setToolTip("Remove the last item of this row")
        minus.clicked.connect(lambda _=False, r=row: self.remove_from_row.emit(r))
        h.addWidget(plus)
        h.addWidget(minus)
        return w

    def _select(self, chip: _CanvasChip) -> None:
        self.selected_ref = chip.item_ref
        for c in self.chips:
            c.setStyleSheet(self._chip_qss(c.kind, c is chip))
        self.item_selected.emit((self.block_index, chip.kind, chip.item_ref))

    def select_ref(self, item_ref) -> None:
        """Highlight the chip matching item_ref (e.g. driven from the table)."""
        self.selected_ref = item_ref
        for c in self.chips:
            nested_ref = c.item_ref.get("_popup_stat") if isinstance(c.item_ref, dict) else None
            c.setStyleSheet(self._chip_qss(c.kind, c.item_ref is item_ref or nested_ref is item_ref))


# --- Add/Edit Stat Dialog ---
class BlockPropertiesDialog(QDialog):
    """Edit a HUD panel (block): label, villain position, title/border colours."""

    _POSITIONS = ["", "SB", "BB", "BTN", "CO", "MP", "EP"]
    _COLOR_FIELDS = (("title_bgcolor", "Title background"), ("title_fgcolor", "Title text"), ("bordercolor", "Border"))

    def __init__(self, block: dict, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Block Properties")
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
        self.pos_combo.setToolTip("Show this panel only for a villain in this position (blank = always)")
        form.addRow("Show for position:", self.pos_combo)

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
        from PySide6.QtGui import QColor

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
        return {"label": self.label_input.text(), "position": self.pos_combo.currentText(), **self._colors}


class AddStatDialog(QDialog):
    def __init__(self, stat=None, max_rows=5, max_cols=5, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add/Edit Statistic")
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
        self.setWindowTitle("Export Layout Coordinates")
        self.setMinimumSize(400, 300)

        layout = QVBoxLayout(self)

        info = QLabel(
            "Select the site layout coordinates you want to include in the package.\n"
            "This will let other users position the HUD boxes exactly like yours."
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
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(self.select_all)
        select_none_btn = QPushButton("Select None")
        select_none_btn.clicked.connect(self.select_none)
        btn_layout.addWidget(select_all_btn)
        btn_layout.addWidget(select_none_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # OK/Cancel buttons
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
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
class ModernHudPreferences(QDialog):
    def __init__(self, config, parent=None) -> None:
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
        header_frame.setFrameStyle(QFrame.Shape.StyledPanel)
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
        # Let qt_material manage the style
        self.profile_combo.currentIndexChanged.connect(self.on_profile_selected)
        profile_bar.addWidget(self.profile_combo)

        # Push the action buttons to the right so a short profile name doesn't
        # leave them crowding the combo.
        profile_bar.addStretch()

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

        self.export_profile_btn = QPushButton("📤 Export HUD")
        self.export_profile_btn.setMinimumWidth(120)
        self.export_profile_btn.clicked.connect(self.export_profile)

        self.import_profile_btn = QPushButton("📥 Import HUD")
        self.import_profile_btn.setMinimumWidth(120)
        self.import_profile_btn.clicked.connect(self.import_profile)

        profile_bar.addWidget(self.add_profile_btn)
        profile_bar.addWidget(self.dup_profile_btn)
        profile_bar.addWidget(self.del_profile_btn)
        profile_bar.addWidget(self.export_profile_btn)
        profile_bar.addWidget(self.import_profile_btn)

        header_layout.addLayout(profile_bar)

        # Second row: per-profile HUD display options, kept off the (already
        # crowded) profile/buttons row so they never overlap it.
        hud_options_bar = QHBoxLayout()
        hud_options_bar.setSpacing(10)

        # Positional-panel mode for multi-block HUDs. "all" stacks SB/BB/BU
        # together (an import-driven HUD is one hand behind the live position, so
        # a single positional panel would be stale); "current" shows only the
        # panel matching the last imported position.
        self.positional_mode_label = QLabel("Positional panels:")
        self.positional_mode_label.setProperty("class", "subtitle")
        hud_options_bar.addWidget(self.positional_mode_label)
        self.positional_mode_combo = QComboBox()
        self.positional_mode_combo.addItem("Show all (stacked)", "all")
        self.positional_mode_combo.addItem("Only current position", "current")
        self.positional_mode_combo.setMinimumWidth(180)
        self.positional_mode_combo.currentIndexChanged.connect(self._on_positional_mode_changed)
        hud_options_bar.addWidget(self.positional_mode_combo)

        hud_options_bar.addSpacing(24)

        # Whether the hero's own stat windows are drawn (multi-block HUDs are
        # usually hero-hidden; this exposes the toggle per profile).
        self.show_hero_checkbox = QCheckBox("Show hero HUD")
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

        # Statistics splitter
        stats_splitter = QSplitter(Qt.Orientation.Horizontal)
        stats_splitter.setHandleWidth(8)

        # Left panel: Statistics table
        left_panel = QFrame()
        left_panel.setFrameStyle(QFrame.Shape.StyledPanel)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(15, 15, 15, 15)
        left_layout.setSpacing(10)

        # PT4-style panel (group) management: list + inline Group Properties.
        self._loading_group = False
        self._current_block_index = 0
        # The four property zones live in a horizontal splitter so they never
        # overlap (a QHBoxLayout can collide when min widths exceed the width)
        # and can be resized like PT4.
        group_row = QSplitter(Qt.Orientation.Horizontal)
        group_row.setChildrenCollapsible(False)

        group_list_col = QVBoxLayout()
        group_list_col.setContentsMargins(0, 0, 0, 0)
        glh = QHBoxLayout()
        glabel = QLabel("Panels")
        glabel.setProperty("class", "h2")
        glh.addWidget(glabel)
        glh.addStretch()
        self.group_new_btn = QPushButton("New")
        self.group_new_btn.setFixedHeight(26)
        self.group_new_btn.clicked.connect(self._group_new)
        self.group_del_btn = QPushButton("Delete")
        self.group_del_btn.setFixedHeight(26)
        self.group_del_btn.clicked.connect(self._group_delete)
        glh.addWidget(self.group_new_btn)
        glh.addWidget(self.group_del_btn)
        group_list_col.addLayout(glh)
        self.group_list = QListWidget()
        self.group_list.setMinimumWidth(150)
        self.group_list.setMinimumHeight(140)
        self.group_list.currentRowChanged.connect(self._on_group_selected)
        group_list_col.addWidget(self.group_list)
        _panels_w = QWidget()
        _panels_w.setLayout(group_list_col)
        group_row.addWidget(_panels_w)

        self.group_props_box = QGroupBox("Group Properties")
        self.group_props_box.setMinimumWidth(250)
        gp = QFormLayout(self.group_props_box)
        gp.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        gp.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.gp_name = QLineEdit()
        self.gp_name.editingFinished.connect(self._group_prop_changed)
        gp.addRow("Name:", self.gp_name)
        self.gp_position = QComboBox()
        self.gp_position.addItems(["", "SB", "BB", "BTN", "CO", "MP", "EP"])
        self.gp_position.currentIndexChanged.connect(lambda _i: self._group_prop_changed())
        gp.addRow("Position:", self.gp_position)
        self.gp_titlebg = self._group_color_btn("title_bgcolor")
        gp.addRow("Title bg:", self.gp_titlebg)
        self.gp_titlefg = self._group_color_btn("title_fgcolor")
        gp.addRow("Title fg:", self.gp_titlefg)
        self.gp_border = self._group_color_btn("bordercolor")
        gp.addRow("Border:", self.gp_border)
        self.gp_bg = self._group_color_btn("bgcolor")
        gp.addRow("Panel bg:", self.gp_bg)
        self.gp_opacity = QSlider(Qt.Orientation.Horizontal)
        self.gp_opacity.setRange(0, 255)
        self.gp_opacity.setValue(178)
        self.gp_opacity.valueChanged.connect(lambda _v: self._group_prop_changed())
        gp.addRow("Opacity:", self.gp_opacity)
        group_row.addWidget(self.group_props_box)

        # PT4-style Group Items list + Item Properties / Color Ranges tabs, placed
        # in the SAME top row so the four property zones sit side-by-side (PT4).
        self._loading_item = False
        self._group_item_refs: list = []
        items_col = QVBoxLayout()
        items_col.setContentsMargins(0, 0, 0, 0)
        ilabel = QLabel("Items")
        ilabel.setProperty("class", "h2")
        items_col.addWidget(ilabel)
        self.group_items_list = QListWidget()
        self.group_items_list.setMinimumWidth(150)
        self.group_items_list.setMinimumHeight(140)
        self.group_items_list.currentRowChanged.connect(self._on_group_item_selected)
        items_col.addWidget(self.group_items_list)

        self.item_props_tabs = QTabWidget()
        self.item_props_tabs.setMinimumWidth(250)
        self._item_color_btns = {}
        # --- Item tab ---
        item_tab = QWidget()
        itf = QFormLayout(item_tab)
        itf.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        itf.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.ip_text = QLineEdit()
        self.ip_text.editingFinished.connect(self._item_prop_changed)
        itf.addRow("Text:", self.ip_text)
        self.ip_popup = QLineEdit()
        self.ip_popup.editingFinished.connect(self._item_prop_changed)
        itf.addRow("Popup:", self.ip_popup)
        self.ip_colspan = QSpinBox()
        self.ip_colspan.setRange(1, 12)
        self.ip_colspan.valueChanged.connect(lambda _v: self._item_prop_changed())
        itf.addRow("Span:", self.ip_colspan)
        self.ip_align = QComboBox()
        self.ip_align.addItems(["center", "left", "right"])
        self.ip_align.currentIndexChanged.connect(lambda _i: self._item_prop_changed())
        itf.addRow("Align:", self.ip_align)
        self.ip_fg = self._item_color_btn("fg")
        itf.addRow("Text col:", self.ip_fg)
        self.ip_bg = self._item_color_btn("bg")
        itf.addRow("Cell bg:", self.ip_bg)
        self.item_props_tabs.addTab(item_tab, "Item Properties")
        # --- Color Ranges tab ---
        cr_tab = QWidget()
        crf = QFormLayout(cr_tab)
        crf.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        crf.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.ip_loth = QSpinBox()
        self.ip_loth.setRange(0, 100)
        self.ip_loth.valueChanged.connect(lambda _v: self._item_prop_changed())
        crf.addRow("Lo th:", self.ip_loth)
        self.ip_hith = QSpinBox()
        self.ip_hith.setRange(0, 100)
        self.ip_hith.valueChanged.connect(lambda _v: self._item_prop_changed())
        crf.addRow("Hi th:", self.ip_hith)
        self.ip_locolor = self._item_color_btn("lo")
        crf.addRow("Lo col:", self.ip_locolor)
        self.ip_midcolor = self._item_color_btn("mid")
        crf.addRow("Mid col:", self.ip_midcolor)
        self.ip_hicolor = self._item_color_btn("hi")
        crf.addRow("Hi col:", self.ip_hicolor)
        self.item_props_tabs.addTab(cr_tab, "Color Ranges")
        _items_w = QWidget()
        _items_w.setLayout(items_col)
        group_row.addWidget(_items_w)
        group_row.addWidget(self.item_props_tabs)
        # Lists stay compact; the two property forms absorb the extra width.
        group_row.setStretchFactor(0, 0)
        group_row.setStretchFactor(1, 1)
        group_row.setStretchFactor(2, 0)
        group_row.setStretchFactor(3, 1)
        group_row.setSizes([190, 330, 210, 360])
        left_layout.addWidget(group_row)

        # PT4-style design canvas: shows the SELECTED panel only (box-by-box).
        self.design_label = QLabel("Design")
        self.design_label.setProperty("class", "h2")
        left_layout.addWidget(self.design_label)
        self.design_scroll = QScrollArea()
        self.design_scroll.setWidgetResizable(True)
        self.design_scroll.setMinimumHeight(240)
        self.design_scroll.setStyleSheet("QScrollArea{border:1px solid #2c3e46;background:#1d282e;}")
        self._design_host = QWidget()
        self._design_host.setStyleSheet("background:#1d282e;")
        self._design_layout = QVBoxLayout(self._design_host)
        self._design_layout.setContentsMargins(6, 6, 6, 6)
        self._design_layout.setSpacing(10)
        self.design_scroll.setWidget(self._design_host)
        left_layout.addWidget(self.design_scroll, 2)
        self._design_canvases: list = []

        # Statistics table: kept for selection state + add/edit/remove logic, but
        # hidden in the PT4 layout (the Items list + design canvas replace it).
        self.stat_table = QTableWidget(0, 7)
        self.stat_table.setHorizontalHeaderLabels(["Type", "Row", "Col", "Item", "Span", "Click Action", "Popup"])
        self.stat_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.stat_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.stat_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.stat_table.setAlternatingRowColors(True)
        self.stat_table.hide()
        left_layout.addWidget(self.stat_table)

        # Statistics action buttons
        stat_btn_frame = QFrame()
        stat_btn_layout = QHBoxLayout(stat_btn_frame)
        stat_btn_layout.setContentsMargins(0, 10, 0, 0)

        self.add_stat_btn = QPushButton("Add Stat")
        self.add_stat_btn.setMinimumHeight(35)
        self.add_stat_btn.clicked.connect(self.add_stat)

        self.edit_stat_btn = QPushButton("Edit")
        self.edit_stat_btn.setMinimumHeight(35)
        self.edit_stat_btn.clicked.connect(self.edit_stat)

        self.remove_stat_btn = QPushButton("Remove")
        self.remove_stat_btn.setMinimumHeight(35)
        self.remove_stat_btn.clicked.connect(self.remove_stat)

        self.add_label_btn = QPushButton("Add Label")
        self.add_label_btn.setMinimumHeight(35)
        self.add_label_btn.setToolTip("Add a text label (column/row header or caption) to a panel")
        self.add_label_btn.clicked.connect(self.add_text_label)

        self.add_block_btn = QPushButton("Add Block")
        self.add_block_btn.setMinimumHeight(35)
        self.add_block_btn.setToolTip("Add a new panel (block) to a multi-panel HUD")
        self.add_block_btn.clicked.connect(self.add_block)

        self.block_props_btn = QPushButton("Block Props")
        self.block_props_btn.setMinimumHeight(35)
        self.block_props_btn.setToolTip("Edit the selected panel's title/border colours, position and label")
        self.block_props_btn.clicked.connect(self.edit_block_properties)

        self.add_hline_btn = QPushButton("Add Line")
        self.add_hline_btn.setMinimumHeight(35)
        self.add_hline_btn.setToolTip("Add a horizontal separator line (PT4 'Horz Line') to a panel")
        self.add_hline_btn.clicked.connect(self.add_hline)

        stat_btn_layout.addWidget(self.add_stat_btn)
        stat_btn_layout.addWidget(self.edit_stat_btn)
        stat_btn_layout.addWidget(self.remove_stat_btn)
        stat_btn_layout.addWidget(self.add_label_btn)
        stat_btn_layout.addWidget(self.add_hline_btn)
        stat_btn_layout.addWidget(self.add_block_btn)
        stat_btn_layout.addWidget(self.block_props_btn)
        stat_btn_layout.addStretch()

        left_layout.addWidget(stat_btn_frame)
        # Wrap the editor in a scroll area: a vertical scrollbar appears when the
        # content is taller than the window, and a horizontal one when the window
        # is too narrow for the property zones — instead of cramming/truncating,
        # the editor keeps a comfortable minimum width and scrolls.
        left_panel.setMinimumWidth(1000)
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.Shape.NoFrame)
        left_scroll.setWidget(left_panel)
        stats_splitter.addWidget(left_scroll)

        # Right panel: Visual preview
        right_panel = QFrame()
        right_panel.setFrameStyle(QFrame.Shape.StyledPanel)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(15, 15, 15, 15)
        right_layout.setSpacing(10)

        # Preview header
        preview_label = QLabel("HUD Preview")
        preview_label.setProperty("class", "h2")
        right_layout.addWidget(preview_label)

        # Preview widget, in a scroll area so a large HUD (many stats/columns)
        # scrolls instead of overflowing and overlapping the preview box.
        self.preview = HudPreviewWidget()
        self.preview.setMinimumSize(300, 280)
        preview_scroll = QScrollArea()
        preview_scroll.setWidgetResizable(True)
        preview_scroll.setFrameShape(QFrame.Shape.NoFrame)
        preview_scroll.setWidget(self.preview)
        right_layout.addWidget(preview_scroll)

        # Preview info
        info_label = QLabel(
            "The preview uses the same compact label grid as the in-game HUD.\n"
            "Spacing, font, colors and HUD cell values come from the selected profile.",
        )
        info_label.setProperty("class", "caption")
        info_label.setWordWrap(True)
        right_layout.addWidget(info_label)

        right_layout.addStretch()
        stats_splitter.addWidget(right_panel)

        # Give most of the width to the editor (the four property zones need room
        # so they don't truncate); the preview is secondary. On resize the editor
        # grows faster than the preview.
        stats_splitter.setStretchFactor(0, 3)
        stats_splitter.setStretchFactor(1, 1)
        stats_splitter.setSizes([1180, 420])
        stats_layout.addWidget(stats_splitter)

        # Add stats tab
        self.tabs.addTab(stats_tab, "📊 Statistics")

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

        popup_select_label = QLabel("Select Popup:")
        popup_select_label.setProperty("class", "subtitle")
        popup_select_layout.addWidget(popup_select_label)

        self.popup_combo = QComboBox()
        self.popup_combo.setMinimumWidth(360)
        self.popup_combo.setMinimumHeight(30)
        self.popup_combo.currentIndexChanged.connect(self.on_popup_selected)
        popup_select_layout.addWidget(self.popup_combo)

        popup_select_layout.addSpacing(20)

        # Popup action buttons
        self.add_popup_btn = QPushButton("➕ New Popup")
        self.add_popup_btn.setMinimumWidth(120)
        self.add_popup_btn.setFixedHeight(34)
        self.add_popup_btn.clicked.connect(self.add_popup)

        self.dup_popup_btn = QPushButton("📋 Duplicate")
        self.dup_popup_btn.setMinimumWidth(120)
        self.dup_popup_btn.setFixedHeight(34)
        self.dup_popup_btn.clicked.connect(self.duplicate_popup)

        self.del_popup_btn = QPushButton("🗑️ Delete")
        self.del_popup_btn.setMinimumWidth(120)
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
        left_popup_panel.setMinimumWidth(1000)
        left_popup_layout = QVBoxLayout(left_popup_panel)
        left_popup_layout.setContentsMargins(12, 12, 12, 12)
        left_popup_layout.setSpacing(8)

        popup_top_splitter = QSplitter(Qt.Orientation.Horizontal)
        popup_top_splitter.setChildrenCollapsible(False)
        popup_top_splitter.setMaximumHeight(190)
        popup_top_splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        # Statistics list
        stats_group = QGroupBox("Statistics")
        stats_layout = QVBoxLayout()
        stats_layout.setSpacing(6)

        # Stats buttons at the top
        stats_btn_layout = QHBoxLayout()
        stats_btn_layout.setContentsMargins(0, 8, 0, 0)
        stats_btn_layout.setSpacing(10)

        self.add_popup_stat_btn = QPushButton("➕ Add")
        self.add_popup_stat_btn.setMinimumHeight(34)
        self.add_popup_stat_btn.clicked.connect(self.add_popup_stat)

        self.edit_popup_stat_btn = QPushButton("📝 Edit")
        self.edit_popup_stat_btn.setMinimumHeight(34)
        self.edit_popup_stat_btn.clicked.connect(self.edit_popup_stat)

        self.remove_popup_stat_btn = QPushButton("➖ Remove")
        self.remove_popup_stat_btn.setMinimumHeight(34)
        self.remove_popup_stat_btn.clicked.connect(self.remove_popup_stat)

        self.move_up_btn = QPushButton("↑ Up")
        self.move_up_btn.setMinimumHeight(34)
        self.move_up_btn.clicked.connect(self.move_stat_up)

        self.move_down_btn = QPushButton("↓ Down")
        self.move_down_btn.setMinimumHeight(34)
        self.move_down_btn.clicked.connect(self.move_stat_down)

        # PT4-style design canvas: the popup's stats as a vertical chip stack,
        # synced with the list below and the live preview.
        design_lbl = QLabel("Design")
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

        popup_info_group = QGroupBox("Popup Information")
        popup_info_layout = QGridLayout()
        popup_info_layout.setSpacing(6)
        popup_info_layout.setContentsMargins(8, 8, 8, 8)

        popup_info_layout.addWidget(QLabel("Name:"), 0, 0)
        self.popup_name_edit = QLineEdit()
        self.popup_name_edit.setReadOnly(True)
        self.popup_name_edit.setMinimumHeight(28)
        popup_info_layout.addWidget(self.popup_name_edit, 0, 1)

        popup_info_layout.addWidget(QLabel("Class:"), 1, 0)
        self.popup_class_combo = QComboBox()
        self.popup_class_combo.addItems(["default", "Submenu", "Multicol", "RangeChartPopup", "BlockPopup"])
        self.popup_class_combo.setMinimumHeight(28)
        self.popup_class_combo.currentTextChanged.connect(self.on_popup_class_changed)
        popup_info_layout.addWidget(self.popup_class_combo, 1, 1)

        popup_info_group.setLayout(popup_info_layout)
        popup_info_group.setMinimumWidth(300)
        popup_top_splitter.addWidget(popup_info_group)

        # PT4-style Item Properties for the selected popup item/cell.
        self._popup_group = None          # loaded BlockPopup group (editable cells)
        self._popup_item_cell = None      # the selected cell dict
        self.pi_props_box = QGroupBox("Item Properties")
        self.pi_props_box.setMinimumWidth(360)
        pif = QFormLayout(self.pi_props_box)
        pif.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        pif.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        pif.setVerticalSpacing(5)
        pif.setContentsMargins(8, 8, 8, 8)
        self.pi_text = QLineEdit()
        self.pi_text.editingFinished.connect(self._popup_item_changed)
        pif.addRow("Text / Stat:", self.pi_text)
        self.pi_submenu = QLineEdit()
        self.pi_submenu.editingFinished.connect(self._popup_item_changed)
        pif.addRow("Submenu:", self.pi_submenu)
        self.pi_type = QLabel("—")
        pif.addRow("Type:", self.pi_type)
        self.pi_pos = QLabel("—")
        pif.addRow("Position:", self.pi_pos)
        self._popup_item_color_btns = {}
        self.pi_fg = self._popup_item_color_btn("fg")
        pif.addRow("Foreground:", self.pi_fg)
        self.pi_bg = self._popup_item_color_btn("bg")
        pif.addRow("Background:", self.pi_bg)
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
        preview_label = QLabel("Popup Preview")
        preview_label.setProperty("class", "h3")
        right_popup_layout.addWidget(preview_label)

        self.popup_preview = PopupPreviewWidget()
        self.popup_preview.setMinimumHeight(220)
        self.popup_preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
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
        self.tabs.addTab(popup_tab, "💬 Popup Windows")

        # Tab 3: General Settings
        general_tab = QWidget()
        general_layout = QVBoxLayout(general_tab)
        general_layout.setContentsMargins(30, 30, 30, 30)
        general_layout.setSpacing(20)

        # Title
        general_title = QLabel("General HUD and Profiling Settings")
        general_title.setProperty("class", "h2")
        general_layout.addWidget(general_title)

        # Form / Group Container
        general_card = QFrame()
        general_card.setFrameStyle(QFrame.Shape.StyledPanel)
        general_card_layout = QVBoxLayout(general_card)
        general_card_layout.setContentsMargins(25, 25, 25, 25)
        general_card_layout.setSpacing(20)

        # 1. Profiling checkbox
        self.profiling_checkbox = QCheckBox("Enable Player Profiling (Categorization)")
        self.profiling_checkbox.setToolTip("Enable auto-classification of players into Nit, Calling Station, Fish, Maniac, LAG, Reg, TAG.")
        general_card_layout.addWidget(self.profiling_checkbox)

        # 2. Profile in name checkbox
        self.profile_in_name_checkbox = QCheckBox("Show profile emoji and color code directly on player name labels")
        self.profile_in_name_checkbox.setToolTip("Append the profile emoji (e.g. 🐟, 🐌, 🎯) and color the player's name in the HUD.")
        general_card_layout.addWidget(self.profile_in_name_checkbox)

        # 3. Min hands setting (SpinBox)
        hands_layout = QHBoxLayout()
        hands_label = QLabel("Minimum hands required for profiling:")
        hands_label.setToolTip("The minimum number of hands tracked on an opponent before profiling is computed.")
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
        self.tabs.addTab(general_tab, "⚙️ General Settings")

        # Add tabs to main layout
        main_layout.addWidget(self.tabs)

        # Bottom action bar
        bottom_frame = QFrame()
        bottom_frame.setFrameStyle(QFrame.Shape.StyledPanel)
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

        # Track changes
        self.original_profiles = self._deep_copy_profiles(self.hud_profiles)
        self.original_popups = self._deep_copy_popups(self.popup_windows)

        # Update status
        self.update_status()

    def update_status(self) -> None:
        """Update status label with current profile info."""
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
        """Create a deep copy of profiles for change detection."""
        import copy

        return copy.deepcopy(profiles)

    def _deep_copy_popups(self, popups):
        """Create a deep copy of popup windows for change detection."""
        import copy

        return copy.deepcopy(popups)

    def has_unsaved_changes(self):
        """Check if there are unsaved changes."""
        profiling_changed = (
            self.profiling_checkbox.isChecked() != self.original_player_profiling or
            self.profile_in_name_checkbox.isChecked() != self.original_profile_in_name or
            self.profile_min_hands_spin.value() != self.original_profile_min_hands
        )
        return self.hud_profiles != self.original_profiles or self.popup_windows != self.original_popups or profiling_changed

    def _hud_preview_params(self) -> dict[str, str]:
        ui = getattr(self.config, "ui", None)
        return {
            "bgcolor": getattr(ui, "hudbgcolor", "") or getattr(ui, "bgcolor", "#000000"),
            "fgcolor": getattr(ui, "hudfgcolor", "") or getattr(ui, "fgcolor", "#ffffff"),
            "font": getattr(ui, "font", "Sans") or "Sans",
            "font_size": getattr(ui, "font_size", "8") or "8",
        }

    def closeEvent(self, event) -> None:
        """Handle window close event."""
        if self.has_unsaved_changes():
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes. Do you want to save before closing?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            )

            if reply == QMessageBox.Save:
                self.save_changes()
                if self.result() == QDialog.DialogCode.Accepted:
                    event.accept()
                else:
                    event.ignore()
            elif reply == QMessageBox.Discard:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

    @staticmethod
    def _stat_to_dict(stat, row: int, col: int, panel: str = "") -> dict:
        """Convert a Configuration.Stat into the editor's flat stat dict."""
        d = {
            "row": row,
            "col": col,
            "stat": getattr(stat, "stat_name", "unknown"),
            "click": getattr(stat, "click", ""),
            "popup": getattr(stat, "popup", ""),
        }
        if panel:
            d["panel"] = panel
        for attr in ("stat_loth", "stat_hith", "stat_locolor", "stat_hicolor",
                     "stat_midcolor", "hudcolor", "hudbgcolor", "hudprefix", "hudsuffix", "tip"):
            if hasattr(stat, attr):
                d[attr] = getattr(stat, attr, "")
        # PT4 cell layout (kept only when non-default to avoid noisy XML).
        if getattr(stat, "colspan", 1) and int(getattr(stat, "colspan", 1)) != 1:
            d["colspan"] = int(stat.colspan)
        if getattr(stat, "align", "") and stat.align != "center":
            d["align"] = stat.align
        return d

    def _profile_from_stat_set(self, stat_set) -> dict:
        """Convert a Configuration.Stat_sets object into the editor profile."""
        blocks = getattr(stat_set, "blocks", None)
        if blocks and len(blocks) > 1:
            stats = []
            block_meta = []
            row_offset = 0
            total_cols = 0
            for blk in blocks:
                bstats = []
                for pos, stat in blk.stats.items():
                    stats.append(self._stat_to_dict(stat, pos[0] + row_offset, pos[1], blk.label))
                    bstats.append(self._stat_to_dict(stat, pos[0], pos[1], blk.label))
                block_meta.append({
                    "label": blk.label,
                    "id": getattr(blk, "id", ""),
                    "scope": getattr(blk, "scope", "player"),
                    "audience": getattr(blk, "audience", "everyone"),
                    "position": getattr(blk, "position", ""),
                    "rows": blk.rows,
                    "cols": blk.cols,
                    "title_bgcolor": getattr(blk, "title_bgcolor", ""),
                    "title_fgcolor": getattr(blk, "title_fgcolor", ""),
                    "bordercolor": getattr(blk, "bordercolor", ""),
                    "x": getattr(blk, "x", 0),
                    "y": getattr(blk, "y", 0),
                    "stats": bstats,
                    # PT4-style text-label items (column/row headers, captions).
                    "texts": [dict(t) for t in getattr(blk, "texts", [])],
                    # PT4 "Horz Line" separators.
                    "hlines": [dict(h) for h in getattr(blk, "hlines", [])],
                })
                row_offset += blk.rows
                total_cols = max(total_cols, blk.cols)
            return {
                "rows": max(row_offset, 1),
                "cols": max(total_cols, 1),
                "xpad": getattr(stat_set, "xpad", 0),
                "ypad": getattr(stat_set, "ypad", 0),
                "multiblock": True,
                # "all" = show every position panel stacked; "current" = only the
                # panel matching the last imported position. Editable in the UI.
                "positional_mode": getattr(stat_set, "positional_mode", "all") or "all",
                # "" (default), "true" or "false": whether the hero's own stat
                # windows are drawn. Multi-block HUDs default to hidden.
                "show_hero_hud": getattr(stat_set, "show_hero_hud", "") or "",
                "blocks": block_meta,
                "stats": stats,
            }

        stats = []
        if hasattr(stat_set, "stats"):
            for pos, stat in stat_set.stats.items():
                stats.append(self._stat_to_dict(stat, pos[0], pos[1], ""))

        if hasattr(stat_set, "rows") and hasattr(stat_set, "cols"):
            return {
                "rows": stat_set.rows,
                "cols": stat_set.cols,
                "xpad": getattr(stat_set, "xpad", 0),
                "ypad": getattr(stat_set, "ypad", 0),
                "stats": stats,
            }
        return stats

    def load_profiles(self) -> None:
        # Try to load HUD profiles from config (from HUD_config.xml)
        self.hud_profiles = None
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
                popup_data = {"name": popup_name, "class": popup_obj.pu_class, "stats": [],
                              "source": _params.get("source", ""), "group": _params.get("group", "")}

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
        self._loading_popup = False

        # Update stats list
        self.popup_stats_list.clear()
        for stat in popup_data.get("stats", []):
            stat_text = stat["stat_name"]
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
            self.pi_type.setText("—")
            self.pi_pos.setText("—")
            self._style_color_btn(self.pi_fg, "")
            self._style_color_btn(self.pi_bg, "")
            self.pi_fg.setEnabled(True)
            self.pi_bg.setEnabled(True)
        if popup_data.get("class") == "BlockPopup" and popup_data.get("source") and popup_data.get("group"):
            from fpdb_3_legacy.BlockPopup import load_block_popup

            try:
                group = load_block_popup(popup_data["source"], popup_data["group"])
            except Exception:
                group = None
            if group:
                # Keep the loaded group + its source so Item Properties edits the
                # real cells and can be saved back to the JSON sidecar.
                self._popup_group = group
                self._popup_group_source = popup_data["source"]
                block = {"label": "", "rows": max(1, int(group.get("rows", 1))),
                         "cols": max(1, int(group.get("cols", 1))), "hlines": [],
                         "stats": [{"row": c["row"], "col": c["col"], "stat": c["text"],
                                    "hudcolor": c.get("fg", ""), "hudbgcolor": c.get("bg", "")}
                                   for c in group.get("cells", []) if c["kind"] == "stat"],
                         "texts": [{"rowcol": (c["row"], c["col"]), "label": c["text"], "colspan": 1,
                                    "align": "center", "fgcolor": c.get("fg", ""), "bgcolor": c.get("bg", "")}
                                   for c in group.get("cells", []) if c["kind"] == "text"]}
                # Keep the imported grid editor aligned with the Statistics tab:
                # full chips plus per-row +/- controls, even for dense PT4 grids.
                self.popup_canvas.compact = False
                self.popup_canvas.set_block(0, block)
                return

        stats = popup_data.get("stats", [])

        def _label(s):
            name = s.get("stat_name", "")
            return f"{name}  →  {s['submenu']}" if s.get("submenu") else name

        block = {"label": "", "rows": max(1, len(stats)), "cols": 1,
                 "stats": [{"row": i, "col": 0, "stat": _label(s), "_popup_stat": s}
                           for i, s in enumerate(stats)],
                 "texts": [], "hlines": []}
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
            cell = next((c for c in self._popup_group.get("cells", [])
                         if c["row"] == row and c["col"] == col), None)
            self._load_popup_item(cell)
            return
        stat = ref.get("_popup_stat") if isinstance(ref, dict) else None
        if stat is not None:
            self._load_popup_stat_item(stat, row)

    # --- popup Item Properties ------------------------------------------
    def _popup_item_color_btn(self, role: str) -> QPushButton:
        btn = QPushButton("(none)")
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
        self.pi_props_box.setEnabled(True)
        self.pi_text.setText(str(cell.get("text", "")))
        self.pi_submenu.clear()
        self.pi_submenu.setEnabled(False)
        self.pi_type.setText("Stat" if cell.get("kind") == "stat" else "Text")
        self.pi_pos.setText(f"row {cell.get('row', 0)}, col {cell.get('col', 0)}")
        self.pi_fg.setEnabled(True)
        self.pi_bg.setEnabled(True)
        self._style_color_btn(self.pi_fg, cell.get("fg", ""))
        self._style_color_btn(self.pi_bg, cell.get("bg", ""))

    def _load_popup_stat_item(self, stat: dict, row: int | None) -> None:
        self._popup_item_cell = stat
        self._popup_item_mode = "stat"
        self.pi_props_box.setEnabled(True)
        self.pi_text.setText(str(stat.get("stat_name", "")))
        self.pi_submenu.setEnabled(True)
        self.pi_submenu.setText(str(stat.get("submenu", "")))
        self.pi_type.setText("Stat")
        self.pi_pos.setText(f"row {row}, col 0" if row is not None else "row —, col 0")
        self.pi_fg.setEnabled(False)
        self.pi_bg.setEnabled(False)
        self._style_color_btn(self.pi_fg, "")
        self._style_color_btn(self.pi_bg, "")

    def _popup_item_changed(self) -> None:
        cell = self._popup_item_cell
        if cell is None:
            return
        if getattr(self, "_popup_item_mode", None) == "stat":
            cell["stat_name"] = self.pi_text.text()
            cell["submenu"] = self.pi_submenu.text()
            self._after_popup_stat_edit()
        else:
            cell["text"] = self.pi_text.text()
            self._after_popup_item_edit()

    def _pick_popup_item_color(self, role: str) -> None:
        from PySide6.QtGui import QColor

        cell = self._popup_item_cell
        if cell is None or getattr(self, "_popup_item_mode", None) == "stat":
            return
        key = "fg" if role == "fg" else "bg"
        current = cell.get(key, "")
        col = QColorDialog.getColor(QColor(current) if current else QColor("#ffffff"), self, "Pick colour")
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

    def update_popup_preview(self) -> None:
        """Update the popup preview display."""
        if self.popup_combo.currentIndex() < 0:
            return

        popup_name = self.popup_combo.currentText()
        popup_data = self.popup_windows.get(popup_name, {})
        popup_class = popup_data.get("class", "default")
        stats = popup_data.get("stats", [])
        source = popup_data.get("source", "")
        group = popup_data.get("group", "")
        self.popup_preview.set_popup(popup_name, popup_class, stats, source, group)

    def _on_positional_mode_changed(self, _index: int) -> None:
        """Store the chosen positional-panel mode on the current profile."""
        name = self.profile_combo.currentText()
        profile = self.hud_profiles.get(name) if self.hud_profiles else None
        if isinstance(profile, dict):
            profile["positional_mode"] = self.positional_mode_combo.currentData() or "all"

    def _on_show_hero_changed(self, checked: bool) -> None:
        """Store the hero-HUD visibility on the current profile."""
        name = self.profile_combo.currentText()
        profile = self.hud_profiles.get(name) if self.hud_profiles else None
        if isinstance(profile, dict):
            profile["show_hero_hud"] = "true" if checked else "false"

    def on_profile_selected(self, index) -> None:
        if index < 0 or index >= self.profile_combo.count():
            self.stat_table.setRowCount(0)
            self.preview.set_stats([])
            self.update_status()
            return
        name = self.profile_combo.currentText()
        profile = self.hud_profiles.get(name, {})

        # Reflect this profile's positional-panel mode in the combo (multi-block
        # only). Block the signal so setting it here doesn't mark a fake edit.
        # Guarded: some code paths build a bare dialog without this control.
        if getattr(self, "positional_mode_combo", None) is not None:
            is_multiblock = isinstance(profile, dict) and profile.get("multiblock")
            self.positional_mode_combo.setEnabled(bool(is_multiblock))
            self.positional_mode_label.setEnabled(bool(is_multiblock))
            mode = profile.get("positional_mode", "all") if isinstance(profile, dict) else "all"
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
                show_hero = not (isinstance(profile, dict) and profile.get("multiblock"))
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

        # Update grid size
        self.preview.set_hud_params(xpad=xpad, ypad=ypad, **self._hud_preview_params())
        self.preview.set_grid(rows, cols)

        # Build the table rows: stats plus PT4-style text-label items (column/row
        # headers, captions). For multi-panel profiles the texts live per block
        # with local positions, so offset them to the same stacked grid as stats.
        # self._row_items maps each table row -> (block_index|None, kind, ref dict)
        # so add/edit/remove operate on the actual block item (block-aware), which
        # is what gets saved for multi-panel profiles.
        entries = []  # (gr, gc, display_dict, block_index, kind, ref)
        blocks = profile.get("blocks") if isinstance(profile, dict) else None
        if blocks:
            row_offset = 0
            for bi, blk in enumerate(blocks):
                for s in blk.get("stats", []):
                    entries.append((s.get("row", 0) + row_offset, s.get("col", 0), s, bi, "stat", s))
                for t in blk.get("texts", []):
                    disp = {"row": t["rowcol"][0] + row_offset, "col": t["rowcol"][1],
                            "stat": f"🔤 {t['label']}" if t["label"] else "🔤 (label)", "is_text": True}
                    entries.append((t["rowcol"][0] + row_offset, t["rowcol"][1], disp, bi, "text", t))
                for h in blk.get("hlines", []):
                    disp = {"row": h["rowcol"][0] + row_offset, "col": h["rowcol"][1],
                            "stat": "──── (line)", "is_text": True}
                    entries.append((h["rowcol"][0] + row_offset, h["rowcol"][1], disp, bi, "hline", h))
                row_offset += blk.get("rows", 1)
            entries.sort(key=lambda x: (x[0], x[1]))
        else:
            entries = [(s.get("row", 0), s.get("col", 0), s, None, "stat", s) for s in stats]
        table_rows = [(gr, gc, disp) for gr, gc, disp, _bi, _k, _r in entries]
        self._row_items = [(bi, kind, ref) for _gr, _gc, _d, bi, kind, ref in entries]

        # Update table
        row_items = getattr(self, "_row_items", [])
        self.stat_table.setRowCount(len(table_rows))
        for i, (_r, _c, stat) in enumerate(table_rows):
            kind = row_items[i][1] if i < len(row_items) else "stat"
            ref = row_items[i][2] if i < len(row_items) else stat

            type_item = QTableWidgetItem({"text": "Label", "hline": "Line"}.get(kind, "Stat"))
            type_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.stat_table.setItem(i, 0, type_item)

            row_item = QTableWidgetItem(str(stat["row"]))
            row_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.stat_table.setItem(i, 1, row_item)

            col_item = QTableWidgetItem(str(stat["col"]))
            col_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.stat_table.setItem(i, 2, col_item)

            stat_item = QTableWidgetItem(stat["stat"])
            if stat.get("is_text"):
                stat_item.setToolTip("Text label (header / caption) — not a stat")
            self.stat_table.setItem(i, 3, stat_item)

            span_item = QTableWidgetItem(str(int(ref.get("colspan", 1) or 1)))
            span_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.stat_table.setItem(i, 4, span_item)

            click_item = QTableWidgetItem(stat.get("click", ""))
            self.stat_table.setItem(i, 5, click_item)

            popup_item = QTableWidgetItem(stat.get("popup", ""))
            self.stat_table.setItem(i, 6, popup_item)

            if stat.get("stat_locolor") or stat.get("stat_hicolor"):
                stat_item.setToolTip(
                    f"Colors configured: Low={stat.get('stat_locolor', 'none')}, "
                    f"High={stat.get('stat_hicolor', 'none')}",
                )

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

    def _rebuild_design_canvas(self, profile) -> None:
        """Render the design canvas for the *currently selected* panel only.

        Mirrors PT4: clicking a panel in the Panels list shows that panel's grid
        on the canvas (box-by-box), not every panel stacked. The live preview
        (right) still shows the whole HUD.
        """
        if not hasattr(self, "_design_layout"):
            return
        # Clear previous canvas. Detach AND delete so an old canvas never lingers
        # as a stray top-level window (setParent(None) alone leaves it floating).
        self._design_canvases = []
        while self._design_layout.count():
            item = self._design_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        blocks = profile.get("blocks") if isinstance(profile, dict) else None
        if blocks:
            bi = self._current_block_index if 0 <= self._current_block_index < len(blocks) else 0
            block = blocks[bi]
            canvas_index = bi
        else:
            block = {"label": "", "rows": profile.get("rows", 1) if isinstance(profile, dict) else 1,
                     "cols": profile.get("cols", 1) if isinstance(profile, dict) else 1,
                     "stats": profile.get("stats", []) if isinstance(profile, dict) else profile,
                     "texts": [], "hlines": []}
            canvas_index = 0
        # Keep the section header in sync with the selected panel.
        if hasattr(self, "design_label"):
            label = block.get("label", "")
            self.design_label.setText(f"Design — {label}" if label else "Design")
        canvas = HudDesignCanvas()
        canvas.set_block(canvas_index, block)
        canvas.item_selected.connect(self._on_canvas_item_selected)
        canvas.add_to_row.connect(lambda row, b=canvas_index: self._canvas_add_item(b, row))
        canvas.remove_from_row.connect(lambda row, b=canvas_index: self._canvas_remove_item(b, row))
        self._design_layout.addWidget(canvas)
        self._design_canvases.append(canvas)
        self._design_layout.addStretch()

    def _on_canvas_item_selected(self, payload) -> None:
        """A chip was clicked -> select the matching row in the stat table."""
        _bi, _kind, ref = payload
        items = getattr(self, "_row_items", [])
        for row, (_b, _k, r) in enumerate(items):
            if r is ref:
                self.stat_table.setCurrentCell(row, 0)
                break

    def _canvas_add_item(self, block_index, row) -> None:
        """+ on a canvas row: add a stat into that block's row (next free col)."""
        name, profile = self._current_profile()
        if profile is None:
            return
        container = self._item_container(profile, block_index)
        cols = max(1, int(container.get("cols", 4)))
        used = {c for (r, c) in
                ([(s.get("row", 0), s.get("col", 0)) for s in container.get("stats", [])]
                 + [tuple(t["rowcol"]) for t in container.get("texts", [])]
                 + [tuple(h["rowcol"]) for h in container.get("hlines", [])]) if r == row}
        col = next((c for c in range(cols) if c not in used), cols - 1)
        dlg = AddStatDialog(max_rows=max(cols, row + 1), max_cols=cols, parent=self)
        dlg.row_input.setCurrentText(str(row))
        dlg.col_input.setCurrentText(str(col))
        if dlg.exec():
            stat = dlg.get_stat()
            container.setdefault("stats", []).append(stat)
            container["rows"] = max(int(container.get("rows", 1)), int(stat["row"]) + 1)
            container["cols"] = max(int(container.get("cols", 1)), int(stat["col"]) + 1)
            self.on_profile_selected(self.profile_combo.currentIndex())

    def _canvas_remove_item(self, block_index, row) -> None:
        """− on a canvas row: remove the right-most item of that row."""
        name, profile = self._current_profile()
        if profile is None:
            return
        container = self._item_container(profile, block_index)
        candidates = []
        for key in ("stats", "texts", "hlines"):
            for it in container.get(key, []):
                r, c = (it.get("row", 0), it.get("col", 0)) if key == "stats" else it["rowcol"]
                if r == row:
                    candidates.append((c, key, it))
        if not candidates:
            return
        _c, key, victim = max(candidates, key=lambda x: x[0])
        container[key].remove(victim)
        self.on_profile_selected(self.profile_combo.currentIndex())

    # --- PT4-style group (panel) list + Group Properties -----------------
    def _group_color_btn(self, attr: str) -> QPushButton:
        btn = QPushButton("(none)")
        btn.setFixedHeight(24)
        btn.clicked.connect(lambda _=False, a=attr: self._pick_group_color(a))
        if not hasattr(self, "_group_color_btns"):
            self._group_color_btns = {}
        self._group_color_btns[attr] = btn
        return btn

    @staticmethod
    def _style_color_btn(btn: QPushButton, colour: str) -> None:
        btn.setText(colour or "(none)")
        btn.setStyleSheet(f"background:{colour};" if colour else "")

    @staticmethod
    def _rgb_of(colour: str) -> tuple[int, int, int]:
        c = (colour or "").strip()
        if c.startswith("rgba") or c.startswith("rgb"):
            nums = [int(float(x)) for x in c[c.find("(") + 1:c.find(")")].split(",")[:3]]
            if len(nums) == 3:
                return tuple(nums)  # type: ignore[return-value]
        if c.startswith("#") and len(c) >= 7:
            return int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)
        return 0, 0, 0

    @staticmethod
    def _opacity_of(colour: str):
        c = (colour or "").strip()
        if c.startswith("rgba"):
            parts = c[c.find("(") + 1:c.find(")")].split(",")
            if len(parts) == 4:
                try:
                    return int(float(parts[3]))
                except ValueError:
                    return None
        return None

    def _populate_group_list(self, profile) -> None:
        self._loading_group = True
        self.group_list.clear()
        blocks = profile.get("blocks") if isinstance(profile, dict) else None
        if blocks:
            for b in blocks:
                self.group_list.addItem(b.get("label") or "(unnamed)")
        else:
            self.group_list.addItem("(single grid)")
        count = self.group_list.count()
        bi = self._current_block_index if 0 <= self._current_block_index < count else 0
        self.group_list.setCurrentRow(bi)
        self._loading_group = False
        self._on_group_selected(bi)

    def _on_group_selected(self, row) -> None:
        if row is None or row < 0:
            self.group_props_box.setEnabled(False)
            return
        self._current_block_index = row
        _name, profile = self._current_profile()
        blocks = profile.get("blocks") if isinstance(profile, dict) else None
        if blocks and row < len(blocks):
            self.group_props_box.setEnabled(True)
            self._load_group_props(blocks[row])
            self._populate_group_items(blocks[row])
        else:
            self.group_props_box.setEnabled(False)
            flat = {"stats": profile.get("stats", []) if isinstance(profile, dict) else [],
                    "texts": [], "hlines": []}
            self._populate_group_items(flat)
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
        from PySide6.QtGui import QColor

        _bi, block = self._selected_block()
        if block is None:
            return
        initial = QColor(*self._rgb_of(block.get(attr, "")))
        col = QColorDialog.getColor(initial, self, "Pick colour")
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
        r, g, b = self._rgb_of(block.get("bgcolor", ""))
        block["bgcolor"] = f"rgba({r}, {g}, {b}, {self.gp_opacity.value()})"
        self._refresh_after_group_edit()

    def _refresh_after_group_edit(self) -> None:
        """Light refresh after editing a group: list label + canvas + preview,
        without rebuilding the table or resetting the group selection."""
        _name, profile = self._current_profile()
        item = self.group_list.currentItem()
        if item is not None:
            item.setText(self.gp_name.text() or "(unnamed)")
        try:
            self._rebuild_design_canvas(profile)
        except Exception:
            log.exception("design canvas refresh failed")
        self._preview_selected_block()

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
            QMessageBox.information(self, "Delete Panel", "A profile needs at least one panel.")
            return
        del blocks[bi]
        self._current_block_index = max(0, bi - 1)
        self.on_profile_selected(self.profile_combo.currentIndex())

    # --- PT4-style Group Items list + Item Properties --------------------
    def _item_color_btn(self, role: str) -> QPushButton:
        btn = QPushButton("(none)")
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
            return {"fg": "hudcolor", "bg": "hudbgcolor", "lo": "stat_locolor",
                    "mid": "stat_midcolor", "hi": "stat_hicolor"}.get(role)
        if kind == "text":
            return {"fg": "fgcolor", "bg": "bgcolor"}.get(role)
        if kind == "hline":
            return {"bg": "color"}.get(role)
        return None

    def _populate_group_items(self, block) -> None:
        if not hasattr(self, "group_items_list"):
            return
        self._loading_item = True
        self.group_items_list.clear()
        self._group_item_refs = []
        rows = []
        for s in (block or {}).get("stats", []):
            rows.append((s.get("row", 0), s.get("col", 0), "stat", s, f"Stat: {s.get('stat', '')}"))
        for t in (block or {}).get("texts", []):
            rows.append((t["rowcol"][0], t["rowcol"][1], "text", t, f"Text: {t.get('label', '') or '(label)'}"))
        for h in (block or {}).get("hlines", []):
            rows.append((h["rowcol"][0], h["rowcol"][1], "hline", h, "Horz Line"))
        rows.sort(key=lambda x: (x[0], x[1]))
        for _r, _c, kind, ref, label in rows:
            self.group_items_list.addItem(label)
            self._group_item_refs.append((kind, ref))
        self._loading_item = False
        if self._group_item_refs:
            self.group_items_list.setCurrentRow(0)
        else:
            self._clear_item_props()

    def _current_item(self):
        row = self.group_items_list.currentRow()
        if 0 <= row < len(self._group_item_refs):
            return self._group_item_refs[row]
        return None, None

    def _on_group_item_selected(self, row) -> None:
        if row is None or not (0 <= row < len(self._group_item_refs)):
            return
        kind, ref = self._group_item_refs[row]
        self._load_item_props(kind, ref)
        for cv in getattr(self, "_design_canvases", []):
            cv.select_ref(ref)
        for trow, (_b, _k, r) in enumerate(getattr(self, "_row_items", [])):
            if r is ref:
                self.stat_table.setCurrentCell(trow, 0)
                break

    def _clear_item_props(self) -> None:
        self._loading_item = True
        self.ip_text.clear()
        self.ip_popup.clear()
        for btn in getattr(self, "_item_color_btns", {}).values():
            self._style_color_btn(btn, "")
        self._loading_item = False

    def _load_item_props(self, kind: str, ref: dict) -> None:
        self._loading_item = True
        for w in (self.ip_text, self.ip_popup, self.ip_align, self.ip_colspan, self.ip_fg, self.ip_bg):
            w.setEnabled(True)
        # Keep the Color Ranges tab itself clickable; only its controls are
        # stat-specific (disabled for text/line items, which have no thresholds).
        is_stat = kind == "stat"
        self.item_props_tabs.setTabEnabled(1, True)
        for w in (self.ip_loth, self.ip_hith, self.ip_locolor, self.ip_midcolor, self.ip_hicolor):
            w.setEnabled(is_stat)
        if not is_stat:
            for v in (self.ip_loth, self.ip_hith):
                v.setValue(0)
            for b in (self.ip_locolor, self.ip_midcolor, self.ip_hicolor):
                self._style_color_btn(b, "")
        if kind == "stat":
            self.ip_text.setText(ref.get("stat", ""))
            self.ip_popup.setText(ref.get("popup", ""))
            self.ip_colspan.setValue(int(ref.get("colspan", 1) or 1))
            self._set_combo(self.ip_align, ref.get("align", "center"))
            self._style_color_btn(self.ip_fg, ref.get("hudcolor", ""))
            self._style_color_btn(self.ip_bg, ref.get("hudbgcolor", ""))
            self.ip_loth.setValue(int(float(ref.get("stat_loth") or 0)))
            self.ip_hith.setValue(int(float(ref.get("stat_hith") or 0)))
            self._style_color_btn(self.ip_locolor, ref.get("stat_locolor", ""))
            self._style_color_btn(self.ip_midcolor, ref.get("stat_midcolor", ""))
            self._style_color_btn(self.ip_hicolor, ref.get("stat_hicolor", ""))
        elif kind == "text":
            self.ip_text.setText(ref.get("label", ""))
            self.ip_popup.setEnabled(False)
            self.ip_colspan.setValue(int(ref.get("colspan", 1) or 1))
            self._set_combo(self.ip_align, ref.get("align", "center"))
            self._style_color_btn(self.ip_fg, ref.get("fgcolor", ""))
            self._style_color_btn(self.ip_bg, ref.get("bgcolor", ""))
        else:  # hline
            self.ip_text.setText("Horz Line")
            self.ip_text.setEnabled(False)
            self.ip_popup.setEnabled(False)
            self.ip_align.setEnabled(False)
            self.ip_colspan.setValue(max(1, int(ref.get("colspan", 0) or 1)))
            self._style_color_btn(self.ip_fg, "")
            self._style_color_btn(self.ip_bg, ref.get("color", ""))
        self._loading_item = False

    def _item_prop_changed(self) -> None:
        if self._loading_item:
            return
        kind, ref = self._current_item()
        if ref is None:
            return
        if kind == "stat":
            ref["stat"] = self.ip_text.text()
            ref["popup"] = self.ip_popup.text()
            ref["colspan"] = self.ip_colspan.value()
            ref["align"] = self.ip_align.currentText()
            ref["stat_loth"] = str(self.ip_loth.value()) if self.ip_loth.value() else ""
            ref["stat_hith"] = str(self.ip_hith.value()) if self.ip_hith.value() else ""
        elif kind == "text":
            ref["label"] = self.ip_text.text()
            ref["colspan"] = self.ip_colspan.value()
            ref["align"] = self.ip_align.currentText()
        else:  # hline
            ref["colspan"] = self.ip_colspan.value()
        item = self.group_items_list.currentItem()
        if item is not None:
            if kind == "stat":
                item.setText(f"Stat: {ref.get('stat', '')}")
            elif kind == "text":
                item.setText(f"Text: {ref.get('label', '') or '(label)'}")
        self._refresh_after_group_edit()

    def _pick_item_color(self, role: str) -> None:
        from PySide6.QtGui import QColor

        kind, ref = self._current_item()
        if ref is None:
            return
        key = self._item_color_key(kind, role)
        if key is None:
            return
        current = ref.get(key, "")
        col = QColorDialog.getColor(QColor(current) if current else QColor("#ffffff"), self, "Pick colour")
        if not col.isValid():
            return
        ref[key] = col.name()
        self._style_color_btn(self._item_color_btns[role], col.name())
        self._refresh_after_group_edit()

    def add_profile(self) -> None:
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

        if dialog.exec() == QDialog.DialogCode.Accepted:
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

    def duplicate_profile(self) -> None:
        if self.profile_combo.currentIndex() < 0:
            return
        name = self.profile_combo.currentText()
        from PySide6.QtWidgets import QInputDialog

        new_name, ok = QInputDialog.getText(self, "Duplicate Profile", "New profile name:")
        if ok and new_name and new_name not in self.hud_profiles:
            import copy

            self.hud_profiles[new_name] = copy.deepcopy(self.hud_profiles[name])
            self.profile_combo.addItem(new_name)
            self.profile_combo.setCurrentIndex(self.profile_combo.count() - 1)

    def delete_profile(self) -> None:
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

        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export HUD Profile",
            os.path.expanduser(f"~/{profile_name}.xml"),
            "XML Files (*.xml);;FPDB HUD Files (*.fpdbhud)",
        )

        if not filename:
            return

        try:
            import xml.dom.minidom
            impl = xml.dom.minidom.getDOMImplementation()
            pkg_doc = impl.createDocument(None, "fpdb_hud_package", None)
            root = pkg_doc.documentElement
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
                    "Export Warning",
                    "The current profile is not saved to the configuration yet. Please save your changes before exporting."
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
                    "Export Layout Coordinates",
                    "Do you want to include custom table coordinates (Layout Sets) in this HUD package?",
                    QMessageBox.Yes | QMessageBox.No
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
                "Export Successful",
                f"HUD profile '{profile_name}' exported successfully to:\n{filename}"
            )
        except Exception as e:  # intentional broad catch
            QMessageBox.critical(
                self,
                "Export Error",
                f"An error occurred while exporting HUD profile:\n{e}"
            )

    def import_profile(self) -> None:
        import os
        import xml.dom.minidom

        from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Import HUD Profile",
            os.path.expanduser("~"),
            "PT4 HUD Layouts (*.pt4hud);;XML Files (*.xml);;FPDB HUD Files (*.fpdbhud);;All Files (*)",
        )

        if not filename:
            return

        # PokerTracker 4 layouts use a different (binary) format and a dedicated
        # importer that builds a multi-panel stat-set + range-chart popup.
        if filename.lower().endswith(".pt4hud"):
            self._import_pt4hud(filename)
            return

        try:
            import_doc = xml.dom.minidom.parse(filename)
            root = import_doc.documentElement
            if root.tagName != "fpdb_hud_package":
                QMessageBox.critical(
                    self,
                    "Import Error",
                    "Invalid package file. The root element must be <fpdb_hud_package>."
                )
                return

            # 1. Process ss (Stat Set)
            ss_nodes = root.getElementsByTagName("ss")
            if not ss_nodes:
                QMessageBox.critical(
                    self,
                    "Import Error",
                    "No HUD profile (stat set) found in the package."
                )
                return

            ss_node = ss_nodes[0]
            imported_name = ss_node.getAttribute("name")
            if not imported_name:
                QMessageBox.critical(
                    self,
                    "Import Error",
                    "Imported HUD profile has no name."
                )
                return

            overwrite_profile = False
            new_profile_name = imported_name

            # Check for conflict
            if imported_name in self.hud_profiles:
                msg_box = QMessageBox(self)
                msg_box.setWindowTitle("Profile Conflict")
                msg_box.setText(f"A HUD profile named '{imported_name}' already exists.")

                overwrite_btn = msg_box.addButton("Overwrite", QMessageBox.ButtonRole.DestructiveRole)
                rename_btn = msg_box.addButton("Rename", QMessageBox.ButtonRole.ActionRole)
                cancel_btn = msg_box.addButton(QMessageBox.StandardButton.Cancel)

                msg_box.setDefaultButton(rename_btn)
                msg_box.exec()

                clicked_btn = msg_box.clickedButton()
                if clicked_btn == cancel_btn:
                    return
                elif clicked_btn == rename_btn:
                    new_name, ok = QInputDialog.getText(
                        self,
                        "Rename Imported Profile",
                        f"Enter new name for imported profile '{imported_name}':",
                        text=f"{imported_name}_imported"
                    )
                    if not ok or not new_name:
                        return
                    while new_name in self.hud_profiles:
                        new_name, ok = QInputDialog.getText(
                            self,
                            "Rename Imported Profile",
                            f"Name '{new_name}' already exists. Enter another name:",
                            text=f"{new_name}_1"
                        )
                        if not ok or not new_name:
                            return
                    new_profile_name = new_name
                elif clicked_btn == overwrite_btn:
                    overwrite_profile = True

            # 2. Process pu (Popup Windows)
            pu_nodes = root.getElementsByTagName("pu")
            overwrite_popups = {} # pu_name -> bool
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
                        msg_box.setWindowTitle("Popup Conflict")
                        msg_box.setText(f"Popup window '{pu_name}' already exists.")

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
            overwrite_layouts = {} # ls_name -> bool
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
                        msg_box.setWindowTitle("Layout Conflict")
                        msg_box.setText(f"Layout coordinates for site layout '{ls_name}' already exist.")
                        msg_box.setInformativeText("Do you want to overwrite your existing layout coordinates for this site with the imported ones?")

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

            # Append imported ss_node
            indent = self.config.doc.createTextNode("\n        ")
            stat_sets_node.appendChild(indent)
            merged_ss = self.config.doc.importNode(ss_node, True)
            stat_sets_node.appendChild(merged_ss)

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

            # Save configuration and reload
            self.config.save()
            self.config.reload()

            # Reload HUD profiles and popups in the UI
            self.load_profiles()
            self.load_popup_windows()

            # Select the imported profile
            self.profile_combo.setCurrentText(new_profile_name)
            self.on_profile_selected(self.profile_combo.currentIndex())

            # Reload parent config to apply changes live
            self.reload_parent_config()

            QMessageBox.information(
                self,
                "Import Successful",
                f"HUD profile '{new_profile_name}' successfully imported!"
            )

        except Exception as e:  # intentional broad catch
            QMessageBox.critical(
                self,
                "Import Error",
                f"An error occurred while importing HUD profile:\n{e}"
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
            # Apply live in the running HUD if the parent wired this hook.
            if hasattr(self, "reload_parent_config"):
                self.reload_parent_config()
        except Exception as e:  # intentional broad catch
            log.exception("PT4 .pt4hud import failed")
            QMessageBox.critical(self, "Import Error", f"Could not import {filename}:\n{e}")
            return

        lines = [
            f"Imported '{summary['name']}'.",
            f"• {summary['stats']} stats mapped"
            + (f" across {summary['blocks']} position panels." if summary.get("blocks") else "."),
        ]
        if summary["charts"]:
            lines.append(f"• {len(summary['charts'])} range chart(s) "
                         f"({', '.join(summary['charts'])}) → popup '{summary['popup']}'.")
        if summary["unmapped"]:
            lines.append(f"• {len(summary['unmapped'])} custom formula stat(s) could not be mapped.")
        QMessageBox.information(self, "PT4 HUD imported", "\n".join(lines))

    def get_current_profile(self):
        if self.profile_combo.currentIndex() < 0:
            return None, None
        name = self.profile_combo.currentText()
        profile = self.hud_profiles[name]

        # Handle both old and new format
        if isinstance(profile, list):
            # Old format - return the list directly
            return name, profile
        # New format - return the stats list
        return name, profile.get("stats", [])

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
        """(block_index, kind, ref) for the selected table row, or None."""
        items = getattr(self, "_row_items", [])
        row = self.stat_table.currentRow()
        if 0 <= row < len(items):
            return items[row]
        return None

    def add_stat(self) -> None:
        name, profile = self._current_profile()
        if profile is None:
            return
        # Add to the block of the selected row (or the first block / flat list).
        sel = self._selected_row_item()
        block_index = sel[0] if sel else (0 if isinstance(profile, dict) and profile.get("blocks") else None)
        container = self._item_container(profile, block_index)
        max_rows = int(container.get("rows", 5)) or 5
        max_cols = int(container.get("cols", 5)) or 5
        dlg = AddStatDialog(max_rows=max_rows, max_cols=max_cols, parent=self)
        if dlg.exec():
            stat = dlg.get_stat()
            container.setdefault("stats", []).append(stat)
            container["rows"] = max(int(container.get("rows", 1)), int(stat["row"]) + 1)
            container["cols"] = max(int(container.get("cols", 1)), int(stat["col"]) + 1)
            self.on_profile_selected(self.profile_combo.currentIndex())

    def edit_stat(self) -> None:
        name, profile = self._current_profile()
        if profile is None:
            return
        sel = self._selected_row_item()
        if sel is None:
            return
        block_index, kind, ref = sel
        if kind == "text":
            from PySide6.QtWidgets import QInputDialog

            new_label, ok = QInputDialog.getText(self, "Edit Text Label", "Label:", text=ref.get("label", ""))
            if ok:
                ref["label"] = new_label
                self.on_profile_selected(self.profile_combo.currentIndex())
            return
        if kind == "hline":
            from PySide6.QtGui import QColor
            from PySide6.QtWidgets import QColorDialog

            col = QColorDialog.getColor(QColor(ref.get("color") or "#d7b500"), self, "Line colour")
            if col.isValid():
                ref["color"] = col.name()
                self.on_profile_selected(self.profile_combo.currentIndex())
            return
        container = self._item_container(profile, block_index)
        max_rows = int(container.get("rows", 5)) or 5
        max_cols = int(container.get("cols", 5)) or 5
        dlg = AddStatDialog(stat=ref, max_rows=max_rows, max_cols=max_cols, parent=self)
        if dlg.exec():
            ref.update(dlg.get_stat())  # ref is the block's stat dict -> edit persists
            self.on_profile_selected(self.profile_combo.currentIndex())

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
        self.on_profile_selected(self.profile_combo.currentIndex())

    def _next_free_cell(self, container) -> tuple[int, int]:
        """First free (row, col) in a block/profile container."""
        cols = max(1, int(container.get("cols", 4)))
        used = {(s.get("row", 0), s.get("col", 0)) for s in container.get("stats", [])}
        used |= {tuple(t["rowcol"]) for t in container.get("texts", [])}
        used |= {tuple(h["rowcol"]) for h in container.get("hlines", [])}
        r = 0
        while True:
            for cc in range(cols):
                if (r, cc) not in used:
                    return r, cc
            r += 1

    def add_text_label(self) -> None:
        from PySide6.QtWidgets import QInputDialog

        name, profile = self._current_profile()
        if profile is None:
            return
        sel = self._selected_row_item()
        block_index = sel[0] if sel else (0 if isinstance(profile, dict) and profile.get("blocks") else None)
        container = self._item_container(profile, block_index)
        label, ok = QInputDialog.getText(self, "Add Text Label", "Label text (e.g. column header, caption):")
        if not ok or not label.strip():
            return
        r, cc = self._next_free_cell(container)
        container.setdefault("texts", []).append(
            {"rowcol": (r, cc), "label": label.strip(), "colspan": 1, "align": "center", "fgcolor": "", "bgcolor": ""},
        )
        container["rows"] = max(int(container.get("rows", 1)), r + 1)
        self.on_profile_selected(self.profile_combo.currentIndex())

    def add_hline(self) -> None:
        name, profile = self._current_profile()
        if profile is None:
            return
        sel = self._selected_row_item()
        block_index = sel[0] if sel else (0 if isinstance(profile, dict) and profile.get("blocks") else None)
        container = self._item_container(profile, block_index)
        r, _cc = self._next_free_cell(container)
        # A separator takes its own row and spans the whole panel width (colspan 0).
        container.setdefault("hlines", []).append({"rowcol": (r, 0), "colspan": 0, "color": ""})
        container["rows"] = max(int(container.get("rows", 1)), r + 1)
        self.on_profile_selected(self.profile_combo.currentIndex())

    def add_block(self) -> None:
        from PySide6.QtWidgets import QInputDialog

        name, profile = self._current_profile()
        if not isinstance(profile, dict):
            return
        label, ok = QInputDialog.getText(self, "Add Block", "New panel (block) name:")
        if not ok:
            return
        cols = int(profile.get("cols", 4)) or 4
        blocks = profile.setdefault("blocks", [])
        if not blocks:
            # Promote the existing flat grid to the first block so the profile
            # becomes a genuine multi-panel set.
            blocks.append({"label": "Main", "position": "", "rows": int(profile.get("rows", 1)), "cols": cols,
                           "title_bgcolor": "", "title_fgcolor": "", "bordercolor": "", "x": 0, "y": 0,
                           "stats": [dict(s) for s in profile.get("stats", [])], "texts": []})
        blocks.append({"label": label.strip() or f"Block {len(blocks) + 1}", "position": "", "rows": 1, "cols": cols,
                       "title_bgcolor": "", "title_fgcolor": "", "bordercolor": "", "x": 0, "y": 0,
                       "stats": [], "texts": []})
        profile["multiblock"] = True
        self.on_profile_selected(self.profile_combo.currentIndex())

    def edit_block_properties(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        name, profile = self._current_profile()
        if not isinstance(profile, dict):
            return
        blocks = profile.get("blocks")
        if not blocks:
            QMessageBox.information(self, "Block Properties", "This profile has no panels. Use Add Block first.")
            return
        sel = self._selected_row_item()
        bi = sel[0] if sel and sel[0] is not None else 0
        dlg = BlockPropertiesDialog(blocks[bi], parent=self)
        if dlg.exec():
            blocks[bi].update(dlg.get_props())
            self.on_profile_selected(self.profile_combo.currentIndex())

    def _append_stat_node(self, parent_node, stat: dict, row: int, col: int) -> None:
        stat_node = self.config.doc.createElement("stat")
        stat_node.setAttribute("_rowcol", f"({row + 1},{col + 1})")
        stat_node.setAttribute("_stat_name", stat.get("stat", ""))
        stat_node.setAttribute("click", stat.get("click", ""))
        stat_node.setAttribute("popup", stat.get("popup", "default"))
        stat_node.setAttribute("tip", stat.get("tip", ""))
        stat_node.setAttribute("hudprefix", stat.get("hudprefix", ""))
        stat_node.setAttribute("hudsuffix", stat.get("hudsuffix", ""))
        stat_node.setAttribute("hudcolor", stat.get("hudcolor", ""))
        stat_node.setAttribute("hudbgcolor", stat.get("hudbgcolor", ""))
        stat_node.setAttribute("stat_loth", stat.get("stat_loth", ""))
        stat_node.setAttribute("stat_hith", stat.get("stat_hith", ""))
        stat_node.setAttribute("stat_locolor", stat.get("stat_locolor", ""))
        stat_node.setAttribute("stat_hicolor", stat.get("stat_hicolor", ""))
        stat_node.setAttribute("stat_midcolor", stat.get("stat_midcolor", ""))
        # PT4 cell layout (written only when non-default to keep XML clean).
        if int(stat.get("colspan", 1) or 1) > 1:
            stat_node.setAttribute("colspan", str(int(stat["colspan"])))
        if stat.get("align") and stat["align"] != "center":
            stat_node.setAttribute("align", stat["align"])
        parent_node.appendChild(stat_node)

    def _append_hline_node(self, parent_node, hline: dict) -> None:
        """Write a PT4-style <hline> separator item within a block."""
        rc = hline.get("rowcol", (0, 0))
        node = self.config.doc.createElement("hline")
        node.setAttribute("_rowcol", f"({int(rc[0]) + 1},{int(rc[1]) + 1})")
        if hline.get("colspan"):
            node.setAttribute("colspan", str(int(hline["colspan"])))
        if hline.get("color"):
            node.setAttribute("color", hline["color"])
        parent_node.appendChild(node)

    def _append_text_node(self, parent_node, text: dict) -> None:
        """Write a PT4-style <text> label item within a block."""
        rc = text.get("rowcol", (0, 0))
        node = self.config.doc.createElement("text")
        node.setAttribute("_rowcol", f"({int(rc[0]) + 1},{int(rc[1]) + 1})")
        node.setAttribute("label", text.get("label", ""))
        if int(text.get("colspan", 1)) > 1:
            node.setAttribute("colspan", str(int(text.get("colspan", 1))))
        if text.get("align"):
            node.setAttribute("align", text["align"])
        if text.get("fgcolor"):
            node.setAttribute("fgcolor", text["fgcolor"])
        if text.get("bgcolor"):
            node.setAttribute("bgcolor", text["bgcolor"])
        parent_node.appendChild(node)

    def _write_profile_stats(self, stat_set_node, profile_data, rows: int, cols: int) -> None:
        """Write a profile as flat <stat> nodes or PT4-style <block> nodes."""
        stat_set_node.setAttribute("rows", str(rows))
        stat_set_node.setAttribute("cols", str(cols))

        while stat_set_node.firstChild:
            stat_set_node.removeChild(stat_set_node.firstChild)

        blocks = profile_data.get("blocks") if isinstance(profile_data, dict) else None
        if blocks:
            for block in blocks:
                stat_set_node.appendChild(self.config.doc.createTextNode("\n            "))
                block_node = self.config.doc.createElement("block")
                for attr in ("label", "id", "scope", "audience", "position", "title_bgcolor", "title_fgcolor", "bordercolor"):
                    if block.get(attr) is not None:
                        block_node.setAttribute(attr, str(block.get(attr, "")))
                block_node.setAttribute("rows", str(block.get("rows", 1)))
                block_node.setAttribute("cols", str(block.get("cols", cols)))
                block_node.setAttribute("x", str(block.get("x", 0)))
                block_node.setAttribute("y", str(block.get("y", 0)))

                for text in block.get("texts", []):
                    block_node.appendChild(self.config.doc.createTextNode("\n                "))
                    self._append_text_node(block_node, text)
                for hline in block.get("hlines", []):
                    block_node.appendChild(self.config.doc.createTextNode("\n                "))
                    self._append_hline_node(block_node, hline)
                for stat in block.get("stats", []):
                    block_node.appendChild(self.config.doc.createTextNode("\n                "))
                    self._append_stat_node(block_node, stat, int(stat.get("row", 0)), int(stat.get("col", 0)))
                if block.get("stats") or block.get("texts") or block.get("hlines"):
                    block_node.appendChild(self.config.doc.createTextNode("\n            "))
                stat_set_node.appendChild(block_node)
            stat_set_node.appendChild(self.config.doc.createTextNode("\n        "))
            return

        stats = profile_data if isinstance(profile_data, list) else profile_data.get("stats", [])
        for stat in stats:
            stat_set_node.appendChild(self.config.doc.createTextNode("\n            "))
            self._append_stat_node(stat_set_node, stat, int(stat["row"]), int(stat["col"]))
        if stats:
            stat_set_node.appendChild(self.config.doc.createTextNode("\n        "))

    def save_changes(self) -> None:
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
                        rows = 5
                        cols = 5
                    else:
                        # New format - dict with rows/cols/stats
                        rows = profile_data.get("rows", 5)
                        cols = profile_data.get("cols", 5)
                        # Persist the positional-panel mode for multi-block HUDs.
                        if profile_data.get("multiblock"):
                            stat_set_node.setAttribute(
                                "positional_mode", profile_data.get("positional_mode", "all") or "all"
                            )
                        # Persist hero-HUD visibility when explicitly set.
                        if profile_data.get("show_hero_hud"):
                            stat_set_node.setAttribute("show_hero_hud", profile_data["show_hero_hud"])

                    self._write_profile_stats(stat_set_node, profile_data, rows, cols)

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

            # Save general profiling settings
            hud_params = {
                "player_profiling": "True" if self.profiling_checkbox.isChecked() else "False",
                "profile_in_name": "True" if self.profile_in_name_checkbox.isChecked() else "False",
                "profile_min_hands": str(self.profile_min_hands_spin.value())
            }
            if hasattr(self.config, "set_hud_ui_parameters"):
                self.config.set_hud_ui_parameters(hud_params)

            # Save to file
            if hasattr(self.config, "save"):
                self.config.save()
                # Update original profiles and popups after successful save
                self.original_profiles = self._deep_copy_profiles(self.hud_profiles)
                self.original_popups = self._deep_copy_popups(self.popup_windows)
                self.original_player_profiling = self.profiling_checkbox.isChecked()
                self.original_profile_in_name = self.profile_in_name_checkbox.isChecked()
                self.original_profile_min_hands = self.profile_min_hands_spin.value()
                QMessageBox.information(self, "Success", "HUD configuration saved successfully!")
            else:
                QMessageBox.warning(self, "Warning", "Could not save to file. Config save method not available.")

            self.accept()

        except Exception as e:  # intentional broad catch: GUI save-profiles boundary surfaces failure in a dialog
            QMessageBox.critical(self, "Error", f"Failed to save HUD profiles:\n{e!s}")

    def add_popup(self) -> None:
        """Add a new popup window."""
        from PySide6.QtWidgets import QInputDialog

        name, ok = QInputDialog.getText(self, "New Popup", "Enter popup name:")
        if ok and name and name not in self.popup_windows:
            self.popup_windows[name] = {"name": name, "class": "default", "stats": []}
            self.popup_combo.addItem(name)
            self.popup_combo.setCurrentText(name)

    def duplicate_popup(self) -> None:
        """Duplicate current popup."""
        if self.popup_combo.currentIndex() < 0:
            return
        current_name = self.popup_combo.currentText()
        from PySide6.QtWidgets import QInputDialog

        new_name, ok = QInputDialog.getText(self, "Duplicate Popup", "New popup name:")
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
class PopupStatEditDialog(QDialog):
    def __init__(self, stat_data=None, parent=None) -> None:
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
        """Get the stat data from the dialog."""
        return {"stat_name": self.stat_name_input.text(), "submenu": self.submenu_input.text()}


# --- Popup Edit Dialog ---
class PopupEditDialog(QDialog):
    def __init__(self, popup_data=None, parent=None) -> None:
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
        self.stats_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
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
