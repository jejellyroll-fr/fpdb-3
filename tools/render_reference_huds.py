#!/usr/bin/env python3
"""Render the reference HUDs to PNGs, the same way every time (#370).

A HUD is a picture, and a picture is the one thing a changelog cannot carry.
This renders each shipped package -- and the dynamic package in each of its
contexts -- through the preview pane Preferences uses, so the images in the
docs are the product rather than a mock-up of it, and regenerating them after
a package change is one command:

    QT_QPA_PLATFORM=offscreen .venv/bin/python tools/render_reference_huds.py

Deterministic on purpose: offscreen, a fixed font size, a fixed window size
and no data from the user's database -- the preview's own fictional values.
Two runs of an unchanged package produce byte-identical files, so a diff in
``docs/images`` means a change in the HUD rather than in the weather.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parent.parent
if str(REPOSITORY) not in sys.path:
    sys.path.insert(0, str(REPOSITORY))

# Offscreen before Qt is imported: a rendering tool must never need a display,
# and must never steal focus on the machine that runs it.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

DEFAULT_OUTPUT = REPOSITORY / "docs" / "images" / "reference-huds"

#: The contexts worth a picture of their own: one per pot shape and per side,
#: rather than all nineteen, because a document nobody scrolls to the end of
#: has not shown anything.
FEATURED_CONTEXTS: tuple[str, ...] = (
    "preflop_facing_open",
    "preflop_facing_three_bet",
    "blinds_defence",
    "srp_cbet_ip",
    "srp_face_cbet_oop",
    "threebet_pot_oop",
    "fourbet_pot",
    "ssh_stack",
)


def _render(widget, path: Path) -> None:
    """Grab the HUD itself into a PNG, cropped to what a seat would show.

    The pane around it is Preferences furniture; an image of the product is
    the block and nothing else.
    """
    window = getattr(widget, "hud_window", widget)
    window.adjustSize()
    pixmap = window.grab()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not pixmap.save(str(path), "PNG"):
        raise RuntimeError(f"could not write {path}")


def render_all(output: Path) -> list[Path]:
    """Render every reference package and featured context. Returns the files."""
    from PySide6.QtWidgets import QApplication

    from fpdb_3_legacy.modern_hud_preferences.reference_preview import (
        PACKAGE_ORDER,
        ReferenceHudPreview,
    )

    application = QApplication.instance() or QApplication([])
    preview = ReferenceHudPreview()
    preview.resize(1100, 640)
    written: list[Path] = []

    for name, _label in PACKAGE_ORDER:
        preview.select_package(name)
        application.processEvents()
        target = output / f"{name}.png"
        _render(preview.preview, target)
        written.append(target)

    preview.select_package("dynamic")
    for context in FEATURED_CONTEXTS:
        if context not in preview.context_ids:
            continue
        preview.select_context(context)
        application.processEvents()
        target = output / f"dynamic-{context.replace('_', '-')}.png"
        _render(preview.preview, target)
        written.append(target)

    preview.deleteLater()
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="where the PNGs are written (default: docs/images/reference-huds)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="render to a temporary directory and report what would change",
    )
    arguments = parser.parse_args()

    if arguments.check:
        import filecmp
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            fresh = render_all(Path(directory))
            stale = [
                path.name for path in fresh
                if not (arguments.output / path.name).exists()
                or not filecmp.cmp(path, arguments.output / path.name, shallow=False)
            ]
        if stale:
            print("out of date:", ", ".join(sorted(stale)))
            return 1
        print(f"{len(fresh)} screenshots are up to date")
        return 0

    written = render_all(arguments.output)
    for path in written:
        print(path.relative_to(REPOSITORY))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
