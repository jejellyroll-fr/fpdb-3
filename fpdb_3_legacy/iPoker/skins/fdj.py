from __future__ import annotations

from fpdb_3_legacy.iPoker.base import iPoker


class FDJIPoker(iPoker):
    """FDJ iPoker skin parser.

    The implementation is currently inherited from the shared iPoker base; this
    class gives FDJ a dedicated extension point and test target.
    """

    sitename = "FDJ Poker"
    site_id = 57
