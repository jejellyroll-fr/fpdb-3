"""An importer releases the database connections it opened (#282).

``Importer`` opens one connection for itself and one per writer thread, and
nothing else owns them. Before ``close()`` existed there was no way to give them
back, so a caller that imported and then deleted or replaced the database file
found it still in use. POSIX unlinks an open file without complaint, which is
why this never showed on the maintainers' machines; Windows refuses with
``WinError 32``, which is why it showed on every contributor's.

The invariant asserted here is the portable half of that: after ``close()`` the
importer holds no open connection. The unlink that follows only fails on
Windows, so it is the connection state, not the delete, that is the subject.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.Importer import Importer


def _sqlite_importer(threads: int = 1):
    """A real importer on a throwaway SQLite file, and that file's path."""
    db_file = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
    db_file.close()

    config = Config()
    params = config.get_db_parameters().copy()
    params.update(
        {
            "db-backend": Database.SQLITE,
            "db-server": "sqlite",
            "db-databaseName": db_file.name,
            "db-host": "",
            "db-user": "",
            "db-password": "",
        },
    )
    config.get_db_parameters = lambda: params

    schema = Database(config)
    schema.recreate_tables()
    schema.close_connection()

    importer = Importer(caller=None, settings={"testData": False, "threads": threads}, config=config, sql=None)
    return importer, Path(db_file.name)


def _bare_importer(databases):
    """An importer with only the two attributes ``close`` reads."""
    importer = Importer.__new__(Importer)
    importer.database = databases[0]
    importer.writerdbs = list(databases[1:])
    return importer


def test_close_releases_the_importers_own_connections() -> None:
    importer, path = _sqlite_importer()
    try:
        assert importer.database.connection is not None
        assert importer.writerdbs and all(db.connection is not None for db in importer.writerdbs)

        importer.close()

        assert importer.database.connection is None
        assert importer.writerdbs == []
    finally:
        path.unlink(missing_ok=True)


def test_every_writer_thread_gets_its_connection_closed() -> None:
    # One connection per thread, so a multi-threaded import leaves several
    # behind; closing only the importer's own would still hold the file.
    importer, path = _sqlite_importer(threads=3)
    try:
        writers = list(importer.writerdbs)
        assert len(writers) == 3

        importer.close()

        assert all(db.connection is None for db in writers)
    finally:
        path.unlink(missing_ok=True)


def test_closing_twice_is_a_no_op() -> None:
    # Shutdown paths close more than once; the second must not raise.
    importer, path = _sqlite_importer()
    try:
        importer.close()
        importer.close()
        assert importer.database.connection is None
    finally:
        path.unlink(missing_ok=True)


def test_one_connection_that_refuses_does_not_strand_the_others() -> None:
    # Closing is what runs while something else has already gone wrong, so a
    # handle that raises must not keep the remaining ones open.
    angry = MagicMock(name="angry")
    angry.close_connection.side_effect = RuntimeError("this handle is gone")
    calm_one, calm_two = MagicMock(name="calm_one"), MagicMock(name="calm_two")

    _bare_importer([angry, calm_one, calm_two]).close()

    calm_one.close_connection.assert_called_once_with()
    calm_two.close_connection.assert_called_once_with()


def test_an_importer_without_writers_closes_cleanly() -> None:
    # A caller that builds an importer without running __init__ has neither
    # attribute; close() is still the right thing to call on the way out.
    importer = Importer.__new__(Importer)

    importer.close()

    assert importer.writerdbs == []
