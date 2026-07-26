"""Finding a configuration on a machine that has never run fpdb.

The first thing fpdb does is look for HUD_config.xml where it keeps it, and if
there is none, copy the shipped example into place. Everything after that
assumes the file exists, so this is where a fresh install either starts
working or stops with a message.

The two ways it stops both call sys.exit, which is why they are worth pinning:
they are the difference between fpdb telling somebody what is wrong and fpdb
raising a traceback at them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import fpdb_3_legacy.Configuration as config_module
from fpdb_3_legacy.Configuration import get_config

NAME = "HUD_config.xml"


@pytest.fixture
def where(tmp_path, monkeypatch) -> Path:
    """Point the configuration directory at this test's own."""
    home = tmp_path / "config"
    home.mkdir()
    monkeypatch.setattr(config_module, "CONFIG_PATH", str(home))
    return home


@pytest.fixture
def example(tmp_path, monkeypatch) -> Any:
    """Decide what the shipped example is, and whether it exists."""

    def place(contents: str | None) -> Path:
        path = tmp_path / f"{NAME}.example"
        if contents is not None:
            path.write_text(contents, encoding="utf-8")
        monkeypatch.setattr(config_module, "_find_example_config", lambda _name: str(path))
        return path

    return place


# --------------------------------------------------------------------------
# A configuration that is already there
# --------------------------------------------------------------------------


def test_the_configuration_already_in_place_is_the_one_used(where, example) -> None:
    example("<example/>")
    (where / NAME).write_text("<mine/>", encoding="utf-8")

    path, copied, _ = get_config(NAME)

    assert path == str(where / NAME).replace("\\", "/")
    assert copied is False
    assert Path(path).read_text(encoding="utf-8") == "<mine/>"


def test_where_the_example_is_comes_back_too(where, example) -> None:
    # The caller reads it to fill in sections the configuration is missing,
    # so it is answered whether or not it was needed here.
    shipped = example("<example/>")
    (where / NAME).write_text("<mine/>", encoding="utf-8")

    assert get_config(NAME)[2] == str(shipped)


def test_the_path_is_given_with_forward_slashes(tmp_path, monkeypatch, example) -> None:
    # The configuration directory is a Windows path on Windows, and the rest
    # of fpdb compares these as strings.
    example("<example/>")
    monkeypatch.setattr(config_module, "CONFIG_PATH", "C:\\Users\\hero\\fpdb")

    assert get_config(NAME, fallback=False)[0] == "C:/Users/hero/fpdb/HUD_config.xml"


# --------------------------------------------------------------------------
# A machine that has none
# --------------------------------------------------------------------------


def test_the_example_is_copied_into_place(where, example) -> None:
    example("<shipped/>")

    path, copied, _ = get_config(NAME)

    assert copied is True
    assert Path(path).read_text(encoding="utf-8") == "<shipped/>"


def test_nothing_is_copied_when_the_caller_says_not_to(where, example) -> None:
    # get_config is also asked simply where the file would be.
    example("<shipped/>")

    path, copied, _ = get_config(NAME, fallback=False)

    assert copied is False
    assert not Path(path).exists()


def test_no_example_to_copy_stops_fpdb_with_a_message(where, example, capsys) -> None:
    example(None)

    with pytest.raises(SystemExit):
        get_config(NAME)

    assert f"No {NAME} found, cannot fall back" in capsys.readouterr().err


def test_an_example_that_cannot_be_copied_stops_fpdb_with_a_message(where, example, monkeypatch, capsys) -> None:
    # A read-only configuration directory, or a full disk: fpdb cannot go on
    # without the file, and says which step failed rather than unwinding.
    example("<shipped/>")

    def refuse(*_args, **_kwargs):
        msg = "read-only file system"
        raise OSError(msg)

    monkeypatch.setattr(config_module.shutil, "copyfile", refuse)

    with pytest.raises(SystemExit):
        get_config(NAME)

    assert "Error copying .example config file" in capsys.readouterr().err


def test_a_failed_copy_leaves_no_half_written_configuration(where, example, monkeypatch) -> None:
    # Whatever the caller does with the exit, it must not later find a file
    # that looks like a configuration and is not one.
    example("<shipped/>")
    monkeypatch.setattr(config_module.shutil, "copyfile", lambda *_a, **_k: (_ for _ in ()).throw(OSError("no")))

    with pytest.raises(SystemExit):
        get_config(NAME)

    assert not (where / NAME).exists()


# --------------------------------------------------------------------------
# Which example gets copied
# --------------------------------------------------------------------------
#
# fpdb runs from a source checkout, from a package, and from a system install,
# and the example sits somewhere different in each. The list is searched in
# order, so which one wins when several exist is the whole behaviour.

SEARCHED_IN_ORDER = ("SOURCE_ROOT_PATH", "SOURCE_DIR", "FPDB_ROOT_PATH", "PYFPDB_PATH")


@pytest.fixture
def places(tmp_path, monkeypatch) -> Any:
    """Give each searched location a directory of its own, all of them empty."""
    # The list also holds a bare relative name, so the working directory is
    # one of the places searched and has to be an empty one.
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    directories = {}
    for constant in (*SEARCHED_IN_ORDER, "CONFIG_PATH"):
        directory = tmp_path / constant
        directory.mkdir()
        directories[constant] = directory
        monkeypatch.setattr(config_module, constant, str(directory))
    return directories


def put_example(directory: Path) -> Path:
    path = directory / f"{NAME}.example"
    path.write_text("<shipped/>", encoding="utf-8")
    return path


@pytest.mark.parametrize("constant", SEARCHED_IN_ORDER)
def test_every_place_fpdb_can_run_from_is_searched(places, constant) -> None:
    expected = put_example(places[constant])

    assert config_module._find_example_config(NAME) == str(expected)


def test_the_first_place_that_has_one_wins(places) -> None:
    # A source checkout that is also installed has two, and the checkout's is
    # the one being worked on.
    first = put_example(places["SOURCE_ROOT_PATH"])
    put_example(places["PYFPDB_PATH"])

    assert config_module._find_example_config(NAME) == str(first)


def test_nowhere_having_one_answers_beside_the_configuration(places) -> None:
    # Not a path that exists: it is what get_config then reports as missing.
    answer = config_module._find_example_config(NAME)

    assert answer == str(places["CONFIG_PATH"] / f"{NAME}.example")
    assert not Path(answer).exists()
