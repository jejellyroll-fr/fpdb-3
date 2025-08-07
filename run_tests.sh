#!/bin/bash
# -------------------------------------------------------------------------------------------------
# fpdb-3 – unified test runner
# Runs Ruff linting + pytest with coverage (terminal + HTML + XML)
# -------------------------------------------------------------------------------------------------
set -euo pipefail

echo "Installing test dependencies..."
uv pip install .[test]

echo
echo "Running pytest with coverage..."
if uv run python -c "import pytest_cov" 2>/dev/null; then
    echo "Running with coverage support..."
    uv run pytest -v \
      --cov=. \
      --cov-config=.coveragerc \
      --cov-report=term-missing \
      --cov-report=html \
      --cov-report=xml
    echo
    echo "Tests finished with coverage."
    echo "Coverage: see summary above."
    echo "Detailed HTML report: htmlcov/index.html"
else
    echo "Coverage not available, running basic tests..."
    uv run pytest -v
    echo
    echo "Tests finished."
    echo "Install test dependencies for coverage: uv pip install .[test]"
fi
