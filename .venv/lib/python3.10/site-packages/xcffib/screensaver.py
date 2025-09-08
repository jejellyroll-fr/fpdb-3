import xcffib
import struct
import io
MAJOR_VERSION = 1
MINOR_VERSION = 1
key = xcffib.ExtensionKey("MIT-SCREEN-SAVER")
_events = {}
_errors = {}
from . import xproto
class Kind:
    Blanked = 0
    Internal = 1
    External = 2
class Event:
    NotifyMask = 1 << 0
    CycleMask = 1 << 1
class State:
    Off = 0
    On = 1
    Cycle = 2
    Disabled = 3
class QueryVersionReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.server_major_version, self.server_minor_version = unpacker.unpack("xx2x4xHH20x")
        self.bufsize = unpacker.offset - base
class QueryVersionCookie(xcffib.Cookie):
    reply_type = QueryVersionReply
class QueryInfoReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.state, self.saver_window, self.ms_until_server, self.ms_since_user_input, self.event_mask, self.kind = unpacker.unpack("xB2x4xIIIIB7x")
        self.bufsize = unpacker.offset - base
class QueryInfoCookie(xcffib.Cookie):
    reply_type = QueryInfoReply
class NotifyEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.state, self.time, self.root, self.window, self.kind, self.forced = unpacker.unpack("xB2xIIIBB14x")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 0))
        buf.write(struct.pack("=B2xIIIBB14x", self.state, self.time, self.root, self.window, self.kind, self.forced))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, state, time, root, window, kind, forced):
        self = cls.__new__(cls)
        self.state = state
        self.time = time
        self.root = root
        self.window = window
        self.kind = kind
        self.forced = forced
        return self
_events[0] = NotifyEvent
class screensaverExtension(xcffib.Extension):
    def QueryVersion(self, client_major_version, client_minor_version, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xBB2x", client_major_version, client_minor_version))
        return self.send_request(0, buf, QueryVersionCookie, is_checked=is_checked)
    def QueryInfo(self, drawable, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", drawable))
        return self.send_request(1, buf, QueryInfoCookie, is_checked=is_checked)
    def SelectInput(self, drawable, event_mask, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", drawable, event_mask))
        return self.send_request(2, buf, is_checked=is_checked)
    def SetAttributes(self, drawable, x, y, width, height, border_width, _class, depth, visual, value_mask, value_list, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIhhHHHBBII", drawable, x, y, width, height, border_width, _class, depth, visual, value_mask))
        if value_mask & xproto.CW:
            background_pixmap = value_list.pop(0)
            buf.write(struct.pack("=I", background_pixmap))
        if value_mask & xproto.CW:
            background_pixel = value_list.pop(0)
            buf.write(struct.pack("=I", background_pixel))
        if value_mask & xproto.CW:
            border_pixmap = value_list.pop(0)
            buf.write(struct.pack("=I", border_pixmap))
        if value_mask & xproto.CW:
            border_pixel = value_list.pop(0)
            buf.write(struct.pack("=I", border_pixel))
        if value_mask & xproto.CW:
            bit_gravity = value_list.pop(0)
            buf.write(struct.pack("=I", bit_gravity))
        if value_mask & xproto.CW:
            win_gravity = value_list.pop(0)
            buf.write(struct.pack("=I", win_gravity))
        if value_mask & xproto.CW:
            backing_store = value_list.pop(0)
            buf.write(struct.pack("=I", backing_store))
        if value_mask & xproto.CW:
            backing_planes = value_list.pop(0)
            buf.write(struct.pack("=I", backing_planes))
        if value_mask & xproto.CW:
            backing_pixel = value_list.pop(0)
            buf.write(struct.pack("=I", backing_pixel))
        if value_mask & xproto.CW:
            override_redirect = value_list.pop(0)
            buf.write(struct.pack("=I", override_redirect))
        if value_mask & xproto.CW:
            save_under = value_list.pop(0)
            buf.write(struct.pack("=I", save_under))
        if value_mask & xproto.CW:
            event_mask = value_list.pop(0)
            buf.write(struct.pack("=I", event_mask))
        if value_mask & xproto.CW:
            do_not_propogate_mask = value_list.pop(0)
            buf.write(struct.pack("=I", do_not_propogate_mask))
        if value_mask & xproto.CW:
            colormap = value_list.pop(0)
            buf.write(struct.pack("=I", colormap))
        if value_mask & xproto.CW:
            cursor = value_list.pop(0)
            buf.write(struct.pack("=I", cursor))
        return self.send_request(3, buf, is_checked=is_checked)
    def UnsetAttributes(self, drawable, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", drawable))
        return self.send_request(4, buf, is_checked=is_checked)
    def Suspend(self, suspend, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", suspend))
        return self.send_request(5, buf, is_checked=is_checked)
xcffib._add_ext(key, screensaverExtension, _events, _errors)
