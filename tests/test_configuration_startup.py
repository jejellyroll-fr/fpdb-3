"""Building a Config: what fpdb does with the file it is handed.

Config.__init__ is the first thing fpdb runs. It decides where the
configuration lives, creates it if it is not there, reads every section, and
refuses to start on the handful of mistakes it cannot work around. A wrong
turn here is not a wrong statistic later, it is an application that will not
open, so the branches that reject something matter as much as the ones that
accept it.

CONFIG_PATH is redirected into each test's own directory throughout. It is not
only where the log and database directories are derived from -- one branch
saves the configuration back to it outright -- so leaving it alone would mean
writing into the configuration of whoever runs the tests.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

import fpdb_3_legacy.Configuration as config_module
from fpdb_3_legacy.Configuration import CONFIG_VERSION, Config

DATABASE = '<database db_name="fpdb" db_server="sqlite" db_ip="" db_user="" db_pass="" db_desc="test"/>'


def config_xml(body: str = "", *, version: int | None = None, databases: str | None = None) -> str:
    """A configuration holding the least fpdb will start on, plus `body`."""
    general = "" if version is None else f'<general version="{version}"/>'
    section = DATABASE if databases is None else databases
    return (
        '<?xml version="1.0"?>\n'
        "<FreePokerToolsConfig>\n"
        f"{general}\n"
        f"<supported_databases>{section}</supported_databases>\n"
        f"{body}\n"
        "</FreePokerToolsConfig>\n"
    )


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    """Point everything Config derives from CONFIG_PATH at this test."""
    target = tmp_path / "fpdb-config"
    monkeypatch.setattr(config_module, "CONFIG_PATH", str(target))
    return target


def build(directory: Path, xml: str, **kwargs: Any) -> Config:
    path = directory / "HUD_config.xml"
    path.write_text(xml, encoding="utf-8")
    return Config(file=str(path), **kwargs)


# --------------------------------------------------------------------------
# Finding somewhere to keep the configuration
# --------------------------------------------------------------------------


def test_the_configuration_directory_is_created_on_a_first_run(tmp_path, home) -> None:
    assert not home.exists()

    build(tmp_path, config_xml(version=CONFIG_VERSION))

    assert home.is_dir()


def test_the_log_and_database_directories_sit_beside_the_configuration(tmp_path, home) -> None:
    config = build(tmp_path, config_xml(version=CONFIG_VERSION))

    assert Path(config.dir_log) == home / "log"
    assert Path(config.dir_database) == home / "database"


@pytest.mark.parametrize("as_given", [str, str.encode], ids=["text", "bytes"])
def test_a_log_directory_can_be_asked_for(tmp_path, home, as_given) -> None:
    # Either form works. The signature asks for a str, and a path handed
    # straight from the operating system arrives as bytes.
    chosen = tmp_path / "somewhere-else"
    chosen.mkdir()

    config = build(tmp_path, config_xml(version=CONFIG_VERSION), custom_log_dir=as_given(str(chosen)))

    assert Path(config.dir_log) == chosen


def test_a_log_directory_with_an_accent_survives_the_round_trip(tmp_path, home) -> None:
    # Decoding is the whole job of that branch, and "utf8" was hard-coded
    # where the platform's own filesystem encoding belongs.
    chosen = tmp_path / "journaux-privés"
    chosen.mkdir()

    config = build(tmp_path, config_xml(version=CONFIG_VERSION), custom_log_dir=str(chosen))

    assert Path(config.dir_log) == chosen


@pytest.mark.parametrize("as_given", [str, str.encode], ids=["text", "bytes"])
def test_a_log_directory_that_is_not_there_is_ignored(tmp_path, home, as_given) -> None:
    config = build(tmp_path, config_xml(version=CONFIG_VERSION), custom_log_dir=as_given(str(tmp_path / "absent")))

    assert Path(config.dir_log) == home / "log"


def test_no_log_directory_asked_for_puts_it_beside_the_configuration(tmp_path, home) -> None:
    config = build(tmp_path, config_xml(version=CONFIG_VERSION))

    assert Path(config.dir_log) == home / "log"


def test_a_file_that_is_not_there_falls_back_to_the_usual_one(tmp_path, home, capsys) -> None:
    # Passing a path that does not exist must not be fatal: fpdb says so and
    # goes looking for the configuration where it normally lives.
    fallback = tmp_path / "found.xml"
    fallback.write_text(config_xml(version=CONFIG_VERSION), encoding="utf-8")

    with patch.object(config_module, "get_config", return_value=(str(fallback), False, None)) as looked_up:
        config = Config(file=str(tmp_path / "not-here.xml"))

    assert looked_up.called
    assert config.file == str(fallback)
    assert "not found" in capsys.readouterr().err


# --------------------------------------------------------------------------
# Reading the sections
# --------------------------------------------------------------------------


def test_a_configuration_with_no_general_section_gets_the_defaults(tmp_path, home) -> None:
    config = build(tmp_path, config_xml())

    assert config.general["ui_language"] == "system"
    assert config.general["config_difficulty"] == "expert"


def test_a_configuration_of_the_current_version_is_not_flagged(tmp_path, home) -> None:
    config = build(tmp_path, config_xml(version=CONFIG_VERSION))

    assert config.wrongConfigVersion is False


def test_a_configuration_from_an_older_version_is_flagged(tmp_path, home) -> None:
    # fpdb offers to rebuild the file when this is set, so getting it wrong
    # either nags every start or never offers at all.
    config = build(tmp_path, config_xml(version=CONFIG_VERSION - 1))

    assert config.wrongConfigVersion is True


def test_the_hero_profiles_are_read(tmp_path, home) -> None:
    profiles = """<hero_profiles>
        <hero_profile name="Main"><site site_name="PokerStars" screen_name="Hero"/></hero_profile>
        <hero_profile name="Second"><site site_name="Winamax" screen_name="Villain"/></hero_profile>
    </hero_profiles>"""

    config = build(tmp_path, config_xml(profiles, version=CONFIG_VERSION))

    assert sorted(config.hero_profiles) == ["Main", "Second"]


def test_a_hero_profile_with_no_name_is_dropped(tmp_path, home) -> None:
    # It could not be selected by name afterwards, and it would displace a
    # real profile in the dictionary.
    profiles = '<hero_profiles><hero_profile name=""/><hero_profile name="Main"/></hero_profiles>'

    config = build(tmp_path, config_xml(profiles, version=CONFIG_VERSION))

    assert list(config.hero_profiles) == ["Main"]


# --------------------------------------------------------------------------
# What it refuses to start on
# --------------------------------------------------------------------------


def test_a_configuration_defining_no_database_is_refused(tmp_path, home) -> None:
    with pytest.raises(ValueError, match="at least one database"):
        build(tmp_path, config_xml(version=CONFIG_VERSION, databases=""))


def test_two_databases_of_the_same_name_are_refused(tmp_path, home) -> None:
    # The second would silently replace the first, and which one fpdb then
    # connects to would depend on document order.
    with pytest.raises(ValueError, match="must be unique"):
        build(tmp_path, config_xml(version=CONFIG_VERSION, databases=DATABASE + DATABASE))


def test_two_databases_of_the_same_name_outside_the_section_are_refused(tmp_path, home) -> None:
    # Older files list the databases at the top level rather than inside
    # supported_databases, and that path checks the same thing.
    loose = (
        '<?xml version="1.0"?>\n'
        "<FreePokerToolsConfig>\n"
        f'<general version="{CONFIG_VERSION}"/>\n'
        f"{DATABASE}{DATABASE}\n"
        "</FreePokerToolsConfig>\n"
    )

    with pytest.raises(ValueError, match="must be unique"):
        build(tmp_path, loose)


def test_a_database_listed_outside_the_section_is_still_found(tmp_path, home) -> None:
    loose = (
        '<?xml version="1.0"?>\n'
        "<FreePokerToolsConfig>\n"
        f'<general version="{CONFIG_VERSION}"/>\n'
        f"{DATABASE}\n"
        "</FreePokerToolsConfig>\n"
    )

    config = build(tmp_path, loose)

    assert config.db_selected == "fpdb"


def test_a_file_that_is_not_valid_xml_is_refused(tmp_path, home) -> None:
    with pytest.raises(ValueError, match="Unable to load configuration file"):
        build(tmp_path, "<this is not closed")


# --------------------------------------------------------------------------
# The two things it rewrites on the way in
# --------------------------------------------------------------------------

STALE_ENTAIN = """<supported_sites>
    <site site_name="Bwin.fr Poker" enabled="True" screen_name="hero"
          HH_path="C:\\Wrong\\Tables" network="PartyPoker"/>
  </supported_sites>
  <hhcs><hhc site="Bwin.fr Poker" converter="PartyPokerToFpdb"/></hhcs>"""


def test_a_stale_entain_configuration_is_migrated_and_saved(tmp_path, home) -> None:
    # bwin.fr moved from the PartyPoker network to iPoker, and a config written
    # before that never parses its hands. The migration runs while the file is
    # being read, so the new values hold in this very session, and the file is
    # written back with a .backup of what it was.
    config = build(tmp_path, config_xml(STALE_ENTAIN, version=CONFIG_VERSION))

    assert config.supported_sites["Bwin.fr Poker"].network == "iPoker"
    assert (tmp_path / "HUD_config.xml.backup").exists()


def test_a_current_configuration_is_not_rewritten(tmp_path, home) -> None:
    build(tmp_path, config_xml(version=CONFIG_VERSION))

    assert not (tmp_path / "HUD_config.xml.backup").exists()


def test_a_placeholder_mysql_password_is_replaced_from_the_default_file(tmp_path, home) -> None:
    # A config shipped with the placeholder still in it sends fpdb looking for
    # the credentials in the MySQL default file.
    placeholder = (
        '<database db_name="fpdb" db_server="mysql" db_ip="localhost" '
        'db_user="fpdb" db_pass="YOUR MYSQL PASSWORD" db_desc="test"/>'
    )
    found = {"db-host": "10.0.0.1", "db-user": "someone", "db-password": "secret"}

    with (
        patch.object(Config, "find_default_conf", return_value="/somewhere/my.cnf"),
        patch.object(Config, "read_default_conf", return_value=found),
        patch.object(Config, "save") as saved,
    ):
        config = build(tmp_path, config_xml(version=CONFIG_VERSION, databases=placeholder))

    assert config.get_db_parameters()["db-password"] == "secret"
    assert saved.called


def test_no_default_file_leaves_the_placeholder_alone(tmp_path, home) -> None:
    placeholder = (
        '<database db_name="fpdb" db_server="mysql" db_ip="localhost" '
        'db_user="fpdb" db_pass="YOUR MYSQL PASSWORD" db_desc="test"/>'
    )

    with patch.object(Config, "find_default_conf", return_value=None), patch.object(Config, "save") as saved:
        config = build(tmp_path, config_xml(version=CONFIG_VERSION, databases=placeholder))

    assert config.get_db_parameters()["db-password"] == "YOUR MYSQL PASSWORD"
    assert not saved.called


# --------------------------------------------------------------------------
# Choosing the database from outside the file
# --------------------------------------------------------------------------

SECOND = '<database db_name="other" db_server="sqlite" db_ip="" db_user="" db_pass="" db_desc="second"/>'


def test_the_database_can_be_chosen_by_name(tmp_path, home) -> None:
    config = build(tmp_path, config_xml(version=CONFIG_VERSION, databases=DATABASE + SECOND), dbname="other")

    assert config.db_selected == "other"


def test_a_name_that_matches_nothing_leaves_the_file_s_choice(tmp_path, home) -> None:
    config = build(tmp_path, config_xml(version=CONFIG_VERSION, databases=DATABASE + SECOND), dbname="no-such-database")

    assert config.db_selected == "fpdb"


def test_asking_for_nothing_leaves_the_file_s_choice(tmp_path, home) -> None:
    # None means the command line said nothing, which is not the same as
    # naming the database whose name is the empty string.
    config = build(tmp_path, config_xml(version=CONFIG_VERSION, databases=DATABASE + SECOND), dbname=None)

    assert config.db_selected == "fpdb"


def test_the_empty_string_is_a_name_like_any_other(tmp_path, home) -> None:
    # The XML format has always allowed it, so it has to stay tellable apart
    # from "the command line said nothing".
    unnamed = '<database db_name="" db_server="sqlite" db_ip="" db_user="" db_pass="" db_desc="unnamed"/>'

    config = build(tmp_path, config_xml(version=CONFIG_VERSION, databases=DATABASE + unnamed), dbname="")

    assert config.db_selected == ""


# --------------------------------------------------------------------------
# Reading a configuration does not rewrite it
# --------------------------------------------------------------------------

TWO_DATABASES = (
    '<database db_name="first" db_server="sqlite" db_ip="" db_user="" db_pass="" db_desc="a"/>'
    '<database db_name="second" db_server="sqlite" db_ip="" db_user="" db_pass="" db_desc="b" default="True"/>'
)


def flagged(config: Config) -> list[str]:
    return [
        node.getAttribute("db_name")
        for node in config.doc.getElementsByTagName("database")
        if node.hasAttribute("default")
    ]


def test_the_database_the_file_chose_is_the_one_selected(tmp_path, home) -> None:
    config = build(tmp_path, config_xml(version=CONFIG_VERSION, databases=TWO_DATABASES))

    assert config.db_selected == "second"


def test_reading_does_not_flag_the_first_database_it_meets(tmp_path, home) -> None:
    # Selection is worked out while reading, and the first database is
    # selected before any flagged one is reached. Writing that back marked a
    # database the file never chose.
    config = build(tmp_path, config_xml(version=CONFIG_VERSION, databases=TWO_DATABASES))

    assert flagged(config) == ["second"]


def test_opening_and_saving_leaves_the_file_saying_what_it_said(tmp_path, home) -> None:
    # This is where it was felt: changing any setting at all saves the whole
    # document, so a flag added while reading became a flag on disk.
    path = tmp_path / "HUD_config.xml"
    config = build(tmp_path, config_xml(version=CONFIG_VERSION, databases=TWO_DATABASES))

    config.save()

    saved = path.read_text(encoding="utf-8")
    assert saved.count('default="True"') == 1


def test_a_file_choosing_nothing_still_selects_the_first_database(tmp_path, home) -> None:
    # With no database flagged, the first one wins -- and it stays unflagged,
    # so the choice is remade the same way on every load rather than being
    # frozen into the file by the first save.
    neither = TWO_DATABASES.replace(' default="True"', "")
    config = build(tmp_path, config_xml(version=CONFIG_VERSION, databases=neither))

    assert config.db_selected == "first"
    assert flagged(config) == []


# --------------------------------------------------------------------------
# Where the databases are read from
# --------------------------------------------------------------------------


def sections(*bodies: str) -> str:
    return "".join(f"<supported_databases>{body}</supported_databases>" for body in bodies)


def named(db_name: str, *, default: bool = False) -> str:
    flag = ' default="True"' if default else ""
    return f'<database db_name="{db_name}" db_server="sqlite" db_ip="" db_user="" db_pass=""{flag}/>'


def test_every_section_of_a_file_is_read(tmp_path, home) -> None:
    # Nothing forbids a file from carrying more than one section, and dropping
    # the databases in the later ones would lose them silently.
    xml = config_xml(version=CONFIG_VERSION, databases="").replace(
        "<supported_databases></supported_databases>", sections(named("a"), named("b", default=True))
    )

    config = build(tmp_path, xml)

    assert sorted(config.supported_databases) == ["a", "b"]
    assert config.db_selected == "b"


def test_the_same_name_in_two_sections_is_refused(tmp_path, home) -> None:
    xml = config_xml(version=CONFIG_VERSION, databases="").replace(
        "<supported_databases></supported_databases>", sections(named("same"), named("same"))
    )

    with pytest.raises(ValueError, match="must be unique"):
        build(tmp_path, xml)


def test_an_empty_section_falls_back_to_the_top_level(tmp_path, home) -> None:
    # The section wins only when it holds something; an empty one must not
    # hide the databases beside it.
    xml = config_xml(version=CONFIG_VERSION, databases="") + ""
    xml = xml.replace("</FreePokerToolsConfig>", named("beside") + "</FreePokerToolsConfig>")

    config = build(tmp_path, xml)

    assert list(config.supported_databases) == ["beside"]
    assert config.db_selected == "beside"
