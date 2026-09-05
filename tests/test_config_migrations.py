"""Regressions for stale version-83 HUD files (issue #287)."""

from pathlib import Path
from unittest.mock import patch

import defusedxml.minidom
import pytest

from fpdb_3_legacy.config_migrations import reference_errors, upgrade_document, write_upgrade
from fpdb_3_legacy.Configuration import CONFIG_VERSION

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


@pytest.mark.parametrize("name", ["HUD_config.xml", "HUD_config.xml.example"])
def test_templates_have_current_version_and_resolve(name):
    template = defusedxml.minidom.parse(str(ROOT / name))
    assert int(template.getElementsByTagName("general")[0].getAttribute("version")) == CONFIG_VERSION
    assert reference_errors(template) == []


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
    xml = (ROOT / "HUD_config.xml.example").read_text()
    path.write_text(xml.replace('aux="ClassicHud, mucked"', 'aux="unknown"'))
    config = configuration.Config(file=str(path))
    assert config.wrongConfigVersion is False
    assert any("unknown" in error for error in config.config_reference_errors)
    path.write_text(xml.replace('version="84"', 'version="invalid"'))
    assert configuration.Config(file=str(path)).wrongConfigVersion is True


def test_upgrade_config_can_be_reloaded_and_does_not_repeat(tmp_path, monkeypatch):
    import fpdb_3_legacy.Configuration as configuration

    monkeypatch.setattr(configuration, "CONFIG_PATH", str(tmp_path))
    monkeypatch.setattr(configuration, "_find_example_config", lambda _: str(ROOT / "HUD_config.xml.example"))
    path = tmp_path / "HUD_config.xml"
    old = (ROOT / "HUD_config.xml.example").read_text().replace('version="84"', 'version="83"')
    old = old.replace('aux="ClassicHud, mucked"', 'aux="Classic_HUD, mucked"')
    path.write_text(old)
    config = configuration.Config(file=str(path))
    assert config.wrongConfigVersion
    assert config.config_reference_errors
    backup = config.upgrade_config()
    assert Path(backup).read_text() == old
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
    (tmp_path / "fpdb_3_legacy/Configuration.py").write_text("CONFIG_VERSION = 84")
    old = '<config><general version="84"/></config>'
    changed = '<config><general version="84"/><new/></config>'
    for name in ("HUD_config.xml", "HUD_config.xml.example"):
        (tmp_path / name).write_text(changed)
    with patch("tools.check_config_version.subprocess.check_output", return_value=old):
        with pytest.raises(ValueError, match="increment"):
            check("base", tmp_path)
        for name in ("HUD_config.xml", "HUD_config.xml.example"):
            (tmp_path / name).write_text(changed.replace('version="84"', 'version="85"'))
        with pytest.raises(ValueError, match="must equal"):
            check("base", tmp_path)
        (tmp_path / "fpdb_3_legacy/Configuration.py").write_text("CONFIG_VERSION = 85")
        check("base", tmp_path)


def test_adding_general_defaults_does_not_hide_missing_version(tmp_path, monkeypatch):
    import fpdb_3_legacy.Configuration as configuration

    monkeypatch.setattr(configuration, "CONFIG_PATH", str(tmp_path))
    path = tmp_path / "HUD_config.xml"
    xml = (ROOT / "HUD_config.xml.example").read_text()
    doc = parse(xml)
    general = doc.getElementsByTagName("general")[0]
    general.parentNode.removeChild(general)
    path.write_text(doc.toxml())
    config = configuration.Config(file=str(path))
    config.add_missing_elements(config.doc, str(ROOT / "HUD_config.xml.example"))
    reloaded = configuration.Config(file=str(path))
    assert reloaded.general["version"] == 0
    assert reloaded.wrongConfigVersion
