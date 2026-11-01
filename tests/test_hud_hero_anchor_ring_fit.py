"""The hero anchor is the slot of the bottom-centre chair, found by ring fit.

A layout's slots are a rotation of the ring of chairs, so the anchor is decided
by fitting whole rings rather than by reading one block's coordinates. The
regression this covers: a player who drags the bottom-centre block aside to
clear the hero's own cards and buttons leaves it higher than the bottom-left
one, and the old "lowest slot, nearest the middle" rule then answered
bottom-left -- putting every stat block on the table one chair off, which is
what Fast-Fold tables showed on Windows (issue: HUD positions rotated by one).
"""

from __future__ import annotations

from types import SimpleNamespace

from fpdb_3_legacy.Aux_Base import AuxSeats

# Shipped winamax_default, max=6: the slots sit between the chairs (there is no
# bottom-centre slot at all), so two rotations fit equally well and the tie must
# keep answering what it always has.
WINAMAX_DEFAULT_6MAX = [
    None,
    (663, 48),
    (664, 293),
    (563, 402),
    (120, 401),
    (32, 291),
    (12, 46),
]

# The same layout after a player arranged it over a real 6-max table: slot 1 is
# the top-centre chair and the ring runs clockwise, so slot 4 is the hero's.
# Slot 4 is 48px higher than slot 5 because the hero's cards and action buttons
# occupy the bottom centre of the felt.
ARRANGED_6MAX = [
    None,
    (561, 167),  # top-centre
    (997, 229),  # top-right
    (1035, 577),  # bottom-right
    (328, 533),  # bottom-centre  <- hero
    (67, 581),  # bottom-left
    (51, 232),  # top-left
]


def _make_aux(max_seats: int, locations: list, width: int, fav: int = 0) -> AuxSeats:
    aux = object.__new__(AuxSeats)
    layout = SimpleNamespace(
        max=max_seats,
        hh_seats=list(range(max_seats + 1)),
        location=list(locations),
        width=width,
        height=792,
        common=(0, 0),
    )
    aux.hud = SimpleNamespace(
        max=max_seats,
        layout=layout,
        stat_dict={},
        site="TestSite",
        site_parameters={"fav_seat": {max_seats: fav}},
    )
    aux.config = SimpleNamespace(is_hero_name=lambda site, name: name == "hero")
    return aux


def test_arranged_layout_anchors_hero_at_the_bottom_centre_slot() -> None:
    aux = _make_aux(6, ARRANGED_6MAX, 1273)
    assert aux._bottom_center_slot() == 4
    assert aux._anchor_slot() == 4


def test_shipped_winamax_layout_keeps_its_established_anchor() -> None:
    # Both rotations fit this ring to within 0.1%; the tie goes to the slot
    # closest to straight down, which is the seat 3 every release has used.
    aux = _make_aux(6, WINAMAX_DEFAULT_6MAX, 792)
    assert aux._bottom_center_slot() == 3


def test_explicit_fav_seat_still_wins() -> None:
    aux = _make_aux(6, ARRANGED_6MAX, 1273, fav=2)
    assert aux._anchor_slot() == 2


def test_slot_bearings_run_clockwise_from_the_bottom() -> None:
    aux = _make_aux(6, ARRANGED_6MAX, 1273)
    order = [slot for _bearing, slot in aux._slot_bearings()]
    # Clockwise from the bottom chair: bottom-centre, bottom-left, top-left,
    # top-centre, top-right, bottom-right.
    assert order == [4, 5, 6, 1, 2, 3]


def test_a_layout_with_no_locations_does_not_raise() -> None:
    aux = _make_aux(6, [None] * 7, 792)
    assert aux._bottom_center_slot() == 6
