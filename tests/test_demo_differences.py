"""The demo corpus encodes known Hero-vs-Field deviations, on purpose (#371).

*Biggest Differences vs Field* is only worth demonstrating on a corpus where
the hero actually differs from the field -- and only worth trusting as a demo
if the differences are stated rather than stumbled on. The deviations live in
``tools.make_demo_db.HERO_DEVIATIONS``; these tests are them in executable
form, at two levels:

* the **styles** the generator is built from really do encode each declared
  deviation, which no database is needed to check;
* the **corpus** those styles produce really does surface them in the shipped
  difference report, which is what a reader following the guided tour sees.

The second is deliberately about direction and presence rather than exact
percentages: the observed frequency also moves with position, with who was
dealt in and with the cards, which is the lesson
``docs/reading-differences.md`` exists to teach.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fpdb_3_legacy.research_differences import DifferenceFilters, build_difference_report
from fpdb_3_legacy.research_studies import builtin_studies
from tools import make_demo_db

# Enough hands that every declared deviation clears its sample floor, small
# enough that the corpus builds in seconds.
HANDS = 2000
SEED = 371


@pytest.fixture(scope="module")
def demo_report(tmp_path_factory):
    """The difference report a reader meets on the demo workspace."""
    from fpdb_3_legacy.Configuration import Config
    from fpdb_3_legacy.Database import Database

    directory = tmp_path_factory.mktemp("demo-differences")
    hands = make_demo_db.generate(directory, HANDS, seed=SEED)
    config_path = make_demo_db.write_config(directory)
    make_demo_db.import_hands(config_path, hands)
    database = Database(Config(file=str(config_path)))
    return build_difference_report(
        database,
        builtin_studies(),
        DifferenceFilters(min_hero_sample=15, min_field_sample=40, max_rows=40),
    )


# -- the styles ----------------------------------------------------------------


def test_every_declared_deviation_is_really_in_the_styles() -> None:
    """Editing a style without updating the table has to fail here."""
    for deviation in make_demo_db.HERO_DEVIATIONS:
        gap = make_demo_db.hero_gap(deviation.stat)
        signed = gap if deviation.direction == "above" else -gap
        assert signed >= deviation.minimum, (
            f"{deviation.stat} is {gap:+.3f} from the field, "
            f"which is not {deviation.direction} it by {deviation.minimum}"
        )


def test_a_deviation_points_one_way_or_the_other() -> None:
    for deviation in make_demo_db.HERO_DEVIATIONS:
        assert deviation.direction in {"above", "below"}
        assert deviation.minimum > 0
        assert deviation.headline.strip()


def test_every_deviation_names_a_study_that_ships() -> None:
    """A deviation nobody can go and look at is not a demo of anything."""
    shipped = {study.id for study in builtin_studies().studies}

    for deviation in make_demo_db.HERO_DEVIATIONS:
        assert deviation.study in shipped, deviation.study


def test_the_corpus_keeps_one_spot_where_hero_and_field_agree() -> None:
    """A demo of only large gaps teaches that every row is a finding."""
    gap = abs(make_demo_db.hero_gap(make_demo_db.HERO_AGREEMENT))

    assert gap < 0.02
    assert all(
        deviation.stat != make_demo_db.HERO_AGREEMENT
        for deviation in make_demo_db.HERO_DEVIATIONS
    )


def test_the_deviations_are_spread_across_the_streets() -> None:
    """One preflop leak repeated five ways would not exercise the page."""
    stats = {deviation.stat for deviation in make_demo_db.HERO_DEVIATIONS}

    assert {"vpip", "pfr"} & stats, "no preflop deviation"
    assert {"barrel_turn", "barrel_river", "fold_to_cbet"} & stats, "no postflop deviation"


# -- the corpus ----------------------------------------------------------------


def test_the_demo_corpus_produces_a_non_empty_ranking(demo_report) -> None:
    assert demo_report.rows
    assert demo_report.panels_executed == demo_report.candidates_evaluated
    assert all(row.hero_sample > 0 and row.field_sample > 0 for row in demo_report.rows)


def test_the_hero_folds_to_an_open_more_than_the_field_does(demo_report) -> None:
    """The vpip deviation, as the page shows it."""
    row = next(
        row for row in demo_report.rows
        if "Facing an open" in row.spot and row.context == "Response: Fold"
    )

    assert row.gap_bp > 0, f"hero folds {row.hero_value_bp / 100:.1f}% vs {row.field_value_bp / 100:.1f}%"
    assert row.hero_sample >= 100


def test_the_hero_folds_to_a_flop_cbet_more_than_the_field_does(demo_report) -> None:
    """The fold_to_cbet deviation, as the page shows it."""
    row = next(
        row for row in demo_report.rows
        if "Facing flop c-bet" in row.spot and row.context == "Response: Fold"
    )

    assert row.gap_bp > 0


def test_the_ranking_is_review_priority_rather_than_the_raw_gap(demo_report) -> None:
    """A huge gap over nine hands must not outrank a real one over nine hundred."""
    assert all(
        row.score == abs(row.gap_bp) * min(row.hero_sample, row.field_sample)
        for row in demo_report.rows
    )
    assert demo_report.rows[0].score >= demo_report.rows[-1].score
    assert "not EV loss" in demo_report.heuristic_description


def test_the_demo_shows_a_near_zero_gap_as_well_as_large_ones(demo_report) -> None:
    """The counter-example has to be on screen, not only in the prose."""
    smallest = min(abs(row.gap_bp) for row in demo_report.rows)
    largest = max(abs(row.gap_bp) for row in demo_report.rows)

    assert smallest < 250, "every demo row is a large gap; nothing teaches restraint"
    assert largest > 800, "no demo row is a striking gap; nothing teaches discovery"


def test_no_demo_row_names_a_real_person(demo_report) -> None:
    """A published screenshot of this page must carry no private identity."""
    invented = {style.name for style in make_demo_db.ROSTER} | {make_demo_db.HERO}

    for row in demo_report.rows:
        for name in invented:
            assert name not in row.spot or name in invented
    assert all("@" not in row.spot for row in demo_report.rows)


# -- the guided tour -----------------------------------------------------------


GUIDE = Path(__file__).resolve().parents[1] / "docs" / "study-explorer-quick-start.md"


def test_the_guided_tour_walks_discovery_through_to_a_hand() -> None:
    text = _prose(GUIDE.name)

    for step in (
        "Study Explorer",
        "Biggest Differences vs Field",
        "Overview",
        "Sizing",
        "Board",
        "Cross-filter",
        "source hands",
        "replayer",
    ):
        assert step in text, f"the tour never reaches {step!r}"


def test_the_tour_can_be_followed_without_the_query_builder() -> None:
    text = _prose(GUIDE.name)

    assert "without ever opening" in text or "At no point did you open" in text
    assert "Custom / Advanced Research" in text


@pytest.mark.parametrize(
    "document",
    ["study-explorer-quick-start.md", "study-visualizations.md"],
)
def test_every_picture_a_guide_shows_exists(document: str) -> None:
    import re

    docs = Path(__file__).resolve().parents[1] / "docs"
    referenced = set(re.findall(r"\(images/([^)]+\.png)\)", (docs / document).read_text()))

    assert referenced, f"{document} shows no pictures"
    missing = sorted(name for name in referenced if not (docs / "images" / name).exists())
    assert missing == []


def _prose(name: str) -> str:
    """One guide as a single line, so an assertion is about words not wrapping."""
    text = (Path(__file__).resolve().parents[1] / "docs" / name).read_text()
    return " ".join(text.split())


def test_the_field_is_documented_as_observed_rather_than_optimal() -> None:
    text = _prose("reading-differences.md")

    assert "Not a solution" in text, "the guide does not say the field is not a solution"
    assert "not a theoretically correct" in text
    assert "review candidate" in text or "review priority" in text
    assert "Samples matter" in text
    for explanation in ("Composition", "Position", "Stack depth", "Board and sizing"):
        assert explanation in text, f"the guide does not offer {explanation!r} as an explanation"


def test_every_visualization_has_a_reading_guide() -> None:
    text = _prose("study-visualizations.md")

    for panel in (
        "Sizing distribution",
        "Position matrix",
        "Board texture heatmap",
        "Range grid",
        "Hand-strength distribution",
        "Profit and EV",
        "Source hands",
    ):
        assert panel in text, f"no reading guide for {panel!r}"


def test_the_readme_leads_with_the_spot_first_workflow() -> None:
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text()
    analytics = readme.index("Advanced Poker Analytics")
    spot_first = readme.index("Choose a spot")
    builder = readme.index("Custom / Advanced Research")

    assert analytics < spot_first < builder, "the query builder is pitched before the spot"
    assert "Study Explorer" in readme[analytics:builder]
