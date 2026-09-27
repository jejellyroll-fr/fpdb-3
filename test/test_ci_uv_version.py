"""The uv version CI installs is the one pyproject.toml requires.

``ci.yml`` pins uv once, in a workflow-level ``UV_VERSION``; ``pyproject.toml``
states the same version as ``[tool.uv] required-version``. Nothing ties the two
together but this test, so a bump of one without the other fails here instead
of as a resolution difference between CI and a developer's machine.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ci_installs_the_uv_version_pyproject_requires() -> None:
    required = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["uv"]["required-version"]
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    pinned = re.search(r'^\s+UV_VERSION:\s*"([^"]+)"', workflow, re.MULTILINE)

    assert pinned, "ci.yml must pin uv once as a workflow-level UV_VERSION"
    assert required == f"=={pinned.group(1)}"
    # Every setup-uv step reads that one value rather than its own pin.
    assert "version: ${{ env.UV_VERSION }}" in workflow
    assert not re.search(r'setup-uv@[^\n]+\n\s+with:\n\s+version:\s*"', workflow)
