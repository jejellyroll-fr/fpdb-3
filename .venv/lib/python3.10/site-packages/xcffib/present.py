import xcffib
import struct
import io
MAJOR_VERSION = 1
MINOR_VERSION = 3
key = xcffib.ExtensionKey("Present")
_events = {}
_errors = {}
from . import xproto
from . import randr
from . import xfixes
from . import sync
class Event:
    ConfigureNotify = 0
    CompleteNotify = 1
    IdleNotify = 2
    RedirectNotify = 3
class EventMask:
    NoEvent = 0
    ConfigureNotify = 1 << 0
    CompleteNotify = 1 << 1
    IdleNotify = 1 << 2
    RedirectNotify = 1 << 3
class Option:
    _None = 0
    Async = 1 << 0
    Copy = 1 << 1
    UST = 1 << 2
    Suboptimal = 1 << 3
    AsyncMayTear = 1 << 4
class Capability:
    _None = 0
    Async = 1 << 0
    Fence = 1 << 1
    UST = 1 << 2
    AsyncMayTear = 1 << 3
class CompleteKind:
    Pixmap = 0
    NotifyMSC = 1
class CompleteMode:
    Copy = 0
    Flip = 1
    Skip = 2
    SuboptimalCopy = 3
class Notify(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.window, self.serial = unpacker.unpack("II")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=II", self.window, self.serial))
        return buf.getvalue()
    fixed_size = 8
    @classmethod
    def synthetic(cls, window, serial):
        self = cls.__new__(cls)
        self.window = window
        self.serial = serial
        return self
class QueryVersionReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.major_version, self.minor_version = unpacker.unpack("xx2x4xII")
        self.bufsize = unpacker.offset - base
class QueryVersionCookie(xcffib.Cookie):
    reply_type = QueryVersionReply
class QueryCapabilitiesReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.capabilities, = unpacker.unpack("xx2x4xI")
        self.bufsize = unpacker.offset - base
class QueryCapabilitiesCookie(xcffib.Cookie):
    reply_type = QueryCapabilitiesReply
class GenericEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.extension, self.length, self.evtype, self.event = unpacker.unpack("xB2xIH2xI")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 0))
        buf.write(struct.pack("=B2xIH2xI", self.extension, self.length, self.evtype, self.event))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, extension, length, evtype, event):
        self = cls.__new__(cls)
        self.extension = extension
        self.length = length
        self.evtype = evtype
        self.event = event
        return self
_events[0] = GenericEvent
class ConfigureNotifyEvent(xcffib.Event):
    xge = True
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.event, self.window, self.x, self.y, self.width, self.height, self.off_x, self.off_y, self.pixmap_width, self.pixmap_height, self.pixmap_flags = unpacker.unpack("xx2x2xIIhhHHhhHHI")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 0))
        buf.write(struct.pack("=x2x2xIIhhHHhhHHI", self.event, self.window, self.x, self.y, self.width, self.height, self.off_x, self.off_y, self.pixmap_width, self.pixmap_height, self.pixmap_flags))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, event, window, x, y, width, height, off_x, off_y, pixmap_width, pixmap_height, pixmap_flags):
        self = cls.__new__(cls)
        self.event = event
        self.window = window
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.off_x = off_x
        self.off_y = off_y
        self.pixmap_width = pixmap_width
        self.pixmap_height = pixmap_height
        self.pixmap_flags = pixmap_flags
        return self
_events[0] = ConfigureNotifyEvent
class IdleNotifyEvent(xcffib.Event):
    xge = True
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.event, self.window, self.serial, self.pixmap, self.idle_fence = unpacker.unpack("xx2x2xIIIII")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 2))
        buf.write(struct.pack("=x2x2xIIIII", self.event, self.window, self.serial, self.pixmap, self.idle_fence))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, event, window, serial, pixmap, idle_fence):
        self = cls.__new__(cls)
        self.event = event
        self.window = window
        self.serial = serial
        self.pixmap = pixmap
        self.idle_fence = idle_fence
        return self
_events[2] = IdleNotifyEvent
class presentExtension(xcffib.Extension):
    def QueryVersion(self, major_version, minor_version, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", major_version, minor_version))
        return self.send_request(0, buf, QueryVersionCookie, is_checked=is_checked)
    def SelectInput(self, eid, window, event_mask, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIII", eid, window, event_mask))
        return self.send_request(3, buf, is_checked=is_checked)
    def QueryCapabilities(self, target, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", target))
        return self.send_request(4, buf, QueryCapabilitiesCookie, is_checked=is_checked)
xcffib._add_ext(key, presentExtension, _events, _errors)
