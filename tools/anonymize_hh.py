#!/usr/bin/env python3
"""Developer CLI for the packaged hand-history anonymizer."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fpdb_3_legacy import anonymize_hh as _implementation  # pylint: disable=wrong-import-position
from fpdb_3_legacy.anonymize_hh import anonymize_text  # pylint: disable=wrong-import-position

__all__ = ["anonymize_text"]


def __getattr__(name: str):
    """Keep the historical ``tools.anonymize_hh`` Python API available."""
    return getattr(_implementation, name)


if __name__ == "__main__":
    raise SystemExit(_implementation.main())
