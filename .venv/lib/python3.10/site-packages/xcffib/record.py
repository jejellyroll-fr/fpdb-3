import xcffib
import struct
import io
MAJOR_VERSION = 1
MINOR_VERSION = 13
key = xcffib.ExtensionKey("RECORD")
_events = {}
_errors = {}
class Range8(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.first, self.last = unpacker.unpack("BB")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=BB", self.first, self.last))
        return buf.getvalue()
    fixed_size = 2
    @classmethod
    def synthetic(cls, first, last):
        self = cls.__new__(cls)
        self.first = first
        self.last = last
        return self
class Range16(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.first, self.last = unpacker.unpack("HH")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=HH", self.first, self.last))
        return buf.getvalue()
    fixed_size = 4
    @classmethod
    def synthetic(cls, first, last):
        self = cls.__new__(cls)
        self.first = first
        self.last = last
        return self
class ExtRange(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.major = Range8(unpacker)
        unpacker.pad(Range16)
        self.minor = Range16(unpacker)
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(self.major.pack() if hasattr(self.major, "pack") else Range8.synthetic(*self.major).pack())
        buf.write(self.minor.pack() if hasattr(self.minor, "pack") else Range16.synthetic(*self.minor).pack())
        return buf.getvalue()
    @classmethod
    def synthetic(cls, major, minor):
        self = cls.__new__(cls)
        self.major = major
        self.minor = minor
        return self
class Range(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.core_requests = Range8(unpacker)
        unpacker.pad(Range8)
        self.core_replies = Range8(unpacker)
        unpacker.pad(ExtRange)
        self.ext_requests = ExtRange(unpacker)
        unpacker.pad(ExtRange)
        self.ext_replies = ExtRange(unpacker)
        unpacker.pad(Range8)
        self.delivered_events = Range8(unpacker)
        unpacker.pad(Range8)
        self.device_events = Range8(unpacker)
        unpacker.pad(Range8)
        self.errors = Range8(unpacker)
        self.client_started, self.client_died = unpacker.unpack("BB")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(self.core_requests.pack() if hasattr(self.core_requests, "pack") else Range8.synthetic(*self.core_requests).pack())
        buf.write(self.core_replies.pack() if hasattr(self.core_replies, "pack") else Range8.synthetic(*self.core_replies).pack())
        buf.write(self.ext_requests.pack() if hasattr(self.ext_requests, "pack") else ExtRange.synthetic(*self.ext_requests).pack())
        buf.write(self.ext_replies.pack() if hasattr(self.ext_replies, "pack") else ExtRange.synthetic(*self.ext_replies).pack())
        buf.write(self.delivered_events.pack() if hasattr(self.delivered_events, "pack") else Range8.synthetic(*self.delivered_events).pack())
        buf.write(self.device_events.pack() if hasattr(self.device_events, "pack") else Range8.synthetic(*self.device_events).pack())
        buf.write(self.errors.pack() if hasattr(self.errors, "pack") else Range8.synthetic(*self.errors).pack())
        buf.write(struct.pack("=B", self.client_started))
        buf.write(struct.pack("=B", self.client_died))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, core_requests, core_replies, ext_requests, ext_replies, delivered_events, device_events, errors, client_started, client_died):
        self = cls.__new__(cls)
        self.core_requests = core_requests
        self.core_replies = core_replies
        self.ext_requests = ext_requests
        self.ext_replies = ext_replies
        self.delivered_events = delivered_events
        self.device_events = device_events
        self.errors = errors
        self.client_started = client_started
        self.client_died = client_died
        return self
class HType:
    FromServerTime = 1 << 0
    FromClientTime = 1 << 1
    FromClientSequence = 1 << 2
class CS:
    CurrentClients = 1
    FutureClients = 2
    AllClients = 3
class ClientInfo(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.client_resource, self.num_ranges = unpacker.unpack("II")
        self.ranges = xcffib.List(unpacker, Range, self.num_ranges)
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=II", self.client_resource, self.num_ranges))
        buf.write(xcffib.pack_list(self.ranges, Range))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, client_resource, num_ranges, ranges):
        self = cls.__new__(cls)
        self.client_resource = client_resource
        self.num_ranges = num_ranges
        self.ranges = ranges
        return self
class BadContextError(xcffib.Error):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Error.__init__(self, unpacker)
        base = unpacker.offset
        self.invalid_record, = unpacker.unpack("xx2xI")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 0))
        buf.write(struct.pack("=x2xI", self.invalid_record))
        return buf.getvalue()
BadBadContext = BadContextError
_errors[0] = BadContextError
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
class GetContextReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.enabled, self.element_header, self.num_intercepted_clients = unpacker.unpack("xB2x4xB3xI16x")
        self.intercepted_clients = xcffib.List(unpacker, ClientInfo, self.num_intercepted_clients)
        self.bufsize = unpacker.offset - base
class GetContextCookie(xcffib.Cookie):
    reply_type = GetContextReply
class EnableContextReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.category, self.element_header, self.client_swapped, self.xid_base, self.server_time, self.rec_sequence_num = unpacker.unpack("xB2x4xBB2xIII8x")
        self.data = xcffib.List(unpacker, "B", self.length * 4)
        self.bufsize = unpacker.offset - base
class EnableContextCookie(xcffib.Cookie):
    reply_type = EnableContextReply
class recordExtension(xcffib.Extension):
    def QueryVersion(self, major_version, minor_version, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xHH", major_version, minor_version))
        return self.send_request(0, buf, QueryVersionCookie, is_checked=is_checked)
    def CreateContext(self, context, element_header, num_client_specs, num_ranges, client_specs, ranges, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIB3xII", context, element_header, num_client_specs, num_ranges))
        buf.write(xcffib.pack_list(client_specs, "I"))
        buf.write(xcffib.pack_list(ranges, Range))
        return self.send_request(1, buf, is_checked=is_checked)
    def RegisterClients(self, context, element_header, num_client_specs, num_ranges, client_specs, ranges, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIB3xII", context, element_header, num_client_specs, num_ranges))
        buf.write(xcffib.pack_list(client_specs, "I"))
        buf.write(xcffib.pack_list(ranges, Range))
        return self.send_request(2, buf, is_checked=is_checked)
    def UnregisterClients(self, context, num_client_specs, client_specs, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", context, num_client_specs))
        buf.write(xcffib.pack_list(client_specs, "I"))
        return self.send_request(3, buf, is_checked=is_checked)
    def GetContext(self, context, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", context))
        return self.send_request(4, buf, GetContextCookie, is_checked=is_checked)
    def EnableContext(self, context, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", context))
        return self.send_request(5, buf, EnableContextCookie, is_checked=is_checked)
    def DisableContext(self, context, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", context))
        return self.send_request(6, buf, is_checked=is_checked)
    def FreeContext(self, context, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", context))
        return self.send_request(7, buf, is_checked=is_checked)
xcffib._add_ext(key, recordExtension, _events, _errors)
