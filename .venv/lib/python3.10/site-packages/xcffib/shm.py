import xcffib
import struct
import io
MAJOR_VERSION = 1
MINOR_VERSION = 2
key = xcffib.ExtensionKey("MIT-SHM")
_events = {}
_errors = {}
from . import xproto
class CompletionEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.drawable, self.minor_event, self.major_event, self.shmseg, self.offset = unpacker.unpack("xx2xIHBxII")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 0))
        buf.write(struct.pack("=x2xIHBxII", self.drawable, self.minor_event, self.major_event, self.shmseg, self.offset))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, drawable, minor_event, major_event, shmseg, offset):
        self = cls.__new__(cls)
        self.drawable = drawable
        self.minor_event = minor_event
        self.major_event = major_event
        self.shmseg = shmseg
        self.offset = offset
        return self
_events[0] = CompletionEvent
class BadSegError(xcffib.Error):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Error.__init__(self, unpacker)
        base = unpacker.offset
        self.bad_value, self.minor_opcode, self.major_opcode = unpacker.unpack("xx2xIHBx")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 0))
        buf.write(struct.pack("=x2xIHBx", self.bad_value, self.minor_opcode, self.major_opcode))
        return buf.getvalue()
BadBadSeg = BadSegError
_errors[0] = BadSegError
class QueryVersionReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.shared_pixmaps, self.major_version, self.minor_version, self.uid, self.gid, self.pixmap_format = unpacker.unpack("xB2x4xHHHHB15x")
        self.bufsize = unpacker.offset - base
class QueryVersionCookie(xcffib.Cookie):
    reply_type = QueryVersionReply
class GetImageReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.depth, self.visual, self.size = unpacker.unpack("xB2x4xII")
        self.bufsize = unpacker.offset - base
class GetImageCookie(xcffib.Cookie):
    reply_type = GetImageReply
class CreateSegmentReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.nfd, = unpacker.unpack("xB2x4x24x")
        self.bufsize = unpacker.offset - base
class CreateSegmentCookie(xcffib.Cookie):
    reply_type = CreateSegmentReply
class shmExtension(xcffib.Extension):
    def QueryVersion(self, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2x"))
        return self.send_request(0, buf, QueryVersionCookie, is_checked=is_checked)
    def Attach(self, shmseg, shmid, read_only, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIB3x", shmseg, shmid, read_only))
        return self.send_request(1, buf, is_checked=is_checked)
    def Detach(self, shmseg, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", shmseg))
        return self.send_request(2, buf, is_checked=is_checked)
    def PutImage(self, drawable, gc, total_width, total_height, src_x, src_y, src_width, src_height, dst_x, dst_y, depth, format, send_event, shmseg, offset, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIHHHHHHhhBBBxII", drawable, gc, total_width, total_height, src_x, src_y, src_width, src_height, dst_x, dst_y, depth, format, send_event, shmseg, offset))
        return self.send_request(3, buf, is_checked=is_checked)
    def GetImage(self, drawable, x, y, width, height, plane_mask, format, shmseg, offset, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIhhHHIB3xII", drawable, x, y, width, height, plane_mask, format, shmseg, offset))
        return self.send_request(4, buf, GetImageCookie, is_checked=is_checked)
    def CreatePixmap(self, pid, drawable, width, height, depth, shmseg, offset, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIHHB3xII", pid, drawable, width, height, depth, shmseg, offset))
        return self.send_request(5, buf, is_checked=is_checked)
    def AttachFd(self, shmseg, read_only, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIB3x", shmseg, read_only))
        return self.send_request(6, buf, is_checked=is_checked)
    def CreateSegment(self, shmseg, size, read_only, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIB3x", shmseg, size, read_only))
        return self.send_request(7, buf, CreateSegmentCookie, is_checked=is_checked)
xcffib._add_ext(key, shmExtension, _events, _errors)
