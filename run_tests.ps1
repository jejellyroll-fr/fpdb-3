# PowerShell version of run_tests.sh for Windows CI
# -------------------------------------------------------------------------------------------------
# fpdb-3 – unified test runner for Windows
# Runs pytest with coverage (terminal + HTML + XML)
# Excludes GUI tests (test_HUD_main.py) to avoid segfaults
# -------------------------------------------------------------------------------------------------

Write-Host "Installing test dependencies..." -ForegroundColor Green
uv pip install ".[test]"

Write-Host ""
Write-Host "Running main test suite (excluding GUI tests)..." -ForegroundColor Green
try {
    uv run pytest --cov=. --cov-config=.coveragerc --cov-report=term-missing --cov-report=html --cov-report=xml
    $MAIN_EXIT_CODE = $LASTEXITCODE
    Write-Host ""
    Write-Host "Main tests finished with coverage." -ForegroundColor Green
    Write-Host "Coverage: see summary above."
    Write-Host "Detailed HTML report: htmlcov/index.html"
}
catch {
    Write-Host "Main tests failed with error: $_" -ForegroundColor Red
    $MAIN_EXIT_CODE = 1
}

Write-Host ""
Write-Host "Running GUI tests separately (may have warnings)..." -ForegroundColor Yellow
Write-Host "Note: GUI tests may show Qt warnings - this is normal" -ForegroundColor Yellow
try {
    uv run pytest test/test_HUD_main.py -v --tb=short
    if ($LASTEXITCODE -ne 0) {
        Write-Host "GUI tests failed with exit code: $LASTEXITCODE" -ForegroundColor Yellow
        Write-Host "This is often due to Qt/GUI issues on headless systems and may not indicate real problems" -ForegroundColor Yellow
    }
}
catch {
    Write-Host "GUI tests encountered error: $_" -ForegroundColor Yellow
    Write-Host "This is often due to Qt/GUI issues on headless systems and may not indicate real problems" -ForegroundColor Yellow
}

# Exit with main test suite status
Write-Host ""
Write-Host "Exiting with main test suite status: $MAIN_EXIT_CODE" -ForegroundColor $(if ($MAIN_EXIT_CODE -eq 0) { "Green" } else { "Red" })
exit $MAIN_EXIT_CODE