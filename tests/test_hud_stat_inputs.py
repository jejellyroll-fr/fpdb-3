"""Every key a HUD stat reads must be a column the HUD queries select (#790).

The HUD builds each player's stat dict from a query row and lower-cases the
column names (``database_hud_stats``). A stat that reads ``street1Bets`` while
the query selects ``bet_1``, or ``CAR_0`` while the dict holds ``car_0``, never
finds its input: ``.get(key, 0)`` hides it and the stat shows 0 or no data.
Unit tests that build a stat dict by hand cannot see this, so this one reads
the keys off the stat functions and the names off the query text.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from fpdb_3_legacy import Stats

LEGACY = Path(__file__).resolve().parent.parent / "fpdb_3_legacy"
HUD_QUERIES = (
    "sql_queries_hud_current_stats.py",
    "sql_queries_hud_aggregated_stats.py",
    "sql_queries_aof.py",
)

#: Keys that are not a selected column, with why each is allowed. Never add to it
#: to make a stat pass: select the column or read the right key instead.
KNOWN_ABSENT = {
    # ``currency`` is read with a USD default; the HUD query does not select it.
    "currency",
    # ``rfi_total`` subtracts a ``3bet`` count nothing fills, so it equals PFR; its
    # measured counterparts are the per-position ``rfi_*`` stats.
    "3bet",
}


class _Row(dict):  # type: ignore[type-arg]
    """A stat row that records every key read and serves one chosen value per key."""

    def __init__(self, value_of: Any, log: list[str]) -> None:
        super().__init__()
        self._value_of = value_of
        self._log = log

    def get(self, key: str, _default: Any = None) -> Any:
        self._log.append(key)
        return self._value_of(key)

    def __getitem__(self, key: str) -> Any:
        return self.get(key)

    def __contains__(self, key: object) -> bool:
        self._log.append(str(key))
        return True


# Several value patterns, because a stat that subtracts two counters returns
# before reading its other inputs when they cancel out.
_PATTERNS = (
    lambda key: 5,
    lambda key: 3 + (sum(map(ord, key)) % 17) * 11,
    lambda key: 1000 - (sum(map(ord, key)) % 17) * 11,
    # Seen/opportunity counters above the others, so "seen - done" stays positive.
    lambda key: 2000 if key.startswith(("saw", "sd", "n")) or key.endswith("_opp") else 7,
)


def _selected_columns() -> set[str]:
    names: set[str] = set()
    for filename in HUD_QUERIES:
        text = (LEGACY / filename).read_text(encoding="utf-8")
        names.update(name.lower() for name in re.findall(r"\bas\s+(\w+)", text, flags=re.IGNORECASE))
    return names


def _keys_read(function: Any) -> set[str]:
    keys: set[str] = set()
    for value_of in _PATTERNS:
        log: list[str] = []
        try:
            function({1: _Row(value_of, log)}, 1)
        except Exception:  # noqa: BLE001 - helpers that are not stats raise on the probe
            continue
        keys.update(log)
    return keys


def _native_stats() -> list[str]:
    stats = []
    for name in Stats.STATLIST:
        try:
            result = getattr(Stats, name)({1: _Row(_PATTERNS[0], [])}, 1)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(result, tuple) and len(result) > 5:
            stats.append(name)
    return stats


SELECTED = _selected_columns()
NATIVE = _native_stats()


def test_the_probe_sees_the_stats() -> None:
    assert len(NATIVE) > 250
    assert {"vpip", "cb1", "bet_frequency_flop", "probe_bet", "float_bet", "cold_call"} <= set(NATIVE)


@pytest.mark.parametrize("name", NATIVE)
def test_a_stat_reads_only_columns_the_hud_selects(name: str) -> None:
    unknown = {key for key in _keys_read(getattr(Stats, name)) if key not in SELECTED} - KNOWN_ABSENT - {"screen_name"}
    assert not unknown, f"{name} reads {sorted(unknown)}: the HUD queries select no such column (names are lower-cased)"


def test_the_fixed_stats_read_the_selected_names() -> None:
    assert "bet_1" in _keys_read(Stats.bet_frequency_flop)
    assert {"call_1", "saw_2", "bet_2", "street1inposition"} <= _keys_read(Stats.float_bet)
    assert {"car_0", "car_opp_0"} <= _keys_read(Stats.cold_call)
    assert {"f4b_0", "f4b_opp_0"} <= _keys_read(Stats.fold_vs_4bet)


def test_the_known_exceptions_are_still_needed() -> None:
    read = set().union(*(_keys_read(getattr(Stats, name)) for name in NATIVE))
    assert {key for key in KNOWN_ABSENT if key in read and key not in SELECTED} == KNOWN_ABSENT, (
        "an exception is no longer needed: remove it"
    )
