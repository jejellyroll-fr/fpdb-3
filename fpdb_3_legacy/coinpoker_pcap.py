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
# hotspot, container) and almost never carry the real internet route. These match
# Unix interface names (en0, utun3, docker0, ...).
_VIRTUAL_PREFIXES = (
    "lo", "ap", "awdl", "llw", "utun", "bridge", "p2p", "gif", "stf", "xhc",
    "vmnet", "vnic", "tun", "tap", "docker", "veth", "ppp", "anpi",
)

# Windows Npcap names are opaque GUIDs (\Device\NPF_{...}), so the prefixes above
# never match; the *description* is the only discriminator. These substrings flag
# the pseudo/virtual adapters (WAN miniports, VPNs, hypervisor switches, ...) that
# carry no real game traffic, so auto-detect skips them.
_VIRTUAL_DESC_KEYWORDS = (
    "wan miniport", "hyper-v", "virtual", "vmware", "virtualbox", "wireguard",
    "openvpn", "tap-", "tunnel", "vpn", "bluetooth", "loopback", "pseudo",
    "npcap loopback",
)


def default_device() -> str:
    """Pick a sensible capture device for the current platform.

    On Windows the adapter that owns the default *internet* route is used
    directly: poker traffic follows the same route as any internet host, so when
    a VPN full-tunnel is up (WireGuard/OpenVPN, common for poker) the plaintext
    game stream appears on the tunnel adapter and the physical NIC carries only
    encrypted packets. Route resolution beats any name/description guess. If it
    fails, or on macOS, fall back to preferring a physical up-and-running
    interface and skipping obviously virtual ones. The GUI lets the user
    override this.
    """
    if sys.platform.startswith("linux"):
        return "any"  # DLT_LINUX_SLL; captures every interface
    devices = list_devices()
    if sys.platform == "win32":
        route_dev = _windows_capture_device(devices)
        if route_dev:
            return route_dev
    return _heuristic_device(devices)


def _windows_capture_device(devices: list[tuple[str, str, int]]) -> str | None:
    """Return the pcap device that owns the internet route, matched in ``devices``."""
    route_dev = _windows_route_device_name()
    if not route_dev:
        return None
    for name, _desc, _flags in devices:
        if name.lower() == route_dev.lower():
            return name
    return None


def _heuristic_device(devices: list[tuple[str, str, int]]) -> str:
    """Prefer a physical, up-and-running, non-virtual interface (route-agnostic)."""
    running_or_up = _PCAP_IF_RUNNING | _PCAP_IF_UP
    candidates = [(name, desc, flags) for name, desc, flags in devices if not (flags & _PCAP_IF_LOOPBACK)]
    for name, desc, flags in candidates:
        if flags & running_or_up and not _is_virtual_device(name, desc):
            return name
    for name, _desc, flags in candidates:
        if flags & running_or_up:
            return name
    if not candidates:
        raise OSError("No capture devices found (need privileges / Npcap on Windows).")
    return candidates[0][0]


def _is_virtual_device(name: str, desc: str) -> bool:
    """True for adapters that carry no real internet route (skip in auto-detect).

    Unix interfaces are matched by name prefix; Windows adapters (opaque GUID
    names) are matched by description keyword.
    """
    low_name = name.lower()
    if any(low_name.startswith(prefix) for prefix in _VIRTUAL_PREFIXES):
        return True
    low_desc = (desc or "").lower()
    return any(keyword in low_desc for keyword in _VIRTUAL_DESC_KEYWORDS)


def _windows_route_device_name(probe: tuple[int, int, int, int] = (8, 8, 8, 8)) -> str | None:
    r"""Return the Npcap device (``\Device\NPF_{GUID}``) owning the internet route.

    Resolves, via the Windows IP Helper API, which interface a packet to a public
    host would leave through, then maps its index to the adapter GUID Npcap names
    the device after. This correctly follows an active VPN full-tunnel. Returns
    ``None`` on any failure so the caller falls back to the heuristic.
    """
    if sys.platform != "win32":
        return None

    class _SockaddrIn(ctypes.Structure):
        _fields_ = [
            ("sin_family", ctypes.c_short),
            ("sin_port", ctypes.c_ushort),
            ("sin_addr", ctypes.c_ubyte * 4),
            ("sin_zero", ctypes.c_ubyte * 8),
        ]

    class _GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", ctypes.c_uint32),
            ("Data2", ctypes.c_uint16),
            ("Data3", ctypes.c_uint16),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    try:
        iphlpapi = ctypes.windll.iphlpapi  # type: ignore[attr-defined]

        dest = _SockaddrIn()
        dest.sin_family = 2  # AF_INET
        dest.sin_addr[:] = probe
        if_index = ctypes.c_uint32()
        if iphlpapi.GetBestInterfaceEx(ctypes.byref(dest), ctypes.byref(if_index)) != 0:
            return None

        luid = ctypes.c_uint64()  # NET_LUID is a 64-bit opaque value
        if iphlpapi.ConvertInterfaceIndexToLuid(if_index, ctypes.byref(luid)) != 0:
            return None

        guid = _GUID()
        if iphlpapi.ConvertInterfaceLuidToGuid(ctypes.byref(luid), ctypes.byref(guid)) != 0:
            return None
    except (AttributeError, OSError):
        return None

    d4 = bytes(guid.Data4)
    guid_str = (
        f"{{{guid.Data1:08X}-{guid.Data2:04X}-{guid.Data3:04X}-"
        f"{d4[0]:02X}{d4[1]:02X}-{d4[2]:02X}{d4[3]:02X}{d4[4]:02X}{d4[5]:02X}{d4[6]:02X}{d4[7]:02X}}}"
    )
    return r"\Device\NPF_" + guid_str


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
