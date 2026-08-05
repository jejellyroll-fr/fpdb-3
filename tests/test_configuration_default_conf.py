"""The database credentials fpdb inherits from its old configuration file.

Before HUD_config.xml, fpdb kept its database settings in a plain
``key = value`` file called default.conf. It still reads that one, but only in
one situation: a configuration whose MySQL password is the placeholder that
ships with it has never been filled in, so the credentials are looked for in
the old file instead and copied across.

That makes this the upgrade path from a very old install, and the only reason
those two functions still exist.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest

import fpdb_3_legacy.Configuration as config_module
from fpdb_3_legacy.Configuration import CONFIG_VERSION, Config

PLACEHOLDER = "YOUR MYSQL PASSWORD"


@pytest.fixture
def reader() -> Any:
    """The two functions need no configuration of their own to be exercised."""
    return object.__new__(Config)


def write(path: Path, text: str) -> str:
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    return str(path)


# --------------------------------------------------------------------------
# Reading the old file
# --------------------------------------------------------------------------


def test_the_settings_are_read(reader, tmp_path) -> None:
    path = write(tmp_path / "default.conf", "db-host = localhost\ndb-user = fpdb\n")

    assert reader.read_default_conf(path) == {"db-host": "localhost", "db-user": "fpdb"}


def test_the_spaces_around_a_setting_are_not_part_of_it(reader, tmp_path) -> None:
    # The file was written by hand, so it is laid out for reading rather than
    # for parsing.
    path = write(tmp_path / "default.conf", "   db-host   =   localhost   \n")

    assert reader.read_default_conf(path) == {"db-host": "localhost"}


def test_a_setting_with_no_spaces_reads_the_same(reader, tmp_path) -> None:
    path = write(tmp_path / "default.conf", "db-host=localhost\n")

    assert reader.read_default_conf(path) == {"db-host": "localhost"}


def test_a_comment_is_not_a_setting(reader, tmp_path) -> None:
    path = write(tmp_path / "default.conf", "# db-host = commented out\ndb-user = fpdb\n")

    assert reader.read_default_conf(path) == {"db-user": "fpdb"}


def test_a_blank_line_is_not_a_setting(reader, tmp_path) -> None:
    path = write(tmp_path / "default.conf", "db-user = fpdb\n\n   \n")

    assert reader.read_default_conf(path) == {"db-user": "fpdb"}


def test_a_line_that_is_not_a_setting_is_stepped_over(reader, tmp_path) -> None:
    # Whatever else someone left in the file, rather than refusing the lot.
    path = write(tmp_path / "default.conf", "just some words\ndb-user = fpdb\n")

    assert reader.read_default_conf(path) == {"db-user": "fpdb"}


def test_a_password_may_contain_the_separator(reader, tmp_path) -> None:
    # Only the first = separates; the rest is the value. A password is exactly
    # the setting people put odd characters in.
    path = write(tmp_path / "default.conf", "db-password = a=b=c\n")

    assert reader.read_default_conf(path) == {"db-password": "a=b=c"}


def test_a_setting_given_twice_keeps_the_last(reader, tmp_path) -> None:
    path = write(tmp_path / "default.conf", "db-host = first\ndb-host = second\n")

    assert reader.read_default_conf(path) == {"db-host": "second"}


def test_a_file_with_nothing_in_it_reads_as_nothing(reader, tmp_path) -> None:
    path = write(tmp_path / "default.conf", "")

    assert reader.read_default_conf(path) == {}


def test_a_file_that_is_not_there_is_not_read_quietly(reader, tmp_path) -> None:
    # Nothing calls this without find_default_conf having said the file is
    # there, so it does not guard against the file being gone.
    with pytest.raises(OSError, match="No such file"):
        reader.read_default_conf(str(tmp_path / "absent.conf"))


# --------------------------------------------------------------------------
# Finding it
# --------------------------------------------------------------------------


def test_the_file_is_looked_for_beside_the_configuration(reader, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(config_module, "CONFIG_PATH", str(tmp_path))
    expected = write(tmp_path / "default.conf", "db-host = localhost\n")

    assert reader.find_default_conf() == expected


def test_no_such_file_means_nothing_to_read(reader, tmp_path, monkeypatch) -> None:
    # The normal case: nobody who installed fpdb this decade has one.
    monkeypatch.setattr(config_module, "CONFIG_PATH", str(tmp_path))

    assert reader.find_default_conf() is None


def test_nowhere_to_look_means_nothing_to_read(reader, monkeypatch) -> None:
    monkeypatch.setattr(config_module, "CONFIG_PATH", "")

    assert reader.find_default_conf() is None


# --------------------------------------------------------------------------
# What it is all for
# --------------------------------------------------------------------------

DATABASE = (
    '<database db_name="fpdb" db_server="mysql" db_ip="localhost" '
    f'db_user="fpdb" db_pass="{PLACEHOLDER}" db_desc="test"/>'
)


@pytest.fixture
def upgrading(tmp_path, monkeypatch) -> Any:
    """A configuration still carrying the placeholder password."""
    monkeypatch.setattr(config_module, "CONFIG_PATH", str(tmp_path))

    def make() -> Config:
        path = tmp_path / "HUD_config.xml"
        path.write_text(
            '<?xml version="1.0"?>\n<FreePokerToolsConfig>\n'
            f'<general version="{CONFIG_VERSION}"/>\n'
            f"<supported_databases>{DATABASE}</supported_databases>\n"
            "</FreePokerToolsConfig>\n",
            encoding="utf-8",
        )
        return Config(file=str(path))

    return make


def test_the_old_credentials_are_carried_over(upgrading, tmp_path) -> None:
    write(
        tmp_path / "default.conf",
        """\
        db-host = dbhost
        db-user = someone
        db-password = secret
        """,
    )

    config = upgrading()

    database = config.get_db_parameters()
    assert database["db-host"] == "dbhost"
    assert database["db-user"] == "someone"
    assert database["db-password"] == "secret"


def test_the_placeholder_stays_when_there_is_no_old_file(upgrading) -> None:
    config = upgrading()

    assert config.get_db_parameters()["db-password"] == PLACEHOLDER
