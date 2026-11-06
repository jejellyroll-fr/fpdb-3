"""Knockout or freezeout: the tournament reports' format filter (#447).

The tournament graph and the tournament player report filter their
``TourneyTypes tt`` rows with the condition returned here. "Freezeout" keeps
every tournament not known to be a knockout: a type stored before the knockout
flag was read has it unset, and is not a knockout as far as fpdb knows.

The conditions are fixed strings, one per format and backend, so nothing is
formatted into the SQL.
"""

from __future__ import annotations

from typing import Final

__all__ = ["FORMAT_ALL", "FORMAT_FREEZEOUT", "FORMAT_KNOCKOUT", "TOURNEY_FORMATS", "format_condition"]

FORMAT_ALL: Final = "all"
FORMAT_KNOCKOUT: Final = "knockout"
FORMAT_FREEZEOUT: Final = "freezeout"
TOURNEY_FORMATS: Final = (FORMAT_ALL, FORMAT_KNOCKOUT, FORMAT_FREEZEOUT)

# SQLite stores booleans as 1/0; MySQL and PostgreSQL compare with TRUE.
_CONDITIONS: Final[dict[tuple[str, bool], str]] = {
    (FORMAT_KNOCKOUT, True): "AND tt.knockout = 1",
    (FORMAT_KNOCKOUT, False): "AND tt.knockout = TRUE",
    (FORMAT_FREEZEOUT, True): "AND (tt.knockout IS NULL OR NOT tt.knockout = 1)",
    (FORMAT_FREEZEOUT, False): "AND (tt.knockout IS NULL OR NOT tt.knockout = TRUE)",
}


def format_condition(tourney_format: str, sqlite: bool) -> str:
    """The ``AND ...`` condition on ``tt`` for a format; empty for all tournaments."""
    return _CONDITIONS.get((tourney_format, sqlite), "")
