# Testing Guide for fpdb-3

This document explains how to run tests in the fpdb-3 project.

## 🚀 Quick Start

```bash
# Run main test suite (recommended)
make test

# Or directly with pytest
uv run pytest

# Run all tests including GUI tests
make test-all
# Or
./run_tests.sh
```

## 📁 Test Structure

- **947 main tests** - All tests except GUI tests
- **35 GUI tests** - `test_HUD_main.py` (run separately due to Qt/GUI issues)
- **Test categories**: Unit tests, integration tests, performance tests, regression tests

## 🔧 Available Commands

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

## 🐛 Troubleshooting

### Common Issues

1. **Mock pollution between tests** ✅ **FIXED**
   - Problem: `sys.modules` mocks affecting other tests
   - Solution: Isolated mocks using `setUpClass`/`tearDownClass`

2. **GUI tests failing**
   - Expected on headless systems
   - Run with: `make test-gui` or `uv run pytest test/test_HUD_main.py`

3. **Performance test failures**
   - Adjust thresholds in `test_popup_performance.py` if needed
   - Current threshold: 50x linear scaling

### Test Isolation

Tests are properly isolated using:
- Class-level mock setup/teardown
- Module-level import isolation
- Proper cleanup of Qt objects

## 📊 Coverage Reports

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

## 🔍 Debugging Tests

```bash
# Verbose output with full tracebacks
make debug-test

# Run specific failing test
uv run pytest test/specific_test.py::TestClass::test_method -v -s

# Debug with pdb
uv run pytest test/failing_test.py --pdb
```

## ✅ Test Status

Current test suite status:
- ✅ 947/947 main tests passing
- ⚠️ GUI tests run separately (may show Qt warnings - normal)
- ✅ Mock isolation issues resolved
- ✅ CI/CD integration working
- ✅ Coverage reporting enabled

## 🛠️ Development Workflow

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

## 📝 Adding New Tests

- Place tests in `test/` directory
- Follow naming convention: `test_*.py`
- Use proper test isolation (see existing examples)
- For GUI tests, consider if they belong in `test_HUD_main.py` or should be separate

For questions about testing, see existing test files for patterns and examples.