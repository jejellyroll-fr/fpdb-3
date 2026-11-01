"""Seat -> HUD-position mapping (Aux_Base.AuxSeats.adj_seats).

The iPoker client numbers a 6-max table's seats on a 10-slot grid
(1,3,5,6,8,10), and the shipped config only carries a hist_seat table for
max=6 and max=9. Combined with fav_seat defaulting to 0 (no rotation), the hero
landed at the bottom of the table only by coincidence, and sparse table sizes
with no hist_seat table errored out ("Error finding hero seat") and dropped the
HUD onto the wrong seats.

The reworked adj_seats always anchors the hero to the bottom-centre slot
(computed from layout geometry) and rebuilds the visual-slot -> physical-seat
ring from the occupied seats when the config ring does not cover them.
"""

from __future__ import annotations

from types import SimpleNamespace

from fpdb_3_legacy.Aux_Base import AuxSeats

# iPoker 6-max reference layout (from HUD_config.xml ipoker_default, max=6).
IPOKER_6MAX_LOC = [
    None,
    (473, 128),  # slot 1  top-centre
    (749, 195),  # slot 2  right-top
    (737, 472),  # slot 3  right-bottom
    (420, 500),  # slot 4  bottom-centre  <- anchor
    (65, 469),   # slot 5  left-bottom
    (38, 197),   # slot 6  left-top
]
IPOKER_6MAX_RING = [None, 1, 3, 5, 6, 8, 10]  # hist_seat mapping

# A generic 3-max oval with the bottom-centre at slot 3.
THREE_MAX_LOC = [None, (573, 41), (112, 41), (320, 450)]


def _make_aux(max_seats, hh_seats, locations, width, stat_dict, hero, fav=0):
    aux = object.__new__(AuxSeats)
    layout = SimpleNamespace(
        max=max_seats,
        hh_seats=list(hh_seats),
        location=list(locations),
        width=width,
        common=(0, 0),
    )
    hud = SimpleNamespace(
        max=max_seats,
        layout=layout,
        stat_dict=stat_dict,
        site="TestSite",
        site_parameters={"fav_seat": {max_seats: fav}},
    )
    aux.hud = hud
    aux.config = SimpleNamespace(is_hero_name=lambda site, name: name == hero)
    return aux


def _stat_dict(seats: dict[int, str]) -> dict[int, dict]:
    """seats: {physical_seat: screen_name} -> stat_dict keyed by player id."""
    return {pid: {"screen_name": name, "seat": seat} for pid, (seat, name) in enumerate(seats.items(), 1)}


def _is_permutation(adj: list[int], max_seats: int) -> bool:
    return sorted(adj[1:]) == list(range(1, max_seats + 1))


def test_bottom_center_slot_from_geometry() -> None:
    aux = _make_aux(6, IPOKER_6MAX_RING, IPOKER_6MAX_LOC, 920, {}, "hero")
    assert aux._bottom_center_slot() == 4  # (420,500): max y, near centre 460


def test_ipoker_6max_hero_anchored_to_bottom_regardless_of_seat() -> None:
    # Hero at physical seat 10 (slot 6, left-top) must still land at the bottom.
    stat = _stat_dict({1: "villainA", 3: "villainB", 6: "villainC", 10: "hero"})
    aux = _make_aux(6, IPOKER_6MAX_RING, IPOKER_6MAX_LOC, 920, stat, "hero")

    adj = aux.adj_seats()

    # Hero occupies visual slot 6 (hh_seats[6] == 10); its position must be slot 4.
    assert adj[6] == 4
    assert _is_permutation(adj, 6)


def test_standard_6max_hero_rotated_to_bottom_with_fav_seat_zero() -> None:
    # Identity ring, fav_seat=0: legacy code did NOT rotate; now the hero must.
    stat = _stat_dict({2: "hero", 4: "villainA", 5: "villainB"})
    aux = _make_aux(6, [None, 1, 2, 3, 4, 5, 6], IPOKER_6MAX_LOC, 920, stat, "hero", fav=0)

    adj = aux.adj_seats()

    assert adj[2] == 4  # hero at physical/visual slot 2 -> bottom-centre slot 4
    assert _is_permutation(adj, 6)


def test_explicit_fav_seat_overrides_bottom_center() -> None:
    stat = _stat_dict({3: "hero", 1: "villainA"})
    aux = _make_aux(6, [None, 1, 2, 3, 4, 5, 6], IPOKER_6MAX_LOC, 920, stat, "hero", fav=2)

    adj = aux.adj_seats()

    assert adj[3] == 2  # honoured user override, not the geometric bottom slot
    assert _is_permutation(adj, 6)


def test_sparse_size_without_hist_seat_is_synthesised() -> None:
    # 3-max Twister: config ring is identity (1,2,3) but the client seats
    # players at {1, 3, 6}. Legacy code errored; now a ring is synthesised.
    stat = _stat_dict({1: "villainA", 3: "hero", 6: "villainB"})
    aux = _make_aux(3, [None, 1, 2, 3], THREE_MAX_LOC, 792, stat, "hero")

    adj = aux.adj_seats()

    # Ring synthesised to [None, 1, 3, 6]; hero (seat 3) is visual slot 2.
    assert aux.hud.layout.hh_seats == [None, 1, 3, 6]
    assert adj[2] == 3  # hero -> bottom-centre slot 3
    assert _is_permutation(adj, 3)


def test_config_ring_used_when_it_covers_occupied_seats() -> None:
    # Not every seat occupied, but all occupied seats are within the ring.
    stat = _stat_dict({1: "hero", 6: "villainA", 10: "villainB"})
    aux = _make_aux(6, IPOKER_6MAX_RING, IPOKER_6MAX_LOC, 920, stat, "hero")

    adj = aux.adj_seats()

    # Config ring is authoritative (not synthesised) because it covers 1,6,10.
    assert aux.hud.layout.hh_seats == IPOKER_6MAX_RING
    assert adj[1] == 4  # hero at physical seat 1 -> visual slot 1 -> bottom
    assert _is_permutation(adj, 6)


def test_hero_not_seated_returns_identity_without_error() -> None:
    stat = _stat_dict({1: "villainA", 3: "villainB"})
    aux = _make_aux(6, IPOKER_6MAX_RING, IPOKER_6MAX_LOC, 920, stat, "hero")

    adj = aux.adj_seats()

    assert adj == list(range(7))  # identity fallback, no exception


def test_a_hud_with_no_players_yet_keeps_the_configured_ring() -> None:
    """Synthesising from an empty table gives a ring of Nones.

    That ring is stored on the layout, so every later seat lookup maps to None
    and every stat block hides itself -- for as long as the table lives. A HUD
    created before its first hand (from the client log) starts exactly here.
    """
    ring = [None, 1, 2, 3, 4, 5, 6]
    aux = _make_aux(6, ring, [None] + [(i * 10, i * 10) for i in range(6)], 700, {}, "Hero")

    assert aux._effective_hh_seats() == ring


def test_seats_stay_usable_after_a_hud_is_created_empty() -> None:
    """adj_seats stores the ring it computed, so an empty one is not recoverable."""
    ring = [None, 1, 2, 3, 4, 5, 6]
    aux = _make_aux(6, ring, [None] + [(i * 10, i * 10) for i in range(6)], 700, {}, "Hero")

    adj = aux.adj_seats()

    assert aux.hud.layout.hh_seats == ring
    assert _is_permutation(adj, 6)


def test_mucked_windows_are_not_built_for_fast_fold_tables() -> None:
    """They replay a showdown of a table the hero left before it finished."""
    from types import SimpleNamespace as NS

    from fpdb_3_legacy.Hud import Hud

    hud = object.__new__(Hud)
    hud.aux_windows = []
    hud.supported_games_parameters = {"aux": "ClassicHud, mucked"}

    built = []

    class _Config:
        @staticmethod
        def get_aux_parameters(name):
            return {
                "ClassicHud": {"module": "Aux_Classic_Hud", "class": "ClassicHud"},
                "mucked": {"module": "Mucked", "class": "Flop_Mucked"},
            }[name]

    def _fake_import(module, cls):
        def _make(*_a, **_k):
            built.append(cls)
            return NS(cls=cls)

        return _make

    import fpdb_3_legacy.Hud as hud_module

    original = hud_module.importName
    hud_module.importName = _fake_import
    try:
        hud.hud_context = NS(speed="fast")
        hud._build_aux_windows(_Config())
        assert built == ["ClassicHud"]

        built.clear()
        hud.aux_windows = []
        hud.hud_context = NS(speed="normal")
        hud._build_aux_windows(_Config())
        assert built == ["ClassicHud", "Flop_Mucked"]
    finally:
        hud_module.importName = original
