"""The pack gallery's index and packages, checked before anything installs (#449).

A gallery here is a folder laid out as the packs repository will be: an
``index.json`` beside the packages. The acceptance of the issue is held
against it: the reference HUDs and two stat packs install from it into a fresh
profile, a malformed package is refused with a readable reason, and an update
is detected.
"""

from __future__ import annotations

import json
import shutil
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import defusedxml.minidom
import pytest

from fpdb_3_legacy import pack_gallery, pt4hud, stat_packs
from fpdb_3_legacy.hud_package import install_missing_hud_package, package_problems
from fpdb_3_legacy.pack_gallery import (
    INDEX_NAME,
    INDEX_SCHEMA,
    GalleryError,
    _HttpsOnlyRedirects,
    fetch_package,
    incompatibility,
    index_entry,
    install_entry,
    installed_versions,
    load_index,
    main,
    parse_index,
    read_location,
    read_record,
    uninstall_entry,
    updates,
    validate_repository,
)
from tests.helpers.pack_gallery import HUDS, LICENSE, ROOT, build_gallery, library_popups, stat_pack, write_index


@pytest.fixture
def gallery(tmp_path: Path) -> Path:
    return build_gallery(tmp_path / "gallery")


def entries_of(root: Path) -> list[dict[str, Any]]:
    return json.loads((root / INDEX_NAME).read_text(encoding="utf-8"))["packs"]


# -- acceptance --------------------------------------------------------------------------


def test_the_reference_huds_and_two_stat_packs_install_into_a_fresh_profile(gallery, tmp_path) -> None:
    index = load_index(str(gallery), tmp_path / "cache")
    assert len(index.entries) == 5 and index.rejected == () and not index.stale
    config = defusedxml.minidom.parseString("<FreePokerToolsConfig/>")
    packs_dir = tmp_path / "profile" / "stat-definitions.d"

    for entry in index.entries:
        package = fetch_package(entry, str(gallery), tmp_path / "cache")
        if entry.kind == "hud":
            assert install_missing_hud_package(config, defusedxml.minidom.parse(str(package)).documentElement)
        else:
            stat_packs.install_pack(package, packs_dir)

    profiles = {node.getAttribute("name") for node in config.getElementsByTagName("ss")}
    assert set(HUDS) <= profiles
    # Their popups come with them: a cell whose popup is missing opens nothing.
    opened = {node.getAttribute("popup") for node in config.getElementsByTagName("stat")} - {""}
    defined = {node.getAttribute("pu_name") for node in config.getElementsByTagName("pu")}
    assert "nlhe6_advanced_core" in defined
    assert opened <= defined | library_popups()
    installed = {status.id: status.status for status in stat_packs.list_packs(packs_dir)}
    assert installed["example.steals"] == installed["example.blinds"] == stat_packs.ENABLED


def test_the_repository_check_accepts_a_good_gallery(gallery, capsys) -> None:
    assert validate_repository(gallery) == []
    assert main(["validate", str(gallery)]) == 0
    assert "every package checks out" in capsys.readouterr().out


def test_a_newer_version_in_the_index_is_an_update(gallery, tmp_path) -> None:
    index = load_index(str(gallery), tmp_path / "cache")

    found = updates(index, {"example.steals": "0.9", "example.blinds": "1.0.0", "fpdb-3.nlhe_6max_basic": "manual"})

    assert sorted((entry.id, installed) for entry, installed in found) == [
        ("example.steals", "0.9"),
        ("fpdb-3.nlhe_6max_basic", "manual"),  # an unreadable installed version counts as older
    ]


def test_the_same_version_written_shorter_is_not_an_update(gallery, tmp_path) -> None:
    index = load_index(str(gallery), tmp_path / "cache")

    # Codex (#640): 1.0 and 1.0.0 are one release.
    assert updates(index, {"example.steals": "1.0", "example.blinds": "1"}) == []


# -- what is refused, and why ---------------------------------------------------------------


def test_a_hud_naming_a_stat_that_does_not_exist_is_refused_with_its_name(gallery, tmp_path) -> None:
    path = gallery / "hud" / "nlhe_6max_basic.fpdbhud"
    path.write_text(
        path.read_text(encoding="utf-8").replace('_stat_name="vpip"', '_stat_name="no_such_stat"', 1), encoding="utf-8"
    )
    entries = entries_of(gallery)
    entries[0] = index_entry(
        path, pack_id="fpdb-3.nlhe_6max_basic", kind="hud", name="b", version="1.0.0", author="a", license=LICENSE
    )
    write_index(gallery, entries)
    index = load_index(str(gallery), tmp_path / "cache")

    with pytest.raises(GalleryError) as refused:
        fetch_package(index.entries[0], str(gallery), tmp_path / "cache")

    assert any("unknown stat(s): no_such_stat" in message for message in refused.value.messages)
    assert not (tmp_path / "cache" / "packages" / "fpdb-3.nlhe_6max_basic").exists()
    assert validate_repository(gallery) == ["fpdb-3.nlhe_6max_basic: unknown stat(s): no_such_stat"]
    assert main(["validate", str(gallery)]) == 1


def test_a_package_that_is_not_the_one_indexed_is_refused(gallery, tmp_path) -> None:
    index = load_index(str(gallery), tmp_path / "cache")
    (gallery / "hud" / "nlhe_6max_basic.fpdbhud").write_bytes(b"<fpdb_hud_package/>" * 2)

    with pytest.raises(GalleryError) as refused:
        fetch_package(index.entries[0], str(gallery), tmp_path / "cache")

    assert "the index says" in str(refused.value)


def test_a_tampered_package_with_the_right_size_fails_its_checksum(gallery, tmp_path) -> None:
    index = load_index(str(gallery), tmp_path / "cache")
    path = gallery / "hud" / "nlhe_6max_basic.fpdbhud"
    data = bytearray(path.read_bytes())
    data[-2] = ord("x") if data[-2] != ord("x") else ord("y")
    path.write_bytes(bytes(data))

    with pytest.raises(GalleryError) as refused:
        fetch_package(index.entries[0], str(gallery), tmp_path / "cache")

    assert refused.value.messages == ["does not match the checksum in the index"]


def test_a_stat_pack_that_is_not_the_one_indexed_is_refused(gallery, tmp_path) -> None:
    entries = entries_of(gallery)
    stats = next(entry for entry in entries if entry["id"] == "example.steals")
    path = stat_pack(gallery / "stats", "example.steals", version="2.0.0")
    stats.update(
        index_entry(
            path, pack_id="example.steals", kind="stats", name="s", version="1.0.0", author="a", license=LICENSE
        )
    )
    write_index(gallery, entries)

    assert validate_repository(gallery) == [
        "example.steals: the pack inside is version '2.0.0', the index says '1.0.0'"
    ]


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"kind": "notes"}, "kind 'notes' is not one this fpdb installs"),
        ({"file": "../../etc/passwd.fpdbhud"}, "must be a relative path inside the gallery"),
        ({"file": "hud/basic.xml"}, "must end in .fpdbhud"),
        ({"sha256": "abc"}, "sha256 must be 64 lower-case hexadecimal digits"),
        ({"size": 0}, "size must be a whole number of bytes"),
        ({"version": "latest"}, "version 'latest' must be written like"),
        ({"id": "nodots"}, "id must be a dotted lower-case namespace"),
        ({"script": "rm -rf /"}, "unsupported field(s) ['script']"),
    ],
)
def test_a_malformed_entry_is_set_aside_and_the_rest_stays_usable(gallery, change, reason) -> None:
    entries = entries_of(gallery)
    entries[0].update(change)
    write_index(gallery, entries)

    index = parse_index((gallery / INDEX_NAME).read_bytes())

    assert len(index.entries) == 4
    ((_label, why),) = index.rejected
    assert reason in why


def test_an_entry_listed_twice_is_set_aside() -> None:
    entry = {
        "id": "a.b",
        "kind": "hud",
        "name": "n",
        "version": "1",
        "author": "a",
        "license": LICENSE,
        "file": "hud/b.fpdbhud",
        "sha256": "0" * 64,
        "size": 1,
    }
    index = parse_index(json.dumps({"schema": INDEX_SCHEMA, "version": 1, "packs": [entry, entry]}))

    assert len(index.entries) == 1 and index.rejected == (("a.b", "listed twice"),)


@pytest.mark.parametrize(
    "document",
    [
        "not json",
        "[]",
        json.dumps({"schema": "other", "version": 1, "packs": []}),
        json.dumps({"schema": INDEX_SCHEMA, "version": 9, "packs": []}),
    ],
)
def test_an_index_that_is_not_one_is_refused_whole(document) -> None:
    with pytest.raises(GalleryError):
        parse_index(document)


def test_a_pack_for_a_newer_fpdb_says_so(gallery, tmp_path) -> None:
    entries = entries_of(gallery)
    entries[0]["min_fpdb_version"] = "99.0"
    write_index(gallery, entries)

    entry = load_index(str(gallery), tmp_path / "cache").entries[0]

    assert incompatibility(entry, "3.9.1") == "needs fpdb 99.0 or newer (this is 3.9.1)"
    assert incompatibility(entry, "99.0") == ""
    # Codex (#640): the package checks refuse it too, for every kind, fetched or cached.
    with pytest.raises(GalleryError, match=r"needs fpdb 99\.0 or newer"):
        fetch_package(entry, str(gallery), tmp_path / "cache", fpdb_version="3.9.1")
    assert validate_repository(gallery, fpdb_version="3.9.1") == [
        f"{entry.id}: needs fpdb 99.0 or newer (this is 3.9.1)"
    ]
    assert validate_repository(gallery, fpdb_version="99.0") == []


# -- offline ------------------------------------------------------------------------------------


def test_without_the_network_the_cached_index_and_packages_are_used(gallery, tmp_path) -> None:
    cache = tmp_path / "cache"
    entry = load_index(str(gallery), cache).entries[0]
    fetch_package(entry, str(gallery), cache)

    def offline(_where: str, _limit: int) -> bytes:
        raise OSError("network is unreachable")

    index = load_index("https://example.invalid/packs", cache, read=offline)
    package = fetch_package(entry, "https://example.invalid/packs", cache, read=offline)

    assert index.stale and len(index.entries) == 5
    assert package.read_bytes() == (gallery / entry.file).read_bytes()


def test_without_the_network_or_a_cache_the_gallery_says_so(tmp_path) -> None:
    def offline(_where: str, _limit: int) -> bytes:
        raise OSError("network is unreachable")

    with pytest.raises(GalleryError) as refused:
        load_index("https://example.invalid/packs", tmp_path / "cache", read=offline)

    assert "nothing is cached" in str(refused.value)


def test_the_gallery_is_only_read_over_https() -> None:
    with pytest.raises(OSError, match="only read over https"):
        read_location("http://example.invalid/packs/index.json", 100)


def test_a_redirect_away_from_https_is_refused() -> None:
    # Codex (#640): the index carries the checksums, so its transport must stay https end to end.
    handler = _HttpsOnlyRedirects()
    request = urllib.request.Request("https://example.invalid/packs/index.json")

    with pytest.raises(OSError, match="only read over https"):
        handler.redirect_request(request, None, 302, "Found", {}, "http://example.invalid/packs/index.json")
    followed = handler.redirect_request(request, None, 302, "Found", {}, "https://mirror.invalid/packs/index.json")
    assert followed is not None
    assert followed.full_url == "https://mirror.invalid/packs/index.json"


def test_a_file_larger_than_allowed_is_not_read_whole(tmp_path) -> None:
    big = tmp_path / "big.fpdbhud"
    big.write_bytes(b"x" * 101)

    with pytest.raises(OSError, match="larger than 100 bytes"):
        read_location(str(big), 100)


# -- the HUD package checker ---------------------------------------------------------------------


@pytest.mark.parametrize("path", sorted((ROOT / "hud-packages").glob("*.fpdbhud")), ids=lambda path: path.name)
def test_every_shipped_hud_package_passes_the_install_check(path) -> None:
    assert package_problems(defusedxml.minidom.parse(str(path)).documentElement) == []


@pytest.mark.parametrize(
    ("xml", "problem"),
    [
        ("<other/>", "the root element must be <fpdb_hud_package>"),
        ("<fpdb_hud_package/>", "the package holds no HUD profile (<ss>)"),
        # Codex (#640): what the configuration loader would fail on, or silently overwrite.
        (
            '<fpdb_hud_package><ss name="p" rows="1" cols="1"><stat _stat_name="vpip"/></ss></fpdb_hud_package>',
            "p: vpip has no _rowcol; write where it sits as (row,col), counted from 1",
        ),
        (
            '<fpdb_hud_package><ss name="p" rows="1" cols="1"><stat _rowcol="1,1" _stat_name="vpip"/></ss></fpdb_hud_package>',
            "p: vpip has an invalid _rowcol '1,1'; write where it sits as (row,col), counted from 1",
        ),
        (
            '<fpdb_hud_package><ss name="p" rows="1" cols="2"><stat _rowcol="(1,1)" _stat_name="vpip"/>'
            '<stat _rowcol="(1,1)" _stat_name="pfr"/></ss></fpdb_hud_package>',
            "p: pfr at (1,1) overlaps vpip at (1,1)",
        ),
        (
            '<fpdb_hud_package><ss name="p" rows="1" cols="2"><stat _rowcol="(2,1)" _stat_name="vpip"/></ss></fpdb_hud_package>',
            "p: vpip at (2,1) is outside the 1x2 grid",
        ),
        (
            '<fpdb_hud_package><ss name="p" rows="1" cols="1"><block label="b" rows="1" cols="2"><text _rowcol="(1,1)" label="Pre" colspan="2"/>'
            '<stat _rowcol="(1,2)" _stat_name="vpip"/></block></ss></fpdb_hud_package>',
            "b: vpip at (1,2) overlaps Pre at (1,1)",
        ),
        (
            '<fpdb_hud_package><ss name="p" rows="1" cols="1"><block label="b" rows="1" cols="2">'
            '<text _rowcol="(1,1)" label="Pre" colspan="3"/></block></ss></fpdb_hud_package>',
            "b: Pre at (1,1) is outside the 1x2 grid",
        ),
        (
            '<fpdb_hud_package><ss name="p" rows="1" cols="2"><stat _rowcol="(1,1)" _stat_name="vpip" colspan="x"/>'
            "</ss></fpdb_hud_package>",
            "p: vpip at (1,1): colspan must be a whole number from 1 to 100",
        ),
        # Codex (#640), second round: a span is bounded before it is expanded...
        (
            '<fpdb_hud_package><ss name="p" rows="1" cols="1"><block label="b">'
            '<stat _rowcol="(1,1)" _stat_name="vpip" colspan="1000000000"/></block></ss></fpdb_hud_package>',
            "b: vpip at (1,1): colspan must be a whole number from 1 to 100",
        ),
        # ... a profile with blocks still needs the size the loader reads...
        (
            '<fpdb_hud_package><ss name="p"><block label="b" rows="1" cols="1">'
            '<stat _rowcol="(1,1)" _stat_name="vpip"/></block></ss></fpdb_hud_package>',
            "p: a profile needs rows and cols",
        ),
        (
            '<fpdb_hud_package><ss name="p" rows="two" cols="1"><block label="b" rows="1" cols="1">'
            '<stat _rowcol="(1,1)" _stat_name="vpip"/></block></ss></fpdb_hud_package>',
            "p: rows and cols must be whole numbers up to 100",
        ),
        (
            '<fpdb_hud_package><ss name="p" rows="1" cols="1"><block label="b" x="left">'
            '<stat _rowcol="(1,1)" _stat_name="vpip"/></block></ss></fpdb_hud_package>',
            "b: x 'left' is not a number",
        ),
        # Codex (#640): float() reads nan, but the HUD cannot round a font size scaled by it.
        (
            '<fpdb_hud_package><ss name="p" rows="1" cols="1"><block label="b" heading_font_scale="nan">'
            '<stat _rowcol="(1,1)" _stat_name="vpip"/></block></ss></fpdb_hud_package>',
            "b: heading_font_scale 'nan' is not a number",
        ),
        # ... and a header that does not say where it sits is checked on the first cell.
        (
            '<fpdb_hud_package><ss name="p" rows="1" cols="1"><block label="b">'
            '<text label="Header" colspan="bad"/></block></ss></fpdb_hud_package>',
            "b: Header at (1,1): colspan must be a whole number from 1 to 100",
        ),
        (
            '<fpdb_hud_package><ss name="p" rows="1" cols="1"><block label="b" rows="1" cols="1">'
            '<text label="Header"/><stat _rowcol="(1,1)" _stat_name="vpip"/></block></ss></fpdb_hud_package>',
            "b: vpip at (1,1) overlaps Header at (1,1)",
        ),
        (
            '<fpdb_hud_package><ss name="p" rows="1" cols="1">'
            '<stat _rowcol="(1,1)" _stat_name="vpip" popup="nowhere"/></ss></fpdb_hud_package>',
            "popup(s) neither in the package nor in the shipped library: nowhere",
        ),
        (
            '<fpdb_hud_package><ss name="p" rows="1" cols="1"><stat _rowcol="(1,1)" _stat_name="x" '
            'data_source="analytics" data_definition="no_such_definition"/></ss></fpdb_hud_package>',
            "unknown analytics definition(s): no_such_definition",
        ),
    ],
)
def test_a_broken_hud_package_says_what_is_wrong(xml, problem) -> None:
    assert problem in package_problems(defusedxml.minidom.parseString(xml).documentElement)


@pytest.mark.parametrize(
    "xml",
    [
        # Codex (#640): a header above a stat, as a PT4 layout converts it.
        '<fpdb_hud_package><ss name="p" rows="1" cols="1"><block label="b" rows="2" cols="1"><text _rowcol="(1,1)" label="Preflop"/>'
        '<stat _rowcol="(2,1)" _stat_name="vpip"/></block></ss></fpdb_hud_package>',
        # A header spanning the block, a separator, and an empty cell.
        '<fpdb_hud_package><ss name="p" rows="1" cols="1"><block label="b" rows="3" cols="2"><text _rowcol="(1,1)" label="Pre" colspan="2"/>'
        '<hline _rowcol="(2,1)"/><stat _rowcol="(3,1)" _stat_name="vpip"/></block></ss></fpdb_hud_package>',
        # A block that does not state its size takes it from its items.
        '<fpdb_hud_package><ss name="p" rows="1" cols="1"><block label="b"><stat _rowcol="(1,3)" _stat_name="vpip"/></block></ss>'
        "</fpdb_hud_package>",
        # A table stat, and the popup every configuration has.
        '<fpdb_hud_package><ss name="p" rows="1" cols="2"><stat _rowcol="(1,1)" _stat_name="live_min_stack_bb"/>'
        '<stat _rowcol="(1,2)" _stat_name="vpip" popup="default"/></ss></fpdb_hud_package>',
        # Codex (#640): a stat with its decimal places (vpip_0), and a separator whose span of 0 crosses the block.
        '<fpdb_hud_package><ss name="p" rows="2" cols="2"><block label="b" rows="2" cols="2">'
        '<stat _rowcol="(1,1)" _stat_name="vpip_0"/><hline _rowcol="(2,1)" colspan="0"/></block></ss></fpdb_hud_package>',
        # Codex (#640): a declarative stat from stats.d, which Stats.do_stat dispatches through the registry.
        '<fpdb_hud_package><ss name="p" rows="1" cols="1"><stat _rowcol="(1,1)" _stat_name="chipev_3h_btn"/></ss>'
        "</fpdb_hud_package>",
        # Codex (#640): a cell the HUD editor bound to an analytics definition, by its definition or by its name.
        '<fpdb_hud_package><ss name="p" rows="1" cols="2"><stat _rowcol="(1,1)" _stat_name="f3b" data_source="analytics"'
        ' data_definition="fold_to_3bet_preflop"/><stat _rowcol="(1,2)" _stat_name="fold_to_cbet_flop"'
        ' data_source="analytics"/></ss></fpdb_hud_package>',
    ],
)
def test_a_well_formed_hud_package_passes(xml) -> None:
    assert package_problems(defusedxml.minidom.parseString(xml).documentElement) == []


@pytest.mark.parametrize("multiblock", [True, False], ids=["blocks", "flat"])
def test_a_pt4_layout_converted_to_a_package_passes(multiblock) -> None:
    xml, _summary = pt4hud.to_package(
        str(ROOT / "test" / "fixtures" / "generationpoker_3h.pt4hud"), multiblock=multiblock
    )

    root = defusedxml.minidom.parseString(xml).documentElement

    assert root.getElementsByTagName("text") or not multiblock
    assert package_problems(root) == []


# -- installing from the gallery ----------------------------------------------------------------


def fresh_config() -> Any:
    return defusedxml.minidom.parseString(
        "<FreePokerToolsConfig><stat_sets>"
        '<ss name="mine" rows="1" cols="1"><stat _rowcol="(1,1)" _stat_name="vpip" popup="my_popup"/></ss>'
        '</stat_sets><popup_windows><pu pu_name="my_popup"><pu_stat pu_stat_name="pfr"/></pu></popup_windows>'
        '<supported_games><game game_name="holdem"><game_stat_set game_type="ring" stat_set="mine"/></game>'
        "</supported_games></FreePokerToolsConfig>"
    )


def names(config: Any, tag: str, attribute: str) -> set[str]:
    return {node.getAttribute(attribute) for node in config.getElementsByTagName(tag)}


@pytest.fixture
def installer(gallery, tmp_path):
    index = load_index(str(gallery), tmp_path / "cache")
    record = tmp_path / "profile" / "pack-gallery.json"
    packs_dir = tmp_path / "profile" / "stat-definitions.d"

    def install(pack_id: str, config: Any, *, replace: bool = False) -> bool:
        entry = index.get(pack_id)
        package = fetch_package(entry, str(gallery), tmp_path / "cache")
        return install_entry(entry, package, config_doc=config, record=record, packs_dir=packs_dir, replace=replace)

    return SimpleNamespace(index=index, record=record, packs_dir=packs_dir, install=install)


def test_a_hud_from_the_gallery_is_added_beside_the_users_own(installer) -> None:
    config = fresh_config()

    assert installer.install("fpdb-3.nlhe_6max_advanced", config) is True

    assert {"mine", "nlhe_6max_advanced"} <= names(config, "ss", "name")
    assert installed_versions(installer.record, installer.packs_dir)["fpdb-3.nlhe_6max_advanced"] == "1.0.0"
    recorded = read_record(installer.record)["fpdb-3.nlhe_6max_advanced"]
    assert recorded["profiles"] == ["nlhe_6max_advanced"]


def test_a_hud_never_replaces_a_profile_of_the_users_with_its_name(installer) -> None:
    config = fresh_config()
    config.getElementsByTagName("ss")[0].setAttribute("name", "nlhe_6max_basic")

    with pytest.raises(GalleryError, match="you already have a HUD profile named nlhe_6max_basic"):
        installer.install("fpdb-3.nlhe_6max_basic", config)
    with pytest.raises(GalleryError):
        installer.install("fpdb-3.nlhe_6max_basic", config, replace=True)
    assert read_record(installer.record) == {}


def test_an_update_replaces_the_packs_own_profile_and_nothing_else(installer) -> None:
    config = fresh_config()
    installer.install("fpdb-3.nlhe_6max_basic", config)
    profile = next(node for node in config.getElementsByTagName("ss") if node.getAttribute("name") == "nlhe_6max_basic")
    profile.setAttribute("rows", "99")  # edited since

    installer.install("fpdb-3.nlhe_6max_basic", config, replace=True)

    profiles = [node for node in config.getElementsByTagName("ss") if node.getAttribute("name") == "nlhe_6max_basic"]
    assert len(profiles) == 1 and profiles[0].getAttribute("rows") != "99"
    assert "mine" in names(config, "ss", "name") and "my_popup" in names(config, "pu", "pu_name")


def test_uninstalling_a_hud_removes_what_it_added_and_keeps_what_is_yours(installer) -> None:
    config = fresh_config()
    installer.install("fpdb-3.nlhe_6max_advanced", config)
    added = set(read_record(installer.record)["fpdb-3.nlhe_6max_advanced"]["popups"])
    assert added and "my_popup" not in added

    assert uninstall_entry("fpdb-3.nlhe_6max_advanced", config_doc=config, record=installer.record) is True

    assert names(config, "ss", "name") == {"mine"}
    assert names(config, "pu", "pu_name") == {"my_popup"}
    assert read_record(installer.record) == {}


def test_a_hud_a_game_still_uses_is_not_uninstalled(installer) -> None:
    config = fresh_config()
    installer.install("fpdb-3.nlhe_6max_basic", config)
    config.getElementsByTagName("game_stat_set")[0].setAttribute("stat_set", "nlhe_6max_basic")

    with pytest.raises(GalleryError, match=r"in use for holdem \(ring\)"):
        uninstall_entry("fpdb-3.nlhe_6max_basic", config_doc=config, record=installer.record)

    assert "nlhe_6max_basic" in names(config, "ss", "name")
    assert "fpdb-3.nlhe_6max_basic" in read_record(installer.record)


def test_a_stat_pack_installs_updates_and_uninstalls_through_the_pack_directory(installer) -> None:
    config = fresh_config()

    assert installer.install("example.steals", config) is False  # the HUD configuration is untouched
    assert installed_versions(installer.record, installer.packs_dir)["example.steals"] == "1.0.0"
    installer.install("example.steals", config, replace=True)
    uninstall_entry("example.steals", config_doc=config, record=installer.record, packs_dir=installer.packs_dir)

    assert "example.steals" not in installed_versions(installer.record, installer.packs_dir)


def test_a_pack_not_installed_from_the_gallery_cannot_be_uninstalled_from_it(installer) -> None:
    with pytest.raises(GalleryError, match="was not installed from the gallery"):
        uninstall_entry("fpdb-3.nlhe_6max_basic", config_doc=fresh_config(), record=installer.record)


def test_a_damaged_record_reads_as_nothing_installed(tmp_path) -> None:
    record = tmp_path / "pack-gallery.json"
    record.write_text("{not json", encoding="utf-8")

    assert read_record(record) == {}


def test_a_popup_the_pack_added_stays_while_something_of_yours_opens_it(installer) -> None:
    config = fresh_config()
    installer.install("fpdb-3.nlhe_6max_advanced", config)
    # The user's own profile now opens the pack's core popup, which opens its "opens" popup.
    config.getElementsByTagName("stat")[0].setAttribute("popup", "nlhe6_advanced_core")

    uninstall_entry("fpdb-3.nlhe_6max_advanced", config_doc=config, record=installer.record)

    assert {"nlhe6_advanced_core", "nlhe6_advanced_opens"} <= names(config, "pu", "pu_name")
    assert "nlhe_6max_advanced" not in names(config, "ss", "name")


# -- updates and installs that must not break the user's configuration (Codex, #641) -----------


def republish(gallery: Path, pack_id: str, edit) -> None:
    """Publish version 2.0.0 of a HUD pack in *gallery*, its XML changed by *edit*."""
    entries = entries_of(gallery)
    entry = next(item for item in entries if item["id"] == pack_id)
    path = gallery / entry["file"]
    path.write_text(edit(path.read_text(encoding="utf-8")), encoding="utf-8")
    entry.update(
        index_entry(path, pack_id=pack_id, kind="hud", name=entry["name"], version="2.0.0", author="a", license=LICENSE)
    )
    write_index(gallery, entries)


def drop_opens_popup(xml: str) -> str:
    """Version 2 of the Advanced HUD: its "opens" popup gone, and every link to it pointed at the core popup."""
    start = xml.index('<pu pu_name="nlhe6_advanced_opens"')
    without = xml[:start] + xml[xml.index("</pu>", start) + len("</pu>") :]
    return without.replace('"nlhe6_advanced_opens"', '"nlhe6_advanced_core"')


def install_from(gallery: Path, tmp_path: Path, pack_id: str, config: Any, *, replace: bool = False) -> bool:
    entry = load_index(str(gallery), tmp_path / "cache").get(pack_id)
    package = fetch_package(entry, str(gallery), tmp_path / "cache")
    return install_entry(entry, package, config_doc=config, record=tmp_path / "record.json", replace=replace)


def test_an_update_that_drops_a_profile_a_game_uses_is_refused(gallery, tmp_path) -> None:
    config = fresh_config()
    install_from(gallery, tmp_path, "fpdb-3.nlhe_6max_basic", config)
    config.getElementsByTagName("game_stat_set")[0].setAttribute("stat_set", "nlhe_6max_basic")
    republish(
        gallery, "fpdb-3.nlhe_6max_basic", lambda xml: xml.replace('name="nlhe_6max_basic"', 'name="basic_v2"', 1)
    )
    before = config.toxml()

    with pytest.raises(GalleryError, match=r"drops a HUD profile used for holdem \(ring\)"):
        install_from(gallery, tmp_path, "fpdb-3.nlhe_6max_basic", config, replace=True)

    assert config.toxml() == before
    assert read_record(tmp_path / "record.json")["fpdb-3.nlhe_6max_basic"]["version"] == "1.0.0"


def test_an_update_keeps_a_dropped_popup_that_something_of_yours_opens(gallery, tmp_path) -> None:
    config = fresh_config()
    install_from(gallery, tmp_path, "fpdb-3.nlhe_6max_advanced", config)
    # The user's own profile opens the pack's "opens" popup; version 2 no longer has it.
    config.getElementsByTagName("stat")[0].setAttribute("popup", "nlhe6_advanced_opens")

    republish(gallery, "fpdb-3.nlhe_6max_advanced", drop_opens_popup)

    install_from(gallery, tmp_path, "fpdb-3.nlhe_6max_advanced", config, replace=True)

    assert {"nlhe6_advanced_core", "nlhe6_advanced_opens"} <= names(config, "pu", "pu_name")
    recorded = read_record(tmp_path / "record.json")["fpdb-3.nlhe_6max_advanced"]
    assert recorded["version"] == "2.0.0" and "nlhe6_advanced_opens" in recorded["popups"]
    # Once nothing opens it, uninstalling the pack removes it.
    config.getElementsByTagName("stat")[0].setAttribute("popup", "my_popup")
    uninstall_entry("fpdb-3.nlhe_6max_advanced", config_doc=config, record=tmp_path / "record.json")
    assert names(config, "pu", "pu_name") == {"my_popup"}


def test_an_update_drops_a_popup_nothing_opens_any_more(gallery, tmp_path) -> None:
    config = fresh_config()
    install_from(gallery, tmp_path, "fpdb-3.nlhe_6max_advanced", config)

    republish(gallery, "fpdb-3.nlhe_6max_advanced", drop_opens_popup)

    install_from(gallery, tmp_path, "fpdb-3.nlhe_6max_advanced", config, replace=True)

    assert "nlhe6_advanced_opens" not in names(config, "pu", "pu_name")
    assert "nlhe6_advanced_opens" not in read_record(tmp_path / "record.json")["fpdb-3.nlhe_6max_advanced"]["popups"]


def test_a_gallery_hud_never_binds_itself_to_a_game(gallery, tmp_path) -> None:
    binding = '<game game_name="omahahi"><game_stat_set game_type="ring" stat_set="nlhe_6max_basic"/></game>'
    republish(
        gallery,
        "fpdb-3.nlhe_6max_basic",
        lambda xml: xml.replace("</fpdb_hud_package>", binding + "</fpdb_hud_package>"),
    )
    config = fresh_config()

    install_from(gallery, tmp_path, "fpdb-3.nlhe_6max_basic", config)

    assert "nlhe_6max_basic" in names(config, "ss", "name")
    assert names(config, "game", "game_name") == {"holdem"}
    assert names(config, "game_stat_set", "stat_set") == {"mine"}


def test_a_package_with_game_bindings_still_brings_its_panel_rules() -> None:
    package = defusedxml.minidom.parse(str(ROOT / "hud-packages" / "nlhe_6max_dynamic.fpdbhud")).documentElement
    binding = defusedxml.minidom.parseString(
        '<game game_name="holdem"><game_stat_set game_type="ring" stat_set="nlhe_6max_dynamic"/></game>'
    ).documentElement
    package.appendChild(binding)
    config = defusedxml.minidom.parseString("<FreePokerToolsConfig/>")

    assert install_missing_hud_package(config, package) is True

    # Chained with `or`, the binding's True skipped the panel rules entirely.
    assert config.getElementsByTagName("game_stat_set") and config.getElementsByTagName("hud_panel_rules")


def panel_sections(config: Any) -> dict[str, str]:
    """Each panel-rule section's profile and fallback."""
    return {
        node.getAttribute("profile"): node.getAttribute("fallback")
        for node in config.getElementsByTagName("hud_panel_rules")
    }


def test_an_update_replaces_the_panel_rules_the_pack_added_and_keeps_yours(gallery, tmp_path) -> None:
    # Codex (#641): the old version's section stayed, selecting panels the new one may no longer have.
    config = fresh_config()
    mine = defusedxml.minidom.parseString(
        '<hud_panel_rules enabled="true" source="builtin" fallback="my_core" profile="mine"/>'
    ).documentElement
    config.documentElement.appendChild(config.importNode(mine, True))
    install_from(gallery, tmp_path, "fpdb-3.nlhe_6max_dynamic", config)
    assert panel_sections(config) == {"mine": "my_core", "nlhe_6max_dynamic": "core"}
    republish(
        gallery,
        "fpdb-3.nlhe_6max_dynamic",
        lambda xml: xml.replace(
            'fallback="core" profile="nlhe_6max_dynamic"', 'fallback="core_v2" profile="nlhe_6max_dynamic"'
        ),
    )

    install_from(gallery, tmp_path, "fpdb-3.nlhe_6max_dynamic", config, replace=True)

    assert panel_sections(config) == {"mine": "my_core", "nlhe_6max_dynamic": "core_v2"}
    assert read_record(tmp_path / "record.json")["fpdb-3.nlhe_6max_dynamic"]["panel_rules"] == ["nlhe_6max_dynamic"]
    uninstall_entry("fpdb-3.nlhe_6max_dynamic", config_doc=config, record=tmp_path / "record.json")
    assert panel_sections(config) == {"mine": "my_core"}


def failing_save() -> None:
    raise OSError("disk full")


def test_a_hud_whose_configuration_cannot_be_saved_is_not_recorded(gallery, tmp_path) -> None:
    # Codex (#641): the record said installed while HUD_config.xml never received the pack.
    config = fresh_config()
    before = config.toxml()
    entry = load_index(str(gallery), tmp_path / "cache").get("fpdb-3.nlhe_6max_dynamic")
    package = fetch_package(entry, str(gallery), tmp_path / "cache")

    with pytest.raises(OSError, match="disk full"):
        install_entry(entry, package, config_doc=config, record=tmp_path / "record.json", save=failing_save)

    assert config.toxml() == before
    assert read_record(tmp_path / "record.json") == {}


def test_a_hud_whose_removal_cannot_be_saved_stays_recorded(gallery, tmp_path) -> None:
    config = fresh_config()
    install_from(gallery, tmp_path, "fpdb-3.nlhe_6max_dynamic", config)
    before = config.toxml()

    with pytest.raises(OSError, match="disk full"):
        uninstall_entry(
            "fpdb-3.nlhe_6max_dynamic", config_doc=config, record=tmp_path / "record.json", save=failing_save
        )

    assert config.toxml() == before
    assert read_record(tmp_path / "record.json")["fpdb-3.nlhe_6max_dynamic"]["version"] == "1.0.0"


class Saves:
    """A configuration save that remembers what it wrote."""

    def __init__(self, config: Any) -> None:
        self.config, self.written = config, []

    def __call__(self) -> None:
        self.written.append(self.config.toxml())


def unwritable_record(monkeypatch) -> None:
    def refuse(_path, _installed) -> None:
        raise OSError("read-only profile")

    monkeypatch.setattr(pack_gallery, "_write_record", refuse)


def test_a_hud_whose_record_cannot_be_written_is_taken_back_out(gallery, tmp_path, monkeypatch) -> None:
    # Codex (#641): saved but unrecorded, the profile then blocked its own reinstall as a name of the user's.
    config = fresh_config()
    before = config.toxml()
    saves = Saves(config)
    entry = load_index(str(gallery), tmp_path / "cache").get("fpdb-3.nlhe_6max_basic")
    package = fetch_package(entry, str(gallery), tmp_path / "cache")
    unwritable_record(monkeypatch)

    with pytest.raises(OSError, match="read-only profile"):
        install_entry(entry, package, config_doc=config, record=tmp_path / "record.json", save=saves)

    assert config.toxml() == before
    assert len(saves.written) == 2 and saves.written[-1] == before  # saved, then saved back as it was
    assert read_record(tmp_path / "record.json") == {}


def test_a_hud_whose_record_cannot_be_updated_on_uninstall_stays(gallery, tmp_path, monkeypatch) -> None:
    config = fresh_config()
    install_from(gallery, tmp_path, "fpdb-3.nlhe_6max_basic", config)
    before = config.toxml()
    saves = Saves(config)
    unwritable_record(monkeypatch)

    with pytest.raises(OSError, match="read-only profile"):
        uninstall_entry("fpdb-3.nlhe_6max_basic", config_doc=config, record=tmp_path / "record.json", save=saves)

    assert config.toxml() == before and saves.written[-1] == before
    assert "fpdb-3.nlhe_6max_basic" in read_record(tmp_path / "record.json")


def test_a_new_stat_pack_whose_record_cannot_be_written_is_taken_back_out(installer, monkeypatch) -> None:
    unwritable_record(monkeypatch)

    with pytest.raises(OSError, match="read-only profile"):
        installer.install("example.steals", fresh_config())

    assert "example.steals" not in installed_versions(installer.record, installer.packs_dir)


def test_a_stat_pack_whose_removal_cannot_be_recorded_stays_installed(installer, monkeypatch) -> None:
    # Codex (#641): the folder was deleted first, leaving a record of a pack that no longer existed.
    config = fresh_config()
    installer.install("example.steals", config)
    unwritable_record(monkeypatch)

    with pytest.raises(OSError, match="read-only profile"):
        uninstall_entry("example.steals", config_doc=config, record=installer.record, packs_dir=installer.packs_dir)

    assert (installer.packs_dir / "example.steals").is_dir()
    assert installed_versions(installer.record, installer.packs_dir)["example.steals"] == "1.0.0"
    assert "example.steals" in read_record(installer.record)


def test_a_stale_stat_pack_record_does_not_block_reinstalling_it(installer) -> None:
    config = fresh_config()
    installer.install("example.steals", config)
    shutil.rmtree(installer.packs_dir / "example.steals")  # gone, though the record still names it

    assert "example.steals" not in installed_versions(installer.record, installer.packs_dir)
    uninstall_entry("example.steals", config_doc=config, record=installer.record, packs_dir=installer.packs_dir)
    assert read_record(installer.record) == {}
    installer.install("example.steals", config)
    assert installed_versions(installer.record, installer.packs_dir)["example.steals"] == "1.0.0"
