#!/usr/bin/env python

# Copyright 2025
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.

"""
HHTailer: Event-driven file monitoring for real-time hand history streaming

Provides real-time monitoring and line-by-line reading of hand history files
as they're being written by poker clients. Supports multiple operating systems
and gracefully falls back to polling if watchdog is unavailable.
"""

import os
import sys
import time
import threading
from typing import Callable, List, Optional, Dict, Any

from loggingFpdb import get_logger

log = get_logger("hh_tailer")

# Optional: Try to import watchdog for efficient file monitoring
try:
    from watchdog.observers import Observer
    from watchdog.events import FileModifiedEvent, FileSystemEventHandler

    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    log.debug("watchdog not available, will use polling fallback")


class HHTailerEventHandler(FileSystemEventHandler):
    """Watchdog event handler for file modifications."""

    def __init__(self, filepath: str, on_modified: Callable) -> None:
        """Initialize the event handler.

        Args:
            filepath: Full path to the file being monitored
            on_modified: Callback function when file is modified
        """
        self.filepath = filepath
        self.on_modified = on_modified

    def on_modified(self, event) -> None:
        """Handle file modification events."""
        if not event.is_directory and event.src_path == self.filepath:
            self.on_modified(event)


class HHTailer:
    """Event-driven file tailer for streaming hand history data.

    Monitors a hand history file and calls callbacks as new data arrives.
    Uses watchdog library for efficient monitoring on supported platforms,
    falls back to polling on others.

    Attributes:
        filepath: Path to the hand history file
        callbacks: List of (event_type, callback) tuples
        encoding: File encoding (default: cp1252)
        poll_interval: Polling interval in seconds (default: 0.1s)
        _running: Whether the tailer is actively monitoring
        _position: Current read position in file
        _observer: Watchdog observer instance (if available)
    """

    # Chunk size for reading file updates
    READ_CHUNK_SIZE = 10000  # bytes

    def __init__(
        self,
        filepath: str,
        encoding: str = "cp1252",
        poll_interval: float = 0.1,
    ) -> None:
        """Initialize the HHTailer.

        Args:
            filepath: Path to the hand history file to monitor
            encoding: File encoding (default: cp1252, common for PokerStars/Bovada)
            poll_interval: Polling interval in seconds (for fallback mode)
        """
        self.filepath = os.path.abspath(filepath)
        self.encoding = encoding
        self.poll_interval = poll_interval

        # State tracking
        self._position = 0
        self._running = False
        self._observer = None
        self._monitor_thread = None
        self._lock = threading.Lock()

        # Callbacks
        self.callbacks: Dict[str, List[Callable]] = {
            "line": [],  # Called when a new line is available
            "data": [],  # Called when new data chunk arrives
            "eof": [],  # Called when EOF reached
            "error": [],  # Called on errors
        }

        log.info(
            f"HHTailer initialized for {filepath} (encoding: {encoding}, "
            f"using {'watchdog' if WATCHDOG_AVAILABLE else 'polling'})"
        )

    def register_callback(self, event_type: str, callback: Callable) -> None:
        """Register a callback for an event.

        Args:
            event_type: Type of event ('line', 'data', 'eof', 'error')
            callback: Callable that takes (filepath, data) as arguments
        """
        if event_type not in self.callbacks:
            raise ValueError(f"Unknown event type: {event_type}")
        self.callbacks[event_type].append(callback)
        log.debug(f"Registered callback for event '{event_type}'")

    def start(self) -> None:
        """Start monitoring the file.

        Initializes the appropriate monitoring mechanism (watchdog or polling)
        and starts the monitoring thread.
        """
        if self._running:
            log.warning("HHTailer is already running")
            return

        # Check file exists
        if not os.path.exists(self.filepath):
            raise FileNotFoundError(f"File not found: {self.filepath}")

        self._running = True
        self._position = 0

        if WATCHDOG_AVAILABLE:
            self._start_watchdog()
        else:
            self._start_polling()

        log.info(f"HHTailer started for {self.filepath}")

    def stop(self) -> None:
        """Stop monitoring the file."""
        self._running = False

        if self._observer is not None:
            self._observer.stop()
            self._observer.join()

        if self._monitor_thread is not None:
            self._monitor_thread.join(timeout=5)

        log.info(f"HHTailer stopped for {self.filepath}")

    def _start_watchdog(self) -> None:
        """Start watchdog-based file monitoring."""
        try:
            watch_dir = os.path.dirname(self.filepath)
            handler = HHTailerEventHandler(
                self.filepath, self._on_file_modified
            )

            self._observer = Observer()
            self._observer.schedule(handler, watch_dir, recursive=False)
            self._observer.start()

            log.debug(f"Watchdog started for {watch_dir}")
        except Exception as e:
            log.warning(f"Failed to start watchdog: {e}, falling back to polling")
            self._observer = None
            self._start_polling()

    def _start_polling(self) -> None:
        """Start polling-based file monitoring."""
        self._monitor_thread = threading.Thread(
            target=self._polling_loop, daemon=True
        )
        self._monitor_thread.start()
        log.debug(f"Polling thread started with interval {self.poll_interval}s")

    def _polling_loop(self) -> None:
        """Poll the file for new data."""
        while self._running:
            try:
                self._read_new_data()
                time.sleep(self.poll_interval)
            except Exception as e:
                log.exception(f"Error in polling loop: {e}")
                self._fire_callback("error", str(e))

    def _on_file_modified(self, event) -> None:
        """Handle watchdog file modification event."""
        try:
            self._read_new_data()
        except Exception as e:
            log.exception(f"Error handling file modification: {e}")
            self._fire_callback("error", str(e))

    def _read_new_data(self) -> None:
        """Read new data from the file since last position."""
        with self._lock:
            if not os.path.exists(self.filepath):
                log.warning(f"File disappeared: {self.filepath}")
                return

            try:
                with open(
                    self.filepath, "r", encoding=self.encoding, errors="replace"
                ) as f:
                    f.seek(self._position)
                    data = f.read(self.READ_CHUNK_SIZE)

                    if not data:
                        # EOF reached
                        if self._position > 0:
                            self._fire_callback("eof", None)
                        return

                    self._position = f.tell()

                    # Fire data callback
                    self._fire_callback("data", data)

                    # Parse lines and fire line callbacks
                    self._process_lines(data)

            except UnicodeDecodeError as e:
                log.warning(
                    f"Unicode error in {self.filepath} at position {self._position}: {e}"
                )
                # Try to recover by skipping bad byte
                self._position += 1
            except IOError as e:
                log.warning(f"IO error reading {self.filepath}: {e}")

    def _process_lines(self, data: str) -> None:
        """Process data and fire line callbacks for complete lines.

        Args:
            data: New data chunk to process
        """
        lines = data.split("\n")

        # All but the last line are complete
        for line in lines[:-1]:
            if line.rstrip():  # Skip empty lines
                self._fire_callback("line", line)

        # Last item might be incomplete, keep it for next read
        # (This is handled by reading from the file position)

    def _fire_callback(self, event_type: str, data: Any) -> None:
        """Fire all callbacks for an event type.

        Args:
            event_type: Type of event
            data: Data to pass to callbacks
        """
        callbacks = self.callbacks.get(event_type, [])
        for callback in callbacks:
            try:
                if data is not None:
                    callback(self.filepath, data)
                else:
                    callback(self.filepath)
            except Exception as e:
                log.exception(
                    f"Error in callback for event '{event_type}': {e}"
                )

    def get_position(self) -> int:
        """Get current read position in the file.

        Returns:
            Current byte position in the file
        """
        with self._lock:
            return self._position

    def set_position(self, position: int) -> None:
        """Set read position in the file.

        Useful for resuming from a saved position.

        Args:
            position: Byte position to seek to
        """
        with self._lock:
            self._position = max(0, min(position, os.path.getsize(self.filepath)))
            log.debug(f"Position set to {self._position}")

    def seek_to_end(self) -> None:
        """Seek to end of file (only read new data from now on)."""
        with self._lock:
            if os.path.exists(self.filepath):
                self._position = os.path.getsize(self.filepath)
                log.debug(f"Seeked to end of file (position: {self._position})")
