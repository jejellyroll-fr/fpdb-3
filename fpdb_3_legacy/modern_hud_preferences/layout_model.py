"""Where the items of one HUD panel sit, without Qt.

A *container* is the dict that holds a panel's items: a block of a multi-block
profile, or a flat profile itself. It carries ``rows``/``cols`` and three item
lists:

* ``stats``  -- dicts with ``row``, ``col`` and an optional ``colspan``;
* ``texts``  -- dicts with ``rowcol`` and ``colspan``;
* ``hlines`` -- dicts with ``rowcol`` and ``colspan``, where 0 spans the row.

An item is named by ``(kind, ref)``, with ``kind`` one of :data:`KINDS` and
``ref`` the dict itself: identity, not equality, says which item is meant, so
two identical stats stay two items.

The HUD keeps one item per cell (``Configuration.StatBlock`` indexes stats by
position), so every operation here refuses a cell another item covers.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

KINDS = {"stat": "stats", "text": "texts", "hline": "hlines"}

Cell = tuple[int, int]
Item = tuple[str, dict[str, Any]]


def _cols(container: dict[str, Any]) -> int:
    return max(1, int(container.get("cols", 1) or 1))


def _rows(container: dict[str, Any]) -> int:
    return max(1, int(container.get("rows", 1) or 1))


def position(kind: str, ref: dict[str, Any]) -> Cell:
    """The item's top-left cell."""
    if kind == "stat":
        return int(ref.get("row", 0) or 0), int(ref.get("col", 0) or 0)
    row, col = ref.get("rowcol", (0, 0))
    return int(row), int(col)


def span(kind: str, ref: dict[str, Any], cols: int) -> int:
    """How many columns the item covers in a panel ``cols`` wide."""
    width = int(ref.get("colspan", 0 if kind == "hline" else 1) or 0)
    if kind == "hline" and width <= 0:
        return max(1, cols)
    return max(1, width)


def _set_position(kind: str, ref: dict[str, Any], row: int, col: int) -> None:
    if kind == "stat":
        ref["row"], ref["col"] = row, col
    else:
        ref["rowcol"] = (row, col)


def items(container: dict[str, Any]) -> Iterator[Item]:
    """Every item of the panel, stats first."""
    for kind, key in KINDS.items():
        for ref in container.get(key, []):
            yield kind, ref


def cells_of(kind: str, ref: dict[str, Any], cols: int) -> list[Cell]:
    row, col = position(kind, ref)
    return [(row, col + offset) for offset in range(span(kind, ref, cols))]


def occupancy(container: dict[str, Any], ignore: dict[str, Any] | None = None) -> dict[Cell, Item]:
    """Cell -> the item covering it. ``ignore`` leaves one item out."""
    cols = _cols(container)
    taken: dict[Cell, Item] = {}
    for kind, ref in items(container):
        if ref is ignore:
            continue
        for cell in cells_of(kind, ref, cols):
            taken.setdefault(cell, (kind, ref))
    return taken


def collisions(container: dict[str, Any]) -> list[tuple[Cell, Item, Item]]:
    """Cells two items claim at once: ``(cell, first, second)``."""
    cols = _cols(container)
    seen: dict[Cell, Item] = {}
    clashes: list[tuple[Cell, Item, Item]] = []
    for kind, ref in items(container):
        for cell in cells_of(kind, ref, cols):
            if cell in seen:
                clashes.append((cell, seen[cell], (kind, ref)))
            else:
                seen[cell] = (kind, ref)
    return clashes


def occupant(container: dict[str, Any], row: int, col: int, ignore: dict[str, Any] | None = None) -> Item | None:
    """The item covering ``(row, col)``, if any."""
    return occupancy(container, ignore).get((row, col))


def can_place(
    container: dict[str, Any], row: int, col: int, width: int = 1, ignore: dict[str, Any] | None = None
) -> bool:
    """Whether an item ``width`` wide fits at ``(row, col)`` on free cells."""
    if row < 0 or col < 0 or width < 1:
        return False
    taken = occupancy(container, ignore)
    return all((row, col + offset) not in taken for offset in range(width))


def first_free_cell(container: dict[str, Any], width: int = 1) -> Cell:
    """The first cell, row by row, where an item ``width`` wide fits.

    Searches the panel's rows and then the row below them, so a full panel
    answers with a new row rather than a cell past its right edge.
    """
    cols = _cols(container)
    width = min(max(1, width), cols)
    taken = occupancy(container)
    last_row = max([_rows(container)] + [row + 1 for row, _col in taken])
    for row in range(last_row + 1):
        for col in range(cols - width + 1):
            if all((row, col + offset) not in taken for offset in range(width)):
                return row, col
    return last_row, 0


def first_free_row(container: dict[str, Any]) -> int:
    """The first row no item touches (a full-width line needs one)."""
    taken_rows = {row for row, _col in occupancy(container)}
    row = 0
    while row in taken_rows:
        row += 1
    return row


def grow_to_fit(container: dict[str, Any], kind: str, ref: dict[str, Any]) -> None:
    """Enlarge the panel so the item lies inside it."""
    row, col = position(kind, ref)
    cols = _cols(container)
    container["rows"] = max(_rows(container), row + 1)
    if kind != "hline":
        container["cols"] = max(cols, col + span(kind, ref, cols))


def add(container: dict[str, Any], kind: str, ref: dict[str, Any], row: int, col: int) -> bool:
    """Put a new item at ``(row, col)``; refused when a cell is taken."""
    width = span(kind, ref, _cols(container))
    if not can_place(container, row, col, width):
        return False
    _set_position(kind, ref, row, col)
    container.setdefault(KINDS[kind], []).append(ref)
    grow_to_fit(container, kind, ref)
    return True


def remove(container: dict[str, Any], ref: dict[str, Any]) -> bool:
    """Take an item out of the panel; False when it is not there."""
    for key in KINDS.values():
        lst = container.get(key, [])
        for index, candidate in enumerate(lst):
            if candidate is ref:
                del lst[index]
                return True
    return False


def find(container: dict[str, Any], ref: dict[str, Any]) -> Item | None:
    """``(kind, ref)`` when ``ref`` belongs to the panel."""
    return next(((kind, item) for kind, item in items(container) if item is ref), None)


def _fits(container: dict[str, Any], mover: Item) -> bool:
    """Whether ``mover`` overlaps no other item of the panel."""
    cols = _cols(container)
    mine = set(cells_of(*mover, cols))
    return not any(mine & set(cells_of(kind, ref, cols)) for kind, ref in items(container) if ref is not mover[1])


def move(container: dict[str, Any], ref: dict[str, Any], row: int, col: int) -> str:
    """Move an item to ``(row, col)``.

    Returns ``"moved"`` onto free cells, ``"swapped"`` when the target holds one
    item that fits where the moved one was, or ``"refused"`` (nothing changes).
    """
    found = find(container, ref)
    if found is None or row < 0 or col < 0:
        return "refused"
    kind = found[0]
    cols = _cols(container)
    width = span(kind, ref, cols)
    if can_place(container, row, col, width, ignore=ref):
        _set_position(kind, ref, row, col)
        grow_to_fit(container, kind, ref)
        return "moved"

    taken = occupancy(container, ignore=ref)
    others = {id(taken[cell][1]): taken[cell] for offset in range(width) if (cell := (row, col + offset)) in taken}
    if len(others) != 1:
        return "refused"
    other_kind, other = next(iter(others.values()))
    origin, other_origin = position(kind, ref), position(other_kind, other)
    # Try the swap on the positions alone, then keep it only if neither item
    # now lies on a cell held by a third one.
    _set_position(kind, ref, row, col)
    _set_position(other_kind, other, *origin)
    if not (_fits(container, (kind, ref)) and _fits(container, (other_kind, other))):
        _set_position(other_kind, other, *other_origin)
        _set_position(kind, ref, *origin)
        return "refused"
    grow_to_fit(container, kind, ref)
    grow_to_fit(container, other_kind, other)
    return "swapped"


def preview_move(container: dict[str, Any], ref: dict[str, Any], row: int, col: int) -> str:
    """What :func:`move` would answer, leaving the panel exactly as it is.

    The canvas asks while an item is dragged over a cell, to show the drop as
    accepted or refused before it happens.
    """
    saved = [(kind, item, position(kind, item)) for kind, item in items(container)]
    size = {key: container[key] for key in ("rows", "cols") if key in container}
    try:
        return move(container, ref, row, col)
    finally:
        for kind, item, (r, c) in saved:
            _set_position(kind, item, r, c)
        for key in ("rows", "cols"):
            if key in size:
                container[key] = size[key]
            else:
                container.pop(key, None)


def _spans_the_row(kind: str, ref: dict[str, Any]) -> bool:
    """A line without a span: it stretches with the panel, whatever its width."""
    return kind == "hline" and int(ref.get("colspan", 0) or 0) <= 0


def row_is_empty(container: dict[str, Any], row: int) -> bool:
    return not any(r == row for r, _c in occupancy(container))


def col_is_empty(container: dict[str, Any], col: int) -> bool:
    """No item covers the column; a line spanning the whole row does not count."""
    cols = _cols(container)
    for kind, ref in items(container):
        if _spans_the_row(kind, ref):
            continue
        if any(c == col for _r, c in cells_of(kind, ref, cols)):
            return False
    return True


def insert_row(container: dict[str, Any], at: int) -> bool:
    """Open an empty row at ``at``; the items from that row down move one row down."""
    rows = _rows(container)
    at = min(max(at, 0), rows)
    for kind, ref in items(container):
        row, col = position(kind, ref)
        if row >= at:
            _set_position(kind, ref, row + 1, col)
    container["rows"] = rows + 1
    return True


def insert_col(container: dict[str, Any], at: int) -> bool:
    """Open an empty column at ``at``; the items from that column on move right."""
    cols = _cols(container)
    at = min(max(at, 0), cols)
    for kind, ref in items(container):
        if _spans_the_row(kind, ref):
            continue
        row, col = position(kind, ref)
        if col >= at:
            _set_position(kind, ref, row, col + 1)
    container["cols"] = cols + 1
    return True


def delete_row(container: dict[str, Any], at: int) -> bool:
    """Close an empty row; refused for a row an item covers, or the last row left."""
    rows = _rows(container)
    if rows <= 1 or not 0 <= at < rows or not row_is_empty(container, at):
        return False
    for kind, ref in items(container):
        row, col = position(kind, ref)
        if row > at:
            _set_position(kind, ref, row - 1, col)
    container["rows"] = rows - 1
    return True


def delete_col(container: dict[str, Any], at: int) -> bool:
    """Close an empty column; refused for a column an item covers, or the last one left."""
    cols = _cols(container)
    if cols <= 1 or not 0 <= at < cols or not col_is_empty(container, at):
        return False
    for kind, ref in items(container):
        if _spans_the_row(kind, ref):
            continue
        row, col = position(kind, ref)
        if col > at:
            _set_position(kind, ref, row, col - 1)
    container["cols"] = cols - 1
    return True


def fits_inside(container: dict[str, Any], kind: str, ref: dict[str, Any], col: int) -> bool:
    """Whether the item, its left edge on ``col``, stays inside the panel's columns."""
    cols = _cols(container)
    return col >= 0 and col + span(kind, ref, cols) <= cols
