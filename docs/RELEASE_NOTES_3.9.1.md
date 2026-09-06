# FPDB 3.9.1

## Configuration and upgrade safety

- Migrate stale HUD configurations while preserving user-defined profiles and
  creating an atomic backup before writing the migrated file.
- Synchronize fallback HUD and PLO profiles with the current templates.
- Report unresolved HUD references with actionable diagnostics instead of
  silently dropping them.
- Keep the configuration schema marker, runtime version and package metadata in
  sync at `3.9.1`.

## HUD reliability

- Preserve a table's HUD when its configuration has aged without replacing a
  valid live configuration.
- Clean up only the claim made by the current attempt when HUD ownership is
  released.
- Isolate HUD imports in tests and cover stale auxiliary configuration paths.

## Stud Hi/Lo and PokerStars parsing

- Preserve PokerStars header casing and parse spaced Stud Hi/Lo stakes.
- Preserve showdown results and distinguish equivalent high and low winners in
  the replayer.
- Render the exact winning low hand, skip ambiguous cards, and avoid double
  counting uncalled bets or uncontested pots.

## Validation and packaging

- Add migration fixtures and version checks to CI, including UTF-8 fixture
  handling and the Windows test path.
- Keep release metadata aligned across the Python package, Briefcase and the
  runtime version exposed by the application.
