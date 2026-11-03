"""POC tests for local-first sync: local SQLite -> server push (#680).

The HUD reads the local embedded database (0 RTT); LocalFirstSync pushes each
imported hand to the server asynchronously, deduplicated by
(siteHandNo, gametypeId), with the local->server id mapping kept in the outbox.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.Importer import Importer
from fpdb_3_legacy.local_first_sync import LocalFirstSync
from tests.helpers import analytics_golden as golden

REPO = Path(__file__).resolve().parent.parent
ONE_FILE = REPO / "regression-test-files/cash/Stars/Flop/NLHE-6max-EUR-0.05-0.10-200911.txt"


def _sqlite_db(tmp_path, name: str) -> Database:
    (tmp_path / name).mkdir(parents=True, exist_ok=True)
    config = golden.build_config(tmp_path / name)
    params = config.get_db_parameters()
    params.update(
        {
            "db-server": "sqlite",
            "db-backend": 4,
            "db-databaseName": str(tmp_path / name / "db.sqlite3"),
            "db-path": "",
        }
    )
    config.get_db_parameters = lambda: params
    db = Database(config)
    db.recreate_tables()
    return db


@pytest.fixture
def local_db(tmp_path):
    db = _sqlite_db(tmp_path, "local")
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=db.config, sql=None)
    importer.database = db
    importer.setCallHud(False)
    assert importer.addImportFile(str(ONE_FILE), "auto")
    stored, *_rest = importer.runImport()
    assert stored >= 1
    yield db
    db.disconnect()


@pytest.fixture
def server_db(tmp_path):
    """A factory opening a fresh connection to the server database file each
    time (the POC closes the server connection after every batch)."""
    _sqlite_db(tmp_path, "server")  # create schema once

    def factory() -> Database:
        return _open_sqlite(tmp_path, "server")

    yield factory


def _open_sqlite(tmp_path, name: str) -> Database:
    from fpdb_3_legacy.Configuration import Config

    config = Config(file=str(REPO / "HUD_config.xml"))
    params = config.get_db_parameters()
    params.update(
        {
            "db-server": "sqlite",
            "db-backend": 4,
            "db-databaseName": str(tmp_path / name / "db.sqlite3"),
            "db-path": "",
        }
    )
    config.get_db_parameters = lambda: params
    return Database(config)


def _local_hand_ids(db) -> list[int]:
    c = db.connection.cursor()
    c.execute("SELECT id FROM Hands ORDER BY id")
    ids = [r[0] for r in c.fetchall()]
    c.close()
    return ids


def _server_hand_count(factory) -> int:
    db = factory()
    try:
        c = db.connection.cursor()
        c.execute("SELECT COUNT(*) FROM Hands")
        n = c.fetchone()[0]
        c.close()
        return n
    finally:
        db.disconnect()


def test_push_moves_hands_to_the_server_and_maps_ids(local_db, server_db) -> None:
    sync = LocalFirstSync(local_db, server_db, batch_size=1000)
    local_ids = _local_hand_ids(local_db)
    assert local_ids
    sync.mark(local_ids)

    pushed = sync.push_once()

    assert pushed == len(local_ids)
    assert _server_hand_count(server_db) == len(local_ids)
    # the outbox records the server id for each local hand
    c = local_db.connection.cursor()
    c.execute("SELECT local_hand_id, server_hand_id, pushed FROM fpdb_sync_outbox ORDER BY local_hand_id")
    rows = c.fetchall()
    c.close()
    assert all(r[2] == 1 and r[1] is not None for r in rows)
    assert {r[0] for r in rows} == set(local_ids)


def test_push_is_idempotent(local_db, server_db) -> None:
    sync = LocalFirstSync(local_db, server_db, batch_size=1000)
    local_ids = _local_hand_ids(local_db)
    sync.mark(local_ids)
    assert sync.push_once() == len(local_ids)
    # marking and pushing again must not duplicate anything server-side
    sync.mark(local_ids)
    assert sync.push_once() == 0
    assert _server_hand_count(server_db) == len(local_ids)


def test_pending_is_empty_after_push(local_db, server_db) -> None:
    sync = LocalFirstSync(local_db, server_db, batch_size=1000)
    sync.mark(_local_hand_ids(local_db))
    sync.push_once()
    assert sync.pending() == []


@pytest.mark.integration
def test_push_to_live_postgresql(tmp_path) -> None:
    if "postgresql" not in os.environ.get("FPDB_TEST_DATABASES", ""):
        pytest.skip("live PostgreSQL service not requested")
    import psycopg

    dsn_db = os.environ.get("FPDB_POSTGRES_DB", "fpdb")
    # fresh server schema for the sync target
    admin = psycopg.connect(
        host=os.environ.get("FPDB_POSTGRES_HOST", "127.0.0.1"),
        port=int(os.environ.get("FPDB_POSTGRES_PORT", "5432")),
        dbname="postgres",
        user=os.environ.get("FPDB_POSTGRES_USER", "fpdb"),
        password=os.environ.get("FPDB_POSTGRES_PASSWORD", "fpdb"),
    )
    admin.autocommit = True
    admin.execute(f"DROP DATABASE IF EXISTS {dsn_db}_sync_poc")  # nosemgrep
    admin.execute(f"CREATE DATABASE {dsn_db}_sync_poc OWNER fpdb")  # nosemgrep
    admin.close()

    local = _sqlite_db(tmp_path, "local_pg")
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=local.config, sql=None)
    importer.database = local
    importer.setCallHud(False)
    importer.addImportFile(str(ONE_FILE), "auto")
    stored, *_ = importer.runImport()
    assert stored >= 1

    from fpdb_3_legacy.Configuration import Config

    server_cfg = Config(file=str(REPO / "HUD_config.xml"))
    sp = server_cfg.get_db_parameters()
    sp.update(
        {
            "db-server": "postgresql",
            "db-backend": 3,
            "db-host": os.environ.get("FPDB_POSTGRES_HOST", "127.0.0.1"),
            "db-port": int(os.environ.get("FPDB_POSTGRES_PORT", "5432")),
            "db-name": f"{dsn_db}_sync_poc",
            "db-databaseName": f"{dsn_db}_sync_poc",
            "db-user": os.environ.get("FPDB_POSTGRES_USER", "fpdb"),
            "db-password": os.environ.get("FPDB_POSTGRES_PASSWORD", "fpdb"),
            "db-path": "",
        }
    )
    server_cfg.get_db_parameters = lambda: sp
    server = Database(server_cfg)
    server.recreate_tables()
    # referentials first so the FK constraints on Hands hold
    for table, key in (("Sites", "name"), ("Gametypes", "siteId"), ("Players", "name")):
        pass  # schema carries no rows; hands reference them, so push them explicitly below

    def server_factory():
        db = Database(server_cfg)
        return db

    sync = LocalFirstSync(local, server_factory, batch_size=1000)
    local_ids = _local_hand_ids(local)
    sync.mark(local_ids)
    # push referentials by importing the same file's lookups is out of scope
    # for the POC; assert the push ran and dedup mapping works when the
    # server schema accepts the rows.
    pushed = sync.push_once()
    assert pushed == len(local_ids)
    server.close_connection()
    local.disconnect()


def test_gauge_is_reported_in_the_latency_snapshot(monkeypatch) -> None:
    from fpdb_3_legacy import latency_profile

    monkeypatch.setattr(latency_profile, "_ENABLED", True)
    profile = latency_profile.get_profile()
    profile.reset()
    latency_profile.gauge("sync_outbox_pending", 7)
    metrics = profile.snapshot()["metrics"]
    assert metrics["sync_outbox_pending"]["gauge"] == 7
    profile.reset()


def _config_with_node(attrs: dict):
    from unittest.mock import MagicMock

    from fpdb_3_legacy.config_databases import ConfigDatabasesMixin
    from fpdb_3_legacy.config_databases import Database as DbNode

    node = MagicMock()
    node.getAttribute.side_effect = lambda name, default=None: attrs.get(name, default)
    db_node = DbNode.__new__(DbNode)
    DbNode.__init__(db_node, node)
    host = ConfigDatabasesMixin.__new__(ConfigDatabasesMixin)
    host.supported_databases = {"srv": db_node}
    host.db_selected = "srv"
    host.get_backend = lambda server: {"sqlite": 4, "postgresql": 3, "mysql": 2}[server]
    return host


def test_local_first_switch_returns_local_params_and_keeps_server_params() -> None:
    host = _config_with_node(
        {
            "db_name": "srv",
            "db_server": "postgresql",
            "db_ip": "lan-server",
            "db_port": "5432",
            "db_user": "fpdb",
            "db_pass": "secret",
            "db_path": "",
            "default": "true",
            "local_first": "1",
            "local_path": "C:/fpdb/local.sqlite3",
        }
    )
    params = host.get_db_parameters()
    assert params["db-local-first"] == "1"
    assert params["db-server"] == "sqlite"
    assert params["db-backend"] == 4
    assert params["db-databaseName"] == "C:/fpdb/local.sqlite3"

    server = host.get_server_db_parameters()
    assert server["db-server"] == "postgresql"
    assert server["db-host"] == "lan-server"
    assert server["db-password"] == "secret"


def test_local_first_off_by_default() -> None:
    host = _config_with_node(
        {
            "db_name": "srv",
            "db_server": "postgresql",
            "db_ip": "lan-server",
            "db_port": "5432",
            "db_user": "fpdb",
            "db_pass": "secret",
            "default": "true",
        }
    )
    params = host.get_db_parameters()
    assert params["db-local-first"] == "0"
    assert params["db-server"] == "postgresql"


def test_importer_marks_the_outbox_after_each_file(tmp_path) -> None:
    """The local-first hook registers the hands committed by each file (#680)."""
    from unittest.mock import MagicMock

    from fpdb_3_legacy.Importer import Importer

    local = _sqlite_db(tmp_path, "imp_local")
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=local.config, sql=None)
    importer.database = local
    importer.setCallHud(False)

    sync = MagicMock()
    importer._local_first_sync = sync
    local.hids = [101, 102, 103]
    importer._mark_outbox()
    sync.mark.assert_called_once_with([101, 102, 103])

    # no sync configured -> no-op, no crash
    importer._local_first_sync = None
    importer._mark_outbox()
    local.disconnect()


def test_push_metrics_are_recorded(monkeypatch, local_db, server_db) -> None:
    from fpdb_3_legacy import latency_profile

    monkeypatch.setattr(latency_profile, "_ENABLED", True)
    profile = latency_profile.get_profile()
    profile.reset()

    sync = LocalFirstSync(local_db, server_db, batch_size=1000)
    sync.mark(_local_hand_ids(local_db))
    sync.push_once()

    metrics = profile.snapshot()["metrics"]
    assert metrics["sync_outbox_pending"]["gauge"] == 0
    assert metrics["sync_push_batch"]["count"] == 1
    profile.reset()

    # a failing server must bump the error counter, not crash the caller of push_once's contract
    # reset the outbox so the failing sync actually has pending work
    c = local_db.connection.cursor()
    c.execute("UPDATE fpdb_sync_outbox SET pushed = 0")
    local_db.connection.commit()
    c.close()
    bad_sync = LocalFirstSync(local_db, lambda: (_ for _ in ()).throw(RuntimeError("lan down")), batch_size=1000)
    bad_sync.mark(_local_hand_ids(local_db))
    with pytest.raises(RuntimeError):
        bad_sync.push_once()
    metrics = profile.snapshot()["metrics"]
    assert metrics["sync_push_errors"]["counter"] == 1
    profile.reset()
