"""The demo workspace (#333): one command, and what it promises.

``tools/make_demo_workspace.py`` exists to make a claim that a contributor can
check without private data: open this directory and every advanced screen is
populated with invented hands. These tests are that claim in executable form --
they build a small workspace end to end and then check the things that quietly
rot when nobody is looking:

* the files are all there, and the tool says where they are;
* every Research view answers a non-empty, deterministic question, measured by
  running the query rather than by inspecting the files it wrote;
* each generated configuration resolves to the reference HUD its name promises,
  and the dynamic panels stay scoped to the profile that ships them;
* the corpus really covers the behaviours the views advertise -- positional
  opening, three-bet defence, squeeze, c-bet responses, several bet sizes,
  turn and river continuation, and known hole cards;
* the same seed produces the same hands, so the same statistics;
* nothing outside the workspace is written, including the user's own config
  directory.

The count floors in :data:`MINIMUM_COVERAGE` are deliberately far below what a
build of this size produces: they are there to catch a behaviour disappearing,
not to pin today's exact frequencies.
"""

from __future__ import annotations

import collections
import json
import sqlite3
from pathlib import Path

import pytest

from tools import make_demo_db, make_demo_workspace

# Big enough that every view has something to say, small enough that the whole
# workspace builds in seconds -- the point is coverage, not volume.
HANDS = 400

# Situation labels the corpus must produce, with floors set well under the
# observed counts so that a change in *behaviour* fails and a change in
# frequency does not. A label here is a behaviour a view demonstrates.
MINIMUM_COVERAGE = {
    # positional opening
    "open_raise": 100,
    "steal_spot": 100,
    "open_fold": 200,
    "open_limp": 5,
    # three-betting and facing it
    "three_bet": 40,
    "facing_3bet": 120,
    "opener_vs_3bet": 30,
    "four_bet": 5,
    # squeeze
    "squeeze_spot": 100,
    "squeeze": 10,
    "squeeze_defence": 40,
    # c-bet and the responses to it
    "cbet_spot": 120,
    "cbet": 60,
    "facing_cbet": 80,
    "facing_raise": 30,
    "donk": 20,
    "check_raise": 5,
    # turn and river continuation
    "probe": 8,
    "delayed_cbet": 5,
    # population contrast
    "heads_up": 400,
    "multiway": 800,
}

# Situations per street, so "turn and river continuation" is measured on the
# streets themselves and not only through the labels above.
MINIMUM_STREET_COVERAGE = {0: 1000, 1: 300, 2: 200, 3: 120}

# Flop texture variety: a board view over one texture is not a board view.
# ``pairing`` asks for two, not three: three cards can only be unpaired, paired,
# or -- when the same rank shows up three times, on about one board in four
# hundred -- trips. Demanding the third value made the assertion depend on
# whether such a board happened to be dealt, which is luck rather than coverage.
MINIMUM_FLOPS = {"suit_structure": 3, "rank_bucket": 4, "pairing": 2, "connectivity": 2}


@pytest.fixture(scope="module")
def workspace(tmp_path_factory) -> make_demo_workspace.WorkspaceReport:
    root = tmp_path_factory.mktemp("demo-workspace")
    return make_demo_workspace.build_workspace(root, hands=HANDS)


@pytest.fixture(scope="module")
def demo_db(workspace: make_demo_workspace.WorkspaceReport) -> sqlite3.Connection:
    connection = sqlite3.connect(workspace.root / "demo.db3")
    yield connection
    connection.close()


def _labels(demo_db: sqlite3.Connection) -> collections.Counter:
    """Every situation label the imported hands produced, with its count."""
    counts: collections.Counter = collections.Counter()
    for (raw,) in demo_db.execute("SELECT labels FROM HandsSituations"):
        counts.update(json.loads(raw))
    return counts


# ---------------------------------------------------------------------------
# One command, a complete workspace.
# ---------------------------------------------------------------------------


def test_one_command_builds_a_self_contained_workspace(workspace) -> None:
    root = workspace.root
    assert (root / "demo.db3").is_file()
    assert (root / "README.md").is_file()
    assert (root / make_demo_workspace.SCREENSHOT_DIR).is_dir()
    assert workspace.hand_files >= 1
    assert sorted(path.name for path in root.glob("lands/*.txt")) == []
    hands = sorted((root / "hands").glob("*.txt"))
    assert len(hands) == workspace.hand_files
    assert sum(len(path.read_text(encoding="utf-8").split("PokerStars Hand #")) - 1 for path in hands) == HANDS


def test_the_workspace_ships_one_configuration_per_reference_hud(workspace) -> None:
    assert {variant.name for variant in make_demo_workspace.HUD_VARIANTS} == set(workspace.variants)
    for variant in make_demo_workspace.HUD_VARIANTS:
        assert workspace.variants[variant.name].is_file()
    # The default the README tells the reader to launch is the Basic one.
    basic = next(v for v in make_demo_workspace.HUD_VARIANTS if v.name == "basic")
    assert workspace.config == workspace.variants[basic.name]


def test_each_configuration_selects_the_profile_its_name_promises(workspace) -> None:
    """Not "the file has a rule" -- the rule *resolves*, the way the HUD does."""
    assert workspace.profiles, "the build reported no resolved profiles"
    assert workspace.profiles_are_selected, workspace.profiles
    for variant in make_demo_workspace.HUD_VARIANTS:
        assert workspace.profiles[variant.name] == variant.profile


def test_every_reference_package_is_staged_in_every_configuration(workspace) -> None:
    """Switching between the reference HUDs is a rule, not a re-import."""
    text = (workspace.root / "HUD_config.advanced.xml").read_text(encoding="utf-8")
    for variant in make_demo_workspace.HUD_VARIANTS:
        assert f'name="{variant.profile}"' in text


def test_dynamic_panels_are_scoped_to_the_profile_that_ships_them(workspace) -> None:
    """Importing the Dynamic HUD must not turn panels on for the other two."""
    from fpdb_3_legacy.Configuration import Config, parse_hud_panel_rules

    for variant in make_demo_workspace.HUD_VARIANTS:
        config = Config(file=str(workspace.variants[variant.name]))
        rules, fallback, enabled = parse_hud_panel_rules(config.doc)
        assert enabled is True and fallback == "core"
        assert {rule.profile for rule in rules} == {"nlhe_6max_dynamic"}
        # The rules only ever name the dynamic profile, so the profiles that do
        # not match them resolve to nothing at all.
        from fpdb_3_legacy.hud_situation import HudSituationContext, HudSituationResolver

        resolver = HudSituationResolver(rules, fallback=fallback, enabled=enabled)
        context = HudSituationContext(street="flop", pot_type="single_raised", is_preflop_aggressor=True)
        if variant.profile == "nlhe_6max_dynamic":
            assert resolver.resolve(context, variant.profile).panels
        else:
            assert resolver.resolve(context, variant.profile).panels == ()


# ---------------------------------------------------------------------------
# Every view is populated, and measured rather than assumed.
# ---------------------------------------------------------------------------


def test_every_research_view_has_a_non_empty_deterministic_example(workspace) -> None:
    expected = {view for view, _question, _preset in make_demo_workspace.demo_views()}
    expected.add(make_demo_workspace.DRILL_VIEW[0])
    assert set(workspace.view_counts) == expected
    empty = {view: counts for view, counts in workspace.view_counts.items() if counts["rows"] <= 0}
    assert empty == {}, f"views with nothing to show: {empty}"
    assert all(counts["opportunities"] > 0 for counts in workspace.view_counts.values())
    # The two shapes that are not a single query are measured in their own
    # terms: a grid is worthless with 169 empty cells, and a composition with
    # nothing classified is an unclassified population wearing a table.
    grid = workspace.view_counts["range"]
    assert grid["rows"] == 169
    assert grid["cells_with_data"] > 0
    composition = workspace.view_counts["hand_strength"]
    assert composition["classified"] > 0
    assert composition["classified"] + composition["without_known_cards"] == composition["opportunities"]


def test_the_measured_examples_are_written_down_with_their_questions(workspace) -> None:
    payload = json.loads((workspace.root / make_demo_workspace.EXAMPLES_FILE).read_text(encoding="utf-8"))
    assert payload["hands"] == HANDS
    recorded = {entry["view"]: entry for entry in payload["views"]}
    assert set(recorded) == {view for view, _q, _p in make_demo_workspace.demo_views()}
    for view, question, preset in make_demo_workspace.demo_views():
        entry = recorded[view]
        assert entry["question"] == question
        # JSON has no tuples: the dimensions arrive as a list of the same names.
        assert entry["preset"]["metric"] == preset["metric"]
        assert entry["preset"]["filters"] == dict(preset.get("filters", {}))
        assert entry["preset"].get("group_by", []) == list(preset.get("group_by", ()))
        assert entry["result"]["rows"] > 0


def test_the_demo_preset_file_round_trips_through_the_real_store(workspace) -> None:
    from fpdb_3_legacy.research_browser import ResearchPresets

    stored = ResearchPresets(directory=workspace.root).load()
    assert set(stored) == set(make_demo_workspace.DEMO_PRESETS)
    # The browser validates on read, so a stored preset that came back is a
    # preset the UI can run; check the vocabulary survived the round trip.
    for name, preset in make_demo_workspace.DEMO_PRESETS.items():
        assert stored[name]["metric"] == preset["metric"]
        assert stored[name]["filters"] == dict(preset.get("filters", {}))
    assert workspace.presets is not None and workspace.presets.parent == workspace.root


# ---------------------------------------------------------------------------
# The corpus covers what the views advertise.
# ---------------------------------------------------------------------------


def test_the_corpus_produces_every_behaviour_the_views_need(demo_db) -> None:
    labels = _labels(demo_db)
    missing = {
        label: (labels[label], floor)
        for label, floor in MINIMUM_COVERAGE.items()
        if labels[label] < floor
    }
    assert missing == {}, f"label: (produced, floor) -- {missing}"


def test_the_corpus_reaches_the_turn_and_the_river(demo_db) -> None:
    streets = dict(demo_db.execute("SELECT street, COUNT(*) FROM HandsSituations GROUP BY street"))
    short = {street: (streets.get(street, 0), floor) for street, floor in MINIMUM_STREET_COVERAGE.items() if streets.get(street, 0) < floor}
    assert short == {}, f"street: (situations, floor) -- {short}"


def test_the_corpus_plays_more_than_one_board_texture(demo_db) -> None:
    (suit, rank, pairing, connectivity) = demo_db.execute(
        "SELECT COUNT(DISTINCT suitStructure), COUNT(DISTINCT rankBucket), "
        "COUNT(DISTINCT pairing), COUNT(DISTINCT connectivity) "
        "FROM BoardFeatures WHERE street = 1",
    ).fetchone()
    produced = {
        "suit_structure": suit,
        "rank_bucket": rank,
        "pairing": pairing,
        "connectivity": connectivity,
    }
    short = {name: (produced[name], floor) for name, floor in MINIMUM_FLOPS.items() if produced[name] < floor}
    assert short == {}, f"texture: (distinct values, floor) -- {short}"


def test_bets_come_in_more_than_one_size(demo_db) -> None:
    """The sizing view buckets bets; one size would fill one bucket."""
    bands = demo_db.execute(
        "SELECT COUNT(DISTINCT facingSizingBp / 500) FROM HandsSituations WHERE facingSizingBp > 0",
    ).fetchone()[0]
    assert bands >= 12, f"only {bands} half-pot bands appear among the sizes faced"


def test_the_hero_holds_known_cards_in_every_hand(workspace, demo_db) -> None:
    """Range and hand-strength views need cards that exist, not placeholders."""
    known = demo_db.execute(
        "SELECT COUNT(*) FROM HandsPlayers hp JOIN Players p ON p.id = hp.playerId "
        "WHERE p.name = ? AND hp.card1 > 0 AND hp.card2 > 0",
        (make_demo_db.HERO,),
    ).fetchone()[0]
    assert known == HANDS


# The position codes the rows store (``analytics_query.POSITION_CODES``) in the
# words the Research screen shows. Six-max has no separate lojack, so code 3 is
# the seat an under-the-gun range belongs to here.
SEAT_NAMES = {"-2": "BB", "-1": "SB", "0": "BTN", "1": "CO", "2": "HJ", "3": "UTG"}


def test_position_changes_how_wide_the_same_roster_opens(workspace) -> None:
    """The positional view is only meaningful if the seats differ.

    Read back through the research engine, with the same metrics the view uses,
    so this is a statement about the demo data as the UI will see it rather than
    about the generator's intent.
    """
    from fpdb_3_legacy import research_browser as rb
    from fpdb_3_legacy.Configuration import Config
    from fpdb_3_legacy.Database import Database

    config = Config(file=str(workspace.config))
    database = Database(config)
    try:
        result = rb.execute_preset(
            database,
            {
                "metric": "raise_frequency",
                "filters": {"pot_type": "unopened"},
                "group_by": ("position",),
            },
        )
    finally:
        database.disconnect()

    by_position = {SEAT_NAMES[str(row["position"])]: row for row in result.rows}
    assert {"BTN", "UTG"} <= set(by_position), sorted(by_position)
    # ``frequency_bp`` is the rate; ``value`` is the numerator, which is a count
    # of raises and would only measure how many hands each seat played.
    assert by_position["BTN"]["frequency_bp"] > by_position["UTG"]["frequency_bp"], {
        seat: row["frequency_bp"] for seat, row in by_position.items()
    }


def test_a_seats_name_comes_from_where_it_sits() -> None:
    """The position table is read from the button, and it has to say so.

    ``_position`` indexes it by a seat's distance from the button, so index 0 is
    the button itself. Read the other way round every seat is named one place
    off: the button is called the small blind, the small blind the big blind,
    and every positional statistic in the demo describes the player to the left
    of the one it claims.
    """
    import random

    seats = [make_demo_db.Player(make_demo_db.HERO_STYLE, index + 1) for index in range(6)]
    button_first = make_demo_db.HandWriter(random.Random(11), seats, button=0, table="T")
    assert [
        button_first._position(player) for player in seats
    ] == ["BTN", "SB", "BB", "UTG", "HJ", "CO"]
    # The order still follows the button when it moves: the seat three along
    # from it acts first preflop, which is what makes it UTG.
    moved = make_demo_db.HandWriter(random.Random(11), seats, button=3, table="T")
    assert [moved._position(player) for player in seats] == ["UTG", "HJ", "CO", "BTN", "SB", "BB"]


def test_the_open_raise_is_drawn_from_the_pfr_not_the_vpip() -> None:
    """Raising and entering the pot are two tendencies, not one.

    A 58/4 calling station that opened at its VPIP rate was a 40% opener once
    the position factor was applied, so the demo's positional PFR numbers
    described a player nobody had invented -- and a station is exactly the
    profile a HUD screenshot is supposed to show next to a maniac.
    """
    import random

    station = next(style for style in make_demo_db.ROSTER if style.name == "CallingStation")
    assert station.vpip == 0.58 and station.pfr == 0.04
    player = make_demo_db.Player(station, 1)
    writer = make_demo_db.HandWriter(random.Random(11), [player], button=0, table="T")
    # On the button, where the position factor widens the range most.
    raise_rate = station.pfr * make_demo_db.OPEN_FACTOR["BTN"]
    enter_rate = station.vpip * make_demo_db.OPEN_FACTOR["BTN"]

    action, target = writer._decide_open(player, make_demo_db.BIG_BLIND, roll=raise_rate / 2)
    assert action == "raise" and target >= make_demo_db.BIG_BLIND * 2
    # Between the two rates it enters the pot quietly rather than raising.
    action, _ = writer._decide_open(player, make_demo_db.BIG_BLIND, roll=raise_rate + 0.01)
    assert action == "call"
    # Above the VPIP rate it is the fold the profile is famous for.
    action, _ = writer._decide_open(player, make_demo_db.BIG_BLIND, roll=enter_rate + 0.01)
    assert action == "fold"


def test_player_identities_are_obviously_invented() -> None:
    """Nothing generated here can be mistaken for a real screen name."""
    names = [make_demo_db.HERO, *(style.name for style in make_demo_db.ROSTER)]
    assert len(set(names)) == len(names)
    assert all(len(name) > 3 and name.isalpha() for name in names)
    assert not any(name.lower() in {"hero", "player"} for name in names[1:])


# ---------------------------------------------------------------------------
# Reproducibility and safety.
# ---------------------------------------------------------------------------


def test_the_same_seed_produces_the_same_hands(tmp_path) -> None:
    """Screenshots and statistics have to be regenerable, not just similar."""
    first = make_demo_db.generate(tmp_path / "first", 60, 4242)
    second = make_demo_db.generate(tmp_path / "second", 60, 4242)
    other = make_demo_db.generate(tmp_path / "other", 60, 4243)

    names = sorted(path.name for path in first.glob("*.txt"))
    assert names and names == sorted(path.name for path in second.glob("*.txt"))
    for name in names:
        assert (first / name).read_bytes() == (second / name).read_bytes()
    # A different seed has to actually deal different hands, or "deterministic"
    # would be satisfied by a generator that ignores its seed.
    assert any(
        (first / name).read_bytes() != (other / name).read_bytes()
        for name in names
        if (other / name).exists()
    )


def test_the_workspace_never_writes_outside_its_own_directory(tmp_path, monkeypatch) -> None:
    """The user's configuration directory must come out of this untouched.

    The generators are pointed at a fake home for the duration, so an accidental
    ``Path.home()`` or default-config-directory write lands where the test can
    see it instead of in the person's real setup.
    """
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr("fpdb_3_legacy.Configuration.CONFIG_PATH", str(fake_home / ".fpdb"))

    root = tmp_path / "workspace"
    report = make_demo_workspace.build_workspace(root, hands=60, import_hands=False)

    assert report.variants and report.readme and report.presets
    for path in (report.readme, report.presets, *report.variants.values()):
        assert path.is_file() and root in path.parents
    # Constructing a ``Config`` is what creates the config directory itself --
    # a pre-existing behaviour of the application, not of this tool. What must
    # not happen is any *content* appearing there: no configuration, no saved
    # preset, no database.
    written = sorted(path for path in fake_home.rglob("*") if path.is_file())
    assert written == [], f"the demo wrote into the user's own config directory: {written}"


def test_a_generate_only_build_skips_the_database_and_the_measurements(tmp_path) -> None:
    report = make_demo_workspace.build_workspace(tmp_path / "hands-only", hands=60, import_hands=False)
    assert (report.root / "hands").is_dir()
    assert not (report.root / "demo.db3").exists()
    assert report.view_counts == {}
    assert report.examples is None
    assert report.stale_before_rebuild == ()
    # The configuration work still happens: the HUD stage is independent of the
    # database, and a contributor regenerating screenshots needs both.
    assert report.profiles_are_selected
