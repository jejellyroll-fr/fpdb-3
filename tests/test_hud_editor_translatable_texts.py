"""Every text the HUD Preferences editor shows goes through ``_()`` (#776, B16).

The scan reads the editor's modules with :mod:`ast` and looks at the string
literals passed to the Qt calls that put text on screen: widget constructors,
text setters, form rows, tab titles, message boxes, input and file dialogs.
A literal there that is not wrapped in ``_()`` stays in English whatever the
interface language, so the suite fails on it.

What the scan leaves alone:

* values that are data rather than wording (stored values listed in
  ``DATA_VALUES``), default file names and default input values;
* f-strings and concatenations whose literal parts carry no word, such as
  ``f"{name}  ⚠"`` or ``f"🔍 {popup}"``.

Every module of the editor is scanned, the Design canvas included (#775).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parent.parent / "fpdb_3_legacy" / "modern_hud_preferences"

#: Stored values shown as they are written in the configuration: HUD
#: positions, popup classes and popup sections, cell alignments, and ``n``,
#: the default sample variable of a dynamic panel rule.
DATA_VALUES = frozenset(
    {
        "",
        "SB",
        "BB",
        "BTN",
        "CO",
        "MP",
        "EP",
        "default",
        "Submenu",
        "Multicol",
        "ModernSubmenu",
        "ModernSubmenuLight",
        "ModernSubmenuClassic",
        "CategorizedPopup",
        "RangeChartPopup",
        "BlockPopup",
        "auto",
        "player_info",
        "preflop",
        "flop",
        "turn",
        "river",
        "steal",
        "aggression",
        "general",
        "center",
        "left",
        "right",
        "n",
    },
)

#: Widgets whose constructor takes the text they show.
TEXT_CONSTRUCTORS = frozenset(
    {
        "QLabel",
        "QPushButton",
        "QCheckBox",
        "QRadioButton",
        "QGroupBox",
        "QAction",
        "QTableWidgetItem",
        "QListWidgetItem",
    },
)

#: Methods every positional argument of which is shown (widgets are never literals).
TEXT_METHODS = frozenset(
    {
        "setText",
        "setTitle",
        "setWindowTitle",
        "setToolTip",
        "setStatusTip",
        "setWhatsThis",
        "setPlaceholderText",
        "setInformativeText",
        "setDetailedText",
        "setSpecialValueText",
        "setPrefix",
        "setSuffix",
        "setLabelText",
        "setTabText",
        "setTabToolTip",
        "addTab",
        "insertTab",
        "addRow",
        "insertRow",
        "addAction",
        "addButton",
        "addMenu",
        "set_summary",
        "showMessage",
    },
)

#: Methods whose first positional argument is shown, the rest being item data.
FIRST_ARGUMENT_METHODS = frozenset({"addItem", "insertItem"})

#: Methods taking a list of shown texts.
LIST_METHODS = frozenset(
    {"addItems", "insertItems", "setHorizontalHeaderLabels", "setVerticalHeaderLabels", "setHeaderLabels"}
)

#: Static dialogs: the positional arguments that are shown (title, prompt,
#: message, file filter); the others are a parent, a start path or a default.
DIALOG_ARGUMENTS: dict[tuple[str, str], frozenset[int]] = {
    **{
        ("QMessageBox", name): frozenset({1, 2}) for name in ("information", "warning", "critical", "question", "about")
    },
    **{
        ("QInputDialog", name): frozenset({1, 2})
        for name in ("getText", "getInt", "getDouble", "getItem", "getMultiLineText")
    },
    **{("QFileDialog", name): frozenset({1, 3}) for name in ("getSaveFileName", "getOpenFileName", "getOpenFileNames")},
    ("QFileDialog", "getExistingDirectory"): frozenset({1}),
    ("QColorDialog", "getColor"): frozenset({2}),
}

TRANSLATORS = frozenset({"_", "N_", "gettext"})


@dataclass(frozen=True)
class Finding:
    file: str
    line: int
    function: str
    call: str
    text: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line} in {self.function or '<module>'}: {self.call}({self.text!r})"


def _has_word(text: str) -> bool:
    return any(ch.isalpha() for ch in text)


def _untranslated(node: ast.AST) -> list[str]:
    """The literal wording in ``node`` that does not go through a translator."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value] if _has_word(node.value) and node.value not in DATA_VALUES else []
    if isinstance(node, ast.JoinedStr):
        literal = "".join(part.value for part in node.values if isinstance(part, ast.Constant))
        return [ast.unparse(node)] if _has_word(literal) else []
    if isinstance(node, ast.BinOp):
        return _untranslated(node.left) + _untranslated(node.right)
    if isinstance(node, ast.IfExp):
        return _untranslated(node.body) + _untranslated(node.orelse)
    if isinstance(node, ast.BoolOp):
        return [text for value in node.values for text in _untranslated(value)]
    # A call is _() itself, or builds its text some other way (str(), join()).
    return []


def _method_arguments(name: str, args: list[ast.expr]) -> list[ast.expr]:
    """The arguments of a call to method ``name`` whose text is shown."""
    if name in TEXT_METHODS:
        return list(args)
    if name in FIRST_ARGUMENT_METHODS:
        return args[:1]
    if name in LIST_METHODS and args and isinstance(args[0], (ast.List, ast.Tuple)):
        return list(args[0].elts)
    return []


def _shown_arguments(call: ast.Call) -> tuple[str, list[ast.expr]]:
    """The callee's name and the arguments of ``call`` whose text is shown."""
    func = call.func
    if isinstance(func, ast.Name):
        return (func.id, list(call.args)) if func.id in TEXT_CONSTRUCTORS else ("", [])
    if not isinstance(func, ast.Attribute):
        return "", []
    name = func.attr
    owner = func.value.id if isinstance(func.value, ast.Name) else ""
    if (owner, name) in DIALOG_ARGUMENTS:
        indexes = DIALOG_ARGUMENTS[(owner, name)]
        return f"{owner}.{name}", [arg for index, arg in enumerate(call.args) if index in indexes]
    arguments = _method_arguments(name, call.args)
    return (name if arguments else ""), arguments


def _qualified_names(tree: ast.AST) -> dict[ast.AST, str]:
    """Each node's enclosing ``Class.function`` (classes and defs only)."""
    names: dict[ast.AST, str] = {}

    def visit(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            inner = prefix
            if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                inner = f"{prefix}.{child.name}" if prefix else child.name
            names[child] = inner
            visit(child, inner)

    visit(tree, "")
    return names


def scan_source(source: str, filename: str) -> list[Finding]:
    """The untranslated texts shown by the calls in ``source``."""
    tree = ast.parse(source, filename=filename)
    names = _qualified_names(tree)
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee, arguments = _shown_arguments(node)
        if not callee:
            continue
        function = names.get(node, "")
        texts = [text for argument in arguments for text in _untranslated(argument)]
        if not texts:
            continue
        findings.extend(Finding(filename, node.lineno, function, callee, text) for text in texts)
    return findings


def _modules() -> list[Path]:
    return sorted(PACKAGE.glob("*.py"))


def test_scope_covers_the_editor_package() -> None:
    names = {path.name for path in _modules()}
    assert {"main_dialog.py", "dialogs.py", "design_canvas.py", "preview_widgets.py", "reference_preview.py"} <= names


@pytest.mark.parametrize("path", _modules(), ids=lambda path: path.name)
def test_no_untranslated_text_in_the_editor(path: Path) -> None:
    findings = scan_source(path.read_text(encoding="utf-8"), path.name)
    assert not findings, "Wrap these texts in _() (use .format() for values):\n" + "\n".join(map(str, findings))


@pytest.mark.parametrize(
    ("snippet", "expected"),
    [
        ('QLabel("Name")', ["Name"]),
        ('box.setTitle(f"Panel {n}")', ["f'Panel {n}'"]),
        ('form.addRow("Rows:", spin)', ["Rows:"]),
        ('QMessageBox.warning(self, "Oops", "It failed: " + str(e))', ["Oops", "It failed: "]),
        ('QInputDialog.getText(self, _("Rename"), "New name:", text=f"{old}_1")', ["New name:"]),
        ('QFileDialog.getSaveFileName(self, _("Export"), "rules.json", "JSON (*.json)")', ["JSON (*.json)"]),
        ('btn.setText(colour or "(none)")', ["(none)"]),
        ('combo.addItem("All", "all")', ["All"]),
        ('combo.addItems(["SB", "BB", "Other seat"])', ["Other seat"]),
        ('table.setHorizontalHeaderLabels(["Name", _("Value")])', ["Name"]),
        ('QLabel(_("Name"))', []),
        ('label.setText(f"{name}  ⚠")', []),
        ('label.setText(_("{n} rows").format(n=n))', []),
        ('label.setStyleSheet("color: red;")', []),
        ('QColorDialog.getColor(initial, self, _("Pick colour"))', []),
    ],
)
def test_the_scan_finds_what_it_should(snippet: str, expected: list[str]) -> None:
    findings = scan_source(f"def f():\n    {snippet}\n", "snippet.py")
    assert [finding.text for finding in findings] == expected
