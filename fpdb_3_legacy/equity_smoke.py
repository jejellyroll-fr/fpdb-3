"""Smoke-test the native equity backend in a frozen FPDB build.

Run with ``fpdb --run-module fpdb_3_legacy.equity_smoke``. Keeping this check
inside the packaged application verifies both PyInstaller's module collection
and the native extension's ability to load and evaluate a PLO5 hand.
"""

from __future__ import annotations

from fpdb_3_legacy.equity import calculate_equity, load_poker_eval


def main() -> None:
    backend = load_poker_eval()
    if backend is None:
        msg = "pypoker-eval could not be loaded from the packaged application"
        raise SystemExit(msg)

    result = calculate_equity(
        "omaha",
        [["7s", "As", "Ad", "4h", "Jc"], ["5h", "4d", "7h", "6c", "3h"]],
        ["4s", "5s", "Tc", "Qc", "8c"],
        backend=backend,
    )
    equities = tuple(player.equity for player in result.players)
    if equities != (0, 1):
        msg = f"Unexpected PLO5 smoke-test equities: {equities!r}"
        raise SystemExit(msg)

    print("pypoker-eval packaged backend: PLO5 evaluation passed")


if __name__ == "__main__":
    main()
