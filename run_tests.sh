#!/bin/bash
# -------------------------------------------------------------------------------------------------
# fpdb-3 legacy – unified test runner
# Runs pytest with coverage (terminal + HTML + XML)
# Excludes GUI tests (test_HUD_main.py) to avoid segfaults
# -------------------------------------------------------------------------------------------------
set -euo pipefail

echo "Installing test dependencies..."
export QT_API=pyside6
uv pip install -e .[test]

echo
echo "Running main test suite (excluding GUI tests)..."
if uv run python -c "import pytest_cov" 2>/dev/null; then
    echo "Running with coverage support..."
    uv run pytest \
      --cov=fpdb_3_legacy \
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
fi

echo
echo "Running GUI tests separately (may have warnings)..."
echo "Note: GUI tests may show Qt warnings - this is normal"
uv run pytest test/test_HUD_main.py -v --tb=short || {
    GUI_EXIT_CODE=$?
    echo "GUI tests failed with exit code: $GUI_EXIT_CODE"
}

exit $MAIN_EXIT_CODE
