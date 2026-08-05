from __future__ import annotations

from fpdb_3_legacy.iPoker.base import iPoker


class BetclicIPoker(iPoker):
    """Betclic iPoker skin parser.

    The implementation is currently inherited from the shared iPoker base; this
    class gives Betclic a dedicated extension point and test target.
    """

    sitename = "Betclic Poker"
    site_id = 131
