import xcffib
import struct
import io
MAJOR_VERSION = 2
MINOR_VERSION = 2
key = xcffib.ExtensionKey("XFree86-VidModeExtension")
_events = {}
_errors = {}
class ModeFlag:
    Positive_HSync = 1 << 0
    Negative_HSync = 1 << 1
    Positive_VSync = 1 << 2
    Negative_VSync = 1 << 3
    Interlace = 1 << 4
    Composite_Sync = 1 << 5
    Positive_CSync = 1 << 6
    Negative_CSync = 1 << 7
    HSkew = 1 << 8
    Broadcast = 1 << 9
    Pixmux = 1 << 10
    Double_Clock = 1 << 11
    Half_Clock = 1 << 12
class ClockFlag:
    Programable = 1 << 0
class Permission:
    Read = 1 << 0
    Write = 1 << 1
class ModeInfo(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.dotclock, self.hdisplay, self.hsyncstart, self.hsyncend, self.htotal, self.hskew, self.vdisplay, self.vsyncstart, self.vsyncend, self.vtotal, self.flags, self.privsize = unpacker.unpack("IHHHHIHHHH4xI12xI")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=IHHHHIHHHH4xI12xI", self.dotclock, self.hdisplay, self.hsyncstart, self.hsyncend, self.htotal, self.hskew, self.vdisplay, self.vsyncstart, self.vsyncend, self.vtotal, self.flags, self.privsize))
        return buf.getvalue()
    fixed_size = 48
    @classmethod
    def synthetic(cls, dotclock, hdisplay, hsyncstart, hsyncend, htotal, hskew, vdisplay, vsyncstart, vsyncend, vtotal, flags, privsize):
        self = cls.__new__(cls)
        self.dotclock = dotclock
        self.hdisplay = hdisplay
        self.hsyncstart = hsyncstart
        self.hsyncend = hsyncend
        self.htotal = htotal
        self.hskew = hskew
        self.vdisplay = vdisplay
        self.vsyncstart = vsyncstart
        self.vsyncend = vsyncend
        self.vtotal = vtotal
        self.flags = flags
        self.privsize = privsize
        return self
class QueryVersionReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.major_version, self.minor_version = unpacker.unpack("xx2x4xHH")
        self.bufsize = unpacker.offset - base
class QueryVersionCookie(xcffib.Cookie):
    reply_type = QueryVersionReply
class GetModeLineReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.dotclock, self.hdisplay, self.hsyncstart, self.hsyncend, self.htotal, self.hskew, self.vdisplay, self.vsyncstart, self.vsyncend, self.vtotal, self.flags, self.privsize = unpacker.unpack("xx2x4xIHHHHHHHHH2xI12xI")
        self.private = xcffib.List(unpacker, "B", self.privsize)
        self.bufsize = unpacker.offset - base
class GetModeLineCookie(xcffib.Cookie):
    reply_type = GetModeLineReply
class GetMonitorReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.vendor_length, self.model_length, self.num_hsync, self.num_vsync = unpacker.unpack("xx2x4xBBBB20x")
        self.hsync = xcffib.List(unpacker, "I", self.num_hsync)
        unpacker.pad("I")
        self.vsync = xcffib.List(unpacker, "I", self.num_vsync)
        unpacker.pad("c")
        self.vendor = xcffib.List(unpacker, "c", self.vendor_length)
        unpacker.pad("c")
        self.alignment_pad = xcffib.List(unpacker, "c", ((self.vendor_length + 3) & (~ 3)) - self.vendor_length)
        unpacker.pad("c")
        self.model = xcffib.List(unpacker, "c", self.model_length)
        self.bufsize = unpacker.offset - base
class GetMonitorCookie(xcffib.Cookie):
    reply_type = GetMonitorReply
class GetAllModeLinesReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.modecount, = unpacker.unpack("xx2x4xI20x")
        self.modeinfo = xcffib.List(unpacker, ModeInfo, self.modecount)
        self.bufsize = unpacker.offset - base
class GetAllModeLinesCookie(xcffib.Cookie):
    reply_type = GetAllModeLinesReply
class ValidateModeLineReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.status, = unpacker.unpack("xx2x4xI20x")
        self.bufsize = unpacker.offset - base
class ValidateModeLineCookie(xcffib.Cookie):
    reply_type = ValidateModeLineReply
class GetViewPortReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.x, self.y = unpacker.unpack("xx2x4xII16x")
        self.bufsize = unpacker.offset - base
class GetViewPortCookie(xcffib.Cookie):
    reply_type = GetViewPortReply
class GetDotClocksReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.flags, self.clocks, self.maxclocks = unpacker.unpack("xx2x4xIII12x")
        self.clock = xcffib.List(unpacker, "I", (1 - (self.flags & 1)) * self.clocks)
        self.bufsize = unpacker.offset - base
class GetDotClocksCookie(xcffib.Cookie):
    reply_type = GetDotClocksReply
class GetGammaReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.red, self.green, self.blue = unpacker.unpack("xx2x4xIII12x")
        self.bufsize = unpacker.offset - base
class GetGammaCookie(xcffib.Cookie):
    reply_type = GetGammaReply
class GetGammaRampReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.size, = unpacker.unpack("xx2x4xH22x")
        self.red = xcffib.List(unpacker, "H", (self.size + 1) & (~ 1))
        unpacker.pad("H")
        self.green = xcffib.List(unpacker, "H", (self.size + 1) & (~ 1))
        unpacker.pad("H")
        self.blue = xcffib.List(unpacker, "H", (self.size + 1) & (~ 1))
        self.bufsize = unpacker.offset - base
class GetGammaRampCookie(xcffib.Cookie):
    reply_type = GetGammaRampReply
class GetGammaRampSizeReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.size, = unpacker.unpack("xx2x4xH22x")
        self.bufsize = unpacker.offset - base
class GetGammaRampSizeCookie(xcffib.Cookie):
    reply_type = GetGammaRampSizeReply
class GetPermissionsReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.permissions, = unpacker.unpack("xx2x4xI20x")
        self.bufsize = unpacker.offset - base
class GetPermissionsCookie(xcffib.Cookie):
    reply_type = GetPermissionsReply
class BadClockError(xcffib.Error):
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
BadBadClock = BadClockError
_errors[0] = BadClockError
class BadHTimingsError(xcffib.Error):
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
BadBadHTimings = BadHTimingsError
_errors[1] = BadHTimingsError
class BadVTimingsError(xcffib.Error):
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
BadBadVTimings = BadVTimingsError
_errors[2] = BadVTimingsError
class ModeUnsuitableError(xcffib.Error):
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
BadModeUnsuitable = ModeUnsuitableError
_errors[3] = ModeUnsuitableError
class ExtensionDisabledError(xcffib.Error):
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
BadExtensionDisabled = ExtensionDisabledError
_errors[4] = ExtensionDisabledError
class ClientNotLocalError(xcffib.Error):
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
        buf.write(struct.pack("=B", 5))
        buf.write(struct.pack("=x2x"))
        return buf.getvalue()
BadClientNotLocal = ClientNotLocalError
_errors[5] = ClientNotLocalError
class ZoomLockedError(xcffib.Error):
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
        buf.write(struct.pack("=B", 6))
        buf.write(struct.pack("=x2x"))
        return buf.getvalue()
BadZoomLocked = ZoomLockedError
_errors[6] = ZoomLockedError
class xf86vidmodeExtension(xcffib.Extension):
    def QueryVersion(self, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2x"))
        return self.send_request(0, buf, QueryVersionCookie, is_checked=is_checked)
    def GetModeLine(self, screen, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xH2x", screen))
        return self.send_request(1, buf, GetModeLineCookie, is_checked=is_checked)
    def ModModeLine(self, screen, hdisplay, hsyncstart, hsyncend, htotal, hskew, vdisplay, vsyncstart, vsyncend, vtotal, flags, privsize, private, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIHHHHHHHHH2xI12xI", screen, hdisplay, hsyncstart, hsyncend, htotal, hskew, vdisplay, vsyncstart, vsyncend, vtotal, flags, privsize))
        buf.write(xcffib.pack_list(private, "B"))
        return self.send_request(2, buf, is_checked=is_checked)
    def SwitchMode(self, screen, zoom, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xHH", screen, zoom))
        return self.send_request(3, buf, is_checked=is_checked)
    def GetMonitor(self, screen, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xH2x", screen))
        return self.send_request(4, buf, GetMonitorCookie, is_checked=is_checked)
    def LockModeSwitch(self, screen, lock, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xHH", screen, lock))
        return self.send_request(5, buf, is_checked=is_checked)
    def GetAllModeLines(self, screen, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xH2x", screen))
        return self.send_request(6, buf, GetAllModeLinesCookie, is_checked=is_checked)
    def AddModeLine(self, screen, dotclock, hdisplay, hsyncstart, hsyncend, htotal, hskew, vdisplay, vsyncstart, vsyncend, vtotal, flags, privsize, after_dotclock, after_hdisplay, after_hsyncstart, after_hsyncend, after_htotal, after_hskew, after_vdisplay, after_vsyncstart, after_vsyncend, after_vtotal, after_flags, private, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIHHHHHHHHH2xI12xIIHHHHHHHHH2xI12x", screen, dotclock, hdisplay, hsyncstart, hsyncend, htotal, hskew, vdisplay, vsyncstart, vsyncend, vtotal, flags, privsize, after_dotclock, after_hdisplay, after_hsyncstart, after_hsyncend, after_htotal, after_hskew, after_vdisplay, after_vsyncstart, after_vsyncend, after_vtotal, after_flags))
        buf.write(xcffib.pack_list(private, "B"))
        return self.send_request(7, buf, is_checked=is_checked)
    def DeleteModeLine(self, screen, dotclock, hdisplay, hsyncstart, hsyncend, htotal, hskew, vdisplay, vsyncstart, vsyncend, vtotal, flags, privsize, private, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIHHHHHHHHH2xI12xI", screen, dotclock, hdisplay, hsyncstart, hsyncend, htotal, hskew, vdisplay, vsyncstart, vsyncend, vtotal, flags, privsize))
        buf.write(xcffib.pack_list(private, "B"))
        return self.send_request(8, buf, is_checked=is_checked)
    def ValidateModeLine(self, screen, dotclock, hdisplay, hsyncstart, hsyncend, htotal, hskew, vdisplay, vsyncstart, vsyncend, vtotal, flags, privsize, private, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIHHHHHHHHH2xI12xI", screen, dotclock, hdisplay, hsyncstart, hsyncend, htotal, hskew, vdisplay, vsyncstart, vsyncend, vtotal, flags, privsize))
        buf.write(xcffib.pack_list(private, "B"))
        return self.send_request(9, buf, ValidateModeLineCookie, is_checked=is_checked)
    def SwitchToMode(self, screen, dotclock, hdisplay, hsyncstart, hsyncend, htotal, hskew, vdisplay, vsyncstart, vsyncend, vtotal, flags, privsize, private, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIHHHHHHHHH2xI12xI", screen, dotclock, hdisplay, hsyncstart, hsyncend, htotal, hskew, vdisplay, vsyncstart, vsyncend, vtotal, flags, privsize))
        buf.write(xcffib.pack_list(private, "B"))
        return self.send_request(10, buf, is_checked=is_checked)
    def GetViewPort(self, screen, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xH2x", screen))
        return self.send_request(11, buf, GetViewPortCookie, is_checked=is_checked)
    def SetViewPort(self, screen, x, y, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xH2xII", screen, x, y))
        return self.send_request(12, buf, is_checked=is_checked)
    def GetDotClocks(self, screen, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xH2x", screen))
        return self.send_request(13, buf, GetDotClocksCookie, is_checked=is_checked)
    def SetClientVersion(self, major, minor, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xHH", major, minor))
        return self.send_request(14, buf, is_checked=is_checked)
    def SetGamma(self, screen, red, green, blue, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xH2xIII12x", screen, red, green, blue))
        return self.send_request(15, buf, is_checked=is_checked)
    def GetGamma(self, screen, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xH26x", screen))
        return self.send_request(16, buf, GetGammaCookie, is_checked=is_checked)
    def GetGammaRamp(self, screen, size, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xHH", screen, size))
        return self.send_request(17, buf, GetGammaRampCookie, is_checked=is_checked)
    def SetGammaRamp(self, screen, size, red, green, blue, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xHH", screen, size))
        buf.write(xcffib.pack_list(red, "H"))
        buf.write(xcffib.pack_list(green, "H"))
        buf.write(xcffib.pack_list(blue, "H"))
        return self.send_request(18, buf, is_checked=is_checked)
    def GetGammaRampSize(self, screen, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xH2x", screen))
        return self.send_request(19, buf, GetGammaRampSizeCookie, is_checked=is_checked)
    def GetPermissions(self, screen, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xH2x", screen))
        return self.send_request(20, buf, GetPermissionsCookie, is_checked=is_checked)
xcffib._add_ext(key, xf86vidmodeExtension, _events, _errors)
