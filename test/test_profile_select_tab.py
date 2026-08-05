"""The Profile Select tab: 154 lines of UI that shipped with no tests.

It is the only place a player creates the rules that decide which HUD profile
a table gets, and a wrong rule is not visible until a table opens. These tests
drive the real dialog against a real configuration file.
"""

from __future__ import annotations

import os
import shutil

import pytest

pytestmark = pytest.mark.qt

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
EXAMPLE = os.path.join(ROOT, "HUD_config.xml.example")

pytestmark = [pytest.mark.qt, pytest.mark.skipif(not os.path.exists(EXAMPLE), reason="example config missing")]


@pytest.fixture
def dialog(tmp_path):
    from PySide6.QtWidgets import QApplication

    from fpdb_3_legacy import Configuration as Conf
    from fpdb_3_legacy import ModernHudPreferences as M

    QApplication.instance() or QApplication([])
    config_path = tmp_path / "HUD_config.xml"
    shutil.copy(EXAMPLE, config_path)
    config = Conf.Config(file=str(config_path))
    dlg = M.ModernHudPreferences(config, None)
    dlg._config_path = config_path
    return dlg


def _select(dialog, **values) -> None:
    """Set the selector combos by their stored data, not their labels."""
    combos = {
        "site": dialog.rule_site_combo,
        "game": dialog.rule_game_combo,
        "game_type": dialog.rule_type_combo,
        "limit": dialog.rule_limit_combo,
        "seats": dialog.rule_seats_combo,
        "players": dialog.rule_players_combo,
        "speed": dialog.rule_speed_combo,
        "profile": dialog.rule_profile_combo,
    }
    for key, value in values.items():
        combo = combos[key]
        index = combo.findData(str(value))
        assert index >= 0, f"no {key} option for {value!r}"
        combo.setCurrentIndex(index)


def test_the_tab_exists_and_starts_empty(dialog) -> None:
    titles = [dialog.tabs.tabText(i) for i in range(dialog.tabs.count())]
    assert any("Profile Select" in title for title in titles)
    assert dialog.profile_rules == []
    assert dialog.profile_rules_table.rowCount() == 0


def test_adding_a_rule_lists_it_with_wildcards_spelled_out(dialog) -> None:
    profile = dialog.rule_profile_combo.itemData(0)
    _select(dialog, site="CoinPoker", game="omahahi", seats="6", profile=profile)

    dialog._add_profile_rule()

    assert dialog.profile_rules_table.rowCount() == 1
    row = [dialog.profile_rules_table.item(0, column).text() for column in range(8)]
    assert row[0] == "coinpoker"
    assert row[1] == "omahahi"
    assert row[2] == "ANY", "an unset dimension must read as ANY, not blank"
    assert row[4] == "6"
    assert row[7] == profile


def test_a_duplicate_rule_is_refused(dialog, monkeypatch) -> None:
    from fpdb_3_legacy.modern_hud_preferences import main_dialog

    warned = []
    monkeypatch.setattr(main_dialog.QMessageBox, "warning", lambda *args: warned.append(args))
    profile = dialog.rule_profile_combo.itemData(0)
    _select(dialog, site="CoinPoker", game="omahahi", profile=profile)

    dialog._add_profile_rule()
    dialog._add_profile_rule()

    assert len(dialog.profile_rules) == 1
    assert warned, "the player must be told, not silently ignored"


def test_deleting_a_rule_renumbers_the_rest(dialog) -> None:
    """Order is the last tie-breaker, so it must stay 0..n-1 after a delete."""
    profile = dialog.rule_profile_combo.itemData(0)
    for game in ("omahahi", "holdem"):
        _select(dialog, game=game, profile=profile)
        dialog._add_profile_rule()

    dialog.profile_rules_table.setCurrentCell(0, 0)
    dialog._delete_profile_rule()

    assert [rule.game for rule in dialog.profile_rules] == ["holdem"]
    assert [rule.order for rule in dialog.profile_rules] == [0]


def test_the_preview_names_the_rule_that_wins(dialog) -> None:
    profile = dialog.rule_profile_combo.itemData(0)
    _select(dialog, site="CoinPoker", game="omahahi", seats="6", profile=profile)
    dialog._add_profile_rule()

    text = dialog.profile_preview_label.text()

    assert profile in text
    assert "site=coinpoker" in text and "seats=6" in text


def test_the_preview_falls_back_to_the_game_default(dialog) -> None:
    """With no rule, the table gets what <supported_games> says."""
    _select(dialog, game="holdem", game_type="ring")

    text = dialog.profile_preview_label.text()

    assert "no rule matches" in text
    default = dialog.config.get_supported_games_parameters("holdem", "ring")["game_stat_set"].name
    assert default in text


def test_the_preview_follows_the_most_specific_rule(dialog) -> None:
    """Two rules match; the resolver's precedence must be what is shown."""
    profiles = [dialog.rule_profile_combo.itemData(i) for i in range(2)]
    _select(dialog, game="omahahi", profile=profiles[0])
    dialog._add_profile_rule()
    _select(dialog, site="CoinPoker", game="omahahi", seats="6", profile=profiles[1])
    dialog._add_profile_rule()

    _select(dialog, site="CoinPoker", game="omahahi", seats="6")

    assert profiles[1] in dialog.profile_preview_label.text()


def test_a_rule_naming_a_missing_profile_is_flagged(dialog) -> None:
    from fpdb_3_legacy.hud_profiles import HudProfileRule

    dialog.profile_rules = [HudProfileRule.from_mapping({"profile": "deleted_profile", "game": "omahahi"})]
    dialog._refresh_profile_rules_table()

    cell = dialog.profile_rules_table.item(0, 7)
    assert "⚠" in cell.text()
    assert "No HUD profile of this name exists" in cell.toolTip()

    _select(dialog, game="omahahi")
    assert "⚠" in dialog.profile_preview_label.text()


def test_saved_rules_survive_a_reload_and_reach_the_resolver(dialog) -> None:
    """Apply has to reach the config the HUD reads, not just the dialog."""
    from fpdb_3_legacy import Configuration as Conf
    from fpdb_3_legacy.hud_profiles import HudContext

    profile = dialog.rule_profile_combo.itemData(0)
    _select(dialog, site="CoinPoker", game="omahahi", seats="6", profile=profile)
    dialog._add_profile_rule()
    dialog.config.set_hud_profile_rules(dialog.profile_rules)
    dialog.config.save()

    reloaded = Conf.Config(file=str(dialog._config_path))
    params = reloaded.get_supported_games_parameters(
        "omahahi", "ring", HudContext("CoinPoker", "omahahi", "ring", max_seats=6)
    )

    assert params["game_stat_set"].name == profile


def test_reload_picks_up_rules_saved_by_another_process(dialog) -> None:
    """HUD_main reloads the same object; the rules must come back with it."""
    profile = dialog.rule_profile_combo.itemData(0)
    _select(dialog, site="CoinPoker", game="aof_omaha", profile=profile)
    dialog._add_profile_rule()
    dialog.config.set_hud_profile_rules(dialog.profile_rules)
    dialog.config.save()

    dialog.config.hud_profile_rules = []  # as if this were a fresh process
    dialog.config.reload()

    assert [rule.profile for rule in dialog.config.get_hud_profile_rules()] == [profile]
