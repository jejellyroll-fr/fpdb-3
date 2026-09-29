"""User-installed declarative stat packs (#403).

Each test works on a throwaway pack directory; the example pack shipped in the
documentation is the fixture, so the documented example is proven installable.
"""

from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path
from typing import Any

import pytest

from fpdb_3_legacy import analytics_definitions, stat_packs
from fpdb_3_legacy.hud_panel_editor import analytics_choices

EXAMPLE = Path(__file__).resolve().parents[1] / "docs" / "examples" / "example-preflop-pack"
PACK_ID = "example.preflop"


@pytest.fixture
def packs_dir(tmp_path: Path) -> Path:
    return tmp_path / "stat-definitions.d"


@pytest.fixture
def source(tmp_path: Path) -> Path:
    """A private copy of the example pack, safe to edit."""
    target = tmp_path / "source-pack"
    shutil.copytree(EXAMPLE, target)
    return target


def edit_manifest(pack: Path, **changes: Any) -> None:
    manifest = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
    for key, value in changes.items():
        if value is None:
            manifest.pop(key, None)
        else:
            manifest[key] = value
    (pack / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def write_stats(pack: Path, stats: list[dict[str, Any]], name: str = "stats/steals.json") -> None:
    (pack / name).write_text(json.dumps({"schema_version": 1, "stats": stats}), encoding="utf-8")


def refused(source: Path, packs_dir: Path, **kwargs: Any) -> str:
    with pytest.raises(stat_packs.PackError) as caught:
        stat_packs.install_pack(source, packs_dir, **kwargs)
    assert not (packs_dir / PACK_ID).exists(), "a refused pack must not be written"
    return str(caught.value)


# -- the documented example ---------------------------------------------------


def test_the_documented_example_pack_is_valid() -> None:
    pack = stat_packs.read_pack(EXAMPLE)

    assert pack.id == PACK_ID
    assert [d.name for d in pack.definitions] == ["example.preflop.btn_open", "example.preflop.sb_open"]
    assert [p.id for p in pack.presets] == ["example.preflop.steal_by_position"]


# -- installing and using -------------------------------------------------------


def test_an_installed_pack_lives_in_user_data_and_feeds_the_registry(source: Path, packs_dir: Path) -> None:
    stat_packs.install_pack(source, packs_dir)

    assert (packs_dir / PACK_ID / "manifest.json").is_file()
    registry = analytics_definitions.load_default_registry(packs_dir=packs_dir)
    definition = registry.resolve("example.preflop.btn_open")
    assert stat_packs.pack_of(definition) == PACK_ID
    assert "example.preflop.unopened" in registry.fragments
    # The pack's fragment is merged the way the engine will run it.
    query = analytics_definitions.resolve_query(definition, fragments=registry.fragments)
    assert query.filters["pot_type"] == "unopened"
    # The shipped library is still all there.
    assert "fold_to_3bet_preflop" in registry


def test_the_hud_picker_names_the_pack_a_stat_comes_from(source: Path, packs_dir: Path) -> None:
    stat_packs.install_pack(source, packs_dir)
    registry = analytics_definitions.load_default_registry(packs_dir=packs_dir)

    choices = {choice.name: choice for choice in analytics_choices(registry)}

    assert choices["example.preflop.btn_open"].origin() == f"analytics: {PACK_ID}"
    assert choices["fold_to_3bet_preflop"].origin() == "analytics"


def test_pack_presets_reach_research(source: Path, packs_dir: Path) -> None:
    stat_packs.install_pack(source, packs_dir)

    presets = stat_packs.installed_presets(packs_dir)

    assert [preset.id for preset in presets] == ["example.preflop.steal_by_position"]


def test_the_manager_lists_built_ins_and_installed_packs(source: Path, packs_dir: Path) -> None:
    stat_packs.install_pack(source, packs_dir)

    rows = {row.id: row for row in stat_packs.list_packs(packs_dir)}

    assert rows["builtin"].status == stat_packs.BUILTIN
    assert rows[PACK_ID].status == stat_packs.ENABLED
    assert rows[PACK_ID].definitions == ("example.preflop.btn_open", "example.preflop.sb_open")


def test_a_pack_can_be_disabled_and_enabled_again(source: Path, packs_dir: Path) -> None:
    stat_packs.install_pack(source, packs_dir)

    stat_packs.set_enabled(PACK_ID, False, packs_dir)
    assert "example.preflop.btn_open" not in analytics_definitions.load_default_registry(packs_dir=packs_dir)
    assert {row.id: row.status for row in stat_packs.list_packs(packs_dir)}[PACK_ID] == stat_packs.DISABLED

    stat_packs.set_enabled(PACK_ID, True, packs_dir)
    assert "example.preflop.btn_open" in analytics_definitions.load_default_registry(packs_dir=packs_dir)


def test_a_pack_can_be_uninstalled(source: Path, packs_dir: Path) -> None:
    stat_packs.install_pack(source, packs_dir)
    stat_packs.set_enabled(PACK_ID, False, packs_dir)

    stat_packs.uninstall_pack(PACK_ID, packs_dir)

    assert not (packs_dir / PACK_ID).exists()
    assert [row.id for row in stat_packs.list_packs(packs_dir)] == ["builtin"]
    assert json.loads((packs_dir / "state.json").read_text(encoding="utf-8"))["disabled"] == []


def test_reinstalling_needs_an_explicit_replace(source: Path, packs_dir: Path) -> None:
    stat_packs.install_pack(source, packs_dir)
    with pytest.raises(stat_packs.PackError, match="already installed"):
        stat_packs.install_pack(source, packs_dir)

    edit_manifest(source, pack_version="1.1.0")
    stat_packs.install_pack(source, packs_dir, replace=True)

    assert stat_packs.read_pack(packs_dir / PACK_ID).pack_version == "1.1.0"


# -- export / import ------------------------------------------------------------


def test_export_then_import_round_trips_on_another_installation(source: Path, packs_dir: Path, tmp_path: Path) -> None:
    stat_packs.install_pack(source, packs_dir)
    archive = stat_packs.export_pack(PACK_ID, tmp_path, packs_dir)
    assert archive.name == f"{PACK_ID}.fpdbstats"

    other = tmp_path / "other-install"
    imported = stat_packs.install_pack(archive, other)

    original = stat_packs.read_pack(packs_dir / PACK_ID)
    assert [d.as_dict() for d in imported.definitions] == [d.as_dict() for d in original.definitions]
    assert imported.fragments == original.fragments
    assert [p.id for p in imported.presets] == [p.id for p in original.presets]


def test_export_is_deterministic(source: Path, packs_dir: Path, tmp_path: Path) -> None:
    stat_packs.install_pack(source, packs_dir)

    first = stat_packs.export_pack(PACK_ID, tmp_path / "a.fpdbstats", packs_dir).read_bytes()
    second = stat_packs.export_pack(PACK_ID, tmp_path / "b.fpdbstats", packs_dir).read_bytes()

    assert first == second


def test_an_archive_of_the_pack_folder_installs(source: Path, packs_dir: Path, tmp_path: Path) -> None:
    # What "zip the folder" produces: everything under one top-level directory.
    archive = tmp_path / "zipped.fpdbstats"
    with zipfile.ZipFile(archive, "w") as out:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                out.write(path, f"my-pack/{path.relative_to(source).as_posix()}")

    assert stat_packs.install_pack(archive, packs_dir).id == PACK_ID


# -- identity and collisions ----------------------------------------------------


def test_a_stat_outside_the_pack_namespace_is_refused(source: Path, packs_dir: Path) -> None:
    # A built-in's own name is the case that matters: it can never be taken.
    write_stats(source, [{"name": "fold_to_3bet_preflop", "metric": "fold_frequency"}])

    message = refused(source, packs_dir)

    assert "'fold_to_3bet_preflop' must be namespaced under 'example.preflop.'" in message


def test_two_packs_cannot_define_the_same_name(source: Path, packs_dir: Path, tmp_path: Path) -> None:
    stat_packs.install_pack(source, packs_dir)
    # A deeper namespace can reach a name the first pack already uses.
    second = tmp_path / "second"
    shutil.copytree(source, second)
    edit_manifest(second, id="example.preflop.btn_open", fragments={}, presets=[])
    write_stats(second, [{"name": "example.preflop.btn_open.x", "metric": "fold_frequency"}])
    first = stat_packs.read_pack(packs_dir / PACK_ID)
    write_stats(
        packs_dir / PACK_ID,
        [d.as_dict() for d in first.definitions] + [{"name": "example.preflop.btn_open.x", "metric": "fold_frequency"}],
    )

    with pytest.raises(stat_packs.PackError, match="already defined by installed pack 'example.preflop'"):
        stat_packs.install_pack(second, packs_dir)


def test_a_reserved_or_flat_pack_id_is_refused(source: Path, packs_dir: Path) -> None:
    edit_manifest(source, id="fpdb.core")
    assert "reserved namespace" in refused(source, packs_dir)

    edit_manifest(source, id="mypack")
    assert "dotted lower-case namespace" in refused(source, packs_dir)


# -- versions -------------------------------------------------------------------


def test_a_newer_pack_schema_is_refused_before_installation(source: Path, packs_dir: Path) -> None:
    edit_manifest(source, version=2)

    assert "pack schema version 2 is newer than supported (1)" in refused(source, packs_dir)


def test_a_newer_definition_schema_is_refused(source: Path, packs_dir: Path) -> None:
    edit_manifest(source, definition_schema_version=2)
    assert "definition schema version 2 is newer than supported" in refused(source, packs_dir)

    edit_manifest(source, definition_schema_version=1)
    (source / "stats" / "steals.json").write_text(json.dumps({"schema_version": 2, "stats": []}), encoding="utf-8")
    assert "definition schema version 2 is newer than supported" in refused(source, packs_dir)


def test_a_pack_for_a_newer_fpdb_is_refused(source: Path, packs_dir: Path) -> None:
    edit_manifest(source, min_fpdb_version="99.0")

    assert "needs fpdb 99.0 or newer" in refused(source, packs_dir, fpdb_version="3.9.1")


# -- what a pack cannot contain -------------------------------------------------


@pytest.mark.parametrize(
    ("path", "reason"),
    [
        ("../outside.json", "must stay inside the pack"),
        ("/etc/passwd.json", "must be relative"),
        ("C:/evil.json", "must be relative"),
        ("stats/evil.py", "is not a data file"),
    ],
)
def test_listed_files_must_be_data_inside_the_pack(source: Path, packs_dir: Path, path: str, reason: str) -> None:
    edit_manifest(source, definitions=[path])

    assert reason in refused(source, packs_dir)


def test_sql_or_code_fields_are_refused(source: Path, packs_dir: Path) -> None:
    write_stats(source, [{"name": "example.preflop.x", "metric": "fold_frequency", "sql": "DROP TABLE Hands"}])
    assert "unsupported field(s) ['sql']" in refused(source, packs_dir)

    edit_manifest(source, script="import os")
    assert "unsupported manifest field(s) ['script']" in refused(source, packs_dir)


def test_unknown_metrics_filters_and_values_are_refused(source: Path, packs_dir: Path) -> None:
    write_stats(
        source,
        [
            {"name": "example.preflop.a", "metric": "shell"},
            {"name": "example.preflop.b", "metric": "fold_frequency", "filters": {"table": "Hands"}},
            {"name": "example.preflop.c", "metric": "fold_frequency", "filters": {"position": ["dealer-ish"]}},
            {"name": "example.preflop.d", "metric": "fold_frequency", "fragments": ["nowhere"]},
        ],
    )

    message = refused(source, packs_dir)

    # Every problem at once, so an author fixes the pack in one pass.
    assert "unknown metric 'shell'" in message
    assert "unknown filter 'table'" in message
    assert "Unknown position 'dealer-ish'" in message
    assert "unknown fragment 'nowhere'" in message


def test_an_archive_entry_cannot_escape_the_pack(packs_dir: Path, tmp_path: Path) -> None:
    archive = tmp_path / "slip.fpdbstats"
    with zipfile.ZipFile(archive, "w") as out:
        out.writestr("manifest.json", (EXAMPLE / "manifest.json").read_text(encoding="utf-8"))
        out.writestr("../../escaped.json", "{}")

    with pytest.raises(stat_packs.PackError, match="escapes the pack"):
        stat_packs.install_pack(archive, packs_dir)
    assert not (tmp_path / "escaped.json").exists()


def test_a_symbolic_link_in_a_pack_folder_is_refused(source: Path, packs_dir: Path, tmp_path: Path) -> None:
    secret = tmp_path / "secret.json"
    secret.write_text("{}", encoding="utf-8")
    try:
        (source / "stats" / "linked.json").symlink_to(secret)
    except OSError:
        pytest.skip("symbolic links are not available here")
    edit_manifest(source, definitions=["stats/steals.json", "stats/linked.json"])

    assert "symbolic links are not allowed" in refused(source, packs_dir)


def test_a_linked_folder_in_a_pack_is_refused(source: Path, packs_dir: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    shutil.copy(source / "stats" / "steals.json", outside / "steals.json")
    try:
        (source / "linked").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symbolic links are not available here")
    edit_manifest(source, definitions=["linked/steals.json"])

    assert "symbolic links are not allowed" in refused(source, packs_dir)


def test_a_preset_outside_the_namespace_is_refused(source: Path, packs_dir: Path) -> None:
    presets = json.loads((source / "presets" / "steals.json").read_text(encoding="utf-8"))
    presets["presets"][0]["id"] = "steal_by_position"
    (source / "presets" / "steals.json").write_text(json.dumps(presets), encoding="utf-8")

    assert "preset 'steal_by_position' must be namespaced" in refused(source, packs_dir)


# -- a pack that goes bad after installation ------------------------------------


def test_a_broken_installed_pack_is_reported_and_skipped(source: Path, packs_dir: Path, tmp_path: Path) -> None:
    stat_packs.install_pack(source, packs_dir)
    other = tmp_path / "other"
    shutil.copytree(source, other)
    edit_manifest(other, id="example.other", fragments={}, presets=[])
    write_stats(other, [{"name": "example.other.x", "metric": "fold_frequency"}])
    stat_packs.install_pack(other, packs_dir)
    # Hand-edited into nonsense after installation.
    (packs_dir / PACK_ID / "stats" / "steals.json").write_text("{not json", encoding="utf-8")

    rows = {row.id: row for row in stat_packs.list_packs(packs_dir)}
    registry = analytics_definitions.load_default_registry(packs_dir=packs_dir)

    assert rows[PACK_ID].status == stat_packs.INVALID
    assert "not valid JSON" in rows[PACK_ID].errors[0]
    assert "example.preflop.btn_open" not in registry
    assert "example.other.x" in registry  # the healthy pack still loads


# -- review hardening (PR #411) ----------------------------------------------


def test_text_that_is_not_utf8_is_a_pack_error(source: Path, packs_dir: Path) -> None:
    (source / "stats" / "steals.json").write_bytes(b"\xff\xfe{}")

    assert "is not UTF-8 text" in refused(source, packs_dir)


def test_yaml_files_are_refused_in_a_pack(source: Path, packs_dir: Path) -> None:
    # A shared pack must install on every fpdb, and fpdb does not ship PyYAML.
    (source / "stats" / "more.yaml").write_text("stats: []", encoding="utf-8")
    edit_manifest(source, definitions=["stats/steals.json", "stats/more.yaml"])

    assert "'stats/more.yaml' is not a data file; allowed suffixes: ['.json']" in refused(source, packs_dir)


def test_a_nested_fragment_list_must_be_names(source: Path, packs_dir: Path) -> None:
    edit_manifest(source, fragments={"example.preflop.unopened": {"street": "preflop", "fragments": 5}})

    assert "fragments must be a list of fragment names" in refused(source, packs_dir)


def test_a_preset_of_the_wrong_shape_is_reported_not_raised(source: Path, packs_dir: Path) -> None:
    presets = json.loads((source / "presets" / "steals.json").read_text(encoding="utf-8"))
    presets["presets"][0]["group_by"] = 7
    (source / "presets" / "steals.json").write_text(json.dumps(presets), encoding="utf-8")

    assert "presets/steals.json" in refused(source, packs_dir)


def test_a_failed_replacement_keeps_the_previous_install(
    source: Path, packs_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stat_packs.install_pack(source, packs_dir)
    edit_manifest(source, pack_version="2.0.0")
    real_rename = Path.rename

    def failing_rename(self: Path, target: Any) -> Any:
        # Moving the old install aside works; moving the new one in does not.
        if self.name.startswith(f".{PACK_ID}.") and not self.name.endswith(".previous"):
            raise OSError("disk full")
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", failing_rename)
    with pytest.raises(OSError, match="disk full"):
        stat_packs.install_pack(source, packs_dir, replace=True)
    monkeypatch.undo()

    assert stat_packs.read_pack(packs_dir / PACK_ID).pack_version == "1.0.0"
    assert not any(path.name.startswith(".") for path in packs_dir.iterdir() if path.is_dir())


def test_a_folder_holding_another_pack_is_invalid_and_removable(source: Path, packs_dir: Path) -> None:
    stat_packs.install_pack(source, packs_dir)
    shutil.copytree(packs_dir / PACK_ID, packs_dir / "renamed-by-hand")

    rows = {row.id: row for row in stat_packs.list_packs(packs_dir)}
    assert rows["renamed-by-hand"].status == stat_packs.INVALID

    stat_packs.uninstall_pack("renamed-by-hand", packs_dir)

    assert not (packs_dir / "renamed-by-hand").exists()
    assert (packs_dir / PACK_ID).is_dir()  # the real pack is untouched


@pytest.mark.parametrize("folder", ["..", "../elsewhere", ".hidden", "a/b", ""])
def test_uninstall_only_reaches_pack_folders(packs_dir: Path, folder: str) -> None:
    packs_dir.mkdir(parents=True)
    with pytest.raises(stat_packs.PackError):
        stat_packs.uninstall_pack(folder, packs_dir)


def test_a_failed_state_write_keeps_the_previous_state(
    source: Path, packs_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stat_packs.install_pack(source, packs_dir)
    stat_packs.set_enabled(PACK_ID, False, packs_dir)

    def failing_replace(*_args: Any) -> None:
        raise OSError("interrupted")

    monkeypatch.setattr(stat_packs.os, "replace", failing_replace)
    with pytest.raises(OSError, match="interrupted"):
        stat_packs.set_enabled(PACK_ID, True, packs_dir)
    monkeypatch.undo()

    assert {row.id: row.status for row in stat_packs.list_packs(packs_dir)}[PACK_ID] == stat_packs.DISABLED
    assert [path.name for path in packs_dir.iterdir() if path.name.startswith(".state")] == []


# -- second review round (PR #411) ---------------------------------------------


@pytest.mark.parametrize("spelling", ["./stats/steals.json", "stats//steals.json"])
def test_a_listed_path_must_be_spelled_canonically(source: Path, packs_dir: Path, spelling: str) -> None:
    edit_manifest(source, definitions=[spelling])

    assert "must be written 'stats/steals.json'" in refused(source, packs_dir)


def test_a_zip_bomb_is_stopped(packs_dir: Path, tmp_path: Path) -> None:
    archive = tmp_path / "bomb.fpdbstats"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as out:
        out.writestr("manifest.json", (EXAMPLE / "manifest.json").read_text(encoding="utf-8"))
        out.writestr("stats/steals.json", b" " * (stat_packs.MAX_ARCHIVE_BYTES + 1))

    with pytest.raises(stat_packs.PackError, match="compressed suspiciously well|larger than"):
        stat_packs.install_pack(archive, packs_dir)


def test_an_interrupted_replacement_is_recovered(source: Path, packs_dir: Path) -> None:
    stat_packs.install_pack(source, packs_dir)
    # fpdb stopped after moving the old install aside, before the new one moved in.
    (packs_dir / PACK_ID).rename(packs_dir / f".{PACK_ID}.previous")

    rows = {row.id: row.status for row in stat_packs.list_packs(packs_dir)}

    assert rows[PACK_ID] == stat_packs.ENABLED
    assert not (packs_dir / f".{PACK_ID}.previous").exists()


def test_two_enabled_packs_cannot_both_load_a_preset_id(source: Path, packs_dir: Path) -> None:
    stat_packs.install_pack(source, packs_dir)
    # Folders edited by hand, bypassing the install-time checks: a deeper
    # namespace reaches the same preset id as the first pack.
    duplicate = "example.preflop.x.dup"
    first = packs_dir / PACK_ID / "presets" / "steals.json"
    presets = json.loads(first.read_text(encoding="utf-8"))
    presets["presets"][0]["id"] = duplicate
    first.write_text(json.dumps(presets), encoding="utf-8")
    clone = packs_dir / "example.preflop.x"
    shutil.copytree(packs_dir / PACK_ID, clone)
    edit_manifest(clone, id="example.preflop.x", fragments={}, definitions=[])

    assert {row.id: row.status for row in stat_packs.list_packs(packs_dir)}["example.preflop.x"] == stat_packs.ENABLED
    presets_loaded = [preset.id for preset in stat_packs.installed_presets(packs_dir)]

    assert presets_loaded.count(duplicate) == 1


# -- third review round (PR #411) ----------------------------------------------


def test_a_corrupt_archive_entry_is_a_pack_error(source: Path, packs_dir: Path, tmp_path: Path) -> None:
    archive = tmp_path / "corrupt.fpdbstats"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as out:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                out.write(path, path.relative_to(source).as_posix())
    # Flip a byte inside the stored manifest: its CRC no longer matches.
    data = bytearray(archive.read_bytes())
    offset = data.index(b'"schema"')
    data[offset + 1] ^= 0x20
    archive.write_bytes(bytes(data))

    with pytest.raises(stat_packs.PackError, match="the archive cannot be read"):
        stat_packs.install_pack(archive, packs_dir)


def test_a_preset_id_repeated_in_another_file_is_refused(source: Path, packs_dir: Path) -> None:
    shutil.copy(source / "presets" / "steals.json", source / "presets" / "again.json")
    edit_manifest(source, presets=["presets/steals.json", "presets/again.json"])

    assert "preset 'example.preflop.steal_by_position' is defined twice" in refused(source, packs_dir)


@pytest.mark.parametrize("disabled", [[{}], [["x"]], [3, None], "example.preflop"])
def test_a_malformed_state_file_leaves_packs_enabled(source: Path, packs_dir: Path, disabled: Any) -> None:
    stat_packs.install_pack(source, packs_dir)
    (packs_dir / "state.json").write_text(json.dumps({"disabled": disabled}), encoding="utf-8")

    rows = {row.id: row.status for row in stat_packs.list_packs(packs_dir)}

    assert rows[PACK_ID] == stat_packs.ENABLED
    assert "example.preflop.btn_open" in analytics_definitions.load_default_registry(packs_dir=packs_dir)


def test_a_malformed_state_entry_does_not_hide_a_valid_one(source: Path, packs_dir: Path) -> None:
    stat_packs.install_pack(source, packs_dir)
    (packs_dir / "state.json").write_text(json.dumps({"disabled": [{}, PACK_ID]}), encoding="utf-8")

    assert {row.id: row.status for row in stat_packs.list_packs(packs_dir)}[PACK_ID] == stat_packs.DISABLED



# -- fourth review round (PR #411) ---------------------------------------------


def test_a_folder_import_reads_only_what_the_manifest_lists(
    source: Path, packs_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A pack unpacked beside something large and unrelated.
    (source / "movie.bin").write_bytes(b"x" * 64)
    read: list[str] = []
    real_read_bytes = Path.read_bytes

    def tracking_read_bytes(self: Path) -> bytes:
        read.append(self.name)
        return real_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", tracking_read_bytes)
    stat_packs.install_pack(source, packs_dir)

    assert "movie.bin" not in read
    assert not (packs_dir / PACK_ID / "movie.bin").exists()


def test_a_listed_file_over_the_size_limit_is_refused(
    source: Path, packs_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(stat_packs, "MAX_ARCHIVE_BYTES", 100)

    assert "larger than 100 bytes" in refused(source, packs_dir)


def test_names_differing_only_by_case_are_refused(packs_dir: Path, tmp_path: Path) -> None:
    archive = tmp_path / "case.fpdbstats"
    stats = (EXAMPLE / "stats" / "steals.json").read_text(encoding="utf-8")
    manifest = json.loads((EXAMPLE / "manifest.json").read_text(encoding="utf-8"))
    manifest["definitions"] = ["stats/Steals.json", "stats/steals.json"]
    manifest["presets"] = []
    with zipfile.ZipFile(archive, "w") as out:
        out.writestr("manifest.json", json.dumps(manifest))
        out.writestr("stats/Steals.json", stats.replace("btn_open", "btn_open2").replace("sb_open", "sb_open2"))
        out.writestr("stats/steals.json", stats)

    with pytest.raises(stat_packs.PackError, match="name the same file on some systems"):
        stat_packs.install_pack(archive, packs_dir)


@pytest.mark.parametrize(
    ("filters", "reason"),
    [
        # Refused first as a shape Research cannot hold, then by the compiler.
        ({"effective_stack_bb": [10, 20, 30]}, "[low, high]"),
        ({"effective_stack_bb": 15}, "[low, high]"),
        ({"position": ["dealer-ish"]}, "Unknown position 'dealer-ish'"),
    ],
)
def test_a_preset_with_a_value_the_engine_cannot_run_is_refused(
    source: Path, packs_dir: Path, filters: dict[str, Any], reason: str
) -> None:
    presets = json.loads((source / "presets" / "steals.json").read_text(encoding="utf-8"))
    presets["presets"][0]["filters"] = filters
    (source / "presets" / "steals.json").write_text(json.dumps(presets), encoding="utf-8")

    message = refused(source, packs_dir)

    assert "preset 'example.preflop.steal_by_position'" in message
    assert reason in message


# -- fifth review round (PR #411) ----------------------------------------------


def test_an_oversized_archive_is_refused_before_it_is_opened(
    packs_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "huge.fpdbstats"
    with zipfile.ZipFile(archive, "w") as out:
        out.writestr("manifest.json", (EXAMPLE / "manifest.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(stat_packs, "MAX_ARCHIVE_BYTES", 10)
    opened: list[Any] = []
    monkeypatch.setattr(stat_packs.zipfile, "ZipFile", lambda *args, **kwargs: opened.append(args))

    with pytest.raises(stat_packs.PackError, match="the archive is larger than 10 bytes"):
        stat_packs.install_pack(archive, packs_dir)
    assert opened == []


@pytest.mark.parametrize(
    ("path", "reason"),
    [
        ("stats./steals.json", "ending in a dot or a space"),
        ("stats /steals.json", "ending in a dot or a space"),
        ("stats/con.json", "reserved Windows name 'con'"),
        ("stats/NUL.json", "reserved Windows name 'NUL'"),
        ("stats/what?.json", "character Windows does not allow"),
        ("stats/a:b.json", "character Windows does not allow"),
    ],
)
def test_paths_that_alias_or_fail_on_windows_are_refused(
    source: Path, packs_dir: Path, path: str, reason: str
) -> None:
    edit_manifest(source, definitions=[path])

    assert reason in refused(source, packs_dir)


@pytest.mark.parametrize("name", ["example.preflop.bad\x00name", "example.preflop.two words", "example.preflop.a<b>"])
def test_a_name_that_is_not_an_identifier_is_refused(source: Path, packs_dir: Path, name: str) -> None:
    # Such a name ends up in HUD_config.xml once the stat is put on a HUD.
    write_stats(source, [{"name": name, "metric": "fold_frequency"}])

    assert "may only use letters, digits" in refused(source, packs_dir)


def test_fragment_and_preset_names_are_identifiers_too(source: Path, packs_dir: Path) -> None:
    edit_manifest(source, fragments={"example.preflop.un opened": {"street": "preflop"}})
    assert "fragment 'example.preflop.un opened' may only use" in refused(source, packs_dir)

    edit_manifest(source, fragments={"example.preflop.unopened": {"street": "preflop", "pot_type": "unopened"}})
    presets = json.loads((source / "presets" / "steals.json").read_text(encoding="utf-8"))
    presets["presets"][0]["id"] = "example.preflop.steal\tby"
    (source / "presets" / "steals.json").write_text(json.dumps(presets), encoding="utf-8")
    assert "may only use letters, digits" in refused(source, packs_dir)


# -- sixth review round (PR #411) ----------------------------------------------


@pytest.mark.parametrize(
    "filters",
    [{"bet_sizing_pct": [{}, 50]}, {"bet_sizing_pct": [None, "x"]}],
)
def test_a_malformed_filter_value_is_a_pack_error(source: Path, packs_dir: Path, filters: dict[str, Any]) -> None:
    write_stats(source, [{"name": "example.preflop.x", "metric": "fold_frequency", "filters": filters}])

    assert "stat 'example.preflop.x'" in refused(source, packs_dir)


@pytest.mark.parametrize("pack_id", ["con.stats", "aux.pack", "nul.x", "lpt1.x"])
def test_a_pack_id_windows_cannot_use_as_a_folder_is_refused(source: Path, packs_dir: Path, pack_id: str) -> None:
    edit_manifest(source, id=pack_id)

    assert "reserved Windows name" in refused(source, packs_dir)


def test_an_uninstall_that_cannot_update_the_state_still_succeeds(
    source: Path, packs_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stat_packs.install_pack(source, packs_dir)
    stat_packs.set_enabled(PACK_ID, False, packs_dir)

    def locked(*_args: Any) -> None:
        raise OSError("state.json is locked")

    monkeypatch.setattr(stat_packs.os, "replace", locked)
    stat_packs.uninstall_pack(PACK_ID, packs_dir)  # no exception: the pack is gone

    assert not (packs_dir / PACK_ID).exists()
    assert [row.id for row in stat_packs.list_packs(packs_dir)] == ["builtin"]


def test_a_pack_recovered_from_an_interrupted_replacement_is_not_silently_replaced(
    source: Path, packs_dir: Path
) -> None:
    stat_packs.install_pack(source, packs_dir)
    (packs_dir / PACK_ID).rename(packs_dir / f".{PACK_ID}.previous")
    edit_manifest(source, pack_version="2.0.0")

    with pytest.raises(stat_packs.PackError, match="already installed"):
        stat_packs.install_pack(source, packs_dir)

    assert stat_packs.read_pack(packs_dir / PACK_ID).pack_version == "1.0.0"


# -- seventh review round (PR #411) --------------------------------------------


def test_a_fresh_install_does_not_inherit_a_stale_disabled_flag(source: Path, packs_dir: Path) -> None:
    stat_packs.install_pack(source, packs_dir)
    stat_packs.set_enabled(PACK_ID, False, packs_dir)
    # An uninstall whose state update failed leaves the flag behind.
    shutil.rmtree(packs_dir / PACK_ID)

    stat_packs.install_pack(source, packs_dir)

    assert {row.id: row.status for row in stat_packs.list_packs(packs_dir)}[PACK_ID] == stat_packs.ENABLED


def test_a_replacement_keeps_the_disabled_choice(source: Path, packs_dir: Path) -> None:
    stat_packs.install_pack(source, packs_dir)
    stat_packs.set_enabled(PACK_ID, False, packs_dir)

    stat_packs.install_pack(source, packs_dir, replace=True)

    assert {row.id: row.status for row in stat_packs.list_packs(packs_dir)}[PACK_ID] == stat_packs.DISABLED


def test_a_number_too_large_for_a_float_is_a_pack_error(source: Path, packs_dir: Path) -> None:
    huge = int("9" * 400)
    presets = json.loads((source / "presets" / "steals.json").read_text(encoding="utf-8"))
    presets["presets"][0]["filters"] = {"bet_sizing_pct": [1, huge]}
    (source / "presets" / "steals.json").write_text(json.dumps(presets), encoding="utf-8")
    write_stats(source, [{"name": "example.preflop.x", "metric": "fold_frequency", "filters": {"bet_sizing_pct": [1, huge]}}])

    message = refused(source, packs_dir)

    assert "preset 'example.preflop.steal_by_position'" in message
    assert "stat 'example.preflop.x'" in message


# -- eighth review round (PR #411) ---------------------------------------------


def test_a_name_ending_in_a_newline_is_refused(source: Path, packs_dir: Path) -> None:
    # "$" matches before a final newline; the XML attribute would turn it into
    # a space and the stat on the HUD would no longer resolve.
    write_stats(source, [{"name": "example.preflop.bad\n", "metric": "fold_frequency"}])

    assert "may only use letters, digits" in refused(source, packs_dir)


def test_a_pack_id_ending_in_a_newline_is_refused(source: Path, packs_dir: Path) -> None:
    edit_manifest(source, id="example.preflop\n")

    assert "dotted lower-case namespace" in refused(source, packs_dir)


# -- ninth review round (PR #411) ----------------------------------------------


@pytest.mark.parametrize(
    "bounds",
    [["low", "high"], [10, "20"], {"min": "a"}, [True, 5], [float("inf"), 5]],
)
def test_range_bounds_must_be_numbers(source: Path, packs_dir: Path, bounds: Any) -> None:
    presets = json.loads((source / "presets" / "steals.json").read_text(encoding="utf-8"))
    presets["presets"][0]["filters"] = {"effective_stack_bb": bounds}
    (source / "presets" / "steals.json").write_text(json.dumps(presets), encoding="utf-8")
    write_stats(source, [{"name": "example.preflop.x", "metric": "fold_frequency", "filters": {"effective_stack_bb": bounds}}])

    message = refused(source, packs_dir)

    assert "preset 'example.preflop.steal_by_position'" in message
    assert "stat 'example.preflop.x'" in message
    assert "needs numbers for its bounds" in message


def test_an_open_range_bound_is_accepted(source: Path, packs_dir: Path) -> None:
    write_stats(source, [{"name": "example.preflop.x", "metric": "fold_frequency", "filters": {"effective_stack_bb": [None, 40]}}])

    assert stat_packs.install_pack(source, packs_dir).definitions[0].name == "example.preflop.x"


def test_json_nested_too_deeply_is_a_pack_error(source: Path, packs_dir: Path) -> None:
    (source / "stats" / "steals.json").write_text("[" * 100_000 + "]" * 100_000, encoding="utf-8")

    assert "nested too deeply to read" in refused(source, packs_dir)


def test_names_equal_after_unicode_normalization_are_refused(packs_dir: Path, tmp_path: Path) -> None:
    composed, decomposed = "stats/é.json", "stats/é.json"  # the same "é", two spellings
    archive = tmp_path / "unicode.fpdbstats"
    manifest = json.loads((EXAMPLE / "manifest.json").read_text(encoding="utf-8"))
    manifest["definitions"] = [composed, decomposed]
    manifest["presets"] = []
    stats = (EXAMPLE / "stats" / "steals.json").read_text(encoding="utf-8")
    with zipfile.ZipFile(archive, "w") as out:
        out.writestr("manifest.json", json.dumps(manifest))
        out.writestr(composed, stats)
        out.writestr(decomposed, stats.replace("btn_open", "btn_open2").replace("sb_open", "sb_open2"))

    with pytest.raises(stat_packs.PackError, match="name the same file on some systems"):
        stat_packs.install_pack(archive, packs_dir)


# -- tenth review round (PR #411) ----------------------------------------------


@pytest.mark.parametrize(
    ("name", "value"),
    [("in_position", "false"), ("multiway", 0), ("tournament", "yes"), ("hero", None)],
)
def test_boolean_filters_need_true_or_false(source: Path, packs_dir: Path, name: str, value: Any) -> None:
    # bool("false") is True: the stat would measure the opposite of its label.
    write_stats(source, [{"name": "example.preflop.x", "metric": "fold_frequency", "filters": {name: value}}])

    assert f"filter {name!r} needs true or false" in refused(source, packs_dir)


def test_a_boolean_from_a_fragment_is_checked_too(source: Path, packs_dir: Path) -> None:
    edit_manifest(source, fragments={"example.preflop.unopened": {"street": "preflop", "in_position": "no"}})

    assert "filter 'in_position' needs true or false" in refused(source, packs_dir)


@pytest.mark.parametrize("filters", [{"date_from": "2026-01-01"}, {"hand_id_to": 10}])
def test_a_preset_cannot_store_a_one_sided_window(source: Path, packs_dir: Path, filters: dict[str, Any]) -> None:
    presets = json.loads((source / "presets" / "steals.json").read_text(encoding="utf-8"))
    presets["presets"][0]["filters"] = {**presets["presets"][0]["filters"], **filters}
    (source / "presets" / "steals.json").write_text(json.dumps(presets), encoding="utf-8")

    assert "is chosen in Research, not stored in a preset" in refused(source, packs_dir)


# -- eleventh review round (PR #411) -------------------------------------------


@pytest.mark.parametrize("flag", ["false", 0, None])
def test_an_is_null_flag_needs_true_or_false(source: Path, packs_dir: Path, flag: Any) -> None:
    # {"is_null": "false"} compiles to IS NULL: the opposite of what it says.
    write_stats(source, [{"name": "example.preflop.x", "metric": "fold_frequency", "filters": {"position": {"is_null": flag}}}])

    assert "needs is_null to be true or false" in refused(source, packs_dir)


def test_a_boolean_is_null_flag_is_accepted(source: Path, packs_dir: Path) -> None:
    write_stats(source, [{"name": "example.preflop.x", "metric": "fold_frequency", "filters": {"position": {"is_null": False}}}])

    assert stat_packs.install_pack(source, packs_dir).definitions[0].name == "example.preflop.x"


@pytest.mark.parametrize("bounds", [{"minimum": 10, "maximum": 20}, {"min": 10, "high": 20}, {}, {"min": None}])
def test_a_range_mapping_takes_only_min_and_max(source: Path, packs_dir: Path, bounds: dict[str, Any]) -> None:
    # Misspelled keys read as an unbounded range: the constraint would vanish.
    write_stats(source, [{"name": "example.preflop.x", "metric": "fold_frequency", "filters": {"effective_stack_bb": bounds}}])

    assert "takes min and/or max" in refused(source, packs_dir)


def test_a_range_mapping_with_one_bound_is_accepted(source: Path, packs_dir: Path) -> None:
    write_stats(source, [{"name": "example.preflop.x", "metric": "fold_frequency", "filters": {"effective_stack_bb": {"max": 40}}}])

    assert stat_packs.install_pack(source, packs_dir).definitions[0].name == "example.preflop.x"


# -- twelfth review round (PR #411) --------------------------------------------


def test_an_integer_past_pythons_digit_limit_is_a_pack_error(source: Path, packs_dir: Path) -> None:
    # json.loads raises a plain ValueError here, not JSONDecodeError.
    (source / "stats" / "steals.json").write_text('{"schema_version": ' + "9" * 5000 + "}", encoding="utf-8")

    assert "stats/steals.json is not valid JSON" in refused(source, packs_dir)


def test_display_precision_is_bounded(source: Path, packs_dir: Path) -> None:
    write_stats(source, [{"name": "example.preflop.x", "metric": "fold_frequency", "precision": 100_000_000}])

    assert f"precision must be at most {stat_packs.MAX_PRECISION}" in refused(source, packs_dir)


@pytest.mark.parametrize("value", [{"unexpected": "value"}, [["PokerStars"]], [None], None])
def test_a_set_filter_takes_values_not_structures(source: Path, packs_dir: Path, value: Any) -> None:
    write_stats(source, [{"name": "example.preflop.x", "metric": "fold_frequency", "filters": {"site": value}}])

    assert "filter 'site' takes a value or a list of values" in refused(source, packs_dir)


def test_a_set_filter_keeps_its_is_null_form(source: Path, packs_dir: Path) -> None:
    write_stats(source, [{"name": "example.preflop.x", "metric": "fold_frequency", "filters": {"site": {"is_null": False}}}])

    assert stat_packs.install_pack(source, packs_dir).definitions[0].name == "example.preflop.x"


# -- thirteenth review round (PR #411) -----------------------------------------


def test_a_preset_cannot_use_the_is_null_form(source: Path, packs_dir: Path) -> None:
    # A Research filter row would turn it into the text "{'is_null': False}".
    presets = json.loads((source / "presets" / "steals.json").read_text(encoding="utf-8"))
    presets["presets"][0]["filters"] = {**presets["presets"][0]["filters"], "site": {"is_null": False}}
    (source / "presets" / "steals.json").write_text(json.dumps(presets), encoding="utf-8")

    assert "cannot use is_null in a preset" in refused(source, packs_dir)


@pytest.mark.parametrize(("name", "value"), [("hand_id_from", [10, 20]), ("date_to", {"max": "2026-01-01"}), ("date_from", None), ("hand_id_to", True)])
def test_a_one_sided_range_in_a_definition_takes_one_value(
    source: Path, packs_dir: Path, name: str, value: Any
) -> None:
    write_stats(source, [{"name": "example.preflop.x", "metric": "fold_frequency", "filters": {name: value}}])

    assert f"filter {name!r} takes a single date or number" in refused(source, packs_dir)


@pytest.mark.parametrize(("name", "value"), [("hand_id_from", 10), ("date_from", "2026-01-01")])
def test_a_one_sided_range_in_a_definition_is_accepted(source: Path, packs_dir: Path, name: str, value: Any) -> None:
    write_stats(source, [{"name": "example.preflop.x", "metric": "fold_frequency", "filters": {name: value}}])

    assert stat_packs.install_pack(source, packs_dir).definitions[0].name == "example.preflop.x"


# -- fourteenth review round (PR #411) -----------------------------------------


def _preset_with(source: Path, **filters: Any) -> None:
    presets = json.loads((source / "presets" / "steals.json").read_text(encoding="utf-8"))
    presets["presets"][0]["filters"] = {**presets["presets"][0]["filters"], **filters}
    (source / "presets" / "steals.json").write_text(json.dumps(presets), encoding="utf-8")


def test_a_preset_range_is_written_as_low_and_high(source: Path, packs_dir: Path) -> None:
    # Research's range control only reads [low, high]; a mapping leaves it at defaults.
    _preset_with(source, effective_stack_bb={"min": 10, "max": 20})

    assert "must be written [low, high] in a preset" in refused(source, packs_dir)


@pytest.mark.parametrize(
    "filters",
    [{"identity": [["PokerStars", "Hero"]]}, {"site": ["Poker, Stars"]}, {"site": [1.5]}],
)
def test_a_preset_text_filter_must_survive_the_research_control(
    source: Path, packs_dir: Path, filters: dict[str, Any]
) -> None:
    _preset_with(source, **filters)

    assert "takes words or whole numbers without commas" in refused(source, packs_dir)


def test_a_preset_identity_in_site_alias_form_is_accepted(source: Path, packs_dir: Path) -> None:
    _preset_with(source, identity=["PokerStars:Hero"], effective_stack_bb=[10, 20])

    assert [p.id for p in stat_packs.install_pack(source, packs_dir).presets] == ["example.preflop.steal_by_position"]


# -- fifteenth review round (PR #411) ------------------------------------------


@pytest.mark.parametrize(
    "filters",
    # Flag filters (draw, board_texture) are already refused by the compiler.
    [{"situation": {"unexpected": "value"}}, {"situation": [["facing_3bet"]]}],
)
def test_label_and_flag_filters_take_values_not_structures(
    source: Path, packs_dir: Path, filters: dict[str, Any]
) -> None:
    # A label mapping is stringified into its LIKE pattern and matches nothing.
    write_stats(source, [{"name": "example.preflop.x", "metric": "fold_frequency", "filters": filters}])

    name = next(iter(filters))
    assert f"filter {name!r} takes a value or a list of values" in refused(source, packs_dir)


def test_a_label_value_is_accepted(source: Path, packs_dir: Path) -> None:
    write_stats(source, [{"name": "example.preflop.x", "metric": "fold_frequency", "filters": {"situation": "facing_3bet"}}])

    assert stat_packs.install_pack(source, packs_dir).definitions[0].name == "example.preflop.x"


# -- sixteenth review round (PR #411) ------------------------------------------


def test_a_fragment_chain_too_deep_to_expand_is_a_pack_error(source: Path, packs_dir: Path) -> None:
    depth = 3000
    fragments = {
        f"example.preflop.f{i}": {"street": "preflop", "fragments": [f"example.preflop.f{i + 1}"]}
        for i in range(depth)
    }
    fragments[f"example.preflop.f{depth}"] = {"street": "preflop"}
    edit_manifest(source, fragments=fragments, presets=[])
    write_stats(source, [{"name": "example.preflop.x", "metric": "fold_frequency", "fragments": ["example.preflop.f0"]}])

    assert "its fragments are nested too deeply" in refused(source, packs_dir)


# -- seventeenth review round (PR #411) ----------------------------------------


def test_a_bad_denominator_value_is_not_hidden_by_the_numerator(source: Path, packs_dir: Path) -> None:
    write_stats(
        source,
        [
            {
                "name": "example.preflop.x",
                "metric": "action_frequency",
                "filters": {"in_position": "false"},
                "numerator": {"in_position": True},
            },
        ],
    )

    assert "filter 'in_position' needs true or false, not 'false'" in refused(source, packs_dir)


def test_a_bad_preset_denominator_is_not_hidden_by_the_numerator(source: Path, packs_dir: Path) -> None:
    presets = json.loads((source / "presets" / "steals.json").read_text(encoding="utf-8"))
    presets["presets"][0]["filters"] = {**presets["presets"][0]["filters"], "in_position": "false"}
    presets["presets"][0]["numerator"] = {"in_position": True}
    (source / "presets" / "steals.json").write_text(json.dumps(presets), encoding="utf-8")

    assert "filter 'in_position' needs true or false, not 'false'" in refused(source, packs_dir)


# -- eighteenth review round (PR #411) -----------------------------------------


@pytest.mark.parametrize(
    ("name", "value", "written"),
    [
        ("hand_id", float("nan"), "NaN"),
        ("pot_type", float("inf"), "Infinity"),
        ("site", [float("-inf")], "-Infinity"),
        ("hand_id_from", float("nan"), "NaN"),
        ("date_to", float("inf"), "Infinity"),
    ],
)
def test_a_filter_value_must_be_a_finite_number(
    source: Path, packs_dir: Path, name: str, value: Any, written: str
) -> None:
    # json.dumps writes NaN and Infinity as those bare constants and Python's
    # parser reads them back, so a hand-written pack can carry one. Bound as a
    # parameter it matches nothing on SQLite: the stat reports an empty
    # population instead of failing where anyone can see it.
    write_stats(source, [{"name": "example.preflop.x", "metric": "fold_frequency", "filters": {name: value}}])
    assert written in (source / "stats" / "steals.json").read_text(encoding="utf-8")

    assert f"filter {name!r} needs a finite number" in refused(source, packs_dir)


def test_a_finite_number_is_still_a_filter_value(source: Path, packs_dir: Path) -> None:
    write_stats(source, [{"name": "example.preflop.x", "metric": "fold_frequency", "filters": {"hand_id": 7}}])

    assert stat_packs.install_pack(source, packs_dir).definitions[0].name == "example.preflop.x"


def _pack_named(pack: Path, pack_id: str) -> None:
    """The example pack, with every name it adds re-spelled under ``pack_id``."""
    edit_manifest(pack, id=pack_id, fragments={}, presets=[])
    write_stats(pack, [{"name": f"{pack_id}.x", "metric": "fold_frequency"}])


def test_a_pack_id_at_the_length_limit_is_accepted(packs_dir: Path, tmp_path: Path) -> None:
    pack = tmp_path / "long-id-pack"
    shutil.copytree(EXAMPLE, pack)
    longest = "a." + "b" * (stat_packs.MAX_ID_LENGTH - 2)
    _pack_named(pack, longest)

    assert stat_packs.install_pack(pack, packs_dir).id == longest


def test_a_pack_id_past_the_length_limit_is_refused(packs_dir: Path, tmp_path: Path) -> None:
    # The id names the install folder, and fpdb writes a staging folder and a
    # backup beside it, each ten characters longer. Past that the id validated
    # and the install failed with ENAMETOOLONG -- which the dialog reported as
    # a read failure.
    pack = tmp_path / "long-id-pack"
    shutil.copytree(EXAMPLE, pack)
    _pack_named(pack, "a." + "b" * (stat_packs.MAX_ID_LENGTH - 1))

    with pytest.raises(stat_packs.PackError, match=f"longer than {stat_packs.MAX_ID_LENGTH} characters"):
        stat_packs.install_pack(pack, packs_dir)


def _archive_naming(tmp_path: Path, listed: str) -> Path:
    """A one-stat archive whose definition file is called ``listed``."""
    manifest = json.loads((EXAMPLE / "manifest.json").read_text(encoding="utf-8"))
    manifest["definitions"] = [listed]
    manifest["presets"] = []
    archive = tmp_path / "long-name.fpdbstats"
    with zipfile.ZipFile(archive, "w") as out:
        out.writestr("manifest.json", json.dumps(manifest))
        out.writestr(listed, (EXAMPLE / "stats" / "steals.json").read_text(encoding="utf-8"))
    return archive


def test_a_file_name_at_the_length_limit_is_accepted(packs_dir: Path, tmp_path: Path) -> None:
    listed = f"stats/{'a' * (stat_packs.MAX_NAME_BYTES - len('.json'))}.json"

    assert stat_packs.install_pack(_archive_naming(tmp_path, listed), packs_dir).definitions


def test_a_file_name_past_the_length_limit_is_refused(packs_dir: Path, tmp_path: Path) -> None:
    # An archive can carry a name no file system accepts, so the install would
    # have failed on it after the pack had been accepted.
    listed = f"stats/{'a' * stat_packs.MAX_NAME_BYTES}.json"

    with pytest.raises(stat_packs.PackError, match=f"longer than {stat_packs.MAX_NAME_BYTES} bytes"):
        stat_packs.install_pack(_archive_naming(tmp_path, listed), packs_dir)


def test_a_preset_range_needs_at_least_one_bound(source: Path, packs_dir: Path) -> None:
    # Neither bound is not a filter: the control reads it back as an empty row.
    _preset_with(source, effective_stack_bb=[None, None])

    assert "needs at least one bound in a preset" in refused(source, packs_dir)


@pytest.mark.parametrize("bounds", [[None, 40], [10, None]])
def test_a_preset_range_with_one_bound_is_accepted(source: Path, packs_dir: Path, bounds: list[Any]) -> None:
    # The range control reads a blank bound back as null, so an open bound
    # means "up to 40" and not "0 to 40" (the Qt test drives the control).
    _preset_with(source, effective_stack_bb=bounds)

    assert [p.id for p in stat_packs.install_pack(source, packs_dir).presets] == ["example.preflop.steal_by_position"]


# -- review of 17ac9c03 (PR #411) ------------------------------------------------


@pytest.mark.parametrize(
    "path",
    ["/".join(["d"] * 1800) + "/x.json", "/".join(["d"] * 9) + "/x.json", "/".join(["a" * 200] * 3) + ".json"],
)
def test_a_listed_path_too_deep_or_too_long_is_refused(source: Path, packs_dir: Path, path: str) -> None:
    # 1,800 nested folders made mkdir(parents=True) recurse past Python's limit.
    edit_manifest(source, definitions=[path])

    assert "is too deep or too long" in refused(source, packs_dir)


# -- review of 69b83549 (PR #411) ------------------------------------------------


@pytest.mark.parametrize(
    "filters",
    [{"hand_id": 10**100}, {"hand_id": [1, 10**100]}, {"effective_stack_bb": [1, 10**100]}, {"hand_id_from": 10**100}],
)
def test_a_number_too_large_for_the_database_is_refused(source: Path, packs_dir: Path, filters: dict[str, Any]) -> None:
    # Binding it fails only when the stat runs: "Python int too large to convert to SQLite INTEGER".
    write_stats(source, [{"name": "example.preflop.x", "metric": "fold_frequency", "filters": filters}])

    assert "too large for the database" in refused(source, packs_dir)


@pytest.mark.parametrize(
    ("bounds", "reason"),
    [
        ([10.001, 20], "more than 2 decimals"),
        ([10, 20_000_000], "outside what Research can show"),
        ([-10_000_000, 20], "outside what Research can show"),  # the minimum reads as "no bound"
    ],
)
def test_a_preset_range_must_fit_its_control(source: Path, packs_dir: Path, bounds: list[Any], reason: str) -> None:
    presets = json.loads((source / "presets" / "steals.json").read_text(encoding="utf-8"))
    presets["presets"][0]["filters"] = {**presets["presets"][0]["filters"], "effective_stack_bb": bounds}
    (source / "presets" / "steals.json").write_text(json.dumps(presets), encoding="utf-8")

    assert reason in refused(source, packs_dir)


def test_a_preset_range_the_control_holds_is_accepted(source: Path, packs_dir: Path) -> None:
    presets = json.loads((source / "presets" / "steals.json").read_text(encoding="utf-8"))
    presets["presets"][0]["filters"] = {**presets["presets"][0]["filters"], "effective_stack_bb": [10.5, 40]}
    (source / "presets" / "steals.json").write_text(json.dumps(presets), encoding="utf-8")

    assert [p.id for p in stat_packs.install_pack(source, packs_dir).presets] == ["example.preflop.steal_by_position"]


def test_the_path_limit_counts_bytes_not_characters(source: Path, packs_dir: Path) -> None:
    # Eight components of 60 emoji: under 512 characters, about 1.9 KB of UTF-8.
    component = "\U0001F600" * 60
    path = "/".join([component] * 7) + "/x.json"
    assert len(path) < stat_packs.MAX_PATH_LENGTH < len(path.encode("utf-8"))
    edit_manifest(source, definitions=[path])

    assert "is too deep or too long" in refused(source, packs_dir)


# -- pre-merge review (PR #411) --------------------------------------------------


def test_loading_the_registry_never_moves_pack_folders(source: Path, packs_dir: Path) -> None:
    # The HUD process builds the registry too: a read that restored a backup
    # could undo a replacement the GUI process is half-way through.
    stat_packs.install_pack(source, packs_dir)
    (packs_dir / PACK_ID).rename(packs_dir / f".{PACK_ID}.previous")

    analytics_definitions.load_default_registry(packs_dir=packs_dir)
    stat_packs.installed_presets(packs_dir)

    assert (packs_dir / f".{PACK_ID}.previous").is_dir()
    assert not (packs_dir / PACK_ID).exists()
    # The manager, opened in the GUI, is where it is put back.
    assert {row.id: row.status for row in stat_packs.list_packs(packs_dir)}[PACK_ID] == stat_packs.ENABLED


# -- review of 03191eb8 (PR #411) ------------------------------------------------


def test_a_highly_compressible_pack_survives_export_and_re_import(source: Path, packs_dir: Path, tmp_path: Path) -> None:
    # 100 KB of leading whitespace compresses far past any fixed ratio.
    stats = (source / "stats" / "steals.json").read_text(encoding="utf-8")
    (source / "stats" / "steals.json").write_text(" " * 100_000 + stats, encoding="utf-8")
    stat_packs.install_pack(source, packs_dir)

    archive = stat_packs.export_pack(PACK_ID, tmp_path, packs_dir)

    assert stat_packs.install_pack(archive, tmp_path / "other").id == PACK_ID


@pytest.mark.parametrize(("listed", "alias"), [("stats/steals.json", "stats//steals.json"), ("manifest.json", "./manifest.json")])
def test_an_archive_entry_cannot_replace_a_listed_one(packs_dir: Path, tmp_path: Path, listed: str, alias: str) -> None:
    archive = tmp_path / "alias.fpdbstats"
    with zipfile.ZipFile(archive, "w") as out:
        for path in sorted(EXAMPLE.rglob("*")):
            if path.is_file():
                out.write(path, path.relative_to(EXAMPLE).as_posix())
        out.writestr(alias, "{}")

    with pytest.raises(stat_packs.PackError, match="repeats or re-spells another entry"):
        stat_packs.install_pack(archive, packs_dir)


@pytest.mark.parametrize("bounds", [[True, 50], ["10", 50], [None, 10**100]])
def test_a_percentage_range_is_checked_like_any_range(source: Path, packs_dir: Path, bounds: list[Any]) -> None:
    # _to_bp turns True into 100 basis points: [true, 50] would mean "from 1%".
    write_stats(source, [{"name": "example.preflop.x", "metric": "fold_frequency", "filters": {"bet_sizing_pct": bounds}}])

    assert "stat 'example.preflop.x'" in refused(source, packs_dir)


# -- review of 8ec9720a (PR #411) ------------------------------------------------


@pytest.mark.parametrize(
    "identity",
    [{"PokerStars": ["Hero", "Villain"]}, [["PokerStars", {"alias": "Hero"}]], [["PokerStars", ""]], {"PokerStars": 7}],
)
def test_an_identity_names_a_site_and_an_alias_as_text(source: Path, packs_dir: Path, identity: Any) -> None:
    # The compiler stringifies each part: a list would match "['Hero', 'Villain']".
    write_stats(source, [{"name": "example.preflop.x", "metric": "fold_frequency", "filters": {"identity": identity}}])

    assert "filter 'identity'" in refused(source, packs_dir)


@pytest.mark.parametrize("identity", [{"PokerStars": "Hero"}, ["PokerStars:Hero"], [["PokerStars", "Hero"]]])
def test_every_supported_identity_form_is_accepted(source: Path, packs_dir: Path, identity: Any) -> None:
    write_stats(source, [{"name": "example.preflop.x", "metric": "fold_frequency", "filters": {"identity": identity}}])

    assert stat_packs.install_pack(source, packs_dir).definitions[0].name == "example.preflop.x"
