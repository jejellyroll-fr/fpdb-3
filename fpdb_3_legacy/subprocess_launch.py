#!/usr/bin/env python3
"""Build argv for the helper processes fpdb spawns (HUD, live capture).

A source install can simply run ``sys.executable -m some.module``. Frozen
builds cannot: ``sys.executable`` is the fpdb launcher itself, so ``-m`` reaches
fpdb's own option parser and the child dies with ``no such option: -m``. Frozen
launchers instead accept a ``--run-module`` escape hatch, dispatched by
:func:`dispatch_run_module` before the GUI is imported.
"""

from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

RUN_MODULE_FLAG = "--run-module"
HUD_FLAG = "--hud"


def python_module_command(module: str, *args: str, unbuffered: bool = True) -> list[str]:
    """Return the argv that runs ``module`` as ``__main__`` in this install.

    ``unbuffered`` keeps a child's stdout unbuffered so progress shows up
    immediately in a log the GUI tails; frozen launchers are always unbuffered
    through :func:`dispatch_run_module`.
    """
    if getattr(sys, "frozen", False):
        return [sys.executable, RUN_MODULE_FLAG, module, *args]
    interpreter = [sys.executable, "-u"] if unbuffered else [sys.executable]
    return [*interpreter, "-m", module, *args]


def hud_main_command(*args: str) -> list[str]:
    """Return the argv that starts HUD_main, whatever the install method.

    Raises:
        FileNotFoundError: when a packaged build has no HUD_main next to it.
    """
    frozen = getattr(sys, "frozen", False)
    if frozen == "pyoxidizer" or (frozen and sys.platform == "darwin"):
        # macOS must keep the GUI and HUD under one code identity so TCC grants
        # (Screen Recording and Accessibility) apply to both processes.
        # PyOxidizer always uses one launcher; the PyInstaller main executable
        # embeds the same --hud dispatcher on macOS.
        return [sys.executable, HUD_FLAG, *args]
    if frozen:
        # PyInstaller ships HUD_main as a sibling executable of fpdb.
        name = "HUD_main.exe" if os.name == "nt" else "HUD_main"
        executable = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), name)
        if not os.path.isfile(executable):
            msg = f"HUD_main not found at {executable}"
            raise FileNotFoundError(msg)
        return [executable, *args]
    hud_main = Path(__file__).resolve().parent / "HUD_main.pyw"
    if not hud_main.is_file():
        msg = f"HUD_main not found at {hud_main}"
        raise FileNotFoundError(msg)
    return [sys.executable, str(hud_main), *args]


def dispatch_run_module(argv: list[str] | None = None) -> bool:
    """Run the module named by ``--run-module`` and report whether it ran.

    Frozen entry points call this before importing anything heavy, so a helper
    process does not drag the GUI stack in. Returns False when the command line
    is a normal launch, leaving argv untouched.
    """
    argv = sys.argv if argv is None else argv
    if len(argv) < 3 or argv[1] != RUN_MODULE_FLAG:
        return False
    module = argv[2]
    sys.argv = [module, *argv[3:]]
    unbuffer_streams()
    runpy.run_module(module, run_name="__main__", alter_sys=True)
    return True


def dispatch_hud_main(argv: list[str] | None = None) -> bool:
    """Run ``HUD_main.pyw`` through the current frozen launcher.

    PyInstaller's macOS bundle must use the same executable for the GUI and HUD
    so macOS applies the app's TCC permissions to both processes. The HUD script
    is already shipped as package data beside this module.
    """
    argv = sys.argv if argv is None else argv
    if len(argv) < 2 or argv[1] != HUD_FLAG:
        return False
    hud_main = Path(__file__).resolve().with_name("HUD_main.pyw")
    if not hud_main.is_file():
        msg = f"HUD_main not found at {hud_main}"
        raise FileNotFoundError(msg)
    sys.argv = [str(hud_main), *argv[2:]]
    unbuffer_streams()
    runpy.run_path(str(hud_main), run_name="__main__")
    return True


def unbuffer_streams() -> None:
    """Make stdout/stderr line buffered, the way ``python -u`` would.

    A helper redirected to a file (the capture log the GUI tails) is otherwise
    block buffered: progress appears minutes late, and whatever is still in the
    buffer is lost when the process is terminated.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(line_buffering=True)  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            # No console at all (windowed build), or an already-closed stream.
            continue
