"""The table identity row the HUD reads for a hand.

``Database.get_table_info`` used to hand back a bare list whose meaning was
carried entirely by position, and every consumer unpacked it with a fixed
arity. Appending one column (``limitType``) therefore broke callers that had
nothing to do with the new field. ``TableInfo`` is a ``NamedTuple``, so index
access and tuple unpacking keep working for existing code and caches, while new
code reads fields by name and a future column costs no caller a change.
"""

from __future__ import annotations

from typing import Any, NamedTuple


class TableInfo(NamedTuple):
    """One table's identity, as the HUD needs it to place and key a window."""

    table_name: str = ""
    max_seats: int = 0
    poker_game: str = ""
    game_type: str = ""
    fast: Any = False
    site_id: Any = None
    site_name: str = ""
    num_seats: int = 0
    tour_number: Any = None
    tab_number: Any = None
    tourney_name: Any = None
    limit_type: str = "all"

    @classmethod
    def coerce(cls, value: Any) -> TableInfo:
        """Adapt any historical row shape to the current field set.

        Rows come from three places that cannot all be migrated at once: the
        database, the in-process hand cache (which may hold rows serialized by
        an older run), and tests. Short rows are padded from the field
        defaults and long ones are truncated, so a caller never has to know
        which shape it was handed.
        """
        if isinstance(value, cls):
            return value
        values = list(value)
        width = len(cls._fields)
        if len(values) < width:
            values.extend(cls._field_defaults[name] for name in cls._fields[len(values) :])
        return cls(*values[:width])
