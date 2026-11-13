"""Which games and variants a HUD stat applies to, for the Stats Guide (issue #751).

The generator measures most of it on the regression corpus; this module names
the game families and their streets, and holds the rules for the stats that read
no HudCache column (display, last-hand and All-in-or-Fold stats).
"""

from __future__ import annotations

from collections.abc import Callable

BASE_LABELS = {
    "hold": "Hold'em / Omaha (flop games)",
    "stud": "Stud / Razz",
    "draw": "Draw (2-7, A-5, Badugi, 5-card draw...)",
}

# What a street number of the database is, per game family (Hand.actionStreets).
_STREET_NAMES = {
    "hold": {0: "preflop", 1: "on the flop", 2: "on the turn", 3: "on the river"},
    "stud": {0: "on 3rd street", 1: "on 4th street", 2: "on 5th street", 3: "on 6th street", 4: "on 7th street"},
    "draw": {
        0: "before the first draw",
        1: "after the first draw",
        2: "after the second draw (triple draw)",
        3: "after the third draw (triple draw)",
    },
}

TOURNAMENTS = "Tournaments (MTT and SnG alike: the HUD reads one tournament game type for both)"
CASH = "Cash games"


def street_label(base: str, street: int | None) -> str:
    """ "yes", or where a street-N stat happens in this game family."""
    if street is None:
        return "yes"
    name = _STREET_NAMES[base].get(street)
    return f"yes, {name}" if name else ""


def games_for(entry: dict) -> list[str]:
    """Cash and/or tournaments, from the descriptor scope or the stat's nature."""
    name = entry["name"]
    if entry["origin"] == "registry" and name.startswith("chipev_"):
        return [TOURNAMENTS]
    if name in {
        "BBper100",
        "bbper100",
        "profit100",
        "totalprofit",
        "amt_blind",
        "amt_bet_p",
        "amt_bet_f",
        "amt_bet_t",
        "amt_bet_r",
        "amt_bet_ttl",
    }:
        return [CASH, TOURNAMENTS + "; amounts are tournament chips there, not money"]
    return [CASH, TOURNAMENTS]


_ALL = {"hold": "yes", "stud": "yes", "draw": "yes"}
_HOLD_ONLY = {"hold": "yes", "stud": "", "draw": ""}


_NO_VARIANT = {"hold": "", "stud": "", "draw": ""}
_SPLASH = frozenset({"aof_splash_freq", "aof_splash_won"})

# (does this rule cover the stat?, games, variants), tried in order.
_Rule = tuple[Callable[[str], bool], list[str], dict[str, str]]
_NATIVE_RULES: tuple[_Rule, ...] = (
    (
        lambda n: n.startswith("aof_") and n not in _SPLASH | {"aof_showdowns"},
        ["All-in or Fold cash tables (AoF Hold'em and AoF Omaha)"],
        _HOLD_ONLY,
    ),
    (lambda n: n in _SPLASH, ["Cash tables of rooms that add splash pots"], _HOLD_ONLY),
    (
        lambda n: n == "starthands",
        [CASH, TOURNAMENTS],
        {"hold": "Hold'em only (the query is limited to holdem)", "stud": "", "draw": ""},
    ),
    (lambda n: n == "bounty", ["Knockout (bounty) tournaments"], _ALL),
    (
        lambda n: n in {"m_ratio", "bbstack"},
        [TOURNAMENTS + "; computed in cash games too, where it means less"],
        _ALL,
    ),
    (
        lambda n: (
            n
            in {
                "blank",
                "game_abbr",
                "player_note",
                "playername",
                "playershort",
                "playerprofile",
                "covers",
                "stack_amount",
                "stack_bb",
                "stack_native_bb",
                "n",
            }
        ),
        [CASH, TOURNAMENTS],
        _ALL,
    ),
    (
        lambda n: (
            n
            in {
                "call_vs_steal",
                "iso",
                "three_bet_vs_steal",
                "avg_bet_size_flop",
                "avg_bet_size_turn",
                "avg_bet_size_river",
            }
        ),
        ["none (shows no data)"],
        _NO_VARIANT,
    ),
)


def applies_override(name: str, origin: str) -> dict | None:
    """Applicability of the stats that do not read HudCache columns; None for the measured ones."""
    rules: tuple[_Rule, ...] = ()
    if origin == "analytics":
        variants = {"hold": "", "stud": "", "draw": "yes"} if name == "draw_decision_distribution" else _ALL
        rules = ((lambda _n: True, [CASH, TOURNAMENTS], variants),)
    elif origin == "native":
        rules = _NATIVE_RULES
    found = next((rule for rule in rules if rule[0](name)), None)
    return None if found is None else {"games": list(found[1]), "variants": dict(found[2])}


def applies_lines(entry: dict, corpus: dict) -> list[tuple[str, str]]:
    """("Games", ...) and one line per game family, for the guide and the app."""
    applies = entry.get("applies") or {}
    games = applies.get("games") or ["none: the stat shows no data"]
    lines = [("Games", "; ".join(games))]
    for base, label in BASE_LABELS.items():
        value = applies.get("variants", {}).get(base, "")
        if not value:
            count = sum(n for kind, n in corpus.get("hands", {}).items() if kind.endswith(":" + base))
            value = (
                "no data"
                if entry.get("status") in ("deprecated", "input-missing")
                else f"no data (its columns stay empty on all {count} {label.split(' (')[0]} test hands)"
            )
        lines.append((label, value))
    return lines
