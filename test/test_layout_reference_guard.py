"""A layout's reference size must be able to contain the positions it frames.

Aux_Base.create_scale_position() scales every block by table/reference, so a
reference far smaller than its own positions multiplies them instead of mapping
them: a live config carried ``<layout max="8" height="103" width="336">`` with a
seat at (1225, 737), which placed that block at (7483, 4796) for a 955x650 SwC
table -- off every screen, so the HUD looked absent. Both ends are covered here:
the load never trusts such a pair again, and the save never writes one.
"""

from __future__ import annotations

from types import SimpleNamespace
from xml.dom import minidom

import pytest

from fpdb_3_legacy.Configuration import Config, Layout, layout_reference_fits


def _layout(xml: str) -> Layout:
    return Layout(minidom.parseString(xml).documentElement)


class _RecordingConfig:
    """Just enough of Config for save_layout_set to run its guard and stop.

    Reaching get_layout_set_node means the guard let the save through, so the
    stub records that instead of building a DOM.
    """

    def __init__(self) -> None:
        self.reached_write = False

    def get_layout_set_node(self, name):  # noqa: ANN001, ANN201
        self.reached_write = True
        msg = "stop before touching the DOM"
        raise _Wrote(msg)


class _Wrote(Exception):
    pass


def _attempt_save(locations: dict, width, height) -> bool:  # noqa: ANN001
    """Whether save_layout_set got past its guard for this (locations, size)."""
    cfg = _RecordingConfig()
    ls = SimpleNamespace(name="sealswithclubs_default")
    try:
        Config.save_layout_set(cfg, ls, 8, locations, width, height)
    except _Wrote:
        pass
    return cfg.reached_write


def test_sane_layout_keeps_its_declared_reference() -> None:
    lo = _layout(
        """<layout max="2" height="546" width="792">
             <location seat="1" x="681" y="221"/>
             <location seat="2" x="2" y="221"/>
             <location common="1" x="323" y="232"/>
           </layout>""",
    )
    assert (lo.width, lo.height) == (792, 546)


def test_block_parked_just_off_the_table_edge_is_still_sane() -> None:
    """A modest overhang is a real user choice, not corruption."""
    lo = _layout(
        """<layout max="2" height="546" width="792">
             <location seat="1" x="850" y="221"/>
             <location seat="2" x="2" y="600"/>
           </layout>""",
    )
    assert (lo.width, lo.height) == (792, 546)


def test_corrupt_reference_grows_to_contain_its_positions() -> None:
    """The observed SwC 8-max layout: 336x103 framing a seat at (1225, 737)."""
    lo = _layout(
        """<layout max="8" height="103" width="336">
             <location seat="1" x="1225" y="737"/>
             <location seat="2" x="1055" y="318"/>
             <location seat="3" x="1156" y="445"/>
             <location seat="4" x="974" y="540"/>
             <location seat="5" x="731" y="525"/>
             <location seat="6" x="521" y="450"/>
             <location seat="7" x="616" y="303"/>
             <location seat="8" x="711" y="195"/>
             <location common="1" x="137" y="41"/>
           </layout>""",
    )
    assert (lo.width, lo.height) == (1225, 737)

    # With the repaired reference every block lands inside a 947x619 table
    # instead of thousands of pixels past its right edge.
    for x, y in (p for p in lo.location if p is not None):
        assert 0 <= int(x * 947 / lo.width) <= 947
        assert 0 <= int(y * 619 / lo.height) <= 619


def test_zero_reference_is_repaired_rather_than_dividing_by_zero() -> None:
    lo = _layout(
        """<layout max="2" height="0" width="0">
             <location seat="1" x="400" y="300"/>
             <location seat="2" x="100" y="200"/>
           </layout>""",
    )
    assert (lo.width, lo.height) == (400, 300)


@pytest.mark.parametrize(
    ("width", "height", "positions", "expected"),
    [
        (792, 546, [(681, 221), (2, 221)], True),
        (792, 546, [], True),
        (336, 103, [(1225, 737)], False),
        (0, 546, [(100, 100)], False),
        (792, None, [(100, 100)], False),
    ],
)
def test_layout_reference_fits(width, height, positions, expected) -> None:
    assert layout_reference_fits(width, height, positions) is expected


def test_save_refuses_a_reference_that_cannot_hold_the_positions() -> None:
    """The write end: this pair is exactly what corrupted the shipped layout."""
    assert _attempt_save({1: (1225, 737)}, 336, 103) is False


def test_save_accepts_a_normal_drag() -> None:
    assert _attempt_save({1: (681, 221), 2: (2, 221)}, 792, 546) is True


def test_save_without_a_reference_is_not_blocked() -> None:
    """Saving only the common position from the mucked display carries no size."""
    assert _attempt_save({"common": (323, 232)}, None, None) is True
