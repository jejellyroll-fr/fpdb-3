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
