"""Enter, paste or apply a tournament's payout structure (#446).

ICM needs what each place pays. When an imported summary does not settle it,
the replayer opens this dialog on the hand's tournament: it shows the
structure in use and where it comes from, applies a sit-and-go preset to the
prize pool, or stores prizes or percentages pasted from the room's lobby. The
reading and storing live in :mod:`fpdb_3_legacy.tourney_payouts`.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy import tourney_payouts
from fpdb_3_legacy.i18n import N_
from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.localized_formats import format_number

_PRESET_LABELS = {
    "winner_take_all": N_("Winner takes all (heads-up, Spin & Go)"),
    "sng_6max": N_("6-max sit-and-go: 65 / 35"),
    "sng_9max": N_("9-max sit-and-go: 50 / 30 / 20"),
    "sng_10max": N_("10-max sit-and-go: 50 / 30 / 20"),
    "sng_18max": N_("18-player sit-and-go: 40 / 30 / 20 / 10"),
    "double_or_nothing": N_("Double or nothing: half the field paid"),
}
_SOURCE_LABELS = {
    tourney_payouts.SOURCE_SUMMARY: N_("from the imported results"),
    tourney_payouts.SOURCE_MANUAL: N_("entered"),
}


def _money(hundredths: int | None, currency: str | None) -> str:
    if hundredths is None:
        return _("unknown")
    return f"{format_number(hundredths / 100, 2)} {currency or ''}".strip()


class TourneyPayoutsDialog(QDialog):
    """The payout structure of one tournament: shown, entered, or applied from a preset."""

    def __init__(self, db: Any, tourney_id: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.db = db
        self.tourney_id = tourney_id
        self.changed = False  # whether a structure was stored or cleared: ICM must be priced again
        self.setWindowTitle(_("Tournament payouts"))
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        self.factsLabel = QLabel()
        self.factsLabel.setWordWrap(True)
        layout.addWidget(self.factsLabel)
        self.currentLabel = QLabel()
        self.currentLabel.setWordWrap(True)
        layout.addWidget(self.currentLabel)

        presets = QHBoxLayout()
        self.presetCombo = QComboBox()
        for name in tourney_payouts.PRESETS:
            self.presetCombo.addItem(_(_PRESET_LABELS.get(name, name)), name)
        presets.addWidget(self.presetCombo, 1)
        self.presetButton = QPushButton(_("Apply to the prize pool"))
        self.presetButton.clicked.connect(self.apply_preset)
        presets.addWidget(self.presetButton)
        layout.addLayout(presets)

        layout.addWidget(QLabel(_("Or paste the lobby's payouts, first place first:")))
        self.entry = QPlainTextEdit()
        self.entry.setPlaceholderText(
            _('One place per line ("1st  $45.00", "2: 30%"), or on one line: 45, 27, 18 or 50% 30% 20%')
        )
        self.entry.setFixedHeight(96)
        layout.addWidget(self.entry)

        actions = QHBoxLayout()
        self.clearButton = QPushButton(_("Forget the stored structure"))
        self.clearButton.setToolTip(_("Go back to the imported results, when they settle the payouts"))
        self.clearButton.clicked.connect(self.clear)
        actions.addWidget(self.clearButton)
        actions.addStretch()
        self.saveButton = QPushButton(_("Save"))
        self.saveButton.clicked.connect(self.save_entry)
        actions.addWidget(self.saveButton)
        layout.addLayout(actions)

        self.errorLabel = QLabel()
        self.errorLabel.setWordWrap(True)
        self.errorLabel.setStyleSheet("color: #d9534f;")
        layout.addWidget(self.errorLabel)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.refresh()

    def refresh(self) -> None:
        """Show the tournament's facts and the structure ICM uses for it now."""
        facts = tourney_payouts.tourney_facts(self.db, self.tourney_id)
        title = _("Tournament #%s") % facts.number if facts.number else _("Tournament")
        entries = str(facts.entries) if facts.entries else _("unknown")
        self.factsLabel.setText(
            _("%(title)s · %(entries)s entries · prize pool %(pool)s")
            % {"title": title, "entries": entries, "pool": _money(facts.prize_pool, facts.currency)}
        )
        lookup = tourney_payouts.payouts_for_tourney(self.db, self.tourney_id)
        if lookup.payouts is None:
            self.currentLabel.setText(_("No structure in use: %s") % lookup.reason)
        else:
            places = " / ".join(_money(amount, None) for amount in lookup.payouts.amounts)
            self.currentLabel.setText(
                _("In use: %(places)s %(currency)s (%(source)s)")
                % {
                    "places": places,
                    "currency": lookup.payouts.currency or "",
                    "source": self._source(lookup.payouts.source),
                }
            )
        self.clearButton.setEnabled(tourney_payouts.stored_payouts(self.db, self.tourney_id) is not None)

    @staticmethod
    def _source(source: str) -> str:
        if source.startswith(f"{tourney_payouts.SOURCE_PRESET}:"):
            name = source.split(":", 1)[1]
            return _("preset: %s") % _(_PRESET_LABELS.get(name, name))
        return _(_SOURCE_LABELS.get(source, source))

    def _stored(self, store: Any) -> bool:
        try:
            store()
        except ValueError as exc:
            self.errorLabel.setText(_("Not saved: %s") % exc)
            return False
        self.errorLabel.clear()
        self.changed = True
        self.refresh()
        return True

    def apply_preset(self) -> bool:
        preset = self.presetCombo.currentData()
        return self._stored(lambda: tourney_payouts.apply_preset(self.db, self.tourney_id, preset))

    def save_entry(self) -> bool:
        text = self.entry.toPlainText()
        if self._stored(
            lambda: tourney_payouts.store_entered(self.db, self.tourney_id, tourney_payouts.parse_structure(text))
        ):
            self.entry.clear()
            return True
        return False

    def clear(self) -> None:
        tourney_payouts.clear_payouts(self.db, self.tourney_id)
        self.changed = True
        self.errorLabel.clear()
        self.refresh()
