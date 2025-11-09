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

- **serialize_hand_for_snapshot.py**: Canonical serialization aligned with Hands/HandsPlayers/HandsActions, amounts in cents, reinforced invariants.
- **test_snapshots.py**: Reference tests with syrupy covering legacy THP scenarios + invariant/constraint verification before DB insertion.
- **test_invariants.py**: Complementary business rules validation (poker rules).
- **test_hypothesis_properties.py**: Hypothesis test suites (optional) to verify invariance and detect non-conforming amounts.

**Expected Evolution**: The regression system is designed for iterative improvement. Scripts contain evolution notes and are structured for easy refactoring as requirements evolve.

#### Snapshot Tests (test_snapshots.py)

```bash
# Run snapshot tests
uv run pytest regression-tests/test_snapshots.py

# Update snapshots after code changes
uv run pytest regression-tests/test_snapshots.py --snapshot-update

# Review snapshot differences
uv run pytest regression-tests/test_snapshots.py --snapshot-details
```

- `verify_hand_invariants()` checks the presence and type of critical columns (amounts in cents, `NOT NULL` keys, etc.).
- `simulate_db_insert()` replays a virtual INSERT into Hands/HandsPlayers/HandsActions to detect any incompatibility before data reaches the database.
- After regeneration (`--snapshot-update`), quickly inspect the diff then run `uv run pytest regression-tests/test_snapshots.py` to confirm.

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
# Run property tests (optional)
uv run pytest regression-tests/test_hypothesis_properties.py -m hypothesis
```

- Hypothesis cases inject non-integer amounts to validate new database constraints.
- If `numpy` is not available, the Hypothesis suite is automatically skipped. Install it (`uv pip install numpy`) for complete coverage.

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
uv run python regression-tests/TestHandsPlayers_legacy.py -s PokerStars -f sample_hand.txt
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
   uv run pytest regression-tests/test_snapshots.py -k "new_hand"
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

> ℹ️ The script tries UTF-8 then falls back to CP1252 if necessary. Filter out outputs (`*.snapshot.json`, `*_summary.txt`) before re-running the tool in batch mode (e.g., `find … -name '*.txt' ! -name '*snapshot*' ! -name '*summary*'`).

## Directory Structure Summary

```
fpdb-3/
├── test/                           # Unit tests
│   └── test_*.py                   # Unit/integration tests
├── regression-tests/               # Regression testing system
│   ├── archive/                    # Historical THP tooling (reference only)
│   ├── test_snapshots.py          # Snapshot testing with syrupy (covers legacy cases)
│   ├── test_invariants.py         # Poker rules validation
│   └── test_hypothesis_properties.py # Property-based testing
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

## 🔧 Worros Legacy THP Workflow

### Quick Regression Testing with .hp/.hands/.gt Files

For developers who prefer the classic THP (TestHandsPlayers) workflow with legacy test files:

#### Commands

```bash
# Test single site (walks default directories)
uv run python regression-tests/TestHandsPlayers_legacy.py -s PokerStars

# Test single file
uv run python regression-tests/TestHandsPlayers_legacy.py -s Stars -f regression-test-files/cash/Stars/Flop/hand.txt

# Test directory tree
uv run python regression-tests/TestHandsPlayers_legacy.py -s Stars -d regression-test-files/cash/Stars/Flop/

# Test all sites (WARNING: very long!)
uv run python regression-tests/TestHandsPlayers_legacy.py
```

#### Output Format

The legacy THP provides error histograms by stat type:

```
---------------------
Errors by stat:
---------------------
(  4) : startCards
(  2) : allInEV
(  4) : street0CalledRaiseChance
(  2) : street0Raises
(  1) : street1CBChance
---------------------
Total Errors: 17
---------------------

-------- Parse Error List --------
PokerStars:
(0): regression-test-files/cash/Stars/Flop/hand1.txt
(X): regression-test-files/cash/Stars/Flop/hand2.txt  # Unexpected result
```

#### When to Use Legacy THP

**✅ Use legacy THP for:**
- Quick validation of parser changes against existing baselines
- Error histogram by stat type (useful for identifying patterns)
- Working with existing .hp/.hands/.gt files (127+ files available)
- Familiar Worros workflow for rapid iteration

**⚠️ Use modern approach for:**
- New test files (generates stable JSON snapshots)
- CI/CD integration (pytest-based)
- Complex debugging (invariants, comparisons, filters)
- Schema-independent tests (survives DB changes)

#### Integration with Modern Tests

**Important:** The modern pytest system (`test_thp_param.py`) automatically uses legacy
.hp/.hands/.gt files when available via `_compare_legacy_files()`.

This means:
- Running `pytest regression-tests/test_thp_param.py` will validate against both JSON snapshots AND legacy files
- Both test methods work together, not in conflict
- You can generate both formats for maximum compatibility

Generate both formats simultaneously:
```bash
uv run python tools/make_snapshot.py hand.txt --both-formats
# Creates:
# - hand.txt.snapshot.json (for CI/regression testing)
# - hand.txt.raw.json (for debugging with raw Hand objects)
```

#### Supported Sites

The legacy THP script supports all major poker sites:

- PokerStars
- Full Tilt Poker
- Party Poker
- iPoker
- Winamax
- Bovada
- OnGame
- Microgaming
- Cake
- Everest Poker
- Boss
- Entraction
- PokerTracker
- PKR
- And more (see `TestHandsPlayers_legacy.py:462-484`)

#### Site Aliases

Common site name variations accepted:
- `Stars` → `PokerStars`
- `FTP` → `Full Tilt Poker`
- `PP` → `Party Poker`

See `Options.py:site_alias()` for full list.

---

## 🔀 Dual Workflow Integration: Legacy THP + Modern JSON

### Overview

FPDB-3 **actively maintains both validation systems**. They are complementary, not mutually exclusive:

```
┌─────────────────────────────────────────────────────────────┐
│                    LEGACY THP WORKFLOW                       │
│  Fast iteration • Error histograms • 60+ test files          │
└─────────────────────────────────────────────────────────────┘
                            ∩
┌─────────────────────────────────────────────────────────────┐
│                  MODERN JSON WORKFLOW                        │
│  CI/CD friendly • Schema-independent • Deep debugging        │
└─────────────────────────────────────────────────────────────┘
```

### Quick Decision Guide

**Working on parser changes?**
→ Use Legacy THP for fast iteration
→ Use JSON snapshots for final validation

**Adding new test case?**
→ Use JSON snapshots (generate both formats with `--both-formats`)

**CI/CD pipeline?**
→ Use JSON snapshots (pytest-based)

**Debugging complex hand?**
→ Use JSON snapshots (invariant validation, manual editing)

**Need error patterns?**
→ Use Legacy THP (histogram shows which stats fail most)

### Complete Validation Workflow

For comprehensive validation documentation, see **[VALIDATION_GUIDE.md](VALIDATION_GUIDE.md)** which covers:

- Three-level validation system (Syntactic → Invariants → Semantic)
- Complete workflows for all use cases
- Troubleshooting guide with common errors
- CI/CD integration examples
- Validation checklists
- Decision matrices

### Quick Reference: Both Systems

```bash
# LEGACY THP - Fast validation
uv run python regression-tests/TestHandsPlayers_legacy.py -s PokerStars -f hand.txt
# Output: Error histogram in seconds

# MODERN JSON - Comprehensive validation
uv run python tools/make_snapshot.py hand.txt --output hand.snapshot.json
# Output: JSON with invariant checks

# BOTH FORMATS - Maximum compatibility
uv run python tools/make_snapshot.py hand.txt --both-formats
# Creates: hand.txt.snapshot.json + hand.txt.raw.json

# REGRESSION TEST - Compare against baseline
uv run python tools/make_snapshot.py --directory DIR --regression-mode
# Detects any changes from baseline snapshots
```

### Migration Path: .hp → .snapshot.json

For migrating legacy .hp files to modern JSON format:

```bash
# Dry run (see what would be migrated)
uv run python tools/migrate_hp_to_snapshots.py --dry-run

# Migrate specific directory
uv run python tools/migrate_hp_to_snapshots.py \
    --directory regression-test-files/active-sites/pokerstars/legacy

# Full migration with report
uv run python tools/migrate_hp_to_snapshots.py
```

The migration tool:
- ✅ Validates 100% identical output (see `documentations/md/validation_snapshots_report_EN.md`)
- ✅ Preserves all statistical data
- ✅ Adds invariant validation
- ✅ Generates detailed migration report

### Validation Levels

Both systems support multiple validation levels:

| Level | Legacy THP | Modern JSON | Time |
|-------|------------|-------------|------|
| **1: Parsing** | ✅ Implicit | ✅ `--verify-only` | Seconds |
| **2: Invariants** | ❌ No | ✅ Automatic | Minutes |
| **3: Statistics** | ✅ Full comparison | ✅ Pytest assertions | Variable |

**See [VALIDATION_GUIDE.md](VALIDATION_GUIDE.md) for complete details on each validation level.**

---

### Creating Legacy .hp Files

Legacy `.hp` files are Python dictionaries containing HandsPlayers statistics used by `TestHandsPlayers_legacy.py` for regression testing.

#### What is a .hp File?

**Format:** Serialized Python dictionary with per-player statistics
```python
{
  'Player1': {
    'seatNo': 1,
    'startCash': 1000,
    'winnings': 500,
    'rake': 25,
    'VPIP': True,
    'PFR': True,
    'street0Raises': 1,
    # ... 167 fields total
  },
  'Hero': { ... }
}
```

**Contents:** 167 statistical fields per player including:
- Basic stats: `seatNo`, `startCash`, `winnings`, `rake`, `totalProfit`
- Rake breakdown: `rakeDealt`, `rakeContributed`, `rakeWeighted`
- Preflop stats: `VPIP`, `PFR`, `street0_3BChance`, `street0_3BDone`
- Postflop stats: `street1CBChance`, `foldToStreet1CBDone`, etc.
- Position stats: `position`, `raiseFirstInChance`, `raisedFirstIn`
- All-in EV: `allInEV`, `wentAllIn`
- Cards: `card1` through `card20`

#### Why Use .hp Files?

**Advantages:**
- ✅ **Complete statistics** - All 167 HandsPlayers fields
- ✅ **Fast validation** - Tests run in < 5 seconds
- ✅ **Error histograms** - Shows which stats fail most frequently
- ✅ **Detailed rake info** - Includes `rakeDealt`, `rakeContributed`, `rakeWeighted`
- ✅ **Legacy compatibility** - Works with existing 60+ test files

**Use when:**
- Quick validation during parser development
- Need detailed statistical breakdown
- Working with existing .hp files
- Want error patterns (histogram by stat type)

#### Generating .hp Files

**Tool:** `tools/generate_hp_file.py`

**Single file:**
```bash
uv run python tools/generate_hp_file.py hand.txt --site PokerStars
# Creates: hand.txt.hp
```

**Entire directory:**
```bash
uv run python tools/generate_hp_file.py \
    --directory regression-test-files/active-sites/pokerstars/ \
    --site PokerStars
# Processes all .txt files in directory tree
```

**Overwrite existing:**
```bash
uv run python tools/generate_hp_file.py hand.txt --site PokerStars --force
```

**Output example:**
```
⚙️  Setting up test environment...
✅ Test environment ready

Progress: |████████████████████████████████████████| 100.0% Complete
✅ Generated hand.txt.hp (6 players)
   Players: Hero, Player1, Player2, Player3, Player5, Player6
   Stats per player: 167 fields
```

#### Validating .hp Files

After generating, verify the .hp file is correct:

```bash
# Test with TestHandsPlayers_legacy.py
uv run python regression-tests/TestHandsPlayers_legacy.py -s PokerStars -f hand.txt

# Expected output if correct:
# Total Errors: 0

# If errors detected, output shows histogram:
# (  2) : allInEV
# (  1) : VPIP
# Total Errors: 3
```

#### .hp vs .snapshot.json Comparison

| Aspect | .hp (Legacy) | .snapshot.json (Modern) |
|--------|--------------|------------------------|
| **Fields per player** | 167 | 42 |
| **Total data** | ~1,000 values | ~250 values |
| **Rake details** | ✅ Dealt/Contributed/Weighted | ❌ Only basic `rake` |
| **All stats** | ✅ VPIP, PFR, 3bet, etc. | ❌ Only canonical fields |
| **Format** | Python dict (Decimal precision) | JSON (integer cents) |
| **Speed** | ⚡ Very fast (< 5 sec) | 🐢 Slower (minutes) |
| **CI/CD** | ❌ Manual inspection | ✅ Automatic pass/fail |
| **Editability** | ⚠️ eval() required | ✅ Human-readable JSON |
| **Schema changes** | ❌ Breaks on DB changes | ✅ Survives changes |

**Recommendation:** Generate both formats for maximum compatibility:
```bash
# Modern JSON (for CI/CD)
uv run python tools/make_snapshot.py hand.txt --output hand.snapshot.json

# Legacy .hp (for fast iteration)
uv run python tools/generate_hp_file.py hand.txt --site PokerStars
```

#### Understanding Decimal Precision

.hp files use Python `Decimal` for financial precision:

```python
'rakeDealt': Decimal('20.83333333333333333333333333')
```

**Why so many decimals?**
- Mathematical accuracy (125 / 6 = 20.8333... is periodic)
- Prevents floating-point errors (0.1 + 0.2 ≠ 0.3 problem)
- Financial standard (never lose cents to rounding)

**This is correct and intentional!** See `documentations/md/hp_vs_snapshot_coherence_analysis.md` for detailed analysis.

#### Rake Calculation Methods in .hp Files

Legacy .hp files include **4 rake calculation methods**:

1. **rake** - Total rake paid (gagnant only)
   ```python
   'rake': 125  # Winner pays $1.25 rake
   ```

2. **rakeDealt** - Equal distribution among all seated players
   ```python
   'rakeDealt': Decimal('20.83333333333333...')  # 125¢ / 6 players
   ```

3. **rakeContributed** - Equal distribution among contributors
   ```python
   'rakeContributed': Decimal('31.25')  # 125¢ / 4 contributors
   ```

4. **rakeWeighted** - Proportional to pot contribution
   ```python
   'rakeWeighted': Decimal('62.15545755237045...')  # (contrib/pot) × rake
   ```

**All methods are mathematically correct and verified.** See coherence analysis for details.

---

### Creating Legacy .hands Files

Legacy `.hands` files are Python dictionaries containing Hands table statistics used by `TestHandsPlayers_legacy.py` for regression testing.

#### What is a .hands File?

**Format:** Serialized Python dictionary with per-hand aggregate statistics
```python
{
  'siteHandNo': '123456789',
  'startTime': datetime.datetime(2025, 11, 4, 12, 0, 0, tzinfo=pytz.utc),
  'seats': 9,
  'playersVpi': 3,
  'playersAtStreet1': 2,
  'playersAtShowdown': 2,
  'street0Raises': 1,
  'street1Pot': 450,
  'street1Raises': 2,
  'street2Pot': 900,
  'boardcard1': 22,  # Card rank encoding
  'boardcard2': 42,
  'boardcard3': 26,
  # ... ~35 fields total
}
```

**Contents:** ~35 statistical fields per hand including:
- **Hand identification**: `siteHandNo`, `tableName`, `startTime`, `gametypeId`
- **Player counts**: `seats`, `playersVpi`, `playersAtStreet1-4`, `playersAtShowdown`
- **Action statistics**: `street0-4Raises`, `street1-4Pot`
- **Board cards**: `boardcard1` through `boardcard5` (encoded as integers)
- **Metadata**: `fileId`, `importTime`, `sessionId`, `tourneyId`
- **Special**: `runItTwice`, `showdownPot`, `texture`

#### Why Use .hands Files?

**Advantages:**
- ✅ **Hand-level validation** - Tests aggregate statistics for the entire hand
- ✅ **Complements .hp files** - While .hp has per-player stats, .hands has per-hand stats
- ✅ **Board card validation** - Verifies flop/turn/river cards are parsed correctly
- ✅ **Complete sets** - Combine .hp + .hands + .gt for comprehensive validation

**Use when:**
- Testing hand-level aggregates (pot sizes, raise counts)
- Validating board card parsing
- Creating complete test sets (.hp + .hands + .gt)
- Verifying street-by-street action counts

#### Generating .hands Files

**Tool:** `tools/generate_hands_file.py`

**Single file:**
```bash
uv run python tools/generate_hands_file.py hand.txt --site PokerStars
# Creates: hand.txt.hands
```

**Entire directory:**
```bash
uv run python tools/generate_hands_file.py \
    --directory regression-test-files/active-sites/pokerstars/ \
    --site PokerStars
# Processes all .txt files in directory tree
```

**Overwrite existing:**
```bash
uv run python tools/generate_hands_file.py hand.txt --site PokerStars --force
```

**Output example:**
```
⚙️  Setting up test environment...
✅ Test environment ready

✅ Generated hand.txt.hands
   Hand ID: 123456789
   Seats: 9
   Players at showdown: 2
   Total fields: 35
```

#### Validating .hands Files

After generating, verify the .hands file is correct:

```bash
# Test with TestHandsPlayers_legacy.py
uv run python regression-tests/TestHandsPlayers_legacy.py -s PokerStars -f hand.txt

# Expected output if correct:
# Total Errors: 0 (hands)
```

---

### Creating Legacy .gt Files

Legacy `.gt` files are Python tuples containing GameType information used by `TestHandsPlayers_legacy.py` for regression testing.

#### What is a .gt File?

**Format:** Serialized Python tuple with game type metadata
```python
(
    1,              # [0]  siteId
    'USD',          # [1]  currency (USD, EUR, play, etc.)
    'ring',         # [2]  type (ring=cash, tour=tournament)
    'hold',         # [3]  base (hold, stud, draw)
    'holdem',       # [4]  game (holdem, omahahi, omaha8, razz, etc.)
    'nl',           # [5]  limit (nl, pl, fl)
    'h',            # [6]  hilo (h=high, l=low, s=split)
    'none',         # [7]  mix (none, horse, 8game, etc.)
    50,             # [8]  smallBlind (cents)
    100,            # [9]  bigBlind (cents)
    100,            # [10] smallBet (cents)
    200,            # [11] bigBet (cents)
    9,              # [12] maxSeats
    0,              # [13] ante (cents)
    False,          # [14] cap (table cap enabled?)
    False           # [15] zoom (fast-fold format?)
)
```

**Contents:** 16 fields describing the game structure:
- **Site & Currency**: `siteId`, `currency`
- **Game Structure**: `type` (ring/tour), `base` (hold/stud/draw), `game` (holdem/omaha/etc)
- **Betting Structure**: `limit` (nl/pl/fl), `hilo` (h/l/s)
- **Stakes**: `smallBlind`, `bigBlind`, `smallBet`, `bigBet`, `ante` (all in cents)
- **Table Settings**: `maxSeats`, `cap`, `zoom`
- **Special**: `mix` (for mixed game formats like HORSE)

#### Why Use .gt Files?

**Advantages:**
- ✅ **Game type validation** - Verifies parser correctly identifies game structure
- ✅ **Stakes verification** - Ensures blinds/antes parsed correctly
- ✅ **Complete sets** - Part of the trinity (.hp + .hands + .gt)
- ✅ **Lightweight** - Only 16 fields, very fast to generate/validate

**Use when:**
- Testing parser's game type detection
- Verifying stakes parsing (especially mixed currencies)
- Creating complete test sets
- Validating special formats (zoom, cap tables, mixed games)

#### Generating .gt Files

**Tool:** `tools/generate_gt_file.py`

**Single file:**
```bash
uv run python tools/generate_gt_file.py hand.txt --site PokerStars
# Creates: hand.txt.gt
```

**Entire directory:**
```bash
uv run python tools/generate_gt_file.py \
    --directory regression-test-files/active-sites/pokerstars/ \
    --site PokerStars
# Processes all .txt files in directory tree
```

**Overwrite existing:**
```bash
uv run python tools/generate_gt_file.py hand.txt --site PokerStars --force
```

**Output example:**
```
⚙️  Setting up test environment...
✅ Test environment ready

✅ Generated hand.txt.gt
   GameType fields (16 values):
     [0] siteId: 1
     [1] currency: USD
     [2] type: ring
     [3] base: hold
     [4] game: holdem
     [5] limit: nl
     [6] hilo: h
     [7] mix: none
     [8] smallBlind: 50
     [9] bigBlind: 100
     [10] smallBet: 100
     [11] bigBet: 200
     [12] maxSeats: 9
     [13] ante: 0
     [14] cap: False
     [15] zoom: False
```

#### Validating .gt Files

After generating, verify the .gt file is correct:

```bash
# Test with TestHandsPlayers_legacy.py
uv run python regression-tests/TestHandsPlayers_legacy.py -s PokerStars -f hand.txt

# Expected output if correct:
# Total Errors: 0 (gametype)
```

---

### Generating All Legacy Files at Once

**Tool:** `tools/generate_all_legacy_files.py`

Generate `.hp`, `.hands`, and `.gt` files simultaneously with a single command.

#### Generate All Three Types

**Single file:**
```bash
uv run python tools/generate_all_legacy_files.py hand.txt --site PokerStars
# Creates: hand.txt.hp, hand.txt.hands, hand.txt.gt
```

**Entire directory:**
```bash
uv run python tools/generate_all_legacy_files.py \
    --directory regression-test-files/active-sites/pokerstars/ \
    --site PokerStars
# Processes all .txt files in directory tree
```

**Auto-detect site from path:**
```bash
uv run python tools/generate_all_legacy_files.py \
    --directory regression-test-files/active-sites/pokerstars/ \
    --auto-detect-site
# Automatically detects "PokerStars" from directory path
```

#### Generate Specific Types Only

**Only .hp and .hands (skip .gt):**
```bash
uv run python tools/generate_all_legacy_files.py hand.txt \
    --site PokerStars \
    --types hp,hands
```

**Only .gt:**
```bash
uv run python tools/generate_all_legacy_files.py hand.txt \
    --site PokerStars \
    --types gt
```

#### Batch Processing Output

```
⚙️  Setting up test environment...
✅ Test environment ready

🔍 Found 150 hand history files
📝 Generating types: gt, hands, hp

[1/150] NLHE-6max-USD-0.05-0.10.txt (site: PokerStars)
  ✅ .hp
  ✅ .hands
  ✅ .gt

[2/150] PLO-6max-USD-0.10-0.25.txt (site: PokerStars)
  ✅ .hp
  ✅ .hands
  ⏭️  .gt (exists)

...

======================================================================
📊 SUMMARY BY FILE TYPE:
======================================================================

.GT FILES:
  ✅ Generated:  145 / 150
  ⏭️  Skipped:     3 / 150
  ❌ Errors:      2 / 150

.HANDS FILES:
  ✅ Generated:  147 / 150
  ⏭️  Skipped:     1 / 150
  ❌ Errors:      2 / 150

.HP FILES:
  ✅ Generated:  148 / 150
  ⏭️  Skipped:     0 / 150
  ❌ Errors:      2 / 150

======================================================================
```

---

### Comparison of Legacy File Types

| Aspect | .hp (HandsPlayers) | .hands (Hands) | .gt (GameType) |
|--------|-------------------|----------------|----------------|
| **Format** | Python dict | Python dict | Python tuple |
| **Scope** | Per-player | Per-hand | Per-game-type |
| **Fields** | 167 | ~35 | 16 |
| **Size** | Large (~50KB) | Medium (~5KB) | Small (~500B) |
| **Key Stats** | VPIP, PFR, 3bet, winnings | Pot sizes, player counts, board | Stakes, game type, limits |
| **Generation Time** | ~2 sec | ~2 sec | ~1 sec |
| **Use Case** | Player statistics | Hand aggregates | Game structure |
| **Required?** | ✅ Primary | ⚠️ Optional | ⚠️ Optional |
| **Existing Files** | 24 | 12 | 11 |
| **Tool** | `generate_hp_file.py` | `generate_hands_file.py` | `generate_gt_file.py` |

**Complete Test Set:** A hand with `.hp`, `.hands`, and `.gt` files has full coverage:
- `.hp` → validates per-player statistics
- `.hands` → validates hand-level aggregates
- `.gt` → validates game type detection

**Recommendation:** For comprehensive validation, generate all three types:
```bash
uv run python tools/generate_all_legacy_files.py hand.txt --site PokerStars
```

---

## 🔬 Invariant Validation

Modern JSON snapshots include automatic invariant validation to catch poker rule violations and data integrity issues.

### Generic Invariants (7 Rules)

These invariants apply to all poker game types:

1. **Money Conservation** - Total winnings + rake must equal final pot
   ```python
   sum(player_winnings) + rake == finalPot
   ```

2. **Unique Seats** - Each player must have a unique seat number
   ```python
   len(seat_numbers) == len(set(seat_numbers))
   ```

3. **Valid Seat Range** - Seat numbers must be within table limits
   ```python
   1 <= seatNo <= maxSeats
   ```

4. **Non-Negative Rake** - Rake cannot be negative
   ```python
   rake >= 0
   ```

5. **Winner Validation** - If pot > 0, at least one player must have winnings
   ```python
   if finalPot > 0: sum(player_winnings) > 0
   ```

6. **Valid Actions** - Action types must be recognized
   ```python
   actionType in ['fold', 'check', 'call', 'bet', 'raise', 'all-in', ...]
   ```

7. **Valid Streets** - Street names must be valid
   ```python
   street in ['preflop', 'flop', 'turn', 'river', 'showdown']
   ```

### Game-Specific Invariants (6 Rules)

These invariants validate game-specific rules:

#### Hold'em/Omaha Board Cards

**Rule:** Board must have 0, 3, 4, or 5 cards (not 1 or 2)
```python
board_count in [0, 3, 4, 5]  # No flop, flop, turn, or river
```

**Sequence Validation:**
- Turn requires complete flop (3 cards)
- River requires turn (4 cards)

**Example violations:**
```
❌ Invalid board card count: 2 (expected 0, 3, 4, or 5)
❌ Turn card present without complete flop
❌ River card present without turn card
```

#### Omaha Hole Cards

**Rule:** Omaha players must have 4 hole cards (or 0 if not shown)
```python
if hole_count > 0: hole_count == 4
```

**Example violation:**
```
❌ Omaha player Hero has 2 hole cards (expected 4)
```

#### Action Amounts

**Rules:**
- **Fold/Check**: amount must be 0
- **Call**: amount > 0 or amountCalled > 0
- **Raise/Bet**: amount > 0 or raiseTo > 0

**Example violations:**
```
❌ fold action should have amount=0, got 50
❌ Call action should have amount > 0 or amountCalled > 0
❌ raise action should have amount > 0 or raiseTo > 0
```

### Testing Invariants

**Run invariant tests:**
```bash
# All invariants on all hands
uv run pytest regression-tests/test_invariants.py -v

# Specific invariant
uv run pytest regression-tests/test_invariants.py -k "money_conservation"

# On specific site
uv run pytest regression-tests/test_invariants.py -k "PokerStars"
```

**Check invariants manually:**
```bash
# Generate snapshot and check invariants
uv run python tools/make_snapshot.py hand.txt --output hand.snapshot.json

# Review violations
cat hand.snapshot.json | jq '._metadata.invariant_violations'
# Should be [] (empty array)
```

### Invariant Violations in Snapshots

Snapshots include invariant violation metadata:

```json
{
  "_metadata": {
    "invariant_violations": [
      "Invalid board card count: 2 (expected 0, 3, 4, or 5)",
      "Omaha player Hero has 2 hole cards (expected 4)"
    ]
  }
}
```

**If violations found:**
1. Check parser logic for the affected game type
2. Verify hand history file format
3. Review manual corrections if any
4. Fix parser and regenerate snapshot

### Adding Custom Invariants

To add game-specific invariants, edit `tools/serialize_hand_for_snapshot.py`:

```python
def verify_hand_invariants(serialized_hand: Dict[str, Any]) -> List[str]:
    violations = []

    # Add your custom validation
    game_type = hand_details.get("gameType", "").lower()

    if "stud" in game_type:
        # Validate antes for stud games
        if hand_details.get("ante", 0) == 0:
            violations.append("Stud game should have antes")

    return violations
```

---

## 🔄 Legacy/Raw Hand Object Workflow

### Background: Supporting Worros Original Approach

The modern workflow above uses JSON snapshots, but Worros originally preferred working with **raw Hand objects** directly from the HHC (Hand History Converter). We now support both approaches.

### Raw Hand Object vs JSON Snapshots

| Approach | Pros | Cons | Use Case |
|----------|------|------|----------|
| **JSON Snapshots** | Stable, human-readable, CI-friendly | Less debugging detail | Production regression testing |
| **Raw Hand Objects** | Full debugging access, closer to parser | Database-dependent | Deep debugging, legacy workflow |

---

## 📋 Legacy Workflow Commands

### Basic Raw Hand Object Generation

```bash
# Generate raw Hand objects (JSON format, human-readable)
uv run python tools/make_snapshot.py hand.txt --raw-hand-objects --output hand.raw.json

# Generate raw Hand objects (pickle format, complete preservation)
uv run python tools/make_snapshot.py hand.txt --raw-hand-objects --raw-format pickle --output hand.raw.pkl

# Generate PokerStars format for web posting
uv run python tools/make_snapshot.py hand.txt --stars-format --output hand.stars.txt
```

### Print to stdout (Worros Style)

```bash
# Print Hand object to stdout for piping/debugging
uv run python tools/make_snapshot.py hand.txt --print-hand-stdout

# Pipe output for analysis
uv run python tools/make_snapshot.py hand.txt --print-hand-stdout | grep "Hero"
uv run python tools/make_snapshot.py hand.txt --print-hand-stdout > debug_output.txt
```

### Hybrid Workflow (Best of Both)

```bash
# Generate both snapshot JSON and raw Hand objects
uv run python tools/make_snapshot.py hand.txt --both-formats

# This creates:
# - hand.txt.snapshot.json (for CI/regression)
# - hand.txt.raw.json (for debugging)
```

### Raw Hand Object Comparison

```bash
# Compare raw Hand objects before/after code changes
uv run python tools/make_snapshot.py --compare-raw before.raw.json after.raw.json

# Example output:
# ❌ Hand 198361245189: totalpot changed
#    Before: 20.89
#    After:  21.15
```

### Directory Processing with Raw Objects

```bash
# Process entire directory, save raw objects
uv run python tools/make_snapshot.py --directory regression-test-files/Stars/cash/Flop \
  --raw-hand-objects --site PokerStars

# Regression testing with raw objects
uv run python tools/make_snapshot.py --directory regression-test-files/Stars/cash/Flop \
  --raw-hand-objects --regression-mode --site PokerStars
```

---

## 💡 When to Use Each Approach

### Use JSON Snapshots For:
- **CI/CD regression testing** (stable across schema changes)
- **Money conservation validation** (built-in invariant checks)
- **Long-term test maintenance** (human-readable diffs)
- **Cross-site regression detection** (normalized format)

### Use Raw Hand Objects For:
- **Deep parser debugging** (access to internal Hand state)
- **HHC development** (see exactly what converter produces)
- **Action sequence analysis** (raw action data vs processed)
- **Database debugging** (HandsActions vs Hand.actions comparison)

### Use Hybrid Approach For:
- **Complex bug investigation** (both perspectives)
- **Parser validation** (raw data + invariant checking)
- **Worros legacy workflow** (raw objects + modern CI)

---

For questions about testing, see existing test files for patterns and examples.
