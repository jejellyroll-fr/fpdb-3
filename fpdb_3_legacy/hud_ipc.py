"""How the HUD hears about new hands and live actions: the ZMQ worker and receiver."""

import json
import time
from collections.abc import Mapping
from typing import Any

import zmq as _zmq
from PySide6.QtCore import QObject, QThread, Signal

from fpdb_3_legacy.Importer import LIVE_ACTION_PREFIX

zmq: Any = _zmq
from fpdb_3_legacy.hud_main_base import log


class ZMQWorker(QThread):
    """A QThread to run the ZMQ message processing loop."""

    error_occurred = Signal(str)

    def __init__(self, zmq_receiver: "ZMQReceiver") -> None:
        """Initialize the ZMQ worker."""
        super().__init__()
        self.zmq_receiver = zmq_receiver
        self.is_running = True

    def run(self) -> None:
        """Run the ZMQ message processing loop."""
        log.info("ZMQWorker started and listening for messages")
        while self.is_running:
            try:
                self.zmq_receiver.process_message()
            except Exception:
                log.exception("Error in ZMQWorker")
                self.error_occurred.emit("Error in ZMQWorker")
            time.sleep(0.01)  # Short delay to avoid excessive CPU usage

    def stop(self) -> None:
        """Stop the worker thread."""
        self.is_running = False
        self.wait()



def parse_live_message(message: str) -> dict[str, Any] | None:
    """The live-action payload a ZMQ message carries, or ``None``.

    A capture sends two things on one socket: a bare hand id, and a prefixed
    JSON payload naming an action still being played (#336). Anything malformed
    answers ``None`` and is logged rather than raised -- one bad packet must
    not take the receiver thread down with it.
    """
    if not message.startswith(LIVE_ACTION_PREFIX):
        return None
    try:
        payload = json.loads(message[len(LIVE_ACTION_PREFIX):])
    except ValueError:
        log.warning("Dropping a malformed live-action message (%s chars)", len(message))
        return None
    return payload if isinstance(payload, dict) else None



def route_live_action(payload: dict[str, Any], tables: Mapping[str, str], huds: Mapping[str, Any]) -> Any:
    """The HUD a live action belongs to, or ``None`` when no table claims it.

    The capture derives a table id from the hand number; HUD_main learns which
    of its HUDs serves that table the first time it imports one of its hands,
    keyed by the table name's last token, which is that same id for a cash game
    and its trailing number for a tournament. Until a table's first hand has
    been imported there is no HUD to route to, and the action is dropped: the
    panels fall back to the hand-refresh path, which is what they did before
    live context existed.
    """
    table = str(payload.get("table") or "").strip()
    key = tables.get(table)
    return huds.get(key) if key is not None else None



class ZMQReceiver(QObject):
    """A QObject to receive ZMQ messages."""

    message_received = Signal(str)
    live_action_received = Signal(dict)

    def __init__(self, port: str = "5555", parent: QObject | None = None) -> None:
        """Initialize the ZMQ receiver."""
        super().__init__(parent)
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.PULL)
        self.socket.bind(f"tcp://127.0.0.1:{port}")
        log.info("ZMQ receiver bound to port %s", port)
        # Set socket options for better debugging
        self.socket.setsockopt(zmq.RCVTIMEO, 1000)  # 1 second timeout

        # Heartbeat configuration
        self.poller = zmq.Poller()
        self.poller.register(self.socket, zmq.POLLIN)

    def process_message(self) -> None:
        """Process a ZMQ message."""
        if self.socket.closed:
            return
        try:
            socks = dict(self.poller.poll(1000))  # Timeout 1 seconde
            if self.socket.closed:
                return
            if self.socket in socks and socks[self.socket] == zmq.POLLIN:
                message = self.socket.recv_string(zmq.NOBLOCK)
                payload = parse_live_message(message)
                if payload is not None:
                    self.live_action_received.emit(payload)
                else:
                    log.info("ZMQ received hand ID: %s", message)
                    self.message_received.emit(message)
            else:
                # Heartbeat
                log.debug("Heartbeat: No message received")
        except zmq.ZMQError as e:
            if e.errno == zmq.EAGAIN:
                pass  # No message available
            elif hasattr(zmq, "ENOTSOCK") and e.errno == zmq.ENOTSOCK:
                log.info("ZMQ socket closed during poll")
            elif "non-socket" in str(e):
                log.info("ZMQ socket closed during poll")
            else:
                log.exception("ZMQ error")

    def close(self) -> None:
        """Close the ZMQ socket and context."""
        if not self.socket.closed:
            self.socket.close()
        self.context.term()
        log.info("ZMQ receiver closed")

