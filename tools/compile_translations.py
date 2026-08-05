#!/usr/bin/env python3
"""CLI to compile fpdb's gettext catalogs (locale/fpdb-<lang>.po -> .mo).

Thin wrapper over ``fpdb_3_legacy.i18n_compile``; the same logic runs lazily at
startup, so this is mainly for builds/CI or a manual refresh after editing .po.

Usage:
    python tools/compile_translations.py            # compile every locale
    python tools/compile_translations.py fr_FR es_ES
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fpdb_3_legacy import i18n_compile

LOCALE_DIR = Path(__file__).resolve().parent.parent / "locale"


def main(argv: list[str]) -> int:
    langs = argv or i18n_compile.available_locales(LOCALE_DIR)
    for lang in langs:
        mo_path = i18n_compile.compile_locale(LOCALE_DIR, lang)
        count = len(i18n_compile.parse_po(LOCALE_DIR / f"fpdb-{lang}.po"))
        print(f"{lang}: {count} messages -> {mo_path.relative_to(LOCALE_DIR.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
