#!/usr/bin/env python
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy.Aux_Hud import SimpleLabel
from fpdb_3_legacy.loggingFpdb import get_logger
from fpdb_3_legacy.PopupIcons import get_icon_provider, get_stat_category
from fpdb_3_legacy.PopupThemes import get_theme

log = get_logger("modern_hud_preferences.preview_widgets")

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
        painter.setPen(QPen(QColor(Qt.GlobalColor.black), 2))
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
        self.stats: list[dict[str, Any]] = []  # List of dicts: {row, col, stat, click, popup}
        self.blocks: list[dict[str, Any]] = []  # Multi-panel layout: list of block dicts (styled boxes)
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
        grid.setContentsMargins(
            round(2 * self.preview_scale),
            round(2 * self.preview_scale),
            round(2 * self.preview_scale),
            round(2 * self.preview_scale),
        )
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
        nrows = block.get("rows") or (
            max([s.get("row", 0) for s in bstats] + [t["rowcol"][0] for t in btexts], default=-1) + 1
        )
        ncols = block.get("cols") or (
            max([s.get("col", 0) for s in bstats] + [t["rowcol"][1] for t in btexts], default=-1) + 1
        )
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

    def set_popup(
        self,
        popup_name: str,
        popup_class: str,
        stats: list[dict],
        source: str = "",
        group: str = "",
        theme_name: str = "",
        icon_provider_name: str = "",
    ) -> None:
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

        if popup_class.startswith("ModernSubmenu"):
            if not theme_name:
                theme_name = (
                    "material_light"
                    if popup_class == "ModernSubmenuLight"
                    else "classic"
                    if popup_class == "ModernSubmenuClassic"
                    else "material_dark"
                )
            if not icon_provider_name:
                icon_provider_name = "text" if popup_class == "ModernSubmenuClassic" else "emoji"
            self._build_modern(stats, theme_name, icon_provider_name)
        elif popup_class == "Submenu":
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
            if item is None:
                continue
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

    def _build_modern(self, stats: list[dict], theme_name: str, icon_provider_name: str) -> None:
        """Preview a ModernSubmenu using its selected theme, icons, and sections."""
        theme = get_theme(theme_name)
        icons = get_icon_provider(icon_provider_name)
        self.popup_frame.setStyleSheet(
            "QFrame#popupPreviewFrame{"
            f"background:{theme.get_color('window_bg')};"
            f"border:1px solid {theme.get_color('border')};"
            "}"
            "QLabel{background:transparent;border:none;}"
        )
        grouped: dict[str, list[dict]] = {}
        for stat in stats:
            category = stat.get("category") or get_stat_category(stat.get("stat_name", ""))
            grouped.setdefault(category, []).append(stat)

        section_order = ["player_info", "preflop", "flop", "turn", "river", "steal", "aggression", "general"]
        ordered_sections = [name for name in section_order if name in grouped]
        ordered_sections.extend(name for name in grouped if name not in ordered_sections)
        for section_name in ordered_sections:
            header = QLabel(f"{icons.get_section_icon(section_name)}  {section_name.replace('_', ' ').title()}")
            header.setStyleSheet(
                f"color:{theme.get_color('text_accent')};"
                f"background:{theme.get_color('section_bg')};"
                "font-weight:800;padding:5px 6px;"
            )
            self.popup_layout.addWidget(header)
            for stat in grouped[section_name]:
                stat_name = stat.get("stat_name", "")
                value = self.sample_values.get(stat_name.lower(), "--")
                row = QLabel(f"{icons.get_icon(stat_name)}  {stat_name:<18} {value:>7}")
                row.setStyleSheet(f"color:{theme.get_color('text_primary')};padding:2px 8px;")
                self.popup_layout.addWidget(row)

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
