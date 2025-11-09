# Contributing Hand Histories to FPDB

This guide explains how to submit **private hand histories (HH)** to improve FPDB while protecting your privacy and that of other players.

## Privacy Rules

### What IS accepted

- **Anonymized hands** (player names replaced)
- **Tournaments/Cash games** from your own play
- **Compressed files** with password protection
- **Complete metadata** (site, stakes, OS, etc.)

### What is NOT accepted

- Real player names (except yours → "Hero")
- Other players' hands without permission
- Uncompressed files
- Hands without context/metadata

## Pre-Submission Checklist

- [ ] **Anonymization**: All usernames → `Hero`, `Player1`, `Player2`, etc.
- [ ] **Compression**: `.7z` or `.zip` archive with password
- [ ] **Metadata**: Site, stakes, period, OS, encoding
- [ ] **Format**: `.txt` or `.xml` depending on site
- [ ] **Size**: < 10 MB per archive (split if necessary)

## Anonymization Process

### Method 1: Using FPDB's Built-in Script (Recommended)

FPDB includes a professional anonymization script at `/utils/Anonymise.py`. This script:

- **Automatically detects** the poker site format
- **Uses site-specific regex** patterns for accurate player detection
- **Preserves hand structure** while replacing names
- **Handles encoding** automatically

#### Usage

```python
#!/usr/bin/env python3
import sys
sys.path.append('/path/to/fpdb-3')
from utils.Anonymise import anonymize_hand_history

# Replace 'YourUsername' with your actual poker username
anonymize_hand_history("path/to/your/hand_history.txt", "YourUsername")
```

#### Command Line Usage

```bash
cd /path/to/fpdb-3
python3 -c "
from utils.Anonymise import anonymize_hand_history
anonymize_hand_history('hand_history.txt', 'YourUsername')
"
```

This creates an anonymized file: `hand_history.txt.anon`

#### Batch Processing

```bash
#!/bin/bash
# anonymize_batch.sh
cd /path/to/fpdb-3

for file in /path/to/hands/*.txt; do
    echo "Processing: $file"
    python3 -c "
from utils.Anonymise import anonymize_hand_history
anonymize_hand_history('$file', 'YourUsername')
"
done
```

### Method 2: Manual Anonymization

If you prefer manual control:

#### Before

```
Seat 1: MyUsername123 ($50.00 in chips)
Seat 2: ProPlayer777 ($100.00 in chips)
Seat 3: WeekendFish ($25.00 in chips)
```

#### After

```
Seat 1: Hero ($50.00 in chips)
Seat 2: Player1 ($100.00 in chips)  
Seat 3: Player2 ($25.00 in chips)
```

#### Python Script

```python
#!/usr/bin/env python3
import re
import os

def manual_anonymize(file_path, your_username):
    """Manually anonymize a hand history file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Extract all unique player names
    player_pattern = r'Seat \d+: ([^\s(]+)'
    players = set(re.findall(player_pattern, content))
    
    # Create replacement mapping
    replacements = {}
    player_counter = 1
    
    for player in players:
        if player == your_username:
            replacements[player] = 'Hero'
        else:
            replacements[player] = f'Player{player_counter}'
            player_counter += 1
    
    # Apply replacements
    for original, anonymous in replacements.items():
        content = content.replace(original, anonymous)
    
    # Save anonymized version
    with open(file_path + '.anon', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"Anonymized: {file_path} → {file_path}.anon")
    print(f"Replaced players: {replacements}")

# Usage
manual_anonymize('hand_history.txt', 'YourUsername')
```

### 3. Secure Compression

#### With 7-Zip

```bash
# Windows
7z a -p"SecurePassword123" hands_anonymous.7z *.anon

# Linux/Mac
7z a -p"SecurePassword123" hands_anonymous.7z *.anon
```

#### With ZIP

```bash
# Linux/Mac
zip -P "SecurePassword123" hands_anonymous.zip *.anon

# Windows PowerShell
Compress-Archive -Path *.anon -DestinationPath hands_anonymous.zip
```

## Metadata Template

Include a `METADATA.txt` file in your archive:

```
=== FPDB Hand History Contribution ===

SITE: PokerStars
PERIOD: 2025-01-01 to 2025-01-31
STAKES: $0.05/$0.10 NLHE, $0.10/$0.25 NLHE
TYPE: Cash Game 6-max
HAND_COUNT: ~500 hands
ENCODING: UTF-8
PLATFORM: Windows 11
CLIENT_VERSION: PokerStars v7.123.456
LANGUAGE: English

SPECIAL_CASES:
- Several hands with Run It Twice
- 2-3 hands with All-in Cash Out
- No PKO/Bounty tournaments

KNOWN_ISSUES:
- No parsing errors detected
- All showdowns present
- No incomplete hands

ANONYMIZATION_METHOD: FPDB utils/Anonymise.py
ORIGINAL_USERNAME: [REDACTED]

CONTACT: (optional)
GitHub: @myusername
Discord: MyUsername#1234
```

## Recommended Submission Structure

```
contribution_2023_stars_nlhe/
├── METADATA.txt
├── cash_nlhe_05_10/
│   ├── session_2023_01_01.txt.anon
│   ├── session_2023_01_02.txt.anon
│   └── ...
├── cash_nlhe_10_25/
│   └── session_2023_01_15.txt.anon
└── tournament/
    └── sng_180_man.txt.anon
```

## 🎯 Particularly Useful Hand Types

### HIGH Priority

- **Run It Twice** (RiT)
- **All-in Cash Out**
- **CAP tables**
- **New variants** (6+ Hold'em, Short Deck)
- **Known parsing bugs**

### MEDIUM Priority

- **Multi-table tournaments** (MTT)
- **Sit & Go** (SNG) various structures
- **Heads-Up** (HU)
- **Pot Limit Omaha** (PLO)

### LOW Priority

- **Standard NLHE cash**
- **Simple micro-stakes**
- **Basic freeroll tournaments**

## Submission Methods

### 1. GitHub Issue (Recommended)

1. Go to <https://github.com/jejellyroll-fr/fpdb-3/issues>
2. Create new issue with label `hand-history-contribution`
3. Upload your archive (< 25 MB)
4. Include password in a **private** comment (@mention a maintainer)

### 2. Email (Large Archives)

- **Email**: [maintainer@fpdb.org] to define(mailto:maintainer@fpdb.org) to define
- **Subject**: `[HH Contribution] Site - Period - Stakes`
- **Password**: In separate email

### 3. Discord/Forum

- **FPDB Discord**: #hand-histories channel
- **2+2 Forum**: Official FPDB thread

## Validation Process

1. **Automatic verification**: Validation scripts
2. **Parse testing**: Import into test FPDB
3. **Invariant checking**: Consistency tests
4. **Anonymization check**: No real usernames
5. **Regression test addition**: If new cases detected

## Urgent Hands / Bug Reports

If you have hands that **break FPDB** (parsing error), follow the expedited procedure:

### Urgent Procedure

1. **GitHub Issue** with labels `bug` + `parsing-error`
2. **Title**: `[URGENT] Parsing Error - Site - Type`
3. **Description**: Exact error + stack trace
4. **Archive**: Problem hand(s) only
5. **Logs**: FPDB log file if available

### Bug Report Format

```markdown
## Parsing Error Report

**Site**: PokerStars  
**Game Type**: NLHE Tournament  
**Error**: IndexError: list index out of range  
**FPDB Version**: 3.x.x  
**OS**: Windows 11 / Python 3.11

### Stack Trace
```

[Paste complete stack trace]

```

### Hand History
Attached archive: `parsing_error_stars_nlhe.7z`  
Password: `fpdb2025`

### Anonymization
Used: FPDB utils/Anonymise.py
Original username: [REDACTED]
```

## Testing Your Contribution

Before submitting, you can test your hands locally:

```bash
# 1. Test anonymization worked
grep -i "yourusername" *.anon
# Should return no results

# 2. Test FPDB can parse them
cd /path/to/fpdb-3
python3 fpdb.pyw
# Import your .anon files and check for errors

# 3. Run regression tests (if you have the setup)
pytest tests/test_thp_param.py -k "your_hands"
```

## Contribution Statistics

Contributors can track the impact of their submissions:

- **Bugs fixed** thanks to your hands
- **New features** added
- **Site support** improved
- **Mentions** in changelog

## Advanced: Creating Test Cases

If you're technically inclined, you can create proper test cases:

```python
# tests/test_my_contribution.py
import pytest
from tests.test_thp_param import test_regression_file

def test_my_pokerstars_rit_hands():
    """Test my PokerStars Run It Twice hands."""
    # Your test implementation
    pass
```

## FAQ

**Q: Are my hands truly anonymous?**
A: Yes, if you follow the procedure. Maintainers only see Hero/Player1/etc.

**Q: Can I contribute hands from unsupported sites?**
A: Absolutely! This is very helpful for adding new site support.

**Q: What's the size limit?**
A: 10 MB per GitHub archive. For larger submissions, use email or split.

**Q: How long until integration?**
A: 1-4 weeks depending on complexity. Urgent bugs: 1-7 days.

**Q: Can I remove my contribution?**
A: Yes, contact maintainers. Your hands will be removed.

**Q: What if the Anonymise.py script doesn't work for my site?**
A: Use manual method and report the issue. We'll update the script.

**Q: Should I include losing hands?**
A: Yes! All hands are valuable, regardless of outcome.

## Troubleshooting

### Anonymise.py Issues

```python
# If you get import errors
import sys
sys.path.append('/path/to/fpdb-3')
sys.path.append('/path/to/fpdb-3/utils')

# If encoding detection fails
# The script handles this automatically, but report if you see issues

# If site isn't detected
# Check that your hand history file is properly formatted
```

### Common Problems

- **"Site not recognized"**: File might be corrupted or unsupported format
- **"No players found"**: Regex might not match your site's format
- **"Encoding error"**: Try different encoding or report the issue

## Acknowledgments

Thanks to all contributors who make FPDB better! Your help is **essential** for supporting new sites and fixing bugs.

**Recent contributors**:

- @user1: 150 PokerStars RiT hands
- @user2: 300 Winamax MTT hands  
- @user3: 888poker Omaha bug fix

---

## Legal Notice

By contributing hand histories:

- You confirm you have the right to share these hands
- You understand they will be used for FPDB development
- You agree to the anonymization of player names
- You retain no ownership over the contributed data

---

*For any questions, please open a GitHub issue or contact us on Discord.*
