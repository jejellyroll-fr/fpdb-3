# FPDB-3 Validation Guide

> Comprehensive guide for validating poker hand histories and regression testing

---

## Table of Contents

1. [Overview](#overview)
2. [Current State](#current-state)
3. [Validation Architecture](#validation-architecture)
4. [Dual Workflow System](#dual-workflow-system)
5. [Decision Matrix](#decision-matrix)
6. [Validation Levels](#validation-levels)
7. [Complete Workflows](#complete-workflows)
8. [Troubleshooting Guide](#troubleshooting-guide)
9. [Validation Checklist](#validation-checklist)
10. [CI/CD Integration](#cicd-integration)

---

## Overview

FPDB-3 maintains **two complementary validation systems** for regression testing:

1. **Legacy THP** (TestHandsPlayers) - Original Worros workflow using .hp/.hands/.gt files
2. **Modern JSON Snapshots** - New pytest-based system using .snapshot.json files

**Both systems are fully supported and maintained.** Choose based on your workflow needs.

---

## Current State

### Test File Inventory

**Active Sites:**
- files organized by network/year/skin
- Sites: PokerStars, Winamax, 888poker, GGPoker, Bovada/Ignition, iPoker network, Cake

**File Types:**
-  **.txt files** - Hand history source files (source of truth)
-  **.hp/gt/hand files** - Legacy validation data (binary format)
-  **.snapshot.json** - Modern JSON validation data (expanding)
-  **Companion files** - .hands, .gt files for legacy tests

### File Organization

```
regression-test-files/
├── active-sites/
│   ├── pokerstars/
│   │   ├── legacy/2010/stars/cash/
│   │   │   ├── NLHE-6max-USD-0.05-0.10-200912.Allin-pre.txt
│   │   │   ├── NLHE-6max-USD-0.05-0.10-200912.Allin-pre.txt.hp
│   │   │   └── NLHE-6max-USD-0.05-0.10-200912.Allin-pre.txt.snapshot.json
│   │   └── 2024/stars/cash/
│   ├── winamax/
│   ├── 888poker/
│   └── bovada-network/
└── inactive-sites/
    └── [archived poker sites]
```

---

## Validation Architecture

### Three-Level Validation System

```
┌─────────────────────────────────────────────────────────────┐
│                     LEVEL 1: SYNTACTIC                       │
│  ✓ Parser doesn't crash                                     │
│  ✓ Required fields present                                  │
│  ✓ Data types correct                                       │
│  Speed: Seconds                                              │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                     LEVEL 2: INVARIANTS                      │
│  ✓ Money conservation (in = out)                            │
│  ✓ Pot coherence (street0Pot ≤ street1Pot ≤ ...)           │
│  ✓ Rake validation (0 ≤ rake ≤ 50% pot)                    │
│  ✓ Database schema compatibility                            │
│  Speed: Minutes                                              │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                     LEVEL 3: SEMANTIC                        │
│  ✓ Player statistics correct (VPIP, PFR, 3bet, etc.)       │
│  ✓ All-in EV calculations                                   │
│  ✓ Position statistics                                      │
│  ✓ Comparison with legacy data (if available)               │
│  Speed: Hours (full suite)                                   │
└─────────────────────────────────────────────────────────────┘
```

---

## Dual Workflow System

### System Comparison

| Aspect | Legacy THP | Modern JSON Snapshots |
|--------|------------|----------------------|
| **Format** | Binary .hp/.hands/.gt files | Human-readable JSON |
| **Speed** | ⚡ Fast (seconds) | 🐢 Slower (minutes) |
| **Error Display** | Histogram by stat type | Detailed diff with context |
| **Schema Changes** | ❌ Breaks on DB changes | ✅ Survives schema changes |
| **Editability** | ❌ Binary, not editable | ✅ JSON, easily editable |
| **Debugging** | Quick iteration | Deep analysis |
| **CI/CD** | Manual inspection needed | ✅ Automatic pass/fail |
| **Coverage** | 60+ legacy files | Expanding (new tests) |
| **Maintenance** | Stable, frozen | Active development |

### Visual Workflow Comparison

```
LEGACY THP WORKFLOW:
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ hand.txt │───▶│ Parse    │───▶│ Compare  │───▶│ Error    │
│          │    │ to DB    │    │ with .hp │    │ Histogram│
└──────────┘    └──────────┘    └──────────┘    └──────────┘
                                      ▲
                                      │ Legacy reference data
                                 ┌──────────┐
                                 │ hand.hp  │
                                 │ hand.gt  │
                                 └──────────┘

MODERN JSON WORKFLOW:
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ hand.txt │───▶│ Parse    │───▶│ Serialize│───▶│ Validate │
│          │    │ to DB    │    │ to JSON  │    │ Invariants│
└──────────┘    └──────────┘    └──────────┘    └──────────┘
                                      │
                                      ▼
                                 ┌──────────┐    ┌──────────┐
                                 │hand.json │───▶│ Pytest   │
                                 │snapshot  │    │ Assertion│
                                 └──────────┘    └──────────┘
```

---

## Decision Matrix

### When to Use Which System

#### Use Legacy THP When:

✅ **Quick validation during development**
```bash
# Instant feedback with error histogram
uv run python regression-tests/TestHandsPlayers_legacy.py -s PokerStars -f hand.txt
```

✅ **Working with existing .hp files** (60+ available)

✅ **Debugging parser changes** (fast iteration)

✅ **Need error patterns** (histogram shows which stats fail most)

✅ **Daily development workflow** (< 5 second feedback loop)

#### Use Modern JSON Snapshots When:

✅ **Creating new test cases** (future-proof format)

✅ **CI/CD automation** (clear pass/fail, no manual inspection)

✅ **Deep debugging** (human-readable, editable, version control friendly)

✅ **Database schema changes** (JSON survives, .hp breaks)

✅ **Invariant validation** (automatic money conservation checks)

✅ **Documentation** (JSON can be reviewed in PRs)

✅ **Cross-verification** (compare against legacy for migration)

---

## Validation Levels

### Level 1: Syntactic Validation

**Objective:** Does the hand parse without errors?

**Time:** Seconds per file

**Commands:**

```bash
# Quick parse check (no snapshot generation)
uv run python tools/make_snapshot.py hand.txt --verify-only

# Legacy THP (also checks parsing)
uv run python regression-tests/TestHandsPlayers_legacy.py -s PokerStars -f hand.txt
```

**What's Validated:**
- ✅ Parser doesn't crash
- ✅ Site detected correctly
- ✅ All required fields present (players, blinds, actions)
- ✅ Data types correct (integers for money, strings for names)
- ✅ Date format valid

**Expected Output:**
```
✅ All hands parsed successfully
✅ 1 hand(s) processed
```

**Common Errors:**
- `ParseException`: Malformed hand history
- `Site detection failed`: Unknown format
- `Missing required field`: Incomplete hand history

---

### Level 2: Invariant Validation

**Objective:** Does the data respect poker's mathematical laws?

**Time:** Minutes per file

**Commands:**

```bash
# Generate snapshot with invariant validation
uv run python tools/make_snapshot.py hand.txt --output hand.snapshot.json

# Check validation status
cat hand.snapshot.json | jq '._metadata.invariant_violations'
```

**What's Validated:**

#### Money Conservation
```
Sum(player startCash) + Sum(rake) = Sum(player endCash)
```

#### Pot Coherence
```
street0Pot ≤ street1Pot ≤ street2Pot ≤ street3Pot ≤ finalPot
```

#### Rake Validity
```
0 ≤ rake ≤ 0.5 * totalPot (50% cap)
rake ≥ 0 (no negative rake)
```

#### Winnings Accuracy
```
Sum(player winnings) = totalPot - rake
For each player: winnings = collected - contributed
```

#### Database Schema Compliance
```
All foreign keys valid
All required fields present for DB insertion
Data types match schema
```

**Expected Output:**
```json
{
  "_metadata": {
    "invariant_violations": 0,
    "validation_level": "auto"
  }
}
```

**Common Violations:**
- `Money conservation failed`: Parsing error in bets/collections
- `Pot coherence violated`: Incorrect pot building logic
- `Negative rake`: Collection parsing error
- `Winnings mismatch`: Side pot calculation error

---

### Level 3: Semantic Validation

**Objective:** Are derived statistics correct?

**Time:** Hours (full suite), minutes (single file)

**Commands:**

```bash
# Compare against legacy data (if .hp exists)
uv run python regression-tests/TestHandsPlayers_legacy.py -s PokerStars -f hand.txt

# Pytest snapshot comparison
uv run pytest regression-tests/test_snapshots.py -k "hand_name" -v

# Run full regression suite
uv run pytest regression-tests/test_snapshots.py
```

**What's Validated:**

#### Preflop Statistics
- `VPIP` (Voluntarily Put In Pot)
- `PFR` (Preflop Raise)
- `3bet`, `4bet` opportunities and actions
- `Steal` attempts and success rate

#### Postflop Statistics
- `Continuation bet` chances and actions (all streets)
- `Check-raise` frequency
- `Fold to CB` statistics
- `Aggression` factors

#### All-in EV Calculations
- Expected value when all-in
- Equity calculations
- Multiple all-ins

#### Position Statistics
- `In position` flags
- `First to act` tracking
- Button/blind statistics

**Expected Output (Legacy):**
```
---------------------
Errors by stat:
---------------------
---------------------
Total Errors: 0
---------------------
```

**Expected Output (Pytest):**
```
test_pokerstars_snapshot.py::test_hand_allin_preflop PASSED
```

**Common Errors:**
- `VPIP mismatch`: Blind/ante handling
- `All-in EV incorrect`: Equity calculation bug
- `Position wrong`: Button/blind detection error
- `CB stats mismatch`: Street parsing error

---

## Complete Workflows

### Workflow A: Validating a New Hand History

**Use Case:** You found a new hand on a forum and want to add it to the test suite.

**Steps:**

1. **Download and name the file**
   ```bash
   # Follow naming convention: {GAME}-{FORMAT}-{CURRENCY}-{STAKES}-{DATE}.{FEATURE}.txt
   # Example: NLHE-6max-USD-0.25-0.50-202411.Hero-bad-beat.txt
   ```

2. **Level 1: Quick parse check**
   ```bash
   uv run python tools/make_snapshot.py hand.txt --verify-only
   ```

   If errors → Fix hand history or parser

3. **Level 2: Generate snapshot with invariants**
   ```bash
   uv run python tools/make_snapshot.py hand.txt --output hand.snapshot.json

   # Check for violations
   cat hand.snapshot.json | jq '._metadata.invariant_violations'
   ```

   If violations > 0 → Investigate with:
   ```bash
   cat hand.snapshot.json | jq '.snapshot[0].invariant_checks'
   ```

4. **Manual review**
   ```bash
   # Verify critical fields
   cat hand.snapshot.json | jq '.snapshot[0].hand_details | {totalPot, rake, siteName}'

   # Check player winnings
   cat hand.snapshot.json | jq '.snapshot[0].players[] | {name, winnings, totalProfit}'
   ```

5. **Commit to repository**
   ```bash
   git add hand.txt hand.snapshot.json
   git commit -m "test: add regression case for [FEATURE]"
   ```

6. **Level 3: Run pytest (creates baseline)**
   ```bash
   uv run pytest regression-tests/test_snapshots.py --snapshot-update
   ```

**Time:** 5-10 minutes per hand

---

### Workflow B: Testing Parser Changes

**Use Case:** You modified a parser and want to verify no regressions.

**Fast Iteration (Legacy THP):**

```bash
# Test single site quickly
uv run python regression-tests/TestHandsPlayers_legacy.py -s PokerStars

# Output shows error histogram
# Example:
# wpfr: 2 errors
# VPIP: 1 error
# Total Errors: 3
```

**Comprehensive Validation (Modern JSON):**

```bash
# Regression mode: regenerate all snapshots and compare
uv run python tools/make_snapshot.py \
    --directory regression-test-files/active-sites/pokerstars \
    --regression-mode

# If differences detected, review them:
uv run python tools/make_snapshot.py \
    --compare baseline.json new.json
```

**Time:**
- Legacy: 30 seconds - 2 minutes
- Modern: 5-15 minutes (depending on file count)

---

### Workflow C: Collecting New Hands from Forums

**Use Case:** You want to expand test coverage for Winamax 2024 hands.

**See:** [COLLECTION_WINAMAX.md](COLLECTION_WINAMAX.md) for site-specific guide

**General Steps:**

1. **Find hands on forums/communities**
   ```bash
   # Google search operators
   site:forumserver.twoplustwo.com "winamax" "hand history" after:2024-01-01
   ```

2. **Validate format** (site-specific)
   ```bash
   # Use site-specific validator
   uv run python tools/validate_winamax_hand.py hand.txt
   ```

3. **Follow Workflow A** (validating new hand)

4. **Organize by network/year**
   ```bash
   # Place in correct directory
   regression-test-files/active-sites/winamax/2024/winamax/cash/
   ```

**Time:** 15-30 minutes per hand (including search)

---

### Workflow D: Creating Legacy .hp Files

**Use Case:** You want to create legacy .hp files for use with TestHandsPlayers_legacy.py.

**What are .hp files?**

Legacy .hp files contain HandsPlayers statistics (Python dictionaries) used by TestHandsPlayers_legacy.py for regression testing. They store per-player statistics like VPIP, PFR, winnings, etc.

**Format:** `{"Player1": {"seatNo": 1, "startCash": 1000, ...}, "Player2": {...}}`

**Commands:**

```bash
# Generate .hp for single file
uv run python tools/generate_hp_file.py hand.txt --site PokerStars

# Generate for all files in directory
uv run python tools/generate_hp_file.py \
    --directory regression-test-files/active-sites/pokerstars/ \
    --site PokerStars

# Overwrite existing .hp files
uv run python tools/generate_hp_file.py hand.txt --site PokerStars --force
```

**Validation:**

```bash
# Test the generated .hp file
uv run python regression-tests/TestHandsPlayers_legacy.py -s PokerStars -f hand.txt

# Should show "Total Errors: 0" if .hp is correct
```

**Time:** 2-5 seconds per file

**Note:** The .hp file is automatically placed next to the .txt file with `.hp` extension.

---

### Workflow D2: Creating Legacy .hands Files

**Use Case:** You want to generate legacy .hands files (Hands table statistics) for regression testing.

Legacy .hands files contain Hands table statistics (Python dictionaries) used by TestHandsPlayers_legacy.py. They store per-hand aggregate statistics like pot sizes, player counts, board cards, etc.

**Format:** `{'siteHandNo': '123456', 'seats': 9, 'playersAtShowdown': 2, ...}`

**Commands:**

```bash
# Generate .hands for single file
uv run python tools/generate_hands_file.py hand.txt --site PokerStars

# Generate for all files in directory
uv run python tools/generate_hands_file.py \
    --directory regression-test-files/active-sites/pokerstars/ \
    --site PokerStars

# Overwrite existing .hands files
uv run python tools/generate_hands_file.py hand.txt --site PokerStars --force
```

**Validation:**

```bash
# Test the generated .hands file
uv run python regression-tests/TestHandsPlayers_legacy.py -s PokerStars -f hand.txt

# Should show "Total Errors: 0 (hands)" if .hands is correct
```

**Time:** 2-5 seconds per file

**Note:** The .hands file is automatically placed next to the .txt file with `.hands` extension.

---

### Workflow D3: Creating Legacy .gt Files

**Use Case:** You want to generate legacy .gt files (GameType information) for regression testing.

Legacy .gt files contain GameType information (Python tuples) used by TestHandsPlayers_legacy.py. They store game structure metadata like stakes, game type, limits, etc.

**Format:** `(siteId, currency, type, base, game, limit, hilo, mix, smallBlind, bigBlind, ...)`

**Commands:**

```bash
# Generate .gt for single file
uv run python tools/generate_gt_file.py hand.txt --site PokerStars

# Generate for all files in directory
uv run python tools/generate_gt_file.py \
    --directory regression-test-files/active-sites/pokerstars/ \
    --site PokerStars

# Overwrite existing .gt files
uv run python tools/generate_gt_file.py hand.txt --site PokerStars --force
```

**Validation:**

```bash
# Test the generated .gt file
uv run python regression-tests/TestHandsPlayers_legacy.py -s PokerStars -f hand.txt

# Should show "Total Errors: 0 (gametype)" if .gt is correct
```

**Time:** 1-2 seconds per file

**Note:** The .gt file is automatically placed next to the .txt file with `.gt` extension.

---

### Workflow D4: Batch Generation of All Legacy Files

**Use Case:** You want to generate all three legacy file types (.hp, .hands, .gt) at once, or process many files efficiently.

**Commands:**

```bash
# Generate all three types for single file
uv run python tools/generate_all_legacy_files.py hand.txt --site PokerStars

# Generate all types for directory
uv run python tools/generate_all_legacy_files.py \
    --directory regression-test-files/active-sites/pokerstars/ \
    --site PokerStars

# Auto-detect site from directory path
uv run python tools/generate_all_legacy_files.py \
    --directory regression-test-files/active-sites/pokerstars/ \
    --auto-detect-site

# Generate only specific types (e.g., skip .gt)
uv run python tools/generate_all_legacy_files.py hand.txt \
    --site PokerStars \
    --types hp,hands

# Overwrite existing files
uv run python tools/generate_all_legacy_files.py hand.txt \
    --site PokerStars \
    --force
```

**Validation:**

```bash
# Test all generated legacy files
uv run python regression-tests/TestHandsPlayers_legacy.py -s PokerStars -f hand.txt

# Should show "Total Errors: 0" if all files are correct
```

**Time:** 3-6 seconds per file (all three types)

**Batch Output Example:**

```
⚙️  Setting up test environment...
✅ Test environment ready

🔍 Found 150 hand history files
📝 Generating types: gt, hands, hp

[1/150] NLHE-6max-USD-0.05-0.10.txt (site: PokerStars)
  ✅ .hp
  ✅ .hands
  ✅ .gt

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

**Recommendation:** Use this workflow for creating complete test sets with all three legacy file types.

---

### Workflow E: Migrating Legacy .hp to JSON

**Use Case:** You have legacy .hp files and want to create modern JSON snapshots.

**Commands:**

```bash
# Dry run (see what would be migrated)
uv run python tools/migrate_hp_to_snapshots.py --dry-run

# Migrate specific directory
uv run python tools/migrate_hp_to_snapshots.py \
    --directory regression-test-files/active-sites/pokerstars/legacy

# Migrate with limit (testing)
uv run python tools/migrate_hp_to_snapshots.py --limit 5

# Full migration
uv run python tools/migrate_hp_to_snapshots.py
```

**Validation:**

```bash
# Compare migrated vs direct generation
uv run python tools/make_snapshot.py \
    --compare hand.txt.snapshot.json \
    hand-direct.snapshot.json
```

**Time:** 2-5 seconds per file

---

### Workflow E: Pre-Commit Validation

**Use Case:** You want to validate changes before committing.

**Quick Check:**

```bash
# Run tests on modified files
git diff --name-only '*.txt' | while read file; do
    echo "Testing $file..."
    uv run python tools/make_snapshot.py "$file" --verify-only
done
```

**Full Regression:**

```bash
# Run pytest suite
uv run pytest regression-tests/test_snapshots.py -v

# Run legacy THP on all active sites
for site in PokerStars Winamax "888poker"; do
    echo "Testing $site..."
    uv run python regression-tests/TestHandsPlayers_legacy.py -s $site
done
```

**Time:**
- Quick: 30 seconds
- Full: 5-10 minutes

---

## Troubleshooting Guide

### Problem: Parser Crashes on Hand History

**Symptoms:**
```
ParseException: Unable to parse hand history
```

**Diagnosis:**

1. Check site detection:
   ```bash
   uv run python -c "from IdentifySite import identify_site; print(identify_site('hand.txt'))"
   ```

2. Check encoding:
   ```bash
   file hand.txt
   # Should show: UTF-8 or ASCII
   ```

3. Check format manually:
   ```bash
   head -20 hand.txt
   # Verify site-specific header format
   ```

**Solutions:**

- **Wrong site detected:** Rename file to include site name, or use `--site` flag
- **Encoding issues:** Convert to UTF-8: `iconv -f CP1252 -t UTF-8 hand.txt > hand_utf8.txt`
- **Malformed hand:** Compare against working example from same site
- **Missing parser support:** Check if parser exists for this site variant

---

### Problem: Invariant Violations Detected

**Symptoms:**
```json
{
  "_metadata": {
    "invariant_violations": 3
  }
}
```

**Diagnosis:**

```bash
# Show detailed violations
cat hand.snapshot.json | jq '.snapshot[0].invariant_checks'
```

**Common Violations and Fixes:**

#### Money Conservation Failed
```
IN: startCash = 10000, rake = 50
OUT: endCash = 9500
VIOLATION: 10000 + 50 ≠ 9500 (missing 550)
```

**Causes:**
- Side pot calculation error
- Uncollected bets
- Parsing missed a collection line

**Fix:** Review `collectPot()` logic and collection regexes

#### Pot Coherence Violated
```
street1Pot = 500
street2Pot = 400
VIOLATION: Pot decreased between streets
```

**Causes:**
- Pot parsing error (missed all-in)
- Side pot confusion
- Street marker misaligned

**Fix:** Review `addCallandRaise()` and street pot building

#### Rake Exceeds 50% of Pot
```
totalPot = 100
rake = 60
VIOLATION: rake > 0.5 * totalPot
```

**Causes:**
- Rake parsing regex error
- Currency conversion issue
- Tournament fee misinterpreted as rake

**Fix:** Review rake regex patterns for this site

---

### Problem: Legacy THP Shows Many Errors

**Symptoms:**
```
Total Errors: 45
allInEV: 12 errors
VPIP: 8 errors
street0Raises: 7 errors
```

**Diagnosis:**

This is often **expected behavior** - it shows differences, not necessarily bugs.

**Interpretation:**

1. **Old .hp files may be wrong** - Legacy data frozen in time, may contain old bugs
2. **New calculations may be correct** - Parser improvements since .hp was created
3. **Different interpretation** - Edge cases handled differently

**Action Plan:**

1. **Pick one example:**
   ```bash
   # Find a file with allInEV error
   uv run python regression-tests/TestHandsPlayers_legacy.py -s PokerStars -f specific-hand.txt
   ```

2. **Generate modern snapshot:**
   ```bash
   uv run python tools/make_snapshot.py specific-hand.txt --output test.json
   ```

3. **Manual calculation:**
   - Read hand history manually
   - Calculate expected allInEV
   - Compare against both .hp value and new snapshot

4. **Decision:**
   - If new value is correct → Update baseline (migrate to JSON)
   - If .hp value is correct → Fix parser bug
   - If unclear → Mark for manual review

---

### Problem: Pytest Snapshot Test Failing

**Symptoms:**
```
AssertionError: Snapshot does not match
```

**Diagnosis:**

```bash
# Re-run with verbose diff
uv run pytest regression-tests/test_snapshots.py -k "failing_test" -vv
```

**Solutions:**

#### Intentional Change (Parser Fix)
```bash
# Update snapshot baseline
uv run pytest regression-tests/test_snapshots.py --snapshot-update
```

#### Regression (Bug Introduced)
```bash
# Review the diff carefully
# Fix the parser
# Re-run tests
```

#### False Positive (Non-deterministic Data)
```bash
# Check if timestamps or IDs are being compared
# Add to exclusion list in compare logic
```

---

### Problem: Database Schema Validation Fails

**Symptoms:**
```
Schema validation error: Missing required field 'heroSeat'
```

**Cause:** Database schema changed, but snapshot serialization not updated

**Fix:**

1. Check database schema:
   ```bash
   grep -A 10 "CREATE TABLE Hands" pyfpdb/SQL.py
   ```

2. Check serialization:
   ```bash
   grep "heroSeat" tools/serialize_hand_for_snapshot.py
   ```

3. Add missing field to serialization:
   ```python
   hand_data["heroSeat"] = hand.heroSeat if hasattr(hand, "heroSeat") else None
   ```

---

### Problem: Site-Specific Format Not Recognized

**Symptoms:**
```
Unable to detect site from hand history
```

**Diagnosis:**

```bash
# Check first few lines
head -5 hand.txt

# Expected formats:
# PokerStars: "PokerStars Hand #..."
# Winamax: "Winamax Poker - ..."
# 888poker: "***** 888poker Hand History for Game..."
```

**Solutions:**

1. **Add site detection pattern:**
   Edit `IdentifySite.py`:
   ```python
   if "NewSite Poker" in firstline:
       return "NewSite"
   ```

2. **Use explicit site flag:**
   ```bash
   uv run python tools/make_snapshot.py hand.txt --site NewSite
   ```

3. **Check for variant:**
   Some sites have multiple formats (XML vs TXT)
   ```bash
   # iPoker uses XML
   file hand.xml  # Should show XML content
   ```

---

### Problem: Migration Script Fails

**Symptoms:**
```
❌ Failed to setup test environment: Database connection error
```

**Solutions:**

1. **Check test config exists:**
   ```bash
   ls -la HUD_config.test.xml
   ```

2. **Create test config if missing:**
   ```bash
   cp HUD_config.xml HUD_config.test.xml
   # Edit to use SQLite test database
   ```

3. **Check database permissions:**
   ```bash
   ls -la ~/.fpdb/
   chmod 755 ~/.fpdb/
   ```

4. **Run with verbose output:**
   ```bash
   uv run python tools/migrate_hp_to_snapshots.py --dry-run -v
   ```

---

## Validation Checklist

### For New Hand History Files

- [ ] **Naming Convention**
  - [ ] Format: `{GAME}-{FORMAT}-{CURRENCY}-{STAKES}-{DATE}.{FEATURE}.txt`
  - [ ] Date is YYYYMM format
  - [ ] Feature describes the edge case (if applicable)

- [ ] **File Placement**
  - [ ] Correct directory: `active-sites/{network}/{year}/{skin}/{game_type}/`
  - [ ] Year matches hand date
  - [ ] Network/skin correctly identified

- [ ] **Level 1: Parsing**
  - [ ] File parses without errors
  - [ ] Site detected correctly
  - [ ] Encoding is UTF-8 or ASCII
  - [ ] All required fields present

- [ ] **Level 2: Invariants**
  - [ ] Money conservation passes (0 violations)
  - [ ] Pot coherence verified
  - [ ] Rake is reasonable (0-50% of pot)
  - [ ] Database schema validation passes

- [ ] **Level 3: Statistics** (if .hp exists)
  - [ ] Compared against legacy data
  - [ ] Differences documented/explained
  - [ ] Critical stats verified manually (VPIP, PFR, winnings)

- [ ] **Documentation**
  - [ ] Snapshot file generated (.snapshot.json)
  - [ ] Metadata includes validation_level
  - [ ] Commit message describes test case
  - [ ] If edge case, documented in comments

- [ ] **Git**
  - [ ] Both .txt and .snapshot.json committed together
  - [ ] Companion files (.hp, .hands, .gt) if legacy test
  - [ ] Tests pass in CI

---

### For Parser Modifications

- [ ] **Pre-Modification**
  - [ ] Created branch for changes
  - [ ] Documented expected behavior change
  - [ ] Identified affected test files

- [ ] **During Development**
  - [ ] Fast iteration with Legacy THP
  - [ ] Error histogram reviewed after each change
  - [ ] Individual hands debugged

- [ ] **Pre-Commit**
  - [ ] Full Legacy THP suite run (all sites with .hp files)
  - [ ] Regression mode snapshot generation
  - [ ] Snapshot comparisons reviewed
  - [ ] New errors investigated and documented

- [ ] **Post-Commit**
  - [ ] CI passes
  - [ ] Pytest snapshots updated (if intentional changes)
  - [ ] Documentation updated (if behavior changed)

---

### For Releases

- [ ] **Test Coverage**
  - [ ] All active sites have recent test cases (2023+)
  - [ ] Common edge cases covered (all-in, side pots, splits)
  - [ ] All game types represented (NLHE, PLO, Stud, Draw)

- [ ] **Validation Status**
  - [ ] All test files pass Level 1 (parsing)
  - [ ] 95%+ pass Level 2 (invariants)
  - [ ] Known Level 3 failures documented

- [ ] **Migration Progress**
  - [ ] Legacy .hp files migrated to JSON (or migration plan exists)
  - [ ] Orphaned companion files cleaned up
  - [ ] Archive directory organized

- [ ] **CI/CD**
  - [ ] pytest suite passes
  - [ ] Coverage metrics meet threshold
  - [ ] Performance benchmarks acceptable

---

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Regression Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v3

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'

    - name: Install UV
      run: curl -LsSf https://astral.sh/uv/install.sh | sh

    - name: Install dependencies
      run: uv pip install .[test]

    - name: Run Level 1 validation (parsing)
      run: |
        find regression-test-files/active-sites -name "*.txt" | while read file; do
          uv run python tools/make_snapshot.py "$file" --verify-only || exit 1
        done

    - name: Run Level 2 validation (invariants)
      run: |
        uv run python tools/make_snapshot.py \
          --directory regression-test-files/active-sites \
          --regression-mode

    - name: Run Level 3 validation (pytest)
      run: |
        uv run pytest regression-tests/test_snapshots.py -v

    - name: Run Legacy THP (PokerStars)
      run: |
        uv run python regression-tests/TestHandsPlayers_legacy.py -s PokerStars

    - name: Upload artifacts on failure
      if: failure()
      uses: actions/upload-artifact@v3
      with:
        name: test-failures
        path: |
          migration-report.json
          test-results/
```

### Pre-Commit Hook Example

Create `.git/hooks/pre-commit`:

```bash
#!/bin/bash

echo "Running validation checks..."

# Get modified .txt files
MODIFIED_TXT=$(git diff --cached --name-only --diff-filter=ACM | grep '\.txt$')

if [ -n "$MODIFIED_TXT" ]; then
    echo "Validating modified hand histories..."

    for file in $MODIFIED_TXT; do
        echo "  Checking $file..."
        uv run python tools/make_snapshot.py "$file" --verify-only

        if [ $? -ne 0 ]; then
            echo "❌ Validation failed for $file"
            exit 1
        fi
    done

    echo "✅ All hand histories validated"
fi

# Run quick pytest
echo "Running pytest quick tests..."
uv run pytest regression-tests/test_snapshots.py -k "quick" -v

if [ $? -ne 0 ]; then
    echo "❌ Quick tests failed"
    exit 1
fi

echo "✅ All checks passed"
exit 0
```

Make executable:
```bash
chmod +x .git/hooks/pre-commit
```

### Makefile Integration

Add to `Makefile`:

```makefile
.PHONY: validate-quick validate-full validate-invariants

validate-quick:
	@echo "Quick validation (parsing only)..."
	@uv run python tools/make_snapshot.py --directory regression-test-files/active-sites --verify-only

validate-invariants:
	@echo "Invariant validation..."
	@uv run python tools/make_snapshot.py --directory regression-test-files/active-sites --regression-mode

validate-full: validate-invariants
	@echo "Full validation (including stats)..."
	@uv run pytest regression-tests/test_snapshots.py -v
	@uv run python regression-tests/TestHandsPlayers_legacy.py -s PokerStars
	@uv run python regression-tests/TestHandsPlayers_legacy.py -s Winamax

validate-single:
	@test -n "$(FILE)" || (echo "Usage: make validate-single FILE=path/to/hand.txt" && exit 1)
	@uv run python tools/make_snapshot.py $(FILE) --verify-only
	@uv run python tools/make_snapshot.py $(FILE) --output /tmp/validation.json
	@cat /tmp/validation.json | jq '._metadata'
```

Usage:
```bash
make validate-quick
make validate-full
make validate-single FILE=regression-test-files/active-sites/pokerstars/2024/stars/cash/hand.txt
```

---

## Quick Reference Card

```
┌────────────────────────────────────────────────────────────────┐
│                    VALIDATION QUICK REFERENCE                   │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  FAST VALIDATION (Seconds)                                     │
│  ├─ Parse check:                                               │
│  │   uv run python tools/make_snapshot.py hand.txt --verify    │
│  └─ Legacy THP:                                                │
│      uv run python regression-tests/TestHandsPlayers_legacy.py │
│                  -s PokerStars -f hand.txt                     │
│                                                                 │
│  THOROUGH VALIDATION (Minutes)                                 │
│  ├─ With invariants:                                           │
│  │   uv run python tools/make_snapshot.py hand.txt             │
│  │                 --output hand.snapshot.json                 │
│  └─ Regression mode:                                           │
│      uv run python tools/make_snapshot.py --directory DIR      │
│                    --regression-mode                           │
│                                                                 │
│  COMPLETE VALIDATION (Hours)                                   │
│  ├─ Pytest suite:                                              │
│  │   uv run pytest regression-tests/test_snapshots.py -v      │
│  └─ All sites legacy:                                          │
│      uv run python regression-tests/TestHandsPlayers_legacy.py │
│                                                                 │
│  MIGRATION                                                      │
│  └─ Legacy to JSON:                                            │
│      uv run python tools/migrate_hp_to_snapshots.py            │
│                    --directory DIR                             │
│                                                                 │
│  COMPARISON                                                     │
│  └─ Two snapshots:                                             │
│      uv run python tools/make_snapshot.py                      │
│                    --compare file1.json file2.json             │
│                                                                 │
└────────────────────────────────────────────────────────────────┘

Decision Tree:

    Need result now? ──YES──▶ Use Legacy THP
           │
          NO
           │
           ▼
    Creating new test? ──YES──▶ Use JSON Snapshots
           │
          NO
           │
           ▼
    Parser debugging? ──YES──▶ Use Legacy THP (fast iteration)
           │                   then JSON (verification)
          NO
           │
           ▼
        Use both!
```

---

## Additional Resources

- **[TESTING.md](TESTING.md)** - Complete testing documentation
- **[COLLECTION_WINAMAX.md](COLLECTION_WINAMAX.md)** - Site-specific collection guide
- **[new-THP.md](new-THP.md)** - Original THP specifications
- **[tools/make_snapshot.py](tools/make_snapshot.py)** - Main snapshot tool
- **[tools/migrate_hp_to_snapshots.py](tools/migrate_hp_to_snapshots.py)** - Migration script
- **[regression-tests/TestHandsPlayers_legacy.py](regression-tests/TestHandsPlayers_legacy.py)** - Legacy THP system

---

**Last Updated:** November 2, 2025
**Maintainer:** FPDB-3 Team
**Version:** 2.0
