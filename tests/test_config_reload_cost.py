"""Opening a dialog should not re-do work that has already been done.

fpdb reloads its configuration before opening most of its dialogs, and each
reload used to re-parse the shipped example configuration and reconnect to the
database. Neither is free: the example is a ~120 KB XML file, and the reconnect
is a round trip on the GUI thread that also empties the database read caches.
The tests here pin the cheap behaviour so it does not quietly come back.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import fpdb_3_legacy.Configuration as config_module
from fpdb_3_legacy.Database import Database

EXAMPLE = """<?xml version="1.0"?>
<FreePokerToolsConfig>
  <hud_ui label="From the example"/>
</FreePokerToolsConfig>
"""


@pytest.fixture(autouse=True)
def _clear_example_cache() -> Any:
    """Keep the module-level parse cache from leaking between tests."""
    config_module._EXAMPLE_DOC_CACHE.clear()
    yield
    config_module._EXAMPLE_DOC_CACHE.clear()


def write_example(tmp_path: Path, body: str = EXAMPLE) -> str:
    path = tmp_path / "HUD_config.xml.example"
    path.write_text(body, encoding="utf-8")
    return str(path)


class TestExampleConfigCache:
    def test_second_parse_reuses_the_first(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        example = write_example(tmp_path)
        parses = []
        real_parse = config_module.defusedxml.minidom.parse

        def counting_parse(path: str, *args: Any, **kwargs: Any) -> Any:
            parses.append(path)
            return real_parse(path, *args, **kwargs)

        monkeypatch.setattr(config_module.defusedxml.minidom, "parse", counting_parse)

        first = config_module._parse_example_config(example)
        second = config_module._parse_example_config(example)

        assert first is second
        assert parses == [example]

    def test_a_replaced_example_is_re_read(self, tmp_path: Path) -> None:
        example = write_example(tmp_path)
        first = config_module._parse_example_config(example)

        # A new file at the same path -- an upgrade dropping in a newer example
        # -- must not be served from the cache. Force a distinct mtime so the
        # test does not depend on filesystem timestamp resolution.
        Path(example).write_text(EXAMPLE.replace("From the example", "Updated"), encoding="utf-8")
        stat = Path(example).stat()
        import os

        os.utime(example, (stat.st_atime + 10, stat.st_mtime + 10))

        second = config_module._parse_example_config(example)

        assert second is not first
        assert second.getElementsByTagName("hud_ui")[0].getAttribute("label") == "Updated"

    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        assert config_module._parse_example_config(str(tmp_path / "absent.xml")) is None

    def test_unparsable_file_returns_none(self, tmp_path: Path) -> None:
        broken = tmp_path / "broken.xml.example"
        broken.write_text("<not-closed>", encoding="utf-8")
        assert config_module._parse_example_config(str(broken)) is None


class FakeConfig:
    """Just the two accessors Database reads back out of a config."""

    def __init__(self, **db_params: Any) -> None:
        self._db_params = {
            "db-backend": 4,
            "db-server": "sqlite",
            "db-databaseName": "fpdb.db3",
            "db-host": "localhost",
            **db_params,
        }

    def get_db_parameters(self) -> dict[str, Any]:
        return dict(self._db_params)

    def get_import_parameters(self) -> dict[str, Any]:
        return {"sessionTimeout": "45", "publicDB": True}

    def get_general_params(self) -> dict[str, Any]:
        return {"day_start": "6"}


def make_db(*, connected: bool) -> Database:
    """A Database with the attributes rebind_config touches, and nothing else."""
    db = Database.__new__(Database)
    db.backend = 4
    db.db_server = "sqlite"
    db.database = "fpdb.db3"
    db.host = "localhost"
    db.config = FakeConfig()
    db.import_options = {"sessionTimeout": "30", "publicDB": False}
    db.day_start = 0.0
    db.sessionTimeout = 30.0
    db.publicDB = False
    db._Database__connected = connected
    return db


class TestRebindConfig:
    def test_same_database_keeps_the_connection_and_refreshes_values(self) -> None:
        db = make_db(connected=True)
        new_config = FakeConfig()

        assert db.rebind_config(new_config) is True
        assert db.config is new_config
        # The values __init__ derives from the config follow the reload, so a
        # kept connection never serves stale import settings.
        assert db.sessionTimeout == 45.0
        assert db.publicDB is True
        assert db.day_start == 6.0

    def test_a_different_database_refuses_the_rebind(self) -> None:
        db = make_db(connected=True)
        moved = FakeConfig(**{"db-databaseName": "other.db3"})

        assert db.rebind_config(moved) is False
        assert db.config is not moved

    def test_a_different_host_refuses_the_rebind(self) -> None:
        db = make_db(connected=True)
        assert db.rebind_config(FakeConfig(**{"db-host": "remote"})) is False

    def test_a_different_backend_refuses_the_rebind(self) -> None:
        db = make_db(connected=True)
        assert db.rebind_config(FakeConfig(**{"db-backend": 2, "db-server": "postgresql"})) is False

    def test_a_closed_connection_refuses_the_rebind(self) -> None:
        db = make_db(connected=False)
        assert db.rebind_config(FakeConfig()) is False
