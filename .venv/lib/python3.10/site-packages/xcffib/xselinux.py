import xcffib
import struct
import io
MAJOR_VERSION = 1
MINOR_VERSION = 0
key = xcffib.ExtensionKey("SELinux")
_events = {}
_errors = {}
from . import xproto
class QueryVersionReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.server_major, self.server_minor = unpacker.unpack("xx2x4xHH")
        self.bufsize = unpacker.offset - base
class QueryVersionCookie(xcffib.Cookie):
    reply_type = QueryVersionReply
class GetDeviceCreateContextReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.context_len, = unpacker.unpack("xx2x4xI20x")
        self.context = xcffib.List(unpacker, "c", self.context_len)
        self.bufsize = unpacker.offset - base
class GetDeviceCreateContextCookie(xcffib.Cookie):
    reply_type = GetDeviceCreateContextReply
class GetDeviceContextReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.context_len, = unpacker.unpack("xx2x4xI20x")
        self.context = xcffib.List(unpacker, "c", self.context_len)
        self.bufsize = unpacker.offset - base
class GetDeviceContextCookie(xcffib.Cookie):
    reply_type = GetDeviceContextReply
class GetWindowCreateContextReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.context_len, = unpacker.unpack("xx2x4xI20x")
        self.context = xcffib.List(unpacker, "c", self.context_len)
        self.bufsize = unpacker.offset - base
class GetWindowCreateContextCookie(xcffib.Cookie):
    reply_type = GetWindowCreateContextReply
class GetWindowContextReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.context_len, = unpacker.unpack("xx2x4xI20x")
        self.context = xcffib.List(unpacker, "c", self.context_len)
        self.bufsize = unpacker.offset - base
class GetWindowContextCookie(xcffib.Cookie):
    reply_type = GetWindowContextReply
class ListItem(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.name, self.object_context_len, self.data_context_len = unpacker.unpack("III")
        self.object_context = xcffib.List(unpacker, "c", self.object_context_len)
        unpacker.pad("c")
        self.data_context = xcffib.List(unpacker, "c", self.data_context_len)
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=III", self.name, self.object_context_len, self.data_context_len))
        buf.write(xcffib.pack_list(self.object_context, "c"))
        buf.write(struct.pack("=4x", ))
        buf.write(xcffib.pack_list(self.data_context, "c"))
        buf.write(struct.pack("=4x", ))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, name, object_context_len, data_context_len, object_context, data_context):
        self = cls.__new__(cls)
        self.name = name
        self.object_context_len = object_context_len
        self.data_context_len = data_context_len
        self.object_context = object_context
        self.data_context = data_context
        return self
class GetPropertyCreateContextReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.context_len, = unpacker.unpack("xx2x4xI20x")
        self.context = xcffib.List(unpacker, "c", self.context_len)
        self.bufsize = unpacker.offset - base
class GetPropertyCreateContextCookie(xcffib.Cookie):
    reply_type = GetPropertyCreateContextReply
class GetPropertyUseContextReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.context_len, = unpacker.unpack("xx2x4xI20x")
        self.context = xcffib.List(unpacker, "c", self.context_len)
        self.bufsize = unpacker.offset - base
class GetPropertyUseContextCookie(xcffib.Cookie):
    reply_type = GetPropertyUseContextReply
class GetPropertyContextReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.context_len, = unpacker.unpack("xx2x4xI20x")
        self.context = xcffib.List(unpacker, "c", self.context_len)
        self.bufsize = unpacker.offset - base
class GetPropertyContextCookie(xcffib.Cookie):
    reply_type = GetPropertyContextReply
class GetPropertyDataContextReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.context_len, = unpacker.unpack("xx2x4xI20x")
        self.context = xcffib.List(unpacker, "c", self.context_len)
        self.bufsize = unpacker.offset - base
class GetPropertyDataContextCookie(xcffib.Cookie):
    reply_type = GetPropertyDataContextReply
class ListPropertiesReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.properties_len, = unpacker.unpack("xx2x4xI20x")
        self.properties = xcffib.List(unpacker, ListItem, self.properties_len)
        self.bufsize = unpacker.offset - base
class ListPropertiesCookie(xcffib.Cookie):
    reply_type = ListPropertiesReply
class GetSelectionCreateContextReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.context_len, = unpacker.unpack("xx2x4xI20x")
        self.context = xcffib.List(unpacker, "c", self.context_len)
        self.bufsize = unpacker.offset - base
class GetSelectionCreateContextCookie(xcffib.Cookie):
    reply_type = GetSelectionCreateContextReply
class GetSelectionUseContextReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.context_len, = unpacker.unpack("xx2x4xI20x")
        self.context = xcffib.List(unpacker, "c", self.context_len)
        self.bufsize = unpacker.offset - base
class GetSelectionUseContextCookie(xcffib.Cookie):
    reply_type = GetSelectionUseContextReply
class GetSelectionContextReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.context_len, = unpacker.unpack("xx2x4xI20x")
        self.context = xcffib.List(unpacker, "c", self.context_len)
        self.bufsize = unpacker.offset - base
class GetSelectionContextCookie(xcffib.Cookie):
    reply_type = GetSelectionContextReply
class GetSelectionDataContextReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.context_len, = unpacker.unpack("xx2x4xI20x")
        self.context = xcffib.List(unpacker, "c", self.context_len)
        self.bufsize = unpacker.offset - base
class GetSelectionDataContextCookie(xcffib.Cookie):
    reply_type = GetSelectionDataContextReply
class ListSelectionsReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.selections_len, = unpacker.unpack("xx2x4xI20x")
        self.selections = xcffib.List(unpacker, ListItem, self.selections_len)
        self.bufsize = unpacker.offset - base
class ListSelectionsCookie(xcffib.Cookie):
    reply_type = ListSelectionsReply
class GetClientContextReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.context_len, = unpacker.unpack("xx2x4xI20x")
        self.context = xcffib.List(unpacker, "c", self.context_len)
        self.bufsize = unpacker.offset - base
class GetClientContextCookie(xcffib.Cookie):
    reply_type = GetClientContextReply
class xselinuxExtension(xcffib.Extension):
    def QueryVersion(self, client_major, client_minor, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xBB", client_major, client_minor))
        return self.send_request(0, buf, QueryVersionCookie, is_checked=is_checked)
    def SetDeviceCreateContext(self, context_len, context, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", context_len))
        buf.write(xcffib.pack_list(context, "c"))
        return self.send_request(1, buf, is_checked=is_checked)
    def GetDeviceCreateContext(self, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2x"))
        return self.send_request(2, buf, GetDeviceCreateContextCookie, is_checked=is_checked)
    def SetDeviceContext(self, device, context_len, context, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", device, context_len))
        buf.write(xcffib.pack_list(context, "c"))
        return self.send_request(3, buf, is_checked=is_checked)
    def GetDeviceContext(self, device, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", device))
        return self.send_request(4, buf, GetDeviceContextCookie, is_checked=is_checked)
    def SetWindowCreateContext(self, context_len, context, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", context_len))
        buf.write(xcffib.pack_list(context, "c"))
        return self.send_request(5, buf, is_checked=is_checked)
    def GetWindowCreateContext(self, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2x"))
        return self.send_request(6, buf, GetWindowCreateContextCookie, is_checked=is_checked)
    def GetWindowContext(self, window, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", window))
        return self.send_request(7, buf, GetWindowContextCookie, is_checked=is_checked)
    def SetPropertyCreateContext(self, context_len, context, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", context_len))
        buf.write(xcffib.pack_list(context, "c"))
        return self.send_request(8, buf, is_checked=is_checked)
    def GetPropertyCreateContext(self, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2x"))
        return self.send_request(9, buf, GetPropertyCreateContextCookie, is_checked=is_checked)
    def SetPropertyUseContext(self, context_len, context, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", context_len))
        buf.write(xcffib.pack_list(context, "c"))
        return self.send_request(10, buf, is_checked=is_checked)
    def GetPropertyUseContext(self, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2x"))
        return self.send_request(11, buf, GetPropertyUseContextCookie, is_checked=is_checked)
    def GetPropertyContext(self, window, property, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", window, property))
        return self.send_request(12, buf, GetPropertyContextCookie, is_checked=is_checked)
    def GetPropertyDataContext(self, window, property, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", window, property))
        return self.send_request(13, buf, GetPropertyDataContextCookie, is_checked=is_checked)
    def ListProperties(self, window, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", window))
        return self.send_request(14, buf, ListPropertiesCookie, is_checked=is_checked)
    def SetSelectionCreateContext(self, context_len, context, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", context_len))
        buf.write(xcffib.pack_list(context, "c"))
        return self.send_request(15, buf, is_checked=is_checked)
    def GetSelectionCreateContext(self, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2x"))
        return self.send_request(16, buf, GetSelectionCreateContextCookie, is_checked=is_checked)
    def SetSelectionUseContext(self, context_len, context, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", context_len))
        buf.write(xcffib.pack_list(context, "c"))
        return self.send_request(17, buf, is_checked=is_checked)
    def GetSelectionUseContext(self, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2x"))
        return self.send_request(18, buf, GetSelectionUseContextCookie, is_checked=is_checked)
    def GetSelectionContext(self, selection, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", selection))
        return self.send_request(19, buf, GetSelectionContextCookie, is_checked=is_checked)
    def GetSelectionDataContext(self, selection, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", selection))
        return self.send_request(20, buf, GetSelectionDataContextCookie, is_checked=is_checked)
    def ListSelections(self, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2x"))
        return self.send_request(21, buf, ListSelectionsCookie, is_checked=is_checked)
    def GetClientContext(self, resource, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", resource))
        return self.send_request(22, buf, GetClientContextCookie, is_checked=is_checked)
xcffib._add_ext(key, xselinuxExtension, _events, _errors)
