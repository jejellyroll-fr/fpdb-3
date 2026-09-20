#!/usr/bin/env python
from __future__ import annotations

import os

# OPTION A : on veut XWayland si la variable est posée
if os.getenv("FPDB_FORCE_X11") == "1":
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

import hashlib
import json
import subprocess
import sys
import threading
import time
import traceback
from contextlib import suppress
from optparse import OptionParser
from pathlib import Path
from typing import Any

try:
    import interlocks
except ImportError:
    from fpdb_3_legacy import interlocks
from PySide6.QtCore import QDateTime, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QPalette, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy import Configuration, Importer
from fpdb_3_legacy.hud_diagnostics import session_id
from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.interlocks import (
    HUD_ALREADY_RUNNING_EXIT_CODE,
    HUD_LOCK_UNDETERMINED_EXIT_CODE,
    read_lock_owner,
)
from fpdb_3_legacy.loggingFpdb import get_logger
from fpdb_3_legacy.subprocess_launch import hud_main_command

# Import for dynamic reloading configuration
try:
    from AutoImportConfigObserver import AutoImportConfigObserver

    from fpdb_3_legacy.ConfigurationManager import ConfigurationManager

    DYNAMIC_CONFIG_AVAILABLE = True
except ImportError:
    DYNAMIC_CONFIG_AVAILABLE = False
    log = get_logger("gui_auto_import")
    log.warning("ConfigurationManager not available, dynamic config reload disabled")

if __name__ == "__main__":
    Configuration.set_logfile("fpdb-log.txt")
# logging has been set up in fpdb.py or HUD_main.py, use their settings:
log = get_logger("gui_auto_import")

if os.name == "nt":
    try:
        import win32console
    except ImportError:
        # pywin32 is optional (e.g. not installed in CI); console detection for
        # the HUD launch degrades gracefully when it is unavailable.
        win32console = None


# Import cycles overrunning their interval back to back. One or two is a large
# batch; this many means the worker is wedged and the user deserves to be told.
DEFERRED_CYCLES_BEFORE_WARNING = 6

# How long "Stop Auto Import" waits for the worker before giving up on it. Long
# enough for an ordinary cycle to land, short enough not to read as a freeze.
STOP_WAIT_MS = 5000

# The one room with no hand history files, and so the only one the native
# capture has anything to do for.
SWC_SITE_NAME = "SealsWithClubs"


def to_raw(string) -> str:
    return rf"{string}"


class AutoImportThread(QThread):
    """Worker thread to run auto-import cycle off the main GUI thread."""

    finished = Signal()
    error = Signal(str)
    db_offline = Signal()

    def __init__(self, importer, db_write_lock: threading.Lock | None = None) -> None:
        super().__init__()
        self.importer = importer
        self.db_write_lock = db_write_lock

    def run(self) -> None:
        # Held for the whole cycle: the importer's database is one connection
        # with one set of bulk buffers, and the live SwC hand callback would
        # otherwise write through both from the GUI thread mid-cycle.
        lock = self.db_write_lock
        if lock is not None:
            lock.acquire()
        try:
            # Checked here rather than left to fail mid-cycle so the GUI can say
            # the database is away, instead of reporting a raw driver error once
            # every interval for as long as the outage lasts.
            if not self.importer.database.ensure_connection():
                self.db_offline.emit()
                return
            self.importer.autoSummaryGrab()
            self.importer.runUpdated()
            self.finished.emit()
        except Exception as e:  # intentional broad catch: Qt worker thread surfaces any failure via the error signal
            self.error.emit(str(e))
        finally:
            if lock is not None:
                lock.release()


def _hand_snapshot_fingerprint(hand: dict) -> str:
    """Content hash of one normalized hand, so an unchanged snapshot is not re-offered."""
    return hashlib.sha256(json.dumps(hand, sort_keys=True, default=str).encode("utf-8")).hexdigest()


class SwCWindowsAttachThread(QThread):
    """Load the tap into the running SwC client without stopping the GUI.

    ``attach_to_windows_client`` compiles the tap and the injector, enumerates
    processes, runs the injector once per client and then waits for each to
    report that it has hooked its TLS library. The client loads that library
    lazily, so a lobby with no table open never reports and the wait runs its
    full ten seconds -- the ordinary case when Auto Import is switched on before
    sitting down. Called straight from startClicked, that was ten seconds with
    the Qt event loop stopped, which reads as a frozen application.

    The tailing thread does not wait for this: it reads the archive, and an
    archive that is not growing yet simply yields nothing.
    """

    attached = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cancel_requested = False

    def cancel(self) -> None:
        """Abandon the attach if the tap has not been injected yet.

        Stopping Auto Import used to leave this worker running: the stop waited
        a second, gave up, and finalized, while the worker went on to inject.
        The tap has no unload path, so that injection outlived the stop -- the
        DLL stayed resident in the client and kept writing decrypted traffic to
        the archive until the client exited, with the GUI saying capture was
        off. The worker cannot be interrupted inside a compiler or an injector
        call, so it reads this before the one step that cannot be undone.
        """
        self._cancel_requested = True

    @property
    def cancelled(self) -> bool:
        """Whether this attach has been told to abandon its injection."""
        return self._cancel_requested

    def run(self) -> None:
        from fpdb_3_legacy.swc_native_capture import CaptureAttachCancelled, attach_to_windows_client

        try:
            self.attached.emit(attach_to_windows_client(should_cancel=lambda: self._cancel_requested))
        except CaptureAttachCancelled as exc:
            # Nothing was injected and nothing is wrong: the user stopped the
            # capture. Reported to the log, never to the user as a failure.
            log.info("SwC tap attachment abandoned: %s", exc)
        except Exception as exc:  # noqa: BLE001 - reported to the user, never raised into Qt
            log.warning("Could not attach the SwC tap: %s", exc)
            self.attached.emit(
                _("SwC live capture could not attach: {reason}. Importing SwC hand history files still works.").format(
                    reason=exc,
                ),
            )


class SwCNativeTailingThread(QThread):
    """Background thread tailing raw SwC native capture and importing live hands."""

    hand_imported = Signal(dict)

    #: A hand needs the messages around it to be reconstructed, so decoded
    #: messages are retained across polls rather than re-read from disk. This
    #: caps that history: a long session would otherwise grow it without bound.
    MAX_RETAINED_MESSAGES = 20000

    #: An attempt that was not terminal is repeated on a delay that doubles to a
    #: cap, for a bounded number of offers. Both ends matter: the reasons to
    #: retry clear on their own (an import cycle finishes, the database comes
    #: back, the text history of the hand lands), while a hand that will never
    #: be importable must not reach the database every 2.5s for the rest of the
    #: session. At these values a hand is retried for about nine minutes.
    MAX_RETRY_OFFERS = 20
    RETRY_BACKOFF_SECONDS = 2.5
    RETRY_BACKOFF_CAP_SECONDS = 30.0

    #: Ceiling on the doubling exponent, so the backoff arithmetic stays finite
    #: however long an outage runs (see _retry_delay). Far beyond the four
    #: doublings these constants need to reach the cap; it exists only to keep
    #: 2 ** n representable, not to shape the delay.
    MAX_BACKOFF_DOUBLINGS = 64

    def __init__(self, raw_path: Any = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        default = Path.home() / ".fpdb" / "swc-native-capture" / "swc-native.raw"
        self.raw_path = Path(raw_path or default).expanduser().resolve()
        self._stop_requested = False
        # Hands are decoded while they are still being played, so a first
        # snapshot is routinely not importable yet and the same hand has to be
        # offered again once later records complete it. Only a terminal import
        # result retires a key; until then a snapshot is re-emitted when its
        # content changes, or when a retry was asked for. The GUI thread writes
        # these through the methods below while this thread reads them in
        # poll_once, hence the lock.
        self._state_lock = threading.Lock()
        self._completed_keys: set[tuple[int, int]] = set()
        self._emitted: dict[tuple[int, int], str] = {}
        self._capture_only_keys: set[tuple[int, int]] = set()
        self._retry_offers: dict[tuple[int, int], int] = {}
        self._retry_after: dict[tuple[int, int], float] = {}
        # The envelope each deferred hand was last offered as. A retry must not
        # depend on the hand still being reconstructible from the rolling message
        # window: a finished hand produces no more records, so once busy tables
        # push its snapshots out of that window normalization can never return it
        # again, and the deadline would come due forever with nothing to offer.
        self._pending_envelopes: dict[tuple[int, int], dict] = {}
        self._offset = 0
        self._messages: list[Any] = []
        # Kept across polls: a protocol message routinely spans two batches, and
        # a decoder rebuilt each poll loses the half it was holding.
        self._protocol_stream: Any = None
        # The latest descriptor per (source, table), exempt from the rolling trim.
        self._table_messages: dict[tuple[int, int], Any] = {}
        self._consecutive_errors = 0

    def stop(self) -> None:
        self._stop_requested = True

    @property
    def stopping(self) -> bool:
        """Whether this thread was told to stop, however long it takes to notice.

        A poll that is normalizing a full message window outlasts the wait the
        stop path gives it, so a thread can be both running and finished with.
        """
        return self._stop_requested

    @staticmethod
    def _hand_key(hand_data: dict) -> tuple[int, int]:
        return (hand_data.get("table_id", 0), hand_data.get("hand_id", 0))

    def mark_hand_complete(self, hand_data: dict) -> None:
        """Retire a hand whose import reached a terminal result (imported, duplicate, updated)."""
        key = self._hand_key(hand_data)
        with self._state_lock:
            self._completed_keys.add(key)
            self._emitted.pop(key, None)
            self._capture_only_keys.discard(key)
            self._retry_offers.pop(key, None)
            self._retry_after.pop(key, None)
            self._pending_envelopes.pop(key, None)

    def retry_hand(self, hand_data: dict, *, transient: bool = False) -> None:
        """Offer this hand again later even though its snapshot has not changed.

        For an attempt that was not terminal: the importer could not use the
        hand yet, the database raised, or an auto-import cycle owned the
        connection. Waiting for new capture content instead lost the hand,
        because a finished hand produces no more records.

        ``transient`` says the refusal came from outside the hand -- a busy
        connection, a database that is away. Nothing about the hand will change
        to fix that, and nothing about it is wrong, so it keeps its place in the
        queue at the capped interval for as long as the outage lasts. The budget
        applies only to a hand the importer itself judged unusable: that verdict
        cannot change while its snapshot does not, so re-offering it forever
        would be work with no possible result.
        """
        key = self._hand_key(hand_data)
        with self._state_lock:
            offers = self._retry_offers.get(key, 0) + 1
            if offers > self.MAX_RETRY_OFFERS and not transient:
                # Budget spent: drop the deadline too, or the elapsed one left
                # behind would keep re-offering this hand every poll.
                self._retry_after.pop(key, None)
                self._pending_envelopes.pop(key, None)
                return
            self._retry_offers[key] = offers
            delay = self._retry_delay(offers)
            self._retry_after[key] = time.monotonic() + delay
            # Held so the hand can be offered again from what it was, not from
            # what the message window still happens to contain.
            self._pending_envelopes[key] = hand_data

    def _retry_delay(self, offers: int) -> float:
        """How long before this offer is repeated: doubling, then held at the cap.

        The exponent is clamped before it is built. ``2 ** (offers - 1)`` is an
        arbitrary-precision int, and past ``2 ** 1024`` multiplying it by a float
        raises OverflowError instead of being capped by the ``min`` around it --
        and a transient refusal has no offer limit by design, so ``offers`` really
        does get there: about 8.5 hours of an outage at the 30s cap. The raise
        landed after the offer count had been stored but before the new deadline
        was, leaving the elapsed one in place, so the hand was re-offered every
        poll while every attempt to reschedule it failed the same way.

        The clamp is only there to keep the arithmetic finite; the cap below is
        what actually bounds the wait, and with these constants it is reached
        after four doublings.
        """
        # Read off self, not the class: these are tunables, and the tests (and any
        # subclass) set them per instance.
        doublings = min(max(offers - 1, 0), self.MAX_BACKOFF_DOUBLINGS)
        return min(self.RETRY_BACKOFF_SECONDS * (2**doublings), self.RETRY_BACKOFF_CAP_SECONDS)

    def note_capture_only(self, hand_data: dict) -> bool:
        """Whether this hand is being reported as not-yet-importable for the first time.

        "Capture-only" is a passing state rather than a verdict, so the hand
        stays eligible; this only keeps the log from repeating it every poll.
        """
        key = self._hand_key(hand_data)
        with self._state_lock:
            if key in self._capture_only_keys:
                return False
            self._capture_only_keys.add(key)
            return True

    def _retry_is_due(self, now: float) -> bool:
        """Whether a deferred hand's delay has elapsed, so a poll is worth doing.

        A hand is deferred precisely when it is *finished* and something outside
        the capture refused it -- an auto-import cycle held the connection, the
        database raised, or it is waiting for its text history. A finished hand
        produces no further records, so waiting for new bytes before looking at
        the deadline is waiting for something that never comes: the retry has to
        be reachable on an idle archive or it never fires at all.
        """
        with self._state_lock:
            return any(
                deadline <= now for key, deadline in self._retry_after.items() if key not in self._completed_keys
            )

    def _forget_partial_frame(self) -> None:
        """Drop the decoder when the archive is truncated or rotated.

        The decoder is kept across polls so a message split over two polls still
        decodes, which means it can be holding the old archive's half-written
        tail. Feeding the new archive's first bytes onto that splices two
        unrelated streams together: the resynchronizer then has to throw away
        real records before it finds an anchor it can trust.

        Only the decoder goes. The retained messages, the table descriptors, the
        emitted and completed hand keys, the retry ledger and the deferred
        envelopes are all keyed by hand, not by byte offset -- clearing them
        would re-offer hands already imported, blind every table whose descriptor
        the new archive has not re-announced yet, and lose hands still waiting
        for a retry.
        """
        self._protocol_stream = None

    def poll_once(self) -> list[dict]:
        """Decode whatever was appended since the last call and return new hands.

        Split out of the polling loop so the decode path can be exercised without
        starting a thread or waiting on its timing.

        A hand already offered is returned again only when its snapshot changed,
        or when a retry was asked for and its delay has elapsed, and never once
        a terminal import result retired it. That is what lets a hand decoded
        mid-play be imported once its later records arrive.
        """
        from fpdb_3_legacy.swc_native_capture import (
            NativeProtocolStream,
            extract_table_info,
            normalize_native_hands,
            read_records_since,
        )

        records, self._offset = read_records_since(
            self.raw_path,
            self._offset,
            on_restart=self._forget_partial_frame,
        )
        now = time.monotonic()

        if records:
            if self._protocol_stream is None:
                self._protocol_stream = NativeProtocolStream()
            decoded = self._protocol_stream.feed(records)
            for message in decoded:
                # A table descriptor is what names a table id and its game, and
                # normalize_native_hands rebuilds its table map from the message
                # list alone. Held separately so the rolling trim below cannot
                # drop the descriptor of a table that is still being played --
                # every later hand from it would otherwise become invisible.
                info = extract_table_info(message)
                if info is not None:
                    # Keyed by source as well as table, because normalization is
                    # partitioned by source: two clients watching one table would
                    # otherwise leave a single descriptor, belonging to whichever
                    # announced it last. Once the trim dropped the active client's
                    # own copy, its snapshots would have no table metadata and all
                    # its later hands would disappear.
                    self._table_messages[getattr(message, "source_id", 0), info.table_id] = message
            self._messages.extend(decoded)
            if len(self._messages) > self.MAX_RETAINED_MESSAGES:
                del self._messages[: len(self._messages) - self.MAX_RETAINED_MESSAGES]
        elif not self._retry_is_due(now):
            # Nothing new to decode and nothing waiting to be re-offered:
            # normalizing the retained buffer again could not produce a hand this
            # poll, and it is the expensive half of the work.
            return []
        fresh: list[dict] = []
        # Descriptors first: a duplicate of one still in _messages is harmless
        # (the table map is a dict, and a descriptor yields no snapshot).
        retained = [*self._table_messages.values(), *self._messages]
        for hand in normalize_native_hands(retained, raw_ref=str(self.raw_path)):
            key = self._hand_key(hand)
            fingerprint = _hand_snapshot_fingerprint(hand)
            with self._state_lock:
                if key in self._completed_keys:
                    continue
                offered_before = self._emitted.get(key)
                if offered_before == fingerprint:
                    retry_after = self._retry_after.get(key)
                    if retry_after is None or now < retry_after:
                        continue
                elif offered_before is not None:
                    # New content is new information, so the retry budget is not
                    # spent by a hand still being played: it bounds how often an
                    # unchanged, refused snapshot is repeated.
                    self._retry_offers.pop(key, None)
                self._emitted[key] = fingerprint
                # The deadline is spent by the offer, not by the answer to it.
                # Left standing it went on reading as due until the GUI callback
                # got round to this hand -- and that callback is queued onto a
                # thread that may be inside a database import, while this poll
                # comes round every 2.5s. Every poll in between re-offered the
                # same hand: the backoff was ignored, one refusal spent several
                # of the retry budget's offers, and a hand the first callback
                # imported was imported again by the ones queued behind it.
                # Removing it here is what "in flight" means: the hand is not
                # due again until its callback completes it or asks for another
                # turn.
                self._retry_after.pop(key, None)
                # A fresher view supersedes the copy held for the retry.
                if key in self._pending_envelopes:
                    self._pending_envelopes[key] = hand
            fresh.append(hand)
        fresh.extend(self._due_pending_envelopes(now, {self._hand_key(hand) for hand in fresh}))
        return fresh

    def _due_pending_envelopes(self, now: float, already_offered: set[tuple[int, int]]) -> list[dict]:
        """Deferred hands whose delay has elapsed but that normalization no longer yields.

        A hand is only deferred once it is finished, so it produces no further
        records; once busy tables push its snapshots past MAX_RETAINED_MESSAGES it
        can never be rebuilt from the window again. Without the copy kept at
        deferral, its deadline would come due forever with nothing behind it --
        and, because a transient refusal has no budget, forever really means it.
        """
        due: list[dict] = []
        with self._state_lock:
            for key, deadline in list(self._retry_after.items()):
                if key in already_offered or key in self._completed_keys or deadline > now:
                    continue
                envelope = self._pending_envelopes.get(key)
                if envelope is not None:
                    # Spent by the offer, exactly as in poll_once: the copy stays
                    # so a later refusal can be offered from it again, but the
                    # deadline goes, so the polls between this offer and its
                    # answer do not hand out the same hand over and over.
                    self._retry_after.pop(key, None)
                    due.append(envelope)
        return due

    def run(self) -> None:
        while not self._stop_requested:
            try:
                for hand in self.poll_once():
                    self.hand_imported.emit(hand)
                self._consecutive_errors = 0
            except Exception:
                # One failure is unremarkable while the tap is mid-write; a run of
                # them means the archive is unreadable and the user is silently
                # getting no hands, so say so instead of hiding it at debug level.
                self._consecutive_errors += 1
                if self._consecutive_errors in (1, 10, 100):
                    log.warning(
                        "SwC native tailing failed %d time(s) reading %s",
                        self._consecutive_errors,
                        self.raw_path,
                        exc_info=True,
                    )
            for _step in range(10):
                if self._stop_requested:
                    break
                time.sleep(0.25)


class GuiAutoImport(QWidget):
    log_message = Signal(str, str)

    def __init__(self, settings, config, sql=None, parent=None, cli=False) -> None:
        if not cli:
            QWidget.__init__(self, parent)
            self.log_message.connect(self._addText_slot)
        self.importtimer: QTimer | None = None
        self.import_thread: AutoImportThread | None = None
        self.swc_tailing_thread: SwCNativeTailingThread | None = None
        self.swc_attach_thread: SwCWindowsAttachThread | None = None
        # Cancelled attach workers still unwinding. They are parentless -- CLI
        # mode skips QWidget.__init__, so nothing but a reference can own one --
        # and dropping the last reference to a running QThread destroys it
        # mid-run, so a restart parks the old worker here until it has exited.
        self._retiring_attach_threads: list[SwCWindowsAttachThread] = []
        # One writer at a time on the importer's database: a single connection
        # with a single set of bulk buffers, which no driver here lets two
        # threads drive at once (see Database._create_new_worker_connection).
        # AutoImportThread holds it for a whole cycle; the live SwC hand
        # callback tries it without blocking, since that one runs on the GUI
        # thread and a cycle can take minutes.
        self.db_write_lock = threading.Lock()
        # Outage bookkeeping, so the database going away is reported once rather
        # than once per interval, and its return is reported too.
        self._deferred_cycles = 0
        self._db_offline = False
        # When Stop's bounded wait expires, cleanup is deferred until the
        # worker really exits. The importer, its database connection and the
        # global lock must remain exclusively owned by that worker meanwhile.
        self._stop_cleanup_pending = False
        self.settings = settings
        self.config = config
        self.sql = sql
        self.parent = parent

        self.pipe_to_hud: subprocess.Popen[Any] | None = None
        self.doAutoImportBool = False

        self.cli = cli

        self.importer = Importer.Importer(self, self.settings, self.config, self.sql)

        self.importer.setCallHud(True)
        self.importer.setQuiet(False)
        self.importer.setHandCount(0)
        self.importer.setMode("auto")

        self.server = settings["db-host"]
        self.user = settings["db-user"]
        self.password = settings["db-password"]
        self.database = settings["db-databaseName"]

        if cli is False:
            self.setupGui()
            self._setup_config_observer()
        # In headless (cli) mode there is no GUI to build and no config observer
        # to attach; the caller drives the import loop via run_headless().

    def setupGui(self) -> None:
        self.setWindowTitle(_("FPDB Auto Import"))
        self.setGeometry(100, 100, 800, 600)

        # Set minimal custom styles for specific needs
        self.setStyleSheet("""
            QTextEdit#logView {
                font-family: Monaco, "Cascadia Code", "Roboto Mono", Consolas, "Courier New", monospace;
                font-size: 13px;
                line-height: 1.4;
                border-radius: 8px;
            }

            QGroupBox {
                font-weight: bold;
                margin-top: 10px;
            }

            QProgressBar {
                border-radius: 2px;
                text-align: center;
            }
        """)

        mainLayout = QVBoxLayout()
        self.setLayout(mainLayout)

        # --- Settings Group ---
        settingsGroup = QGroupBox(_("Settings"))
        settingsLayout = QFormLayout()
        settingsGroup.setLayout(settingsLayout)
        mainLayout.addWidget(settingsGroup)

        self.intervalEntry = QSpinBox()
        self.intervalEntry.setValue(
            int(self.config.get_import_parameters().get("interval")),
        )
        settingsLayout.addRow(QLabel(_("Time between imports (seconds):")), self.intervalEntry)

        # --- Log Group ---
        logGroup = QGroupBox(_("Log"))
        logLayout = QVBoxLayout()
        logGroup.setLayout(logLayout)
        mainLayout.addWidget(logGroup)

        self.textview = QTextEdit()
        self.textview.setObjectName("logView")  # For custom styling
        self.textview.setReadOnly(True)
        logLayout.addWidget(self.textview)

        # --- Controls ---
        controlsLayout = QHBoxLayout()

        self.startButton = QCheckBox(_("Start Auto Import"))
        self.startButton.stateChanged.connect(self.startClicked)
        controlsLayout.addWidget(self.startButton)

        # Add a progress indicator
        self.progressBar = QProgressBar()
        self.progressBar.setTextVisible(False)
        self.progressBar.setMaximum(0)  # Indeterminate progress
        self.progressBar.setVisible(False)
        self.progressBar.setMaximumHeight(4)
        # Let qt_material handle the progress bar styling
        controlsLayout.addWidget(self.progressBar, 1)

        controlsLayout.addStretch()

        mainLayout.addLayout(controlsLayout)

        # Status label
        self.statusLabel = QLabel(_("Ready"))
        # Use qt_material property for styling
        self.statusLabel.setProperty("class", "caption")
        mainLayout.addWidget(self.statusLabel)

        self.addText(_("Auto Import Ready.\n"), "info")

    def apply_theme(self, theme_name="dark_purple.xml") -> None:
        """Apply a qt_material theme to the widget."""
        from fpdb_3_legacy.ThemeManager import ThemeManager

        if ThemeManager().set_qt_material_theme(theme_name):
            self.addText(f"Theme changed to {theme_name.replace('.xml', '')}\n", "info")
        else:
            self.addText(f"Unable to apply theme {theme_name}\n", "warning")

    def addText(self, text, level="info") -> None:
        if getattr(self, "cli", False):
            # Headless mode: no GUI log view — route to the logger instead.
            message = text.strip()
            if message:
                {"error": log.error, "warning": log.warning}.get(level, log.info)(message)
            return
        try:
            self.log_message.emit(text, level)
        except RuntimeError:
            # The widget's C++ object was deleted (e.g. the auto-import tab was
            # closed) while a config-observer callback was still running. Drop
            # the UI log line instead of crashing on a dead signal source.
            log.debug("addText: GuiAutoImport widget already deleted, skipping UI log")

    def _addText_slot(self, text, level="info") -> None:
        """Add formatted text to the log with timestamp, icon and color coding."""
        cursor = self.textview.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        # Clean text: remove leading newlines to ensure timestamp stays at line start
        clean_text = text.lstrip("\n")
        leading_newlines = len(text) - len(clean_text)

        # Add any leading newlines first (but not before timestamp)
        if leading_newlines > 0:
            cursor.insertText("\n" * leading_newlines)

        # Add timestamp at the start of the actual message line
        timestamp = QDateTime.currentDateTime().toString("hh:mm:ss")
        timestamp_format = QTextCharFormat()

        palette = self.palette()
        timestamp_format.setForeground(palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text))

        cursor.insertText(f"[{timestamp}] ", timestamp_format)

        # Add icon and set color based on level
        icon_format = QTextCharFormat()
        text_format = QTextCharFormat()

        if level == "error":
            # Material Red 500
            color = QColor("#F44336")
            icon = "❌ "  # Cross mark
        elif level == "warning":
            # Material Orange 500
            color = QColor("#FF9800")
            icon = "⚠️  "  # Warning sign
        elif level == "success":
            # Material Green 500
            color = QColor("#4CAF50")
            icon = "✅ "  # Check mark
        elif level == "info":
            # Material Blue 500
            color = QColor("#2196F3")
            icon = "ℹ️  "  # Information
        elif level == "import":
            # Material Purple 500
            color = QColor("#9C27B0")
            icon = "📥 "  # Inbox tray (import)
        elif level == "export":
            # Material Indigo 500
            color = QColor("#3F51B5")
            icon = "📤 "  # Outbox tray (export)
        elif level == "process":
            # Material Deep Orange 500
            color = QColor("#FF5722")
            icon = "⚙️  "  # Gear (processing)
        elif level == "hud":
            # Material Teal 500
            color = QColor("#009688")
            icon = "🎮 "  # Video game controller (HUD)
        elif level == "file":
            # Material Brown 500
            color = QColor("#795548")
            icon = "📄 "  # Document
        elif level == "folder":
            # Material Blue Grey 500
            color = QColor("#607D8B")
            icon = "📁 "  # Folder
        elif level == "network":
            # Material Light Green 500
            color = QColor("#8BC34A")
            icon = "🌐 "  # Globe
        elif level == "database":
            # Material Cyan 500
            color = QColor("#00BCD4")
            icon = "🗄️  "  # File cabinet
        elif level == "poker":
            # Material Red 700
            color = QColor("#D32F2F")
            icon = "♠️  "  # Spade suit
        elif level == "lock":
            # Material Amber 700
            color = QColor("#FFA000")
            icon = "🔒 "  # Lock
        elif level == "unlock":
            # Material Light Green 700
            color = QColor("#689F38")
            icon = "🔓 "  # Unlock
        else:
            # Use theme's normal text color
            color = palette.color(QPalette.ColorRole.Text)
            icon = "📝 "  # Memo (default)

        # Set format for both icon and text
        icon_format.setForeground(color)
        text_format.setForeground(color)

        # Insert icon and text
        cursor.insertText(icon, icon_format)
        cursor.insertText(clean_text, text_format)

        # Ensure the new text is visible
        self.textview.setTextCursor(cursor)
        self.textview.ensureCursorVisible()

    #   end of GuiAutoImport.__init__

    def do_import(self) -> bool:
        """Callback for timer to do an import iteration asynchronously."""
        if self.doAutoImportBool:
            if self.import_thread is not None and self.import_thread.isRunning():
                # A cycle that overruns one interval is normal on a big batch;
                # one that overruns many means the worker is wedged -- most
                # often on a database that stopped answering. Say so once,
                # because silence here is what made this look like the importer
                # had simply decided to stop working.
                self._deferred_cycles += 1
                if self._deferred_cycles == DEFERRED_CYCLES_BEFORE_WARNING:
                    log.warning(
                        "AutoImport: no import cycle has completed in %d intervals; "
                        "the worker is still busy (slow import, or an unresponsive database).",
                        self._deferred_cycles,
                    )
                    self.statusLabel.setText(_("Import cycle is taking longer than usual..."))
                else:
                    log.debug("AutoImport: previous import thread is still running, deferring this iteration.")
                return True

            self._deferred_cycles = 0
            self.progressBar.setVisible(True)
            self.progressBar.setMaximum(0)  # Indeterminate progress

            self.import_thread = AutoImportThread(self.importer, db_write_lock=self.db_write_lock)
            self.import_thread.finished.connect(self.import_finished)
            self.import_thread.error.connect(self.import_error)
            self.import_thread.db_offline.connect(self.import_db_offline)
            self.import_thread.start()
            return True
        return False

    def import_finished(self) -> None:
        """Called when auto import cycle finishes in the background."""
        self.progressBar.setVisible(False)
        if self._db_offline:
            self._db_offline = False
            self.addText(_("\nDatabase is back. Auto Import resumed."), "info")
        status = _("Stopping Auto Import...") if self._stop_cleanup_pending else _("Ready")
        self.statusLabel.setText(status)
        log.debug("AutoImport: background import cycle finished successfully")

    def import_db_offline(self) -> None:
        """Called when a cycle was skipped because the database is unreachable."""
        self.progressBar.setVisible(False)
        self.statusLabel.setText(_("Database unreachable - retrying"))
        if not self._db_offline:
            # Once per outage, not once per interval.
            self._db_offline = True
            log.warning("AutoImport: database unreachable, cycles are paused until it returns.")
            self.addText(_("\nDatabase unreachable. Auto Import paused, retrying..."), "error")

    def _stop_import_worker(self) -> bool:
        """Wait, briefly, for the running import cycle to finish.

        Returns:
            True when there is no longer a cycle running.

        The wait is bounded on purpose. It runs on the UI thread, so waiting
        without a timeout on a worker stuck against an unresponsive database
        froze the window and left force-quit as the only way out. An overrunning
        worker is left to finish on its own instead.
        """
        if self.import_thread is None or not self.import_thread.isRunning():
            return True
        if self.import_thread.wait(STOP_WAIT_MS):
            return True
        log.warning("AutoImport: import worker did not stop in time; leaving it to finish.")
        self.addText(
            _("\nStop requested while an import was still running; it will finish in the background."),
            "warning",
        )
        return False

    def _cancel_swc_attach(self) -> None:
        """Tell a pending tap attach to abandon its injection, at once.

        Every second between the click and this request is a second in which
        the attacher can pass its own check and load a DLL that nothing can
        unload -- so it is made the moment Stop is asked for, not from the
        finalizer. The finalizer runs behind the import worker's bounded wait,
        and when that worker overruns, behind a deferral loop with no bound at
        all; either delay is a window the injection can slip through.

        The attacher also stops reporting here: one that injected before the
        request arrived must not announce live capture into a stopped session.

        Idempotent, because the finalizer calls it again for the Stop paths
        that do not come through the button.
        """
        attacher = self.swc_attach_thread
        if attacher is None:
            return
        attacher.cancel()
        with suppress(RuntimeError, TypeError):
            attacher.attached.disconnect(self._on_swc_tap_attached)

    def _wait_for_import_worker_stop(self) -> None:
        """Finish a pending Stop once the import worker has really exited."""
        if not self._stop_cleanup_pending:
            return
        if self.import_thread is not None and self.import_thread.isRunning():
            QTimer.singleShot(250, self._wait_for_import_worker_stop)
            return
        self._finalize_auto_import_stop()

    def _finalize_auto_import_stop(self) -> None:
        """Release importer resources after no worker can still be using them."""
        self._stop_cleanup_pending = False
        if self.swc_tailing_thread is not None:
            self.swc_tailing_thread.stop()
            # A poll can still be normalizing twenty thousand retained messages
            # when this wait elapses, and the thread goes on running. Nothing it
            # finds may reach the importer now: the global lock is released
            # below, and an import from a thread the user has stopped writes to
            # a database nothing is holding open for it. The signal goes first,
            # so a late poll's hands are dropped rather than imported.
            with suppress(RuntimeError, TypeError):
                self.swc_tailing_thread.hand_imported.disconnect(self._on_swc_native_hand_imported)
            self.swc_tailing_thread.wait(1000)
            # Kept referenced while it drains; start_swc_native_capture will not
            # adopt a thread that was told to stop, so a restart still gets one.
            if not self.swc_tailing_thread.isRunning():
                self.swc_tailing_thread = None
        # Already done when Stop came from the button; repeated for the paths
        # that reach the finalizer without it.
        self._cancel_swc_attach()
        if self.swc_attach_thread is not None:
            # Given a moment, and kept referenced if it needs longer: dropping
            # the last reference to a running QThread destroys it mid-run.
            self.swc_attach_thread.wait(1000)
            if not self.swc_attach_thread.isRunning():
                self.swc_attach_thread = None
        self.importer.autoSummaryGrab(True)
        self.settings["global_lock"].release()
        self.addText("\nStopping Auto Import. Global lock released.", "unlock")
        self.progressBar.setVisible(False)
        self.statusLabel.setText(_("Ready"))
        if self.pipe_to_hud and self.pipe_to_hud.poll() is not None:
            self.addText("\n * Stop Auto Import: HUD already terminated.", "hud")
        else:
            if self.pipe_to_hud:
                self.pipe_to_hud.terminate()
                log.debug(f"pipe_to_hud stdin: {self.pipe_to_hud.stdin}")
            self.pipe_to_hud = None
        self.intervalEntry.setEnabled(True)
        self.startButton.setEnabled(True)

    def _swc_capture_wanted(self) -> bool:
        """Whether this configuration has any use for the SwC native capture.

        The capture exists because SwC ships no hand history files; every other
        room writes them, so for a player of one of those there is nothing here
        to start. That matters because building the tap shells out to a C
        compiler, which a Windows machine almost never has, and the failure was
        reported to every user on every Start:

            SwC Native Capture warning: [WinError 2] Le fichier specifie est introuvable

        -- a SealsWithClubs message sending Winamax players to look for a
        Winamax bug. Nothing is attempted for a site that is not configured.
        """
        try:
            params = self.config.get_site_parameters(SWC_SITE_NAME)
        except KeyError:
            log.debug("SwC native capture skipped: %s is not in the configuration", SWC_SITE_NAME)
            return False
        if not params.get("enabled", False):
            log.debug("SwC native capture skipped: %s is not enabled", SWC_SITE_NAME)
            return False
        return True

    def _retire_attach_thread(self) -> None:
        """Set the current attach worker aside so a new one can replace it.

        It is parentless, so nothing but a reference keeps it alive and dropping
        the last one destroys a running QThread mid-run. A worker still unwinding
        is parked until it has exited; the list is swept on the way past, so it
        holds at most the few that have not finished yet.
        """
        thread = self.swc_attach_thread
        self.swc_attach_thread = None
        self._retiring_attach_threads = [t for t in self._retiring_attach_threads if t.isRunning()]
        if thread is not None and thread.isRunning():
            self._retiring_attach_threads.append(thread)

    def start_swc_native_capture(self) -> None:
        """Launch SwC native TLS capture and start live raw tailing thread."""
        if not self._swc_capture_wanted():
            return
        try:
            import platform as _platform

            from fpdb_3_legacy.swc_native_capture import (
                DEFAULT_ARCHIVE,
                build_tap,
                native_capture_supported,
            )

            if not native_capture_supported():
                log.info("SwC live capture is not available on %s.", _platform.system())
                self.addText(
                    _("\nSwC live capture is not available on this platform. Importing SwC files still works."),
                    "info",
                )
                return

            if _platform.system() == "Windows":
                # Windows has no launch-time interposition, so the tap is injected
                # into the already-running client: build the tap + injector and
                # load them into SwCPoker.exe, which the user must have running.
                # On its own thread because it compiles, injects and then waits on
                # the client (see SwCWindowsAttachThread).
                attacher = self.swc_attach_thread
                if attacher is None or not attacher.isRunning() or attacher.cancelled:
                    # A cancelled attach is finished with even while it is still
                    # unwinding: it will inject nothing, so a restart that
                    # adopted it would leave the client untapped while saying
                    # capture was running.
                    self._retire_attach_thread()
                    # No parent: GuiAutoImport skips QWidget.__init__ in CLI mode,
                    # and parenting to a half-built widget fails outright. The
                    # attribute below is what keeps this alive.
                    self.swc_attach_thread = SwCWindowsAttachThread()
                    self.swc_attach_thread.attached.connect(self._on_swc_tap_attached)
                    self.swc_attach_thread.start()
            else:
                build_tap(check_executable=False)

            tailer = self.swc_tailing_thread
            if tailer is None or not tailer.isRunning() or tailer.stopping:
                # A thread still draining its last poll is finished with, not
                # available: it has been told to stop and its signal is already
                # disconnected. Qt owns it through its parent, so replacing the
                # reference here does not destroy it mid-poll.
                self.swc_tailing_thread = SwCNativeTailingThread(DEFAULT_ARCHIVE, parent=self)
                self.swc_tailing_thread.hand_imported.connect(self._on_swc_native_hand_imported)
                self.swc_tailing_thread.start()
                self.addText(_("\nSwC Native Live HUD tailing thread started."), "poker")
        except Exception as e:
            log.warning("Could not start SwC native capture: %s", e)
            self.addText(
                _("\nSwC live capture unavailable: {reason}. Importing SwC hand history files still works.").format(
                    reason=e,
                ),
                "warning",
            )

    def _on_swc_native_hand_imported(self, hand_data: dict) -> None:
        """Callback when a new live SwC hand is parsed from swc-native.raw."""
        from fpdb_3_legacy.http_capture_db_import import import_http_capture_hand

        # Importer holds its connection as `database`; `db` never existed, so
        # every live hand raised AttributeError into the handler below and was
        # dropped. Nothing captured live ever reached the database.
        database = getattr(self.importer, "database", None)
        if database is None:
            log.warning("SwC live hand dropped: the importer has no database connection")
            return
        tailer = getattr(self, "swc_tailing_thread", None)
        lock = getattr(self, "db_write_lock", None)

        # An auto-import cycle owns that connection while it runs, and importing
        # from this thread too would reset its bulk buffers and commit inside
        # its transaction. Tried without blocking, because a cycle can take
        # minutes and this is the GUI thread: the hand is simply offered again.
        if lock is not None and not lock.acquire(blocking=False):
            log.debug("SwC live hand %s waits for the running import cycle", hand_data.get("hand_id"))
            if tailer is not None:
                tailer.retry_hand(hand_data, transient=True)
            return

        try:
            result = import_http_capture_hand(database, hand_data)
        except Exception:
            # Not terminal: a database that is away comes back, and the hand is
            # offered again on a delay rather than once per poll.
            log.exception("Failed to import SwC live hand %s", hand_data.get("hand_id"))
            if tailer is not None:
                tailer.retry_hand(hand_data, transient=True)
            return
        finally:
            if lock is not None:
                lock.release()

        if result is not None and result.status == "skipped":
            # Not terminal either. A hand decoded while it is still being played
            # lacks the actions and settlement that make it importable, and a
            # finished one can be waiting for its text history to be imported:
            # later records are not the only thing that can complete it.
            if tailer is not None:
                tailer.retry_hand(hand_data)
                report = log.info if tailer.note_capture_only(hand_data) else log.debug
            else:
                report = log.info
            report("SwC native hand %s remains capture-only: %s", hand_data.get("hand_id"), result.message)
            return
        if tailer is not None:
            tailer.mark_hand_complete(hand_data)
        if result is not None and result.status == "duplicate":
            self.addText(f"\n[SwC Live] Hand #{hand_data.get('hand_id', 0)} already imported.", "info")
            return
        if result is not None and result.status == "updated":
            self.addText(f"\n[SwC Live] Repaired boards for hand #{hand_data.get('hand_id', 0)}.", "info")
            return

        game_cat = hand_data.get("game", {}).get("category", "unknown")
        hand_id = hand_data.get("hand_id", 0)
        self._notify_hud_of_hand(getattr(result, "row_id", None))
        self.addText(f"\n[SwC Live] Imported hand #{hand_id} ({game_cat}).", "poker")

    def _on_swc_tap_attached(self, status: str) -> None:
        """Report what the injection thread found, once it is done."""
        self.addText(f"\n{status}", "poker")

    def _notify_hud_of_hand(self, row_id) -> None:
        """Push a hand imported outside the auto-import cycle to a running HUD.

        HUD_main queues hands only from its ZMQ receiver, and the ordinary
        importer pushes ids there once the write is committed. A live native hand
        that skips that push reaches the database and stops -- the HUD never
        shows it until some unrelated import happens to wake it, which defeats
        the point of a live capture. Best effort: the HUD not running is the
        normal case for someone importing without one.
        """
        if not row_id:
            return
        importer = getattr(self, "importer", None)
        if importer is None or not getattr(importer, "callHud", False):
            return
        try:
            from fpdb_3_legacy.Importer import ZMQSender

            if getattr(importer, "zmq_sender", None) is None:
                importer.zmq_sender = ZMQSender()
            importer.zmq_sender.send_hand_id(row_id)
        except Exception:
            log.exception("Could not tell the HUD about SwC live hand %s", row_id)

    def import_error(self, error_msg: str) -> None:
        """Called when auto import cycle fails in the background."""
        self.progressBar.setVisible(False)
        log.error(f"AutoImport: background import cycle failed: {error_msg}")
        self.addText(f"Auto Import Error: {error_msg}\n", "error")

    def run_headless(self, interval: int | None = None, launch_hud: bool = True) -> int:
        """Run the auto-import loop without a GUI (used by the ``-q``/``--quiet`` mode).

        Watches the hand-history and tournament-summary directories configured for
        the enabled sites and imports new/updated files on a fixed interval — the
        same engine the GUI auto-import tab drives, but stepped by a plain
        ``time.sleep`` loop instead of a Qt timer. Runs until interrupted
        (Ctrl+C / SIGTERM).

        Like the GUI "Start Auto Import" button, this launches the HUD subprocess
        (``launch_hud=True``) and feeds it the imported hands over ZMQ. Note the
        HUD is itself a GUI overlay, so a display must be available.

        Args:
            interval: Seconds between import cycles. Defaults to the ``interval``
                import parameter from the configuration.
            launch_hud: Whether to spawn the HUD_main subprocess. Set False to run
                a pure background importer with no HUD.

        Returns:
            int: Process exit code (0 on clean shutdown, 1 if the global lock is
            unavailable).
        """
        if interval is None:
            try:
                interval = int(self.config.get_import_parameters().get("interval"))
            except (TypeError, ValueError):
                interval = 10
        interval = max(1, interval)

        lock = self.settings.get("global_lock")
        if lock is not None and not lock.acquire(wait=False, source="AutoImport"):
            log.error("Auto Import aborted: global lock not available (another fpdb import running?).")
            return 1

        log.info("Headless auto-import started (interval: %ss). Press Ctrl+C to stop.", interval)
        self.doAutoImportBool = True

        if launch_hud and self.pipe_to_hud is None:
            # HUD_main uses fpdb's shared option parser and rejects the
            # auto-import's own -q flag, so hand it HUD-appropriate options (the
            # config path) instead of whatever this process was invoked with.
            config_file = getattr(self.config, "file", None)
            self.settings["cl_options"] = f"-c {config_file}" if config_file else ""
            try:
                self._launch_hud()
                log.info("HUD launched.")
            except (OSError, ValueError):
                # A missing HUD must not stop imports; log and carry on headless.
                log.warning("Could not launch HUD; continuing without it: %s", traceback.format_exc())

        try:
            self.updatePaths()
            while True:
                try:
                    self.importer.autoSummaryGrab()
                    self.importer.runUpdated()
                except Exception:
                    # One bad cycle must not kill the daemon; log and keep watching.
                    log.exception("Auto-import cycle failed; continuing.")
                time.sleep(interval)
        except KeyboardInterrupt:
            log.info("Stopping headless auto-import (interrupt received).")
        finally:
            self.doAutoImportBool = False
            try:
                self.importer.autoSummaryGrab(force=True)
            except Exception:
                log.exception("Final tournament-summary grab failed.")
            if self.pipe_to_hud is not None:
                try:
                    self.pipe_to_hud.terminate()
                except OSError:
                    log.debug("HUD subprocess already gone.")
                self.pipe_to_hud = None
                log.info("HUD subprocess stopped.")
            if lock is not None:
                lock.release()
                log.info("Global lock released.")
        return 0

    def reset_startbutton(self) -> bool:
        if self.pipe_to_hud is not None:
            self.startButton.set_label(_("Stop Auto Import"))
        else:
            self.startButton.set_label(_("Start Auto Import"))

        return False

    def detect_hh_dirs(self, widget, data) -> None:
        """Attempt to find user hand history directories for enabled sites."""
        the_sites = self.config.get_supported_sites()
        for site in the_sites:
            params = self.config.get_site_parameters(site)
            if params["enabled"] is True:
                log.debug(f"Detecting hand history directory for site: '{site}'")
                if os.name == "posix":
                    if self.posix_detect_hh_dirs(site):
                        # data[1].set_text(dia_chooser.get_filename())
                        pass
                elif os.name == "nt":
                    # Sorry
                    pass

    def posix_detect_hh_dirs(self, site) -> bool:
        defaults = {
            "PokerStars": "~/.wine/drive_c/Program Files/PokerStars/HandHistory",
        }
        if site == "PokerStars":
            directory = os.path.expanduser(defaults[site])
            for file in [file for file in os.listdir(directory) if file not in [".", ".."]]:
                log.debug(file)
        return False

    @staticmethod
    def _hud_base_path() -> str:
        """Return the directory that contains HUD_main(.pyw), resolved robustly.

        PyInstaller's ``sys._MEIPASS`` is the resource directory (``_internal``
        on Windows/Linux and ``Contents/Frameworks`` on macOS), not the directory
        containing sibling executables. Packaged builds therefore resolve from
        ``sys.executable``. Source installs resolve next to this module rather
        than from ``sys.path[0]``/CWD, which depend on how fpdb was launched.
        """
        if getattr(sys, "frozen", False):
            return os.path.dirname(os.path.abspath(sys.executable))
        return os.path.dirname(os.path.abspath(__file__))

    def _launch_hud(self) -> None:
        """Build the HUD_main command for the current install method and spawn it.

        Sets ``self.pipe_to_hud`` to the launched subprocess. Raises OSError or
        ValueError on failure (callers decide how to surface it). Shared by the
        GUI auto-import (startClicked) and the headless mode (run_headless).
        """
        # ------------------------------------------------------------------
        # 1) build command line
        # ------------------------------------------------------------------
        command: str | list[str]
        frozen = getattr(sys, "frozen", False)
        if frozen:
            command = hud_main_command(*self.settings["cl_options"].split())
            bs = 0 if os.name == "nt" and frozen != "pyoxidizer" else 1

        elif self.config.install_method == "exe":
            command = "HUD_main.exe"
            bs = 0

        elif self.config.install_method == "app":
            base_path = self._hud_base_path()
            command = os.path.join(base_path, "HUD_main")
            if not os.path.isfile(command):
                msg = f"HUD_main not found at {command}"
                raise FileNotFoundError(msg)
            bs = 1

        elif os.name == "nt":  # Windows installation source
            path = to_raw(self._hud_base_path())
            use_pythonw = win32console is not None and win32console.GetConsoleWindow() == 0
            # Use the current interpreter (e.g. the uv/venv python) so the
            # HUD subprocess shares the same environment and installed
            # packages (zmq, PyQt, ...). Falling back to a bare
            # "python"/"pythonw" from PATH would pick a different
            # interpreter that may lack our dependencies.
            interpreter = sys.executable
            if use_pythonw:
                pythonw = os.path.join(os.path.dirname(interpreter), "pythonw.exe")
                if os.path.isfile(pythonw):
                    interpreter = pythonw
            command = f'"{interpreter}" "{path}\\HUD_main.pyw" {self.settings["cl_options"]}'
            bs = 0

        else:  # Linux & macOS installation source
            base_path = self._hud_base_path()
            command = os.path.join(base_path, "HUD_main.pyw")
            if not os.path.isfile(command):
                self.addText(f"\n*** {command} was not found", "error")
            command = [command, *self.settings["cl_options"].split()]
            bs = 1

        # ------------------------------------------------------------------
        # 2) prepare env for sub process
        # ------------------------------------------------------------------
        env = None  # default

        # Since PyInstaller 6.9, a frozen executable launched from another
        # frozen executable is assumed to be a worker process unless the
        # bootloader environment is explicitly reset. HUD_main is an
        # independent application and must initialize its own bootloader state.
        if getattr(sys, "frozen", False) and getattr(sys, "frozen", False) != "pyoxidizer":
            env = os.environ.copy()
            env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"

        if sys.platform.startswith("linux") and os.getenv("FPDB_FORCE_X11") == "1":
            if env is None:
                env = os.environ.copy()
            env.setdefault("QT_QPA_PLATFORM", "xcb")
            env.setdefault("FPDB_FORCE_X11", "1")

        log.info("opening pipe to HUD")
        log.debug(f"Running {command!r} with bs={bs}")
        # WARNING, not DEBUG: which argv actually started the HUD is the first
        # thing a duplicate-overlay report needs, and DEBUG is not on in the
        # logs users send.
        log.warning(
            "HUD launch: session=%s parent_pid=%s install_method=%s command=%r",
            session_id(),
            os.getpid(),
            self.config.install_method,
            command,
        )

        # ------------------------------------------------------------------
        # 3) launch HUD
        # ------------------------------------------------------------------
        popen_kwargs: dict[str, Any] = {
            "bufsize": bs,
            "stdin": subprocess.PIPE,
            "universal_newlines": True,
        }
        # A windowed Windows process has no console. Do not leave unread PIPEs
        # that can fill up and block the HUD; HUD_main writes diagnostics to its
        # own rotating log.
        if self.config.install_method == "exe" or (
            os.name == "nt" and win32console is not None and win32console.GetConsoleWindow() == 0
        ):
            popen_kwargs.update(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if env is not None:
            popen_kwargs["env"] = env

        self.pipe_to_hud = subprocess.Popen(command, **popen_kwargs)
        log.info("HUD process spawned with pid=%s", self.pipe_to_hud.pid)

    def _check_hud_process_started(self) -> None:
        """Report a HUD process that exited during its startup window."""
        process = self.pipe_to_hud
        if process is None:
            return
        return_code = process.poll()
        if return_code is None:
            log.info("HUD process %s is running", process.pid)
            return
        if return_code == HUD_ALREADY_RUNNING_EXIT_CODE:
            # The one startup failure a player can act on, and the one that
            # otherwise shows up as a second set of stat blocks over every
            # table with nothing anywhere to explain it.
            owner = read_lock_owner() or "owner not recorded"
            msg = (
                "The HUD did not start: another FPDB HUD is already running and owns the "
                f"single-HUD lock ({owner}). Two HUDs draw two sets of stat blocks over every "
                "table. Quit the other one, then start Auto Import again."
            )
        elif return_code == HUD_LOCK_UNDETERMINED_EXIT_CODE:
            # Deliberately not "another HUD is running": the HUD reached this
            # exit because it could not find out. Sending the player off to
            # quit a HUD they do not have is what #259 was about.
            msg = (
                "The HUD did not start: the single-HUD lock could not be tested, so whether "
                "another FPDB HUD is running is unknown. See HUD-log.txt for the underlying "
                "error. If no other HUD is running, retrying usually succeeds."
            )
        else:
            msg = f"HUD_main exited during startup with code {return_code}"
        log.error(msg)
        self.addText(f"\n*** {msg}", "error")
        self.pipe_to_hud = None

    def startClicked(self) -> None:
        """Runs when user clicks start on auto import tab."""
        # Check to see if we have an open file handle to the HUD and open one if we do not.
        # bufsize = 1 means unbuffered
        # We need to close this file handle sometime.

        if self.startButton.isChecked():
            # - Ideally we want to release the lock if the auto-import is killed by some
            # kind of exception - is this possible?
            if self.settings["global_lock"].acquire(wait=False, source="AutoImport"):
                self.addText("\nGlobal lock taken ... Auto Import Started.\n", "lock")
                self.doAutoImportBool = True
                self.intervalEntry.setEnabled(False)
                self.progressBar.setVisible(True)
                self.statusLabel.setText(_("Auto Import Running..."))

                if self.pipe_to_hud is None:
                    log.debug("start hud - pipe_to_hud is none:")
                    try:
                        self._launch_hud()
                    except (OSError, ValueError):
                        error_msg = f"GuiAutoImport Error opening pipe: {traceback.format_exc()}"
                        log.warning(error_msg)
                        self.addText(f"\n*** {error_msg}", "error")
                    else:
                        QTimer.singleShot(1500, self._check_hud_process_started)
                        # ------------------------------------------------------------------
                        # path config, timer, etc.
                        # ------------------------------------------------------------------
                        self.updatePaths()

                        self.do_import()
                        self.start_swc_native_capture()
                        interval = self.intervalEntry.value()
                        self.importtimer = QTimer()
                        self.importtimer.timeout.connect(self.do_import)
                        self.importtimer.start(interval * 1000)

            else:
                self.addText("\nAuto Import aborted. Global lock not available.", "error")

        else:  # bouton « Start » décoché → arrêt
            self.doAutoImportBool = False
            # First, before anything here can wait on a worker: the tap has no
            # unload path, so the only thing that can still be taken back is an
            # injection that has not happened yet (see _cancel_swc_attach).
            self._cancel_swc_attach()
            if self.importtimer:
                self.importtimer.stop()
                self.importtimer = None
            if self._stop_cleanup_pending:
                return
            if not self._stop_import_worker():
                # Do not touch the Importer, its connection, the HUD process or
                # the global lock while runUpdated() can still be using them.
                self._stop_cleanup_pending = True
                self.startButton.setEnabled(False)
                self.statusLabel.setText(_("Stopping Auto Import..."))
                QTimer.singleShot(250, self._wait_for_import_worker_stop)
                return
            self._finalize_auto_import_stop()

    # end def GuiAutoImport.startClicked

    def get_vbox(self):
        """Returns the vbox of this thread."""
        return self.mainVBox

    # end def get_vbox

    def _setup_config_observer(self) -> None:
        """Configure the configuration observer for auto-import."""
        if DYNAMIC_CONFIG_AVAILABLE:
            try:
                config_manager = ConfigurationManager()

                # Ensure ConfigurationManager is initialized
                if not config_manager.initialized:
                    config_manager.initialize(self.config.file)

                # Create and register observer
                self.config_observer = AutoImportConfigObserver(self)
                config_manager.register_observer(self.config_observer)

                log.info("Configuration observer registered for auto-import")

            except Exception as e:  # intentional broad catch: config observer registration best-effort, log only
                log.exception(f"Error during observer configuration: {e}")

    def _teardown_config_observer(self) -> None:
        """Unregister the config observer so it can't call into a deleted widget.

        Without this the ConfigurationManager (a singleton) keeps a reference to
        this widget after it is closed; the next config change then calls
        updatePaths() -> addText() and emits a signal on a dead Qt object.
        """
        observer = getattr(self, "config_observer", None)
        if observer is None or not DYNAMIC_CONFIG_AVAILABLE:
            return
        try:
            ConfigurationManager().unregister_observer(observer)
        except Exception:  # intentional broad catch: teardown best-effort, log only
            log.debug("Failed to unregister auto-import config observer", exc_info=True)
        self.config_observer = None

    def shutdown_workers(self) -> None:
        """Stop auto-import before this tab is destroyed (#347).

        A widget removed from the tab notebook is never sent ``closeEvent``,
        which is what this hook exists for. Without it, closing the tab left
        the timer firing into a dying widget, the import worker running, the
        global lock taken for the rest of the session -- and the config
        observer registered, so the next configuration change called back into
        a deleted Qt object.

        The stop performed here is the one the Stop button performs, run
        synchronously: the widget is about to be deleted, so there is nothing
        left to defer the finish to. A worker that overruns its bounded wait is
        the one case left alone, because the finalizer releases the lock and
        touches the importer, and neither is safe while an import is still
        using them; it finishes on its own, holding what it holds.
        """
        self._teardown_config_observer()
        if not self.doAutoImportBool and self.importtimer is None:
            return
        self.doAutoImportBool = False
        self._cancel_swc_attach()
        if self.importtimer:
            self.importtimer.stop()
            self.importtimer = None
        if not self._stop_import_worker():
            log.warning("AutoImport tab closed while an import was still running; leaving it to finish.")
            return
        self._stop_cleanup_pending = False
        self._finalize_auto_import_stop()

    def close_owned_database(self) -> None:
        """Give back the connections this tab's importer opened (#282, #347).

        An importer holds one connection for itself and one per writer thread.
        ``close_tab`` calls this after :meth:`shutdown_workers`, so by now no
        import worker should be running -- but a worker that overran its wait
        still holds the importer, and closing underneath it would hand it a
        dead handle. That case keeps its connections until the process ends,
        which is what happened on every close before this existed.
        """
        importer = getattr(self, "importer", None)
        if importer is None:
            return
        if self.import_thread is not None and self.import_thread.isRunning():
            log.warning("AutoImport: an import is still running; its database connections stay open.")
            return
        importer.close()

    def closeEvent(self, event) -> None:
        self._teardown_config_observer()
        super().closeEvent(event)

    def _configured_import_directories(self) -> dict[tuple[str, str], str]:
        """Resolve import paths for the current enabled sites.

        This helper is reached only from an active ``updatePaths()`` call.
        Keeping ``get_default_paths(site)`` here preserves room-specific path
        recovery (for example after an OS/account migration) without probing
        any site while Auto Import is stopped.
        """
        directories: dict[tuple[str, str], str] = {}
        for site in self.config.get_supported_sites():
            # A site can be enabled under <supported_sites> without a matching
            # <hhc> converter entry (e.g. "BetOnline" vs "BetOnline Poker").
            # Skip such a site instead of letting one KeyError abort auto-import
            # for every site — which leaves the HUD with nothing to import.
            try:
                params = self.config.get_site_parameters(site)
            except KeyError as e:
                log.warning("Skipping auto-import for misconfigured site %s (missing config: %s)", site, e)
                continue
            if not params.get("enabled", False):
                continue

            try:
                paths = self.config.get_default_paths(site)
            except KeyError as e:
                log.warning("Skipping auto-import paths for misconfigured site %s (missing config: %s)", site, e)
                continue

            hh_path = paths.get("hud-defaultPath")
            if hh_path and os.path.isdir(hh_path):
                directories[(site, "hh")] = hh_path
            elif hh_path:
                log.warning("Ignoring invalid hand-history path for %s: %s", site, hh_path)

            ts_path = paths.get("hud-defaultTSPath")
            if ts_path and os.path.isdir(ts_path):
                directories[(site, "ts")] = ts_path
            elif ts_path:
                log.warning("Ignoring invalid tournament-summary path for %s: %s", site, ts_path)

        return directories

    def updatePaths(self) -> None:
        """Reload config paths and resynchronise the importer's watched dirs."""
        if not self.doAutoImportBool:
            # Configuration observers also run while the tab is merely open.
            # Defer all reload/path work until Start Auto Import (or the
            # headless equivalent) has explicitly made the importer active.
            log.debug("Deferring auto-import path update while Auto Import is stopped")
            return

        log.debug("Updating auto-import paths from configuration")

        if hasattr(self.config, "reload"):
            self.config.reload()

        desired = self._configured_import_directories()
        current = dict(getattr(self.importer, "dirlist", {}))

        for key, (old_path, _old_filter) in current.items():
            new_path = desired.get(key)
            if new_path != old_path:
                self.importer.removeImportDirectory(old_path, site=key)
                self.addText(f"\n * Remove {key[0]} {key[1]} directory: {old_path}", "folder")

        for key, path in desired.items():
            current_path = self.importer.dirlist.get(key, [None])[0]
            if current_path == path:
                continue
            self.importer.addImportDirectory(path, monitor=True, site=key)
            label = "hand history" if key[1] == "hh" else "tournament summary"
            self.addText(f"\n * Add {key[0]} {label} directory: {path}", "folder")


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    # Parse command line options
    parser = OptionParser()
    parser.add_option(
        "-q",
        "--quiet",
        action="store_false",
        dest="gui",
        default=True,
        help="don't start gui",
    )
    (options, remaining_argv) = parser.parse_args(argv)

    config = Configuration.Config()

    settings = {}
    if os.name == "nt":
        settings["os"] = "windows"
    else:
        settings["os"] = "linuxmac"

    settings.update(config.get_db_parameters())
    settings.update(config.get_import_parameters())
    # Path discovery belongs to an active Auto Import session. In particular,
    # get_default_paths() probes fallback locations when the configured default
    # is missing, which is inappropriate while merely constructing this entry
    # point.
    settings["global_lock"] = interlocks.InterProcessLock(name="fpdb_global_lock")
    settings["cl_options"] = ".".join(argv)

    if options.gui is True:
        from PySide6.QtWidgets import QApplication, QMainWindow

        app = QApplication([])
        i = GuiAutoImport(settings, config, None, None)
        main_window = QMainWindow()
        main_window.setCentralWidget(i)
        main_window.show()
        app.exec()
    else:
        i = GuiAutoImport(settings, config, cli=True)
        return i.run_headless()

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
