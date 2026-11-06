"""The deterministic tournament corpus behind the MTT study pack (#369).

Fourteen nine-max PokerStars tournament hands at 500/1000, no antes and no
rake, so every pot in the files is exact arithmetic. The seats keep one role
throughout, as in the Hold'em cash corpus: seat 3 Cara is always the button,
seat 2 Boris is the cutoff and the recorded hero, seat 6 Frank is under the
gun, seat 4 Dave the small blind and seat 5 Erin the big blind.

What varies here is the thing the pack is about: the stacks. The hands are
dealt at seven different depths so that every band of the default table is
populated -- a nine-big-blind shove, a twelve-blind open, a twenty-blind call,
and single-raised pots at thirty-five, fifty, eighty and a hundred and fifty
blinds. Between them the hands reach every family the pack ships: first in,
facing an open, the opener facing a 3-bet, blind defence, facing an all-in,
shoving, and single-raised pots from the raiser's and the defender's seat
including a turn barrel.

Nothing in the corpus carries stage or payout information, because fpdb does
not store any: these are tournament hands, not bubble hands.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from tests.helpers.analytics_golden import build_config

MTT_DIR: Final[Path] = Path(__file__).resolve().parents[1] / "fixtures" / "analytics" / "mtt"

#: The recorded hero, so a test can name a side rather than guess one.
HERO_NAME: Final[str] = "Boris"

#: The big blind every hand is played at, in chips.
BIG_BLIND: Final[int] = 1000


def mtt_files() -> list[Path]:
    """Every corpus file, in the order their hand numbers run."""
    return sorted(MTT_DIR.glob("*.txt"))


__all__ = ["BIG_BLIND", "HERO_NAME", "MTT_DIR", "build_config", "mtt_files"]
