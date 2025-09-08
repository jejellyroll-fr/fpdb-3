import xcffib
import struct
import io
MAJOR_VERSION = 0
MINOR_VERSION = 4
key = xcffib.ExtensionKey("Composite")
_events = {}
_errors = {}
from . import xproto
from . import xfixes
class Redirect:
    Automatic = 0
    Manual = 1
class QueryVersionReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.major_version, self.minor_version = unpacker.unpack("xx2x4xII16x")
        self.bufsize = unpacker.offset - base
class QueryVersionCookie(xcffib.Cookie):
    reply_type = QueryVersionReply
class GetOverlayWindowReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.overlay_win, = unpacker.unpack("xx2x4xI20x")
        self.bufsize = unpacker.offset - base
class GetOverlayWindowCookie(xcffib.Cookie):
    reply_type = GetOverlayWindowReply
class compositeExtension(xcffib.Extension):
    def QueryVersion(self, client_major_version, client_minor_version, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", client_major_version, client_minor_version))
        return self.send_request(0, buf, QueryVersionCookie, is_checked=is_checked)
    def RedirectWindow(self, window, update, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIB3x", window, update))
        return self.send_request(1, buf, is_checked=is_checked)
    def RedirectSubwindows(self, window, update, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIB3x", window, update))
        return self.send_request(2, buf, is_checked=is_checked)
    def UnredirectWindow(self, window, update, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIB3x", window, update))
        return self.send_request(3, buf, is_checked=is_checked)
    def UnredirectSubwindows(self, window, update, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIB3x", window, update))
        return self.send_request(4, buf, is_checked=is_checked)
    def CreateRegionFromBorderClip(self, region, window, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", region, window))
        return self.send_request(5, buf, is_checked=is_checked)
    def NameWindowPixmap(self, window, pixmap, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", window, pixmap))
        return self.send_request(6, buf, is_checked=is_checked)
    def GetOverlayWindow(self, window, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", window))
        return self.send_request(7, buf, GetOverlayWindowCookie, is_checked=is_checked)
    def ReleaseOverlayWindow(self, window, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", window))
        return self.send_request(8, buf, is_checked=is_checked)
xcffib._add_ext(key, compositeExtension, _events, _errors)
