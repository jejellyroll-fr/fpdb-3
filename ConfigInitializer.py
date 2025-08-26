"""Enhanced configuration initialization module for fpdb.

This module solves the issue #22 problem by providing robust
and centralized configuration initialization.
"""

import logging
import sys
from pathlib import Path
from typing import Any

# Configuration  logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("config_initializer")


class ConfigInitializer:
    """fpdb configuration initialization manager."""

    _initialized = False
    _config = None
    _config_file = None

    @classmethod
    def _find_config_path(cls, config_file: str) -> str:
        """Find the full path to the configuration file, creating it if necessary.

        Searches for the configuration file in several standard locations and
        creates it in the user's home directory if not found.

        Args:
            config_file: The name of the configuration file to locate.

        Returns:
            The full path to the configuration file.
        """
        if Path(config_file).is_absolute():
            return config_file

        # Search in order: current directory, home, fpdb
        fpdb_dir = Path(__file__).parent
        search_paths = [
            Path.cwd() / config_file,
            Path.home() / ".fpdb" / config_file,
            fpdb_dir / config_file,
        ]

        for path in search_paths:
            if path.exists():
                return str(path)

        # If not found, create in ~/.fpdb/
        fpdb_config_dir = Path.home() / ".fpdb"
        fpdb_config_dir.mkdir(exist_ok=True)
        config_path = str(fpdb_config_dir / config_file)
        log.info("Creating new configuration in: %s", config_path)
        return config_path

    @classmethod
    def initialize(cls, config_file: str = "HUD_config.xml", *, fallback_to_default: bool = True) -> Any:
        """Initialize fpdb configuration robustly.

        Args:
            config_file: Configuration file name
            fallback_to_default: If True, creates a default config if necessary

        Returns:
            The initialized Configuration object

        """
        if cls._initialized and cls._config:
            return cls._config

        try:
            # Add fpdb directory to path if necessary
            fpdb_dir = Path(__file__).parent
            if str(fpdb_dir) not in sys.path:
                sys.path.insert(0, str(fpdb_dir))

            # Deferred import to avoid circular dependencies
            import Configuration

            # Find configuration file
            config_path = cls._find_config_path(config_file)

            # Initialize configuration
            config_path_result = Configuration.get_config(config_path, fallback_to_default)
            if isinstance(config_path_result, tuple):
                # get_config returns (config_path, example_copy, example_path)
                actual_config_path = config_path_result[0]
            else:
                actual_config_path = config_path_result
                
            # Create the actual Configuration object
            cls._config = Configuration.Config(file=actual_config_path)
            cls._config_file = actual_config_path
            cls._initialized = True

        except Exception:
            log.exception("Error during configuration initialization")
            if not fallback_to_default:
                raise
            try:
                # Try to create a minimal configuration
                import Configuration

                cls._config = Configuration.Config()
                cls._initialized = True
                log.warning("Minimal configuration created following error")
            except (ImportError, AttributeError):
                log.exception("Unable to create minimal configuration")
                raise
        else:
            log.info("Configuration initialized from: %s", config_path)

        return cls._config

    @classmethod
    def get_config(cls) -> Any:
        """Return the current configuration object, initializing if necessary.

        Retrieves the configuration if it is already initialized, or initializes it if not.

        Returns:
            The initialized Configuration object.
        """
        return cls._config if cls._initialized and cls._config else cls.initialize()


    @classmethod
    def reload_config(cls) -> Any:
        """Reload the configuration from the current configuration file.

        Resets the initialization state and reloads the configuration if a config file is set.
        Raises an error if no config file is available.

        Returns:
            The reloaded Configuration object.

        Raises:
            RuntimeError: If no configuration file is available to reload.
        """
        if cls._config_file:
            cls._initialized = False
            cls._config = None
            return cls.initialize(cls._config_file)
        msg = "No configuration file to reload"
        raise RuntimeError(msg)

    @classmethod
    def is_initialized(cls) -> bool:
        """Check if the configuration has been initialized.

        Returns True if the configuration is initialized and available, otherwise False.

        Returns:
            True if configuration is initialized, False otherwise.
        """
        return cls._initialized and cls._config is not None

    @classmethod
    def get_config_path(cls) -> str | None:
        """Return the path to the current configuration file.

        Provides the file path of the configuration file if it has been set, otherwise returns None.

        Returns:
            The path to the configuration file, or None if not set.
        """
        return cls._config_file


# Convenience function for quick initialization
def ensure_config_initialized(config_file: str = "HUD_config.xml") -> Any:
    """Ensure the fpdb configuration is initialized and return it.

    Initializes the configuration using the specified file if it is not already initialized.

    Args:
        config_file: The name of the configuration file to use.

    Returns:
        The initialized Configuration object.
    """
    return ConfigInitializer.initialize(config_file)

