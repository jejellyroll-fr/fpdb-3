"""Where each screen's "?" sends the reader (#334).

The user guides live in ``docs/`` and the technical references beside them. This
module is the one place that says which guide belongs to which screen, so the
Help affordances cannot drift from the docs they name, and a test can check that
every topic resolves to a file that exists.

Only the *user* guides are opened from the UI. The developer references
(``query-engine.md``, ``dynamic-panels.md``, ...) stay linked from the guides
themselves, so a reader is never dropped into engine vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from .loggingFpdb import get_logger

log = get_logger("help_links")

#: The repository's docs directory, resolved from this file (``fpdb_3_legacy/``).
DOCS_DIR: Final[Path] = Path(__file__).resolve().parent.parent / "docs"

#: Where the same guides are published, for a build that has no docs directory.
#:
#: The installers ship the application modules, not the repository's
#: documentation, so ``DOCS_DIR`` points at a directory that is not there. A
#: missing file used to be logged and answered ``False``, which turns the Help
#: button into a no-op in exactly the build a new user would open first; the
#: guide is opened as published instead.
DOCS_URL: Final[str] = "https://github.com/jejellyroll-fr/fpdb-3/blob/development/docs"


@dataclass(frozen=True)
class HelpTopic:
    """One screen's guide: a stable id, a title and the file it opens."""

    id: str
    title: str
    filename: str

    @property
    def path(self) -> Path:
        return DOCS_DIR / self.filename

    def exists(self) -> bool:
        return self.path.is_file()

    def url(self) -> str:
        """The URL a desktop handler opens: the local guide, else the published one."""
        if self.path.is_file():
            return self.path.as_uri()
        return f"{DOCS_URL}/{self.filename}"


#: The screens that offer help, in the order the guides introduce them.
#:
#: A topic is listed only once its guide is in the tree: an entry pointing at a
#: document nobody wrote turns the Help button into a log line, which is the
#: failure mode this table exists to catch -- and so does a screen that asks for
#: a topic nobody listed, which is how the Dynamic HUD button reached this table
#: with nothing behind it. The id is what the button calls; the filename is the
#: *user* guide, never a developer reference beside it.
TOPICS: Final[tuple[HelpTopic, ...]] = (
    HelpTopic("research", "Research Browser", "research-quick-start.md"),
    HelpTopic("research-omaha", "Research Browser for Omaha", "research-omaha.md"),
    HelpTopic("hud-dynamic", "Dynamic HUD panels", "hud-dynamic-guide.md"),
)

_BY_ID: Final[dict[str, HelpTopic]] = {topic.id: topic for topic in TOPICS}


def help_topic(topic_id: str) -> HelpTopic | None:
    """The topic an id names, or ``None`` when nothing offers help there."""
    return _BY_ID.get(str(topic_id or "").strip())


def help_topics() -> tuple[HelpTopic, ...]:
    """Every screen that offers help, for a test or an index page."""
    return TOPICS


def open_help(topic_id: str, *, opener: Any = None) -> bool:
    """Open a topic's guide, returning whether anything was opened.

    An unknown topic is logged and answered ``False`` rather than raising: a Help
    button that cannot find its document must not take the window down with it.
    A known topic whose file is absent from this build opens the published
    guide. ``opener`` is injectable so the behaviour can be tested without a
    desktop.
    """
    topic = help_topic(topic_id)
    if topic is None:
        log.warning("No guide is installed for help topic %r", topic_id)
        return False
    if not topic.exists():
        log.info("Help topic %r is not in this build; opening the published guide", topic_id)
    open_url = opener if opener is not None else _desktop_opener()
    if open_url is None:
        log.info("Help for %s: %s", topic_id, topic.path)
        return False
    try:
        return bool(open_url(topic.url()))
    except Exception:  # intentional broad catch: Help must never raise into the UI
        log.exception("Could not open the guide for help topic %r", topic_id)
        return False


def _desktop_opener() -> Any:
    """A Qt URL opener, or ``None`` outside a Qt application."""
    try:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
    except Exception:  # noqa: BLE001 - no Qt means no window to help
        return None

    def open_url(url: str) -> bool:
        return bool(QDesktopServices.openUrl(QUrl(url)))

    return open_url


__all__ = [
    "DOCS_DIR",
    "DOCS_URL",
    "HelpTopic",
    "TOPICS",
    "help_topic",
    "help_topics",
    "open_help",
]
