import os
import re
import logging
import colorlog
import inspect


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


def setup_logging():
    """Configure the logging system."""
    log_colors = {"DEBUG": "green", "INFO": "blue", "WARNING": "yellow", "ERROR": "red"}
    log_format = "%(log_color)s%(asctime)s [%(name)s:%(module)s:%(funcName)s] [%(levelname)s] %(message)s%(reset)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    formatter = FpdbLogFormatter(fmt=log_format, datefmt=date_format, log_colors=log_colors)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.DEBUG)

    # Root logger
    logger = logging.getLogger()
    logger.setLevel(logging.WARNING)  # Set default level to WARNING
    logger.addHandler(console_handler)
    logger.propagate = True

    # File handler
    log_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "fpdb-log.txt")

    file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
    file_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt=date_format)
    file_handler.setFormatter(file_formatter)
    file_handler.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)


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
setup_logging()
