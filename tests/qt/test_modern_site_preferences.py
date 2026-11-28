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


def _betfair_card(qtbot):
    from fpdb_3_legacy.ModernSitePreferences import ModernSiteCard

    site_config = types.SimpleNamespace(enabled=False, screen_name="", hero_aliases=[], HH_path="", TS_path="")
    card = ModernSiteCard("PokerStars on Betfair", site_config)
    qtbot.addWidget(card)
    return card


@pytest.mark.qt
def test_a_folder_that_names_no_hero_keeps_the_typed_screen_name(qtbot) -> None:
    """#854: typing the name, then Detect, saved the room with no hero."""
    card = _betfair_card(qtbot)
    card.screen_name_input.setText("alice")

    card.apply_detection_results(
        {
            "detected": True,
            "heroname": "",
            "hhpath": "C:/Betfair.UK/HandHistory",
            "tspath": "C:/Betfair.UK/TournSummary",
        }
    )

    values = card.get_values()
    assert values["screen_name"] == "alice"
    assert values["hh_path"] == "C:/Betfair.UK/HandHistory"
    assert values["ts_path"] == "C:/Betfair.UK/TournSummary"
    assert values["enabled"] is True


@pytest.mark.qt
def test_a_folder_that_names_its_hero_fills_the_screen_name(qtbot) -> None:
    card = _betfair_card(qtbot)
    card.screen_name_input.setText("typo")

    card.apply_detection_results({"detected": True, "heroname": "alice", "hhpath": "C:/hh/alice", "tspath": ""})

    assert card.get_values()["screen_name"] == "alice"


BWIN_FR = "/Containers/com.entainpt.bwinpokerfr.app/Data/Library/Application Support/Bwin.fr Online Poker"


def _bwin_card_detecting(qtbot, monkeypatch, skins, protected):
    """A Bwin.fr card whose detector finds ``skins`` and could not list ``protected``.

    Returns the card, the names the detector was given, and the warnings shown.
    """
    from fpdb_3_legacy import DetectInstalledSites, ModernSitePreferences
    from fpdb_3_legacy.ModernSitePreferences import ModernSiteCard

    given: list[list[str]] = []
    warnings: list[str] = []

    class FakeDetector:
        def __init__(self, sitename, hero_names=()):
            given.append(list(hero_names))

        def get_all_ipoker_skins(self):
            return skins

        def get_protected_ipoker_skins(self):
            return protected

    monkeypatch.setattr(DetectInstalledSites, "DetectInstalledSites", FakeDetector)
    monkeypatch.setattr(
        ModernSitePreferences.QMessageBox, "warning", lambda _parent, _title, text: warnings.append(text)
    )

    site_config = types.SimpleNamespace(enabled=True, screen_name="", hero_aliases=[], HH_path="", TS_path="")
    card = ModernSiteCard("Bwin.fr Poker", site_config)
    qtbot.addWidget(card)
    card.screen_name_input.setText("alice")
    card.aliases_input.setText("Hero, ")
    card.detect_clicked()
    return card, given, warnings


@pytest.mark.qt
def test_a_bwin_fr_folder_found_behind_macos_protection_fills_the_card_and_says_why(qtbot, monkeypatch) -> None:
    hhpath = f"{BWIN_FR}/alice/History/Data/Tables"
    found = {
        "detected": True,
        "skin": "Bwin.fr Poker",
        "heroname": "alice",
        "hhpath": hhpath,
        "tspath": f"{BWIN_FR}/alice/History/Data/Tournaments",
        "listing_denied": True,
    }

    card, given, warnings = _bwin_card_detecting(qtbot, monkeypatch, [found], {"Bwin.fr Poker": BWIN_FR})

    # The names typed in the card reach the detector: it cannot list the folder to find them.
    assert given == [["alice", "Hero"]]
    assert card.hh_path_input.text() == hhpath
    # Import lists that folder too, so the player must hear about Full Disk Access.
    [warning] = warnings
    assert hhpath in warning
    assert "Full Disk Access" in warning


@pytest.mark.qt
def test_a_protected_bwin_fr_folder_does_not_take_another_skins_paths(qtbot, monkeypatch) -> None:
    pmu = {"detected": True, "skin": "PMU Poker", "heroname": "bob", "hhpath": "/pmu/bob", "tspath": ""}

    card, _given, warnings = _bwin_card_detecting(qtbot, monkeypatch, [pmu], {"Bwin.fr Poker": BWIN_FR})

    assert card.hh_path_input.text() == ""
    [warning] = warnings
    assert BWIN_FR in warning


CHAMPION = "/Containers/com.championpoker.poker/Data/Library/Application Support/Championpoker Poker"


@pytest.mark.qt
def test_the_championpoker_card_detects_through_the_ipoker_detector(qtbot, monkeypatch) -> None:
    from fpdb_3_legacy import DetectInstalledSites
    from fpdb_3_legacy.ModernSitePreferences import ModernSiteCard

    asked: list[str] = []
    found = {
        "detected": True,
        "skin": "ChampionPoker",
        "heroname": "alice",
        "hhpath": f"{CHAMPION}/alice/History/Data/Tables",
        "tspath": f"{CHAMPION}/alice/History/Data/Tournaments",
    }
    pmu = {"detected": True, "skin": "PMU Poker", "heroname": "bob", "hhpath": "/pmu/bob", "tspath": ""}

    class FakeDetector:
        def __init__(self, sitename, hero_names=()):
            asked.append(sitename)

        def get_all_ipoker_skins(self):
            return [pmu, found]

        def get_protected_ipoker_skins(self):
            return {}

    monkeypatch.setattr(DetectInstalledSites, "DetectInstalledSites", FakeDetector)
    site_config = types.SimpleNamespace(enabled=True, screen_name="", hero_aliases=[], HH_path="", TS_path="")
    card = ModernSiteCard("ChampionPoker", site_config)
    qtbot.addWidget(card)

    assert card.is_site_detectable()
    card.detect_clicked()

    assert asked == ["iPoker"]
    assert card.hh_path_input.text() == found["hhpath"]
    assert card.get_values()["screen_name"] == "alice"


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
    dia.add_link_row(s0, "koko")
    dia.add_link_row(s1, "koko76")
    dia.add_link_row(s0, "koko")  # duplicate dropped on read
    dia.profile_default_cb.setChecked(True)

    working, deleted = dia.get_profile_changes()
    assert deleted == set()
    assert "Me" in working
    assert working["Me"]["default"] is True
    assert working["Me"]["links"] == [(s0, "koko"), (s1, "koko76")]


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
    dia.add_link_row(room, "koko")
    dia.add_link_row("PHH", "koko_phh")

    working, _deleted = dia.get_profile_changes()
    assert working["Me"]["links"] == [(room, "koko"), ("PHH", "koko_phh")]


@pytest.mark.qt
def test_the_data_sources_tab_edits_the_phh_hero_aliases(qtbot) -> None:
    from fpdb_3_legacy.Configuration import Config
    from fpdb_3_legacy.ModernSitePreferences import ModernSitePreferencesDialog

    cfg = Config(file="HUD_config.xml")
    cfg.set_data_source_hero_aliases("PHH", ["koko"])  # in memory only: never saved here
    dia = ModernSitePreferencesDialog(cfg)
    qtbot.addWidget(dia)

    tabs = [dia.tabs.tabText(i) for i in range(dia.tabs.count())]
    assert "Data Sources" in tabs
    assert dia.data_source_inputs["PHH"].toPlainText() == "koko"

    # One name per line: a PHH name is any string, a comma included, matched exactly.
    dia.data_source_inputs["PHH"].setPlainText("koko\n\nSmith, John\n koko76 \nkoko")
    assert dia.get_data_source_changes() == {"PHH": ["koko", "Smith, John", "koko76"]}


# --------------------------------------------------------------------------- #
# Sites tab: disabled rooms                                                    #
# --------------------------------------------------------------------------- #


def _card_order(dia) -> list[str]:
    layout = dia.sites_layout
    widgets = (layout.itemAt(i).widget() for i in range(layout.count()))
    return [w.site_name for w in widgets if w is not None]


@pytest.mark.qt
def test_a_disabled_room_can_be_listed_and_turned_on(qtbot) -> None:
    """#889: a room arrives off, and the tab listed only rooms that were on."""
    cfg, dia = _dialog(qtbot)
    room = "PokerStars.UK"
    assert not cfg.supported_sites[room].enabled

    assert room not in dia.visible_cards

    dia.show_disabled_cb.setChecked(True)
    assert room in dia.visible_cards
    card = dia.site_cards[room]
    assert not card.enable_toggle.isChecked()

    card.enable_toggle.setChecked(True)
    dia.show_disabled_cb.setChecked(False)
    # Turned on, it stays listed, and is saved as on.
    assert room in dia.visible_cards
    assert dia.get_changes()[room]["enabled"] is True


@pytest.mark.qt
def test_a_room_turned_off_stays_listed_while_disabled_rooms_are_shown(qtbot) -> None:
    _cfg, dia = _dialog(qtbot)
    dia.show_disabled_cb.setChecked(True)
    room = next(name for name in sorted(dia.enabled_sites))

    dia.site_cards[room].enable_toggle.setChecked(False)

    assert room in dia.visible_cards
    dia.show_disabled_cb.setChecked(False)
    assert room not in dia.visible_cards


@pytest.mark.qt
def test_cards_keep_alphabetical_order_when_hidden_ones_stay_in_the_layout(qtbot) -> None:
    _cfg, dia = _dialog(qtbot)
    # A search hides the enabled cards it does not match; they stay in the layout.
    dia.search_input.setText("pokerstars")
    hidden = set(dia.site_cards) - dia.visible_cards
    assert hidden
    # Showing disabled rooms then builds new cards among the hidden ones.
    dia.show_disabled_cb.setChecked(True)
    dia.search_input.setText("")

    order = _card_order(dia)
    assert len(order) > len(hidden)
    assert order == sorted(order)
