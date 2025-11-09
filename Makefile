.PHONY: test test-all test-gui test-main install-deps lint format help

help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'

install-deps: ## Install all dependencies including test dependencies
	uv pip install .[test]

test: ## Run main test suite (excludes GUI tests)
	uv run pytest

test-all: ## Run all tests including GUI tests (using unified script)
	./run_tests.sh

test-gui: ## Run only GUI tests
	uv run pytest test/test_HUD_main.py -v

test-main: ## Run only non-GUI tests with coverage
	uv run pytest --cov=. --cov-report=html

test-stats: ## Run only stats-related tests
	uv run pytest -k "stats"

test-specific: ## Run specific test file (usage: make test-specific FILE=test_file.py)
	uv run pytest test/$(FILE) -v

lint: ## Run linting checks
	uv run ruff check .

format: ## Format code with ruff
	uv run ruff format .

format-check: ## Check code formatting without making changes
	uv run ruff format --check .

clean: ## Clean up generated files
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf .pytest_cache/
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# Development workflow commands
dev-setup: install-deps ## Set up development environment
	@echo "Development environment ready!"
	@echo "Run 'make test' to run tests"
	@echo "Run 'make lint' to check code style"

ci-test: test-all ## Run CI-style tests (same as GitHub Actions)

# Quick commands
quick-test: ## Run tests without coverage (faster)
	uv run pytest --tb=short

debug-test: ## Run tests with verbose output and no capture
	uv run pytest -v -s --tb=long
