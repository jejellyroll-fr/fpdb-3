# FPDB 3.7.0

Released 13 August 2026.

## FastHUD reliability

The fast-fold HUD lifecycle is now guarded end to end:

- one renderer owns a table at a time;
- duplicate HUD processes and windows are refused through cross-platform
  interlocks;
- stale or unowned overlays are removed instead of remaining on screen;
- seat rotation and first-hand statistics are deterministic;
- diagnostics identify the process that currently owns the HUD lock.

The macOS and Windows paths are exercised by deterministic replay and platform
contract tests. CI holds the FastHUD modules at 100% statement and branch
coverage.

## Packaging and upgrade notes

- The package, Briefcase metadata and runtime version are all `3.7.0`.
- macOS is distributed through the PyOxidizer bundle. With the optional
  Developer ID and notarization secrets configured, release builds are stable
  and notarized. Without them, the workflow publishes an explicitly ad-hoc
  fallback; follow [the macOS Gatekeeper guide](macos-gatekeeper.md) before
  granting permissions.
- Windows uses the PyInstaller directory distribution. PyOxidizer is not a
  supported Windows build path.
- The native `pypoker-eval` backend remains pinned to `v1.2.0` and is included
  in the source dependency set and platform build pipeline.

## Validation

The release CI runs the parser regression corpus, the FastHUD platform
contracts on all three operating-system runners, Qt regressions where
available, native equity tests on Python 3.13, database integration tests, and
the SwC interposer compilation on Linux, macOS and Windows.
