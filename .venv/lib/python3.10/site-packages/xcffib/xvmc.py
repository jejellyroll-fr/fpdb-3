import xcffib
import struct
import io
MAJOR_VERSION = 1
MINOR_VERSION = 1
key = xcffib.ExtensionKey("XVideo-MotionCompensation")
_events = {}
_errors = {}
from . import xv
class SurfaceInfo(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.id, self.chroma_format, self.pad0, self.max_width, self.max_height, self.subpicture_max_width, self.subpicture_max_height, self.mc_type, self.flags = unpacker.unpack("IHHHHHHII")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=IHHHHHHII", self.id, self.chroma_format, self.pad0, self.max_width, self.max_height, self.subpicture_max_width, self.subpicture_max_height, self.mc_type, self.flags))
        return buf.getvalue()
    fixed_size = 24
    @classmethod
    def synthetic(cls, id, chroma_format, pad0, max_width, max_height, subpicture_max_width, subpicture_max_height, mc_type, flags):
        self = cls.__new__(cls)
        self.id = id
        self.chroma_format = chroma_format
        self.pad0 = pad0
        self.max_width = max_width
        self.max_height = max_height
        self.subpicture_max_width = subpicture_max_width
        self.subpicture_max_height = subpicture_max_height
        self.mc_type = mc_type
        self.flags = flags
        return self
class QueryVersionReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.major, self.minor = unpacker.unpack("xx2x4xII")
        self.bufsize = unpacker.offset - base
class QueryVersionCookie(xcffib.Cookie):
    reply_type = QueryVersionReply
class ListSurfaceTypesReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.num, = unpacker.unpack("xx2x4xI20x")
        self.surfaces = xcffib.List(unpacker, SurfaceInfo, self.num)
        self.bufsize = unpacker.offset - base
class ListSurfaceTypesCookie(xcffib.Cookie):
    reply_type = ListSurfaceTypesReply
class CreateContextReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.width_actual, self.height_actual, self.flags_return = unpacker.unpack("xx2x4xHHI20x")
        self.priv_data = xcffib.List(unpacker, "I", self.length)
        self.bufsize = unpacker.offset - base
class CreateContextCookie(xcffib.Cookie):
    reply_type = CreateContextReply
class CreateSurfaceReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        unpacker.unpack("xx2x4x24x")
        self.priv_data = xcffib.List(unpacker, "I", self.length)
        self.bufsize = unpacker.offset - base
class CreateSurfaceCookie(xcffib.Cookie):
    reply_type = CreateSurfaceReply
class CreateSubpictureReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.width_actual, self.height_actual, self.num_palette_entries, self.entry_bytes = unpacker.unpack("xx2x4xHHHH")
        self.component_order = xcffib.List(unpacker, "B", 4)
        unpacker.unpack("12x")
        unpacker.pad("I")
        self.priv_data = xcffib.List(unpacker, "I", self.length)
        self.bufsize = unpacker.offset - base
class CreateSubpictureCookie(xcffib.Cookie):
    reply_type = CreateSubpictureReply
class ListSubpictureTypesReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.num, = unpacker.unpack("xx2x4xI20x")
        self.types = xcffib.List(unpacker, xv.ImageFormatInfo, self.num)
        self.bufsize = unpacker.offset - base
class ListSubpictureTypesCookie(xcffib.Cookie):
    reply_type = ListSubpictureTypesReply
class xvmcExtension(xcffib.Extension):
    def QueryVersion(self, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2x"))
        return self.send_request(0, buf, QueryVersionCookie, is_checked=is_checked)
    def ListSurfaceTypes(self, port_id, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", port_id))
        return self.send_request(1, buf, ListSurfaceTypesCookie, is_checked=is_checked)
    def CreateContext(self, context_id, port_id, surface_id, width, height, flags, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIIHHI", context_id, port_id, surface_id, width, height, flags))
        return self.send_request(2, buf, CreateContextCookie, is_checked=is_checked)
    def DestroyContext(self, context_id, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", context_id))
        return self.send_request(3, buf, is_checked=is_checked)
    def CreateSurface(self, surface_id, context_id, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", surface_id, context_id))
        return self.send_request(4, buf, CreateSurfaceCookie, is_checked=is_checked)
    def DestroySurface(self, surface_id, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", surface_id))
        return self.send_request(5, buf, is_checked=is_checked)
    def CreateSubpicture(self, subpicture_id, context, xvimage_id, width, height, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIIHH", subpicture_id, context, xvimage_id, width, height))
        return self.send_request(6, buf, CreateSubpictureCookie, is_checked=is_checked)
    def DestroySubpicture(self, subpicture_id, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", subpicture_id))
        return self.send_request(7, buf, is_checked=is_checked)
    def ListSubpictureTypes(self, port_id, surface_id, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", port_id, surface_id))
        return self.send_request(8, buf, ListSubpictureTypesCookie, is_checked=is_checked)
xcffib._add_ext(key, xvmcExtension, _events, _errors)
