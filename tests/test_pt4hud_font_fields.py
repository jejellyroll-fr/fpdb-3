"""A PT4 record's font face is not a record of its own (#783).

Each visual record of a ``.pt4hud`` export holds its font in a nested record,
e.g. ``< i 10, i 74, s 'Tahoma', ... >``. When that nested record's first
integer is 1, 2 or 4, it parsed as a stat, a container or a text record:
popups then showed "Tahoma" cells, and a font "container" cut a popup in two.
The stream below is built token by token in the export's typed format.
"""

from __future__ import annotations

import struct

from fpdb_3_legacy import pt4hud


def _s(text: str) -> bytes:
    return b"s" + struct.pack(">I", len(text)) + text.encode("utf-16-be")


def _i(value: int) -> bytes:
    return b"i\x02" + value.to_bytes(2, "big")


def _l(argb: int) -> bytes:
    return b"l" + struct.pack(">I", argb)


def _record(text: str, kind: int, font_kind: int, fg: int = 0xFFC0C0C0, bg: int = 0xFF000000) -> bytes:
    """A visual record whose nested font record starts with ``font_kind``."""
    font = b"<" + _i(font_kind) + _s("Tahoma") + _i(90) + b">"
    return b"<" + _s(text) + _i(kind) + _l(fg) + _l(bg) + _s("") + font + b">"


STREAM = b"".join(
    (
        _record("Range popup", 2, font_kind=2),
        _record("A", 4, font_kind=4),
        _record("New Line", 2, font_kind=1),
        _record("B", 4, font_kind=1),
        # Before #783 this font "container" ended the group and opened a
        # "Tahoma" one holding C.
        _record("C", 4, font_kind=2),
        _record("Other popup", 2, font_kind=4),
        _record("D", 4, font_kind=10),
    )
)


def test_a_font_record_is_not_taken_for_a_visual_record() -> None:
    texts = [record["text"] for record in pt4hud._visual_records(STREAM)]
    assert "Tahoma" not in texts
    assert texts == ["Range popup", "A", "New Line", "B", "C", "Other popup", "D"]


def test_popup_groups_keep_their_cells_and_no_font_cell() -> None:
    groups = {group.name: group for group in pt4hud.extract_popup_groups(STREAM)}
    assert list(groups) == ["Range popup", "Other popup"]
    cells = [(cell.kind, cell.text, cell.row, cell.col) for cell in groups["Range popup"].cells]
    assert cells == [("text", "A", 0, 0), ("text", "B", 1, 0), ("text", "C", 1, 1)]
    assert [cell.text for cell in groups["Other popup"].cells] == ["D"]


def test_a_text_that_names_a_font_with_colours_stays() -> None:
    """Only the bare font field goes: a coloured record called "Arial" is a real label."""
    stream = _record("Fonts", 2, font_kind=10) + _record("Arial", 4, font_kind=10)
    (group,) = pt4hud.extract_popup_groups(stream)
    assert [cell.text for cell in group.cells] == ["Arial"]
