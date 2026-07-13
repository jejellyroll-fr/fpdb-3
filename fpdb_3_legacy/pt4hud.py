#!/usr/bin/env python3
"""Parser for PokerTracker 4 ``.pt4hud`` layout exports -> fpdb HUD stat-set.

A ``.pt4hud`` file is PT4's proprietary HUD-layout export: a flat, length-prefixed
**UTF-16BE** binary serialization (4-byte big-endian char count, then ``2*n``
bytes per string, with layout integers/colors interleaved between strings).

This module:

* extracts the ordered strings and recognises the displayed HUD stat cells,
  their short labels (e.g. ``" VP "``) and PT4 stat full names / tooltips
  (e.g. ``"VPIP"``, ``"CBet Flop in non-3Bet+ Pot"``), which the export stores
  as parallel runs grouped by section (``SB 3h`` / ``BB 3h`` / ``BU 3h`` ...);
* maps the **standard** PT4 stats to fpdb (legacy) ``Stats.py`` functions and
  emits an fpdb ``<ss>`` stat-set node ready to drop into ``HUD_config.xml``;
* extracts the **range-chart popups** (push/fold Nash grids) by decoding PT4's
  typed binary stream into 13x13 grids of ``(hand, fill colour)``, ready to be
  rendered by the HUD range-chart widget;
* reports user-defined **formula** stats it cannot map (those not covered by a
  native fpdb stat).

Usage::

    python -m fpdb_3_legacy.pt4hud path/to/layout.pt4hud           # summary
    python -m fpdb_3_legacy.pt4hud path/to/layout.pt4hud --xml     # <ss> config
    python -m fpdb_3_legacy.pt4hud path/to/layout.pt4hud --json    # stats+charts
"""

from __future__ import annotations

import argparse
import json
import os
import re
import struct
from dataclasses import dataclass, field
from xml.sax.saxutils import quoteattr

MAGIC = "PT4.Hud.Layout.Export"

# PT4 stat full name (as stored in the export) -> fpdb Stats.py function name.
# Only standard stats fpdb can actually compute are listed; everything else is
# reported as unsupported by the parser.
PT4_TO_FPDB: dict[str, str] = {
    # preflop
    "VPIP": "vpip",
    "PFR": "pfr",
    "Total AFq": "agg_fact_pct",
    "Preflop Squeeze": "squeeze",
    "Cold Call 2Bet PF": "cold_call",
    "3Bet Preflop": "three_B",
    "4Bet Preflop": "four_B",
    "Preflop Limp": "limp",
    "Limp With Previous Limpers": "open_limp",
    "Fold to PF 3Bet After Raise": "f_3bet",
    "Fold to PF 3Bet": "f_3bet",
    "Fold to PF 4Bet After 3Bet": "fold_vs_4bet",
    "Raise With Previous Limpers": "iso",
    "Raise First In": "rfi_total",
    "Att To Steal": "steal",
    "Fold to Steal": "f_steal",
    "Call Steal": "call_vs_steal",
    "3Bet Steal": "three_bet_vs_steal",
    # continuation betting
    "CBet Flop in non-3Bet+ Pot": "cb1",
    "CBet Turn in non-3Bet+ Pot": "cb2",
    "CBet River in non-3Bet+ Pot": "cb3",
    "Fold to F CBet in non-3Bet+ Pot": "f_cb1",
    "Fold to T CBet in non-3Bet+ Pot": "f_cb2",
    "Fold to R CBet in non-3Bet+ Pot": "f_cb3",
    "CBet Flop": "cb1",
    "CBet Turn": "cb2",
    "CBet River": "cb3",
    "Fold to F CBet": "f_cb1",
    "Fold to T CBet": "f_cb2",
    "Fold to R CBet": "f_cb3",
    # floating
    "Float Flop": "float_bet",
    "Float Turn": "float_turn",
    "Float River": "float_river",
    "Float Turn in non-3Bet+ Pot": "float_turn",
    "Float River in non-3Bet+ Pot": "float_river",
    "Probe Turn": "probe_bet_turn",
    "Probe River": "probe_bet_river",
    "Probe Turn in non-3Bet+ Pot": "probe_bet_turn",
    "Probe River in non-3Bet+ Pot": "probe_bet_river",
    # aggression/showdown
    "WTSD": "wtsd",
    "WSD": "wmsd",
    # meta / identity
    "Player": "playershort",
    "Player Name Short": "playershort",
    "Winnings 3H": "profit100",
    "Hands Abbreviated": "n",
    "Hands": "n",
    # GenerationPoker custom stats may appear either as formulas later in the
    # export or as named layout cells in the visual HUD region.
    "GP 2X": "gp_2x",
    "GP OS": "gp_os",
    "GP LIMP": "gp_limp",
    "GenPoker_C/M VPIP": "vpip",
    "GenPoker_C/M PFR": "pfr",
    "GenPoker_C/M 3BET PF": "three_B",
    "GenPoker_C/M FOLD VS 3BET PF": "f_3bet",
    "GenPoker_C/M RFI": "rfi_total",
    "GenPoker_C/M ISO": "iso",
    "GenPoker_C/M LIMP": "limp",
    "GenPoker_C/M 4BET PF": "four_B",
    "GenPoker_C/M FOLD TO 4BET PF": "fold_vs_4bet",
    "GenPoker_C/M CBET FLOP (R POT)": "cb1",
    "GenPoker_C/M CBET TURN (R POT)": "cb2",
    "GenPoker_C/M CBET RIVER (R POT)": "cb3",
    "GenPoker_C/M FOLD TO CBET FLOP (R POT)": "f_cb1",
    "GenPoker_C/M FOLD TO CBET TURN (R POT)": "f_cb2",
    "GenPoker_C/M FOLD TO CBET RIVER (R POT)": "f_cb3",
    "GENPOKER_C/M FLOAT FLOP": "float_bet",
    "GENPOKER_C/M FLOAT TURN": "float_turn",
    "GENPOKER_C/M FLOAT RIVER": "float_river",
    "GENPOKER_C/M PROBE TURN": "probe_bet_turn",
    "GENPOKER_C/M PROBE RIVER": "probe_bet_river",
    "GENPOKER_C/M FOLD TO PROBE TURN": "fold_turn",
    "GENPOKER_C/M FOLD TO PROBE RIVER": "fold_river",
    "GenPoker Att To Steal": "steal",
    "GenPoker Fold to Steal": "f_steal",
    "Live Min Stack BB": "live_min_stack_bb",
}

# Position/info panel headers (e.g. "SB 3h", "BB 3h", "BU 3h", "Villain Info 3H")
# — the top-level groups PT4 lays out around the table. Explicitly listed so a
# stat that merely ends in "3H" (e.g. "Winnings 3H") is not mistaken for a panel.
_PANEL_RE = re.compile(r"^(SB|BB|BU|SG|BTN|UTG|MP|CO|EP|Villain[ A-Za-z]*)\s*[23][hH]$")
# Street sub-section within a panel (does not change the panel grouping).
_STREET_RE = re.compile(r"^(POST FLOP|Preflop)$")
# A user-defined PT4 stat column / formula token.
_CODE_RE = re.compile(r"^(cnt|val|amt|flg|enum)_[a-z0-9_]+$")
# A custom-stat arithmetic expression, e.g. "(cnt_gp_2x / cnt_gp2x_opp) * 100".
_FORMULA_RE = re.compile(r"[a-z_]+_[a-z0-9_]+\s*[/*+\-]\s*")

# Custom "GenerationPoker" formula stats fpdb now reproduces natively (open-size
# buckets on amt_p_raise_made + limp). Matched on a substring of the formula.
_FORMULA_TO_FPDB: list[tuple[str, str]] = [
    ("cnt_gp_2x / cnt_gp2x_opp", "gp_2x"),
    ("cnt_gp_os / cnt_gp_os_opp", "gp_os"),
    ("cnt_gp_limp / cnt_gp2x_opp", "gp_limp"),
]
_CARD_RE = re.compile(r"^[2-9TJQKA]{2}[so]?$")
_FORMAT_RE = re.compile(r"%[.\d]*[dfn%]")
_FONTS = {"Tahoma", "Calibri", "Verdana", "Go Master", "Arial"}
_NOISE = {"New Line", "Sum", "Avg", "Tournament Player", "win", "PUSH", "CALL",
          "Raises", "Preflop", "POST FLOP", "Note Editor", "Horizontal Line",
          "Spin", " ", ""}


_CHART_NAMES = {
    "DEF Explain", "Push Nash", "Call Nash", "Spin & Go Master",
    "Spin & Go Master Basic", "Flat call + 3Bet vs SB open",
}
_GRID_CARD_RE = re.compile(r"[2-9TJQKA]{2}[so]?")
_DECORATIVE_CONTAINER_TITLES = {"Horizontal Line", "New Line", "Note Editor"}
_SEAT_PANEL_TITLES = {"BTN", "BU", "SB", "BB", "Hero"}
_KNOWN_VISUAL_PANEL_TITLES = {
    "3BP IP", "3BP OOP", "BB Preflop", "Main Panel", "Main Panel2", "Misc",
    "Player Stack", "Post Flop", "Pre Flop", "RFI", "SB Preflop", "SRP IP", "SRP OOP",
}

PT4_PANEL_STYLES: dict[str, dict[str, str]] = {
    "SB": {"bordercolor": "#d7b500", "title_bgcolor": "#d7b500", "title_fgcolor": "#111111", "x": "0", "y": "0"},
    "BB": {"bordercolor": "#b75a70", "title_bgcolor": "#b75a70", "title_fgcolor": "#111111", "x": "0", "y": "0"},
    "BTN": {"bordercolor": "#009a9a", "title_bgcolor": "#009a9a", "title_fgcolor": "#111111", "x": "0", "y": "0"},
    "CO": {"bordercolor": "#009a9a", "title_bgcolor": "#009a9a", "title_fgcolor": "#111111", "x": "0", "y": "0"},
    "INFO": {"bordercolor": "#9a9a9a", "title_bgcolor": "#9a9a9a", "title_fgcolor": "#111111", "x": "0", "y": "54"},
}


def argb_to_hex(argb: int) -> str:
    """Convert a PT4 0xAARRGGBB colour int to a ``#rrggbb`` string."""
    return f"#{argb & 0xFFFFFF:06x}"


@dataclass
class ChartCell:
    """One cell of a 13x13 range chart: a hand and its decision fill colour."""

    hand: str
    fill: str  # "#rrggbb"
    text: str = "#000000"


@dataclass
class Chart:
    """A 13x13 preflop range chart popup (e.g. a push/fold Nash grid)."""

    name: str
    cells: list[ChartCell] = field(default_factory=list)

    def legend(self) -> dict[str, str]:
        """Map distinct fill colours to inferred decisions.

        Heuristic for push/fold grids: the colour on the weakest hand (``72o``)
        is the fold colour; the colour on the strongest (``AA``) is the action
        colour (push/call). Any third colour is left as "other".
        """
        by_hand = {c.hand: c.fill for c in self.cells}
        fold = by_hand.get("72o")
        action = by_hand.get("AA")
        out: dict[str, str] = {}
        for fill in dict.fromkeys(c.fill for c in self.cells):
            if fill == fold:
                out[fill] = "fold"
            elif fill == action:
                out[fill] = "call" if "Call" in self.name else "push"
            else:
                out[fill] = "other"
        return out


@dataclass
class Cell:
    """One displayed HUD item — a stat cell or a text label.

    ``kind`` is ``"stat"`` (a data cell, ``fpdb_stat`` set) or ``"text"`` (a
    column/row header or section caption like "POST FLOP"). ``full_width`` marks
    a text item that takes its own row (section captions).
    """

    pt4_name: str
    label: str = ""
    section: str = ""  # the PT4 position/info panel (e.g. "BU 3h")
    street: str = ""  # sub-section within the panel ("Preflop" / "POST FLOP")
    fpdb_stat: str | None = None  # set when the stat maps to fpdb
    formula: str | None = None  # set for user-defined formula stats
    hudcolor: str = ""
    hudbgcolor: str = ""
    kind: str = "stat"
    full_width: bool = False
    row: int = 0
    col: int = 0


@dataclass
class PopupCell:
    """One cell of a popup group: a text label or a stat, at a grid position."""

    kind: str  # "text" or "stat"
    text: str
    row: int
    col: int
    fg: str = ""
    bg: str = ""


@dataclass
class PopupGroup:
    """A PT4 popup group (e.g. SMK_Call push chart, a multi-stat info popup).

    Structurally identical to a table group: text/stat cells arranged in a grid.
    """

    name: str
    cells: list[PopupCell] = field(default_factory=list)
    rows: int = 0
    cols: int = 0


@dataclass
class Group:
    """A PT4 visual group/panel (e.g. BU 3h, Villain Info 3H)."""

    id: str
    name: str
    scope: str  # "player" / "table" / "popup"
    audience: str  # "everyone" / "opponents" / "hero"
    cells: list[Cell] = field(default_factory=list)
    rows: int = 0
    cols: int = 0


@dataclass
class Layout:
    name: str = ""
    cells: list[Cell] = field(default_factory=list)
    popups: list[str] = field(default_factory=list)
    charts: list[Chart] = field(default_factory=list)
    popup_groups: list[PopupGroup] = field(default_factory=list)
    groups: list[Group] = field(default_factory=list)

    @property
    def supported(self) -> list[Cell]:
        return [c for c in self.cells if c.fpdb_stat]

    @property
    def unsupported(self) -> list[Cell]:
        return [c for c in self.cells if not c.fpdb_stat]


def read_strings(data: bytes) -> list[str]:
    """Return the ordered list of length-prefixed UTF-16BE strings in ``data``."""
    out: list[str] = []
    i, n = 0, len(data)
    while i + 4 <= n:
        count = struct.unpack_from(">I", data, i)[0]
        if 0 < count < 4096 and i + 4 + 2 * count <= n:
            raw = data[i + 4 : i + 4 + 2 * count]
            try:
                s = raw.decode("utf-16-be")
            except UnicodeDecodeError:
                s = ""
            if s and all(0x20 <= ord(ch) < 0x7F or ch == "\t" for ch in s):
                out.append(s)
                i += 4 + 2 * count
                continue
        i += 1
    return out


def _tokenize(data: bytes) -> list[tuple[str, object, int]]:
    """Tokenise the PT4 typed stream.

    Token types: ``s`` (string), ``i`` (int: tag + 1 size byte + big-endian
    value), ``l`` (colour: tag + 4-byte 0xAARRGGBB), ``b`` (bool: tag + 1 byte),
    and the structural markers ``<`` / ``>``.
    """
    toks: list[tuple[str, object, int]] = []
    i, n = 0, len(data)
    while i < n:
        t = data[i]
        if t == 0x73 and i + 5 <= n:  # 's'
            ln = struct.unpack_from(">I", data, i + 1)[0]
            if 0 <= ln < 4096 and i + 5 + 2 * ln <= n:
                try:
                    s = data[i + 5 : i + 5 + 2 * ln].decode("utf-16-be")
                except UnicodeDecodeError:
                    s = None
                if s is not None and all(0x20 <= ord(c) < 0x7F or c == "\t" for c in s):
                    toks.append(("s", s, i))
                    i += 5 + 2 * ln
                    continue
            i += 1
        elif t == 0x69 and i + 2 <= n:  # 'i'
            sz = data[i + 1]
            if 0 < sz <= 8 and i + 2 + sz <= n:
                toks.append(("i", int.from_bytes(data[i + 2 : i + 2 + sz], "big"), i))
                i += 2 + sz
                continue
            i += 1
        elif t == 0x6C and i + 5 <= n:  # 'l' colour
            toks.append(("l", struct.unpack_from(">I", data, i + 1)[0], i))
            i += 5
        elif t == 0x62 and i + 2 <= n:  # 'b'
            toks.append(("b", data[i + 1], i))
            i += 2
        elif t in (0x3C, 0x3E):
            toks.append(("<" if t == 0x3C else ">", None, i))
            i += 1
        else:
            i += 1
    return toks


def _record_bounds(toks: list[tuple[str, object, int]], string_idx: int) -> tuple[int, int] | None:
    """Return the balanced ``<...>`` record enclosing a string token."""
    start = string_idx
    while start >= 0 and toks[start][0] != "<":
        start -= 1
    if start < 0:
        return None
    depth = 0
    for idx in range(start, len(toks)):
        if toks[idx][0] == "<":
            depth += 1
        elif toks[idx][0] == ">":
            depth -= 1
            if depth == 0:
                return start, idx
    return None


def _visual_records(data: bytes) -> list[dict]:
    """Extract PT4 visual text records from the typed layout stream.

    The useful HUD layout portion is not a flat sequence of strings: each text
    object carries a type (2 = panel, 4 = static label, 1 = stat cell), colours,
    and layout flags. Parsing these records lets us pair column headers with stat
    cells and preserve static per-cell colours.
    """
    toks = _tokenize(data)
    records = []
    seen: set[tuple[int, int]] = set()
    for idx, (typ, _val, _off) in enumerate(toks):
        if typ != "s":
            continue
        bounds = _record_bounds(toks, idx)
        if bounds is None or bounds in seen:
            continue
        seen.add(bounds)
        start, end = bounds
        sub = toks[start : end + 1]
        first_s = next((i for i, (t, _v, _o) in enumerate(sub) if t == "s"), None)
        if first_s is None:
            continue
        strings = [str(v) for t, v, _o in sub if t == "s"]
        ints = [int(v) for t, v, _o in sub if t == "i"]
        colors = [int(v) for t, v, _o in sub if t == "l"]
        kind = ints[0] if ints else None
        if kind not in (1, 2, 4):
            continue
        records.append(
            {
                "offset": sub[first_s][2],
                "text": str(sub[first_s][1]),
                "kind": kind,
                "strings": strings,
                "fg": argb_to_hex(colors[0]) if colors else "",
                "bg": argb_to_hex(colors[1]) if len(colors) > 1 else "",
            },
        )
    return records


def _is_visual_panel(record: dict) -> bool:
    """Whether a visual record is a top-level HUD panel/box."""
    if record["kind"] != 2:
        return False
    title = record["text"].strip()
    if not title or title in _DECORATIVE_CONTAINER_TITLES:
        return False
    if _PANEL_RE.match(title):
        return True
    upper = title.upper()
    if upper in {p.upper() for p in _SEAT_PANEL_TITLES}:
        return True
    if upper in {p.upper() for p in _KNOWN_VISUAL_PANEL_TITLES}:
        return True
    if "TABLE" in upper or "MIN STACK" in upper:
        return True
    return upper.startswith("VILLAIN")


def _assign_stat_tips(cells: list[Cell]) -> None:
    """Give each stat cell a tooltip label aligned by grid column.

    PT4 lays a header row and its stat row in the same columns, so a stat at
    column c takes the nearest real header text cell directly above it in
    column c (never crossing a full-width section caption like "POST FLOP").
    Empty and "N/A" placeholder cells ("-", "--") are skipped, so a stat whose
    own row has a "--" spacer still reaches the header above it (e.g. a Probe
    Turn cell under a "PROBE" header gets "T PROBE", not "T --"). A row-label at
    column 0 (F/T/R) is prefixed, giving tips like "F CB".

    This replaces an index-based header cycle that drifted whenever earlier
    stats or intervening New Line records advanced the counter, producing the
    rotated tips (vpip -> "AFq") seen in the villain panel. Stats with no header
    above them keep an empty label and fall back to their PT4 name.
    """
    placeholder = {"", "-", "--"}
    text_at = {(c.row, c.col): c for c in cells if c.kind == "text"}
    stat_at = {(c.row, c.col) for c in cells if c.kind == "stat"}
    caption_rows = {c.row for c in cells if c.kind == "text" and c.full_width}
    for c in cells:
        if c.kind != "stat" or c.label:
            continue
        # 1) Vertical layout: nearest real header text cell above, same column.
        header = ""
        for rr in range(c.row - 1, -1, -1):
            if rr in caption_rows:
                break
            above = text_at.get((rr, c.col))
            if above is None or above.full_width or above.label in placeholder:
                continue  # skip empty/N-A cells; keep looking up for the header
            header = above.label
            break
        row_label = ""
        if header:
            # A column header exists -> a col-0 text is a row label (F/T/R).
            row_label_cell = text_at.get((c.row, 0))
            if row_label_cell is not None and not row_label_cell.full_width:
                row_label = row_label_cell.label
        else:
            # 2) Horizontal layout: some panels put the header directly to the
            #    left of the stat on the same row ("VP <vpip> PFR <pfr>"). Take
            #    the nearest real text cell left of it, stopping at another stat.
            for cc in range(c.col - 1, -1, -1):
                if (c.row, cc) in stat_at:
                    break
                left = text_at.get((c.row, cc))
                if left is None or left.full_width or left.label in placeholder:
                    continue
                header = left.label
                break
        if row_label in {"F", "T", "R"} and header:
            c.label = f"{row_label} {header}"
        elif header:
            c.label = header
        elif row_label:
            c.label = row_label


def extract_hud_groups(data: bytes) -> list[Group]:
    recs = sorted(_visual_records(data), key=lambda r: r["offset"])

    def _is_named_container(r) -> bool:
        return (r["kind"] == 2 and bool(r["text"].strip())
                and r["text"].strip() not in _DECORATIVE_CONTAINER_TITLES)

    boundaries = sorted({
        i for i, r in enumerate(recs)
        if _is_named_container(r) or r["text"].strip() in _CHART_NAMES
    })

    groups: list[Group] = []
    for si in boundaries:
        r0 = recs[si]
        if not _is_visual_panel(r0):
            continue

        name = r0["text"].strip()
        end = next((b for b in boundaries if b > si), len(recs))

        scope = "player"
        if "Table" in name or "(Table)" in name:
            scope = "table"
        else:
            pos = panel_position(name)
            if not pos and name.upper().startswith("MIN STACK"):
                scope = "table"

        audience = "everyone"
        if "Villain" in name:
            audience = "opponents"
        elif "Hero" in name:
            audience = "hero"

        group_id = re.sub(r"[^a-zA-Z0-9_]", "_", name.lower()).strip("_")

        cells: list[Cell] = []
        row = col = 0
        street = ""

        for r in recs[si + 1 : end]:
            t = r["text"].strip()
            if r["kind"] == 2:
                if t == "New Line":
                    if col > 0:
                        row, col = row + 1, 0
                elif t == "Note Editor":
                    cells.append(
                        Cell(
                            pt4_name="Note Editor", label="", section=name, street=street,
                            fpdb_stat="player_note", kind="stat", hudcolor=r["fg"], hudbgcolor=r["bg"],
                            row=row, col=col
                        )
                    )
                    col += 1
                elif t == "Horizontal Line":
                    cells.append(
                        Cell(
                            pt4_name="Horizontal Line", label="", section=name, street=street,
                            fpdb_stat=None, kind="hline", hudcolor=r["fg"], hudbgcolor=r["bg"],
                            row=row, col=col
                        )
                    )
                    col += 1
                continue

            if r["kind"] == 4:
                txt = t[5:].strip() if t.startswith("_TXT:") else t
                is_section = bool(_STREET_RE.match(txt))
                cells.append(
                    Cell(
                        pt4_name=txt, label=txt, section=name, street=street,
                        kind="text", full_width=is_section, hudcolor=r["fg"], hudbgcolor=r["bg"],
                        row=row, col=col
                    )
                )
                col += 1
                if is_section:
                    street = txt
                continue

            if r["kind"] == 1:
                # A kind=1 record with no rendering colours is a stat *definition*
                # (its full formula catalogue, ~60+ strings), not a displayed
                # cell — e.g. a trailing group "source" stat. Every real display
                # cell carries an fg/bg colour, so skip the colourless ones rather
                # than inventing a phantom cell (the old GP 2X next to STACK, or
                # Winnings 3H next to a player name).
                if not r["fg"] and not r["bg"]:
                    continue
                stat_name = t
                mapped_stat = PT4_TO_FPDB.get(stat_name)
                if mapped_stat:
                    cells.append(
                        Cell(
                            pt4_name=stat_name, label="", section=name, street=street,
                            fpdb_stat=mapped_stat, kind="stat", hudcolor=r["fg"], hudbgcolor=r["bg"],
                            row=row, col=col
                        )
                    )
                else:
                    cells.append(
                        Cell(
                            pt4_name="", label="", section=name, street=street,
                            kind="text", hudcolor=r["fg"], hudbgcolor=r["bg"],
                            row=row, col=col
                        )
                    )
                col += 1

        _assign_stat_tips(cells)

        if not cells:
            continue

        groups.append(
            Group(
                id=group_id,
                name=name,
                scope=scope,
                audience=audience,
                cells=cells,
                rows=max((c.row for c in cells), default=0) + 1,
                cols=max((c.col for c in cells), default=0) + 1,
            )
        )
    return groups


def _map_visual_records(data: bytes) -> list[Cell]:
    """Map visual PT4 records to fpdb cells with usable headers/colours."""
    groups = extract_hud_groups(data)
    cells: list[Cell] = []
    for g in groups:
        cells.extend(g.cells)
    return cells


def extract_charts(source: str | bytes) -> list[Chart]:
    """Extract the 13x13 range-chart popups (push/fold Nash grids) from a file.

    Each chart cell is a hand string immediately followed by two colour tokens
    (text colour, then the decision fill colour). Cells are grouped under the
    most recent chart-popup name; only populated grids are returned.
    """
    data = source if isinstance(source, bytes) else open(source, "rb").read()
    toks = _tokenize(data)
    charts: dict[str, Chart] = {}
    current: str | None = None
    for k, (typ, val, _off) in enumerate(toks):
        if typ != "s":
            continue
        if val in _CHART_NAMES:
            current = val
            charts.setdefault(current, Chart(name=current))
            continue
        if current is None or not _GRID_CARD_RE.fullmatch(val):
            continue
        # collect the next two colour tokens before the cell closes / next card
        colours: list[int] = []
        for typ2, val2, _o2 in toks[k + 1 : k + 8]:
            if typ2 == "l":
                colours.append(val2)
                if len(colours) == 2:
                    break
            elif typ2 == "s" and _GRID_CARD_RE.fullmatch(str(val2)):
                break
        if len(colours) == 2:
            charts[current].cells.append(
                ChartCell(hand=val, text=argb_to_hex(colours[0]), fill=argb_to_hex(colours[1])),
            )
    return [c for c in charts.values() if c.cells]


def _is_label(s: str) -> bool:
    # Displayed cell captions are short and padded with spaces in the export.
    return 1 <= len(s) <= 9 and (s != s.strip()) and not _CARD_RE.match(s.strip())


def extract_popup_groups(source: str | bytes) -> list[PopupGroup]:
    """Extract PT4 popup groups (info popups + push/fold text-grid charts).

    Popup groups use the same record structure as table groups: a named ``kind==2``
    container followed by text (kind 4) and stat (kind 1) cells, with "New Line"
    records delimiting rows. Returns one :class:`PopupGroup` per named,
    non-decorative, non-HUD-panel group that carries at least one cell.
    """
    data = source if isinstance(source, bytes) else open(source, "rb").read()
    recs = sorted(_visual_records(data), key=lambda r: r["offset"])
    # A group's content ends at the next *named container* (popup group OR table
    # panel) OR at the next record whose text is a known popup/chart name — the
    # latter catches a following popup that is rendered as a bare text marker
    # (e.g. "Spin & Go Master" + its promo line) rather than a kind==2 container,
    # which would otherwise be absorbed into the preceding chart. Decorative
    # New Line / Horizontal Line records only delimit rows within a group.
    def _is_named_container(r) -> bool:
        return (r["kind"] == 2 and bool(r["text"].strip())
                and r["text"].strip() not in _DECORATIVE_CONTAINER_TITLES)

    boundaries = sorted({
        i for i, r in enumerate(recs)
        if _is_named_container(r) or r["text"].strip() in _CHART_NAMES
    })
    groups: list[PopupGroup] = []
    for si in boundaries:
        r0 = recs[si]
        # Only emit real group containers; bare name markers and table panels are
        # boundaries but not popups in their own right.
        if not _is_named_container(r0) or _is_visual_panel(r0):
            continue
        name = r0["text"].strip()
        end = next((b for b in boundaries if b > si), len(recs))
        cells: list[PopupCell] = []
        row = col = 0
        for r in recs[si + 1 : end]:
            t = r["text"].strip()
            if r["kind"] == 2:
                if t == "New Line" and col:  # close the current grid row
                    row, col = row + 1, 0
                continue
            if r["kind"] == 4:
                txt = t[5:].strip() if t.startswith("_TXT:") else t
                if txt:
                    cells.append(PopupCell("text", txt, row, col, r["fg"], r["bg"]))
                col += 1
            elif r["kind"] == 1:
                cells.append(PopupCell("stat", t, row, col, r["fg"], r["bg"]))
                col += 1
        if not cells:
            continue
        groups.append(
            PopupGroup(
                name=name,
                cells=cells,
                rows=max((c.row for c in cells), default=0) + 1,
                cols=max((c.col for c in cells), default=0) + 1,
            ),
        )
    return groups


def parse(source: str | bytes) -> Layout:
    """Parse a ``.pt4hud`` file path or raw bytes into a :class:`Layout`."""
    data = source if isinstance(source, bytes) else open(source, "rb").read()
    strings = read_strings(data)
    if not strings or strings[0] != MAGIC:
        msg = "not a PT4 HUD layout export (missing magic header)"
        raise ValueError(msg)

    layout = Layout(name=strings[1] if len(strings) > 1 else "")
    layout.cells = _map_visual_records(data)
    layout.groups = extract_hud_groups(data)
    layout.popup_groups = extract_popup_groups(data)
    # The record-tree path (above) carries headers/colours and is preferred. When
    # it yields nothing (older or differently-structured exports), fall back to the
    # flat string scan for *every* recognised stat — not just the first one.
    use_string_scan = not layout.cells
    panel = ""
    street = ""
    seen_stats: set[tuple[str, str]] = set()
    seen_formulas: set[str] = set()
    pending_label = ""

    for s in strings:
        stripped = s.strip()
        # Panel/street markers are matched before the stat catalogue so the
        # grouping stays correct; a known stat never matches _PANEL_RE.
        if _PANEL_RE.match(stripped):
            panel = stripped
            street = ""
            continue
        if _STREET_RE.match(stripped):
            street = stripped
            continue
        if s in _FONTS or _CARD_RE.match(stripped) or _FORMAT_RE.fullmatch(stripped):
            continue
        if _is_label(s):
            pending_label = stripped
            continue
        if s in _NOISE:
            continue

        # A recognised standard stat (mapped) ...
        if s in PT4_TO_FPDB:
            # Visual records carry the layout copy with headers/colours; the flat
            # scan is the fallback when they are unavailable. Dedup per (panel,
            # stat) so repeated panels don't multiply a stat.
            if use_string_scan:
                key = (panel, s)
                if key not in seen_stats:
                    seen_stats.add(key)
                    layout.cells.append(Cell(pt4_name=s, label=pending_label, section=panel, street=street, fpdb_stat=PT4_TO_FPDB[s]))
            pending_label = ""
            continue
        # ... a user-defined formula / custom column ...
        if _FORMULA_RE.search(s) or _CODE_RE.match(s):
            if s not in seen_formulas and _FORMULA_RE.search(s):
                seen_formulas.add(s)
                # Some custom formulas now map to native fpdb stats.
                mapped = next((fp for sub, fp in _FORMULA_TO_FPDB if sub in s), None)
                if mapped and not any(c.fpdb_stat == mapped for c in layout.cells):
                    layout.cells.append(
                        Cell(pt4_name=s, label=pending_label, section=panel, street=street, fpdb_stat=mapped, formula=s),
                    )
                elif not mapped:
                    layout.cells.append(Cell(pt4_name=s, label=pending_label, section=panel, street=street, formula=s))
            pending_label = ""
            continue
        # ... a popup / range chart name.
        if stripped in _CHART_NAMES and stripped not in layout.popups:
            layout.popups.append(stripped)

    layout.charts = extract_charts(data)
    return layout


def _tip(c: Cell) -> str:
    """A readable HUD tooltip: the panel label, else the PT4 name (not a formula)."""
    if c.label:
        return c.label
    if c.formula:
        return c.fpdb_stat or ""
    return c.pt4_name


def grouped_placements(cells: list[Cell], cols: int) -> tuple[list[tuple[Cell, int, int]], int]:
    """Assign each cell a (row, col), starting every PT4 panel on a fresh row.

    This mirrors PT4's panel grouping (SB / BB / BU / info) as contiguous
    row-blocks of the fpdb grid — the closest the grid model gets to PT4's
    free-form, multi-panel layout. Returns the placements and the row count.
    """
    placements: list[tuple[Cell, int, int]] = []
    row = col = 0
    current = None
    for c in cells:
        if current is not None and c.section != current and col != 0:
            row += 1
            col = 0  # new panel -> new row
        current = c.section
        placements.append((c, row, col))
        col += 1
        if col >= cols:
            row += 1
            col = 0
    total = max((r for _, r, _ in placements), default=-1) + 1
    return placements, max(total, 1)


def to_stat_set(layout: Layout, name: str | None = None, cols: int = 4) -> str:
    """Render the supported cells as an fpdb ``<ss>`` (stat-set) XML node."""
    name = name or (layout.name or "imported")[:40]
    placements, rows = grouped_placements(layout.supported, cols)
    lines = [f'    <ss name={quoteattr(name)} rows="{rows}" cols="{cols}">']
    for c, r, col in placements:
        tip = _tip(c)
        lines.append(
            f'        <stat _rowcol="({r + 1},{col + 1})" _stat_name={quoteattr(c.fpdb_stat)} '
            f"click=\"\" popup=\"default\" tip={quoteattr(tip)} hudprefix=\"\" hudsuffix=\"\" hudcolor=\"\"/>",
        )
    lines.append("    </ss>")
    return "\n".join(lines)


def _summary(layout: Layout) -> str:
    out = [f"Layout: {layout.name}", ""]
    out.append(f"Supported stats ({len(layout.supported)}) -> mapped to fpdb:")
    for c in layout.supported:
        sect = f"[{c.section}] " if c.section else ""
        out.append(f"  {sect}{c.pt4_name!r:42s} -> {c.fpdb_stat}")
    custom = [c for c in layout.unsupported if c.formula]
    if custom:
        out.append("")
        out.append(f"Unsupported — user-defined formula stats ({len(custom)}):")
        for c in custom:
            out.append(f"  {c.formula}")
    text_popups = [p for p in layout.popups if p not in {c.name for c in layout.charts}]
    if layout.charts:
        out.append("")
        out.append(f"Range charts ({len(layout.charts)}) — extracted 13x13 grids:")
        for ch in layout.charts:
            leg = ", ".join(f"{argb}={dec}" for argb, dec in ch.legend().items())
            out.append(f"  {ch.name!r}: {len(ch.cells)} cells; legend: {leg}")
    if text_popups:
        out.append("")
        out.append(f"Text/strategy popups (not grids) ({len(text_popups)}):")
        for p in text_popups:
            out.append(f"  {p}")
    return "\n".join(out)


def to_dict(layout: Layout) -> dict:
    """Serialise the parsed layout (stats + charts) to a JSON-ready dict."""
    return {
        "name": layout.name,
        "stats": [
            {"pt4_name": c.pt4_name, "label": c.label, "section": c.section,
             "fpdb_stat": c.fpdb_stat, "formula": c.formula}
            for c in layout.cells
        ],
        "charts": [
            {"name": ch.name, "legend": ch.legend(),
             "cells": [{"hand": x.hand, "fill": x.fill, "text": x.text} for x in ch.cells]}
            for ch in layout.charts
        ],
        "popup_groups": [
            {"name": g.name, "rows": g.rows, "cols": g.cols,
             "cells": [{"kind": c.kind, "text": c.text, "row": c.row, "col": c.col,
                        "fg": c.fg, "bg": c.bg} for c in g.cells]}
            for g in layout.popup_groups
        ],
    }


def panel_position(label: str) -> str:
    """Derive a position binding from a PT4 panel label (e.g. "SB 3h" -> "SB").

    Returns "" for general/info panels, which are always shown.
    """
    m = label.strip().upper()
    for prefix, code in (("SB", "SB"), ("BB", "BB"), ("BTN", "BTN"), ("BU", "BTN"),
                         ("CO", "CO"), ("MP", "MP"), ("EP", "EP"), ("UTG", "EP")):
        if m.startswith(prefix):
            return code
    return ""


def panel_style(label: str) -> dict[str, str]:
    """Default style exported into fpdb config for a PT4 panel label."""
    pos = panel_position(label)
    if pos:
        return PT4_PANEL_STYLES.get(pos, {})
    if label.strip():
        return PT4_PANEL_STYLES["INFO"]
    return {}


def _panel_groups(cells: list[Cell]) -> list[tuple[str, list[Cell]]]:
    """Group cells by PT4 panel (section), in first-seen order."""
    order: list[str] = []
    groups: dict[str, list[Cell]] = {}
    for c in cells:
        key = c.section or ""
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(c)
    return [(k, groups[k]) for k in order]


def _hline_el(doc, c: Cell, r: int, col: int):
    h = doc.createElement("hline")
    h.setAttribute("_rowcol", f"({r + 1},{col + 1})")
    if c.hudcolor:
        h.setAttribute("color", c.hudcolor)
    return h


def _stat_el(doc, c: Cell, r: int, col: int):
    st = doc.createElement("stat")
    st.setAttribute("_rowcol", f"({r + 1},{col + 1})")
    st.setAttribute("_stat_name", c.fpdb_stat)
    st.setAttribute("popup", "default")
    st.setAttribute("tip", _tip(c))
    st.setAttribute("click", "")
    if c.hudcolor:
        st.setAttribute("hudcolor", c.hudcolor)
    if c.hudbgcolor:
        st.setAttribute("hudbgcolor", c.hudbgcolor)
    return st


def _legible_fg(fg: str, bg: str) -> str:
    """Keep ``fg`` unless it is invisible against ``bg`` (identical colours).

    PT4 occasionally exports a header as black-on-black (e.g. VP/PFR/AFq/SQ in
    the villain panel). Reproducing that faithfully yields an unreadable label,
    so when foreground equals background pick a contrasting colour from the
    background's luminance instead.
    """
    if not fg or not bg or fg.lower() != bg.lower():
        return fg
    try:
        r_, g_, b_ = int(bg[1:3], 16), int(bg[3:5], 16), int(bg[5:7], 16)
    except (ValueError, IndexError):
        return fg
    luminance = 0.299 * r_ + 0.587 * g_ + 0.114 * b_
    return "#000000" if luminance > 140 else "#ffffff"


def _text_el(doc, c: Cell, r: int, col: int, span: int):
    t = doc.createElement("text")
    t.setAttribute("_rowcol", f"({r + 1},{col + 1})")
    t.setAttribute("label", c.label or c.pt4_name)
    if span > 1:
        t.setAttribute("colspan", str(span))
    fg = _legible_fg(c.hudcolor, c.hudbgcolor)
    if fg:
        t.setAttribute("fgcolor", fg)
    if c.hudbgcolor:
        t.setAttribute("bgcolor", c.hudbgcolor)
    return t


def _flow_items(items: list[Cell], cols: int):
    """Lay ordered items into a ``cols``-wide grid (PT4 "Arrange in Grid").

    Returns ``(placements, rows)`` where each placement is ``(cell, row, col,
    span)``. A ``full_width`` item (section caption like "POST FLOP") takes its
    own full-width row.
    """
    placed = []
    row = col = 0
    for c in items:
        if c.full_width:
            if col != 0:
                row += 1
                col = 0
            placed.append((c, row, 0, max(cols, 1)))
            row += 1
            col = 0
        else:
            placed.append((c, row, col, 1))
            col += 1
            if col >= cols:
                row += 1
                col = 0
    total = max((r for _, r, _, _ in placed), default=-1) + 1
    return placed, max(total, 1)


def import_to_config(
    source: str | bytes, config, name: str | None = None, charts_path: str | None = None, multiblock: bool = True,
) -> dict:
    """Insert a parsed ``.pt4hud`` layout into an fpdb ``Configuration`` document.

    Appends a ``<ss>`` stat-set to ``<stat_sets>`` — with one ``<block>`` per PT4
    panel (SB/BB/BU/info) when ``multiblock`` (the default) so the HUD shows
    stacked panels per seat; otherwise a single grouped grid. When the layout has
    range charts, also writes a JSON sidecar and appends a ``RangeChartPopup``
    ``<pu>`` to ``<popup_windows>``. Caller is expected to ``config.save()``.
    """
    layout = parse(source)
    doc = config.doc
    name = (name or layout.name or "pt4_import")[:40]
    cols = 4

    # Place stat cells and (PT4-style) text-label items together.
    place_cells = [c for c in layout.cells if c.kind == "text" or c.fpdb_stat]
    n_stats = sum(1 for c in place_cells if c.fpdb_stat)
    ss = doc.createElement("ss")
    ss.setAttribute("name", name)
    ss.setAttribute("cols", str(cols))
    n_blocks = 0
    if multiblock and layout.groups:
        ss.setAttribute("show_hero_hud", "false")
        total_rows = 0
        max_cols = 4
        for g in layout.groups:
            blk = doc.createElement("block")
            blk.setAttribute("id", g.id)
            blk.setAttribute("label", g.name)
            blk.setAttribute("scope", g.scope)
            blk.setAttribute("audience", g.audience)
            blk.setAttribute("position", panel_position(g.name))
            for attr, value in panel_style(g.name).items():
                blk.setAttribute(attr, value)
            blk.setAttribute("rows", str(g.rows))
            blk.setAttribute("cols", str(g.cols))

            for c in g.cells:
                r, col = c.row, c.col
                if c.kind == "text":
                    span = g.cols if c.full_width else 1
                    blk.appendChild(_text_el(doc, c, r, col, span))
                elif c.kind == "hline":
                    blk.appendChild(_hline_el(doc, c, r, col))
                else:
                    blk.appendChild(_stat_el(doc, c, r, col))
            ss.appendChild(blk)
            total_rows += g.rows
            max_cols = max(max_cols, g.cols)
            n_blocks += 1
        ss.setAttribute("rows", str(max(total_rows, 1)))
        ss.setAttribute("cols", str(max_cols))
    else:
        stat_cells = [c for c in place_cells if c.fpdb_stat]
        placements, rows = grouped_placements(stat_cells, cols)
        ss.setAttribute("rows", str(rows))
        for c, r, col in placements:
            ss.appendChild(_stat_el(doc, c, r, col))
    ss_parent = doc.getElementsByTagName("stat_sets")
    if ss_parent:
        # Re-importing the same layout should replace its stat-set, not pile up
        # duplicate <ss name="..."> entries.
        for existing in list(ss_parent[0].getElementsByTagName("ss")):
            if existing.getAttribute("name") == name:
                ss_parent[0].removeChild(existing)
        ss_parent[0].appendChild(ss)

    popup_name = None
    if layout.charts:
        if charts_path is None:
            base = os.path.splitext(getattr(config, "file", "") or "HUD_config.xml")[0]
            slug = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").lower()
            charts_path = f"{base}.{slug}.charts.json"
        with open(charts_path, "w", encoding="utf-8") as fh:
            json.dump(to_dict(layout), fh, indent=2)
        popup_name = f"{name} charts"
        pu = doc.createElement("pu")
        pu.setAttribute("pu_name", popup_name)
        pu.setAttribute("pu_class", "RangeChartPopup")
        pu.setAttribute("pu_source", charts_path)
        pu_parent = doc.getElementsByTagName("popup_windows")
        if pu_parent:
            for existing in list(pu_parent[0].getElementsByTagName("pu")):
                if existing.getAttribute("pu_name") == popup_name:
                    pu_parent[0].removeChild(existing)
            pu_parent[0].appendChild(pu)

    # Import PT4 popup groups (info popups + text-grid push charts) as BlockPopup
    # windows pointing at a JSON sidecar with their full text/stat grid.
    popup_group_names: list[str] = []
    if layout.popup_groups:
        base = os.path.splitext(getattr(config, "file", "") or "HUD_config.xml")[0]
        slug = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").lower()
        popups_path = f"{base}.{slug}.popups.json"
        with open(popups_path, "w", encoding="utf-8") as fh:
            json.dump({"popup_groups": to_dict(layout)["popup_groups"]}, fh, indent=2)
        pu_parent = doc.getElementsByTagName("popup_windows")
        if pu_parent:
            for group in layout.popup_groups:
                pu_pname = f"{name} - {group.name}"
                for existing in list(pu_parent[0].getElementsByTagName("pu")):
                    if existing.getAttribute("pu_name") == pu_pname:
                        pu_parent[0].removeChild(existing)
                pu = doc.createElement("pu")
                pu.setAttribute("pu_name", pu_pname)
                pu.setAttribute("pu_class", "BlockPopup")
                pu.setAttribute("pu_source", popups_path)
                pu.setAttribute("pu_group", group.name)
                pu_parent[0].appendChild(pu)
                popup_group_names.append(pu_pname)

    return {
        "name": name,
        "stats": n_stats,
        "blocks": n_blocks,
        "charts": [c.name for c in layout.charts],
        "charts_path": charts_path,
        "popup": popup_name,
        "popup_groups": popup_group_names,
        "unmapped": [c.formula for c in layout.unsupported if c.formula],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Parse a PT4 .pt4hud layout into an fpdb HUD config.")
    ap.add_argument("path", help="path to a .pt4hud file")
    ap.add_argument("--xml", action="store_true", help="print the fpdb <ss> stat-set XML")
    ap.add_argument("--json", action="store_true", help="dump the full layout (stats + charts) as JSON")
    ap.add_argument("--name", default=None, help="name for the generated stat-set")
    ap.add_argument("--cols", type=int, default=4, help="columns in the generated grid")
    args = ap.parse_args(argv)

    layout = parse(args.path)
    if args.json:
        print(json.dumps(to_dict(layout), indent=2))
    elif args.xml:
        print(to_stat_set(layout, name=args.name, cols=args.cols))
    else:
        print(_summary(layout))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
