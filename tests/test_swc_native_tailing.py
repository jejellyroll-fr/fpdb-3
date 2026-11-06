"""Incremental tailing of the live SwC native capture archive.

The archive is appended to while the client plays, which breaks two assumptions
a one-shot reader can make. Its tail is routinely a half-written record, and it
grows for the whole session — so re-reading it from byte zero on every poll
re-parses everything read so far.

These tests pin both behaviours, plus the fact that a poll actually yields the
hands it decoded: the original tailing test only asserted that the thread
stopped cleanly, so the entire decode path could be deleted without failing it.
"""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from fpdb_3_legacy.swc_native_capture import read_records_since

HEADER = struct.Struct("=IHBBHHIQ")


def _record(payload: bytes = b"game-state", *, direction: int = 0, port: int = 20013) -> bytes:
    return HEADER.pack(0x53574354, 1, direction, 0, port, 0, len(payload), 1_750_000_000_123_456) + payload


class TestIncrementalReads:
    def test_a_first_read_returns_every_record(self, tmp_path: Path) -> None:
        archive = tmp_path / "swc-native.raw"
        archive.write_bytes(_record(b"one") + _record(b"two"))

        records, offset = read_records_since(archive, 0)

        assert [r.payload for r in records] == [b"one", b"two"]
        assert offset == archive.stat().st_size

    def test_a_second_read_returns_only_what_was_appended(self, tmp_path: Path) -> None:
        """The whole point: a poll must not re-parse the session so far."""
        archive = tmp_path / "swc-native.raw"
        archive.write_bytes(_record(b"one"))
        _, offset = read_records_since(archive, 0)

        with archive.open("ab") as handle:
            handle.write(_record(b"two"))
        records, offset = read_records_since(archive, offset)

        assert [r.payload for r in records] == [b"two"]
        assert offset == archive.stat().st_size

    def test_nothing_new_yields_nothing(self, tmp_path: Path) -> None:
        archive = tmp_path / "swc-native.raw"
        archive.write_bytes(_record(b"one"))
        _, offset = read_records_since(archive, 0)

        records, second_offset = read_records_since(archive, offset)

        assert records == []
        assert second_offset == offset

    def test_a_missing_archive_is_not_an_error(self, tmp_path: Path) -> None:
        records, offset = read_records_since(tmp_path / "absent.raw", 0)

        assert records == []
        assert offset == 0


class TestPartialRecords:
    def test_a_half_written_header_does_not_lose_the_complete_records(self, tmp_path: Path) -> None:
        """Raising here would discard every hand decoded in the same pass."""
        archive = tmp_path / "swc-native.raw"
        archive.write_bytes(_record(b"complete") + HEADER.pack(0x53574354, 1, 0, 0, 20013, 0, 99, 0)[:6])

        records, offset = read_records_since(archive, 0)

        assert [r.payload for r in records] == [b"complete"]
        assert offset == len(_record(b"complete"))

    def test_a_half_written_payload_does_not_lose_the_complete_records(self, tmp_path: Path) -> None:
        archive = tmp_path / "swc-native.raw"
        truncated = _record(b"incoming-payload")[:-4]
        archive.write_bytes(_record(b"complete") + truncated)

        records, offset = read_records_since(archive, 0)

        assert [r.payload for r in records] == [b"complete"]
        assert offset == len(_record(b"complete"))

    def test_the_rest_of_a_partial_record_is_read_once_it_lands(self, tmp_path: Path) -> None:
        archive = tmp_path / "swc-native.raw"
        full = _record(b"later")
        archive.write_bytes(full[:5])
        records, offset = read_records_since(archive, 0)
        assert records == []

        archive.write_bytes(full)
        records, _ = read_records_since(archive, offset)

        assert [r.payload for r in records] == [b"later"]

    def test_a_corrupt_header_still_raises(self, tmp_path: Path) -> None:
        """A bad magic is corruption, not a partial write, and must not pass silently."""
        archive = tmp_path / "swc-native.raw"
        archive.write_bytes(HEADER.pack(0xDEADBEEF, 1, 0, 0, 20013, 0, 4, 0) + b"junk")

        with pytest.raises(ValueError, match="invalid SwC native capture header"):
            read_records_since(archive, 0)


class TestRotation:
    def test_a_truncated_archive_restarts_from_the_beginning(self, tmp_path: Path) -> None:
        archive = tmp_path / "swc-native.raw"
        archive.write_bytes(_record(b"one") + _record(b"two"))
        _, offset = read_records_since(archive, 0)

        archive.write_bytes(_record(b"fresh"))  # rewritten, now shorter
        records, new_offset = read_records_since(archive, offset)

        assert [r.payload for r in records] == [b"fresh"]
        assert new_offset == archive.stat().st_size
