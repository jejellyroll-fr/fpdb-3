"""The startup information dialog must accept both text and message lines."""

from __future__ import annotations

import ast
from pathlib import Path
from types import CodeType, FunctionType, SimpleNamespace

SOURCE = Path(__file__).resolve().parents[1] / "fpdb_3_legacy" / "fpdb.pyw"
TREE = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))


def _load_info_box():
    fpdb_class = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "fpdb")
    method = next(node for node in fpdb_class.body if isinstance(node, ast.FunctionDef) and node.name == "info_box")
    module = ast.Module(body=[method], type_ignores=[])
    ast.fix_missing_locations(module)
    compiled = compile(module, str(SOURCE), "exec")
    code = next(item for item in compiled.co_consts if isinstance(item, CodeType) and item.co_name == "info_box")
    return FunctionType(code, {"QMessageBox": _MessageBox}, "info_box")


class _MessageBox:
    last = None

    def __init__(self, parent):
        self.text = None
        type(self).last = self

    def setWindowTitle(self, title):
        pass

    def setText(self, text):
        self.text = text

    def exec(self):
        return 0


def test_info_box_joins_upgrade_message_lines() -> None:
    dialog = SimpleNamespace()
    info_box = _load_info_box()

    # The method creates its own QMessageBox; capture the instance through the
    # fake class rather than constructing the full Qt application.
    info_box(dialog, "Configuration upgraded", ["Backup saved", "Restart FPDB"])
    assert _MessageBox.last.text == "Backup saved\nRestart FPDB"
