"""Between a ``<ss>`` stat-set and the HUD editor's profile data.

The HUD Preferences editor works on plain dicts (a *profile*); the HUD reads
``<ss>`` nodes of ``HUD_config.xml``. This module is the one place that converts
between the two, without Qt, so that what the editor writes can be checked
against what the HUD reads (``tests/test_hud_editor_roundtrip.py``).

A profile is either *flat* -- ``{"rows", "cols", "stats": [...]}``, written as
``<stat>`` children of the ``<ss>`` -- or *multi-block* -- ``"multiblock": True``
and a ``"blocks"`` list, written as ``<block>`` children. A stat-set that was
written with ``<block>`` nodes stays multi-block even when it has a single
block, since only a block can carry a title, colours, text labels and lines.
"""

from __future__ import annotations

from typing import Any

# Optional presentation attributes of a <ss>: written back only when set.
PRESENTATION_ATTRS = ("rich_text", "font_size", "title_font_scale", "heading_font_scale")

# <block> attributes carried verbatim between the node and the editor.
BLOCK_TEXT_ATTRS = (
    "label",
    "id",
    "scope",
    "audience",
    "position",
    "bgcolor",
    "fgcolor",
    "title_bgcolor",
    "title_fgcolor",
    "bordercolor",
)
BLOCK_SCALE_ATTRS = ("title_font_scale", "heading_font_scale")

# Optional <stat> attributes kept in the editor's stat dict when present.
STAT_OPTIONAL_ATTRS = (
    "stat_loth",
    "stat_hith",
    "stat_locolor",
    "stat_hicolor",
    "stat_midcolor",
    "hudcolor",
    "hudbgcolor",
    "hudprefix",
    "hudsuffix",
    "display_label",
    "tip",
    # The declarative binding of an analytics-backed stat (#309). Empty for a
    # column-backed stat, written back only when it is set.
    "data_source",
    "data_definition",
    "data_format",
    "data_min_sample",
)
DATA_ATTRS = ("data_source", "data_definition", "data_format", "data_min_sample")


# --- Reading -----------------------------------------------------------------
def stat_to_dict(stat: Any, row: int, col: int, panel: str = "") -> dict[str, Any]:
    """Convert a ``Configuration.Stat`` into the editor's flat stat dict."""
    d: dict[str, Any] = {
        "row": row,
        "col": col,
        "stat": getattr(stat, "stat_name", "unknown"),
        "click": getattr(stat, "click", ""),
        "popup": getattr(stat, "popup", ""),
    }
    if panel:
        d["panel"] = panel
    for attr in STAT_OPTIONAL_ATTRS:
        if hasattr(stat, attr):
            d[attr] = getattr(stat, attr, "")
    # PT4 cell layout, kept only when non-default to avoid noisy XML.
    if getattr(stat, "colspan", 1) and int(getattr(stat, "colspan", 1)) != 1:
        d["colspan"] = int(stat.colspan)
    if getattr(stat, "align", "") and stat.align != "center":
        d["align"] = stat.align
    return d


def block_to_dict(block: Any) -> dict[str, Any]:
    """Convert a ``Configuration.StatBlock`` into the editor's block dict."""
    d: dict[str, Any] = {attr: getattr(block, attr, "") for attr in BLOCK_TEXT_ATTRS}
    d["scope"] = d["scope"] or "player"
    d["audience"] = d["audience"] or "everyone"
    d.update(
        {
            "rows": block.rows,
            "cols": block.cols,
            "cell_width": getattr(block, "cell_width", 0),
            "x": getattr(block, "x", 0),
            "y": getattr(block, "y", 0),
            "stats": [stat_to_dict(stat, pos[0], pos[1], block.label) for pos, stat in block.stats.items()],
            # PT4-style text-label items (column/row headers, captions).
            "texts": [dict(t) for t in getattr(block, "texts", [])],
            # PT4 "Horz Line" separators.
            "hlines": [dict(h) for h in getattr(block, "hlines", [])],
        }
    )
    for attr in BLOCK_SCALE_ATTRS:
        d[attr] = getattr(block, attr, 0) or 0
    return d


def _presentation(stat_set: Any) -> dict[str, Any]:
    return {attr: getattr(stat_set, attr, "") or "" for attr in PRESENTATION_ATTRS}


def is_block_layout(stat_set: Any) -> bool:
    """Whether the stat-set was written with ``<block>`` nodes."""
    blocks = getattr(stat_set, "blocks", None) or []
    return bool(getattr(stat_set, "has_block_nodes", False)) or len(blocks) > 1


def profile_from_stat_set(stat_set: Any) -> Any:
    """Convert a ``Configuration.Stat_sets`` into the editor's profile."""
    common = {
        "xpad": getattr(stat_set, "xpad", 0),
        "ypad": getattr(stat_set, "ypad", 0),
        **_presentation(stat_set),
    }
    if is_block_layout(stat_set):
        blocks = [block_to_dict(blk) for blk in stat_set.blocks]
        # The stacked stat list is kept for readers that predate blocks; the
        # blocks are the truth, and ``profile_stats`` reads them.
        stats: list[dict[str, Any]] = []
        row_offset = 0
        for blk, data in zip(stat_set.blocks, blocks, strict=True):
            stats.extend(dict(s, row=s["row"] + row_offset) for s in data["stats"])
            row_offset += blk.rows
        return {
            # The <ss> size as written; the panels carry their own.
            "rows": stat_set.rows,
            "cols": stat_set.cols,
            **common,
            "multiblock": True,
            # "all" = show every position panel stacked; "current" = only the
            # panel matching the estimated live position.
            "positional_mode": getattr(stat_set, "positional_mode", "current") or "current",
            # "" (default), "true" or "false": whether the hero's own stat
            # windows are drawn. Multi-block HUDs default to hidden.
            "show_hero_hud": getattr(stat_set, "show_hero_hud", "") or "",
            "blocks": blocks,
            "stats": stats,
        }

    stats = [stat_to_dict(stat, pos[0], pos[1], "") for pos, stat in getattr(stat_set, "stats", {}).items()]
    if hasattr(stat_set, "rows") and hasattr(stat_set, "cols"):
        return {
            "rows": stat_set.rows,
            "cols": stat_set.cols,
            **common,
            "show_hero_hud": getattr(stat_set, "show_hero_hud", "") or "",
            "stats": stats,
        }
    return stats


def profile_stats(profile: Any) -> list[dict[str, Any]]:
    """Every stat of a profile, read from its blocks when it has any."""
    if isinstance(profile, list):
        return profile
    blocks = profile.get("blocks") if isinstance(profile, dict) else None
    if blocks:
        return [stat for block in blocks for stat in block.get("stats", [])]
    return list(profile.get("stats", [])) if isinstance(profile, dict) else []


def new_block(label: str = "", rows: int = 1, cols: int = 1, stats: list | None = None) -> dict[str, Any]:
    """An empty editor block with every attribute the writer expects."""
    return {
        "label": label,
        "id": "",
        "scope": "player",
        "audience": "everyone",
        "position": "",
        "rows": max(1, int(rows)),
        "cols": max(1, int(cols)),
        "bgcolor": "",
        "fgcolor": "",
        "title_bgcolor": "",
        "title_fgcolor": "",
        "bordercolor": "",
        "title_font_scale": 0,
        "heading_font_scale": 0,
        "cell_width": 0,
        "x": 0,
        "y": 0,
        "stats": stats if stats is not None else [],
        "texts": [],
        "hlines": [],
    }


def ensure_blocks(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Turn a flat profile into a one-block profile, in place, and return its blocks.

    Text labels and lines only exist inside a ``<block>``; a flat ``<ss>`` has
    nowhere to keep them. The stat dicts are moved, not copied, so references the
    editor holds to them stay valid.
    """
    blocks = profile.get("blocks")
    if blocks:
        return blocks
    block = new_block(rows=int(profile.get("rows", 1) or 1), cols=int(profile.get("cols", 1) or 1))
    block["stats"] = profile.get("stats", [])
    profile["blocks"] = [block]
    profile["multiblock"] = True
    profile.setdefault("positional_mode", "current")
    return profile["blocks"]


# --- Writing -----------------------------------------------------------------
def append_stat_node(doc: Any, parent: Any, stat: dict[str, Any], row: int, col: int) -> None:
    node = doc.createElement("stat")
    node.setAttribute("_rowcol", f"({row + 1},{col + 1})")
    node.setAttribute("_stat_name", stat.get("stat", ""))
    node.setAttribute("click", stat.get("click", ""))
    node.setAttribute("popup", stat.get("popup", "default"))
    node.setAttribute("tip", stat.get("tip", ""))
    if stat.get("display_label"):
        node.setAttribute("display_label", stat["display_label"])
    for attr in (
        "hudprefix",
        "hudsuffix",
        "hudcolor",
        "hudbgcolor",
        "stat_loth",
        "stat_hith",
        "stat_locolor",
        "stat_hicolor",
        "stat_midcolor",
    ):
        node.setAttribute(attr, stat.get(attr, ""))
    # PT4 cell layout, written only when non-default to keep the XML clean.
    if int(stat.get("colspan", 1) or 1) > 1:
        node.setAttribute("colspan", str(int(stat["colspan"])))
    if stat.get("align") and stat["align"] != "center":
        node.setAttribute("align", stat["align"])
    # An analytics-backed stat (#309) says where its number comes from.
    for attr in DATA_ATTRS:
        if stat.get(attr):
            node.setAttribute(attr, str(stat[attr]))
    parent.appendChild(node)


def append_hline_node(doc: Any, parent: Any, hline: dict[str, Any]) -> None:
    """Write a PT4-style ``<hline>`` separator item within a block."""
    rc = hline.get("rowcol", (0, 0))
    node = doc.createElement("hline")
    node.setAttribute("_rowcol", f"({int(rc[0]) + 1},{int(rc[1]) + 1})")
    if hline.get("colspan"):
        node.setAttribute("colspan", str(int(hline["colspan"])))
    if hline.get("color"):
        node.setAttribute("color", hline["color"])
    parent.appendChild(node)


def append_text_node(doc: Any, parent: Any, text: dict[str, Any]) -> None:
    """Write a PT4-style ``<text>`` label item within a block."""
    rc = text.get("rowcol", (0, 0))
    node = doc.createElement("text")
    node.setAttribute("_rowcol", f"({int(rc[0]) + 1},{int(rc[1]) + 1})")
    node.setAttribute("label", text.get("label", ""))
    if int(text.get("colspan", 1)) > 1:
        node.setAttribute("colspan", str(int(text.get("colspan", 1))))
    if text.get("align"):
        node.setAttribute("align", text["align"])
    if text.get("fgcolor"):
        node.setAttribute("fgcolor", text["fgcolor"])
    if text.get("bgcolor"):
        node.setAttribute("bgcolor", text["bgcolor"])
    parent.appendChild(node)


def _block_node(doc: Any, block: dict[str, Any], cols: int) -> Any:
    node = doc.createElement("block")
    for attr in BLOCK_TEXT_ATTRS:
        if block.get(attr) is not None:
            node.setAttribute(attr, str(block.get(attr, "")))
    node.setAttribute("rows", str(block.get("rows", 1)))
    node.setAttribute("cols", str(block.get("cols", cols)))
    node.setAttribute("x", str(block.get("x", 0)))
    node.setAttribute("y", str(block.get("y", 0)))
    if int(block.get("cell_width", 0) or 0) > 0:
        node.setAttribute("cell_width", str(int(block["cell_width"])))
    for attr in BLOCK_SCALE_ATTRS:
        if block.get(attr):
            node.setAttribute(attr, f"{float(block[attr]):g}")
    for text in block.get("texts", []):
        node.appendChild(doc.createTextNode("\n                "))
        append_text_node(doc, node, text)
    for hline in block.get("hlines", []):
        node.appendChild(doc.createTextNode("\n                "))
        append_hline_node(doc, node, hline)
    for stat in block.get("stats", []):
        node.appendChild(doc.createTextNode("\n                "))
        append_stat_node(doc, node, stat, int(stat.get("row", 0)), int(stat.get("col", 0)))
    if block.get("stats") or block.get("texts") or block.get("hlines"):
        node.appendChild(doc.createTextNode("\n            "))
    return node


def write_profile_items(doc: Any, stat_set_node: Any, profile: Any, rows: int, cols: int) -> None:
    """Replace the children of ``stat_set_node`` with the profile's items."""
    stat_set_node.setAttribute("rows", str(rows))
    stat_set_node.setAttribute("cols", str(cols))
    while stat_set_node.firstChild:
        stat_set_node.removeChild(stat_set_node.firstChild)

    blocks = profile.get("blocks") if isinstance(profile, dict) else None
    if blocks:
        for block in blocks:
            stat_set_node.appendChild(doc.createTextNode("\n            "))
            stat_set_node.appendChild(_block_node(doc, block, cols))
        stat_set_node.appendChild(doc.createTextNode("\n        "))
        return

    stats = profile if isinstance(profile, list) else profile.get("stats", [])
    for stat in stats:
        stat_set_node.appendChild(doc.createTextNode("\n            "))
        append_stat_node(doc, stat_set_node, stat, int(stat["row"]), int(stat["col"]))
    if stats:
        stat_set_node.appendChild(doc.createTextNode("\n        "))


def stat_set_size(profile: Any) -> tuple[int, int]:
    """The ``rows``/``cols`` to write on the ``<ss>``."""
    if isinstance(profile, list):
        return 5, 5
    return int(profile.get("rows", 5) or 1), int(profile.get("cols", 5) or 1)


def write_stat_set_attributes(stat_set_node: Any, profile: Any) -> None:
    """Write the profile's ``<ss>``-level settings onto the node."""
    if not isinstance(profile, dict):
        return
    if profile.get("multiblock"):
        stat_set_node.setAttribute("positional_mode", profile.get("positional_mode", "current") or "current")
    if profile.get("show_hero_hud"):
        stat_set_node.setAttribute("show_hero_hud", profile["show_hero_hud"])
    for attr in ("xpad", "ypad"):
        if attr in profile:
            stat_set_node.setAttribute(attr, str(int(profile.get(attr) or 0)))
    for attr in PRESENTATION_ATTRS:
        value = profile.get(attr)
        if value not in (None, "", 0):
            stat_set_node.setAttribute(attr, str(value))
        elif attr in profile and stat_set_node.hasAttribute(attr):
            stat_set_node.removeAttribute(attr)


def write_profile(doc: Any, stat_set_node: Any, profile: Any) -> None:
    """Write a whole profile into its ``<ss>`` node."""
    write_stat_set_attributes(stat_set_node, profile)
    rows, cols = stat_set_size(profile)
    write_profile_items(doc, stat_set_node, profile, rows, cols)
