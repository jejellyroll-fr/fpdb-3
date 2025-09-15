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

## 🔧 Debugging Workflow for  Issues

### The Problem

PokerStars and other sites sometimes provide **minimal hand history information**, making it difficult to:
- Calculate correct pot sizes
- Track side pots properly
- Handle complex all-in scenarios (Run It Twice, cash-outs)
- Validate rake calculations

### The Solution: Systematic Debugging Workflow

This workflow allows you to:
1. **Establish baselines** for known-good data
2. **Manually correct** problematic hands with accurate financial data
3. **Test code changes** against verified snapshots
4. **Prevent regressions** across multiple poker sites

---

## 📋 Step-by-Step Workflow

### Step 1.0: Establish Baseline (Regression Test)

**Purpose**: Create a reference point of current behavior before making changes.

```bash
# Test all Stars cash FLOP games to establish current state
uv run python tools/make_snapshot.py --directory regression-test-files/Stars/cash/Flop --site PokerStars --regression-mode
```

**What this does**:
- Processes all hand history files in the directory
- Generates `.temp.snapshot.json` files for each hand
- Compares against existing `.snapshot.json` baselines (if they exist)
- Reports any differences found

**Expected output**:
```
Found 45 files to process
Setting up test environment...
Processing: regression-test-files/Stars/cash/Flop/hand1.txt
Successfully processed 3 hands from hand1.txt
...
✅ No regressions detected
```

### Step 2.0: Isolate Problematic Hand

**Purpose**: Generate an editable snapshot of a specific hand with issues.

```bash
# Process the problematic hand and create editable JSON
uv run python tools/make_snapshot.py ~/Downloads/AnonymisedHand.txt --site PokerStars --output Anon-corrected.json
```

**What this does**:
- Parses the hand history file
- Extracts **direct database values** (no calculations)
- Creates human-readable JSON with financial data
- Generates summary file for quick review

**Example output structure**:
```json
{
  "site": "PokerStars",
  "hand_text_id": "12345678",
  "total_pot": 45.50,
  "rake": 1.25,
  "players": [
    {
      "name": "Hero",
      "net_winnings": 44.25,
      "total_profit": -12.50,
      "went_all_in": true
    }
  ]
}
```

### Step 3.0: Add to Regression Test Suite (Manual)

**Purpose**: Integrate the corrected hand into the permanent test suite.

```bash
# Copy hand history to regression test directory
cp ~/Downloads/AnonymisedHand.txt regression-test-files/Stars/cash/Flop/Anon-allInEV-fix.txt

# Copy snapshot as baseline (you'll edit this next)
cp Anon-corrected.json regression-test-files/Stars/cash/Flop/Anon-allInEV-fix.txt.snapshot.json
```

**File naming convention**:
- **Descriptive names**: `Anon-allInEV-fix.txt` (not `hand123.txt`)
- **Matching pairs**: `file.txt` and `file.txt.snapshot.json`
- **Organized by issue**: Group related test cases together

### Step 4.0: Manual Correction (The Critical Step)

**Purpose**: Edit the JSON snapshot with the **correct** financial values.

```bash
# Edit the snapshot file with your preferred editor
code regression-test-files/Stars/cash/Flop/Anon-allInEV-fix.txt.snapshot.json
```

**What to correct**:
1. **Pot sizes**: Ensure `total_pot` matches actual pot
2. **Rake**: Verify rake calculation is correct
3. **Winnings**: Set `net_winnings` to actual amounts won
4. **AllInEV**: Calculate expected winnings vs actual
5. **Side pots**: Handle complex multi-way all-ins

**Example correction**:
```json
// BEFORE (incorrect from database)
"total_pot": 45.50,
"rake": 1.25,
"net_winnings": 44.25,

// AFTER (manually verified correct values)
"total_pot": 47.80,
"rake": 1.30,
"net_winnings": 46.50,
```

### Step 5.0: Validate Corrections

**Purpose**: Compare your manual corrections against the current parser output.

```bash
# Generate current snapshot for comparison
uv run python tools/make_snapshot.py regression-test-files/Stars/cash/Flop/Anon-allInEV-fix.txt --output current.json

# Compare corrected vs current
uv run python tools/make_snapshot.py --compare regression-test-files/Stars/cash/Flop/Anon-allInEV-fix.txt.snapshot.json current.json
```

**Expected output if issues exist**:
```
❌ Hand 12345678: total_pot changed
   Before: 47.80  (your correction)
   After:  45.50  (current parser)

❌ Hand 12345678: net_winnings changed
   Before: 46.50  (your correction)
   After:  44.25  (current parser)

❌ Differences found - regression detected!
```

### Step 6.0: Fix Code and Test

**Purpose**: Modify the parser code to match your corrected values, then verify the fix.

```bash
# After making code changes to fix the AllInEV calculation...

# Re-run regression test on the directory
uv run python tools/make_snapshot.py --directory regression-test-files/Stars/cash/Flop --site PokerStars --regression-mode
```

**Success looks like**:
```
✅ No regression in Anon-allInEV-fix.txt
✅ No regression in existing-hand-1.txt
✅ No regression in existing-hand-2.txt
...
✅ No regressions detected
```

**Failure looks like**:
```
❌ Regression detected in existing-hand-1.txt
   Before: total_pot = 25.00
   After:  total_pot = 25.50
```

### Step 7.0: Multi-Site Validation

**Purpose**: Ensure your PokerStars fix doesn't break other poker sites.

```bash
# Test all FLOP cash games across all sites
uv run python tools/make_snapshot.py --directory regression-test-files --filter-game FLOP --type cash --regression-mode

# Test specific sites if needed
uv run python tools/make_snapshot.py --directory regression-test-files/Winamax --regression-mode
uv run python tools/make_snapshot.py --directory regression-test-files/PartyPoker --regression-mode
```

**What to watch for**:
- No regressions in existing Winamax/Party/888 files
- Only improvements in PokerStars files
- Clean test suite across all supported sites

---

## 🎯 Advanced Filtering Examples

### Game Type Filtering
```bash
# Only Hold'em and Omaha variants
uv run python tools/make_snapshot.py --directory regression-test-files --filter-game FLOP --regression-mode

# Only Stud variants (7-Stud, Razz, etc.)
uv run python tools/make_snapshot.py --directory regression-test-files --filter-game STUD --regression-mode

# Only Draw variants (5-Card Draw, Badugi, etc.)
uv run python tools/make_snapshot.py --directory regression-test-files --filter-game DRAW --regression-mode
```

### Format Filtering
```bash
# Only cash games
uv run python tools/make_snapshot.py --directory regression-test-files --type cash --regression-mode

# Only tournaments
uv run python tools/make_snapshot.py --directory regression-test-files --type tourney --regression-mode

# Combined: Only tournament Hold'em/Omaha games
uv run python tools/make_snapshot.py --directory regression-test-files --filter-game FLOP --type tourney --regression-mode
```

### Site-Specific Testing
```bash
# Test only PokerStars files
uv run python tools/make_snapshot.py --directory regression-test-files/Stars --site PokerStars --regression-mode

# Test only files with "side-pot" in the name
uv run python tools/make_snapshot.py regression-test-files/**/*side-pot*.txt --regression-mode
```

---

## 🚨 Troubleshooting Common Issues

### Issue 1: "No files match the specified filters"

**Cause**: Filter criteria too restrictive or wrong directory structure.

**Solution**:
```bash
# Check what files exist
ls -la regression-test-files/Stars/cash/Flop/

# Remove filters temporarily to see all files
uv run python tools/make_snapshot.py --directory regression-test-files/Stars/cash/Flop --regression-mode
```

### Issue 2: "Error setting up test environment"

**Cause**: Database configuration issues or missing dependencies.

**Solution**:
```bash
# Ensure test config exists
ls -la HUD_config.test.xml

# Check database connectivity
uv run python -c "import Configuration; print('Config OK')"
```

### Issue 3: "Multiple regressions detected after fix"

**Cause**: Your fix changed behavior for other hands (expected if old behavior was wrong).

**Solution**:
```bash
# Review each regression individually
uv run python tools/make_snapshot.py --compare old.json new.json

# If changes are correct, update the baselines:
cp new.json old.json  # For each affected file
```

### Issue 4: JSON editing errors

**Cause**: Invalid JSON syntax after manual editing.

**Solution**:
```bash
# Validate JSON syntax
python -c "import json; print(json.load(open('file.json')))"

# Use a proper JSON editor/linter
# Common errors: trailing commas, unquoted strings, missing brackets
```

### Issue 5: Invariant violations

**Cause**: Manual corrections don't follow poker rules (e.g., winnings + rake ≠ pot).

**Example error**:
```
Invariant violations in hand 12345678:
  - Money conservation failed: winnings(45.00) + rake(1.25) != pot(47.80)
```

**Solution**:
```bash
# Check poker math in your corrections:
# total_pot = sum(all_winnings) + rake
# Example: 47.80 = 46.50 + 1.30 ✓

# Use verify-only mode to check without saving
uv run python tools/make_snapshot.py file.txt --verify-only
```

---

## 💡 Best Practices

### Naming Conventions
- **Use descriptive names**: `Stars-AllIn-SidePot-Bug123.txt`
- **Include issue numbers**: Reference GitHub issues or forum posts
- **Group related tests**: Put similar issues in same directory

### Documentation
- **Add comments in snapshots**: Document why specific values are correct
- **Keep issue links**: Reference 2+2 forum posts, GitHub issues
- **Note manual corrections**: Mark fields that were manually verified

### Workflow Efficiency
- **Start small**: Fix one hand at a time before batch processing
- **Use verify-only**: Check invariants without generating files
- **Test incrementally**: Run regression tests after each code change

### Example Snapshot Documentation
```json
{
  "_metadata": {
    "issue": "https://github.com/user/fpdb/issues/123",
    "forum_post": "https://forumserver.twoplustwo.com/123",
    "manually_verified": ["total_pot", "rake", "net_winnings"],
    "verification_date": "2024-09-14",
    "notes": "Side pot calculation was incorrect in original parser"
  },
  "total_pot": 47.80,
  "rake": 1.30
}
```

---

## 🔄 Integration with CI/CD

Add regression testing to your continuous integration:

```bash
# In your CI script (.github/workflows/test.yml)
- name: Run AllInEV Regression Tests
  run: |
    uv run python tools/make_snapshot.py --directory regression-test-files --regression-mode
    if [ $? -ne 0 ]; then
      echo "❌ Regressions detected in AllInEV calculations"
      exit 1
    fi
```

This ensures any code changes are automatically tested against your verified baselines.

---

For questions about testing, see existing test files for patterns and examples.
