import xcffib
import struct
import io
MAJOR_VERSION = 0
MINOR_VERSION = 11
key = xcffib.ExtensionKey("RENDER")
_events = {}
_errors = {}
from . import xproto
class PictType:
    Indexed = 0
    Direct = 1
class Picture:
    _None = 0
class PictOp:
    Clear = 0
    Src = 1
    Dst = 2
    Over = 3
    OverReverse = 4
    In = 5
    InReverse = 6
    Out = 7
    OutReverse = 8
    Atop = 9
    AtopReverse = 10
    Xor = 11
    Add = 12
    Saturate = 13
    DisjointClear = 16
    DisjointSrc = 17
    DisjointDst = 18
    DisjointOver = 19
    DisjointOverReverse = 20
    DisjointIn = 21
    DisjointInReverse = 22
    DisjointOut = 23
    DisjointOutReverse = 24
    DisjointAtop = 25
    DisjointAtopReverse = 26
    DisjointXor = 27
    ConjointClear = 32
    ConjointSrc = 33
    ConjointDst = 34
    ConjointOver = 35
    ConjointOverReverse = 36
    ConjointIn = 37
    ConjointInReverse = 38
    ConjointOut = 39
    ConjointOutReverse = 40
    ConjointAtop = 41
    ConjointAtopReverse = 42
    ConjointXor = 43
    Multiply = 48
    Screen = 49
    Overlay = 50
    Darken = 51
    Lighten = 52
    ColorDodge = 53
    ColorBurn = 54
    HardLight = 55
    SoftLight = 56
    Difference = 57
    Exclusion = 58
    HSLHue = 59
    HSLSaturation = 60
    HSLColor = 61
    HSLLuminosity = 62
class PolyEdge:
    Sharp = 0
    Smooth = 1
class PolyMode:
    Precise = 0
    Imprecise = 1
class CP:
    Repeat = 1 << 0
    AlphaMap = 1 << 1
    AlphaXOrigin = 1 << 2
    AlphaYOrigin = 1 << 3
    ClipXOrigin = 1 << 4
    ClipYOrigin = 1 << 5
    ClipMask = 1 << 6
    GraphicsExposure = 1 << 7
    SubwindowMode = 1 << 8
    PolyEdge = 1 << 9
    PolyMode = 1 << 10
    Dither = 1 << 11
    ComponentAlpha = 1 << 12
class SubPixel:
    Unknown = 0
    HorizontalRGB = 1
    HorizontalBGR = 2
    VerticalRGB = 3
    VerticalBGR = 4
    _None = 5
class Repeat:
    _None = 0
    Normal = 1
    Pad = 2
    Reflect = 3
class PictFormatError(xcffib.Error):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Error.__init__(self, unpacker)
        base = unpacker.offset
        unpacker.unpack("xx2x")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 0))
        buf.write(struct.pack("=x2x"))
        return buf.getvalue()
BadPictFormat = PictFormatError
_errors[0] = PictFormatError
class PictureError(xcffib.Error):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Error.__init__(self, unpacker)
        base = unpacker.offset
        unpacker.unpack("xx2x")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 1))
        buf.write(struct.pack("=x2x"))
        return buf.getvalue()
BadPicture = PictureError
_errors[1] = PictureError
class PictOpError(xcffib.Error):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Error.__init__(self, unpacker)
        base = unpacker.offset
        unpacker.unpack("xx2x")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 2))
        buf.write(struct.pack("=x2x"))
        return buf.getvalue()
BadPictOp = PictOpError
_errors[2] = PictOpError
class GlyphSetError(xcffib.Error):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Error.__init__(self, unpacker)
        base = unpacker.offset
        unpacker.unpack("xx2x")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 3))
        buf.write(struct.pack("=x2x"))
        return buf.getvalue()
BadGlyphSet = GlyphSetError
_errors[3] = GlyphSetError
class GlyphError(xcffib.Error):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Error.__init__(self, unpacker)
        base = unpacker.offset
        unpacker.unpack("xx2x")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 4))
        buf.write(struct.pack("=x2x"))
        return buf.getvalue()
BadGlyph = GlyphError
_errors[4] = GlyphError
class DIRECTFORMAT(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.red_shift, self.red_mask, self.green_shift, self.green_mask, self.blue_shift, self.blue_mask, self.alpha_shift, self.alpha_mask = unpacker.unpack("HHHHHHHH")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=HHHHHHHH", self.red_shift, self.red_mask, self.green_shift, self.green_mask, self.blue_shift, self.blue_mask, self.alpha_shift, self.alpha_mask))
        return buf.getvalue()
    fixed_size = 16
    @classmethod
    def synthetic(cls, red_shift, red_mask, green_shift, green_mask, blue_shift, blue_mask, alpha_shift, alpha_mask):
        self = cls.__new__(cls)
        self.red_shift = red_shift
        self.red_mask = red_mask
        self.green_shift = green_shift
        self.green_mask = green_mask
        self.blue_shift = blue_shift
        self.blue_mask = blue_mask
        self.alpha_shift = alpha_shift
        self.alpha_mask = alpha_mask
        return self
class PICTFORMINFO(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.id, self.type, self.depth = unpacker.unpack("IBB2x")
        self.direct = DIRECTFORMAT(unpacker)
        self.colormap, = unpacker.unpack("I")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=IBB2x", self.id, self.type, self.depth))
        buf.write(self.direct.pack() if hasattr(self.direct, "pack") else DIRECTFORMAT.synthetic(*self.direct).pack())
        buf.write(struct.pack("=I", self.colormap))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, id, type, depth, direct, colormap):
        self = cls.__new__(cls)
        self.id = id
        self.type = type
        self.depth = depth
        self.direct = direct
        self.colormap = colormap
        return self
class PICTVISUAL(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.visual, self.format = unpacker.unpack("II")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=II", self.visual, self.format))
        return buf.getvalue()
    fixed_size = 8
    @classmethod
    def synthetic(cls, visual, format):
        self = cls.__new__(cls)
        self.visual = visual
        self.format = format
        return self
class PICTDEPTH(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.depth, self.num_visuals = unpacker.unpack("BxH4x")
        self.visuals = xcffib.List(unpacker, PICTVISUAL, self.num_visuals)
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=BxH4x", self.depth, self.num_visuals))
        buf.write(xcffib.pack_list(self.visuals, PICTVISUAL))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, depth, num_visuals, visuals):
        self = cls.__new__(cls)
        self.depth = depth
        self.num_visuals = num_visuals
        self.visuals = visuals
        return self
class PICTSCREEN(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.num_depths, self.fallback = unpacker.unpack("II")
        self.depths = xcffib.List(unpacker, PICTDEPTH, self.num_depths)
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=II", self.num_depths, self.fallback))
        buf.write(xcffib.pack_list(self.depths, PICTDEPTH))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, num_depths, fallback, depths):
        self = cls.__new__(cls)
        self.num_depths = num_depths
        self.fallback = fallback
        self.depths = depths
        return self
class INDEXVALUE(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.pixel, self.red, self.green, self.blue, self.alpha = unpacker.unpack("IHHHH")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=IHHHH", self.pixel, self.red, self.green, self.blue, self.alpha))
        return buf.getvalue()
    fixed_size = 12
    @classmethod
    def synthetic(cls, pixel, red, green, blue, alpha):
        self = cls.__new__(cls)
        self.pixel = pixel
        self.red = red
        self.green = green
        self.blue = blue
        self.alpha = alpha
        return self
class COLOR(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.red, self.green, self.blue, self.alpha = unpacker.unpack("HHHH")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=HHHH", self.red, self.green, self.blue, self.alpha))
        return buf.getvalue()
    fixed_size = 8
    @classmethod
    def synthetic(cls, red, green, blue, alpha):
        self = cls.__new__(cls)
        self.red = red
        self.green = green
        self.blue = blue
        self.alpha = alpha
        return self
class POINTFIX(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.x, self.y = unpacker.unpack("ii")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=ii", self.x, self.y))
        return buf.getvalue()
    fixed_size = 8
    @classmethod
    def synthetic(cls, x, y):
        self = cls.__new__(cls)
        self.x = x
        self.y = y
        return self
class LINEFIX(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.p1 = POINTFIX(unpacker)
        unpacker.pad(POINTFIX)
        self.p2 = POINTFIX(unpacker)
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(self.p1.pack() if hasattr(self.p1, "pack") else POINTFIX.synthetic(*self.p1).pack())
        buf.write(self.p2.pack() if hasattr(self.p2, "pack") else POINTFIX.synthetic(*self.p2).pack())
        return buf.getvalue()
    @classmethod
    def synthetic(cls, p1, p2):
        self = cls.__new__(cls)
        self.p1 = p1
        self.p2 = p2
        return self
class TRIANGLE(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.p1 = POINTFIX(unpacker)
        unpacker.pad(POINTFIX)
        self.p2 = POINTFIX(unpacker)
        unpacker.pad(POINTFIX)
        self.p3 = POINTFIX(unpacker)
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(self.p1.pack() if hasattr(self.p1, "pack") else POINTFIX.synthetic(*self.p1).pack())
        buf.write(self.p2.pack() if hasattr(self.p2, "pack") else POINTFIX.synthetic(*self.p2).pack())
        buf.write(self.p3.pack() if hasattr(self.p3, "pack") else POINTFIX.synthetic(*self.p3).pack())
        return buf.getvalue()
    @classmethod
    def synthetic(cls, p1, p2, p3):
        self = cls.__new__(cls)
        self.p1 = p1
        self.p2 = p2
        self.p3 = p3
        return self
class TRAPEZOID(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.top, self.bottom = unpacker.unpack("ii")
        self.left = LINEFIX(unpacker)
        unpacker.pad(LINEFIX)
        self.right = LINEFIX(unpacker)
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=ii", self.top, self.bottom))
        buf.write(self.left.pack() if hasattr(self.left, "pack") else LINEFIX.synthetic(*self.left).pack())
        buf.write(self.right.pack() if hasattr(self.right, "pack") else LINEFIX.synthetic(*self.right).pack())
        return buf.getvalue()
    @classmethod
    def synthetic(cls, top, bottom, left, right):
        self = cls.__new__(cls)
        self.top = top
        self.bottom = bottom
        self.left = left
        self.right = right
        return self
class GLYPHINFO(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.width, self.height, self.x, self.y, self.x_off, self.y_off = unpacker.unpack("HHhhhh")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=HHhhhh", self.width, self.height, self.x, self.y, self.x_off, self.y_off))
        return buf.getvalue()
    fixed_size = 12
    @classmethod
    def synthetic(cls, width, height, x, y, x_off, y_off):
        self = cls.__new__(cls)
        self.width = width
        self.height = height
        self.x = x
        self.y = y
        self.x_off = x_off
        self.y_off = y_off
        return self
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
class QueryPictFormatsReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.num_formats, self.num_screens, self.num_depths, self.num_visuals, self.num_subpixel = unpacker.unpack("xx2x4xIIIII4x")
        self.formats = xcffib.List(unpacker, PICTFORMINFO, self.num_formats)
        unpacker.pad(PICTSCREEN)
        self.screens = xcffib.List(unpacker, PICTSCREEN, self.num_screens)
        unpacker.pad("I")
        self.subpixels = xcffib.List(unpacker, "I", self.num_subpixel)
        self.bufsize = unpacker.offset - base
class QueryPictFormatsCookie(xcffib.Cookie):
    reply_type = QueryPictFormatsReply
class QueryPictIndexValuesReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.num_values, = unpacker.unpack("xx2x4xI20x")
        self.values = xcffib.List(unpacker, INDEXVALUE, self.num_values)
        self.bufsize = unpacker.offset - base
class QueryPictIndexValuesCookie(xcffib.Cookie):
    reply_type = QueryPictIndexValuesReply
class TRANSFORM(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.matrix11, self.matrix12, self.matrix13, self.matrix21, self.matrix22, self.matrix23, self.matrix31, self.matrix32, self.matrix33 = unpacker.unpack("iiiiiiiii")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=iiiiiiiii", self.matrix11, self.matrix12, self.matrix13, self.matrix21, self.matrix22, self.matrix23, self.matrix31, self.matrix32, self.matrix33))
        return buf.getvalue()
    fixed_size = 36
    @classmethod
    def synthetic(cls, matrix11, matrix12, matrix13, matrix21, matrix22, matrix23, matrix31, matrix32, matrix33):
        self = cls.__new__(cls)
        self.matrix11 = matrix11
        self.matrix12 = matrix12
        self.matrix13 = matrix13
        self.matrix21 = matrix21
        self.matrix22 = matrix22
        self.matrix23 = matrix23
        self.matrix31 = matrix31
        self.matrix32 = matrix32
        self.matrix33 = matrix33
        return self
class QueryFiltersReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.num_aliases, self.num_filters = unpacker.unpack("xx2x4xII16x")
        self.aliases = xcffib.List(unpacker, "H", self.num_aliases)
        unpacker.pad(xproto.STR)
        self.filters = xcffib.List(unpacker, xproto.STR, self.num_filters)
        self.bufsize = unpacker.offset - base
class QueryFiltersCookie(xcffib.Cookie):
    reply_type = QueryFiltersReply
class ANIMCURSORELT(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.cursor, self.delay = unpacker.unpack("II")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=II", self.cursor, self.delay))
        return buf.getvalue()
    fixed_size = 8
    @classmethod
    def synthetic(cls, cursor, delay):
        self = cls.__new__(cls)
        self.cursor = cursor
        self.delay = delay
        return self
class SPANFIX(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.l, self.r, self.y = unpacker.unpack("iii")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=iii", self.l, self.r, self.y))
        return buf.getvalue()
    fixed_size = 12
    @classmethod
    def synthetic(cls, l, r, y):
        self = cls.__new__(cls)
        self.l = l
        self.r = r
        self.y = y
        return self
class TRAP(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.top = SPANFIX(unpacker)
        unpacker.pad(SPANFIX)
        self.bot = SPANFIX(unpacker)
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(self.top.pack() if hasattr(self.top, "pack") else SPANFIX.synthetic(*self.top).pack())
        buf.write(self.bot.pack() if hasattr(self.bot, "pack") else SPANFIX.synthetic(*self.bot).pack())
        return buf.getvalue()
    @classmethod
    def synthetic(cls, top, bot):
        self = cls.__new__(cls)
        self.top = top
        self.bot = bot
        return self
class renderExtension(xcffib.Extension):
    def QueryVersion(self, client_major_version, client_minor_version, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", client_major_version, client_minor_version))
        return self.send_request(0, buf, QueryVersionCookie, is_checked=is_checked)
    def QueryPictFormats(self, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2x"))
        return self.send_request(1, buf, QueryPictFormatsCookie, is_checked=is_checked)
    def QueryPictIndexValues(self, format, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", format))
        return self.send_request(2, buf, QueryPictIndexValuesCookie, is_checked=is_checked)
    def CreatePicture(self, pid, drawable, format, value_mask, value_list, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIII", pid, drawable, format, value_mask))
        if value_mask & CP.Repeat:
            repeat = value_list.pop(0)
            buf.write(struct.pack("=I", repeat))
        if value_mask & CP.AlphaMap:
            alphamap = value_list.pop(0)
            buf.write(struct.pack("=I", alphamap))
        if value_mask & CP.AlphaXOrigin:
            alphaxorigin = value_list.pop(0)
            buf.write(struct.pack("=i", alphaxorigin))
        if value_mask & CP.AlphaYOrigin:
            alphayorigin = value_list.pop(0)
            buf.write(struct.pack("=i", alphayorigin))
        if value_mask & CP.ClipXOrigin:
            clipxorigin = value_list.pop(0)
            buf.write(struct.pack("=i", clipxorigin))
        if value_mask & CP.ClipYOrigin:
            clipyorigin = value_list.pop(0)
            buf.write(struct.pack("=i", clipyorigin))
        if value_mask & CP.ClipMask:
            clipmask = value_list.pop(0)
            buf.write(struct.pack("=I", clipmask))
        if value_mask & CP.GraphicsExposure:
            graphicsexposure = value_list.pop(0)
            buf.write(struct.pack("=I", graphicsexposure))
        if value_mask & CP.SubwindowMode:
            subwindowmode = value_list.pop(0)
            buf.write(struct.pack("=I", subwindowmode))
        if value_mask & CP.PolyEdge:
            polyedge = value_list.pop(0)
            buf.write(struct.pack("=I", polyedge))
        if value_mask & CP.PolyMode:
            polymode = value_list.pop(0)
            buf.write(struct.pack("=I", polymode))
        if value_mask & CP.Dither:
            dither = value_list.pop(0)
            buf.write(struct.pack("=I", dither))
        if value_mask & CP.ComponentAlpha:
            componentalpha = value_list.pop(0)
            buf.write(struct.pack("=I", componentalpha))
        return self.send_request(4, buf, is_checked=is_checked)
    def ChangePicture(self, picture, value_mask, value_list, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", picture, value_mask))
        if value_mask & CP.Repeat:
            repeat = value_list.pop(0)
            buf.write(struct.pack("=I", repeat))
        if value_mask & CP.AlphaMap:
            alphamap = value_list.pop(0)
            buf.write(struct.pack("=I", alphamap))
        if value_mask & CP.AlphaXOrigin:
            alphaxorigin = value_list.pop(0)
            buf.write(struct.pack("=i", alphaxorigin))
        if value_mask & CP.AlphaYOrigin:
            alphayorigin = value_list.pop(0)
            buf.write(struct.pack("=i", alphayorigin))
        if value_mask & CP.ClipXOrigin:
            clipxorigin = value_list.pop(0)
            buf.write(struct.pack("=i", clipxorigin))
        if value_mask & CP.ClipYOrigin:
            clipyorigin = value_list.pop(0)
            buf.write(struct.pack("=i", clipyorigin))
        if value_mask & CP.ClipMask:
            clipmask = value_list.pop(0)
            buf.write(struct.pack("=I", clipmask))
        if value_mask & CP.GraphicsExposure:
            graphicsexposure = value_list.pop(0)
            buf.write(struct.pack("=I", graphicsexposure))
        if value_mask & CP.SubwindowMode:
            subwindowmode = value_list.pop(0)
            buf.write(struct.pack("=I", subwindowmode))
        if value_mask & CP.PolyEdge:
            polyedge = value_list.pop(0)
            buf.write(struct.pack("=I", polyedge))
        if value_mask & CP.PolyMode:
            polymode = value_list.pop(0)
            buf.write(struct.pack("=I", polymode))
        if value_mask & CP.Dither:
            dither = value_list.pop(0)
            buf.write(struct.pack("=I", dither))
        if value_mask & CP.ComponentAlpha:
            componentalpha = value_list.pop(0)
            buf.write(struct.pack("=I", componentalpha))
        return self.send_request(5, buf, is_checked=is_checked)
    def SetPictureClipRectangles(self, picture, clip_x_origin, clip_y_origin, rectangles_len, rectangles, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIhh", picture, clip_x_origin, clip_y_origin))
        buf.write(xcffib.pack_list(rectangles, xproto.RECTANGLE))
        return self.send_request(6, buf, is_checked=is_checked)
    def FreePicture(self, picture, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", picture))
        return self.send_request(7, buf, is_checked=is_checked)
    def Composite(self, op, src, mask, dst, src_x, src_y, mask_x, mask_y, dst_x, dst_y, width, height, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xB3xIIIhhhhhhHH", op, src, mask, dst, src_x, src_y, mask_x, mask_y, dst_x, dst_y, width, height))
        return self.send_request(8, buf, is_checked=is_checked)
    def Trapezoids(self, op, src, dst, mask_format, src_x, src_y, traps_len, traps, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xB3xIIIhh", op, src, dst, mask_format, src_x, src_y))
        buf.write(xcffib.pack_list(traps, TRAPEZOID))
        return self.send_request(10, buf, is_checked=is_checked)
    def Triangles(self, op, src, dst, mask_format, src_x, src_y, triangles_len, triangles, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xB3xIIIhh", op, src, dst, mask_format, src_x, src_y))
        buf.write(xcffib.pack_list(triangles, TRIANGLE))
        return self.send_request(11, buf, is_checked=is_checked)
    def TriStrip(self, op, src, dst, mask_format, src_x, src_y, points_len, points, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xB3xIIIhh", op, src, dst, mask_format, src_x, src_y))
        buf.write(xcffib.pack_list(points, POINTFIX))
        return self.send_request(12, buf, is_checked=is_checked)
    def TriFan(self, op, src, dst, mask_format, src_x, src_y, points_len, points, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xB3xIIIhh", op, src, dst, mask_format, src_x, src_y))
        buf.write(xcffib.pack_list(points, POINTFIX))
        return self.send_request(13, buf, is_checked=is_checked)
    def CreateGlyphSet(self, gsid, format, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", gsid, format))
        return self.send_request(17, buf, is_checked=is_checked)
    def ReferenceGlyphSet(self, gsid, existing, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", gsid, existing))
        return self.send_request(18, buf, is_checked=is_checked)
    def FreeGlyphSet(self, glyphset, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", glyphset))
        return self.send_request(19, buf, is_checked=is_checked)
    def AddGlyphs(self, glyphset, glyphs_len, glyphids, glyphs, data_len, data, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", glyphset, glyphs_len))
        buf.write(xcffib.pack_list(glyphids, "I"))
        buf.write(xcffib.pack_list(glyphs, GLYPHINFO))
        buf.write(xcffib.pack_list(data, "B"))
        return self.send_request(20, buf, is_checked=is_checked)
    def FreeGlyphs(self, glyphset, glyphs_len, glyphs, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", glyphset))
        buf.write(xcffib.pack_list(glyphs, "I"))
        return self.send_request(22, buf, is_checked=is_checked)
    def CompositeGlyphs8(self, op, src, dst, mask_format, glyphset, src_x, src_y, glyphcmds_len, glyphcmds, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xB3xIIIIhh", op, src, dst, mask_format, glyphset, src_x, src_y))
        buf.write(xcffib.pack_list(glyphcmds, "B"))
        return self.send_request(23, buf, is_checked=is_checked)
    def CompositeGlyphs16(self, op, src, dst, mask_format, glyphset, src_x, src_y, glyphcmds_len, glyphcmds, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xB3xIIIIhh", op, src, dst, mask_format, glyphset, src_x, src_y))
        buf.write(xcffib.pack_list(glyphcmds, "B"))
        return self.send_request(24, buf, is_checked=is_checked)
    def CompositeGlyphs32(self, op, src, dst, mask_format, glyphset, src_x, src_y, glyphcmds_len, glyphcmds, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xB3xIIIIhh", op, src, dst, mask_format, glyphset, src_x, src_y))
        buf.write(xcffib.pack_list(glyphcmds, "B"))
        return self.send_request(25, buf, is_checked=is_checked)
    def FillRectangles(self, op, dst, color, rects_len, rects, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xB3xI", op, dst))
        buf.write(color.pack() if hasattr(color, "pack") else COLOR.synthetic(*color).pack())
        buf.write(xcffib.pack_list(rects, xproto.RECTANGLE))
        return self.send_request(26, buf, is_checked=is_checked)
    def CreateCursor(self, cid, source, x, y, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIHH", cid, source, x, y))
        return self.send_request(27, buf, is_checked=is_checked)
    def SetPictureTransform(self, picture, transform, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", picture))
        buf.write(transform.pack() if hasattr(transform, "pack") else TRANSFORM.synthetic(*transform).pack())
        return self.send_request(28, buf, is_checked=is_checked)
    def QueryFilters(self, drawable, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", drawable))
        return self.send_request(29, buf, QueryFiltersCookie, is_checked=is_checked)
    def SetPictureFilter(self, picture, filter_len, filter, values_len, values, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIH2x", picture, filter_len))
        buf.write(xcffib.pack_list(filter, "c"))
        buf.write(struct.pack("=4x", ))
        buf.write(xcffib.pack_list(values, "i"))
        return self.send_request(30, buf, is_checked=is_checked)
    def CreateAnimCursor(self, cid, cursors_len, cursors, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", cid))
        buf.write(xcffib.pack_list(cursors, ANIMCURSORELT))
        return self.send_request(31, buf, is_checked=is_checked)
    def AddTraps(self, picture, x_off, y_off, traps_len, traps, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIhh", picture, x_off, y_off))
        buf.write(xcffib.pack_list(traps, TRAP))
        return self.send_request(32, buf, is_checked=is_checked)
    def CreateSolidFill(self, picture, color, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", picture))
        buf.write(color.pack() if hasattr(color, "pack") else COLOR.synthetic(*color).pack())
        return self.send_request(33, buf, is_checked=is_checked)
    def CreateLinearGradient(self, picture, p1, p2, num_stops, stops, colors, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", picture))
        buf.write(p1.pack() if hasattr(p1, "pack") else POINTFIX.synthetic(*p1).pack())
        buf.write(p2.pack() if hasattr(p2, "pack") else POINTFIX.synthetic(*p2).pack())
        buf.write(struct.pack("=I", num_stops))
        buf.write(xcffib.pack_list(stops, "i"))
        buf.write(xcffib.pack_list(colors, COLOR))
        return self.send_request(34, buf, is_checked=is_checked)
    def CreateRadialGradient(self, picture, inner, outer, inner_radius, outer_radius, num_stops, stops, colors, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", picture))
        buf.write(inner.pack() if hasattr(inner, "pack") else POINTFIX.synthetic(*inner).pack())
        buf.write(outer.pack() if hasattr(outer, "pack") else POINTFIX.synthetic(*outer).pack())
        buf.write(struct.pack("=i", inner_radius))
        buf.write(struct.pack("=i", outer_radius))
        buf.write(struct.pack("=I", num_stops))
        buf.write(xcffib.pack_list(stops, "i"))
        buf.write(xcffib.pack_list(colors, COLOR))
        return self.send_request(35, buf, is_checked=is_checked)
    def CreateConicalGradient(self, picture, center, angle, num_stops, stops, colors, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", picture))
        buf.write(center.pack() if hasattr(center, "pack") else POINTFIX.synthetic(*center).pack())
        buf.write(struct.pack("=i", angle))
        buf.write(struct.pack("=I", num_stops))
        buf.write(xcffib.pack_list(stops, "i"))
        buf.write(xcffib.pack_list(colors, COLOR))
        return self.send_request(36, buf, is_checked=is_checked)
xcffib._add_ext(key, renderExtension, _events, _errors)
