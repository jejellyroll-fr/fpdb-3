"""The HUD editor's load and write code must not change a stat-set it did not edit.

Every ``<ss>`` fpdb ships is read into the editor's data, written back by the
editor's own writer, and parsed again: what the HUD reads must be identical.
Runs without a window, so it is part of the default suite.
"""

from __future__ import annotations

import pytest

from tests.helpers.hud_editor import EditorIO, shipped_stat_sets, stat_set_snapshot

pytest.importorskip("PySide6")

SHIPPED = list(shipped_stat_sets())


def test_the_shipped_stat_sets_are_found() -> None:
    sources = {source.split(":")[0] for source, _node in SHIPPED}
    assert "example" in sources
    assert len(sources) > 1, "no hud-packages stat-set found"


def _round_trip(node):
    from fpdb_3_legacy import Configuration

    before = Configuration.Stat_sets(node)
    io = EditorIO(node.ownerDocument)
    profile = io.load(node)
    after = io.write(node.cloneNode(True), profile, before.rows, before.cols)
    return stat_set_snapshot(before), stat_set_snapshot(after)


@pytest.mark.parametrize(("source", "node"), SHIPPED, ids=[source for source, _node in SHIPPED])
def test_an_unedited_shipped_stat_set_survives_the_editor(source, node) -> None:
    before, after = _round_trip(node)
    assert after == before
    assert before["blocks"] and any(block["stats"] for block in before["blocks"]), "empty snapshot"


def _parse(xml: str):
    import defusedxml.minidom

    return defusedxml.minidom.parseString(xml).documentElement


MULTI_BLOCK = (
    '<ss name="multi" rows="3" cols="2">'
    '<block id="core" label="Core" rows="2" cols="2" title_bgcolor="#312E81" title_font_scale="0.8">'
    '<text _rowcol="(1,1)" label="PRE" colspan="2"/>'
    '<stat _rowcol="(2,1)" _stat_name="vpip" stat_loth="12.5" stat_hith="140"/>'
    '<stat _rowcol="(2,2)" _stat_name="pfr" colspan="1" align="left"/>'
    "</block>"
    '<block label="Post" rows="1" cols="2"><hline _rowcol="(1,1)" color="#d7b500"/></block>'
    "</ss>"
)


def test_texts_lines_and_decimal_thresholds_of_a_multi_block_set_survive() -> None:
    before, after = _round_trip(_parse(MULTI_BLOCK))
    for name in ("texts", "hlines", "stats", "label", "title_bgcolor"):
        assert [b[name] for b in after["blocks"]] == [b[name] for b in before["blocks"]], name


def test_the_snapshot_sees_a_lost_label() -> None:
    from fpdb_3_legacy import Configuration

    node = _parse(MULTI_BLOCK)
    before = stat_set_snapshot(Configuration.Stat_sets(node))
    node.getElementsByTagName("text")[0].setAttribute("label", "")
    assert stat_set_snapshot(Configuration.Stat_sets(node)) != before


# --- Known defects (docs/hud-editor-improvement-plan.md) -----------------------
# Each test states the correct behaviour and is expected to fail until its fix
# lands; strict, so the fix has to remove the marker.


@pytest.mark.xfail(strict=True, reason="B5: a one-<block> stat-set is loaded as a flat grid")
def test_b5_a_single_block_keeps_its_title_texts_and_lines() -> None:
    node = _parse(
        '<ss name="one" rows="3" cols="2">'
        '<block label="Main" rows="3" cols="2" title_bgcolor="#312E81">'
        '<text _rowcol="(1,1)" label="PRE" colspan="2"/>'
        '<stat _rowcol="(2,1)" _stat_name="vpip"/>'
        '<hline _rowcol="(3,1)"/>'
        "</block></ss>"
    )
    before, after = _round_trip(node)
    assert after == before


@pytest.mark.xfail(strict=True, reason="block-level title/heading font scales are not carried by the editor")
def test_a_block_font_scale_survives() -> None:
    before, after = _round_trip(_parse(MULTI_BLOCK))
    assert after["blocks"][0]["title_font_scale"] == before["blocks"][0]["title_font_scale"] == 0.8
