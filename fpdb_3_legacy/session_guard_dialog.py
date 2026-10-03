"""Session Guard in the main window: configure the limits, show where they stand (#395).

:class:`SessionGuardMonitor` reads the current session every half minute, with the main
window's database connection, and reports what :class:`~fpdb_3_legacy.session_guard.SessionGuard`
decides. The window shows it in three places, none of which blocks importing or the HUD:

* a status-bar indicator, always visible while the guard runs;
* a non-modal alert when a limit is reached, which can be acknowledged;
* the Tools > Session Guard dialog, which sets the limits and lists them.

Nothing here touches a poker client.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy.i18n import N_
from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.localized_formats import format_currency, format_number
from fpdb_3_legacy.loggingFpdb import get_logger
from fpdb_3_legacy.session_guard import (
    BB,
    DRAWDOWN_BB,
    DRAWDOWN_MONEY,
    DURATION,
    FIRED,
    GUARDS,
    HANDS,
    LOSS_BB,
    LOSS_MONEY,
    MONEY,
    SECONDS,
    UNITS,
    WIN_BB,
    WIN_MONEY,
    GuardLimits,
    GuardStatus,
    SessionGuard,
    SessionSnapshot,
    fetch_since,
    load_current_session,
    snapshot_of,
)

log = get_logger("session_guard")

#: How often the current session is read again: often enough for a duration limit to be
#: on time, rarely enough that a SELECT over a day of hands never competes with an import.
POLL_INTERVAL_MS = 30_000

GUARD_LABELS = {
    LOSS_MONEY: N_("Loss (money)"),
    LOSS_BB: N_("Loss (BB)"),
    WIN_MONEY: N_("Win (money)"),
    WIN_BB: N_("Win (BB)"),
    DURATION: N_("Session duration"),
    HANDS: N_("Hands"),
    DRAWDOWN_BB: N_("Drawdown from peak (BB)"),
    DRAWDOWN_MONEY: N_("Drawdown from peak (money)"),
}


def format_duration(seconds: float) -> str:
    minutes = int(seconds) // 60
    return f"{minutes // 60}:{minutes % 60:02d}"


def format_value(guard: str, value: float, currency: str | None) -> str:
    """A guard's value or threshold, in its own unit."""
    unit = UNITS[guard]
    if unit == MONEY:
        return format_currency(value / 100, currency or "USD")
    if unit == BB:
        return _("{value} BB").format(value=format_number(value, 1))
    if unit == SECONDS:
        return format_duration(value)
    return format_number(value, 0)


def describe(status: GuardStatus, currency: str | None) -> str:
    """``Loss (BB): 520.0 BB / 500.0 BB``, or why it cannot be measured."""
    label = _(GUARD_LABELS[status.guard])
    threshold = format_value(status.guard, status.threshold, currency)
    if status.value is None:
        return _("{label}: unavailable (a hand has no big blind) / {threshold}").format(
            label=label, threshold=threshold
        )
    return f"{label}: {format_value(status.guard, max(status.value, 0.0), currency)} / {threshold}"


class DurationEdit(QWidget):
    """An elapsed time in hours and minutes -- not a time of day, so a limit can pass 24 h."""

    MAX_HOURS = 999

    def __init__(self, seconds: int = 2 * 3600, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.hours = QSpinBox()
        self.hours.setRange(0, self.MAX_HOURS)
        self.hours.setSuffix(" h")
        self.minutes = QSpinBox()
        self.minutes.setRange(0, 59)
        self.minutes.setSuffix(" min")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.hours)
        layout.addWidget(self.minutes)
        self.set_seconds(seconds)

    def seconds(self) -> int:
        # A limit of 0 means nothing; the shortest one is a minute.
        return max(60, self.hours.value() * 3600 + self.minutes.value() * 60)

    def set_seconds(self, seconds: int) -> None:
        minutes = min(int(seconds) // 60, self.MAX_HOURS * 60 + 59)
        self.hours.setValue(minutes // 60)
        self.minutes.setValue(minutes % 60)


class SessionGuardMonitor(QObject):
    """Reads the current session on a timer and reports the guards that fire."""

    #: The status changed: a new reading, a limit changed, an alert acknowledged.
    changed = Signal()
    #: Guards that have just fired, each once (a list of :class:`GuardStatus`).
    alerts = Signal(list)

    def __init__(
        self,
        get_db: Callable[[], Any],
        get_config: Callable[[], Any],
        parent: QObject | None = None,
        *,
        clock: Callable[[], float] = time.time,
        interval_ms: int = POLL_INTERVAL_MS,
    ) -> None:
        super().__init__(parent)
        self.get_db = get_db
        self.get_config = get_config
        self.clock = clock
        self.guard: SessionGuard | None = None
        self.snapshot: SessionSnapshot | None = None
        self.timer = QTimer(self)
        self.timer.setInterval(interval_ms)
        self.timer.timeout.connect(self.poll)

    @property
    def active(self) -> bool:
        return self.guard is not None

    def start(self, limits: GuardLimits) -> None:
        """Watch the current session with *limits*; already running, change them."""
        if self.guard is None:
            self.guard = SessionGuard(limits)
        else:
            self.guard.set_limits(limits)
        self.timer.start()
        self.poll()

    def stop(self) -> None:
        self.timer.stop()
        self.guard = None
        self.snapshot = None
        self.changed.emit()

    def acknowledge(self) -> None:
        if self.guard is not None:
            self.guard.acknowledge()
            self.changed.emit()

    def reset(self) -> None:
        if self.guard is not None:
            self.guard.reset()
            self.poll()

    def hero_ids(self, db: Any) -> list[int]:
        """Every hero player id of every enabled site, aliases included."""
        config = self.get_config()
        ids: set[int] = set()
        for site in config.get_supported_sites() if config is not None else []:
            ids.update(int(player_id) for player_id in db.get_hero_player_ids(site) or [])
        return sorted(ids)

    def read_session(self) -> SessionSnapshot | None:
        db = self.get_db()
        if db is None:
            return None
        now = self.clock()
        try:
            session = load_current_session(fetch_since(db, self.hero_ids(db)), now)
        finally:
            self.end_read(db)
        return None if session is None else snapshot_of(session, now)

    @staticmethod
    def end_read(db: Any) -> None:
        """End the read's transaction on the shared connection.

        PostgreSQL and MySQL open one with the first SELECT; left open between polls, the
        connection would sit idle in a transaction for as long as the guard runs, and
        PostgreSQL maintenance that switches it to autocommit would fail. ``commit`` defers
        to a transaction block someone else has open, so it never ends theirs.
        """
        commit = getattr(db, "commit", None)
        if not callable(commit):
            return
        try:
            commit()
        except Exception:  # noqa: BLE001 - the reading itself succeeded or was already reported.
            log.exception("Session Guard could not end its read transaction")

    def poll(self) -> None:
        """Read the current session and report what fired; a failure is logged, never raised."""
        if self.guard is None:
            return
        try:
            snapshot = self.read_session()
        except Exception:  # noqa: BLE001 - a timer slot: a failed read must not stop the guard or reach Qt.
            log.exception("Session Guard could not read the current session")
            return
        self.snapshot = snapshot
        fired = self.guard.update(snapshot)
        self.changed.emit()
        if fired:
            self.alerts.emit(fired)

    def summary(self) -> str:
        """One line for the status bar."""
        if self.guard is None:
            return ""
        snapshot = self.snapshot
        if snapshot is None:
            return _("Session Guard: no session in progress")
        result = (
            _("{value} BB").format(value=format_number(snapshot.profit_bb, 1, show_plus=True))
            if snapshot.profit_bb is not None
            else format_currency(snapshot.profit_money / 100, snapshot.currency, show_plus=True)
        )
        text = _("Session Guard: {result} · {duration} · {hands} hands").format(
            result=result,
            duration=format_duration(snapshot.elapsed_seconds),
            hands=format_number(snapshot.hands, 0),
        )
        pending = self.guard.pending()
        if pending:
            text += " · " + _("{count} limit(s) reached").format(count=len(pending))
        return text


class SessionGuardIndicator(QPushButton):
    """The status-bar line: where the session stands, red while a limit is reached."""

    def __init__(self, monitor: SessionGuardMonitor, open_dialog: Callable[[], None], parent: QWidget | None = None):
        super().__init__(parent)
        self.monitor = monitor
        self.setFlat(True)
        self.setToolTip(_("Session Guard: click to see or change the limits"))
        self.clicked.connect(open_dialog)
        monitor.changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        self.setVisible(self.monitor.active)
        self.setText(self.monitor.summary())
        reached = self.monitor.guard is not None and bool(self.monitor.guard.pending())
        self.setStyleSheet("color: #d9534f; font-weight: bold;" if reached else "")


class SessionGuardAlert(QMessageBox):
    """A limit was reached: say which and where it stands, without blocking anything."""

    def __init__(self, monitor: SessionGuardMonitor, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.monitor = monitor
        self.setWindowTitle(_("Session Guard"))
        self.setIcon(QMessageBox.Icon.Warning)
        self.setModal(False)
        self.acknowledge_button = self.addButton(_("Acknowledge"), QMessageBox.ButtonRole.AcceptRole)
        self.addButton(_("Later"), QMessageBox.ButtonRole.RejectRole)
        self.acknowledge_button.clicked.connect(monitor.acknowledge)
        # Kept in step with the guard: a limit acknowledged in the dialog, switched off, or a
        # guard stopped closes the alert; one still pending updates its text.
        monitor.changed.connect(self.follow)

    def fill(self) -> bool:
        """Put the pending limits in the text; whether there is any."""
        guard = self.monitor.guard
        if guard is None or not guard.pending():
            return False
        currency = self.monitor.snapshot.currency if self.monitor.snapshot is not None else None
        self.setText(_("A Session Guard limit has been reached."))
        self.setInformativeText("\n".join(describe(status, currency) for status in guard.pending()))
        return True

    def follow(self) -> None:
        if not self.isVisible():
            return
        if not self.fill():
            self.hide()

    def show_pending(self) -> None:
        if not self.fill():
            return
        self.show()
        self.raise_()
        # Flash the taskbar entry rather than steal the focus from a poker table.
        QApplication.alert(self.parentWidget() or self)


class SessionGuardDialog(QDialog):
    """Set the limits of the current session and see where they stand."""

    def __init__(self, monitor: SessionGuardMonitor, config: Any = None, parent: QWidget | None = None) -> None:
        """*config* pins a configuration (tests); left out, the monitor's live one is used."""
        super().__init__(parent)
        self.monitor = monitor
        self._config = config
        self.setWindowTitle(_("Session Guard"))
        self.checks: dict[str, QCheckBox] = {}
        self.inputs: dict[str, QDoubleSpinBox | QSpinBox | DurationEdit] = {}

        limits_box = QGroupBox(_("Limits for this session"))
        grid = QGridLayout(limits_box)
        for row, guard in enumerate(GUARDS):
            check = QCheckBox(_(GUARD_LABELS[guard]))
            editor = self._editor(guard)
            check.toggled.connect(editor.setEnabled)
            editor.setEnabled(False)
            self.checks[guard] = check
            self.inputs[guard] = editor
            grid.addWidget(check, row, 0)
            grid.addWidget(editor, row, 1)

        self.status = QLabel()
        self.status.setWordWrap(True)
        note = QLabel(
            _(
                "Alerts only: fpdb never closes, sits out or otherwise touches a poker client. "
                "The session is the Session Viewer's: cash hands, ended by a 30-minute pause."
            )
        )
        note.setWordWrap(True)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.start_button = buttons.addButton(_("Start"), QDialogButtonBox.ButtonRole.ActionRole)
        self.stop_button = buttons.addButton(_("Stop"), QDialogButtonBox.ButtonRole.ActionRole)
        self.acknowledge_button = buttons.addButton(_("Acknowledge"), QDialogButtonBox.ButtonRole.ActionRole)
        self.reset_button = buttons.addButton(_("Reset alerts"), QDialogButtonBox.ButtonRole.ActionRole)
        self.defaults_button = buttons.addButton(_("Save as defaults"), QDialogButtonBox.ButtonRole.ActionRole)
        self.start_button.clicked.connect(self.start)
        self.stop_button.clicked.connect(monitor.stop)
        self.acknowledge_button.clicked.connect(monitor.acknowledge)
        self.reset_button.clicked.connect(monitor.reset)
        self.defaults_button.clicked.connect(self.save_defaults)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(limits_box)
        layout.addWidget(self.status)
        layout.addWidget(note)
        layout.addWidget(buttons)

        if monitor.guard is not None:
            self.set_limits(monitor.guard.limits)
        elif (current := self.config()) is not None and hasattr(current, "get_session_guard_defaults"):
            self.set_limits(GuardLimits.from_dict(current.get_session_guard_defaults()))
        monitor.changed.connect(self.refresh)
        self.refresh()

    @staticmethod
    def _editor(guard: str) -> QDoubleSpinBox | QSpinBox | DurationEdit:
        unit = UNITS[guard]
        if unit == SECONDS:
            return DurationEdit()
        if unit == MONEY:
            money = QDoubleSpinBox()
            money.setRange(0.01, 1_000_000)
            money.setDecimals(2)
            money.setValue(100)
            return money
        if unit == BB:
            bb = QDoubleSpinBox()
            bb.setRange(0.1, 1_000_000)
            bb.setDecimals(1)
            bb.setSuffix(" BB")
            bb.setValue(300)
            return bb
        count = QSpinBox()
        count.setRange(1, 10_000_000)
        count.setValue(1000)
        return count

    def limits(self) -> GuardLimits:
        values: dict[str, Any] = {}
        for guard, check in self.checks.items():
            if not check.isChecked():
                continue
            editor = self.inputs[guard]
            unit = UNITS[guard]
            if isinstance(editor, DurationEdit):
                values[guard] = editor.seconds()
            elif unit == MONEY:
                values[guard] = round(editor.value() * 100)
            else:
                values[guard] = editor.value()
        return GuardLimits(**values)

    def set_limits(self, limits: GuardLimits) -> None:
        for guard in GUARDS:
            value = getattr(limits, guard)
            self.checks[guard].setChecked(value is not None)
            if value is None:
                continue
            editor = self.inputs[guard]
            if isinstance(editor, DurationEdit):
                editor.set_seconds(int(value))
            elif UNITS[guard] == MONEY:
                editor.setValue(value / 100)
            else:
                editor.setValue(value)

    def start(self) -> None:
        limits = self.limits()
        if not limits.enabled():
            QMessageBox.information(self, _("Session Guard"), _("Choose at least one limit to watch."))
            return
        self.monitor.start(limits)

    def config(self) -> Any:
        """The configuration as it is now.

        Looked up each time, not kept: the dialog is modeless, and a reload elsewhere (HUD
        Preferences, a profile) replaces the window's configuration while it is open. Saving
        through the old one would write its stale document over the newer one.
        """
        return self._config if self._config is not None else self.monitor.get_config()

    def save_defaults(self) -> None:
        config = self.config()
        if config is None or not hasattr(config, "set_session_guard_defaults"):
            return
        try:
            config.set_session_guard_defaults(self.limits().to_dict())
        except OSError as exc:
            QMessageBox.warning(self, _("Session Guard"), _("Could not save the defaults:\n%s") % exc)

    def refresh(self) -> None:
        active = self.monitor.active
        self.start_button.setText(_("Apply") if active else _("Start"))
        self.stop_button.setEnabled(active)
        guard = self.monitor.guard
        self.acknowledge_button.setEnabled(guard is not None and bool(guard.pending()))
        self.reset_button.setEnabled(active)
        if not active or guard is None:
            self.status.setText(_("Not running."))
            return
        lines = [self.monitor.summary()]
        currency = self.monitor.snapshot.currency if self.monitor.snapshot is not None else None
        for status in guard.statuses:
            marker = "⚠ " if status.state == FIRED else ("✓ " if status.reached else "")
            lines.append(marker + describe(status, currency))
        self.status.setText("\n".join(lines))
