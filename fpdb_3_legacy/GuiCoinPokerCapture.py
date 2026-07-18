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
import subprocess
import sys
from pathlib import Path

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
_GAMES = ["PLO4", "PLO5", "PLO6", "NLHE"]


def _repo_root() -> Path:
    import fpdb_3_legacy

    return Path(fpdb_3_legacy.__file__).resolve().parent.parent


class GuiCoinPokerCapture(QWidget):
    """Start/stop control for the native CoinPoker capture, with elevation."""

    def __init__(self, config, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.proc: subprocess.Popen | None = None
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

        controls.addWidget(QLabel("Game:"))
        self.game_combo = QComboBox()
        self.game_combo.addItems(_GAMES)
        controls.addWidget(self.game_combo)

        self.dry_run = QCheckBox("Dry run (no DB insert)")
        controls.addWidget(self.dry_run)
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

        self.status.setText("Requesting privileges… accept the prompt, then play in CoinPoker.")
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.tail_timer.start()
        # If nothing shows up shortly, the elevation prompt was likely declined.
        QTimer.singleShot(6000, self._check_started)

    def _check_started(self) -> None:
        if not self.stop_button.isEnabled():
            return  # already stopped
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
        # Terminate the process we own (macOS FIFO reader / Linux pkexec child).
        # On macOS this closes the FIFO so the elevated tcpdump exits via SIGPIPE.
        if self.proc is not None and self.proc.poll() is None:
            with contextlib.suppress(Exception):
                self.proc.terminate()
        self.stop_file.unlink(missing_ok=True)
        self.proc = None
        self.status.setText("Idle.")
        self.start_button.setEnabled(True)

    def _launch_elevated(self) -> subprocess.Popen:
        system = platform.system()
        if system == "Darwin":
            return self._launch_macos()
        if system == "Windows":
            return self._launch_windows()
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

    def _launch_windows(self) -> subprocess.Popen:
        import ctypes

        root = _repo_root()
        command = [*self._base_args(), "--live", "--log-file", str(self.log_file)]
        iface = self.iface_combo.currentData()
        if iface:
            command += ["--iface", iface]
        params = " ".join(f'"{a}"' if " " in a else a for a in command[1:])
        rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", command[0], params, str(root), 1)
        if int(rc) <= 32:
            raise OSError(f"UAC elevation was declined or failed (code {rc})")
        return subprocess.Popen(["cmd", "/c", "exit"])  # placeholder; real process is elevated

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

        tcpdump = "/usr/sbin/tcpdump -i {iface} -l -n -S -x {filt} > {fifo} 2>> {log} &".format(
            iface=shlex.quote(iface),
            filt=shlex.quote(BPF_FILTER),
            fifo=shlex.quote(fifo),
            log=log,
        )
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
        super().closeEvent(event)

    def get_vbox(self):
        return self.mainVBox
