"""Inspect the shipped reference HUDs without opening a poker table (#370).

Before this, the only way to find out what the Dynamic package shows when a
player faces a 3-bet was to sit in a 3-bet pot. That is not a way to evaluate a
HUD, and it is certainly not a way to choose between three of them, so the
reference packages were effectively unreviewable except by their authors.

The pane reads the packages straight off disk through
:mod:`fpdb_3_legacy.hud_presentation` -- the same description the tests assert
against -- and renders them with the preview widget the rest of Preferences
already uses. Three things are inspectable:

* the **block**, as a seat would see it, with the package's own colours,
  prefixes and tips;
* the **dynamic context**, chosen from the panels the resolver can select, so
  ``Preflop · Facing a 3-bet`` is one combo box away;
* the **popup paths**, listed in full, so "where does this number live" is
  answered by reading rather than by clicking through a live table.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy.hud_presentation import (
    CONTEXTUAL_MIN_SAMPLE,
    DEMO_VALUES,
    ROLE_BACKGROUNDS,
    ROLE_DESCRIPTIONS,
    SAMPLE_HIGH,
    SAMPLE_LOW,
    PackagePresentation,
    describe_package,
    panel_title,
    popup_paths,
    preview_blocks,
    reference_packages,
)
from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.modern_hud_preferences.preview_widgets import HudPreviewWidget

#: The order the packages are offered in: the one a new user should read
#: first, then the two that ask something of them.
PACKAGE_ORDER: tuple[tuple[str, str], ...] = (
    ("basic", "Basic — eight numbers, no setup"),
    ("advanced", "Advanced — compact surface, popups behind it"),
    ("dynamic", "Dynamic — panels that follow the spot"),
)


class ReferenceHudPreview(QWidget):
    """A read-only tour of the three shipped reference HUD packages."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._packages: dict[str, PackagePresentation] = {}
        self._load_failures: dict[str, str] = {}
        for name, path in reference_packages().items():
            try:
                self._packages[name] = describe_package(path)
            except Exception as exc:  # noqa: BLE001 - a broken package must not break Preferences.
                self._load_failures[name] = str(exc)
        self._build_ui()
        self._package_changed()

    # -- construction --------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        chooser = QHBoxLayout()
        chooser.addWidget(QLabel(_("Reference HUD")))
        self.package_combo = QComboBox()
        for name, label in PACKAGE_ORDER:
            if name in self._packages:
                self.package_combo.addItem(label, name)
        self.package_combo.currentIndexChanged.connect(self._package_changed)
        chooser.addWidget(self.package_combo, 1)

        chooser.addWidget(QLabel(_("Context")))
        self.context_combo = QComboBox()
        self.context_combo.currentIndexChanged.connect(self._context_changed)
        chooser.addWidget(self.context_combo, 1)
        layout.addLayout(chooser)

        self.description_label = QLabel("")
        self.description_label.setWordWrap(True)
        layout.addWidget(self.description_label)

        body = QHBoxLayout()
        self.preview = HudPreviewWidget()
        body.addWidget(self.preview, 2)

        right = QVBoxLayout()
        paths_box = QGroupBox("Popup paths")
        paths_layout = QVBoxLayout(paths_box)
        self.paths_list = QListWidget()
        self.paths_list.setToolTip(
            _(
                "Every popup a cell of this package opens, and everything those popups "
                "navigate to. A row ending in an arrow leaves the package for the "
                "shipped popup library.",
            ),
        )
        paths_layout.addWidget(self.paths_list)
        right.addWidget(paths_box, 2)

        legend_box = QGroupBox("What the colours mean")
        legend_layout = QVBoxLayout(legend_box)
        for role, description in ROLE_DESCRIPTIONS.items():
            swatch = QLabel(f"{role}: {description}")
            swatch.setWordWrap(True)
            swatch.setStyleSheet(
                f"background: {ROLE_BACKGROUNDS[role]}; color: #E6EDF3; padding: 3px 6px;",
            )
            legend_layout.addWidget(swatch)
        sample_rule = QLabel(
            f"Sample: under {SAMPLE_LOW} hands a number is marked thin, over {SAMPLE_HIGH} "
            f"it is solid, and a contextual stat needs {CONTEXTUAL_MIN_SAMPLE} before it is "
            "shown at all. The colour is never the only signal — every cell carries its "
            "prefix and its tooltip.",
        )
        sample_rule.setWordWrap(True)
        legend_layout.addWidget(sample_rule)
        right.addWidget(legend_box, 1)
        body.addLayout(right, 1)
        layout.addLayout(body, 1)

    # -- state ---------------------------------------------------------------

    @property
    def package(self) -> PackagePresentation | None:
        """The package currently on screen."""
        name = self.package_combo.currentData()
        return self._packages.get(str(name)) if name else None

    def select_package(self, name: str) -> None:
        """Show one package by its short name; used by callers and tests."""
        index = self.package_combo.findData(name)
        if index < 0:
            raise KeyError(f"No reference package named {name!r}")
        self.package_combo.setCurrentIndex(index)

    def select_context(self, panel_id: str) -> None:
        """Show one dynamic panel's context."""
        index = self.context_combo.findData(panel_id)
        if index < 0:
            raise KeyError(f"No context named {panel_id!r} in this package")
        self.context_combo.setCurrentIndex(index)

    @property
    def context_ids(self) -> tuple[str, ...]:
        """The contexts this package offers, in the order they are listed."""
        return tuple(
            str(self.context_combo.itemData(index))
            for index in range(self.context_combo.count())
        )

    # -- rendering -----------------------------------------------------------

    def _package_changed(self) -> None:
        package = self.package
        if package is None:
            self.description_label.setText(
                "No reference package could be read: "
                + "; ".join(f"{name}: {why}" for name, why in self._load_failures.items()),
            )
            return
        self.context_combo.blockSignals(True)
        self.context_combo.clear()
        self.context_combo.addItem("At rest (no rule matched)", "")
        for panel in package.dynamic_panels:
            self.context_combo.addItem(panel.label or panel_title(panel.id), panel.id)
        self.context_combo.setEnabled(self.context_combo.count() > 1)
        self.context_combo.blockSignals(False)

        self.paths_list.clear()
        for path in popup_paths(package):
            self.paths_list.addItem("  ›  ".join(path))
        self._context_changed()

    def _context_changed(self) -> None:
        package = self.package
        if package is None:
            return
        panel_id = str(self.context_combo.currentData() or "")
        if panel_id:
            # What a seat actually sees: the panels with no binding, plus the
            # one the rule selected. Showing all nineteen at once would
            # misdescribe the product rather than preview it.
            resting = [panel.id for panel in package.panels if not panel.is_dynamic]
            blocks = preview_blocks(package, [*resting, panel_id])
            context = package.dynamic_panels
            selected = next((panel for panel in context if panel.id == panel_id), None)
            title = selected.label if selected else panel_title(panel_id)
            self.description_label.setText(
                f"{package.name} — the resolver has selected “{title}”. "
                "At a table this panel appears when the rule that names it matches, "
                "and disappears again when the spot changes.",
            )
        else:
            blocks = preview_blocks(package)
            self.description_label.setText(
                f"{package.name} — what a seat shows with no dynamic rule matched. "
                + (
                    f"{len(package.dynamic_panels)} contextual panels are one rule away."
                    if package.dynamic_panels
                    else "This package has no contextual panels: the block never changes."
                ),
            )
        self._apply_blocks(blocks)

    def _apply_blocks(self, blocks: list[dict[str, Any]]) -> None:
        # The fictional values the contract keeps, so the pane reads like a
        # HUD rather than like a grid of dashes -- and so two people looking
        # at "the Dynamic package" are looking at the same numbers.
        self.preview.sample_values.update(DEMO_VALUES)
        self.preview.set_hud_params(bgcolor="#0B1120", fgcolor="#E6EDF3", font_size=10)
        self.preview.set_blocks(blocks)


__all__ = ["PACKAGE_ORDER", "ReferenceHudPreview"]
