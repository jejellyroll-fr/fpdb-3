import xcffib
import struct
import io
MAJOR_VERSION = 1
MINOR_VERSION = 1
key = xcffib.ExtensionKey("XINERAMA")
_events = {}
_errors = {}
from . import xproto
class ScreenInfo(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.x_org, self.y_org, self.width, self.height = unpacker.unpack("hhHH")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=hhHH", self.x_org, self.y_org, self.width, self.height))
        return buf.getvalue()
    fixed_size = 8
    @classmethod
    def synthetic(cls, x_org, y_org, width, height):
        self = cls.__new__(cls)
        self.x_org = x_org
        self.y_org = y_org
        self.width = width
        self.height = height
        return self
class QueryVersionReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.major, self.minor = unpacker.unpack("xx2x4xHH")
        self.bufsize = unpacker.offset - base
class QueryVersionCookie(xcffib.Cookie):
    reply_type = QueryVersionReply
class GetStateReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.state, self.window = unpacker.unpack("xB2x4xI")
        self.bufsize = unpacker.offset - base
class GetStateCookie(xcffib.Cookie):
    reply_type = GetStateReply
class GetScreenCountReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.screen_count, self.window = unpacker.unpack("xB2x4xI")
        self.bufsize = unpacker.offset - base
class GetScreenCountCookie(xcffib.Cookie):
    reply_type = GetScreenCountReply
class GetScreenSizeReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.width, self.height, self.window, self.screen = unpacker.unpack("xx2x4xIIII")
        self.bufsize = unpacker.offset - base
class GetScreenSizeCookie(xcffib.Cookie):
    reply_type = GetScreenSizeReply
class IsActiveReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.state, = unpacker.unpack("xx2x4xI")
        self.bufsize = unpacker.offset - base
class IsActiveCookie(xcffib.Cookie):
    reply_type = IsActiveReply
class QueryScreensReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.number, = unpacker.unpack("xx2x4xI20x")
        self.screen_info = xcffib.List(unpacker, ScreenInfo, self.number)
        self.bufsize = unpacker.offset - base
class QueryScreensCookie(xcffib.Cookie):
    reply_type = QueryScreensReply
class xineramaExtension(xcffib.Extension):
    def QueryVersion(self, major, minor, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xBB", major, minor))
        return self.send_request(0, buf, QueryVersionCookie, is_checked=is_checked)
    def GetState(self, window, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", window))
        return self.send_request(1, buf, GetStateCookie, is_checked=is_checked)
    def GetScreenCount(self, window, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", window))
        return self.send_request(2, buf, GetScreenCountCookie, is_checked=is_checked)
    def GetScreenSize(self, window, screen, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", window, screen))
        return self.send_request(3, buf, GetScreenSizeCookie, is_checked=is_checked)
    def IsActive(self, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2x"))
        return self.send_request(4, buf, IsActiveCookie, is_checked=is_checked)
    def QueryScreens(self, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2x"))
        return self.send_request(5, buf, QueryScreensCookie, is_checked=is_checked)
xcffib._add_ext(key, xineramaExtension, _events, _errors)
