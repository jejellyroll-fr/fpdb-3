"""Live PostgreSQL checks for the HUD's read-transaction boundary."""

from __future__ import annotations

import importlib.machinery
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from fpdb_3_legacy.Database import Database
from test.test_database_backend_integration import _connection, _enabled_backends

pytestmark = pytest.mark.integration


def _load_hud_main():
    source = Path(__file__).parent.parent / "fpdb_3_legacy" / "HUD_main.pyw"
    loader = importlib.machinery.SourceFileLoader("HUD_main_postgresql_integration", str(source))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _backend_state(observer, backend_pid: int) -> str:
    with observer.cursor() as cursor:
        cursor.execute("SELECT state FROM pg_stat_activity WHERE pid = %s", (backend_pid,))
        return cursor.fetchone()[0]


def test_hud_read_batch_returns_postgresql_connection_to_idle() -> None:
    """A remote pool must be able to reuse the server slot between HUD batches."""
    if "postgresql" not in _enabled_backends():
        pytest.skip("live PostgreSQL service not requested")

    hud_module = _load_hud_main()
    with _connection("postgresql") as hud_connection, _connection("postgresql") as observer:
        observer.autocommit = True
        with hud_connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()

        assert _backend_state(observer, hud_connection.info.backend_pid) == "idle in transaction"

        hud = hud_module.HudMain.__new__(hud_module.HudMain)
        hud._db_available = True
        hud.db_connection = SimpleNamespace(connection=hud_connection, backend=Database.PGSQL)
        hud._finish_read_batch()

        assert _backend_state(observer, hud_connection.info.backend_pid) == "idle"
