"""AST guard: recently modernized GUI packages must not ship hardcoded UI strings.

Every user-visible string in the directories listed in ``GUARDED_DIRS`` has to go
through ``fpdb_3_legacy.i18n.gettext`` so it can be extracted into the POT file.
"""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Packages already cleaned up for i18n. Extend this list as more modules are done.
GUARDED_DIRS = [
    "fpdb_3_legacy/ring_stats",
    "fpdb_3_legacy/modern_hud_preferences",
]

FORBIDDEN_METHODS = {"setText", "setWindowTitle", "addTab", "setToolTip", "setPlaceholderText"}
FORBIDDEN_CLASSES = {"QLabel", "QPushButton", "QCheckBox"}


class I18nGuardVisitor(ast.NodeVisitor):
    """Collects calls that pass a literal, alphabetic string to a UI setter."""

    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.violations: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802 - ast API
        func_name = None

        # Method calls: obj.setText("string")
        if isinstance(node.func, ast.Attribute) and node.func.attr in FORBIDDEN_METHODS:
            func_name = node.func.attr
        # Class instantiations: QLabel("string")
        elif isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CLASSES:
            func_name = node.func.id

        if func_name:
            for arg in node.args:
                # Strings wrapped in _() are ast.Call nodes, so only bare literals land here.
                # Purely numeric or punctuation labels are allowed.
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and any(c.isalpha() for c in arg.value):
                    self.violations.append(
                        f"{self.filename}:{node.lineno} - {func_name} called with hardcoded string: {arg.value!r}",
                    )

        self.generic_visit(node)


def _collect_violations(directory: Path) -> list[str]:
    violations: list[str] = []
    for path in sorted(directory.rglob("*.py")):
        relpath = path.relative_to(PROJECT_ROOT).as_posix()
        visitor = I18nGuardVisitor(relpath)
        visitor.visit(ast.parse(path.read_text(encoding="utf-8"), filename=relpath))
        violations.extend(visitor.violations)
    return violations


def test_guarded_dirs_exist() -> None:
    """Guard against the guard silently passing because a path was renamed."""
    for guarded in GUARDED_DIRS:
        assert (PROJECT_ROOT / guarded).is_dir(), f"guarded directory {guarded} no longer exists"


def test_no_hardcoded_ui_strings() -> None:
    violations: list[str] = []
    for guarded in GUARDED_DIRS:
        violations.extend(_collect_violations(PROJECT_ROOT / guarded))

    assert not violations, "Hardcoded UI strings found (wrap them in _()):\n" + "\n".join(violations)
