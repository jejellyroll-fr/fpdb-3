"""The stats the HUD Preferences editor offers, checked against what the HUD draws."""

from __future__ import annotations

from collections import Counter
from types import SimpleNamespace

import pytest

from fpdb_3_legacy import Stats, hud_panel_editor
from fpdb_3_legacy.modern_hud_preferences import stat_catalog as sc


@pytest.fixture(scope="module")
def catalog() -> sc.StatCatalog:
    return sc.build_catalog()


def _choice(name: str, source: str, label: str = "", fmt: str = "", min_sample: int = 0):
    return hud_panel_editor.StatChoice(
        name=name,
        source=source,
        label=label,
        fmt=fmt,
        sample="",
        filters={},
        min_sample=min_sample,
        category="",
    )


# --- Against the running fpdb ------------------------------------------------
def test_every_name_is_a_stat_the_hud_can_draw(catalog) -> None:
    choices = {(choice.source, choice.name) for choice in hud_panel_editor.stat_choices()}
    for entry in catalog:
        if entry.origin == sc.ORIGIN_CLASSIC:
            assert entry.name in Stats.STATLIST, entry.key
        else:
            assert (entry.origin, entry.name) in choices, entry.key


def test_no_entry_is_listed_twice(catalog) -> None:
    keys = Counter(entry.key for entry in catalog)
    assert [key for key, count in keys.items() if count > 1] == []
    per_origin = Counter((entry.origin, entry.name) for entry in catalog)
    assert [pair for pair, count in per_origin.items() if count > 1] == []
    # A stats.d descriptor that a classic stat shadows is not offered twice.
    names = Counter(entry.name for entry in catalog if entry.origin != sc.ORIGIN_ANALYTICS)
    assert [name for name, count in names.items() if count > 1] == []


def test_every_statlist_stat_is_offered(catalog) -> None:
    offered = {entry.name for entry in catalog if entry.origin == sc.ORIGIN_CLASSIC}
    missing = [name for name in Stats.STATLIST if name not in offered]
    # What is left out is what is not a stat: helpers that slip into STATLIST
    # and have no description to show.
    described = Stats.get_valid_stats()
    assert [name for name in missing if described.get(name)] == []
    assert set(missing) <= {
        "STATS_DATA_ERRORS",
        "STAT_FUNCTIONS",
        "annotations",
        "get_hand_instance",
        "get_logger",
        "format_no_data_stat",
    }


def test_the_analytics_stats_are_offered_with_their_data_attributes(catalog) -> None:
    analytics = [choice for choice in hud_panel_editor.stat_choices() if choice.source == "analytics"]
    assert analytics, "the shipped analytics definitions are expected"
    for choice in analytics:
        entry = catalog.get(sc.make_key("analytics", choice.name))
        assert entry is not None, choice.name
        assert entry.attributes["data_source"] == "analytics"
        assert entry.attributes["data_definition"] == choice.name
        expected = hud_panel_editor.stat_entry_attributes(choice)
        assert dict(entry.attributes) == {k: v for k, v in expected.items() if k.startswith("data_")}


def test_no_shipped_classic_stat_falls_into_other(catalog) -> None:
    other = [entry.name for entry in catalog if entry.category == sc.OTHER and entry.origin == sc.ORIGIN_CLASSIC]
    assert other == []


def test_each_shipped_category_holds_stats(catalog) -> None:
    present = {entry.category for entry in catalog}
    assert present - set(sc.CATEGORIES) == set()
    assert present >= {sc.PLAYER, sc.PREFLOP, sc.STEAL, sc.FLOP, sc.TURN, sc.RIVER, sc.RESULTS, sc.AOF}


# --- Categories ----------------------------------------------------------------
@pytest.mark.parametrize(
    ("name", "category"),
    [
        ("vpip", sc.PREFLOP),
        ("f_steal", sc.STEAL),
        ("f_bet_facing", sc.FLOP),
        ("t_spr", sc.TURN),
        ("r_raise_made", sc.RIVER),
        ("cb4", sc.SEVENTH),
        ("aof_pair", sc.AOF),
        ("chipev_hu_sb", sc.TOURNAMENT),
        ("stack_bb", sc.TOURNAMENT),
        ("squeeze_btn", sc.PREFLOP),
        ("fold_vs_turn_cbet", sc.TURN),
        ("fold_to_cbet_flop_by_size", sc.FLOP),
        ("fold_to_3bet_preflop", sc.PREFLOP),
        ("call_float_river", sc.RIVER),
        ("fold_bb_to_steal", sc.STEAL),
        ("playername", sc.PLAYER),
        ("totalprofit", sc.RESULTS),
        ("agg_fact", sc.POSTFLOP),
        ("draw_decision_distribution", sc.OTHER),
        ("", sc.OTHER),
    ],
)
def test_category_for(name, category) -> None:
    assert sc.category_for(name) == category


def test_labels_fall_back_rather_than_fail() -> None:
    assert sc.category_label(sc.FLOP) == "Flop / 4th street"
    assert sc.category_label("nonsense") == "Other"
    assert sc.origin_label(sc.ORIGIN_ANALYTICS) == "analytics"
    assert sc.origin_label("elsewhere") == "elsewhere"


# --- Built from given sources --------------------------------------------------
def _small() -> sc.StatCatalog:
    return sc.build_catalog(
        stat_names=["vpip", "pfr", "get_logger", "fold_to_cbet_flop", "format_no_data_stat"],
        descriptions={
            "vpip": "Voluntarily put in",
            "pfr": "Preflop raise",
            "fold_to_cbet_flop": "Fold to c-bet",
            "format_no_data_stat": None,
        },
        choices=[
            _choice("pfr", "registry", "PFR"),
            _choice("chipev_hu_sb", "registry", "ChipEV heads-up SB"),
            _choice("fold_to_cbet_flop", "analytics", "Fold to flop c-bet", fmt="percentage", min_sample=5),
            _choice("draw_decision_distribution", "analytics"),
            _choice("odd", "elsewhere"),
        ],
    )


def test_the_classic_and_analytics_stats_of_one_name_are_two_entries() -> None:
    catalog = _small()
    assert [entry.key for entry in catalog] == [
        "classic:pfr",
        "classic:vpip",
        "classic:fold_to_cbet_flop",
        "analytics:fold_to_cbet_flop",
        "registry:chipev_hu_sb",
        "analytics:draw_decision_distribution",
    ]
    assert len(catalog) == 6
    assert "classic:pfr" in catalog
    assert "registry:pfr" not in catalog
    assert "classic:get_logger" not in catalog


def test_an_analytics_entry_without_a_label_shows_its_name() -> None:
    entry = _small().get("analytics:draw_decision_distribution")
    assert entry is not None
    assert entry.description == "draw_decision_distribution"
    assert entry.attributes == {"data_source": "analytics", "data_definition": "draw_decision_distribution"}


def test_new_item_carries_the_cell_and_the_data_attributes() -> None:
    catalog = _small()
    analytics = catalog.get("analytics:fold_to_cbet_flop")
    classic = catalog.get("classic:vpip")
    assert analytics is not None
    assert classic is not None
    assert analytics.new_item(1, 2) == {
        "row": 1,
        "col": 2,
        "stat": "fold_to_cbet_flop",
        "click": "",
        "popup": "",
        "data_source": "analytics",
        "data_definition": "fold_to_cbet_flop",
        "data_format": "percentage",
        "data_min_sample": "5",
    }
    assert classic.new_item(0, 0) == {"row": 0, "col": 0, "stat": "vpip", "click": "", "popup": ""}
    assert classic.new_item(0, 0) is not classic.new_item(0, 0)


def test_a_key_given_twice_keeps_the_first_entry() -> None:
    first = sc.CatalogEntry("classic:x", "x", "first", sc.OTHER, sc.ORIGIN_CLASSIC)
    second = sc.CatalogEntry("classic:x", "x", "second", sc.OTHER, sc.ORIGIN_CLASSIC)
    catalog = sc.StatCatalog([first, second])
    assert list(catalog) == [first]
    assert catalog.get("classic:x") is first


# --- Filtering and grouping ----------------------------------------------------
@pytest.mark.parametrize(
    ("text", "keys"),
    [
        ("", 6),
        ("   ", 6),
        ("VPIP", ["classic:vpip"]),
        ("voluntarily", ["classic:vpip"]),
        ("preflop", ["classic:pfr", "classic:vpip"]),
        ("tournament", ["registry:chipev_hu_sb"]),
        ("analytics flop", ["analytics:fold_to_cbet_flop"]),
        ("fold c-bet", ["classic:fold_to_cbet_flop", "analytics:fold_to_cbet_flop"]),
        ("stats.d", ["registry:chipev_hu_sb"]),
        ("nothing-matches", []),
    ],
)
def test_filter(text, keys) -> None:
    found = _small().filter(text)
    if isinstance(keys, int):
        assert len(found) == keys
    else:
        assert [entry.key for entry in found] == keys


def test_grouped_follows_the_category_order() -> None:
    catalog = _small()
    groups = catalog.grouped()
    assert [category for category, _entries in groups] == [sc.PREFLOP, sc.FLOP, sc.TOURNAMENT, sc.OTHER]
    assert [entry.name for entry in groups[0][1]] == ["pfr", "vpip"]


def test_grouped_of_a_filtered_list_leaves_empty_groups_out() -> None:
    catalog = _small()
    assert [category for category, _ in catalog.grouped(catalog.filter("vpip"))] == [sc.PREFLOP]
    assert catalog.grouped(()) == []


def test_grouped_puts_an_unknown_category_last() -> None:
    odd = sc.CatalogEntry("classic:y", "y", "", "unheard-of", sc.ORIGIN_CLASSIC)
    plain = sc.CatalogEntry("classic:vpip", "vpip", "", sc.PREFLOP, sc.ORIGIN_CLASSIC)
    catalog = sc.StatCatalog([odd, plain])
    assert [entry.key for entry in catalog] == ["classic:vpip", "classic:y"]
    assert [category for category, _ in catalog.grouped()] == [sc.PREFLOP, "unheard-of"]
    assert odd.category_label == "Other"


def test_the_default_sources_are_the_running_fpdb(monkeypatch) -> None:
    calls = SimpleNamespace(choices=0)

    def fake_choices():
        calls.choices += 1
        return (_choice("chipev_hu_sb", "registry"),)

    monkeypatch.setattr(hud_panel_editor, "stat_choices", fake_choices)
    catalog = sc.build_catalog(stat_names=["vpip"])
    assert calls.choices == 1
    assert [entry.key for entry in catalog] == ["classic:vpip", "registry:chipev_hu_sb"]
    assert catalog.get("classic:vpip").description == Stats.get_valid_stats()["vpip"]
