"""Remember which files failed identification, without condemning them for good.

Auto-import polls its directories every few seconds, so a file that cannot be
identified is examined again and again — that is what flooded the log with
`siteId Failed` for the regression corpus.

Caching the failure by path alone fixes the noise and breaks the import: the
poker client creates a hand-history file when a table opens and writes the first
hand later, so a poll that arrives in between sees an empty file. Blacklisting
it by path means the hands written a minute later are never imported, and the
same cache that silenced the warning also silences the loss.

So the failure is remembered against the file's size and modification time. An
unchanged file is skipped; one that has grown is read again.

The signature does not catch a rewrite that keeps the byte count identical and
lands inside one filesystem mtime tick — coarse on Windows in particular. That
is deliberate: detecting it would mean reading the file, which is exactly the
work being avoided, and a hand history only ever grows as the client appends.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

# Reference data written beside the regression corpus: Python literals used by
# the test suite, never hand histories. Kept here so the importer and the
# identifier cannot drift apart on what counts as a sidecar.
SIDECAR_EXTENSIONS = (".hp", ".gt", ".hands")

# Files the operating system or an editor leaves behind next to real ones.
SYSTEM_FILES = (".DS_Store",)


def is_sidecar_file(path: str | bytes) -> bool:
    """True for files that sit beside hand histories and are never importable."""
    name = os.fsdecode(path)
    return name.endswith(SYSTEM_FILES) or name.endswith(SIDECAR_EXTENSIONS)


def _signature(path: str | bytes) -> tuple[int, int] | None:
    try:
        stat = os.stat(path)
    except OSError:
        return None
    return (stat.st_size, stat.st_mtime_ns)


class FailureCache:
    """Files whose identification failed, keyed by the content that failed.

    Supports ``in``, iteration and ``discard`` so it can stand where a plain set
    used to.
    """

    def __init__(self) -> None:
        self._signatures: dict[str | bytes, tuple[int, int] | None] = {}

    def remember(self, path: str | bytes) -> None:
        """Record that `path` failed as it currently stands."""
        self._signatures[path] = _signature(path)

    def failed(self, path: str | bytes) -> bool:
        """True only if `path` failed and has not changed since."""
        if path not in self._signatures:
            return False
        if self._signatures[path] != _signature(path):
            # Written to since it failed, so it deserves another read.
            del self._signatures[path]
            return False
        return True

    def discard(self, path: str | bytes) -> None:
        self._signatures.pop(path, None)

    def clear(self) -> None:
        self._signatures.clear()

    def __contains__(self, path: object) -> bool:
        return self.failed(path)  # type: ignore[arg-type]

    def __iter__(self) -> Iterator[str | bytes]:
        return iter(list(self._signatures))

    def __len__(self) -> int:
        return len(self._signatures)
