"""Synthetic PokerTracker 4 HUD layouts, shaped as the exports the parser meets (#614).

A ``.pt4hud`` export is a typed stream: ``s`` strings (big-endian UTF-16, length
prefixed), ``i`` ints, ``l`` ARGB colours, and ``<`` / ``>`` around each record. A
visual record holds a kind (2 = panel or container, 4 = static text, 1 = stat
cell), its text and its two colours. These builders write just that, so the
parser's tests do not depend on layouts downloaded to one machine.

Each layout reproduces the structure of one real export the parser was tuned on:
GenerationPoker's 2-handed and cash HUDs, Spin & Go Master's basic HUD with its
Nash charts, a generic matrix export, and a heads-up cash HUD with named panels.

    python -m tests.helpers.pt4hud_layouts   # rewrite tests/fixtures/pt4hud/
"""

from __future__ import annotations

import struct
from pathlib import Path

from fpdb_3_legacy.pt4hud import MAGIC

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "pt4hud"
FG, BG = 0xFF000000, 0xFFFFFFFF
PANEL, TEXT, STAT = 2, 4, 1


def _s(text: str) -> bytes:
    return b"s" + struct.pack(">I", len(text)) + text.encode("utf-16-be")


def record(kind: int, text: str, fg: int = FG, bg: int = BG) -> bytes:
    """One visual record: its kind, its text, and its text and fill colours."""
    return (
        b"<" + b"i\x01" + bytes([kind]) + _s(text) + b"l" + struct.pack(">I", fg) + b"l" + struct.pack(">I", bg) + b">"
    )


def panel(title: str) -> bytes:
    return record(PANEL, title)


def new_line() -> bytes:
    return record(PANEL, "New Line")


def rows(*lines: tuple[str | tuple[str], ...]) -> bytes:
    """Panel rows: a plain string is a static text cell, a 1-tuple ``(name,)`` a stat cell."""
    out = b""
    for index, line in enumerate(lines):
        if index:
            out += new_line()
        for cell in line:
            out += record(STAT, cell[0]) if isinstance(cell, tuple) else record(TEXT, cell)
    return out


def chart(name: str, action: str) -> bytes:
    """A 13x13 range chart: each hand string followed by its text and fill colours."""
    ranks = "AKQJT98765432"
    fill = {"push": 0xFF00A000, "fold": 0xFFC0C0C0}
    out = panel(name)
    for i, high in enumerate(ranks):
        for j, low in enumerate(ranks):
            hand = high + low if i == j else (high + low + "s" if j > i else low + high + "o")
            strong = i == j or (min(i, j) == 0 and max(i, j) <= 4)
            out += record(TEXT, hand, FG, fill["push" if strong else "fold"])
    # The legend names the action and the fold colour, as PT4's charts do.
    return out + record(TEXT, action, FG, fill["push"]) + record(TEXT, "fold", FG, fill["fold"])


def layout(name: str, *parts: bytes) -> bytes:
    return _s(MAGIC) + _s(name) + b"".join(parts)


def generationpoker_2h() -> bytes:
    """Three seat panels, headers above their stats, F/T row labels, a ``--`` spacer."""
    return layout(
        "Synthetic GenerationPoker 2H",
        panel("SB 2h"),
        rows(
            ("RFI", "Fv3B", "LMP"),
            (("Raise First In",), ("Fold to PF 3Bet",), ("Preflop Limp",)),
            ("STL", "CB", "WTSD"),
            (("Att To Steal",), ("CBet Flop",), ("WTSD",)),
        ),
        panel("BB 2h"),
        rows(
            ("3B", "FvSTL", "CALL"),
            (("3Bet Preflop",), ("Fold to Steal",), ("Call Steal",)),
            ("", "FvCB", "PROBE"),
            ("F", ("Fold to F CBet",), "--"),
            ("T", "--", ("Probe Turn",)),
        ),
        panel("Villain 2h"),
        rows(
            ("VP", "PFR", "AF", "H"),
            (("VPIP",), ("PFR",), ("Total AFq",), ("Hands",)),
            ("4B", "FL", "W$SD", "SQZ"),
            (("4Bet Preflop",), ("Float Flop",), ("WSD",), ("Preflop Squeeze",)),
        ),
    )


def spin_basic() -> bytes:
    """Short seat titles (BTN/SB/BB), a villain info panel, and the two Nash charts."""
    return layout(
        "Synthetic Spin & Go Basic",
        panel("BTN"),
        rows(
            ("VPIP", "PFR", "LMP", "STL"),
            (("VPIP",), ("PFR",), ("Preflop Limp",), ("Att To Steal",)),
            ("RFI", "CB", "CB T", "AF"),
            (("Raise First In",), ("CBet Flop",), ("CBet Turn",), ("Total AFq",)),
        ),
        panel("SB"),
        rows(
            ("FvSTL", "3B", "CALL", "LMP"),
            (("Fold to Steal",), ("3Bet Steal",), ("Call Steal",), ("Preflop Limp",)),
            ("FvCB", "PROBE"),
            (("Fold to F CBet",), ("Probe Turn",)),
        ),
        panel("BB"),
        rows(
            ("FvSTL", "3B", "CALL", "FvCB"),
            (("Fold to Steal",), ("3Bet Steal",), ("Call Steal",), ("Fold to F CBet",)),
            ("FL", "PROBE"),
            (("Float Flop",), ("Probe Turn",)),
        ),
        panel("Villain info"),
        rows(
            ("H", "VP", "PF", "Sq", "3B"),
            (("Hands",), ("VPIP",), ("PFR",), ("Preflop Squeeze",), ("3Bet Preflop",)),
            ("WTSD", "W$SD", "4B", "CC"),
            (("WTSD",), ("WSD",), ("4Bet Preflop",), ("Cold Call 2Bet PF",)),
        ),
        chart("Push Nash", "push"),
        chart("Call Nash", "call"),
    )


def spin_new() -> bytes:
    """A generic Tools / Preflop / Flop / PT4 matrix: large containers, no seat panels."""
    return layout(
        "Synthetic Spin New",
        panel("Tools"),
        rows(("Hands",), (("Hands",),)),
        panel("Preflop"),
        rows(("VP", "PF", "3B"), (("VPIP",), ("PFR",), ("3Bet Preflop",))),
        panel("Flop"),
        rows(("CB", "FvCB"), (("CBet Flop",), ("Fold to F CBet",))),
        panel("PT4"),
        rows(("WTSD",), (("WTSD",),)),
    )


def hu_cash() -> bytes:
    """Panels named after the spot (SB Preflop, SRP IP, ...) rather than the seat."""
    return layout(
        "Synthetic HU Cash",
        panel("SB Preflop"),
        rows(("RFI", "LMP", "Fv3B"), (("Raise First In",), ("Preflop Limp",), ("Fold to PF 3Bet",))),
        panel("BB Preflop"),
        rows(("3-Bet", "FvSTL", "CALL"), (("3Bet Steal",), ("Fold to Steal",), ("Call Steal",))),
        panel("SRP IP"),
        rows(
            ("CB F", "CB T", "FL"), (("CBet Flop in non-3Bet+ Pot",), ("CBet Turn in non-3Bet+ Pot",), ("Float Flop",))
        ),
        panel("SRP OOP"),
        rows(
            ("PROBE T", "FvCB F"),
            (("Probe Turn in non-3Bet+ Pot",), ("Fold to F CBet in non-3Bet+ Pot",)),
        ),
        panel("Misc"),
        rows(("H", "WTSD", "W$SD"), (("Hands",), ("WTSD",), ("WSD",))),
    )


# GenerationPoker's own named stats, as its cash HUD lays them out.
_GP_STATS = (
    ("VP", "GenPoker_C/M VPIP"),
    ("PFR", "GenPoker_C/M PFR"),
    ("3B", "GenPoker_C/M 3BET PF"),
    ("v3B", "GenPoker_C/M FOLD VS 3BET PF"),
    ("RFI", "GenPoker_C/M RFI"),
    ("ISO", "GenPoker_C/M ISO"),
    ("LMP", "GenPoker_C/M LIMP"),
    ("4B", "GenPoker_C/M 4BET PF"),
    ("v4B", "GenPoker_C/M FOLD TO 4BET PF"),
    ("CB F", "GenPoker_C/M CBET FLOP (R POT)"),
    ("CB T", "GenPoker_C/M CBET TURN (R POT)"),
    ("CB R", "GenPoker_C/M CBET RIVER (R POT)"),
    ("vCB F", "GenPoker_C/M FOLD TO CBET FLOP (R POT)"),
    ("vCB T", "GenPoker_C/M FOLD TO CBET TURN (R POT)"),
    ("vCB R", "GenPoker_C/M FOLD TO CBET RIVER (R POT)"),
    ("FL F", "GENPOKER_C/M FLOAT FLOP"),
    ("FL T", "GENPOKER_C/M FLOAT TURN"),
    ("FL R", "GENPOKER_C/M FLOAT RIVER"),
    ("PR T", "GENPOKER_C/M PROBE TURN"),
    ("PR R", "GENPOKER_C/M PROBE RIVER"),
    ("vPR T", "GENPOKER_C/M FOLD TO PROBE TURN"),
    ("vPR R", "GENPOKER_C/M FOLD TO PROBE RIVER"),
    ("STL", "GenPoker Att To Steal"),
    ("vSTL", "GenPoker Fold to Steal"),
)


def _gp_panel(title: str, stats: tuple[tuple[str, str], ...], width: int = 6) -> bytes:
    lines: list[tuple] = []
    for start in range(0, len(stats), width):
        chunk = stats[start : start + width]
        lines.append(tuple(label for label, _name in chunk))
        lines.append(tuple((name,) for _label, name in chunk))
    return panel(title) + rows(*lines)


def generationpoker_cash() -> bytes:
    """GenerationPoker's custom-named stats across five named panels, over a hundred cells."""
    # Main Panel2 opens with the fold-to-4bet stat, as the export does.
    second = (_GP_STATS[8], *(_GP_STATS[:8]), *_GP_STATS[9:])
    return layout(
        "Synthetic GenerationPoker Cash",
        _gp_panel("Main Panel", _GP_STATS),
        _gp_panel("Pre Flop", _GP_STATS),
        _gp_panel("Post Flop", _GP_STATS[9:]),
        _gp_panel("RFI", _GP_STATS),
        _gp_panel("Main Panel2", second),
    )


LAYOUTS = {
    "generationpoker_2h.pt4hud": generationpoker_2h,
    "spin_basic.pt4hud": spin_basic,
    "spin_new.pt4hud": spin_new,
    "hu_cash.pt4hud": hu_cash,
    "generationpoker_cash.pt4hud": generationpoker_cash,
}


def write_all(target: Path = FIXTURES) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for name, build in LAYOUTS.items():
        (target / name).write_bytes(build())


if __name__ == "__main__":
    write_all()
