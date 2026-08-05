#!/usr/bin/env python3
"""Build the generated resource tree consumed by Briefcase."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fpdb_3_legacy import i18n_compile


def prepare_resources(locale_dir: Path, output_root: Path) -> list[Path]:
    """Compile every PO catalogue into ``output_root/locale`` and return outputs."""
    if output_root.exists():
        shutil.rmtree(output_root)
    outputs: list[Path] = []
    for language in i18n_compile.available_locales(locale_dir):
        messages = i18n_compile.parse_po(locale_dir / f"fpdb-{language}.po")
        destination = output_root / "locale" / language / "LC_MESSAGES" / "fpdb.mo"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(i18n_compile.generate_mo(messages))
        outputs.append(destination)
    return outputs


def main() -> int:
    outputs = prepare_resources(ROOT / "locale", ROOT / ".briefcase-resources")
    expected = len(i18n_compile.available_locales(ROOT / "locale"))
    if len(outputs) != expected or not outputs:
        print(f"Expected {expected} compiled catalogues, produced {len(outputs)}", file=sys.stderr)
        return 1
    print(f"Prepared {len(outputs)} Briefcase translation catalogues")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
