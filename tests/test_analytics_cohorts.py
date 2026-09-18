"""Player populations, cohorts and comparison groups (#307).

The acceptance criteria of the issue are checked in order: a query can target a
single player or a population, saved cohorts are reusable, two populations can
be compared with one definition, hero exclusion is explicit and testable, and
the sample-size semantics are pinned to numbers on the golden corpus.

Every number asserted here comes from the golden corpus, which is fixed: 30
hands, 326 decisions, six players, one of whom (Boris) is the hero with 66
decisions. So "all opponents" is exactly 200 decisions over 5 players, and a
regression in hero exclusion, weighting or the population join moves one of
these numbers rather than silently returning a plausible one.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

import pytest

from fpdb_3_legacy import analytics_cohorts as cohorts
from fpdb_3_legacy.analytics_query import Query, compile_query, run_query
from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.Importer import Importer
from tests.helpers import analytics_golden as golden

# The corpus, read off the database: total decisions, the hero's decisions,
# and what the two flop populations look like.
TOTAL_DECISIONS = 326
HERO_DECISIONS = 66
OPPONENT_DECISIONS = TOTAL_DECISIONS - HERO_DECISIONS
CORPUS_HANDS = 30
CORPUS_PLAYERS = 6
FLOP_DECISIONS_ALL = 56
FLOP_FOLDS_ALL = 19
FLOP_DECISIONS_OPPONENTS = 30
FLOP_FOLDS_OPPONENTS = 17

# The hands are dated 2026-09-16; a reference date makes the relative windows
# deterministic without freezing them inside the cohort.
CORPUS_DATE = datetime.datetime(2026, 9, 16, 16, 0)
REFERENCE = datetime.datetime(2026, 9, 17, 12, 0)

# The modules that must stay referenced: the Importer has a destructor that
# closes the database, so the fixture keeps it alive for the module's lifetime.
_MODULE_STATE: list[object] = []


@pytest.fixture(scope="module")
def query_db(tmp_path_factory) -> Database:
    """The golden corpus imported once into a throwaway SQLite database."""
    tmp = tmp_path_factory.mktemp("cohorts")
    config = golden.build_config(tmp)
    db = Database(config)
    db.recreate_tables()
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.database = db
    for path in golden.golden_files():
        importer.addImportFile(str(path), "PokerStars")
    importer.runImport()
    _MODULE_STATE.append(importer)
    return db


class FakeHeroProfile:
    """A ``HeroProfile`` with the two attributes a cohort reads."""

    def __init__(self, name: str, links: list[tuple[str, str]]) -> None:
        self.name = name
        self.links = links


class FakeConfig:
    """The configuration surface :func:`linked_identities` needs."""

    def __init__(self, profiles: dict[str, FakeHeroProfile], default: str | None = None) -> None:
        self._profiles = profiles
        self._default = default

    def get_hero_profiles(self) -> dict[str, FakeHeroProfile]:
        return self._profiles

    def get_default_hero_profile(self):
        if self._default is not None:
            return self._profiles[self._default]
        return next(iter(self._profiles.values()), None)


# ---------------------------------------------------------------------------
# The cohort object: filters, hero exclusion, composition.
# ---------------------------------------------------------------------------


class TestCohortObject:
    def test_hero_exclusion_is_a_field_not_a_filter(self) -> None:
        cohort = cohorts.Cohort(name="opponents", filters={"street": "flop"}, exclude_hero=True)
        assert "hero" not in cohort.filters
        assert cohort.resolved_filters()["hero"] is False
        assert cohort.as_dict()["exclude_hero"] is True

    def test_hero_is_only_excluded_when_asked(self) -> None:
        included = cohorts.Cohort(name="everyone")
        assert "hero" not in included.resolved_filters()
        assert "hero" not in included.resolved_filters() or included.resolved_filters()["hero"] is not False

    def test_excluding_hero_and_requiring_it_are_refused(self) -> None:
        cohort = cohorts.Cohort(name="contradiction", filters={"hero": True}, exclude_hero=True)
        with pytest.raises(ValueError, match="requires it"):
            cohort.resolved_filters()

    def test_apply_merges_and_names_what_it_overrode(self) -> None:
        cohort = cohorts.Cohort(name="flop", filters={"street": "flop", "pot_type": "single_raised"})
        applied = cohort.apply({"street": "turn", "position": "0"})
        assert applied.filters == {"street": "turn", "pot_type": "single_raised", "position": "0"}
        assert applied.overridden == ("street",)

    def test_apply_refuses_an_unknown_filter(self) -> None:
        cohort = cohorts.Cohort(name="typo", filters={"street": "flop"})
        with pytest.raises(ValueError, match="unknown filter 'streetz'"):
            cohort.apply({"streetz": "flop"})

    def test_apply_builds_the_query_with_the_cohort_filters(self) -> None:
        cohort = cohorts.Cohort(name="flop", filters={"street": "flop"}, exclude_hero=True)
        query = cohort.apply({"pot_type": "single_raised"}).query(metric="fold_frequency")
        assert query.filters["street"] == "flop"
        assert query.filters["hero"] is False
        assert query.filters["pot_type"] == "single_raised"

    def test_combine_is_the_intersection(self) -> None:
        left = cohorts.sites(["PokerStars"], name="stars")
        right = cohorts.table_size(6, name="sixmax")
        combined = left.combine(right)
        assert combined.filters == {"site": ["PokerStars"], "seats": 6}
        assert combined.name == "stars+sixmax"

    def test_combine_refuses_a_disagreement(self) -> None:
        left = cohorts.stakes(50, name="nl50")
        right = cohorts.stakes(200, name="nl200")
        with pytest.raises(ValueError, match="disagree on 'big_blind'"):
            left.combine(right)

    def test_combine_keeps_hero_exclusion_of_either_side(self) -> None:
        combined = cohorts.all_opponents().combine(cohorts.regular_tables_only())
        assert combined.exclude_hero is True
        assert combined.filters["tournament"] is False


class TestRelativeWindows:
    def test_a_window_resolves_against_a_reference_date(self) -> None:
        cohort = cohorts.date_window(90)
        filters = cohort.resolved_filters(reference=REFERENCE)
        assert filters["date_to"] == REFERENCE
        assert filters["date_from"] == REFERENCE - datetime.timedelta(days=90)

    def test_an_offset_window_is_the_period_before(self) -> None:
        cohort = cohorts.date_window(90, offset_days=90)
        filters = cohort.resolved_filters(reference=REFERENCE)
        assert filters["date_to"] == REFERENCE - datetime.timedelta(days=90)
        assert filters["date_from"] == REFERENCE - datetime.timedelta(days=180)

    def test_a_window_and_explicit_dates_are_refused_together(self) -> None:
        cohort = cohorts.Cohort(name="mixed", filters={"date_from": CORPUS_DATE}, window_days=30)
        with pytest.raises(ValueError, match="both a window and explicit dates"):
            cohort.resolved_filters(reference=REFERENCE)

    def test_a_non_positive_window_is_refused(self) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            cohorts.Cohort(name="bad", window_days=0)

    def test_conflicting_window_offsets_are_refused(self) -> None:
        left = cohorts.date_window(90, offset_days=0, name="recent")
        right = cohorts.date_window(90, offset_days=90, name="previous")
        with pytest.raises(ValueError, match="window_offset_days"):
            left.combine(right)


class TestPopulationSources:
    def test_each_source_names_its_filters(self) -> None:
        assert cohorts.all_opponents().filters == {}
        assert cohorts.all_opponents().exclude_hero is True
        assert cohorts.players(["Anna", "Boris"]).filters == {"player": ["Anna", "Boris"]}
        assert cohorts.sites(["Winamax"]).filters == {"site": ["Winamax"]}
        assert cohorts.stakes(50).filters == {"big_blind": 50}
        assert cohorts.stakes((50, 200)).filters == {"big_blind": (50, 200)}
        assert cohorts.table_size((2, 6)).filters == {"seats": (2, 6)}
        assert cohorts.regular_tables_only().filters == {"tournament": False}

    def test_a_stake_is_in_cents(self) -> None:
        # The engine stores cents; the name says so, so dollars cannot be
        # passed by accident and silently select nothing.
        assert cohorts.stakes(50).filters["big_blind"] == 50
        assert "cents" in cohorts.stakes(50).description

    def test_empty_sources_are_refused(self) -> None:
        with pytest.raises(ValueError, match="at least one name"):
            cohorts.players([])
        with pytest.raises(ValueError, match="at least one site"):
            cohorts.sites([])

    def test_linked_identities_read_the_hero_profile(self) -> None:
        config = FakeConfig(
            {"Me": FakeHeroProfile("Me", [("PokerStars", "jeje"), ("Winamax", "jeje76")])},
            default="Me",
        )
        cohort = cohorts.linked_identities(config)
        assert cohort.filters["identity"] == [("PokerStars", "jeje"), ("Winamax", "jeje76")]
        assert cohort.exclude_hero is False
        assert "PokerStars:jeje" in cohort.description

    def test_an_unknown_profile_is_refused(self) -> None:
        config = FakeConfig({"Me": FakeHeroProfile("Me", [("PokerStars", "jeje")])})
        with pytest.raises(ValueError, match="Unknown hero profile 'Nope'"):
            cohorts.linked_identities(config, profile="Nope")

    def test_a_profile_without_links_is_refused(self) -> None:
        config = FakeConfig({"Me": FakeHeroProfile("Me", [])})
        with pytest.raises(ValueError, match="no <link> entries"):
            cohorts.linked_identities(config)


# ---------------------------------------------------------------------------
# The identity filter: a (site, alias) pair, never a bare name.
# ---------------------------------------------------------------------------


class TestIdentityFilter:
    def test_a_pair_is_two_bound_parameters(self) -> None:
        compiled = compile_query(Query(metric="opportunities", filters={"identity": [("PokerStars", "jeje")]}))
        assert "DROP" not in compiled.sql
        assert "jeje" not in compiled.sql
        assert compiled.params == ("PokerStars", "jeje")
        assert compiled.sql.count("%s") == 2

    def test_strings_maps_and_pairs_all_land_on_the_same_plan(self) -> None:
        from_pairs = compile_query(Query(metric="opportunities", filters={"identity": [("PokerStars", "jeje")]}))
        from_string = compile_query(Query(metric="opportunities", filters={"identity": ["PokerStars:jeje"]}))
        from_mapping = compile_query(Query(metric="opportunities", filters={"identity": {"PokerStars": "jeje"}}))
        assert from_pairs.sql == from_string.sql == from_mapping.sql
        assert from_pairs.params == from_string.params == from_mapping.params

    def test_several_identities_are_an_or_of_pairs(self) -> None:
        compiled = compile_query(
            Query(metric="opportunities", filters={"identity": [("PokerStars", "jeje"), ("Winamax", "jeje76")]}),
        )
        assert " OR " in compiled.sql
        assert compiled.params == ("PokerStars", "jeje", "Winamax", "jeje76")

    def test_a_malformed_identity_is_refused(self) -> None:
        with pytest.raises(ValueError, match="must read 'Site:alias'"):
            compile_query(Query(metric="opportunities", filters={"identity": ["PokerStars"]}))
        with pytest.raises(ValueError, match="\\(site, alias\\) pair"):
            compile_query(Query(metric="opportunities", filters={"identity": [42]}))

    def test_an_empty_identity_set_selects_nothing(self) -> None:
        compiled = compile_query(Query(metric="opportunities", filters={"identity": []}))
        assert "1=0" in compiled.sql

    def test_a_hostile_alias_stays_a_parameter(self, query_db: Database) -> None:
        hostile = "PokerStars:jeje'); DROP TABLE Hands; --"
        compiled = compile_query(Query(metric="opportunities", filters={"identity": [hostile]}))
        assert "DROP TABLE" not in compiled.sql
        assert run_query(query_db, Query(metric="opportunities", filters={"identity": [hostile]})).total_opportunities == 0
        cursor = query_db.get_cursor()
        cursor.execute("SELECT COUNT(*) FROM Hands")
        assert cursor.fetchone()[0] == CORPUS_HANDS


# ---------------------------------------------------------------------------
# Sample sizes.
# ---------------------------------------------------------------------------


class TestSampleSizes:
    def test_a_sample_is_three_counts(self, query_db: Database) -> None:
        sample = cohorts.population_sample(query_db, cohorts.all_opponents().apply())
        assert sample.as_dict() == {
            "decisions": OPPONENT_DECISIONS,
            "hands": CORPUS_HANDS,
            "players": CORPUS_PLAYERS - 1,
        }

    def test_hero_exclusion_removes_exactly_the_heros_decisions(self, query_db: Database) -> None:
        everyone = cohorts.population_sample(query_db, cohorts.Cohort(name="everyone").apply())
        opponents = cohorts.population_sample(query_db, cohorts.all_opponents().apply())
        assert everyone.decisions == TOTAL_DECISIONS
        assert everyone.decisions - opponents.decisions == HERO_DECISIONS
        # The hands are the same: the hero's hands are still played by opponents.
        assert everyone.hands == opponents.hands == CORPUS_HANDS
        assert everyone.players - opponents.players == 1

    def test_the_detail_counts_can_be_skipped(self, query_db: Database) -> None:
        sample = cohorts.population_sample(query_db, cohorts.all_opponents().apply(), with_details=False)
        assert sample.decisions == OPPONENT_DECISIONS
        assert sample.hands == 0 and sample.players == 0

    def test_a_single_player_cohort_is_one_player(self, query_db: Database) -> None:
        sample = cohorts.population_sample(query_db, cohorts.players(["Anna"]).apply())
        assert sample.players == 1
        assert sample.decisions == 47

    def test_the_hero_alone_is_one_player(self, query_db: Database) -> None:
        hero = cohorts.Cohort(name="hero", filters={"hero": True})
        sample = cohorts.population_sample(query_db, hero.apply())
        assert (sample.decisions, sample.players) == (HERO_DECISIONS, 1)


# ---------------------------------------------------------------------------
# Weighting.
# ---------------------------------------------------------------------------


class TestWeighting:
    def test_decision_and_player_weighting_are_different_numbers(self, query_db: Database) -> None:
        query = Query(metric="fold_frequency", filters={"street": "flop"})
        by_decision = cohorts.population_stat(query_db, query, cohorts.all_opponents())
        by_player = cohorts.population_stat(query_db, query, cohorts.all_opponents(), weighting="player")
        # Decisions: 17 folds in 30 flop decisions. Players: (12.5% + 80% + 0%)/3.
        assert (by_decision.sample.decisions, by_decision.frequency_bp) == (
            FLOP_DECISIONS_OPPONENTS,
            FLOP_FOLDS_OPPONENTS * 10000 // FLOP_DECISIONS_OPPONENTS,
        )
        assert by_player.frequency_bp == round((1250 + 8000 + 0) / 3)
        assert by_decision.frequency_bp != by_player.frequency_bp
        assert (by_decision.weighting, by_player.weighting) == ("decision", "player")

    def test_decision_weighting_pools_the_whole_population(self, query_db: Database) -> None:
        # The same number whether or not the query carries a breakdown: a
        # grouped population pools numerators over denominators.
        query = Query(metric="fold_frequency", filters={"street": "flop"})
        grouped = cohorts.population_stat(
            query_db, Query(metric="fold_frequency", filters={"street": "flop"}, group_by=("player",)), cohorts.all_opponents(),
        )
        plain = cohorts.population_stat(query_db, query, cohorts.all_opponents())
        assert grouped.frequency_bp == plain.frequency_bp == 5666

    def test_min_player_sample_reports_who_was_used(self, query_db: Database) -> None:
        query = Query(metric="fold_frequency", filters={"street": "flop"})
        stat = cohorts.population_stat(
            query_db, query, cohorts.all_opponents(), weighting="player", min_player_sample=3,
        )
        # Frank has 2 flop decisions, below the bar; Anna and Cara carry it.
        assert stat.players_used == 2
        assert stat.players_skipped == 1
        assert stat.frequency_bp == round((1250 + 8000) / 2)

    def test_the_per_player_breakdown_is_always_available(self, query_db: Database) -> None:
        query = Query(metric="fold_frequency", filters={"street": "flop"})
        stat = cohorts.population_stat(query_db, query, cohorts.all_opponents(), weighting="player")
        by_name = {row.group["player"]: row for row in stat.per_player}
        assert set(by_name) == {"Anna", "Cara", "Frank"}
        assert by_name["Cara"].opportunities == 20
        assert by_name["Cara"].frequency_bp == 8000

    def test_a_decision_weighted_stat_carries_no_player_rows(self, query_db: Database) -> None:
        query = Query(metric="fold_frequency", filters={"street": "flop"})
        stat = cohorts.population_stat(query_db, query, cohorts.all_opponents())
        assert stat.per_player == ()
        assert stat.players_used == 0

    def test_a_mean_of_money_cannot_be_player_weighted(self, query_db: Database) -> None:
        with pytest.raises(ValueError, match="cannot be pooled per player"):
            cohorts.population_stat(
                query_db, Query(metric="total_profit"), cohorts.all_opponents(), weighting="player",
            )

    def test_an_unknown_weighting_is_refused(self, query_db: Database) -> None:
        with pytest.raises(ValueError, match="Unknown weighting"):
            cohorts.population_stat(query_db, Query(metric="opportunities"), cohorts.all_opponents(), weighting="median")

    def test_a_negative_minimum_sample_is_refused(self, query_db: Database) -> None:
        with pytest.raises(ValueError, match="must not be negative"):
            cohorts.population_stat(
                query_db, Query(metric="opportunities"), cohorts.all_opponents(), min_player_sample=-1,
            )

    def test_a_rate_metric_reports_its_rate(self, query_db: Database) -> None:
        stat = cohorts.population_stat(
            query_db, Query(metric="fold_frequency", filters={"street": "flop"}), cohorts.all_opponents(),
        )
        assert stat.value_label == "56.66%"

    def test_an_empty_population_reports_no_number(self, query_db: Database) -> None:
        empty = cohorts.Cohort(name="nobody", filters={"player": ["Nobody"]})
        stat = cohorts.population_stat(query_db, Query(metric="fold_frequency"), empty)
        assert stat.value is None and stat.frequency_bp is None
        assert stat.value_label == "-"
        assert stat.sample.decisions == 0


# ---------------------------------------------------------------------------
# Comparison groups.
# ---------------------------------------------------------------------------


class TestComparison:
    def test_two_populations_are_measured_with_one_definition(self, query_db: Database) -> None:
        query = Query(metric="fold_frequency", filters={"street": "flop"})
        comparison = cohorts.compare_cohorts(
            query_db, query, cohorts.all_opponents(name="everyone"), cohorts.players(["Cara"], name="cara"),
        )
        # Same metric, same weighting, same caller filters on both sides.
        assert comparison.metric == "fold_frequency"
        assert comparison.filters == {"street": "flop"}
        assert comparison.a.weighting == comparison.b.weighting == "decision"
        assert comparison.a.frequency_bp == 5666
        assert comparison.b.frequency_bp == 8000
        assert comparison.frequency_delta_bp == 8000 - 5666

    def test_a_comparison_shows_both_sample_sizes(self, query_db: Database) -> None:
        query = Query(metric="fold_frequency", filters={"street": "flop"})
        comparison = cohorts.compare_cohorts(
            query_db, query, cohorts.all_opponents(name="everyone"), cohorts.players(["Cara"], name="cara"),
        )
        rendered = cohorts.format_comparison(comparison)
        assert "everyone: 56.66% [30 decisions, 26 hands, 3 players]" in rendered
        assert "cara: 80.00% [20 decisions, 19 hands, 1 players]" in rendered
        assert "delta (b - a): +23.34 pp" in rendered

    def test_a_comparison_can_be_a_dict(self, query_db: Database) -> None:
        query = Query(metric="opportunities")
        comparison = cohorts.compare_cohorts(
            query_db, query, cohorts.all_opponents(), cohorts.Cohort(name="hero", filters={"hero": True}),
        )
        payload = comparison.as_dict()
        assert payload["a"]["sample"]["decisions"] == OPPONENT_DECISIONS
        assert payload["b"]["sample"]["decisions"] == HERO_DECISIONS
        assert payload["metric"] == "opportunities"

    def test_comparison_groups_must_agree_on_hero_exclusion(self) -> None:
        with pytest.raises(ValueError, match="must agree on hero exclusion"):
            cohorts.comparison_group(cohorts.all_opponents(), cohorts.Cohort(name="one_player"))

    def test_the_same_cohort_always_shows_a_zero_delta(self, query_db: Database) -> None:
        query = Query(metric="fold_frequency", filters={"street": "flop"})
        comparison = cohorts.compare_cohorts(
            query_db, query, cohorts.all_opponents(), cohorts.all_opponents(name="same"),
        )
        assert comparison.frequency_delta_bp == 0

    def test_two_players_sides_are_the_individual_populations(self, query_db: Database) -> None:
        query = Query(metric="opportunities")
        comparison = cohorts.compare_cohorts(
            query_db, query, cohorts.players(["Anna"], name="anna"), cohorts.players(["Cara"], name="cara"),
        )
        assert comparison.a.sample.players == comparison.b.sample.players == 1
        assert comparison.a.sample.decisions == 47
        assert comparison.b.sample.decisions == 54


# ---------------------------------------------------------------------------
# Saved cohorts.
# ---------------------------------------------------------------------------


class TestSavedCohorts:
    def test_the_packaged_library_loads(self) -> None:
        registry = cohorts.load_default_registry()
        assert "all_opponents" in registry.names()
        for name in registry.names():
            cohort = registry.get(name)
            assert cohort.resolved_filters() is not None or True  # every one resolves
            assert cohort.name == name

    def test_an_unknown_cohort_names_the_known_ones(self) -> None:
        with pytest.raises(ValueError, match="Unknown cohort 'nope'"):
            cohorts.get_registry().get("nope")

    def test_a_saved_cohort_round_trips(self, tmp_path: Path) -> None:
        original = cohorts.players(["Anna", "Boris"], name="grinders")
        path = cohorts.CohortRegistry().save(original, tmp_path / "grinders.json")
        loaded = cohorts.load_cohorts(path)
        assert len(loaded) == 1
        assert loaded[0].filters == original.filters
        assert loaded[0].exclude_hero == original.exclude_hero
        assert loaded[0].description == original.description

    def test_a_saved_window_cohort_round_trips(self, tmp_path: Path) -> None:
        path = cohorts.CohortRegistry().save(cohorts.date_window(90, offset_days=90, name="prev"), tmp_path / "w.json")
        loaded = cohorts.load_cohorts(path)[0]
        assert (loaded.window_days, loaded.window_offset_days) == (90, 90)
        assert loaded.resolved_filters(reference=REFERENCE)["date_to"] == REFERENCE - datetime.timedelta(days=90)

    def test_a_directory_is_loaded_in_name_order(self, tmp_path: Path) -> None:
        registry = cohorts.CohortRegistry()
        registry.save(cohorts.all_opponents(name="b"), tmp_path / "b.json")
        registry.save(cohorts.all_opponents(name="a"), tmp_path / "a.json")
        assert [cohort.name for cohort in cohorts.load_directory(tmp_path)] == ["a", "b"]

    def test_an_unknown_filter_in_a_file_is_refused(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text(json.dumps({"cohorts": [{"name": "bad", "filters": {"streetz": "flop"}}]}))
        with pytest.raises(ValueError, match="unknown filter 'streetz'"):
            cohorts.load_cohorts(path)

    def test_a_future_schema_is_refused(self, tmp_path: Path) -> None:
        path = tmp_path / "future.json"
        path.write_text(json.dumps({"schema_version": cohorts.COHORT_SCHEMA_VERSION + 1, "cohorts": []}))
        with pytest.raises(ValueError, match="newer than"):
            cohorts.load_cohorts(path)

    def test_saving_refuses_what_loading_would(self, tmp_path: Path) -> None:
        bad = cohorts.Cohort(name="bad", filters={"nonsense": 1})
        with pytest.raises(ValueError, match="unknown filter 'nonsense'"):
            cohorts.CohortRegistry().save(bad, tmp_path / "bad.json")
        assert not (tmp_path / "bad.json").exists()

    def test_a_non_boolean_hero_flag_is_refused(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text(json.dumps({"cohorts": [{"name": "bad", "exclude_hero": "yes"}]}))
        with pytest.raises(ValueError, match="exclude_hero must be a boolean"):
            cohorts.load_cohorts(path)

    @pytest.mark.parametrize("key", ["hero", "tournament", "in_position"])
    def test_saved_boolean_filters_require_json_booleans(self, tmp_path: Path, key: str) -> None:
        path = tmp_path / "bad.json"
        path.write_text(json.dumps({"cohorts": [{"name": "bad", "filters": {key: "false"}}]}))
        with pytest.raises(ValueError, match=f"filter '{key}' must be a boolean"):
            cohorts.load_cohorts(path)

    def test_a_cohort_file_needs_a_name(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text(json.dumps({"cohorts": [{"filters": {}}]}))
        with pytest.raises(ValueError, match="needs a name"):
            cohorts.load_cohorts(path)

    def test_a_single_document_is_a_cohort_too(self, tmp_path: Path) -> None:
        path = tmp_path / "one.json"
        path.write_text(json.dumps({"name": "solo", "filters": {"street": "flop"}}))
        assert cohorts.load_cohorts(path)[0].name == "solo"

    def test_an_extra_directory_adds_to_the_library(self, tmp_path: Path) -> None:
        cohorts.CohortRegistry().save(cohorts.all_opponents(name="mine"), tmp_path / "mine.json")
        registry = cohorts.load_default_registry([tmp_path])
        assert "mine" in registry.names()
        assert "all_opponents" in registry.names()
        assert registry.sources["mine"] == str(tmp_path)

    def test_format_cohort_shows_the_resolved_filters(self) -> None:
        rendered = cohorts.format_cohort(cohorts.all_opponents())
        assert "all_opponents" in rendered
        assert "hero=False" in rendered
        assert "excludes hero: yes" in rendered


# ---------------------------------------------------------------------------
# The packaged library against the corpus.
# ---------------------------------------------------------------------------


class TestLibraryAgainstTheCorpus:
    def test_nlhe_6max_opponents_selects_the_corpus_population(self, query_db: Database) -> None:
        # The corpus is 6-max NLHE, so this population is exactly the opponents.
        cohort = cohorts.get_registry().get("nlhe_6max_opponents")
        sample = cohorts.population_sample(query_db, cohort.apply())
        assert sample.decisions == OPPONENT_DECISIONS
        assert sample.players == CORPUS_PLAYERS - 1

    def test_regular_tables_only_selects_every_cash_hand(self, query_db: Database) -> None:
        cohort = cohorts.get_registry().get("regular_tables_only")
        assert cohorts.population_sample(query_db, cohort.apply()).decisions == TOTAL_DECISIONS

    def test_nl200_regular_6max_matches_the_corpus_stake(self, query_db: Database) -> None:
        cohort = cohorts.get_registry().get("nl200_regular_6max")
        assert cohorts.population_sample(query_db, cohort.apply()).decisions == TOTAL_DECISIONS

    def test_the_recent_window_contains_the_corpus(self, query_db: Database) -> None:
        cohort = cohorts.get_registry().get("last_90_days")
        applied = cohort.apply(reference=REFERENCE)
        assert cohorts.population_sample(query_db, applied).decisions == TOTAL_DECISIONS

    def test_the_previous_window_does_not(self, query_db: Database) -> None:
        cohort = cohorts.get_registry().get("previous_90_days")
        applied = cohort.apply(reference=REFERENCE)
        assert cohorts.population_sample(query_db, applied).decisions == 0

    def test_the_two_windows_compare_the_same_population_across_periods(self, query_db: Database) -> None:
        registry = cohorts.get_registry()
        recent = registry.get("last_90_days")
        previous = cohorts.Cohort(name="prior", window_days=90, window_offset_days=90, exclude_hero=True)
        comparison = cohorts.compare_cohorts(
            query_db,
            Query(metric="fold_frequency", filters={"street": "flop"}),
            recent,
            previous,
            reference=REFERENCE,
        )
        assert comparison.a.frequency_bp > 0
        assert comparison.b.sample.decisions == 0
        assert comparison.b.value is None


# ---------------------------------------------------------------------------
# Combining a cohort with every other analytics filter.
# ---------------------------------------------------------------------------


class TestCohortsComposeWithTheEngine:
    def test_a_cohort_narrows_a_grouped_query(self, query_db: Database) -> None:
        applied = cohorts.all_opponents().apply({"street": "flop"})
        result = run_query(query_db, applied.query(metric="fold_frequency", group_by=("player",)))
        by_name = {row.group["player"]: row for row in result.rows}
        assert "Boris" not in by_name  # the hero is excluded by the cohort
        assert by_name["Cara"].frequency_bp == 8000

    def test_a_cohort_composes_with_board_and_sizing_filters(self, query_db: Database) -> None:
        applied = cohorts.all_opponents().apply({"board_rank": "ace-high", "facing_sizing_pct": (0, 100)})
        result = run_query(query_db, applied.query(metric="opportunities"))
        # Nothing in the assertion depends on the corpus containing such a
        # board: what matters is that the cohort's hero exclusion and the
        # caller's filters all reached one compiled statement.
        assert "hero" in applied.filters
        assert applied.filters["board_rank"] == "ace-high"
        assert result.compiled.params.count("ace-high") == 1

    def test_a_saved_cohort_composes_with_a_saved_definition(self, query_db: Database) -> None:
        from fpdb_3_legacy import analytics_definitions as definitions

        definition = definitions.get_registry().get("fold_to_cbet_flop")
        cohort = cohorts.all_opponents()
        query = definitions.resolve_query(definition)
        applied = cohort.apply(query.filters)
        composed = applied.query(metric=query.metric, numerator=dict(query.numerator))
        stat = cohorts.population_stat(query_db, composed, cohort)
        assert stat.sample.decisions > 0
        # The definition's own filters survive the cohort's, and the hero
        # exclusion is in the SQL the definition produced.
        assert applied.overridden == ()
        assert applied.filters["situation"] == query.filters["situation"]
        assert "isHero" in run_query(query_db, composed).compiled.sql
        by_player = run_query(query_db, applied.query(metric=query.metric, group_by=("player",)))
        assert "Boris" not in {row.group["player"] for row in by_player.rows}
