from __future__ import annotations

import types

import pytest


@pytest.mark.qt
def test_site_card_prefills_extra_aliases(qtbot) -> None:
    from fpdb_3_legacy.ModernSitePreferences import ModernSiteCard

    site_config = types.SimpleNamespace(
        enabled=True,
        screen_name="main",
        hero_aliases=["main", "old"],
        HH_path="/tmp/hh",
        TS_path="",
    )
    card = ModernSiteCard("PokerStars", site_config)
    qtbot.addWidget(card)

    # The "Other Aliases" field shows every alias except the primary screen name.
    assert card.aliases_input.text() == "old"


@pytest.mark.qt
def test_site_card_get_values_returns_deduped_hero_aliases(qtbot) -> None:
    from fpdb_3_legacy.ModernSitePreferences import ModernSiteCard

    site_config = types.SimpleNamespace(
        enabled=True,
        screen_name="main",
        hero_aliases=["main"],
        HH_path="/tmp/hh",
        TS_path="",
    )
    card = ModernSiteCard("PokerStars", site_config)
    qtbot.addWidget(card)

    card.screen_name_input.setText("newmain")
    # Includes blanks and a duplicate of the primary -> both dropped.
    card.aliases_input.setText("old, , newmain, second")

    values = card.get_values()
    assert values["screen_name"] == "newmain"
    assert values["hero_aliases"] == ["newmain", "old", "second"]


# --------------------------------------------------------------------------- #
# Hero Profiles tab                                                            #
# --------------------------------------------------------------------------- #


def _dialog(qtbot):
    from fpdb_3_legacy.Configuration import Config
    from fpdb_3_legacy.ModernSitePreferences import ModernSitePreferencesDialog

    cfg = Config(file="HUD_config.xml")
    dia = ModernSitePreferencesDialog(cfg)
    qtbot.addWidget(dia)
    return cfg, dia


@pytest.mark.qt
def test_profiles_tab_create_returns_changes(qtbot) -> None:
    cfg, dia = _dialog(qtbot)
    sites = cfg.get_supported_sites(all=True)
    s0, s1 = sites[0], sites[1]

    dia.add_profile("Me")
    dia.add_link_row(s0, "jeje")
    dia.add_link_row(s1, "jeje76")
    dia.add_link_row(s0, "jeje")  # duplicate dropped on read
    dia.profile_default_cb.setChecked(True)

    working, deleted = dia.get_profile_changes()
    assert deleted == set()
    assert "Me" in working
    assert working["Me"]["default"] is True
    assert working["Me"]["links"] == [(s0, "jeje"), (s1, "jeje76")]


@pytest.mark.qt
def test_profiles_tab_loads_and_deletes_existing(qtbot) -> None:
    from fpdb_3_legacy.Configuration import Config
    from fpdb_3_legacy.ModernSitePreferences import ModernSitePreferencesDialog

    cfg = Config(file="HUD_config.xml")
    site = cfg.get_supported_sites(all=True)[0]
    cfg.save_hero_profile("Old", [(site, "a")], default=False)

    dia = ModernSitePreferencesDialog(cfg)
    qtbot.addWidget(dia)

    # The existing profile is loaded into the editor list.
    items = [dia.profile_list.item(i).text() for i in range(dia.profile_list.count())]
    assert "Old" in items

    dia.profile_list.setCurrentRow(items.index("Old"))
    dia.delete_profile()

    working, deleted = dia.get_profile_changes()
    assert "Old" not in working
    assert "Old" in deleted
