# TODO - AIeV Debugging Workflow (All-In Equity Variance)

## Objective
Implement the complete workflow described by Worros for debugging AIeV issues on PokerStars and other sites.

## Already Done
- [x] Universal serializer with support for all FPDB poker variants (25+ games)
- [x] Basic CLI `tools/make_snapshot.py`
- [x] Direct data from database (no calculations)
- [x] Actions correctly mapped with readable names
- [x] Card support per variant (2-7 cards depending on game)
- [x] Streets adapted by game type (Hold'em, Stud, Draw)
- [x] Debug output cleanup

## TODO

### 1. Missing CLI Extensions

#### 1.1 `--site SITE` option
```bash
# Explicit site support
uv run python tools/make_snapshot.py --site PokerStars -f file.txt
uv run python tools/make_snapshot.py --site Winamax -f file.txt
```

#### 1.2 `-d DIRECTORY` option (batch processing)
```bash
# Test entire directory
uv run python tools/make_snapshot.py --site PokerStars -d regression-test-files/Stars/cash/Flop/
```

#### 1.3 `--printHand OUTPUT.json` option (manual editing)
```bash
# Generate manually editable JSON file
uv run python tools/make_snapshot.py --printHand editable.json -f file.txt
```

#### 1.4 `--compare BEFORE.json AFTER.json` option (regression detection)
```bash
# Compare snapshots to detect regressions
uv run python tools/make_snapshot.py --compare baseline.json current.json
```

#### 1.5 `--gametypes TYPE --type VARIANT` options
```bash
# Filter by game type
uv run python tools/make_snapshot.py --gametypes FLOP --type cash -d directory/
```

### 2. Complete Debugging Workflow

#### 2.1 Initial regression test
- Generate baseline snapshots for all sites
- Store results for comparison

#### 2.2 Editable snapshot generation
- Well-indented JSON format for manual editing
- Comments in JSON to guide editing
- JSON validation after editing

#### 2.3 Iterative testing
- "Watch" mode for automatic regeneration
- Real-time comparison with baseline

#### 2.4 Multi-site validation
- Batch testing on all supported sites
- Regression report per site
- Verify PokerStars fixes don't affect other sites

### 3. Utility Improvements

#### 3.1 Diff reporting
- Visual diff between snapshots
- Highlight modified financial fields
- Export differences in readable format

#### 3.2 Automatic validation
- Verify poker invariants on snapshots
- Alert if totals don't match (pot + rake = winnings)
- Validate card/action consistency

#### 3.3 Documentation
- Debugging workflow usage guide
- Examples for each CLI option
- Snapshot format documentation

## Priorities

### Priority 1 (Essential for Worros workflow)
- [ ] `-d DIRECTORY` option for batch testing
- [ ] `--printHand` option for manual editing
- [ ] `--compare` option for regression detection
- [ ] Multi-site support (`--site`)

### Priority 2 (Workflow improvements)
- [ ] Game type filtering (`--gametypes`, `--type`)
- [ ] Visual diff reporting
- [ ] "Watch" mode for iterative development

### Priority 3 (Polish and documentation)
- [ ] Automatic invariant validation
- [ ] Complete workflow documentation
- [ ] Usage examples

## Current Status
 WIP

## 🎯 Expected Result
Complete workflow allowing to:
1. Debug AIeV issues on PokerStars
2. Manually correct financial data
3. Validate corrections don't break other sites
4. Automated multi-site regression testing