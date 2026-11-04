"""POC tests for local-first sync: local SQLite -> server push (#680).

The HUD reads the local embedded database (0 RTT); LocalFirstSync pushes each
imported hand to the server asynchronously, deduplicated by
(siteHandNo, gametypeId), with the local->server id mapping kept in the outbox.
"""

from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.Importer import Importer
from fpdb_3_legacy.local_first_sync import LocalFirstSync
from tests.helpers import analytics_golden as golden
from tests.test_database_backend_integration import _enabled_backends

REPO = Path(__file__).resolve().parent.parent
ONE_FILE = REPO / "regression-test-files/cash/Stars/Flop/NLHE-6max-EUR-0.05-0.10-200911.txt"
TOURNEY_FILE = REPO / "regression-test-files/tour/Stars/Flop/NLHE-Play-STT-20110405.txt"


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
    # a local session id the server's foreign key would refuse
    c = local.connection.cursor()
    c.execute("UPDATE Hands SET sessionId = 4242")
    local.connection.commit()
    c.close()
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
    sync.release.assert_called_once()
    local.disconnect()


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
    first = [c.temp_key for c in service._bounded_secondary_tables(req, set())]
    second = [c.temp_key for c in service._bounded_secondary_tables(req, set())]
    third = [c.temp_key for c in service._bounded_secondary_tables(req, set())]
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


@pytest.fixture
def tourney_db(tmp_path):
    """A local database holding the hands of one tournament."""
    db = _sqlite_db(tmp_path, "tourney_local")
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=db.config, sql=None)
    importer.database = db
    importer.setCallHud(False)
    assert importer.addImportFile(str(TOURNEY_FILE), "auto")
    stored, *_rest = importer.runImport()
    assert stored >= 2
    yield db
    db.disconnect()


def _rows(db, query: str) -> list[tuple]:
    c = db.connection.cursor()
    c.execute(query)  # nosec B608  # nosemgrep
    rows = [tuple(r) for r in c.fetchall()]
    c.close()
    return rows


def _assert_tournament_links_hold(server) -> None:
    """Each pushed hand points at its tournament, each seat at its own entry in it."""
    hands = _rows(
        server, "SELECT h.id, h.tourneyId, t.siteTourneyNo FROM Hands h JOIN Tourneys t ON t.id = h.tourneyId"
    )
    assert hands
    seats = _rows(
        server,
        "SELECT hp.playerId, tp.playerId, h.tourneyId, tp.tourneyId FROM HandsPlayers hp "
        "JOIN Hands h ON h.id = hp.handId JOIN TourneysPlayers tp ON tp.id = hp.tourneysPlayersId",
    )
    assert seats
    assert all(
        hp_player == tp_player and h_tourney == tp_tourney for hp_player, tp_player, h_tourney, tp_tourney in seats
    )


def test_push_maps_tournament_hands_to_server_rows(tourney_db, server_db) -> None:
    """Server ids diverge from local ones: the hand, its seats and the tournament rows follow."""
    srv = server_db()
    for table in ("Players", "TourneyTypes", "Tourneys", "TourneysPlayers"):
        _insert_decoy_rows(srv, table)
    srv.disconnect()

    sync = LocalFirstSync(tourney_db, server_db, batch_size=1000, local_db_path=tourney_db.db_path)
    local_ids = _local_hand_ids(tourney_db)
    sync.mark(local_ids)
    assert sync.push_once() == len(local_ids)
    sync.stop()

    srv = server_db()
    _assert_tournament_links_hold(srv)
    local_no = _rows(tourney_db, "SELECT DISTINCT siteTourneyNo FROM Tourneys")
    assert _rows(srv, "SELECT DISTINCT t.siteTourneyNo FROM Hands h JOIN Tourneys t ON t.id = h.tourneyId") == local_no
    assert all(r[0] > 9000 for r in _rows(srv, "SELECT tourneyId FROM Hands"))
    assert all(r[0] > 9000 for r in _rows(srv, "SELECT tourneysPlayersId FROM HandsPlayers"))
    assert all(r[0] > 9000 for r in _rows(srv, "SELECT tourneyTypeId FROM Tourneys WHERE siteTourneyNo IS NOT NULL"))
    srv.disconnect()


def test_tournament_rows_are_not_duplicated_across_batches(tourney_db, server_db) -> None:
    sync = LocalFirstSync(tourney_db, server_db, batch_size=1, local_db_path=tourney_db.db_path)
    local_ids = _local_hand_ids(tourney_db)
    sync.mark(local_ids)
    for _ in local_ids:
        assert sync.push_once() == 1
    sync.stop()

    srv = server_db()
    for table in ("TourneyTypes", "Tourneys", "TourneysPlayers"):
        query = f"SELECT COUNT(*) FROM {table}"  # nosec B608  # nosemgrep
        assert _rows(srv, query) == _rows(tourney_db, query), table
    _assert_tournament_links_hold(srv)
    srv.disconnect()


def test_push_carries_only_the_tournaments_of_the_batch(tourney_db, server_db) -> None:
    """Tourneys grow with the hands played: a batch must not re-read them all."""
    _insert_decoy_rows(tourney_db, "Tourneys")
    sync = LocalFirstSync(tourney_db, server_db, batch_size=1000, local_db_path=tourney_db.db_path)
    sync.mark(_local_hand_ids(tourney_db))
    sync.push_once()
    sync.stop()

    srv = server_db()
    assert _rows(srv, "SELECT COUNT(*) FROM Tourneys") == [(1,)]
    srv.disconnect()


def test_push_leaves_out_referentials_the_batch_does_not_use(local_db, server_db) -> None:
    """Each row is a round trip, and Players and Files grow with everything ever imported."""
    for table in ("Players", "Files", "Gametypes"):
        _insert_decoy_rows(local_db, table)
    sync = LocalFirstSync(local_db, server_db, batch_size=1000)
    sync.mark(_local_hand_ids(local_db)[:1])
    assert sync.push_once() == 1

    srv = server_db()
    assert _rows(srv, "SELECT COUNT(*) FROM Players WHERE name = 'decoy'") == [(0,)]
    assert _rows(srv, "SELECT COUNT(*) FROM Files WHERE file = 'decoy'") == [(0,)]
    assert _rows(srv, "SELECT COUNT(*) FROM Gametypes WHERE currency = 'decoy'") == [(0,)]
    assert _rows(srv, "SELECT COUNT(*) FROM Players") == _rows(
        local_db,
        "SELECT COUNT(DISTINCT playerId) FROM HandsPlayers WHERE handId = (SELECT MIN(id) FROM Hands)",
    )
    srv.disconnect()


def test_a_hand_gone_from_the_local_database_does_not_stay_pending(local_db, server_db) -> None:
    """Oldest ids are read first: left pending, enough of these would fill every batch."""
    real = _local_hand_ids(local_db)[0]
    sync = LocalFirstSync(local_db, server_db, batch_size=1)
    gone = real - 1
    sync.mark([gone, real])

    assert sync.push_once() == 0
    assert sync.pending() == [real]
    assert sync.push_once() == 1
    assert not sync.pending()
    assert _rows(local_db, "SELECT server_hand_id FROM fpdb_sync_outbox ORDER BY local_hand_id")[0] == (None,)


def _hud_cache(db) -> list[tuple]:
    """HudCache without its id, which depends on the order a row was first written in,
    and with fractions rounded: a sum of them depends on the order of its terms."""
    c = db.connection.cursor()
    c.execute("SELECT * FROM HudCache")
    cols = [d[0] for d in c.description]
    rows = [
        tuple(round(float(v), 6) if isinstance(v, (float, Decimal)) else v for k, v in zip(cols, row) if k != "id")
        for row in c.fetchall()
    ]
    c.close()
    return sorted(rows, key=repr)


@pytest.mark.parametrize("batch_size", [1, 1000])
def test_pushed_hud_cache_matches_a_full_rebuild(tmp_path, server_db, batch_size) -> None:
    """The server's statistics after a push are what a rebuild from its facts gives."""
    local = _sqlite_db(tmp_path, "hud_local")
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=local.config, sql=None)
    importer.database = local
    importer.setCallHud(False)
    for path in (ONE_FILE, TOURNEY_FILE):
        assert importer.addImportFile(str(path), "auto")
    stored, *_rest = importer.runImport()
    assert stored >= 2

    sync = LocalFirstSync(local, server_db, batch_size=batch_size, local_db_path=local.db_path)
    local_ids = _local_hand_ids(local)
    sync.mark(local_ids)
    pushed = 0
    while sync.pending():
        pushed += sync.push_once()
    sync.stop()
    assert pushed == len(local_ids)
    local.disconnect()

    srv = server_db()
    pushed_cache = _hud_cache(srv)
    assert pushed_cache
    srv.rebuild_cache()
    assert pushed_cache == _hud_cache(srv)
    srv.disconnect()


def test_pushing_a_hand_twice_counts_it_once_in_the_hud_cache(local_db, server_db) -> None:
    local_ids = _local_hand_ids(local_db)[:1]
    sync = LocalFirstSync(local_db, server_db, batch_size=1000)
    sync.mark(local_ids)
    assert sync.push_once() == 1
    c = local_db.connection.cursor()
    c.execute("UPDATE fpdb_sync_outbox SET pushed = 0")
    local_db.connection.commit()
    c.close()
    srv = server_db()
    before = _hud_cache(srv)
    srv.disconnect()
    assert before

    sync.push_once()

    srv = server_db()
    assert _hud_cache(srv) == before
    srv.disconnect()


def test_a_failed_batch_leaves_no_hud_cache_behind(local_db, server_db, monkeypatch) -> None:
    sync = LocalFirstSync(local_db, server_db, batch_size=1000)
    local_ids = _local_hand_ids(local_db)[:2]
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
    srv = server_db()
    assert _hud_cache(srv) == []
    srv.disconnect()


def test_outbox_gets_the_hands_of_a_file_that_also_holds_summaries(tmp_path) -> None:
    """The summary resets database.hids: the hands must be registered before it runs."""
    local = _sqlite_db(tmp_path, "both_local")
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=local.config, sql=None)
    importer.database = local
    sync = MagicMock()
    importer._local_first_sync = sync

    def import_hands(fpdbfile):
        local.hids = [101, 102]
        fpdbfile.ftype = "both"
        return (2, 0, 0, 0, 0, 0.0, "PokerStars")

    importer._import_hh_file = import_hands
    importer._import_summary_file = lambda _fpdbfile: local.resetBulkCache(False)
    fpdbfile = MagicMock(ftype="hh", path="tourney.txt")
    importer._import_despatch(fpdbfile)

    assert not local.hids  # the summary did run and reset the buffer
    sync.mark.assert_called_once_with([101, 102])
    importer._local_first_sync = None
    local.disconnect()


def test_push_keeps_the_results_the_server_already_has(tourney_db, server_db) -> None:
    """Another machine may have imported the summary: a local NULL must not erase it."""
    local_ids = _local_hand_ids(tourney_db)
    sync = LocalFirstSync(tourney_db, server_db, batch_size=1, local_db_path=tourney_db.db_path)
    sync.mark(local_ids[:1])
    assert sync.push_once() == 1

    srv = server_db()
    c = srv.connection.cursor()
    c.execute("UPDATE TourneysPlayers SET winnings = 12345")
    srv.connection.commit()
    c.close()
    srv.disconnect()

    sync.mark(local_ids[1:2])
    assert sync.push_once() == 1
    sync.stop()

    srv = server_db()
    known = _rows(srv, "SELECT COUNT(*) FROM TourneysPlayers WHERE winnings = 12345")
    assert known[0][0] > 0
    srv.disconnect()


def test_push_does_not_carry_the_tourneys_local_session_id(tourney_db, server_db) -> None:
    c = tourney_db.connection.cursor()
    c.execute("UPDATE Tourneys SET sessionId = 4242")
    tourney_db.connection.commit()
    c.close()
    sync = LocalFirstSync(tourney_db, server_db, batch_size=1000, local_db_path=tourney_db.db_path)
    sync.mark(_local_hand_ids(tourney_db))
    sync.push_once()
    sync.stop()

    srv = server_db()
    assert _rows(srv, "SELECT sessionId FROM Tourneys") == [(None,)]
    srv.disconnect()


@pytest.mark.integration
@pytest.mark.parametrize("backend", ["postgresql", "mysql"])
def test_push_tournament_hands_to_a_live_backend(backend: str, tourney_db) -> None:
    """Foreign keys, boolean columns and the reserved ``rank`` only exist on real servers."""
    if backend not in _enabled_backends():
        pytest.skip(f"live {backend} service not requested")
    from fpdb_3_legacy.Configuration import Config

    env = "POSTGRES" if backend == "postgresql" else "MYSQL"
    config = Config(file=str(REPO / "HUD_config.xml"))
    params = config.get_db_parameters()
    params.update(
        {
            "db-server": backend,
            "db-backend": Database.PGSQL if backend == "postgresql" else Database.MYSQL_INNODB,
            "db-host": os.environ.get(f"FPDB_{env}_HOST", "127.0.0.1"),
            "db-port": int(os.environ.get(f"FPDB_{env}_PORT", "5432" if backend == "postgresql" else "3306")),
            "db-databaseName": os.environ.get(f"FPDB_{env}_DB", "fpdb"),
            "db-user": os.environ.get(f"FPDB_{env}_USER", "fpdb"),
            "db-password": os.environ.get(f"FPDB_{env}_PASSWORD", "fpdb"),
            "db-path": "",
        }
    )
    config.get_db_parameters = lambda: params
    server = Database(config)
    server.recreate_tables()

    c = tourney_db.connection.cursor()
    c.execute("UPDATE Hands SET sessionId = 4242")
    c.execute("UPDATE Tourneys SET sessionId = 4242")
    tourney_db.connection.commit()
    c.close()

    # Two batches, as the production worker does, through its own local connection:
    # the second one finds every referential row already on the server.
    sync = LocalFirstSync(tourney_db, lambda: Database(config), batch_size=2, local_db_path=tourney_db.db_path)
    local_ids = _local_hand_ids(tourney_db)
    sync.mark(local_ids[:4])
    assert sync.push_once() == 2
    assert sync.push_once() == 2
    sync.stop()

    server.connection.commit()
    _assert_tournament_links_hold(server)
    for table in ("Gametypes", "TourneyTypes", "Tourneys"):
        query = f"SELECT COUNT(*) FROM {table}"  # nosec B608  # nosemgrep
        assert _rows(server, query) == _rows(tourney_db, query), table
    assert _rows(server, "SELECT COUNT(*) FROM Hands") == [(4,)]
    assert _rows(server, "SELECT COUNT(sessionId) FROM Hands") == [(0,)]
    pushed_cache = _hud_cache(server)
    assert pushed_cache
    server.rebuild_cache()
    server.connection.commit()
    assert pushed_cache == _hud_cache(server)
    server.close_connection()


def _gametype_with(db, gametype_id: int, **changes) -> int:
    """Clone a Gametypes row with some columns changed; returns the new id."""
    c = db.connection.cursor()
    c.execute("SELECT * FROM Gametypes WHERE id = ?", (gametype_id,))
    row = dict(zip([d[0] for d in c.description], c.fetchone()))
    del row["id"]
    row.update(changes)
    ph = ", ".join(["?"] * len(row))
    c.execute(f"INSERT INTO Gametypes ({', '.join(row)}) VALUES ({ph})", list(row.values()))  # nosec B608  # nosemgrep
    new_id = c.lastrowid
    db.connection.commit()
    c.close()
    return new_id


def test_push_keeps_game_types_of_different_stakes_apart(local_db, server_db) -> None:
    """Same variant at other stakes: each hand keeps its own server game type."""
    local_ids = _local_hand_ids(local_db)
    assert len(local_ids) >= 2
    c = local_db.connection.cursor()
    c.execute("SELECT gametypeId FROM Hands WHERE id = ?", (local_ids[0],))
    local_gametype_id = c.fetchone()[0]
    c.close()
    higher = _gametype_with(local_db, local_gametype_id, smallBlind=5000, bigBlind=10000)
    c = local_db.connection.cursor()
    c.execute("UPDATE Hands SET gametypeId = ? WHERE id = ?", (higher, local_ids[1]))
    c.execute("SELECT siteHandNo FROM Hands WHERE id = ?", (local_ids[1],))
    moved_hand = c.fetchone()[0]
    local_db.connection.commit()
    c.close()

    sync = LocalFirstSync(local_db, server_db, batch_size=1000)
    sync.mark(local_ids[:2])
    assert sync.push_once() == 2

    srv = server_db()
    c = srv.connection.cursor()
    c.execute(
        "SELECT h.siteHandNo, g.bigBlind FROM Hands h JOIN Gametypes g ON g.id = h.gametypeId ORDER BY h.id",
    )
    blinds = dict(c.fetchall())
    c.close()
    srv.disconnect()
    assert len(set(blinds.values())) == 2
    assert blinds[moved_hand] == 10000


def test_push_finds_existing_game_types_with_null_columns(local_db, server_db) -> None:
    """A NULL column must not defeat the lookup and duplicate the row per batch."""
    local_ids = _local_hand_ids(local_db)
    c = local_db.connection.cursor()
    c.execute("UPDATE Gametypes SET fast = NULL, smallBlind = NULL")
    local_db.connection.commit()
    c.close()

    for local_id in local_ids[:2]:
        sync = LocalFirstSync(local_db, server_db, batch_size=1000)
        sync.mark([local_id])
        assert sync.push_once() == 1

    srv = server_db()
    c = srv.connection.cursor()
    c.execute("SELECT COUNT(*) FROM Gametypes")
    count = c.fetchone()[0]
    c.close()
    srv.disconnect()
    c = local_db.connection.cursor()
    c.execute("SELECT COUNT(*) FROM Gametypes")
    assert count == c.fetchone()[0]
    c.close()


def test_push_casts_boolean_lookup_values_for_the_server(local_db, server_db) -> None:
    """PostgreSQL rejects ``fast = 0``: lookups must bind real booleans."""
    sync = LocalFirstSync(local_db, server_db, batch_size=1000)
    sync._bool_columns["Gametypes"] = {"fast", "newtogame", "homegame", "split"}
    seen = []
    srv = server_db()
    real_cursor = srv.connection.cursor

    class SpyCursor:
        def __init__(self) -> None:
            self._c = real_cursor()

        def execute(self, q, params=()):
            if q.startswith("SELECT id FROM Gametypes"):
                seen.append(list(params))
            return self._c.execute(q, params)

        def __getattr__(self, name):
            return getattr(self._c, name)

    class SpyConnection:
        def cursor(self):
            return SpyCursor()

    server = MagicMock(connection=SpyConnection())
    server.get_last_insert_id = srv.get_last_insert_id
    sync._push_referentials(server, _local_hand_ids(local_db), "?")
    srv.disconnect()
    assert seen
    assert all(any(p is False or p is True for p in params) for params in seen)


def test_push_remaps_site_of_referentials_when_server_ids_diverge(local_db, server_db) -> None:
    """A local site with another id on the server: its players and game types follow."""
    c = local_db.connection.cursor()
    c.execute("SELECT id, name FROM Sites WHERE id = (SELECT MIN(siteId) FROM Gametypes)")
    local_site_id, site_name = c.fetchone()
    c.close()
    srv = server_db()
    c = srv.connection.cursor()
    c.execute("PRAGMA foreign_keys = OFF")
    c.execute("UPDATE Sites SET id = 7777 WHERE name = ?", (site_name,))
    srv.connection.commit()
    c.close()
    srv.disconnect()
    assert local_site_id != 7777

    sync = LocalFirstSync(local_db, server_db, batch_size=1000)
    sync.mark(_local_hand_ids(local_db)[:1])
    assert sync.push_once() == 1

    srv = server_db()
    c = srv.connection.cursor()
    c.execute("SELECT DISTINCT siteId FROM Gametypes")
    assert c.fetchall() == [(7777,)]
    c.execute("SELECT DISTINCT siteId FROM Players")
    assert (7777,) in c.fetchall()
    c.close()
    srv.disconnect()


def test_push_does_not_carry_the_local_session_id(local_db, server_db) -> None:
    """Sessions are not pushed: the server's FK would fail, or hit a foreign session."""
    local_ids = _local_hand_ids(local_db)
    c = local_db.connection.cursor()
    c.execute("UPDATE Hands SET sessionId = 4242 WHERE id = ?", (local_ids[0],))
    local_db.connection.commit()
    c.close()

    sync = LocalFirstSync(local_db, server_db, batch_size=1000)
    sync.mark(local_ids[:1])
    assert sync.push_once() == 1

    srv = server_db()
    c = srv.connection.cursor()
    c.execute("SELECT sessionId FROM Hands")
    assert c.fetchall() == [(None,)]
    c.close()
    srv.disconnect()


def _local_first_importer(tmp_path, monkeypatch):
    """An Importer in local-first mode: relative local_path, SQLite catalogue
    passed in as the GUI does, PostgreSQL as the server."""
    from fpdb_3_legacy import SQL

    config = golden.build_config(tmp_path)
    config.dir_database = str(tmp_path)
    params = dict(config.get_db_parameters(), **{"db-local-first": "1", "db-databaseName": "relative-local.sqlite3"})
    config.get_db_parameters = lambda: params
    config.get_server_db_parameters = lambda: dict(
        params,
        **{"db-server": "postgresql", "db-backend": Database.PGSQL, "db-databaseName": "fpdb", "db-local-first": "0"},
    )
    monkeypatch.chdir(tmp_path / "cwd")
    return Importer(
        caller=None, settings={"testData": False, "threads": 1}, config=config, sql=SQL.Sql(db_server="sqlite")
    )


def test_importer_sync_opens_the_database_the_importer_writes(tmp_path, monkeypatch) -> None:
    (tmp_path / "cwd").mkdir()
    importer = _local_first_importer(tmp_path, monkeypatch)
    try:
        sync = importer._local_first_sync
        assert sync is not None
        c = sync._local_conn().cursor()
        c.execute("PRAGMA database_list")
        opened = Path(c.fetchone()[2])
        c.close()
        assert opened.resolve() == Path(importer.database.db_path).resolve()
        assert opened.resolve() == (tmp_path / "relative-local.sqlite3").resolve()
        assert not (tmp_path / "cwd" / "relative-local.sqlite3").exists()
    finally:
        importer.close()


def test_importers_of_one_local_database_share_one_worker(tmp_path, monkeypatch) -> None:
    (tmp_path / "cwd").mkdir()
    first = _local_first_importer(tmp_path, monkeypatch)
    second = Importer(caller=None, settings={"testData": False, "threads": 1}, config=first.config, sql=first.sql)
    sync = first._local_first_sync
    try:
        assert second._local_first_sync is sync
        first.close()
        assert sync._thread.is_alive()  # the other Importer still needs it
    finally:
        second.close()
        first.close()
    assert not sync._thread.is_alive()


def test_importer_sync_builds_the_server_connection_with_its_own_dialect(tmp_path, monkeypatch) -> None:
    (tmp_path / "cwd").mkdir()
    importer = _local_first_importer(tmp_path, monkeypatch)
    try:
        monkeypatch.setattr(Database, "_connect_and_configure", lambda self, c: None)
        server = importer._local_first_sync.server_db_factory()
        assert server.backend == Database.PGSQL
        assert server.sql.query["placeholder"] == "%s"
        assert importer.database.sql.query["placeholder"] == "?"
    finally:
        importer.close()


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


def test_server_column_quotes_rank_only_on_mysql() -> None:
    """``rank`` is reserved on MySQL 8, and a backtick is a syntax error elsewhere."""
    mysql, postgres = MagicMock(backend=Database.MYSQL_INNODB), MagicMock(backend=Database.PGSQL)
    assert LocalFirstSync._server_column(mysql, "rank") == "`rank`"
    assert LocalFirstSync._server_column(mysql, "entryId") == "entryId"
    assert LocalFirstSync._server_column(postgres, "rank") == "rank"
