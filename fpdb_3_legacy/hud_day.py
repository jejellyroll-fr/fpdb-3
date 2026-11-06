"""The day HudCache files a hand under (#600).

HudCache keeps one row per player and day (``styleKey`` ``dYYMMDD``): the
hand's UTC start time moved to the machine's local time, then back by
``day_start`` hours, so a session that runs past midnight stays in one day.

The local time is taken at the hand's own start time. Both the import and the
cache rebuild used the offset in force when they ran, so on a machine that
observes daylight saving time a hand within an hour of the day boundary changed
day depending on the season of the import, and again on a rebuild.

The rebuild cannot ask the database for the machine's zone (PostgreSQL would
need its name, MySQL its time zone tables), so it gets the offsets as a CASE
over the instants they change, worked out here with the same rules the import
uses.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

STYLE_KEY_FORMAT = "d%y%m%d"
SQL_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def local_offset(utc: datetime) -> timedelta:
    """The machine's UTC offset at the naive UTC instant ``utc``."""
    try:
        offset = utc.replace(tzinfo=timezone.utc).astimezone().utcoffset()
    except (OverflowError, OSError, ValueError):
        # Outside the platform's time range (before 1970 on Windows): the
        # offset of today is the best there is.
        offset = datetime.now(timezone.utc).astimezone().utcoffset()
    return offset or timedelta(0)


def as_utc(start_time: datetime) -> datetime:
    """A hand's start time as a naive UTC datetime, which the database stores."""
    if start_time.tzinfo is not None:
        start_time = start_time.astimezone(timezone.utc).replace(tzinfo=None)
    return start_time


def style_key(start_time: datetime, day_start: float) -> str:
    """The HudCache day of a hand that started at ``start_time`` (UTC)."""
    utc = as_utc(start_time)
    return (utc + _shift(utc, day_start)).strftime(STYLE_KEY_FORMAT)


def _shift(utc: datetime, day_start: float) -> timedelta:
    return local_offset(utc) - timedelta(hours=day_start)


def offset_changes(first: datetime, last: datetime) -> list[tuple[datetime, timedelta]]:
    """The machine's offset from ``first`` to ``last`` (naive UTC), as (from, offset) pairs.

    The first pair starts at ``first``; each next one at the second the offset
    changes. Days are stepped through and a change is narrowed down to the
    second, which assumes at most one change a day, as every zone has.
    """
    offset = local_offset
    changes = [(first, offset(first))]
    day = first
    while day < last:
        following = min(day + timedelta(days=1), last)
        if offset(following) != changes[-1][1]:
            before, after = day, following
            while after - before > timedelta(seconds=1):
                middle = before + timedelta(seconds=int((after - before).total_seconds()) // 2)
                if offset(middle) == changes[-1][1]:
                    before = middle
                else:
                    after = middle
            changes.append((after, offset(after)))
        day = following
    return changes


def minutes_sql(first: datetime | None, last: datetime | None, day_start: float) -> str:
    """SQL for the minutes to add to ``h.startTime`` to reach the hand's HudCache day.

    A constant when the offset does not change between the first and the last
    hand, otherwise a CASE on the start time; parenthesized either way.
    """
    if first is None or last is None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        first = last = now
    changes = offset_changes(first, last)
    minutes = [round((offset - timedelta(hours=day_start)).total_seconds() / 60) for _start, offset in changes]
    if len(changes) == 1:
        return f"({minutes[0]})"
    branches = "".join(
        f" WHEN h.startTime < '{start.strftime(SQL_TIME_FORMAT)}' THEN {previous}"
        for (start, _offset), previous in zip(changes[1:], minutes, strict=False)
    )
    return f"(CASE{branches} ELSE {minutes[-1]} END)"


def parse_time(value: datetime | str | None) -> datetime | None:
    """MIN/MAX of a timestamp column: a datetime, or text on SQLite."""
    if value is None or isinstance(value, datetime):
        return as_utc(value) if isinstance(value, datetime) else None
    return datetime.fromisoformat(str(value)[:19])
