#!/usr/bin/env python3
"""Cross-platform native packet capture for CoinPoker (libpcap / Npcap via ctypes).

No external Python dependency: binds the system capture library directly.

- Linux:   libpcap (``libpcap.so``); capture device "any" works.
- macOS:   libpcap (``libpcap.dylib``), ships with the OS.
- Windows: Npcap (``wpcap.dll``) -- install Npcap; its API is libpcap-compatible.

Live capture needs privileges (root / Administrator / BPF access), like any
sniffer. Reading a saved capture file (``open_offline``) does not. TCP sequence
numbers come straight from the packet bytes, so they are always absolute.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import sys
from collections.abc import Callable, Iterator

# --- library loading ----------------------------------------------------------


def _load_pcap() -> ctypes.CDLL:
    candidates: list[str] = []
    if sys.platform == "win32":
        candidates = ["wpcap.dll", r"C:\Windows\System32\Npcap\wpcap.dll", "wpcap"]
    else:
        found = ctypes.util.find_library("pcap")
        candidates = [c for c in (found, "libpcap.so.1", "libpcap.so", "libpcap.dylib") if c]
    for name in candidates:
        try:
            return ctypes.CDLL(name)  # libpcap and Npcap both use the cdecl ABI
        except OSError:
            continue
    hint = "Npcap (https://npcap.com)" if sys.platform == "win32" else "libpcap"
    raise OSError(f"Packet capture library not found. Install {hint}.")


class _timeval(ctypes.Structure):
    _fields_ = [("tv_sec", ctypes.c_long), ("tv_usec", ctypes.c_long)]


class _pkthdr(ctypes.Structure):
    _fields_ = [("ts", _timeval), ("caplen", ctypes.c_uint32), ("len", ctypes.c_uint32)]


class _bpf_program(ctypes.Structure):
    _fields_ = [("bf_len", ctypes.c_uint), ("bf_insns", ctypes.c_void_p)]


class _pcap_if(ctypes.Structure):
    pass


_pcap_if._fields_ = [
    ("next", ctypes.POINTER(_pcap_if)),
    ("name", ctypes.c_char_p),
    ("description", ctypes.c_char_p),
    ("addresses", ctypes.c_void_p),
    ("flags", ctypes.c_uint),
]

_PCAP_IF_LOOPBACK = 0x1
_PCAP_IF_UP = 0x2
_PCAP_IF_RUNNING = 0x4
_PCAP_NETMASK_UNKNOWN = 0xFFFFFFFF


def _bind(lib: ctypes.CDLL) -> None:
    lib.pcap_open_live.restype = ctypes.c_void_p
    lib.pcap_open_live.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_char_p]
    lib.pcap_open_offline.restype = ctypes.c_void_p
    lib.pcap_open_offline.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    lib.pcap_compile.argtypes = [ctypes.c_void_p, ctypes.POINTER(_bpf_program), ctypes.c_char_p, ctypes.c_int, ctypes.c_uint]
    lib.pcap_setfilter.argtypes = [ctypes.c_void_p, ctypes.POINTER(_bpf_program)]
    lib.pcap_datalink.argtypes = [ctypes.c_void_p]
    lib.pcap_datalink.restype = ctypes.c_int
    lib.pcap_next_ex.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.POINTER(_pkthdr)),
        ctypes.POINTER(ctypes.POINTER(ctypes.c_ubyte)),
    ]
    lib.pcap_next_ex.restype = ctypes.c_int
    lib.pcap_geterr.argtypes = [ctypes.c_void_p]
    lib.pcap_geterr.restype = ctypes.c_char_p
    lib.pcap_close.argtypes = [ctypes.c_void_p]
    lib.pcap_findalldevs.argtypes = [ctypes.POINTER(ctypes.POINTER(_pcap_if)), ctypes.c_char_p]
    lib.pcap_freealldevs.argtypes = [ctypes.POINTER(_pcap_if)]


# --- link-layer / IP / TCP parsing (pure, unit-testable) ----------------------

# DLT link-header sizes we handle. EN10MB is resolved dynamically for VLAN tags.
_DLT_EN10MB = 1
_DLT_NULL = 0
_DLT_LOOP = 108
_DLT_RAW = (12, 14, 101)
_DLT_LINUX_SLL = 113
_DLT_LINUX_SLL2 = 276


def _l3_offset(pkt: bytes, dlt: int) -> int:
    if dlt == _DLT_EN10MB:
        if len(pkt) < 14:
            return -1
        ethertype = int.from_bytes(pkt[12:14], "big")
        off = 14
        while ethertype == 0x8100 and len(pkt) >= off + 4:  # 802.1Q VLAN tag
            ethertype = int.from_bytes(pkt[off + 2 : off + 4], "big")
            off += 4
        return off
    if dlt in (_DLT_NULL, _DLT_LOOP):
        return 4
    if dlt == _DLT_LINUX_SLL:
        return 16
    if dlt == _DLT_LINUX_SLL2:
        return 20
    if dlt in _DLT_RAW:
        return 0
    return 14  # best-effort default (assume Ethernet)


def parse_segment(pkt: bytes, dlt: int) -> tuple[int, int, int, bytes] | None:
    """Return (src_port, dst_port, seq, payload) for a TCP packet, else None."""
    off = _l3_offset(pkt, dlt)
    if off < 0 or off + 20 > len(pkt):
        return None
    version = pkt[off] >> 4
    if version == 6:
        if pkt[off + 6] != 6:  # next header must be TCP (no extension headers)
            return None
        l4 = off + 40
    elif version == 4:
        ihl = (pkt[off] & 0x0F) * 4
        if pkt[off + 9] != 6:
            return None
        l4 = off + ihl
    else:
        return None
    if l4 + 20 > len(pkt):
        return None
    src_port = int.from_bytes(pkt[l4 : l4 + 2], "big")
    dst_port = int.from_bytes(pkt[l4 + 2 : l4 + 4], "big")
    seq = int.from_bytes(pkt[l4 + 4 : l4 + 8], "big")
    data_off = (pkt[l4 + 12] >> 4) * 4
    payload = pkt[l4 + data_off :]
    return src_port, dst_port, seq, payload


# --- device discovery ---------------------------------------------------------


def list_devices() -> list[tuple[str, str, int]]:
    """Return [(name, description, flags)] for available capture devices."""
    lib = _load_pcap()
    _bind(lib)
    alldevs = ctypes.POINTER(_pcap_if)()
    errbuf = ctypes.create_string_buffer(256)
    if lib.pcap_findalldevs(ctypes.byref(alldevs), errbuf) != 0:
        raise OSError(errbuf.value.decode() or "pcap_findalldevs failed")
    devices = []
    node = alldevs
    while node:
        cur = node.contents
        devices.append(
            (
                cur.name.decode() if cur.name else "",
                cur.description.decode() if cur.description else "",
                int(cur.flags),
            ),
        )
        node = cur.next
    lib.pcap_freealldevs(alldevs)
    return devices


# Interface name prefixes that are virtual/secondary (VPN, AirDrop, bridges,
# hotspot, container) and almost never carry the real internet route.
_VIRTUAL_PREFIXES = (
    "lo", "ap", "awdl", "llw", "utun", "bridge", "p2p", "gif", "stf", "xhc",
    "vmnet", "vnic", "tun", "tap", "docker", "veth", "ppp", "anpi",
)


def default_device() -> str:
    """Pick a sensible capture device for the current platform.

    Prefers a physical, up-and-running interface (e.g. en0 / Ethernet / Wi-Fi)
    and skips virtual ones (VPN, AirDrop, hotspot, bridges) that would sniff no
    game traffic. The GUI lets the user override this.
    """
    if sys.platform.startswith("linux"):
        return "any"  # DLT_LINUX_SLL; captures every interface
    running_or_up = _PCAP_IF_RUNNING | _PCAP_IF_UP
    candidates = [(name, flags) for name, _desc, flags in list_devices() if not (flags & _PCAP_IF_LOOPBACK)]

    def _is_virtual(name: str) -> bool:
        low = name.lower()
        return any(low.startswith(prefix) for prefix in _VIRTUAL_PREFIXES)

    for name, flags in candidates:
        if flags & running_or_up and not _is_virtual(name):
            return name
    for name, flags in candidates:
        if flags & running_or_up:
            return name
    if not candidates:
        raise OSError("No capture devices found (need privileges / Npcap on Windows).")
    return candidates[0][0]


# --- capture loops ------------------------------------------------------------


def _iter_handle(lib: ctypes.CDLL, handle: int, stop: Callable[[], bool] | None) -> Iterator[tuple[int, int, int, bytes]]:
    dlt = lib.pcap_datalink(handle)
    hdr = ctypes.POINTER(_pkthdr)()
    data = ctypes.POINTER(ctypes.c_ubyte)()
    try:
        while stop is None or not stop():
            rc = lib.pcap_next_ex(handle, ctypes.byref(hdr), ctypes.byref(data))
            if rc == 1:
                caplen = hdr.contents.caplen
                pkt = bytes(bytearray(data[:caplen]))
                seg = parse_segment(pkt, dlt)
                if seg is not None:
                    yield seg
            elif rc == 0:
                continue  # live timeout
            else:
                break  # EOF (offline) or error
    finally:
        lib.pcap_close(handle)


def _compile_filter(lib: ctypes.CDLL, handle: int, bpf: str) -> None:
    if not bpf:
        return
    prog = _bpf_program()
    if lib.pcap_compile(handle, ctypes.byref(prog), bpf.encode(), 1, _PCAP_NETMASK_UNKNOWN) != 0:
        raise OSError(lib.pcap_geterr(handle).decode())
    if lib.pcap_setfilter(handle, ctypes.byref(prog)) != 0:
        raise OSError(lib.pcap_geterr(handle).decode())


def capture_live(
    iface: str | None,
    bpf: str,
    stop: Callable[[], bool] | None = None,
) -> Iterator[tuple[int, int, int, bytes]]:
    """Yield (src_port, dst_port, seq, payload) for each TCP packet on ``iface``."""
    lib = _load_pcap()
    _bind(lib)
    device = (iface or default_device()).encode()
    errbuf = ctypes.create_string_buffer(256)
    handle = lib.pcap_open_live(device, 262144, 0, 100, errbuf)  # snaplen 256K, no promisc, 100ms
    if not handle:
        raise OSError(errbuf.value.decode() or "pcap_open_live failed (need privileges?)")
    _compile_filter(lib, handle, bpf)
    yield from _iter_handle(lib, handle, stop)


def open_offline(path: str, bpf: str = "") -> Iterator[tuple[int, int, int, bytes]]:
    """Yield (src_port, dst_port, seq, payload) from a saved pcap/pcapng file."""
    lib = _load_pcap()
    _bind(lib)
    errbuf = ctypes.create_string_buffer(256)
    handle = lib.pcap_open_offline(path.encode(), errbuf)
    if not handle:
        raise OSError(errbuf.value.decode() or f"cannot open {path}")
    _compile_filter(lib, handle, bpf)
    yield from _iter_handle(lib, handle, None)
