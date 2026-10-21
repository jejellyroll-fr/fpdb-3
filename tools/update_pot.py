#!/usr/bin/env python3
"""Keep the translation template and catalogues in step with the source (#444).

``locale/fpdb.pot`` holds every string marked with ``_()`` or ``N_()`` across
``fpdb_3_legacy``. It is committed, so that a translation platform and
translators can work from it; each ``locale/fpdb-<lang>.po`` is merged against
it with ``msgmerge``.

References carry the file only, not the line: with line numbers, any edit to a
file with a translated string would change the template and every catalogue.

Requires GNU gettext (``brew install gettext`` / ``apt install gettext``).

Usage:
    python tools/update_pot.py            # rewrite locale/fpdb.pot
    python tools/update_pot.py --merge    # ... and merge every .po against it
    python tools/update_pot.py --check    # fail if either is stale; print each language's completion
"""

from __future__ import annotations

import argparse
import ast
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fpdb_3_legacy import i18n_compile  # noqa: E402

SRC = ROOT / "fpdb_3_legacy"
LOCALE = ROOT / "locale"
POT = LOCALE / "fpdb.pot"


def _tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        msg = f"{name} not found; install GNU gettext (brew install gettext / apt install gettext)."
        raise SystemExit(msg)
    return path


def _run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)  # noqa: S603 - gettext tools, fixed arguments
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        raise SystemExit(result.returncode)


def write_pot(pot: Path) -> None:
    # Recursive: subpackages such as ring_stats/ and modern_hud_preferences/
    # hold user-visible strings too.
    files = sorted(str(p.relative_to(ROOT)) for p in [*SRC.rglob("*.py"), *SRC.rglob("*.pyw")])
    _run(
        [
            _tool("xgettext"),
            "--language=Python",
            "--keyword=_",
            "--keyword=N_",
            "--from-code=UTF-8",
            "--package-name=fpdb",
            "--add-location=file",
            "--sort-by-file",
            f"--directory={ROOT}",
            f"--output={pot}",
            *files,
        ]
    )


def merge(po: Path, pot: Path, output: Path) -> None:
    """``msgmerge`` a catalogue against the template; a changed message becomes fuzzy."""
    _run(
        [
            _tool("msgmerge"),
            "--quiet",
            "--add-location=file",
            "--sort-by-file",
            "--previous",
            f"--output-file={output}",
            str(po),
            str(pot),
        ]
    )


def _messages(path: Path) -> list[tuple[str, str, bool]]:
    """What a catalogue says, header aside: compared rather than the text, which
    line wrapping and the header vary with the gettext version."""
    return sorted((entry.msgid, entry.msgstr, entry.fuzzy) for entry in i18n_compile.read_entries(path) if entry.msgid)


def _shown(path: Path) -> str:
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def source_strings() -> set[str]:
    """Every literal passed to ``_()`` or ``N_()`` in the source, read with ``ast``.

    The check compares the template with this rather than with a fresh
    xgettext run: xgettext versions do not extract the same strings (CI's
    gettext 0.21 is not 1.0), and the check must not depend on the runner.
    It is what xgettext 1.0 extracts, string for string.
    """
    strings: set[str] = set()
    for path in sorted([*SRC.rglob("*.py"), *SRC.rglob("*.pyw")]):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in ("_", "N_")
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
                and node.args[0].value
            ):
                strings.add(node.args[0].value)
    return strings


def _template_gap(template: Path) -> list[str]:
    """The strings the source and the committed template disagree on, named."""
    source = source_strings()
    committed = (
        {entry.msgid for entry in i18n_compile.read_entries(template) if entry.msgid} if template.exists() else set()
    )
    return [
        f"{label}: {msgid!r}"
        for label, strings in (
            ("in the source, not the template", source - committed),
            ("in the template, not the source", committed - source),
        )
        for msgid in sorted(strings)
    ]


def catalogues() -> list[Path]:
    return [LOCALE / f"{i18n_compile.DOMAIN}-{lang}.po" for lang in i18n_compile.available_locales(LOCALE)]


def completion_table() -> str:
    lines = ["language  translated  of     %"]
    for po in catalogues():
        translated, total = i18n_compile.completion(po)
        share = translated / total if total else 0.0
        lines.append(f"{po.stem.split('-', 1)[1]:<9} {translated:>10}  {total:<5} {share:6.1%}")
    return "\n".join(lines)


def check() -> int:
    """1 when the template or a catalogue is not what the source and the template give."""
    stale = []
    gap = _template_gap(POT)
    if gap:
        stale.append(_shown(POT))
        print("\n".join(gap[:40]))
    with tempfile.TemporaryDirectory() as tmp:
        for po in catalogues():
            merged = Path(tmp) / po.name
            merge(po, POT, merged)
            if _messages(merged) != _messages(po):
                stale.append(_shown(po))
            i18n_compile.generate_mo(i18n_compile.parse_po(po))  # must compile
    print(completion_table())
    if stale:
        print("\nOut of date (run: python tools/update_pot.py --merge):\n  " + "\n  ".join(stale))
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--merge", action="store_true", help="also merge every .po against the template")
    group.add_argument("--check", action="store_true", help="change nothing; fail if anything is stale")
    args = parser.parse_args(argv)

    if args.check:
        return check()
    write_pot(POT)
    count = sum(1 for entry in i18n_compile.read_entries(POT) if entry.msgid)
    print(f"Wrote {POT.relative_to(ROOT)} ({count} messages).")
    if args.merge:
        for po in catalogues():
            merge(po, POT, po)
        print(completion_table())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
