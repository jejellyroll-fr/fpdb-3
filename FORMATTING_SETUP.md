# Global Formatting and Ruff Configuration Setup

This document describes the formatting configuration implemented to maintain consistent code quality across all development environments.

## Objectives

- Prevent noisy diffs (trailing whitespace, mixed EOL)
- Maintain baseline quality (Ruff lint + import sorting) without style wars
- Don't slow down priority work
- Provide simple path for future automatic formatting migration

## Configuration Files

### .editorconfig
Universal configuration for all editors (VS Code, PyCharm, Vim, etc.):
- UTF-8 encoding
- LF (Unix) line endings
- 4-space indentation
- 120 character line length
- Automatic trailing whitespace removal

### pyproject.toml - Ruff Section
Ruff configuration with **essential checks only**:
- **E/W**: pycodestyle (errors and warnings)
- **F**: pyflakes (undefined names, unused variables)
- **I**: isort (import sorting)
- **UP**: pyupgrade (Python syntax modernization)

```toml
[tool.ruff]
extend-include = ["*.pyw"]
extend-exclude = ["build", "archives", "documentations/notebook"]
line-length = 120
indent-width = 4

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "W"]
ignore = [
    "E401",  # Multiple imports on one line - sometimes necessary for legacy code
    "E731",  # Assign lambda - common pattern in callbacks
    "E713",  # Use 'not in' - can be stylistic choice
]
```

### .pre-commit-config.yaml
Automatic cleanup before each commit:
- Trailing whitespace removal
- End-of-file newline insertion
- Line ending normalization (LF)
- Ruff linting with automatic fixes
- Ruff formatting

### .vscode/settings.json (optional)
VS Code configuration for optimized experience:
- Automatic trailing whitespace removal
- Automatic final newline insertion
- Visual ruler at 120 characters
- Enhanced Python auto-completion

## Installation

### 1. Install Dependencies

```bash
# Install pre-commit with uv
uv add --dev pre-commit

# Install pre-commit hooks
uv run pre-commit install
```

### 2. Initial Run

```bash
# Clean all existing files
uv run pre-commit run --all-files

# Check Ruff status
uv run ruff check --statistics
```

## Daily Usage

### For Developers

Fixes happen automatically on each commit thanks to pre-commit hooks. No manual action required.

### Useful Commands

```bash
# Check code without fixing
uv run ruff check

# Automatically fix what can be fixed
uv run ruff check --fix

# Format code
uv run ruff format

# Run all pre-commit hooks
uv run pre-commit run --all-files

# Bypass hooks (emergency only)
git commit --no-verify -m "message"
```

### Update Hooks

```bash
uv run pre-commit autoupdate
```

## Editor Configuration

Most modern editors support .editorconfig automatically. For VS Code, the configuration in .vscode/settings.json adds additional features.

### Other Editors

- **PyCharm**: Native .editorconfig support
- **Vim/Neovim**: editorconfig-vim plugin
- **Emacs**: editorconfig package
- **Sublime Text**: EditorConfig package

## Future Migration

This configuration prepares for migration to more automated formatting:

- Solid foundation with Ruff already configured
- Ability to add `ruff format` across entire repo in single pass
- Easy extension to other Ruff rules (add to `select`)

## Troubleshooting

### Pre-commit Not Working

```bash
# Reinstall hooks
uv run pre-commit clean
uv run pre-commit install
```

### Ruff Reports Too Many Errors

Rules are intentionally minimal but some errors may persist:

- **E501 (line-too-long)**: Ignored in pre-commit but visible in manual checks
- **F841 (unused-variable)**: Often in test files or legacy code
- **E722 (bare-except)**: Legacy error handling patterns
- **UP031/UP038**: Python modernization suggestions

To temporarily ignore specific errors:

```python
# ruff: noqa: E501  # Ignore line too long
# ruff: noqa: F841  # Ignore unused variable
```

### Conflict with Existing Formatting

Configuration respects existing code. Only automatic modifications:

- Trailing whitespace
- Missing newlines
- Import sorting
- Safe Ruff fixes only
