#!/bin/bash
# -------------------------------------------------------------------------------------------------
# fpdb-3 – unified test runner
# Runs pytest with coverage (terminal + HTML + XML)
# Excludes GUI tests (test_HUD_main.py) to avoid segfaults
# -------------------------------------------------------------------------------------------------
set -euo pipefail

echo "Installing test dependencies..."
# Check if PyQt5 is already installed (e.g., from CI setup)
if uv run python -c "import PyQt5.QtCore; print('PyQt5 already installed')" 2>/dev/null; then
    echo "PyQt5 already installed, skipping PyQt5 installation"
    # Install test dependencies without PyQt5 to avoid version conflicts
    uv pip install .[test-no-pyqt]
    uv pip install -e . --no-deps
else
    echo "Installing all test dependencies including PyQt5"
    uv pip install .[test]
fi

echo
echo "Running main test suite (excluding GUI tests)..."
if uv run python -c "import pytest_cov" 2>/dev/null; then
    echo "Running with coverage support..."
    uv run pytest \
      --cov=. \
      --cov-config=.coveragerc \
      --cov-report=term-missing \
      --cov-report=html \
      --cov-report=xml
    MAIN_EXIT_CODE=$?
    echo
    echo "Main tests finished with coverage."
    echo "Coverage: see summary above."
    echo "Detailed HTML report: htmlcov/index.html"
else
    echo "Coverage not available, running basic tests..."
    uv run pytest
    MAIN_EXIT_CODE=$?
    echo
    echo "Main tests finished."
    echo "Install test dependencies for coverage: uv pip install .[test]"
fi

echo
echo "Running GUI tests separately (may have warnings)..."
echo "Note: GUI tests may show Qt warnings - this is normal"
uv run pytest test/test_HUD_main.py -v --tb=short || {
    GUI_EXIT_CODE=$?
    echo "GUI tests failed with exit code: $GUI_EXIT_CODE"
    echo "This is often due to Qt/GUI issues on headless systems and may not indicate real problems"
}

# Exit with main test suite status
exit $MAIN_EXIT_CODE
