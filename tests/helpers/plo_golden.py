"""The deterministic Pot-Limit Omaha corpus behind the PLO study pack (#368).

Thirteen six-max $0.50/$1 Omaha hands, every stack $100 and no rake, so every
pot in the files is exact arithmetic rather than a rounding question. The
seats keep one role throughout, as in the Hold'em golden corpus: seat 1 Anna
is the hijack, seat 2 Boris the cutoff and the recorded hero, seat 3 Cara the
button, seat 4 Dave the small blind, seat 5 Erin the big blind, seat 6 Frank
under the gun.

Between them the hands reach every family the PLO pack ships: an unopened
open, a 3-bet, a squeeze, a blind defence, single-raised pots from the
raiser's and the caller's seat both in and out of position, a turn barrel, a
multiway flop, a 3-bet pot from both sides, monotone and paired boards, and
one showdown so the field has some known cards and most of it does not.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

from tests.helpers.analytics_golden import build_config

PLO_DIR: Final[Path] = Path(__file__).resolve().parents[1] / "fixtures" / "analytics" / "plo"

#: The game category every hand in this corpus is stored as.
PLO_GAME: Final[str] = "omahahi"

#: The recorded hero, so a test can say which side is which without guessing.
HERO_NAME: Final[str] = "Boris"


def plo_files() -> list[Path]:
    """Every corpus file, in the order their hand numbers run."""
    return sorted(PLO_DIR.glob("*.txt"))


def five_card_files(directory: Path) -> list[Path]:
    """The same action scenarios as real five-card hand histories for import.

    Distinct hand numbers and table names keep both variants in one database.
    Each known holding gains an unused low card, consistently across its dealt,
    shown and summary lines. The paired-board showdown keeps the same winner.
    Board cards and all betting and money stay as in the four-card corpus.
    """
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for original in plo_files():
        contents = original.read_text(encoding="utf-8")
        used = set(re.findall(r"\b[2-9TJQKA][cdhs]\b", contents))
        holdings: dict[str, str] = {}

        def add_card(match: re.Match) -> str:
            cards = match[1]
            if cards not in holdings:
                extra = next(
                    f"{rank}{suit}"
                    for rank in "3456789TJQKA2" for suit in "cdhs"
                    if f"{rank}{suit}" not in used
                )
                used.add(extra)
                holdings[cards] = f"{cards} {extra}"
            return f"[{holdings[cards]}]"

        lines = []
        for line in contents.splitlines():
            if "Dealt to " in line or ": shows [" in line or " showed [" in line:
                line = re.sub(r"\[([^]]+)\]", add_card, line)
            lines.append(line)
        contents = "\n".join(lines) + "\n"
        contents = contents.replace("#320000", "#330000").replace("  Omaha Pot Limit", "  5 Card Omaha Pot Limit")
        contents = contents.replace("'PLO ", "'PLO5 ")
        path = directory / original.name.replace("_plo_", "_plo5_")
        path.write_text(contents, encoding="utf-8")
        paths.append(path)
    return paths


__all__ = ["HERO_NAME", "PLO_DIR", "PLO_GAME", "build_config", "five_card_files", "plo_files"]
