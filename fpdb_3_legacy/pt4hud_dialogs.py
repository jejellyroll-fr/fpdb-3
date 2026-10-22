"""What a PT4 HUD import tells the user, and saving it as an ``.fpdbhud`` package (#614).

Both places that import a ``.pt4hud`` -- the Configure menu and HUD
Preferences -- end on the same report: what was translated and every PT4 stat
that was not. *Configure ▸ Convert PT4 HUD to .fpdbhud* saves a layout as a
package that can be shared or re-imported without the PT4 file. Every box here
is a static ``QMessageBox`` call, as elsewhere in the application.
"""

from __future__ import annotations

import os
from typing import Any

from PySide6.QtWidgets import QFileDialog, QMessageBox

from fpdb_3_legacy import pt4hud
from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("pt4hud")

__all__ = [
    "convert_to_package",
    "listed",
    "save_package",
    "show_import_summary",
    "show_package_import",
    "untranslated_lines",
]

# A PT4 formula can run to hundreds of characters; the list shows its start.
_FORMULA_SHOWN = 120
# How many untranslated stats a message names before saying how many more there are.
_LISTED = 25


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


def listed(stats: list[dict[str, str]]) -> str:
    """The untranslated stats as message text, the first few in full."""
    lines = untranslated_lines(stats[:_LISTED])
    if len(stats) > _LISTED:
        lines.append(_("… and %d more") % (len(stats) - _LISTED))
    return "\n".join(lines)


def show_import_summary(parent: Any, summary: dict) -> None:
    """Report an import: what was translated, and every PT4 stat that was not.

    One static ``QMessageBox.information``, like every other report in the
    application, so a modal box never waits on a click nothing can give. Saving
    the result as a package is *Configure ▸ Convert PT4 HUD to .fpdbhud*.
    """
    lines = [
        _("Imported '%s'.") % summary["name"],
        _("%(stats)d stats translated, in %(blocks)d panels.")
        % {"stats": summary["stats"], "blocks": summary.get("blocks", 0)},
    ]
    if summary.get("charts"):
        lines.append(
            _("Range charts %(charts)s are in the popup '%(popup)s'.")
            % {"charts": ", ".join(summary["charts"]), "popup": summary.get("popup") or ""}
        )
    missing = summary.get("untranslated", [])
    if missing:
        lines.append(_("%d PT4 stats have no fpdb equivalent and were left out:") % len(missing))
        lines.append(listed(missing))
    else:
        lines.append(_("Every PT4 stat was translated."))
    lines.append(_("Assign the new HUD profile to a game in HUD Preferences."))
    QMessageBox.information(parent, _("PT4 HUD imported"), "\n".join(lines))


def convert_to_package(parent: Any) -> str | None:
    """Configure ▸ Convert PT4 HUD to .fpdbhud: pick a ``.pt4hud``, then save it as a package."""
    source, _filter = QFileDialog.getOpenFileName(
        parent, _("Convert PT4 HUD to .fpdbhud"), "", _("PT4 HUD layout (*.pt4hud);;All files (*)")
    )
    return save_package(parent, source) if source else None


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
    text = _("HUD profile '%s' successfully imported!") % profile
    missing = pt4hud.package_untranslated(package_root)
    if missing:
        text += "\n\n" + _(
            "This package was converted from PokerTracker 4: %d of its stats have no fpdb equivalent and are not in it:"
        ) % len(missing)
        text += "\n" + listed(missing)
    QMessageBox.information(parent, _("Import Successful"), text)
