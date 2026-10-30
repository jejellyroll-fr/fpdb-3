"""Saving HUD_config.xml leaves it either fully old or fully new (#642).

``Config.save()`` used to move the file to ``.backup`` and then write the new
content straight into ``HUD_config.xml``. A write cut short -- a full disk, a
crash -- left the configuration truncated or missing, and the next save moved
that truncated file over the good backup.

The new content now goes to a temporary file beside the configuration, is
flushed to disk, and replaces the file in one step. The backup is a copy.
"""

from __future__ import annotations

import errno
import os
import sys
from pathlib import Path
from typing import Any

import pytest

import fpdb_3_legacy.Configuration as config_module
from fpdb_3_legacy.Configuration import CONFIG_VERSION, Config

CONFIG_XML = (
    '<?xml version="1.0"?>\n<FreePokerToolsConfig>\n'
    f'<general version="{CONFIG_VERSION}"/>\n'
    '<supported_sites><site enabled="True" site_name="PokerStars" screen_name="hero"/></supported_sites>\n'
    '<supported_databases><database db_name="fpdb" db_server="sqlite" db_ip="" db_user="" db_pass="" db_desc="t"/>'
    "</supported_databases>\n"
    "</FreePokerToolsConfig>\n"
)

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions and links")


@pytest.fixture
def config(tmp_path, monkeypatch) -> Any:
    monkeypatch.setattr(config_module, "CONFIG_PATH", str(tmp_path / "cfgdir"))
    path = tmp_path / "HUD_config.xml"
    path.write_text(CONFIG_XML, encoding="utf-8")
    loaded = Config(file=str(path))
    # Whatever loading wrote back is the "previous version" the tests protect.
    loaded.previous = path.read_bytes()
    return loaded


def rename_hero(config) -> None:
    for node in config.doc.getElementsByTagName("site"):
        node.setAttribute("screen_name", "alice")


def leftovers(config) -> list[str]:
    return sorted(p.name for p in Path(config.file).parent.iterdir() if p.name.endswith(".tmp"))


class _HalfWritten:
    """A stream that writes half of what it is given, then finds the disk full."""

    def __init__(self, raw) -> None:
        self.raw = raw

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> None:
        self.raw.close()

    def write(self, data: bytes) -> int:
        self.raw.write(data[: len(data) // 2])
        self.raw.flush()
        raise OSError(errno.ENOSPC, "No space left on device")


# --------------------------------------------------------------------------
# A save that fails leaves the previous file whole
# --------------------------------------------------------------------------


def test_a_write_cut_short_halfway_leaves_the_previous_file(config, monkeypatch) -> None:
    real_fdopen = os.fdopen
    monkeypatch.setattr(config_module.os, "fdopen", lambda fd, *a, **k: _HalfWritten(real_fdopen(fd, *a, **k)))
    rename_hero(config)

    with pytest.raises(OSError, match="No space left"):
        config.save()

    assert Path(config.file).read_bytes() == config.previous
    assert leftovers(config) == []


def test_a_write_that_never_reaches_the_disk_leaves_the_previous_file(config, monkeypatch) -> None:
    def full(_fd) -> None:
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(config_module.os, "fsync", full)
    rename_hero(config)

    with pytest.raises(OSError):
        config.save()

    assert Path(config.file).read_bytes() == config.previous
    assert leftovers(config) == []


def test_a_replace_that_fails_leaves_the_previous_file(config, monkeypatch) -> None:
    def refuse(*_args) -> None:
        raise PermissionError(errno.EACCES, "Permission denied")

    monkeypatch.setattr(config_module.os, "replace", refuse)
    rename_hero(config)

    with pytest.raises(PermissionError):
        config.save()

    assert Path(config.file).read_bytes() == config.previous
    assert leftovers(config) == []


def test_failed_saves_never_reach_the_backup(config, monkeypatch) -> None:
    # The old save moved the file aside before writing: after one failure the
    # configuration was truncated, and the next save moved that over the backup.
    real_fdopen = os.fdopen
    monkeypatch.setattr(config_module.os, "fdopen", lambda fd, *a, **k: _HalfWritten(real_fdopen(fd, *a, **k)))
    rename_hero(config)

    for _attempt in range(2):
        with pytest.raises(OSError):
            config.save()

    assert Path(config.file).read_bytes() == config.previous
    backup = Path(f"{config.file}.backup")
    assert not backup.exists() or backup.read_bytes() == config.previous


# --------------------------------------------------------------------------
# A save that succeeds
# --------------------------------------------------------------------------


def test_a_save_writes_the_new_file_and_backs_up_the_previous_one(config) -> None:
    rename_hero(config)

    config.save()

    assert 'screen_name="alice"' in Path(config.file).read_text(encoding="utf-8")
    assert Path(f"{config.file}.backup").read_bytes() == config.previous
    assert leftovers(config) == []


def test_the_file_is_written_byte_for_byte_with_unix_line_ends(config) -> None:
    # The old writer used codecs.open, a binary stream; a text stream would
    # turn every line end into CRLF on Windows.
    config.save()

    assert Path(config.file).read_bytes() == config.wrap_long_lines(config.doc.toxml()).encode("utf-8")


@posix_only
def test_a_save_keeps_the_file_permissions(config) -> None:
    Path(config.file).chmod(0o640)

    config.save()

    assert Path(config.file).stat().st_mode & 0o777 == 0o640


@posix_only
def test_a_file_saved_under_a_new_name_gets_the_usual_permissions(config, tmp_path) -> None:
    mask = os.umask(0)
    os.umask(mask)
    exported = tmp_path / "exported.xml"

    config.save(file=str(exported))

    assert exported.stat().st_mode & 0o777 == 0o666 & ~mask


@posix_only
def test_a_linked_configuration_is_written_through_its_link(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(config_module, "CONFIG_PATH", str(tmp_path / "cfgdir"))
    real = tmp_path / "dotfiles" / "HUD_config.xml"
    real.parent.mkdir()
    real.write_text(CONFIG_XML, encoding="utf-8")
    link = tmp_path / "HUD_config.xml"
    link.symlink_to(real)
    config = Config(file=str(link))
    rename_hero(config)

    config.save()

    assert link.is_symlink()
    assert 'screen_name="alice"' in real.read_text(encoding="utf-8")
