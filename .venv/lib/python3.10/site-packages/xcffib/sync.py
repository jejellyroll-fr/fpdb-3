import xcffib
import struct
import io
MAJOR_VERSION = 3
MINOR_VERSION = 1
key = xcffib.ExtensionKey("SYNC")
_events = {}
_errors = {}
from . import xproto
class ALARMSTATE:
    Active = 0
    Inactive = 1
    Destroyed = 2
class TESTTYPE:
    PositiveTransition = 0
    NegativeTransition = 1
    PositiveComparison = 2
    NegativeComparison = 3
class VALUETYPE:
    Absolute = 0
    Relative = 1
class CA:
    Counter = 1 << 0
    ValueType = 1 << 1
    Value = 1 << 2
    TestType = 1 << 3
    Delta = 1 << 4
    Events = 1 << 5
class INT64(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.hi, self.lo = unpacker.unpack("iI")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=iI", self.hi, self.lo))
        return buf.getvalue()
    fixed_size = 8
    @classmethod
    def synthetic(cls, hi, lo):
        self = cls.__new__(cls)
        self.hi = hi
        self.lo = lo
        return self
class SYSTEMCOUNTER(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.counter, = unpacker.unpack("I")
        self.resolution = INT64(unpacker)
        self.name_len, = unpacker.unpack("H")
        unpacker.pad("c")
        self.name = xcffib.List(unpacker, "c", self.name_len)
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=I", self.counter))
        buf.write(self.resolution.pack() if hasattr(self.resolution, "pack") else INT64.synthetic(*self.resolution).pack())
        buf.write(struct.pack("=H", self.name_len))
        buf.write(xcffib.pack_list(self.name, "c"))
        buf.write(struct.pack("=4x", ))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, counter, resolution, name_len, name):
        self = cls.__new__(cls)
        self.counter = counter
        self.resolution = resolution
        self.name_len = name_len
        self.name = name
        return self
class TRIGGER(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.counter, self.wait_type = unpacker.unpack("II")
        self.wait_value = INT64(unpacker)
        self.test_type, = unpacker.unpack("I")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=II", self.counter, self.wait_type))
        buf.write(self.wait_value.pack() if hasattr(self.wait_value, "pack") else INT64.synthetic(*self.wait_value).pack())
        buf.write(struct.pack("=I", self.test_type))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, counter, wait_type, wait_value, test_type):
        self = cls.__new__(cls)
        self.counter = counter
        self.wait_type = wait_type
        self.wait_value = wait_value
        self.test_type = test_type
        return self
class WAITCONDITION(xcffib.Struct):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Struct.__init__(self, unpacker)
        base = unpacker.offset
        self.trigger = TRIGGER(unpacker)
        unpacker.pad(INT64)
        self.event_threshold = INT64(unpacker)
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(self.trigger.pack() if hasattr(self.trigger, "pack") else TRIGGER.synthetic(*self.trigger).pack())
        buf.write(self.event_threshold.pack() if hasattr(self.event_threshold, "pack") else INT64.synthetic(*self.event_threshold).pack())
        return buf.getvalue()
    @classmethod
    def synthetic(cls, trigger, event_threshold):
        self = cls.__new__(cls)
        self.trigger = trigger
        self.event_threshold = event_threshold
        return self
class CounterError(xcffib.Error):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Error.__init__(self, unpacker)
        base = unpacker.offset
        self.bad_counter, self.minor_opcode, self.major_opcode = unpacker.unpack("xx2xIHB")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 0))
        buf.write(struct.pack("=x2xIHB", self.bad_counter, self.minor_opcode, self.major_opcode))
        return buf.getvalue()
BadCounter = CounterError
_errors[0] = CounterError
class AlarmError(xcffib.Error):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Error.__init__(self, unpacker)
        base = unpacker.offset
        self.bad_alarm, self.minor_opcode, self.major_opcode = unpacker.unpack("xx2xIHB")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 1))
        buf.write(struct.pack("=x2xIHB", self.bad_alarm, self.minor_opcode, self.major_opcode))
        return buf.getvalue()
BadAlarm = AlarmError
_errors[1] = AlarmError
class InitializeReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.major_version, self.minor_version = unpacker.unpack("xx2x4xBB22x")
        self.bufsize = unpacker.offset - base
class InitializeCookie(xcffib.Cookie):
    reply_type = InitializeReply
class ListSystemCountersReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.counters_len, = unpacker.unpack("xx2x4xI20x")
        self.counters = xcffib.List(unpacker, SYSTEMCOUNTER, self.counters_len)
        self.bufsize = unpacker.offset - base
class ListSystemCountersCookie(xcffib.Cookie):
    reply_type = ListSystemCountersReply
class QueryCounterReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        unpacker.unpack("xx2x4x")
        self.counter_value = INT64(unpacker)
        self.bufsize = unpacker.offset - base
class QueryCounterCookie(xcffib.Cookie):
    reply_type = QueryCounterReply
class QueryAlarmReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        unpacker.unpack("xx2x4x")
        self.trigger = TRIGGER(unpacker)
        unpacker.pad(INT64)
        self.delta = INT64(unpacker)
        self.events, self.state = unpacker.unpack("BB2x")
        self.bufsize = unpacker.offset - base
class QueryAlarmCookie(xcffib.Cookie):
    reply_type = QueryAlarmReply
class GetPriorityReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.priority, = unpacker.unpack("xx2x4xi")
        self.bufsize = unpacker.offset - base
class GetPriorityCookie(xcffib.Cookie):
    reply_type = GetPriorityReply
class QueryFenceReply(xcffib.Reply):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Reply.__init__(self, unpacker)
        base = unpacker.offset
        self.triggered, = unpacker.unpack("xx2x4xB23x")
        self.bufsize = unpacker.offset - base
class QueryFenceCookie(xcffib.Cookie):
    reply_type = QueryFenceReply
class CounterNotifyEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.kind, self.counter = unpacker.unpack("xB2xI")
        self.wait_value = INT64(unpacker)
        unpacker.pad(INT64)
        self.counter_value = INT64(unpacker)
        self.timestamp, self.count, self.destroyed = unpacker.unpack("IHBx")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 0))
        buf.write(struct.pack("=B2xI", self.kind, self.counter))
        buf.write(self.wait_value.pack() if hasattr(self.wait_value, "pack") else INT64.synthetic(*self.wait_value).pack())
        buf.write(self.counter_value.pack() if hasattr(self.counter_value, "pack") else INT64.synthetic(*self.counter_value).pack())
        buf.write(struct.pack("=I", self.timestamp))
        buf.write(struct.pack("=H", self.count))
        buf.write(struct.pack("=B", self.destroyed))
        buf.write(struct.pack("=x", ))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, kind, counter, wait_value, counter_value, timestamp, count, destroyed):
        self = cls.__new__(cls)
        self.kind = kind
        self.counter = counter
        self.wait_value = wait_value
        self.counter_value = counter_value
        self.timestamp = timestamp
        self.count = count
        self.destroyed = destroyed
        return self
_events[0] = CounterNotifyEvent
class AlarmNotifyEvent(xcffib.Event):
    xge = False
    def __init__(self, unpacker):
        if isinstance(unpacker, xcffib.Protobj):
            unpacker = xcffib.MemoryUnpacker(unpacker.pack())
        xcffib.Event.__init__(self, unpacker)
        base = unpacker.offset
        self.kind, self.alarm = unpacker.unpack("xB2xI")
        self.counter_value = INT64(unpacker)
        unpacker.pad(INT64)
        self.alarm_value = INT64(unpacker)
        self.timestamp, self.state = unpacker.unpack("IB3x")
        self.bufsize = unpacker.offset - base
    def pack(self):
        buf = io.BytesIO()
        buf.write(struct.pack("=B", 1))
        buf.write(struct.pack("=B2xI", self.kind, self.alarm))
        buf.write(self.counter_value.pack() if hasattr(self.counter_value, "pack") else INT64.synthetic(*self.counter_value).pack())
        buf.write(self.alarm_value.pack() if hasattr(self.alarm_value, "pack") else INT64.synthetic(*self.alarm_value).pack())
        buf.write(struct.pack("=I", self.timestamp))
        buf.write(struct.pack("=B", self.state))
        buf.write(struct.pack("=3x", ))
        buf_len = len(buf.getvalue())
        if buf_len < 32:
            buf.write(struct.pack("x" * (32 - buf_len)))
        return buf.getvalue()
    @classmethod
    def synthetic(cls, kind, alarm, counter_value, alarm_value, timestamp, state):
        self = cls.__new__(cls)
        self.kind = kind
        self.alarm = alarm
        self.counter_value = counter_value
        self.alarm_value = alarm_value
        self.timestamp = timestamp
        self.state = state
        return self
_events[1] = AlarmNotifyEvent
class syncExtension(xcffib.Extension):
    def Initialize(self, desired_major_version, desired_minor_version, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xBB", desired_major_version, desired_minor_version))
        return self.send_request(0, buf, InitializeCookie, is_checked=is_checked)
    def ListSystemCounters(self, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2x"))
        return self.send_request(1, buf, ListSystemCountersCookie, is_checked=is_checked)
    def CreateCounter(self, id, initial_value, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", id))
        buf.write(initial_value.pack() if hasattr(initial_value, "pack") else INT64.synthetic(*initial_value).pack())
        return self.send_request(2, buf, is_checked=is_checked)
    def DestroyCounter(self, counter, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", counter))
        return self.send_request(6, buf, is_checked=is_checked)
    def QueryCounter(self, counter, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", counter))
        return self.send_request(5, buf, QueryCounterCookie, is_checked=is_checked)
    def Await(self, wait_list_len, wait_list, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2x"))
        buf.write(xcffib.pack_list(wait_list, WAITCONDITION))
        return self.send_request(7, buf, is_checked=is_checked)
    def ChangeCounter(self, counter, amount, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", counter))
        buf.write(amount.pack() if hasattr(amount, "pack") else INT64.synthetic(*amount).pack())
        return self.send_request(4, buf, is_checked=is_checked)
    def SetCounter(self, counter, value, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", counter))
        buf.write(value.pack() if hasattr(value, "pack") else INT64.synthetic(*value).pack())
        return self.send_request(3, buf, is_checked=is_checked)
    def CreateAlarm(self, id, value_mask, value_list, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", id, value_mask))
        if value_mask & CA.Counter:
            counter = value_list.pop(0)
            buf.write(struct.pack("=I", counter))
        if value_mask & CA.ValueType:
            valueType = value_list.pop(0)
            buf.write(struct.pack("=I", valueType))
        if value_mask & CA.Value:
            value = value_list.pop(0)
            buf.write(value.pack() if hasattr(value, "pack") else INT64.synthetic(*value).pack())
        if value_mask & CA.TestType:
            testType = value_list.pop(0)
            buf.write(struct.pack("=I", testType))
        if value_mask & CA.Delta:
            delta = value_list.pop(0)
            buf.write(delta.pack() if hasattr(delta, "pack") else INT64.synthetic(*delta).pack())
        if value_mask & CA.Events:
            events = value_list.pop(0)
            buf.write(struct.pack("=I", events))
        return self.send_request(8, buf, is_checked=is_checked)
    def ChangeAlarm(self, id, value_mask, value_list, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xII", id, value_mask))
        if value_mask & CA.Counter:
            counter = value_list.pop(0)
            buf.write(struct.pack("=I", counter))
        if value_mask & CA.ValueType:
            valueType = value_list.pop(0)
            buf.write(struct.pack("=I", valueType))
        if value_mask & CA.Value:
            value = value_list.pop(0)
            buf.write(value.pack() if hasattr(value, "pack") else INT64.synthetic(*value).pack())
        if value_mask & CA.TestType:
            testType = value_list.pop(0)
            buf.write(struct.pack("=I", testType))
        if value_mask & CA.Delta:
            delta = value_list.pop(0)
            buf.write(delta.pack() if hasattr(delta, "pack") else INT64.synthetic(*delta).pack())
        if value_mask & CA.Events:
            events = value_list.pop(0)
            buf.write(struct.pack("=I", events))
        return self.send_request(9, buf, is_checked=is_checked)
    def DestroyAlarm(self, alarm, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", alarm))
        return self.send_request(11, buf, is_checked=is_checked)
    def QueryAlarm(self, alarm, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", alarm))
        return self.send_request(10, buf, QueryAlarmCookie, is_checked=is_checked)
    def SetPriority(self, id, priority, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIi", id, priority))
        return self.send_request(12, buf, is_checked=is_checked)
    def GetPriority(self, id, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", id))
        return self.send_request(13, buf, GetPriorityCookie, is_checked=is_checked)
    def CreateFence(self, drawable, fence, initially_triggered, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xIIB", drawable, fence, initially_triggered))
        return self.send_request(14, buf, is_checked=is_checked)
    def TriggerFence(self, fence, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", fence))
        return self.send_request(15, buf, is_checked=is_checked)
    def ResetFence(self, fence, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", fence))
        return self.send_request(16, buf, is_checked=is_checked)
    def DestroyFence(self, fence, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", fence))
        return self.send_request(17, buf, is_checked=is_checked)
    def QueryFence(self, fence, is_checked=True):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2xI", fence))
        return self.send_request(18, buf, QueryFenceCookie, is_checked=is_checked)
    def AwaitFence(self, fence_list_len, fence_list, is_checked=False):
        buf = io.BytesIO()
        buf.write(struct.pack("=xx2x"))
        buf.write(xcffib.pack_list(fence_list, "I"))
        return self.send_request(19, buf, is_checked=is_checked)
xcffib._add_ext(key, syncExtension, _events, _errors)
