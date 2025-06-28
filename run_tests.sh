#!/bin/bash
# Script to run tests locally

echo "Running fpdb-3 tests..."

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "uv is not installed. Installing..."
    pip install uv
fi

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    uv venv
fi

# Install test dependencies
echo "Installing test dependencies..."
uv pip install -e .[test]

# Run linting
echo "Running ruff linting..."
uv run ruff check .

# Create necessary directories
echo "Creating necessary directories..."
mkdir -p ~/.fpdb
if [ -f "HUD_config.xml" ]; then
    cp HUD_config.xml ~/.fpdb/
fi

# Run tests
echo "Running tests..."
uv run pytest -v --tb=short test/

# Run tests with coverage if requested
if [ "$1" == "--coverage" ]; then
    echo "Running tests with coverage..."
    uv run pytest --cov=. --cov-report=html --cov-report=term test/
    echo "Coverage report generated in htmlcov/"
fi

echo "Tests completed!"