"""Runtime identity of the running fpdb: version, packaging and environment.

A bug report is only actionable when it says *which* build produced it. Until
now the GUI answered that with a modal ``QMessageBox`` holding a licence blurb
and the config path, so users had to be walked through ``python -c`` snippets to
report their PySide6 or SQLite version, and packaged builds -- where no
interpreter is reachable at all -- could not report them even then.

This module collects those facts as plain data so the widget in
``GuiVersionInfo`` only has to render them. Keeping the collection Qt-free is
what makes it testable in the headless suite, and it also lets the checks stay
defensive: every probe here answers with a placeholder instead of raising, since
a version tab that crashes on a missing optional dependency is strictly worse
than one that reports the dependency as unavailable.
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path

__all__ = [
    "DOCUMENTATION_URL",
    "ISSUES_URL",
    "REPOSITORY_URL",
    "UNKNOWN",
    "GitCheckout",
    "VersionReport",
    "collect_report",
    "database_status",
    "detect_packaging",
    "git_checkout",
    "runtime_environment",
]

# Placeholder for any fact this build cannot determine. A single spelling keeps
# the rendered table uniform and gives the tests one value to assert against.
UNKNOWN = "unknown"

REPOSITORY_URL = "https://github.com/jejellyroll-fr/fpdb-3"
ISSUES_URL = "https://github.com/jejellyroll-fr/fpdb-3/issues"
DOCUMENTATION_URL = "https://github.com/jejellyroll-fr/fpdb-3/wiki"

# How long to wait for git. A checkout on a slow or unreachable network mount can
# hang `git describe` indefinitely, and this runs while the user is opening a
# tab: report "unknown" rather than freeze the GUI thread.
_GIT_TIMEOUT_SECONDS = 5


@dataclass(frozen=True)
class GitCheckout:
    """What the source checkout can say about itself, if it is one at all."""

    is_repository: bool
    commit: str = UNKNOWN
    branch: str = UNKNOWN
    dirty: bool = False


@dataclass(frozen=True)
class VersionReport:
    """Everything the Version tab shows, already resolved to display strings."""

    version: str
    packaging: str
    git: GitCheckout
    runtime: dict[str, str] = field(default_factory=dict)
    config_file: str = UNKNOWN
    database: str = UNKNOWN


def detect_packaging() -> str:
    """Name the mechanism that produced the running build.

    PyInstaller and PyOxidizer both set ``sys.frozen`` but are told apart by the
    marker each leaves behind: PyInstaller unpacks to ``sys._MEIPASS``, while
    ``pyoxidizer.bzl`` assigns ``sys.frozen = 'pyoxidizer'`` outright. Anything
    else frozen is reported as such rather than guessed at, and an unfrozen
    process is running from source.
    """
    if not getattr(sys, "frozen", False):
        return "Source"
    if hasattr(sys, "_MEIPASS"):
        return "PyInstaller"
    marker = getattr(sys, "frozen", "")
    if isinstance(marker, str) and marker.lower() == "pyoxidizer":
        return "PyOxidizer"
    if "APPDIR" in os.environ:
        return "AppImage"
    return "Frozen"


def _run_git(args: list[str], cwd: Path) -> str | None:
    """Return stripped stdout of ``git args``, or None when git cannot answer.

    Failures are indistinguishable to the caller on purpose: a missing git, a
    directory that is not a checkout and a repository with no commits all mean
    the same thing here -- there is nothing to display.
    """
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["git", *args],  # noqa: S607 - git is resolved from PATH by design
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=True,
            cwd=cwd,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout.strip() or None


def git_checkout(root: Path | None = None) -> GitCheckout:
    """Describe the checkout fpdb runs from, if any.

    ``root`` defaults to this module's directory so that launching fpdb from
    inside an unrelated repository reports fpdb's own commit, matching how
    ``fpdb.pyw`` anchors its ``git describe``. A frozen build ships no
    repository, so git is not even attempted -- spawning a subprocess that can
    only fail would cost startup time and, on Windows, flash a console window.
    """
    if getattr(sys, "frozen", False):
        return GitCheckout(is_repository=False)

    cwd = root if root is not None else Path(__file__).resolve().parent
    commit = _run_git(["rev-parse", "--short", "HEAD"], cwd)
    if commit is None:
        return GitCheckout(is_repository=False)

    branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd) or UNKNOWN
    # A detached HEAD answers "HEAD", which is not a branch name a reader can
    # use; say so explicitly instead of showing the placeholder.
    if branch == "HEAD":
        branch = "detached HEAD"
    # --porcelain prints one line per modified path and nothing at all on a
    # clean tree, so emptiness is the test. `git describe --dirty` was not used:
    # it ignores untracked files, which is exactly what a user "just editing one
    # file" tends to have.
    dirty = bool(_run_git(["status", "--porcelain"], cwd))
    return GitCheckout(is_repository=True, commit=commit, branch=branch, dirty=dirty)


def _module_version(module_name: str, attribute: str = "__version__") -> str:
    """Report ``module.attribute``, or why it is not available.

    Optional and platform-specific dependencies must not be able to break the
    tab, so an import failure becomes a displayed value rather than a traceback.
    """
    try:
        module = import_module(module_name)
    except Exception:  # noqa: BLE001 - any import problem is "not available" here
        return "not installed"
    value = getattr(module, attribute, None)
    return str(value) if value else UNKNOWN


def _qt_versions() -> dict[str, str]:
    """Both Qt numbers: the PySide6 binding and the Qt runtime underneath it.

    They are reported separately because they drift apart -- a wheel pinning
    PySide6 6.8.1 can still load a different Qt at runtime, and widget bugs
    usually belong to the Qt side.
    """
    try:
        from PySide6 import __version__ as pyside_version
        from PySide6.QtCore import qVersion
    except Exception:  # noqa: BLE001 - a headless/misbuilt install must still render
        return {"PySide6": "not installed", "Qt": "not installed"}
    try:
        qt_runtime = qVersion()
    except Exception:  # noqa: BLE001
        qt_runtime = UNKNOWN
    return {"PySide6": str(pyside_version), "Qt": str(qt_runtime)}


def runtime_environment() -> dict[str, str]:
    """The interpreter, libraries and OS the session is actually running on."""
    import sqlite3

    environment = {
        "Python": platform.python_version(),
        "Python implementation": platform.python_implementation(),
        "Python executable": sys.executable or UNKNOWN,
    }
    environment.update(_qt_versions())
    environment["SQLite"] = sqlite3.sqlite_version
    environment["NumPy"] = _module_version("numpy")
    environment["pandas"] = _module_version("pandas")
    environment["OS"] = f"{platform.system()} {platform.release()}".strip() or UNKNOWN
    environment["Platform"] = platform.platform()
    environment["Architecture"] = platform.machine() or UNKNOWN
    return environment


def database_status(db: object | None) -> str:
    """Summarise the live database connection as "<backend> — <state>".

    Takes the database object rather than reaching for a global so the failure
    modes stay explicit: no object at all (the tab opened before
    ``load_profile``), an object whose backend cannot be named, and a connected
    or disconnected one are four distinct answers, and each is more useful to a
    bug report than a bare "unknown".
    """
    if db is None:
        return "not connected"

    backend = UNKNOWN
    getter = getattr(db, "get_backend_name", None)
    if callable(getter):
        try:
            backend = str(getter())
        except Exception:  # noqa: BLE001 - an unrecognised backend must not break the tab
            backend = UNKNOWN

    connected = getattr(db, "is_connected", None)
    if callable(connected):
        try:
            state = "connected" if connected() else "disconnected"
        except Exception:  # noqa: BLE001
            state = UNKNOWN
    else:
        state = UNKNOWN

    return f"{backend} — {state}"


def collect_report(version: str, config_file: str | None = None, db: object | None = None) -> VersionReport:
    """Assemble the whole report the Version tab renders.

    ``version`` is passed in rather than recomputed: ``fpdb.pyw`` already
    resolves it at import time (``git describe`` in a checkout, the packaged
    version when frozen), and duplicating that logic is how the two displays
    would drift apart.
    """
    return VersionReport(
        version=version,
        packaging=detect_packaging(),
        git=git_checkout(),
        runtime=runtime_environment(),
        config_file=config_file or UNKNOWN,
        database=database_status(db),
    )
