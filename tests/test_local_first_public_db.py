"""Local-first push to a public database, which keeps one row per hero seat (#680)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.Importer import Importer
from fpdb_3_legacy.local_first_sync import LocalFirstSync
from tests.helpers import analytics_golden as golden

ONE_FILE = (
    Path(__file__).resolve().parent.parent / "regression-test-files/cash/Stars/Flop/NLHE-6max-EUR-0.05-0.10-200911.txt"
)


def _config(tmp_path: Path, name: str):
    (tmp_path / name).mkdir()
    config = golden.build_config(tmp_path / name)
    params = config.get_db_parameters()
    params.update(
        {"db-server": "sqlite", "db-backend": 4, "db-databaseName": str(tmp_path / name / "db.sqlite3"), "db-path": ""}
    )
    config.get_db_parameters = lambda: params
    import_parameters = {**config.get_import_parameters(), "publicDB": True}
    config.get_import_parameters = lambda: import_parameters
    return config


def _second_perspective(path: str, hand_id: int) -> int:
    """Store the hand again from another hero seat, as a second player's history would."""
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        hand = dict(connection.execute("SELECT * FROM Hands WHERE id = ?", (hand_id,)).fetchone())
        hand.pop("id")
        hand["heroSeat"] += 1
        columns = ", ".join(hand)
        marks = ", ".join("?" * len(hand))
        copy_id = connection.execute(  # nosemgrep
            "INSERT INTO Hands (" + columns + ") VALUES (" + marks + ")",  # nosec B608  # nosemgrep
            list(hand.values()),
        ).lastrowid
        for row in connection.execute("SELECT * FROM HandsPlayers WHERE handId = ?", (hand_id,)).fetchall():
            player = dict(row)
            player.pop("id")
            player["handId"] = copy_id
            columns = ", ".join(player)
            marks = ", ".join("?" * len(player))
            connection.execute(  # nosemgrep
                "INSERT INTO HandsPlayers (" + columns + ") VALUES (" + marks + ")",  # nosec B608  # nosemgrep
                list(player.values()),
            )
    return copy_id


@pytest.fixture
def pushed(tmp_path):
    """Two perspectives of one hand, pushed to a public server."""
    local_config = _config(tmp_path, "local")
    local = Database(local_config)
    local.recreate_tables()
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=local_config, sql=None)
    importer.database = local
    importer.setCallHud(False)
    assert importer.addImportFile(str(ONE_FILE), "auto")
    assert importer.runImport()[0] >= 1

    server_config = _config(tmp_path, "server")
    server = Database(server_config)
    server.recreate_tables()
    server.disconnect()

    path = str(tmp_path / "local" / "db.sqlite3")
    with sqlite3.connect(path) as connection:
        first = connection.execute("SELECT min(id) FROM Hands").fetchone()[0]
    ids = [first, _second_perspective(path, first)]
    sync = LocalFirstSync(local, lambda: Database(server_config), local_db_path=path)
    sync.mark(ids)
    assert sync.push_once() == 2
    yield sync, sqlite3.connect(tmp_path / "server" / "db.sqlite3")
    sync.stop()


def test_each_hero_seat_of_a_hand_reaches_a_public_server(pushed) -> None:
    _sync, server = pushed

    hands = server.execute("SELECT id, siteHandNo, heroSeat FROM Hands ORDER BY heroSeat").fetchall()
    assert len(hands) == 2
    assert hands[0][1] == hands[1][1]
    assert hands[0][2] != hands[1][2]
    for hand in hands:
        assert server.execute("SELECT count(*) FROM HandsPlayers WHERE handId = ?", (hand[0],)).fetchone()[0] > 0
    server.close()


def test_a_perspective_the_public_server_holds_is_not_pushed_twice(pushed) -> None:
    sync, server = pushed
    outbox = sync._own_conn
    before = outbox.execute("SELECT local_hand_id, server_hand_id FROM fpdb_sync_outbox ORDER BY 1").fetchall()

    outbox.execute("UPDATE fpdb_sync_outbox SET pushed = 0")
    outbox.commit()
    sync.push_once()

    assert server.execute("SELECT count(*) FROM Hands").fetchone()[0] == 2
    assert outbox.execute("SELECT local_hand_id, server_hand_id FROM fpdb_sync_outbox ORDER BY 1").fetchall() == before
    server.close()
