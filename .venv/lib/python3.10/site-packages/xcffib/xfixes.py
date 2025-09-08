import xcffib
import struct
import io
MAJOR_VERSION = 6
MINOR_VERSION = 0
key = xcffib.ExtensionKey("XFIXES")
_events = {}
_errors = {}
from . import xproto
from . import render
from . import shape
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
class SaveSetMode:
    Insert = 0
    Delete = 1
class SaveSetTarget:
    Nearest = 0
    Root = 1
class SaveSetMapping:
    Map = 0
    Unmap = 1
class SelectionEvent:
    SetSelectionOwner = 0
    SelectionWindowDestroy = 1
    SelectionClientClose = 2
class SelectionEventMask:
    SetSelectionOwner = 1 << 0
    SelectionWindowDestroy = 1 << 1
    SelectionClientClose = 1 << 2
class SelectionNotifyEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.subtype, self.window, self.owner, self.selection, self.timestamp, self.selection_timestamp = unpacker.unpack("xB2xIIIII8x")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 0))
        buf.write(struct.pack("=B2xIIIII8x", self.subtype, self.window, self.owner, self.selection, self.timestamp, self.selection_timestamp))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, subtype, window, owner, selection, timestamp, selection_timestamp):
        self = cls.__new__(cls)
        self.subtype = subtype
        self.window = window
        self.owner = owner
        self.selection = selection
        self.timestamp = timestamp
        self.selection_timestamp = selection_timestamp
        return self
_events[0] = SelectionNotifyEvent
class CursorNotify:
    DisplayCursor = 0
class CursorNotifyMask:
    DisplayCursor = 1 << 0
class CursorNotifyEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.subtype, self.window, self.cursor_serial, self.timestamp, self.name = unpacker.unpack("xB2xIIII12x")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 1))
        buf.write(struct.pack("=B2xIIII12x", self.subtype, self.window, self.cursor_serial, self.timestamp, self.name))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, subtype, window, cursor_serial, timestamp, name):
        self = cls.__new__(cls)
        self.subtype = subtype
        self.window = window
        self.cursor_serial = cursor_serial
        self.timestamp = timestamp
        self.name = name
        return self
_events[1] = CursorNotifyEvent
class GetCursorImageReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.x, self.y, self.width, self.height, self.xhot, self.yhot, self.cursor_serial = unpacker.unpack("xx2x4xhhHHHHI8x")
        self.cursor_image = xcffib.List(unpacker, "I", self.width * self.height)
        self.bufsize = unpacker.offset - base
class GetCursorImageCookie(xcffib.Cookie):
    reply_type = GetCursorImageReply
class BadRegionError(xcffib.Error):
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
BadBadRegion = BadRegionError
_errors[0] = BadRegionError
class Region:
    _None = 0
class FetchRegionReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        unpacker.unpack("xx2x4x")
        self.extents = xproto.RECTANGLE(unpacker)
        unpacker.unpack("16x")
        unpacker.pad(xproto.RECTANGLE)
        self.rectangles = xcffib.List(unpacker, xproto.RECTANGLE, self.length // 2)
        self.bufsize = unpacker.offset - base
class FetchRegionCookie(xcffib.Cookie):
    reply_type = FetchRegionReply
class GetCursorNameReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.atom, self.nbytes = unpacker.unpack("xx2x4xIH18x")
        self.name = xcffib.List(unpacker, "c", self.nbytes)
        self.bufsize = unpacker.offset - base
class GetCursorNameCookie(xcffib.Cookie):
    reply_type = GetCursorNameReply
class GetCursorImageAndNameReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.x, self.y, self.width, self.height, self.xhot, self.yhot, self.cursor_serial, self.cursor_atom, self.nbytes = unpacker.unpack("xx2x4xhhHHHHIIH2x")
        self.cursor_image = xcffib.List(unpacker, "I", self.width * self.height)
        unpacker.pad("c")
        self.name = xcffib.List(unpacker, "c", self.nbytes)
        self.bufsize = unpacker.offset - base
class GetCursorImageAndNameCookie(xcffib.Cookie):
    reply_type = GetCursorImageAndNameReply
class BarrierDirections:
    PositiveX = 1 << 0
    PositiveY = 1 << 1
    NegativeX = 1 << 2
    NegativeY = 1 << 3
class ClientDisconnectFlags:
    Default = 0
    Terminate = 1 << 0
class GetClientDisconnectModeReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.disconnect_mode, = unpacker.unpack("xx2x4xI20x")
        self.bufsize = unpacker.offset - base
class GetClientDisconnectModeCookie(xcffib.Cookie):
    reply_type = GetClientDisconnectModeReply
class xfixesExtension(xcffib.Extension):
    def QueryVersion(self, client_major_version, client_minor_version, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", client_major_version, client_minor_version))
        return self.send_request(0, buf, QueryVersionCookie, is_checked=is_checked)
    def ChangeSaveSet(self, mode, target, map, window, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xBBBxI", mode, target, map, window))
        return self.send_request(1, buf, is_checked=is_checked)
    def SelectSelectionInput(self, window, selection, event_mask, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIII", window, selection, event_mask))
        return self.send_request(2, buf, is_checked=is_checked)
    def SelectCursorInput(self, window, event_mask, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", window, event_mask))
        return self.send_request(3, buf, is_checked=is_checked)
    def GetCursorImage(self, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2x"))
        return self.send_request(4, buf, GetCursorImageCookie, is_checked=is_checked)
    def CreateRegion(self, region, rectangles_len, rectangles, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", region))
        buf.write(xcffib.pack_list(rectangles, xproto.RECTANGLE))
        return self.send_request(5, buf, is_checked=is_checked)
    def CreateRegionFromBitmap(self, region, bitmap, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", region, bitmap))
        return self.send_request(6, buf, is_checked=is_checked)
    def CreateRegionFromWindow(self, region, window, kind, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIB3x", region, window, kind))
        return self.send_request(7, buf, is_checked=is_checked)
    def CreateRegionFromGC(self, region, gc, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", region, gc))
        return self.send_request(8, buf, is_checked=is_checked)
    def CreateRegionFromPicture(self, region, picture, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", region, picture))
        return self.send_request(9, buf, is_checked=is_checked)
    def DestroyRegion(self, region, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", region))
        return self.send_request(10, buf, is_checked=is_checked)
    def SetRegion(self, region, rectangles_len, rectangles, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", region))
        buf.write(xcffib.pack_list(rectangles, xproto.RECTANGLE))
        return self.send_request(11, buf, is_checked=is_checked)
    def CopyRegion(self, source, destination, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", source, destination))
        return self.send_request(12, buf, is_checked=is_checked)
    def UnionRegion(self, source1, source2, destination, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIII", source1, source2, destination))
        return self.send_request(13, buf, is_checked=is_checked)
    def IntersectRegion(self, source1, source2, destination, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIII", source1, source2, destination))
        return self.send_request(14, buf, is_checked=is_checked)
    def SubtractRegion(self, source1, source2, destination, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIII", source1, source2, destination))
        return self.send_request(15, buf, is_checked=is_checked)
    def InvertRegion(self, source, bounds, destination, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", source))
        buf.write(bounds.pack() if hasattr(bounds, "pack") else xproto.RECTANGLE.synthetic(*bounds).pack())
        buf.write(struct.pack("=I", destination))
        return self.send_request(16, buf, is_checked=is_checked)
    def TranslateRegion(self, region, dx, dy, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIhh", region, dx, dy))
        return self.send_request(17, buf, is_checked=is_checked)
    def RegionExtents(self, source, destination, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", source, destination))
        return self.send_request(18, buf, is_checked=is_checked)
    def FetchRegion(self, region, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", region))
        return self.send_request(19, buf, FetchRegionCookie, is_checked=is_checked)
    def SetGCClipRegion(self, gc, region, x_origin, y_origin, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIhh", gc, region, x_origin, y_origin))
        return self.send_request(20, buf, is_checked=is_checked)
    def SetWindowShapeRegion(self, dest, dest_kind, x_offset, y_offset, region, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIB3xhhI", dest, dest_kind, x_offset, y_offset, region))
        return self.send_request(21, buf, is_checked=is_checked)
    def SetPictureClipRegion(self, picture, region, x_origin, y_origin, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIhh", picture, region, x_origin, y_origin))
        return self.send_request(22, buf, is_checked=is_checked)
    def SetCursorName(self, cursor, nbytes, name, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIH2x", cursor, nbytes))
        buf.write(xcffib.pack_list(name, "c"))
        return self.send_request(23, buf, is_checked=is_checked)
    def GetCursorName(self, cursor, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", cursor))
        return self.send_request(24, buf, GetCursorNameCookie, is_checked=is_checked)
    def GetCursorImageAndName(self, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2x"))
        return self.send_request(25, buf, GetCursorImageAndNameCookie, is_checked=is_checked)
    def ChangeCursor(self, source, destination, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", source, destination))
        return self.send_request(26, buf, is_checked=is_checked)
    def ChangeCursorByName(self, src, nbytes, name, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIH2x", src, nbytes))
        buf.write(xcffib.pack_list(name, "c"))
        return self.send_request(27, buf, is_checked=is_checked)
    def ExpandRegion(self, source, destination, left, right, top, bottom, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIHHHH", source, destination, left, right, top, bottom))
        return self.send_request(28, buf, is_checked=is_checked)
    def HideCursor(self, window, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", window))
        return self.send_request(29, buf, is_checked=is_checked)
    def ShowCursor(self, window, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", window))
        return self.send_request(30, buf, is_checked=is_checked)
    def CreatePointerBarrier(self, barrier, window, x1, y1, x2, y2, directions, num_devices, devices, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIHHHHI2xH", barrier, window, x1, y1, x2, y2, directions, num_devices))
        buf.write(xcffib.pack_list(devices, "H"))
        return self.send_request(31, buf, is_checked=is_checked)
    def DeletePointerBarrier(self, barrier, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", barrier))
        return self.send_request(32, buf, is_checked=is_checked)
    def SetClientDisconnectMode(self, disconnect_mode, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", disconnect_mode))
        return self.send_request(33, buf, is_checked=is_checked)
    def GetClientDisconnectMode(self, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2x"))
        return self.send_request(34, buf, GetClientDisconnectModeCookie, is_checked=is_checked)
xcffib._add_ext(key, xfixesExtension, _events, _errors)
