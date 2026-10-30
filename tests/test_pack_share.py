"""Share this HUD / pack: a folder ready to submit to the pack gallery (#449).

What is written is held to the packs repository's own terms: with the entry
added to an ``index.json`` beside it, the folder is a gallery that
``validate_repository`` accepts, and a stat pack's archive is the one the
repository's ``scripts/build.py`` builds from its sources.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any

import defusedxml.minidom
import pytest

from fpdb_3_legacy import hud_situation, stat_packs
from fpdb_3_legacy.hud_package import install_missing_hud_package
from fpdb_3_legacy.pack_gallery import GalleryError, validate_repository
from fpdb_3_legacy.pack_share import (
    ENTRY_NAME,
    _stock_popup_nodes,
    _submenus,
    hud_package,
    profile_names,
    share_hud,
    share_stat_pack,
)
from tests.helpers.pack_gallery import LICENSE, ROOT, stat_pack, write_index

HUD = {"pack_id": "me.mine", "name": "Mine", "version": "1.0.0", "author": "me", "license": LICENSE}


def config_with(extra: str = "", stat: str = "vpip") -> Any:
    return defusedxml.minidom.parseString(
        "<FreePokerToolsConfig><stat_sets>"
        f'<ss name="mine" rows="1" cols="1"><stat _rowcol="(1,1)" _stat_name="{stat}" popup="my_popup"/></ss>'
        '<ss name="other" rows="1" cols="1"><stat _rowcol="(1,1)" _stat_name="pfr" popup="not_mine"/></ss>'
        '</stat_sets><popup_windows><pu pu_name="my_popup"><pu_stat pu_stat_name="pfr" pu_stat_submenu="sub"/></pu>'
        '<pu pu_name="sub"><pu_stat pu_stat_name="vpip"/></pu><pu pu_name="not_mine"><pu_stat pu_stat_name="n"/></pu>'
        '<pu pu_name="default"><pu_stat pu_stat_name="n"/></pu></popup_windows>'
        '<supported_games><game game_name="holdem"><game_stat_set game_type="ring" stat_set="mine"/></game>'
        f"</supported_games>{extra}</FreePokerToolsConfig>"
    )


def without_default(config: Any) -> Any:
    """*config* without the base ``default`` popup, so a test can give its own."""
    first = next(node for node in config.getElementsByTagName("pu") if node.getAttribute("pu_name") == "default")
    first.parentNode.removeChild(first)
    return config


def as_gallery(folder: Path) -> list[str]:
    """What the packs repository's check says of *folder* once its entry is in an index."""
    write_index(folder, [json.loads((folder / ENTRY_NAME).read_text(encoding="utf-8"))])
    return validate_repository(folder)


def test_a_shared_hud_is_a_gallery_entry_the_packs_repository_accepts(tmp_path) -> None:
    config = config_with(
        '<hud_panel_rules enabled="true" source="builtin" fallback="core" profile="Mine"/>'
        '<hud_panel_rules enabled="true" source="builtin" fallback="core" profile="other"/>'
    )

    folder = share_hud(config, "mine", tmp_path, **HUD, description="My HUD.")

    assert folder == tmp_path / "me.mine"
    assert sorted(path.relative_to(folder).as_posix() for path in folder.rglob("*")) == [
        "hud",
        "hud/me.mine.fpdbhud",
        ENTRY_NAME,
    ]
    entry = json.loads((folder / ENTRY_NAME).read_text(encoding="utf-8"))
    assert entry["file"] == "hud/me.mine.fpdbhud" and entry["stats"] == ["vpip"]
    assert entry["description"] == "My HUD."
    package = defusedxml.minidom.parse(str(folder / "hud" / "me.mine.fpdbhud")).documentElement
    # The profile, the popups it opens (and those they open), and its own panel rules; nothing of the sharer's tables.
    assert [node.getAttribute("name") for node in package.getElementsByTagName("ss")] == ["mine"]
    assert sorted(node.getAttribute("pu_name") for node in package.getElementsByTagName("pu")) == ["my_popup", "sub"]
    assert [node.getAttribute("profile") for node in package.getElementsByTagName("hud_panel_rules")] == ["Mine"]
    assert not package.getElementsByTagName("game")
    assert as_gallery(folder) == []


def test_a_shared_reference_hud_installs_as_the_original_does() -> None:
    def installed(package: Any) -> Any:
        config = config_with()
        install_missing_hud_package(config, package, bind_games=False)
        return {
            tag: sorted(node.getAttribute(attribute) for node in config.getElementsByTagName(tag))
            for tag, attribute in (("ss", "name"), ("pu", "pu_name"), ("hud_panel_rules", "profile"))
        }

    original = defusedxml.minidom.parse(str(ROOT / "hud-packages" / "nlhe_6max_dynamic.fpdbhud")).documentElement
    config = config_with()
    install_missing_hud_package(config, original, bind_games=False)

    shared = defusedxml.minidom.parseString(hud_package(config, "nlhe_6max_dynamic")).documentElement

    assert installed(shared) == installed(original)


def test_a_hud_the_gallery_would_refuse_is_not_written(tmp_path) -> None:
    with pytest.raises(GalleryError) as refused:
        share_hud(config_with(stat="no_such_stat"), "mine", tmp_path, **HUD)

    assert "unknown stat(s): no_such_stat" in refused.value.messages
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        ({"pack_id": "Not An Id"}, "id"),
        ({"license": ""}, "license is missing"),
        ({"version": "one"}, "version 'one' must be written like '1.2' or '1.2.3'"),
    ],
)
def test_an_entry_the_gallery_would_refuse_is_not_written(tmp_path, change, problem) -> None:
    with pytest.raises(GalleryError) as refused:
        share_hud(config_with(), "mine", tmp_path, **{**HUD, **change})

    assert any(message.startswith(problem) for message in refused.value.messages)
    assert list(tmp_path.iterdir()) == []


def test_sharing_never_writes_over_a_folder_already_there(tmp_path) -> None:
    (tmp_path / "me.mine").mkdir()
    (tmp_path / "me.mine" / "notes.txt").write_text("mine", encoding="utf-8")

    with pytest.raises(GalleryError, match="already exists"):
        share_hud(config_with(), "mine", tmp_path, **HUD)

    assert [path.name for path in tmp_path.iterdir()] == ["me.mine"]
    assert [path.name for path in (tmp_path / "me.mine").iterdir()] == ["notes.txt"]


def test_a_share_that_cannot_be_written_leaves_nothing_behind(tmp_path, monkeypatch) -> None:
    def full_disk(*_args: Any, **_kwargs: Any) -> int:
        raise OSError("No space left on device")

    monkeypatch.setattr(Path, "write_text", full_disk)

    with pytest.raises(OSError, match="No space left"):
        share_hud(config_with(), "mine", tmp_path, **HUD)

    assert list(tmp_path.iterdir()) == []


def test_an_unknown_profile_is_said_so() -> None:
    assert profile_names(config_with()) == ["mine", "other"]
    with pytest.raises(GalleryError, match="no HUD profile named 'nowhere'"):
        hud_package(config_with(), "nowhere")


def repository_archive(source: Path) -> bytes:
    """The archive the packs repository's ``scripts/build.py`` builds from a pack's sources."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as out:
        for path in sorted(p for p in source.rglob("*") if p.is_file()):
            info = zipfile.ZipInfo(path.relative_to(source).as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            out.writestr(info, path.read_bytes())
    return buffer.getvalue()


def test_a_shared_stat_pack_is_its_sources_and_the_archive_the_repository_builds(tmp_path) -> None:
    packs_dir = tmp_path / "packs"
    archive = stat_pack(tmp_path, "example.steals", version="1.2.0")
    pack = stat_packs.install_pack(archive, packs_dir)
    out = tmp_path / "out"
    out.mkdir()

    folder = share_stat_pack("example.steals", out, license=LICENSE, packs_dir=packs_dir)

    entry = json.loads((folder / ENTRY_NAME).read_text(encoding="utf-8"))
    # The id and version are the pack's own; the rest defaults to its manifest.
    assert (entry["id"], entry["version"], entry["name"]) == ("example.steals", "1.2.0", pack.name)
    assert entry["file"] == "stats/example.steals.fpdbstats"
    assert entry["stats"] == [definition.name for definition in pack.definitions]
    sources = folder / "sources" / "stats" / "example.steals"
    assert (sources / "manifest.json").is_file()
    assert (folder / entry["file"]).read_bytes() == repository_archive(sources)
    assert as_gallery(folder) == []


def test_a_stat_pack_that_is_not_installed_is_said_so(tmp_path) -> None:
    with pytest.raises(stat_packs.PackError, match="not installed"):
        share_stat_pack("example.nowhere", tmp_path, license=LICENSE, packs_dir=tmp_path / "packs")


def test_the_profiles_rules_in_a_section_for_every_profile_are_shared_scoped_to_it(tmp_path) -> None:
    # Preferences write one section for every profile, each rule naming its own profile.
    config = config_with(
        '<hud_panel_rules enabled="true" fallback="core">'
        '<hud_panel_rule panel="facing_open" profile="mine"/>'
        '<hud_panel_rule panel="short_stack" profile="other"/>'
        '<hud_panel_rule panel="facing_cbet"/>'
        "</hud_panel_rules>"
    )

    package = defusedxml.minidom.parseString(hud_package(config, "mine")).documentElement

    # Codex (#643): only sections scoped to the profile were shared, so these rules were lost.
    (section,) = package.getElementsByTagName("hud_panel_rules")
    assert section.getAttribute("profile") == "mine"  # it changes nothing for the recipient's other profiles
    panels = [rule.getAttribute("panel") for rule in section.getElementsByTagName("hud_panel_rule")]
    assert panels == ["facing_open", "facing_cbet"]
    assert as_gallery(share_hud(config, "mine", tmp_path, **HUD)) == []


def test_a_stock_popup_the_sharer_customised_is_shared_under_a_name_of_its_own(tmp_path) -> None:
    config = without_default(
        config_with(
            "<popup_windows>"
            '<pu pu_name="default"><pu_stat pu_stat_name="vpip" pu_stat_submenu="deeper"/></pu>'
            '<pu pu_name="deeper"><pu_stat pu_stat_name="pfr"/></pu>'
            "</popup_windows>"
        )
    )
    for cell in config.getElementsByTagName("stat"):
        cell.setAttribute("popup", "default")

    package = defusedxml.minidom.parseString(hud_package(config, "mine")).documentElement

    # Codex (#643): the customised "default" was left out, and the recipient's stock one opened instead.
    names = sorted(node.getAttribute("pu_name") for node in package.getElementsByTagName("pu"))
    assert names == ["deeper", "default (mine)"]
    assert {cell.getAttribute("popup") for cell in package.getElementsByTagName("stat")} == {"default (mine)"}
    assert as_gallery(share_hud(config, "mine", tmp_path, **HUD)) == []


def test_a_stock_popup_as_shipped_is_left_to_the_recipients_own() -> None:
    stock = _stock_popup_nodes()["default"]
    config = without_default(config_with(f"<popup_windows>{stock.toxml()}</popup_windows>"))
    for cell in config.getElementsByTagName("stat"):
        cell.setAttribute("popup", "default")

    package = defusedxml.minidom.parseString(hud_package(config, "mine")).documentElement

    assert "default" not in {node.getAttribute("pu_name") for node in package.getElementsByTagName("pu")}
    assert {cell.getAttribute("popup") for cell in package.getElementsByTagName("stat")} == {"default"}


def test_rules_read_from_a_file_of_the_sharers_are_written_into_the_package(tmp_path) -> None:
    rules = tmp_path / "my_rules.json"
    rules.write_text(json.dumps({"fallback": "core", "rules": [{"panel": "facing_open", "profile": "mine"}]}))
    config = config_with(f'<hud_panel_rules enabled="true" source="{rules}" profile="mine"/>')

    package = defusedxml.minidom.parseString(hud_package(config, "mine")).documentElement

    # Codex (#643): the package named the sharer's file, which no recipient has.
    (section,) = package.getElementsByTagName("hud_panel_rules")
    assert not section.getAttribute("source")
    assert section.getAttribute("fallback") == "core"
    assert [rule.getAttribute("panel") for rule in section.getElementsByTagName("hud_panel_rule")] == ["facing_open"]


def test_a_rules_file_that_cannot_be_read_refuses_the_share(tmp_path) -> None:
    config = config_with(f'<hud_panel_rules enabled="true" source="{tmp_path / "gone.json"}" profile="mine"/>')

    with pytest.raises(GalleryError, match="cannot be read"):
        hud_package(config, "mine")


def test_the_shipped_rule_library_stays_named() -> None:
    config = config_with('<hud_panel_rules enabled="true" source="builtin" profile="mine"/>')

    package = defusedxml.minidom.parseString(hud_package(config, "mine")).documentElement

    assert package.getElementsByTagName("hud_panel_rules")[0].getAttribute("source") == "builtin"


def test_a_stock_popup_leading_to_a_customised_one_goes_in_too() -> None:
    stock = _stock_popup_nodes()
    config = without_default(
        config_with(
            "<popup_windows>"
            + stock["holdring_main"].toxml()
            + '<pu pu_name="default"><pu_stat pu_stat_name="vpip"/></pu>'
            + "".join(stock[name].toxml() for name in _submenus(stock["holdring_main"]) if name not in ("", "default"))
            + "</popup_windows>"
        )
    )
    for cell in config.getElementsByTagName("stat"):
        cell.setAttribute("popup", "holdring_main")

    package = defusedxml.minidom.parseString(hud_package(config, "mine")).documentElement

    # Codex (#643): holdring_main is as shipped, so the customised default under it was never reached.
    popups = {node.getAttribute("pu_name"): node for node in package.getElementsByTagName("pu")}
    assert sorted(popups) == ["default (mine)", "holdring_main (mine)"]
    assert "default (mine)" in _submenus(popups["holdring_main (mine)"])
    assert "default" not in _submenus(popups["holdring_main (mine)"])
    assert {cell.getAttribute("popup") for cell in package.getElementsByTagName("stat")} == {"holdring_main (mine)"}


def test_every_section_that_applies_becomes_one_in_the_order_it_is_read(tmp_path) -> None:
    config = config_with(
        '<hud_panel_rules enabled="true" fallback="core">'
        '<hud_panel_rule panel="facing_open" profile="mine"/>'
        '<hud_panel_rule panel="short_stack" profile="other"/>'
        "</hud_panel_rules>"
        '<hud_panel_rules enabled="false"><hud_panel_rule panel="never_read"/></hud_panel_rules>'
        '<hud_panel_rules enabled="true" profile="mine" source="builtin">'
        '<hud_panel_rule panel="facing_cbet"/>'
        "</hud_panel_rules>"
    )

    package = defusedxml.minidom.parseString(hud_package(config, "mine")).documentElement

    # Codex (#643): two sections scoped to "mine" went in, and an install keeps only the first.
    (section,) = package.getElementsByTagName("hud_panel_rules")
    assert (section.getAttribute("profile"), section.getAttribute("fallback")) == ("mine", "core")
    assert not section.getAttribute("source")  # the library's rules are written out, in their place
    panels = [rule.getAttribute("panel") for rule in section.getElementsByTagName("hud_panel_rule")]
    library = [rule.panel for rule in hud_situation.load_source("builtin")[0]]
    assert panels == ["facing_open", *library, "facing_cbet"]
    assert as_gallery(share_hud(config, "mine", tmp_path, **HUD)) == []


def test_rules_saved_for_a_mixed_case_profile_are_shared() -> None:
    config = config_with(
        '<hud_panel_rules enabled="true"><hud_panel_rule panel="facing_open" profile="mine"/></hud_panel_rules>'
    )
    config.getElementsByTagName("ss")[0].setAttribute("name", "My HUD")
    # Codex (#643): Preferences save the rule's profile as "my hud"; the case-sensitive match dropped it.
    config.getElementsByTagName("hud_panel_rule")[0].setAttribute("profile", "my hud")

    package = defusedxml.minidom.parseString(hud_package(config, "My HUD")).documentElement
    assert [rule.getAttribute("panel") for rule in package.getElementsByTagName("hud_panel_rule")] == ["facing_open"]


def test_a_source_section_that_does_not_say_enabled_is_shared() -> None:
    config = config_with('<hud_panel_rules source="builtin" profile="mine"/>')

    package = defusedxml.minidom.parseString(hud_package(config, "mine")).documentElement

    # Codex (#643): no "enabled" was taken for the empty stock section, and the library dropped.
    (section,) = package.getElementsByTagName("hud_panel_rules")
    assert (section.getAttribute("source"), section.getAttribute("enabled")) == ("builtin", "true")


def test_an_empty_section_is_not_shared() -> None:
    config = config_with('<hud_panel_rules enabled="false"/>')

    package = defusedxml.minidom.parseString(hud_package(config, "mine")).documentElement

    assert not package.getElementsByTagName("hud_panel_rules")
