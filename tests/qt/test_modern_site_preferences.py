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
def test_site_card_does_not_scan_the_filesystem_to_offer_auto_detect(qtbot, monkeypatch) -> None:
    """Building a card must not run site detection.

    Whether a site offers auto-detection is a lookup in a static list, but it
    used to be answered by constructing a DetectInstalledSites -- which parses
    the configuration and probes the filesystem for every supported network.
    One card did that once; a dialog full of them froze the UI for seconds, and
    on a cold cache far longer.
    """
    from fpdb_3_legacy import DetectInstalledSites
    from fpdb_3_legacy.ModernSitePreferences import ModernSiteCard

    def explode(*args, **kwargs):
        msg = "site detection must not run while building a site card"
        raise AssertionError(msg)

    monkeypatch.setattr(DetectInstalledSites, "DetectInstalledSites", explode)

    site_config = types.SimpleNamespace(
        enabled=True,
        screen_name="main",
        hero_aliases=["main"],
        HH_path="/tmp/hh",
        TS_path="",
    )
    card = ModernSiteCard("PokerStars", site_config)
    qtbot.addWidget(card)

    # PokerStars has a detector, so the button is still offered.
    assert card.is_site_detectable() is True
    # A site with no detector still gets no button.
    assert not ModernSiteCard("Some Unknown Room", site_config).is_site_detectable()


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


@pytest.mark.qt
def test_a_profile_link_can_name_the_phh_source(qtbot) -> None:
    """#423: a PHH name joins a room's in one hero profile."""
    cfg, dia = _dialog(qtbot)
    room = cfg.get_supported_sites(all=True)[0]

    assert "PHH" in dia._all_site_names()
    dia.add_profile("Me")
    dia.add_link_row(room, "jeje")
    dia.add_link_row("PHH", "jeje_phh")

    working, _deleted = dia.get_profile_changes()
    assert working["Me"]["links"] == [(room, "jeje"), ("PHH", "jeje_phh")]


@pytest.mark.qt
def test_the_data_sources_tab_edits_the_phh_hero_aliases(qtbot) -> None:
    from fpdb_3_legacy.Configuration import Config
    from fpdb_3_legacy.ModernSitePreferences import ModernSitePreferencesDialog

    cfg = Config(file="HUD_config.xml")
    cfg.set_data_source_hero_aliases("PHH", ["jeje"])  # in memory only: never saved here
    dia = ModernSitePreferencesDialog(cfg)
    qtbot.addWidget(dia)

    tabs = [dia.tabs.tabText(i) for i in range(dia.tabs.count())]
    assert "Data Sources" in tabs
    assert dia.data_source_inputs["PHH"].toPlainText() == "jeje"

    # One name per line: a PHH name is any string, a comma included, matched exactly.
    dia.data_source_inputs["PHH"].setPlainText("jeje\n\nSmith, John\n jeje76 \njeje")
    assert dia.get_data_source_changes() == {"PHH": ["jeje", "Smith, John", "jeje76"]}
