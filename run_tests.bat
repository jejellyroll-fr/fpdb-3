@echo off
REM Script to run tests locally on Windows

echo Running fpdb-3 tests...

REM Check if uv is installed
where uv >nul 2>nul
if %errorlevel% neq 0 (
    echo uv is not installed. Installing...
    pip install uv
)

REM Create virtual environment if it doesn't exist
if not exist ".venv" (
    echo Creating virtual environment...
    uv venv
)

REM Install test dependencies
echo Installing test dependencies...
uv pip install -e .[test]

REM Run linting
echo Running ruff linting...
uv run ruff check .

REM Create necessary directories
echo Creating necessary directories...
if not exist "%APPDATA%\fpdb" mkdir "%APPDATA%\fpdb"
if exist "HUD_config.xml" copy "HUD_config.xml" "%APPDATA%\fpdb\"

REM Run tests
echo Running tests...
uv run pytest -v --tb=short --ignore=test/test_HUD_main.py test\ test_*.py

REM Run tests with coverage if requested
if "%1"=="--coverage" (
    echo Running tests with coverage...
    uv run pytest --cov=. --cov-report=html --cov-report=term --ignore=test/test_HUD_main.py test\ test_*.py
    echo Coverage report generated in htmlcov\
)

echo Tests completed!