"""Static checks for the explicit GUI-tab database ownership contract."""

import ast
from pathlib import Path

ROOT = Path(__file__).parents[1]
OWNING_TABS = (
    "GuiGraphViewer.py",
    "GuiHandViewer.py",
    "GuiSessionViewer.py",
    "GuiTourneyGraphViewer.py",
    "GuiTourHandViewer.py",
    "GuiOpponentsReport.py",
    "ring_stats/__init__.py",
)


def _methods(path: Path) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    tree = ast.parse(path.read_text())
    return {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_each_owned_tab_exposes_a_disconnect_hook() -> None:
    for relative_path in OWNING_TABS:
        methods = _methods(ROOT / "fpdb_3_legacy" / relative_path)
        hook = methods["close_owned_database"]
        assert any(
            isinstance(node, ast.Attribute) and node.attr == "disconnect"
            for node in ast.walk(hook)
        ), relative_path


def test_hand_viewers_close_detached_replayers_before_disconnect() -> None:
    for relative_path in ("GuiHandViewer.py", "GuiTourHandViewer.py"):
        hook = _methods(ROOT / "fpdb_3_legacy" / relative_path)["close_owned_database"]
        calls = [
            node.func.attr
            for node in ast.walk(hook)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        ]
        assert "close" in calls, relative_path
        assert "disconnect" in calls, relative_path


def test_main_window_calls_the_ownership_hook_before_deleting_a_tab() -> None:
    methods = _methods(ROOT / "fpdb_3_legacy" / "fpdb.pyw")
    close_tab = methods["close_tab"]
    names = [node.attr for node in ast.walk(close_tab) if isinstance(node, ast.Attribute)]
    strings = [node.value for node in ast.walk(close_tab) if isinstance(node, ast.Constant)]
    assert "close_owned_database" in strings
    assert "deleteLater" in names
