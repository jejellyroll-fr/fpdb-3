"""Standard-library shims for the Python the packaged builds actually run.

`requires-python` says >=3.11, but the frozen binaries do not run on it:
PyOxidizer 0.24 cannot link CPython 3.11+ and embeds 3.10.14 (see
pyoxidizer.bzl). Anything the source takes from 3.11 needs a fallback, and it
belongs here rather than copied into each module that wants it -- one
definition, one place where the lint exception has to be justified.

`fpdb` is the lower layer: `fpdb_3_legacy` imports from it and never the
reverse, so both packages can rely on this module.
"""

from __future__ import annotations

try:  # Python 3.11+
    from enum import StrEnum
except ImportError:  # the 3.10 embedded in packaged builds
    from enum import Enum

    class StrEnum(str, Enum):  # type: ignore[no-redef]
        """`enum.StrEnum` for Python 3.10.

        Mixing `str` into an `Enum` is what 3.11 made a builtin; on 3.10 it is
        still the way to get members that compare and format as their value.
        """

        def __str__(self) -> str:
            return str(self.value)


__all__ = ["StrEnum"]
