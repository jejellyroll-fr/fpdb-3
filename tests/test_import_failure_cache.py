"""Silencing repeated identification failures must not lose hands.

Auto-import polls every few seconds, so an unidentifiable file is examined over
and over — the flooding that #181 reported. Remembering the failure by path
alone stops the noise and creates a worse problem: the poker client creates a
hand-history file when a table opens and writes the first hand later, so a poll
landing in between sees an empty file and blacklists it. The hands written a
minute later are then never imported, and the cache that silenced the warning
silences the loss too.

The failure is therefore remembered against the file's size and mtime: an
unchanged file stays skipped, one that has been written to is read again.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from fpdb_3_legacy.import_failure_cache import (
    SIDECAR_EXTENSIONS,
    FailureCache,
    is_sidecar_file,
)


def _touch(path: Path, content: str = "") -> Path:
    path.write_text(content, encoding="utf-8")
    return path


class TestRememberingFailures:
    def test_an_unchanged_file_stays_failed(self, tmp_path: Path) -> None:
        """The point of the cache: no second warning for the same content."""
        cache = FailureCache()
        target = _touch(tmp_path / "junk.txt", "not a hand history")
        cache.remember(target)

        assert cache.failed(target)
        assert target in cache

    def test_an_unknown_file_has_not_failed(self, tmp_path: Path) -> None:
        assert not FailureCache().failed(tmp_path / "never-seen.txt")

    def test_a_file_written_to_is_examined_again(self, tmp_path: Path) -> None:
        """The regression: an empty file must not be condemned for good."""
        cache = FailureCache()
        target = _touch(tmp_path / "HH20260806.txt")
        cache.remember(target)
        assert cache.failed(target)

        _touch(target, "PokerStars Hand #1: Hold'em No Limit")

        assert not cache.failed(target)

    def test_a_file_that_only_grew_is_examined_again(self, tmp_path: Path) -> None:
        """A client appending the next hand changes size even within one mtime tick."""
        cache = FailureCache()
        target = _touch(tmp_path / "HH20260806.txt", "partial")
        cache.remember(target)

        with target.open("a", encoding="utf-8") as handle:
            handle.write(" ...and the rest of the hand")

        assert not cache.failed(target)

    def test_a_second_failure_re_arms_the_cache(self, tmp_path: Path) -> None:
        cache = FailureCache()
        target = _touch(tmp_path / "junk.txt", "one")
        cache.remember(target)
        _touch(target, "two")
        assert not cache.failed(target)

        cache.remember(target)

        assert cache.failed(target)

    def test_a_deleted_file_does_not_raise(self, tmp_path: Path) -> None:
        cache = FailureCache()
        target = _touch(tmp_path / "junk.txt", "gone soon")
        cache.remember(target)
        os.unlink(target)

        assert cache.failed(target) in (True, False)  # must not raise


class TestSetInterface:
    """It stands where a plain set used to, so existing callers keep working."""

    def test_discard_forgets_the_file(self, tmp_path: Path) -> None:
        cache = FailureCache()
        target = _touch(tmp_path / "junk.txt", "x")
        cache.remember(target)

        cache.discard(target)

        assert not cache.failed(target)

    def test_clear_forgets_everything(self, tmp_path: Path) -> None:
        cache = FailureCache()
        for name in ("a.txt", "b.txt"):
            cache.remember(_touch(tmp_path / name, "x"))

        cache.clear()

        assert len(cache) == 0

    def test_iteration_yields_the_remembered_paths(self, tmp_path: Path) -> None:
        cache = FailureCache()
        first = _touch(tmp_path / "a.txt", "x")
        second = _touch(tmp_path / "b.txt", "x")
        cache.remember(first)
        cache.remember(second)

        assert sorted(str(path) for path in cache) == sorted([str(first), str(second)])

    def test_iterating_while_discarding_is_safe(self, tmp_path: Path) -> None:
        """removeImportDirectory discards as it walks the cache."""
        cache = FailureCache()
        for name in ("a.txt", "b.txt", "c.txt"):
            cache.remember(_touch(tmp_path / name, "x"))

        for path in cache:
            cache.discard(path)

        assert len(cache) == 0


class TestSidecarRecognition:
    def test_reference_data_is_a_sidecar(self, tmp_path: Path) -> None:
        for extension in SIDECAR_EXTENSIONS:
            assert is_sidecar_file(str(tmp_path / f"hand.txt{extension}"))

    def test_system_leftovers_are_sidecars(self, tmp_path: Path) -> None:
        assert is_sidecar_file(str(tmp_path / ".DS_Store"))

    def test_a_hand_history_is_not_a_sidecar(self, tmp_path: Path) -> None:
        assert not is_sidecar_file(str(tmp_path / "HH20260806 T1.txt"))

    def test_bytes_paths_are_accepted(self, tmp_path: Path) -> None:
        assert is_sidecar_file(os.fsencode(str(tmp_path / "hand.txt.hp")))


def test_the_cache_does_not_depend_on_clock_resolution(tmp_path: Path) -> None:
    """Two writes inside one mtime tick still differ, because size is part of it."""
    cache = FailureCache()
    target = _touch(tmp_path / "HH.txt", "a")
    cache.remember(target)
    _touch(target, "ab")
    first = cache.failed(target)

    cache.remember(target)
    time.sleep(0.01)
    _touch(target, "abc")

    assert first is False
    assert cache.failed(target) is False


class TestIdentifySiteWiring:
    """The reported scenario, end to end through the identifier."""

    @staticmethod
    def _identifier():
        from fpdb_3_legacy import IdentifySite
        from fpdb_3_legacy.Configuration import Config

        return IdentifySite.IdentifySite(Config())

    @staticmethod
    def _a_real_hand_history() -> str:
        source = Path(__file__).resolve().parents[1] / "regression-test-files" / "cash" / "Stars" / "Flop"
        return next(source.glob("*.txt")).read_text(encoding="utf-8", errors="replace")

    def test_a_file_polled_while_empty_is_still_imported_once_written(self, tmp_path: Path) -> None:
        """Caching by path alone lost these hands for the rest of the session."""
        identifier = self._identifier()
        history = _touch(tmp_path / "HH20260806 T1.txt")

        identifier.processFile(str(history))
        assert str(history) not in identifier.filelist

        _touch(history, self._a_real_hand_history())
        identifier.processFile(str(history))

        assert str(history) in identifier.filelist

    def test_an_empty_file_is_not_re_read_until_it_changes(self, tmp_path: Path) -> None:
        """Without this the log floods again, which is what #181 was about."""
        identifier = self._identifier()
        history = _touch(tmp_path / "HH20260806 T2.txt")
        identifier.processFile(str(history))

        assert identifier.identification_failed(str(history))
