"""Tests for performance optimizations when creating tabs in FPDB."""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import fpdb_3_legacy.Configuration as Configuration
from fpdb_3_legacy.Filters import Filters


def test_mplconfigdir_configured() -> None:
    """Verify MPLCONFIGDIR is set to a user-writable path under CONFIG_PATH."""
    assert "MPLCONFIGDIR" in os.environ
    assert os.environ["MPLCONFIGDIR"].startswith(Configuration.CONFIG_PATH)


def test_filters_uses_isolated_cursor(qapp: MagicMock) -> None:
    """Verify Filters creates a dedicated cursor to avoid lock contention on db.cursor."""
    _ = qapp
    mock_connection = MagicMock()
    mock_dedicated_cursor = MagicMock()
    mock_connection.cursor.return_value = mock_dedicated_cursor

    mock_db = MagicMock()
    mock_db.connection = mock_connection
    mock_db.cursor = MagicMock()
    mock_db.config.get_supported_sites.return_value = []
    mock_db.config.get_general_params.return_value = {}

    filters = Filters(mock_db)

    # Dedicated cursor should be used instead of sharing mock_db.cursor
    assert filters.db_cursor == mock_dedicated_cursor
    assert filters.db_cursor != mock_db.cursor
