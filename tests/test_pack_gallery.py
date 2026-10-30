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
import zipfile
from pathlib import Path
from typing import Any

import defusedxml.minidom
import pytest

from fpdb_3_legacy import pt4hud, stat_packs
from fpdb_3_legacy.hud_package import install_missing_hud_package, package_problems
from fpdb_3_legacy.pack_gallery import (
    INDEX_NAME,
    INDEX_SCHEMA,
    GalleryError,
    _HttpsOnlyRedirects,
    fetch_package,
    incompatibility,
    index_entry,
    load_index,
    main,
    parse_index,
    read_location,
    updates,
    validate_repository,
)

ROOT = Path(__file__).resolve().parents[1]
HUDS = ("nlhe_6max_basic", "nlhe_6max_advanced", "nlhe_6max_dynamic")
EXAMPLE_PACK = ROOT / "docs" / "examples" / "example-preflop-pack"
LICENSE = "AGPL-3.0-or-later"


def stat_pack(target: Path, pack_id: str, version: str = "1.0.0") -> Path:
    """The example stat pack as a ``.fpdbstats`` archive, renamed to *pack_id*."""
    manifest = json.loads((EXAMPLE_PACK / "manifest.json").read_text(encoding="utf-8"))
    old = manifest["id"]
    archive = target / f"{pack_id}{stat_packs.PACK_SUFFIX}"
    with zipfile.ZipFile(archive, "w") as out:
        for path in sorted(EXAMPLE_PACK.rglob("*")):
            name = path.relative_to(EXAMPLE_PACK).as_posix()
            if path.is_file() and name != "manifest.json":
                # Every name the pack adds is namespaced by its id.
                out.writestr(name, path.read_text(encoding="utf-8").replace(old, pack_id))
        manifest_text = json.dumps({**json.loads(json.dumps(manifest).replace(old, pack_id)), "pack_version": version})
        out.writestr("manifest.json", manifest_text)
    return archive


def write_index(root: Path, entries: list[dict[str, Any]]) -> None:
    (root / INDEX_NAME).write_text(
        json.dumps({"schema": INDEX_SCHEMA, "version": 1, "packs": entries}), encoding="utf-8"
    )


@pytest.fixture
def gallery(tmp_path: Path) -> Path:
    """A packs repository holding the three reference HUDs and two stat packs."""
    root = tmp_path / "gallery"
    (root / "hud").mkdir(parents=True)
    (root / "stats").mkdir()
    entries = []
    for hud in HUDS:
        path = root / "hud" / f"{hud}.fpdbhud"
        shutil.copy(ROOT / "hud-packages" / path.name, path)
        entries.append(
            index_entry(
                path, pack_id=f"fpdb-3.{hud}", kind="hud", name=hud, version="1.0.0", author="fpdb-3", license=LICENSE
            )
        )
    for pack_id in ("example.steals", "example.blinds"):
        path = stat_pack(root / "stats", pack_id)
        entries.append(
            index_entry(
                path, pack_id=pack_id, kind="stats", name=pack_id, version="1.0.0", author="example", license=LICENSE
            )
        )
    write_index(root, entries)
    return root


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
