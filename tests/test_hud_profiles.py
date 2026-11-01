import shutil
from pathlib import Path
from types import SimpleNamespace

import defusedxml.minidom as minidom

from fpdb_3_legacy import Aux_Base, Aux_Hud, Configuration
from fpdb_3_legacy.hud_profiles import HudContext, HudPositionScope, HudProfileResolver, HudProfileRule


def test_more_specific_profile_rule_wins() -> None:
    rules = [
        HudProfileRule.from_mapping({"profile": "generic", "site": "CoinPoker"}, 0),
        HudProfileRule.from_mapping({"profile": "aof", "site": "CoinPoker", "game": "aof_omaha", "seats": 6}, 1),
    ]
    ctx = HudContext("CoinPoker", "aof_omaha", "ring", max_seats=6, players=2)
    assert HudProfileResolver(rules).resolve(ctx, "fallback") == "aof"


def test_priority_then_xml_order_break_ties_deterministically() -> None:
    rules = [
        HudProfileRule.from_mapping({"profile": "first", "game": "omahahi", "priority": 3}, 0),
        HudProfileRule.from_mapping({"profile": "second", "game": "omahahi", "priority": 3}, 1),
        HudProfileRule.from_mapping({"profile": "priority", "game": "omahahi", "priority": 4}, 2),
    ]
    assert HudProfileResolver(rules).resolve(HudContext("x", "omahahi", "ring")) == "priority"
    assert HudProfileResolver(rules[:2]).resolve(HudContext("x", "omahahi", "ring")) == "first"


def test_position_scope_separates_standard_plo_and_aof() -> None:
    common = dict(site="CoinPoker", game_type="ring", max_seats=6, layout="default")
    plo = HudPositionScope(game="omahahi", profile="plo4_6max_pro", **common)
    aof = HudPositionScope(game="aof_omaha", profile="aof_default", **common)
    assert plo.key(1, "main") != aof.key(1, "main")


def test_wildcards_match_any_context_dimension() -> None:
    rule = HudProfileRule.from_mapping({"profile": "default"})
    assert rule.matches(HudContext("CoinPoker", "future_game", "tour", "pl", 9, 6, "fast"))


def test_v2_store_keeps_identical_layout_and_profile_separate_by_game(tmp_path) -> None:
    store = Aux_Hud.HUDLayoutPositionsStore.__new__(Aux_Hud.HUDLayoutPositionsStore)
    store.path = str(tmp_path / "positions.json")
    store.data = {"version": 2, "positions": {}}
    common = ("CoinPoker", "default", "shared_profile", 6, 1, "classic")
    store.set_position(*common, 10, 20, game="omahahi", game_type="ring")
    store.set_position(*common, 30, 40, game="aof_omaha", game_type="ring")
    assert store.get_position(*common, game="omahahi", game_type="ring") == (10, 20)
    assert store.get_position(*common, game="aof_omaha", game_type="ring") == (30, 40)


def test_live_drag_propagates_only_to_exact_position_scope() -> None:
    layout_set = object()
    standard_scope = HudPositionScope("CoinPoker", "omahahi", "ring", 6, "shared", "default")
    aof_scope = HudPositionScope("CoinPoker", "aof_omaha", "ring", 6, "shared", "default")
    source = SimpleNamespace(position_scope=standard_scope, layout_set=layout_set, max=6, table=SimpleNamespace(width=800, height=600))
    same = SimpleNamespace(position_scope=standard_scope, layout_set=layout_set, max=6)
    other_game = SimpleNamespace(position_scope=aof_scope, layout_set=layout_set, max=6)
    source.parent = SimpleNamespace(hud_dict={"source": source, "same": same, "aof": other_game})
    aux = Aux_Base.AuxSeats.__new__(Aux_Base.AuxSeats)
    aux.hud = source
    reached = []
    aux._apply_position_to_hud = lambda hud, *_args: reached.append(hud)
    aux._propagate_to_open_huds(1, (100, 200))
    assert reached == [same]


def test_shipped_config_carries_an_empty_documented_rules_section() -> None:
    """The section must ship present and inert: discoverable, but a no-op.

    An absent section left the feature invisible; a populated one would
    silently repoint everybody's HUD on upgrade.
    """
    source = Path(__file__).parents[1] / "HUD_config.xml.example"
    config = Configuration.Config(file=str(source))

    assert config.get_hud_profile_rules() == []
    assert config.doc.getElementsByTagName("hud_profile_rules"), "the section must exist to be found"
    assert "hud_profile_rule " in source.read_text(encoding="utf-8"), "an example must be documented"


def test_an_existing_config_gains_the_section_with_its_documentation(tmp_path) -> None:
    """Upgrading users get the section installed; empty and unexplained is no use."""
    source = minidom.parse(str(Path(__file__).parents[1] / "HUD_config.xml.example"))
    for node in list(source.getElementsByTagName("hud_profile_rules")):
        node.parentNode.removeChild(node)
    config_path = tmp_path / "HUD_config.xml"
    config_path.write_text(source.toxml(), encoding="utf-8")

    config = object.__new__(Configuration.Config)
    config.file = str(config_path)
    config.general = Configuration.General()
    config.doc = minidom.parse(str(config_path))
    added = config.add_missing_elements(config.doc, str(Path(__file__).parents[1] / "HUD_config.xml.example"))

    saved = config_path.read_text(encoding="utf-8")
    assert added == 1
    assert "<hud_profile_rules" in saved
    assert "HUD profile rules: choose which stat set" in saved, "the section must arrive explained"
    assert Configuration.Config(file=str(config_path)).get_hud_profile_rules() == []


def test_saving_rules_keeps_the_documentation_comment(tmp_path) -> None:
    """The GUI rewrites the element, so the docs have to live outside it."""
    source = Path(__file__).parents[1] / "HUD_config.xml.example"
    config_path = tmp_path / "HUD_config.xml"
    shutil.copyfile(source, config_path)
    config = Configuration.Config(file=str(config_path))

    config.set_hud_profile_rules([HudProfileRule.from_mapping({"profile": "aof_default", "site": "CoinPoker"})])
    config.save(file=str(config_path))

    saved = config_path.read_text(encoding="utf-8")
    assert "HUD profile rules: choose which stat set" in saved
    assert saved.count("<hud_profile_rules>") == 1, "the GUI must reuse the shipped section"


def test_profile_rules_round_trip_through_hud_config(tmp_path) -> None:
    source = Path(__file__).parents[1] / "HUD_config.xml.example"
    config_path = tmp_path / "HUD_config.xml"
    shutil.copyfile(source, config_path)
    config = Configuration.Config(file=str(config_path))
    config.set_hud_profile_rules(
        [
            HudProfileRule.from_mapping(
                {
                    "id": "coin-aof",
                    "site": "CoinPoker",
                    "game": "aof_omaha",
                    "game_type": "ring",
                    "seats": 6,
                    "profile": "aof_default",
                }
            )
        ]
    )
    config.save(file=str(config_path))

    reloaded = Configuration.Config(file=str(config_path))
    assert reloaded.get_hud_profile_rules()[0].profile == "aof_default"
    params = reloaded.get_supported_games_parameters(
        "aof_omaha",
        "ring",
        HudContext("CoinPoker", "aof_omaha", "ring", max_seats=6),
    )
    assert params["game_stat_set"].name == "aof_default"
