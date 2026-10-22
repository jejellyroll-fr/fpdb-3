"""What a PT4 HUD import tells the user, and saving it as an ``.fpdbhud`` package (#614).

Both places that import a ``.pt4hud`` -- the Configure menu and HUD
Preferences -- end on the same report: what was translated, every PT4 stat
that was not, and an offer to save the result as a package that can be shared
or re-imported without the PT4 file.
"""

from __future__ import annotations

import os
from typing import Any

from PySide6.QtWidgets import QFileDialog, QMessageBox

from fpdb_3_legacy import pt4hud
from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("pt4hud")

__all__ = ["save_package", "show_import_summary", "show_package_import", "untranslated_lines"]

# A PT4 formula can run to hundreds of characters; the list shows its start.
_FORMULA_SHOWN = 120


def untranslated_lines(stats: list[dict[str, str]]) -> list[str]:
    """One readable line per untranslated PT4 stat: panel, label, then what PT4 computes."""
    lines = []
    for stat in stats:
        what = stat.get("formula") or stat.get("pt4_name", "")
        if len(what) > _FORMULA_SHOWN:
            what = what[: _FORMULA_SHOWN - 1] + "…"
        label = stat.get("label", "")
        head = f"[{stat.get('section', '')}] {label}".rstrip()
        lines.append(f"{head}: {what}" if label else f"{head} {what}")
    return lines


def show_import_summary(parent: Any, summary: dict, source: str) -> None:
    """Report an import and offer to save it as a package."""
    lines = [
        _("Imported '%s'.") % summary["name"],
        _("%(stats)d stats translated, in %(blocks)d panels.")
        % {
            "stats": summary["stats"],
            "blocks": summary.get("blocks", 0),
        },
    ]
    if summary.get("charts"):
        lines.append(
            _("Range charts %(charts)s are in the popup '%(popup)s'.")
            % {"charts": ", ".join(summary["charts"]), "popup": summary.get("popup") or ""}
        )
    missing = summary.get("untranslated", [])
    if missing:
        lines.append(_("%d PT4 stats have no fpdb equivalent and were left out (see Details).") % len(missing))
    else:
        lines.append(_("Every PT4 stat was translated."))
    lines.append(_("Assign the new HUD profile to a game in HUD Preferences."))

    box = QMessageBox(parent)
    box.setWindowTitle(_("PT4 HUD imported"))
    box.setIcon(QMessageBox.Icon.Information)
    box.setText("\n".join(lines))
    if missing:
        box.setDetailedText("\n".join(untranslated_lines(missing)))
    save = box.addButton(_("Save as .fpdbhud package…"), QMessageBox.ButtonRole.ActionRole)
    box.addButton(QMessageBox.StandardButton.Ok)
    box.exec()
    if box.clickedButton() is save:
        save_package(parent, source, summary["name"])


def save_package(parent: Any, source: str, name: str | None = None) -> str | None:
    """Write ``source`` (a ``.pt4hud``) as an ``.fpdbhud`` package; the path written, or None."""
    suggested = os.path.join(os.path.expanduser("~"), f"{os.path.splitext(os.path.basename(source))[0]}.fpdbhud")
    path, _filter = QFileDialog.getSaveFileName(
        parent, _("Save as .fpdbhud package"), suggested, _("FPDB HUD package (*.fpdbhud)")
    )
    if not path:
        return None
    try:
        xml, summary = pt4hud.to_package(source, name=name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(xml)
    except Exception as exc:  # intentional broad catch: reported to the user, never lost
        log.exception("Saving the PT4 HUD as a package failed")
        QMessageBox.critical(parent, _("Save as .fpdbhud package"), _("Could not save the package:\n%s") % exc)
        return None
    note = [_("Saved %s.") % path]
    if summary["untranslated"]:
        note.append(_("The package lists the %d PT4 stats it leaves out.") % len(summary["untranslated"]))
    if summary["left_out"]:
        note.append(
            _("Not in the package: %s. Import the .pt4hud itself to get the range charts and info popups.")
            % ", ".join(summary["left_out"])
        )
    QMessageBox.information(parent, _("Save as .fpdbhud package"), "\n".join(note))
    return path


def show_package_import(parent: Any, profile: str, package_root: Any) -> None:
    """Confirm a package import, naming the PT4 stats a converted package left out."""
    missing = pt4hud.package_untranslated(package_root)
    text = _("HUD profile '%s' successfully imported!") % profile
    box = QMessageBox(parent)
    box.setWindowTitle(_("Import Successful"))
    box.setIcon(QMessageBox.Icon.Information)
    if missing:
        text += "\n\n" + _(
            "This package was converted from PokerTracker 4: %d of its stats have no fpdb equivalent "
            "and are not in it (see Details)."
        ) % len(missing)
        box.setDetailedText("\n".join(untranslated_lines(missing)))
    box.setText(text)
    box.exec()
