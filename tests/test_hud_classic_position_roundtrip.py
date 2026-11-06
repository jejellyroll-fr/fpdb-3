"""A dragged classic HUD must come back where it was left -- for its own game.

The classic one-window-per-seat HUD is the layout the reported CoinPoker bug
was seen on: PLO4 and AoF PLO4 share a layout set and a seat count, so a drag
on one moved the other, and a restart handed both the same XML geometry. The
drag path and the restart path are covered separately elsewhere; what is
pinned here is the whole round trip through the on-disk store.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fpdb_3_legacy import Aux_Hud


def _shared_layout_set(max_seats: int = 6) -> SimpleNamespace:
    """The site-wide layout set, in its own reference space.

    CoinPoker files every game under one of these, which is what made two
    games collide; the tests below share a single instance on purpose.
    """
    return SimpleNamespace(
        name="default",
        layout={
            max_seats: SimpleNamespace(
                width=920,
                height=652,
                location=[None, *[(10 * seat, 20 * seat) for seat in range(1, max_seats + 1)]],
                common=(0, 0),
            )
        },
    )


LAYOUT_SET = _shared_layout_set()


@pytest.fixture
def store(tmp_path, monkeypatch):
    """A positions store on disk, so a reload really re-reads the file."""
    instance = Aux_Hud.HUDLayoutPositionsStore.__new__(Aux_Hud.HUDLayoutPositionsStore)
    instance.path = str(tmp_path / "HUD_layout_positions.json")
    instance.data = {"version": 2, "positions": {}}
    monkeypatch.setattr(Aux_Hud, "get_positions_store", lambda: instance)
    return instance


def _make_aux(game: str, profile: str, *, max_seats: int = 6, table_size: tuple[int, int] = (920, 652)):
    """A classic (non-block) SimpleHUD wired to the smallest usable HUD stub."""
    aux = Aux_Hud.SimpleHUD.__new__(Aux_Hud.SimpleHUD)
    width, height = table_size
    aux.hud = SimpleNamespace(
        site="CoinPoker",
        poker_game=game,
        game_type="ring",
        max=max_seats,
        layout_set=LAYOUT_SET,
        layout=SimpleNamespace(
            location=[None, *[(10 * seat, 20 * seat) for seat in range(1, max_seats + 1)]],
            common=(0, 0),
            width=920,
            height=652,
        ),
        table=SimpleNamespace(x=0, y=0, width=width, height=height),
    )
    # A single block means the classic one-window-per-seat renderer.
    aux.block_layouts = [{"x": 0, "y": 0}]
    aux.game_params = SimpleNamespace(name=profile)
    return aux


def _reload(aux):
    """Restart the HUD: fresh layout from the XML, then the stored overrides."""
    max_seats = aux.hud.max
    aux.hud.layout.location = [None, *[(10 * seat, 20 * seat) for seat in range(1, max_seats + 1)]]
    aux.hud.layout.common = (0, 0)
    aux._apply_classic_position_overrides()
    return aux.hud.layout


def test_a_drag_survives_a_restart(store) -> None:
    aux = _make_aux("aof_omaha", "aof_advanced")

    aux._persist_position_override(3, (400, 250))

    assert _reload(aux).location[3] == (400, 250)


def test_two_games_sharing_a_layout_keep_their_own_positions(store) -> None:
    """The reported bug: same room, same layout set, same seats, two games."""
    plo = _make_aux("omahahi", "plo4_6max_pro")
    aof = _make_aux("aof_omaha", "aof_advanced")

    plo._persist_position_override(3, (400, 250))
    aof._persist_position_override(3, (111, 222))

    assert _reload(plo).location[3] == (400, 250)
    assert _reload(aof).location[3] == (111, 222), "AoF must keep its own drag"


def test_a_game_never_dragged_keeps_the_shipped_layout(store) -> None:
    """Moving one game must not silently place the other one for the player."""
    plo = _make_aux("omahahi", "plo4_6max_pro")
    aof = _make_aux("aof_omaha", "aof_advanced")

    plo._persist_position_override(3, (400, 250))

    assert _reload(aof).location[3] == (30, 60), "the untouched game keeps its XML position"


def test_the_common_window_round_trips_too(store) -> None:
    aux = _make_aux("aof_omaha", "aof_advanced")

    aux._persist_position_override("common", (55, 66))

    assert _reload(aux).common == (55, 66)


def test_a_drag_is_stored_in_layout_space_not_this_tables_pixels(store) -> None:
    """A table opened at another size must not inherit a scaled-up position.

    ``configure_event_cb`` hands over table-relative pixels; the store keeps
    the layout's own reference space, so a half-size table saving (200, 150)
    is read back as (400, 300) by a full-size one.
    """
    small = _make_aux("aof_omaha", "aof_advanced", table_size=(460, 326))
    full = _make_aux("aof_omaha", "aof_advanced", table_size=(920, 652))

    small._persist_position_override(2, (200, 150))

    assert _reload(full).location[2] == (400, 300)


def test_positions_reach_a_brand_new_store_instance(store, monkeypatch) -> None:
    """The override has to be on disk, not just in the live store's dict."""
    aux = _make_aux("aof_omaha", "aof_advanced")
    aux._persist_position_override(3, (400, 250))

    reopened = Aux_Hud.HUDLayoutPositionsStore.__new__(Aux_Hud.HUDLayoutPositionsStore)
    reopened.path = store.path
    reopened.data = {"version": 2, "positions": {}}
    reopened.load()
    monkeypatch.setattr(Aux_Hud, "get_positions_store", lambda: reopened)

    assert _reload(aux).location[3] == (400, 250)
