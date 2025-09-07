# FPDB Command Line Interface Usage

This document describes the command line interfaces available in FPDB after the standardization of `__main__` entrypoints.

## Core Library Files

### Configuration.py
Test and validate FPDB configuration files.

```bash
uv run python Configuration.py [options]
```

**Options:**
- `--validate` : Validate configuration file
- `--show-sites` : Show configured poker sites
- `--show-games` : Show supported games
- `--show-databases` : Show database configurations
- `--show-all` : Show all configuration sections
- `--interactive` : Run original interactive test

### Database.py
Test database connections and display database information.

```bash
uv run python Database.py [options]
```

**Options:**
- `--test-connection` : Test database connection
- `--rebuild-indexes` : Drop and recreate all database indexes
- `--show-stats` : Show statistics for last hand
- `--show-info` : Show database information
- `--interactive` : Run original interactive test

### Stats.py
Calculate and display poker statistics.

```bash
uv run python Stats.py [options]
```

**Options:**
- `--show-stats` : Show available statistics
- `--list-stats` : List all stat functions
- `--validate-stats` : Validate stat calculations
- `--interactive` : Run original interactive test

### SQL.py
Test SQL queries and database operations.

```bash
uv run python SQL.py [options]
```

**Options:**
- `--list-queries` : List all available SQL queries
- `--show-query QUERY_NAME` : Show specific query details
- `--interactive` : Run original interactive test

### Options.py
FPDB command line options parser and utility.

```bash
uv run python Options.py [options]
```

**Standard FPDB Options:**
- `-h, --help` : Show help message and exit
- `-x, --errorsToConsole` : Send error messages to console
- `-d DBNAME, --databaseName DBNAME` : Specifies a database name
- `-c CONFIG, --configFile CONFIG` : Specifies a configuration file path
- `-r, --rerunPython` : Indicates program was restarted with different path
- `-k HHC, --konverter HHC` : Module name for Hand History Converter
- `-s SITENAME, --sitename SITENAME` : A sitename
- `-l {DEBUG,INFO,WARNING,ERROR,CRITICAL,EMPTY}, --logging` : Error logging level
- `-v, --version` : Print version information and exit
- `-i, --initialrun` : Force initial-run dialog
- `-u, --usage` : Print some useful one liners
- `-f FILE, --file FILE` : Input file
- `-D DIR, --directory DIR` : Input directory
- `-o PATH, --outpath PATH` : Out path in quiet mode
- `-a, --archive` : File is a PokerStars or Full Tilt Poker archive file
- `-t, --testdata` : Developer option to print regression test data

**Testing Options:**
- `--test-parsing` : Test FPDB option parsing with legacy OptionParser
- `--test-aliases` : Show poker site aliases
- `--interactive` : Run original interactive test

## Utility Files

### utils/Anonymise.py
Anonymize poker hand history files by replacing player names.

```bash
uv run python utils/Anonymise.py [file_path] [hero_name] [options]
```

**Arguments:**
- `file_path` : Path to hand history file to anonymize
- `hero_name` : Name of hero player (will be replaced with "Hero")

**Options:**
- `--site {Winamax,PokerStars,Bovada,Cake,GGPoker,iPoker,KingsClub,Merge,PacificPoker,PartyPoker,Winning}` : Specify poker site manually
- `--output PATH, -o PATH` : Output file path (default: input_file.anon)
- `--list-sites` : List supported poker sites
- `--dry-run` : Show what would be anonymized without creating output

**Examples:**
```bash
# Anonymize PokerStars hand with auto-detection
uv run python utils/Anonymise.py hand.txt "MyUsername"

# Force PokerStars parser with custom output
uv run python utils/Anonymise.py hand.txt "MyUsername" --site PokerStars -o anon_hand.txt

# List supported sites
uv run python utils/Anonymise.py --list-sites

# Dry run to see what would be changed
uv run python utils/Anonymise.py hand.txt "MyUsername" --dry-run
```

### utils/detect_osx_windows.py
Detect poker client windows on macOS.

```bash
uv run python utils/detect_osx_windows.py [options]
```

**Options:**
- `--list-windows` : List all detected windows
- `--show-poker-windows {Winamax,PokerStars,888,PartyPoker,iPoker}` : Show windows for specific poker room

### utils/win_table_detect.py
Detect poker tables on Windows systems.

```bash
uv run python utils/win_table_detect.py [options]
```

**Options:**
- `--list-windows` : List all detected windows
- `--show-poker-windows {Winamax,PokerStars,888,PartyPoker,iPoker}` : Show windows for specific poker room

### DetectInstalledSites.py
Detect installed poker clients on the system.

```bash
uv run python DetectInstalledSites.py [options]
```

**Options:**
- `--list-detected` : List detected poker sites
- `--show-info SITE` : Show information for specific site
- `--show-paths` : Show detected paths
- `--test-detection` : Test detection functionality
- `--supported-sites` : Show supported sites for detection
- `--interactive` : Run original interactive test

## Testing and Development

### Card.py
Test card encoding/decoding functions.

```bash
uv run python Card.py [options]
```

**Options:**
- `--test-rank` : Test card rank functions
- `--test-encoding` : Test card encoding functions
- `--test-two-cards` : Test two-card functions
- `--test-suits` : Test suit functions
- `--test-razz` : Test Razz-specific functions
- `--demo` : Run card demonstration
- `--interactive` : Run original interactive test

### interlocks.py
Test inter-process locking mechanisms.

```bash
uv run python interlocks.py [options]
```

**Options:**
- `--test` : Test locking functionality
- `--demo` : Run locking demonstration
- `--list-locks` : List active locks
- `--interactive` : Run original interactive test

### HandHistory.py
Test hand history parsing functionality.

```bash
uv run python HandHistory.py
```

Simple test script that attempts to parse "test.xml" file but no really working ... i don't where is this file. No CLI options available.

## GUI Applications

All GUI applications can be run from command line:

### GuiAutoImport.py
Auto-import GUI application.

```bash
uv run python GuiAutoImport.py [options]
```

**Options:**
- `--quiet` : Don't start GUI (creates instance without display, mainly for testing)

### Other GUI Applications
The following GUI applications can be launched directly:

- `uv run python GuiSessionViewer.py` - Session graph viewer
- `uv run python GuiTourneyPlayerStats.py` - Tournament player statistics
- `uv run python GuiTourneyGraphViewer.py` - Tournament graph viewer
- `uv run python GuiTourHandViewer.py` - Tournament hand viewer
- `uv run python GuiRingPlayerStats.py` - Ring game player statistics
- `uv run python GuiReplayer.py` - Hand replayer
- `uv run python GuiHandViewer.py` - Hand viewer
- `uv run python GuiLogView.py` - Log viewer
- `uv run python GuiPrefs.py` - Preferences

## Notes

1. All scripts follow the standardized Python `main(argv=None)` pattern for better testability
2. Most scripts require a valid FPDB configuration file (typically `HUD_config.xml`)
3. Database scripts require proper database setup and connection parameters
4. GUI applications will launch their respective interfaces when run
5. Use `--help` with any script for detailed option information (where available)
6. For hand history anonymization, auto-detection works for most supported sites, but manual site specification may be needed for edge cases

## Configuration

Most CLI tools read configuration from:
- `~/.fpdb/HUD_config.xml` (Linux/macOS)
- `%APPDATA%/fpdb/HUD_config.xml` (Windows)

Or specify custom config with `--config PATH` option where available.
