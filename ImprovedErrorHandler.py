#!/usr/bin/env python3
"""Improved error handler for import operations to prevent unnecessary HUD restarts.

This module provides better error classification and handling to distinguish
between temporary parsing issues and permanent file corruption.
"""

import time
from dataclasses import dataclass
from enum import Enum

from loggingFpdb import get_logger

log = get_logger("improved_error_handler")


class ErrorSeverity(Enum):
    """Classification of error severity levels."""

    TEMPORARY = "temporary"  # Retry possible, don't reset file position
    RECOVERABLE = "recoverable"  # Minor adjustment needed
    PERMANENT = "permanent"  # File position reset required


@dataclass
class ParseError:
    """Container for parse error information."""

    error_type: str
    message: str
    severity: ErrorSeverity
    hand_text: str
    timestamp: float
    retry_count: int = 0


class ImprovedErrorHandler:
    """Enhanced error handler for import operations."""

    def __init__(self) -> None:
        """Initialize the error handler."""
        self.error_history: dict[str, list[ParseError]] = {}
        self.max_retries = 3
        self.temporary_error_threshold = 5  # Max temporary errors before treating as permanent

        # Patterns that indicate temporary vs permanent errors
        self.temporary_error_patterns = [
            "connection",
            "timeout",
            "network",
            "temporary",
            "lock",
            "busy",
        ]

        self.permanent_error_patterns = [
            "invalid format",
            "corrupted",
            "malformed",
            "syntax error",
            "unexpected end",
        ]

    def classify_error(self, error_message: str, hand_text: str) -> ErrorSeverity:
        """Classify error severity based on error message and context.

        Args:
            error_message: The error message
            hand_text: The problematic hand text

        Returns:
            ErrorSeverity classification
        """
        error_lower = error_message.lower()

        # Check for permanent error indicators
        for pattern in self.permanent_error_patterns:
            if pattern in error_lower:
                return ErrorSeverity.PERMANENT

        # Check for temporary error indicators
        for pattern in self.temporary_error_patterns:
            if pattern in error_lower:
                return ErrorSeverity.TEMPORARY

        # Analyze hand text characteristics
        if len(hand_text.strip()) < 50:
            return ErrorSeverity.RECOVERABLE  # Likely incomplete hand

        # Check for common partial hand indicators
        if not any(keyword in hand_text.lower() for keyword in ["hand #", "seat ", "dealt to"]):
            return ErrorSeverity.RECOVERABLE

        # Default to recoverable for unknown errors
        return ErrorSeverity.RECOVERABLE

    def should_reset_file_position(self, file_path: str, error: ParseError) -> bool:
        """Determine if file position should be reset based on error history.

        Args:
            file_path: Path to the file being processed
            error: The current parse error

        Returns:
            True if file position should be reset, False otherwise
        """
        if error.severity == ErrorSeverity.PERMANENT:
            log.info(f"Permanent error detected for {file_path}, resetting file position")
            return True

        if error.severity == ErrorSeverity.TEMPORARY:
            # Don't reset for temporary errors
            log.debug(f"Temporary error for {file_path}, maintaining file position")
            return False

        # For recoverable errors, check history
        if file_path not in self.error_history:
            self.error_history[file_path] = []

        recent_errors = [e for e in self.error_history[file_path] if time.time() - e.timestamp < 300]  # Last 5 minutes

        if len(recent_errors) >= self.temporary_error_threshold:
            log.warning(f"Too many recent errors for {file_path}, treating as permanent")
            return True

        return False

    def record_error(self, file_path: str, error_type: str, message: str, hand_text: str) -> ParseError:
        """Record a parse error and return error information.

        Args:
            file_path: Path to the file being processed
            error_type: Type of error (partial, error, etc.)
            message: Error message
            hand_text: Problematic hand text

        Returns:
            ParseError object with classification
        """
        severity = self.classify_error(message, hand_text)

        error = ParseError(
            error_type=error_type,
            message=message,
            severity=severity,
            hand_text=hand_text[:200],  # Truncate for storage
            timestamp=time.time(),
        )

        if file_path not in self.error_history:
            self.error_history[file_path] = []

        self.error_history[file_path].append(error)

        # Cleanup old errors (older than 1 hour)
        cutoff_time = time.time() - 3600
        self.error_history[file_path] = [e for e in self.error_history[file_path] if e.timestamp > cutoff_time]

        log.debug(f"Recorded {severity.value} error for {file_path}: {message}")
        return error

    def should_retry_import(self, file_path: str, error: ParseError) -> bool:
        """Determine if import should be retried.

        Args:
            file_path: Path to the file being processed
            error: The parse error

        Returns:
            True if import should be retried, False otherwise
        """
        if error.severity == ErrorSeverity.PERMANENT:
            return False

        if error.retry_count >= self.max_retries:
            log.warning(f"Max retries reached for {file_path}")
            return False

        return error.severity in [ErrorSeverity.TEMPORARY, ErrorSeverity.RECOVERABLE]

    def get_error_statistics(self, file_path: str) -> dict[str, int]:
        """Get error statistics for a file.

        Args:
            file_path: Path to the file

        Returns:
            Dictionary with error counts by severity
        """
        if file_path not in self.error_history:
            return {"temporary": 0, "recoverable": 0, "permanent": 0}

        stats = {"temporary": 0, "recoverable": 0, "permanent": 0}
        for error in self.error_history[file_path]:
            stats[error.severity.value] += 1

        return stats

    def cleanup_file_history(self, file_path: str) -> None:
        """Clean up error history for a file (e.g., when file processing is complete).

        Args:
            file_path: Path to the file
        """
        if file_path in self.error_history:
            del self.error_history[file_path]
            log.debug(f"Cleaned up error history for {file_path}")


# Global instance for easy usage
_error_handler_instance = None


def get_improved_error_handler() -> ImprovedErrorHandler:
    """Return global instance of improved error handler."""
    global _error_handler_instance
    if _error_handler_instance is None:
        _error_handler_instance = ImprovedErrorHandler()
    return _error_handler_instance
