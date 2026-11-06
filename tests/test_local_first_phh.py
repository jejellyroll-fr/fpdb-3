"""PHH files in local-first sync (#680).

A PHH file commits hand by hand and empties the bulk buffers before each one, so
``database.hids`` only ever holds the last hand when the file is done.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from fpdb_3_legacy import phh_import
from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.Importer import Importer
from fpdb_3_legacy.local_first_sync import LocalFirstSync
from tests.helpers import analytics_golden as golden

FIXTURES = Path(__file__).parent / "fixtures" / "phh"
HANDS = {
    "razz": (FIXTURES / "razz.phh").read_text(encoding="utf-8"),
    "stud": (FIXTURES / "stud_hi.phh").read_text(encoding="utf-8"),
    "omaha": (FIXTURES / "pl_omaha.phh").read_text(encoding="utf-8"),
}


def _dataset(path: Path, labels: list[str]) -> Path:
    path.write_text("\n".join(f"[{label}]\n{HANDS[label]}" for label in labels), encoding="utf-8")
    return path


def _ids(db: Database, query: str) -> list[int]:
    with sqlite3.connect(db.db_path) as connection:
        return sorted(row[0] for row in connection.execute(query))


def _hand_ids(db: Database) -> list[int]:
    return _ids(db, "SELECT id FROM Hands")


def _outbox(db: Database) -> list[int]:
    return _ids(db, "SELECT local_hand_id FROM fpdb_sync_outbox")


def _run(importer: Importer, path: Path) -> tuple[int, int]:
    assert importer.addImportFile(str(path))
    stored, duplicates, *_rest = importer.runImport()
    return stored, duplicates


@pytest.fixture
def importer_for():
    syncs = []

    def build(db: Database) -> Importer:
        importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=db.config, sql=None)
        importer.database = db
        importer.setCallHud(False)
        sync = LocalFirstSync(db, MagicMock(), local_db_path=db.db_path)
        # runImport starts the worker. These tests read the queue, so nothing may push it, and a
        # worker left running would add to the process-wide latency metrics of later tests.
        sync.start = lambda: None
        syncs.append(sync)
        importer._local_first_sync = sync
        return importer

    yield build
    for sync in syncs:
        sync.stop()


@pytest.fixture
def local(tmp_path):
    config = golden.build_config(tmp_path)
    params = config.get_db_parameters()
    params.update(
        {"db-server": "sqlite", "db-backend": 4, "db-databaseName": str(tmp_path / "db.sqlite3"), "db-path": ""}
    )
    config.get_db_parameters = lambda: params
    db = Database(config)
    db.recreate_tables()
    yield db
    db.disconnect()


def test_every_hand_of_a_multi_hand_file_is_queued(local, importer_for, tmp_path) -> None:
    importer = importer_for(local)

    assert _run(importer, _dataset(tmp_path / "dataset.phhs", ["razz", "stud", "omaha"])) == (3, 0)

    assert len(_hand_ids(local)) == 3
    assert _outbox(local) == _hand_ids(local)


def test_hands_before_a_trailing_duplicate_are_queued(local, importer_for, tmp_path) -> None:
    dataset = _dataset(tmp_path / "dataset.phhs", ["stud"])
    assert _run(importer_for(local), dataset) == (1, 0)

    # A new hand first, then the one the database already holds: nothing is buffered at the end.
    _dataset(dataset, ["razz", "stud"])
    assert _run(importer_for(Database(local.config)), dataset) == (1, 1)  # runImport closed the first connection

    assert len(_hand_ids(local)) == 2
    assert _outbox(local) == _hand_ids(local)


def test_hands_committed_before_the_file_breaks_stay_queued(local, importer_for, tmp_path, monkeypatch) -> None:
    dataset = _dataset(tmp_path / "dataset.phhs", ["razz", "stud", "omaha"])
    read = phh_import.iter_documents

    def breaks_after_two(path):
        for position, item in enumerate(read(path)):
            if position == 2:
                raise OSError("disk gone")
            yield item

    monkeypatch.setattr(phh_import, "iter_documents", breaks_after_two)
    fpdbfile = MagicMock(path=str(dataset), fileId=0)

    with pytest.raises(OSError, match="disk gone"):
        importer_for(local)._import_phh_file(fpdbfile)

    assert len(_hand_ids(local)) == 2
    assert _outbox(local) == _hand_ids(local)
