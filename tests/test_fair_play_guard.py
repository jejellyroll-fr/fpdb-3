"""What fpdb promises about play stays true of the code (#450).

docs/fair-play.md says two things a test can hold the code to: the solver
review is a manual export the HUD process cannot start, and no fpdb module
sends a click or a keystroke to another program. Both are read from the source,
not by running it: the HUD process is HUD_main.pyw and whatever it imports,
however deep, including imports made inside functions.
"""

from __future__ import annotations

import ast
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEGACY = ROOT / "fpdb_3_legacy"

#: The solver review and the windows that open it: none may load in the HUD.
REVIEW_MODULES = frozenset(
    {
        "hand_review_dialog",
        "hand_review_payload",
        "hand_review_spots",
        "GuiReplayer",
        "GuiHandViewer",
        "GuiTourHandViewer",
        "fpdb",  # the main window, fpdb.pyw, which opens them
    }
)

#: Where a click on "Solver review…" lives: a window the user opened.
REVIEW_OPENERS = frozenset({"GuiReplayer", "GuiHandViewer", "GuiTourHandViewer", "hand_review_dialog"})

#: Libraries and calls that synthesise input for another program.
INPUT_LIBRARIES = frozenset({"pyautogui", "pynput", "keyboard", "mouse", "autoit", "pywinauto"})
INPUT_CALLS = frozenset(
    {
        "SendInput",
        "mouse_event",
        "keybd_event",
        "CGEventPost",
        "CGEventPostToPid",
        "CGEventCreateMouseEvent",
        "CGEventCreateKeyboardEvent",
        "XTestFakeKeyEvent",
        "XTestFakeButtonEvent",
        "XTestFakeMotionEvent",
    }
)


def _legacy_modules() -> dict[str, Path]:
    return {path.stem: path for pattern in ("*.py", "*.pyw") for path in LEGACY.glob(pattern)}


@cache
def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _imported(path: Path, modules: dict[str, Path]) -> set[str]:
    """The legacy modules ``path`` imports, as ``fpdb_3_legacy.X``, ``.X`` or bare ``X``."""
    found: set[str] = set()
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            names = [base, *(f"{base}.{alias.name}" if base else alias.name for alias in node.names)]
        else:
            continue
        for name in names:
            if name.startswith("fpdb_3_legacy"):
                name = name.removeprefix("fpdb_3_legacy").removeprefix(".")
            elif "." in name:
                # Another package (``fpdb.infrastructure...``), not a legacy module.
                continue
            head = name.split(".")[0]
            if head in modules:
                found.add(head)
    return found


def _named_in_strings(path: Path, names: frozenset[str]) -> set[str]:
    """Module names a string spells out, as ``importlib.import_module`` would take them."""
    found: set[str] = set()
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = node.value.removeprefix("fpdb_3_legacy.")
            if text in names:
                found.add(text)
    return found


def _loaded_by(entry: str) -> dict[str, str | None]:
    """Every legacy module ``entry`` loads, with the module that first imported it."""
    modules = _legacy_modules()
    reached: dict[str, str | None] = {entry: None}
    pending = [entry]
    while pending:
        current = pending.pop()
        for name in _imported(modules[current], modules):
            if name not in reached:
                reached[name] = current
                pending.append(name)
    return reached


def _hud_process() -> dict[str, str | None]:
    return _loaded_by("HUD_main")


def _chain(reached: dict[str, str | None], name: str) -> str:
    links = [name]
    while (parent := reached[links[-1]]) is not None:
        links.append(parent)
    return " <- ".join(links)


def test_the_hud_process_cannot_reach_the_solver_review() -> None:
    reached = _hud_process()

    assert len(reached) > 50, "the import graph found too little of the HUD to mean anything"
    leaked = sorted(REVIEW_MODULES & reached.keys())
    assert not leaked, "the HUD process loads " + "; ".join(_chain(reached, name) for name in leaked)


def test_the_main_window_does_reach_it() -> None:
    # Without this, a graph that found nothing would pass the guard above.
    assert "hand_review_payload" in _loaded_by("fpdb")


def test_no_hud_module_loads_the_review_by_name() -> None:
    modules = _legacy_modules()
    by_name = {
        module: sorted(_named_in_strings(modules[module], REVIEW_MODULES - {"fpdb"})) for module in _hud_process()
    }

    assert {module: names for module, names in by_name.items() if names} == {}


def test_the_solver_review_is_opened_only_from_a_window_the_user_opened() -> None:
    modules = _legacy_modules()
    openers = {name for name, path in modules.items() if "hand_review_dialog" in _imported(path, modules)}

    assert openers <= REVIEW_OPENERS


def test_the_import_graph_sees_imports_inside_functions(tmp_path) -> None:
    # The HUD imports much of what it uses lazily; a graph of top-level imports
    # only would pass this guard while missing them.
    source = tmp_path / "probe.py"
    source.write_text(
        "def later():\n    from fpdb_3_legacy import Hud\n    import Configuration\n"
        "from fpdb.infrastructure.platform import permissions\n",
        encoding="utf-8",
    )

    assert _imported(source, _legacy_modules()) == {"Hud", "Configuration"}


def test_no_module_sends_input_to_another_program() -> None:
    sources = [*_legacy_modules().values(), *(ROOT / "fpdb").rglob("*.py")]
    offenders: list[str] = []
    for path in sources:
        for node in ast.walk(_tree(path)):
            if isinstance(node, ast.Import):
                names = {alias.name.split(".")[0] for alias in node.names} & INPUT_LIBRARIES
            elif isinstance(node, ast.ImportFrom) and not node.level:
                names = {(node.module or "").split(".")[0]} & INPUT_LIBRARIES
            elif isinstance(node, ast.Attribute):
                names = {node.attr} & INPUT_CALLS
            elif isinstance(node, ast.Name):
                names = {node.id} & INPUT_CALLS
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                # The X11 command-line way: subprocess.run(["xdotool", "click", ...]).
                names = {"xdotool"} if "xdotool" in node.value else set()
            else:
                continue
            offenders.extend(f"{path.relative_to(ROOT)}:{node.lineno} {name}" for name in names)

    assert offenders == []
