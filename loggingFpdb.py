import os
import re
import logging
import colorlog
import inspect
import json
from logging.handlers import TimedRotatingFileHandler
import time


# Set default logging and debugging modes
def set_default_logging():
    """Sets logging to show only warnings and errors."""
    logging.getLogger().setLevel(logging.WARNING)


def enable_debug_logging():
    """Sets logging to show all levels, including info and debug."""
    logging.getLogger().setLevel(logging.DEBUG)


class FpdbLogFormatter(colorlog.ColoredFormatter):
    """Custom formatter for FPDB logs."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.var_color = "\033[36m"  # Cyan for variables
        self.reset_color = "\033[0m"

    def format(self, record):
        if hasattr(record, "msg"):
            record.msg = self._colorize_variables(record.msg)
        return super().format(record)

    def _colorize_variables(self, message):
        if not isinstance(message, str):
            return message
        pattern = r"'([^']*)'|\"([^\"]*)\""

        def repl(match):
            var = match.group(1) or match.group(2)
            return f"{self.var_color}'{var}'{self.reset_color}"

        return re.sub(pattern, repl, message)


class JsonFormatter(logging.Formatter):
    def format(self, record):
        record_dict = {
            "asctime": self.formatTime(record, self.datefmt),
            "name": record.name,
            "levelname": record.levelname,
            "module": record.module,
            "funcName": record.funcName,
            "message": record.getMessage(),
        }
        return json.dumps(record_dict)


class TimedSizedRotatingFileHandler(TimedRotatingFileHandler):
    """
    Handler for logging to a file, rotating the log file at certain timed
    intervals and when the log file reaches a certain size.

    This handler rotates the log file based on time and size, and names the
    rotated files including date and part number.
    """

    def __init__(
        self,
        filename,
        when="midnight",
        interval=1,
        backupCount=0,
        encoding=None,
        delay=False,
        utc=False,
        atTime=None,
        maxBytes=0,
    ):
        super().__init__(filename, when, interval, backupCount, encoding, delay, utc, atTime)
        self.maxBytes = maxBytes
        self.part = 1  # Initialize part number
        self.currentDate = time.strftime("%Y-%m-%d")

    def shouldRollover(self, record):
        """
        Determine if rollover should occur.

        Overridden to check both time-based and size-based rollover conditions.
        """
        t = int(time.time())
        if t >= self.rolloverAt:
            self.part = 1  # Reset part number when date changes
            self.currentDate = time.strftime("%Y-%m-%d")
            return True
        if self.maxBytes > 0:
            self.stream.seek(0, os.SEEK_END)
            if self.stream.tell() >= self.maxBytes:
                return True
        return False

    def doRollover(self):
        """
        Do a rollover, as described in __init__().
        """
        self.stream.close()
        currentTime = int(time.time())
        timeTuple = time.localtime(currentTime)
        dateStr = time.strftime("%d-%m-%Y", timeTuple)

        # Construct the rotated file name
        dfn = f"{self.baseFilename}-{dateStr}-part{self.part}.txt"

        # Increment part number for next rollover
        self.part += 1

        # Rotate the file
        if os.path.exists(dfn):
            os.remove(dfn)
        os.rename(self.baseFilename, dfn)

        # Remove old log files
        if self.backupCount > 0:
            for s in self.getFilesToDelete():
                os.remove(s)

        # Reopen the stream
        if not self.delay:
            self.stream = self._open()

        # Compute new rolloverAt
        newRolloverAt = self.computeRollover(currentTime)
        while newRolloverAt <= currentTime:
            newRolloverAt += self.interval
        self.rolloverAt = newRolloverAt

    def getFilesToDelete(self):
        """
        Determine the files to delete when rolling over.

        We need to override this method to match the file naming pattern.
        """
        dirName, baseName = os.path.split(self.baseFilename)
        fileNames = os.listdir(dirName)
        result = []
        for fileName in fileNames:
            if fileName.startswith(baseName) and fileName.endswith(".txt"):
                result.append(os.path.join(dirName, fileName))
        result.sort()
        if len(result) <= self.backupCount:
            return []
        else:
            return result[: len(result) - self.backupCount]


def setup_logging(log_dir=None, console_only=False):
    """Configure the logging system."""
    try:
        # Console handler setup remains unchanged
        log_colors = {"DEBUG": "green", "INFO": "blue", "WARNING": "yellow", "ERROR": "red"}
        log_format = (
            "%(log_color)s%(asctime)s [%(name)s:%(module)s:%(funcName)s] " "[%(levelname)s] %(message)s%(reset)s"
        )
        date_format = "%Y-%m-%d %H:%M:%S"
        formatter = colorlog.ColoredFormatter(fmt=log_format, datefmt=date_format, log_colors=log_colors)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(logging.DEBUG)

        # Configure root logger
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)  # Default to INFO level

        # Remove existing handlers to prevent duplicate logs
        logger.handlers = []
        logger.addHandler(console_handler)

        if not console_only:
            if log_dir is None:
                log_dir = os.path.join(os.path.expanduser("~"), "fpdb_logs")
            log_dir = os.path.normpath(log_dir)
            os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, "fpdb-log.txt")
            print(f"Attempting to write logs to: {log_file}")

            # Use the custom TimedSizedRotatingFileHandler
            maxBytes = 1024 * 1024  # 1 MB
            backupCount = 30  # Keep logs for 30 rollovers
            file_formatter = JsonFormatter(datefmt=date_format)
            file_handler = TimedSizedRotatingFileHandler(
                log_file,
                when="midnight",
                interval=1,
                backupCount=backupCount,
                encoding="utf-8",
                maxBytes=maxBytes,
            )
            file_handler.setFormatter(file_formatter)
            file_handler.setLevel(logging.DEBUG)

            logger.addHandler(file_handler)

            print("Logging initialized successfully.")
            print(f"Logs will be written to: {log_file}")

    except Exception as e:
        print(f"Error initializing logging: {e}")
        raise


# Update specific logger's level dynamically
def update_log_level(logger_name: str, level: int):
    """Updates the logging level for a specific logger."""
    logger = logging.getLogger(logger_name)
    logger.setLevel(level)


class FpdbLogger:
    """Custom logger for FPDB."""

    def __init__(self, name: str):
        self.logger = logging.getLogger(name)

    def debug(self, msg: str, *args, **kwargs):
        stacklevel = self._get_stacklevel()
        self.logger.debug(msg, *args, stacklevel=stacklevel, **kwargs)

    def info(self, msg: str, *args, **kwargs):
        stacklevel = self._get_stacklevel()
        self.logger.info(msg, *args, stacklevel=stacklevel, **kwargs)

    def warning(self, msg: str, *args, **kwargs):
        stacklevel = self._get_stacklevel()
        self.logger.warning(msg, *args, stacklevel=stacklevel, **kwargs)

    def error(self, msg: str, *args, **kwargs):
        stacklevel = self._get_stacklevel()
        self.logger.error(msg, *args, stacklevel=stacklevel, **kwargs)

    def setLevel(self, level):
        """Sets the logging level for this logger."""
        self.logger.setLevel(level)

    def getEffectiveLevel(self):
        """Gets the effective logging level for this logger."""
        return self.logger.getEffectiveLevel()

    def _get_stacklevel(self):
        # Calculate the stack level to pass to the underlying logger
        # to get accurate line numbers and function names in the logs
        frame = inspect.currentframe()
        stacklevel = 1
        while frame:
            co_name = frame.f_code.co_name
            if co_name in ("debug", "info", "warning", "error", "__init__", "_get_stacklevel"):
                frame = frame.f_back
                stacklevel += 1
            else:
                break
        return stacklevel


def get_logger(name: str) -> FpdbLogger:
    """Returns a configured FPDB logger."""
    return FpdbLogger(name)


# Initialize logging configuration on module load
# setup_logging()
