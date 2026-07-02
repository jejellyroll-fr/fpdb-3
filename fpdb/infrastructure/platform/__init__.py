"""Platform abstraction layer for table detection

This module provides a unified interface for table window detection
across different operating systems (Linux, Windows, macOS).
"""

from .factory import TableDetectorFactory, get_table_detector, reset_detector
from .protocol import TableDetector, TableGeometry, TableInfo

__all__ = [
    "TableDetector",
    "TableGeometry",
    "TableInfo",
    "TableDetectorFactory",
    "get_table_detector",
    "reset_detector",
]
