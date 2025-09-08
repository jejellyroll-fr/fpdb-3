import xcffib
import struct
import io
_events = {}
_errors = {}
class CHAR2B(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.byte1, self.byte2 = unpacker.unpack("BB")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=BB", self.byte1, self.byte2))
        return buf.getvalue()
    fixed_size = 2
    @classmethod
    def synthetic(cls, byte1, byte2):
        self = cls.__new__(cls)
        self.byte1 = byte1
        self.byte2 = byte2
        return self
class POINT(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.x, self.y = unpacker.unpack("hh")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=hh", self.x, self.y))
        return buf.getvalue()
    fixed_size = 4
    @classmethod
    def synthetic(cls, x, y):
        self = cls.__new__(cls)
        self.x = x
        self.y = y
        return self
class RECTANGLE(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.x, self.y, self.width, self.height = unpacker.unpack("hhHH")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=hhHH", self.x, self.y, self.width, self.height))
        return buf.getvalue()
    fixed_size = 8
    @classmethod
    def synthetic(cls, x, y, width, height):
        self = cls.__new__(cls)
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        return self
class ARC(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.x, self.y, self.width, self.height, self.angle1, self.angle2 = unpacker.unpack("hhHHhh")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=hhHHhh", self.x, self.y, self.width, self.height, self.angle1, self.angle2))
        return buf.getvalue()
    fixed_size = 12
    @classmethod
    def synthetic(cls, x, y, width, height, angle1, angle2):
        self = cls.__new__(cls)
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.angle1 = angle1
        self.angle2 = angle2
        return self
class FORMAT(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.depth, self.bits_per_pixel, self.scanline_pad = unpacker.unpack("BBB5x")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=BBB5x", self.depth, self.bits_per_pixel, self.scanline_pad))
        return buf.getvalue()
    fixed_size = 8
    @classmethod
    def synthetic(cls, depth, bits_per_pixel, scanline_pad):
        self = cls.__new__(cls)
        self.depth = depth
        self.bits_per_pixel = bits_per_pixel
        self.scanline_pad = scanline_pad
        return self
class VisualClass:
    StaticGray = 0
    GrayScale = 1
    StaticColor = 2
    PseudoColor = 3
    TrueColor = 4
    DirectColor = 5
class VISUALTYPE(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.visual_id, self._class, self.bits_per_rgb_value, self.colormap_entries, self.red_mask, self.green_mask, self.blue_mask = unpacker.unpack("IBBHIII4x")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=IBBHIII4x", self.visual_id, self._class, self.bits_per_rgb_value, self.colormap_entries, self.red_mask, self.green_mask, self.blue_mask))
        return buf.getvalue()
    fixed_size = 24
    @classmethod
    def synthetic(cls, visual_id, _class, bits_per_rgb_value, colormap_entries, red_mask, green_mask, blue_mask):
        self = cls.__new__(cls)
        self.visual_id = visual_id
        self._class = _class
        self.bits_per_rgb_value = bits_per_rgb_value
        self.colormap_entries = colormap_entries
        self.red_mask = red_mask
        self.green_mask = green_mask
        self.blue_mask = blue_mask
        return self
class DEPTH(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.depth, self.visuals_len = unpacker.unpack("BxH4x")
        self.visuals = xcffib.List(unpacker, VISUALTYPE, self.visuals_len)
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=BxH4x", self.depth, self.visuals_len))
        buf.write(xcffib.pack_list(self.visuals, VISUALTYPE))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, depth, visuals_len, visuals):
        self = cls.__new__(cls)
        self.depth = depth
        self.visuals_len = visuals_len
        self.visuals = visuals
        return self
class EventMask:
    NoEvent = 0
    KeyPress = 1 << 0
    KeyRelease = 1 << 1
    ButtonPress = 1 << 2
    ButtonRelease = 1 << 3
    EnterWindow = 1 << 4
    LeaveWindow = 1 << 5
    PointerMotion = 1 << 6
    PointerMotionHint = 1 << 7
    Button1Motion = 1 << 8
    Button2Motion = 1 << 9
    Button3Motion = 1 << 10
    Button4Motion = 1 << 11
    Button5Motion = 1 << 12
    ButtonMotion = 1 << 13
    KeymapState = 1 << 14
    Exposure = 1 << 15
    VisibilityChange = 1 << 16
    StructureNotify = 1 << 17
    ResizeRedirect = 1 << 18
    SubstructureNotify = 1 << 19
    SubstructureRedirect = 1 << 20
    FocusChange = 1 << 21
    PropertyChange = 1 << 22
    ColorMapChange = 1 << 23
    OwnerGrabButton = 1 << 24
class BackingStore:
    NotUseful = 0
    WhenMapped = 1
    Always = 2
class SCREEN(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.root, self.default_colormap, self.white_pixel, self.black_pixel, self.current_input_masks, self.width_in_pixels, self.height_in_pixels, self.width_in_millimeters, self.height_in_millimeters, self.min_installed_maps, self.max_installed_maps, self.root_visual, self.backing_stores, self.save_unders, self.root_depth, self.allowed_depths_len = unpacker.unpack("IIIIIHHHHHHIBBBB")
        self.allowed_depths = xcffib.List(unpacker, DEPTH, self.allowed_depths_len)
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=IIIIIHHHHHHIBBBB", self.root, self.default_colormap, self.white_pixel, self.black_pixel, self.current_input_masks, self.width_in_pixels, self.height_in_pixels, self.width_in_millimeters, self.height_in_millimeters, self.min_installed_maps, self.max_installed_maps, self.root_visual, self.backing_stores, self.save_unders, self.root_depth, self.allowed_depths_len))
        buf.write(xcffib.pack_list(self.allowed_depths, DEPTH))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, root, default_colormap, white_pixel, black_pixel, current_input_masks, width_in_pixels, height_in_pixels, width_in_millimeters, height_in_millimeters, min_installed_maps, max_installed_maps, root_visual, backing_stores, save_unders, root_depth, allowed_depths_len, allowed_depths):
        self = cls.__new__(cls)
        self.root = root
        self.default_colormap = default_colormap
        self.white_pixel = white_pixel
        self.black_pixel = black_pixel
        self.current_input_masks = current_input_masks
        self.width_in_pixels = width_in_pixels
        self.height_in_pixels = height_in_pixels
        self.width_in_millimeters = width_in_millimeters
        self.height_in_millimeters = height_in_millimeters
        self.min_installed_maps = min_installed_maps
        self.max_installed_maps = max_installed_maps
        self.root_visual = root_visual
        self.backing_stores = backing_stores
        self.save_unders = save_unders
        self.root_depth = root_depth
        self.allowed_depths_len = allowed_depths_len
        self.allowed_depths = allowed_depths
        return self
class SetupRequest(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.byte_order, self.protocol_major_version, self.protocol_minor_version, self.authorization_protocol_name_len, self.authorization_protocol_data_len = unpacker.unpack("BxHHHH2x")
        self.authorization_protocol_name = xcffib.List(unpacker, "c", self.authorization_protocol_name_len)
        unpacker.pad("c")
        self.authorization_protocol_data = xcffib.List(unpacker, "c", self.authorization_protocol_data_len)
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=BxHHHH2x", self.byte_order, self.protocol_major_version, self.protocol_minor_version, self.authorization_protocol_name_len, self.authorization_protocol_data_len))
        buf.write(xcffib.pack_list(self.authorization_protocol_name, "c"))
        buf.write(struct.pack("=4x", ))
        buf.write(xcffib.pack_list(self.authorization_protocol_data, "c"))
        buf.write(struct.pack("=4x", ))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, byte_order, protocol_major_version, protocol_minor_version, authorization_protocol_name_len, authorization_protocol_data_len, authorization_protocol_name, authorization_protocol_data):
        self = cls.__new__(cls)
        self.byte_order = byte_order
        self.protocol_major_version = protocol_major_version
        self.protocol_minor_version = protocol_minor_version
        self.authorization_protocol_name_len = authorization_protocol_name_len
        self.authorization_protocol_data_len = authorization_protocol_data_len
        self.authorization_protocol_name = authorization_protocol_name
        self.authorization_protocol_data = authorization_protocol_data
        return self
class SetupFailed(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.status, self.reason_len, self.protocol_major_version, self.protocol_minor_version, self.length = unpacker.unpack("BBHHH")
        self.reason = xcffib.List(unpacker, "c", self.reason_len)
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=BBHHH", self.status, self.reason_len, self.protocol_major_version, self.protocol_minor_version, self.length))
        buf.write(xcffib.pack_list(self.reason, "c"))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, status, reason_len, protocol_major_version, protocol_minor_version, length, reason):
        self = cls.__new__(cls)
        self.status = status
        self.reason_len = reason_len
        self.protocol_major_version = protocol_major_version
        self.protocol_minor_version = protocol_minor_version
        self.length = length
        self.reason = reason
        return self
class SetupAuthenticate(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.status, self.length = unpacker.unpack("B5xH")
        self.reason = xcffib.List(unpacker, "c", self.length * 4)
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B5xH", self.status, self.length))
        buf.write(xcffib.pack_list(self.reason, "c"))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, status, length, reason):
        self = cls.__new__(cls)
        self.status = status
        self.length = length
        self.reason = reason
        return self
class ImageOrder:
    LSBFirst = 0
    MSBFirst = 1
class Setup(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.status, self.protocol_major_version, self.protocol_minor_version, self.length, self.release_number, self.resource_id_base, self.resource_id_mask, self.motion_buffer_size, self.vendor_len, self.maximum_request_length, self.roots_len, self.pixmap_formats_len, self.image_byte_order, self.bitmap_format_bit_order, self.bitmap_format_scanline_unit, self.bitmap_format_scanline_pad, self.min_keycode, self.max_keycode = unpacker.unpack("BxHHHIIIIHHBBBBBBBB4x")
        self.vendor = xcffib.List(unpacker, "c", self.vendor_len)
        unpacker.pad(FORMAT)
        self.pixmap_formats = xcffib.List(unpacker, FORMAT, self.pixmap_formats_len)
        unpacker.pad(SCREEN)
        self.roots = xcffib.List(unpacker, SCREEN, self.roots_len)
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=BxHHHIIIIHHBBBBBBBB4x", self.status, self.protocol_major_version, self.protocol_minor_version, self.length, self.release_number, self.resource_id_base, self.resource_id_mask, self.motion_buffer_size, self.vendor_len, self.maximum_request_length, self.roots_len, self.pixmap_formats_len, self.image_byte_order, self.bitmap_format_bit_order, self.bitmap_format_scanline_unit, self.bitmap_format_scanline_pad, self.min_keycode, self.max_keycode))
        buf.write(xcffib.pack_list(self.vendor, "c"))
        buf.write(struct.pack("=4x", ))
        buf.write(xcffib.pack_list(self.pixmap_formats, FORMAT))
        buf.write(xcffib.pack_list(self.roots, SCREEN))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, status, protocol_major_version, protocol_minor_version, length, release_number, resource_id_base, resource_id_mask, motion_buffer_size, vendor_len, maximum_request_length, roots_len, pixmap_formats_len, image_byte_order, bitmap_format_bit_order, bitmap_format_scanline_unit, bitmap_format_scanline_pad, min_keycode, max_keycode, vendor, pixmap_formats, roots):
        self = cls.__new__(cls)
        self.status = status
        self.protocol_major_version = protocol_major_version
        self.protocol_minor_version = protocol_minor_version
        self.length = length
        self.release_number = release_number
        self.resource_id_base = resource_id_base
        self.resource_id_mask = resource_id_mask
        self.motion_buffer_size = motion_buffer_size
        self.vendor_len = vendor_len
        self.maximum_request_length = maximum_request_length
        self.roots_len = roots_len
        self.pixmap_formats_len = pixmap_formats_len
        self.image_byte_order = image_byte_order
        self.bitmap_format_bit_order = bitmap_format_bit_order
        self.bitmap_format_scanline_unit = bitmap_format_scanline_unit
        self.bitmap_format_scanline_pad = bitmap_format_scanline_pad
        self.min_keycode = min_keycode
        self.max_keycode = max_keycode
        self.vendor = vendor
        self.pixmap_formats = pixmap_formats
        self.roots = roots
        return self
class ModMask:
    Shift = 1 << 0
    Lock = 1 << 1
    Control = 1 << 2
    _1 = 1 << 3
    _2 = 1 << 4
    _3 = 1 << 5
    _4 = 1 << 6
    _5 = 1 << 7
    Any = 1 << 15
class KeyButMask:
    Shift = 1 << 0
    Lock = 1 << 1
    Control = 1 << 2
    Mod1 = 1 << 3
    Mod2 = 1 << 4
    Mod3 = 1 << 5
    Mod4 = 1 << 6
    Mod5 = 1 << 7
    Button1 = 1 << 8
    Button2 = 1 << 9
    Button3 = 1 << 10
    Button4 = 1 << 11
    Button5 = 1 << 12
class Window:
    _None = 0
class KeyPressEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.detail, self.time, self.root, self.event, self.child, self.root_x, self.root_y, self.event_x, self.event_y, self.state, self.same_screen = unpacker.unpack("xB2xIIIIhhhhHBx")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 2))
        buf.write(struct.pack("=B2xIIIIhhhhHBx", self.detail, self.time, self.root, self.event, self.child, self.root_x, self.root_y, self.event_x, self.event_y, self.state, self.same_screen))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, detail, time, root, event, child, root_x, root_y, event_x, event_y, state, same_screen):
        self = cls.__new__(cls)
        self.detail = detail
        self.time = time
        self.root = root
        self.event = event
        self.child = child
        self.root_x = root_x
        self.root_y = root_y
        self.event_x = event_x
        self.event_y = event_y
        self.state = state
        self.same_screen = same_screen
        return self
_events[2] = KeyPressEvent
class KeyReleaseEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.detail, self.time, self.root, self.event, self.child, self.root_x, self.root_y, self.event_x, self.event_y, self.state, self.same_screen = unpacker.unpack("xB2xIIIIhhhhHBx")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 3))
        buf.write(struct.pack("=B2xIIIIhhhhHBx", self.detail, self.time, self.root, self.event, self.child, self.root_x, self.root_y, self.event_x, self.event_y, self.state, self.same_screen))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, detail, time, root, event, child, root_x, root_y, event_x, event_y, state, same_screen):
        self = cls.__new__(cls)
        self.detail = detail
        self.time = time
        self.root = root
        self.event = event
        self.child = child
        self.root_x = root_x
        self.root_y = root_y
        self.event_x = event_x
        self.event_y = event_y
        self.state = state
        self.same_screen = same_screen
        return self
_events[3] = KeyReleaseEvent
class ButtonMask:
    _1 = 1 << 8
    _2 = 1 << 9
    _3 = 1 << 10
    _4 = 1 << 11
    _5 = 1 << 12
    Any = 1 << 15
class ButtonPressEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.detail, self.time, self.root, self.event, self.child, self.root_x, self.root_y, self.event_x, self.event_y, self.state, self.same_screen = unpacker.unpack("xB2xIIIIhhhhHBx")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 4))
        buf.write(struct.pack("=B2xIIIIhhhhHBx", self.detail, self.time, self.root, self.event, self.child, self.root_x, self.root_y, self.event_x, self.event_y, self.state, self.same_screen))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, detail, time, root, event, child, root_x, root_y, event_x, event_y, state, same_screen):
        self = cls.__new__(cls)
        self.detail = detail
        self.time = time
        self.root = root
        self.event = event
        self.child = child
        self.root_x = root_x
        self.root_y = root_y
        self.event_x = event_x
        self.event_y = event_y
        self.state = state
        self.same_screen = same_screen
        return self
_events[4] = ButtonPressEvent
class ButtonReleaseEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.detail, self.time, self.root, self.event, self.child, self.root_x, self.root_y, self.event_x, self.event_y, self.state, self.same_screen = unpacker.unpack("xB2xIIIIhhhhHBx")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 5))
        buf.write(struct.pack("=B2xIIIIhhhhHBx", self.detail, self.time, self.root, self.event, self.child, self.root_x, self.root_y, self.event_x, self.event_y, self.state, self.same_screen))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, detail, time, root, event, child, root_x, root_y, event_x, event_y, state, same_screen):
        self = cls.__new__(cls)
        self.detail = detail
        self.time = time
        self.root = root
        self.event = event
        self.child = child
        self.root_x = root_x
        self.root_y = root_y
        self.event_x = event_x
        self.event_y = event_y
        self.state = state
        self.same_screen = same_screen
        return self
_events[5] = ButtonReleaseEvent
class Motion:
    Normal = 0
    Hint = 1
class MotionNotifyEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.detail, self.time, self.root, self.event, self.child, self.root_x, self.root_y, self.event_x, self.event_y, self.state, self.same_screen = unpacker.unpack("xB2xIIIIhhhhHBx")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 6))
        buf.write(struct.pack("=B2xIIIIhhhhHBx", self.detail, self.time, self.root, self.event, self.child, self.root_x, self.root_y, self.event_x, self.event_y, self.state, self.same_screen))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, detail, time, root, event, child, root_x, root_y, event_x, event_y, state, same_screen):
        self = cls.__new__(cls)
        self.detail = detail
        self.time = time
        self.root = root
        self.event = event
        self.child = child
        self.root_x = root_x
        self.root_y = root_y
        self.event_x = event_x
        self.event_y = event_y
        self.state = state
        self.same_screen = same_screen
        return self
_events[6] = MotionNotifyEvent
class NotifyDetail:
    Ancestor = 0
    Virtual = 1
    Inferior = 2
    Nonlinear = 3
    NonlinearVirtual = 4
    Pointer = 5
    PointerRoot = 6
    _None = 7
class NotifyMode:
    Normal = 0
    Grab = 1
    Ungrab = 2
    WhileGrabbed = 3
class EnterNotifyEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.detail, self.time, self.root, self.event, self.child, self.root_x, self.root_y, self.event_x, self.event_y, self.state, self.mode, self.same_screen_focus = unpacker.unpack("xB2xIIIIhhhhHBB")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 7))
        buf.write(struct.pack("=B2xIIIIhhhhHBB", self.detail, self.time, self.root, self.event, self.child, self.root_x, self.root_y, self.event_x, self.event_y, self.state, self.mode, self.same_screen_focus))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, detail, time, root, event, child, root_x, root_y, event_x, event_y, state, mode, same_screen_focus):
        self = cls.__new__(cls)
        self.detail = detail
        self.time = time
        self.root = root
        self.event = event
        self.child = child
        self.root_x = root_x
        self.root_y = root_y
        self.event_x = event_x
        self.event_y = event_y
        self.state = state
        self.mode = mode
        self.same_screen_focus = same_screen_focus
        return self
_events[7] = EnterNotifyEvent
class LeaveNotifyEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.detail, self.time, self.root, self.event, self.child, self.root_x, self.root_y, self.event_x, self.event_y, self.state, self.mode, self.same_screen_focus = unpacker.unpack("xB2xIIIIhhhhHBB")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 8))
        buf.write(struct.pack("=B2xIIIIhhhhHBB", self.detail, self.time, self.root, self.event, self.child, self.root_x, self.root_y, self.event_x, self.event_y, self.state, self.mode, self.same_screen_focus))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, detail, time, root, event, child, root_x, root_y, event_x, event_y, state, mode, same_screen_focus):
        self = cls.__new__(cls)
        self.detail = detail
        self.time = time
        self.root = root
        self.event = event
        self.child = child
        self.root_x = root_x
        self.root_y = root_y
        self.event_x = event_x
        self.event_y = event_y
        self.state = state
        self.mode = mode
        self.same_screen_focus = same_screen_focus
        return self
_events[8] = LeaveNotifyEvent
class FocusInEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.detail, self.event, self.mode = unpacker.unpack("xB2xIB3x")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 9))
        buf.write(struct.pack("=B2xIB3x", self.detail, self.event, self.mode))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, detail, event, mode):
        self = cls.__new__(cls)
        self.detail = detail
        self.event = event
        self.mode = mode
        return self
_events[9] = FocusInEvent
class FocusOutEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.detail, self.event, self.mode = unpacker.unpack("xB2xIB3x")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 10))
        buf.write(struct.pack("=B2xIB3x", self.detail, self.event, self.mode))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, detail, event, mode):
        self = cls.__new__(cls)
        self.detail = detail
        self.event = event
        self.mode = mode
        return self
_events[10] = FocusOutEvent
class KeymapNotifyEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        unpacker.unpack("x")
        self.keys = xcffib.List(unpacker, "B", 31)
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 11))
        buf.write(xcffib.pack_list(self.keys, "B"))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, keys):
        self = cls.__new__(cls)
        self.keys = keys
        return self
_events[11] = KeymapNotifyEvent
class ExposeEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.window, self.x, self.y, self.width, self.height, self.count = unpacker.unpack("xx2xIHHHHH2x")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 12))
        buf.write(struct.pack("=x2xIHHHHH2x", self.window, self.x, self.y, self.width, self.height, self.count))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, window, x, y, width, height, count):
        self = cls.__new__(cls)
        self.window = window
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.count = count
        return self
_events[12] = ExposeEvent
class GraphicsExposureEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.drawable, self.x, self.y, self.width, self.height, self.minor_opcode, self.count, self.major_opcode = unpacker.unpack("xx2xIHHHHHHB3x")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 13))
        buf.write(struct.pack("=x2xIHHHHHHB3x", self.drawable, self.x, self.y, self.width, self.height, self.minor_opcode, self.count, self.major_opcode))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, drawable, x, y, width, height, minor_opcode, count, major_opcode):
        self = cls.__new__(cls)
        self.drawable = drawable
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.minor_opcode = minor_opcode
        self.count = count
        self.major_opcode = major_opcode
        return self
_events[13] = GraphicsExposureEvent
class NoExposureEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.drawable, self.minor_opcode, self.major_opcode = unpacker.unpack("xx2xIHBx")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 14))
        buf.write(struct.pack("=x2xIHBx", self.drawable, self.minor_opcode, self.major_opcode))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, drawable, minor_opcode, major_opcode):
        self = cls.__new__(cls)
        self.drawable = drawable
        self.minor_opcode = minor_opcode
        self.major_opcode = major_opcode
        return self
_events[14] = NoExposureEvent
class Visibility:
    Unobscured = 0
    PartiallyObscured = 1
    FullyObscured = 2
class VisibilityNotifyEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.window, self.state = unpacker.unpack("xx2xIB3x")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 15))
        buf.write(struct.pack("=x2xIB3x", self.window, self.state))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, window, state):
        self = cls.__new__(cls)
        self.window = window
        self.state = state
        return self
_events[15] = VisibilityNotifyEvent
class CreateNotifyEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.parent, self.window, self.x, self.y, self.width, self.height, self.border_width, self.override_redirect = unpacker.unpack("xx2xIIhhHHHBx")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 16))
        buf.write(struct.pack("=x2xIIhhHHHBx", self.parent, self.window, self.x, self.y, self.width, self.height, self.border_width, self.override_redirect))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, parent, window, x, y, width, height, border_width, override_redirect):
        self = cls.__new__(cls)
        self.parent = parent
        self.window = window
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.border_width = border_width
        self.override_redirect = override_redirect
        return self
_events[16] = CreateNotifyEvent
class DestroyNotifyEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.event, self.window = unpacker.unpack("xx2xII")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 17))
        buf.write(struct.pack("=x2xII", self.event, self.window))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, event, window):
        self = cls.__new__(cls)
        self.event = event
        self.window = window
        return self
_events[17] = DestroyNotifyEvent
class UnmapNotifyEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.event, self.window, self.from_configure = unpacker.unpack("xx2xIIB3x")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 18))
        buf.write(struct.pack("=x2xIIB3x", self.event, self.window, self.from_configure))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, event, window, from_configure):
        self = cls.__new__(cls)
        self.event = event
        self.window = window
        self.from_configure = from_configure
        return self
_events[18] = UnmapNotifyEvent
class MapNotifyEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.event, self.window, self.override_redirect = unpacker.unpack("xx2xIIB3x")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 19))
        buf.write(struct.pack("=x2xIIB3x", self.event, self.window, self.override_redirect))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, event, window, override_redirect):
        self = cls.__new__(cls)
        self.event = event
        self.window = window
        self.override_redirect = override_redirect
        return self
_events[19] = MapNotifyEvent
class MapRequestEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.parent, self.window = unpacker.unpack("xx2xII")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 20))
        buf.write(struct.pack("=x2xII", self.parent, self.window))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, parent, window):
        self = cls.__new__(cls)
        self.parent = parent
        self.window = window
        return self
_events[20] = MapRequestEvent
class ReparentNotifyEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.event, self.window, self.parent, self.x, self.y, self.override_redirect = unpacker.unpack("xx2xIIIhhB3x")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 21))
        buf.write(struct.pack("=x2xIIIhhB3x", self.event, self.window, self.parent, self.x, self.y, self.override_redirect))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, event, window, parent, x, y, override_redirect):
        self = cls.__new__(cls)
        self.event = event
        self.window = window
        self.parent = parent
        self.x = x
        self.y = y
        self.override_redirect = override_redirect
        return self
_events[21] = ReparentNotifyEvent
class ConfigureNotifyEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.event, self.window, self.above_sibling, self.x, self.y, self.width, self.height, self.border_width, self.override_redirect = unpacker.unpack("xx2xIIIhhHHHBx")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 22))
        buf.write(struct.pack("=x2xIIIhhHHHBx", self.event, self.window, self.above_sibling, self.x, self.y, self.width, self.height, self.border_width, self.override_redirect))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, event, window, above_sibling, x, y, width, height, border_width, override_redirect):
        self = cls.__new__(cls)
        self.event = event
        self.window = window
        self.above_sibling = above_sibling
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.border_width = border_width
        self.override_redirect = override_redirect
        return self
_events[22] = ConfigureNotifyEvent
class ConfigureRequestEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.stack_mode, self.parent, self.window, self.sibling, self.x, self.y, self.width, self.height, self.border_width, self.value_mask = unpacker.unpack("xB2xIIIhhHHHH")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 23))
        buf.write(struct.pack("=B2xIIIhhHHHH", self.stack_mode, self.parent, self.window, self.sibling, self.x, self.y, self.width, self.height, self.border_width, self.value_mask))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, stack_mode, parent, window, sibling, x, y, width, height, border_width, value_mask):
        self = cls.__new__(cls)
        self.stack_mode = stack_mode
        self.parent = parent
        self.window = window
        self.sibling = sibling
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.border_width = border_width
        self.value_mask = value_mask
        return self
_events[23] = ConfigureRequestEvent
class GravityNotifyEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.event, self.window, self.x, self.y = unpacker.unpack("xx2xIIhh")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 24))
        buf.write(struct.pack("=x2xIIhh", self.event, self.window, self.x, self.y))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, event, window, x, y):
        self = cls.__new__(cls)
        self.event = event
        self.window = window
        self.x = x
        self.y = y
        return self
_events[24] = GravityNotifyEvent
class ResizeRequestEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.window, self.width, self.height = unpacker.unpack("xx2xIHH")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 25))
        buf.write(struct.pack("=x2xIHH", self.window, self.width, self.height))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, window, width, height):
        self = cls.__new__(cls)
        self.window = window
        self.width = width
        self.height = height
        return self
_events[25] = ResizeRequestEvent
class Place:
    OnTop = 0
    OnBottom = 1
class CirculateNotifyEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.event, self.window, self.place = unpacker.unpack("xx2xII4xB3x")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 26))
        buf.write(struct.pack("=x2xII4xB3x", self.event, self.window, self.place))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, event, window, place):
        self = cls.__new__(cls)
        self.event = event
        self.window = window
        self.place = place
        return self
_events[26] = CirculateNotifyEvent
class CirculateRequestEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.event, self.window, self.place = unpacker.unpack("xx2xII4xB3x")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 27))
        buf.write(struct.pack("=x2xII4xB3x", self.event, self.window, self.place))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, event, window, place):
        self = cls.__new__(cls)
        self.event = event
        self.window = window
        self.place = place
        return self
_events[27] = CirculateRequestEvent
class Property:
    NewValue = 0
    Delete = 1
class PropertyNotifyEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.window, self.atom, self.time, self.state = unpacker.unpack("xx2xIIIB3x")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 28))
        buf.write(struct.pack("=x2xIIIB3x", self.window, self.atom, self.time, self.state))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, window, atom, time, state):
        self = cls.__new__(cls)
        self.window = window
        self.atom = atom
        self.time = time
        self.state = state
        return self
_events[28] = PropertyNotifyEvent
class SelectionClearEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.time, self.owner, self.selection = unpacker.unpack("xx2xIII")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 29))
        buf.write(struct.pack("=x2xIII", self.time, self.owner, self.selection))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, time, owner, selection):
        self = cls.__new__(cls)
        self.time = time
        self.owner = owner
        self.selection = selection
        return self
_events[29] = SelectionClearEvent
class Time:
    CurrentTime = 0
class Atom:
    _None = 0
    Any = 0
    PRIMARY = 1
    SECONDARY = 2
    ARC = 3
    ATOM = 4
    BITMAP = 5
    CARDINAL = 6
    COLORMAP = 7
    CURSOR = 8
    CUT_BUFFER0 = 9
    CUT_BUFFER1 = 10
    CUT_BUFFER2 = 11
    CUT_BUFFER3 = 12
    CUT_BUFFER4 = 13
    CUT_BUFFER5 = 14
    CUT_BUFFER6 = 15
    CUT_BUFFER7 = 16
    DRAWABLE = 17
    FONT = 18
    INTEGER = 19
    PIXMAP = 20
    POINT = 21
    RECTANGLE = 22
    RESOURCE_MANAGER = 23
    RGB_COLOR_MAP = 24
    RGB_BEST_MAP = 25
    RGB_BLUE_MAP = 26
    RGB_DEFAULT_MAP = 27
    RGB_GRAY_MAP = 28
    RGB_GREEN_MAP = 29
    RGB_RED_MAP = 30
    STRING = 31
    VISUALID = 32
    WINDOW = 33
    WM_COMMAND = 34
    WM_HINTS = 35
    WM_CLIENT_MACHINE = 36
    WM_ICON_NAME = 37
    WM_ICON_SIZE = 38
    WM_NAME = 39
    WM_NORMAL_HINTS = 40
    WM_SIZE_HINTS = 41
    WM_ZOOM_HINTS = 42
    MIN_SPACE = 43
    NORM_SPACE = 44
    MAX_SPACE = 45
    END_SPACE = 46
    SUPERSCRIPT_X = 47
    SUPERSCRIPT_Y = 48
    SUBSCRIPT_X = 49
    SUBSCRIPT_Y = 50
    UNDERLINE_POSITION = 51
    UNDERLINE_THICKNESS = 52
    STRIKEOUT_ASCENT = 53
    STRIKEOUT_DESCENT = 54
    ITALIC_ANGLE = 55
    X_HEIGHT = 56
    QUAD_WIDTH = 57
    WEIGHT = 58
    POINT_SIZE = 59
    RESOLUTION = 60
    COPYRIGHT = 61
    NOTICE = 62
    FONT_NAME = 63
    FAMILY_NAME = 64
    FULL_NAME = 65
    CAP_HEIGHT = 66
    WM_CLASS = 67
    WM_TRANSIENT_FOR = 68
class SelectionRequestEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.time, self.owner, self.requestor, self.selection, self.target, self.property = unpacker.unpack("xx2xIIIIII")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 30))
        buf.write(struct.pack("=x2xIIIIII", self.time, self.owner, self.requestor, self.selection, self.target, self.property))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, time, owner, requestor, selection, target, property):
        self = cls.__new__(cls)
        self.time = time
        self.owner = owner
        self.requestor = requestor
        self.selection = selection
        self.target = target
        self.property = property
        return self
_events[30] = SelectionRequestEvent
class SelectionNotifyEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.time, self.requestor, self.selection, self.target, self.property = unpacker.unpack("xx2xIIIII")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 31))
        buf.write(struct.pack("=x2xIIIII", self.time, self.requestor, self.selection, self.target, self.property))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, time, requestor, selection, target, property):
        self = cls.__new__(cls)
        self.time = time
        self.requestor = requestor
        self.selection = selection
        self.target = target
        self.property = property
        return self
_events[31] = SelectionNotifyEvent
class ColormapState:
    Uninstalled = 0
    Installed = 1
class Colormap:
    _None = 0
class ColormapNotifyEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.window, self.colormap, self.new, self.state = unpacker.unpack("xx2xIIBB2x")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 32))
        buf.write(struct.pack("=x2xIIBB2x", self.window, self.colormap, self.new, self.state))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, window, colormap, new, state):
        self = cls.__new__(cls)
        self.window = window
        self.colormap = colormap
        self.new = new
        self.state = state
        return self
_events[32] = ColormapNotifyEvent
class ClientMessageData(xcffib.Union):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Union.__init__(self, unpacker)
        self.data8 = xcffib.List(unpacker.copy(), "B", 20)
        self.data16 = xcffib.List(unpacker.copy(), "H", 10)
        self.data32 = xcffib.List(unpacker.copy(), "I", 5)
    def pack(self):
        buf = io.BytesIO()
        buf.write(xcffib.pack_list(self.data8, "B"))
        return buf.getvalue()
class ClientMessageEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.format, self.window, self.type = unpacker.unpack("xB2xII")
        self.data = ClientMessageData(unpacker)
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 33))
        buf.write(struct.pack("=B2xII", self.format, self.window, self.type))
        buf.write(self.data.pack() if hasattr(self.data, "pack") else ClientMessageData.synthetic(*self.data).pack())
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, format, window, type, data):
        self = cls.__new__(cls)
        self.format = format
        self.window = window
        self.type = type
        self.data = data
        return self
_events[33] = ClientMessageEvent
class Mapping:
    Modifier = 0
    Keyboard = 1
    Pointer = 2
class MappingNotifyEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.request, self.first_keycode, self.count = unpacker.unpack("xx2xBBBx")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 34))
        buf.write(struct.pack("=x2xBBBx", self.request, self.first_keycode, self.count))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, request, first_keycode, count):
        self = cls.__new__(cls)
        self.request = request
        self.first_keycode = first_keycode
        self.count = count
        return self
_events[34] = MappingNotifyEvent
class GeGenericEvent(xcffib.Event):
    xge = True
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        unpacker.unpack("xx2x22x")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 35))
        buf.write(struct.pack("=x2x22x"))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
_events[35] = GeGenericEvent
class RequestError(xcffib.Error):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Error.__init__(self, unpacker)
        base = unpacker.offset
        self.bad_value, self.minor_opcode, self.major_opcode = unpacker.unpack("xx2xIHBx")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 1))
        buf.write(struct.pack("=x2xIHBx", self.bad_value, self.minor_opcode, self.major_opcode))
        return buf.getvalue()
BadRequest = RequestError
_errors[1] = RequestError
class ValueError(xcffib.Error):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Error.__init__(self, unpacker)
        base = unpacker.offset
        self.bad_value, self.minor_opcode, self.major_opcode = unpacker.unpack("xx2xIHBx")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 2))
        buf.write(struct.pack("=x2xIHBx", self.bad_value, self.minor_opcode, self.major_opcode))
        return buf.getvalue()
BadValue = ValueError
_errors[2] = ValueError
class WindowError(xcffib.Error):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Error.__init__(self, unpacker)
        base = unpacker.offset
        self.bad_value, self.minor_opcode, self.major_opcode = unpacker.unpack("xx2xIHBx")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 3))
        buf.write(struct.pack("=x2xIHBx", self.bad_value, self.minor_opcode, self.major_opcode))
        return buf.getvalue()
BadWindow = WindowError
_errors[3] = WindowError
class PixmapError(xcffib.Error):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Error.__init__(self, unpacker)
        base = unpacker.offset
        self.bad_value, self.minor_opcode, self.major_opcode = unpacker.unpack("xx2xIHBx")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 4))
        buf.write(struct.pack("=x2xIHBx", self.bad_value, self.minor_opcode, self.major_opcode))
        return buf.getvalue()
BadPixmap = PixmapError
_errors[4] = PixmapError
class AtomError(xcffib.Error):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Error.__init__(self, unpacker)
        base = unpacker.offset
        self.bad_value, self.minor_opcode, self.major_opcode = unpacker.unpack("xx2xIHBx")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 5))
        buf.write(struct.pack("=x2xIHBx", self.bad_value, self.minor_opcode, self.major_opcode))
        return buf.getvalue()
BadAtom = AtomError
_errors[5] = AtomError
class CursorError(xcffib.Error):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Error.__init__(self, unpacker)
        base = unpacker.offset
        self.bad_value, self.minor_opcode, self.major_opcode = unpacker.unpack("xx2xIHBx")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 6))
        buf.write(struct.pack("=x2xIHBx", self.bad_value, self.minor_opcode, self.major_opcode))
        return buf.getvalue()
BadCursor = CursorError
_errors[6] = CursorError
class FontError(xcffib.Error):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Error.__init__(self, unpacker)
        base = unpacker.offset
        self.bad_value, self.minor_opcode, self.major_opcode = unpacker.unpack("xx2xIHBx")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 7))
        buf.write(struct.pack("=x2xIHBx", self.bad_value, self.minor_opcode, self.major_opcode))
        return buf.getvalue()
BadFont = FontError
_errors[7] = FontError
class MatchError(xcffib.Error):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Error.__init__(self, unpacker)
        base = unpacker.offset
        self.bad_value, self.minor_opcode, self.major_opcode = unpacker.unpack("xx2xIHBx")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 8))
        buf.write(struct.pack("=x2xIHBx", self.bad_value, self.minor_opcode, self.major_opcode))
        return buf.getvalue()
BadMatch = MatchError
_errors[8] = MatchError
class DrawableError(xcffib.Error):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Error.__init__(self, unpacker)
        base = unpacker.offset
        self.bad_value, self.minor_opcode, self.major_opcode = unpacker.unpack("xx2xIHBx")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 9))
        buf.write(struct.pack("=x2xIHBx", self.bad_value, self.minor_opcode, self.major_opcode))
        return buf.getvalue()
BadDrawable = DrawableError
_errors[9] = DrawableError
class AccessError(xcffib.Error):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Error.__init__(self, unpacker)
        base = unpacker.offset
        self.bad_value, self.minor_opcode, self.major_opcode = unpacker.unpack("xx2xIHBx")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 10))
        buf.write(struct.pack("=x2xIHBx", self.bad_value, self.minor_opcode, self.major_opcode))
        return buf.getvalue()
BadAccess = AccessError
_errors[10] = AccessError
class AllocError(xcffib.Error):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Error.__init__(self, unpacker)
        base = unpacker.offset
        self.bad_value, self.minor_opcode, self.major_opcode = unpacker.unpack("xx2xIHBx")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 11))
        buf.write(struct.pack("=x2xIHBx", self.bad_value, self.minor_opcode, self.major_opcode))
        return buf.getvalue()
BadAlloc = AllocError
_errors[11] = AllocError
class ColormapError(xcffib.Error):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Error.__init__(self, unpacker)
        base = unpacker.offset
        self.bad_value, self.minor_opcode, self.major_opcode = unpacker.unpack("xx2xIHBx")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 12))
        buf.write(struct.pack("=x2xIHBx", self.bad_value, self.minor_opcode, self.major_opcode))
        return buf.getvalue()
BadColormap = ColormapError
_errors[12] = ColormapError
class GContextError(xcffib.Error):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Error.__init__(self, unpacker)
        base = unpacker.offset
        self.bad_value, self.minor_opcode, self.major_opcode = unpacker.unpack("xx2xIHBx")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 13))
        buf.write(struct.pack("=x2xIHBx", self.bad_value, self.minor_opcode, self.major_opcode))
        return buf.getvalue()
BadGContext = GContextError
_errors[13] = GContextError
class IDChoiceError(xcffib.Error):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Error.__init__(self, unpacker)
        base = unpacker.offset
        self.bad_value, self.minor_opcode, self.major_opcode = unpacker.unpack("xx2xIHBx")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 14))
        buf.write(struct.pack("=x2xIHBx", self.bad_value, self.minor_opcode, self.major_opcode))
        return buf.getvalue()
BadIDChoice = IDChoiceError
_errors[14] = IDChoiceError
class NameError(xcffib.Error):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Error.__init__(self, unpacker)
        base = unpacker.offset
        self.bad_value, self.minor_opcode, self.major_opcode = unpacker.unpack("xx2xIHBx")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 15))
        buf.write(struct.pack("=x2xIHBx", self.bad_value, self.minor_opcode, self.major_opcode))
        return buf.getvalue()
BadName = NameError
_errors[15] = NameError
class LengthError(xcffib.Error):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Error.__init__(self, unpacker)
        base = unpacker.offset
        self.bad_value, self.minor_opcode, self.major_opcode = unpacker.unpack("xx2xIHBx")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 16))
        buf.write(struct.pack("=x2xIHBx", self.bad_value, self.minor_opcode, self.major_opcode))
        return buf.getvalue()
BadLength = LengthError
_errors[16] = LengthError
class ImplementationError(xcffib.Error):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Error.__init__(self, unpacker)
        base = unpacker.offset
        self.bad_value, self.minor_opcode, self.major_opcode = unpacker.unpack("xx2xIHBx")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 17))
        buf.write(struct.pack("=x2xIHBx", self.bad_value, self.minor_opcode, self.major_opcode))
        return buf.getvalue()
BadImplementation = ImplementationError
_errors[17] = ImplementationError
class WindowClass:
    CopyFromParent = 0
    InputOutput = 1
    InputOnly = 2
class CW:
    BackPixmap = 1 << 0
    BackPixel = 1 << 1
    BorderPixmap = 1 << 2
    BorderPixel = 1 << 3
    BitGravity = 1 << 4
    WinGravity = 1 << 5
    BackingStore = 1 << 6
    BackingPlanes = 1 << 7
    BackingPixel = 1 << 8
    OverrideRedirect = 1 << 9
    SaveUnder = 1 << 10
    EventMask = 1 << 11
    DontPropagate = 1 << 12
    Colormap = 1 << 13
    Cursor = 1 << 14
class BackPixmap:
    _None = 0
    ParentRelative = 1
class Gravity:
    BitForget = 0
    WinUnmap = 0
    NorthWest = 1
    North = 2
    NorthEast = 3
    West = 4
    Center = 5
    East = 6
    SouthWest = 7
    South = 8
    SouthEast = 9
    Static = 10
class MapState:
    Unmapped = 0
    Unviewable = 1
    Viewable = 2
class GetWindowAttributesReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.backing_store, self.visual, self._class, self.bit_gravity, self.win_gravity, self.backing_planes, self.backing_pixel, self.save_under, self.map_is_installed, self.map_state, self.override_redirect, self.colormap, self.all_event_masks, self.your_event_mask, self.do_not_propagate_mask = unpacker.unpack("xB2x4xIHBBIIBBBBIIIH2x")
        self.bufsize = unpacker.offset - base
class GetWindowAttributesCookie(xcffib.Cookie):
    reply_type = GetWindowAttributesReply
class SetMode:
    Insert = 0
    Delete = 1
class ConfigWindow:
    X = 1 << 0
    Y = 1 << 1
    Width = 1 << 2
    Height = 1 << 3
    BorderWidth = 1 << 4
    Sibling = 1 << 5
    StackMode = 1 << 6
class StackMode:
    Above = 0
    Below = 1
    TopIf = 2
    BottomIf = 3
    Opposite = 4
class Circulate:
    RaiseLowest = 0
    LowerHighest = 1
class GetGeometryReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.depth, self.root, self.x, self.y, self.width, self.height, self.border_width = unpacker.unpack("xB2x4xIhhHHH2x")
        self.bufsize = unpacker.offset - base
class GetGeometryCookie(xcffib.Cookie):
    reply_type = GetGeometryReply
class QueryTreeReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.root, self.parent, self.children_len = unpacker.unpack("xx2x4xIIH14x")
        self.children = xcffib.List(unpacker, "I", self.children_len)
        self.bufsize = unpacker.offset - base
class QueryTreeCookie(xcffib.Cookie):
    reply_type = QueryTreeReply
class InternAtomReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.atom, = unpacker.unpack("xx2x4xI")
        self.bufsize = unpacker.offset - base
class InternAtomCookie(xcffib.Cookie):
    reply_type = InternAtomReply
class GetAtomNameReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.name_len, = unpacker.unpack("xx2x4xH22x")
        self.name = xcffib.List(unpacker, "c", self.name_len)
        self.bufsize = unpacker.offset - base
class GetAtomNameCookie(xcffib.Cookie):
    reply_type = GetAtomNameReply
class PropMode:
    Replace = 0
    Prepend = 1
    Append = 2
class GetPropertyType:
    Any = 0
class GetPropertyReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.format, self.type, self.bytes_after, self.value_len = unpacker.unpack("xB2x4xIII12x")
        self.value = xcffib.List(unpacker, "c", self.value_len * (self.format // 8))
        self.bufsize = unpacker.offset - base
class GetPropertyCookie(xcffib.Cookie):
    reply_type = GetPropertyReply
class ListPropertiesReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.atoms_len, = unpacker.unpack("xx2x4xH22x")
        self.atoms = xcffib.List(unpacker, "I", self.atoms_len)
        self.bufsize = unpacker.offset - base
class ListPropertiesCookie(xcffib.Cookie):
    reply_type = ListPropertiesReply
class GetSelectionOwnerReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.owner, = unpacker.unpack("xx2x4xI")
        self.bufsize = unpacker.offset - base
class GetSelectionOwnerCookie(xcffib.Cookie):
    reply_type = GetSelectionOwnerReply
class SendEventDest:
    PointerWindow = 0
    ItemFocus = 1
class GrabMode:
    Sync = 0
    Async = 1
class GrabStatus:
    Success = 0
    AlreadyGrabbed = 1
    InvalidTime = 2
    NotViewable = 3
    Frozen = 4
class Cursor:
    _None = 0
class GrabPointerReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.status, = unpacker.unpack("xB2x4x")
        self.bufsize = unpacker.offset - base
class GrabPointerCookie(xcffib.Cookie):
    reply_type = GrabPointerReply
class ButtonIndex:
    Any = 0
    _1 = 1
    _2 = 2
    _3 = 3
    _4 = 4
    _5 = 5
class GrabKeyboardReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.status, = unpacker.unpack("xB2x4x")
        self.bufsize = unpacker.offset - base
class GrabKeyboardCookie(xcffib.Cookie):
    reply_type = GrabKeyboardReply
class Grab:
    Any = 0
class Allow:
    AsyncPointer = 0
    SyncPointer = 1
    ReplayPointer = 2
    AsyncKeyboard = 3
    SyncKeyboard = 4
    ReplayKeyboard = 5
    AsyncBoth = 6
    SyncBoth = 7
class QueryPointerReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.same_screen, self.root, self.child, self.root_x, self.root_y, self.win_x, self.win_y, self.mask = unpacker.unpack("xB2x4xIIhhhhH2x")
        self.bufsize = unpacker.offset - base
class QueryPointerCookie(xcffib.Cookie):
    reply_type = QueryPointerReply
class TIMECOORD(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.time, self.x, self.y = unpacker.unpack("Ihh")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=Ihh", self.time, self.x, self.y))
        return buf.getvalue()
    fixed_size = 8
    @classmethod
    def synthetic(cls, time, x, y):
        self = cls.__new__(cls)
        self.time = time
        self.x = x
        self.y = y
        return self
class GetMotionEventsReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.events_len, = unpacker.unpack("xx2x4xI20x")
        self.events = xcffib.List(unpacker, TIMECOORD, self.events_len)
        self.bufsize = unpacker.offset - base
class GetMotionEventsCookie(xcffib.Cookie):
    reply_type = GetMotionEventsReply
class TranslateCoordinatesReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.same_screen, self.child, self.dst_x, self.dst_y = unpacker.unpack("xB2x4xIhh")
        self.bufsize = unpacker.offset - base
class TranslateCoordinatesCookie(xcffib.Cookie):
    reply_type = TranslateCoordinatesReply
class InputFocus:
    _None = 0
    PointerRoot = 1
    Parent = 2
    FollowKeyboard = 3
class GetInputFocusReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.revert_to, self.focus = unpacker.unpack("xB2x4xI")
        self.bufsize = unpacker.offset - base
class GetInputFocusCookie(xcffib.Cookie):
    reply_type = GetInputFocusReply
class QueryKeymapReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        unpacker.unpack("xx2x4x")
        self.keys = xcffib.List(unpacker, "B", 32)
        self.bufsize = unpacker.offset - base
class QueryKeymapCookie(xcffib.Cookie):
    reply_type = QueryKeymapReply
class FontDraw:
    LeftToRight = 0
    RightToLeft = 1
class FONTPROP(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.name, self.value = unpacker.unpack("II")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=II", self.name, self.value))
        return buf.getvalue()
    fixed_size = 8
    @classmethod
    def synthetic(cls, name, value):
        self = cls.__new__(cls)
        self.name = name
        self.value = value
        return self
class CHARINFO(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.left_side_bearing, self.right_side_bearing, self.character_width, self.ascent, self.descent, self.attributes = unpacker.unpack("hhhhhH")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=hhhhhH", self.left_side_bearing, self.right_side_bearing, self.character_width, self.ascent, self.descent, self.attributes))
        return buf.getvalue()
    fixed_size = 12
    @classmethod
    def synthetic(cls, left_side_bearing, right_side_bearing, character_width, ascent, descent, attributes):
        self = cls.__new__(cls)
        self.left_side_bearing = left_side_bearing
        self.right_side_bearing = right_side_bearing
        self.character_width = character_width
        self.ascent = ascent
        self.descent = descent
        self.attributes = attributes
        return self
class QueryFontReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        unpacker.unpack("xx2x4x")
        self.min_bounds = CHARINFO(unpacker)
        unpacker.unpack("4x")
        unpacker.pad(CHARINFO)
        self.max_bounds = CHARINFO(unpacker)
        self.min_char_or_byte2, self.max_char_or_byte2, self.default_char, self.properties_len, self.draw_direction, self.min_byte1, self.max_byte1, self.all_chars_exist, self.font_ascent, self.font_descent, self.char_infos_len = unpacker.unpack("4xHHHHBBBBhhI")
        unpacker.pad(FONTPROP)
        self.properties = xcffib.List(unpacker, FONTPROP, self.properties_len)
        unpacker.pad(CHARINFO)
        self.char_infos = xcffib.List(unpacker, CHARINFO, self.char_infos_len)
        self.bufsize = unpacker.offset - base
class QueryFontCookie(xcffib.Cookie):
    reply_type = QueryFontReply
class QueryTextExtentsReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.draw_direction, self.font_ascent, self.font_descent, self.overall_ascent, self.overall_descent, self.overall_width, self.overall_left, self.overall_right = unpacker.unpack("xB2x4xhhhhiii")
        self.bufsize = unpacker.offset - base
class QueryTextExtentsCookie(xcffib.Cookie):
    reply_type = QueryTextExtentsReply
class STR(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.name_len, = unpacker.unpack("B")
        self.name = xcffib.List(unpacker, "c", self.name_len)
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", self.name_len))
        buf.write(xcffib.pack_list(self.name, "c"))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, name_len, name):
        self = cls.__new__(cls)
        self.name_len = name_len
        self.name = name
        return self
class ListFontsReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.names_len, = unpacker.unpack("xx2x4xH22x")
        self.names = xcffib.List(unpacker, STR, self.names_len)
        self.bufsize = unpacker.offset - base
class ListFontsCookie(xcffib.Cookie):
    reply_type = ListFontsReply
class ListFontsWithInfoReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.name_len, = unpacker.unpack("xB2x4x")
        self.min_bounds = CHARINFO(unpacker)
        unpacker.unpack("4x")
        unpacker.pad(CHARINFO)
        self.max_bounds = CHARINFO(unpacker)
        self.min_char_or_byte2, self.max_char_or_byte2, self.default_char, self.properties_len, self.draw_direction, self.min_byte1, self.max_byte1, self.all_chars_exist, self.font_ascent, self.font_descent, self.replies_hint = unpacker.unpack("4xHHHHBBBBhhI")
        unpacker.pad(FONTPROP)
        self.properties = xcffib.List(unpacker, FONTPROP, self.properties_len)
        unpacker.pad("c")
        self.name = xcffib.List(unpacker, "c", self.name_len)
        self.bufsize = unpacker.offset - base
class ListFontsWithInfoCookie(xcffib.Cookie):
    reply_type = ListFontsWithInfoReply
class GetFontPathReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.path_len, = unpacker.unpack("xx2x4xH22x")
        self.path = xcffib.List(unpacker, STR, self.path_len)
        self.bufsize = unpacker.offset - base
class GetFontPathCookie(xcffib.Cookie):
    reply_type = GetFontPathReply
class GC:
    Function = 1 << 0
    PlaneMask = 1 << 1
    Foreground = 1 << 2
    Background = 1 << 3
    LineWidth = 1 << 4
    LineStyle = 1 << 5
    CapStyle = 1 << 6
    JoinStyle = 1 << 7
    FillStyle = 1 << 8
    FillRule = 1 << 9
    Tile = 1 << 10
    Stipple = 1 << 11
    TileStippleOriginX = 1 << 12
    TileStippleOriginY = 1 << 13
    Font = 1 << 14
    SubwindowMode = 1 << 15
    GraphicsExposures = 1 << 16
    ClipOriginX = 1 << 17
    ClipOriginY = 1 << 18
    ClipMask = 1 << 19
    DashOffset = 1 << 20
    DashList = 1 << 21
    ArcMode = 1 << 22
class GX:
    clear = 0
    _and = 1
    andReverse = 2
    copy = 3
    andInverted = 4
    noop = 5
    xor = 6
    _or = 7
    nor = 8
    equiv = 9
    invert = 10
    orReverse = 11
    copyInverted = 12
    orInverted = 13
    nand = 14
    set = 15
class LineStyle:
    Solid = 0
    OnOffDash = 1
    DoubleDash = 2
class CapStyle:
    NotLast = 0
    Butt = 1
    Round = 2
    Projecting = 3
class JoinStyle:
    Miter = 0
    Round = 1
    Bevel = 2
class FillStyle:
    Solid = 0
    Tiled = 1
    Stippled = 2
    OpaqueStippled = 3
class FillRule:
    EvenOdd = 0
    Winding = 1
class SubwindowMode:
    ClipByChildren = 0
    IncludeInferiors = 1
class ArcMode:
    Chord = 0
    PieSlice = 1
class ClipOrdering:
    Unsorted = 0
    YSorted = 1
    YXSorted = 2
    YXBanded = 3
class CoordMode:
    Origin = 0
    Previous = 1
class SEGMENT(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.x1, self.y1, self.x2, self.y2 = unpacker.unpack("hhhh")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=hhhh", self.x1, self.y1, self.x2, self.y2))
        return buf.getvalue()
    fixed_size = 8
    @classmethod
    def synthetic(cls, x1, y1, x2, y2):
        self = cls.__new__(cls)
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        return self
class PolyShape:
    Complex = 0
    Nonconvex = 1
    Convex = 2
class ImageFormat:
    XYBitmap = 0
    XYPixmap = 1
    ZPixmap = 2
class GetImageReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.depth, self.visual = unpacker.unpack("xB2x4xI20x")
        self.data = xcffib.List(unpacker, "B", self.length * 4)
        self.bufsize = unpacker.offset - base
class GetImageCookie(xcffib.Cookie):
    reply_type = GetImageReply
class ColormapAlloc:
    _None = 0
    All = 1
class ListInstalledColormapsReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.cmaps_len, = unpacker.unpack("xx2x4xH22x")
        self.cmaps = xcffib.List(unpacker, "I", self.cmaps_len)
        self.bufsize = unpacker.offset - base
class ListInstalledColormapsCookie(xcffib.Cookie):
    reply_type = ListInstalledColormapsReply
class AllocColorReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.red, self.green, self.blue, self.pixel = unpacker.unpack("xx2x4xHHH2xI")
        self.bufsize = unpacker.offset - base
class AllocColorCookie(xcffib.Cookie):
    reply_type = AllocColorReply
class AllocNamedColorReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.pixel, self.exact_red, self.exact_green, self.exact_blue, self.visual_red, self.visual_green, self.visual_blue = unpacker.unpack("xx2x4xIHHHHHH")
        self.bufsize = unpacker.offset - base
class AllocNamedColorCookie(xcffib.Cookie):
    reply_type = AllocNamedColorReply
class AllocColorCellsReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.pixels_len, self.masks_len = unpacker.unpack("xx2x4xHH20x")
        self.pixels = xcffib.List(unpacker, "I", self.pixels_len)
        unpacker.pad("I")
        self.masks = xcffib.List(unpacker, "I", self.masks_len)
        self.bufsize = unpacker.offset - base
class AllocColorCellsCookie(xcffib.Cookie):
    reply_type = AllocColorCellsReply
class AllocColorPlanesReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.pixels_len, self.red_mask, self.green_mask, self.blue_mask = unpacker.unpack("xx2x4xH2xIII8x")
        self.pixels = xcffib.List(unpacker, "I", self.pixels_len)
        self.bufsize = unpacker.offset - base
class AllocColorPlanesCookie(xcffib.Cookie):
    reply_type = AllocColorPlanesReply
class ColorFlag:
    Red = 1 << 0
    Green = 1 << 1
    Blue = 1 << 2
class COLORITEM(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.pixel, self.red, self.green, self.blue, self.flags = unpacker.unpack("IHHHBx")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=IHHHBx", self.pixel, self.red, self.green, self.blue, self.flags))
        return buf.getvalue()
    fixed_size = 12
    @classmethod
    def synthetic(cls, pixel, red, green, blue, flags):
        self = cls.__new__(cls)
        self.pixel = pixel
        self.red = red
        self.green = green
        self.blue = blue
        self.flags = flags
        return self
class RGB(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.red, self.green, self.blue = unpacker.unpack("HHH2x")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=HHH2x", self.red, self.green, self.blue))
        return buf.getvalue()
    fixed_size = 8
    @classmethod
    def synthetic(cls, red, green, blue):
        self = cls.__new__(cls)
        self.red = red
        self.green = green
        self.blue = blue
        return self
class QueryColorsReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.colors_len, = unpacker.unpack("xx2x4xH22x")
        self.colors = xcffib.List(unpacker, RGB, self.colors_len)
        self.bufsize = unpacker.offset - base
class QueryColorsCookie(xcffib.Cookie):
    reply_type = QueryColorsReply
class LookupColorReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.exact_red, self.exact_green, self.exact_blue, self.visual_red, self.visual_green, self.visual_blue = unpacker.unpack("xx2x4xHHHHHH")
        self.bufsize = unpacker.offset - base
class LookupColorCookie(xcffib.Cookie):
    reply_type = LookupColorReply
class Pixmap:
    _None = 0
class Font:
    _None = 0
class QueryShapeOf:
    LargestCursor = 0
    FastestTile = 1
    FastestStipple = 2
class QueryBestSizeReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.width, self.height = unpacker.unpack("xx2x4xHH")
        self.bufsize = unpacker.offset - base
class QueryBestSizeCookie(xcffib.Cookie):
    reply_type = QueryBestSizeReply
class QueryExtensionReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.present, self.major_opcode, self.first_event, self.first_error = unpacker.unpack("xx2x4xBBBB")
        self.bufsize = unpacker.offset - base
class QueryExtensionCookie(xcffib.Cookie):
    reply_type = QueryExtensionReply
class ListExtensionsReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.names_len, = unpacker.unpack("xB2x4x24x")
        self.names = xcffib.List(unpacker, STR, self.names_len)
        self.bufsize = unpacker.offset - base
class ListExtensionsCookie(xcffib.Cookie):
    reply_type = ListExtensionsReply
class GetKeyboardMappingReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.keysyms_per_keycode, = unpacker.unpack("xB2x4x24x")
        self.keysyms = xcffib.List(unpacker, "I", self.length)
        self.bufsize = unpacker.offset - base
class GetKeyboardMappingCookie(xcffib.Cookie):
    reply_type = GetKeyboardMappingReply
class KB:
    KeyClickPercent = 1 << 0
    BellPercent = 1 << 1
    BellPitch = 1 << 2
    BellDuration = 1 << 3
    Led = 1 << 4
    LedMode = 1 << 5
    Key = 1 << 6
    AutoRepeatMode = 1 << 7
class LedMode:
    Off = 0
    On = 1
class AutoRepeatMode:
    Off = 0
    On = 1
    Default = 2
class GetKeyboardControlReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.global_auto_repeat, self.led_mask, self.key_click_percent, self.bell_percent, self.bell_pitch, self.bell_duration = unpacker.unpack("xB2x4xIBBHH2x")
        self.auto_repeats = xcffib.List(unpacker, "B", 32)
        self.bufsize = unpacker.offset - base
class GetKeyboardControlCookie(xcffib.Cookie):
    reply_type = GetKeyboardControlReply
class GetPointerControlReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.acceleration_numerator, self.acceleration_denominator, self.threshold = unpacker.unpack("xx2x4xHHH18x")
        self.bufsize = unpacker.offset - base
class GetPointerControlCookie(xcffib.Cookie):
    reply_type = GetPointerControlReply
class Blanking:
    NotPreferred = 0
    Preferred = 1
    Default = 2
class Exposures:
    NotAllowed = 0
    Allowed = 1
    Default = 2
class GetScreenSaverReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.timeout, self.interval, self.prefer_blanking, self.allow_exposures = unpacker.unpack("xx2x4xHHBB18x")
        self.bufsize = unpacker.offset - base
class GetScreenSaverCookie(xcffib.Cookie):
    reply_type = GetScreenSaverReply
class HostMode:
    Insert = 0
    Delete = 1
class Family:
    Internet = 0
    DECnet = 1
    Chaos = 2
    ServerInterpreted = 5
    Internet6 = 6
class HOST(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.family, self.address_len = unpacker.unpack("BxH")
        self.address = xcffib.List(unpacker, "B", self.address_len)
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=BxH", self.family, self.address_len))
        buf.write(xcffib.pack_list(self.address, "B"))
        buf.write(struct.pack("=4x", ))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, family, address_len, address):
        self = cls.__new__(cls)
        self.family = family
        self.address_len = address_len
        self.address = address
        return self
class ListHostsReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.mode, self.hosts_len = unpacker.unpack("xB2x4xH22x")
        self.hosts = xcffib.List(unpacker, HOST, self.hosts_len)
        self.bufsize = unpacker.offset - base
class ListHostsCookie(xcffib.Cookie):
    reply_type = ListHostsReply
class AccessControl:
    Disable = 0
    Enable = 1
class CloseDown:
    DestroyAll = 0
    RetainPermanent = 1
    RetainTemporary = 2
class Kill:
    AllTemporary = 0
class ScreenSaver:
    Reset = 0
    Active = 1
class MappingStatus:
    Success = 0
    Busy = 1
    Failure = 2
class SetPointerMappingReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.status, = unpacker.unpack("xB2x4x")
        self.bufsize = unpacker.offset - base
class SetPointerMappingCookie(xcffib.Cookie):
    reply_type = SetPointerMappingReply
class GetPointerMappingReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.map_len, = unpacker.unpack("xB2x4x24x")
        self.map = xcffib.List(unpacker, "B", self.map_len)
        self.bufsize = unpacker.offset - base
class GetPointerMappingCookie(xcffib.Cookie):
    reply_type = GetPointerMappingReply
class MapIndex:
    Shift = 0
    Lock = 1
    Control = 2
    _1 = 3
    _2 = 4
    _3 = 5
    _4 = 6
    _5 = 7
class SetModifierMappingReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.status, = unpacker.unpack("xB2x4x")
        self.bufsize = unpacker.offset - base
class SetModifierMappingCookie(xcffib.Cookie):
    reply_type = SetModifierMappingReply
class GetModifierMappingReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.keycodes_per_modifier, = unpacker.unpack("xB2x4x24x")
        self.keycodes = xcffib.List(unpacker, "B", self.keycodes_per_modifier * 8)
        self.bufsize = unpacker.offset - base
class GetModifierMappingCookie(xcffib.Cookie):
    reply_type = GetModifierMappingReply
class xprotoExtension(xcffib.Extension):
    def CreateWindow(self, depth, wid, parent, x, y, width, height, border_width, _class, visual, value_mask, value_list, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xB2xIIhhHHHHII", depth, wid, parent, x, y, width, height, border_width, _class, visual, value_mask))
        if value_mask & CW.BackPixmap:
            background_pixmap = value_list.pop(0)
            buf.write(struct.pack("=I", background_pixmap))
        if value_mask & CW.BackPixel:
            background_pixel = value_list.pop(0)
            buf.write(struct.pack("=I", background_pixel))
        if value_mask & CW.BorderPixmap:
            border_pixmap = value_list.pop(0)
            buf.write(struct.pack("=I", border_pixmap))
        if value_mask & CW.BorderPixel:
            border_pixel = value_list.pop(0)
            buf.write(struct.pack("=I", border_pixel))
        if value_mask & CW.BitGravity:
            bit_gravity = value_list.pop(0)
            buf.write(struct.pack("=I", bit_gravity))
        if value_mask & CW.WinGravity:
            win_gravity = value_list.pop(0)
            buf.write(struct.pack("=I", win_gravity))
        if value_mask & CW.BackingStore:
            backing_store = value_list.pop(0)
            buf.write(struct.pack("=I", backing_store))
        if value_mask & CW.BackingPlanes:
            backing_planes = value_list.pop(0)
            buf.write(struct.pack("=I", backing_planes))
        if value_mask & CW.BackingPixel:
            backing_pixel = value_list.pop(0)
            buf.write(struct.pack("=I", backing_pixel))
        if value_mask & CW.OverrideRedirect:
            override_redirect = value_list.pop(0)
            buf.write(struct.pack("=I", override_redirect))
        if value_mask & CW.SaveUnder:
            save_under = value_list.pop(0)
            buf.write(struct.pack("=I", save_under))
        if value_mask & CW.EventMask:
            event_mask = value_list.pop(0)
            buf.write(struct.pack("=I", event_mask))
        if value_mask & CW.DontPropagate:
            do_not_propogate_mask = value_list.pop(0)
            buf.write(struct.pack("=I", do_not_propogate_mask))
        if value_mask & CW.Colormap:
            colormap = value_list.pop(0)
            buf.write(struct.pack("=I", colormap))
        if value_mask & CW.Cursor:
            cursor = value_list.pop(0)
            buf.write(struct.pack("=I", cursor))
        return self.send_request(1, buf, is_checked=is_checked)
    def ChangeWindowAttributes(self, window, value_mask, value_list, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", window, value_mask))
        if value_mask & CW.BackPixmap:
            background_pixmap = value_list.pop(0)
            buf.write(struct.pack("=I", background_pixmap))
        if value_mask & CW.BackPixel:
            background_pixel = value_list.pop(0)
            buf.write(struct.pack("=I", background_pixel))
        if value_mask & CW.BorderPixmap:
            border_pixmap = value_list.pop(0)
            buf.write(struct.pack("=I", border_pixmap))
        if value_mask & CW.BorderPixel:
            border_pixel = value_list.pop(0)
            buf.write(struct.pack("=I", border_pixel))
        if value_mask & CW.BitGravity:
            bit_gravity = value_list.pop(0)
            buf.write(struct.pack("=I", bit_gravity))
        if value_mask & CW.WinGravity:
            win_gravity = value_list.pop(0)
            buf.write(struct.pack("=I", win_gravity))
        if value_mask & CW.BackingStore:
            backing_store = value_list.pop(0)
            buf.write(struct.pack("=I", backing_store))
        if value_mask & CW.BackingPlanes:
            backing_planes = value_list.pop(0)
            buf.write(struct.pack("=I", backing_planes))
        if value_mask & CW.BackingPixel:
            backing_pixel = value_list.pop(0)
            buf.write(struct.pack("=I", backing_pixel))
        if value_mask & CW.OverrideRedirect:
            override_redirect = value_list.pop(0)
            buf.write(struct.pack("=I", override_redirect))
        if value_mask & CW.SaveUnder:
            save_under = value_list.pop(0)
            buf.write(struct.pack("=I", save_under))
        if value_mask & CW.EventMask:
            event_mask = value_list.pop(0)
            buf.write(struct.pack("=I", event_mask))
        if value_mask & CW.DontPropagate:
            do_not_propogate_mask = value_list.pop(0)
            buf.write(struct.pack("=I", do_not_propogate_mask))
        if value_mask & CW.Colormap:
            colormap = value_list.pop(0)
            buf.write(struct.pack("=I", colormap))
        if value_mask & CW.Cursor:
            cursor = value_list.pop(0)
            buf.write(struct.pack("=I", cursor))
        return self.send_request(2, buf, is_checked=is_checked)
    def GetWindowAttributes(self, window, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", window))
        return self.send_request(3, buf, GetWindowAttributesCookie, is_checked=is_checked)
    def DestroyWindow(self, window, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", window))
        return self.send_request(4, buf, is_checked=is_checked)
    def DestroySubwindows(self, window, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", window))
        return self.send_request(5, buf, is_checked=is_checked)
    def ChangeSaveSet(self, mode, window, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xB2xI", mode, window))
        return self.send_request(6, buf, is_checked=is_checked)
    def ReparentWindow(self, window, parent, x, y, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIhh", window, parent, x, y))
        return self.send_request(7, buf, is_checked=is_checked)
    def MapWindow(self, window, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", window))
        return self.send_request(8, buf, is_checked=is_checked)
    def MapSubwindows(self, window, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", window))
        return self.send_request(9, buf, is_checked=is_checked)
    def UnmapWindow(self, window, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", window))
        return self.send_request(10, buf, is_checked=is_checked)
    def UnmapSubwindows(self, window, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", window))
        return self.send_request(11, buf, is_checked=is_checked)
    def ConfigureWindow(self, window, value_mask, value_list, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIH2x", window, value_mask))
        if value_mask & ConfigWindow.X:
            x = value_list.pop(0)
            buf.write(struct.pack("=i", x))
        if value_mask & ConfigWindow.Y:
            y = value_list.pop(0)
            buf.write(struct.pack("=i", y))
        if value_mask & ConfigWindow.Width:
            width = value_list.pop(0)
            buf.write(struct.pack("=I", width))
        if value_mask & ConfigWindow.Height:
            height = value_list.pop(0)
            buf.write(struct.pack("=I", height))
        if value_mask & ConfigWindow.BorderWidth:
            border_width = value_list.pop(0)
            buf.write(struct.pack("=I", border_width))
        if value_mask & ConfigWindow.Sibling:
            sibling = value_list.pop(0)
            buf.write(struct.pack("=I", sibling))
        if value_mask & ConfigWindow.StackMode:
            stack_mode = value_list.pop(0)
            buf.write(struct.pack("=I", stack_mode))
        return self.send_request(12, buf, is_checked=is_checked)
    def CirculateWindow(self, direction, window, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xB2xI", direction, window))
        return self.send_request(13, buf, is_checked=is_checked)
    def GetGeometry(self, drawable, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", drawable))
        return self.send_request(14, buf, GetGeometryCookie, is_checked=is_checked)
    def QueryTree(self, window, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", window))
        return self.send_request(15, buf, QueryTreeCookie, is_checked=is_checked)
    def InternAtom(self, only_if_exists, name_len, name, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xB2xH2x", only_if_exists, name_len))
        buf.write(xcffib.pack_list(name, "c"))
        return self.send_request(16, buf, InternAtomCookie, is_checked=is_checked)
    def GetAtomName(self, atom, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", atom))
        return self.send_request(17, buf, GetAtomNameCookie, is_checked=is_checked)
    def ChangeProperty(self, mode, window, property, type, format, data_len, data, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xB2xIIIB3xI", mode, window, property, type, format, data_len))
        buf.write(xcffib.pack_list(data, "c"))
        return self.send_request(18, buf, is_checked=is_checked)
    def DeleteProperty(self, window, property, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", window, property))
        return self.send_request(19, buf, is_checked=is_checked)
    def GetProperty(self, delete, window, property, type, long_offset, long_length, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xB2xIIIII", delete, window, property, type, long_offset, long_length))
        return self.send_request(20, buf, GetPropertyCookie, is_checked=is_checked)
    def ListProperties(self, window, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", window))
        return self.send_request(21, buf, ListPropertiesCookie, is_checked=is_checked)
    def SetSelectionOwner(self, owner, selection, time, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIII", owner, selection, time))
        return self.send_request(22, buf, is_checked=is_checked)
    def GetSelectionOwner(self, selection, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", selection))
        return self.send_request(23, buf, GetSelectionOwnerCookie, is_checked=is_checked)
    def ConvertSelection(self, requestor, selection, target, property, time, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIIII", requestor, selection, target, property, time))
        return self.send_request(24, buf, is_checked=is_checked)
    def SendEvent(self, propagate, destination, event_mask, event, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xB2xII", propagate, destination, event_mask))
        buf.write(xcffib.pack_list(event, "c"))
        return self.send_request(25, buf, is_checked=is_checked)
    def GrabPointer(self, owner_events, grab_window, event_mask, pointer_mode, keyboard_mode, confine_to, cursor, time, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xB2xIHBBIII", owner_events, grab_window, event_mask, pointer_mode, keyboard_mode, confine_to, cursor, time))
        return self.send_request(26, buf, GrabPointerCookie, is_checked=is_checked)
    def UngrabPointer(self, time, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", time))
        return self.send_request(27, buf, is_checked=is_checked)
    def GrabButton(self, owner_events, grab_window, event_mask, pointer_mode, keyboard_mode, confine_to, cursor, button, modifiers, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xB2xIHBBIIBxH", owner_events, grab_window, event_mask, pointer_mode, keyboard_mode, confine_to, cursor, button, modifiers))
        return self.send_request(28, buf, is_checked=is_checked)
    def UngrabButton(self, button, grab_window, modifiers, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xB2xIH2x", button, grab_window, modifiers))
        return self.send_request(29, buf, is_checked=is_checked)
    def ChangeActivePointerGrab(self, cursor, time, event_mask, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIH2x", cursor, time, event_mask))
        return self.send_request(30, buf, is_checked=is_checked)
    def GrabKeyboard(self, owner_events, grab_window, time, pointer_mode, keyboard_mode, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xB2xIIBB2x", owner_events, grab_window, time, pointer_mode, keyboard_mode))
        return self.send_request(31, buf, GrabKeyboardCookie, is_checked=is_checked)
    def UngrabKeyboard(self, time, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", time))
        return self.send_request(32, buf, is_checked=is_checked)
    def GrabKey(self, owner_events, grab_window, modifiers, key, pointer_mode, keyboard_mode, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xB2xIHBBB3x", owner_events, grab_window, modifiers, key, pointer_mode, keyboard_mode))
        return self.send_request(33, buf, is_checked=is_checked)
    def UngrabKey(self, key, grab_window, modifiers, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xB2xIH2x", key, grab_window, modifiers))
        return self.send_request(34, buf, is_checked=is_checked)
    def AllowEvents(self, mode, time, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xB2xI", mode, time))
        return self.send_request(35, buf, is_checked=is_checked)
    def GrabServer(self, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2x"))
        return self.send_request(36, buf, is_checked=is_checked)
    def UngrabServer(self, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2x"))
        return self.send_request(37, buf, is_checked=is_checked)
    def QueryPointer(self, window, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", window))
        return self.send_request(38, buf, QueryPointerCookie, is_checked=is_checked)
    def GetMotionEvents(self, window, start, stop, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIII", window, start, stop))
        return self.send_request(39, buf, GetMotionEventsCookie, is_checked=is_checked)
    def TranslateCoordinates(self, src_window, dst_window, src_x, src_y, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIhh", src_window, dst_window, src_x, src_y))
        return self.send_request(40, buf, TranslateCoordinatesCookie, is_checked=is_checked)
    def WarpPointer(self, src_window, dst_window, src_x, src_y, src_width, src_height, dst_x, dst_y, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIhhHHhh", src_window, dst_window, src_x, src_y, src_width, src_height, dst_x, dst_y))
        return self.send_request(41, buf, is_checked=is_checked)
    def SetInputFocus(self, revert_to, focus, time, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xB2xII", revert_to, focus, time))
        return self.send_request(42, buf, is_checked=is_checked)
    def GetInputFocus(self, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2x"))
        return self.send_request(43, buf, GetInputFocusCookie, is_checked=is_checked)
    def QueryKeymap(self, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2x"))
        return self.send_request(44, buf, QueryKeymapCookie, is_checked=is_checked)
    def OpenFont(self, fid, name_len, name, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIH2x", fid, name_len))
        buf.write(xcffib.pack_list(name, "c"))
        return self.send_request(45, buf, is_checked=is_checked)
    def CloseFont(self, font, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", font))
        return self.send_request(46, buf, is_checked=is_checked)
    def QueryFont(self, font, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", font))
        return self.send_request(47, buf, QueryFontCookie, is_checked=is_checked)
    def QueryTextExtents(self, font, string_len, string, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2x"))
        buf.write(struct.pack("=B", string_len & 1))
        buf.write(struct.pack("=I", font))
        buf.write(xcffib.pack_list(string, CHAR2B))
        return self.send_request(48, buf, QueryTextExtentsCookie, is_checked=is_checked)
    def ListFonts(self, max_names, pattern_len, pattern, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xHH", max_names, pattern_len))
        buf.write(xcffib.pack_list(pattern, "c"))
        return self.send_request(49, buf, ListFontsCookie, is_checked=is_checked)
    def ListFontsWithInfo(self, max_names, pattern_len, pattern, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xHH", max_names, pattern_len))
        buf.write(xcffib.pack_list(pattern, "c"))
        return self.send_request(50, buf, ListFontsWithInfoCookie, is_checked=is_checked)
    def SetFontPath(self, font_qty, font, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xH2x", font_qty))
        buf.write(xcffib.pack_list(font, STR))
        return self.send_request(51, buf, is_checked=is_checked)
    def GetFontPath(self, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2x"))
        return self.send_request(52, buf, GetFontPathCookie, is_checked=is_checked)
    def CreatePixmap(self, depth, pid, drawable, width, height, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xB2xIIHH", depth, pid, drawable, width, height))
        return self.send_request(53, buf, is_checked=is_checked)
    def FreePixmap(self, pixmap, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", pixmap))
        return self.send_request(54, buf, is_checked=is_checked)
    def CreateGC(self, cid, drawable, value_mask, value_list, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIII", cid, drawable, value_mask))
        if value_mask & GC.Function:
            function = value_list.pop(0)
            buf.write(struct.pack("=I", function))
        if value_mask & GC.PlaneMask:
            plane_mask = value_list.pop(0)
            buf.write(struct.pack("=I", plane_mask))
        if value_mask & GC.Foreground:
            foreground = value_list.pop(0)
            buf.write(struct.pack("=I", foreground))
        if value_mask & GC.Background:
            background = value_list.pop(0)
            buf.write(struct.pack("=I", background))
        if value_mask & GC.LineWidth:
            line_width = value_list.pop(0)
            buf.write(struct.pack("=I", line_width))
        if value_mask & GC.LineStyle:
            line_style = value_list.pop(0)
            buf.write(struct.pack("=I", line_style))
        if value_mask & GC.CapStyle:
            cap_style = value_list.pop(0)
            buf.write(struct.pack("=I", cap_style))
        if value_mask & GC.JoinStyle:
            join_style = value_list.pop(0)
            buf.write(struct.pack("=I", join_style))
        if value_mask & GC.FillStyle:
            fill_style = value_list.pop(0)
            buf.write(struct.pack("=I", fill_style))
        if value_mask & GC.FillRule:
            fill_rule = value_list.pop(0)
            buf.write(struct.pack("=I", fill_rule))
        if value_mask & GC.Tile:
            tile = value_list.pop(0)
            buf.write(struct.pack("=I", tile))
        if value_mask & GC.Stipple:
            stipple = value_list.pop(0)
            buf.write(struct.pack("=I", stipple))
        if value_mask & GC.TileStippleOriginX:
            tile_stipple_x_origin = value_list.pop(0)
            buf.write(struct.pack("=i", tile_stipple_x_origin))
        if value_mask & GC.TileStippleOriginY:
            tile_stipple_y_origin = value_list.pop(0)
            buf.write(struct.pack("=i", tile_stipple_y_origin))
        if value_mask & GC.Font:
            font = value_list.pop(0)
            buf.write(struct.pack("=I", font))
        if value_mask & GC.SubwindowMode:
            subwindow_mode = value_list.pop(0)
            buf.write(struct.pack("=I", subwindow_mode))
        if value_mask & GC.GraphicsExposures:
            graphics_exposures = value_list.pop(0)
            buf.write(struct.pack("=I", graphics_exposures))
        if value_mask & GC.ClipOriginX:
            clip_x_origin = value_list.pop(0)
            buf.write(struct.pack("=i", clip_x_origin))
        if value_mask & GC.ClipOriginY:
            clip_y_origin = value_list.pop(0)
            buf.write(struct.pack("=i", clip_y_origin))
        if value_mask & GC.ClipMask:
            clip_mask = value_list.pop(0)
            buf.write(struct.pack("=I", clip_mask))
        if value_mask & GC.DashOffset:
            dash_offset = value_list.pop(0)
            buf.write(struct.pack("=I", dash_offset))
        if value_mask & GC.DashList:
            dashes = value_list.pop(0)
            buf.write(struct.pack("=I", dashes))
        if value_mask & GC.ArcMode:
            arc_mode = value_list.pop(0)
            buf.write(struct.pack("=I", arc_mode))
        return self.send_request(55, buf, is_checked=is_checked)
    def ChangeGC(self, gc, value_mask, value_list, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", gc, value_mask))
        if value_mask & GC.Function:
            function = value_list.pop(0)
            buf.write(struct.pack("=I", function))
        if value_mask & GC.PlaneMask:
            plane_mask = value_list.pop(0)
            buf.write(struct.pack("=I", plane_mask))
        if value_mask & GC.Foreground:
            foreground = value_list.pop(0)
            buf.write(struct.pack("=I", foreground))
        if value_mask & GC.Background:
            background = value_list.pop(0)
            buf.write(struct.pack("=I", background))
        if value_mask & GC.LineWidth:
            line_width = value_list.pop(0)
            buf.write(struct.pack("=I", line_width))
        if value_mask & GC.LineStyle:
            line_style = value_list.pop(0)
            buf.write(struct.pack("=I", line_style))
        if value_mask & GC.CapStyle:
            cap_style = value_list.pop(0)
            buf.write(struct.pack("=I", cap_style))
        if value_mask & GC.JoinStyle:
            join_style = value_list.pop(0)
            buf.write(struct.pack("=I", join_style))
        if value_mask & GC.FillStyle:
            fill_style = value_list.pop(0)
            buf.write(struct.pack("=I", fill_style))
        if value_mask & GC.FillRule:
            fill_rule = value_list.pop(0)
            buf.write(struct.pack("=I", fill_rule))
        if value_mask & GC.Tile:
            tile = value_list.pop(0)
            buf.write(struct.pack("=I", tile))
        if value_mask & GC.Stipple:
            stipple = value_list.pop(0)
            buf.write(struct.pack("=I", stipple))
        if value_mask & GC.TileStippleOriginX:
            tile_stipple_x_origin = value_list.pop(0)
            buf.write(struct.pack("=i", tile_stipple_x_origin))
        if value_mask & GC.TileStippleOriginY:
            tile_stipple_y_origin = value_list.pop(0)
            buf.write(struct.pack("=i", tile_stipple_y_origin))
        if value_mask & GC.Font:
            font = value_list.pop(0)
            buf.write(struct.pack("=I", font))
        if value_mask & GC.SubwindowMode:
            subwindow_mode = value_list.pop(0)
            buf.write(struct.pack("=I", subwindow_mode))
        if value_mask & GC.GraphicsExposures:
            graphics_exposures = value_list.pop(0)
            buf.write(struct.pack("=I", graphics_exposures))
        if value_mask & GC.ClipOriginX:
            clip_x_origin = value_list.pop(0)
            buf.write(struct.pack("=i", clip_x_origin))
        if value_mask & GC.ClipOriginY:
            clip_y_origin = value_list.pop(0)
            buf.write(struct.pack("=i", clip_y_origin))
        if value_mask & GC.ClipMask:
            clip_mask = value_list.pop(0)
            buf.write(struct.pack("=I", clip_mask))
        if value_mask & GC.DashOffset:
            dash_offset = value_list.pop(0)
            buf.write(struct.pack("=I", dash_offset))
        if value_mask & GC.DashList:
            dashes = value_list.pop(0)
            buf.write(struct.pack("=I", dashes))
        if value_mask & GC.ArcMode:
            arc_mode = value_list.pop(0)
            buf.write(struct.pack("=I", arc_mode))
        return self.send_request(56, buf, is_checked=is_checked)
    def CopyGC(self, src_gc, dst_gc, value_mask, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIII", src_gc, dst_gc, value_mask))
        return self.send_request(57, buf, is_checked=is_checked)
    def SetDashes(self, gc, dash_offset, dashes_len, dashes, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIHH", gc, dash_offset, dashes_len))
        buf.write(xcffib.pack_list(dashes, "B"))
        return self.send_request(58, buf, is_checked=is_checked)
    def SetClipRectangles(self, ordering, gc, clip_x_origin, clip_y_origin, rectangles_len, rectangles, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xB2xIhh", ordering, gc, clip_x_origin, clip_y_origin))
        buf.write(xcffib.pack_list(rectangles, RECTANGLE))
        return self.send_request(59, buf, is_checked=is_checked)
    def FreeGC(self, gc, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", gc))
        return self.send_request(60, buf, is_checked=is_checked)
    def ClearArea(self, exposures, window, x, y, width, height, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xB2xIhhHH", exposures, window, x, y, width, height))
        return self.send_request(61, buf, is_checked=is_checked)
    def CopyArea(self, src_drawable, dst_drawable, gc, src_x, src_y, dst_x, dst_y, width, height, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIIhhhhHH", src_drawable, dst_drawable, gc, src_x, src_y, dst_x, dst_y, width, height))
        return self.send_request(62, buf, is_checked=is_checked)
    def CopyPlane(self, src_drawable, dst_drawable, gc, src_x, src_y, dst_x, dst_y, width, height, bit_plane, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIIhhhhHHI", src_drawable, dst_drawable, gc, src_x, src_y, dst_x, dst_y, width, height, bit_plane))
        return self.send_request(63, buf, is_checked=is_checked)
    def PolyPoint(self, coordinate_mode, drawable, gc, points_len, points, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xB2xII", coordinate_mode, drawable, gc))
        buf.write(xcffib.pack_list(points, POINT))
        return self.send_request(64, buf, is_checked=is_checked)
    def PolyLine(self, coordinate_mode, drawable, gc, points_len, points, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xB2xII", coordinate_mode, drawable, gc))
        buf.write(xcffib.pack_list(points, POINT))
        return self.send_request(65, buf, is_checked=is_checked)
    def PolySegment(self, drawable, gc, segments_len, segments, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", drawable, gc))
        buf.write(xcffib.pack_list(segments, SEGMENT))
        return self.send_request(66, buf, is_checked=is_checked)
    def PolyRectangle(self, drawable, gc, rectangles_len, rectangles, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", drawable, gc))
        buf.write(xcffib.pack_list(rectangles, RECTANGLE))
        return self.send_request(67, buf, is_checked=is_checked)
    def PolyArc(self, drawable, gc, arcs_len, arcs, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", drawable, gc))
        buf.write(xcffib.pack_list(arcs, ARC))
        return self.send_request(68, buf, is_checked=is_checked)
    def FillPoly(self, drawable, gc, shape, coordinate_mode, points_len, points, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIBB2x", drawable, gc, shape, coordinate_mode))
        buf.write(xcffib.pack_list(points, POINT))
        return self.send_request(69, buf, is_checked=is_checked)
    def PolyFillRectangle(self, drawable, gc, rectangles_len, rectangles, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", drawable, gc))
        buf.write(xcffib.pack_list(rectangles, RECTANGLE))
        return self.send_request(70, buf, is_checked=is_checked)
    def PolyFillArc(self, drawable, gc, arcs_len, arcs, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", drawable, gc))
        buf.write(xcffib.pack_list(arcs, ARC))
        return self.send_request(71, buf, is_checked=is_checked)
    def PutImage(self, format, drawable, gc, width, height, dst_x, dst_y, left_pad, depth, data_len, data, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xB2xIIHHhhBB2x", format, drawable, gc, width, height, dst_x, dst_y, left_pad, depth))
        buf.write(xcffib.pack_list(data, "B"))
        return self.send_request(72, buf, is_checked=is_checked)
    def GetImage(self, format, drawable, x, y, width, height, plane_mask, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xB2xIhhHHI", format, drawable, x, y, width, height, plane_mask))
        return self.send_request(73, buf, GetImageCookie, is_checked=is_checked)
    def PolyText8(self, drawable, gc, x, y, items_len, items, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIhh", drawable, gc, x, y))
        buf.write(xcffib.pack_list(items, "B"))
        return self.send_request(74, buf, is_checked=is_checked)
    def PolyText16(self, drawable, gc, x, y, items_len, items, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIhh", drawable, gc, x, y))
        buf.write(xcffib.pack_list(items, "B"))
        return self.send_request(75, buf, is_checked=is_checked)
    def ImageText8(self, string_len, drawable, gc, x, y, string, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xB2xIIhh", string_len, drawable, gc, x, y))
        buf.write(xcffib.pack_list(string, "c"))
        return self.send_request(76, buf, is_checked=is_checked)
    def ImageText16(self, string_len, drawable, gc, x, y, string, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xB2xIIhh", string_len, drawable, gc, x, y))
        buf.write(xcffib.pack_list(string, CHAR2B))
        return self.send_request(77, buf, is_checked=is_checked)
    def CreateColormap(self, alloc, mid, window, visual, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xB2xIII", alloc, mid, window, visual))
        return self.send_request(78, buf, is_checked=is_checked)
    def FreeColormap(self, cmap, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", cmap))
        return self.send_request(79, buf, is_checked=is_checked)
    def CopyColormapAndFree(self, mid, src_cmap, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", mid, src_cmap))
        return self.send_request(80, buf, is_checked=is_checked)
    def InstallColormap(self, cmap, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", cmap))
        return self.send_request(81, buf, is_checked=is_checked)
    def UninstallColormap(self, cmap, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", cmap))
        return self.send_request(82, buf, is_checked=is_checked)
    def ListInstalledColormaps(self, window, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", window))
        return self.send_request(83, buf, ListInstalledColormapsCookie, is_checked=is_checked)
    def AllocColor(self, cmap, red, green, blue, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIHHH2x", cmap, red, green, blue))
        return self.send_request(84, buf, AllocColorCookie, is_checked=is_checked)
    def AllocNamedColor(self, cmap, name_len, name, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIH2x", cmap, name_len))
        buf.write(xcffib.pack_list(name, "c"))
        return self.send_request(85, buf, AllocNamedColorCookie, is_checked=is_checked)
    def AllocColorCells(self, contiguous, cmap, colors, planes, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xB2xIHH", contiguous, cmap, colors, planes))
        return self.send_request(86, buf, AllocColorCellsCookie, is_checked=is_checked)
    def AllocColorPlanes(self, contiguous, cmap, colors, reds, greens, blues, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xB2xIHHHH", contiguous, cmap, colors, reds, greens, blues))
        return self.send_request(87, buf, AllocColorPlanesCookie, is_checked=is_checked)
    def FreeColors(self, cmap, plane_mask, pixels_len, pixels, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", cmap, plane_mask))
        buf.write(xcffib.pack_list(pixels, "I"))
        return self.send_request(88, buf, is_checked=is_checked)
    def StoreColors(self, cmap, items_len, items, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", cmap))
        buf.write(xcffib.pack_list(items, COLORITEM))
        return self.send_request(89, buf, is_checked=is_checked)
    def StoreNamedColor(self, flags, cmap, pixel, name_len, name, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xB2xIIH2x", flags, cmap, pixel, name_len))
        buf.write(xcffib.pack_list(name, "c"))
        return self.send_request(90, buf, is_checked=is_checked)
    def QueryColors(self, cmap, pixels_len, pixels, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", cmap))
        buf.write(xcffib.pack_list(pixels, "I"))
        return self.send_request(91, buf, QueryColorsCookie, is_checked=is_checked)
    def LookupColor(self, cmap, name_len, name, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIH2x", cmap, name_len))
        buf.write(xcffib.pack_list(name, "c"))
        return self.send_request(92, buf, LookupColorCookie, is_checked=is_checked)
    def CreateCursor(self, cid, source, mask, fore_red, fore_green, fore_blue, back_red, back_green, back_blue, x, y, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIIHHHHHHHH", cid, source, mask, fore_red, fore_green, fore_blue, back_red, back_green, back_blue, x, y))
        return self.send_request(93, buf, is_checked=is_checked)
    def CreateGlyphCursor(self, cid, source_font, mask_font, source_char, mask_char, fore_red, fore_green, fore_blue, back_red, back_green, back_blue, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIIHHHHHHHH", cid, source_font, mask_font, source_char, mask_char, fore_red, fore_green, fore_blue, back_red, back_green, back_blue))
        return self.send_request(94, buf, is_checked=is_checked)
    def FreeCursor(self, cursor, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", cursor))
        return self.send_request(95, buf, is_checked=is_checked)
    def RecolorCursor(self, cursor, fore_red, fore_green, fore_blue, back_red, back_green, back_blue, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIHHHHHH", cursor, fore_red, fore_green, fore_blue, back_red, back_green, back_blue))
        return self.send_request(96, buf, is_checked=is_checked)
    def QueryBestSize(self, _class, drawable, width, height, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xB2xIHH", _class, drawable, width, height))
        return self.send_request(97, buf, QueryBestSizeCookie, is_checked=is_checked)
    def QueryExtension(self, name_len, name, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xH2x", name_len))
        buf.write(xcffib.pack_list(name, "c"))
        return self.send_request(98, buf, QueryExtensionCookie, is_checked=is_checked)
    def ListExtensions(self, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2x"))
        return self.send_request(99, buf, ListExtensionsCookie, is_checked=is_checked)
    def ChangeKeyboardMapping(self, keycode_count, first_keycode, keysyms_per_keycode, keysyms, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xB2xBB2x", keycode_count, first_keycode, keysyms_per_keycode))
        buf.write(xcffib.pack_list(keysyms, "I"))
        return self.send_request(100, buf, is_checked=is_checked)
    def GetKeyboardMapping(self, first_keycode, count, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xBB", first_keycode, count))
        return self.send_request(101, buf, GetKeyboardMappingCookie, is_checked=is_checked)
    def ChangeKeyboardControl(self, value_mask, value_list, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", value_mask))
        if value_mask & KB.KeyClickPercent:
            key_click_percent = value_list.pop(0)
            buf.write(struct.pack("=i", key_click_percent))
        if value_mask & KB.BellPercent:
            bell_percent = value_list.pop(0)
            buf.write(struct.pack("=i", bell_percent))
        if value_mask & KB.BellPitch:
            bell_pitch = value_list.pop(0)
            buf.write(struct.pack("=i", bell_pitch))
        if value_mask & KB.BellDuration:
            bell_duration = value_list.pop(0)
            buf.write(struct.pack("=i", bell_duration))
        if value_mask & KB.Led:
            led = value_list.pop(0)
            buf.write(struct.pack("=I", led))
        if value_mask & KB.LedMode:
            led_mode = value_list.pop(0)
            buf.write(struct.pack("=I", led_mode))
        if value_mask & KB.Key:
            key = value_list.pop(0)
            buf.write(struct.pack("=I", key))
        if value_mask & KB.AutoRepeatMode:
            auto_repeat_mode = value_list.pop(0)
            buf.write(struct.pack("=I", auto_repeat_mode))
        return self.send_request(102, buf, is_checked=is_checked)
    def GetKeyboardControl(self, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2x"))
        return self.send_request(103, buf, GetKeyboardControlCookie, is_checked=is_checked)
    def Bell(self, percent, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xb2x", percent))
        return self.send_request(104, buf, is_checked=is_checked)
    def ChangePointerControl(self, acceleration_numerator, acceleration_denominator, threshold, do_acceleration, do_threshold, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xhhhBB", acceleration_numerator, acceleration_denominator, threshold, do_acceleration, do_threshold))
        return self.send_request(105, buf, is_checked=is_checked)
    def GetPointerControl(self, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2x"))
        return self.send_request(106, buf, GetPointerControlCookie, is_checked=is_checked)
    def SetScreenSaver(self, timeout, interval, prefer_blanking, allow_exposures, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xhhBB", timeout, interval, prefer_blanking, allow_exposures))
        return self.send_request(107, buf, is_checked=is_checked)
    def GetScreenSaver(self, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2x"))
        return self.send_request(108, buf, GetScreenSaverCookie, is_checked=is_checked)
    def ChangeHosts(self, mode, family, address_len, address, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xB2xBxH", mode, family, address_len))
        buf.write(xcffib.pack_list(address, "B"))
        return self.send_request(109, buf, is_checked=is_checked)
    def ListHosts(self, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2x"))
        return self.send_request(110, buf, ListHostsCookie, is_checked=is_checked)
    def SetAccessControl(self, mode, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xB2x", mode))
        return self.send_request(111, buf, is_checked=is_checked)
    def SetCloseDownMode(self, mode, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xB2x", mode))
        return self.send_request(112, buf, is_checked=is_checked)
    def KillClient(self, resource, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", resource))
        return self.send_request(113, buf, is_checked=is_checked)
    def RotateProperties(self, window, atoms_len, delta, atoms, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIHh", window, atoms_len, delta))
        buf.write(xcffib.pack_list(atoms, "I"))
        return self.send_request(114, buf, is_checked=is_checked)
    def ForceScreenSaver(self, mode, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xB2x", mode))
        return self.send_request(115, buf, is_checked=is_checked)
    def SetPointerMapping(self, map_len, map, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xB2x", map_len))
        buf.write(xcffib.pack_list(map, "B"))
        return self.send_request(116, buf, SetPointerMappingCookie, is_checked=is_checked)
    def GetPointerMapping(self, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2x"))
        return self.send_request(117, buf, GetPointerMappingCookie, is_checked=is_checked)
    def SetModifierMapping(self, keycodes_per_modifier, keycodes, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xB2x", keycodes_per_modifier))
        buf.write(xcffib.pack_list(keycodes, "B"))
        return self.send_request(118, buf, SetModifierMappingCookie, is_checked=is_checked)
    def GetModifierMapping(self, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2x"))
        return self.send_request(119, buf, GetModifierMappingCookie, is_checked=is_checked)
    def NoOperation(self, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2x"))
        return self.send_request(127, buf, is_checked=is_checked)
xcffib._add_core(xprotoExtension, Setup, _events, _errors)
