#!/usr/bin/env python3
"""Developer CLI for the packaged hand-history anonymizer."""

from fpdb_3_legacy import anonymize_hh as _implementation


def __getattr__(name: str):
    """Keep the historical ``tools.anonymize_hh`` Python API available."""
    return getattr(_implementation, name)


if __name__ == "__main__":
    raise SystemExit(_implementation.main())
