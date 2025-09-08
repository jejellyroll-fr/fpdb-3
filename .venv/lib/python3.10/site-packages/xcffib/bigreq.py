import xcffib
import struct
import io
MAJOR_VERSION = 0
MINOR_VERSION = 0
key = xcffib.ExtensionKey("BIG-REQUESTS")
_events = {}
_errors = {}
class EnableReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.maximum_request_length, = unpacker.unpack("xx2x4xI")
        self.bufsize = unpacker.offset - base
class EnableCookie(xcffib.Cookie):
    reply_type = EnableReply
class bigreqExtension(xcffib.Extension):
    def Enable(self, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2x"))
        return self.send_request(0, buf, EnableCookie, is_checked=is_checked)
xcffib._add_ext(key, bigreqExtension, _events, _errors)
