import xcffib
import struct
import io
MAJOR_VERSION = 2
MINOR_VERSION = 2
key = xcffib.ExtensionKey("XVideo")
_events = {}
_errors = {}
from . import xproto
from . import shm
class Type:
    InputMask = 1 << 0
    OutputMask = 1 << 1
    VideoMask = 1 << 2
    StillMask = 1 << 3
    ImageMask = 1 << 4
class ImageFormatInfoType:
    RGB = 0
    YUV = 1
class ImageFormatInfoFormat:
    Packed = 0
    Planar = 1
class AttributeFlag:
    Gettable = 1 << 0
    Settable = 1 << 1
class VideoNotifyReason:
    Started = 0
    Stopped = 1
    Busy = 2
    Preempted = 3
    HardError = 4
class ScanlineOrder:
    TopToBottom = 0
    BottomToTop = 1
class GrabPortStatus:
    Success = 0
    BadExtension = 1
    AlreadyGrabbed = 2
    InvalidTime = 3
    BadReply = 4
    BadAlloc = 5
class Rational(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.numerator, self.denominator = unpacker.unpack("ii")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=ii", self.numerator, self.denominator))
        return buf.getvalue()
    fixed_size = 8
    @classmethod
    def synthetic(cls, numerator, denominator):
        self = cls.__new__(cls)
        self.numerator = numerator
        self.denominator = denominator
        return self
class Format(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.visual, self.depth = unpacker.unpack("IB3x")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=IB3x", self.visual, self.depth))
        return buf.getvalue()
    fixed_size = 8
    @classmethod
    def synthetic(cls, visual, depth):
        self = cls.__new__(cls)
        self.visual = visual
        self.depth = depth
        return self
class AdaptorInfo(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.base_id, self.name_size, self.num_ports, self.num_formats, self.type = unpacker.unpack("IHHHBx")
        self.name = xcffib.List(unpacker, "c", self.name_size)
        unpacker.pad(Format)
        self.formats = xcffib.List(unpacker, Format, self.num_formats)
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=IHHHBx", self.base_id, self.name_size, self.num_ports, self.num_formats, self.type))
        buf.write(xcffib.pack_list(self.name, "c"))
        buf.write(struct.pack("=4x", ))
        buf.write(xcffib.pack_list(self.formats, Format))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, base_id, name_size, num_ports, num_formats, type, name, formats):
        self = cls.__new__(cls)
        self.base_id = base_id
        self.name_size = name_size
        self.num_ports = num_ports
        self.num_formats = num_formats
        self.type = type
        self.name = name
        self.formats = formats
        return self
class EncodingInfo(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.encoding, self.name_size, self.width, self.height = unpacker.unpack("IHHH2x")
        self.rate = Rational(unpacker)
        unpacker.pad("c")
        self.name = xcffib.List(unpacker, "c", self.name_size)
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=IHHH2x", self.encoding, self.name_size, self.width, self.height))
        buf.write(self.rate.pack() if hasattr(self.rate, "pack") else Rational.synthetic(*self.rate).pack())
        buf.write(xcffib.pack_list(self.name, "c"))
        buf.write(struct.pack("=4x", ))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, encoding, name_size, width, height, rate, name):
        self = cls.__new__(cls)
        self.encoding = encoding
        self.name_size = name_size
        self.width = width
        self.height = height
        self.rate = rate
        self.name = name
        return self
class Image(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.id, self.width, self.height, self.data_size, self.num_planes = unpacker.unpack("IHHII")
        self.pitches = xcffib.List(unpacker, "I", self.num_planes)
        unpacker.pad("I")
        self.offsets = xcffib.List(unpacker, "I", self.num_planes)
        unpacker.pad("B")
        self.data = xcffib.List(unpacker, "B", self.data_size)
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=IHHII", self.id, self.width, self.height, self.data_size, self.num_planes))
        buf.write(xcffib.pack_list(self.pitches, "I"))
        buf.write(xcffib.pack_list(self.offsets, "I"))
        buf.write(xcffib.pack_list(self.data, "B"))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, id, width, height, data_size, num_planes, pitches, offsets, data):
        self = cls.__new__(cls)
        self.id = id
        self.width = width
        self.height = height
        self.data_size = data_size
        self.num_planes = num_planes
        self.pitches = pitches
        self.offsets = offsets
        self.data = data
        return self
class AttributeInfo(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.flags, self.min, self.max, self.size = unpacker.unpack("IiiI")
        self.name = xcffib.List(unpacker, "c", self.size)
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=IiiI", self.flags, self.min, self.max, self.size))
        buf.write(xcffib.pack_list(self.name, "c"))
        buf.write(struct.pack("=4x", ))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, flags, min, max, size, name):
        self = cls.__new__(cls)
        self.flags = flags
        self.min = min
        self.max = max
        self.size = size
        self.name = name
        return self
class ImageFormatInfo(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.id, self.type, self.byte_order = unpacker.unpack("IBB2x")
        self.guid = xcffib.List(unpacker, "B", 16)
        self.bpp, self.num_planes, self.depth, self.red_mask, self.green_mask, self.blue_mask, self.format, self.y_sample_bits, self.u_sample_bits, self.v_sample_bits, self.vhorz_y_period, self.vhorz_u_period, self.vhorz_v_period, self.vvert_y_period, self.vvert_u_period, self.vvert_v_period = unpacker.unpack("BB2xB3xIIIB3xIIIIIIIII")
        unpacker.pad("B")
        self.vcomp_order = xcffib.List(unpacker, "B", 32)
        self.vscanline_order, = unpacker.unpack("B11x")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=IBB2x", self.id, self.type, self.byte_order))
        buf.write(xcffib.pack_list(self.guid, "B"))
        buf.write(struct.pack("=B", self.bpp))
        buf.write(struct.pack("=B", self.num_planes))
        buf.write(struct.pack("=2x", ))
        buf.write(struct.pack("=B", self.depth))
        buf.write(struct.pack("=3x", ))
        buf.write(struct.pack("=I", self.red_mask))
        buf.write(struct.pack("=I", self.green_mask))
        buf.write(struct.pack("=I", self.blue_mask))
        buf.write(struct.pack("=B", self.format))
        buf.write(struct.pack("=3x", ))
        buf.write(struct.pack("=I", self.y_sample_bits))
        buf.write(struct.pack("=I", self.u_sample_bits))
        buf.write(struct.pack("=I", self.v_sample_bits))
        buf.write(struct.pack("=I", self.vhorz_y_period))
        buf.write(struct.pack("=I", self.vhorz_u_period))
        buf.write(struct.pack("=I", self.vhorz_v_period))
        buf.write(struct.pack("=I", self.vvert_y_period))
        buf.write(struct.pack("=I", self.vvert_u_period))
        buf.write(struct.pack("=I", self.vvert_v_period))
        buf.write(xcffib.pack_list(self.vcomp_order, "B"))
        buf.write(struct.pack("=B", self.vscanline_order))
        buf.write(struct.pack("=11x", ))
        return buf.getvalue()
    fixed_size = 128
    @classmethod
    def synthetic(cls, id, type, byte_order, guid, bpp, num_planes, depth, red_mask, green_mask, blue_mask, format, y_sample_bits, u_sample_bits, v_sample_bits, vhorz_y_period, vhorz_u_period, vhorz_v_period, vvert_y_period, vvert_u_period, vvert_v_period, vcomp_order, vscanline_order):
        self = cls.__new__(cls)
        self.id = id
        self.type = type
        self.byte_order = byte_order
        self.guid = guid
        self.bpp = bpp
        self.num_planes = num_planes
        self.depth = depth
        self.red_mask = red_mask
        self.green_mask = green_mask
        self.blue_mask = blue_mask
        self.format = format
        self.y_sample_bits = y_sample_bits
        self.u_sample_bits = u_sample_bits
        self.v_sample_bits = v_sample_bits
        self.vhorz_y_period = vhorz_y_period
        self.vhorz_u_period = vhorz_u_period
        self.vhorz_v_period = vhorz_v_period
        self.vvert_y_period = vvert_y_period
        self.vvert_u_period = vvert_u_period
        self.vvert_v_period = vvert_v_period
        self.vcomp_order = vcomp_order
        self.vscanline_order = vscanline_order
        return self
class BadPortError(xcffib.Error):
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
BadBadPort = BadPortError
_errors[0] = BadPortError
class BadEncodingError(xcffib.Error):
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
BadBadEncoding = BadEncodingError
_errors[1] = BadEncodingError
class BadControlError(xcffib.Error):
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
BadBadControl = BadControlError
_errors[2] = BadControlError
class VideoNotifyEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.reason, self.time, self.drawable, self.port = unpacker.unpack("xB2xIII")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 0))
        buf.write(struct.pack("=B2xIII", self.reason, self.time, self.drawable, self.port))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, reason, time, drawable, port):
        self = cls.__new__(cls)
        self.reason = reason
        self.time = time
        self.drawable = drawable
        self.port = port
        return self
_events[0] = VideoNotifyEvent
class PortNotifyEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.time, self.port, self.attribute, self.value = unpacker.unpack("xx2xIIIi")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 1))
        buf.write(struct.pack("=x2xIIIi", self.time, self.port, self.attribute, self.value))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, time, port, attribute, value):
        self = cls.__new__(cls)
        self.time = time
        self.port = port
        self.attribute = attribute
        self.value = value
        return self
_events[1] = PortNotifyEvent
class QueryExtensionReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.major, self.minor = unpacker.unpack("xx2x4xHH")
        self.bufsize = unpacker.offset - base
class QueryExtensionCookie(xcffib.Cookie):
    reply_type = QueryExtensionReply
class QueryAdaptorsReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.num_adaptors, = unpacker.unpack("xx2x4xH22x")
        self.info = xcffib.List(unpacker, AdaptorInfo, self.num_adaptors)
        self.bufsize = unpacker.offset - base
class QueryAdaptorsCookie(xcffib.Cookie):
    reply_type = QueryAdaptorsReply
class QueryEncodingsReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.num_encodings, = unpacker.unpack("xx2x4xH22x")
        self.info = xcffib.List(unpacker, EncodingInfo, self.num_encodings)
        self.bufsize = unpacker.offset - base
class QueryEncodingsCookie(xcffib.Cookie):
    reply_type = QueryEncodingsReply
class GrabPortReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.result, = unpacker.unpack("xB2x4x")
        self.bufsize = unpacker.offset - base
class GrabPortCookie(xcffib.Cookie):
    reply_type = GrabPortReply
class QueryBestSizeReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.actual_width, self.actual_height = unpacker.unpack("xx2x4xHH")
        self.bufsize = unpacker.offset - base
class QueryBestSizeCookie(xcffib.Cookie):
    reply_type = QueryBestSizeReply
class GetPortAttributeReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.value, = unpacker.unpack("xx2x4xi")
        self.bufsize = unpacker.offset - base
class GetPortAttributeCookie(xcffib.Cookie):
    reply_type = GetPortAttributeReply
class QueryPortAttributesReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.num_attributes, self.text_size = unpacker.unpack("xx2x4xII16x")
        self.attributes = xcffib.List(unpacker, AttributeInfo, self.num_attributes)
        self.bufsize = unpacker.offset - base
class QueryPortAttributesCookie(xcffib.Cookie):
    reply_type = QueryPortAttributesReply
class ListImageFormatsReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.num_formats, = unpacker.unpack("xx2x4xI20x")
        self.format = xcffib.List(unpacker, ImageFormatInfo, self.num_formats)
        self.bufsize = unpacker.offset - base
class ListImageFormatsCookie(xcffib.Cookie):
    reply_type = ListImageFormatsReply
class QueryImageAttributesReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.num_planes, self.data_size, self.width, self.height = unpacker.unpack("xx2x4xIIHH12x")
        self.pitches = xcffib.List(unpacker, "I", self.num_planes)
        unpacker.pad("I")
        self.offsets = xcffib.List(unpacker, "I", self.num_planes)
        self.bufsize = unpacker.offset - base
class QueryImageAttributesCookie(xcffib.Cookie):
    reply_type = QueryImageAttributesReply
class xvExtension(xcffib.Extension):
    def QueryExtension(self, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2x"))
        return self.send_request(0, buf, QueryExtensionCookie, is_checked=is_checked)
    def QueryAdaptors(self, window, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", window))
        return self.send_request(1, buf, QueryAdaptorsCookie, is_checked=is_checked)
    def QueryEncodings(self, port, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", port))
        return self.send_request(2, buf, QueryEncodingsCookie, is_checked=is_checked)
    def GrabPort(self, port, time, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", port, time))
        return self.send_request(3, buf, GrabPortCookie, is_checked=is_checked)
    def UngrabPort(self, port, time, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", port, time))
        return self.send_request(4, buf, is_checked=is_checked)
    def PutVideo(self, port, drawable, gc, vid_x, vid_y, vid_w, vid_h, drw_x, drw_y, drw_w, drw_h, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIIhhHHhhHH", port, drawable, gc, vid_x, vid_y, vid_w, vid_h, drw_x, drw_y, drw_w, drw_h))
        return self.send_request(5, buf, is_checked=is_checked)
    def PutStill(self, port, drawable, gc, vid_x, vid_y, vid_w, vid_h, drw_x, drw_y, drw_w, drw_h, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIIhhHHhhHH", port, drawable, gc, vid_x, vid_y, vid_w, vid_h, drw_x, drw_y, drw_w, drw_h))
        return self.send_request(6, buf, is_checked=is_checked)
    def GetVideo(self, port, drawable, gc, vid_x, vid_y, vid_w, vid_h, drw_x, drw_y, drw_w, drw_h, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIIhhHHhhHH", port, drawable, gc, vid_x, vid_y, vid_w, vid_h, drw_x, drw_y, drw_w, drw_h))
        return self.send_request(7, buf, is_checked=is_checked)
    def GetStill(self, port, drawable, gc, vid_x, vid_y, vid_w, vid_h, drw_x, drw_y, drw_w, drw_h, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIIhhHHhhHH", port, drawable, gc, vid_x, vid_y, vid_w, vid_h, drw_x, drw_y, drw_w, drw_h))
        return self.send_request(8, buf, is_checked=is_checked)
    def StopVideo(self, port, drawable, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", port, drawable))
        return self.send_request(9, buf, is_checked=is_checked)
    def SelectVideoNotify(self, drawable, onoff, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIB3x", drawable, onoff))
        return self.send_request(10, buf, is_checked=is_checked)
    def SelectPortNotify(self, port, onoff, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIB3x", port, onoff))
        return self.send_request(11, buf, is_checked=is_checked)
    def QueryBestSize(self, port, vid_w, vid_h, drw_w, drw_h, motion, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIHHHHB3x", port, vid_w, vid_h, drw_w, drw_h, motion))
        return self.send_request(12, buf, QueryBestSizeCookie, is_checked=is_checked)
    def SetPortAttribute(self, port, attribute, value, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIi", port, attribute, value))
        return self.send_request(13, buf, is_checked=is_checked)
    def GetPortAttribute(self, port, attribute, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", port, attribute))
        return self.send_request(14, buf, GetPortAttributeCookie, is_checked=is_checked)
    def QueryPortAttributes(self, port, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", port))
        return self.send_request(15, buf, QueryPortAttributesCookie, is_checked=is_checked)
    def ListImageFormats(self, port, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", port))
        return self.send_request(16, buf, ListImageFormatsCookie, is_checked=is_checked)
    def QueryImageAttributes(self, port, id, width, height, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIHH", port, id, width, height))
        return self.send_request(17, buf, QueryImageAttributesCookie, is_checked=is_checked)
    def PutImage(self, port, drawable, gc, id, src_x, src_y, src_w, src_h, drw_x, drw_y, drw_w, drw_h, width, height, data_len, data, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIIIhhHHhhHHHH", port, drawable, gc, id, src_x, src_y, src_w, src_h, drw_x, drw_y, drw_w, drw_h, width, height))
        buf.write(xcffib.pack_list(data, "B"))
        return self.send_request(18, buf, is_checked=is_checked)
    def ShmPutImage(self, port, drawable, gc, shmseg, id, offset, src_x, src_y, src_w, src_h, drw_x, drw_y, drw_w, drw_h, width, height, send_event, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIIIIIhhHHhhHHHHB3x", port, drawable, gc, shmseg, id, offset, src_x, src_y, src_w, src_h, drw_x, drw_y, drw_w, drw_h, width, height, send_event))
        return self.send_request(19, buf, is_checked=is_checked)
xcffib._add_ext(key, xvExtension, _events, _errors)
