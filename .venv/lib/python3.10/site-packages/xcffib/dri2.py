import xcffib
import struct
import io
MAJOR_VERSION = 1
MINOR_VERSION = 4
key = xcffib.ExtensionKey("DRI2")
_events = {}
_errors = {}
from . import xproto
class Attachment:
    BufferFrontLeft = 0
    BufferBackLeft = 1
    BufferFrontRight = 2
    BufferBackRight = 3
    BufferDepth = 4
    BufferStencil = 5
    BufferAccum = 6
    BufferFakeFrontLeft = 7
    BufferFakeFrontRight = 8
    BufferDepthStencil = 9
    BufferHiz = 10
class DriverType:
    DRI = 0
    VDPAU = 1
class EventType:
    ExchangeComplete = 1
    BlitComplete = 2
    FlipComplete = 3
class DRI2Buffer(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.attachment, self.name, self.pitch, self.cpp, self.flags = unpacker.unpack("IIIII")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=IIIII", self.attachment, self.name, self.pitch, self.cpp, self.flags))
        return buf.getvalue()
    fixed_size = 20
    @classmethod
    def synthetic(cls, attachment, name, pitch, cpp, flags):
        self = cls.__new__(cls)
        self.attachment = attachment
        self.name = name
        self.pitch = pitch
        self.cpp = cpp
        self.flags = flags
        return self
class AttachFormat(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.attachment, self.format = unpacker.unpack("II")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=II", self.attachment, self.format))
        return buf.getvalue()
    fixed_size = 8
    @classmethod
    def synthetic(cls, attachment, format):
        self = cls.__new__(cls)
        self.attachment = attachment
        self.format = format
        return self
class QueryVersionReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.major_version, self.minor_version = unpacker.unpack("xx2x4xII")
        self.bufsize = unpacker.offset - base
class QueryVersionCookie(xcffib.Cookie):
    reply_type = QueryVersionReply
class ConnectReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.driver_name_length, self.device_name_length = unpacker.unpack("xx2x4xII16x")
        self.driver_name = xcffib.List(unpacker, "c", self.driver_name_length)
        unpacker.pad("c")
        self.alignment_pad = xcffib.List(unpacker, "c", ((self.driver_name_length + 3) & (~ 3)) - self.driver_name_length)
        unpacker.pad("c")
        self.device_name = xcffib.List(unpacker, "c", self.device_name_length)
        self.bufsize = unpacker.offset - base
class ConnectCookie(xcffib.Cookie):
    reply_type = ConnectReply
class AuthenticateReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.authenticated, = unpacker.unpack("xx2x4xI")
        self.bufsize = unpacker.offset - base
class AuthenticateCookie(xcffib.Cookie):
    reply_type = AuthenticateReply
class GetBuffersReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.width, self.height, self.count = unpacker.unpack("xx2x4xIII12x")
        self.buffers = xcffib.List(unpacker, DRI2Buffer, self.count)
        self.bufsize = unpacker.offset - base
class GetBuffersCookie(xcffib.Cookie):
    reply_type = GetBuffersReply
class CopyRegionReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        unpacker.unpack("xx2x4x")
        self.bufsize = unpacker.offset - base
class CopyRegionCookie(xcffib.Cookie):
    reply_type = CopyRegionReply
class GetBuffersWithFormatReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.width, self.height, self.count = unpacker.unpack("xx2x4xIII12x")
        self.buffers = xcffib.List(unpacker, DRI2Buffer, self.count)
        self.bufsize = unpacker.offset - base
class GetBuffersWithFormatCookie(xcffib.Cookie):
    reply_type = GetBuffersWithFormatReply
class SwapBuffersReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.swap_hi, self.swap_lo = unpacker.unpack("xx2x4xII")
        self.bufsize = unpacker.offset - base
class SwapBuffersCookie(xcffib.Cookie):
    reply_type = SwapBuffersReply
class GetMSCReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.ust_hi, self.ust_lo, self.msc_hi, self.msc_lo, self.sbc_hi, self.sbc_lo = unpacker.unpack("xx2x4xIIIIII")
        self.bufsize = unpacker.offset - base
class GetMSCCookie(xcffib.Cookie):
    reply_type = GetMSCReply
class WaitMSCReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.ust_hi, self.ust_lo, self.msc_hi, self.msc_lo, self.sbc_hi, self.sbc_lo = unpacker.unpack("xx2x4xIIIIII")
        self.bufsize = unpacker.offset - base
class WaitMSCCookie(xcffib.Cookie):
    reply_type = WaitMSCReply
class WaitSBCReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.ust_hi, self.ust_lo, self.msc_hi, self.msc_lo, self.sbc_hi, self.sbc_lo = unpacker.unpack("xx2x4xIIIIII")
        self.bufsize = unpacker.offset - base
class WaitSBCCookie(xcffib.Cookie):
    reply_type = WaitSBCReply
class GetParamReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.is_param_recognized, self.value_hi, self.value_lo = unpacker.unpack("xB2x4xII")
        self.bufsize = unpacker.offset - base
class GetParamCookie(xcffib.Cookie):
    reply_type = GetParamReply
class BufferSwapCompleteEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.event_type, self.drawable, self.ust_hi, self.ust_lo, self.msc_hi, self.msc_lo, self.sbc = unpacker.unpack("xx2xH2xIIIIII")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 0))
        buf.write(struct.pack("=x2xH2xIIIIII", self.event_type, self.drawable, self.ust_hi, self.ust_lo, self.msc_hi, self.msc_lo, self.sbc))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, event_type, drawable, ust_hi, ust_lo, msc_hi, msc_lo, sbc):
        self = cls.__new__(cls)
        self.event_type = event_type
        self.drawable = drawable
        self.ust_hi = ust_hi
        self.ust_lo = ust_lo
        self.msc_hi = msc_hi
        self.msc_lo = msc_lo
        self.sbc = sbc
        return self
_events[0] = BufferSwapCompleteEvent
class InvalidateBuffersEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.drawable, = unpacker.unpack("xx2xI")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 1))
        buf.write(struct.pack("=x2xI", self.drawable))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, drawable):
        self = cls.__new__(cls)
        self.drawable = drawable
        return self
_events[1] = InvalidateBuffersEvent
class dri2Extension(xcffib.Extension):
    def QueryVersion(self, major_version, minor_version, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", major_version, minor_version))
        return self.send_request(0, buf, QueryVersionCookie, is_checked=is_checked)
    def Connect(self, window, driver_type, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", window, driver_type))
        return self.send_request(1, buf, ConnectCookie, is_checked=is_checked)
    def Authenticate(self, window, magic, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", window, magic))
        return self.send_request(2, buf, AuthenticateCookie, is_checked=is_checked)
    def CreateDrawable(self, drawable, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", drawable))
        return self.send_request(3, buf, is_checked=is_checked)
    def DestroyDrawable(self, drawable, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", drawable))
        return self.send_request(4, buf, is_checked=is_checked)
    def GetBuffers(self, drawable, count, attachments_len, attachments, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", drawable, count))
        buf.write(xcffib.pack_list(attachments, "I"))
        return self.send_request(5, buf, GetBuffersCookie, is_checked=is_checked)
    def CopyRegion(self, drawable, region, dest, src, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIII", drawable, region, dest, src))
        return self.send_request(6, buf, CopyRegionCookie, is_checked=is_checked)
    def GetBuffersWithFormat(self, drawable, count, attachments_len, attachments, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", drawable, count))
        buf.write(xcffib.pack_list(attachments, AttachFormat))
        return self.send_request(7, buf, GetBuffersWithFormatCookie, is_checked=is_checked)
    def SwapBuffers(self, drawable, target_msc_hi, target_msc_lo, divisor_hi, divisor_lo, remainder_hi, remainder_lo, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIIIIII", drawable, target_msc_hi, target_msc_lo, divisor_hi, divisor_lo, remainder_hi, remainder_lo))
        return self.send_request(8, buf, SwapBuffersCookie, is_checked=is_checked)
    def GetMSC(self, drawable, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", drawable))
        return self.send_request(9, buf, GetMSCCookie, is_checked=is_checked)
    def WaitMSC(self, drawable, target_msc_hi, target_msc_lo, divisor_hi, divisor_lo, remainder_hi, remainder_lo, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIIIIII", drawable, target_msc_hi, target_msc_lo, divisor_hi, divisor_lo, remainder_hi, remainder_lo))
        return self.send_request(10, buf, WaitMSCCookie, is_checked=is_checked)
    def WaitSBC(self, drawable, target_sbc_hi, target_sbc_lo, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIII", drawable, target_sbc_hi, target_sbc_lo))
        return self.send_request(11, buf, WaitSBCCookie, is_checked=is_checked)
    def SwapInterval(self, drawable, interval, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", drawable, interval))
        return self.send_request(12, buf, is_checked=is_checked)
    def GetParam(self, drawable, param, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", drawable, param))
        return self.send_request(13, buf, GetParamCookie, is_checked=is_checked)
xcffib._add_ext(key, dri2Extension, _events, _errors)
