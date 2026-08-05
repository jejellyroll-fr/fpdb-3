#!/usr/bin/env python3
"""Tests for the GuiBulkImport headless CLI entry point — GitHub issue #106.

The CLI (`GuiBulkImport.py -x -C <config> -c <site> -f <file>`) is the entry
point the TestHandsPlayers (THP) regression workflow depends on. These tests
cover its argument contract; the import engine itself is exercised elsewhere.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fpdb_3_legacy import GuiBulkImport


def test_no_xtables_prints_help_and_returns_0(capsys) -> None:
    """Without -x there is no GUI to launch standalone: print help, exit 0."""
    rc = GuiBulkImport.main([])
    assert rc == 0
    assert "bulk" in capsys.readouterr().out.lower()


def test_xtables_without_file_returns_2() -> None:
    """-x requires -f; a missing file argument is a usage error."""
    assert GuiBulkImport.main(["-x"]) == 2


def test_xtables_nonexistent_file_returns_2() -> None:
    """A path that does not exist is a usage error, not a crash."""
    assert GuiBulkImport.main(["-x", "-f", "/no/such/hand/history.txt"]) == 2


def test_unknown_flag_is_rejected() -> None:
    """argparse rejects an unknown flag with SystemExit (THP flags are known)."""
    with pytest.raises(SystemExit):
        GuiBulkImport.main(["--definitely-not-a-flag"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
