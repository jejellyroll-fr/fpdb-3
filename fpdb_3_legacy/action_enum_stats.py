"""Counters derived from the PT4 ``enum_*_action`` family, for the HUD.

``DerivedStats.calcActionEnums`` stores one response char per situation in
HandsPlayers -- F, C, R, or N when the situation never arose. The HUD does not
read HandsPlayers: it sums HudCache, and a char column cannot be summed. PT4
resolves the same problem by counting at query time,
``sum(if[enum_p_3bet_action = 'R', 1, 0])``; FPDB's cache is additive, so the
count happens once at import instead.

Each situation therefore contributes three HudCache columns -- faced, called,
raised. The fold leg is deliberately not stored: it is exactly
``faced - called - raised``, because a non-"N" enum holds one of F/C/R and
nothing else.

Column names follow PT4's own (``cnt_p_raise_3bet``), so a PT4 stat definition
naming them maps straight onto FPDB.
"""

from __future__ import annotations

from typing import Any, NamedTuple


class Situation(NamedTuple):
    """One spot a player can be facing, and how the HUD should label it."""

    enum_key: str
    """The HandsPlayers column DerivedStats fills with F/C/R/N."""

    street: str
    """PT4 street letter: p, f, t or r."""

    name: str
    """PT4 situation name, e.g. "3bet"."""

    label: str
    """Short HUD label for the situation, e.g. "v3B"."""

    description: str
    """Human-readable spot, used to build each stat's tooltip."""

    stat_base: str
    """Suffix of the three HUD stat names, e.g. "vs_preflop_3bet" gives
    ``call_vs_preflop_3bet`` / ``raise_...`` / ``fold_...``."""

    @property
    def faced_key(self) -> str:
        return f"cnt_{self.street}_face_{self.name}"

    @property
    def called_key(self) -> str:
        return f"cnt_{self.street}_call_{self.name}"

    @property
    def raised_key(self) -> str:
        return f"cnt_{self.street}_raise_{self.name}"

    @property
    def keys(self) -> tuple[str, str, str]:
        return (self.faced_key, self.called_key, self.raised_key)


SITUATIONS: tuple[Situation, ...] = (
    Situation(
        'enum_p_3bet_action',
        'p',
        '3bet',
        'v3B',
        'a preflop 3-bet',
        'vs_preflop_3bet',
    ),
    Situation(
        'enum_p_4bet_action',
        'p',
        '4bet',
        'v4B',
        'a preflop 4-bet',
        'vs_preflop_4bet',
    ),
    Situation(
        'enum_p_squeeze_action',
        'p',
        'squeeze',
        'vSQ',
        'a preflop squeeze',
        'vs_preflop_squeeze',
    ),
    Situation(
        'enum_f_cbet_action',
        'f',
        'cbet',
        'vFCB',
        'a flop c-bet',
        'vs_flop_cbet',
    ),
    Situation(
        'enum_f_donk_action',
        'f',
        'donk',
        'vFDk',
        'a flop donk bet',
        'vs_flop_donk',
    ),
    Situation(
        'enum_f_3bet_action',
        'f',
        '3bet',
        'vF3B',
        'a flop 3-bet',
        'vs_flop_3bet',
    ),
    Situation(
        'enum_f_4bet_action',
        'f',
        '4bet',
        'vF4B',
        'a flop 4-bet',
        'vs_flop_4bet',
    ),
    Situation(
        'enum_t_cbet_action',
        't',
        'cbet',
        'vTCB',
        'a turn c-bet',
        'vs_turn_cbet',
    ),
    Situation(
        'enum_t_donk_action',
        't',
        'donk',
        'vTDk',
        'a turn donk bet',
        'vs_turn_donk',
    ),
    Situation(
        'enum_t_3bet_action',
        't',
        '3bet',
        'vT3B',
        'a turn 3-bet',
        'vs_turn_3bet',
    ),
    Situation(
        'enum_t_4bet_action',
        't',
        '4bet',
        'vT4B',
        'a turn 4-bet',
        'vs_turn_4bet',
    ),
    Situation(
        'enum_t_float_action',
        't',
        'float',
        'vTFl',
        'the turn barrel, having called the flop c-bet in position',
        'float_turn',
    ),
    Situation(
        'enum_r_cbet_action',
        'r',
        'cbet',
        'vRCB',
        'a river c-bet',
        'vs_river_cbet',
    ),
    Situation(
        'enum_r_donk_action',
        'r',
        'donk',
        'vRDk',
        'a river donk bet',
        'vs_river_donk',
    ),
    Situation(
        'enum_r_3bet_action',
        'r',
        '3bet',
        'vR3B',
        'a river 3-bet',
        'vs_river_3bet',
    ),
    Situation(
        'enum_r_4bet_action',
        'r',
        '4bet',
        'vR4B',
        'a river 4-bet',
        'vs_river_4bet',
    ),
    Situation(
        'enum_r_float_action',
        'r',
        'float',
        'vRFl',
        'the river barrel, having called the turn bet in position',
        'float_river',
    ),
)

CACHE_KEYS: tuple[str, ...] = tuple(key for situation in SITUATIONS for key in situation.keys)


def derive_counters(player_stats: dict[str, Any]) -> None:
    """Turn each response char into the faced/called/raised counters.

    Called once per player per hand, straight after the enums are computed. A
    missing or "N" enum leaves all three at 0, which is what an absent
    situation should add to the cache.
    """
    for situation in SITUATIONS:
        response = player_stats.get(situation.enum_key, "N")
        faced = response in ("F", "C", "R")
        player_stats[situation.faced_key] = int(faced)
        player_stats[situation.called_key] = int(response == "C")
        player_stats[situation.raised_key] = int(response == "R")
