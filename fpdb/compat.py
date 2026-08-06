"""Standard-library shims for the Python the packaged builds actually run.

`requires-python` says >=3.11, but the frozen binaries do not run on it:
PyOxidizer 0.24 cannot link CPython 3.11+ and embeds 3.10.14 (see
pyoxidizer.bzl). Anything the source takes from 3.11 needs a fallback, and it
belongs here rather than copied into each module that wants it -- one
definition, one place where the lint exception has to be justified.

`fpdb` is the lower layer: `fpdb_3_legacy` imports from it and never the
reverse, so both packages can rely on this module.

The branch tests `sys.version_info` rather than catching ImportError: type
checkers evaluate the version test and keep the real stdlib type. With the
try/except form Pyright takes the fallback as the declared type and then
rejects `enum.StrEnum` itself as incompatible with it.
"""

from __future__ import annotations

import sys

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from enum import Enum

    class StrEnum(str, Enum):
        """`enum.StrEnum` for Python 3.10.

        Mixing `str` into an `Enum` is what 3.11 made a builtin; on 3.10 it is
        still how you get members that compare and format as their value.
        """

        def __str__(self) -> str:
            return str(self.value)


__all__ = ["StrEnum"]
