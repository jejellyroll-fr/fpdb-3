"""Qt chart widgets for Research sizing and response distributions (#362)."""

from __future__ import annotations

from typing import Any

import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from .research_distributions import DistributionBin, DistributionSeries
from .ring_stats.styles import get_theme_palette


class DistributionChartWidget(QWidget):
    """A clickable, side-by-side bar chart with a textual exact-data fallback."""

    bin_clicked = Signal(str, object, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._bins: tuple[DistributionBin, ...] = ()
        self._hero: DistributionSeries | None = None
        self._field: DistributionSeries | None = None
        self._bar_items: list[pg.BarGraphItem] = []

        palette = get_theme_palette()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        self.summary_label = QLabel("No distribution loaded")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet(f"color: {palette.get('muted_text', '#a0aec0')};")
        layout.addWidget(self.summary_label)
        self.plot = pg.PlotWidget()
        self.plot.setMinimumHeight(220)
        self.plot.setBackground(palette.get("sidebar", "#1a202c"))
        self.plot.setLabel("left", "Percent")
        self.plot.showGrid(x=False, y=True, alpha=0.2)
        self.plot.scene().sigMouseClicked.connect(self._scene_clicked)
        layout.addWidget(self.plot)

    def set_series(self, series: DistributionSeries) -> None:
        self._hero = series
        self._field = None
        self._bins = series.bins
        self._render()

    def set_comparison(self, hero: DistributionSeries, field: DistributionSeries) -> None:
        self._hero = hero
        self._field = field
        self._bins = self._comparison_bins(hero, field)
        self._render()

    def clear_distribution(self) -> None:
        self._hero = None
        self._field = None
        self._bins = ()
        self.plot.clear()
        self.summary_label.setText("No distribution loaded")

    def click_bin(self, index: int) -> None:
        """Activate a bar programmatically; useful for keyboard/UI tests too."""
        if 0 <= index < len(self._bins):
            item = self._bins[index]
            self.bin_clicked.emit(item.filter_name, item.filter_value, item.label)

    def _render(self) -> None:
        self.plot.clear()
        self._bar_items = []
        if not self._bins:
            self.summary_label.setText("No distribution data for this context.")
            return

        palette = get_theme_palette()
        hero_color = palette.get("accent", "#319795")
        field_color = palette.get("graph_ev", "#f59e3d")
        labels = [item.label for item in self._bins]
        x = list(range(len(labels)))
        max_value = 0.0

        if self._field is None:
            values = [item.percentage for item in self._bins]
            bars = pg.BarGraphItem(
                x=x,
                height=values,
                width=0.68,
                brush=pg.mkBrush(color=hero_color),
                pen=pg.mkPen(color=hero_color),
                name="Value",
            )
            self.plot.addItem(bars)
            self._bar_items.append(bars)
            max_value = max(values, default=0.0)
            summary = self._series_summary(self._hero, "Value")
        else:
            hero_by_label = {item.label: item for item in self._hero.bins} if self._hero else {}
            field_by_label = {item.label: item for item in self._field.bins}
            hero_values = [hero_by_label.get(item.label, _zero_bin(item)).percentage for item in self._bins]
            field_values = [field_by_label.get(item.label, _zero_bin(item)).percentage for item in self._bins]
            width = 0.34
            hero_bars = pg.BarGraphItem(
                x=[value - width / 2 for value in x],
                height=hero_values,
                width=width,
                brush=pg.mkBrush(color=hero_color),
                pen=pg.mkPen(color=hero_color),
                name="Hero",
            )
            field_bars = pg.BarGraphItem(
                x=[value + width / 2 for value in x],
                height=field_values,
                width=width,
                brush=pg.mkBrush(color=field_color),
                pen=pg.mkPen(color=field_color),
                name="Field",
            )
            self.plot.addItem(hero_bars)
            self.plot.addItem(field_bars)
            self._bar_items.extend((hero_bars, field_bars))
            max_value = max([*hero_values, *field_values], default=0.0)
            summary = " · ".join(
                part
                for part in (
                    self._series_summary(self._hero, "Hero"),
                    self._series_summary(self._field, "Field"),
                )
                if part
            )

        self.plot.getAxis("bottom").setTicks([list(enumerate(labels))])
        self.plot.setYRange(0, max(100.0, max_value * 1.15), padding=0)
        self.summary_label.setText(summary + " · Click a bar to filter the study.")

    @staticmethod
    def _series_summary(series: DistributionSeries | None, label: str) -> str:
        if series is None:
            return ""
        warning = f" — {series.low_sample_warning}" if series.low_sample_warning else ""
        return f"{label}: {series.total_opportunities} decisions, {series.chart_unit}{warning}"

    @staticmethod
    def _comparison_bins(hero: DistributionSeries, field: DistributionSeries) -> tuple[DistributionBin, ...]:
        """Use one x-axis even when one side has an unobserved category."""
        bins = list(hero.bins)
        seen = {item.label for item in bins}
        bins.extend(item for item in field.bins if item.label not in seen)
        return tuple(bins)

    def _scene_clicked(self, event: Any) -> None:
        if event.button() != Qt.MouseButton.LeftButton or not self._bins:
            return
        point = self.plot.getViewBox().mapSceneToView(event.scenePos())
        index = int(round(point.x()))
        if 0 <= index < len(self._bins) and abs(point.x() - index) <= 0.55:
            self.click_bin(index)


def _zero_bin(template: DistributionBin) -> DistributionBin:
    return DistributionBin(
        key=template.key,
        label=template.label,
        opportunities=0,
        actions=0,
        value=None,
        unit=template.unit,
        frequency_bp=0 if template.frequency_bp is not None else None,
        share_bp=0,
        filter_name=template.filter_name,
        filter_value=template.filter_value,
    )


__all__ = ["DistributionChartWidget"]
