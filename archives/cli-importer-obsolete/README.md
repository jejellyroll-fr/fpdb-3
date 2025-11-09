# Archive: Obsolete CLI Importer Files

This directory contains files from the standalone CLI importer system that has been replaced by integrated CLI functionality in GuiBulkImport.py.

## Archived Files

- **importer_cli.py** - Standalone CLI importer script
- **CLI_HAND_REPORTING_GUIDE.md** - Documentation for the standalone CLI system  
- **importer_cli.rst** - Sphinx documentation for the CLI module

## Replacement

The CLI functionality has been integrated directly into `GuiBulkImport.py` using Worros' feature/guibulkimport-cli branch.

### New Usage

Instead of:
```bash
uv run python importer_cli.py --site PokerStars --file hand.txt
```

Use:
```bash  
uv run python GuiBulkImport.py -c PokerStars -f hand.txt
```

### Benefits of New System

- Single codebase for GUI and CLI modes
- Consistent behavior between interfaces
- Easier maintenance and development
- Compatible with existing TestHandsPlayers regression tests

## Archive Date

Files archived: January 2025
Reason: Functionality integrated into GuiBulkImport.py