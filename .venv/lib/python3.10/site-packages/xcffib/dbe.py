import xcffib
import struct
import io
MAJOR_VERSION = 1
MINOR_VERSION = 0
key = xcffib.ExtensionKey("DOUBLE-BUFFER")
_events = {}
_errors = {}
from . import xproto
class SwapAction:
    Undefined = 0
    Background = 1
    Untouched = 2
    Copied = 3
class SwapInfo(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.window, self.swap_action = unpacker.unpack("IB3x")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=IB3x", self.window, self.swap_action))
        return buf.getvalue()
    fixed_size = 8
    @classmethod
    def synthetic(cls, window, swap_action):
        self = cls.__new__(cls)
        self.window = window
        self.swap_action = swap_action
        return self
class BufferAttributes(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.window, = unpacker.unpack("I")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=I", self.window))
        return buf.getvalue()
    fixed_size = 4
    @classmethod
    def synthetic(cls, window):
        self = cls.__new__(cls)
        self.window = window
        return self
class VisualInfo(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.visual_id, self.depth, self.perf_level = unpacker.unpack("IBB2x")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=IBB2x", self.visual_id, self.depth, self.perf_level))
        return buf.getvalue()
    fixed_size = 8
    @classmethod
    def synthetic(cls, visual_id, depth, perf_level):
        self = cls.__new__(cls)
        self.visual_id = visual_id
        self.depth = depth
        self.perf_level = perf_level
        return self
class VisualInfos(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.n_infos, = unpacker.unpack("I")
        self.infos = xcffib.List(unpacker, VisualInfo, self.n_infos)
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=I", self.n_infos))
        buf.write(xcffib.pack_list(self.infos, VisualInfo))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, n_infos, infos):
        self = cls.__new__(cls)
        self.n_infos = n_infos
        self.infos = infos
        return self
class BadBufferError(xcffib.Error):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Error.__init__(self, unpacker)
        base = unpacker.offset
        self.bad_buffer, = unpacker.unpack("xx2xI")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 0))
        buf.write(struct.pack("=x2xI", self.bad_buffer))
        return buf.getvalue()
BadBadBuffer = BadBufferError
_errors[0] = BadBufferError
class QueryVersionReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.major_version, self.minor_version = unpacker.unpack("xx2x4xBB22x")
        self.bufsize = unpacker.offset - base
class QueryVersionCookie(xcffib.Cookie):
    reply_type = QueryVersionReply
class GetVisualInfoReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.n_supported_visuals, = unpacker.unpack("xx2x4xI20x")
        self.supported_visuals = xcffib.List(unpacker, VisualInfos, self.n_supported_visuals)
        self.bufsize = unpacker.offset - base
class GetVisualInfoCookie(xcffib.Cookie):
    reply_type = GetVisualInfoReply
class GetBackBufferAttributesReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        unpacker.unpack("xx2x4x")
        self.attributes = BufferAttributes(unpacker)
        unpacker.unpack("20x")
        self.bufsize = unpacker.offset - base
class GetBackBufferAttributesCookie(xcffib.Cookie):
    reply_type = GetBackBufferAttributesReply
class dbeExtension(xcffib.Extension):
    def QueryVersion(self, major_version, minor_version, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xBB2x", major_version, minor_version))
        return self.send_request(0, buf, QueryVersionCookie, is_checked=is_checked)
    def AllocateBackBuffer(self, window, buffer, swap_action, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIB3x", window, buffer, swap_action))
        return self.send_request(1, buf, is_checked=is_checked)
    def DeallocateBackBuffer(self, buffer, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", buffer))
        return self.send_request(2, buf, is_checked=is_checked)
    def SwapBuffers(self, n_actions, actions, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", n_actions))
        buf.write(xcffib.pack_list(actions, SwapInfo))
        return self.send_request(3, buf, is_checked=is_checked)
    def BeginIdiom(self, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2x"))
        return self.send_request(4, buf, is_checked=is_checked)
    def EndIdiom(self, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2x"))
        return self.send_request(5, buf, is_checked=is_checked)
    def GetVisualInfo(self, n_drawables, drawables, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", n_drawables))
        buf.write(xcffib.pack_list(drawables, "I"))
        return self.send_request(6, buf, GetVisualInfoCookie, is_checked=is_checked)
    def GetBackBufferAttributes(self, buffer, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", buffer))
        return self.send_request(7, buf, GetBackBufferAttributesCookie, is_checked=is_checked)
xcffib._add_ext(key, dbeExtension, _events, _errors)
