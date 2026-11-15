#!/usr/bin/env python3
"""Can fpdb read hands straight from a PokerTracker 4 database? The #615 probe.

PT4 keeps the text of every hand it imported in ``cash_hand_histories`` and
``tourney_hand_histories``. This script answers the spike's three questions on a
real database, without writing to it:

1. what those tables hold: their columns and types, and whether the text is the
   room's own hand history or an encoded form;
2. whether fpdb's room parsers read it unchanged: a sample of each room's hands
   goes through ``IdentifySite`` and the room's parser, as a bulk import would;
3. how fast: every stored history is streamed once, and the sample's parse rate
   is measured.

The connection is ``pt4_adapter.connect_pt4``'s: the server refuses any write
on it. The password comes from ``PT4_PASSWORD``, or is asked for when that is
not set; it is never read from PT4's own settings. Parsing uses a copy of the
repository's ``HUD_config.xml`` in a temporary folder, and no fpdb database is
opened.

The report printed on stdout holds counts, rates and the masked start of each
room's first line, never a player name or a hand, so it can be pasted into an
issue. ``--details`` writes the parsers' error messages to a local file; those
can name players.

Usage::

    python tools/pt4_db_probe.py [--per-room 200] [--details probe.json]
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import shutil
import sys
import tempfile
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

KINDS = ("cash", "tourney")
HISTORY_COLUMN = "history"
TEXT_TYPES = {"text", "character varying", "bytea"}
_DIGITS = re.compile(r"\d")
_HEAD_CHARS = 40
# Fixed statements, one per table: nothing is composed into the SQL at run time.
_STREAM = {
    "cash": "SELECT history FROM cash_hand_histories",
    "tourney": "SELECT history FROM tourney_hand_histories",
}
_ROOM_COUNTS = {
    "cash": (
        "SELECT s.site_name, count(*) FROM cash_hand_summary h "
        "JOIN lookup_sites s ON s.id_site = h.id_site GROUP BY s.site_name"
    ),
    "tourney": (
        "SELECT s.site_name, count(*) FROM tourney_hand_summary h "
        "JOIN lookup_sites s ON s.id_site = h.id_site GROUP BY s.site_name"
    ),
}
_ROOM_SAMPLES = {
    "cash": (
        "SELECT site_name, hand_no, history FROM ("
        " SELECT s.site_name, h.hand_no, x.history,"
        "  row_number() OVER (PARTITION BY h.id_site ORDER BY random()) AS pick"
        " FROM cash_hand_histories x"
        " JOIN cash_hand_summary h ON h.id_hand = x.id_hand"
        " JOIN lookup_sites s ON s.id_site = h.id_site"
        ") picked WHERE pick <= %s ORDER BY site_name"
    ),
    "tourney": (
        "SELECT site_name, hand_no, history FROM ("
        " SELECT s.site_name, h.hand_no, x.history,"
        "  row_number() OVER (PARTITION BY h.id_site ORDER BY random()) AS pick"
        " FROM tourney_hand_histories x"
        " JOIN tourney_hand_summary h ON h.id_hand = x.id_hand"
        " JOIN lookup_sites s ON s.id_site = h.id_site"
        ") picked WHERE pick <= %s ORDER BY site_name"
    ),
}
# A hand starts again after a blank line or two in every room's own files.
HAND_SEPARATOR = "\n\n\n"


@dataclass
class Column:
    name: str
    type: str


@dataclass
class Stream:
    """Every history of one table, read once."""

    rows: int = 0
    chars: int = 0
    seconds: float = 0.0

    @property
    def rows_per_second(self) -> float:
        return self.rows / self.seconds if self.seconds else 0.0


@dataclass
class RoomSample:  # pylint: disable=too-many-instance-attributes
    """What fpdb made of a sample of one room's stored histories: one report row."""

    kind: str
    room: str
    hands_in_db: int
    sampled: int = 0
    heads: Counter[str] = field(default_factory=Counter)
    identified_as: str | None = None
    parser: str | None = None
    parsed: int = 0
    partial: int = 0
    errors: int = 0
    skipped: int = 0
    same_hand_no: int = 0
    parse_seconds: float = 0.0
    messages: list[str] = field(default_factory=list)

    @property
    def read_rate(self) -> float:
        return self.parsed / self.sampled if self.sampled else 0.0


def masked_head(history: str) -> str:
    """The start of a hand's first line with every digit as 9: its shape, not its numbers."""
    for line in history.lstrip("﻿").splitlines():
        if line.strip():
            return _DIGITS.sub("9", line.strip()[:_HEAD_CHARS].rstrip())
    return ""


def pick_history_column(columns: Sequence[Column]) -> Column | None:
    """``history`` when the table has it, else its first text-like column besides the keys."""
    by_name = {column.name: column for column in columns}
    if HISTORY_COLUMN in by_name:
        return by_name[HISTORY_COLUMN]
    return next(
        (column for column in columns if column.type in TEXT_TYPES and not column.name.startswith("id_")),
        None,
    )


def as_text(value: Any) -> str:
    """A history as text; a ``bytea`` column comes back as bytes."""
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


def encoding_signature(value: Any) -> str:
    """How a stored history is encoded, from its first bytes."""
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, str):
        return "text"
    if not value:
        return "empty"
    if value[:2] == b"\x1f\x8b":
        return "gzip"
    if value[:1] == b"\x78":
        return "zlib"
    try:
        value.decode("utf-8")
    except UnicodeDecodeError:
        return "binary"
    return "utf-8 bytes"


# --- the PT4 side: read only --------------------------------------------------


def table_columns(conn: Any, table: str) -> list[Column]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s ORDER BY ordinal_position",
            (table,),
        )
        return [Column(name, kind) for name, kind in cur.fetchall()]


def stream_all(conn: Any, kind: str) -> Stream:
    """Read every history of one kind through a server-side cursor, as an importer would."""
    stream = Stream()
    start = perf_counter()
    with conn.transaction(), conn.cursor(name=f"pt4_probe_{kind}") as cur:
        cur.itersize = 2000
        cur.execute(_STREAM[kind])
        for (value,) in cur:
            stream.rows += 1
            stream.chars += len(as_text(value))
    stream.seconds = perf_counter() - start
    return stream


def sample_rooms(conn: Any, kind: str, per_room: int) -> tuple[dict[str, int], list[tuple]]:
    """Each room's hand count, and up to ``per_room`` random hands of each: (room, hand_no, history)."""
    with conn.cursor() as cur:
        cur.execute(_ROOM_COUNTS[kind])
        counts = {str(room): int(n) for room, n in cur.fetchall()}
        cur.execute(_ROOM_SAMPLES[kind], (per_room,))
        return counts, list(cur.fetchall())


# --- the fpdb side: parse only ------------------------------------------------


def probe_config(workdir: Path) -> Any:
    """A configuration read from a copy of the repository's HUD_config.xml: the user's is never touched."""
    from fpdb_3_legacy.Configuration import Config

    config_file = workdir / "HUD_config.xml"
    shutil.copyfile(REPO / "HUD_config.xml", config_file)
    return Config(file=str(config_file))


def parse_room(config: Any, sample: RoomSample, rows: Iterable[tuple], workdir: Path) -> RoomSample:
    """Write one room's sampled histories to a file and read it as a bulk import would."""
    from fpdb_3_legacy.IdentifySite import IdentifySite
    from fpdb_3_legacy.iPoker.dispatcher import get_parser_class_for_path as ipoker_parser_for
    from fpdb_3_legacy.parser_registry import get_parser_class

    hand_nos: set[str] = set()
    texts: list[str] = []
    for _room, hand_no, value in rows:
        text = as_text(value).strip("﻿\r\n ")
        if not text:
            continue
        texts.append(text)
        hand_nos.add(str(hand_no))
        sample.heads[masked_head(text)] += 1
    sample.sampled = len(texts)
    if not texts:
        return sample

    path = workdir / f"{sample.kind}-{re.sub(r'[^A-Za-z0-9]+', '_', sample.room)}.txt"
    path.write_text(HAND_SEPARATOR.join(texts) + "\n", encoding="utf-8")

    identifier = IdentifySite(config)
    identifier.processFile(str(path))
    found = identifier.get_fobj(str(path))
    site = getattr(found, "site", None) if found else None
    if site is None:
        sample.messages.append("no parser recognises these histories")
        return sample
    sample.identified_as = site.name
    parser_class = get_parser_class(site.filter_name)
    if site.filter_name == "iPoker":
        parser_class = ipoker_parser_for(str(path))
    sample.parser = parser_class.__name__

    start = perf_counter()
    try:
        hhc = parser_class(
            config,
            in_path=str(path),
            index=0,
            autostart=False,
            starsArchive=bool(found.archive),
            ftpArchive=bool(found.archive),
            sitename=site.name,
        )
        hhc.start()
    except Exception as exc:  # noqa: BLE001 -- a probe reports every failure, whatever its type
        sample.parse_seconds = perf_counter() - start
        sample.messages.append(f"parser stopped: {type(exc).__name__}: {exc}")
        return sample
    sample.parse_seconds = perf_counter() - start
    hands = list(hhc.getProcessedHands())
    sample.partial = hhc.numPartial
    sample.errors = hhc.numErrors
    sample.skipped = getattr(hhc, "numSkipped", 0)
    sample.parsed = len(hands)
    sample.same_hand_no = sum(1 for hand in hands if str(getattr(hand, "handid", "")) in hand_nos)
    sample.messages.extend(hhc.parsing_issues)
    return sample


# --- the report -----------------------------------------------------------------


def format_report(
    columns: dict[str, list[Column]],
    encodings: dict[str, Counter[str]],
    streams: dict[str, Stream],
    samples: Sequence[RoomSample],
) -> str:
    lines = ["## PT4 database probe (#615)", "", "### Tables", ""]
    for table, cols in columns.items():
        described = ", ".join(f"`{c.name}` {c.type}" for c in cols) or "missing"
        lines.append(f"- `{table}`: {described}")
        if encodings.get(table):
            found = ", ".join(f"{kind} x{n}" for kind, n in encodings[table].most_common())
            lines.append(f"  - stored as: {found}")
    lines += ["", "### Reading every history once", ""]
    for table, stream in streams.items():
        lines.append(
            f"- `{table}`: {stream.rows:,} rows, {stream.chars / 1e6:.1f} M chars "
            f"in {stream.seconds:.1f} s ({stream.rows_per_second:,.0f} rows/s)",
        )
    lines += [
        "",
        "### Parsing a sample of each room",
        "",
        "| kind | room | hands in PT4 | sampled | identified as | parser | read | partial | errors"
        " | same hand no | hands/s | first line |",
        "|---|---|---:|---:|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for s in samples:
        rate = s.parsed / s.parse_seconds if s.parse_seconds else 0.0
        head = " / ".join(f"`{h}`" for h, _n in s.heads.most_common(2))
        lines.append(
            f"| {s.kind} | {s.room} | {s.hands_in_db:,} | {s.sampled} | {s.identified_as or '-'}"
            f" | {s.parser or '-'} | {s.parsed} ({s.read_rate:.0%}) | {s.partial} | {s.errors}"
            f" | {s.same_hand_no} | {rate:,.0f} | {head} |",
        )
    total_sampled = sum(s.sampled for s in samples)
    total_read = sum(s.parsed for s in samples)
    weighted = sum(s.hands_in_db * s.read_rate for s in samples)
    in_db = sum(s.hands_in_db for s in samples)
    lines += [
        "",
        f"Sample: {total_read:,} of {total_sampled:,} hands read ({total_read / total_sampled:.1%})."
        if total_sampled
        else "Sample: none.",
        f"Weighted by each room's share of the database: {weighted / in_db:.1%} of {in_db:,} hands." if in_db else "",
    ]
    return "\n".join(lines).rstrip() + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--per-room", type=int, default=200, help="hands sampled per room and kind (default 200)")
    parser.add_argument("--details", type=Path, help="write per-room parser messages here (may name players)")
    parser.add_argument("--no-stream", action="store_true", help="skip reading every history once")
    args = parser.parse_args(argv)

    from fpdb_3_legacy.pt4_adapter import Pt4Config, connect_pt4

    config = Pt4Config.from_env()
    if "PT4_PASSWORD" not in os.environ:
        config.password = getpass.getpass(f"Password for {config.user}@{config.host}:{config.port}/{config.database}: ")
    conn = connect_pt4(config)

    columns: dict[str, list[Column]] = {}
    encodings: dict[str, Counter[str]] = {}
    streams: dict[str, Stream] = {}
    samples: list[RoomSample] = []
    with tempfile.TemporaryDirectory(prefix="fpdb-pt4-probe-", ignore_cleanup_errors=True) as root:
        workdir = Path(root)
        fpdb_config = probe_config(workdir)
        for kind in KINDS:
            table = f"{kind}_hand_histories"
            columns[table] = table_columns(conn, table)
            column = pick_history_column(columns[table])
            if column is None or column.name != HISTORY_COLUMN:
                # The report's column list shows where the text is; the reads below expect ``history``.
                print(f"{table} has no {HISTORY_COLUMN} column: not read", file=sys.stderr)
                continue
            if not args.no_stream:
                print(f"reading every row of {table}...", file=sys.stderr)
                streams[table] = stream_all(conn, kind)
            print(f"sampling {table}...", file=sys.stderr)
            counts, rows = sample_rooms(conn, kind, args.per_room)
            encodings[table] = Counter(encoding_signature(value) for _r, _n, value in rows)
            by_room: dict[str, list[tuple]] = {}
            for row in rows:
                by_room.setdefault(str(row[0]), []).append(row)
            for room, hands in sorted(counts.items(), key=lambda item: -item[1]):
                print(f"  parsing {kind} {room}...", file=sys.stderr)
                sample = RoomSample(kind, room, hands)
                samples.append(parse_room(fpdb_config, sample, by_room.get(room, []), workdir))
    conn.close()

    print(format_report(columns, encodings, streams, samples))
    if args.details:
        details = [{**asdict(s), "heads": dict(s.heads)} for s in samples]
        args.details.write_text(json.dumps(details, indent=2, default=str), encoding="utf-8")
        print(f"details: {args.details}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
