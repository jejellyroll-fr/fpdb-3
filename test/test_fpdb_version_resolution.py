"""The displayed version must never be a stale hardcoded literal.

`fpdb.pyw` used to compute its version with `git describe`, guarded by
`assert not hasattr(sys, "frozen")` and falling back to the literal
"3.0.0alpha". PyOxidizer sets `sys.frozen = 'pyoxidizer'`, so the assert failed
in exactly the builds that ship: every packaged release reported "3.0.0alpha",
including the 3.3.0 binaries.

These tests pin the resolution rules so the shipped builds cannot drift from the
declared version again.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path
from types import CodeType, FunctionType

import pytest

from fpdb_3_legacy import __version__ as PACKAGE_VERSION

SOURCE = Path(__file__).resolve().parents[1] / "fpdb_3_legacy" / "fpdb.pyw"
PYPROJECT = SOURCE.parents[1] / "pyproject.toml"


def test_package_version_matches_project_metadata() -> None:
    metadata = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))

    assert PACKAGE_VERSION == metadata["project"]["version"]


@pytest.fixture(scope="module")
def resolve_version():
    """Load `_resolve_version` from fpdb.pyw without importing the Qt GUI."""
    source = SOURCE.read_text(encoding="utf-8")
    start = source.index("def _resolve_version()")
    end = source.index("VERSION = _resolve_version()")
    # __file__ must be present: _resolve_version anchors git to its own directory,
    # and without it the NameError would be swallowed by the fallback path.
    namespace: dict = {"sys": sys, "PACKAGE_VERSION": PACKAGE_VERSION, "__file__": str(SOURCE)}
    compiled = compile(source[start:end], str(SOURCE), "exec")
    code = next(item for item in compiled.co_consts if isinstance(item, CodeType) and item.co_name == "_resolve_version")
    return FunctionType(code, namespace, "_resolve_version")


def test_the_source_assigns_no_hardcoded_version_literal() -> None:
    """The regression itself: a literal fallback goes stale and ships wrong.

    Matches assignments and returns only — the docstring in `_resolve_version`
    names the old literal on purpose, to explain what went wrong.
    """
    source = SOURCE.read_text(encoding="utf-8")

    assert not re.search(r"(?:VERSION\s*=|return)\s*[\"']\d+\.\d+\.\d+[^\"']*[\"']", source)


def test_a_frozen_build_reports_the_declared_version(resolve_version, monkeypatch) -> None:
    """PyOxidizer sets sys.frozen; that path used to yield the stale literal."""
    monkeypatch.setattr(sys, "frozen", "pyoxidizer", raising=False)

    assert resolve_version() == PACKAGE_VERSION


def test_a_frozen_build_never_shells_out_to_git(resolve_version, monkeypatch) -> None:
    """A packaged build has no repository, so git must not even be attempted."""
    monkeypatch.setattr(sys, "frozen", "pyoxidizer", raising=False)

    def explode(*args, **kwargs):
        message = "git must not run in a frozen build"
        raise AssertionError(message)

    monkeypatch.setattr(subprocess, "run", explode)

    assert resolve_version() == PACKAGE_VERSION


def _git_returning(stdout: str):
    """Stand-in for subprocess.run carrying only the attribute the caller reads."""
    return lambda *args, **kwargs: type("CompletedProcess", (), {"stdout": stdout})()


def test_a_checkout_reports_what_git_describes(resolve_version, monkeypatch) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(subprocess, "run", _git_returning("v3.3.0-2-gabc1234\n"))

    assert resolve_version() == "v3.3.0-2-gabc1234"


def test_a_git_failure_falls_back_to_the_declared_version(resolve_version, monkeypatch) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)

    def fail(*args, **kwargs):
        raise OSError("git not found")

    monkeypatch.setattr(subprocess, "run", fail)

    assert resolve_version() == PACKAGE_VERSION


def test_empty_git_output_falls_back_to_the_declared_version(resolve_version, monkeypatch) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(subprocess, "run", _git_returning("  \n"))

    assert resolve_version() == PACKAGE_VERSION
