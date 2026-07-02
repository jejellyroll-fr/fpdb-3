"""Unit tests for the legacy Configuration module.

Builds a real Config from the checked-in HUD_config.xml and exercises the many
accessor methods, plus the standalone default-builders (General, GUICashStats,
GUITourStats). This drives a large share of Configuration.py without a DB.
"""

from __future__ import annotations

import pytest

from fpdb_3_legacy import Configuration
from fpdb_3_legacy.Configuration import (
    Config,
    General,
    GUICashStats,
    GUITourStats,
)

CONFIG_FILE = "HUD_config.xml"


@pytest.fixture(scope="module")
def cfg() -> Config:
    return Config(file=CONFIG_FILE)


def test_config_constructs_with_collections(cfg: Config) -> None:
    assert len(cfg.supported_sites) > 0
    assert len(cfg.supported_games) > 0
    assert len(cfg.stat_sets) > 0
    assert len(cfg.aux_windows) > 0
    assert len(cfg.layout_sets) > 0
    assert len(cfg.supported_databases) >= 1


def test_no_arg_getters_return_values(cfg: Config) -> None:
    assert cfg.get_doc() is not None
    assert isinstance(cfg.get_db_parameters(), dict)
    assert isinstance(cfg.get_hud_ui_parameters(), dict)
    assert isinstance(cfg.get_import_parameters(), dict)
    assert isinstance(cfg.get_default_paths(), dict)
    assert isinstance(cfg.get_supported_sites(), list)
    assert isinstance(cfg.get_supported_sites(all=True), list)
    assert isinstance(cfg.get_aux_windows(), list)
    assert isinstance(cfg.get_stat_sets(), (list, dict))
    assert isinstance(cfg.get_layout_sets(), (list, dict))
    assert isinstance(cfg.get_supported_games(), list)
    assert isinstance(cfg.get_general_params(), dict)
    assert cfg.get_gui_cash_stat_params() is not None
    assert cfg.get_gui_tour_stat_params() is not None


def test_get_layout_set_locations(cfg: Config) -> None:
    # Default args reference a "mucked" set/max that may not exist; the method
    # raises KeyError in that case. A known layout set should resolve.
    name = next(iter(cfg.layout_sets))
    ls = cfg.layout_sets[name]
    a_max = next(iter(ls.layout))
    locations = cfg.get_layout_set_locations(set=name, max=a_max)
    assert locations is not None


def test_ipoker_6max_layout_matches_pmu_visual_ring(cfg: Config) -> None:
    layout = cfg.layout_sets["ipoker_default"].layout[6]

    assert layout.hh_seats == [None, 1, 3, 5, 6, 8, 10]
    assert layout.location[1] == (473, 128)
    assert layout.location[2] == (749, 195)
    assert layout.location[3] == (737, 472)
    assert layout.location[4] == (420, 500)
    assert layout.location[5] == (65, 469)
    assert layout.location[6] == (38, 197)


def test_each_site_parameters(cfg: Config) -> None:
    # get_site_parameters reads self.hhcs[site]; only sites with a hand-history
    # converter resolve. (Sites without an HHC raise KeyError - see below.)
    for site in cfg.supported_sites:
        assert cfg.get_site_node(site) is not None
        if site not in cfg.hhcs:
            continue
        params = cfg.get_site_parameters(site)
        assert isinstance(params, dict)
        try:
            cfg.get_site_id(site)
        except Exception:  # noqa: BLE001 - id lookup needs a populated DB
            pass


def test_get_site_parameters_without_hhc_returns_none_converter(cfg: Config) -> None:
    # A supported site with no hand-history converter entry must NOT raise
    # (that would abort auto-import / HUD for every site): get_site_parameters
    # returns converter=None for it instead. See PR #232.
    siteless = [s for s in cfg.supported_sites if s not in cfg.hhcs]
    if not siteless:
        pytest.skip("every supported site has an HHC in this config")
    params = cfg.get_site_parameters(siteless[0])
    assert params["converter"] is None
    assert params["summaryImporter"] is None


def test_each_aux_window_parameters(cfg: Config) -> None:
    for aux in cfg.get_aux_windows():
        assert cfg.get_aux_node(aux) is not None
        assert isinstance(cfg.get_aux_parameters(aux), dict)


def test_each_stat_set_node(cfg: Config) -> None:
    for ss in cfg.stat_sets:
        assert cfg.get_stat_set_node(ss) is not None


def test_each_layout_set(cfg: Config) -> None:
    for ls in cfg.layout_sets:
        assert cfg.get_layout_set_node(ls) is not None
        assert isinstance(cfg.get_layout_set_parameters(ls), dict)


def test_each_database_node(cfg: Config) -> None:
    for db_name in cfg.supported_databases:
        assert cfg.get_db_node(db_name) is not None


def test_each_supported_game_parameters(cfg: Config) -> None:
    for name in cfg.get_supported_games():
        for game_type in ("ring", "tour"):
            params = cfg.get_supported_games_parameters(name, game_type)
            # Returns a dict when the game supports the type, else None/empty.
            assert params is None or isinstance(params, dict)


def test_get_layout_for_sites(cfg: Config) -> None:
    for site in list(cfg.supported_sites)[:5]:
        for game_type in ("ring", "tour"):
            # get_layout may return None when no layout matches; should not raise.
            cfg.get_layout(site, game_type)


def test_get_backend_known_names(cfg: Config) -> None:
    assert cfg.get_backend("sqlite") is not None
    assert cfg.get_backend("postgresql") is not None
    assert cfg.get_backend("mysql") is not None


def test_general_defaults() -> None:
    general = General()
    general.get_defaults()
    assert "ui_language" in general
    assert "config_difficulty" in general


def test_gui_cash_stats_defaults() -> None:
    stats = GUICashStats()
    stats.get_defaults()
    assert len(stats) > 0
    # Each row is a list describing a stat column.
    assert all(isinstance(row, list) for row in stats)


def test_gui_tour_stats_defaults() -> None:
    stats = GUITourStats()
    stats.get_defaults()
    assert len(stats) > 0
    assert all(isinstance(row, list) for row in stats)


def test_get_site_parameters_unknown_site_raises_or_none(cfg: Config) -> None:
    # Unknown site is not in supported_sites; accessing it should not silently
    # succeed with a populated dict.
    with pytest.raises((KeyError, AttributeError, TypeError)):
        cfg.get_site_parameters("NoSuchSite_xyz")


def test_module_get_config_helper(tmp_path) -> None:
    # get_config returns a path string (and a flag) for an existing file.
    result = Configuration.get_config(CONFIG_FILE, fallback=True)
    assert result is not None
