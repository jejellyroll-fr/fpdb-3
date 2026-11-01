"""A drag on one table must line up the other tables already on screen.

Every HUD deep-copies its layout when it is created, so writing a drag through
to the shared layout_set only reached tables opened *later*: while multi-tabling,
adjusting one table left the ones already open untouched until they restarted.

Pairing tables by layout set was too coarse, though: CoinPoker files every game
under one layout, so PLO4 and AoF PLO4 tables dragged each other around. Tables
are now paired on the whole HudPositionScope, and these tests state each
dimension of it separately.
"""

from __future__ import annotations

from types import SimpleNamespace

from fpdb_3_legacy.Aux_Base import AuxSeats
from fpdb_3_legacy.hud_profiles import HudPositionScope

LAYOUT_SET = object()  # the shared layout object a room's tables draw with


class _Point:
    def __init__(self, x: int, y: int) -> None:
        self._x, self._y = x, y

    def x(self) -> int:
        return self._x

    def y(self) -> int:
        return self._y


class _Widget:
    def __init__(self, x: int, y: int) -> None:
        self._p = _Point(x, y)

    def pos(self) -> _Point:
        return self._p


class _Aux:
    """Stand-in aux window recording that it was asked to re-place its windows."""

    def __init__(self) -> None:
        self.resized = 0

    def resize_windows(self) -> None:
        self.resized += 1


def _make_hud(
    *,
    width: int = 920,
    height: int = 652,
    max_seats: int = 3,
    layout_set: object = LAYOUT_SET,
    name: str = "table",
    site: str = "TestSite",
    game: str = "omahahi",
    game_type: str = "ring",
    profile: str = "plo4_6max_pro",
    layout: str = "default",
) -> SimpleNamespace:
    return SimpleNamespace(
        table=SimpleNamespace(x=100, y=200, width=width, height=height),
        layout=SimpleNamespace(location=[None, (10, 10), (20, 20), (30, 30)], common=(0, 0)),
        layout_set=layout_set,
        max=max_seats,
        site=site,
        poker_game=game,
        game_type=game_type,
        position_scope=HudPositionScope(site, game, game_type, max_seats, profile, layout),
        table_name=name,
        aux_windows=[_Aux()],
        ref_layout_width=920,
        ref_layout_height=652,
        ref_layout_locations=[None, (10, 10), (20, 20), (30, 30)],
        ref_layout_common=(0, 0),
        save_layout=lambda: None,
    )


def _make_aux(source: SimpleNamespace, others: list[SimpleNamespace]) -> AuxSeats:
    aux = object.__new__(AuxSeats)
    huds = {f"t{i}": hud for i, hud in enumerate([source, *others])}
    source.parent = SimpleNamespace(hud_dict=huds)
    for hud in others:
        hud.parent = source.parent
    aux.hud = source
    aux.positions = {}
    aux.adj = [0, 1, 2, 3]  # identity: visual seat == layout slot
    return aux


def test_drag_is_mirrored_to_an_open_table_of_the_same_layout() -> None:
    source, other = _make_hud(name="A"), _make_hud(name="B")
    aux = _make_aux(source, [other])

    aux.configure_event_cb(_Widget(150, 260), 2)  # -> relative (50, 60)

    assert source.layout.location[2] == (50, 60)
    assert other.layout.location[2] == (50, 60), "the open table must follow the drag"
    assert other.aux_windows[0].resized == 1, "the open table must re-place its windows"


def test_mirrored_drag_is_scaled_to_a_differently_sized_table() -> None:
    source = _make_hud(name="A", width=920, height=652)
    other = _make_hud(name="B", width=460, height=326)  # half size
    aux = _make_aux(source, [other])

    aux.configure_event_cb(_Widget(150, 260), 2)  # -> relative (50, 60)

    assert other.layout.location[2] == (25, 30)


def test_mirrored_drag_survives_the_other_tables_next_resize() -> None:
    # Hud.resize_windows rebuilds layout.location from ref_layout_locations, so
    # the reference must be updated too or the mirrored drag is reverted.
    source, other = _make_hud(name="A"), _make_hud(name="B")
    aux = _make_aux(source, [other])

    aux.configure_event_cb(_Widget(150, 260), 2)

    assert other.ref_layout_locations[2] == (50, 60)
    assert source.ref_layout_locations[2] == (50, 60), "the dragged table must keep it too"


def test_tables_with_another_layout_or_seat_count_are_untouched() -> None:
    source = _make_hud(name="A")
    foreign_layout = _make_hud(name="B", layout_set=object(), layout="tournament")
    other_max = _make_hud(name="C", max_seats=6)
    aux = _make_aux(source, [foreign_layout, other_max])

    aux.configure_event_cb(_Widget(150, 260), 2)

    assert foreign_layout.layout.location[2] == (20, 20)
    assert other_max.layout.location[2] == (20, 20)
    assert foreign_layout.aux_windows[0].resized == 0
    assert other_max.aux_windows[0].resized == 0


def test_another_game_on_the_same_layout_is_untouched() -> None:
    """The reported CoinPoker bug: one layout, one seat count, two games."""
    source = _make_hud(name="PLO4", game="omahahi", profile="plo4_6max_pro")
    aof = _make_hud(name="AoF", game="aof_omaha", profile="aof_advanced")
    aux = _make_aux(source, [aof])

    aux.configure_event_cb(_Widget(150, 260), 2)

    assert source.layout.location[2] == (50, 60)
    assert aof.layout.location[2] == (20, 20), "AoF must not follow a PLO4 drag"
    assert aof.aux_windows[0].resized == 0


def test_another_profile_on_the_same_game_is_untouched() -> None:
    source = _make_hud(name="A", profile="plo4_6max_pro")
    other_profile = _make_hud(name="B", profile="plo4_simple")
    aux = _make_aux(source, [other_profile])

    aux.configure_event_cb(_Widget(150, 260), 2)

    assert other_profile.layout.location[2] == (20, 20)


def test_another_room_or_format_is_untouched() -> None:
    source = _make_hud(name="A", site="CoinPoker", game_type="ring")
    other_room = _make_hud(name="B", site="Winamax", game_type="ring")
    tournament = _make_hud(name="C", site="CoinPoker", game_type="tour")
    aux = _make_aux(source, [other_room, tournament])

    aux.configure_event_cb(_Widget(150, 260), 2)

    assert other_room.layout.location[2] == (20, 20)
    assert tournament.layout.location[2] == (20, 20)


def test_a_hud_without_a_scope_mirrors_to_nothing() -> None:
    """An unidentified HUD must not claim to share anyone's arrangement."""
    source = _make_hud(name="A")
    source.position_scope = None
    other = _make_hud(name="B")
    aux = _make_aux(source, [other])

    aux.configure_event_cb(_Widget(150, 260), 2)

    assert source.layout.location[2] == (50, 60), "its own drag still applies"
    assert other.layout.location[2] == (20, 20)


def test_common_drag_is_mirrored_too() -> None:
    source, other = _make_hud(name="A"), _make_hud(name="B")
    aux = _make_aux(source, [other])

    aux.configure_event_cb(_Widget(130, 230), "common")  # -> relative (30, 30)

    assert other.layout.common == (30, 30)
    assert other.ref_layout_common == (30, 30)


def test_drag_without_a_parent_hud_dict_does_not_crash() -> None:
    source = _make_hud(name="A")
    aux = object.__new__(AuxSeats)
    aux.hud = source
    aux.positions = {}
    aux.adj = [0, 1, 2, 3]
    source.parent = None  # HUD not attached to a HUD_main (unit/test context)

    aux.configure_event_cb(_Widget(150, 260), 2)

    assert source.layout.location[2] == (50, 60)
