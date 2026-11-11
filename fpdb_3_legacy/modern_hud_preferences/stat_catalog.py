"""The stats the HUD Preferences editor can offer, without Qt.

Three sources feed the catalogue:

* the classic stats: every function of ``Stats.STATLIST`` that describes itself
  through ``Stats.get_valid_stats()`` -- the helpers that slip into
  ``STATLIST`` (``get_logger``, ``STAT_FUNCTIONS``...) have no description and
  are left out;
* the declarative ``stats.d`` descriptors (origin ``registry``) that are not
  already a classic stat: ``Stats.do_stat`` falls back to them, so the HUD draws
  them like any other name;
* the analytics definitions (origin ``analytics``), which a cell only shows
  with the ``data_*`` attributes ``hud_panel_editor.stat_entry_attributes``
  writes.

A classic stat and an analytics definition may share a name and mean two
different things, so an entry is identified by its :attr:`CatalogEntry.key`,
``"<origin>:<name>"``, not by its name. The key is what the catalogue widget
puts on the clipboard of a drag (:data:`MIME_TYPE`).

Categories come from :data:`_EXACT` and :data:`_PREFIXES`, then from the street
named in the stat (``fold_vs_turn_cbet`` is a turn stat); a name no rule knows
goes to :data:`OTHER`, a group the widget shows like any other, never hidden.
The popup icons' table (``PopupIcons.get_stat_category``) was not reused: it
names about half of the stats and files the rest under "general" without
saying so.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from fpdb_3_legacy.i18n import N_
from fpdb_3_legacy.i18n import gettext as _

# What a drag from the catalogue carries; the payload is the entry's key.
MIME_TYPE: Final = "application/x-fpdb-hud-stat"

ORIGIN_CLASSIC: Final = "classic"
ORIGIN_REGISTRY: Final = "registry"
ORIGIN_ANALYTICS: Final = "analytics"
ORIGINS: Final = (ORIGIN_CLASSIC, ORIGIN_REGISTRY, ORIGIN_ANALYTICS)

PLAYER: Final = "player"
PREFLOP: Final = "preflop"
STEAL: Final = "steal"
FLOP: Final = "flop"
TURN: Final = "turn"
RIVER: Final = "river"
SEVENTH: Final = "seventh"
POSTFLOP: Final = "postflop"
RESULTS: Final = "results"
TOURNAMENT: Final = "tournament"
AOF: Final = "aof"
OTHER: Final = "other"

# Category ids in display order, with their English labels (translated by
# category_label). N_ marks them for the catalogue without translating at
# import time, when no language is installed yet.
CATEGORIES: Final[dict[str, str]] = {
    PLAYER: N_("Player"),
    PREFLOP: N_("Preflop"),
    STEAL: N_("Steal and blinds"),
    FLOP: N_("Flop / 4th street"),
    TURN: N_("Turn / 5th street"),
    RIVER: N_("River / 6th street"),
    SEVENTH: N_("7th street"),
    POSTFLOP: N_("Postflop, all streets"),
    RESULTS: N_("Results and showdown"),
    TOURNAMENT: N_("Tournament and stack"),
    AOF: N_("All-in or Fold"),
    OTHER: N_("Other"),
}

ORIGIN_LABELS: Final[dict[str, str]] = {
    ORIGIN_CLASSIC: N_("classic"),
    ORIGIN_REGISTRY: N_("stats.d"),
    ORIGIN_ANALYTICS: N_("analytics"),
}

# Names whose category their spelling does not tell.
_EXACT_BY_CATEGORY: Final[dict[str, tuple[str, ...]]] = {
    PLAYER: ("blank", "game_abbr", "n", "player_note", "playername", "playerprofile", "playershort", "starthands"),
    PREFLOP: (
        "car0",
        "cfour_B",
        "cold_call",
        "ctb",
        "f_3bet",
        "f_4bet",
        "face_limpers",
        "fbr",
        "fold_to_squeeze",
        "fold_vs_4bet",
        "four_B",
        "four_bet",
        "iso",
        "limp",
        "open_limp",
        "pfr",
        "rfi",
        "squeeze",
        "straddle",
        "three_B",
        "three_bet",
        "vpip",
        "vpip_pfr_ratio",
    ),
    STEAL: (
        "amt_blind",
        "call_vs_steal",
        "f_BB_steal",
        "f_SB_steal",
        "f_steal",
        "raiseToSteal",
        "resteal",
        "s_steal",
        "steal",
        "three_bet_vs_steal",
    ),
    FLOP: ("a_freq1", "cb1", "cb_ip", "cb_oop", "cr1", "dbr1", "f_cb1", "f_dbr1", "ffreq1", "probe_bet"),
    TURN: ("a_freq2", "cb2", "cr2", "dbr2", "f_cb2", "f_dbr2", "ffreq2", "float_bet"),
    RIVER: ("a_freq3", "cb3", "cr3", "dbr3", "f_cb3", "f_dbr3", "ffreq3"),
    SEVENTH: ("a_freq4", "cb4", "cr4", "f_cb4", "ffreq4"),
    POSTFLOP: (
        "a_freq_123",
        "agg_fact",
        "agg_fact_pct",
        "cbet",
        "check_raise_frequency",
        "fold_to_allin",
        "overbet_frequency",
        "triple_barrel",
    ),
    RESULTS: (
        "BBper100",
        "WMsF",
        "bbper100",
        "non_sd_winrate",
        "profit100",
        "saw_f",
        "sd_winrate",
        "totalprofit",
        "wmsd",
        "wsd",
        "wtsd",
        "wwsf",
    ),
    TOURNAMENT: ("bbstack", "bounty", "covers", "m_ratio"),
}
_EXACT: Final[dict[str, str]] = {name: category for category, names in _EXACT_BY_CATEGORY.items() for name in names}

# Prefixes, tried in order after the exact names: "f_" would claim "f_steal"
# if the exact table did not come first.
_PREFIXES: Final[tuple[tuple[str, str], ...]] = (
    ("aof_", AOF),
    ("chipev_", TOURNAMENT),
    ("stack_", TOURNAMENT),
    ("amt_bet_", RESULTS),
    ("three_bet_", PREFLOP),
    ("four_bet_", PREFLOP),
    ("squeeze_", PREFLOP),
    ("rfi_", PREFLOP),
    ("gp_", PREFLOP),
    ("p_", PREFLOP),
    ("f_", FLOP),
    ("t_", TURN),
    ("r_", RIVER),
)

# A word of the name that says the street, in the order they are tried:
# "fold_to_3bet_preflop" is preflop, "fold_bb_to_steal" a steal stat.
_WORDS: Final[tuple[tuple[str, str], ...]] = (
    ("preflop", PREFLOP),
    ("flop", FLOP),
    ("turn", TURN),
    ("river", RIVER),
    ("steal", STEAL),
)


def category_for(name: str) -> str:
    """The category id of a stat name; :data:`OTHER` when no rule knows it."""
    if name in _EXACT:
        return _EXACT[name]
    for prefix, category in _PREFIXES:
        if name.startswith(prefix):
            return category
    words = set(name.lower().split("_"))
    for word, category in _WORDS:
        if word in words:
            return category
    return OTHER


def category_label(category: str) -> str:
    """The category as the user reads it, translated."""
    return _(CATEGORIES.get(category, CATEGORIES[OTHER]))


def origin_label(origin: str) -> str:
    """Where an entry comes from, as the user reads it, translated."""
    return _(ORIGIN_LABELS.get(origin, origin))


def make_key(origin: str, name: str) -> str:
    """The identity of an entry: its origin and its name."""
    return f"{origin}:{name}"


@dataclass(frozen=True)
class CatalogEntry:
    """One stat the editor can place in a cell."""

    key: str
    name: str
    description: str
    category: str
    origin: str
    # The data_* attributes a cell of this stat carries (analytics only).
    attributes: Mapping[str, str] = field(default_factory=dict)

    @property
    def category_label(self) -> str:
        return category_label(self.category)

    @property
    def origin_label(self) -> str:
        return origin_label(self.origin)

    def search_text(self) -> str:
        """Everything a filter looks at, folded for comparison."""
        parts = (self.name, self.description, self.category, self.category_label, CATEGORIES.get(self.category, ""))
        return " ".join(parts + (self.origin, self.origin_label)).casefold()

    def matches(self, text: str) -> bool:
        """Whether every word of *text* is in the name, description, category or origin."""
        haystack = self.search_text()
        return all(word in haystack for word in text.casefold().split())

    def new_item(self, row: int, col: int) -> dict[str, Any]:
        """A stat item for the editor's profile dict, at ``(row, col)``."""
        item: dict[str, Any] = {"row": int(row), "col": int(col), "stat": self.name, "click": "", "popup": ""}
        item.update(self.attributes)
        return item


class StatCatalog:
    """The entries, by key, in category then name order."""

    def __init__(self, entries: Iterable[CatalogEntry]) -> None:
        order = {category: index for index, category in enumerate(CATEGORIES)}
        unique: dict[str, CatalogEntry] = {}
        for entry in entries:
            unique.setdefault(entry.key, entry)
        self.entries: tuple[CatalogEntry, ...] = tuple(
            sorted(
                unique.values(),
                key=lambda e: (order.get(e.category, len(order)), e.name.casefold(), ORIGINS.index(e.origin)),
            )
        )
        self._by_key = {entry.key: entry for entry in self.entries}

    def __len__(self) -> int:
        return len(self.entries)

    def __iter__(self) -> Iterator[CatalogEntry]:
        return iter(self.entries)

    def __contains__(self, key: object) -> bool:
        return key in self._by_key

    def get(self, key: str) -> CatalogEntry | None:
        return self._by_key.get(key)

    def filter(self, text: str = "") -> tuple[CatalogEntry, ...]:
        """The entries *text* matches; all of them for an empty text."""
        if not text.strip():
            return self.entries
        return tuple(entry for entry in self.entries if entry.matches(text))

    def grouped(self, entries: Sequence[CatalogEntry] | None = None) -> list[tuple[str, list[CatalogEntry]]]:
        """``(category, entries)`` pairs in display order, empty groups left out."""
        groups: dict[str, list[CatalogEntry]] = {}
        for entry in self.entries if entries is None else entries:
            groups.setdefault(entry.category, []).append(entry)
        order = list(CATEGORIES)
        return sorted(groups.items(), key=lambda pair: order.index(pair[0]) if pair[0] in order else len(order))


def classic_entries(stat_names: Iterable[str], descriptions: Mapping[str, Any]) -> list[CatalogEntry]:
    """The ``Stats.STATLIST`` functions that describe themselves."""
    entries = []
    for name in stat_names:
        description = descriptions.get(name)
        if not isinstance(description, str) or not description:
            continue
        entries.append(
            CatalogEntry(
                key=make_key(ORIGIN_CLASSIC, name),
                name=name,
                description=description,
                category=category_for(name),
                origin=ORIGIN_CLASSIC,
            )
        )
    return entries


def choice_entries(choices: Iterable[Any], classic_names: Iterable[str] = ()) -> list[CatalogEntry]:
    """The ``hud_panel_editor`` choices, without the registry ones a classic stat shadows.

    ``Stats.do_stat`` reaches a ``stats.d`` descriptor only for a name that is
    not a classic stat, so a registry choice of the same name is the classic
    stat and is not listed twice.
    """
    from fpdb_3_legacy import hud_panel_editor  # noqa: PLC0415 - keeps this module import-light

    shadowed = set(classic_names)
    entries = []
    for choice in choices:
        if choice.source == ORIGIN_REGISTRY and choice.name in shadowed:
            continue
        if choice.source not in (ORIGIN_REGISTRY, ORIGIN_ANALYTICS):
            continue
        written = hud_panel_editor.stat_entry_attributes(choice)
        attributes = {key: str(value) for key, value in written.items() if key.startswith("data_")}
        entries.append(
            CatalogEntry(
                key=make_key(choice.source, choice.name),
                name=choice.name,
                description=str(choice.label or choice.name),
                category=category_for(choice.name),
                origin=choice.source,
                attributes=attributes,
            )
        )
    return entries


def build_catalog(
    *,
    stat_names: Iterable[str] | None = None,
    descriptions: Mapping[str, Any] | None = None,
    choices: Iterable[Any] | None = None,
) -> StatCatalog:
    """The catalogue of the running fpdb, or of the sources given.

    ``Stats`` is imported here rather than at module level: it pulls in the
    database layer, which the editor does not need until the catalogue is shown.
    """
    if stat_names is None or descriptions is None:
        from fpdb_3_legacy import Stats  # noqa: PLC0415 - heavy, see the docstring

        stat_names = Stats.STATLIST if stat_names is None else stat_names
        descriptions = Stats.get_valid_stats() if descriptions is None else descriptions
    if choices is None:
        from fpdb_3_legacy import hud_panel_editor  # noqa: PLC0415

        choices = hud_panel_editor.stat_choices()
    names = list(stat_names)
    return StatCatalog(classic_entries(names, descriptions) + choice_entries(choices, names))
