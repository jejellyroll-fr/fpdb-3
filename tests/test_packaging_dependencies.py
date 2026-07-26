"""What the packaged application is given to run with.

briefcase does not read the project's dependencies: it installs the `requires`
list of its own section. The two drift apart silently, and the result only
shows up in the packaged application -- most of these imports sit inside the
function that needs them, so a missing one is a feature that quietly stops
working rather than an application that refuses to start.

This keeps the two lists reconciled, and makes every deliberate difference say
why it is one.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# Stdlib from 3.11, and the project still claims 3.10.
tomllib = pytest.importorskip("tomllib")

ROOT = Path(__file__).resolve().parents[1]

# A runtime dependency briefcase is deliberately not given, and why.
NOT_PACKAGED = {
    # A meta-package pulling in every Objective-C framework binding. The macOS
    # section names the three fpdb actually imports instead, which is smaller.
    "pyobjc": "the macOS section names the individual pyobjc frameworks",
}


def requirement_name(spec: str) -> str:
    """ "beautifulsoup4==4.12.3" -> "beautifulsoup4"."""
    return re.split(r"[<>=!;\s]", spec.strip())[0].lower()


@pytest.fixture(scope="module")
def pyproject() -> dict:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)


@pytest.fixture(scope="module")
def briefcase_app(pyproject) -> dict:
    return pyproject["tool"]["briefcase"]["app"]["fpdb"]


def declared_to_briefcase(app: dict) -> set[str]:
    sections = (app, app.get("macOS", {}), app.get("windows", {}), app.get("linux", {}))
    return {requirement_name(spec) for section in sections for spec in section.get("requires", [])}


def test_every_runtime_dependency_reaches_the_package(pyproject, briefcase_app) -> None:
    wanted = {requirement_name(spec) for spec in pyproject["project"]["dependencies"]}

    missing = wanted - declared_to_briefcase(briefcase_app) - set(NOT_PACKAGED)

    assert missing == set(), (
        f"{sorted(missing)} would be absent from the packaged application. "
        f"Add them to [tool.briefcase.app.fpdb] requires, or to NOT_PACKAGED with the reason."
    )


def test_a_deliberate_omission_is_still_a_real_dependency(pyproject) -> None:
    # An entry left in NOT_PACKAGED after its dependency is gone hides the next
    # real omission behind a name nobody recognises.
    wanted = {requirement_name(spec) for spec in pyproject["project"]["dependencies"]}

    assert set(NOT_PACKAGED) <= wanted


@pytest.mark.parametrize("package", ["beautifulsoup4", "pymysql", "defusedxml"])
def test_a_dependency_imported_at_runtime_is_packaged(briefcase_app, package) -> None:
    # The three that were missing when this test was written.
    assert package in declared_to_briefcase(briefcase_app)


@pytest.mark.parametrize(
    "framework",
    ["pyobjc-framework-Cocoa", "pyobjc-framework-Quartz", "pyobjc-framework-ApplicationServices"],
)
def test_the_macos_frameworks_the_hud_needs_are_packaged(briefcase_app, framework) -> None:
    # Quartz is how the HUD finds a table, and ApplicationServices is how the
    # permission checks answer. Both are imported inside the function that uses
    # them and the ImportError is swallowed into "permission granted", so
    # leaving one out costs a working HUD without any error to go on.
    packaged = {requirement_name(spec) for spec in briefcase_app["macOS"]["requires"]}

    assert framework.lower() in packaged
