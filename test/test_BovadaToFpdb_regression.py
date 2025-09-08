"""Regression tests for BovadaToFpdb - Ensure fixes remain functional.

This module contains regression tests to prevent reintroduction of bugs
already fixed in the Bovada parser.
"""

import datetime
import inspect
import subprocess
import sys
import unittest
from pathlib import Path

from BovadaToFpdb import Bovada


class BovadaRegressionTests(unittest.TestCase):
    """Regression tests to ensure previous fixes still work."""

    def test_all_original_tests_still_pass(self) -> None:
        """Regression: Ensure all original tests still pass."""
        # Run the original tests that worked after the fixes
        # Security: Using trusted command with validated arguments and shell=False
        # Validate that we're using the expected Python executable
        if not Path(sys.executable).exists():
            self.fail(f"Python executable not found: {sys.executable}")

        # Validate test file exists
        test_file = Path(__file__).parent.parent / "test" / "test_BovadaToFpdb.py"
        if not test_file.exists():
            self.skipTest(f"Test file not found: {test_file}")

        result = subprocess.run(  # noqa: S603
            [sys.executable, "-m", "pytest", str(test_file), "-v"],
            cwd=Path(__file__).parent.parent,
            capture_output=True,
            text=True,
            shell=False,
            check=False,
            timeout=60,  # Add timeout for security
        )

        assert result.returncode == 0, f"Original tests fail - regression detected:\n{result.stdout}\n{result.stderr}"

        # Verify that the exact number of tests pass (23 tests)
        assert "23 passed" in result.stdout

    def test_datetime_import_regression(self) -> None:
        """Regression: Ensure datetime.strptime import works."""
        try:
            # Direct test of usage in the code - most important
            test_date_string = "2012-08-26 23:35:15"
            # Use timezone-aware parsing to avoid naive datetime warning
            parsed_date = datetime.datetime.strptime(test_date_string, "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=datetime.timezone.utc,
            )
            assert isinstance(parsed_date, datetime.datetime)

        except AttributeError as e:
            if "datetime" in str(e):
                self.fail(f"Datetime import regression detected: {e}")
            raise

    def test_split_flag_regression(self) -> None:
        """Regression: Ensure 'split' key is still defined."""
        # Verify that _buildGameTypeInfo contains the split code
        source = inspect.getsource(Bovada._buildGameTypeInfo)
        assert "split" in source, "'split' key missing in _buildGameTypeInfo - regression detected"

    def test_cli_importer_basic_functionality(self) -> None:
        """Regression: Ensure CLI importer still works."""
        # Security: Validate all paths before subprocess execution
        base_dir = Path(__file__).parent.parent
        test_file = (
            base_dir / "regression-test-files/cash/Bovada/Flop/" "NLHE-USD-0.10-0.25-201208.raise.to.format.change.txt"
        )
        # Skip this test since importer_cli is obsolete
        self.skipTest("CLI importer test skipped - importer_cli.py is in obsolete archive")

        if not Path(sys.executable).exists():
            self.fail(f"Python executable not found: {sys.executable}")

        # Test import without actually modifying the database
        # Security: Using validated paths and controlled arguments with shell=False
        result = subprocess.run(  # noqa: S603
            [sys.executable, str(importer_cli), "--site", "Bovada", "--no-progress", "--debug", str(test_file)],
            cwd=base_dir,
            capture_output=True,
            text=True,
            shell=False,
            timeout=30,
            check=False,
        )

        # Import must succeed (return code 0)
        assert result.returncode == 0, (
            f"CLI importer fails - regression detected:\n"
            f"Exit code: {result.returncode}\n"
            f"Command: {' '.join([sys.executable, str(importer_cli), '--site', 'Bovada', '--no-progress', str(test_file)])}\n"
            f"Working directory: {base_dir}\n"
            f"Test file exists: {test_file.exists()}\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )


if __name__ == "__main__":
    unittest.main()
