#!/usr/bin/env python3
"""Generate the tracked inventory of technical-debt markers."""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = ROOT / "TECHNICAL_DEBT.md"
SCAN_ROOTS = (ROOT / "fpdb", ROOT / "fpdb_3_legacy")
MARKER_RE = re.compile(r"\b(TODO|FIXME|HACK)\b(?P<text>.*)")


@dataclass(frozen=True)
class DebtItem:
    """One source marker represented as a trackable inventory item."""

    identifier: str
    category: str
    marker: str
    path: str
    line: int
    description: str


def _category(path: str) -> str:
    name = Path(path).name
    if name.endswith("ToFpdb.py") or "Summary" in name:
        return "parser"
    if name.startswith("sql_") or name in {"Database.py", "Configuration.py"}:
        return "database"
    if name in {"Hand.py", "DerivedStats.py"}:
        return "poker-domain"
    if name.startswith("Gui") or name in {"Mucked.py"}:
        return "ui"
    return "core"


def collect_items(root: Path, scan_roots: tuple[Path, ...]) -> list[DebtItem]:
    """Collect debt markers from Python sources below *scan_roots*."""
    items: list[DebtItem] = []
    occurrences: dict[tuple[str, str, str], int] = {}
    for scan_root in scan_roots:
        for source in sorted(scan_root.rglob("*.py")):
            relative = source.relative_to(root).as_posix()
            for line_number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
                match = MARKER_RE.search(line)
                if match is None:
                    continue
                marker = match.group(1)
                description = match.group("text").strip(" \t:-@()") or "Description à préciser"
                key = (relative, marker, description)
                occurrences[key] = occurrences.get(key, 0) + 1
                fingerprint = f"{relative}\0{marker}\0{description}\0{occurrences[key]}".encode()
                identifier = f"TD-{hashlib.sha1(fingerprint).hexdigest()[:8].upper()}"
                items.append(
                    DebtItem(
                        identifier=identifier,
                        category=_category(relative),
                        marker=marker,
                        path=relative,
                        line=line_number,
                        description=description,
                    ),
                )
    return sorted(items, key=lambda item: (item.category, item.path, item.line))


def render_inventory(items: list[DebtItem]) -> str:
    """Render a deterministic Markdown register."""
    identifiers = [item.identifier for item in items]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("technical-debt identifiers must be unique")
    category_counts: dict[str, int] = {}
    for item in items:
        category_counts[item.category] = category_counts.get(item.category, 0) + 1

    lines = [
        "# Registre de dette technique",
        "",
        "Ce fichier est généré par `python tools/todo_inventory.py`. Chaque marqueur",
        "`TODO`, `FIXME` ou `HACK` du code possède ainsi un identifiant stable et une",
        "catégorie. Modifier le code source, puis régénérer ce registre.",
        "",
        f"**Total : {len(items)} tâches ouvertes.**",
        "",
        "| Catégorie | Nombre |",
        "|---|---:|",
    ]
    lines.extend(f"| {category} | {count} |" for category, count in sorted(category_counts.items()))
    lines.extend(["", "## Tâches", "", "| ID | Catégorie | Type | Emplacement | Description |", "|---|---|---|---|---|"])
    for item in items:
        description = item.description.replace("|", "\\|").replace("`", "'")
        location = f"[{item.path}:{item.line}]({item.path}#L{item.line})"
        lines.append(
            f"| `{item.identifier}` | {item.category} | {item.marker} | {location} | {description} |",
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Write the inventory, or verify that the tracked copy is current."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail when the tracked inventory is stale")
    args = parser.parse_args(argv)
    rendered = render_inventory(collect_items(ROOT, SCAN_ROOTS))
    if args.check:
        if not DEFAULT_OUTPUT.exists() or DEFAULT_OUTPUT.read_text(encoding="utf-8") != rendered:
            print("TECHNICAL_DEBT.md is stale; run python tools/todo_inventory.py", file=sys.stderr)
            return 1
        print("Technical-debt inventory is current")
        return 0
    DEFAULT_OUTPUT.write_text(rendered, encoding="utf-8")
    print(f"Wrote {DEFAULT_OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
