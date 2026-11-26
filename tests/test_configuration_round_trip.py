"""HUD_config.xml survives load -> edit -> save -> reload (#453, step 1).

``Configuration.py`` reads and writes the file through ``minidom``. #453 moves it
to ``ElementTree``, and this suite comes first so that the switch is checked
against what the file does today. It is written to pass with either parser:

- documents are compared by meaning (tags, attributes in their order, text,
  children), never by bytes, since the two serializers indent differently;
- comments are compared on the raw text, because ``ElementTree`` drops them
  unless it is told to keep them, and the one after the root element (the
  warning about the clear-text email password) is outside any element at all;
- every edit goes through a public ``Config`` method, and its result is read
  back through a fresh ``Config``.

Each edit is checked three ways: a reload sees the new value, every part of the
file the edit has no business touching is unchanged, and saving the reloaded
configuration again changes nothing more.

Every file here is a copy in ``tmp_path``; the user's configuration is never read.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import defusedxml.ElementTree as SafeET
import pytest

import fpdb_3_legacy.Configuration as config_module
from fpdb_3_legacy.config_common import normalizePath
from fpdb_3_legacy.config_migrations import (
    SITES_ADDED_IN_88,
    SITES_ADDED_IN_90,
    SITES_ADDED_IN_91,
    SITES_ADDED_IN_94,
    SITES_ADDED_IN_95,
)
from fpdb_3_legacy.Configuration import CONFIG_VERSION, Config
from fpdb_3_legacy.hud_profiles import HudProfileRule
from fpdb_3_legacy.hud_situation import PanelRule

EXAMPLE = Path(__file__).resolve().parents[1] / "fpdb_3_legacy" / "HUD_config.xml.example"
COMMENT = re.compile(r"<!--(.*?)-->", re.DOTALL)

# Entries of the shipped template the edits work on.
SITE = "PokerStars"
OTHER_SITE = "Full Tilt Poker"
STAT_SET = "holdem_default"
LAYOUT_SET = "ps_default"
LAYOUT_MAX = 2
DATABASE = "fpdb.db3"

# A user's file is mostly saved layouts and stat sets: copies of the shipped ones
# bring the template to the size a real configuration reaches.
LARGE_CONFIG_BYTES = 300_000

# Rooms the migrations from version 87 add back to a configuration.
ROOMS_ADDED_SINCE_87 = SITES_ADDED_IN_88 + SITES_ADDED_IN_90 + SITES_ADDED_IN_91 + SITES_ADDED_IN_94 + SITES_ADDED_IN_95

# Values that need escaping in an attribute, and text outside ASCII.
AWKWARD_NAME = "Zoë \"Z\" <&> 'q'"
AWKWARD_WINDOWS_PATH = "C:\\Users\\Zoë\\Hand Histories & more\\"
AWKWARD_POSIX_PATH = "/home/zoë/tournament summaries & <co>/"


# --------------------------------------------------------------------------
# Comparing documents by meaning
# --------------------------------------------------------------------------


def _root(path: Path) -> Any:
    return SafeET.parse(str(path)).getroot()


def _canonical(element: Any) -> tuple:
    """An element by meaning: tag, attributes in order, text, children. Indentation is ignored."""
    return (
        element.tag,
        tuple(element.attrib.items()),
        (element.text or "").strip(),
        tuple(_canonical(child) for child in element),
    )


def _comments(text: str) -> list[str]:
    return COMMENT.findall(text)


@dataclass(frozen=True)
class Child:
    """The one child of a section an edit may change, e.g. the <site> named PokerStars."""

    tag: str
    attribute: str
    value: str

    def matches(self, element: Any) -> bool:
        return element.tag == self.tag and element.get(self.attribute) == self.value


def _sections(root: Any) -> dict[str, Any]:
    sections: dict[str, Any] = {}
    for section in root:
        assert section.tag not in sections, f"<{section.tag}> appears twice at the top level"
        sections[section.tag] = section
    return sections


def assert_only_touched_changed(before: Any, after: Any, touched: Mapping[str, Child | None]) -> None:
    """Everything outside ``touched`` is unchanged, in the same order.

    ``touched`` maps a top-level section to the one child of it that may change,
    or to None when the whole section may.
    """
    assert after.tag == before.tag
    assert tuple(after.attrib.items()) == tuple(before.attrib.items())
    old, new = _sections(before), _sections(after)

    for tag in old.keys() | new.keys():
        if tag not in touched:
            assert tag in old, f"<{tag}> appeared although no edit asked for it"
            assert tag in new, f"<{tag}> disappeared"
            assert _canonical(new[tag]) == _canonical(old[tag]), f"<{tag}> changed although nothing edited it"
            continue
        child = touched[tag]
        if child is None or tag not in old:
            continue
        assert tag in new, f"<{tag}> disappeared"
        assert tuple(new[tag].attrib.items()) == tuple(old[tag].attrib.items()), f"<{tag}>'s own attributes changed"
        kept_old = [_canonical(c) for c in old[tag] if not child.matches(c)]
        kept_new = [_canonical(c) for c in new[tag] if not child.matches(c)]
        assert kept_new == kept_old, f"<{tag}> changed outside {child}"

    untouched_order = [tag for tag in old if tag in new]
    assert [tag for tag in new if tag in old] == untouched_order, "the top-level sections were reordered"


def assert_same_document(before: Any, after: Any) -> None:
    assert_only_touched_changed(before, after, {})


# --------------------------------------------------------------------------
# The configurations
# --------------------------------------------------------------------------


def _example_text() -> str:
    return EXAMPLE.read_text(encoding="utf-8")


def _copies(text: str, section: str, tag: str, suffix: str) -> str:
    """Copy every <tag name="..."> of <section> under a new name, at the end of the section."""
    start = text.index(f"<{section}>")
    end = text.index(f"</{section}>", start)
    body = text[start:end]
    # Comments may quote an element; copy only the real ones.
    body_without_comments = COMMENT.sub("", body)
    blocks = re.findall(rf"<{tag}\s[^>]*?\bname=\"[^\"]+\".*?</{tag}>", body_without_comments, re.DOTALL)
    assert blocks, f"no <{tag}> found in <{section}>"
    copied = "".join(
        "\n        " + re.sub(r'\bname="([^"]+)"', rf'name="\1{suffix}"', block, count=1) for block in blocks
    )
    return text[:end] + copied + "\n    " + text[end:]


def _large_text() -> str:
    """The template grown to a user's size: copied stat sets and layouts, and a second database."""
    text = _example_text()
    copy = 0
    while len(text.encode("utf-8")) < LARGE_CONFIG_BYTES:
        copy += 1
        text = _copies(text, "stat_sets", "ss", f"_copy{copy}")
        text = _copies(text, "layout_sets", "ls", f"_copy{copy}")
    second_database = (
        '<database db_server="postgresql" db_name="archive" db_ip="db.example.test" db_port="5433" '
        'db_user="alice" db_pass="p&amp;ss &quot;w&lt;o&gt;rd&quot;" db_desc="Zoë\'s archive"/>\n    '
    )
    return text.replace("</supported_databases>", second_database + "</supported_databases>", 1)


def _version_87_text() -> str:
    """The template as a version-87 file had it: without the rooms added since, and with padded stat sets."""
    text = _example_text()
    text = re.sub(r'<general version="\d+"', '<general version="87"', text, count=1)
    for room in ROOMS_ADDED_SINCE_87:
        name = re.escape(room)
        text, sites = re.subn(
            rf'\s*<site\s[^>]*?\bsite_name="{name}"[^>]*?(?:/>|>.*?</site>)', "", text, flags=re.DOTALL
        )
        text, hhcs = re.subn(rf'\s*<hhc\s[^>]*?\bsite="{name}"[^>]*?/>', "", text, flags=re.DOTALL)
        assert sites == 1, f"the template should declare {room} once"
        assert hhcs == 1, f"the template should give {room} one converter"
    # Up to v92 every shipped profile carried xpad="1"; v93 sets it to 0.
    return re.sub(r'(<ss\s[^>]*?\bxpad=")0"', r'\g<1>1"', text)


BUILDERS: dict[str, Callable[[], str]] = {"example": _example_text, "large": _large_text}


@pytest.fixture
def isolated(tmp_path, monkeypatch) -> Path:
    """A directory standing in for the config directory, so nothing reaches the real one."""
    monkeypatch.setattr(config_module, "CONFIG_PATH", str(tmp_path / "cfgdir"))
    return tmp_path


def _write(directory: Path, text: str) -> Path:
    path = directory / "HUD_config.xml"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture(params=sorted(BUILDERS))
def config_file(request, isolated) -> Path:
    return _write(isolated, BUILDERS[request.param]())


def test_the_large_configuration_is_the_size_of_a_users() -> None:
    text = _large_text()
    assert len(text.encode("utf-8")) >= LARGE_CONFIG_BYTES
    names = [ss.get("name") for ss in SafeET.fromstring(text.encode("utf-8")).iter("ss")]
    assert len(names) == len(set(names)), "every copied stat set needs a name of its own"


# --------------------------------------------------------------------------
# Saving without an edit
# --------------------------------------------------------------------------


def test_saving_an_unedited_configuration_keeps_the_document(config_file) -> None:
    before_text = config_file.read_text(encoding="utf-8")
    before = _root(config_file)

    Config(file=str(config_file)).save()

    after_text = config_file.read_text(encoding="utf-8")
    assert_same_document(before, _root(config_file))
    assert _comments(after_text) == _comments(before_text)


def test_the_comment_after_the_root_element_survives_a_save(isolated) -> None:
    # fpdb's only warning that the email password is stored in clear text sits
    # after </FreePokerToolsConfig>, where an ElementTree has nowhere to keep it.
    path = _write(isolated, _example_text())
    trailing = path.read_text(encoding="utf-8").rsplit("</FreePokerToolsConfig>", 1)[1]
    assert "password" in trailing

    Config(file=str(path)).save()

    assert path.read_text(encoding="utf-8").rsplit("</FreePokerToolsConfig>", 1)[1].strip() == trailing.strip()


def test_wrapped_long_lines_are_still_the_same_document(isolated) -> None:
    path = _write(isolated, _example_text())
    before = _root(path)
    config = Config(file=str(path))
    config.general["config_wrap_len"] = "60"

    config.save()

    text = path.read_text(encoding="utf-8")
    assert len(text.splitlines()) > len(_example_text().splitlines()), "the long lines were not wrapped"
    assert_same_document(before, _root(path))
    # The wrapper also breaks long lines inside comments: their words stay, their spacing does not.
    assert [" ".join(c.split()) for c in _comments(text)] == [" ".join(c.split()) for c in _comments(_example_text())]


# --------------------------------------------------------------------------
# Every public setter
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Edit:
    """Public setters applied together, how to tell a reload saw them, and what they may change."""

    name: str
    apply: Callable[[Config], object]
    check: Callable[[Config], None]
    touched: Mapping[str, Child | None] = field(default_factory=dict)
    setters: tuple[str, ...] = ()

    def __str__(self) -> str:
        return self.name


def _set_database(config: Config) -> None:
    config.set_db_parameters(
        db_name=DATABASE,
        db_ip="db.example.test",
        db_port="5433",
        db_user="alice",
        db_pass=AWKWARD_NAME,
        db_desc="Zoë's main base",
        db_server="postgresql",
    )


def _check_database(config: Config) -> None:
    db = config.supported_databases[DATABASE]
    assert (db.db_ip, db.db_port, db.db_user, db.db_pass, db.db_desc, db.db_server) == (
        "db.example.test",
        "5433",
        "alice",
        AWKWARD_NAME,
        "Zoë's main base",
        "postgresql",
    )


def _add_database(config: Config) -> None:
    config.add_db_parameters(
        db_name="bob_db",
        db_ip="10.0.0.2",
        db_user="bob",
        db_pass="s3cret",
        db_desc="second base",
        db_server="postgresql",
    )


def _check_added_database(config: Config) -> None:
    db = config.supported_databases["bob_db"]
    assert (db.db_ip, db.db_user, db.db_pass, db.db_desc, db.db_server) == (
        "10.0.0.2",
        "bob",
        "s3cret",
        "second base",
        "postgresql",
    )
    assert config.db_selected == DATABASE


def _add_and_delete_database(config: Config) -> None:
    _add_database(config)
    config.del_db_parameters("bob_db")


def _check_database_gone(config: Config) -> None:
    assert "bob_db" not in config.supported_databases


def _check_language(config: Config) -> None:
    assert config.general["ui_language"] == "fr"


PREFLOP_ADVISOR = "/opt/Preflop Advisor/Zoë & co"


def _check_preflop_advisor(config: Config) -> None:
    assert config.general["preflop_advisor"] == PREFLOP_ADVISOR


def _set_preflop_then_forget(config: Config) -> None:
    config.set_preflop_advisor_path(PREFLOP_ADVISOR)
    config.set_preflop_advisor_path("")


def _check_preflop_forgotten(config: Config) -> None:
    assert "preflop_advisor" not in config.general


def _check_amounts_in_bb(config: Config) -> None:
    assert config.get_replayer_amounts_in_bb() is True


def _check_no_update_check(config: Config) -> None:
    assert config.get_check_for_updates() is False


def _check_session_guard(config: Config) -> None:
    assert config.get_session_guard_defaults() == {"max_loss": "50.5", "max_minutes": "120"}


def _set_session_guard_then_forget(config: Config) -> None:
    config.set_session_guard_defaults({"max_loss": "5"})
    config.set_session_guard_defaults(None)


def _check_session_guard_forgotten(config: Config) -> None:
    assert config.get_session_guard_defaults() == {}


def _rename_first_cash_column(config: Config) -> None:
    config.gui_cash_stats[0][1] = "Gäme & <co>"
    config.save_gui_cash_stats()


def _check_first_cash_column(config: Config) -> None:
    assert config.gui_cash_stats[0][0] == "game"
    assert config.gui_cash_stats[0][1] == "Gäme & <co>"


FAV_SEATS = {seats: seats - 1 for seats in range(2, 11)}


def _edit_fav_seats(config: Config) -> None:
    config.edit_fav_seat(SITE, "True", *(str(seat) for seat in FAV_SEATS.values()))


def _check_fav_seats(config: Config) -> None:
    assert config.supported_sites[SITE].fav_seat == FAV_SEATS


def _edit_site(config: Config) -> None:
    config.edit_site(SITE, "False", AWKWARD_NAME, AWKWARD_WINDOWS_PATH, AWKWARD_POSIX_PATH)


def _check_site(config: Config) -> None:
    site = config.supported_sites[SITE]
    assert site.enabled is False
    assert site.screen_name == AWKWARD_NAME
    assert site.HH_path == normalizePath(AWKWARD_WINDOWS_PATH)
    assert site.TS_path == normalizePath(AWKWARD_POSIX_PATH)


def _check_hero_aliases(config: Config) -> None:
    assert config.get_hero_aliases(SITE) == ["alice", "Ålice & co"]


def _check_data_source_aliases(config: Config) -> None:
    assert config.get_data_source_hero_aliases("PHH") == ["alice", "bob"]


def _save_two_profiles_delete_one(config: Config) -> None:
    config.save_hero_profile("main", [(SITE, "alice"), (OTHER_SITE, "Ålice")], default=True)
    config.save_hero_profile("spare", [(SITE, "bob")])
    config.delete_hero_profile("spare")


def _check_profiles(config: Config) -> None:
    assert list(config.hero_profiles) == ["main"]
    profile = config.hero_profiles["main"]
    assert profile.default is True
    assert profile.links == [(SITE, "alice"), (OTHER_SITE, "Ålice")]


def _edit_hud_cell(config: Config) -> None:
    config.edit_hud(
        STAT_SET,
        "(0,0)",
        "vpip",
        "tog_decorate",
        "#FF0000",
        "V:",
        "%",
        "default",
        "#00FF00",
        "40",
        "#0000FF",
        "10",
        "VP$IP & <co>",
    )


def _check_hud_cell(config: Config) -> None:
    stat = config.stat_sets[STAT_SET].stats[(0, 0)]
    assert (stat.stat_name, stat.click, stat.hudcolor, stat.hudprefix, stat.hudsuffix, stat.popup) == (
        "vpip",
        "tog_decorate",
        "#FF0000",
        "V:",
        "%",
        "default",
    )
    assert (stat.stat_hicolor, stat.stat_hith, stat.stat_locolor, stat.stat_loth) == ("#00FF00", "40", "#0000FF", "10")
    assert stat.tip == "VP$IP & <co>"


GRID = (("vpip", "pfr"), ("three_B", "wtsd"))


def _edit_grid(config: Config) -> None:
    config.editStats(STAT_SET, [list(row) for row in GRID])


def _check_grid(config: Config) -> None:
    stat_set = config.stat_sets[STAT_SET]
    assert (stat_set.rows, stat_set.cols) == (2, 2)
    names = {rowcol: stat.stat_name for rowcol, stat in stat_set.stats.items()}
    assert names == {(0, 0): "vpip", (0, 1): "pfr", (1, 0): "three_B", (1, 1): "wtsd"}


LAYOUT_LOCATIONS = {1: (600, 200), 2: (20, 210), "common": (300, 240)}


def _save_layout(config: Config) -> None:
    config.save_layout_set(config.layout_sets[LAYOUT_SET], LAYOUT_MAX, dict(LAYOUT_LOCATIONS), 800, 560)


def _check_layout(config: Config) -> None:
    layout = config.layout_sets[LAYOUT_SET].layout[LAYOUT_MAX]
    assert (layout.width, layout.height) == (800, 560)
    assert layout.location[1] == LAYOUT_LOCATIONS[1]
    assert layout.location[2] == LAYOUT_LOCATIONS[2]
    assert layout.common == LAYOUT_LOCATIONS["common"]


def _set_panel_rules(config: Config) -> None:
    rule = PanelRule.from_mapping({"panel": "srp_flop", "when": {"street": "flop"}})
    config.set_hud_panel_rules([rule], fallback="core")


def _check_panel_rules(config: Config) -> None:
    rules = config.get_hud_panel_rules()
    assert [(rule.panel, rule.when) for rule in rules] == [("srp_flop", {"street": "flop"})]
    assert config.hud_panel_fallback == "core"


def _set_profile_rules(config: Config) -> None:
    config.set_hud_profile_rules(
        [HudProfileRule.from_mapping({"profile": "aof_advanced", "site": SITE, "game": "aof_omaha", "seats": "6"})]
    )


def _check_profile_rules(config: Config) -> None:
    rules = config.get_hud_profile_rules()
    # A rule's site is matched without case and stored lowered (HudProfileRule).
    assert [(rule.profile, rule.site, rule.game, rule.seats) for rule in rules] == [
        ("aof_advanced", SITE.lower(), "aof_omaha", 6)
    ]


HUD_UI = {"label": "Zoë's <HUD> & co", "stat_range": "S", "hud_days": 30, "font": "Courier New"}


def _check_hud_ui(config: Config) -> None:
    params = config.get_hud_ui_parameters()
    assert {key: params[key] for key in HUD_UI} == HUD_UI


def _check_import_filters(config: Config) -> None:
    assert config.imp.importFilters == ["holdem", "razz"]


def _set_hand_viewer_preferences(config: Config) -> None:
    config.set_hand_viewer_preferences(200, {"Date", "HandId", "Net"})


def _check_hand_viewer_preferences(config: Config) -> None:
    assert config.get_hand_viewer_preferences() == (200, {"Date", "HandId", "Net"})


THIS_SITE = {"supported_sites": Child("site", "site_name", SITE)}
THIS_STAT_SET = {"stat_sets": Child("ss", "name", STAT_SET)}

EDITS = (
    Edit("set_db_parameters", _set_database, _check_database, {"supported_databases": None}),
    Edit(
        "add_db_parameters",
        _add_database,
        _check_added_database,
        {"supported_databases": Child("database", "db_name", "bob_db")},
    ),
    # Adding then deleting a database gives back the section as it was.
    Edit(
        "add_then_del_db_parameters",
        _add_and_delete_database,
        _check_database_gone,
        setters=("add_db_parameters", "del_db_parameters"),
    ),
    Edit("set_general", lambda config: config.set_general(lang="fr"), _check_language, {"general": None}),
    Edit(
        "set_preflop_advisor_path",
        lambda config: config.set_preflop_advisor_path(PREFLOP_ADVISOR),
        _check_preflop_advisor,
        {"general": None},
    ),
    Edit(
        "set_preflop_advisor_path_then_forget",
        _set_preflop_then_forget,
        _check_preflop_forgotten,
        setters=("set_preflop_advisor_path",),
    ),
    Edit(
        "set_replayer_amounts_in_bb",
        lambda config: config.set_replayer_amounts_in_bb(True),
        _check_amounts_in_bb,
        {"general": None},
    ),
    Edit(
        "set_check_for_updates",
        lambda config: config.set_check_for_updates(False),
        _check_no_update_check,
        {"general": None},
    ),
    Edit(
        "set_session_guard_defaults",
        lambda config: config.set_session_guard_defaults({"max_minutes": 120, "max_loss": "50.5"}),
        _check_session_guard,
        {"session_guard": None},
    ),
    Edit(
        "set_session_guard_defaults_then_forget",
        _set_session_guard_then_forget,
        _check_session_guard_forgotten,
        setters=("set_session_guard_defaults",),
    ),
    Edit("save_gui_cash_stats", _rename_first_cash_column, _check_first_cash_column, {"gui_cash_stats": None}),
    Edit("edit_fav_seat", _edit_fav_seats, _check_fav_seats, THIS_SITE),
    Edit("edit_site", _edit_site, _check_site, THIS_SITE),
    Edit(
        "set_hero_aliases",
        lambda config: config.set_hero_aliases(SITE, ["alice", "Ålice & co", "alice"]),
        _check_hero_aliases,
        THIS_SITE,
    ),
    Edit(
        "set_data_source_hero_aliases",
        lambda config: config.set_data_source_hero_aliases("PHH", ["alice", "bob"]),
        _check_data_source_aliases,
        {"data_sources": None},
    ),
    Edit(
        "save_then_delete_hero_profile",
        _save_two_profiles_delete_one,
        _check_profiles,
        {"hero_profiles": None},
        setters=("save_hero_profile", "delete_hero_profile"),
    ),
    Edit("edit_hud", _edit_hud_cell, _check_hud_cell, THIS_STAT_SET),
    Edit("editStats", _edit_grid, _check_grid, THIS_STAT_SET),
    Edit("save_layout_set", _save_layout, _check_layout, {"layout_sets": Child("ls", "name", LAYOUT_SET)}),
    Edit("set_hud_panel_rules", _set_panel_rules, _check_panel_rules, {"hud_panel_rules": None}),
    Edit("set_hud_profile_rules", _set_profile_rules, _check_profile_rules, {"hud_profile_rules": None}),
    Edit(
        "set_hud_ui_parameters",
        lambda config: config.set_hud_ui_parameters(dict(HUD_UI)),
        _check_hud_ui,
        {"hud_ui": None},
    ),
    Edit(
        "editImportFilters",
        lambda config: config.editImportFilters("holdem,razz"),
        _check_import_filters,
        {"import": None},
    ),
    Edit("set_hand_viewer_preferences", _set_hand_viewer_preferences, _check_hand_viewer_preferences, {"general": None}),
)

# Public methods named like setters that never write the file: set_timezone and
# set_site_ids change memory only, and editEmail edits an <email> the template never
# ships. add_missing_elements has a test of its own below.
NOT_ROUND_TRIPPED = {"set_timezone", "set_site_ids", "editEmail", "add_missing_elements"}
SETTER_NAME = re.compile(r"(set|add|del|delete|edit|save)_?[A-Za-z]")


@pytest.mark.parametrize("edit", EDITS, ids=str)
def test_an_edit_survives_a_save_and_a_reload_and_touches_nothing_else(config_file, edit) -> None:
    before_text = config_file.read_text(encoding="utf-8")
    before = _root(config_file)
    config = Config(file=str(config_file))

    edit.apply(config)
    config.save()

    reloaded = Config(file=str(config_file))
    edit.check(reloaded)
    saved = _root(config_file)
    assert_only_touched_changed(before, saved, edit.touched)
    assert _comments(config_file.read_text(encoding="utf-8")) == _comments(before_text)

    # What a reload read back is what it writes: a second save changes nothing.
    reloaded.save()
    assert_same_document(saved, _root(config_file))


def test_every_public_setter_has_a_round_trip() -> None:
    # A setter added later needs an entry in EDITS, or the parser switch can break it unseen.
    covered = {setter for edit in EDITS for setter in (edit.setters or (edit.name,))}
    setters = {
        name for name in dir(Config) if SETTER_NAME.match(name) and callable(getattr(Config, name)) and name != "save"
    }
    assert covered <= setters, f"EDITS names methods Config does not have: {sorted(covered - setters)}"
    assert setters - covered - NOT_ROUND_TRIPPED == set()


# --------------------------------------------------------------------------
# Sections added to a file
# --------------------------------------------------------------------------


def test_restoring_missing_sections_brings_them_back_with_their_comment(isolated) -> None:
    example = _example_text()
    template = SafeET.fromstring(example.encode("utf-8"))
    comment = re.search(r"\s*<!-- Dynamic HUD panels:.*?-->", example, re.DOTALL)
    assert comment is not None
    stripped = example.replace(comment.group(0), "", 1)
    stripped = re.sub(r"\s*<hud_panel_rules\b.*?</hud_panel_rules>", "", stripped, count=1, flags=re.DOTALL)
    stripped = re.sub(r"\s*<raw_tourneys\b[^>]*?(?:/>|>.*?</raw_tourneys>)", "", stripped, count=1, flags=re.DOTALL)
    path = _write(isolated, stripped)
    before = _root(path)
    assert {"hud_panel_rules", "raw_tourneys"}.isdisjoint(_sections(before))
    config = Config(file=str(path))

    added = config.add_missing_elements(config.doc, str(EXAMPLE))

    assert added == 2
    saved = _root(path)
    assert_only_touched_changed(before, saved, {"hud_panel_rules": None, "raw_tourneys": None})
    for tag in ("hud_panel_rules", "raw_tourneys"):
        assert _canonical(_sections(saved)[tag]) == _canonical(_sections(template)[tag])
    assert _comments(path.read_text(encoding="utf-8")) == _comments(example)
    Config(file=str(path))  # and the result loads


# --------------------------------------------------------------------------
# Upgrading an older file
# --------------------------------------------------------------------------


def test_an_upgrade_from_version_87_changes_only_what_the_migrations_say(isolated) -> None:
    path = _write(isolated, _version_87_text())
    before_text = path.read_text(encoding="utf-8")
    before = _root(path)
    config = Config(file=str(path))
    assert config.wrongConfigVersion

    backup = config.upgrade_config()

    assert Path(backup).read_text(encoding="utf-8") == before_text
    after = _root(path)
    old, new = _sections(before), _sections(after)
    assert_only_touched_changed(
        before, after, {"general": None, "supported_sites": None, "hhcs": None, "stat_sets": None}
    )

    # <general>: only the version moved.
    assert new["general"].get("version") == str(CONFIG_VERSION)
    assert [(k, v) for k, v in new["general"].attrib.items() if k != "version"] == [
        (k, v) for k, v in old["general"].attrib.items() if k != "version"
    ]
    # Rooms and converters: the ones added since came back, the others are as they were.
    for section, key in (("supported_sites", "site_name"), ("hhcs", "site")):
        kept = [_canonical(c) for c in new[section] if c.get(key) not in ROOMS_ADDED_SINCE_87]
        assert kept == [_canonical(c) for c in old[section]]
        added = sorted(c.get(key) for c in new[section] if c.get(key) in ROOMS_ADDED_SINCE_87)
        assert added == sorted(ROOMS_ADDED_SINCE_87)
    # Stat sets: the padding went back to 0, which is the template, and nothing else moved.
    assert _canonical(new["stat_sets"]) == _canonical(_sections(_root(EXAMPLE))["stat_sets"])
    assert _comments(path.read_text(encoding="utf-8")) == _comments(before_text)

    reloaded = Config(file=str(path))
    assert not reloaded.wrongConfigVersion
    assert set(ROOMS_ADDED_SINCE_87) <= set(reloaded.supported_sites)
