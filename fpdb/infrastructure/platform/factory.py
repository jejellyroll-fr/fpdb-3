"""Factory for creating platform-specific table detectors

Auto-detects the current platform and creates the appropriate detector.
"""

from __future__ import annotations

import logging
import sys

from .protocol import Platform, TableDetector

logger = logging.getLogger(__name__)


class TableDetectorFactory:
    """Factory for creating platform-specific table detectors

    Example:
        >>> detector = TableDetectorFactory.create()
        >>> tables = detector.find_tables("PokerStars")
    """

    @staticmethod
    def detect_platform() -> Platform:
        """Detect the current operating system platform

        Returns:
            Platform enum value for current OS
        """
        platform_str = sys.platform.lower()

        if platform_str.startswith("linux"):
            return Platform.LINUX
        elif platform_str.startswith("win"):
            return Platform.WINDOWS
        elif platform_str.startswith("darwin"):
            return Platform.MACOS
        else:
            logger.warning(f"Unknown platform: {platform_str}")
            return Platform.UNKNOWN

    @staticmethod
    def create(platform: Platform | None = None) -> TableDetector:
        """Create a table detector for the specified platform

        Args:
            platform: Platform to create detector for (auto-detected if None)

        Returns:
            Platform-specific TableDetector implementation

        Raises:
            NotImplementedError: If platform is not supported
            ImportError: If platform-specific dependencies are not installed
        """
        if platform is None:
            platform = TableDetectorFactory.detect_platform()

        logger.info(f"Creating table detector for platform: {platform}")

        if platform == Platform.LINUX:
            from .linux import LinuxTableDetector

            return LinuxTableDetector()

        elif platform == Platform.WINDOWS:
            from .windows import WindowsTableDetector

            return WindowsTableDetector()

        elif platform == Platform.MACOS:
            from .macos import MacOSTableDetector

            return MacOSTableDetector()

        else:
            raise NotImplementedError(f"Platform not supported: {platform}")

    @staticmethod
    def is_platform_supported(platform: Platform) -> bool:
        """Check if a platform is supported

        Args:
            platform: Platform to check

        Returns:
            True if platform has an implementation
        """
        return platform in (Platform.LINUX, Platform.WINDOWS, Platform.MACOS)


# Singleton instance
_detector_instance: TableDetector | None = None


def get_table_detector(force_reload: bool = False) -> TableDetector:
    """Get the global table detector instance

    This function returns a singleton instance of the platform-specific
    table detector. The detector is created on first call and reused.

    Args:
        force_reload: If True, create a new instance even if one exists

    Returns:
        Platform-specific TableDetector

    Example:
        >>> detector = get_table_detector()
        >>> tables = detector.find_tables("PokerStars")
    """
    global _detector_instance

    if _detector_instance is None or force_reload:
        _detector_instance = TableDetectorFactory.create()
        logger.info(f"Initialized table detector for {_detector_instance.platform}")

    return _detector_instance


def reset_detector() -> None:
    """Reset the global detector instance (for testing)"""
    global _detector_instance
    _detector_instance = None
