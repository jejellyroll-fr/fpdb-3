#!/usr/bin/env python3
"""End-to-end tests for the cross-backend data migration engine (db_migrate).

Uses two real SQLite databases (no server needed): a populated source and a
freshly-initialised destination. Verifies that every table is copied with
matching row counts, that edited data is carried over, and that the
destination's own default rows are replaced rather than duplicated.
"""

from __future__ import annotations

import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fpdb_3_legacy import Configuration, db_migrate

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_TEMPLATE = os.path.join(REPO_ROOT, "HUD_config.xml")


def _build_db(config, db_name):
    """Connect a Database to the named sqlite entry (schema auto-created)."""
    from fpdb_3_legacy import Database

    config.db_selected = db_name
    return Database.Database(config)


def _counts(db, tables):
    counts = {}
    cursor = db.get_cursor()
    for table in tables:
        cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
        counts[table] = cursor.fetchone()[0]
    return counts


@pytest.fixture
def config(tmp_path):
    cfg_path = tmp_path / "HUD_config.xml"
    shutil.copy(CONFIG_TEMPLATE, cfg_path)
    cfg = Configuration.Config(file=str(cfg_path))
    cfg.dir_database = str(tmp_path)
    cfg.add_db_parameters(db_name="source.db3", db_server="sqlite")
    cfg.add_db_parameters(db_name="dest.db3", db_server="sqlite")
    return cfg


def test_migrate_sqlite_to_sqlite_copies_every_table(config):
    source = _build_db(config, "source.db3")
    # Make the source distinguishable from a default DB: rename a Site.
    cur = source.get_cursor()
    cur.execute("SELECT MIN(id) FROM Sites")
    site_id = cur.fetchone()[0]
    cur.execute('UPDATE Sites SET name = ? WHERE id = ?', ("MIGRATED_SITE", site_id))
    source.commit()

    tables = db_migrate.list_data_tables(source)
    assert "Players" in tables and "Sites" in tables and "Hands" in tables
    source_counts = _counts(source, tables)

    dest = _build_db(config, "dest.db3")

    report = db_migrate.migrate(source, dest)

    assert report.ok, report.error
    assert report.total_rows > 0
    # Every table has the same number of rows as the source.
    assert _counts(dest, tables) == source_counts
    # The edited value was carried over (and the destination's default replaced).
    cur = dest.get_cursor()
    cur.execute('SELECT name FROM Sites WHERE id = ?', (site_id,))
    assert cur.fetchone()[0] == "MIGRATED_SITE"

    source.close_connection()
    dest.close_connection()


def test_migrate_is_idempotent(config):
    """Running the migration twice must not duplicate rows (delete-then-copy)."""
    source = _build_db(config, "source.db3")
    tables = db_migrate.list_data_tables(source)
    source_counts = _counts(source, tables)
    dest = _build_db(config, "dest.db3")

    first = db_migrate.migrate(source, dest)
    second = db_migrate.migrate(source, dest)

    assert first.ok and second.ok
    assert _counts(dest, tables) == source_counts  # unchanged after the second run

    source.close_connection()
    dest.close_connection()


def test_migrate_preserves_ids_of_non_default_rows(config):
    """A user row inserted into an initially-empty table migrates with its id."""
    source = _build_db(config, "source.db3")
    cur = source.get_cursor()
    cur.execute("INSERT INTO Players (id, name, siteId, hero) VALUES (?, ?, ?, ?)", (4242, "heroic", 2, 1))
    source.commit()

    dest = _build_db(config, "dest.db3")
    report = db_migrate.migrate(source, dest)
    assert report.ok

    cur = dest.get_cursor()
    cur.execute("SELECT name, siteId FROM Players WHERE id = ?", (4242,))
    assert cur.fetchone() == ("heroic", 2)  # id preserved, so FKs stay valid

    source.close_connection()
    dest.close_connection()


def test_report_lists_rows_per_table(config):
    source = _build_db(config, "source.db3")
    dest = _build_db(config, "dest.db3")
    report = db_migrate.migrate(source, dest)
    assert report.ok
    # Actions is a lookup table populated by fillDefaultData, so it has rows.
    assert report.tables.get("Actions", 0) > 0
    assert report.total_rows == sum(report.tables.values())
    source.close_connection()
    dest.close_connection()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
