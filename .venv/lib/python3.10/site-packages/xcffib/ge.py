import xcffib
import struct
import io
MAJOR_VERSION = 1
MINOR_VERSION = 0
key = xcffib.ExtensionKey("Generic Event Extension")
_events = {}
_errors = {}
class QueryVersionReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.major_version, self.minor_version = unpacker.unpack("xx2x4xHH20x")
        self.bufsize = unpacker.offset - base
class QueryVersionCookie(xcffib.Cookie):
    reply_type = QueryVersionReply
class geExtension(xcffib.Extension):
    def QueryVersion(self, client_major_version, client_minor_version, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xHH", client_major_version, client_minor_version))
        return self.send_request(0, buf, QueryVersionCookie, is_checked=is_checked)
xcffib._add_ext(key, geExtension, _events, _errors)
