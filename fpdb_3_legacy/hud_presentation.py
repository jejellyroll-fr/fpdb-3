"""The shared presentation contract of the reference HUD packages (#370).

The Basic, Advanced and Dynamic packages each worked, and each looked like a
different product: three sample thresholds, three ways of writing a panel
name, three greens. The gap was never the engine, it was that nothing said
what a colour *meant*, so every package invented its own answer.

This module is that answer, in one Qt-free place the packages, the preview and
the tests all read:

* **Roles.** Every visible cell is one of six things -- who the player is, the
  sample, a core number, a contextual number, an analytics-backed number, or a
  link into a popup -- and a role decides the background it is drawn on.
* **A second channel.** A role is never carried by colour alone: each one has
  a prefix a reader can see in a screenshot, in a colour-blind palette and in
  a black-and-white print. ``H `` is the sample, ``VP`` is core preflop,
  ``>`` is navigation.
* **One low-sample rule.** A sample is thin under
  :data:`SAMPLE_LOW` hands and solid over :data:`SAMPLE_HIGH`, in all three
  packages, and a thin one is marked rather than rounded to a confident-looking
  percentage.
* **Readable panel titles.** A dynamic panel announces the spot it is about --
  ``SRP · PFR IP · Flop`` -- instead of the rule id that selected it.
* **One navigation order.** A popup tree walks the spots in the order a hand
  is played, so the reader learns the shape once.

Nothing here draws anything. :func:`describe_package` reads a ``.fpdbhud``
into the small model the preview renders and the tests assert against, which
is why a package cannot drift from its own contract without a test saying so.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import defusedxml.minidom

# ---------------------------------------------------------------------------
# Roles: what a cell is, and how that is shown twice.
# ---------------------------------------------------------------------------

ROLE_IDENTITY: Final = "identity"
ROLE_SAMPLE: Final = "sample"
ROLE_CORE: Final = "core"
ROLE_CONTEXTUAL: Final = "contextual"
ROLE_ANALYTICS: Final = "analytics"
ROLE_NAVIGATION: Final = "navigation"

ROLES: Final[tuple[str, ...]] = (
    ROLE_IDENTITY,
    ROLE_SAMPLE,
    ROLE_CORE,
    ROLE_CONTEXTUAL,
    ROLE_ANALYTICS,
    ROLE_NAVIGATION,
)

#: The background each role is drawn on. Two families, deliberately: the
#: neutral slate is "this is about the player or the hand", the indigo is
#: "this is about a decision", and the deepest indigo marks the numbers that
#: come out of the analytics tables rather than off a native column.
ROLE_BACKGROUNDS: Final[dict[str, str]] = {
    ROLE_IDENTITY: "#0F172A",
    ROLE_SAMPLE: "#0F172A",
    ROLE_CORE: "#1E1B4B",
    ROLE_CONTEXTUAL: "#172554",
    ROLE_ANALYTICS: "#312E81",
    ROLE_NAVIGATION: "#0F172A",
}

ROLE_DESCRIPTIONS: Final[dict[str, str]] = {
    ROLE_IDENTITY: "Who this seat is: the name, and the notes behind it.",
    ROLE_SAMPLE: "How many hands every other number on the block is based on.",
    ROLE_CORE: "The handful of numbers that describe a player at all.",
    ROLE_CONTEXTUAL: "A number about the spot in front of this seat right now.",
    ROLE_ANALYTICS: "Backed by the analytics tables rather than a native column.",
    ROLE_NAVIGATION: "A link: this cell opens a popup rather than answering.",
}

# ---------------------------------------------------------------------------
# Samples: one rule, three packages.
# ---------------------------------------------------------------------------

#: Under this many hands a percentage is a rumour, and the sample is drawn in
#: the warning colour with its own prefix rather than quietly.
SAMPLE_LOW: Final[int] = 25

#: Over this many hands the sample is solid enough to read the block as a
#: description of a player rather than of a session.
SAMPLE_HIGH: Final[int] = 200

#: The minimum sample a *contextual* or analytics-backed stat needs before the
#: package shows it at all. Higher than the headline threshold on purpose: a
#: c-bet-by-position number over twelve hands looks precise and is not.
CONTEXTUAL_MIN_SAMPLE: Final[int] = 40

SAMPLE_LOW_COLOR: Final = "#FF6B6B"
SAMPLE_MID_COLOR: Final = "#F2F4E6"
SAMPLE_HIGH_COLOR: Final = "#4ADE80"

#: What a package prints where a number cannot honestly be printed. One string
#: in one place, because three spellings of "not enough hands" read as three
#: different states.
UNAVAILABLE_TEXT: Final = "–"

#: The tip every package puts on its sample cell, so the reader is told the
#: rule rather than left to infer it from a colour.
SAMPLE_TIP: Final = (
    f"Hands seen: the sample every other number is based on. "
    f"Under {SAMPLE_LOW} the sample is marked as thin; over {SAMPLE_HIGH} it is solid."
)

# ---------------------------------------------------------------------------
# Panel titles: the spot, not the rule id.
# ---------------------------------------------------------------------------

#: Every dynamic panel the shipped rules can select, and the context label it
#: shows above itself. The separator is a middle dot because the parts are a
#: path through the hand -- pot shape, role, street -- rather than a sentence.
PANEL_TITLES: Final[dict[str, str]] = {
    "core": "Core",
    "preflop_open": "Preflop · Unopened",
    "preflop_facing_open": "Preflop · Facing an open",
    "preflop_facing_three_bet": "Preflop · Facing a 3-bet",
    "preflop_squeeze": "Preflop · Squeeze spot",
    "blinds_defence": "Preflop · Blind defence",
    "blinds_steal": "Preflop · Stealing",
    "preflop_deep": "Preflop · Deep stacks",
    "srp_cbet_ip": "SRP · PFR IP · Betting",
    "srp_cbet_oop": "SRP · PFR OOP · Betting",
    "srp_face_cbet_ip": "SRP · Caller IP · Facing the bet",
    "srp_face_cbet_oop": "SRP · Caller OOP · Facing the bet",
    "srp_probe_ip": "SRP · Checked to · Turn and river",
    "threebet_pot_ip": "3-bet pot · IP",
    "threebet_pot_oop": "3-bet pot · OOP",
    "fourbet_pot": "4-bet pot",
    "ssh_stack": "Short stack",
    "overbet_river": "River · Facing an overbet",
    "minbet_faced": "Facing a small bet",
}

PANEL_TITLE_BG: Final = "#312E81"
PANEL_TITLE_FG: Final = "#E6EDF3"

# ---------------------------------------------------------------------------
# Navigation: the order a hand is played.
# ---------------------------------------------------------------------------

#: The order popup navigation rows appear in, everywhere. A reader who learns
#: it in one popup has learned it in all of them, which is the only reason a
#: compact surface with depth behind it is usable at all.
SPOT_ORDER: Final[tuple[str, ...]] = (
    "Preflop",
    "Single-raised pot",
    "3-bet pot",
    "4-bet pot",
    "Sizing",
    "Stacks",
    "Position",
    "Population",
)

#: Navigation labels the shipped packs use that are the same spot under
#: another name. Kept as a table rather than as prefix-matching cleverness:
#: "Opening by position" is a position row, and no amount of string handling
#: would work that out.
SPOT_ALIASES: Final[dict[str, str]] = {
    "analytics": "Population",
    "research": "Population",
    "population": "Population",
    "opening by position": "Position",
    "steal and blind defence": "Position",
    "blind defence": "Position",
    "stack depth": "Stacks",
    "preflop sizing": "Sizing",
}

#: The rows every popup page carries whatever it is about: who the seat is,
#: the sample behind the page, and the result. They are context rather than
#: content, so a child page repeating them is not repeating itself -- and
#: anything else it repeats is a click that bought nothing (#370).
POPUP_CONTEXT_STATS: Final[frozenset[str]] = frozenset(
    {"playername", "n", "totalprofit", "bbper100"},
)

#: What marks a navigation row apart from a number, without using colour: the
#: popup renderer puts a chevron where a value would be, because a link has no
#: value and an empty cell reads as a number that failed to load.
NAVIGATION_MARKER: Final = "\u203a"


def spot_rank(label: str) -> int:
    """Where a navigation label sits in :data:`SPOT_ORDER`.

    Unknown labels sort last rather than raising: a pack may navigate
    somewhere this table has not learned about yet, and that is a reason to
    put it at the end, not to refuse to draw it.
    """
    cleaned = label.strip().strip(NAVIGATION_MARKER).strip().casefold()
    for alias, spot in SPOT_ALIASES.items():
        if cleaned.startswith(alias):
            cleaned = spot.casefold()
            break
    for index, spot in enumerate(SPOT_ORDER):
        if cleaned.startswith(spot.casefold()):
            return index
    return len(SPOT_ORDER)


# ---------------------------------------------------------------------------
# Reading a package.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PresentationStat:
    """One visible cell of a package, as the contract sees it."""

    row: int
    col: int
    name: str
    prefix: str = ""
    tip: str = ""
    popup: str = ""
    background: str = ""
    low_threshold: str = ""
    high_threshold: str = ""

    @property
    def role(self) -> str:
        """The role this cell is drawn as, read back from how it is drawn."""
        if self.name == "playername":
            return ROLE_IDENTITY
        if self.name == "n":
            return ROLE_SAMPLE
        for role, background in ROLE_BACKGROUNDS.items():
            if role in {ROLE_IDENTITY, ROLE_SAMPLE}:
                continue
            if self.background.upper() == background.upper():
                return role
        return ROLE_CORE

    @property
    def is_documented(self) -> bool:
        """Whether a reader can find out what this abbreviation means."""
        return bool(self.tip.strip())


@dataclass(frozen=True)
class PresentationPanel:
    """One block of a package: its context label and the cells in it."""

    id: str
    label: str
    position: str = ""
    rows: int = 0
    cols: int = 0
    stats: tuple[PresentationStat, ...] = ()
    title_bgcolor: str = ""
    title_fgcolor: str = ""

    @property
    def is_dynamic(self) -> bool:
        """Whether the resolver decides when this panel is on screen."""
        return self.position == "dynamic"

    @property
    def has_context_label(self) -> bool:
        """Whether the title says which spot the panel is about.

        A label equal to the block id is not a title: ``srp_cbet_ip`` names
        the rule that selected the panel, which is the one thing the reader
        already cannot see.
        """
        label = self.label.strip()
        return bool(label) and label != self.id


@dataclass(frozen=True)
class PresentationPopup:
    """One popup of a package: its own rows, and where it navigates."""

    name: str
    title: str
    stats: tuple[str, ...] = ()
    submenus: tuple[tuple[str, str], ...] = ()

    @property
    def navigation_labels(self) -> tuple[str, ...]:
        return tuple(label for label, _target in self.submenus)


@dataclass(frozen=True)
class PackagePresentation:
    """A whole ``.fpdbhud`` read as presentation rather than as XML."""

    name: str
    path: Path
    panels: tuple[PresentationPanel, ...] = ()
    popups: tuple[PresentationPopup, ...] = ()
    comment: str = ""
    profiles: Mapping[str, Any] = field(default_factory=dict)

    @property
    def stats(self) -> tuple[PresentationStat, ...]:
        return tuple(stat for panel in self.panels for stat in panel.stats)

    @property
    def dynamic_panels(self) -> tuple[PresentationPanel, ...]:
        return tuple(panel for panel in self.panels if panel.is_dynamic)

    def popup(self, name: str) -> PresentationPopup | None:
        return next((popup for popup in self.popups if popup.name == name), None)

    def undocumented_stats(self) -> tuple[PresentationStat, ...]:
        """Cells whose abbreviation a reader has no way to expand."""
        return tuple(
            stat for stat in self.stats
            if stat.name != "playername" and not stat.is_documented
        )


def _text_of(node: Any) -> str:
    return "".join(
        child.data for child in node.childNodes if child.nodeType == child.TEXT_NODE
    )


def _stat_from(node: Any) -> PresentationStat:
    raw = node.getAttribute("_rowcol") or "(1,1)"
    try:
        row, col = (int(part) for part in raw.strip("()").split(","))
    except ValueError:
        row, col = 1, 1
    return PresentationStat(
        row=row,
        col=col,
        name=node.getAttribute("_stat_name"),
        prefix=node.getAttribute("hudprefix"),
        tip=node.getAttribute("tip"),
        popup=node.getAttribute("popup"),
        background=node.getAttribute("hudbgcolor"),
        low_threshold=node.getAttribute("stat_loth"),
        high_threshold=node.getAttribute("stat_hith"),
    )


def _panels_from(stat_set: Any) -> tuple[PresentationPanel, ...]:
    blocks = [
        child for child in stat_set.childNodes
        if child.nodeType == child.ELEMENT_NODE and child.tagName == "block"
    ]
    if not blocks:
        # A flat stat set is one unnamed panel; naming it here keeps every
        # caller from having to special-case the shape.
        return (
            PresentationPanel(
                id=stat_set.getAttribute("name"),
                label="",
                rows=int(stat_set.getAttribute("rows") or 0),
                cols=int(stat_set.getAttribute("cols") or 0),
                stats=tuple(_stat_from(node) for node in stat_set.getElementsByTagName("stat")),
            ),
        )
    return tuple(
        PresentationPanel(
            id=block.getAttribute("id"),
            label=block.getAttribute("label"),
            position=block.getAttribute("position"),
            rows=int(block.getAttribute("rows") or 0),
            cols=int(block.getAttribute("cols") or 0),
            stats=tuple(_stat_from(node) for node in block.getElementsByTagName("stat")),
            title_bgcolor=block.getAttribute("title_bgcolor"),
            title_fgcolor=block.getAttribute("title_fgcolor"),
        )
        for block in blocks
    )


def _popups_from(document: Any) -> tuple[PresentationPopup, ...]:
    popups = []
    for node in document.getElementsByTagName("pu"):
        own: list[str] = []
        navigation: list[tuple[str, str]] = []
        for entry in node.getElementsByTagName("pu_stat"):
            name = entry.getAttribute("pu_stat_name")
            submenu = entry.getAttribute("pu_stat_submenu")
            if submenu:
                navigation.append((name, submenu))
            else:
                own.append(name)
        popups.append(
            PresentationPopup(
                name=node.getAttribute("pu_name"),
                title=node.getAttribute("pu_title"),
                stats=tuple(own),
                submenus=tuple(navigation),
            ),
        )
    return tuple(popups)


def describe_package(path: str | Path) -> PackagePresentation:
    """Read one ``.fpdbhud`` as the presentation contract sees it."""
    path = Path(path)
    # defusedxml, like every other parser in this project: a package is a
    # file players pass to each other, and the stock parser would fetch
    # whatever an entity declaration told it to.
    document = defusedxml.minidom.parse(str(path))
    stat_sets = document.getElementsByTagName("ss")
    panels: list[PresentationPanel] = []
    for stat_set in stat_sets:
        panels.extend(_panels_from(stat_set))
    comment = "\n".join(
        node.data for node in document.childNodes if node.nodeType == node.COMMENT_NODE
    )
    return PackagePresentation(
        name=stat_sets[0].getAttribute("name") if stat_sets else path.stem,
        path=path,
        panels=tuple(panels),
        popups=_popups_from(document),
        comment=comment,
    )


#: Fictional values for the stats the reference packages show, so a preview
#: and a screenshot read like a HUD rather than like a grid of dashes. The
#: player is deliberately a recognisable invention and the sample is thin --
#: eleven hands -- because the low-sample state is the one a reader most needs
#: to recognise, and a screenshot of the comfortable case teaches nothing.
DEMO_VALUES: Final[dict[str, str]] = {
    "playername": "Cara",
    "n": "11",
    "vpip": "33",
    "pfr": "22",
    "three_B": "4.4",
    "f_3bet": "61",
    "four_B": "2.1",
    "f_4bet": "44",
    "cb1": "50.0",
    "cb2": "50.0",
    "cb3": "33.3",
    "f_cb1": "80.0",
    "f_cb2": "100.0",
    "f_cb3": "--",
    "three_B_flop": "6.0",
    "four_B_flop": "1.8",
    "steal": "38",
    "s_steal": "31",
    "f_steal": "57",
    "f_BB_steal": "62",
    "f_SB_steal": "70",
    "open_limp": "14",
    "cold_call": "9",
    "squeeze": "6.2",
    "totalprofit": "-4.14",
    "wtsd": "29",
    "triple_barrel": "18",
    "check_raise_frequency": "9",
    "fold_vs_flop_cbet": "55",
    "call_vs_flop_cbet": "33",
    "raise_vs_flop_cbet": "12",
    "fold_to_three_B_flop": "48",
    "fold_to_cbet_flop": "52",
    "float_turn": "18",
    "probe_bet_turn": "24",
    "probe_bet_river": "16",
    "a_freq2": "41",
    "fold_vs_preflop_squeeze": "66",
    "call_vs_preflop_squeeze": "24",
    "raise_vs_preflop_squeeze": "10",
    "three_bet_vs_steal": "13",
    "call_vs_steal": "41",
}


def preview_blocks(
    package: PackagePresentation,
    panel_ids: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """One package as the blocks ``HudPreviewWidget`` draws.

    ``panel_ids`` is the dynamic selection to show: a real table never has
    every panel on screen at once, so previewing all nineteen would misdescribe
    the product. ``None`` means the panels a seat sees with no rule matched --
    the ones with no position binding.

    The grid is converted from the package's one-based ``_rowcol`` to the
    preview's zero-based rows, and each cell keeps its tip, so hovering a
    preview cell answers the same question hovering the real one does.
    """
    wanted = None if panel_ids is None else {str(panel) for panel in panel_ids}
    blocks: list[dict[str, Any]] = []
    for panel in package.panels:
        if wanted is None:
            if panel.is_dynamic:
                continue
        elif panel.id not in wanted:
            continue
        blocks.append(
            {
                # An unlabelled flat package has no title bar at a table, so
                # the preview does not invent one for it either.
                "label": panel.label,
                "rows": panel.rows,
                "cols": panel.cols,
                "bordercolor": panel.title_bgcolor or PANEL_TITLE_BG,
                "title_bgcolor": panel.title_bgcolor or PANEL_TITLE_BG,
                "title_fgcolor": panel.title_fgcolor or PANEL_TITLE_FG,
                "texts": [],
                "hlines": [],
                "stats": [
                    {
                        "stat": stat.name,
                        "row": max(stat.row - 1, 0),
                        "col": max(stat.col - 1, 0),
                        "hudprefix": stat.prefix,
                        "hudbgcolor": stat.background,
                        "tip": stat.tip,
                        "popup": stat.popup,
                    }
                    for stat in panel.stats
                ],
            },
        )
    return blocks


def popup_paths(package: PackagePresentation) -> list[tuple[str, ...]]:
    """Every navigation path a reader can walk inside one package.

    Depth-first from each popup a table cell opens, so a test can assert that
    every link resolves and a preview can list the paths without opening a
    poker table. A path that revisits a popup stops there rather than looping.
    """
    entry_points = sorted({stat.popup for stat in package.stats if stat.popup})
    paths: list[tuple[str, ...]] = []

    def walk(name: str, trail: tuple[str, ...]) -> None:
        if name in trail:
            return
        trail = (*trail, name)
        popup = package.popup(name)
        if popup is None or not popup.submenus:
            paths.append(trail)
            return
        for label, target in popup.submenus:
            if package.popup(target) is None:
                # A link out of this package into the shipped popup library:
                # the path ends here, named by where it goes.
                paths.append((*trail, f"{label} -> {target}"))
                continue
            walk(target, trail)

    for entry in entry_points:
        walk(entry, ())
    return paths


def reference_packages_dir() -> Path:
    """Where the shipped reference packages live."""
    return Path(__file__).resolve().parent.parent / "hud-packages"


def reference_packages() -> dict[str, Path]:
    """The three reference packages, by the short name a reader uses."""
    directory = reference_packages_dir()
    return {
        "basic": directory / "nlhe_6max_basic.fpdbhud",
        "advanced": directory / "nlhe_6max_advanced.fpdbhud",
        "dynamic": directory / "nlhe_6max_dynamic.fpdbhud",
    }


def panel_title(panel_id: str) -> str:
    """The readable context label of one dynamic panel."""
    return PANEL_TITLES.get(panel_id, panel_id.replace("_", " ").title())


def sample_attributes() -> dict[str, str]:
    """The sample cell's thresholds and colours, as package attributes.

    Written once so the three packages cannot disagree about where thin
    becomes readable.
    """
    return {
        "stat_loth": str(SAMPLE_LOW),
        "stat_locolor": SAMPLE_LOW_COLOR,
        "stat_midcolor": SAMPLE_MID_COLOR,
        "stat_hith": str(SAMPLE_HIGH),
        "stat_hicolor": SAMPLE_HIGH_COLOR,
    }


def navigation_rows_in_order(labels: Iterable[str]) -> bool:
    """Whether a popup's navigation rows follow :data:`SPOT_ORDER`."""
    ranks = [spot_rank(label) for label in labels]
    return ranks == sorted(ranks)


__all__ = [
    "CONTEXTUAL_MIN_SAMPLE",
    "DEMO_VALUES",
    "NAVIGATION_MARKER",
    "PANEL_TITLES",
    "PANEL_TITLE_BG",
    "PANEL_TITLE_FG",
    "POPUP_CONTEXT_STATS",
    "ROLES",
    "ROLE_ANALYTICS",
    "ROLE_BACKGROUNDS",
    "ROLE_CONTEXTUAL",
    "ROLE_CORE",
    "ROLE_DESCRIPTIONS",
    "ROLE_IDENTITY",
    "ROLE_NAVIGATION",
    "ROLE_SAMPLE",
    "SAMPLE_HIGH",
    "SAMPLE_HIGH_COLOR",
    "SAMPLE_LOW",
    "SAMPLE_LOW_COLOR",
    "SAMPLE_MID_COLOR",
    "SAMPLE_TIP",
    "SPOT_ALIASES",
    "SPOT_ORDER",
    "UNAVAILABLE_TEXT",
    "PackagePresentation",
    "PresentationPanel",
    "PresentationPopup",
    "PresentationStat",
    "describe_package",
    "navigation_rows_in_order",
    "panel_title",
    "popup_paths",
    "preview_blocks",
    "reference_packages",
    "reference_packages_dir",
    "sample_attributes",
    "spot_rank",
]
