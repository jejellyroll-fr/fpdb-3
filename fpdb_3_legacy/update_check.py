"""Is a newer fpdb release out? (#445)

Binaries ship as archives on GitHub releases and nothing told users when a new
one appeared, so bugs already fixed kept being reported against old builds.
This module answers the question as plain data, without Qt, so the headless
suite can hold the parts that matter: which tag counts as newer, which archive
fits the running build, and that a network problem is silence, not an error.

Privacy: one anonymous, unauthenticated ``GET`` to the GitHub releases API --
no identifier, no cookie, nothing about the user or their hands. fpdb never
downloads or installs anything; it only links to the release page and the
archive that matches the running build.
"""

from __future__ import annotations

import json
import platform
import re
import sys
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("update_check")

__all__ = [
    "CHECK_INTERVAL",
    "LATEST_RELEASE_URL",
    "RELEASES_URL",
    "Release",
    "asset_for",
    "check_due",
    "fetch_release",
    "is_newer",
    "newer_release",
    "parse_version",
    "record_check",
    "release_to_announce",
]

LATEST_RELEASE_URL = "https://api.github.com/repos/jejellyroll-fr/fpdb-3/releases/latest"
# /releases/latest never returns a pre-release, so the opt-in reads the list.
RELEASES_URL = "https://api.github.com/repos/jejellyroll-fr/fpdb-3/releases?per_page=20"

# At most one automatic check a day; the Help menu's manual check ignores it.
CHECK_INTERVAL = timedelta(days=1)

# Startup must never wait on the network: this runs in a background thread, and
# a slow answer is treated like no answer.
_TIMEOUT_SECONDS = 5

# 3.9.1, v3.10.0, 3.10.0-alpha2, 3.10.0rc1, 3.10.0-beta.3 ...
_VERSION = re.compile(
    r"^v?(\d+)\.(\d+)(?:\.(\d+))?(?:[-.]?(a|alpha|b|beta|rc)[-.]?(\d*))?$",
    re.IGNORECASE,
)
# A final release sorts after every pre-release of the same number.
_STAGE_RANK = {"a": 0, "alpha": 0, "b": 1, "beta": 1, "rc": 2}
_FINAL = 3


def parse_version(tag: str) -> tuple[int, int, int, int, int] | None:
    """A sortable key for a release tag or package version, or None when it is not one.

    ``git describe`` output (``3.9.1-12-gabc123``) and anything else that is not a
    plain release number is None: comparing it would only guess.
    """
    match = _VERSION.match(tag.strip())
    if match is None:
        return None
    major, minor, patch, stage, number = match.groups()
    rank = _STAGE_RANK[stage.lower()] if stage else _FINAL
    return int(major), int(minor), int(patch or 0), rank, int(number or 0)


def is_newer(candidate: str, current: str) -> bool:
    """Whether ``candidate`` is a later release than ``current``; False when either is unreadable."""
    newer, running = parse_version(candidate), parse_version(current)
    return newer is not None and running is not None and newer > running


@dataclass(frozen=True)
class Release:
    """The release worth telling the user about."""

    tag: str
    page_url: str
    prerelease: bool = False
    asset_name: str | None = None
    asset_url: str | None = None


def _platform_suffix() -> str | None:
    """The ``<os>-<arch>`` part of the release archive names for this machine."""
    system = {"win32": "windows", "darwin": "macos"}.get(
        sys.platform, "linux" if sys.platform.startswith("linux") else None
    )
    machine = platform.machine().lower()
    arch = {"x86_64": "x64", "amd64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(machine)
    if system is None or arch is None:
        return None
    return f"{system}-{arch}"


def asset_for(assets: list[dict[str, Any]], packaging: str) -> tuple[str, str] | None:
    """The ``(name, url)`` of the archive built like the running fpdb, if the release has one.

    Archives are named ``fpdb-<packager>-<os>-<arch>.tar.gz``. A source checkout
    has no archive to replace it -- it is updated with git -- so it gets none.
    """
    packager = {"PyInstaller": "pyinstaller", "PyOxidizer": "pyoxidizer"}.get(packaging)
    suffix = _platform_suffix()
    if packager is None or suffix is None:
        return None
    wanted = f"fpdb-{packager}-{suffix}"
    for asset in assets:
        name = str(asset.get("name", ""))
        if name.startswith(wanted + "."):
            return name, str(asset.get("browser_download_url", ""))
    return None


def _read_json(url: str, timeout: float) -> Any:
    request = urllib.request.Request(  # noqa: S310 - fixed https URL
        url,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "fpdb-update-check"},
    )
    # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310  # nosec B310 - fixed https URL
        return json.load(response)


def fetch_release(
    *,
    include_prereleases: bool = False,
    reader: Callable[[str, float], Any] = _read_json,
    timeout: float = _TIMEOUT_SECONDS,
) -> dict[str, Any] | None:
    """The newest published release as GitHub describes it, or None when it cannot be read.

    Offline, rate-limited, a proxy page instead of JSON: all of it is None, and
    logged at debug level only -- the user did not ask, so there is nothing to tell.
    """
    try:
        if not include_prereleases:
            data = reader(LATEST_RELEASE_URL, timeout)
            return data if isinstance(data, dict) and data.get("tag_name") else None
        releases = reader(RELEASES_URL, timeout)
        if not isinstance(releases, list):
            return None
        published = [r for r in releases if isinstance(r, dict) and not r.get("draft") and r.get("tag_name")]
        readable = [r for r in published if parse_version(str(r["tag_name"])) is not None]
        return max(readable, key=lambda r: parse_version(str(r["tag_name"]))) if readable else None
    except Exception as exc:  # noqa: BLE001 - any failure means "no answer"
        log.debug(f"Update check failed: {exc}")
        return None


def newer_release(
    current: str,
    packaging: str,
    *,
    include_prereleases: bool = False,
    reader: Callable[[str, float], Any] = _read_json,
) -> Release | None:
    """The release to announce to a user running ``current``, or None when there is none."""
    data = fetch_release(include_prereleases=include_prereleases, reader=reader)
    return None if data is None else release_to_announce(data, current, packaging)


def release_to_announce(data: dict[str, Any], current: str, packaging: str) -> Release | None:
    """``data`` (a GitHub release) as a Release, when it is newer than ``current``."""
    tag = str(data["tag_name"])
    if not is_newer(tag, current):
        return None
    assets = data.get("assets")
    asset = asset_for(assets if isinstance(assets, list) else [], packaging)
    return Release(
        tag=tag,
        page_url=str(data.get("html_url") or "https://github.com/jejellyroll-fr/fpdb-3/releases"),
        prerelease=bool(data.get("prerelease")),
        asset_name=asset[0] if asset else None,
        asset_url=asset[1] if asset else None,
    )


def check_due(state_file: Path, now: datetime | None = None) -> bool:
    """Whether a day has passed since the last automatic check recorded in ``state_file``."""
    now = now or datetime.now()
    try:
        last = datetime.fromisoformat(json.loads(state_file.read_text(encoding="utf-8"))["last_check"])
    except (OSError, ValueError, KeyError, TypeError):
        return True
    # A clock moved backwards would otherwise silence the check until it caught up.
    return not (now - CHECK_INTERVAL < last <= now)


def record_check(state_file: Path, now: datetime | None = None) -> None:
    """Remember that an automatic check ran, so the next start within a day skips it."""
    try:
        state_file.write_text(json.dumps({"last_check": (now or datetime.now()).isoformat()}), encoding="utf-8")
    except OSError as exc:
        log.debug(f"Could not record the update check: {exc}")
