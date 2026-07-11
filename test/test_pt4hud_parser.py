#!/usr/bin/env python3
"""Tests for fpdb_3_legacy.pt4hud — the PokerTracker 4 ``.pt4hud`` layout parser.

Exercises the binary string extraction, the PT4 -> fpdb stat mapping, the
fpdb ``<ss>`` stat-set export, and the recognition of unsupported user-defined
formula stats / range-chart popups, against a real exported layout.
"""

from __future__ import annotations

import os
import re
import struct
import sys

# NB: the only XML parsed here is the parser's own freshly generated output (no
# external input, no DTD/entities), so the stdlib parser's XXE/entity-expansion
# surface does not apply. The pt4hud module itself never parses XML.
import xml.dom.minidom as minidom

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fpdb_3_legacy import pt4hud

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "generationpoker_3h.pt4hud")
LOCAL_GP2H = "/Users/jde/Downloads/tournament_-_generationpoker_2h_free_generationpoker.pt_.pt4hud"
LOCAL_SPIN_BASIC = "/Users/jde/Downloads/spin_and_go_master_-_basic.pt4hud"
LOCAL_SPIN_NEW = "/Users/jde/Downloads/tournament_-_spin_new.pt4hud"
LOCAL_HU_CASH = "/Users/jde/Downloads/cash_-_ev_hu_cash_enthusiast_v.1.00.pt4hud"
LOCAL_GP_CASH = "/Users/jde/Downloads/cash_-_genarationpoker_cash_free_generationpoker.pt_.pt4hud"


def _be_str(s: str) -> bytes:
    raw = s.encode("utf-16-be")
    return struct.pack(">I", len(s)) + raw


# ---------------------------------------------------------------------------
# low-level string extraction
# ---------------------------------------------------------------------------
def test_read_strings_roundtrip():
    blob = _be_str("PT4.Hud.Layout.Export") + b"\x00\x00\x00\x05" + _be_str("VPIP")
    assert pt4hud.read_strings(blob)[0] == "PT4.Hud.Layout.Export"
    assert "VPIP" in pt4hud.read_strings(blob)


def test_parse_rejects_non_pt4hud():
    with pytest.raises(ValueError, match="not a PT4"):
        pt4hud.parse(_be_str("something else"))


# ---------------------------------------------------------------------------
# real-fixture parsing
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not os.path.exists(FIXTURE), reason="pt4hud fixture missing")
class TestRealLayout:
    @pytest.fixture(scope="class")
    def layout(self):
        return pt4hud.parse(FIXTURE)

    def test_name_and_magic(self, layout):
        assert "GenerationPoker" in layout.name

    def test_standard_stats_mapped(self, layout):
        by_name = {c.pt4_name: c.fpdb_stat for c in layout.supported}
        assert by_name["VPIP"] == "vpip"
        assert by_name["PFR"] == "pfr"
        assert by_name["Preflop Squeeze"] == "squeeze"
        assert by_name["CBet Flop in non-3Bet+ Pot"] == "cb1"
        assert by_name["Fold to R CBet in non-3Bet+ Pot"] == "f_cb3"
        assert by_name["Cold Call 2Bet PF"] == "cold_call"
        # ~20 standard stats are recognised in this layout.
        assert len(layout.supported) >= 18

    def test_gp_formula_stats_now_mapped(self, layout):
        # The GP display ratios are reproduced natively (open-size buckets + limp).
        mapped = {c.fpdb_stat for c in layout.supported}
        assert {"gp_2x", "gp_os", "gp_limp"} <= mapped
        # Only the internal counter *definitions* remain unsupported.
        unsupported = [c.formula for c in layout.unsupported if c.formula]
        assert any("amt_p_raise_made" in f for f in unsupported)

    def test_visual_record_headers_and_colours_are_extracted(self, layout):
        by_panel_stat = {(c.section, c.fpdb_stat, c.pt4_name): c for c in layout.supported}
        assert by_panel_stat[("BU 3h", "vpip", "VPIP")].label == "VP"
        assert by_panel_stat[("BU 3h", "gp_2x", "GP 2X")].label == "2X"
        assert by_panel_stat[("BB 3h", "float_bet", "Float Flop")].label == "F FLOAT"
        hands = by_panel_stat[("Villain Info 3H", "n", "Hands Abbreviated")]
        assert hands.hudcolor == "#0069d2"
        assert hands.hudbgcolor == "#a2a28a"

    def test_range_chart_popups_flagged(self, layout):
        assert "Push Nash" in layout.popups
        assert "Call Nash" in layout.popups

    def test_export_is_valid_fpdb_stat_set(self, layout):
        xml = pt4hud.to_stat_set(layout, name="GP 3H", cols=4)
        doc = minidom.parseString(f"<root>{xml}</root>")
        ss = doc.getElementsByTagName("ss")[0]
        assert ss.getAttribute("name") == "GP 3H"
        assert ss.getAttribute("cols") == "4"
        stats = doc.getElementsByTagName("stat")
        assert len(stats) == len(layout.supported)
        # every cell carries a rowcol and a stat name
        for st in stats:
            assert st.getAttribute("_rowcol").startswith("(")
            assert st.getAttribute("_stat_name")

    def test_every_mapped_stat_exists_in_fpdb(self, layout):
        from unittest.mock import MagicMock

        for m in ("PySide6", "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets"):
            sys.modules.setdefault(m, MagicMock())
        from fpdb_3_legacy import Stats

        # A mapped stat is valid if it is a player stat (STATLIST) or a
        # table-scope stat (do_table_stat's registry, e.g. live_min_stack_bb,
        # which is deliberately kept out of STATLIST/do_stat's player dispatch).
        table_stats = getattr(Stats, "_TABLE_STAT_FUNCTIONS", {})
        for c in layout.supported:
            assert c.fpdb_stat in Stats.STATLIST or c.fpdb_stat in table_stats, c.fpdb_stat

    def test_range_charts_extracted_as_13x13_grids(self, layout):
        charts = {c.name: c for c in layout.charts}
        assert {"Push Nash", "Call Nash"} <= set(charts)
        for ch in charts.values():
            assert len(ch.cells) == 169  # full 13x13 grid
            hands = {c.hand for c in ch.cells}
            assert {"AA", "AKs", "72o", "22"} <= hands
            # every cell has a #rrggbb fill colour
            assert all(re.fullmatch(r"#[0-9a-f]{6}", c.fill) for c in ch.cells)

    def test_chart_fold_vs_action_colours(self, layout):
        push = next(c for c in layout.charts if c.name == "Push Nash")
        by_hand = {c.hand: c.fill for c in push.cells}
        # AA is always an action; 72o is the fold colour; they differ.
        assert by_hand["AA"] != by_hand["72o"]
        assert push.legend()[by_hand["72o"]] == "fold"
        assert push.legend()[by_hand["AA"]] == "push"

    def test_to_dict_roundtrips_charts(self, layout):
        d = pt4hud.to_dict(layout)
        assert d["name"]
        names = {c["name"] for c in d["charts"]}
        assert {"Push Nash", "Call Nash"} <= names
        push = next(c for c in d["charts"] if c["name"] == "Push Nash")
        assert len(push["cells"]) == 169


def test_argb_to_hex():
    assert pt4hud.argb_to_hex(0xFF009393) == "#009393"
    assert pt4hud.argb_to_hex(0xFFFFFFFF) == "#ffffff"


def test_panel_position_binding():
    assert pt4hud.panel_position("SB 3h") == "SB"
    assert pt4hud.panel_position("BB 3h") == "BB"
    assert pt4hud.panel_position("BU 3h") == "BTN"
    assert pt4hud.panel_position("Villain Info 3H") == ""  # always shown


def test_grouped_placements_starts_each_panel_on_new_row():
    C = pt4hud.Cell
    cells = [
        C("a", section="SB 3h", fpdb_stat="cb1"),
        C("b", section="SB 3h", fpdb_stat="cb2"),
        C("c", section="BB 3h", fpdb_stat="cold_call"),  # new panel -> new row
    ]
    placements, rows = pt4hud.grouped_placements(cells, cols=4)
    rc = {c.pt4_name: (r, col) for c, r, col in placements}
    assert rc["a"] == (0, 0)
    assert rc["b"] == (0, 1)
    assert rc["c"] == (1, 0)  # BB panel forced onto a fresh row
    assert rows == 2


@pytest.mark.skipif(not os.path.exists(FIXTURE), reason="pt4hud fixture missing")
def test_real_layout_panels_are_position_panels():
    layout = pt4hud.parse(FIXTURE)
    panels = {c.section for c in layout.supported}
    # position/info panels, not the "POST FLOP" street sub-section
    assert {"SB 3h", "BB 3h", "BU 3h"} <= panels
    assert "POST FLOP" not in panels
    assert "Winnings 3H" not in panels  # a stat, not a panel


@pytest.mark.skipif(not os.path.exists(LOCAL_GP2H), reason="local 2H pt4hud fixture missing")
def test_generationpoker_2h_visual_panels_are_detected():
    layout = pt4hud.parse(LOCAL_GP2H)
    panels = {c.section for c in layout.supported}
    assert {"SB 2h", "BB 2h", "Villain 2h"} <= panels
    assert len(layout.supported) >= 17

    by_panel_stat = {(c.section, c.fpdb_stat): c for c in layout.supported}
    assert by_panel_stat[("SB 2h", "rfi_total")].label == "RFI"
    assert by_panel_stat[("SB 2h", "f_3bet")].label == "Fv3B"
    assert by_panel_stat[("SB 2h", "limp")].label == "LMP"
    assert by_panel_stat[("BB 2h", "three_B")].label == "3B"
    assert by_panel_stat[("BB 2h", "f_cb1")].label == "F FvCB"
    assert by_panel_stat[("BB 2h", "probe_bet_turn")].label == "T PROBE"
    assert by_panel_stat[("Villain 2h", "vpip")].label == "VP"
    assert by_panel_stat[("Villain 2h", "pfr")].label == "PFR"


@pytest.mark.skipif(not os.path.exists(LOCAL_SPIN_BASIC), reason="local Spin Basic pt4hud fixture missing")
def test_spin_basic_short_position_panels_and_charts_are_detected():
    layout = pt4hud.parse(LOCAL_SPIN_BASIC)
    panels = {c.section for c in layout.supported}
    assert {"BTN", "SB", "BB", "Villain info"} <= panels
    assert len(layout.supported) >= 25
    assert {c.name for c in layout.charts} == {"Push Nash", "Call Nash"}

    by_panel_stat = {(c.section, c.fpdb_stat, c.pt4_name): c for c in layout.supported}
    assert by_panel_stat[("BTN", "vpip", "VPIP")].label == "VPIP"
    assert by_panel_stat[("BTN", "pfr", "PFR")].label == "PFR"
    assert by_panel_stat[("SB", "f_steal", "Fold to Steal")].label == "FvSTL"
    assert by_panel_stat[("Villain info", "squeeze", "Preflop Squeeze")].label == "Sq"


@pytest.mark.skipif(not os.path.exists(LOCAL_SPIN_NEW), reason="local Spin New pt4hud fixture missing")
def test_spin_new_generic_table_layout_is_not_misread_as_seat_panels():
    layout = pt4hud.parse(LOCAL_SPIN_NEW)
    # This file is a generic Tools/Preflop/Flop/PT4 matrix export rather than a
    # seat-box HUD. Keep the parser conservative so it does not create fake
    # multi-box panels from large section containers.
    assert {c.section for c in layout.supported} == {""}


@pytest.mark.skipif(not os.path.exists(LOCAL_HU_CASH), reason="local HU cash pt4hud fixture missing")
def test_hu_cash_named_panels_are_detected():
    layout = pt4hud.parse(LOCAL_HU_CASH)
    panels = {c.section for c in layout.supported}
    assert {"SB Preflop", "BB Preflop", "SRP IP", "SRP OOP", "Misc"} <= panels
    by_panel_stat = {(c.section, c.fpdb_stat, c.pt4_name): c for c in layout.supported}
    assert by_panel_stat[("SB Preflop", "rfi_total", "Raise First In")].label == "RFI"
    assert by_panel_stat[("BB Preflop", "three_bet_vs_steal", "3Bet Steal")].label == "3-Bet"
    assert by_panel_stat[("SRP IP", "cb1", "CBet Flop in non-3Bet+ Pot")].label
    assert by_panel_stat[("SRP OOP", "probe_bet_turn", "Probe Turn in non-3Bet+ Pot")].label


@pytest.mark.skipif(not os.path.exists(LOCAL_GP_CASH), reason="local GenerationPoker cash pt4hud fixture missing")
def test_generationpoker_cash_custom_visual_stats_are_mapped():
    layout = pt4hud.parse(LOCAL_GP_CASH)
    panels = {c.section for c in layout.supported}
    assert {"Main Panel", "Pre Flop", "Post Flop", "RFI", "Main Panel2"} <= panels
    # The file maps ~113 visual stat cells; the old >=200 target predated the
    # switch to deduplicated per-panel extraction (it counted the flat scan's
    # duplicates/definitions). 100 still proves the custom stats are mapped.
    assert len(layout.supported) >= 100
    by_panel_stat = {(c.section, c.fpdb_stat, c.pt4_name): c for c in layout.supported}
    assert by_panel_stat[("Main Panel", "vpip", "GenPoker_C/M VPIP")].label == "VP"
    assert by_panel_stat[("Main Panel", "f_3bet", "GenPoker_C/M FOLD VS 3BET PF")].label == "v3B"
    assert any(
        c.section == "Main Panel2"
        and c.fpdb_stat == "fold_vs_4bet"
        and c.pt4_name == "GenPoker_C/M FOLD TO 4BET PF"
        and c.label == "v4B"
        for c in layout.supported
    )


@pytest.mark.skipif(not os.path.exists(FIXTURE), reason="fixture missing")
def test_extract_popup_groups_returns_structured_grids():
    """PT4 popup groups parse as named text/stat grids (same shape as panels)."""
    groups = pt4hud.extract_popup_groups(FIXTURE)
    assert groups, "expected at least one popup group"
    by_name = {g.name: g for g in groups}
    # the Nash push chart imports as a grid of text cells
    push = by_name.get("Push Nash")
    assert push is not None
    assert push.rows >= 13 and push.cols >= 13
    texts = {c.text for c in push.cells if c.kind == "text"}
    assert {"AA", "AKs", "72o"} <= texts                    # 13x13 hand-grid labels
    # cells carry grid positions
    assert all(0 <= c.row < push.rows and 0 <= c.col < push.cols for c in push.cells)


@pytest.mark.skipif(not os.path.exists(FIXTURE), reason="fixture missing")
def test_popup_group_does_not_absorb_following_panels():
    """A popup group's content stops at the next named container, so it does not
    swallow the cells of the table panels (or groups) that follow it."""
    groups = {g.name: g for g in pt4hud.extract_popup_groups(FIXTURE)}
    cn = groups["Call Nash"]
    texts = {c.text for c in cn.cells}
    assert {"AA", "AKs"} <= texts                          # its own hand grid
    # none of the main-HUD panel labels, nor the following popup's promo, leaked in
    assert not ({"GP 2X", "GP OS", "GP LIMP", "POST FLOP", "TOTAL"} & texts)
    assert not any("Spin" in t or "snghud" in t for t in texts)
    # bounded to a chart's worth of rows (caption + 13x13 grid + stack legend)
    assert cn.rows <= 18
