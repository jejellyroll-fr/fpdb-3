import xcffib
import struct
import io
MAJOR_VERSION = 4
MINOR_VERSION = 1
key = xcffib.ExtensionKey("XFree86-DRI")
_events = {}
_errors = {}
class DrmClipRect(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.x1, self.y1, self.x2, self.x3 = unpacker.unpack("hhhh")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=hhhh", self.x1, self.y1, self.x2, self.x3))
        return buf.getvalue()
    fixed_size = 8
    @classmethod
    def synthetic(cls, x1, y1, x2, x3):
        self = cls.__new__(cls)
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.x3 = x3
        return self
class QueryVersionReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.dri_major_version, self.dri_minor_version, self.dri_minor_patch = unpacker.unpack("xx2x4xHHI")
        self.bufsize = unpacker.offset - base
class QueryVersionCookie(xcffib.Cookie):
    reply_type = QueryVersionReply
class QueryDirectRenderingCapableReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.is_capable, = unpacker.unpack("xx2x4xB")
        self.bufsize = unpacker.offset - base
class QueryDirectRenderingCapableCookie(xcffib.Cookie):
    reply_type = QueryDirectRenderingCapableReply
class OpenConnectionReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.sarea_handle_low, self.sarea_handle_high, self.bus_id_len = unpacker.unpack("xx2x4xIII12x")
        self.bus_id = xcffib.List(unpacker, "c", self.bus_id_len)
        self.bufsize = unpacker.offset - base
class OpenConnectionCookie(xcffib.Cookie):
    reply_type = OpenConnectionReply
class GetClientDriverNameReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.client_driver_major_version, self.client_driver_minor_version, self.client_driver_patch_version, self.client_driver_name_len = unpacker.unpack("xx2x4xIIII8x")
        self.client_driver_name = xcffib.List(unpacker, "c", self.client_driver_name_len)
        self.bufsize = unpacker.offset - base
class GetClientDriverNameCookie(xcffib.Cookie):
    reply_type = GetClientDriverNameReply
class CreateContextReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.hw_context, = unpacker.unpack("xx2x4xI")
        self.bufsize = unpacker.offset - base
class CreateContextCookie(xcffib.Cookie):
    reply_type = CreateContextReply
class CreateDrawableReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.hw_drawable_handle, = unpacker.unpack("xx2x4xI")
        self.bufsize = unpacker.offset - base
class CreateDrawableCookie(xcffib.Cookie):
    reply_type = CreateDrawableReply
class GetDrawableInfoReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.drawable_table_index, self.drawable_table_stamp, self.drawable_origin_X, self.drawable_origin_Y, self.drawable_size_W, self.drawable_size_H, self.num_clip_rects, self.back_x, self.back_y, self.num_back_clip_rects = unpacker.unpack("xx2x4xIIhhhhIhhI")
        self.clip_rects = xcffib.List(unpacker, DrmClipRect, self.num_clip_rects)
        unpacker.pad(DrmClipRect)
        self.back_clip_rects = xcffib.List(unpacker, DrmClipRect, self.num_back_clip_rects)
        self.bufsize = unpacker.offset - base
class GetDrawableInfoCookie(xcffib.Cookie):
    reply_type = GetDrawableInfoReply
class GetDeviceInfoReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.framebuffer_handle_low, self.framebuffer_handle_high, self.framebuffer_origin_offset, self.framebuffer_size, self.framebuffer_stride, self.device_private_size = unpacker.unpack("xx2x4xIIIIII")
        self.device_private = xcffib.List(unpacker, "I", self.device_private_size)
        self.bufsize = unpacker.offset - base
class GetDeviceInfoCookie(xcffib.Cookie):
    reply_type = GetDeviceInfoReply
class AuthConnectionReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.authenticated, = unpacker.unpack("xx2x4xI")
        self.bufsize = unpacker.offset - base
class AuthConnectionCookie(xcffib.Cookie):
    reply_type = AuthConnectionReply
class xf86driExtension(xcffib.Extension):
    def QueryVersion(self, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2x"))
        return self.send_request(0, buf, QueryVersionCookie, is_checked=is_checked)
    def QueryDirectRenderingCapable(self, screen, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", screen))
        return self.send_request(1, buf, QueryDirectRenderingCapableCookie, is_checked=is_checked)
    def OpenConnection(self, screen, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", screen))
        return self.send_request(2, buf, OpenConnectionCookie, is_checked=is_checked)
    def CloseConnection(self, screen, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", screen))
        return self.send_request(3, buf, is_checked=is_checked)
    def GetClientDriverName(self, screen, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", screen))
        return self.send_request(4, buf, GetClientDriverNameCookie, is_checked=is_checked)
    def CreateContext(self, screen, visual, context, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIII", screen, visual, context))
        return self.send_request(5, buf, CreateContextCookie, is_checked=is_checked)
    def DestroyContext(self, screen, context, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", screen, context))
        return self.send_request(6, buf, is_checked=is_checked)
    def CreateDrawable(self, screen, drawable, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", screen, drawable))
        return self.send_request(7, buf, CreateDrawableCookie, is_checked=is_checked)
    def DestroyDrawable(self, screen, drawable, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", screen, drawable))
        return self.send_request(8, buf, is_checked=is_checked)
    def GetDrawableInfo(self, screen, drawable, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", screen, drawable))
        return self.send_request(9, buf, GetDrawableInfoCookie, is_checked=is_checked)
    def GetDeviceInfo(self, screen, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", screen))
        return self.send_request(10, buf, GetDeviceInfoCookie, is_checked=is_checked)
    def AuthConnection(self, screen, magic, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", screen, magic))
        return self.send_request(11, buf, AuthConnectionCookie, is_checked=is_checked)
xcffib._add_ext(key, xf86driExtension, _events, _errors)
