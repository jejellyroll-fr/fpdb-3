"""Reading cursor rows by name, on every backend fpdb supports.

PostgreSQL folds an unquoted identifier to lower case, so ``SELECT HA.actionNo``
comes back from ``cursor.description`` as ``actionno``; SQLite and MySQL hand it
back as written. Any code that reads a mixed-case column by the spelling its
SELECT uses therefore works on two backends and raises ``KeyError`` on the
third -- a fault invisible to a suite that runs on SQLite.

That has bitten this project three times: the research browser's drill-down
(``KeyError: 'handId'``), and both row readers of the analytics rebuild
(``KeyError: 'actionNo'``), which left the rebuild unable to derive a single
row on PostgreSQL and so left the whole Research Browser empty. Several other
modules had already solved it one at a time by lower-casing their own
description.

One helper, so the next reader does not have to rediscover it. A row reads by
whatever spelling the caller finds clearest -- the SELECT's own, most of the
time -- and the backend's folding stops being something to remember.
"""

from __future__ import annotations

from typing import Any

__all__ = ["Row", "row_by_alias", "rows_by_alias"]


class Row(dict):
    """A result row whose keys are matched without regard to case.

    An exact hit costs what a dict costs; only a miss pays for the fold, which
    is the case a backend that lower-cases its identifiers always takes.
    """

    def __missing__(self, key: Any) -> Any:
        wanted = str(key).lower()
        for name, value in self.items():
            if str(name).lower() == wanted:
                return value
        raise KeyError(key)

    def get(self, key: Any, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key: Any) -> bool:
        if super().__contains__(key):
            return True
        wanted = str(key).lower()
        return any(str(name).lower() == wanted for name in self)


def rows_by_alias(cursor: Any) -> list[Row]:
    """Every remaining row of ``cursor``, readable by either spelling."""
    columns = [description[0] for description in cursor.description]
    return [Row(zip(columns, raw, strict=True)) for raw in cursor.fetchall()]


def row_by_alias(cursor: Any) -> Row | None:
    """The next row, read the same way, or ``None`` when there is none."""
    columns = [description[0] for description in cursor.description]
    raw = cursor.fetchone()
    return None if raw is None else Row(zip(columns, raw, strict=True))
