#!/usr/bin/env python3
"""Decoder for CoinPoker's TCP game protocol (poker-nlb.coinpoker.ai:9000/7002).

CoinPoker's poker traffic is a plaintext, self-describing binary protocol on a
raw TCP socket (opened by the Electron main process, so it is invisible to the
renderer's DevTools/WebSocket capture). This module decodes it.

Wire format
-----------
Frames::  [flags:u8][length:u16][payload:length]
    flags & 0x20  -> payload is zlib-compressed
    payload is a TLV value whose first byte is its type.

TLV value types observed::
    0x02  u8
    0x03  u16 (big-endian)
    0x04  u32
    0x05  u64
    0x08  string, u16 length prefix
    0x0a  string, u32 length prefix (large; often a JSON blob)
    0x12  map: [count:u16] then count * ([klen:u16][key][valtype:u8][value])
    0x13  array: [count:u16][elemtype:u8] then count * value

Game events arrive as envelopes ``{"p": {"p": {...,"data": <json>}, "c": <event
name>, ...}, "a": 13, ...}`` where ``c`` is a ``game.*`` event name and ``data``
is a JSON string carrying the event detail (seats, cards, actions, winners).

This module only decodes the transport; mapping events to fpdb Hand objects is
the job of a converter built on top of ``iter_game_events``.
"""

from __future__ import annotations

import json
import struct
import zlib
from collections.abc import Iterator
from typing import Any

COMPRESSED_FLAG = 0x20


def split_frames(buf: bytes) -> list[tuple[int, bytes]]:
    """Split a reassembled TCP byte stream into (flags, payload) frames."""
    frames: list[tuple[int, bytes]] = []
    i = 0
    while i + 3 <= len(buf):
        flags = buf[i]
        length = struct.unpack_from(">H", buf, i + 1)[0]
        i += 3
        payload = buf[i : i + length]
        i += length
        if len(payload) < length:
            break  # truncated tail (partial capture)
        frames.append((flags, payload))
    return frames


# Fixed-width scalar TLV types -> struct format (0x02 is a bare byte).
_SCALAR_FMT = {0x03: ">H", 0x04: ">I", 0x05: ">Q"}
# Length-prefixed string TLV types -> format of the length prefix.
_STRLEN_FMT = {0x08: ">H", 0x0A: ">I"}


def _read_map(b: bytes, off: int) -> tuple[dict[str, Any], int]:
    count = struct.unpack_from(">H", b, off)[0]
    off += 2
    out: dict[str, Any] = {}
    for _ in range(count):
        klen = struct.unpack_from(">H", b, off)[0]
        off += 2
        key = b[off : off + klen].decode("latin1")
        off += klen
        vtyp = b[off]
        off += 1
        out[key], off = _read_value(b, off, vtyp)
    return out, off


def _read_array(b: bytes, off: int) -> tuple[list[Any], int]:
    count = struct.unpack_from(">H", b, off)[0]
    off += 2
    etyp = b[off]
    off += 1
    arr = []
    for _ in range(count):
        val, off = _read_value(b, off, etyp)
        arr.append(val)
    return arr, off


def _read_value(b: bytes, off: int, typ: int) -> tuple[Any, int]:
    if typ == 0x12:  # map
        return _read_map(b, off)
    if typ == 0x13:  # array
        return _read_array(b, off)
    if typ == 0x02:  # single byte
        return b[off], off + 1
    if typ in _SCALAR_FMT:
        fmt = _SCALAR_FMT[typ]
        return struct.unpack_from(fmt, b, off)[0], off + struct.calcsize(fmt)
    if typ in _STRLEN_FMT:
        fmt = _STRLEN_FMT[typ]
        prefix = struct.calcsize(fmt)
        ln = struct.unpack_from(fmt, b, off)[0]
        off += prefix
        return b[off : off + ln].decode("latin1"), off + ln
    raise ValueError(f"unknown TLV type 0x{typ:02x} at offset {off}")


def decode_frame(flags: int, payload: bytes) -> Any:
    """Decode one frame's payload (decompressing first if flagged) into an object."""
    data = zlib.decompress(payload) if flags & COMPRESSED_FLAG else payload
    if not data:
        return None
    value, _ = _read_value(data, 1, data[0])
    return value


def iter_messages(stream: bytes) -> Iterator[Any]:
    """Yield each decodable message object from a reassembled server->client stream."""
    for flags, payload in split_frames(stream):
        try:
            obj = decode_frame(flags, payload)
        except (ValueError, zlib.error, struct.error, IndexError):
            continue
        if obj is not None:
            yield obj


def protocol_event_from_object(obj: Any) -> tuple[str, str | None, Any] | None:
    """Return any named CoinPoker protocol envelope as an event tuple."""
    if not (isinstance(obj, dict) and isinstance(obj.get("p"), dict)):
        return None
    inner = obj["p"]
    name = inner.get("c")
    if not isinstance(name, str):
        return None
    detail = inner.get("p", {})
    hand_id = detail.get("gameHandId") if isinstance(detail, dict) else None
    data: Any = detail.get("data") if isinstance(detail, dict) else None
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (ValueError, TypeError):
            pass
    return name, hand_id, data


def game_event_from_object(obj: Any) -> tuple[str, str | None, Any] | None:
    """Return a decoded ``game.*`` envelope, excluding other protocol events."""
    event = protocol_event_from_object(obj)
    if event is None or not event[0].startswith("game."):
        return None
    return event


def iter_game_events(stream: bytes) -> Iterator[tuple[str, str | None, Any]]:
    """Yield (event_name, game_hand_id, parsed_data) for each ``game.*`` event.

    ``parsed_data`` is the JSON-decoded ``data`` field when present, else the raw
    inner payload dict.
    """
    for obj in iter_messages(stream):
        event = game_event_from_object(obj)
        if event is not None:
            yield event
