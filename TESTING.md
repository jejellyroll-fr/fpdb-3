# Testing Guide for fpdb-3

This document explains how to run tests in the fpdb-3 project, including the new regression testing system and snapshot-based validation.

## Quick Start

```bash
# Run main test suite (recommended)
make test

# Or directly with pytest
uv run pytest

# Run all tests including GUI tests
make test-all
# Or
./run_tests.sh

# Run new regression & snapshot tests
pytest regression-tests/
```

## Test Structure

### Legacy Test Suite

- **947 main tests** - All tests except GUI tests
- **35 GUI tests** - `test_HUD_main.py` (run separately due to Qt/GUI issues)
- **Test categories**: Unit tests, integration tests, performance tests

### New Regression Testing System

- **regression-tests/test_thp_param.py** - Modernized regression tests (replaces TestHandsPlayers.py)
- **regression-tests/test_snapshots.py** - Snapshot-based testing with syrupy
- **regression-tests/test_invariants.py** - Poker rules validation
- **regression-tests/test_hypothesis_properties.py** - Property-based testing with Hypothesis

## Available Commands

### Installation Options

```bash
# Install test dependencies only (without PyQt5 - useful in CI)
uv pip install .[test-no-pyqt]

# Install all test dependencies (including PyQt5)
uv pip install .[test]
```

### Make Commands

```bash
make test              # Main test suite (excludes GUI)
make test-all          # All tests including GUI
make test-gui          # Only GUI tests
make test-main         # Main tests with coverage report
make test-stats        # Only stats-related tests
make quick-test        # Fast tests without coverage
make debug-test        # Verbose output for debugging
```

### Direct pytest Commands

```bash
uv run pytest                              # Main tests (default config)
uv run pytest test/test_HUD_main.py       # GUI tests only
uv run pytest -k "stats"                  # Tests matching "stats"
uv run pytest test/test_specific_file.py  # Specific test file
uv run pytest --cov=. --cov-report=html   # With coverage report
```

## 🏗️ CI/CD Integration

### GitHub Actions

The project uses unified test scripts for consistent behavior across platforms:

- **Linux/macOS**: Uses `run_tests.sh`
- **Windows**: Uses `run_tests.ps1`
- **Configuration**: `pytest.ini` with GUI tests excluded by default

### Test Matrix

- **OS**: Ubuntu, Windows, macOS
- **Python**: 3.10, 3.11
- **Coverage**: Generated on Ubuntu 3.11

## 🎯 Test Configuration

### pytest.ini

```ini
[pytest]
addopts = 
    -v
    --tb=short
    --strict-markers
    --disable-warnings
    --ignore=test/test_HUD_main.py  # GUI tests excluded
```

### Why GUI Tests are Separate

GUI tests (`test_HUD_main.py`) can cause segfaults in headless environments due to:

- Qt/PyQt5 issues on headless systems
- Display server problems
- Memory management with GUI components

**Solution**: Run GUI tests separately with error tolerance.

## Troubleshooting

### Common Issues

1. **Mock pollution between tests**  **FIXED**
   - Problem: `sys.modules` mocks affecting other tests
   - Solution: Isolated mocks using `setUpClass`/`tearDownClass`

2. **PyQt5 installation issues**  **FIXED**
   - Problem: Version conflicts between CI and local installations
   - Solution: Smart detection in scripts + `test-no-pyqt` option
   - CI installs PyQt5 first, then scripts use `test-no-pyqt` to avoid conflicts

3. **GUI tests failing**
   - Expected on headless systems
   - Run with: `make test-gui` or `uv run pytest test/test_HUD_main.py`

4. **Performance test failures**
   - Adjust thresholds in `test_popup_performance.py` if needed
   - Current threshold: 50x linear scaling

### Test Isolation

Tests are properly isolated using:

- Class-level mock setup/teardown
- Module-level import isolation
- Proper cleanup of Qt objects

## Coverage Reports

Coverage reports are generated in multiple formats:

- **Terminal**: Summary during test run
- **HTML**: `htmlcov/index.html`
- **XML**: For CI integration

```bash
# Generate coverage report
make test-main

# View HTML report
open htmlcov/index.html
```

## Debugging Tests

```bash
# Verbose output with full tracebacks
make debug-test

# Run specific failing test
uv run pytest test/specific_test.py::TestClass::test_method -v -s

# Debug with pdb
uv run pytest test/failing_test.py --pdb
```

## Test Status

Current test suite status:

- ✅ 947/947 main tests passing
- ⚠️ GUI tests run separately (may show Qt warnings - normal)
- ✅ Mock isolation issues resolved
- ✅ CI/CD integration working
- ✅ Coverage reporting enabled

## Development Workflow

1. **Before making changes**:

   ```bash
   make test  # Ensure tests pass
   ```

2. **After making changes**:

   ```bash
   make test           # Run tests
   make lint           # Check code style
   make format-check   # Check formatting
   ```

3. **Before committing**:

   ```bash
   make ci-test  # Run full CI-style test suite
   ```

## Adding New Tests

- Place tests in `test/` directory
- Follow naming convention: `test_*.py`
- Use proper test isolation (see existing examples)
- For GUI tests, consider if they belong in `test_HUD_main.py` or should be separate

## Regression Testing System

FPDB uses a modern pytest-based regression testing system:

### 🔄 Evolution Status

**Current Version: v1.0** - Foundation established, ready for refactoring iterations

- **serialize_hand_for_snapshot.py**: Base serialization system implemented
- **test_snapshots.py**: First iteration snapshot testing with syrupy  
- **test_thp_param.py**: Migration from legacy system, performance optimizations needed
- **test_invariants.py**: Basic invariants implemented, more game-specific rules needed
- **OSXTables.py**: AppKit import issues fixed for macOS compatibility

**Expected Evolution**: The regression system is designed for iterative improvement. Scripts contain evolution notes and are structured for easy refactoring as requirements evolve.

#### Regression Tests (test_thp_param.py)

```bash
# Run all regression tests
uv run pytest regression-tests/test_thp_param.py -v

# Run tests for specific site
uv run pytest regression-tests/test_thp_param.py -k "PokerStars"

# Run tests for specific file type
uv run pytest regression-tests/test_thp_param.py -k "Flop"

# Show detailed output
uv run pytest regression-tests/test_thp_param.py -v -s
```

#### Snapshot Tests (test_snapshots.py)

```bash
# Run snapshot tests
uv run pytest regression-tests/test_snapshots.py

# Update snapshots after code changes
uv run pytest regression-tests/test_snapshots.py --snapshot-update

# Review snapshot differences
uv run pytest regression-tests/test_snapshots.py --snapshot-details
```

#### Invariant Tests (test_invariants.py)

```bash
# Run invariant tests
uv run pytest regression-tests/test_invariants.py

# Run specific invariant
uv run pytest regression-tests/test_invariants.py -k "money_conservation"

# Test invariants on specific files
uv run pytest regression-tests/test_invariants.py -k "Stars"
```

#### Property-Based Tests (test_hypothesis_properties.py)

```bash
# Run property tests (slower)
uv run pytest regression-tests/test_hypothesis_properties.py

# Run with more examples for deeper testing
uv run pytest regression-tests/test_hypothesis_properties.py --hypothesis-max-examples=100
```

### CLI Support for Bulk Import and Testing

GuiBulkImport.py now supports CLI mode for automated testing and scripting:

```bash
# CLI syntax
uv run python GuiBulkImport.py [options]

# Options
-C, --config FILE    Configuration file (default: HUD_config.xml)
-c, --converter SITE Site converter to use (default: auto)
-f, --file PATH      Hand history file or directory to import
-q, --quiet          Reduce output verbosity

# Examples
uv run python GuiBulkImport.py -f regression-test-files/cash/Stars/Flop/sample.txt -c PokerStars
uv run python GuiBulkImport.py -f /path/to/hands/ -c auto -q
uv run python GuiBulkImport.py -C HUD_config.test.xml -f hand.txt
```

**CLI Usage in Testing:**

- **TestHandsPlayers legacy compatibility**: The legacy script now works correctly with CLI support
- **Programmatic import**: CLI can be called from Python code for automated testing
- **Batch processing**: Import multiple files or directories from command line
- **CI/CD integration**: Enables automated import testing in continuous integration

```bash
# Legacy TestHandsPlayers script (restored functionality)
uv run python regression-tests/TestHandsPlayers_legacy.py PokerStars -f sample_hand.txt
```

### Modern System Benefits

The pytest-based system provides:

| Feature | Benefit |
|---------|---------|
| **Parameterized testing** | Faster execution, better error reporting |
| **JSON snapshots** | Stable, version-independent, human-readable |
| **Invariant testing** | Automated poker rule validation |
| **Property-based testing** | Comprehensive edge case testing with Hypothesis |
| **Integration with CI/CD** | Seamless pytest integration |
| **CLI support** | Command-line bulk import for automation and testing |

## Dependencies for New Tests

Install additional testing dependencies:

```bash
# Core testing (already included)
pip install pytest

# Snapshot testing
pip install syrupy

# Property-based testing  
pip install hypothesis

# Install all at once
pip install pytest syrupy hypothesis
```

## Adding New Hand Histories for Testing

1. **Place file** in appropriate `regression-test-files/` directory:

   ```bash
   cp new_hand.txt regression-test-files/cash/Stars/Flop/
   ```

2. **Generate snapshots**:

   ```bash
   uv run pytest regression-tests/test_snapshots.py --snapshot-update -k "new_hand"
   ```

3. **Run regression test**:

   ```bash
   uv run pytest regression-tests/test_thp_param.py -k "new_hand"
   ```

4. **Validate invariants**:

   ```bash
   uv run pytest regression-tests/test_invariants.py -k "new_hand"
   ```

### Using Snapshot Generation Tool

For easier snapshot generation, use the provided tool:

```bash
# Generate snapshot for specific file
uv run python tools/make_snapshot.py regression-test-files/cash/Stars/Flop/new_hand.txt --verbose

# Generate snapshots for multiple files
uv run python tools/make_snapshot.py regression-test-files/cash/Stars/Flop/*.txt
```

## Directory Structure Summary

```
fpdb-3/
├── test/                           # Unit tests
│   └── test_*.py                   # Unit/integration tests
├── regression-tests/               # Regression testing system
│   ├── test_thp_param.py          # Regression tests (replaces TestHandsPlayers.py)
│   ├── test_snapshots.py          # Snapshot testing with syrupy
│   ├── test_invariants.py         # Poker rules validation
│   ├── test_hypothesis_properties.py # Property-based testing
│   └── TestHandsPlayers_legacy.py # Legacy script (archived, not recommended)
├── regression-test-files/          # Hand history files for testing
│   ├── cash/                       # Cash game hands
│   ├── tour/                       # Tournament hands
│   └── summaries/                  # Summary files
├── tools/
│   └── make_snapshot.py           # Tool for generating snapshots
└── serialize_hand_for_snapshot.py # Hand serialization module
```

**Modern System Features:**

- **Pytest-based**: Fast, parameterized tests with excellent error reporting
- **JSON snapshots**: Stable, version-independent test data (replaces .hp/.hands/.gt files)
- **Invariant testing**: Automated poker rule validation
- **Property-based testing**: Comprehensive edge case coverage with Hypothesis
- **CI/CD integration**: Seamless integration with continuous integration systems
- **Consistent commands**: All tests use `uv run pytest` prefix

For questions about testing, see existing test files for patterns and examples.
