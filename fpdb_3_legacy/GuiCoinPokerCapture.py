#!/usr/bin/env python3
"""GUI tab to start/stop the elevated CoinPoker live packet-capture feed.

Packet capture needs root / Administrator, and fpdb normally runs unprivileged,
so this tab launches the capture as a separate elevated process (pkexec on
Linux, an administrator ``osascript`` on macOS, a UAC ``runas`` on Windows).
The elevated process imports hands into the same database the HUD reads.

To avoid having a non-privileged GUI capture an elevated child's stdout or kill
a root process, the capture is asked to tee its output to a log file (which this
tab tails) and to stop when a sentinel stop-file appears (which Stop creates).
"""

from __future__ import annotations

import contextlib
import os
import platform
import shlex
import signal
import subprocess
import sys
from pathlib import Path
from typing import TextIO

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("coinpoker_capture_gui")

_MODULE = "fpdb_3_legacy.coinpoker_live_capture"
_GAMES = ["PLO4", "PLO5", "PLO6", "NLHE", "Shortdeck"]


def _repo_root() -> Path:
    import fpdb_3_legacy

    return Path(fpdb_3_legacy.__file__).resolve().parent.parent


class GuiCoinPokerCapture(QWidget):
    """Start/stop control for the native CoinPoker capture, with elevation."""

    def __init__(self, config, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.proc: subprocess.Popen | None = None
        self.hud_proc: subprocess.Popen | None = None
        self._hud_log: TextIO | None = None
        self._log_pos = 0

        state_dir = Path(os.path.expanduser("~/.fpdb"))
        state_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = state_dir / "coinpoker-capture.log"
        self.stop_file = state_dir / "coinpoker-capture.stop"

        self._build_ui()

        self.tail_timer = QTimer(self)
        self.tail_timer.setInterval(500)
        self.tail_timer.timeout.connect(self._tail_log)

    # -- UI ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.mainVBox = QVBoxLayout()
        self.setLayout(self.mainVBox)

        self.mainVBox.addWidget(
            QLabel(
                "Capture CoinPoker hands live from the network and import them for the HUD.\n"
                "This starts a separate process with administrator privileges.",
            ),
        )

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Interface:"))
        self.iface_combo = QComboBox()
        controls.addWidget(self.iface_combo, 1)

        game_label = QLabel("Default game:")
        self.game_combo = QComboBox()
        self.game_combo.addItems(_GAMES)
        # The variant is detected per hand from the number of cards dealt to the
        # hero, so this only applies to hands where the hero's cards are not
        # captured (e.g. observing a table).
        game_tip = "Fallback game type. Each hand's variant is auto-detected from your hole cards; this is only used when they aren't captured (e.g. observing)."
        game_label.setToolTip(game_tip)
        self.game_combo.setToolTip(game_tip)
        controls.addWidget(game_label)
        controls.addWidget(self.game_combo)

        self.dry_run = QCheckBox("Dry run (no DB insert)")
        controls.addWidget(self.dry_run)

        self.launch_hud = QCheckBox("Launch HUD")
        self.launch_hud.setChecked(True)
        self.launch_hud.setToolTip("Also start HUD_main (uncheck if HUD/Auto Import is already running).")
        controls.addWidget(self.launch_hud)
        self.mainVBox.addLayout(controls)

        buttons = QHBoxLayout()
        self.start_button = QPushButton("Start capture")
        self.start_button.clicked.connect(self._start)
        buttons.addWidget(self.start_button)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._stop)
        buttons.addWidget(self.stop_button)
        self.refresh_button = QPushButton("Refresh interfaces")
        self.refresh_button.clicked.connect(self._populate_ifaces)
        buttons.addWidget(self.refresh_button)
        buttons.addStretch(1)
        self.mainVBox.addLayout(buttons)

        self.status = QLabel("Idle.")
        self.mainVBox.addWidget(self.status)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.mainVBox.addWidget(self.output, 1)

        self._populate_ifaces()

    def _populate_ifaces(self) -> None:
        self.iface_combo.clear()
        self.iface_combo.addItem("(auto-detect)", None)
        try:
            from fpdb_3_legacy.coinpoker_pcap import list_devices

            for name, desc, _flags in list_devices():
                label = f"{name}  {desc}".strip()
                self.iface_combo.addItem(label, name)
        except Exception as exc:  # noqa: BLE001 - capture lib may be missing (e.g. no Npcap)
            self.status.setText(
                f"Could not list interfaces ({exc}). Install libpcap/Npcap; you can still use auto-detect.",
            )

    # -- start / stop --------------------------------------------------------

    def _base_args(self) -> list[str]:
        """Common importer args (source flag and --log-file added per platform).

        ``-u`` keeps stdout unbuffered so progress shows immediately in the log
        the tab tails (a long-running redirect to a file is block-buffered).
        """
        args = [sys.executable, "-u", "-m", _MODULE, "--game", self.game_combo.currentText(), "--stop-file", str(self.stop_file)]
        cfg = getattr(self.config, "file", None)
        if cfg:
            args += ["--config-file", str(cfg)]
        if self.dry_run.isChecked():
            args.append("--dry-run")
        return args

    def _start(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            return
        # Check before starting tcpdump or HUD.  On macOS the importer only gets
        # a chance to take this lock after tcpdump opens the FIFO; without this
        # preflight a duplicate click/session starts unnecessary helper processes.
        if not self.dry_run.isChecked():
            from fpdb_3_legacy.coinpoker_live_capture import _acquire_instance_lock

            try:
                probe = _acquire_instance_lock()
            except RuntimeError as exc:
                if platform.system() == "Darwin" and self.stop_file.exists():
                    # A reader inherited by launchd (for example after fpdb was
                    # restarted) can be blocked on the FIFO and never observe
                    # the stop sentinel. The lock contains the verified holder
                    # PID, so terminate that exact unprivileged reader and retry.
                    try:
                        holder_pid = int(Path(os.path.expanduser("~/.fpdb/coinpoker-capture.lock")).read_text().strip())
                        os.kill(holder_pid, signal.SIGTERM)
                    except (OSError, ValueError):
                        self.status.setText(f"Capture already active: {exc}")
                        return
                    self.status.setText("Finishing previous capture…")
                    QTimer.singleShot(500, self._start)
                    return
                self.status.setText(f"Capture already active: {exc}")
                return
            else:
                probe.close()
        # Fresh log + clear any stale stop signal.
        self.stop_file.unlink(missing_ok=True)
        self.log_file.write_text("", encoding="utf-8")
        self._log_pos = 0
        self.output.clear()

        try:
            self.proc = self._launch_elevated()
        except Exception as exc:  # noqa: BLE001
            self.status.setText(f"Failed to launch capture: {exc}")
            log.exception("CoinPoker capture launch failed")
            return

        if self.launch_hud.isChecked() and not self.dry_run.isChecked():
            self._launch_hud_main()

        self.status.setText("Requesting privileges… accept the prompt, then play in CoinPoker.")
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.tail_timer.start()
        # If nothing shows up shortly, the elevation prompt was likely declined.
        QTimer.singleShot(6000, self._check_started)

    def _check_started(self) -> None:
        if not self.stop_button.isEnabled():
            return  # already stopped
        if self.proc is not None and self.proc.poll() is not None:
            self._tail_log()
            self._terminate_children()
            self.proc = None
            self.status.setText("Capture failed to start — see the log above.")
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self.tail_timer.stop()
            return
        try:
            started = self.log_file.stat().st_size > 0
        except OSError:
            started = False
        if not started:
            self.status.setText(
                "No output yet — the admin prompt may have been declined, or capture failed to start.",
            )

    def _stop(self) -> None:
        # Signal the elevated process to exit; it polls for this file.
        try:
            self.stop_file.write_text("stop", encoding="utf-8")
        except OSError as exc:
            self.status.setText(f"Could not write stop file: {exc}")
            return
        self.status.setText("Stopping…")
        self.stop_button.setEnabled(False)
        QTimer.singleShot(1500, self._finish_stop)

    def _finish_stop(self) -> None:
        self.tail_timer.stop()
        self._tail_log()
        self._terminate_children()
        self.stop_file.unlink(missing_ok=True)
        self.proc = None
        self.status.setText("Idle.")
        self.start_button.setEnabled(True)

    def _terminate_children(self) -> None:
        """Terminate capture/HUD children and close their owned resources."""
        # On macOS terminating the FIFO reader closes the pipe, so tcpdump gets
        # SIGPIPE.  This is essential on widget close because --stdin can be
        # blocked waiting for input and cannot observe the stop sentinel.
        for child in (self.proc, self.hud_proc):
            if child is None or child.poll() is not None:
                continue
            with contextlib.suppress(Exception):
                child.terminate()
                try:
                    child.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=1)
        self.hud_proc = None
        if self._hud_log is not None:
            with contextlib.suppress(Exception):
                self._hud_log.close()
            self._hud_log = None

    def _launch_hud_main(self) -> None:
        """Spawn HUD_main (listens on ZMQ 5555) using the same interpreter."""
        if self.hud_proc is not None and self.hud_proc.poll() is None:
            return
        hud_main = Path(__file__).resolve().parent / "HUD_main.pyw"
        if not hud_main.is_file():
            self.output.appendPlainText(f"[warn] HUD_main not found at {hud_main}")
            return
        command = [sys.executable, str(hud_main), "-x"]
        cfg = getattr(self.config, "file", None)
        if cfg:
            command += ["-c", str(cfg)]
        try:
            # Capture HUD_main's console output so its table-detection decisions
            # are visible (~/.fpdb/coinpoker-hud.log).
            self._hud_log = (Path(os.path.expanduser("~/.fpdb")) / "coinpoker-hud.log").open("w", encoding="utf-8")
            self.hud_proc = subprocess.Popen(command, stdout=self._hud_log, stderr=subprocess.STDOUT)  # noqa: S603
            self.output.appendPlainText("[info] HUD_main started (ZMQ 5555); log -> ~/.fpdb/coinpoker-hud.log")
        except Exception as exc:  # noqa: BLE001
            self.output.appendPlainText(f"[warn] could not launch HUD_main: {exc}")

    def _launch_elevated(self) -> subprocess.Popen | None:
        """Launch capture and return a child only when this GUI owns it.

        Windows ``ShellExecuteW(..., runas, ...)`` starts a detached elevated
        process and exposes no usable ``Popen`` handle.  Returning ``None`` is
        intentional: a short-lived placeholder must never be treated as the
        real capture or as evidence that startup failed.
        """
        system = platform.system()
        if system == "Darwin":
            return self._launch_macos()
        if system == "Windows":
            self._launch_windows()
            return None
        return self._launch_linux()

    def _launch_linux(self) -> subprocess.Popen:
        # No TCC on Linux: run the venv importer directly as root via polkit.
        root = _repo_root()
        command = [*self._base_args(), "--live"]
        iface = self.iface_combo.currentData()
        if iface:
            command += ["--iface", iface]
        log_handle = self.log_file.open("a", encoding="utf-8")
        return subprocess.Popen(  # noqa: S603, S607
            ["pkexec", "env", f"PYTHONPATH={root}", *command],
            cwd=str(root),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
        )

    def _launch_windows(self) -> None:
        import ctypes

        root = _repo_root()
        command = [*self._base_args(), "--live", "--log-file", str(self.log_file)]
        iface = self.iface_combo.currentData()
        if iface:
            command += ["--iface", iface]
        params = " ".join(f'"{a}"' if " " in a else a for a in command[1:])
        rc = ctypes.windll.shell32.ShellExecuteW(  # type: ignore[attr-defined]
            None,
            "runas",
            command[0],
            params,
            str(root),
            1,
        )
        if int(rc) <= 32:
            raise OSError(f"UAC elevation was declined or failed (code {rc})")
        # ShellExecuteW does not return a process handle here. The elevated
        # importer reports readiness through --log-file and stops via the
        # sentinel; do not manufacture an exited placeholder process because
        # _check_started would interpret it as a crash and terminate HUD_main.
        return None

    def _launch_macos(self) -> subprocess.Popen:
        # macOS TCC blocks a root process from reading the venv under ~/Documents,
        # so we cannot run the importer elevated. Instead only the system tcpdump
        # (which touches only /dev/bpf, not Documents) runs elevated and pipes
        # packets through a FIFO to the unprivileged importer, which keeps the
        # user's Documents/venv access.
        from fpdb_3_legacy.coinpoker_pcap import default_device

        root = _repo_root()
        log = shlex.quote(str(self.log_file))
        iface = self.iface_combo.currentData() or default_device()
        fifo = "/tmp/coinpoker-capture.fifo"  # noqa: S108 - transient IPC pipe
        with contextlib.suppress(OSError):
            os.remove(fifo)
        os.mkfifo(fifo)

        importer = " ".join(shlex.quote(a) for a in [*self._base_args(), "--stdin"])
        reader = subprocess.Popen(  # noqa: S603
            [
                "/bin/sh", "-c",
                "cd {r} && PYTHONPATH={r} exec {imp} < {fifo} >> {log} 2>&1".format(
                    r=shlex.quote(str(root)), imp=importer, fifo=shlex.quote(fifo), log=log,
                ),
            ],
        )

        from fpdb_3_legacy.coinpoker_live_capture import BPF_FILTER

        tcpdump = f"/usr/sbin/tcpdump -i {shlex.quote(iface)} -l -n -S -x {shlex.quote(BPF_FILTER)} > {shlex.quote(fifo)} 2>> {log} &"
        applescript = 'do shell script "{}" with administrator privileges'.format(
            tcpdump.replace("\\", "\\\\").replace('"', '\\"'),
        )
        subprocess.Popen(["osascript", "-e", applescript])  # noqa: S603, S607
        # Terminating the reader closes the FIFO -> tcpdump gets SIGPIPE and exits.
        return reader

    # -- log tailing ---------------------------------------------------------

    def _tail_log(self) -> None:
        try:
            with self.log_file.open("r", encoding="utf-8", errors="replace") as handle:
                handle.seek(self._log_pos)
                chunk = handle.read()
                self._log_pos = handle.tell()
        except OSError:
            return
        if chunk:
            self.output.appendPlainText(chunk.rstrip("\n"))

    # -- lifecycle -----------------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self.stop_button.isEnabled():
            try:
                self.stop_file.write_text("stop", encoding="utf-8")
            except OSError:
                pass
        self.tail_timer.stop()
        self._terminate_children()
        super().closeEvent(event)

    def get_vbox(self):
        return self.mainVBox
