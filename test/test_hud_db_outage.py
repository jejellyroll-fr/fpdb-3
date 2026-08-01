"""Tests for the HUD's behaviour while the database is unreachable.

Every HUD database read runs on the Qt thread that repaints the windows. When
the database sits behind a VPN that drops, each read stalls that thread, so the
HUD froze once per hand for as long as the outage lasted -- and, because the
table-info lookup swallowed the error, it looked like hands that were merely not
committed yet, so the HUD stayed dead after the link came back.

HudMain now trips a breaker on the first lost connection: it stops querying,
hands the connection to DbRecoveryWorker (a thread, so the reconnect cost is not
paid on the UI thread), and resumes when that reports the link is back.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.qt

sys.path.insert(0, str(Path(__file__).parent.parent))


def _load_hud_main():
    """Load HUD_main.pyw, reusing the instance another test module loaded.

    Executing the source a second time would leave two module objects under the
    same name: patches applied by one test module would then miss the classes
    the other is using, and the ZMQ sockets bound by its fixtures would never be
    released.
    """
    existing = sys.modules.get("HUD_main")
    if existing is not None:
        return existing

    win_tables_module = types.ModuleType("WinTables")
    win_tables_module.Table = MagicMock()
    sys.modules["WinTables"] = win_tables_module

    source_file = Path(__file__).parent.parent / "fpdb_3_legacy" / "HUD_main.pyw"
    loader = importlib.machinery.SourceFileLoader("HUD_main", str(source_file))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules["HUD_main"] = module
    try:
        loader.exec_module(module)
    except (ImportError, ModuleNotFoundError) as exc:
        del sys.modules["HUD_main"]
        pytest.skip(f"HUD_main eager-load failed: {exc}", allow_module_level=True)
    return module


HUD_main = _load_hud_main()

psycopg = pytest.importorskip("psycopg")

from fpdb_3_legacy.Database import Database  # noqa: E402


def make_hud_main(**attrs):
    """A HudMain carrying only what the breaker touches.

    ``__new__`` skips ``__init__``, which would open a database connection and
    bind a ZMQ socket.
    """
    hud = HUD_main.HudMain.__new__(HUD_main.HudMain)
    hud.db_connection = MagicMock()
    hud.db_connection.backend = Database.PGSQL
    hud._db_available = True
    hud._db_recovery_worker = None
    hud._pending_hands = []
    hud.hud_dict = {}
    hud.cache = {}
    hud.started_recovery = 0

    def record_recovery() -> None:
        hud.started_recovery += 1

    hud._start_db_recovery = record_recovery
    for name, value in attrs.items():
        setattr(hud, name, value)
    return hud


def lost_connection_error():
    return psycopg.OperationalError("consuming input failed: server closed the connection unexpectedly")


def test_a_lost_connection_opens_the_breaker_once() -> None:
    hud = make_hud_main()

    assert hud.note_db_error(lost_connection_error()) is True
    assert hud._db_available is False
    assert hud.started_recovery == 1

    # Later failures during the same outage must not restart recovery.
    assert hud.note_db_error(lost_connection_error()) is True
    assert hud.started_recovery == 1


def test_an_ordinary_sql_error_leaves_the_breaker_closed() -> None:
    """A bad query is not an outage; the HUD must carry on serving hands."""
    hud = make_hud_main()

    assert hud.note_db_error(psycopg.ProgrammingError('column "nope" does not exist')) is False
    assert hud._db_available is True
    assert hud.started_recovery == 0


def test_table_info_reports_the_outage_instead_of_swallowing_it() -> None:
    """Returning None here is what made the HUD look merely out of date."""
    hud = make_hud_main()
    hud.db_connection.get_table_info.side_effect = lost_connection_error()

    assert hud._get_table_info("123") is None
    assert hud._db_available is False
    # No rollback attempt: the connection is gone and now belongs to recovery.
    hud.db_connection.connection.rollback.assert_not_called()


def test_hands_arriving_during_an_outage_are_dropped_not_queried() -> None:
    hud = make_hud_main(_db_available=False)

    hud.handle_message("456")

    assert hud._pending_hands == []
    hud.db_connection.connection.rollback.assert_not_called()


def test_a_pending_batch_is_dropped_rather_than_run_against_a_dead_link() -> None:
    hud = make_hud_main(_db_available=False, _pending_hands=["1", "2", "3"])

    hud._drain_pending_hands()

    assert hud._pending_hands == []
    hud.db_connection.get_table_info.assert_not_called()


def test_recovery_closes_the_breaker() -> None:
    hud = make_hud_main(_db_available=False)

    hud._on_db_recovered()

    assert hud._db_available is True


def test_recovery_worker_stops_at_the_first_success() -> None:
    """It must hand the connection back rather than keep polling it."""
    db = MagicMock()
    db.recover_connection.side_effect = [False, False, True]
    worker = HUD_main.DbRecoveryWorker(db)
    recovered = []
    worker.recovered.connect(lambda: recovered.append(True))

    # Drive run() inline, without the retry interval.
    HUD_main.DB_RECOVERY_INTERVAL_S, saved = 0.0, HUD_main.DB_RECOVERY_INTERVAL_S
    try:
        worker.run()
    finally:
        HUD_main.DB_RECOVERY_INTERVAL_S = saved

    assert db.recover_connection.call_count == 3
    assert recovered == [True]


def test_recovery_worker_survives_an_unexpected_failure() -> None:
    """A raising attempt must not end recovery -- the outage would be permanent."""
    db = MagicMock()
    db.recover_connection.side_effect = [RuntimeError("boom"), True]
    worker = HUD_main.DbRecoveryWorker(db)
    recovered = []
    worker.recovered.connect(lambda: recovered.append(True))

    HUD_main.DB_RECOVERY_INTERVAL_S, saved = 0.0, HUD_main.DB_RECOVERY_INTERVAL_S
    try:
        worker.run()
    finally:
        HUD_main.DB_RECOVERY_INTERVAL_S = saved

    assert db.recover_connection.call_count == 2
    assert recovered == [True]


def test_stopping_the_worker_ends_the_loop() -> None:
    db = MagicMock()
    db.recover_connection.return_value = False
    worker = HUD_main.DbRecoveryWorker(db)
    worker._stopping.set()

    worker.run()

    db.recover_connection.assert_not_called()
