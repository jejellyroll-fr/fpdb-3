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


def test_malformed_yaml_is_a_pack_error(source: Path, packs_dir: Path) -> None:
    pytest.importorskip("yaml")
    (source / "stats" / "broken.yaml").write_text("stats: [unclosed", encoding="utf-8")
    edit_manifest(source, definitions=["stats/steals.json", "stats/broken.yaml"])

    assert "stats/broken.yaml is not valid YAML" in refused(source, packs_dir)


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
