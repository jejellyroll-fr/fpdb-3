"""How the HUD hears about new hands: the ZMQ worker and receiver."""

import time
from typing import Any

import zmq as _zmq
from PySide6.QtCore import QObject, QThread, Signal

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


class ZMQReceiver(QObject):
    """A QObject to receive ZMQ messages."""

    message_received = Signal(str)

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
