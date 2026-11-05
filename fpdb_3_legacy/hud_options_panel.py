"""The stat range options of a HUD, shown by the table menu and by fpdb's Configure menu (#693).

The two windows differ only in which values they edit. The table menu hands the
panel a table's own ``hud_params``, which take effect on that table and are not
saved. :class:`HudOptionsDialog` edits a copy of the saved defaults, which fpdb
writes to ``<hud_ui>`` and the HUD reads for the tables it opens afterwards.
"""

from __future__ import annotations

from collections.abc import Callable, MutableMapping, Sequence
from typing import Any

from PySide6.QtCore import QCoreApplication, QEvent, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy.i18n import N_
from fpdb_3_legacy.i18n import gettext as _

HERO_PREFIX = "h_"
OPPONENT_PREFIX = ""
OPTION_FIELDS = tuple(
    prefix + name
    for prefix in (HERO_PREFIX, OPPONENT_PREFIX)
    for name in (
        "agg_bb_mult",
        "seats_style",
        "seats_cust_nums_low",
        "seats_cust_nums_high",
        "stat_range",
        "hud_days",
    )
)

_BLINDS = (
    (N_("This level"), 1),
    (N_("0.5x to 2x"), 2),
    (N_("0.33x to 3x"), 3),
    (N_("0.1x to 10x"), 10),
    (N_("All levels"), 10000),
)
_SEATS = ((N_("Any"), "A"), (N_("Custom"), "C"), (N_("Exact"), "E"))
_PERIOD = ((N_("All time"), "A"), (N_("Session"), "S"), (N_("Last n days"), "T"))

_SEATS_CUSTOM = "C"
_PERIOD_DAYS = "T"
_SPINNER_WIDTH = 60

# Sizes only: colours stay with the application's theme.
COMPACT_STYLE = """
    QPushButton, QComboBox, QSpinBox {
        height: 24px;
        min-height: 24px;
        max-height: 24px;
        padding-top: 0;
        padding-bottom: 0;
    }
"""


def fit_to_content(window: QWidget) -> None:
    """Resize a window to what its content needs right now.

    Hiding a widget only posts the layout request that reaches the window, so
    without delivering it first the window keeps its size when content goes away.
    """
    QCoreApplication.sendPostedEvents(None, QEvent.Type.LayoutRequest)
    window.adjustSize()


def bound_combo(
    params: MutableMapping[str, Any],
    field: str,
    items: Sequence[tuple[str, Any]],
    on_change: Callable[[], None] | None = None,
) -> QComboBox:
    """Build a combo box that shows and edits ``params[field]``.

    A value matching no item shows the first item and stays in ``params`` until
    the player picks something else, so opening a window never rewrites it.

    Args:
        params: The values being edited.
        field: The key this combo box edits.
        items: The ``(label, value)`` pairs to offer, labels already translated.
        on_change: Called after the player changes the value.
    """
    combo = QComboBox()
    for position, (label, value) in enumerate(items):
        combo.addItem(label)
        if value == params[field]:
            combo.setCurrentIndex(position)

    def store(position: int) -> None:
        params[field] = items[position][1]
        if on_change is not None:
            on_change()

    combo.currentIndexChanged.connect(store)
    return combo


class HudOptionsPanel(QWidget):
    """Blinds, seats and period, for the player and for the opponents."""

    #: A spinner appeared or went away, so the window may need another size.
    layout_changed = Signal()

    def __init__(self, params: MutableMapping[str, Any], parent: QWidget | None = None) -> None:
        """Build the panel.

        Args:
            params: The values to edit, changed in place as the player edits them.
            parent: The owning widget.
        """
        super().__init__(parent)
        self._params = params
        self._custom_seats: dict[str, QWidget] = {}
        self._days: dict[str, QSpinBox] = {}

        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(4)
        for row, label in enumerate((_("Blinds"), _("Seats"), _("Period")), start=1):
            grid.addWidget(QLabel(label), row, 0)
        grid.addWidget(QLabel(_("Player")), 0, 1)
        grid.addWidget(QLabel(_("Opponents")), 0, 2)
        self._add_column(grid, 1, HERO_PREFIX)
        self._add_column(grid, 2, OPPONENT_PREFIX)
        self._update_spinners()

    def _add_column(self, grid: QGridLayout, column: int, prefix: str) -> None:
        blinds = bound_combo(self._params, f"{prefix}agg_bb_mult", self._translated(_BLINDS))
        blinds.setObjectName(f"{prefix}agg_bb_mult")
        grid.addWidget(blinds, 1, column)

        seats = bound_combo(self._params, f"{prefix}seats_style", self._translated(_SEATS), self._on_choice)
        seats.setObjectName(f"{prefix}seats_style")
        custom = QWidget()
        custom_row = QHBoxLayout(custom)
        custom_row.setContentsMargins(0, 0, 0, 0)
        custom_row.setSpacing(4)
        custom_row.addWidget(self._spinner(f"{prefix}seats_cust_nums_low", 1, 9))
        custom_row.addWidget(QLabel(_("to")))
        custom_row.addWidget(self._spinner(f"{prefix}seats_cust_nums_high", 2, 10))
        self._custom_seats[prefix] = custom
        grid.addLayout(self._row(seats, custom), 2, column)

        period = bound_combo(self._params, f"{prefix}stat_range", self._translated(_PERIOD), self._on_choice)
        period.setObjectName(f"{prefix}stat_range")
        days = self._spinner(f"{prefix}hud_days", 1, 9999)
        self._days[prefix] = days
        grid.addLayout(self._row(period, days), 3, column)

    @staticmethod
    def _translated(items: Sequence[tuple[str, Any]]) -> list[tuple[str, Any]]:
        return [(_(label), value) for label, value in items]

    @staticmethod
    def _row(*widgets: QWidget) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(4)
        for widget in widgets:
            row.addWidget(widget)
        return row

    def _spinner(self, field: str, low: int, high: int) -> QSpinBox:
        spinner = QSpinBox()
        spinner.setObjectName(field)
        spinner.setFixedWidth(_SPINNER_WIDTH)
        spinner.setRange(low, high)
        spinner.setValue(int(self._params[field]))

        def store(value: int) -> None:
            self._params[field] = value

        spinner.valueChanged.connect(store)
        return spinner

    def _on_choice(self) -> None:
        self._update_spinners()
        self.layout_changed.emit()

    def _update_spinners(self) -> None:
        for prefix in (HERO_PREFIX, OPPONENT_PREFIX):
            self._custom_seats[prefix].setVisible(self._params[f"{prefix}seats_style"] == _SEATS_CUSTOM)
            self._days[prefix].setVisible(self._params[f"{prefix}stat_range"] == _PERIOD_DAYS)


class HudOptionsDialog(QDialog):
    """Edit the options a new table starts with, from fpdb's main window."""

    def __init__(self, saved: dict[str, Any], parent: QWidget | None = None) -> None:
        """Build the dialog.

        Args:
            saved: The saved options. They are copied, so Cancel changes nothing.
            parent: The owning window.
        """
        super().__init__(parent)
        self.setWindowTitle(_("HUD Options"))
        self.setStyleSheet(COMPACT_STYLE)
        self._values = dict(saved)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(_("Used by tables opened from now on. Open tables keep their current options.")))
        self.panel = HudOptionsPanel(self._values, self)
        self.panel.layout_changed.connect(lambda: fit_to_content(self))
        layout.addWidget(self.panel)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.buttons = buttons

    def option_values(self) -> dict[str, Any]:
        """Return the edited options alone, so saving them touches nothing else in ``<hud_ui>``."""
        return {field: self._values[field] for field in OPTION_FIELDS}
