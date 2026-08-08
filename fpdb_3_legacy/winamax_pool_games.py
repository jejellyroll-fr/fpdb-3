"""Remember which game a Winamax Fast-Fold pool deals.

Why this exists
---------------
A Fast-Fold HUD is built from the client log the moment a hand starts, long
before that hand is imported. Everything it needs comes from the log or the
window title except one thing: the game. That is written only in the header the
client draws inside the table, which can be read solely through the macOS
accessibility API -- and a packaged build is a fresh TCC client that macOS never
prompts for *Accessibility*, so in practice that header is unreadable.

The game does arrive eventually, on the first hand of the pool that gets
imported. Keeping it means the wait is paid once per pool rather than once per
hand: every later hand, and every later session, can build the HUD straight from
the log.

Pools are keyed by their display name ("Colorado", "Casablanca"), which is what
both the hand history and the window title carry.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

MAX_POOLS = 200
"""Cap on remembered pools, so a long-lived file cannot grow without bound."""


def pool_name(table_name: str) -> str:
    """The pool a table belongs to: its name without the client's window index.

    ``"Colorado 4"`` and ``"Colorado"`` are both the Colorado pool; the trailing
    number identifies which of its windows, not which game it deals. The client
    always separates it from the name, so a name that simply ends in a digit
    keeps it.
    """
    return re.sub(r"\s+\d+\s*$", "", table_name or "").strip()


class WinamaxPoolGames:
    """Pool display name -> fpdb game category, persisted between sessions."""

    def __init__(self, path: Path | None) -> None:
        self._path = path
        self._games: dict[str, str] = {}
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if self._path is None or not self._path.is_file():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            log.debug("Could not read remembered Winamax pool games from %s", self._path)
            return
        if isinstance(data, dict):
            self._games = {str(k): str(v) for k, v in data.items() if k and v}

    def get(self, table_name: str) -> str | None:
        """The game last seen at this table's pool, if one was ever imported."""
        self._load()
        return self._games.get(pool_name(table_name))

    def remember(self, table_name: str, poker_game: str) -> None:
        """Record the game an imported hand proved this pool deals."""
        name = pool_name(table_name)
        if not name or not poker_game:
            return
        self._load()
        if self._games.get(name) == poker_game:
            return
        self._games[name] = poker_game
        # Oldest first: dict preserves insertion order, and a pool that is still
        # being played is re-inserted only when its game changes, so trimming the
        # front drops the pools longest untouched.
        while len(self._games) > MAX_POOLS:
            self._games.pop(next(iter(self._games)))
        self._save()

    def _save(self) -> None:
        if self._path is None:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(self._games, indent=2, sort_keys=True), encoding="utf-8")
        except OSError:
            # Losing the file only costs one hand's delay per pool next session.
            log.debug("Could not save remembered Winamax pool games to %s", self._path)
