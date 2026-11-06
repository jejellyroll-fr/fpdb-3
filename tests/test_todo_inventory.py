"""Tests for the generated technical-debt register."""

from pathlib import Path

from tools.todo_inventory import collect_items, render_inventory


def test_collect_items_assigns_stable_ids_and_categories(tmp_path: Path) -> None:
    parser_dir = tmp_path / "fpdb_3_legacy"
    parser_dir.mkdir()
    source = parser_dir / "ExampleToFpdb.py"
    source.write_text("# TODO: support another format\n# FIXME incomplete payout\n", encoding="utf-8")

    first = collect_items(tmp_path, (parser_dir,))
    source.write_text("\n# TODO: support another format\n# FIXME incomplete payout\n", encoding="utf-8")
    moved = collect_items(tmp_path, (parser_dir,))

    assert [item.identifier for item in first] == [item.identifier for item in moved]
    assert {item.category for item in first} == {"parser"}
    assert [item.marker for item in first] == ["TODO", "FIXME"]
    assert moved[0].line == 2


def test_render_inventory_escapes_markdown_and_reports_counts(tmp_path: Path) -> None:
    source_dir = tmp_path / "fpdb_3_legacy"
    source_dir.mkdir()
    (source_dir / "Hand.py").write_text("# HACK: preserve a | legacy case\n", encoding="utf-8")

    rendered = render_inventory(collect_items(tmp_path, (source_dir,)))

    assert "**Total : 1 tâches ouvertes.**" in rendered
    assert "| poker-domain | 1 |" in rendered
    assert "preserve a \\| legacy case" in rendered
    assert "[fpdb_3_legacy/Hand.py:1](fpdb_3_legacy/Hand.py#L1)" in rendered


def test_identical_markers_in_one_file_have_distinct_ids(tmp_path: Path) -> None:
    source_dir = tmp_path / "fpdb_3_legacy"
    source_dir.mkdir()
    (source_dir / "Database.py").write_text("# FIXME same\n# FIXME same\n", encoding="utf-8")

    items = collect_items(tmp_path, (source_dir,))

    assert len({item.identifier for item in items}) == 2
