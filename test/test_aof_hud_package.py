"""Distribution and migration contracts for the AoF Omaha HUD package."""

from __future__ import annotations

import shutil
import xml.dom.minidom
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

import fpdb_3_legacy.Configuration as config_module
from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.hud_package import merge_package_game_bindings

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "aof_omaha.fpdbhud"
SHIPPED_CONFIG = ROOT / "HUD_config.xml"
EXAMPLE_CONFIG = ROOT / "HUD_config.xml.example"
PROFILE_NAME = "aof_default"
GAME_NAME = "aof_omaha"


def _normalized_element(element: ET.Element) -> tuple:
    return (
        element.tag,
        tuple(sorted(element.attrib.items())),
        tuple(_normalized_element(child) for child in element),
    )


def _named_element(root: ET.Element, xpath: str, attribute: str, name: str) -> ET.Element:
    element = next((node for node in root.findall(xpath) if node.get(attribute) == name), None)
    assert element is not None, f"{name!r} is missing from {xpath!r}"
    return element


def _remove_named_nodes(doc, tag_name: str, attribute: str, value: str) -> None:
    for node in list(doc.getElementsByTagName(tag_name)):
        if node.getAttribute(attribute) == value:
            node.parentNode.removeChild(node)


def _direct_named_nodes(doc, tag_name: str, attribute: str, value: str) -> list:
    return [node for node in doc.getElementsByTagName(tag_name) if node.getAttribute(attribute) == value]


def test_aof_hud_package_matches_the_import_contract_and_shipped_config() -> None:
    package_root = ET.parse(PACKAGE).getroot()
    config_root = ET.parse(SHIPPED_CONFIG).getroot()

    assert package_root.tag == "fpdb_hud_package"
    assert package_root.get("version") == "1.1"

    package_profile = _named_element(package_root, "./ss", "name", PROFILE_NAME)
    package_game = _named_element(package_root, "./game", "game_name", GAME_NAME)
    assert package_game.find("./game_stat_set[@game_type='all']").get("stat_set") == PROFILE_NAME

    config_profile = _named_element(config_root, "./stat_sets/ss", "name", PROFILE_NAME)
    config_game = _named_element(config_root, "./supported_games/game", "game_name", GAME_NAME)
    assert _normalized_element(package_profile) == _normalized_element(config_profile)
    assert _normalized_element(package_game) == _normalized_element(config_game)


def test_package_binding_follows_a_profile_renamed_during_import() -> None:
    config = xml.dom.minidom.parseString(
        """<FreePokerToolsConfig>
          <supported_games>
            <game game_name="aof_omaha">
              <game_stat_set game_type="all" stat_set="old_profile"/>
            </game>
          </supported_games>
        </FreePokerToolsConfig>""",
    )
    package = xml.dom.minidom.parse(str(PACKAGE))

    changed = merge_package_game_bindings(
        config,
        package.documentElement,
        profile_names={PROFILE_NAME: "aof_imported"},
        overwrite=True,
    )

    assert changed is True
    (game,) = _direct_named_nodes(config, "game", "game_name", GAME_NAME)
    (mapping,) = game.getElementsByTagName("game_stat_set")
    assert mapping.getAttribute("stat_set") == "aof_imported"
    assert (
        merge_package_game_bindings(
            config,
            package.documentElement,
            profile_names={PROFILE_NAME: "aof_imported"},
            overwrite=True,
        )
        is False
    )


def test_existing_config_migration_is_idempotent_and_preserves_custom_profiles() -> None:
    target = xml.dom.minidom.parseString(
        """<FreePokerToolsConfig>
          <supported_games/>
          <stat_sets>
            <ss name="aof_default" rows="9" cols="9">
              <stat _rowcol="(1,1)" _stat_name="playershort" hudprefix="CUSTOM"/>
            </ss>
          </stat_sets>
        </FreePokerToolsConfig>""",
    )
    source = xml.dom.minidom.parse(str(PACKAGE))
    config = object.__new__(Config)

    assert config._migrate_aof_omaha_hud(target, source) is True
    assert config._migrate_aof_omaha_hud(target, source) is False

    (profile,) = _direct_named_nodes(target, "ss", "name", PROFILE_NAME)
    assert profile.getAttribute("rows") == "9"
    assert profile.getElementsByTagName("stat")[0].getAttribute("hudprefix") == "CUSTOM"
    (game,) = _direct_named_nodes(target, "game", "game_name", GAME_NAME)
    assert game.getElementsByTagName("game_stat_set")[0].getAttribute("stat_set") == PROFILE_NAME


def test_existing_aof_binding_is_not_overwritten_by_the_automatic_migration() -> None:
    target = xml.dom.minidom.parseString(
        """<FreePokerToolsConfig>
          <supported_games>
            <game game_name="aof_omaha">
              <game_stat_set game_type="all" stat_set="my_aof_profile"/>
            </game>
          </supported_games>
          <stat_sets>
            <ss name="my_aof_profile" rows="1" cols="1"/>
          </stat_sets>
        </FreePokerToolsConfig>""",
    )
    source = xml.dom.minidom.parse(str(PACKAGE))

    assert object.__new__(Config)._migrate_aof_omaha_hud(target, source) is True
    (game,) = _direct_named_nodes(target, "game", "game_name", GAME_NAME)
    assert game.getElementsByTagName("game_stat_set")[0].getAttribute("stat_set") == "my_aof_profile"
    assert len(_direct_named_nodes(target, "ss", "name", PROFILE_NAME)) == 1


def test_startup_migrates_an_existing_user_file_once(tmp_path: Path, monkeypatch) -> None:
    config_dir = tmp_path / ".fpdb"
    config_dir.mkdir()
    config_path = config_dir / "HUD_config.xml"
    doc = xml.dom.minidom.parse(str(EXAMPLE_CONFIG))
    _remove_named_nodes(doc, "game", "game_name", GAME_NAME)
    _remove_named_nodes(doc, "ss", "name", PROFILE_NAME)
    config_path.write_text(doc.toxml(), encoding="utf-8")
    monkeypatch.setattr(config_module, "CONFIG_PATH", str(config_dir))

    migrated = Config()
    params = migrated.get_supported_games_parameters(GAME_NAME, "ring")
    assert params is not None
    assert params["game_stat_set"].name == PROFILE_NAME
    assert config_path.with_suffix(".xml.backup").exists()

    once = config_path.read_bytes()
    backup_once = config_path.with_suffix(".xml.backup").read_bytes()
    Config()
    assert config_path.read_bytes() == once
    assert config_path.with_suffix(".xml.backup").read_bytes() == backup_once


@pytest.mark.qt
def test_preferences_imports_the_profile_and_its_game_binding(tmp_path: Path, monkeypatch) -> None:
    from PySide6.QtWidgets import QApplication, QComboBox, QFileDialog, QMessageBox

    from fpdb_3_legacy.ModernHudPreferences import ModernHudPreferences

    QApplication.instance() or QApplication([])
    config_path = tmp_path / "HUD_config.xml"
    shutil.copy(EXAMPLE_CONFIG, config_path)
    config = Config(file=str(config_path))

    _remove_named_nodes(config.doc, "game", "game_name", GAME_NAME)
    _remove_named_nodes(config.doc, "ss", "name", PROFILE_NAME)
    config.supported_games.pop(GAME_NAME, None)
    config.stat_sets.pop(PROFILE_NAME, None)

    errors = []
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        staticmethod(lambda *args, **kwargs: (str(PACKAGE), "FPDB HUD Files (*.fpdbhud)")),
    )
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *args, **kwargs: None))
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *args, **kwargs: errors.append(args)))

    dialog = ModernHudPreferences.__new__(ModernHudPreferences)
    dialog.config = config
    dialog.hud_profiles = dict(config.stat_sets)
    dialog.profile_combo = QComboBox()
    dialog.load_profiles = lambda: None
    dialog.load_popup_windows = lambda: None
    dialog.on_profile_selected = lambda _index: None
    dialog.reload_parent_config = lambda: None

    dialog.import_profile()

    assert errors == []
    saved = ET.parse(config_path).getroot()
    _named_element(saved, "./stat_sets/ss", "name", PROFILE_NAME)
    game = _named_element(saved, "./supported_games/game", "game_name", GAME_NAME)
    assert game.find("./game_stat_set[@game_type='all']").get("stat_set") == PROFILE_NAME
