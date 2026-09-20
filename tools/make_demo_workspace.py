#!/usr/bin/env python3
"""Build the complete fpdb demo workspace: hands, database, HUDs, presets, README.

``tools/make_demo_db.py`` answers "where do fictional hands come from". This
answers the next question -- "what does a contributor open to see what fpdb
does" -- with one command and one directory:

    python tools/make_demo_workspace.py                  # ~/fpdb-demo
    python tools/make_demo_workspace.py --hands 8000 --out /tmp/fpdb-demo

    fpdb-demo/
      hands/                    the invented hand histories
      demo.db3                  SQLite database: imported, analytics current
      HUD_config.xml            default -- the Basic reference HUD, selected
      HUD_config.advanced.xml   the same table, Advanced HUD selected
      HUD_config.dynamic.xml    ... and Dynamic, with its panels enabled
      research_presets.json     saved questions to copy into ``~/.fpdb``
      demo_examples.json        one measured question per Research view
      README.md                 how to launch it, and what to look at
      screenshots/              where ``capture_wiki_screenshots.py`` writes

Everything the workspace needs is inside it, and nothing here writes to the
user's own configuration: the base file is *copied* from ``HUD_config.xml`` (as
``make_demo_db`` already did), and every later edit -- installing the reference
HUDs, selecting a profile, enabling the dynamic panels -- happens to a copy
inside the workspace. The user's own ``~/.fpdb`` is never opened for writing,
which is what makes "look at the demo" safe to do without a backup.

Three claims this file makes are checked rather than asserted, because they are
the ones that quietly rot:

* **the analytics tables are current** -- the workspace reports which
  subsystems were stale and rebuilds them, so Research is never pointed at rows
  derived by different rules;
* **each configuration selects the profile its name says** -- the profile rule
  is written through ``Config``, then the file is reloaded and *resolved* the
  way the HUD resolves it at a table;
* **each Research view has a non-empty, deterministic example** -- every
  question :func:`demo_views` returns is executed against the freshly built
  database, and the counts are written to ``demo_examples.json`` so a change
  that empties a view is a changed number rather than a blank screenshot.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from tools import make_demo_db  # noqa: E402 - the repo has to be importable first


def package_dir() -> Path:
    """Where the shipped ``.fpdbhud`` reference packages live."""
    return REPO / "hud-packages"


@dataclass(frozen=True)
class HudVariant:
    """One reference HUD staged for the demo, and the configuration that selects it."""

    name: str
    package: str
    profile: str
    config: str
    note: str


# The three reference HUDs (#332), one configuration each. All three packages go
# into every configuration; the variants differ only in the profile rule that
# selects one, which is exactly how a user would switch between them.
HUD_VARIANTS: Final[tuple[HudVariant, ...]] = (
    HudVariant(
        "basic",
        "nlhe_6max_basic.fpdbhud",
        "nlhe_6max_basic",
        "HUD_config.xml",
        "Eight numbers, no analytics dependency. What the workspace opens with.",
    ),
    HudVariant(
        "advanced",
        "nlhe_6max_advanced.fpdbhud",
        "nlhe_6max_advanced",
        "HUD_config.advanced.xml",
        "Three rows plus the shipped hierarchical popup library.",
    ),
    HudVariant(
        "dynamic",
        "nlhe_6max_dynamic.fpdbhud",
        "nlhe_6max_dynamic",
        "HUD_config.dynamic.xml",
        "Blocks that follow the hand: c-bet, facing a c-bet, squeeze, and so on.",
    ),
)

# The demo hands are PokerStars no-limit Hold'em six-max ring games at one stake,
# so the rule that selects a reference HUD names exactly that table.
DEMO_SITE: Final = "PokerStars"
DEMO_GAME: Final = "holdem"
DEMO_GAME_TYPE: Final = "ring"
DEMO_SEATS: Final = 6

# One question per Research view (#331). Read from the workbench's own
# catalogue rather than restated here: the question a screenshot shows, the
# example this file documents and the view the screen offers are then one
# thing, and a view added to the workbench is measured the next time the
# workspace is built.
#
# The hands view is not a question of its own -- it is the drill-down of
# whichever row is clicked -- so it is measured separately, below.
def demo_views() -> tuple[tuple[str, str, dict[str, Any]], ...]:
    """The workbench's views, as the (id, question, preset) triples measured here."""
    from fpdb_3_legacy import research_views as rv

    return tuple(
        (spec.id, spec.question, rv.preset(spec)) for spec in rv.VIEWS if spec.kind != rv.HANDS
    )


# The row the hands view is demonstrated on: the filters of the "table" view
# narrowed to a street every workspace has a flop on.
DRILL_VIEW: Final = ("hands", {"street": "flop"}, False)

DEFAULT_SEED: Final = 20260808

# The saved questions the workspace hands the user to copy. User presets live in
# ``~/.fpdb/research_presets.json`` and the shipped library (#330) covers the
# common ones, so this file is an *example to copy* rather than an install step:
# a demo that silently rewrote the user's own saved questions would be a bug.
DEMO_PRESETS: Final[dict[str, dict[str, Any]]] = {
    "Demo: fold to a 3-bet": {
        "metric": "fold_frequency",
        "filters": {"primary_situation": "facing_3bet"},
        "description": "How often an opening raiser folds once they are three-bet.",
    },
    "Demo: c-bet size vs fold rate": {
        "metric": "fold_frequency",
        "filters": {"street": "flop", "primary_situation": "facing_cbet"},
        "group_by": ("facing_sizing_bucket",),
        "description": "Do bigger flop bets get more folds?",
    },
    "Demo: squeeze spots": {
        "metric": "raise_frequency",
        "filters": {"primary_situation": "squeeze_spot"},
        "group_by": ("position",),
        "description": "Re-raising a raise that already has a caller behind it.",
    },
    "Demo: profit by position after opening": {
        "metric": "total_profit",
        "filters": {"primary_situation": "open_raise"},
        "group_by": ("position",),
        "description": "Which seats make money from the hands they open.",
    },
}

PRESET_FILE: Final = "research_presets.json"
EXAMPLES_FILE: Final = "demo_examples.json"
SCREENSHOT_DIR: Final = "screenshots"


@dataclass
class WorkspaceReport:
    """What the build produced, as values rather than as prose.

    ``main`` prints it and the tests assert on it, so the two cannot drift: any
    claim the README makes about the workspace is in here.
    """

    root: Path
    hands: int
    hand_files: int
    config: Path
    variants: dict[str, Path] = field(default_factory=dict)
    profiles: dict[str, str] = field(default_factory=dict)
    presets: Path | None = None
    examples: Path | None = None
    readme: Path | None = None
    screenshots: Path | None = None
    stale_before_rebuild: tuple[str, ...] = ()
    rebuilt: tuple[str, ...] = ()
    view_counts: dict[str, dict[str, int]] = field(default_factory=dict)

    @property
    def profiles_are_selected(self) -> bool:
        """Whether every configuration resolves to the profile it is named for."""
        return all(self.profiles.get(variant.name) == variant.profile for variant in HUD_VARIANTS)


# ---------------------------------------------------------------------------
# The configuration, and the reference HUDs staged inside it.
# ---------------------------------------------------------------------------


def _package_root(package: str):
    """One shipped package as a minidom root, to merge into a configuration."""
    from defusedxml import minidom

    path = package_dir() / package
    if not path.is_file():
        raise FileNotFoundError(f"the reference HUD package {path} is missing")
    return minidom.parse(str(path)).documentElement


def stage_reference_huds(config_path: Path) -> list[str]:
    """Install every reference HUD into the demo configuration.

    All three at once, because a configuration that already carries them is
    what lets the variants differ by one profile rule instead of by three
    separate imports. The merge helpers are the ones HUD Preferences' import
    calls, so a package that imports cleanly there imports here.
    """
    from fpdb_3_legacy.Configuration import Config
    from fpdb_3_legacy.hud_package import install_missing_hud_package, merge_package_panel_rules

    config = Config(file=str(config_path))
    installed: list[str] = []
    for variant in HUD_VARIANTS:
        root = _package_root(variant.package)
        install_missing_hud_package(config.doc, root)
        # Only the Dynamic package carries panel rules, and its section is
        # scoped to its own profile, so staging it here changes nothing for the
        # other two variants -- which is precisely what the scoping is for.
        merge_package_panel_rules(config.doc, root, overwrite=True)
        installed.append(variant.profile)
    config.save(file=str(config_path))
    return installed


def select_profile(config_path: Path, variant: HudVariant) -> str:
    """Make one reference profile the one that applies to the demo's table.

    A profile rule, not a game binding: the rule is the shipped mechanism for
    "which HUD for which table", it is what the HUD Preferences profile tab
    edits, and it leaves the game's own default profile alone rather than
    replacing it. The file is then reloaded and resolved the way the HUD
    resolves it at a table, so the returned name is an observation.
    """
    from fpdb_3_legacy.Configuration import Config
    from fpdb_3_legacy.hud_profiles import HudContext, HudProfileRule

    config = Config(file=str(config_path))
    config.set_hud_profile_rules(
        [
            HudProfileRule.from_mapping(
                {
                    "id": f"demo-{variant.name}",
                    "site": DEMO_SITE,
                    "game": DEMO_GAME,
                    "game_type": DEMO_GAME_TYPE,
                    "seats": DEMO_SEATS,
                    "profile": variant.profile,
                },
            ),
        ],
    )
    config.save(file=str(config_path))

    reloaded = Config(file=str(config_path))
    params = reloaded.get_supported_games_parameters(
        DEMO_GAME,
        DEMO_GAME_TYPE,
        HudContext(DEMO_SITE, DEMO_GAME, DEMO_GAME_TYPE, max_seats=DEMO_SEATS, players=DEMO_SEATS),
    )
    if params is None:
        raise RuntimeError(f"{config_path} has no {DEMO_GAME}/{DEMO_GAME_TYPE} binding to select a profile for")
    return str(getattr(params["game_stat_set"], "name", ""))


def write_config_variants(base_config: Path, root: Path) -> tuple[dict[str, Path], dict[str, str]]:
    """The three configurations, each selecting its own reference HUD."""
    paths = {variant.name: root / variant.config for variant in HUD_VARIANTS}
    for variant in HUD_VARIANTS:
        target = paths[variant.name]
        if target != base_config:
            shutil.copyfile(base_config, target)
    profiles = {variant.name: select_profile(paths[variant.name], variant) for variant in HUD_VARIANTS}
    return paths, profiles


# ---------------------------------------------------------------------------
# The analytics tables, and the measured examples.
# ---------------------------------------------------------------------------


def ensure_analytics_current(config_path: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(what was stale, what was rebuilt) for the freshly imported database.

    A database this tool just created is stamped current by the importer, so
    the usual answer is "nothing". The check is still made every time, because
    the one case that matters is the other one: a code change that bumps an
    extractor version would otherwise leave the demo -- and every screenshot
    taken from it -- reading rows the current rules would not have written.
    """
    from fpdb_3_legacy.analytics_lifecycle import stale_subsystems
    from fpdb_3_legacy.analytics_rebuild import rebuild_subsystems
    from fpdb_3_legacy.Configuration import Config
    from fpdb_3_legacy.Database import Database

    config = Config(file=str(config_path))
    database = Database(config)
    try:
        stale = stale_subsystems(database)
        if not stale:
            return (), ()
        rebuild_subsystems(database, config, list(stale))
        remaining = stale_subsystems(database)
        if remaining:
            raise RuntimeError(f"the analytics rebuild left these subsystems stale: {list(remaining)}")
        return stale, stale
    finally:
        database.disconnect()


def measure_views(config_path: Path) -> dict[str, dict[str, int]]:
    """Run one question per Research view and report what each returned.

    The measurement is the point: a demo whose "13x13 range" view is empty is a
    demo that does not demonstrate the feature, and only running the query can
    tell the difference between that and a working one.
    """
    from fpdb_3_legacy import research_browser as rb
    from fpdb_3_legacy import research_views as rv
    from fpdb_3_legacy.Configuration import Config
    from fpdb_3_legacy.Database import Database

    config = Config(file=str(config_path))
    database = Database(config)
    try:
        measured: dict[str, dict[str, int]] = {}
        for view, _question, preset in demo_views():
            measured[view] = _measure(database, rv.view(view), preset)
        drill_preset = next(preset for view, _question, preset in demo_views() if view == "table")
        _view, group, numerator = DRILL_VIEW
        drill = rb.run_drill_down(
            database,
            rb.preset_to_query(drill_preset),
            group=group,
            numerator_only=numerator,
        )
        measured[_view] = {"opportunities": len(drill.hand_ids), "rows": len(drill.rows)}
        return measured
    finally:
        database.disconnect()


def _measure(database: Any, spec: Any, preset: dict[str, Any]) -> dict[str, int]:
    """What one view returns in this workspace, in its own terms.

    The whole point of the catalogue is that a view is not one query, so a view
    is not measured by one row count either: a grid is 169 cells of which some
    hold data, a composition is categories plus the decisions they could not
    classify, and a money report is groups. Documenting them all as "rows"
    would let a view that draws nothing pass as populated.
    """
    from fpdb_3_legacy import research_browser as rb
    from fpdb_3_legacy import research_views as rv

    if spec.kind == rv.GRID:
        matrix = rv.range_matrix(database, spec)
        cells = matrix.known_cells()
        return {
            "opportunities": matrix.total_opportunities,
            "rows": len(cells),
            "cells_with_data": sum(1 for cell in cells if cell.opportunities),
            "decisions_without_cards": matrix.unknown_opportunities(),
        }
    if spec.kind == rv.COMPOSITION:
        composition = rv.hand_composition(database, spec)
        return {
            "opportunities": composition.total,
            "rows": len(composition.rows),
            "classified": composition.classified,
            "without_known_cards": composition.unclassified,
        }
    if spec.kind == rv.MONEY:
        report = rv.money_report(database, spec)
        return {"opportunities": report.total.hands, "rows": len(report.rows)}
    result = rb.execute_preset(database, preset)
    return {"opportunities": int(result.total_opportunities), "rows": len(result.rows)}


def write_examples(root: Path, counts: dict[str, dict[str, int]], hands: int) -> Path:
    """The example questions, with what each returns in this workspace."""
    payload = {
        "generator": "tools/make_demo_workspace.py",
        "hands": hands,
        "views": [
            {
                "view": view,
                "question": question,
                "preset": preset,
                "result": counts.get(view, {}),
            }
            for view, question, preset in demo_views()
        ],
    }
    path = root / EXAMPLES_FILE
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# The saved questions the workspace offers to copy.
# ---------------------------------------------------------------------------


def write_presets(root: Path) -> Path:
    """Write the example preset file, validated by the code that will read it.

    Written through ``ResearchPresets`` rather than by hand, into the workspace
    directory instead of the user's config directory: the file a user copies is
    byte-for-byte the format the browser writes when they save a preset, and
    the tool never touches their own saved questions.
    """
    from fpdb_3_legacy.research_browser import ResearchPresets

    presets = ResearchPresets(directory=root)
    for name, preset in DEMO_PRESETS.items():
        presets.save(name, preset)
    stored = presets.load()
    missing = [name for name in DEMO_PRESETS if name not in stored]
    if missing:
        raise RuntimeError(f"the demo preset file did not round-trip: {missing}")
    return presets.path


# ---------------------------------------------------------------------------
# The README that ships inside the workspace.
# ---------------------------------------------------------------------------


def readme_text(report: WorkspaceReport) -> str:
    """How to launch the workspace, and what to look at once it is open."""
    lines = [
        "# fpdb demo workspace",
        "",
        "Everything in this directory is invented: the players, the hands, the",
        "statistics. Nothing here came from a real table and nothing here needs",
        "redacting before it appears in a screenshot.",
        "",
        f"Built by `tools/make_demo_workspace.py` from {report.hands} generated hands.",
        "",
        "## Launch it",
        "",
        "```",
        f"python fpdb_3_legacy/fpdb.pyw -c {report.config}",
        "```",
        "",
        "This configuration points at this directory's database only. Your own",
        "`HUD_config.xml` and your own database are not read or written by the",
        "workspace.",
        "",
        "## What to look at",
        "",
        "| Screen | What it shows |",
        "| --- | --- |",
        "| Research Browser | The built-in presets, plus one measured example question "
        f"per view in `{EXAMPLES_FILE}` |",
        "| Ring Player Stats | VPIP/PFR/3-bet spread across twelve invented styles |",
        "| Sessions and Graphs | 120 days of sessions, played by the same roster |",
        "| HUD Preferences | All three reference HUDs, and the dynamic panel editor |",
        "| Replayer | Any hand, with the decision cards |",
        "",
        "## The reference HUDs",
        "",
        "All three packages are installed in every configuration below; they",
        "differ only in which profile the demo table selects, so switching is a",
        "matter of launching with a different file rather than re-importing.",
        "",
        "| Configuration | Profile | What it shows |",
        "| --- | --- | --- |",
    ]
    by_name = {variant.name: variant for variant in HUD_VARIANTS}
    for name, path in report.variants.items():
        variant = by_name[name]
        resolved = report.profiles.get(name, "?")
        mark = "" if resolved == variant.profile else f"  ⚠ resolves to {resolved}"
        lines.append(f"| `{path.name}` | `{variant.profile}` | {variant.note}{mark} |")
    lines += [
        "",
        "The dynamic panel rules are shipped by the Dynamic package and are scoped",
        "to its own profile, so only `HUD_config.dynamic.xml` shows blocks that",
        "change with the hand. The other two keep their static grid.",
        "",
        "## Screenshots",
        "",
        "```",
        f"python tools/capture_wiki_screenshots.py --config {report.config} --out {report.screenshots}",
        "```",
        "",
        "The same seed produces the same hands, so the same statistics; the",
        "pixel output can shift between Qt versions, the data cannot.",
        "",
        "## Saved questions",
        "",
        f"`{PRESET_FILE}` holds four example presets in the format the Research",
        "browser writes. To use them as your own, copy the file to `~/.fpdb/`:",
        "",
        "```",
        f"cp {report.presets or PRESET_FILE} ~/.fpdb/{PRESET_FILE}",
        "```",
        "",
        "The demo never writes there itself, and the shipped preset library is",
        "already available without copying anything.",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Building the workspace.
# ---------------------------------------------------------------------------


def build_workspace(
    root: Path,
    *,
    hands: int = 2000,
    seed: int = DEFAULT_SEED,
    import_hands: bool = True,
) -> WorkspaceReport:
    """Build (or rebuild) the whole demo workspace at ``root``.

    The order is the one the dependencies impose: hands before a database,
    a database before anything can be measured, and the configuration before
    the HUD variants that are copies of it.
    """
    root = root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)

    hands_dir = make_demo_db.generate(root, hands, seed)
    report = WorkspaceReport(
        root=root,
        hands=hands,
        hand_files=len(list(hands_dir.glob("*.txt"))),
        config=root / "HUD_config.xml",
        screenshots=root / SCREENSHOT_DIR,
    )
    (root / SCREENSHOT_DIR).mkdir(exist_ok=True)

    config_path = make_demo_db.write_config(root)
    report.config = config_path
    if import_hands:
        make_demo_db.import_hands(config_path, hands_dir)
        # Only meaningful once there is a database: opening one that has not
        # been imported would create an empty file and call every subsystem
        # stale, which is exactly the state a generate-only run is supposed to
        # leave behind untouched.
        report.stale_before_rebuild, report.rebuilt = ensure_analytics_current(config_path)

    stage_reference_huds(config_path)
    report.variants, report.profiles = write_config_variants(config_path, root)

    if import_hands:
        report.view_counts = measure_views(config_path)

    report.presets = write_presets(root)
    if import_hands:
        report.examples = write_examples(root, report.view_counts, hands)
    report.readme = root / "README.md"
    report.readme.write_text(readme_text(report), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--hands", type=int, default=2000, help="how many hands to invent")
    parser.add_argument("--out", type=Path, default=Path.home() / "fpdb-demo", help="where to build the workspace")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="generator seed; same seed, same hands")
    parser.add_argument(
        "--generate-only",
        action="store_true",
        help="write hand histories and configuration without importing them",
    )
    args = parser.parse_args(argv)

    print(f"building the demo workspace in {args.out.expanduser()} ...")
    report = build_workspace(args.out, hands=args.hands, seed=args.seed, import_hands=not args.generate_only)

    print(f"  hands/            {report.hands} hands in {report.hand_files} session files")
    if report.stale_before_rebuild:
        print(f"  analytics         rebuilt {', '.join(report.stale_before_rebuild)}")
    else:
        print("  analytics         current")
    for variant in HUD_VARIANTS:
        resolved = report.profiles.get(variant.name, "?")
        state = "ok" if resolved == variant.profile else f"resolves to {resolved}!"
        print(f"  {report.variants[variant.name].name:26s} {variant.profile}  ({state})")
    if report.view_counts:
        print("  research views measured:")
        for view, counts in report.view_counts.items():
            print(f"    {view:14s} {counts['rows']:5d} rows, {counts['opportunities']:6d} opportunities")
    print(f"  {report.presets.name}   example saved questions (copy into ~/.fpdb to use)")
    print(f"  {report.readme.name}         how to launch it\n")
    print("Launch it:")
    print(f"    python fpdb_3_legacy/fpdb.pyw -c {report.config}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
