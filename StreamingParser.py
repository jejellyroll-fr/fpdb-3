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
StreamingParser: Incremental hand history parsing for live streaming

Parses hand history data line-by-line as it arrives from HHTailer,
maintaining state about partial hands and buffering until complete hands
can be sent for database insertion.

Uses a state machine to track parsing progress:
  IDLE → HAND_START → IN_HAND → HAND_COMPLETE → SEND_TO_DB
"""

import re
from enum import Enum
from typing import Callable, List, Optional, Dict, Any, Tuple
from datetime import datetime

from loggingFpdb import get_logger

log = get_logger("streaming_parser")


class ParsingState(Enum):
    """State machine states for hand history parsing."""

    IDLE = 0  # Waiting for hand start
    HAND_START = 1  # Found hand header line
    IN_HAND = 2  # Currently parsing a hand
    HAND_COMPLETE = 3  # Hand fully parsed
    ERROR = 4  # Parse error occurred


class StreamingParser:
    """Incremental hand history parser for live streaming.

    Processes hand history data line-by-line as it arrives from HHTailer.
    Maintains state about partial hands and buffers until complete hands
    can be processed.

    Attributes:
        site_name: Name of the poker site (e.g., 'PokerStars', 'Bovada')
        state: Current parsing state
        current_hand: Buffer for the current hand being parsed
        callbacks: List of callbacks for completed hands
        line_count: Total lines processed
        hand_count: Total complete hands parsed
    """

    # Hand start patterns for different sites
    HAND_START_PATTERNS = {
        "PokerStars": re.compile(r"^PokerStars (Hand|Zoom) #"),
        "Bovada": re.compile(r"^Bovada Hand #"),
        "Winamax": re.compile(r"^Winamax Hand #"),
        "GGPoker": re.compile(r"^GGPoker Hand #"),
        "PartyPoker": re.compile(r"^PartyPoker Hand #"),
        "Unibet": re.compile(r"^Unibet Hand #"),
        "iPoker": re.compile(r"^iPoker Hand #"),
        "Cake": re.compile(r"^Cake Poker Hand #"),
    }

    # Hand end patterns
    HAND_END_PATTERNS = [
        re.compile(r"^Uncalled bet .* returned to"),  # Uncalled bet end
        re.compile(r"^Hand was (folded|run twice)"),  # Fold/run twice end
        re.compile(r"^Board:"),  # Board indicator
        re.compile(r"^\*\*\* SHOW DOWN \*\*\*"),  # Show down
        re.compile(r"^\*\*\* SUMMARY \*\*\*"),  # Summary start (hand end)
    ]

    def __init__(self, site_name: str = "PokerStars") -> None:
        """Initialize the streaming parser.

        Args:
            site_name: Name of poker site to determine parsing patterns
        """
        self.site_name = site_name
        self.state = ParsingState.IDLE
        self.current_hand: List[str] = []
        self.callbacks: Dict[str, List[Callable]] = {
            "hand_complete": [],  # Called with (hand_lines,)
            "hand_start": [],  # Called with (hand_header,)
            "parsing_error": [],  # Called with (error_msg,)
        }

        # Statistics
        self.line_count = 0
        self.hand_count = 0
        self.error_count = 0

        # Determine hand start pattern for this site
        self.hand_start_pattern = self.HAND_START_PATTERNS.get(
            site_name, self.HAND_START_PATTERNS["PokerStars"]
        )

        log.info(f"StreamingParser initialized for {site_name}")

    def register_callback(self, event_type: str, callback: Callable) -> None:
        """Register a callback for an event.

        Args:
            event_type: Type of event ('hand_complete', 'hand_start', 'parsing_error')
            callback: Callable that takes specific arguments based on event type

        Raises:
            ValueError: If event_type is not recognized
        """
        if event_type not in self.callbacks:
            raise ValueError(f"Unknown event type: {event_type}")
        self.callbacks[event_type].append(callback)
        log.debug(f"Registered callback for event '{event_type}'")

    def process_line(self, line: str) -> None:
        """Process a single line from the hand history file.

        Args:
            line: A single line of text from the hand history file
        """
        self.line_count += 1
        line = line.rstrip()

        if not line:
            # Empty lines are allowed in hand histories
            if self.state == ParsingState.IN_HAND:
                self.current_hand.append(line)
            return

        try:
            if self.state == ParsingState.IDLE:
                self._handle_idle(line)
            elif self.state == ParsingState.HAND_START:
                self._handle_hand_start(line)
            elif self.state == ParsingState.IN_HAND:
                self._handle_in_hand(line)

        except Exception as e:
            log.exception(f"Error processing line {self.line_count}: {e}")
            self.error_count += 1
            self._fire_callback("parsing_error", str(e))
            self.state = ParsingState.ERROR

    def process_chunk(self, chunk: str) -> None:
        """Process a chunk of data (multiple lines).

        Args:
            chunk: String containing one or more lines (separated by \\n)
        """
        lines = chunk.split("\n")
        for line in lines:
            self.process_line(line)

    def _handle_idle(self, line: str) -> None:
        """Handle a line when in IDLE state (looking for hand start).

        Args:
            line: The line to check for hand start pattern
        """
        if self.hand_start_pattern.match(line):
            self.state = ParsingState.HAND_START
            self.current_hand = [line]
            self._fire_callback("hand_start", line)
            log.debug(f"Hand start detected: {line[:50]}...")

    def _handle_hand_start(self, line: str) -> None:
        """Handle a line when in HAND_START state.

        Just collect the line and transition to IN_HAND.

        Args:
            line: The line to add to current hand
        """
        self.current_hand.append(line)
        self.state = ParsingState.IN_HAND

    def _handle_in_hand(self, line: str) -> None:
        """Handle a line when IN_HAND state (parsing hand content).

        Checks for hand end conditions and processes accordingly.

        Args:
            line: The line to check for hand end or add to current hand
        """
        self.current_hand.append(line)

        # Check if this line indicates end of hand
        if self._is_hand_end(line):
            self._complete_hand()

    def _is_hand_end(self, line: str) -> bool:
        """Check if a line indicates the end of a hand.

        Args:
            line: The line to check

        Returns:
            True if line indicates hand end, False otherwise
        """
        # Summary section ends the hand
        if line.strip().startswith("*** SUMMARY ***"):
            return True

        # A new hand starting means previous one is complete
        if self.hand_start_pattern.match(line):
            # Remove the new hand line from current hand
            self.current_hand.pop()
            return True

        # Check other end patterns
        for pattern in self.HAND_END_PATTERNS:
            if pattern.match(line):
                # These don't immediately end, but indicate we're in summary
                return False

        return False

    def _complete_hand(self) -> None:
        """Mark current hand as complete and fire callback."""
        if not self.current_hand:
            return

        self.hand_count += 1
        hand_text = "\n".join(self.current_hand)

        log.debug(
            f"Hand {self.hand_count} complete ({len(self.current_hand)} lines)"
        )

        # Fire callback
        self._fire_callback("hand_complete", self.current_hand)

        # Reset state
        self.state = ParsingState.IDLE
        self.current_hand = []

    def _fire_callback(self, event_type: str, data: Any) -> None:
        """Fire all callbacks for an event type.

        Args:
            event_type: Type of event
            data: Data to pass to callbacks
        """
        callbacks = self.callbacks.get(event_type, [])
        for callback in callbacks:
            try:
                callback(data)
            except Exception as e:
                log.exception(
                    f"Error in callback for event '{event_type}': {e}"
                )

    def get_statistics(self) -> Dict[str, int]:
        """Get parsing statistics.

        Returns:
            Dictionary with line_count, hand_count, and error_count
        """
        return {
            "line_count": self.line_count,
            "hand_count": self.hand_count,
            "error_count": self.error_count,
        }

    def reset_statistics(self) -> None:
        """Reset statistics counters."""
        self.line_count = 0
        self.hand_count = 0
        self.error_count = 0

    def flush(self) -> Optional[List[str]]:
        """Flush any buffered partial hand.

        Returns:
            List of lines if there's a partial hand, None otherwise
        """
        if self.state == ParsingState.IN_HAND and self.current_hand:
            hand = self.current_hand
            self.current_hand = []
            self.state = ParsingState.IDLE
            return hand
        return None
