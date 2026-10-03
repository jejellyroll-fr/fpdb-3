"""Offscreen checks for the Session Guard dialog, monitor and indicator (#395)."""

from __future__ import annotations

import datetime
import sqlite3
from pathlib import Path

import pytest
from PySide6.QtWidgets import QMessageBox

from fpdb_3_legacy.session_guard import (
    DURATION,
    FIRED,
    GUARDS,
    HANDS,
    LOSS_BB,
    LOSS_MONEY,
    WIN_BB,
    GuardLimits,
)
from fpdb_3_legacy.session_guard_dialog import (
    DurationEdit,
    SessionGuardAlert,
    SessionGuardDialog,
    SessionGuardIndicator,
    SessionGuardMonitor,
)

pytestmark = pytest.mark.qt

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "hands" / "pokerstars"
#: review/nl_3bet_6max.txt: 20:00 ET on 2026-09-01, so midnight UTC. Hero opens, calls a
#: 3-bet to $8 and folds the flop: -$8.00, -8 BB at $0.50/$1.
HAND_TIME = datetime.datetime(2026, 9, 2, tzinfo=datetime.timezone.utc).timestamp()


class Defaults:
    """Stands in for the configuration: never the real HUD_config.xml."""

    def __init__(self, saved: dict | None = None) -> None:
        self.saved = dict(saved or {})
        self.writes: list[dict | None] = []

    def get_session_guard_defaults(self) -> dict:
        return {key: str(value) for key, value in self.saved.items()}

    def set_session_guard_defaults(self, limits: dict | None) -> None:
        self.writes.append(limits)
        self.saved = dict(limits or {})

    def get_supported_sites(self) -> list[str]:
        return []


def idle_monitor(qtbot) -> SessionGuardMonitor:
    """A monitor with no database: it never finds a session."""
    monitor = SessionGuardMonitor(lambda: None, lambda: None, clock=lambda: HAND_TIME)
    return monitor


@pytest.fixture
def imported(importer, fresh_db, tmp_path):
    source = FIXTURES / "review" / "nl_3bet_6max.txt"
    copy = tmp_path / source.name
    copy.write_bytes(source.read_bytes())
    importer.addImportFile(str(copy), "PokerStars")
    assert importer.runImport()[0] == 1
    connection = sqlite3.connect(fresh_db.database)
    connection.row_factory = sqlite3.Row
    hero = dict(connection.execute("SELECT * FROM Players WHERE name = 'Hero'").fetchone())
    connection.close()
    return fresh_db, hero["id"]


def watching(qtbot, db, hero_id, monkeypatch, now: float) -> SessionGuardMonitor:
    monitor = SessionGuardMonitor(lambda: db, lambda: Defaults(), clock=lambda: now)
    monkeypatch.setattr(monitor, "hero_ids", lambda _db: [hero_id])
    return monitor


# -- the dialog -------------------------------------------------------------------


def test_each_guard_is_enabled_on_its_own(qtbot) -> None:
    dialog = SessionGuardDialog(idle_monitor(qtbot))
    qtbot.addWidget(dialog)

    assert dialog.limits() == GuardLimits()
    assert not any(editor.isEnabled() for editor in dialog.inputs.values())

    dialog.checks[LOSS_BB].setChecked(True)
    dialog.inputs[LOSS_BB].setValue(500)
    assert dialog.inputs[LOSS_BB].isEnabled()
    assert dialog.limits() == GuardLimits(loss_bb=500)

    dialog.checks[HANDS].setChecked(True)
    dialog.inputs[HANDS].setValue(1000)
    dialog.checks[LOSS_BB].setChecked(False)
    assert not dialog.inputs[LOSS_BB].isEnabled()
    assert dialog.limits() == GuardLimits(hands=1000)


def test_money_is_entered_in_currency_and_kept_in_cents(qtbot) -> None:
    dialog = SessionGuardDialog(idle_monitor(qtbot))
    qtbot.addWidget(dialog)

    dialog.checks[LOSS_MONEY].setChecked(True)
    dialog.inputs[LOSS_MONEY].setValue(250.5)
    dialog.checks[DURATION].setChecked(True)
    duration = dialog.inputs[DURATION]
    assert isinstance(duration, DurationEdit)
    duration.hours.setValue(2)
    duration.minutes.setValue(30)

    assert dialog.limits() == GuardLimits(loss_money=25_050, duration=9000)


def test_starting_without_a_limit_says_so(qtbot, monkeypatch) -> None:
    told: list[str] = []
    monkeypatch.setattr(QMessageBox, "information", lambda _parent, _title, text: told.append(text))
    monitor = idle_monitor(qtbot)
    dialog = SessionGuardDialog(monitor)
    qtbot.addWidget(dialog)

    dialog.start_button.click()

    assert told
    assert not monitor.active


def test_the_dialog_starts_and_stops_the_monitor(qtbot) -> None:
    monitor = idle_monitor(qtbot)
    dialog = SessionGuardDialog(monitor)
    qtbot.addWidget(dialog)
    indicator = SessionGuardIndicator(monitor, lambda: None)
    qtbot.addWidget(indicator)
    assert indicator.isHidden()

    dialog.checks[WIN_BB].setChecked(True)
    dialog.start_button.click()

    assert monitor.active
    assert monitor.timer.isActive()
    assert dialog.start_button.text() == "Apply"
    assert not indicator.isHidden()
    assert indicator.text() == "Session Guard: no session in progress"

    dialog.stop_button.click()

    assert not monitor.active
    assert not monitor.timer.isActive()
    assert indicator.isHidden()


def test_defaults_are_saved_and_offered_next_time(qtbot) -> None:
    config = Defaults()
    dialog = SessionGuardDialog(idle_monitor(qtbot), config)
    qtbot.addWidget(dialog)
    dialog.checks[LOSS_BB].setChecked(True)
    dialog.inputs[LOSS_BB].setValue(500)

    dialog.defaults_button.click()

    assert config.writes == [{LOSS_BB: 500.0}]
    again = SessionGuardDialog(idle_monitor(qtbot), config)
    qtbot.addWidget(again)
    assert again.limits() == GuardLimits(loss_bb=500)
    assert [guard for guard in GUARDS if again.checks[guard].isChecked()] == [LOSS_BB]


# -- the monitor, over a real database -------------------------------------------


def test_a_limit_reached_in_the_database_fires_once_and_is_acknowledged(qtbot, imported, monkeypatch) -> None:
    db, hero_id = imported
    monitor = watching(qtbot, db, hero_id, monkeypatch, now=HAND_TIME + 60)
    alerts: list[list] = []
    monitor.alerts.connect(alerts.append)
    indicator = SessionGuardIndicator(monitor, lambda: None)
    qtbot.addWidget(indicator)

    monitor.start(GuardLimits(loss_bb=5, loss_money=1000, hands=10))

    assert monitor.snapshot is not None
    assert monitor.snapshot.profit_bb == pytest.approx(-8)
    assert monitor.snapshot.profit_money == pytest.approx(-800)
    assert [[status.guard for status in fired] for fired in alerts] == [[LOSS_BB]]
    assert "1 limit(s) reached" in indicator.text()
    assert "bold" in indicator.styleSheet()

    monitor.poll()  # the next reading: nothing new to say
    assert len(alerts) == 1

    monitor.acknowledge()
    assert monitor.guard.pending() == []
    assert "limit(s) reached" not in indicator.text()


def test_a_session_that_ended_is_not_watched(qtbot, imported, monkeypatch) -> None:
    db, hero_id = imported
    monitor = watching(qtbot, db, hero_id, monkeypatch, now=HAND_TIME + 3 * 3600)
    alerts: list[list] = []
    monitor.alerts.connect(alerts.append)

    monitor.start(GuardLimits(loss_bb=5))

    assert monitor.snapshot is None
    assert alerts == []


def test_the_alert_names_the_limit_and_its_value(qtbot, imported, monkeypatch) -> None:
    db, hero_id = imported
    monitor = watching(qtbot, db, hero_id, monkeypatch, now=HAND_TIME + 60)
    alert = SessionGuardAlert(monitor)
    qtbot.addWidget(alert)
    monitor.alerts.connect(lambda _fired: alert.show_pending())

    monitor.start(GuardLimits(loss_bb=5))

    assert alert.isVisible()
    assert not alert.isModal(), "an alert never blocks importing or the HUD"
    assert "Loss (BB): 8.0 BB / 5.0 BB" in alert.informativeText()

    alert.acknowledge_button.click()
    assert monitor.guard.statuses[0].state != FIRED


def test_a_failed_reading_is_logged_and_the_guard_keeps_running(qtbot) -> None:
    def broken():
        raise RuntimeError("database went away")

    monitor = SessionGuardMonitor(broken, lambda: None, clock=lambda: HAND_TIME)
    monitor.start(GuardLimits(hands=1))

    assert monitor.active
    assert monitor.timer.isActive()
    monitor.stop()


def test_the_hero_is_found_the_way_the_viewers_find_it(qtbot, imported) -> None:
    """Hero ids are every enabled site's: its hero aliases, or else the players imported as hero."""
    db, hero_id = imported

    class Sites(Defaults):
        def get_supported_sites(self) -> list[str]:
            return ["PokerStars.COM"]

    monitor = SessionGuardMonitor(lambda: db, Sites, clock=lambda: HAND_TIME + 60)

    assert monitor.hero_ids(db) == [hero_id]
    monitor.start(GuardLimits(loss_bb=5))
    assert monitor.snapshot is not None
    assert monitor.snapshot.hands == 1
    monitor.stop()


def test_a_duration_can_pass_a_day(qtbot) -> None:
    """An elapsed time, not a time of day: a saved 25-hour limit is not read back as 01:00."""
    dialog = SessionGuardDialog(idle_monitor(qtbot), Defaults({DURATION: 25 * 3600}))
    qtbot.addWidget(dialog)

    assert dialog.limits() == GuardLimits(duration=25 * 3600)
    dialog.inputs[DURATION].hours.setValue(36)
    assert dialog.limits() == GuardLimits(duration=36 * 3600)


def test_an_open_alert_follows_the_guard(qtbot, imported, monkeypatch) -> None:
    db, hero_id = imported
    monitor = watching(qtbot, db, hero_id, monkeypatch, now=HAND_TIME + 60)
    alert = SessionGuardAlert(monitor)
    qtbot.addWidget(alert)
    monitor.alerts.connect(lambda _fired: alert.show_pending())

    monitor.start(GuardLimits(loss_bb=5))
    assert alert.isVisible()
    monitor.acknowledge()  # from the dialog, not from the alert
    assert not alert.isVisible()

    monitor.reset()  # fires again, and shows again
    assert alert.isVisible()
    monitor.stop()
    assert not alert.isVisible()


def test_every_reading_ends_its_transaction(qtbot, imported, monkeypatch) -> None:
    """PostgreSQL and MySQL open one with the first SELECT; the guard must not leave it open."""
    db, hero_id = imported
    commits: list[int] = []
    monkeypatch.setattr(db, "commit", lambda *args, **kwargs: commits.append(1))
    monitor = watching(qtbot, db, hero_id, monkeypatch, now=HAND_TIME + 60)

    monitor.start(GuardLimits(hands=10))
    monitor.poll()

    assert len(commits) == 2
    monitor.stop()


def test_defaults_are_saved_to_the_configuration_of_the_moment(qtbot) -> None:
    """A reload replaces the window's configuration while the modeless dialog is open."""
    window = {"config": Defaults()}
    monitor = SessionGuardMonitor(lambda: None, lambda: window["config"], clock=lambda: HAND_TIME)
    dialog = SessionGuardDialog(monitor)
    qtbot.addWidget(dialog)
    dialog.checks[HANDS].setChecked(True)

    stale = window["config"]
    window["config"] = Defaults()  # HUD Preferences reloaded the configuration
    dialog.defaults_button.click()

    assert stale.writes == []
    assert window["config"].writes == [{HANDS: 1000}]
