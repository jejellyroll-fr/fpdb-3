"""Between a ``<ss>`` and the HUD editor's profile data, without Qt."""

from __future__ import annotations

import defusedxml.minidom
import pytest

from fpdb_3_legacy import Configuration
from fpdb_3_legacy.modern_hud_preferences import profile_io
from tests.helpers.hud_editor import stat_set_snapshot


def _node(xml: str):
    return defusedxml.minidom.parseString(xml).documentElement


def _profile(xml: str):
    return profile_io.profile_from_stat_set(Configuration.Stat_sets(_node(xml)))


def _write(profile, name: str = "copy"):
    """Write a profile into a brand-new <ss>, as Save does for a new profile."""
    doc = defusedxml.minidom.parseString("<stat_sets/>")
    node = doc.createElement("ss")
    node.setAttribute("name", name)
    doc.documentElement.appendChild(node)
    profile_io.write_profile(doc, node, profile)
    return Configuration.Stat_sets(node)


RICH = (
    '<ss name="rich" rows="1" cols="2" xpad="2" ypad="1" rich_text="True" font_size="10"'
    ' title_font_scale="0.82" heading_font_scale="0.6" show_hero_hud="true">'
    '<stat _rowcol="(1,1)" _stat_name="vpip"/><stat _rowcol="(1,2)" _stat_name="pfr"/></ss>'
)
BLOCKS = (
    '<ss name="b" rows="2" cols="2" positional_mode="all">'
    '<block label="Core" rows="1" cols="2" heading_font_scale="0.5"><stat _rowcol="(1,1)" _stat_name="vpip"/></block>'
    '<block label="Post" rows="2" cols="2" cell_width="44" bgcolor="rgba(1, 2, 3, 100)">'
    '<text _rowcol="(1,1)" label="POST" colspan="2" align="left" fgcolor="#ffffff" bgcolor="#000000"/>'
    '<hline _rowcol="(2,1)" colspan="1" color="#d7b500"/>'
    '<stat _rowcol="(2,2)" _stat_name="cb1" colspan="1" display_label="CB" data_source="analytics"'
    ' data_definition="cbet_flop" data_format="pct" data_min_sample="20"/>'
    "</block>"
    '<block label="Wide" rows="1" cols="2"><stat _rowcol="(1,1)" _stat_name="wtsd" colspan="2" align="right"/></block>'
    "</ss>"
)


def test_a_profile_written_to_a_new_node_keeps_its_presentation() -> None:
    original = Configuration.Stat_sets(_node(RICH))
    copy = _write(_profile(RICH))
    expected = stat_set_snapshot(original)
    assert stat_set_snapshot(copy) == expected


def test_a_multi_block_profile_written_to_a_new_node_is_the_same_set() -> None:
    original = Configuration.Stat_sets(_node(BLOCKS))
    assert stat_set_snapshot(_write(_profile(BLOCKS))) == stat_set_snapshot(original)


def test_a_multi_block_profile_keeps_the_size_written_on_its_ss() -> None:
    profile = _profile(BLOCKS)
    assert (profile["rows"], profile["cols"]) == (2, 2)
    assert profile_io.stat_set_size(profile) == (2, 2)


def test_the_stacked_list_offsets_each_block_by_the_rows_above() -> None:
    profile = _profile(BLOCKS)
    assert [(s["stat"], s["row"], s["col"]) for s in profile["stats"]] == [
        ("vpip", 0, 0),
        ("cb1", 2, 1),
        ("wtsd", 3, 0),
    ]
    assert [s["row"] for b in profile["blocks"] for s in b["stats"]] == [0, 1, 0]


def test_a_flat_set_stays_flat() -> None:
    profile = _profile(RICH)
    assert "blocks" not in profile and not profile.get("multiblock")


def test_a_cleared_presentation_attribute_is_removed_from_the_node() -> None:
    node = _node(RICH)
    profile = profile_io.profile_from_stat_set(Configuration.Stat_sets(node))
    profile["rich_text"] = ""
    profile_io.write_stat_set_attributes(node, profile)
    assert not node.hasAttribute("rich_text")
    assert node.getAttribute("font_size") == "10"


def test_an_old_list_profile_is_written_as_a_five_by_five_grid() -> None:
    stats = [{"row": 0, "col": 0, "stat": "vpip"}]
    saved = _write(stats)
    assert (saved.rows, saved.cols) == (5, 5)
    assert saved.stats[(0, 0)].stat_name == "vpip"
    assert profile_io.profile_stats(stats) is stats


def test_profile_stats_reads_the_blocks_not_the_stacked_list() -> None:
    profile = _profile(BLOCKS)
    profile["blocks"][1]["stats"].append({"row": 0, "col": 1, "stat": "pfr"})
    assert [s["stat"] for s in profile_io.profile_stats(profile)] == ["vpip", "cb1", "pfr", "wtsd"]
    assert [s["stat"] for s in profile_io.profile_stats(_profile(RICH))] == ["vpip", "pfr"]
    assert profile_io.profile_stats(None) == []


def test_ensure_blocks_moves_the_flat_stats_into_one_block() -> None:
    profile = _profile(RICH)
    vpip = profile["stats"][0]
    blocks = profile_io.ensure_blocks(profile)
    assert len(blocks) == 1 and blocks[0]["stats"][0] is vpip
    assert profile["multiblock"] and (blocks[0]["rows"], blocks[0]["cols"]) == (1, 2)
    assert profile_io.ensure_blocks(profile) is blocks


def test_a_one_block_profile_without_title_is_written_as_a_block() -> None:
    profile = _profile(RICH)
    profile_io.ensure_blocks(profile)
    profile["blocks"][0]["texts"].append({"rowcol": (1, 0), "label": "HDR", "colspan": 2})
    saved = _write(profile)
    assert saved.has_block_nodes and not saved.is_multiblock
    assert [t["label"] for t in saved.blocks[0].texts] == ["HDR"]
    assert sorted(saved.stats) == [(0, 0), (0, 1)]


@pytest.mark.parametrize("label", ["", "Main"])
def test_new_block_is_complete(label) -> None:
    block = profile_io.new_block(label, rows=0, cols=3)
    assert block["label"] == label and (block["rows"], block["cols"]) == (1, 3)
    assert block["stats"] == block["texts"] == block["hlines"] == []


def test_an_object_without_a_grid_size_reads_as_a_stat_list() -> None:
    from types import SimpleNamespace

    stat = SimpleNamespace(stat_name="vpip", click="", popup="", colspan=1, align="center")
    assert profile_io.profile_from_stat_set(SimpleNamespace(stats={(0, 1): stat})) == [
        {"row": 0, "col": 1, "stat": "vpip", "click": "", "popup": ""}
    ]
