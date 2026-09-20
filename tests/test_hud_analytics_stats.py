"""The runtime value of an analytics-backed HUD cell (#335).

The HUD editor (#309) can already *declare* that a cell comes from a definition;
these tests cover the half that was missing -- resolving that declaration to a
query, running it once per ``(definition, player)``, and rendering the answer (or
an honest reason) in the cell. The corpus is the golden one (#308), so a HUD
value and a report value are the same number because they are the same query.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import defusedxml.minidom as minidom
import pytest

from fpdb_3_legacy import analytics_definitions as dsl
from fpdb_3_legacy import hud_analytics_stats as stats
from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.hud_read_service import HudPreparedHand, HudReadService
from fpdb_3_legacy.Importer import Importer
from tests.helpers import analytics_golden as golden


@pytest.fixture(scope="module")
def query_db(tmp_path_factory) -> Database:
    """The golden corpus imported once into a throwaway SQLite database."""
    tmp = tmp_path_factory.mktemp("hud_analytics")
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


_MODULE_STATE: list[object] = []


def _provider(**overrides) -> stats.AnalyticsStatProvider:
    registry = overrides.pop("registry", dsl.load_default_registry())
    return stats.AnalyticsStatProvider(registry=registry, **overrides)


def _binding(definition: str, **overrides) -> stats.AnalyticsStatBinding:
    data = {"stat_name": definition, "definition": definition}
    data.update(overrides)
    return stats.AnalyticsStatBinding(**data)


# ---------------------------------------------------------------------------
# Bindings: what a cell says about itself
# ---------------------------------------------------------------------------


class TestBindings:
    def test_a_native_cell_binds_nothing(self) -> None:
        assert stats.AnalyticsStatBinding.from_attributes({"_stat_name": "vpip"}) is None
        assert stats.AnalyticsStatBinding.from_attributes({"data_source": stats.NATIVE_SOURCE}) is None

    def test_an_analytics_cell_reads_its_binding(self) -> None:
        binding = stats.AnalyticsStatBinding.from_attributes(
            {
                "_stat_name": "my_fold",
                "data_source": "analytics",
                "data_definition": "fold_to_cbet_flop",
                "data_format": "percentage",
                "data_min_sample": "5",
            }
        )
        assert binding == stats.AnalyticsStatBinding(
            stat_name="my_fold",
            definition="fold_to_cbet_flop",
            fmt="percentage",
            min_sample=5,
        )

    def test_a_broken_binding_is_kept_as_one(self) -> None:
        """A cell that names no definition must explain itself, not become native."""
        binding = stats.AnalyticsStatBinding.from_attributes(
            {"_stat_name": "mystery", "data_source": "analytics"}
        )
        assert binding is not None
        assert binding.definition == "mystery"

    def test_an_unknown_format_falls_back_to_the_definition(self) -> None:
        binding = stats.AnalyticsStatBinding.from_attributes(
            {
                "data_source": "analytics",
                "data_definition": "fold_to_cbet_flop",
                "data_format": "not_a_format",
                "data_min_sample": "-4",
            }
        )
        assert binding is not None
        assert binding.fmt == ""
        assert binding.min_sample is None

    def test_from_stat_reads_a_configuration_stat(self) -> None:
        stat = MagicMock(
            data_source="analytics",
            data_definition="fold_to_cbet_flop",
            data_format="percentage",
            data_min_sample=0,
            stat_name="fold_cbet",
        )
        binding = stats.AnalyticsStatBinding.from_stat(stat)
        assert binding is not None
        assert binding.stat_name == "fold_cbet"
        assert binding.min_sample == 0

    def test_bindings_from_config_walks_the_stat_nodes(self) -> None:
        document = minidom.parseString(
            """
            <stat_set>
              <stat _stat_name="vpip" data_source="registry"/>
              <stat _stat_name="fold_cbet" data_source="analytics"
                    data_definition="fold_to_cbet_flop" data_format="percentage"
                    data_min_sample="10"/>
              <stat _stat_name="fold_cbet" data_source="analytics"
                    data_definition="fold_to_cbet_flop" data_format="percentage"
                    data_min_sample="10"/>
            </stat_set>
            """
        )
        config = MagicMock()
        config.doc = document
        bindings = stats.bindings_from_config(config)
        assert [binding.stat_name for binding in bindings] == ["fold_cbet"]
        assert bindings[0].min_sample == 10

    def test_a_config_without_a_document_binds_nothing(self) -> None:
        config = MagicMock(doc=None)
        assert stats.bindings_from_config(config) == ()

    def test_a_stat_set_scopes_the_bindings_to_that_profile(self) -> None:
        """A binding in another profile must not be inherited by this one."""
        document = minidom.parseString(
            """
            <stat_sets>
              <ss name="holdem_ring">
                <stat _stat_name="fold_cbet" data_source="analytics"
                      data_definition="fold_to_cbet_flop"/>
              </ss>
              <ss name="holdem_tour">
                <stat _stat_name="fold_cbet" data_source="registry"/>
              </ss>
            </stat_sets>
            """
        )
        config = MagicMock()
        config.doc = document
        assert [b.stat_name for b in stats.bindings_from_config(config, stat_set="holdem_ring")] == ["fold_cbet"]
        assert stats.bindings_from_config(config, stat_set="holdem_tour") == ()
        # Unscoped, the whole document is walked, as before.
        assert [b.stat_name for b in stats.bindings_from_config(config)] == ["fold_cbet"]

    def test_an_unknown_stat_set_binds_nothing_rather_than_everything(self) -> None:
        document = minidom.parseString(
            '<stat_sets><ss name="a"><stat _stat_name="x" data_source="analytics" data_definition="y"/></ss></stat_sets>'
        )
        config = MagicMock()
        config.doc = document
        assert stats.bindings_from_config(config, stat_set="no_such_profile") == ()


# ---------------------------------------------------------------------------
# Scope: who the cell is about
# ---------------------------------------------------------------------------


class TestScope:
    def test_reads_the_screen_name_of_a_row(self) -> None:
        scope = stats.scope_for_entry({"screen_name": "Cara", "vpip_opp": 3}, site="PokerStars", player_id=7)
        assert scope.alias == "Cara"
        assert scope.site == "PokerStars"
        assert scope.player_id == 7
        assert scope.is_resolved()

    def test_accepts_the_other_alias_spellings(self) -> None:
        assert stats.scope_for_entry({"name": "Bob"}).alias == "Bob"
        assert stats.scope_for_entry({"playerName": "Ann"}).alias == "Ann"

    def test_a_row_without_a_name_is_unresolved(self) -> None:
        scope = stats.scope_for_entry({"vpip": 1})
        assert not scope.is_resolved()
        assert scope.filters() == {}

    def test_identity_is_a_site_and_a_name(self) -> None:
        assert stats.PlayerScope(alias="Cara", site="PokerStars").filters() == {
            "identity": {"PokerStars": "Cara"}
        }
        assert stats.PlayerScope(alias="Cara").filters() == {"player": ["Cara"]}

    def test_scopes_cover_every_seat(self) -> None:
        scopes = stats.scopes_for_stat_dict({1: {"screen_name": "Cara"}, 2: {"vpip": 4}}, site="PokerStars")
        assert set(scopes) == {1, 2}
        assert scopes[2].is_resolved() is False

    def test_a_non_mapping_row_becomes_an_unresolved_scope(self) -> None:
        scopes = stats.scopes_for_stat_dict({3: "garbage"})
        assert scopes[3].is_resolved() is False


# ---------------------------------------------------------------------------
# Capability: what a cell can and cannot show
# ---------------------------------------------------------------------------


class TestCapability:
    def test_a_plain_definition_is_capable(self) -> None:
        assert _provider().capability(_binding("fold_to_cbet_flop")) == ""

    def test_an_unknown_definition_names_what_is_installed(self) -> None:
        reason = _provider().capability(_binding("no_such_stat"))
        assert "no definition named" in reason
        assert "fold_to_cbet_flop" in reason

    def test_a_binding_with_no_definition_is_explained(self) -> None:
        reason = _provider().capability(stats.AnalyticsStatBinding(stat_name="x", definition=""))
        assert "names no definition" in reason

    def test_a_grouped_definition_cannot_fill_one_cell(self) -> None:
        reason = _provider().capability(_binding("fold_to_cbet_flop_by_size"))
        assert "grouped by" in reason

    def test_a_definition_naming_the_street_is_still_capable(self) -> None:
        """A flop stat is not unsupported because it names the flop.

        The street lives in the definition's fragments/filters, which the engine
        evaluates per stored decision. Only *injecting* a street into a refresh
        would be a lie -- see :class:`TestContext`.
        """
        definition = dsl.load_default_registry().resolve("fold_to_cbet_flop")
        assert "flop" in definition.fragments
        assert _provider().capability(_binding("fold_to_cbet_flop")) == ""


# ---------------------------------------------------------------------------
# Context: what a refresh may and may not claim
# ---------------------------------------------------------------------------


class TestContext:
    def test_an_injectable_context_is_accepted(self) -> None:
        assert stats.AnalyticsStatProvider._check_context({"site": "PokerStars", "seats": 6}) == ""

    def test_a_live_only_fact_is_refused(self) -> None:
        reason = stats.AnalyticsStatProvider._check_context({"street": "flop"})
        assert "street" in reason

    def test_the_refusal_is_on_injection_not_on_the_definition(self) -> None:
        assert set(stats.NOT_INJECTABLE_CONTEXT) & set(stats.INJECTABLE_CONTEXT) == set()

    def test_a_refused_context_renders_unsupported(self, query_db: Database) -> None:
        value = _provider().compute(
            query_db,
            _binding("fold_to_cbet_flop"),
            stats.PlayerScope(alias="Cara"),
            context={"street": "flop"},
        )
        assert value.state == stats.STATE_UNSUPPORTED
        assert value.text == dsl.NO_DATA


# ---------------------------------------------------------------------------
# Computing
# ---------------------------------------------------------------------------


class TestComputing:
    def test_a_real_value_over_a_real_sample(self, query_db: Database) -> None:
        value = _provider().compute(query_db, _binding("fold_to_cbet_flop"), stats.PlayerScope(alias="Cara"))
        assert value.state == stats.STATE_OK
        assert value.available
        assert value.text.endswith("%")
        assert value.sample > 0
        assert "Value:" in value.tooltip()

    def test_a_hud_value_matches_the_report_value(self, query_db: Database) -> None:
        provider = _provider()
        binding = _binding("fold_to_cbet_flop")
        scope = stats.PlayerScope(alias="Cara")
        hud = provider.compute(query_db, binding, scope)
        entry = provider.report_entry(query_db, binding, scope)
        assert hud.rendered == entry["value"]

    def test_a_cell_below_its_sample_shows_no_data(self, query_db: Database) -> None:
        binding = _binding("fold_to_cbet_flop", min_sample=10_000)
        value = _provider().compute(query_db, binding, stats.PlayerScope(alias="Cara"))
        assert value.state == stats.STATE_BELOW_SAMPLE
        assert value.text == dsl.NO_DATA
        assert "below the minimum" in value.reason

    def test_a_player_with_no_matching_hands_shows_no_data(self, query_db: Database) -> None:
        """A player outside the population is an empty sample, and shows as one."""
        value = _provider().compute(query_db, _binding("fold_to_cbet_flop"), stats.PlayerScope(alias="Nobody"))
        assert value.state == stats.STATE_BELOW_SAMPLE
        assert value.text == dsl.NO_DATA

    def test_an_unresolved_seat_asks_about_nobody(self, query_db: Database) -> None:
        value = _provider().compute(query_db, _binding("fold_to_cbet_flop"), stats.PlayerScope())
        assert value.state == stats.STATE_UNKNOWN_PLAYER

    def test_an_unknown_definition_never_falls_back_to_a_same_named_stat(self, query_db: Database) -> None:
        value = _provider().compute(query_db, _binding("vpip"), stats.PlayerScope(alias="Cara"))
        assert value.state == stats.STATE_UNKNOWN_DEFINITION
        assert value.text == dsl.NO_DATA

    def test_the_cell_format_overrides_the_definition(self, query_db: Database) -> None:
        provider = _provider()
        definition = provider.definition(_binding("fold_to_cbet_flop"))
        assert definition is not None
        effective = provider.effective_definition(_binding("fold_to_cbet_flop", fmt="count"), definition)
        assert effective.display.fmt == "count"

    def test_a_second_read_is_served_from_the_session_cache(self, query_db: Database) -> None:
        provider = _provider()
        binding = _binding("fold_to_cbet_flop")
        scope = stats.PlayerScope(alias="Cara")
        first = provider.compute(query_db, binding, scope)
        queries_after_first = provider.counters.queries
        second = provider.compute(query_db, binding, scope)
        assert second == first
        assert provider.counters.queries == queries_after_first
        assert provider.counters.cache_hits == 1

    def test_a_query_failure_becomes_an_error_value_not_an_exception(self, query_db: Database) -> None:
        provider = _provider()
        with patch.object(stats, "run_query", side_effect=RuntimeError("boom")):
            value = provider.compute(query_db, _binding("fold_to_cbet_flop"), stats.PlayerScope(alias="Cara"))
        assert value.state == stats.STATE_ERROR
        assert provider.counters.failures == 1

    def test_invalidate_forgets_the_cache(self, query_db: Database) -> None:
        provider = _provider()
        scope = stats.PlayerScope(alias="Cara")
        provider.compute(query_db, _binding("fold_to_cbet_flop"), scope)
        assert provider.invalidate("test") == 1


# ---------------------------------------------------------------------------
# Batching: many cells, few queries
# ---------------------------------------------------------------------------


class TestBatching:
    def test_identical_requests_collapse_into_one_query(self, query_db: Database) -> None:
        provider = _provider()
        binding = _binding("fold_to_cbet_flop")
        scope = stats.PlayerScope(alias="Cara")
        provider.compute_batch(query_db, [(binding, scope)] * 8)
        assert provider.counters.queries == 1
        assert provider.counters.batch_reads == 1

    def test_two_formats_of_one_definition_share_a_query(self, query_db: Database) -> None:
        provider = _provider()
        scope = stats.PlayerScope(alias="Cara")
        values = provider.compute_batch(
            query_db,
            [
                (_binding("fold_to_cbet_flop", stat_name="a"), scope),
                (_binding("fold_to_cbet_flop", stat_name="b", fmt="count"), scope),
            ],
        )
        assert provider.counters.queries == 1
        assert len(values) == 2

    def test_distinct_definitions_cost_one_query_each(self, query_db: Database) -> None:
        provider = _provider()
        scope = stats.PlayerScope(alias="Cara")
        provider.compute_batch(
            query_db,
            [(_binding("fold_to_cbet_flop"), scope), (_binding("fold_to_3bet_preflop"), scope)],
        )
        assert provider.counters.queries == 2

    def test_compute_for_stat_dict_regroups_by_player(self, query_db: Database) -> None:
        provider = _provider()
        stat_dict = {
            7: {"screen_name": "Cara"},
            9: {"screen_name": "Nobody"},
            11: {"vpip": 3},
        }
        values = provider.compute_for_stat_dict(query_db, [_binding("fold_to_cbet_flop")], stat_dict)
        assert values[7]["fold_to_cbet_flop"].state == stats.STATE_OK
        assert values[9]["fold_to_cbet_flop"].state == stats.STATE_BELOW_SAMPLE
        assert values[11]["fold_to_cbet_flop"].state == stats.STATE_UNKNOWN_PLAYER

    def test_compute_for_stat_dict_is_free_without_bindings(self, query_db: Database) -> None:
        provider = _provider()
        assert provider.compute_for_stat_dict(query_db, [], {7: {"screen_name": "Cara"}}) == {}
        assert provider.counters.queries == 0

    def test_an_over_budget_batch_is_counted(self, query_db: Database) -> None:
        provider = _provider(latency_budget_ms=-1.0)
        provider.compute_batch(query_db, [(_binding("fold_to_cbet_flop"), stats.PlayerScope(alias="Cara"))])
        assert provider.counters.over_budget == 1


# ---------------------------------------------------------------------------
# Session: one table's handle on its analytics cells
# ---------------------------------------------------------------------------


class TestSession:
    def test_a_session_without_bindings_is_falsy(self) -> None:
        session = stats.AnalyticsStatSession()
        assert not session
        assert session.text_for("fold_to_cbet_flop") is None

    def test_a_bound_cell_with_no_published_value_shows_no_data(self) -> None:
        session = stats.AnalyticsStatSession(bindings=[_binding("fold_to_cbet_flop")])
        assert session
        assert session.text_for("fold_to_cbet_flop", 7) == dsl.NO_DATA
        assert session.pending(["fold_to_cbet_flop"], 7)

    def test_publishing_is_per_player(self) -> None:
        session = stats.AnalyticsStatSession(bindings=[_binding("fold_to_cbet_flop")])
        ok = stats.AnalyticsStatValue(
            stat_name="fold_to_cbet_flop",
            definition="fold_to_cbet_flop",
            state=stats.STATE_OK,
            raw=40.0,
            sample=25,
            rendered="40%",
        )
        session.publish({7: {"fold_to_cbet_flop": ok}})
        assert session.text_for("fold_to_cbet_flop", 7) == "40%"
        assert session.text_for("fold_to_cbet_flop", 9) == dsl.NO_DATA
        assert session.value_for("fold_to_cbet_flop", 7) is ok

    def test_a_flat_mapping_is_ignored_rather_than_misread(self) -> None:
        session = stats.AnalyticsStatSession(bindings=[_binding("fold_to_cbet_flop")])
        session.publish({"fold_to_cbet_flop": 1})  # not nested by player
        assert session.text_for("fold_to_cbet_flop", 7) == dsl.NO_DATA

    def test_an_unbound_name_is_not_an_analytics_cell(self) -> None:
        session = stats.AnalyticsStatSession(bindings=[_binding("fold_to_cbet_flop")])
        assert session.text_for("vpip", 7) is None

    def test_an_import_makes_the_published_values_stale(self, query_db: Database) -> None:
        provider = _provider()
        session = stats.AnalyticsStatSession(provider, [_binding("fold_to_cbet_flop")])
        session.publish({7: {"fold_to_cbet_flop": stats.AnalyticsStatValue("a", "a", stats.STATE_OK)}})
        assert not session.is_stale
        session.on_import()
        assert session.is_stale
        assert session.text_for("fold_to_cbet_flop", 7) == dsl.NO_DATA

    def test_from_config_reads_the_document(self) -> None:
        config = MagicMock()
        config.doc = minidom.parseString(
            '<stat_set><stat _stat_name="c" data_source="analytics" data_definition="fold_to_cbet_flop"/></stat_set>'
        )
        session = stats.AnalyticsStatSession.from_config(config)
        assert session.binding_for("c") is not None

    def test_from_config_can_scope_to_one_profile(self) -> None:
        config = MagicMock()
        config.doc = minidom.parseString(
            """
            <stat_sets>
              <ss name="ring"><stat _stat_name="c" data_source="analytics" data_definition="fold_to_cbet_flop"/></ss>
              <ss name="tour"><stat _stat_name="c" data_source="registry"/></ss>
            </stat_sets>
            """
        )
        assert stats.AnalyticsStatSession.from_config(config, stat_set="ring").binding_for("c") is not None
        assert stats.AnalyticsStatSession.from_config(config, stat_set="tour").binding_for("c") is None


# ---------------------------------------------------------------------------
# Publishing a batch the way the HUD read service needs it
# ---------------------------------------------------------------------------


class TestPublishHandValues:
    def test_regroups_by_player_and_stat_name(self) -> None:
        binding = _binding("fold_to_cbet_flop")
        scope = stats.PlayerScope(alias="Cara", player_id=7)
        value = stats.AnalyticsStatValue("fold_to_cbet_flop", "fold_to_cbet_flop", stats.STATE_OK, rendered="40%")
        batch = {(*binding.key(), scope.key()): value}
        by_player = stats.publish_hand_values(batch, {7: scope}, [binding])
        assert by_player[7]["fold_to_cbet_flop"] is value

    def test_a_missing_pair_is_simply_absent(self) -> None:
        assert stats.publish_hand_values({}, {7: stats.PlayerScope(alias="Cara")}, [_binding("x")]) == {}


# ---------------------------------------------------------------------------
# The read worker: the place the value is actually computed off the UI thread
# ---------------------------------------------------------------------------

_ANALYTICS_CONFIG = MagicMock()
_ANALYTICS_CONFIG.doc = minidom.parseString(
    """
    <stat_set>
      <stat _stat_name="fold_cbet" data_source="analytics"
            data_definition="fold_to_cbet_flop" data_format="percentage"/>
    </stat_set>
    """
)


class TestReadServiceIntegration:
    def test_a_config_with_analytics_cells_builds_a_provider(self) -> None:
        service = HudReadService(_ANALYTICS_CONFIG, MagicMock())
        provider, bindings = service._analytics()
        assert provider is not None
        assert [binding.stat_name for binding in bindings] == ["fold_cbet"]

    def test_a_config_without_analytics_cells_builds_nothing(self) -> None:
        service = HudReadService(MagicMock(), MagicMock())
        provider, bindings = service._analytics()
        assert provider is None
        assert bindings == ()

    def test_the_worker_fills_a_prepared_hand(self, query_db: Database) -> None:
        service = HudReadService(_ANALYTICS_CONFIG, query_db)
        prepared = HudPreparedHand(hand_id="h1", stat_dict={7: {"screen_name": "Cara"}})
        service._attach_analytics(prepared)
        value = prepared.analytics_values[7]["fold_cbet"]
        assert value.state == stats.STATE_OK
        assert value.text.endswith("%")

    def test_the_site_comes_from_the_table_info(self) -> None:
        from fpdb_3_legacy.table_info import TableInfo

        prepared = HudPreparedHand(
            hand_id="h1",
            table_info=TableInfo(table_name="t", site_name="PokerStars"),
            stat_dict={7: {"screen_name": "Cara"}},
        )
        assert HudReadService._site_name(prepared) == "PokerStars"
        assert HudReadService._site_name(HudPreparedHand(hand_id="h2")) == ""

    def test_a_profile_without_analytics_cells_does_not_touch_the_database(self) -> None:
        database = MagicMock()
        service = HudReadService(MagicMock(), database)
        prepared = HudPreparedHand(hand_id="h1", stat_dict={7: {"screen_name": "Cara"}})
        service._attach_analytics(prepared)
        assert prepared.analytics_values == {}
        assert database.method_calls == []
