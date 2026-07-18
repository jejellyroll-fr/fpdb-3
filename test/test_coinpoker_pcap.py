"""Tests for the cross-platform packet parsing in ``coinpoker_pcap``.

These exercise the pure link-layer / IP / TCP parsing (no capture, no root), so
they run on any platform regardless of libpcap/Npcap being installed.
"""

from __future__ import annotations

import struct

from fpdb_3_legacy.coinpoker_pcap import _l3_offset, parse_segment

_DLT_EN10MB = 1
_DLT_LINUX_SLL = 113
_DLT_NULL = 0


def _tcp(sport: int, dport: int, seq: int, payload: bytes) -> bytes:
    # 20-byte TCP header (data offset 5), then payload.
    return struct.pack(">HHIIBBHHH", sport, dport, seq, 0, 5 << 4, 0, 0, 0, 0) + payload


def _ipv6(next_header: int, body: bytes) -> bytes:
    return struct.pack(">IHBB", 0x60000000, len(body), next_header, 64) + b"\x00" * 32 + body


def _ipv4(proto: int, body: bytes) -> bytes:
    header = struct.pack(">BBHHHBBH", 0x45, 0, 20 + len(body), 0, 0, 64, proto, 0) + b"\x00" * 8
    return header + body


def _eth(ethertype: int, body: bytes) -> bytes:
    return b"\xff" * 6 + b"\x11" * 6 + struct.pack(">H", ethertype) + body


def test_parse_ethernet_ipv6_tcp() -> None:
    pkt = _eth(0x86DD, _ipv6(6, _tcp(9000, 55291, 123456, b"hello")))
    assert parse_segment(pkt, _DLT_EN10MB) == (9000, 55291, 123456, b"hello")


def test_parse_ethernet_ipv4_tcp() -> None:
    pkt = _eth(0x0800, _ipv4(6, _tcp(7002, 40000, 42, b"\x80\x00\x01\x99")))
    assert parse_segment(pkt, _DLT_EN10MB) == (7002, 40000, 42, b"\x80\x00\x01\x99")


def test_parse_linux_cooked_sll() -> None:
    # DLT_LINUX_SLL: 16-byte cooked header, then the IP packet.
    pkt = b"\x00" * 16 + _ipv6(6, _tcp(9000, 1, 7, b"x"))
    assert parse_segment(pkt, _DLT_LINUX_SLL) == (9000, 1, 7, b"x")


def test_vlan_tag_is_skipped() -> None:
    inner = _ipv6(6, _tcp(9000, 2, 8, b"y"))
    pkt = b"\xff" * 6 + b"\x11" * 6 + struct.pack(">H", 0x8100) + b"\x00\x00" + struct.pack(">H", 0x86DD) + inner
    assert parse_segment(pkt, _DLT_EN10MB) == (9000, 2, 8, b"y")


def test_non_tcp_returns_none() -> None:
    pkt = _eth(0x86DD, _ipv6(17, b"\x00" * 8))  # next header 17 = UDP
    assert parse_segment(pkt, _DLT_EN10MB) is None


def test_truncated_returns_none() -> None:
    assert parse_segment(b"\x00" * 10, _DLT_EN10MB) is None


def test_l3_offset_for_known_dlts() -> None:
    assert _l3_offset(b"\x00" * 20, _DLT_LINUX_SLL) == 16
    assert _l3_offset(b"\x00" * 8, _DLT_NULL) == 4
    assert _l3_offset(_eth(0x86DD, b""), _DLT_EN10MB) == 14
