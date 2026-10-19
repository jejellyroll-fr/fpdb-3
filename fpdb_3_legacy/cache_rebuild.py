"""Generated stat columns for the cache rebuild query (#591).

The rebuild's column lists used to be written by hand, once per backend; the
import kept appending keys to CACHE_KEYS and the lists did not follow, so a
rebuild left 138 HudCache columns -- and street0FaceRaise in every cache -- at
zero.

The lists are now generated from the keys the import writes
(:data:`~fpdb_3_legacy.database_caches.CACHE_KEYS` and friends): a key added
there is rebuilt too, and a key the rebuild cannot compute fails
:func:`rebuild_stat_columns` instead of being silently dropped.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from functools import cache

from fpdb_3_legacy.action_enum_stats import SITUATIONS as ACTION_ENUM_SITUATIONS
from fpdb_3_legacy.sql_schema_hand_player import hand_player_schema_queries


@cache
def _boolean_columns(db_server: str) -> frozenset[str]:
    """HandsPlayers columns declared BOOLEAN, which PostgreSQL cannot sum as such."""
    ddl = hand_player_schema_queries(db_server)["createHandsPlayersTable"]
    return frozenset(re.findall(r"^\s*(\w+)\s+BOOLEAN\b", ddl, re.MULTILINE))


def _as_number(db_server: str, column: str) -> str:
    if db_server == "postgresql" and column in _boolean_columns(db_server):
        return f"CAST(hp.{column} AS integer)"
    return f"hp.{column}"


def _saw_showdown(db_server: str) -> str:
    return "hp.sawShowdown" if db_server == "postgresql" else "hp.sawShowdown = 1"


def _derived_expressions(db_server: str) -> dict[str, str]:
    """Keys the import computes in memory rather than reading a HandsPlayers column.

    Each mirrors DerivedStats: the showdown split of totalProfit, the open-limp
    opportunity (set together with raiseFirstInChance), and the PT4 action-enum
    counters derived from the stored response chars (action_enum_stats).
    """
    showdown = _saw_showdown(db_server)
    expressions = {
        "n": "count(1)",
        "showdownWinnings": f"sum(case when {showdown} then hp.totalProfit else 0 end)",
        "nonShowdownWinnings": f"sum(case when {showdown} then 0 else hp.totalProfit end)",
        "street0OpenLimpChance": f"sum({_as_number(db_server, 'raiseFirstInChance')})",
    }
    for situation in ACTION_ENUM_SITUATIONS:
        enum = f"hp.{situation.enum_key}"
        expressions[situation.faced_key] = f"sum(case when {enum} in ('F', 'C', 'R') then 1 else 0 end)"
        expressions[situation.called_key] = f"sum(case when {enum} = 'C' then 1 else 0 end)"
        expressions[situation.raised_key] = f"sum(case when {enum} = 'R' then 1 else 0 end)"
    return expressions


def rebuild_stat_columns(db_server: str, keys: Sequence[str]) -> tuple[str, str]:
    """The insert column list and the matching select expressions for ``keys``.

    Every key is either a HandsPlayers column, summed, or one the import derives,
    computed the same way. Anything else raises: a cache column the rebuild
    cannot fill must not be refilled with zeros.
    """
    columns = _hand_player_columns(db_server)
    derived = _derived_expressions(db_server)
    unknown = [key for key in keys if key not in derived and key not in columns]
    if unknown:
        msg = f"the cache rebuild cannot compute {', '.join(unknown)}"
        raise ValueError(msg)
    expressions = [derived.get(key) or f"sum({_as_number(db_server, key)})" for key in keys]
    insert = "".join(f"\n            ,{key}" for key in keys)
    select = "".join(f"\n                  ,{expression}" for expression in expressions)
    return insert, select


@cache
def _hand_player_columns(db_server: str) -> frozenset[str]:
    ddl = hand_player_schema_queries(db_server)["createHandsPlayersTable"]
    return frozenset(re.findall(r"^\s*(\w+)\s+[A-Za-z]", ddl, re.MULTILINE))
