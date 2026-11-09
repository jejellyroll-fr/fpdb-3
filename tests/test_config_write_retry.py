"""Atomic config writes under a briefly locked target, and change detection (#741).

_replace_with renames a fully written temporary file over the target. On
Windows another process (the HUD writing its layout, or the OS indexing the
file) can hold the target open for a moment, which makes os.replace fail with
PermissionError; the write must retry briefly and, when that is not enough,
leave the previous file whole. Config.changed_on_disk is what lets a process
notice the other process wrote the file in between.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

import fpdb_3_legacy.Configuration as config_module
from fpdb_3_legacy.Configuration import CONFIG_VERSION, Config

DATABASE = '<database db_name="fpdb" db_server="sqlite" db_ip="" db_user="" db_pass="" db_desc="test"/>'

CONFIG_XML = (
    '<?xml version="1.0"?>\n<FreePokerToolsConfig>\n'
    f'<general version="{CONFIG_VERSION}"/>\n'
    f"<supported_databases>{DATABASE}</supported_databases>\n"
    "</FreePokerToolsConfig>\n"
)


@pytest.fixture
def build(tmp_path, monkeypatch):
    monkeypatch.setattr(config_module, "CONFIG_PATH", str(tmp_path / "cfgdir"))

    def make() -> Config:
        path = tmp_path / "HUD_config.xml"
        path.write_text(CONFIG_XML, encoding="utf-8")
        return Config(file=str(path))

    return make


def test_replace_retries_while_the_target_is_briefly_locked(build, monkeypatch) -> None:
    config = build()
    target = str(Path(config.file))
    real_replace = os.replace
    attempts = {"n": 0}

    def flaky_replace(src, dst):
        if os.fspath(dst) == target:
            attempts["n"] += 1
            if attempts["n"] <= 2:
                raise PermissionError(13, "Permission denied", os.fspath(dst))
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", flaky_replace)
    monkeypatch.setattr(time, "sleep", lambda *_args: None)  # do not really wait out the backoff

    config.save()

    assert attempts["n"] == 3
    assert "<database" in Path(config.file).read_text(encoding="utf-8")


def test_replace_gives_up_after_bounded_retries_and_leaves_the_file_whole(build, monkeypatch) -> None:
    config = build()
    original = Path(config.file).read_bytes()
    target = str(Path(config.file))
    real_replace = os.replace
    attempts = {"n": 0}

    def locked_replace(src, dst):
        if os.fspath(dst) == target:
            attempts["n"] += 1
            raise PermissionError(13, "Permission denied", os.fspath(dst))
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", locked_replace)
    monkeypatch.setattr(time, "sleep", lambda *_args: None)

    with pytest.raises(PermissionError):
        config.save()

    assert attempts["n"] == 5
    assert Path(config.file).read_bytes() == original
    # The half-written temporary file must not linger beside the target.
    assert not list(Path(config.file).parent.glob(".*.tmp"))


def test_changed_on_disk_tracks_external_writes_reloads_and_own_saves(build) -> None:
    config = build()
    assert config.changed_on_disk() is False

    path = Path(config.file)
    path.write_bytes(path.read_bytes() + b"<!-- touched by the other process -->")
    future = time.time() + 10
    os.utime(path, (future, future))
    assert config.changed_on_disk() is True

    assert config.reload() is True
    assert config.changed_on_disk() is False

    path.write_bytes(path.read_bytes() + b"<!-- touched again -->")
    os.utime(path, (future + 10, future + 10))
    assert config.changed_on_disk() is True

    # A save of this very object is not an external change.
    config.save()
    assert config.changed_on_disk() is False
