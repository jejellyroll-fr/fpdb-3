#!/usr/bin/env python3
"""Regenerate the translation template ``locale/fpdb.pot`` from the source.

Extracts every string marked with ``_()`` or ``N_()`` across ``fpdb_3_legacy``
into a fresh POT template that translators merge into the per-language .po files
(``msgmerge``). The template is a build artifact (git-ignored), like the .mo.

Requires GNU ``xgettext`` (``brew install gettext`` / ``apt install gettext``).

Usage:
    python tools/update_pot.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "fpdb_3_legacy"
POT = ROOT / "locale" / "fpdb.pot"


def main() -> int:
    xgettext = shutil.which("xgettext")
    if not xgettext:
        print("xgettext not found; install GNU gettext (brew install gettext).", file=sys.stderr)
        return 1

    # Recursive: subpackages such as ring_stats/ and modern_hud_preferences/
    # hold user-visible strings too.
    files = sorted(str(p) for p in [*SRC.rglob("*.py"), *SRC.rglob("*.pyw")])
    cmd = [
        xgettext,
        "--language=Python",
        "--keyword=_",
        "--keyword=N_",
        "--from-code=UTF-8",
        "--package-name=fpdb",
        "--sort-by-file",
        f"--output={POT}",
        *files,
    ]
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)  # noqa: S603
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        return result.returncode

    count = POT.read_text(encoding="utf-8").count("\nmsgid ") if POT.exists() else 0
    print(f"Wrote {POT.relative_to(ROOT)} ({count} messages).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
