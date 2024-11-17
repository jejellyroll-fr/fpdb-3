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
    """Formateur personnalisé pour les logs FPDB"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.var_color = "\033[36m"  # Cyan pour les variables
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
    """Configure le système de logging"""
    log_colors = {"DEBUG": "green", "INFO": "blue", "WARNING": "yellow", "ERROR": "red"}
    log_format = "%(log_color)s%(asctime)s [%(name)s:%(module)s:%(funcName)s] [%(levelname)s] %(message)s%(reset)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    formatter = FpdbLogFormatter(fmt=log_format, datefmt=date_format, log_colors=log_colors)

    # Handler console
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.DEBUG)

    # Logger racine
    logger = logging.getLogger()
    logger.setLevel(logging.WARNING)  # Set default level to WARNING
    logger.addHandler(console_handler)

    # Handler fichier
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
    """Met à jour le niveau de logging pour un logger spécifique"""
    logger = logging.getLogger(logger_name)
    logger.setLevel(level)


class FpdbLogger:
    """Logger personnalisé pour FPDB"""

    def __init__(self, name: str):
        self.logger = logging.getLogger(name)

    def debug(self, msg: str):
        stacklevel = self._get_stacklevel()
        self.logger.debug(msg, stacklevel=stacklevel)

    def info(self, msg: str):
        stacklevel = self._get_stacklevel()
        self.logger.info(msg, stacklevel=stacklevel)

    def warning(self, msg: str):
        stacklevel = self._get_stacklevel()
        self.logger.warning(msg, stacklevel=stacklevel)

    def error(self, msg: str):
        stacklevel = self._get_stacklevel()
        self.logger.error(msg, stacklevel=stacklevel)

    def _get_stacklevel(self):
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
    """Retourne un logger FPDB configuré"""
    return FpdbLogger(name)


# Initialize logging configuration on module load
setup_logging()
