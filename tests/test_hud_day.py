"""HudCache files a hand under the day of its own start time (#600).

The import and the rebuild used the machine's UTC offset of the moment they
ran, so in a zone with daylight saving time a hand near midnight changed day
with the season of the import. The zone is pinned with pytz, which carries its
own time zone database, so these run the same on every platform.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
import pytz

from fpdb_3_legacy import hud_day

NEW_YORK = pytz.timezone("America/New_York")


def _new_york(utc: datetime) -> timedelta:
    """New York's offset at the UTC instant ``utc``, as hud_day.local_offset gives the machine's."""
    return pytz.utc.localize(utc).astimezone(NEW_YORK).utcoffset()


@pytest.fixture
def new_york(monkeypatch) -> None:
    monkeypatch.setattr(hud_day, "local_offset", _new_york)


@pytest.mark.usefixtures("new_york")
@pytest.mark.parametrize(
    ("start", "day"),
    [
        (datetime(2026, 1, 15, 4, 30), "d260114"),  # 23:30 EST the day before
        (datetime(2026, 7, 15, 4, 30), "d260715"),  # 00:30 EDT
    ],
    ids=["winter", "summer"],
)
def test_a_hand_takes_the_offset_of_its_own_date(start, day) -> None:
    assert hud_day.style_key(start, 0.0) == day


@pytest.mark.usefixtures("new_york")
def test_an_aware_start_time_is_read_as_utc() -> None:
    naive = datetime(2026, 1, 15, 4, 30)

    assert hud_day.style_key(pytz.utc.localize(naive), 0.0) == hud_day.style_key(naive, 0.0)


@pytest.mark.usefixtures("new_york")
def test_day_start_moves_the_boundary_back() -> None:
    """With the day starting at 06:00, 05:30 local still belongs to the day before."""
    assert hud_day.style_key(datetime(2026, 7, 15, 9, 30), 6.0) == "d260714"
    assert hud_day.style_key(datetime(2026, 7, 15, 10, 30), 6.0) == "d260715"


@pytest.mark.usefixtures("new_york")
def test_the_offset_changes_are_found_to_the_second() -> None:
    changes = hud_day.offset_changes(datetime(2026, 1, 1), datetime(2026, 12, 31))

    assert changes == [
        (datetime(2026, 1, 1), timedelta(hours=-5)),
        (datetime(2026, 3, 8, 7, 0), timedelta(hours=-4)),
        (datetime(2026, 11, 1, 6, 0), timedelta(hours=-5)),
    ]


@pytest.mark.usefixtures("new_york")
def test_the_rebuild_offset_is_a_case_over_the_changes() -> None:
    sql = hud_day.minutes_sql(datetime(2026, 1, 1), datetime(2026, 12, 31), 0.0)

    assert sql == (
        "(CASE WHEN h.startTime < '2026-03-08 07:00:00' THEN -300"
        " WHEN h.startTime < '2026-11-01 06:00:00' THEN -240 ELSE -300 END)"
    )
    assert hud_day.minutes_sql(datetime(2026, 1, 1), datetime(2026, 2, 1), 1.5) == "(-390)"


def test_text_from_sqlite_is_read_as_a_time() -> None:
    assert hud_day.parse_time("2014-04-07 00:57:23") == datetime(2014, 4, 7, 0, 57, 23)
    assert hud_day.parse_time(None) is None


@pytest.mark.usefixtures("new_york")
def test_sqlite_computes_the_same_day(tmp_path) -> None:
    """The rebuild's SQLite expression agrees with the import on either side of a change."""
    import sqlite3

    from fpdb_3_legacy.Database import Database

    host = Database.__new__(Database)
    host.backend = Database.SQLITE
    minutes = hud_day.minutes_sql(datetime(2026, 1, 1), datetime(2026, 12, 31), 0.0)
    query = "SELECT <day> FROM (SELECT ? AS startTime) h".replace("<day>", host.hud_day_sql(minutes))
    connection = sqlite3.connect(tmp_path / "day.db")
    for start in (datetime(2026, 1, 15, 4, 30), datetime(2026, 3, 8, 6, 59, 59), datetime(2026, 7, 15, 4, 30)):
        (day,) = connection.execute(query, (start.strftime(hud_day.SQL_TIME_FORMAT),)).fetchone()
        assert day == hud_day.style_key(start, 0.0), start
    connection.close()
