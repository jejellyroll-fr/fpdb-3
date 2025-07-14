#!/bin/bash
# -------------------------------------------------------------------------------------------------
# fpdb-3 – unified test runner
# Runs Ruff linting + pytest with coverage (terminal + HTML + XML)
# -------------------------------------------------------------------------------------------------
set -euo pipefail

#echo "Running Ruff linting..."
#uv run ruff check . --fix --unsafe-fixes

echo
echo "Running pytest with coverage..."
uv run pytest -v \
  --cov=. \
  --cov-config=.coveragerc \
  --cov-report=term-missing \
  --cov-report=html \
  --cov-report=xml

echo
echo "✅ Tests finished."
echo "📊 Coverage: see summary above."
echo "🖥️  Detailed HTML report: htmlcov/index.html"
