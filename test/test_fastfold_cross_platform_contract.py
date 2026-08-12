"""Guard rails for adding a Windows or Linux Fast-Fold HUD.

The Fast-Fold HUD works on macOS today. Windows and Linux are next, and the
shapes of the two most likely regressions are already visible:

1. **A platform-only import escaping into shared code.** The macOS reader
   needs AppKit and ApplicationServices; those modules do not exist on
   Windows or Linux, so importing one at module scope in a file the other
   platforms load turns a missing feature into a HUD that will not start at
   all. The check here is static, over the source, so it fails on the change
   rather than on the platform that cannot run it.

2. **The two readers drifting apart on what a slot means.** Every seat
   reader feeds the same layout: slot 0 is the bottom-centre chair where the
   client draws the hero, and slots count clockwise from there. If a new
   reader numbers them the other way, or from a different origin, nothing
   fails -- every player's statistics simply appear on somebody else's chair,
   which is precisely the bug this HUD has already been through once.

Both are checked here rather than in the per-platform test files, so a new
implementation inherits them by existing rather than by remembering to.
"""

from __future__ import annotations

import ast
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fpdb_3_legacy import winamax_ax_seats as ax
from fpdb_3_legacy.winamax_ax_seats import AXSeat, WinamaxAXSeatReader, seat_slots_from_positions

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Modules that exist only on macOS. Importing one at module scope makes the
#: importing file unloadable everywhere else.
MACOS_ONLY_MODULES = frozenset({"AppKit", "ApplicationServices", "Quartz", "Foundation", "CoreFoundation", "objc"})

#: Modules that exist only on Windows.
WINDOWS_ONLY_MODULES = frozenset({"comtypes", "win32gui", "win32process", "win32api", "win32console", "pywintypes"})

#: Files allowed to import a macOS module at their top level, because nothing
#: but macOS ever loads them. Anything else must import inside a function, so
#: the module stays importable and the failure is confined to the call.
MACOS_MODULE_SCOPE_ALLOWED = frozenset({"fpdb_3_legacy/OSXTables.py"})

#: The Fast-Fold HUD's own files, which every platform will load.
FAST_FOLD_SHARED_SOURCES = (
    "fpdb_3_legacy/fast_fold_engine.py",
    "fpdb_3_legacy/winamax_ax_seats.py",
    "fpdb_3_legacy/winamax_live_log_reader.py",
    "fpdb_3_legacy/winamax_pool_games.py",
    "fpdb_3_legacy/hud_window_registry.py",
    "fpdb_3_legacy/hud_diagnostics.py",
    "fpdb_3_legacy/ui_instrumentation.py",
    "fpdb_3_legacy/HUD_main.pyw",
)


#: What ``platform.system()`` can return for an OS this HUD might support.
KNOWN_PLATFORM_NAMES = frozenset({"Darwin", "Windows", "Linux", "FreeBSD", "Java"})


def _platform_names_in(tree: ast.Module, function: str) -> set[str]:
    """Platform names a function mentions as literals, docstrings excluded."""
    node = next(item for item in ast.walk(tree) if isinstance(item, ast.FunctionDef) and item.name == function)
    return {
        child.value
        for child in ast.walk(node)
        if isinstance(child, ast.Constant) and child.value in KNOWN_PLATFORM_NAMES
    }


def module_scope_imports(path: Path) -> set[str]:
    """Top-level imported root module names, ignoring nested ones.

    An import inside a function or a ``try`` at module scope is deliberate
    optionality; one at the top of the file is a hard requirement.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in tree.body:  # module scope only, by construction
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


# ---------------------------------------------------------------------------
# Platform-only imports must not escape into shared code
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("relative", FAST_FOLD_SHARED_SOURCES)
def test_a_shared_fast_fold_file_imports_no_macos_module_at_load_time(relative) -> None:
    """Every platform loads these; a pyobjc import makes them unloadable.

    Import inside the function that needs it instead -- which is what
    ``winamax_ax_seats`` already does for ApplicationServices and AppKit.
    """
    offenders = module_scope_imports(REPO_ROOT / relative) & MACOS_ONLY_MODULES

    assert not offenders, (
        f"{relative} imports {sorted(offenders)} at module scope. On Windows and Linux the import "
        f"fails and the whole module is unloadable, so the HUD does not start at all. Move it "
        f"inside the function that uses it."
    )


@pytest.mark.parametrize("relative", FAST_FOLD_SHARED_SOURCES)
def test_a_shared_fast_fold_file_imports_no_windows_module_at_load_time(relative) -> None:
    """The same rule in the other direction, before the Windows work starts."""
    offenders = module_scope_imports(REPO_ROOT / relative) & WINDOWS_ONLY_MODULES

    assert not offenders, (
        f"{relative} imports {sorted(offenders)} at module scope, which macOS and Linux cannot load. "
        f"Import it inside the function that uses it."
    )


def test_the_list_of_files_allowed_a_macos_import_stays_short() -> None:
    """Growing it is the regression; each entry is a file macOS alone can load."""
    for relative in MACOS_MODULE_SCOPE_ALLOWED:
        assert (REPO_ROOT / relative).is_file(), f"{relative} no longer exists; drop it from the allow-list"

    # as_posix, not str: on Windows str() renders backslashes and nothing
    # would ever match the allow-list, so the check would pass by accident on
    # the one platform it is most meant to protect.
    actual = {
        path.relative_to(REPO_ROOT).as_posix()
        for path in (REPO_ROOT / "fpdb_3_legacy").glob("*.py")
        if module_scope_imports(path) & MACOS_ONLY_MODULES
    }

    assert actual == set(MACOS_MODULE_SCOPE_ALLOWED), (
        "a file started importing a macOS module at load time. If it really is macOS-only, add it "
        "to MACOS_MODULE_SCOPE_ALLOWED; otherwise move the import inside the function that uses it."
    )


# ---------------------------------------------------------------------------
# Every platform must agree on what a slot is
# ---------------------------------------------------------------------------

#: A 776x606 table with a player in each chair, as the client draws them.
TABLE_CENTRE = (388.0, 303.0)
CHAIRS = {
    "bottom_centre": (350, 520),
    "bottom_left": (60, 470),
    "top_left": (50, 150),
    "top_centre": (350, 90),
    "top_right": (650, 150),
    "bottom_right": (660, 470),
}

#: The one mapping every seat reader on every platform must produce.
EXPECTED_SLOTS = {
    0: "bottom_centre",
    1: "bottom_left",
    2: "top_left",
    3: "top_centre",
    4: "top_right",
    5: "bottom_right",
}


def test_slot_zero_is_the_bottom_centre_chair_and_slots_run_clockwise() -> None:
    """The contract itself, stated once.

    A reader that numbers slots anticlockwise, or from a different chair,
    breaks nothing visibly: it puts every player's statistics on somebody
    else's seat. That has already happened once on macOS, and it took a
    screenshot and a log to find.
    """
    seats = [AXSeat(name, x, y) for name, (x, y) in CHAIRS.items()]

    assert seat_slots_from_positions(seats, TABLE_CENTRE, 6) == EXPECTED_SLOTS


def test_the_macos_reader_produces_the_contract_mapping(monkeypatch) -> None:
    """macOS reaches the shared mapping through the accessibility tree."""
    from .fastfold_ax_doubles import AXElement, FakeAX, installed, text

    monkeypatch.setattr(ax.platform, "system", lambda: "Darwin")
    labels = []
    for name, (x, y) in CHAIRS.items():
        labels.append(text(name, x, y))
        labels.append(text("100 BB", x, y + 20))
    fake = FakeAX()
    fake.app_element = AXElement(
        "AXApplication",
        windows=[AXElement("AXWindow", title="Winamax Bucarest 3", position=(0, 0), size=(776, 606), children=labels)],
    )

    with installed(fake):
        assert WinamaxAXSeatReader().read_window("Winamax Bucarest 3") == EXPECTED_SLOTS


def test_the_windows_reader_produces_the_same_contract_mapping(monkeypatch) -> None:
    """Windows reaches it through UIAutomation, and must land in the same place.

    Same table, same chairs, same answer. If this and the macOS test above
    ever disagree, one platform is seating players on the wrong chairs.
    """
    from .test_winamax_ax_seats_windows import Rect, UIAArray, UIAElement

    monkeypatch.setattr(ax.platform, "system", lambda: "Windows")
    nodes: list[UIAElement] = []
    for name, (x, y) in CHAIRS.items():
        nodes.append(UIAElement(name, Rect(x, y)))
        nodes.append(UIAElement("100 BB", Rect(x, y + 20)))
    window = UIAElement("table", Rect(0, 0, 776, 606))
    window.FindAll = MagicMock(return_value=UIAArray(nodes))

    automation = MagicMock()
    automation.ElementFromHandle.return_value = window
    client = types.ModuleType("comtypes.client")
    client.GetModule = MagicMock(return_value=types.SimpleNamespace(CUIAutomation=object(), TreeScope_Subtree=4))
    client.CreateObject = MagicMock(return_value=automation)
    comtypes = types.ModuleType("comtypes")
    comtypes.client = client
    monkeypatch.setitem(sys.modules, "comtypes", comtypes)
    monkeypatch.setitem(sys.modules, "comtypes.client", client)

    assert WinamaxAXSeatReader()._read_window_windows(61825) == EXPECTED_SLOTS


def test_both_readers_share_one_slot_implementation() -> None:
    """Two copies of this arithmetic would drift; there must be one.

    Checked in the source because the drift is what matters, not today's
    agreement: a second implementation added for a new platform would pass
    the two tests above on the day it was written and diverge later.
    """
    source = (REPO_ROOT / "fpdb_3_legacy" / "winamax_ax_seats.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    definitions = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and "slot" in node.name and "position" in node.name
    ]
    calls = sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "seat_slots_from_positions"
    )

    assert definitions == ["seat_slots_from_positions"], "there must be exactly one slot mapping"
    assert calls >= 2, "each platform's reader must go through the shared mapping"


def test_both_readers_share_one_player_recogniser() -> None:
    """A name is a label with a stack under it, decided once for all platforms."""
    source = (REPO_ROOT / "fpdb_3_legacy" / "winamax_ax_seats.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    calls = sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "seats_from_labels"
    )

    assert calls >= 2, "each platform's reader must go through the shared recogniser"


# ---------------------------------------------------------------------------
# The entry points must answer on every platform, supported or not
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("system", ["Darwin", "Windows", "Linux", "FreeBSD"])
def test_no_entry_point_raises_on_any_platform(monkeypatch, system) -> None:
    """An unsupported platform means no HUD, never a crash on the GUI thread.

    A new platform that is added to ``is_supported`` before its reader exists
    must degrade to "no seats", which this pins for every entry point at once.
    """
    monkeypatch.setattr(ax.platform, "system", lambda: system)
    for name in (*MACOS_ONLY_MODULES, *WINDOWS_ONLY_MODULES):
        monkeypatch.setitem(sys.modules, name, None)
    reader = WinamaxAXSeatReader(table_detector=MagicMock(find_tables=MagicMock(return_value=[])))

    assert isinstance(ax.is_supported(), bool)
    assert isinstance(ax.is_ax_available(), bool)
    assert reader.find_table_window("3") is None
    assert reader.read_window("Winamax Bucarest 3") == {}


@pytest.mark.parametrize("system", ["Darwin", "Windows", "Linux", "FreeBSD"])
def test_reading_seats_always_answers_with_a_slot_mapping(monkeypatch, system) -> None:
    """Callers index the result; None would be an AttributeError per hand."""
    monkeypatch.setattr(ax.platform, "system", lambda: system)
    for name in (*MACOS_ONLY_MODULES, *WINDOWS_ONLY_MODULES):
        monkeypatch.setitem(sys.modules, name, None)

    result = WinamaxAXSeatReader(table_detector=MagicMock()).read_window("Winamax Bucarest 3")

    assert isinstance(result, dict)


def test_a_platform_that_can_resolve_windows_is_declared_supported() -> None:
    """``is_supported`` and the dispatch in ``find_table_window`` are one decision.

    Adding a platform to one without the other is the failure this catches:
    declared supported with no branch means the macOS path is taken.
    """
    source = (REPO_ROOT / "fpdb_3_legacy" / "winamax_ax_seats.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    declared = _platform_names_in(tree, "is_supported")
    dispatched = _platform_names_in(tree, "find_table_window")

    assert declared, "is_supported no longer names any platform"
    assert declared <= dispatched, (
        f"{sorted(declared - dispatched)} is declared supported but has no branch in find_table_window, "
        f"so it silently takes another platform's path"
    )


# ---------------------------------------------------------------------------
# The HUD looks at its own windows, not at the process's
# ---------------------------------------------------------------------------


def test_the_hud_never_walks_every_window_in_the_process() -> None:
    """``QApplication.topLevelWidgets()`` is not the HUD's to walk.

    Three attempts at a process-wide overlay scanner each broke something
    new, and none of them found a bug:

      * it destroyed widgets it did not own, and one HudMain's timer tore
        down another's in the test suite;
      * it reported the HUD that had just been killed as a leak, because Qt
        keeps a closed window listed until it processes the deferred delete;
      * it segfaulted on a Linux runner, iterating the list while Qt was
        freeing widgets during teardown.

    The question it was built to answer -- does fpdb own more overlays than
    it thinks -- is settled structurally by
    ``AuxSeats._discard_previous_windows``. The question it accidentally
    answered -- who else is drawing on the table -- belongs to
    ``tools/find_hud_windows.py``, which asks the window server and so can
    see other applications, which no in-process scan ever could.

    A HUD reasons about ``hud_dict`` and the aux windows hanging off it.
    """
    source = (REPO_ROOT / "fpdb_3_legacy" / "HUD_main.pyw").read_text(encoding="utf-8")
    tree = ast.parse(source)

    offenders = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "topLevelWidgets"
    ]

    assert not offenders, (
        f"HUD_main walks every window in the process at line(s) {offenders}. Widgets it does not "
        f"own may be mid-destruction, and touching them has segfaulted. To find out who else is "
        f"drawing on a table, use tools/find_hud_windows.py."
    )
