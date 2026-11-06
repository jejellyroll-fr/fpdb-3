"""What mypy checks is configuration, and it only ever tightens (#454).

CI used to type-check a list of some 280 paths written into the workflow, with
imports skipped: a module nobody listed was never checked, and every call into
another fpdb module was ``Any``. ``pyproject.toml`` now says what is checked --
the whole application, imports followed, a strict tier -- and CI runs a bare
``mypy``. These tests keep it that way:

- the workflow does not grow a file list again;
- every module of a tier-A group is strict, or waits in ``STRICT_PENDING``;
- no module is excused from checking unless it is in ``IGNORE_BASELINE``.

Both lists may only shrink: adding to either means editing this file, in the
same review that explains why.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEGACY = ROOT / "fpdb_3_legacy"
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"

#: The groups #454 holds to full annotations: modern modules with no Qt in them.
TIER_A_GROUP = re.compile(
    r"^(stats_|database_|analytics_|research_)"
    r"|^(stat_registry|stat_packs|hand_review_payload|hand_share|phh_import|dialects)$"
)

#: Tier-A modules not strict yet: the database mixins split out of Database.py,
#: whose legacy signatures carry 66 unannotated functions between them. Remove a
#: module from here when it is annotated; never add one.
STRICT_PENDING = frozenset(
    {
        "fpdb_3_legacy.database_bulk_import",
        "fpdb_3_legacy.database_caches",
        "fpdb_3_legacy.database_hud_stats",
        "fpdb_3_legacy.database_players",
        "fpdb_3_legacy.database_tournaments",
    }
)

#: Modules excused from type checking altogether (``ignore_errors = true``).
IGNORE_BASELINE: frozenset[str] = frozenset()


def _mypy_config() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["mypy"]


def _overrides(setting: str) -> set[str]:
    modules: set[str] = set()
    for override in _mypy_config().get("overrides", []):
        if override.get(setting):
            names = override["module"]
            modules.update([names] if isinstance(names, str) else names)
    return modules


def _tier_a_modules() -> set[str]:
    return {f"fpdb_3_legacy.{path.stem}" for path in LEGACY.glob("*.py") if TIER_A_GROUP.search(path.stem)}


def test_imports_are_followed_across_the_whole_application() -> None:
    config = _mypy_config()

    assert config["follow_imports"] == "normal"
    assert {"fpdb_3_legacy", "fpdb"} <= set(config["files"])
    missing = [entry for entry in config["files"] if not (ROOT / entry).exists()]
    assert missing == [], "a [tool.mypy] files entry names nothing"


def test_the_workflow_runs_mypy_without_a_file_list() -> None:
    runs = re.findall(r"^\s*(?:run:\s*)?(mypy\b[^\n]*)$", WORKFLOW.read_text(encoding="utf-8"), flags=re.M)
    # The two scripts are the one exception mypy forces: it names every script
    # __main__, so they cannot share a run with each other.
    scripts = {
        "mypy --no-warn-unused-configs fpdb_3_legacy/fpdb.pyw",
        "mypy --no-warn-unused-configs fpdb_3_legacy/HUD_main.pyw",
    }

    assert "mypy" in runs
    assert set(runs) - scripts == {"mypy"}, "a mypy run with a file list is back in the workflow"


def test_every_tier_a_module_is_strict_or_pending() -> None:
    strict = _overrides("disallow_untyped_defs") & _overrides("warn_return_any")
    tier_a = _tier_a_modules()

    assert tier_a - strict - STRICT_PENDING == set(), "a new tier-A module must be strict"
    assert strict & STRICT_PENDING == set(), "a strict module is still listed as pending: remove it"
    assert STRICT_PENDING <= tier_a, "a pending module no longer exists: remove it"


def test_no_module_is_excused_beyond_the_baseline() -> None:
    excused = _overrides("ignore_errors")
    inline = {
        f"fpdb_3_legacy.{path.stem}"
        for path in LEGACY.rglob("*.py")
        if re.search(r"^#\s*mypy:\s*ignore-errors", path.read_text(encoding="utf-8"), flags=re.M)
    }

    assert (excused | inline) - IGNORE_BASELINE == set()
