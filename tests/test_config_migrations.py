"""Regressions for stale version-83 HUD files (issue #287)."""

from pathlib import Path
from unittest.mock import patch

import defusedxml.minidom
import pytest

from fpdb_3_legacy.config_migrations import _preserve_96_to_97, reference_errors, upgrade_document, write_upgrade
from fpdb_3_legacy.Configuration import CONFIG_VERSION

PADDY_POWER = "PokerStars on Paddy Power"
ROOT = Path(__file__).resolve().parents[1]


def parse(body):
    return defusedxml.minidom.parseString(body)


def stale():
    return parse("""<FreePokerToolsConfig><general version="83"/>
      <supported_sites><site site_name="mine" screen_name="hero" HH_path="/my/hands">
      <fav max="6" fav_seat="4"/><layout_set ls="custom"/></site></supported_sites>
      <layout_sets><ls name="custom"/></layout_sets>
      <stat_sets><ss name="my_stats" rows="1"/></stat_sets>
      <supported_games><game game_name="holdem" aux="Classic_HUD, mucked">
      <game_stat_set game_type="all" stat_set="my_stats"/></game></supported_games>
      <aux_windows/><supported_databases><database db_name="mine"/></supported_databases>
      </FreePokerToolsConfig>""")


@pytest.mark.parametrize(
    "name",
    ["HUD_config.xml", "HUD_config.xml.example", "fpdb_3_legacy/HUD_config.xml.example"],
)
def test_templates_have_current_version_and_resolve(name):
    template = defusedxml.minidom.parse(str(ROOT / name))
    assert int(template.getElementsByTagName("general")[0].getAttribute("version")) == CONFIG_VERSION
    assert reference_errors(template) == []
    games = {node.getAttribute("game_name") for node in template.getElementsByTagName("game")}
    assert {"fusion", "aof_holdem"} <= games
    aux = {node.getAttribute("name") for node in template.getElementsByTagName("aw")}
    stat_sets = {node.getAttribute("name") for node in template.getElementsByTagName("ss")}
    assert "PLO4Hud" in aux
    assert "plo_pro_html" in stat_sets


def test_package_template_stays_synchronized_with_root_template():
    assert (ROOT / "fpdb_3_legacy/HUD_config.xml.example").read_bytes() == (
        ROOT / "HUD_config.xml.example"
    ).read_bytes()


def test_upgrade_preserves_personal_settings_and_repairs_alias():
    old = stale()
    original = old.toxml()
    template = defusedxml.minidom.parse(str(ROOT / "HUD_config.xml.example"))
    updated = upgrade_document(old, template, CONFIG_VERSION)
    assert old.toxml() == original
    assert reference_errors(updated) == []
    for tag in ("site", "ls", "ss", "database"):
        assert updated.getElementsByTagName(tag)[0].toxml() == old.getElementsByTagName(tag)[0].toxml()
    game = updated.getElementsByTagName("game")[0]
    assert game.getAttribute("aux") == "ClassicHud, mucked"
    assert game.getElementsByTagName("game_stat_set")[0].getAttribute("stat_set") == "my_stats"
    assert upgrade_document(updated, template, CONFIG_VERSION).toxml() == updated.toxml()


def test_reports_all_dangling_bindings_even_when_version_current():
    doc = parse("""<FreePokerToolsConfig><general version="84"/>
    <game game_name="holdem" aux="missing, another"><game_stat_set stat_set="bad"/></game>
    <site site_name="mine"><layout_set ls="absent"/></site>
    <hud_profile_rule profile="unknown"/></FreePokerToolsConfig>""")
    errors = reference_errors(doc)
    assert len(errors) == 5
    assert any("holdem" in e and "missing" in e for e in errors)
    assert any("mine" in e and "absent" in e for e in errors)


@pytest.mark.parametrize("version", ["0", "82", "999", "invalid"])
def test_unknown_version_is_not_stamped_current(version):
    doc = stale()
    doc.getElementsByTagName("general")[0].setAttribute("version", version)
    with pytest.raises(ValueError):
        upgrade_document(doc, defusedxml.minidom.parse(str(ROOT / "HUD_config.xml.example")), CONFIG_VERSION)
    assert doc.getElementsByTagName("general")[0].getAttribute("version") == version


def test_unresolved_custom_reference_aborts_upgrade():
    doc = stale()
    doc.getElementsByTagName("game_stat_set")[0].setAttribute("stat_set", "typo")
    with pytest.raises(ValueError, match="typo"):
        upgrade_document(doc, defusedxml.minidom.parse(str(ROOT / "HUD_config.xml.example")), CONFIG_VERSION)
    assert doc.getElementsByTagName("general")[0].getAttribute("version") == "83"


def test_unique_backups_preserve_original_bytes(tmp_path):
    path = tmp_path / "HUD_config.xml"
    original = b"<?xml version='1.0'?>\r\n<original/>\r\n"
    path.write_bytes(original)
    backup = write_upgrade(str(path), stale())
    assert Path(backup).read_bytes() == original
    second = write_upgrade(str(path), stale())
    assert second != backup
    assert Path(backup).read_bytes() == original


@pytest.mark.parametrize("operation", ["shutil.copy2", "os.replace"])
def test_failed_backup_or_replace_keeps_original(tmp_path, operation):
    path = tmp_path / "HUD_config.xml"
    path.write_bytes(b"original")
    with patch("fpdb_3_legacy.config_migrations." + operation, side_effect=OSError("denied")):
        with pytest.raises(OSError, match="denied"):
            write_upgrade(str(path), stale())
    assert path.read_bytes() == b"original"
    assert list(tmp_path.glob("*.tmp")) == []


def test_load_reports_current_config_errors_and_invalid_version(tmp_path, monkeypatch):
    import fpdb_3_legacy.Configuration as configuration

    monkeypatch.setattr(configuration, "CONFIG_PATH", str(tmp_path))
    path = tmp_path / "HUD_config.xml"
    xml = (ROOT / "HUD_config.xml.example").read_text(encoding="utf-8")
    path.write_text(xml.replace('aux="ClassicHud, mucked"', 'aux="unknown"'), encoding="utf-8")
    config = configuration.Config(file=str(path))
    assert config.wrongConfigVersion is False
    assert any("unknown" in error for error in config.config_reference_errors)
    path.write_text(xml.replace(f'version="{CONFIG_VERSION}"', 'version="invalid"', 1), encoding="utf-8")
    assert configuration.Config(file=str(path)).wrongConfigVersion is True


def test_upgrade_config_can_be_reloaded_and_does_not_repeat(tmp_path, monkeypatch):
    import fpdb_3_legacy.Configuration as configuration

    monkeypatch.setattr(configuration, "CONFIG_PATH", str(tmp_path))
    monkeypatch.setattr(configuration, "_find_example_config", lambda _: str(ROOT / "HUD_config.xml.example"))
    path = tmp_path / "HUD_config.xml"
    old = (
        (ROOT / "HUD_config.xml.example")
        .read_text(encoding="utf-8")
        .replace(f'version="{CONFIG_VERSION}"', 'version="83"', 1)
    )
    old = old.replace('aux="ClassicHud, mucked"', 'aux="Classic_HUD, mucked"')
    path.write_text(old, encoding="utf-8")
    config = configuration.Config(file=str(path))
    assert config.wrongConfigVersion
    assert config.config_reference_errors
    backup = config.upgrade_config()
    assert Path(backup).read_text(encoding="utf-8") == old
    reloaded = configuration.Config(file=str(path))
    assert not reloaded.wrongConfigVersion
    assert not reloaded.config_reference_errors
    assert reloaded.supported_games["holdem"].aux == "ClassicHud, mucked"


def test_existing_aux_alias_definition_is_preserved():
    doc = stale()
    aux = doc.createElement("aw")
    aux.setAttribute("name", "Classic_HUD")
    doc.getElementsByTagName("aux_windows")[0].appendChild(aux)
    updated = upgrade_document(doc, defusedxml.minidom.parse(str(ROOT / "HUD_config.xml.example")), CONFIG_VERSION)
    assert updated.getElementsByTagName("game")[0].getAttribute("aux") == "Classic_HUD, mucked"


def test_ci_rejects_unversioned_changes_and_version_mismatch(tmp_path):
    from tools.check_config_version import check

    (tmp_path / "fpdb_3_legacy").mkdir()
    (tmp_path / "fpdb_3_legacy/Configuration.py").write_text("CONFIG_VERSION = 84", encoding="utf-8")
    old = '<config><general version="84"/></config>'
    base_dir = tmp_path / "base"
    (base_dir / "fpdb_3_legacy").mkdir(parents=True)
    changed = '<config><general version="84"/><new/></config>'
    for name in ("HUD_config.xml", "HUD_config.xml.example", "fpdb_3_legacy/HUD_config.xml.example"):
        if "/" in name:
            (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(changed, encoding="utf-8")
        (base_dir / name).write_text(old, encoding="utf-8")
    with pytest.raises(ValueError, match="increment"):
        check(base_dir, tmp_path)
    for name in ("HUD_config.xml", "HUD_config.xml.example", "fpdb_3_legacy/HUD_config.xml.example"):
        (tmp_path / name).write_text(changed.replace('version="84"', 'version="85"'), encoding="utf-8")
    with pytest.raises(ValueError, match="must equal"):
        check(base_dir, tmp_path)
    (tmp_path / "fpdb_3_legacy/Configuration.py").write_text("CONFIG_VERSION = 85", encoding="utf-8")
    check(base_dir, tmp_path)


def test_a_sites_folders_change_without_a_new_version(tmp_path):
    from tools.check_config_version import check

    (tmp_path / "fpdb_3_legacy").mkdir()
    (tmp_path / "fpdb_3_legacy/Configuration.py").write_text("CONFIG_VERSION = 84", encoding="utf-8")
    base_dir = tmp_path / "base"
    (base_dir / "fpdb_3_legacy").mkdir(parents=True)
    site = '<config><general version="84"/><site site_name="S" HH_path="{}" TS_path="{}" site_path="{}" {}/></config>'
    names = ("HUD_config.xml", "HUD_config.xml.example", "fpdb_3_legacy/HUD_config.xml.example")
    for name in names:
        (base_dir / name).write_text(site.format("C:/a", "C:/b", "C:/c", ""), encoding="utf-8")
        (tmp_path / name).write_text(site.format("C:/x", "C:/y", "C:/z", ""), encoding="utf-8")

    # An upgrade never carries a site's folders to an existing configuration.
    check(base_dir, tmp_path)

    # Any other change to the site still needs one.
    (tmp_path / "HUD_config.xml").write_text(site.format("C:/x", "C:/y", "C:/z", 'enabled="True"'), encoding="utf-8")
    with pytest.raises(ValueError, match="increment"):
        check(base_dir, tmp_path)


def test_adding_general_defaults_does_not_hide_missing_version(tmp_path, monkeypatch):
    import fpdb_3_legacy.Configuration as configuration

    monkeypatch.setattr(configuration, "CONFIG_PATH", str(tmp_path))
    path = tmp_path / "HUD_config.xml"
    xml = (ROOT / "HUD_config.xml.example").read_text(encoding="utf-8")
    doc = parse(xml)
    general = doc.getElementsByTagName("general")[0]
    general.parentNode.removeChild(general)
    path.write_text(doc.toxml(), encoding="utf-8")
    config = configuration.Config(file=str(path))
    config.add_missing_elements(config.doc, str(ROOT / "HUD_config.xml.example"))
    reloaded = configuration.Config(file=str(path))
    assert reloaded.general["version"] == 0
    assert reloaded.wrongConfigVersion


def _v88(hhcs: str):
    return parse(f"""<FreePokerToolsConfig><general version="88"/>
      <hhcs>{hhcs}</hhcs></FreePokerToolsConfig>""")


def _importers(doc) -> dict:
    return {node.getAttribute("site"): node.getAttribute("summaryImporter") for node in doc.getElementsByTagName("hhc")}


def test_v89_gives_unibet_its_summary_importer():
    # The development HUD_config.xml declared Unibet without it (#725), so its
    # tournament summaries were never recognised.
    template = defusedxml.minidom.parse(str(ROOT / "HUD_config.xml.example"))
    old = _v88(
        '<hhc site="Unibet" converter="UnibetToFpdb"/>'
        '<hhc site="Winamax" converter="WinamaxToFpdb" summaryImporter="MySummary"/>'
        '<hhc site="mine" converter="UnibetToFpdb"/>'
    )

    updated = upgrade_document(old, template, CONFIG_VERSION)

    assert _importers(updated) == {
        "Unibet": "UnibetSummary",
        # An importer the user named is kept; a room the template lacks is left alone.
        "Winamax": "MySummary",
        "mine": "",
        # v91 adds the 2025+ Betclic room (#730) with the template's converter.
        "Betclic": "",
        # v94 adds CoinPoker back, import-only (#732).
        "CoinPoker": "",
        # v95 adds BetRivers, import-only (#731).
        "BetRivers": "",
        # v99 adds the PokerStars on Betfair skin (#733).
        "PokerStars on Betfair": "PokerStarsSummary",
    }
    assert upgrade_document(updated, template, CONFIG_VERSION).toxml() == updated.toxml()


def test_v89_leaves_a_room_on_another_converter_alone():
    template = defusedxml.minidom.parse(str(ROOT / "HUD_config.xml.example"))
    old = _v88('<hhc site="Unibet" converter="SomethingElse"/>')

    updated = upgrade_document(old, template, CONFIG_VERSION)

    assert _importers(updated) == {
        "Unibet": "",
        "Betclic": "",
        "CoinPoker": "",
        "BetRivers": "",
        "PokerStars on Betfair": "PokerStarsSummary",
    }


def test_v90_adds_the_current_unibet_room():
    # The converter was declared but no <site> (#729), so the room could be
    # neither enabled nor given a folder.
    template = defusedxml.minidom.parse(str(ROOT / "HUD_config.xml.example"))
    old = parse("""<FreePokerToolsConfig><general version="89"/>
      <supported_sites><site site_name="mine"><layout_set ls="custom"/></site></supported_sites>
      <layout_sets><ls name="custom"/></layout_sets>
      <hhcs><hhc site="Unibet" converter="UnibetToFpdb" summaryImporter="UnibetSummary"/></hhcs>
      </FreePokerToolsConfig>""")

    updated = upgrade_document(old, template, CONFIG_VERSION)

    sites = {node.getAttribute("site_name"): node for node in updated.getElementsByTagName("site")}
    # v91: Betclic (#730), v94: CoinPoker (#732), v95: BetRivers (#731), v98: Paddy Power (#888),
    # v99: PokerStars on Betfair (#733)
    assert set(sites) == {
        "mine",
        "Unibet",
        "Betclic",
        "CoinPoker",
        "BetRivers",
        "PokerStars on Paddy Power",
        "PokerStars on Betfair",
    }
    assert sites["Unibet"].getAttribute("network") == "Unibet"
    assert sites["Unibet"].getAttribute("enabled") == "False"
    assert "Unibet_default" in {node.getAttribute("name") for node in updated.getElementsByTagName("ls")}
    # The converter entry the configuration had is kept, not duplicated.
    assert len([n for n in updated.getElementsByTagName("hhc") if n.getAttribute("site") == "Unibet"]) == 1
    assert reference_errors(updated) == []
    assert upgrade_document(updated, template, CONFIG_VERSION).toxml() == updated.toxml()


def test_v91_adds_the_betclic_2025_room():
    # The 2025+ in-house Betclic client is a new room (#730), separate from the
    # iPoker skin "Betclic Poker": every configuration lacks it, so the <site>,
    # its <hhc> entry and the layout set it references come from the template.
    template = defusedxml.minidom.parse(str(ROOT / "HUD_config.xml.example"))
    old = parse("""<FreePokerToolsConfig><general version="90"/>
      <supported_sites><site site_name="mine"><layout_set ls="custom"/></site></supported_sites>
      <layout_sets><ls name="custom"/><ls name="default"/></layout_sets>
      <hhcs><hhc site="Betclic Poker" converter="iPokerToFpdb" summaryImporter="iPokerSummary"/></hhcs>
      </FreePokerToolsConfig>""")

    updated = upgrade_document(old, template, CONFIG_VERSION)

    sites = {node.getAttribute("site_name"): node for node in updated.getElementsByTagName("site")}
    # v94 (#732), v95 (#731), v98 (#888), v99 (#733)
    assert set(sites) == {
        "mine",
        "Betclic",
        "CoinPoker",
        "BetRivers",
        "PokerStars on Paddy Power",
        "PokerStars on Betfair",
    }
    assert sites["Betclic"].getAttribute("network") == "Betclic"
    assert sites["Betclic"].getAttribute("enabled") == "False"
    hhcs = {node.getAttribute("site"): node.getAttribute("converter") for node in updated.getElementsByTagName("hhc")}
    assert hhcs == {
        "Betclic Poker": "iPokerToFpdb",
        "Betclic": "BetclicToFpdb",
        "CoinPoker": "CoinPokerToFpdb",
        "BetRivers": "BetRiversToFpdb",
        "PokerStars on Betfair": "PokerStarsToFpdb",
    }
    assert not reference_errors(updated)
    assert upgrade_document(updated, template, CONFIG_VERSION).toxml() == updated.toxml()


def test_v94_adds_coinpoker_back_as_an_import_only_room():
    # CoinPoker's entries were dropped when the room was switched off; its text
    # export is importable again (#732), with no HUD.
    template = defusedxml.minidom.parse(str(ROOT / "HUD_config.xml.example"))
    old = parse("""<FreePokerToolsConfig><general version="93"/>
      <supported_sites><site site_name="mine"><layout_set ls="custom"/></site></supported_sites>
      <layout_sets><ls name="custom"/></layout_sets>
      <hhcs><hhc site="mine" converter="PokerStarsToFpdb"/></hhcs>
      </FreePokerToolsConfig>""")

    updated = upgrade_document(old, template, CONFIG_VERSION)

    sites = {node.getAttribute("site_name"): node for node in updated.getElementsByTagName("site")}
    # v95 adds BetRivers (#731), v98 PokerStars on Paddy Power (#888), v99 PokerStars on Betfair (#733)
    assert set(sites) == {"mine", "CoinPoker", "BetRivers", "PokerStars on Paddy Power", "PokerStars on Betfair"}
    assert sites["CoinPoker"].getAttribute("enabled") == "False"
    assert sites["CoinPoker"].getAttribute("aux_enabled") == "False"
    hhcs = {node.getAttribute("site"): node.getAttribute("converter") for node in updated.getElementsByTagName("hhc")}
    assert hhcs == {
        "mine": "PokerStarsToFpdb",
        "CoinPoker": "CoinPokerToFpdb",
        "BetRivers": "BetRiversToFpdb",
        "PokerStars on Betfair": "PokerStarsToFpdb",
    }
    assert "default" in {node.getAttribute("name") for node in updated.getElementsByTagName("ls")}
    assert not reference_errors(updated)
    assert upgrade_document(updated, template, CONFIG_VERSION).toxml() == updated.toxml()


def test_v94_keeps_a_coinpoker_entry_the_configuration_still_has():
    template = defusedxml.minidom.parse(str(ROOT / "HUD_config.xml.example"))
    old = parse("""<FreePokerToolsConfig><general version="93"/>
      <supported_sites><site site_name="CoinPoker" screen_name="Hero" HH_path="/my/hands">
      <layout_set ls="custom"/></site></supported_sites>
      <layout_sets><ls name="custom"/></layout_sets>
      <hhcs/>
      </FreePokerToolsConfig>""")

    updated = upgrade_document(old, template, CONFIG_VERSION)

    sites = {n.getAttribute("site_name"): n for n in updated.getElementsByTagName("site")}
    assert sites["CoinPoker"].getAttribute("HH_path") == "/my/hands"
    assert [n.getAttribute("site") for n in updated.getElementsByTagName("hhc")] == [
        "CoinPoker",
        "BetRivers",
        "PokerStars on Betfair",
    ]


def test_v95_adds_betrivers_as_an_import_only_room():
    # BetRivers does not permit third-party HUDs (#731): its files are imported
    # after the session, so the room arrives off and without a HUD.
    template = defusedxml.minidom.parse(str(ROOT / "HUD_config.xml.example"))
    old = parse("""<FreePokerToolsConfig><general version="94"/>
      <supported_sites><site site_name="mine"><layout_set ls="custom"/></site></supported_sites>
      <layout_sets><ls name="custom"/></layout_sets>
      <hhcs><hhc site="mine" converter="PokerStarsToFpdb"/></hhcs>
      </FreePokerToolsConfig>""")

    updated = upgrade_document(old, template, CONFIG_VERSION)

    sites = {node.getAttribute("site_name"): node for node in updated.getElementsByTagName("site")}
    assert set(sites) == {"mine", "BetRivers", "PokerStars on Paddy Power", "PokerStars on Betfair"}  # v98, v99
    assert sites["BetRivers"].getAttribute("enabled") == "False"
    assert sites["BetRivers"].getAttribute("aux_enabled") == "False"
    hhcs = {n.getAttribute("site"): n.getAttribute("converter") for n in updated.getElementsByTagName("hhc")}
    assert hhcs == {
        "mine": "PokerStarsToFpdb",
        "BetRivers": "BetRiversToFpdb",
        "PokerStars on Betfair": "PokerStarsToFpdb",
    }
    assert not reference_errors(updated)
    assert upgrade_document(updated, template, CONFIG_VERSION).toxml() == updated.toxml()


def test_v99_adds_the_pokerstars_on_betfair_skin():
    # A new PokerStars skin (#733): its own site, off, with Betfair's client
    # folders, and an <hhc> on the PokerStars converters.
    template = defusedxml.minidom.parse(str(ROOT / "HUD_config.xml.example"))
    old = parse("""<FreePokerToolsConfig><general version="98"/>
      <supported_sites><site site_name="PokerStars"><layout_set ls="ps_default"/></site></supported_sites>
      <layout_sets><ls name="ps_default"/></layout_sets>
      <hhcs><hhc site="PokerStars" converter="PokerStarsToFpdb" summaryImporter="PokerStarsSummary"/></hhcs>
      </FreePokerToolsConfig>""")

    updated = upgrade_document(old, template, CONFIG_VERSION)

    sites = {node.getAttribute("site_name"): node for node in updated.getElementsByTagName("site")}
    assert set(sites) == {"PokerStars", "PokerStars on Betfair"}
    betfair = sites["PokerStars on Betfair"]
    assert betfair.getAttribute("enabled") == "False"
    assert betfair.getAttribute("network") == "PokerStars"
    assert "Betfair.UK/HandHistory" in betfair.getAttribute("HH_path")
    assert "Betfair.UK/TournSummary" in betfair.getAttribute("TS_path")
    hhcs = {n.getAttribute("site"): n.getAttribute("summaryImporter") for n in updated.getElementsByTagName("hhc")}
    assert hhcs == {"PokerStars": "PokerStarsSummary", "PokerStars on Betfair": "PokerStarsSummary"}
    # Before PokerStars' own: IdentifySite keeps the last entry of a converter,
    # and an Excel summary is filed under it as it is.
    assert [n.getAttribute("site") for n in updated.getElementsByTagName("hhc")] == [
        "PokerStars on Betfair",
        "PokerStars",
    ]
    assert not reference_errors(updated)
    assert upgrade_document(updated, template, CONFIG_VERSION).toxml() == updated.toxml()


def test_v96_gives_ggpoker_its_summary_importer():
    # GG declared no summary importer, so its tournament summaries were never
    # recognised (#868). One the user named is kept.
    template = defusedxml.minidom.parse(str(ROOT / "HUD_config.xml.example"))
    old = parse("""<FreePokerToolsConfig><general version="95"/>
      <hhcs><hhc site="GGPoker" converter="GGPokerToFpdb"/>
      <hhc site="Winamax" converter="WinamaxToFpdb" summaryImporter="MySummary"/></hhcs>
      </FreePokerToolsConfig>""")

    updated = upgrade_document(old, template, CONFIG_VERSION)

    assert _importers(updated) == {
        "GGPoker": "GGPokerSummary",
        "Winamax": "MySummary",
        # v99 adds the PokerStars on Betfair skin (#733).
        "PokerStars on Betfair": "PokerStarsSummary",
    }
    assert upgrade_document(updated, template, CONFIG_VERSION).toxml() == updated.toxml()


def test_v97_leaves_a_configuration_as_it_was():
    # v97 only adds the legacy PokerStars.UK room to the shipped HUD_config.xml
    # (#889); an existing configuration gains nothing from it. Upgraded to the
    # current version, it gains only what later versions add: v98's PokerStars
    # on Paddy Power (#888) and v99's PokerStars on Betfair (#733).
    template = defusedxml.minidom.parse(str(ROOT / "HUD_config.xml.example"))
    body = """<supported_sites><site site_name="PokerStars" screen_name="alice"/></supported_sites>
      <layout_sets/>
      <hhcs><hhc site="PokerStars" converter="PokerStarsToFpdb" summaryImporter="PokerStarsSummary"/></hhcs>
      </FreePokerToolsConfig>"""
    old = parse('<FreePokerToolsConfig><general version="96"/>' + body)
    untouched = old.toxml()

    _preserve_96_to_97(old, template)

    assert old.toxml() == untouched
    updated = upgrade_document(old, template, CONFIG_VERSION)
    sites = [n.getAttribute("site_name") for n in updated.getElementsByTagName("site")]
    assert sites == ["PokerStars", "PokerStars on Paddy Power", "PokerStars on Betfair"]
    assert [n.getAttribute("site") for n in updated.getElementsByTagName("hhc")] == [
        "PokerStars on Betfair",
        "PokerStars",
    ]
    assert not reference_errors(updated)


def test_v98_adds_paddy_power_on_pokerstars_as_a_room_of_its_own():
    # Paddy Power Poker moved to PokerStars software on 28 October 2026 (#888).
    # The new client gets its own room, off, on PokerStars' network and layouts,
    # with no folder (none is documented) and no <hhc>: its files go through the
    # PokerStars entry already there. The iPoker room is left exactly as it was.
    template = defusedxml.minidom.parse(str(ROOT / "HUD_config.xml.example"))
    old = parse("""<FreePokerToolsConfig><general version="97"/>
      <supported_sites>
      <site site_name="Paddy Power Poker" HH_path="/old/ipoker" network="iPoker"><layout_set ls="custom"/></site>
      </supported_sites>
      <layout_sets><ls name="custom"/></layout_sets>
      <hhcs><hhc site="PokerStars.COM" converter="PokerStarsToFpdb" summaryImporter="PokerStarsSummary"/>
      <hhc site="Paddy Power Poker" converter="iPokerToFpdb" summaryImporter="iPokerSummary"/></hhcs>
      </FreePokerToolsConfig>""")

    updated = upgrade_document(old, template, CONFIG_VERSION)

    sites = {node.getAttribute("site_name"): node for node in updated.getElementsByTagName("site")}
    assert set(sites) == {"Paddy Power Poker", "PokerStars on Paddy Power", "PokerStars on Betfair"}  # v99 (#733)
    new = sites["PokerStars on Paddy Power"]
    assert new.getAttribute("enabled") == "False"
    assert new.getAttribute("network") == "PokerStars"
    assert new.getAttribute("HH_path") == new.getAttribute("TS_path") == ""
    assert sites["Paddy Power Poker"].getAttribute("network") == "iPoker"
    assert sites["Paddy Power Poker"].getAttribute("HH_path") == "/old/ipoker"
    hhcs = {n.getAttribute("site"): n.getAttribute("converter") for n in updated.getElementsByTagName("hhc")}
    assert hhcs == {
        "PokerStars.COM": "PokerStarsToFpdb",
        "Paddy Power Poker": "iPokerToFpdb",
        "PokerStars on Betfair": "PokerStarsToFpdb",
    }
    assert "ps_default" in {node.getAttribute("name") for node in updated.getElementsByTagName("ls")}
    assert not reference_errors(updated)
    assert upgrade_document(updated, template, CONFIG_VERSION).toxml() == updated.toxml()


def test_v98_keeps_a_paddy_power_on_pokerstars_entry_the_user_wrote():
    template = defusedxml.minidom.parse(str(ROOT / "HUD_config.xml.example"))
    old = parse("""<FreePokerToolsConfig><general version="97"/>
      <supported_sites><site site_name="PokerStars on Paddy Power" enabled="True" HH_path="/my/pp">
      <layout_set ls="custom"/></site></supported_sites>
      <layout_sets><ls name="custom"/></layout_sets>
      <hhcs/>
      </FreePokerToolsConfig>""")

    updated = upgrade_document(old, template, CONFIG_VERSION)

    (site,) = [n for n in updated.getElementsByTagName("site") if n.getAttribute("site_name") == PADDY_POWER]
    assert site.getAttribute("HH_path") == "/my/pp"
    assert site.getAttribute("enabled") == "True"
