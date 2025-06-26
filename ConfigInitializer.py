#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Enhanced configuration initialization module for fpdb.

This module solves the issue #22 problem by providing robust
and centralized configuration initialization.
"""

import logging
import os
import sys
from pathlib import Path

# Configuration  logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("ConfigInitializer")


class ConfigInitializer:
    """fpdb configuration initialization manager."""

    _initialized = False
    _config = None
    _config_file = None

    @classmethod
    def initialize(cls, config_file="HUD_config.xml", fallback_to_default=True):
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

            # Determine the full path of the configuration file
            if os.path.isabs(config_file):
                config_path = config_file
            else:
                # Search in order: current directory, home, fpdb
                search_paths = [
                    Path.cwd() / config_file,
                    Path.home() / ".fpdb" / config_file,
                    fpdb_dir / config_file,
                ]

                config_path = None
                for path in search_paths:
                    if path.exists():
                        config_path = str(path)
                        break

                if not config_path and fallback_to_default:
                    # Create .fpdb directory if necessary
                    fpdb_config_dir = Path.home() / ".fpdb"
                    fpdb_config_dir.mkdir(exist_ok=True)
                    config_path = str(fpdb_config_dir / config_file)
                    log.info(f"Creating new configuration in: {config_path}")

            # Initialize configuration
            cls._config = Configuration.get_config(config_path, fallback_to_default)
            cls._config_file = config_path
            cls._initialized = True

            log.info(f"Configuration initialized from: {config_path}")
            return cls._config

        except Exception as e:
            log.error(f"Error during configuration initialization: {e}")
            if fallback_to_default:
                try:
                    # Try to create a minimal configuration
                    import Configuration

                    cls._config = Configuration.Config()
                    cls._initialized = True
                    log.warning("Minimal configuration created following error")
                    return cls._config
                except Exception:
                    pass
            raise

    @classmethod
    def get_config(cls):
        """Returns the configuration, initializes it if necessary."""
        if not cls._initialized or not cls._config:
            return cls.initialize()
        return cls._config

    @classmethod
    def reload_config(cls):
        """Reloads the configuration from file."""
        if cls._config_file:
            cls._initialized = False
            cls._config = None
            return cls.initialize(cls._config_file)
        else:
            raise RuntimeError("No configuration file to reload")

    @classmethod
    def is_initialized(cls):
        """Checks if the configuration is initialized."""
        return cls._initialized and cls._config is not None

    @classmethod
    def get_config_path(cls):
        """Returns the current configuration file path."""
        return cls._config_file


# Convenience function for quick initialization
def ensure_config_initialized(config_file="HUD_config.xml"):
    """Ensures that the configuration is initialized.

    This function can be safely called from any module.
    """
    return ConfigInitializer.initialize(config_file)


# Auto-initialization when importing the module
if __name__ != "__main__":
    # If this module is imported (not executed directly),
    # we can optionally initialize the config
    # This is disabled by default to avoid side effects
    pass
