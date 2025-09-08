import xcffib
import struct
import io
MAJOR_VERSION = 2
MINOR_VERSION = 2
key = xcffib.ExtensionKey("XTEST")
_events = {}
_errors = {}
from . import xproto
class GetVersionReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.major_version, self.minor_version = unpacker.unpack("xB2x4xH")
        self.bufsize = unpacker.offset - base
class GetVersionCookie(xcffib.Cookie):
    reply_type = GetVersionReply
class Cursor:
    _None = 0
    Current = 1
class CompareCursorReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.same, = unpacker.unpack("xB2x4x")
        self.bufsize = unpacker.offset - base
class CompareCursorCookie(xcffib.Cookie):
    reply_type = CompareCursorReply
class xtestExtension(xcffib.Extension):
    def GetVersion(self, major_version, minor_version, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xBxH", major_version, minor_version))
        return self.send_request(0, buf, GetVersionCookie, is_checked=is_checked)
    def CompareCursor(self, window, cursor, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", window, cursor))
        return self.send_request(1, buf, CompareCursorCookie, is_checked=is_checked)
    def FakeInput(self, type, detail, time, root, rootX, rootY, deviceid, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xBB2xII8xhh7xB", type, detail, time, root, rootX, rootY, deviceid))
        return self.send_request(2, buf, is_checked=is_checked)
    def GrabControl(self, impervious, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xB3x", impervious))
        return self.send_request(3, buf, is_checked=is_checked)
xcffib._add_ext(key, xtestExtension, _events, _errors)
