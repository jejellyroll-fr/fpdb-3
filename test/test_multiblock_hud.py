#!/usr/bin/env python3
"""Tests for multi-panel ("block") HUD support.

Covers Configuration.Stat_sets block parsing (backward compatible with flat
stat-sets) and Aux_Hud rendering of stacked per-block grids in a seat window.
"""

from __future__ import annotations

import os
import sys
import types

# Only inline trusted XML literals are parsed here (no external input / DTD),
# so the stdlib parser's XXE/entity-expansion surface does not apply.
import xml.dom.minidom as minidom

import pytest

pytestmark = pytest.mark.qt

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QGridLayout, QLabel

from fpdb_3_legacy import Aux_Classic_Hud, Aux_Hud
from fpdb_3_legacy import Configuration as Conf


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ---------------------------------------------------------------------------
# Configuration.Stat_sets block parsing
# ---------------------------------------------------------------------------
def _ss(xml):
    return Conf.Stat_sets(minidom.parseString(xml).documentElement)


def test_flat_stat_set_is_single_block():
    ss = _ss('<ss name="f" rows="1" cols="2">'
             '<stat _rowcol="(1,1)" _stat_name="vpip"/><stat _rowcol="(1,2)" _stat_name="pfr"/></ss>')
    assert len(ss.blocks) == 1
    assert not ss.is_multiblock
    assert {s.stat_name for s in ss.blocks[0].stats.values()} == {"vpip", "pfr"}


def test_build_block_layouts_propagates_scope():
    """_build_block_layouts must carry scope through to block_layouts, else a
    table block is created once per seat instead of one table window (found live:
    Min Stack (Table) rendered as a per-seat player stat -> TypeError)."""
    ss = _ss('<ss name="t" rows="0" cols="0">'
             '<block label="SB 3h" scope="player" cell_width="44">'
             '<stat _rowcol="(1,1)" _stat_name="vpip"/></block>'
             '<block label="Min Stack (Table)" scope="table">'
             '<stat _rowcol="(1,1)" _stat_name="live_min_stack_bb"/></block></ss>')
    aw = Aux_Hud.SimpleHUD.__new__(Aux_Hud.SimpleHUD)
    aw.game_params = ss
    aw.nrows, aw.ncols = ss.rows, ss.cols
    aw._build_block_layouts()
    assert [b["scope"] for b in aw.block_layouts] == ["player", "table"]
    assert [b["cell_width"] for b in aw.block_layouts] == [44, 0]


def test_multiblock_stat_set_parses_panels():
    ss = _ss('<ss name="t" rows="2" cols="2">'
             '<block label="SB 3h" rows="1" cols="2">'
             '<stat _rowcol="(1,1)" _stat_name="vpip"/><stat _rowcol="(1,2)" _stat_name="pfr"/></block>'
             '<block label="BB 3h" rows="1" cols="1">'
             '<stat _rowcol="(1,1)" _stat_name="cb1"/></block></ss>')
    assert len(ss.blocks) == 2
    assert ss.is_multiblock
    assert [b.label for b in ss.blocks] == ["SB 3h", "BB 3h"]
    assert ss.blocks[0].rows == 1 and ss.blocks[0].cols == 2
    assert {s.stat_name for s in ss.blocks[1].stats.values()} == {"cb1"}


def test_block_parses_position_binding():
    ss = _ss('<ss name="t" rows="1" cols="1">'
             '<block label="SB 3h" position="SB"><stat _rowcol="(1,1)" _stat_name="vpip"/></block>'
             '<block label="Info"><stat _rowcol="(1,1)" _stat_name="n"/></block></ss>')
    assert ss.blocks[0].position == "SB"
    assert ss.blocks[1].position == ""  # unbound


def test_block_layout_keeps_empty_position_unbound():
    ss = _ss('<ss name="t" rows="1" cols="1">'
             '<block label="SB 3h"><stat _rowcol="(1,1)" _stat_name="vpip"/></block>'
             '<block label="BB 3h"><stat _rowcol="(1,1)" _stat_name="pfr"/></block>'
             '<block label="BU 3h"><stat _rowcol="(1,1)" _stat_name="n"/></block>'
             '<block label="Villain Info 3H"><stat _rowcol="(1,1)" _stat_name="playershort"/></block>'
             '</ss>')
    aw = Aux_Hud.SimpleHUD.__new__(Aux_Hud.SimpleHUD)
    aw.game_params = ss
    aw.nrows = ss.rows
    aw.ncols = ss.cols
    aw.block_layouts = []
    aw._build_block_layouts()

    assert [b["position"] for b in aw.block_layouts] == ["", "", "", ""]


def test_block_parses_text_label_items():
    ss = _ss('<ss name="t" rows="0" cols="0">'
             '<block label="BB 3h" position="BB">'
             '<text _rowcol="(1,1)" label="POST FLOP" colspan="4" align="center" fgcolor="#fff" bgcolor="#900"/>'
             '<text _rowcol="(2,1)" label="F"/>'
             '<stat _rowcol="(2,2)" _stat_name="f_cb1"/>'
             '<stat _rowcol="(2,3)" _stat_name="f_cb2"/></block></ss>')
    blk = ss.blocks[0]
    assert len(blk.texts) == 2
    post = next(t for t in blk.texts if t["label"] == "POST FLOP")
    assert post["rowcol"] == (0, 0) and post["colspan"] == 4 and post["bgcolor"] == "#900"
    assert {s.stat_name for s in blk.stats.values()} == {"f_cb1", "f_cb2"}
    assert blk.rows == 2 and blk.cols == 4


def test_flat_block_has_no_text_items():
    ss = _ss('<ss name="f" rows="1" cols="2"><stat _rowcol="(1,1)" _stat_name="vpip"/></ss>')
    assert ss.blocks[0].texts == []


def test_positional_hud_defaults_to_current_panel():
    ss = _ss('<ss name="f" rows="1" cols="1"><stat _rowcol="(1,1)" _stat_name="vpip"/></ss>')
    assert ss.positional_mode == "current"


def test_positional_hud_can_explicitly_show_all_panels():
    ss = _ss(
        '<ss name="f" rows="1" cols="1" positional_mode="all">'
        '<stat _rowcol="(1,1)" _stat_name="vpip"/></ss>'
    )
    assert ss.positional_mode == "all"


def test_block_parses_optional_style_attributes():
    ss = _ss('<ss name="t" rows="1" cols="1">'
             '<block label="SB 3h" position="SB" bordercolor="#d7b500" '
             'title_bgcolor="#d7b500" title_fgcolor="#111111" bgcolor="rgba(0,0,0,178)" '
             'cell_width="44" x="12" y="34">'
             '<stat _rowcol="(1,1)" _stat_name="vpip"/></block></ss>')
    blk = ss.blocks[0]
    assert blk.bordercolor == "#d7b500"
    assert blk.title_bgcolor == "#d7b500"
    assert blk.title_fgcolor == "#111111"
    assert blk.bgcolor == "rgba(0,0,0,178)"
    assert blk.cell_width == 44
    assert (blk.x, blk.y) == (12, 34)


def test_block_derives_grid_size_when_unspecified():
    ss = _ss('<ss name="t" rows="0" cols="0">'
             '<block label="x"><stat _rowcol="(1,1)" _stat_name="vpip"/>'
             '<stat _rowcol="(2,3)" _stat_name="pfr"/></block></ss>')
    blk = ss.blocks[0]
    assert blk.rows == 2 and blk.cols == 3


def test_simplehud_accepts_zero_sized_multiblock_profile():
    """Block coordinates must not be indexed into the empty classic grid."""
    ss = _ss(
        '<ss name="plo4" rows="0" cols="0" font_size="10">'
        '<block label="Identity" rows="1" cols="2">'
        '<stat _rowcol="(1,1)" _stat_name="playershort"/>'
        '<stat _rowcol="(1,2)" _stat_name="n"/></block>'
        '<block label="Core" rows="1" cols="2">'
        '<stat _rowcol="(1,1)" _stat_name="vpip"/>'
        '<stat _rowcol="(1,2)" _stat_name="pfr"/></block></ss>'
    )
    hud = types.SimpleNamespace(
        poker_game="omahahi",
        site_parameters={"hud_menu_xshift": 0, "hud_menu_yshift": 0},
        supported_games_parameters={"game_stat_set": ss},
        max=6,
    )
    aux_params = {
        "fgcolor": "#ffffff",
        "bgcolor": "#000000",
        "opacity": "1.0",
        "font": "Sans",
        "font_size": "8",
    }

    aw = Aux_Hud.SimpleHUD(hud, types.SimpleNamespace(), aux_params)

    assert aw.font_size == 10
    assert aw.stats == []
    assert aw.popups == []
    assert aw.tips == []
    assert [block["stats"] for block in aw.block_layouts] == [
        [["playershort", "n"]],
        [["vpip", "pfr"]],
    ]

    # The live profile switch calls this path too.
    aw.refresh_stats_layout()
    assert [block["label"] for block in aw.block_layouts] == ["Identity", "Core"]


# ---------------------------------------------------------------------------
# Aux_Hud multi-block rendering
# ---------------------------------------------------------------------------
def _fake_aw(block_layouts, position="", positional_mode="all"):
    hud = types.SimpleNamespace(
        stat_dict={1: {"screen_name": "p", "seat": 1, "n": 0, "position": position}},
        hand_instance=None,
        layout=types.SimpleNamespace(hh_seats={1: 1}),
        site="TestSite",
    )
    game_params = types.SimpleNamespace(
        name="test", show_hero_hud="", is_multiblock=len(block_layouts) > 1,
        positional_mode=positional_mode,
    )
    config = types.SimpleNamespace(
        stat_sets={},
        supported_sites={},
        is_hero_name=lambda _site, name: str(name).lower() == "hero",
    )
    aw = types.SimpleNamespace(
        bgcolor="#000000", fgcolor="#ffffff", font=QFont(), aux_params={},
        aw_class_stat=Aux_Hud.SimpleStat, aw_class_label=Aux_Hud.SimpleLabel,
        block_layouts=block_layouts, hud=hud, nrows=1, ncols=1,
        game_params=game_params, config=config,
        get_id_from_seat=lambda _s: 1,
    )
    aw._show_hero_hud = types.MethodType(Aux_Hud.SimpleHUD._show_hero_hud, aw)
    aw._is_hero_player = types.MethodType(Aux_Hud.SimpleHUD._is_hero_player, aw)
    aw._hide_seat_for_villain_only = types.MethodType(Aux_Hud.SimpleHUD._hide_seat_for_villain_only, aw)
    aw._positional_mode = types.MethodType(Aux_Hud.SimpleHUD._positional_mode, aw)
    return aw


def _block(label, stats2d, position="", texts=None, colorranges=None):
    nr, nc = len(stats2d), len(stats2d[0])
    return {
        "label": label, "position": position, "nrows": nr, "ncols": nc, "stats": stats2d,
        "bgcolor": "", "fgcolor": "", "bordercolor": "", "title_bgcolor": "", "title_fgcolor": "",
        "cell_width": 0,
        "hudcolors": [[""] * nc for _ in range(nr)],
        "hudbgcolors": [[""] * nc for _ in range(nr)],
        "popups": [["default"] * nc for _ in range(nr)],
        "tips": [[""] * nc for _ in range(nr)],
        "colorranges": colorranges or [[None] * nc for _ in range(nr)],
        "texts": texts or [],
    }


def test_seat_window_renders_text_label_items():
    from PySide6.QtWidgets import QLabel

    texts = [
        {"rowcol": (0, 0), "label": "BB", "colspan": 1, "fgcolor": "#fff", "bgcolor": "#2d2d2d"},
        {"rowcol": (0, 1), "label": "FLAT", "colspan": 1, "fgcolor": "", "bgcolor": ""},
        {"rowcol": (2, 0), "label": "POST FLOP", "colspan": 4, "fgcolor": "", "bgcolor": "#900"},
    ]
    blk = _block("BB 3h", [[None, None, None, None], ["cold_call", "three_B", None, None],
                           [None, None, None, None]], texts=texts)
    win = Aux_Hud.SimpleStatWindow(aw=_fake_aw([blk, _block("SB 3h", [["vpip"]])]), seat=1)
    win.create_contents(1)
    rendered = {w.text() for w in win.findChildren(QLabel)}
    assert {"BB", "FLAT", "POST FLOP"} <= rendered  # text items shown in the HUD grid


def test_seat_window_renders_one_grid_per_block():
    blocks = [
        _block("SB 3h", [["vpip", "pfr"]]),
        _block("BB 3h", [["cb1", None]]),
    ]
    win = Aux_Hud.SimpleStatWindow(aw=_fake_aw(blocks), seat=1)
    win.create_contents(1)
    # one stat-box grid + one container widget per block
    assert len(win.stat_boxes) == 2
    assert len(win.block_widgets) == 2
    assert win.stat_boxes[0][0][0].stat == "vpip"
    assert win.stat_boxes[1][0][0].stat == "cb1"
    assert win.stat_boxes[1][0][1].stat is None
    assert win.stat_boxes[1][0][1].widget.text() == ""
    # each block container holds a grid
    grids = win.findChildren(QGridLayout)
    assert len(grids) == 2
    titles = [w for w in win.findChildren(QLabel) if w.text() in ("SB 3h", "BB 3h")]
    assert {t.text() for t in titles} == {"SB 3h", "BB 3h"}


def test_multiblock_cell_width_is_applied_and_default_is_preserved():
    configured = _block("Wide", [["vpip"]])
    configured["cell_width"] = 44
    default = _block("Default", [["pfr"]])

    win = Aux_Hud.SimpleStatWindow(aw=_fake_aw([configured, default]), seat=1)
    win.create_contents(1)

    assert win.stat_boxes[0][0][0].widget.minimumWidth() == 44
    assert win.stat_boxes[1][0][0].widget.minimumWidth() == 20


def test_single_block_has_no_title_label():
    win = Aux_Hud.SimpleStatWindow(aw=_fake_aw([_block("", [["vpip", "pfr"]])]), seat=1)
    win.create_contents(1)
    assert len(win.stat_boxes) == 1
    # legacy alias preserved
    assert win.stat_box is win.stat_boxes[0]


def test_update_contents_iterates_all_blocks():
    blocks = [_block("A", [["vpip"]]), _block("B", [["pfr"]])]
    win = Aux_Hud.SimpleStatWindow(aw=_fake_aw(blocks), seat=1)
    win.create_contents(1)
    # should not raise and should touch both blocks
    win.update_contents(1)


def test_update_contents_ignores_empty_grid_cells():
    blocks = [_block("A", [["vpip", None]])]
    win = Aux_Hud.SimpleStatWindow(aw=_fake_aw(blocks), seat=1)
    win.create_contents(1)
    win.update_contents(1)
    assert win.stat_boxes[0][0][1].widget.text() == ""


def test_multiblock_style_comes_from_block_config():
    block = _block("SB 3h", [["vpip"]], position="SB")
    block["bordercolor"] = "#123456"
    block["title_bgcolor"] = "#234567"
    block["title_fgcolor"] = "#345678"
    win = Aux_Hud.SimpleStatWindow(aw=_fake_aw([block, _block("Info", [["n"]])]), seat=1)
    win.create_contents(1)
    assert "#123456" in win.block_widgets[0][0].styleSheet()
    titles = [w for w in win.findChildren(QLabel) if w.text() == "SB 3h"]
    assert "#234567" in titles[0].styleSheet()
    assert "#345678" in titles[0].styleSheet()


def test_block_window_renders_single_block_with_pt4_headers():
    blocks = [
        _block("SB 3h", [["vpip", "pfr"]], position="SB"),
        _block("Info", [["n", "profit100"]]),
    ]
    blocks[0]["tips"] = [["VP", "PFR"]]
    win = Aux_Hud.SimpleStatWindow(aw=_fake_aw(blocks), seat=1)
    win.block_index = 0
    win.create_contents(1)
    assert len(win.stat_boxes) == 1
    assert win.stat_boxes[0][0][0].stat == "vpip"
    assert win.stat_boxes[0][0][1].stat == "pfr"
    labels = [w.text() for w in win.findChildren(QLabel)]
    assert "SB 3h" in labels
    assert "VP" in labels
    assert "PFR" in labels


# ---------------------------------------------------------------------------
# position helpers + position-conditional rendering
# ---------------------------------------------------------------------------
def test_normalize_position():
    assert Aux_Hud.normalize_position(0) == "BTN"
    assert Aux_Hud.normalize_position("S") == "SB"
    assert Aux_Hud.normalize_position("B") == "BB"
    assert Aux_Hud.normalize_position("BU") == "BTN"
    assert Aux_Hud.normalize_position(1) == "CO"
    assert Aux_Hud.normalize_position("") == ""


def test_block_visible_rules():
    assert Aux_Hud.block_visible("", "S") is True  # unbound block always shows
    assert Aux_Hud.block_visible("SB", "S") is True  # SB block for SB player
    assert Aux_Hud.block_visible("BB", "S") is False  # BB block for SB player
    assert Aux_Hud.block_visible("BU", 0) is True  # BU block for the button


def test_position_conditional_blocks_show_only_matching():
    blocks = [
        _block("SB 3h", [["vpip"]], position="SB"),
        _block("BB 3h", [["pfr"]], position="BB"),
        _block("Info", [["n"]], position=""),  # always shown
    ]
    # "current" mode filters by the last imported position (player in SB here)
    win = Aux_Hud.SimpleStatWindow(aw=_fake_aw(blocks, position="S", positional_mode="current"), seat=1)
    win.create_contents(1)
    win.update_contents(1)
    visible = [not container.isHidden() for container, _pos in win.block_widgets]
    assert visible == [True, False, True]  # SB shown, BB hidden, Info always shown


def test_all_mode_shows_every_position_panel_regardless_of_position():
    """Default 'all' mode shows SB/BB/BU together even when the player's last
    imported position matches only one of them (import lag would otherwise show a
    stale single panel)."""
    blocks = [
        _block("SB 3h", [["vpip"]], position="SB"),
        _block("BB 3h", [["pfr"]], position="BB"),
        _block("BU 3h", [["n"]], position="BTN"),
    ]
    win = Aux_Hud.SimpleStatWindow(aw=_fake_aw(blocks, position="S", positional_mode="all"), seat=1)
    win.create_contents(1)
    win.update_contents(1)
    visible = [not container.isHidden() for container, _pos in win.block_widgets]
    assert visible == [True, True, True]


def test_empty_position_pt4_blocks_all_show_for_each_villain():
    blocks = [
        _block("SB 3h", [["vpip"]]),
        _block("BB 3h", [["pfr"]]),
        _block("BU 3h", [["n"]]),
        _block("Villain Info 3H", [["profit100"]]),
    ]
    win = Aux_Hud.SimpleStatWindow(aw=_fake_aw(blocks, position="S"), seat=1)
    win.create_contents(1)
    win.update_contents(1)

    visible = [not container.isHidden() for container, _pos in win.block_widgets]
    assert visible == [True, True, True, True]


def test_multiblock_hides_hero_by_default():
    blocks = [_block("SB 3h", [["vpip"]]), _block("BB 3h", [["pfr"]])]
    aw = _fake_aw(blocks)
    aw.hud.stat_dict[1]["screen_name"] = "Hero"
    win = Aux_Hud.SimpleStatWindow(aw=aw, seat=1)
    win.create_contents(1)
    win.update_contents(1)
    assert win.isHidden()


def test_classic_stat_window_does_not_reshow_hidden_hero():
    blocks = [_block("SB 3h", [["vpip"]]), _block("BB 3h", [["pfr"]])]
    aw = _fake_aw(blocks)
    aw.positions = {1: (100, 100)}
    aw.params = {"opacity": "0.8"}
    aw.hud.table = types.SimpleNamespace(x=0, y=0)
    aw.hud.stat_dict[1]["screen_name"] = "Hero"
    win = Aux_Classic_Hud.ClassicStatWindow(aw=aw, seat=1)
    win.create_contents(1)
    win.update_contents(1)
    assert win.isHidden()


def test_show_hero_hud_true_overrides_multiblock_default():
    blocks = [_block("SB 3h", [["vpip"]]), _block("BB 3h", [["pfr"]])]
    aw = _fake_aw(blocks)
    aw.game_params.show_hero_hud = "true"
    aw.hud.stat_dict[1]["screen_name"] = "Hero"
    win = Aux_Hud.SimpleStatWindow(aw=aw, seat=1)
    win.create_contents(1)
    win.update_contents(1)
    assert not win.isHidden()


def test_villain_only_multiblock_keeps_favorite_seat_mapping():
    class DummyWindow:
        def __init__(self, _aw=None, seat=None):
            self.seat = seat

        def move(self, *_args):
            pass

        def setWindowOpacity(self, *_args):
            pass

        def create(self):
            pass

        def show(self):
            pass

    aw = Aux_Hud.SimpleHUD.__new__(Aux_Hud.SimpleHUD)
    aw.game_params = types.SimpleNamespace(name="pt4", show_hero_hud="", is_multiblock=True)
    aw.config = types.SimpleNamespace(stat_sets={})
    aw.block_layouts = [
        {"x": 0, "y": 0},
        {"x": 10, "y": 10},
    ]
    aw.positions = {}
    aw.params = {}
    aw.uses_timer = False
    aw.aw_class_window = DummyWindow
    aw.create_common = lambda *_args: DummyWindow(aw, "common")
    aw.create_contents = lambda *_args: None
    aw.update_contents = lambda *_args: None
    aw.adj_seats = lambda: [0, 3, 1, 2]
    aw.hud = types.SimpleNamespace(
        max=3,
        stat_dict={},
        site="TestSite",
        site_parameters={"fav_seat": {3: 3}},
        layout=types.SimpleNamespace(
            common=(0, 0),
            location=[None, (100, 100), (200, 200), (300, 300)],
            width=800,
            height=600,
            name="TestLayout",
        ),
        table=types.SimpleNamespace(x=0, y=0, width=800, height=600, topify=lambda _w: None),
    )

    aw.create()

    assert aw.adj == [0, 3, 1, 2]
    assert aw.positions == {1: (300, 300), 2: (100, 100), 3: (200, 200)}


def test_multiblock_update_does_not_resize_every_hand():
    aw = Aux_Hud.SimpleHUD.__new__(Aux_Hud.SimpleHUD)
    aw.block_layouts = [{"label": "Info", "position": ""}, {"label": "SB", "position": "SB"}]
    calls = []
    aw._uses_block_windows = lambda: True
    aw.resize_windows = lambda: calls.append("resize")
    aw.update_contents = lambda *_args: None
    aw._log_block_window_position = lambda *_args, **_kwargs: None
    aw.positions = {1: (100, 100)}
    aw.block_positions = {(1, 0): (100, 100)}
    aw.m_windows = {
        (1, 0): types.SimpleNamespace(pos=lambda: types.SimpleNamespace(x=lambda: 100, y=lambda: 100), isVisible=lambda: True),
    }

    aw.update_gui("hand-2")

    assert calls == []


# ---------------------------------------------------------------------------
# PT4-style colour ranges (value-conditional cell colouring)
# ---------------------------------------------------------------------------
def test_block_layout_captures_colorranges():
    """_build_block_layouts pulls stat_loth/hith/locolor/.. into the layout."""
    import xml.dom.minidom as md

    ss = Conf.Stat_sets(md.parseString(
        '<ss name="t" rows="1" cols="1"><block label="x">'
        '<stat _rowcol="(1,1)" _stat_name="vpip" stat_loth="20" stat_hith="60" '
        'stat_locolor="#00f" stat_midcolor="#fff" stat_hicolor="#f00"/></block></ss>').documentElement)
    aw = types.SimpleNamespace(game_params=ss, nrows=1, ncols=1, block_layouts=[])
    Aux_Hud.SimpleStatWindowHud._build_block_layouts(aw) if hasattr(Aux_Hud, "SimpleStatWindowHud") else None
    # call the real builder bound to a stub holding game_params
    Aux_Hud.SimpleStatWindow.__dict__.get("_build_block_layouts")
    # the builder lives on the aux-window class; invoke via the class that defines it
    import inspect
    next(c for c in inspect.getmro(type(aw)) if False) if False else None
    # Simplest: find the method on whichever Aux_Hud class defines it
    for cls in vars(Aux_Hud).values():
        if isinstance(cls, type) and "_build_block_layouts" in cls.__dict__:
            cls._build_block_layouts(aw)
            break
    cr = aw.block_layouts[0]["colorranges"][0][0]
    assert cr == {"loth": "20", "hith": "60", "locolor": "#00f", "midcolor": "#fff", "hicolor": "#f00"}


def test_simplestat_applies_colorrange_by_value(monkeypatch):
    import fpdb_3_legacy.Stats as Stats

    aw = types.SimpleNamespace(
        aux_params={"font": "Sans", "font_size": 8},
        hud=types.SimpleNamespace(layout=types.SimpleNamespace(hh_seats={1: 1}), hand_instance=None),
        aw_class_label=Aux_Hud.SimpleLabel,
    )
    cr = {"loth": "20", "hith": "60", "locolor": "#0000ff", "midcolor": "#ffffff", "hicolor": "#ff0000"}
    for value, expect in [(10, "#0000ff"), (40, "#ffffff"), (80, "#ff0000")]:
        monkeypatch.setattr(Stats, "do_stat", lambda *a, _v=value, **k: (_v / 100.0, str(_v), "x", "x", "x", "x"))
        stat = Aux_Hud.SimpleStat("vpip", 1, "default", aw, colors=cr)
        stat.update("1", {1: {}})
        assert expect in stat.lab.styleSheet().lower()


# ---------------------------------------------------------------------------
# Finitions: stat colspan/align + <hline> separators
# ---------------------------------------------------------------------------
def test_stat_parses_colspan_and_align():
    ss = _ss('<ss name="t" rows="1" cols="3"><block label="x">'
             '<stat _rowcol="(1,1)" _stat_name="vpip" colspan="2" align="left"/>'
             '<stat _rowcol="(1,3)" _stat_name="pfr"/></block></ss>')
    s = ss.blocks[0].stats[(0, 0)]
    assert s.colspan == 2
    assert s.align == "left"
    assert ss.blocks[0].stats[(0, 2)].colspan == 1  # default
    assert ss.blocks[0].stats[(0, 2)].align == "center"  # default


def test_block_parses_hline_items():
    ss = _ss('<ss name="t" rows="0" cols="0"><block label="x">'
             '<hline _rowcol="(2,1)" colspan="3" color="#d7b500"/>'
             '<stat _rowcol="(1,1)" _stat_name="vpip"/>'
             '<stat _rowcol="(3,1)" _stat_name="pfr"/></block></ss>')
    blk = ss.blocks[0]
    assert blk.hlines == [{"rowcol": (1, 0), "colspan": 3, "color": "#d7b500"}]
    assert blk.rows == 3  # hline row counted in grid sizing


def test_seat_window_renders_hline_separator():
    from PySide6.QtWidgets import QFrame

    blk = _block("BB 3h", [["vpip", "pfr"]])
    blk["hlines"] = [{"rowcol": (0, 0), "colspan": 2, "color": "#d7b500"}]
    win = Aux_Hud.SimpleStatWindow(aw=_fake_aw([blk, _block("SB", [["n"]])]), seat=1)
    win.create_contents(1)
    lines = win.findChildren(QFrame)
    assert any(ln.frameShape() == QFrame.Shape.HLine for ln in lines)


def test_colspan_align_hline_save_round_trip(tmp_path):
    """colspan/align on <stat> and <hline> survive write + reparse."""
    import shutil

    from fpdb_3_legacy import ModernHudPreferences as M

    example = os.path.join(os.path.dirname(__file__), "..", "HUD_config.xml.example")
    if not os.path.exists(example):
        import pytest
        pytest.skip("example config missing")
    cfg = tmp_path / "HUD_config.xml"
    shutil.copy(example, cfg)
    c = Conf.Config(file=str(cfg))

    dlg = M.ModernHudPreferences.__new__(M.ModernHudPreferences)
    dlg.config = c
    ss = c.doc.createElement("ss")
    ss.setAttribute("name", "RT")
    c.doc.getElementsByTagName("ss")[0].parentNode.appendChild(ss)
    profile = {"rows": 2, "cols": 3, "blocks": [{
        "label": "BB 3h", "position": "BB", "rows": 2, "cols": 3,
        "title_bgcolor": "", "title_fgcolor": "", "bordercolor": "", "x": 0, "y": 0,
        "texts": [], "hlines": [{"rowcol": (0, 0), "colspan": 3, "color": "#d7b500"}],
        "stats": [{"row": 1, "col": 0, "stat": "vpip", "colspan": 2, "align": "left"},
                  {"row": 1, "col": 2, "stat": "pfr"}],
    }]}
    dlg._write_profile_stats(ss, profile, 2, 3)
    c.save()

    blk = Conf.Config(file=str(cfg)).stat_sets["RT"].blocks[0]
    assert blk.hlines == [{"rowcol": (0, 0), "colspan": 3, "color": "#d7b500"}]
    assert blk.stats[(1, 0)].colspan == 2
    assert blk.stats[(1, 0)].align == "left"
    assert blk.stats[(1, 2)].colspan == 1


# --- block positions belong to the table they were dragged on -----------------
#
# A multi-block HUD remembers where the player put each block in a store shared
# by every table, keyed by site, layout, stat set and table size -- but not by
# table. Two CoinPoker PLO4 6-max tables therefore read and write the same
# entries, and a table that rebuilds its windows used to come back wearing
# whatever had just been dragged on the other one.
#
# A classic single-window HUD has never had this problem: its positions come
# from a layout Hud deepcopies per table. These pin the same rule for blocks.

import tempfile
from unittest.mock import MagicMock, patch


@pytest.fixture
def shared_store():
    """One positions store, as the running application has."""
    store = Aux_Hud.HUDLayoutPositionsStore.__new__(Aux_Hud.HUDLayoutPositionsStore)
    store.path = os.path.join(tempfile.mkdtemp(), "HUD_layout_positions.json")
    store.data = {"version": 1, "positions": {}}
    with patch.object(Aux_Hud, "get_positions_store", return_value=store):
        yield store


@pytest.fixture
def table(shared_store):
    """One table's stat HUD, reduced to what block positions need."""

    def make(stat_set: str = "plo4_6max_pro", max_seats: int = 6, layout_set: str = "coinpoker_default"):
        aux = Aux_Hud.SimpleHUD.__new__(Aux_Hud.SimpleHUD)
        aux.hud = MagicMock()
        aux.hud.site = "CoinPoker"
        aux.hud.max = max_seats
        # As Hud builds them: the name is on the set, and the per-size Layout
        # deepcopied out of it carries geometry and nothing else.
        aux.hud.layout_set = types.SimpleNamespace(name=layout_set)
        aux.hud.layout = types.SimpleNamespace(width=800, height=600, location=[], common=(0, 0))
        aux.game_params = MagicMock()
        aux.game_params.name = stat_set
        aux._default_canonical = lambda _key: (100, 100)
        aux._screen_to_canonical = lambda x, y: (x, y)
        aux._log_block_window_position = lambda *a, **k: None
        aux._keep_block_positions_for_this_table()
        return aux

    return make


def _layout_set(xml):
    """A real Layout_set, as Configuration builds it from the file."""
    node = minidom.parseString(xml).documentElement
    return Conf.Layout_set(node=node)


def _rebuild(aux, keys=((1, 0),)):
    """What create() does to the block windows."""
    aux._keep_block_positions_for_this_table()
    for key in keys:
        aux.block_positions[key] = aux._canonical_for(key)


def _drag(aux, seat, block_index, x, y):
    widget = MagicMock()
    widget.block_index = block_index
    widget.seat = seat
    widget.pos.return_value = MagicMock(x=lambda: x, y=lambda: y)
    aux.configure_event_cb(widget, seat)


def test_dragging_a_block_moves_it_on_that_table(table):
    aux = table()
    _rebuild(aux)

    _drag(aux, 1, 0, 640, 480)

    assert aux._canonical_for((1, 0)) == (640, 480)


def test_dragging_a_block_leaves_another_open_table_alone(table):
    first, second = table(), table()
    _rebuild(first)
    _rebuild(second)

    _drag(first, 1, 0, 640, 480)

    assert second._canonical_for((1, 0)) == (100, 100)


def test_a_table_rebuilding_its_windows_keeps_its_own_blocks(table):
    """The regression: rebuilding used to re-seed from the shared store.

    Windows are rebuilt often -- twice on creation, on a seat-count change, on
    a table-local stat-set switch -- so on a busy multi-table session the other
    table's positions arrived within a hand or two.
    """
    first, second = table(), table()
    _rebuild(first)
    _rebuild(second)
    _drag(first, 1, 0, 640, 480)

    _rebuild(second)

    assert second._canonical_for((1, 0)) == (100, 100)


def test_a_table_keeps_the_position_it_was_given_across_a_rebuild(table):
    aux = table()
    _rebuild(aux)
    _drag(aux, 1, 0, 200, 300)

    _rebuild(aux)

    assert aux._canonical_for((1, 0)) == (200, 300)


def test_only_the_dragged_block_moves(table):
    aux = table()
    _rebuild(aux, keys=[(1, 0), (1, 1), (2, 0)])

    _drag(aux, 1, 0, 640, 480)

    assert aux._canonical_for((1, 1)) == (100, 100)
    assert aux._canonical_for((2, 0)) == (100, 100)


def test_switching_stat_set_starts_the_blocks_over(table):
    """Block 2 of one profile is not block 2 of another."""
    aux = table()
    _rebuild(aux)
    _drag(aux, 1, 0, 640, 480)

    aux.game_params.name = "another_profile"
    _rebuild(aux)

    assert aux._canonical_for((1, 0)) == (100, 100)


def test_changing_table_size_starts_the_blocks_over(table):
    aux = table()
    _rebuild(aux)
    _drag(aux, 1, 0, 640, 480)

    aux.hud.max = 9
    _rebuild(aux)

    assert aux._canonical_for((1, 0)) == (100, 100)


def test_a_table_opened_later_inherits_the_last_saved_layout(table):
    """The store's purpose, which the fix must not take away."""
    first = table()
    _rebuild(first)
    _drag(first, 1, 0, 640, 480)

    fresh = table()
    _rebuild(fresh)

    assert fresh._canonical_for((1, 0)) == (640, 480)


def test_the_position_reaches_the_shared_store(table, shared_store):
    aux = table()
    _rebuild(aux)

    _drag(aux, 1, 0, 640, 480)

    assert shared_store.get_position("CoinPoker", "coinpoker_default", "plo4_6max_pro", 6, 1, 0) == (640, 480)


def test_a_layout_carries_no_name_of_its_own():
    """Why the name has to be read off the set.

    Hud deepcopies layout_set.layout[max] into hud.layout. That object holds
    max, width, height, locations and hh_seats -- asking it for a name gets
    the fallback, every time, for every layout set there is.
    """
    layout_set = _layout_set('<ls name="coinpoker_default"><layout max="6" width="800" height="600"/></ls>')

    assert layout_set.name == "coinpoker_default"
    assert not hasattr(layout_set.layout[6], "name")


def test_the_layout_name_is_the_one_the_set_is_called():
    aux = Aux_Hud.SimpleHUD.__new__(Aux_Hud.SimpleHUD)
    layout_set = _layout_set('<ls name="coinpoker_default"><layout max="6" width="800" height="600"/></ls>')
    aux.hud = types.SimpleNamespace(layout_set=layout_set, layout=layout_set.layout[6])

    assert aux._layout_name() == "coinpoker_default"


def test_two_layout_sets_do_not_share_block_positions(table):
    """The store is keyed by layout, and that key has to mean something.

    Reading the name off the per-size Layout answered "default" for all of
    them, so every layout set of a site wrote over the same entries.
    """
    six_max, nine_max = table(layout_set="coinpoker_default"), table(layout_set="coinpoker_zoom")
    _rebuild(six_max)
    _rebuild(nine_max)

    _drag(six_max, 1, 0, 640, 480)
    fresh = table(layout_set="coinpoker_zoom")
    _rebuild(fresh)

    assert fresh._canonical_for((1, 0)) == (100, 100)


def test_a_table_changing_layout_starts_the_blocks_over(table):
    aux = table(layout_set="coinpoker_default")
    _rebuild(aux)
    _drag(aux, 1, 0, 640, 480)

    aux.hud.layout_set = types.SimpleNamespace(name="coinpoker_zoom")
    _rebuild(aux)

    assert aux._canonical_for((1, 0)) == (100, 100)


class _DummyWindow:
    """Stands in for a stat window through a real create() cycle."""

    def __init__(self, _aw=None, seat=None):
        self.seat = seat
        self.position = (0, 0)

    def move(self, x, y):
        self.position = (x, y)

    def setWindowOpacity(self, *_args):
        pass

    def create(self):
        pass

    def show(self):
        pass

    def hide(self):
        pass

    def destroy(self):
        pass


def _real_hud(shared_store, layout_set="coinpoker_default", stat_set="plo4_6max_pro"):
    """A SimpleHUD taken far enough to run create() for real."""
    aw = Aux_Hud.SimpleHUD.__new__(Aux_Hud.SimpleHUD)
    aw.game_params = types.SimpleNamespace(name=stat_set, show_hero_hud="", is_multiblock=True)
    aw.config = types.SimpleNamespace(stat_sets={})
    aw.block_layouts = [{"x": 0, "y": 0}, {"x": 10, "y": 10}]
    aw.positions = {}
    aw.params = {}
    aw.uses_timer = False
    aw.aw_class_window = _DummyWindow
    aw.create_common = lambda *_args: _DummyWindow(aw, "common")
    aw.create_contents = lambda *_args: None
    aw.update_contents = lambda *_args: None
    aw.adj_seats = lambda: [0, 3, 1, 2]
    aw.hud = types.SimpleNamespace(
        max=3,
        stat_dict={},
        site="CoinPoker",
        site_parameters={"fav_seat": {3: 3}},
        layout_set=types.SimpleNamespace(name=layout_set),
        layout=types.SimpleNamespace(
            common=(0, 0),
            location=[None, (100, 100), (200, 200), (300, 300)],
            width=800,
            height=600,
        ),
        table=types.SimpleNamespace(x=0, y=0, width=800, height=600, topify=lambda _w: None),
        geometry_generation=0,
    )
    return aw


def test_a_second_create_keeps_the_blocks_where_the_player_put_them(shared_store):
    """The real cycle: idle_create runs create() twice on every HUD.

    Each run used to start from an empty cache and re-seed every block from
    the shared store, so the second run of a HUD could already be wearing
    another table's positions.
    """
    aw = _real_hud(shared_store)
    aw.create()
    _drag(aw, 1, 0, 640, 480)

    aw.create()

    assert aw._canonical_for((1, 0)) == (640, 480)


def test_a_second_table_creating_twice_keeps_its_own_blocks(shared_store):
    first, second = _real_hud(shared_store), _real_hud(shared_store)
    first.create()
    second.create()
    before = second._canonical_for((1, 0))

    _drag(first, 1, 0, 640, 480)
    second.create()

    assert second._canonical_for((1, 0)) == before


def test_creating_a_hud_takes_over_the_old_arrangement(shared_store):
    """The migration has to be wired into the real cycle, not only callable.

    Everything above calls _claim_legacy_block_positions directly, so without
    this the call could be dropped from create() and nothing would notice.
    """
    _save_legacy(shared_store, 1, 0, 640, 480, max_seats=3)
    aw = _real_hud(shared_store)

    aw.create()

    assert _legacy_keys(shared_store) == []
    assert aw._stored_position(1, 0) == (640, 480)


def test_creating_a_hud_places_its_blocks_from_the_old_arrangement(shared_store):
    _save_legacy(shared_store, 1, 0, 640, 480, max_seats=3)
    aw = _real_hud(shared_store)

    aw.create()

    assert aw._canonical_for((1, 0)) == (640, 480)


def test_creating_again_after_a_layout_change_starts_over(shared_store):
    aw = _real_hud(shared_store)
    aw.create()
    _drag(aw, 1, 0, 640, 480)
    moved = aw._canonical_for((1, 0))

    aw.hud.layout_set = types.SimpleNamespace(name="coinpoker_zoom")
    aw.create()

    assert aw._canonical_for((1, 0)) != moved


# --- positions saved before layouts were told apart ----------------------------
#
# Every layout of a site used to file its blocks under the literal "default",
# so they all read and wrote one another's. There is one such arrangement and
# there may be several layout sets, so it is given to the first layout that
# opens and the shared entries go -- otherwise the collision outlives the fix.


def _save_legacy(store, seat, block_index, x, y, *, stat_set="plo4_6max_pro", max_seats=6):
    store.set_position("CoinPoker", Aux_Hud.LEGACY_LAYOUT_NAME, stat_set, max_seats, seat, block_index, x, y)


def _legacy_keys(store):
    return [key for key in store.data["positions"] if f"/{Aux_Hud.LEGACY_LAYOUT_NAME}/" in key]


def test_an_arrangement_saved_before_the_fix_is_taken_over(table, shared_store):
    _save_legacy(shared_store, 1, 0, 640, 480)
    aux = table(layout_set="coinpoker_default")

    aux._claim_legacy_block_positions()

    assert aux._stored_position(1, 0) == (640, 480)


def test_taking_it_over_leaves_nothing_shared_behind(table, shared_store):
    """What makes it a migration rather than a fallback."""
    _save_legacy(shared_store, 1, 0, 640, 480)
    aux = table(layout_set="coinpoker_default")

    aux._claim_legacy_block_positions()

    assert _legacy_keys(shared_store) == []


def test_the_whole_arrangement_moves_at_once(table, shared_store):
    for seat in (1, 2, 3):
        for block in (0, 1):
            _save_legacy(shared_store, seat, block, 10 * seat, 10 * block)
    aux = table(layout_set="coinpoker_default")

    aux._claim_legacy_block_positions()

    assert aux._stored_position(3, 1) == (30, 10)
    assert _legacy_keys(shared_store) == []


def test_moving_the_arrangement_writes_the_file_once(table, shared_store):
    # A HUD holds a block per seat; one write per block would be a file
    # rewritten dozens of times as it starts.
    for seat in (1, 2, 3, 4, 5, 6):
        _save_legacy(shared_store, seat, 0, 10, 20)
    aux = table(layout_set="coinpoker_default")

    with patch.object(shared_store, "save") as saved:
        aux._claim_legacy_block_positions()

    assert saved.call_count == 1


def test_the_second_layout_to_open_starts_from_its_own_places(table, shared_store):
    """The policy: one old arrangement, one claimant.

    What the second layout had before was never its own -- it was reading the
    first one's by accident, which is the collision being removed.
    """
    _save_legacy(shared_store, 1, 0, 640, 480)
    first, second = table(layout_set="coinpoker_default"), table(layout_set="coinpoker_zoom")

    first._claim_legacy_block_positions()
    second._claim_legacy_block_positions()

    _rebuild(second)
    assert second._canonical_for((1, 0)) == (100, 100)


def test_a_layout_that_already_has_its_own_keeps_them(table, shared_store):
    _save_legacy(shared_store, 1, 0, 640, 480)
    aux = table(layout_set="coinpoker_default")
    _rebuild(aux)
    _drag(aux, 1, 0, 200, 300)

    aux._claim_legacy_block_positions()

    assert aux._stored_position(1, 0) == (200, 300)
    assert _legacy_keys(shared_store) == []


def test_an_old_entry_of_another_stat_set_is_left_where_it_is(table, shared_store):
    _save_legacy(shared_store, 1, 0, 640, 480, stat_set="some_other_profile")
    aux = table(layout_set="coinpoker_default")

    aux._claim_legacy_block_positions()

    assert aux._stored_position(1, 0) is None
    assert len(_legacy_keys(shared_store)) == 1


def test_a_layout_actually_named_default_keeps_the_arrangement(table, shared_store):
    # The shipped configuration has a layout set called "default", so the old
    # name and a real one can be the same string. There is nothing to move --
    # the entries are already under its own name.
    _save_legacy(shared_store, 1, 0, 640, 480)
    aux = table(layout_set=Aux_Hud.LEGACY_LAYOUT_NAME)

    aux._claim_legacy_block_positions()

    assert aux._stored_position(1, 0) == (640, 480)


def test_a_layout_actually_named_default_claims_the_arrangement(table, shared_store):
    """Having nothing to move is not the same as having nothing to claim.

    The claim is what stops another layout of the site taking the arrangement
    afterwards; inferring it from entries having moved would leave this one
    the only layout that can be robbed.
    """
    _save_legacy(shared_store, 1, 0, 640, 480)
    default_named = table(layout_set=Aux_Hud.LEGACY_LAYOUT_NAME)
    default_named._claim_legacy_block_positions()

    latecomer = table(layout_set="coinpoker_zoom")
    latecomer._claim_legacy_block_positions()

    assert default_named._stored_position(1, 0) == (640, 480)
    assert latecomer._stored_position(1, 0) is None


def test_the_claim_is_recorded_once(table, shared_store):
    _save_legacy(shared_store, 1, 0, 640, 480)
    aux = table(layout_set="coinpoker_default")
    aux._claim_legacy_block_positions()

    with patch.object(shared_store, "save") as saved:
        aux._claim_legacy_block_positions()

    assert not saved.called


def test_a_claimed_arrangement_is_not_taken_by_a_later_layout(table, shared_store):
    _save_legacy(shared_store, 1, 0, 640, 480)
    first = table(layout_set="coinpoker_default")
    first._claim_legacy_block_positions()

    latecomer = table(layout_set="coinpoker_zoom")
    latecomer._claim_legacy_block_positions()

    assert first._stored_position(1, 0) == (640, 480)
    assert latecomer._stored_position(1, 0) is None


def test_nothing_to_move_writes_nothing(table, shared_store):
    aux = table(layout_set="coinpoker_default")

    with patch.object(shared_store, "save") as saved:
        aux._claim_legacy_block_positions()

    assert not saved.called
