"""POC tests for local-first sync: local SQLite -> server push (#680).

The HUD reads the local embedded database (0 RTT); LocalFirstSync pushes each
imported hand to the server asynchronously, deduplicated by
(siteHandNo, gametypeId), with the local->server id mapping kept in the outbox.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

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
    # schema carries no referential rows; hands reference them, so the push
    # must create them explicitly

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


def test_failed_batch_marks_nothing_and_is_retried(local_db, server_db, monkeypatch) -> None:
    """If the server transaction fails mid-batch, no hand may be marked pushed
    (the server rolled back, so marking would lose it) (#680 P0)."""
    sync = LocalFirstSync(local_db, server_db, batch_size=1000)
    local_ids = _local_hand_ids(local_db)
    sync.mark(local_ids)

    original = sync._push_hand
    calls = {"n": 0}

    def failing(server, local_id, sph):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("simulated LAN drop mid-batch")
        return original(server, local_id, sph)

    monkeypatch.setattr(sync, "_push_hand", failing)
    with pytest.raises(RuntimeError):
        sync.push_once()

    c = local_db.connection.cursor()
    c.execute("SELECT COUNT(*) FROM fpdb_sync_outbox WHERE pushed = 1")
    assert c.fetchone()[0] == 0
    c.close()
    # and a clean retry pushes everything
    monkeypatch.setattr(sync, "_push_hand", original)
    assert sync.push_once() == len(local_ids)


def test_stop_is_on_the_sync_and_importer_close_does_not_crash(tmp_path) -> None:  # pylint: disable=unused-argument
    """LocalFirstSync owns stop(); Importer.close() must not AttributeError (#680 P1)."""

    local = _sqlite_db(tmp_path, "imp_close")
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=local.config, sql=None)
    importer.database = local
    sync = MagicMock()
    importer._local_first_sync = sync
    importer.close()  # must not raise
    sync.stop.assert_called_once()
    local.disconnect()


def test_hand_batch_interval_ms_is_parsed_from_xml(tmp_path) -> None:  # pylint: disable=unused-argument
    """The XML attribute must reach get_hud_ui_parameters, not just mocks (#680 P1)."""
    import defusedxml.minidom

    from fpdb_3_legacy.config_hud_ui import ConfigHudUiMixin, HudUI

    xml = (
        '<FreePokerToolsConfig><general version="87"/>'
        '<hud_ui label="m" hand_batch_interval_ms="350"/></FreePokerToolsConfig>'
    )
    doc = defusedxml.minidom.parseString(xml)
    host = ConfigHudUiMixin.__new__(ConfigHudUiMixin)
    host.ui = HudUI(node=doc.getElementsByTagName("hud_ui")[0])
    assert host.get_hud_ui_parameters()["hand_batch_interval_ms"] == 350


def test_secondary_bound_rotates_instead_of_starving() -> None:
    """A capped secondary refresh must rotate tables, not always take the first (#680 P2)."""
    from fpdb_3_legacy.hud_read_service import HudBatchReadRequest, HudReadService, HudTableReadContext

    service = HudReadService.__new__(HudReadService)
    service._secondary_offset = 0

    def ctx(i):
        return HudTableReadContext(
            temp_key=f"t{i}",
            last_hand_id=str(i),
            hud_params={},
            poker_game="holdem",
            game_type="ring",
            site_id=1,
            num_seats=6,
        )

    tables = tuple(ctx(i) for i in range(4))
    req = HudBatchReadRequest(sequence=1, hand_ids=(), hud_params={"max_secondary_tables_per_batch": 1}, tables=tables)
    first = [c.temp_key for c in service._bounded_secondary_tables(req)]
    second = [c.temp_key for c in service._bounded_secondary_tables(req)]
    third = [c.temp_key for c in service._bounded_secondary_tables(req)]
    assert first != second != third
    assert {first[0], second[0], third[0]} == {"t0", "t1", "t2"}


def _insert_decoy_rows(db, table: str, decoy_id: int = 9000) -> None:
    """Insert a row with an explicit high id so the server's auto ids diverge
    from the local ones."""
    c = db.connection.cursor()
    c.execute(f"PRAGMA table_info({table})")  # nosec B608  # nosemgrep
    cols = c.fetchall()
    names, values = [], []
    for _cid, name, ctype, notnull, _dflt, _pk in cols:
        if name == "id":
            names.append(name)
            values.append(decoy_id)
        elif notnull and _dflt is None:
            names.append(name)
            t = (ctype or "").upper()
            if "INT" in t or "BOOL" in t:
                values.append(0)
            elif "TIME" in t or "DATE" in t:
                values.append("2020-01-01 00:00:00")
            else:
                values.append("decoy")
    ph = ", ".join(["?"] * len(names))
    c.execute(f"INSERT INTO {table} ({', '.join(names)}) VALUES ({ph})", values)  # nosec B608  # nosemgrep
    db.connection.commit()
    c.close()


def test_push_remaps_foreign_keys_when_server_ids_diverge(local_db, server_db) -> None:
    """Server already populated -> server ids differ from local ids; the push
    must remap gametypeId / playerId / handId instead of copying local ids."""
    c = local_db.connection.cursor()
    c.execute("SELECT id, gametypeId FROM Hands ORDER BY id LIMIT 1")
    local_hand_id, local_gametype_id = c.fetchone()
    c.execute("SELECT playerId FROM HandsPlayers WHERE handId = ? ORDER BY id LIMIT 1", (local_hand_id,))
    local_player_id = c.fetchone()[0]
    c.execute("SELECT name FROM Players WHERE id = ?", (local_player_id,))
    player_name = c.fetchone()[0]
    c.execute(
        "SELECT siteId, type, base, category, limitType, hiLo, mix FROM Gametypes WHERE id = ?",
        (local_gametype_id,),
    )
    gt_key = c.fetchone()
    c.execute("SELECT name FROM Sites WHERE id = ?", (gt_key[0],))
    site_name = c.fetchone()[0]
    c.close()
    # fresh local db: all referential ids start at 1
    assert (local_gametype_id, local_player_id) == (1, 1)

    # pre-populate the server with decoy rows so every pushed id is > 9000
    srv = server_db()
    for table in ("Sites", "Players", "Files", "Gametypes"):
        _insert_decoy_rows(srv, table)
    srv.disconnect()

    sync = LocalFirstSync(local_db, server_db, batch_size=1000)
    sync.mark([local_hand_id])
    assert sync.push_once() == 1

    srv = server_db()
    c = srv.connection.cursor()
    c.execute("SELECT id, gametypeId FROM Hands")
    server_hand_id, server_gametype_id = c.fetchone()
    assert server_gametype_id > 9000 and server_gametype_id != local_gametype_id
    # the pushed hand references the server gametype with the same natural key
    c.execute(
        "SELECT g.id FROM Gametypes g JOIN Sites s ON s.id = g.siteId "
        "WHERE s.name = ? AND g.type = ? AND g.base = ? AND g.category = ? "
        "AND g.limitType = ? AND g.hiLo = ? AND g.mix = ?",
        (site_name, *gt_key[1:]),
    )
    assert c.fetchone()[0] == server_gametype_id
    # HandsPlayers rows reference the server hand id and the server player id
    c.execute("SELECT handId, playerId FROM HandsPlayers")
    hp_hand_id, hp_player_id = c.fetchone()
    assert hp_hand_id == server_hand_id
    assert hp_player_id > 9000 and hp_player_id != local_player_id
    c.execute(
        "SELECT p.id FROM Players p JOIN Sites s ON s.id = p.siteId WHERE p.name = ? AND s.name = ?",
        (player_name, site_name),
    )
    assert c.fetchone()[0] == hp_player_id
    c.close()
    srv.disconnect()
