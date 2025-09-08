import xcffib
import struct
import io
MAJOR_VERSION = 1
MINOR_VERSION = 1
key = xcffib.ExtensionKey("XC-MISC")
_events = {}
_errors = {}
class GetVersionReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.server_major_version, self.server_minor_version = unpacker.unpack("xx2x4xHH")
        self.bufsize = unpacker.offset - base
class GetVersionCookie(xcffib.Cookie):
    reply_type = GetVersionReply
class GetXIDRangeReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.start_id, self.count = unpacker.unpack("xx2x4xII")
        self.bufsize = unpacker.offset - base
class GetXIDRangeCookie(xcffib.Cookie):
    reply_type = GetXIDRangeReply
class GetXIDListReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.ids_len, = unpacker.unpack("xx2x4xI20x")
        self.ids = xcffib.List(unpacker, "I", self.ids_len)
        self.bufsize = unpacker.offset - base
class GetXIDListCookie(xcffib.Cookie):
    reply_type = GetXIDListReply
class xc_miscExtension(xcffib.Extension):
    def GetVersion(self, client_major_version, client_minor_version, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xHH", client_major_version, client_minor_version))
        return self.send_request(0, buf, GetVersionCookie, is_checked=is_checked)
    def GetXIDRange(self, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2x"))
        return self.send_request(1, buf, GetXIDRangeCookie, is_checked=is_checked)
    def GetXIDList(self, count, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", count))
        return self.send_request(2, buf, GetXIDListCookie, is_checked=is_checked)
xcffib._add_ext(key, xc_miscExtension, _events, _errors)
