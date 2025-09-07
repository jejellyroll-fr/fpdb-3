# Contributing to FPDB-3

Thank you for your interest in contributing to FPDB-3! This guide will help you get started with development setup, coding standards, and contribution workflow.

## 🚀 Development Setup

### Prerequisites
- Python 3.10 or higher
- Git
- UV package manager

### Setting Up Development Environment

#### 1. Fork and Clone
```bash
# Fork the repository on GitHub first
git clone https://github.com/YOUR_USERNAME/fpdb-3.git
cd fpdb-3
git remote add upstream https://github.com/jejellyroll-fr/fpdb-3.git
```

#### 2. Environment Setup with UV (Recommended)
```bash
# Install UV if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment (ONE-TIME setup per repository clone)
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install development dependencies (including test dependencies)
uv pip install .[linux][postgresql][test]  # Adjust for your platform
```

**Important Notes about Virtual Environment Lifecycle:**

- **Creating the venv**: `uv venv` is a **one-time operation** per repository clone. You only need to run this once after cloning.

- **Activating the venv**: `source .venv/bin/activate` (or `.venv\Scripts\activate` on Windows) must be run **every time** you open a new terminal session to work on the project.

- **Installing dependencies**: `uv pip install .[linux][postgresql][test]` only needs to be re-run when:
  - The `pyproject.toml` file changes (new dependencies added/updated)
  - You delete and recreate your virtual environment
  - You encounter import errors suggesting missing packages

- **Switching branches**: Generally does **NOT** require reinstalling dependencies unless that specific branch has different dependencies in `pyproject.toml`.

**Platform-specific dependency installation:**

```bash
# For Linux users with postgresql
uv pip install ".[linux,postgresql,test]"

# For Windows users with postgresql
uv pip install .[windows][postgresql][test]

# For macOS users with postgresql
uv pip install ".[macos,postgresql,test]"

# Minimal installation without database support
uv pip install .[test]
```

## 🏗️ Project Architecture

### Core Components
- **Main Application**: `fpdb.pyw` - Main GUI application entry point
- **HUD System**: `HUD_main.pyw`, `Hud.py` - Real-time poker HUD overlay
- **Database Layer**: `Database.py` - Database operations (SQLite/MySQL/PostgreSQL)
- **Configuration**: `Configuration.py` - XML-based configuration management
- **Hand Parsers**: `*ToFpdb.py` - Site-specific hand history parsers
- **Statistics**: `Stats.py` - Poker statistics calculations
- **Web Interface**: `web/` directory - FastAPI-based web interface

### Site Parser Architecture
Each supported poker site has a dedicated parser inheriting from `HandHistoryConverter.py`:
- `PokerStarsToFpdb.py`
- `WinamaxToFpdb.py`
- `BovadaToFpdb.py`
- And 10+ other site parsers

### Testing Structure
- Tests located in `test/` directory
- Uses pytest framework
- Regression test files in `regression-test-files/`
- Test markers: `@pytest.mark.slow`, `@pytest.mark.integration`, `@pytest.mark.manual`

## 🧪 Testing

### Running Tests
```bash
# Run all tests
./run_tests.sh

# Run specific test file
uv run pytest test/test_specific.py -v

# Run tests with coverage
uv run pytest --cov=. --cov-report=html

# Run only fast tests (skip slow/integration tests)
uv run pytest -m "not slow and not integration"
```

### Test Categories
- **Unit Tests**: Fast, isolated component tests
- **Integration Tests**: Multi-component interaction tests (`@pytest.mark.integration`)
- **Slow Tests**: Performance or long-running tests (`@pytest.mark.slow`)
- **Manual Tests**: Tests requiring manual intervention (`@pytest.mark.manual`)

### Adding Tests
- Place tests in appropriate `test/test_*.py` files
- Use descriptive test names: `test_parser_handles_invalid_hand_format`
- Include regression test files when fixing parser issues
- Add appropriate pytest markers for test categorization

## 📋 Code Style and Standards

### Linting and Formatting
```bash
# Run linting (will auto-fix when possible)
uv run ruff check . --fix --unsafe-fixes

# Format code
uv run ruff format .

# Check specific file
uv run ruff check path/to/file.py
```

### Code Standards
- **Line Length**: Maximum 120 characters
- **Type Hints**: Use typing for all function parameters and return values
- **Imports**: Follow ruff import sorting rules
- **Docstrings**: Use Google-style docstrings for public functions
- **Naming**: Use snake_case for functions/variables, PascalCase for classes

### Example Code Style
```python
from typing import Optional, Dict, List
from loggingFpdb import get_logger

log = get_logger("module_name")

def parse_hand_history(content: str, site: str) -> Optional[Dict[str, Any]]:
    """Parse hand history content from specified poker site.

    Args:
        content: Raw hand history text
        site: Poker site identifier

    Returns:
        Parsed hand data or None if parsing fails

    Raises:
        ValueError: If site is not supported
    """
    if not content.strip():
        log.warning("Empty hand history content")
        return None

    # Implementation here
    return parsed_data
```

## 🌟 Development Workflow

### Git Workflow
We follow a Gitflow-inspired structure for better collaboration:

#### Branch Structure

- **Main branch (`main`)**: Contains only stable, production-ready code. Used for releases.
- **Development branch (`development`)**: Main branch for ongoing development. All other branches derive from it and are merged with it.
- **Feature branches (`feature/xxxx`)**: Created from development branch, merged into development once completed.
- **Bugfix branches (`bugfix/xxxx`)**: Created from development to fix non-critical bugs, merged into development.
- **Hotfix branches (`hotfix/xxxx`)**: Created from main to quickly fix critical production bugs, merged into both main and development.
- **Release branches (`release/xxxx`)**: Created from development when a version is ready for release. Enables final tests and adjustments before merging into main.

#### Workflow Steps

1. **Create Feature Branch**
```bash
git checkout development
git pull upstream development
git checkout -b feature/your-feature-name
```

2. **Create Bugfix Branch**
```bash
git checkout development
git pull upstream development
git checkout -b bugfix/issue-description
```

3. **Create Hotfix Branch (Critical Issues)**
```bash
git checkout main
git pull upstream main
git checkout -b hotfix/critical-fix
```

4. **Make Changes**
- Write code following style guidelines
- Add/update tests as needed
- Update documentation if necessary

5. **Test Your Changes**
```bash
# Run tests
./run_tests.sh

# Run linting
uv run ruff check . --fix --unsafe-fixes
uv run ruff format .
```

6. **Commit Changes**
```bash
git add .
git commit -m "feat: add support for new poker site"
```

7. **Push and Create PR**
```bash
# For features and bugfixes (target: development)
git push origin feature/your-feature-name
git push origin bugfix/issue-description

# For hotfixes (target: main, then development)
git push origin hotfix/critical-fix

# Create pull request on GitHub to appropriate target branch
```

### Commit Message Format
- `feat:` - New features
- `fix:` - Bug fixes
- `docs:` - Documentation changes
- `test:` - Adding or updating tests
- `refactor:` - Code refactoring
- `perf:` - Performance improvements
- `chore:` - Maintenance tasks

## 🎯 Common Development Tasks

### Adding Support for New Poker Site

1. **Create Parser Class**
   - Copy existing parser (e.g., `PokerStarsToFpdb.py`)
   - Inherit from `HandHistoryConverter`
   - Implement site-specific parsing logic

2. **Add Test Files**
   - Create `test/test_newsite.py`
   - Add regression test files to `regression-test-files/`

3. **Update Configuration**
   - Add site to supported sites list
   - Update documentation

### Fixing HUD Issues

1. **Identify Component**
   - `HUD_main.pyw` - Main HUD process
   - `Hud.py` - Individual table windows
   - `Aux_*.py` - Auxiliary components

2. **Test Platform-Specific**
   - Linux: Test X11 and Wayland
   - Windows: Test with different DPI settings
   - macOS: Test window positioning

### Database Changes

1. **Schema Updates**
   - Modify `SQL.py` for schema changes
   - Create migration scripts if needed
   - Test with SQLite, MySQL, PostgreSQL

2. **Test Data Integrity**
   - Backup existing databases before testing
   - Test import/export functionality

## 🐛 Debugging

### Logging
```python
from loggingFpdb import get_logger
log = get_logger("your_module")

log.debug("Detailed debug information")
log.info("General information")
log.warning("Warning message")
log.error("Error occurred")
```

### Common Issues
- **HUD not displaying**: Check window detection and permissions
- **Parser errors**: Enable debug logging and check regex patterns
- **Database connection**: Verify connection strings and permissions
- **Import failures**: Check file permissions and formats

## 📝 Documentation

### Code Documentation
- Use Google-style docstrings
- Document complex algorithms and business logic
- Include examples for public APIs

### User Documentation
- Update wiki for user-facing features
- Add platform-specific setup instructions
- Include troubleshooting guides

## 🤝 Pull Request Guidelines

### Before Submitting
- [ ] Tests pass locally
- [ ] Code follows style guidelines
- [ ] Documentation updated if needed
- [ ] Commit messages are clear
- [ ] Branch is up to date with main

### PR Description Template
```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] Added/updated unit tests
- [ ] Manual testing performed
- [ ] Regression tests pass

## Checklist
- [ ] Code follows project style guidelines
- [ ] Self-review of changes completed
- [ ] Documentation updated
```

## 🆘 Getting Help

- **Discussions**: [GitHub Discussions](https://github.com/jejellyroll-fr/fpdb-3/discussions)
- **Issues**: [GitHub Issues](https://github.com/jejellyroll-fr/fpdb-3/issues)
- **Email**: jejellyroll.fr@gmail.com
- **Documentation**: [Sphinx Docs](https://jejellyroll-fr.github.io/fpdb-3/)

## 📄 License

By contributing to FPDB-3, you agree that your contributions will be licensed under the AGPL v3 License.

---

Thank you for contributing to FPDB-3! Your help makes this project better for the entire poker community. 🃏
