"""FPDB logging configuration and utilities.

This module provides custom logging functionality for FPDB, including colored console output,
JSON file formatting, and advanced log rotation capabilities.
"""

import inspect
import json
import logging
import os
import re
import time
from logging.handlers import TimedRotatingFileHandler
from typing import Any

import colorlog

# Define default logging and debugging modes


def set_default_logging() -> None:
    """Configure the global logging level to display only warnings and errors.

    This function sets the root logger's level to WARNING, ensuring that only messages
    with a severity of WARNING and above are displayed.
    """
    logging.getLogger().setLevel(logging.WARNING)


def enable_debug_logging() -> None:
    """Configure the global logging level to display all log levels, including INFO and DEBUG.

    This function sets the root logger's level to DEBUG, allowing all messages, including
    those with lower severity, to be displayed.
    """
    logging.getLogger().setLevel(logging.DEBUG)


class FpdbLogFormatter(colorlog.ColoredFormatter):
    """Custom formatter for FPDB logs with variable highlighting.

    This formatter extends colorlog.ColoredFormatter to add specific coloring to variables
    within log messages, enhancing readability.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the formatter with color codes for variables.

        Args:
            *args: Positional arguments passed to the parent constructor.
            **kwargs: Keyword arguments passed to the parent constructor.

        """
        super().__init__(*args, **kwargs)
        self.var_color = "\033[36m"  # ANSI code for cyan color, used for variables
        self.reset_color = "\033[0m"  # ANSI code to reset color

    def format(self, record: logging.LogRecord) -> str:
        """Format the log message by highlighting variables.

        Args:
            record (LogRecord): The log record to format.

        Returns:
            str: The formatted log message with variables highlighted.

        """
        if hasattr(record, "msg"):
            # Apply coloring to variables in the message
            record.msg = self._colorize_variables(record.msg)
        return super().format(record)

    def _colorize_variables(self, message: str) -> str:
        """Apply coloring to variables present in the message.

        Variables are identified by single or double quotes.
        For example, in "Variable 'x' is set", 'x' will be colored in cyan.

        Args:
            message (str): The log message potentially containing variables.

        Returns:
            str: The message with variables colored.

        """
        if not isinstance(message, str):

            return message  # If the message is not a string, return it as is

        # Define a regex pattern to capture strings enclosed in single or double quotes
        pattern = r"'([^']*)'|\"([^\"]*)\""

        def repl(match: re.Match[str]) -> str:
            """Replacement function used by re.sub.

            It colors the captured variable in cyan.

            Args:
                match (re.Match): The regex match object.

            Returns:
                str: The captured variable with color codes added.

            """
            var = match.group(1) or match.group(
                2,
            )  # Extract the variable without quotes
            return f"{self.var_color}'{var}'{self.reset_color}"  # Add color codes around the quotes

        # Use re.sub to replace all occurrences of variables with their colored versions
        return re.sub(pattern, repl, message)


class JsonFormatter(logging.Formatter):
    """Formatter that converts log records to JSON format.

    This formatter facilitates automated log analysis by structuring logs in JSON.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as a JSON object containing key information.

        The included fields are:
            - asctime : Timestamp of the log event.
            - name : Name of the logger.
            - levelname : Severity level (DEBUG, INFO, etc.).
            - module : Name of the module where the log was generated.
            - funcName : Name of the function where the log was generated.
            - message : The log message itself.

        Args:
            record (LogRecord): The log record to format.

        Returns:
            str: The JSON representation of the log record.

        """
        record_dict = {
            "asctime": self.formatTime(record, self.datefmt),  # Format the timestamp
            "name": record.name,  # Logger name
            "levelname": record.levelname,  # Log level
            "module": record.module,  # Originating module
            "funcName": record.funcName,  # Originating function
            "message": record.getMessage(),  # Log message
        }
        return json.dumps(record_dict)  # Convert the dictionary to a JSON string


class TimedSizedRotatingFileHandler(TimedRotatingFileHandler):
    """Log file handler that performs rotation based on both time and file size.

    This handler rotates the log file at specified time intervals and when the file
    reaches a certain size. Rotated files include the date and a part number in their name.
    """

    def __init__(  # noqa: PLR0913
        self,
        filename: str,
        when: str = "midnight",
        interval: int = 1,
        backup_count: int = 0,
        encoding: str | None = None,
        delay: bool = False,  # noqa: FBT001, FBT002
        utc: bool = False,  # noqa: FBT001, FBT002
        at_time: Any = None,
        max_bytes: int = 0,
    ) -> None:
        """Initialize the handler with parameters for time-based and size-based rotation.

        Args:
            filename (str): Path to the log file.
            when (str): Time interval for rotation ('midnight' by default).
            interval (int): Rotation interval (1 by default).
            backupCount (int): Number of backup files to keep.
            encoding (str): Encoding of the log file.
            delay (bool): If True, file opening is deferred until the first log message.
            utc (bool): If True, use UTC for time-based rotation.
            atTime (datetime.time): Specific time for time-based rotation.
            maxBytes (int): Maximum file size in bytes before rotation.
            at_time (datetime.time): Specific time for time-based rotation.
            backup_count (int): Number of backup files to keep.
            max_bytes (int): Maximum file size in bytes before rotation.

        """
        super().__init__(
            filename, when, interval, backup_count, encoding, delay, utc, at_time,
        )
        self.max_bytes = max_bytes  # Maximum size before size-based rotation
        self.part = 1  # Initialize part number for rotated files
        self.currentDate = time.strftime(
            "%Y-%m-%d",
        )  # Current date in YYYY-MM-DD format

    def shouldRollover(self, _record: logging.LogRecord) -> bool:
        """Determine whether the log file should be rotated.

        This method checks both time-based and size-based rotation conditions.

        Args:
            record (LogRecord): The current log record.

        Returns:
            bool: True if rotation should occur, False otherwise.

        """
        t = int(time.time())  # Current time in seconds since epoch
        if t >= self.rolloverAt:
            # If current time exceeds the scheduled rollover time
            self.part = 1  # Reset part number
            self.currentDate = time.strftime("%Y-%m-%d")  # Update current date
            return True  # Indicate that a rollover is needed

        if self.max_bytes > 0:
            # If a size limit is set, check the current file size
            self.stream.seek(0, os.SEEK_END)  # Move to the end of the file
            if self.stream.tell() >= self.max_bytes:
                # If current file size exceeds max_bytes
                return True  # Indicate that a rollover is needed

        return False  # No rollover condition met

    def doRollover(self) -> None:
        """Perform the log file rollover.

        This method renames the current log file, deletes old log files if necessary,
        and sets up the next rollover time.
        """
        self.stream.close()  # Close the current log file stream
        current_time = int(time.time())  # Current time
        time_tuple = time.localtime(current_time)  # Convert time to struct_time
        date_str = time.strftime("%d-%m-%Y", time_tuple)  # Format date as DD-MM-YYYY

        # Construct the rotated file name with date and part number
        dfn = f"{self.baseFilename}-{date_str}-part{self.part}.txt"

        # Increment the part number for the next rollover
        self.part += 1

        # Perform the file rotation
        if os.path.exists(dfn):  # noqa: PTH110
            os.remove(dfn)  # Remove the file if it already exists to avoid conflicts  # noqa: PTH107
        os.rename(self.baseFilename, dfn)  # Rename the current log file to the new name  # noqa: PTH104

        # Delete old log files if necessary
        if self.backupCount > 0:
            for s in self.getFilesToDelete():
                os.remove(s)  # Remove files exceeding the backup count  # noqa: PTH107

        # Reopen the log file stream if delay is not enabled
        if not self.delay:
            self.stream = self._open()  # Open a new log file

        # Calculate the next rollover time based on the current time
        new_rollover_at = self.computeRollover(current_time)
        while new_rollover_at <= current_time:
            new_rollover_at += (
                self.interval
            )  # Add the interval until rolloverAt is in the future
        self.rolloverAt = new_rollover_at  # Update rolloverAt

    def getFilesToDelete(self) -> list[str]:
        """Determine which log files should be deleted during rollover.

        This method is overridden to match the rotated file naming pattern.
        It searches for all files that start with the base name and end with '.txt',
        then retains only the most recent files based on backupCount.

        Returns:
            list: List of full paths to log files that should be deleted.

        """
        dir_name, base_name = os.path.split(
            self.baseFilename,
        )  # Split directory and base filename
        file_names = os.listdir(dir_name)  # List all files in the directory
        result = [
            os.path.join(dir_name, file_name)  # noqa: PTH118
            for file_name in file_names
            if file_name.startswith(base_name) and file_name.endswith(".txt")
        ]
        result.sort()  # Sort files alphabetically (usually chronological if dates are in the name)

        # If the number of files exceeds backupCount, return the oldest files to delete
        if len(result) <= self.backupCount:
            return []  # No files to delete
        # Return the excess files, i.e., the oldest ones
        return result[: len(result) - self.backupCount]


def setup_logging(log_dir: str | None = None, *, console_only: bool = False) -> None:
    """Configure the logging system.

    This function sets up console and file handlers with custom formatters,
    applies color coding for console logs, and manages log file rotation.

    Args:
        log_dir (str, optional): Path to the directory where logs will be stored.
            If None, the default directory is '~/fpdb_logs'.
        console_only (bool, optional): If True, only the console handler is configured.
            By default, both console and file handlers are set up.

    Raises:
        Exception: If an error occurs during logging configuration.

    """
    try:
        # Configure the console handler with color coding
        log_colors = {
            "DEBUG": "green",
            "INFO": "blue",
            "WARNING": "yellow",
            "ERROR": "red",
        }
        log_format = (
            "%(log_color)s%(asctime)s [%(name)s:%(module)s:%(funcName)s] "
            "[%(levelname)s] %(message)s%(reset)s"
        )
        date_format = "%Y-%m-%d %H:%M:%S"
        formatter = colorlog.ColoredFormatter(
            fmt=log_format, datefmt=date_format, log_colors=log_colors,
        )

        # Create a stream handler for the console
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)  # Apply the colored formatter
        console_handler.setLevel(logging.DEBUG)  # Minimum log level for the console

        # Configure the root logger
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)  # Default level set to INFO

        # Remove existing handlers to prevent duplicate logs
        logger.handlers = []
        logger.addHandler(console_handler)  # Add the console handler

        if not console_only:
            # Set the log directory if not specified
            if log_dir is None:
                log_dir = os.path.join(os.path.expanduser("~"), "fpdb_logs")  # noqa: PTH118, PTH111
            log_dir = os.path.normpath(log_dir)  # Normalize the directory path
            os.makedirs(  # noqa: PTH103
                log_dir, exist_ok=True,
            )  # Create the directory if it doesn't exist
            log_file = os.path.join(  # noqa: PTH118
                log_dir, "fpdb-log.txt",
            )  # Full path to the log file

            # Use the custom TimedSizedRotatingFileHandler
            max_bytes = 1024 * 1024  # 1 MB
            backup_count = 30  # Keep logs for 30 rotations
            file_formatter = JsonFormatter(
                datefmt=date_format,
            )  # Use JsonFormatter for files
            file_handler = TimedSizedRotatingFileHandler(
                log_file,
                when="midnight",  # Daily rotation at midnight
                interval=1,  # Every day
                backup_count=backup_count,
                encoding="utf-8",
                max_bytes=max_bytes,
            )
            file_handler.setFormatter(file_formatter)  # Apply the JSON formatter
            file_handler.setLevel(logging.DEBUG)  # Minimum log level for the file

            logger.addHandler(file_handler)  # Add the file handler to the root logger


    except Exception:  # noqa: TRY302
        raise  # Re-raise the exception after printing the error


def update_log_level(logger_name: str, level: int) -> None:
    """Update the logging level for a specific logger.

    This function allows dynamic modification of a logger's severity level.

    Args:
        logger_name (str): The name of the logger whose level needs to be updated.
        level (int): The new logging level (e.g., logging.DEBUG).

    """
    logger = logging.getLogger(logger_name)
    logger.setLevel(level)


class FpdbLogger:
    """Custom logger for FPDB.

    This class provides a simplified interface for logging with methods for different
    levels (debug, info, warning, error) and dynamically manages the stack level
    to ensure accurate log information.
    """

    def __init__(self, name: str) -> None:
        """Initialize the FpdbLogger with a specific name.

        Args:
            name (str): The name of the logger (typically __name__ of the calling module).

        """
        self.logger = logging.getLogger(name)  # Obtain a logger with the specified name

    def debug(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log a debug message.

        Args:
            msg (str): The log message.
            *args: Positional arguments for message formatting.
            **kwargs: Keyword arguments for message formatting.

        """
        stacklevel = (
            self._get_stacklevel()
        )  # Calculate stack level for accurate information
        self.logger.debug(msg, *args, stacklevel=stacklevel, **kwargs)

    def info(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log an informational message.

        Args:
            msg (str): The log message.
            *args: Positional arguments for message formatting.
            **kwargs: Keyword arguments for message formatting.

        """
        stacklevel = self._get_stacklevel()
        self.logger.info(msg, *args, stacklevel=stacklevel, **kwargs)

    def warning(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log a warning message.

        Args:
            msg (str): The log message.
            *args: Positional arguments for message formatting.
            **kwargs: Keyword arguments for message formatting.

        """
        stacklevel = self._get_stacklevel()
        self.logger.warning(msg, *args, stacklevel=stacklevel, **kwargs)

    def error(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log an error message.

        Args:
            msg (str): The log message.
            *args: Positional arguments for message formatting.
            **kwargs: Keyword arguments for message formatting.

        """
        stacklevel = self._get_stacklevel()
        self.logger.error(msg, *args, stacklevel=stacklevel, **kwargs)

    def exception(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log an exception message with stack trace.

        Args:
            msg (str): The log message.
            *args: Positional arguments for message formatting.
            **kwargs: Keyword arguments for message formatting.

        """
        stacklevel = self._get_stacklevel()
        self.logger.exception(msg, *args, stacklevel=stacklevel, **kwargs)

    def setLevel(self, level: int) -> None:
        """Set the logging level for this logger.

        Args:
            level (int): The new logging level (e.g., logging.DEBUG).

        """
        self.logger.setLevel(level)

    def getEffectiveLevel(self) -> int:
        """Get the effective logging level for this logger.

        Returns:
            int: The effective logging level.

        """
        return self.logger.getEffectiveLevel()

    def _get_stacklevel(self) -> int:
        """Calculate the stack level to pass to the underlying logger.

        This method inspects the call stack to determine the appropriate stack level
        so that log records reflect accurate line numbers and function names.

        Returns:
            int: The calculated stack level for the logger.

        """
        frame = inspect.currentframe()  # Get the current frame
        stacklevel = 1  # Initialize stack level
        while frame:
            co_name = frame.f_code.co_name  # Get the function name of the current frame
            if co_name in (
                "debug",
                "info",
                "warning",
                "error",
                "__init__",
                "_get_stacklevel",
            ):
                # If the function name is one of the logging methods or internal methods,
                # continue traversing the stack
                frame = frame.f_back  # Move to the previous frame
                stacklevel += 1  # Increment the stack level
            else:
                break  # Stop if a different function name is encountered
        return stacklevel  # Return the calculated stack level


def get_logger(name: str) -> FpdbLogger:
    """Return a configured FPDB logger.

    This function provides an instance of FpdbLogger configured with the specified name.

    Args:
        name (str): The name of the logger (typically __name__ of the calling module).

    Returns:
        FpdbLogger: An instance of FpdbLogger ready for use.

    """
    return FpdbLogger(name)


