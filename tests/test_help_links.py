"""Every Help affordance points at a guide that exists (#334)."""

from __future__ import annotations

import re
from pathlib import Path

from fpdb_3_legacy import help_links

PACKAGE = Path(help_links.__file__).resolve().parent

# ``self._open_help("...")`` and ``help_links.open_help("...")`` with a literal:
# a screen asking for a topic by name is the one place a typo cannot be caught
# by the type checker.
_ASKED = re.compile(r"""(?:_open_help|open_help)\(\s*["']([^"']+)["']""")


def _asked_topics() -> set[str]:
    """Every topic id the screens actually ask for, read off the source."""
    asked: set[str] = set()
    for path in PACKAGE.rglob("*.py"):
        if path.name == "help_links.py":
            continue
        asked.update(_ASKED.findall(path.read_text(encoding="utf-8")))
    return asked


def test_every_topic_names_a_document_that_exists() -> None:
    topics = help_links.help_topics()
    assert topics
    for topic in topics:
        assert topic.filename.endswith(".md"), topic.filename
        assert topic.exists(), f"{topic.id} points at a missing {topic.filename}"


def test_topics_are_unique() -> None:
    ids = [topic.id for topic in help_links.help_topics()]
    assert len(ids) == len(set(ids))


def test_every_screen_that_asks_for_help_finds_a_topic() -> None:
    """A button whose topic nobody listed is a button that does nothing.

    The Dynamic HUD panel help reached the table that way: the screen called
    ``_open_help("hud-dynamic")`` while only "research" was defined, so the
    press logged a warning and opened nothing. Reading the call sites is what
    catches that, since the id is a plain string.
    """
    asked = _asked_topics()
    assert asked, "no help call site was found; the pattern is stale"
    missing = sorted(topic for topic in asked if help_links.help_topic(topic) is None)
    assert missing == [], f"asked for but not listed: {missing}"


def test_an_unknown_topic_is_not_opened() -> None:
    opened: list[str] = []
    assert help_links.open_help("nope", opener=opened.append) is False
    assert opened == []


def test_a_known_topic_opens_its_file_url() -> None:
    for topic in help_links.help_topics():
        opened: list[str] = []
        assert help_links.open_help(topic.id, opener=lambda url: opened.append(url) or True) is True
        assert opened == [topic.path.as_uri()], topic.id


def test_the_ui_opens_the_user_guide_not_a_developer_reference() -> None:
    """The Research button must not drop a reader into engine vocabulary.

    ``docs/research-browser.md`` is the technical reference for the screen's
    internals and is linked from the guides; the guide itself is the quick
    start, which the docs directory is free to rename without changing the id.
    """
    topic = help_links.help_topic("research")
    assert topic is not None
    assert topic.filename == "research-quick-start.md"


def test_a_build_without_the_docs_opens_the_published_guide(monkeypatch, tmp_path) -> None:
    """An installed build ships the modules, not the repository's docs.

    Pointing the button at a directory that is not there used to answer False
    and log, which is a Help button that helps nobody in the build a new user
    installs first.
    """
    monkeypatch.setattr(help_links, "DOCS_DIR", tmp_path)  # empty on purpose
    topic = help_links.help_topic("research")
    assert topic is not None and not topic.exists()
    opened: list[str] = []
    assert help_links.open_help("research", opener=lambda url: opened.append(url) or True) is True
    assert opened == [f"{help_links.DOCS_URL}/{topic.filename}"]
    assert opened[0].startswith("https://")


def test_a_failing_opener_is_not_raised() -> None:
    def boom(_url: str) -> bool:
        raise RuntimeError("no desktop")

    assert help_links.open_help("research", opener=boom) is False


def test_help_topic_lookup_is_forgiving() -> None:
    assert help_links.help_topic("  research ") is not None
    assert help_links.help_topic(None) is None


def test_the_omaha_guide_is_reachable_from_the_help_menu() -> None:
    """A guide nobody can open is a file, not help (#353).

    The research topic is opened by the browser's own "?" button; this one has
    no button of its own, so it needs a menu entry or it is unreachable -- the
    mirror of the failure this table already guards against.
    """
    from fpdb_3_legacy import menu_layout

    help_menu = next(menu for menu in menu_layout.menu_layout() if "Help" in menu.title)
    handlers = {item.handler for item in help_menu.items}

    assert "help_research_omaha" in handlers
    assert help_links.help_topic("research-omaha") is not None


def test_the_quick_start_sends_omaha_readers_to_their_own_guide() -> None:
    # Its worked examples are Hold'em and its leading view cannot work on a
    # four-card game, so an Omaha reader must not be left to discover that.
    quick_start = (help_links.DOCS_DIR / "research-quick-start.md").read_text()

    assert "research-omaha.md" in quick_start
