import xcffib
import struct
import io
MAJOR_VERSION = 1
MINOR_VERSION = 6
key = xcffib.ExtensionKey("RANDR")
_events = {}
_errors = {}
from . import xproto
from . import render
class BadOutputError(xcffib.Error):
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
BadBadOutput = BadOutputError
_errors[0] = BadOutputError
class BadCrtcError(xcffib.Error):
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
BadBadCrtc = BadCrtcError
_errors[1] = BadCrtcError
class BadModeError(xcffib.Error):
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
BadBadMode = BadModeError
_errors[2] = BadModeError
class BadProviderError(xcffib.Error):
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
BadBadProvider = BadProviderError
_errors[3] = BadProviderError
class Rotation:
    Rotate_0 = 1 << 0
    Rotate_90 = 1 << 1
    Rotate_180 = 1 << 2
    Rotate_270 = 1 << 3
    Reflect_X = 1 << 4
    Reflect_Y = 1 << 5
class ScreenSize(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.width, self.height, self.mwidth, self.mheight = unpacker.unpack("HHHH")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=HHHH", self.width, self.height, self.mwidth, self.mheight))
        return buf.getvalue()
    fixed_size = 8
    @classmethod
    def synthetic(cls, width, height, mwidth, mheight):
        self = cls.__new__(cls)
        self.width = width
        self.height = height
        self.mwidth = mwidth
        self.mheight = mheight
        return self
class RefreshRates(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.nRates, = unpacker.unpack("H")
        self.rates = xcffib.List(unpacker, "H", self.nRates)
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=H", self.nRates))
        buf.write(xcffib.pack_list(self.rates, "H"))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, nRates, rates):
        self = cls.__new__(cls)
        self.nRates = nRates
        self.rates = rates
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
class SetConfig:
    Success = 0
    InvalidConfigTime = 1
    InvalidTime = 2
    Failed = 3
class SetScreenConfigReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.status, self.new_timestamp, self.config_timestamp, self.root, self.subpixel_order = unpacker.unpack("xB2x4xIIIH10x")
        self.bufsize = unpacker.offset - base
class SetScreenConfigCookie(xcffib.Cookie):
    reply_type = SetScreenConfigReply
class NotifyMask:
    ScreenChange = 1 << 0
    CrtcChange = 1 << 1
    OutputChange = 1 << 2
    OutputProperty = 1 << 3
    ProviderChange = 1 << 4
    ProviderProperty = 1 << 5
    ResourceChange = 1 << 6
    Lease = 1 << 7
class GetScreenInfoReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.rotations, self.root, self.timestamp, self.config_timestamp, self.nSizes, self.sizeID, self.rotation, self.rate, self.nInfo = unpacker.unpack("xB2x4xIIIHHHHH2x")
        self.sizes = xcffib.List(unpacker, ScreenSize, self.nSizes)
        unpacker.pad(RefreshRates)
        self.rates = xcffib.List(unpacker, RefreshRates, self.nInfo - self.nSizes)
        self.bufsize = unpacker.offset - base
class GetScreenInfoCookie(xcffib.Cookie):
    reply_type = GetScreenInfoReply
class GetScreenSizeRangeReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.min_width, self.min_height, self.max_width, self.max_height = unpacker.unpack("xx2x4xHHHH16x")
        self.bufsize = unpacker.offset - base
class GetScreenSizeRangeCookie(xcffib.Cookie):
    reply_type = GetScreenSizeRangeReply
class ModeFlag:
    HsyncPositive = 1 << 0
    HsyncNegative = 1 << 1
    VsyncPositive = 1 << 2
    VsyncNegative = 1 << 3
    Interlace = 1 << 4
    DoubleScan = 1 << 5
    Csync = 1 << 6
    CsyncPositive = 1 << 7
    CsyncNegative = 1 << 8
    HskewPresent = 1 << 9
    Bcast = 1 << 10
    PixelMultiplex = 1 << 11
    DoubleClock = 1 << 12
    HalveClock = 1 << 13
class ModeInfo(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.id, self.width, self.height, self.dot_clock, self.hsync_start, self.hsync_end, self.htotal, self.hskew, self.vsync_start, self.vsync_end, self.vtotal, self.name_len, self.mode_flags = unpacker.unpack("IHHIHHHHHHHHI")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=IHHIHHHHHHHHI", self.id, self.width, self.height, self.dot_clock, self.hsync_start, self.hsync_end, self.htotal, self.hskew, self.vsync_start, self.vsync_end, self.vtotal, self.name_len, self.mode_flags))
        return buf.getvalue()
    fixed_size = 32
    @classmethod
    def synthetic(cls, id, width, height, dot_clock, hsync_start, hsync_end, htotal, hskew, vsync_start, vsync_end, vtotal, name_len, mode_flags):
        self = cls.__new__(cls)
        self.id = id
        self.width = width
        self.height = height
        self.dot_clock = dot_clock
        self.hsync_start = hsync_start
        self.hsync_end = hsync_end
        self.htotal = htotal
        self.hskew = hskew
        self.vsync_start = vsync_start
        self.vsync_end = vsync_end
        self.vtotal = vtotal
        self.name_len = name_len
        self.mode_flags = mode_flags
        return self
class GetScreenResourcesReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.timestamp, self.config_timestamp, self.num_crtcs, self.num_outputs, self.num_modes, self.names_len = unpacker.unpack("xx2x4xIIHHHH8x")
        self.crtcs = xcffib.List(unpacker, "I", self.num_crtcs)
        unpacker.pad("I")
        self.outputs = xcffib.List(unpacker, "I", self.num_outputs)
        unpacker.pad(ModeInfo)
        self.modes = xcffib.List(unpacker, ModeInfo, self.num_modes)
        unpacker.pad("B")
        self.names = xcffib.List(unpacker, "B", self.names_len)
        self.bufsize = unpacker.offset - base
class GetScreenResourcesCookie(xcffib.Cookie):
    reply_type = GetScreenResourcesReply
class Connection:
    Connected = 0
    Disconnected = 1
    Unknown = 2
class GetOutputInfoReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.status, self.timestamp, self.crtc, self.mm_width, self.mm_height, self.connection, self.subpixel_order, self.num_crtcs, self.num_modes, self.num_preferred, self.num_clones, self.name_len = unpacker.unpack("xB2x4xIIIIBBHHHHH")
        self.crtcs = xcffib.List(unpacker, "I", self.num_crtcs)
        unpacker.pad("I")
        self.modes = xcffib.List(unpacker, "I", self.num_modes)
        unpacker.pad("I")
        self.clones = xcffib.List(unpacker, "I", self.num_clones)
        unpacker.pad("B")
        self.name = xcffib.List(unpacker, "B", self.name_len)
        self.bufsize = unpacker.offset - base
class GetOutputInfoCookie(xcffib.Cookie):
    reply_type = GetOutputInfoReply
class ListOutputPropertiesReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.num_atoms, = unpacker.unpack("xx2x4xH22x")
        self.atoms = xcffib.List(unpacker, "I", self.num_atoms)
        self.bufsize = unpacker.offset - base
class ListOutputPropertiesCookie(xcffib.Cookie):
    reply_type = ListOutputPropertiesReply
class QueryOutputPropertyReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.pending, self.range, self.immutable = unpacker.unpack("xx2x4xBBB21x")
        self.validValues = xcffib.List(unpacker, "i", self.length)
        self.bufsize = unpacker.offset - base
class QueryOutputPropertyCookie(xcffib.Cookie):
    reply_type = QueryOutputPropertyReply
class GetOutputPropertyReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.format, self.type, self.bytes_after, self.num_items = unpacker.unpack("xB2x4xIII12x")
        self.data = xcffib.List(unpacker, "B", self.num_items * (self.format // 8))
        self.bufsize = unpacker.offset - base
class GetOutputPropertyCookie(xcffib.Cookie):
    reply_type = GetOutputPropertyReply
class CreateModeReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.mode, = unpacker.unpack("xx2x4xI20x")
        self.bufsize = unpacker.offset - base
class CreateModeCookie(xcffib.Cookie):
    reply_type = CreateModeReply
class GetCrtcInfoReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.status, self.timestamp, self.x, self.y, self.width, self.height, self.mode, self.rotation, self.rotations, self.num_outputs, self.num_possible_outputs = unpacker.unpack("xB2x4xIhhHHIHHHH")
        self.outputs = xcffib.List(unpacker, "I", self.num_outputs)
        unpacker.pad("I")
        self.possible = xcffib.List(unpacker, "I", self.num_possible_outputs)
        self.bufsize = unpacker.offset - base
class GetCrtcInfoCookie(xcffib.Cookie):
    reply_type = GetCrtcInfoReply
class SetCrtcConfigReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.status, self.timestamp = unpacker.unpack("xB2x4xI20x")
        self.bufsize = unpacker.offset - base
class SetCrtcConfigCookie(xcffib.Cookie):
    reply_type = SetCrtcConfigReply
class GetCrtcGammaSizeReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.size, = unpacker.unpack("xx2x4xH22x")
        self.bufsize = unpacker.offset - base
class GetCrtcGammaSizeCookie(xcffib.Cookie):
    reply_type = GetCrtcGammaSizeReply
class GetCrtcGammaReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.size, = unpacker.unpack("xx2x4xH22x")
        self.red = xcffib.List(unpacker, "H", self.size)
        unpacker.pad("H")
        self.green = xcffib.List(unpacker, "H", self.size)
        unpacker.pad("H")
        self.blue = xcffib.List(unpacker, "H", self.size)
        self.bufsize = unpacker.offset - base
class GetCrtcGammaCookie(xcffib.Cookie):
    reply_type = GetCrtcGammaReply
class GetScreenResourcesCurrentReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.timestamp, self.config_timestamp, self.num_crtcs, self.num_outputs, self.num_modes, self.names_len = unpacker.unpack("xx2x4xIIHHHH8x")
        self.crtcs = xcffib.List(unpacker, "I", self.num_crtcs)
        unpacker.pad("I")
        self.outputs = xcffib.List(unpacker, "I", self.num_outputs)
        unpacker.pad(ModeInfo)
        self.modes = xcffib.List(unpacker, ModeInfo, self.num_modes)
        unpacker.pad("B")
        self.names = xcffib.List(unpacker, "B", self.names_len)
        self.bufsize = unpacker.offset - base
class GetScreenResourcesCurrentCookie(xcffib.Cookie):
    reply_type = GetScreenResourcesCurrentReply
class Transform:
    Unit = 1 << 0
    ScaleUp = 1 << 1
    ScaleDown = 1 << 2
    Projective = 1 << 3
class GetCrtcTransformReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        unpacker.unpack("xx2x4x")
        self.pending_transform = render.TRANSFORM(unpacker)
        self.has_transforms, = unpacker.unpack("B3x")
        unpacker.pad(render.TRANSFORM)
        self.current_transform = render.TRANSFORM(unpacker)
        self.pending_len, self.pending_nparams, self.current_len, self.current_nparams = unpacker.unpack("4xHHHH")
        unpacker.pad("c")
        self.pending_filter_name = xcffib.List(unpacker, "c", self.pending_len)
        unpacker.pad("i")
        self.pending_params = xcffib.List(unpacker, "i", self.pending_nparams)
        unpacker.pad("c")
        self.current_filter_name = xcffib.List(unpacker, "c", self.current_len)
        unpacker.pad("i")
        self.current_params = xcffib.List(unpacker, "i", self.current_nparams)
        self.bufsize = unpacker.offset - base
class GetCrtcTransformCookie(xcffib.Cookie):
    reply_type = GetCrtcTransformReply
class GetPanningReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.status, self.timestamp, self.left, self.top, self.width, self.height, self.track_left, self.track_top, self.track_width, self.track_height, self.border_left, self.border_top, self.border_right, self.border_bottom = unpacker.unpack("xB2x4xIHHHHHHHHhhhh")
        self.bufsize = unpacker.offset - base
class GetPanningCookie(xcffib.Cookie):
    reply_type = GetPanningReply
class SetPanningReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.status, self.timestamp = unpacker.unpack("xB2x4xI")
        self.bufsize = unpacker.offset - base
class SetPanningCookie(xcffib.Cookie):
    reply_type = SetPanningReply
class GetOutputPrimaryReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.output, = unpacker.unpack("xx2x4xI")
        self.bufsize = unpacker.offset - base
class GetOutputPrimaryCookie(xcffib.Cookie):
    reply_type = GetOutputPrimaryReply
class GetProvidersReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.timestamp, self.num_providers = unpacker.unpack("xx2x4xIH18x")
        self.providers = xcffib.List(unpacker, "I", self.num_providers)
        self.bufsize = unpacker.offset - base
class GetProvidersCookie(xcffib.Cookie):
    reply_type = GetProvidersReply
class ProviderCapability:
    SourceOutput = 1 << 0
    SinkOutput = 1 << 1
    SourceOffload = 1 << 2
    SinkOffload = 1 << 3
class GetProviderInfoReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.status, self.timestamp, self.capabilities, self.num_crtcs, self.num_outputs, self.num_associated_providers, self.name_len = unpacker.unpack("xB2x4xIIHHHH8x")
        self.crtcs = xcffib.List(unpacker, "I", self.num_crtcs)
        unpacker.pad("I")
        self.outputs = xcffib.List(unpacker, "I", self.num_outputs)
        unpacker.pad("I")
        self.associated_providers = xcffib.List(unpacker, "I", self.num_associated_providers)
        unpacker.pad("I")
        self.associated_capability = xcffib.List(unpacker, "I", self.num_associated_providers)
        unpacker.pad("c")
        self.name = xcffib.List(unpacker, "c", self.name_len)
        self.bufsize = unpacker.offset - base
class GetProviderInfoCookie(xcffib.Cookie):
    reply_type = GetProviderInfoReply
class ListProviderPropertiesReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.num_atoms, = unpacker.unpack("xx2x4xH22x")
        self.atoms = xcffib.List(unpacker, "I", self.num_atoms)
        self.bufsize = unpacker.offset - base
class ListProviderPropertiesCookie(xcffib.Cookie):
    reply_type = ListProviderPropertiesReply
class QueryProviderPropertyReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.pending, self.range, self.immutable = unpacker.unpack("xx2x4xBBB21x")
        self.valid_values = xcffib.List(unpacker, "i", self.length)
        self.bufsize = unpacker.offset - base
class QueryProviderPropertyCookie(xcffib.Cookie):
    reply_type = QueryProviderPropertyReply
class GetProviderPropertyReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.format, self.type, self.bytes_after, self.num_items = unpacker.unpack("xB2x4xIII12x")
        self.data = xcffib.List(unpacker, "c", self.num_items * (self.format // 8))
        self.bufsize = unpacker.offset - base
class GetProviderPropertyCookie(xcffib.Cookie):
    reply_type = GetProviderPropertyReply
class ScreenChangeNotifyEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.rotation, self.timestamp, self.config_timestamp, self.root, self.request_window, self.sizeID, self.subpixel_order, self.width, self.height, self.mwidth, self.mheight = unpacker.unpack("xB2xIIIIHHHHHH")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 0))
        buf.write(struct.pack("=B2xIIIIHHHHHH", self.rotation, self.timestamp, self.config_timestamp, self.root, self.request_window, self.sizeID, self.subpixel_order, self.width, self.height, self.mwidth, self.mheight))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, rotation, timestamp, config_timestamp, root, request_window, sizeID, subpixel_order, width, height, mwidth, mheight):
        self = cls.__new__(cls)
        self.rotation = rotation
        self.timestamp = timestamp
        self.config_timestamp = config_timestamp
        self.root = root
        self.request_window = request_window
        self.sizeID = sizeID
        self.subpixel_order = subpixel_order
        self.width = width
        self.height = height
        self.mwidth = mwidth
        self.mheight = mheight
        return self
_events[0] = ScreenChangeNotifyEvent
class Notify:
    CrtcChange = 0
    OutputChange = 1
    OutputProperty = 2
    ProviderChange = 3
    ProviderProperty = 4
    ResourceChange = 5
    Lease = 6
class CrtcChange(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.timestamp, self.window, self.crtc, self.mode, self.rotation, self.x, self.y, self.width, self.height = unpacker.unpack("IIIIH2xhhHH")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=IIIIH2xhhHH", self.timestamp, self.window, self.crtc, self.mode, self.rotation, self.x, self.y, self.width, self.height))
        return buf.getvalue()
    fixed_size = 28
    @classmethod
    def synthetic(cls, timestamp, window, crtc, mode, rotation, x, y, width, height):
        self = cls.__new__(cls)
        self.timestamp = timestamp
        self.window = window
        self.crtc = crtc
        self.mode = mode
        self.rotation = rotation
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        return self
class OutputChange(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.timestamp, self.config_timestamp, self.window, self.output, self.crtc, self.mode, self.rotation, self.connection, self.subpixel_order = unpacker.unpack("IIIIIIHBB")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=IIIIIIHBB", self.timestamp, self.config_timestamp, self.window, self.output, self.crtc, self.mode, self.rotation, self.connection, self.subpixel_order))
        return buf.getvalue()
    fixed_size = 28
    @classmethod
    def synthetic(cls, timestamp, config_timestamp, window, output, crtc, mode, rotation, connection, subpixel_order):
        self = cls.__new__(cls)
        self.timestamp = timestamp
        self.config_timestamp = config_timestamp
        self.window = window
        self.output = output
        self.crtc = crtc
        self.mode = mode
        self.rotation = rotation
        self.connection = connection
        self.subpixel_order = subpixel_order
        return self
class OutputProperty(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.window, self.output, self.atom, self.timestamp, self.status = unpacker.unpack("IIIIB11x")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=IIIIB11x", self.window, self.output, self.atom, self.timestamp, self.status))
        return buf.getvalue()
    fixed_size = 28
    @classmethod
    def synthetic(cls, window, output, atom, timestamp, status):
        self = cls.__new__(cls)
        self.window = window
        self.output = output
        self.atom = atom
        self.timestamp = timestamp
        self.status = status
        return self
class ProviderChange(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.timestamp, self.window, self.provider = unpacker.unpack("III16x")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=III16x", self.timestamp, self.window, self.provider))
        return buf.getvalue()
    fixed_size = 28
    @classmethod
    def synthetic(cls, timestamp, window, provider):
        self = cls.__new__(cls)
        self.timestamp = timestamp
        self.window = window
        self.provider = provider
        return self
class ProviderProperty(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.window, self.provider, self.atom, self.timestamp, self.state = unpacker.unpack("IIIIB11x")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=IIIIB11x", self.window, self.provider, self.atom, self.timestamp, self.state))
        return buf.getvalue()
    fixed_size = 28
    @classmethod
    def synthetic(cls, window, provider, atom, timestamp, state):
        self = cls.__new__(cls)
        self.window = window
        self.provider = provider
        self.atom = atom
        self.timestamp = timestamp
        self.state = state
        return self
class ResourceChange(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.timestamp, self.window = unpacker.unpack("II20x")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=II20x", self.timestamp, self.window))
        return buf.getvalue()
    fixed_size = 28
    @classmethod
    def synthetic(cls, timestamp, window):
        self = cls.__new__(cls)
        self.timestamp = timestamp
        self.window = window
        return self
class MonitorInfo(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.name, self.primary, self.automatic, self.nOutput, self.x, self.y, self.width, self.height, self.width_in_millimeters, self.height_in_millimeters = unpacker.unpack("IBBHhhHHII")
        self.outputs = xcffib.List(unpacker, "I", self.nOutput)
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=IBBHhhHHII", self.name, self.primary, self.automatic, self.nOutput, self.x, self.y, self.width, self.height, self.width_in_millimeters, self.height_in_millimeters))
        buf.write(xcffib.pack_list(self.outputs, "I"))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, name, primary, automatic, nOutput, x, y, width, height, width_in_millimeters, height_in_millimeters, outputs):
        self = cls.__new__(cls)
        self.name = name
        self.primary = primary
        self.automatic = automatic
        self.nOutput = nOutput
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.width_in_millimeters = width_in_millimeters
        self.height_in_millimeters = height_in_millimeters
        self.outputs = outputs
        return self
class GetMonitorsReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.timestamp, self.nMonitors, self.nOutputs = unpacker.unpack("xx2x4xIII12x")
        self.monitors = xcffib.List(unpacker, MonitorInfo, self.nMonitors)
        self.bufsize = unpacker.offset - base
class GetMonitorsCookie(xcffib.Cookie):
    reply_type = GetMonitorsReply
class CreateLeaseReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.nfd, = unpacker.unpack("xB2x4x24x")
        self.bufsize = unpacker.offset - base
class CreateLeaseCookie(xcffib.Cookie):
    reply_type = CreateLeaseReply
class LeaseNotify(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.timestamp, self.window, self.lease, self.created = unpacker.unpack("IIIB15x")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=IIIB15x", self.timestamp, self.window, self.lease, self.created))
        return buf.getvalue()
    fixed_size = 28
    @classmethod
    def synthetic(cls, timestamp, window, lease, created):
        self = cls.__new__(cls)
        self.timestamp = timestamp
        self.window = window
        self.lease = lease
        self.created = created
        return self
class NotifyData(xcffib.Union):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Union.__init__(self, unpacker)
        self.cc = CrtcChange(unpacker.copy())
        self.oc = OutputChange(unpacker.copy())
        self.op = OutputProperty(unpacker.copy())
        self.pc = ProviderChange(unpacker.copy())
        self.pp = ProviderProperty(unpacker.copy())
        self.rc = ResourceChange(unpacker.copy())
        self.lc = LeaseNotify(unpacker.copy())
    def pack(self):
        buf = io.BytesIO()
        buf.write(self.cc.pack() if hasattr(self.cc, "pack") else CrtcChange.synthetic(*self.cc).pack())
        return buf.getvalue()
class NotifyEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.subCode, = unpacker.unpack("xB2x")
        self.u = NotifyData(unpacker)
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 1))
        buf.write(struct.pack("=B2x", self.subCode))
        buf.write(self.u.pack() if hasattr(self.u, "pack") else NotifyData.synthetic(*self.u).pack())
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, subCode, u):
        self = cls.__new__(cls)
        self.subCode = subCode
        self.u = u
        return self
_events[1] = NotifyEvent
class randrExtension(xcffib.Extension):
    def QueryVersion(self, major_version, minor_version, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", major_version, minor_version))
        return self.send_request(0, buf, QueryVersionCookie, is_checked=is_checked)
    def SetScreenConfig(self, window, timestamp, config_timestamp, sizeID, rotation, rate, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIIHHH2x", window, timestamp, config_timestamp, sizeID, rotation, rate))
        return self.send_request(2, buf, SetScreenConfigCookie, is_checked=is_checked)
    def SelectInput(self, window, enable, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIH2x", window, enable))
        return self.send_request(4, buf, is_checked=is_checked)
    def GetScreenInfo(self, window, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", window))
        return self.send_request(5, buf, GetScreenInfoCookie, is_checked=is_checked)
    def GetScreenSizeRange(self, window, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", window))
        return self.send_request(6, buf, GetScreenSizeRangeCookie, is_checked=is_checked)
    def SetScreenSize(self, window, width, height, mm_width, mm_height, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIHHII", window, width, height, mm_width, mm_height))
        return self.send_request(7, buf, is_checked=is_checked)
    def GetScreenResources(self, window, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", window))
        return self.send_request(8, buf, GetScreenResourcesCookie, is_checked=is_checked)
    def GetOutputInfo(self, output, config_timestamp, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", output, config_timestamp))
        return self.send_request(9, buf, GetOutputInfoCookie, is_checked=is_checked)
    def ListOutputProperties(self, output, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", output))
        return self.send_request(10, buf, ListOutputPropertiesCookie, is_checked=is_checked)
    def QueryOutputProperty(self, output, property, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", output, property))
        return self.send_request(11, buf, QueryOutputPropertyCookie, is_checked=is_checked)
    def ConfigureOutputProperty(self, output, property, pending, range, values_len, values, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIBB2x", output, property, pending, range))
        buf.write(xcffib.pack_list(values, "i"))
        return self.send_request(12, buf, is_checked=is_checked)
    def ChangeOutputProperty(self, output, property, type, format, mode, num_units, data, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIIBB2xI", output, property, type, format, mode, num_units))
        buf.write(xcffib.pack_list(data, "c"))
        return self.send_request(13, buf, is_checked=is_checked)
    def DeleteOutputProperty(self, output, property, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", output, property))
        return self.send_request(14, buf, is_checked=is_checked)
    def GetOutputProperty(self, output, property, type, long_offset, long_length, delete, pending, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIIIIBB2x", output, property, type, long_offset, long_length, delete, pending))
        return self.send_request(15, buf, GetOutputPropertyCookie, is_checked=is_checked)
    def CreateMode(self, window, mode_info, name_len, name, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", window))
        buf.write(mode_info.pack() if hasattr(mode_info, "pack") else ModeInfo.synthetic(*mode_info).pack())
        buf.write(xcffib.pack_list(name, "c"))
        return self.send_request(16, buf, CreateModeCookie, is_checked=is_checked)
    def DestroyMode(self, mode, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", mode))
        return self.send_request(17, buf, is_checked=is_checked)
    def AddOutputMode(self, output, mode, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", output, mode))
        return self.send_request(18, buf, is_checked=is_checked)
    def DeleteOutputMode(self, output, mode, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", output, mode))
        return self.send_request(19, buf, is_checked=is_checked)
    def GetCrtcInfo(self, crtc, config_timestamp, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", crtc, config_timestamp))
        return self.send_request(20, buf, GetCrtcInfoCookie, is_checked=is_checked)
    def SetCrtcConfig(self, crtc, timestamp, config_timestamp, x, y, mode, rotation, outputs_len, outputs, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIIhhIH2x", crtc, timestamp, config_timestamp, x, y, mode, rotation))
        buf.write(xcffib.pack_list(outputs, "I"))
        return self.send_request(21, buf, SetCrtcConfigCookie, is_checked=is_checked)
    def GetCrtcGammaSize(self, crtc, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", crtc))
        return self.send_request(22, buf, GetCrtcGammaSizeCookie, is_checked=is_checked)
    def GetCrtcGamma(self, crtc, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", crtc))
        return self.send_request(23, buf, GetCrtcGammaCookie, is_checked=is_checked)
    def SetCrtcGamma(self, crtc, size, red, green, blue, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIH2x", crtc, size))
        buf.write(xcffib.pack_list(red, "H"))
        buf.write(xcffib.pack_list(green, "H"))
        buf.write(xcffib.pack_list(blue, "H"))
        return self.send_request(24, buf, is_checked=is_checked)
    def GetScreenResourcesCurrent(self, window, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", window))
        return self.send_request(25, buf, GetScreenResourcesCurrentCookie, is_checked=is_checked)
    def SetCrtcTransform(self, crtc, transform, filter_len, filter_name, filter_params_len, filter_params, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", crtc))
        buf.write(transform.pack() if hasattr(transform, "pack") else render.TRANSFORM.synthetic(*transform).pack())
        buf.write(struct.pack("=H", filter_len))
        buf.write(struct.pack("=2x", ))
        buf.write(xcffib.pack_list(filter_name, "c"))
        buf.write(struct.pack("=4x", ))
        buf.write(xcffib.pack_list(filter_params, "i"))
        return self.send_request(26, buf, is_checked=is_checked)
    def GetCrtcTransform(self, crtc, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", crtc))
        return self.send_request(27, buf, GetCrtcTransformCookie, is_checked=is_checked)
    def GetPanning(self, crtc, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", crtc))
        return self.send_request(28, buf, GetPanningCookie, is_checked=is_checked)
    def SetPanning(self, crtc, timestamp, left, top, width, height, track_left, track_top, track_width, track_height, border_left, border_top, border_right, border_bottom, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIHHHHHHHHhhhh", crtc, timestamp, left, top, width, height, track_left, track_top, track_width, track_height, border_left, border_top, border_right, border_bottom))
        return self.send_request(29, buf, SetPanningCookie, is_checked=is_checked)
    def SetOutputPrimary(self, window, output, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", window, output))
        return self.send_request(30, buf, is_checked=is_checked)
    def GetOutputPrimary(self, window, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", window))
        return self.send_request(31, buf, GetOutputPrimaryCookie, is_checked=is_checked)
    def GetProviders(self, window, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", window))
        return self.send_request(32, buf, GetProvidersCookie, is_checked=is_checked)
    def GetProviderInfo(self, provider, config_timestamp, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", provider, config_timestamp))
        return self.send_request(33, buf, GetProviderInfoCookie, is_checked=is_checked)
    def SetProviderOffloadSink(self, provider, sink_provider, config_timestamp, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIII", provider, sink_provider, config_timestamp))
        return self.send_request(34, buf, is_checked=is_checked)
    def SetProviderOutputSource(self, provider, source_provider, config_timestamp, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIII", provider, source_provider, config_timestamp))
        return self.send_request(35, buf, is_checked=is_checked)
    def ListProviderProperties(self, provider, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", provider))
        return self.send_request(36, buf, ListProviderPropertiesCookie, is_checked=is_checked)
    def QueryProviderProperty(self, provider, property, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", provider, property))
        return self.send_request(37, buf, QueryProviderPropertyCookie, is_checked=is_checked)
    def ConfigureProviderProperty(self, provider, property, pending, range, values_len, values, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIBB2x", provider, property, pending, range))
        buf.write(xcffib.pack_list(values, "i"))
        return self.send_request(38, buf, is_checked=is_checked)
    def ChangeProviderProperty(self, provider, property, type, format, mode, num_items, data, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIIBB2xI", provider, property, type, format, mode, num_items))
        buf.write(xcffib.pack_list(data, "c"))
        return self.send_request(39, buf, is_checked=is_checked)
    def DeleteProviderProperty(self, provider, property, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", provider, property))
        return self.send_request(40, buf, is_checked=is_checked)
    def GetProviderProperty(self, provider, property, type, long_offset, long_length, delete, pending, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIIIIBB2x", provider, property, type, long_offset, long_length, delete, pending))
        return self.send_request(41, buf, GetProviderPropertyCookie, is_checked=is_checked)
    def GetMonitors(self, window, get_active, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIB", window, get_active))
        return self.send_request(42, buf, GetMonitorsCookie, is_checked=is_checked)
    def SetMonitor(self, window, monitorinfo, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", window))
        buf.write(monitorinfo.pack() if hasattr(monitorinfo, "pack") else MonitorInfo.synthetic(*monitorinfo).pack())
        return self.send_request(43, buf, is_checked=is_checked)
    def DeleteMonitor(self, window, name, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", window, name))
        return self.send_request(44, buf, is_checked=is_checked)
    def CreateLease(self, window, lid, num_crtcs, num_outputs, crtcs, outputs, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIHH", window, lid, num_crtcs, num_outputs))
        buf.write(xcffib.pack_list(crtcs, "I"))
        buf.write(xcffib.pack_list(outputs, "I"))
        return self.send_request(45, buf, CreateLeaseCookie, is_checked=is_checked)
    def FreeLease(self, lid, terminate, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIB", lid, terminate))
        return self.send_request(46, buf, is_checked=is_checked)
xcffib._add_ext(key, randrExtension, _events, _errors)
