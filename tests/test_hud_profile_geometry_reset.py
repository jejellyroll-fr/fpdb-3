"""Geometry lifecycle across a HUD profile change, and the positions store's
failure behaviour.

The profile-change paths (the config poll in HUD_main and the table menu) used
to recreate the aux windows without rebuilding the live layout, so profile B
inherited profile A's dragged or already-scaled positions, and resize_windows()
kept treating those as the reference. They now share Hud.rebuild_with_stat_set,
which resets the geometry from the shared layout set first. "Save layout" also
used to pin every computed default into the positions JSON (making later XML
edits dead) and to rewrite block x/y attributes from unchanging in-memory
values; both are gone. The JSON store now reports write failures and never
overwrites a file it could not parse.
"""

from __future__ import annotations

import copy
import json
import os
from types import SimpleNamespace

import pytest

from fpdb_3_legacy import Aux_Hud, Hud
from fpdb_3_legacy.hud_profiles import HudPositionScope

MAX = 6
XML_LOCATIONS = [None, (10, 20), (20, 40), (30, 60), (40, 80), (50, 100), (60, 120)]
XML_COMMON = (5, 5)
XML_WIDTH = 800
XML_HEIGHT = 600


def _layout_set() -> SimpleNamespace:
    return SimpleNamespace(
        name="default",
        layout={
            MAX: SimpleNamespace(
                width=XML_WIDTH,
                height=XML_HEIGHT,
                location=list(XML_LOCATIONS),
                common=XML_COMMON,
                hh_seats=[None, *range(1, MAX + 1)],
            )
        },
    )


def _make_hud(table_size: tuple[int, int] = (XML_WIDTH, XML_HEIGHT)) -> Hud.Hud:
    """A real Hud instance (via __new__) with the smallest usable surroundings."""
    layout_set = _layout_set()
    config = SimpleNamespace(get_layout=lambda site, game_type: layout_set)
    hud = Hud.Hud.__new__(Hud.Hud)
    hud.config = config
    hud.site = "TestSite"
    hud.poker_game = "holdem"
    hud.game_type = "ring"
    hud.max = MAX
    hud.table_name = "table-1"
    hud.stat_dict = {}
    hud.table = SimpleNamespace(
        site="TestSite", key="table-1", x=0, y=0, width=table_size[0], height=table_size[1]
    )
    hud.layout_set = layout_set
    hud.layout = copy.deepcopy(layout_set.layout[MAX])
    hud.supported_games_parameters = {"game_stat_set": SimpleNamespace(name="ProfileA")}
    hud.position_scope = HudPositionScope.from_hud(hud)
    hud.aux_windows = []
    return hud


class _RecordingAux:
    """Stands in for a SimpleHUD: records the rebuild sequence."""

    def __init__(self, hud: Hud.Hud, on_create=None) -> None:
        self.hud = hud
        self.game_params = hud.supported_games_parameters["game_stat_set"]
        self.calls: list[str] = []
        self.on_create = on_create

    def destroy(self) -> None:
        self.calls.append("destroy")

    def refresh_stats_layout(self) -> None:
        self.calls.append("refresh_stats_layout")

    def create(self) -> None:
        self.calls.append("create")
        if self.on_create is not None:
            self.on_create()

    def update_gui(self, _hand_id) -> None:
        self.calls.append("update_gui")


@pytest.fixture
def store(tmp_path, monkeypatch):
    """A positions store on disk, so saves really hit the file."""
    instance = Aux_Hud.HUDLayoutPositionsStore.__new__(Aux_Hud.HUDLayoutPositionsStore)
    instance.path = str(tmp_path / "HUD_layout_positions.json")
    instance.data = {"version": 2, "positions": {}}
    instance.load_error = False
    monkeypatch.setattr(Aux_Hud, "get_positions_store", lambda: instance)
    return instance


def _stat_set(name: str) -> SimpleNamespace:
    return SimpleNamespace(name=name)


# --- The profile change resets the geometry ---------------------------------


def test_profile_change_rebuilds_the_layout_from_the_xml_not_the_dragged_state() -> None:
    hud = _make_hud(table_size=(1200, 900))
    aux = _RecordingAux(hud)
    hud.aux_windows = [aux]

    # What profile A leaves behind: a dragged slot, already scaled to the
    # table, plus the frozen reference that resize_windows() trusts.
    hud.layout.location[3] = (600, 450)
    hud.layout.common = (12, 12)
    hud.layout.width = 1200
    hud.layout.height = 900
    hud.ref_layout_width = XML_WIDTH
    hud.ref_layout_height = XML_HEIGHT
    hud.ref_layout_locations = list(XML_LOCATIONS)
    hud.ref_layout_locations[3] = (450, 338)  # dragged value in reference space
    hud.ref_layout_common = (8, 8)

    Hud.rebuild_with_stat_set(hud, _stat_set("ProfileB"))

    assert hud.layout.location[3] == XML_LOCATIONS[3], "B must start from its own XML default"
    assert hud.layout.common == XML_COMMON
    assert hud.layout.width == XML_WIDTH and hud.layout.height == XML_HEIGHT
    assert hud.ref_layout_width == XML_WIDTH
    assert hud.ref_layout_locations[3] == XML_LOCATIONS[3]
    assert hud.ref_layout_common == XML_COMMON
    assert hud.position_scope.profile == "ProfileB"
    assert aux.calls == ["destroy", "refresh_stats_layout", "create"]


def test_a_resize_after_a_profile_change_scales_from_the_xml_reference() -> None:
    hud = _make_hud(table_size=(1200, 900))
    hud.aux_windows = []

    Hud.rebuild_with_stat_set(hud, _stat_set("ProfileB"))
    hud.resize_windows()  # table is 1200x900, reference 800x600

    assert hud.layout.location[3] == (45, 90)  # (30,60) * 1.5
    assert hud.ref_layout_locations[3] == XML_LOCATIONS[3], "the reference must stay pristine"

    # Resize back: the round trip is pixel-exact, no drift.
    hud.table.width = XML_WIDTH
    hud.table.height = XML_HEIGHT
    hud.resize_windows()
    assert hud.layout.location[3] == XML_LOCATIONS[3]


def test_a_to_b_to_a_restores_each_profiles_own_positions(store) -> None:
    """Classic HUD: A's dragged slot comes back when A is re-selected, B never sees it."""
    hud = _make_hud()

    aux = Aux_Hud.SimpleHUD.__new__(Aux_Hud.SimpleHUD)
    aux.hud = hud
    aux.game_params = _stat_set("ProfileA")
    aux.block_layouts = [{"x": 0, "y": 0}]  # single block => classic renderer
    aux.positions = {}
    aux.adj = [0, *range(1, MAX + 1)]
    aux.m_windows = {}
    calls: list[str] = []

    def _create() -> None:
        calls.append("create")
        # What SimpleHUD.create does on the classic path.
        aux._ensure_reference()
        aux._apply_classic_position_overrides()

    aux.destroy = lambda: calls.append("destroy")  # type: ignore[method-assign]
    aux.refresh_stats_layout = lambda: calls.append("refresh_stats_layout")  # type: ignore[method-assign]
    aux.create = _create  # type: ignore[method-assign]
    aux.update_gui = lambda _h: calls.append("update_gui")  # type: ignore[method-assign]
    hud.aux_windows = [aux]

    # Drag seat 3 under profile A; it persists to the scoped store.
    assert aux._persist_position_override(3, (400, 250)) is True

    # Profile A's live layout is then dragged/scaled, as a session would leave it.
    hud.layout.location[3] = (600, 450)
    hud.layout.width = 1200

    Hud.rebuild_with_stat_set(hud, _stat_set("ProfileB"))
    assert hud.layout.location[3] == XML_LOCATIONS[3], "B gets the XML default, not A's drag"

    Hud.rebuild_with_stat_set(hud, _stat_set("ProfileA"))
    assert hud.layout.location[3] == (400, 250), "A gets its own saved position back"
    assert hud.ref_layout_locations[3] == (400, 250), "and the reference agrees, so a resize keeps it"
    assert calls == ["destroy", "refresh_stats_layout", "create", "destroy", "refresh_stats_layout", "create"]


def test_the_table_menu_uses_the_same_rebuild(monkeypatch) -> None:
    """change_stat_set must go through Hud.rebuild_with_stat_set, not its own copy."""
    hud = _make_hud()
    aux = _RecordingAux(hud)
    hud.aux_windows = [aux]
    parentwin = SimpleNamespace(hud=hud, aw=aux)
    popup = Aux_Hud.SimpleTablePopupMenu.__new__(Aux_Hud.SimpleTablePopupMenu)
    popup.parentwin = parentwin
    popup.delete_event = lambda: None

    calls: list[tuple[object, object]] = []
    real = Hud.rebuild_with_stat_set

    def spy(h, ss):
        calls.append((h, ss))
        real(h, ss)

    monkeypatch.setattr(Aux_Hud.Hud, "rebuild_with_stat_set", staticmethod(spy))
    popup._update_stat_set_in_config = lambda name: _stat_set(name)

    popup.change_stat_set(0, {0: ("ProfileB", "ProfileB")})

    assert calls == [(hud, calls[0][1])] and calls[0][1].name == "ProfileB"
    assert hud.position_scope.profile == "ProfileB"
    assert hud.layout.location[3] == XML_LOCATIONS[3]
    assert aux.calls == ["destroy", "refresh_stats_layout", "create"]


# --- Save layout no longer freezes defaults or rewrites block offsets --------


def _multi_block_aux(hud) -> Aux_Hud.SimpleHUD:
    aux = Aux_Hud.SimpleHUD.__new__(Aux_Hud.SimpleHUD)
    aux.hud = hud
    aux.game_params = hud.supported_games_parameters["game_stat_set"]
    aux.block_layouts = [
        {"id": "core", "label": "core", "x": 0, "y": 0, "scope": "player"},
        {"id": "", "label": "positional", "x": 12, "y": 34, "scope": "player"},
    ]
    aux.block_positions = {(3, 0): (30, 60), (3, 1): (42, 94)}  # as create() seeds them
    aux.positions = {}
    aux.adj = [0, *range(1, MAX + 1)]
    aux.m_windows = {}
    return aux


def test_save_layout_pins_only_dragged_blocks_and_never_the_xml_offsets(store) -> None:
    hud = _make_hud()
    hud.config = SimpleNamespace(
        get_layout=lambda site, game_type: hud.layout_set,
        get_stat_set_node=lambda name: pytest.fail("block x/y must not be rewritten"),
    )
    aux = _multi_block_aux(hud)
    hud.aux_windows = [aux]

    aux.save_layout()

    assert store.data["positions"] == {}, "computed defaults must not be frozen into the JSON"

    # Now mark one block as dragged; only that one is pinned, under its id.
    aux._dragged_block_keys = {(3, 0)}
    aux._dragged_marks_profile = aux._block_profile()
    aux.save_layout()

    positions = store.data["positions"]
    assert len(positions) == 1
    key = next(iter(positions))
    assert json.loads(key)[-1] == "core", "the block id is the store key, not the index"
    assert positions[key] == {"x": 30, "y": 60}


def test_save_layout_ignores_drag_marks_from_another_profile(store) -> None:
    hud = _make_hud()
    aux = _multi_block_aux(hud)
    hud.aux_windows = [aux]
    aux._dragged_block_keys = {(3, 0)}
    aux._dragged_marks_profile = ("default", "SomeOtherProfile", MAX)

    aux.save_layout()

    assert store.data["positions"] == {}, "a mark from profile A must not be written under B"


def test_block_store_id_falls_back_to_the_index_and_old_entries_still_apply(store) -> None:
    hud = _make_hud()
    aux = _multi_block_aux(hud)
    hud.aux_windows = [aux]

    assert aux._block_store_id(0) == "core"
    assert aux._block_store_id(1) == 1, "a block without id keeps the historical index key"

    # A position saved before block 0 gained its id lives under the index key.
    store.set_position("TestSite", "default", "ProfileA", MAX, 3, 0, 111, 222, game="holdem", game_type="ring")
    assert aux._stored_position(3, 0) == (111, 222)


def test_save_block_offsets_is_gone() -> None:
    assert not hasattr(Aux_Hud.SimpleHUD, "_save_block_offsets")


# --- The positions store reports failures and never destroys an unreadable file


def _bare_store(path) -> Aux_Hud.HUDLayoutPositionsStore:
    instance = Aux_Hud.HUDLayoutPositionsStore.__new__(Aux_Hud.HUDLayoutPositionsStore)
    instance.path = str(path)
    instance.data = {"version": 2, "positions": {}}
    instance.load_error = False
    return instance


def test_a_corrupt_file_is_preserved_not_overwritten(tmp_path) -> None:
    path = tmp_path / "HUD_layout_positions.json"
    path.write_text("{ not json", encoding="utf-8")

    instance = _bare_store(path)
    assert instance.load() is False

    assert instance.set_position("TestSite", "default", "P", MAX, 3, "classic", 400, 250) is True

    assert json.loads(path.read_text(encoding="utf-8"))["positions"], "the new store is valid JSON"
    assert path.with_suffix(".json.corrupt").read_text(encoding="utf-8") == "{ not json"
    # and the new entry is readable by a fresh store
    reopened = _bare_store(path)
    assert reopened.load() is True
    assert reopened.get_position("TestSite", "default", "P", MAX, 3, "classic") == (400, 250)


def test_a_failed_write_is_reported(tmp_path, monkeypatch) -> None:
    path = tmp_path / "HUD_layout_positions.json"
    instance = _bare_store(path)
    assert instance.load() is True  # absent file is fine

    monkeypatch.setattr(Aux_Hud.time, "sleep", lambda _s: None)
    monkeypatch.setattr(Aux_Hud.os, "replace", lambda *a, **k: (_ for _ in ()).throw(PermissionError("locked")))

    assert instance.set_position("TestSite", "default", "P", MAX, 3, "classic", 1, 2) is False
    assert not path.exists(), "a failed save must not leave a half-written file behind"


def test_retries_are_bounded(tmp_path, monkeypatch) -> None:
    path = tmp_path / "HUD_layout_positions.json"
    instance = _bare_store(path)

    attempts = []
    real_replace = os.replace

    def flaky(src, dst):
        attempts.append(1)
        if len(attempts) < Aux_Hud.HUDLayoutPositionsStore.SAVE_RETRIES:
            raise PermissionError("locked")
        return real_replace(src, dst)

    monkeypatch.setattr(Aux_Hud.time, "sleep", lambda _s: None)
    monkeypatch.setattr(Aux_Hud.os, "replace", flaky)

    assert instance.set_position("TestSite", "default", "P", MAX, 3, "classic", 7, 8) is True
    assert len(attempts) == Aux_Hud.HUDLayoutPositionsStore.SAVE_RETRIES
