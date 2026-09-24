"""Qt visual distribution for hand-state composition (#364)."""

from __future__ import annotations

from typing import Any

import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QLabel, QVBoxLayout, QWidget

from .hand_state_composition import DIMENSIONS
from .research_hand_strength import HandStrengthDistribution
from .ring_stats.styles import get_theme_palette

_DIMENSION_ORDER = (
    "made_hand",
    "pair_detail",
    "draw",
    "nutness",
    "blocker",
    "made_hand_rank",
    "hand_state_street",
)


class HandStrengthChartWidget(QWidget):
    """Clickable horizontal bars with explicit known-card coverage."""

    dimension_changed = Signal(str)
    category_clicked = Signal(str, object, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._hero: HandStrengthDistribution | None = None
        self._field: HandStrengthDistribution | None = None
        self._categories: tuple[Any, ...] = ()
        self.plot = pg.PlotWidget()

        palette = get_theme_palette()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        self.dimension_combo = QComboBox()
        layout.addWidget(QLabel("Hand-state dimension"))
        for dimension in _DIMENSION_ORDER:
            if dimension in DIMENSIONS:
                self.dimension_combo.addItem(DIMENSIONS[dimension].label, dimension)
        layout.addWidget(self.dimension_combo)
        self.coverage_label = QLabel("No hand-state composition loaded")
        self.coverage_label.setWordWrap(True)
        self.coverage_label.setStyleSheet(f"color: {palette.get('muted_text', '#a0aec0')};")
        layout.addWidget(self.coverage_label)
        self.plot.setMinimumHeight(220)
        self.plot.setMaximumHeight(340)
        self.plot.setBackground(palette.get("sidebar", "#1a202c"))
        self.plot.setLabel("bottom", "Share of classified decisions (%)")
        self.plot.showGrid(x=True, y=False, alpha=0.2)
        self.plot.scene().sigMouseClicked.connect(self._scene_clicked)
        layout.addWidget(self.plot)
        self.dimension_combo.currentIndexChanged.connect(self._dimension_changed)

    def set_dimension(self, dimension: str) -> None:
        index = self.dimension_combo.findData(dimension)
        if index >= 0 and index != self.dimension_combo.currentIndex():
            blocked = self.dimension_combo.blockSignals(True)
            self.dimension_combo.setCurrentIndex(index)
            self.dimension_combo.blockSignals(blocked)

    def set_distribution(
        self,
        hero: HandStrengthDistribution,
        field: HandStrengthDistribution | None = None,
    ) -> None:
        self._hero = hero
        self._field = field
        self._categories = self._union_categories(hero, field)
        self.set_dimension(hero.dimension)
        self._render()

    def clear_distribution(self) -> None:
        self._hero = None
        self._field = None
        self._categories = ()
        self.plot.clear()
        self.coverage_label.setText("No hand-state composition loaded")

    def click_category(self, index: int) -> None:
        if 0 <= index < len(self._categories):
            category = self._categories[index]
            self.category_clicked.emit(category.filter_name or "", category.filter_value, category.label)

    def _dimension_changed(self) -> None:
        dimension = self.dimension_combo.currentData()
        if dimension:
            self.dimension_changed.emit(str(dimension))

    @staticmethod
    def _union_categories(
        hero: HandStrengthDistribution,
        field: HandStrengthDistribution | None,
    ) -> tuple[Any, ...]:
        categories = list(hero.categories)
        if field is not None:
            seen = {category.key for category in categories}
            categories.extend(category for category in field.categories if category.key not in seen)
        return tuple(categories)

    def _render(self) -> None:
        self.plot.clear()
        if self._hero is None or not self._categories:
            self.coverage_label.setText("No classified hand-state decisions for this context.")
            return

        palette = get_theme_palette()
        hero_color = palette.get("accent", "#319795")
        field_color = palette.get("graph_ev", "#f59e3d")
        hero_by_key = {category.key: category for category in self._hero.categories}
        field_by_key = {category.key: category for category in self._field.categories} if self._field else {}
        hero_values = [self._percentage(hero_by_key.get(category.key)) for category in self._categories]
        field_values = [self._percentage(field_by_key.get(category.key)) for category in self._categories]
        y = list(range(len(self._categories)))
        max_value = max([*hero_values, *field_values], default=0.0)
        if self._field is None:
            hero_bars = pg.BarGraphItem(
                x0=0,
                x1=hero_values,
                y=y,
                height=0.68,
                brush=pg.mkBrush(color=hero_color),
                pen=pg.mkPen(color=hero_color),
                name="Known cards",
            )
            self.plot.addItem(hero_bars)
        else:
            width = 0.34
            hero_bars = pg.BarGraphItem(
                x0=0,
                x1=hero_values,
                y=[value - width / 2 for value in y],
                height=width,
                brush=pg.mkBrush(color=hero_color),
                pen=pg.mkPen(color=hero_color),
                name="Hero",
            )
            field_bars = pg.BarGraphItem(
                x0=0,
                x1=field_values,
                y=[value + width / 2 for value in y],
                height=width,
                brush=pg.mkBrush(color=field_color),
                pen=pg.mkPen(color=field_color),
                name="Field",
            )
            self.plot.addItem(hero_bars)
            self.plot.addItem(field_bars)

        self.plot.getAxis("left").setTicks([[(index, category.label) for index, category in enumerate(self._categories)]])
        self.plot.setXRange(0, max(100.0, max_value * 1.15), padding=0)
        self.plot.setYRange(-0.75, len(self._categories) - 0.25, padding=0)
        self.coverage_label.setText(self._coverage_text())

    @staticmethod
    def _percentage(category: Any) -> float:
        return 0.0 if category is None or category.share is None else category.share

    def _coverage_text(self) -> str:
        hero = self._hero
        if hero is None:
            return "No hand-state composition loaded"
        parts = [self._side_coverage("Hero", hero)]
        if self._field is not None:
            parts.append(self._side_coverage("Field", self._field))
        overlap = " Categories overlap; shares do not sum to 100%." if hero.overlapping else ""
        warning = " Low known-card sample." if hero.known_sample_warning else ""
        return " · ".join(parts) + overlap + warning + " Click a category to filter the study."

    @staticmethod
    def _side_coverage(label: str, distribution: HandStrengthDistribution) -> str:
        return (
            f"{label}: {distribution.classified}/{distribution.total} classified "
            f"({distribution.coverage:.1f}% coverage), {distribution.unclassified} unknown"
        )

    def _scene_clicked(self, event: Any) -> None:
        if event.button() != Qt.MouseButton.LeftButton or not self._categories:
            return
        point = self.plot.getViewBox().mapSceneToView(event.scenePos())
        index = int(round(point.y()))
        if 0 <= index < len(self._categories) and abs(point.y() - index) <= 0.55:
            self.click_category(index)


__all__ = ["HandStrengthChartWidget"]
