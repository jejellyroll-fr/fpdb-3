#!/usr/bin/env python3
"""Developer CLI for the packaged hand-history anonymizer."""

from fpdb_3_legacy import anonymize_hh as _implementation
from fpdb_3_legacy.anonymize_hh import anonymize_text

__all__ = ["anonymize_text"]


def __getattr__(name: str):
    """Keep the historical ``tools.anonymize_hh`` Python API available."""
    return getattr(_implementation, name)


if __name__ == "__main__":
    raise SystemExit(_implementation.main())
