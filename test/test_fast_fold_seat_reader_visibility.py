"""Losing the window seat reader must not be silent.

Fast-Fold seats are read from the table window; the client log can only name a
player once they have acted, so falling back to it makes the stat blocks appear
one at a time over the first betting round. That fallback is what a user
reports as "the Fast-Fold HUD is slow again".

Both ways of losing the reader were logged at INFO, or not logged at all. The
root logger is pinned to WARNING (loggingFpdb.DIAGNOSTIC_LEVEL_CAP) and
"hud_main" is persisted lower still, so neither line ever reached a user's log:
the HUD degraded to exactly the reported symptom and said nothing about it.
"""

from __future__ import annotations

import logging
import os

import pytest

from fpdb_3_legacy import winamax_ax_seats


@pytest.fixture
def _no_usable_com(monkeypatch):
    """Make building the client fail, on any platform.

    Where comtypes is installed (a Windows dev box) the real GetModule would
    succeed, so it is made to raise; where it is not (Linux/macOS CI) the import
    inside _windows_uia raises on its own and reaches the same branch. Either
    way the test pins the behaviour rather than the machine it runs on.
    """
    try:
        import comtypes.client
    except ImportError:
        return
    monkeypatch.setattr(
        comtypes.client,
        "GetModule",
        lambda *_a, **_k: (_ for _ in ()).throw(OSError("COM is not available")),
    )


@pytest.fixture(autouse=True)
def _fresh_client():
    """The client is process-wide state; a test must not leak it into the next."""
    winamax_ax_seats.reset_windows_uia()
    yield
    winamax_ax_seats.reset_windows_uia()


def test_a_reader_that_cannot_be_built_says_so(monkeypatch, caplog, _no_usable_com) -> None:
    """COM refusing to start, or a frozen build that cannot generate the wrapper."""
    monkeypatch.setattr(winamax_ax_seats.platform, "system", lambda: "Windows")

    with caplog.at_level(logging.WARNING, logger=winamax_ax_seats.log.name):
        assert winamax_ax_seats._windows_uia() is None

    assert "Fast-Fold seats will come from the client log" in caplog.text


def test_the_reader_is_not_re_reported_on_every_hand(monkeypatch, caplog, _no_usable_com) -> None:
    """The failure is remembered, so the warning must be once per process."""
    monkeypatch.setattr(winamax_ax_seats.platform, "system", lambda: "Windows")

    with caplog.at_level(logging.WARNING, logger=winamax_ax_seats.log.name):
        winamax_ax_seats._windows_uia()
        winamax_ax_seats._windows_uia()
        winamax_ax_seats._windows_uia()

    assert caplog.text.count("Fast-Fold seats will come from the client log") == 1


def test_a_build_without_comtypes_says_so_at_startup(monkeypatch, caplog) -> None:
    """The packaging failure the PyInstaller hook exists to prevent.

    prewarm() returned silently when is_ax_available() was False, so a build
    that had lost comtypes looked exactly like a healthy one.
    """
    monkeypatch.setattr(winamax_ax_seats.platform, "system", lambda: "Windows")
    monkeypatch.setattr(winamax_ax_seats, "is_ax_available", lambda: False)

    with caplog.at_level(logging.WARNING, logger=winamax_ax_seats.log.name):
        winamax_ax_seats.WinamaxAXSeatReader().prewarm()

    assert "comtypes is not importable" in caplog.text


def test_a_healthy_reader_warns_about_nothing(monkeypatch, caplog) -> None:
    """A working session must stay quiet, or the warning means nothing."""
    monkeypatch.setattr(winamax_ax_seats.platform, "system", lambda: "Windows")
    monkeypatch.setattr(winamax_ax_seats, "is_ax_available", lambda: True)
    monkeypatch.setattr(winamax_ax_seats, "_windows_uia", lambda: object())

    with caplog.at_level(logging.WARNING, logger=winamax_ax_seats.log.name):
        winamax_ax_seats.WinamaxAXSeatReader().prewarm()

    assert caplog.text == ""


def test_nothing_is_warned_off_windows(monkeypatch, caplog) -> None:
    monkeypatch.setattr(winamax_ax_seats.platform, "system", lambda: "Darwin")

    with caplog.at_level(logging.WARNING, logger=winamax_ax_seats.log.name):
        winamax_ax_seats.WinamaxAXSeatReader().prewarm()

    assert caplog.text == ""


class _FakeElement:
    """The parts of an IUIAutomationElement collect_labels touches."""

    def __init__(self, name: str, pid: int, x: int = 10, y: int = 20) -> None:
        self.CurrentName = name
        self.CurrentProcessId = pid
        self.CurrentBoundingRectangle = type("R", (), {"left": x, "top": y})()


class _FakeFound:
    def __init__(self, elements) -> None:
        self._elements = elements
        self.Length = len(elements)

    def GetElement(self, index):
        return self._elements[index]


class _FakeRoot:
    def __init__(self, elements) -> None:
        self._found = _FakeFound(elements)

    def FindAll(self, _scope, _condition):
        return self._found


def _client() -> winamax_ax_seats._WindowsUIAClient:
    return winamax_ax_seats._WindowsUIAClient(automation=object(), condition=object())


def test_the_huds_own_stat_blocks_are_not_read_back_as_players() -> None:
    """The HUD's blocks are transient children of the table, so they are in the subtree.

    A real walk of a Winamax table came back holding 'HUD - stats', 'VP 0.0',
    '3B -' and the rest of the HUD's own output. Those are stat abbreviations,
    not players, and the reader must not feed them to seats_from_labels.
    """
    own = os.getpid()
    root = _FakeRoot(
        [
            _FakeElement("Bussy67", pid=own + 1),
            _FakeElement("HUD - stats", pid=own),
            _FakeElement("VP 0.0", pid=own),
            _FakeElement("3B -", pid=own),
            _FakeElement("0newayticket", pid=own + 1),
        ],
    )

    labels = _client().collect_labels(root)

    assert [label.login for label in labels] == ["Bussy67", "0newayticket"]


def test_a_label_whose_owner_cannot_be_read_is_kept() -> None:
    """Fail open: an unreadable pid is not proof the label is ours.

    Dropping it would cost a real player their block, which is the failure this
    reader exists to avoid.
    """

    class _Unreadable:
        CurrentName = "Bussy67"
        CurrentBoundingRectangle = type("R", (), {"left": 10, "top": 20})()

        @property
        def CurrentProcessId(self):  # noqa: N802 - UIA API
            msg = "element is gone"
            raise OSError(msg)

    assert [label.login for label in _client().collect_labels(_FakeRoot([_Unreadable()]))] == ["Bussy67"]


@pytest.fixture(autouse=True)
def _one_client(monkeypatch):
    """A single, stable owning process, unless a test says otherwise."""
    monkeypatch.setattr(winamax_ax_seats, "_window_pid", lambda _hwnd: 4242)


@pytest.fixture
def run_requests_here(monkeypatch):
    """Run the request thread's work inline, so the tests stay deterministic.

    The request is fired and forgotten in production -- AccessibleObjectFromWindow
    and QueryService have no timeout, and a hung client must not hold the GUI
    thread -- but a test that has to wait for a thread is a test that will flake.
    """

    class _Inline:
        def __init__(self, target, args=(), **_kwargs) -> None:
            self._target, self._args = target, args

        def start(self) -> None:
            self._target(*self._args)

    monkeypatch.setattr(winamax_ax_seats.threading, "Thread", _Inline)


def test_a_chromium_client_is_asked_to_publish_its_tree(monkeypatch, run_requests_here) -> None:
    """What the macOS reader does with AXManualAccessibility, on Windows.

    "Chromium only builds its web accessibility tree when an assistive client
    asks for it; without this the windows expose nothing but their titles" --
    and that is exactly what a Winamax table measured on Windows: six nodes, the
    window title among them, not one player.
    """
    winamax_ax_seats.forget_window_state()
    monkeypatch.setattr(winamax_ax_seats.platform, "system", lambda: "Windows")
    asked = []
    monkeypatch.setattr(winamax_ax_seats, "_send_get_object", lambda hwnd: ([hwnd, 4242], 2))
    monkeypatch.setattr(winamax_ax_seats, "_ask_for_complete_tree", lambda hwnd: asked.append(hwnd) or True)

    winamax_ax_seats.request_windows_accessibility(1234)

    # The frame and its render surface: the felt is drawn in the child.
    assert asked == [1234, 4242]


def test_the_request_does_not_run_on_the_calling_thread(monkeypatch) -> None:
    """AccessibleObjectFromWindow and QueryService have no timeout of their own.

    SendMessageTimeoutW is bounded; those two are not -- they send their own
    WM_GETOBJECT and wait. A hung client could hold the HUD's GUI thread for as
    long as it liked, which is what the circuit breaker around this reader exists
    to avoid.
    """
    winamax_ax_seats.forget_window_state()
    monkeypatch.setattr(winamax_ax_seats.platform, "system", lambda: "Windows")
    started = []

    class _Recording:
        def __init__(self, target, args=(), **kwargs) -> None:
            started.append((target, args, kwargs.get("daemon")))

        def start(self) -> None:
            pass

    monkeypatch.setattr(winamax_ax_seats.threading, "Thread", _Recording)
    monkeypatch.setattr(winamax_ax_seats, "_send_get_object", lambda _h: pytest.fail("ran inline"))

    winamax_ax_seats.request_windows_accessibility(1234)

    assert len(started) == 1
    target, args, daemon = started[0]
    assert target is winamax_ax_seats._request_windows_accessibility_now
    # The owner is read on the calling thread -- a local call that cannot block --
    # and carried, so the worker records the window against the client it asked.
    assert args == (1234, 4242)
    assert daemon is True


def test_a_window_is_only_asked_once(monkeypatch, run_requests_here) -> None:
    """Once the client has built its tree, asking again buys nothing."""
    winamax_ax_seats.forget_window_state()
    monkeypatch.setattr(winamax_ax_seats.platform, "system", lambda: "Windows")
    calls = []
    monkeypatch.setattr(
        winamax_ax_seats,
        "_send_get_object",
        lambda hwnd: (calls.append(hwnd), ([hwnd], 1))[1],
    )
    monkeypatch.setattr(winamax_ax_seats, "_ask_for_complete_tree", lambda _hwnd: True)

    for _ in range(3):
        winamax_ax_seats.request_windows_accessibility(1234)

    assert calls == [1234]


def test_a_second_read_does_not_ask_while_the_first_request_is_in_the_air(monkeypatch) -> None:
    """The thread makes the window between asking and knowing wide enough to matter."""
    winamax_ax_seats.forget_window_state()
    monkeypatch.setattr(winamax_ax_seats.platform, "system", lambda: "Windows")
    started = []

    class _NeverRuns:
        def __init__(self, target, args=(), **_kwargs) -> None:
            started.append(args)

        def start(self) -> None:
            pass

    monkeypatch.setattr(winamax_ax_seats.threading, "Thread", _NeverRuns)

    winamax_ax_seats.request_windows_accessibility(1234)
    winamax_ax_seats.request_windows_accessibility(1234)

    assert started == [(1234, 4242)]


def test_a_client_that_will_not_answer_is_not_fatal(monkeypatch, run_requests_here) -> None:
    """A busy or blocked client must not take the HUD down with it."""
    winamax_ax_seats.forget_window_state()
    monkeypatch.setattr(winamax_ax_seats.platform, "system", lambda: "Windows")

    def _boom(_hwnd):
        msg = "the desktop went away"
        raise OSError(msg)

    monkeypatch.setattr(winamax_ax_seats, "_send_get_object", _boom)

    winamax_ax_seats.request_windows_accessibility(1234)  # must not raise
    # And it is not left in flight, so a later read tries again.
    assert winamax_ax_seats._windows[1234].in_flight is False


def test_a_window_with_no_handle_is_not_asked(monkeypatch) -> None:
    monkeypatch.setattr(winamax_ax_seats.platform, "system", lambda: "Windows")
    monkeypatch.setattr(winamax_ax_seats.threading, "Thread", lambda **_k: pytest.fail("asked anyway"))

    winamax_ax_seats.request_windows_accessibility(0)


def test_nothing_is_asked_off_windows(monkeypatch) -> None:
    winamax_ax_seats.forget_window_state()
    monkeypatch.setattr(winamax_ax_seats.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(winamax_ax_seats.threading, "Thread", lambda **_k: pytest.fail("asked anyway"))

    winamax_ax_seats.request_windows_accessibility(1234)


class _Rect:
    def __init__(self, left, top, right, bottom) -> None:
        self.left, self.top, self.right, self.bottom = left, top, right, bottom


#: A whole ring, in the coordinate space the client actually reports.
FULL_RING = [
    winamax_ax_seats.AXSeat("CTroPinJust", 1990, 81),
    winamax_ax_seats.AXSeat("MuckEtMousse", 2200, 117),
    winamax_ax_seats.AXSeat("ayuga1312", 2213, 329),
    winamax_ax_seats.AXSeat("jejellyroll", 2000, 365),
    winamax_ax_seats.AXSeat("depor81", 1783, 329),
    winamax_ax_seats.AXSeat("BluffTesMots", 1767, 117),
]
OFF_FRAME = _Rect(3840, 0, 4800, 739)


@pytest.fixture(autouse=True)
def _fresh_centres():
    winamax_ax_seats.forget_window_state()
    yield
    winamax_ax_seats.forget_window_state()


def test_a_full_ring_is_measured_from_the_players() -> None:
    """The client reports its content in a different space from its frame.

    A window at x 3840..4800 whose players sit at x 1767..2259: a centre taken
    from the frame lies to one side of every player, they all read as lying in
    one direction from it, and the ring collapses into a single slot.
    """
    centre = winamax_ax_seats._table_centre(FULL_RING, OFF_FRAME, 6, hwnd=1)

    assert centre == (1990.0, 223.0)


def test_a_partial_ring_has_no_centre_until_a_full_one_was_seen() -> None:
    """Statistics over the wrong opponents is worse than none at all.

    The hero and the two chairs beside them make a band across the bottom of the
    felt, whose bounding box centre sits well below the table's. The hero still
    lands on slot 0, so the caller would accept it, and the neighbours would land
    two chairs away from where they sit.
    """
    partial = [FULL_RING[3], FULL_RING[4], FULL_RING[2]]

    assert winamax_ax_seats._table_centre(partial, OFF_FRAME, 6, hwnd=1) is None


def test_a_partial_ring_reuses_the_centre_a_full_one_measured() -> None:
    measured = winamax_ax_seats._table_centre(FULL_RING, OFF_FRAME, 6, hwnd=1)
    partial = [FULL_RING[3], FULL_RING[4]]

    assert winamax_ax_seats._table_centre(partial, OFF_FRAME, 6, hwnd=1) == measured


def test_each_window_learns_its_own_centre() -> None:
    """Two tables, two coordinate spaces: one must not answer for the other."""
    winamax_ax_seats._table_centre(FULL_RING, OFF_FRAME, 6, hwnd=1)

    assert winamax_ax_seats._table_centre([FULL_RING[3]], OFF_FRAME, 6, hwnd=2) is None


def test_the_frame_is_used_when_the_players_are_inside_it() -> None:
    """A client reporting one consistent space needs none of this."""
    players = [winamax_ax_seats.AXSeat("jejellyroll", 400, 300)]

    centre = winamax_ax_seats._table_centre(players, _Rect(0, 0, 960, 740), 6, hwnd=1)

    assert centre == (480.0, 370.0)


def test_no_players_has_no_centre() -> None:
    assert winamax_ax_seats._table_centre([], _Rect(0, 0, 100, 200), 6, hwnd=1) is None


def test_read_window_for_reads_by_handle(monkeypatch) -> None:
    """The diagnostic tool holds a HWND and no reader; this is its way in."""
    seen = {}

    def _read(self, title, max_seats, table_pos=None, window_id=None):
        seen.update(title=title, max_seats=max_seats, window_id=window_id)
        return {0: "jejellyroll"}

    monkeypatch.setattr(winamax_ax_seats.WinamaxAXSeatReader, "read_window", _read)

    assert winamax_ax_seats.read_window_for(1234, "Winamax Colorado 1") == {0: "jejellyroll"}
    assert seen == {"title": "Winamax Colorado 1", "max_seats": 6, "window_id": 1234}


def test_a_window_that_answered_nothing_is_asked_again(monkeypatch, run_requests_here) -> None:
    """SendMessageTimeoutW reports a hung client by returning zero, not by raising.

    _ask_for_complete_tree turns every COM failure into False the same way, so an
    attempt can fail completely with nothing thrown. Recording the window then
    wrote it off for the whole session on one badly timed try -- a client still
    starting up never gets asked again.
    """
    winamax_ax_seats.forget_window_state()
    monkeypatch.setattr(winamax_ax_seats.platform, "system", lambda: "Windows")
    calls = []
    monkeypatch.setattr(
        winamax_ax_seats,
        "_send_get_object",
        lambda hwnd: (calls.append(hwnd), ([hwnd], 0))[1],
    )
    monkeypatch.setattr(winamax_ax_seats, "_ask_for_complete_tree", lambda _hwnd: False)

    winamax_ax_seats.request_windows_accessibility(1234)
    winamax_ax_seats.request_windows_accessibility(1234)

    assert calls == [1234, 1234]


def test_an_ia2_query_alone_is_enough_to_call_it_asked(monkeypatch, run_requests_here) -> None:
    """IAccessible2 is the one that matters; WM_GETOBJECT need not have landed."""
    winamax_ax_seats.forget_window_state()
    monkeypatch.setattr(winamax_ax_seats.platform, "system", lambda: "Windows")
    calls = []
    monkeypatch.setattr(
        winamax_ax_seats,
        "_send_get_object",
        lambda hwnd: (calls.append(hwnd), ([hwnd], 0))[1],
    )
    monkeypatch.setattr(winamax_ax_seats, "_ask_for_complete_tree", lambda _hwnd: True)

    winamax_ax_seats.request_windows_accessibility(1234)
    winamax_ax_seats.request_windows_accessibility(1234)

    assert calls == [1234]


def test_a_centre_is_not_reused_after_the_window_moved() -> None:
    """A table moved between hands puts its chairs somewhere else.

    The remembered point is then somewhere on the desktop the seats no longer
    surround, and seats arranged around it land on the wrong chairs while still
    passing the caller's hero check.
    """
    winamax_ax_seats._table_centre(FULL_RING, OFF_FRAME, 6, hwnd=1)
    moved = _Rect(0, 0, 960, 739)

    assert winamax_ax_seats._table_centre([FULL_RING[3], FULL_RING[4]], moved, 6, hwnd=1) is None


def test_a_recycled_handle_does_not_inherit_the_old_table_s_centre() -> None:
    """Windows hands a closed table's HWND to the next one."""
    winamax_ax_seats._table_centre(FULL_RING, OFF_FRAME, 6, hwnd=1)
    reused = _Rect(4800, 0, 5760, 739)

    assert winamax_ax_seats._table_centre([FULL_RING[3]], reused, 6, hwnd=1) is None
    # And the stale entry is gone rather than waiting to be asked again.
    assert winamax_ax_seats._windows[1].centre is None


def test_a_delivered_wm_getobject_alone_is_not_enough(monkeypatch, run_requests_here) -> None:
    """WM_GETOBJECT gets Chromium as far as its native widgets and no further.

    The frame, the Views controls, the dialogs -- never the felt, which is web
    content and needs the IAccessible2 query. Recording the window on the
    WM_GETOBJECT alone left a table whose IA2 query failed transiently without
    opponents for the rest of the session, until the breaker gave up on it.
    """
    winamax_ax_seats.forget_window_state()
    monkeypatch.setattr(winamax_ax_seats.platform, "system", lambda: "Windows")
    calls = []
    monkeypatch.setattr(
        winamax_ax_seats,
        "_send_get_object",
        lambda hwnd: (calls.append(hwnd), ([hwnd], 1))[1],
    )
    monkeypatch.setattr(winamax_ax_seats, "_ask_for_complete_tree", lambda _hwnd: False)

    winamax_ax_seats.request_windows_accessibility(1234)
    winamax_ax_seats.request_windows_accessibility(1234)

    assert calls == [1234, 1234]
    assert winamax_ax_seats._windows[1234].asked is False


def test_a_handle_recycled_by_a_restarted_client_is_asked_again(monkeypatch, run_requests_here) -> None:
    """Windows recycles a closed table's handle to whatever opens next.

    Winamax restarted while the HUD stays alive gets a new process for the same
    numbers. A handle remembered by its digits alone would tell that new Chromium
    it had already been asked, and it would never publish its felt -- every hand
    back to the log-derived seats, then the breaker.
    """
    winamax_ax_seats.forget_window_state()
    monkeypatch.setattr(winamax_ax_seats.platform, "system", lambda: "Windows")
    calls = []
    monkeypatch.setattr(
        winamax_ax_seats,
        "_send_get_object",
        lambda hwnd: (calls.append(hwnd), ([hwnd], 1))[1],
    )
    monkeypatch.setattr(winamax_ax_seats, "_ask_for_complete_tree", lambda _hwnd: True)

    monkeypatch.setattr(winamax_ax_seats, "_window_pid", lambda _hwnd: 1000)
    winamax_ax_seats.request_windows_accessibility(1234)
    winamax_ax_seats.request_windows_accessibility(1234)
    assert calls == [1234]  # same client, asked once

    monkeypatch.setattr(winamax_ax_seats, "_window_pid", lambda _hwnd: 2000)
    winamax_ax_seats.request_windows_accessibility(1234)

    assert calls == [1234, 1234]


def test_an_unreadable_owner_does_not_read_as_already_asked(monkeypatch, run_requests_here) -> None:
    """GetWindowThreadProcessId answers None for a window that has gone.

    None is a real answer here -- it must not collide with "never asked", or the
    first read of a window whose owner could not be determined would skip the
    request outright.
    """
    winamax_ax_seats.forget_window_state()
    monkeypatch.setattr(winamax_ax_seats.platform, "system", lambda: "Windows")
    monkeypatch.setattr(winamax_ax_seats, "_window_pid", lambda _hwnd: None)
    calls = []
    monkeypatch.setattr(
        winamax_ax_seats,
        "_send_get_object",
        lambda hwnd: (calls.append(hwnd), ([hwnd], 1))[1],
    )
    monkeypatch.setattr(winamax_ax_seats, "_ask_for_complete_tree", lambda _hwnd: True)

    winamax_ax_seats.request_windows_accessibility(1234)

    assert calls == [1234]


def test_one_window_can_be_forgotten_without_the_others(monkeypatch) -> None:
    """A table retiring should not cost its neighbour what it learned."""
    winamax_ax_seats.forget_window_state()
    monkeypatch.setattr(winamax_ax_seats.platform, "system", lambda: "Windows")
    winamax_ax_seats._table_centre(FULL_RING, OFF_FRAME, 6, hwnd=1)
    winamax_ax_seats._table_centre(FULL_RING, OFF_FRAME, 6, hwnd=2)

    winamax_ax_seats.forget_window_state(1)

    assert 1 not in winamax_ax_seats._windows
    assert winamax_ax_seats._windows[2].centre is not None


def test_a_new_owner_takes_the_old_client_s_state_with_it(monkeypatch, run_requests_here) -> None:
    """The refactor's own promise: dropped whole when the client changes.

    It detected the new owner and started a fresh request, but kept everything
    the old client had taught it. A table reopening at the same geometry would
    reuse the previous one's centre and seat its stats over the wrong opponents;
    a request the exited process never answered would still read as in the air,
    and the new client would never be asked at all.
    """
    winamax_ax_seats.forget_window_state()
    monkeypatch.setattr(winamax_ax_seats.platform, "system", lambda: "Windows")
    monkeypatch.setattr(winamax_ax_seats, "_send_get_object", lambda hwnd: ([hwnd], 1))
    monkeypatch.setattr(winamax_ax_seats, "_ask_for_complete_tree", lambda _hwnd: True)

    monkeypatch.setattr(winamax_ax_seats, "_window_pid", lambda _hwnd: 1000)
    winamax_ax_seats.request_windows_accessibility(1234)
    winamax_ax_seats._windows[1234].centre = (1.0, 2.0)
    winamax_ax_seats._windows[1234].centre_frame = (0, 0, 10, 10)
    assert winamax_ax_seats._windows[1234].asked is True

    monkeypatch.setattr(winamax_ax_seats, "_window_pid", lambda _hwnd: 2000)
    winamax_ax_seats.request_windows_accessibility(1234)

    state = winamax_ax_seats._windows[1234]
    assert state.owner_pid == 2000
    assert state.centre is None
    assert state.centre_frame is None


def test_a_request_the_old_process_never_answered_does_not_block_the_new_one(
    monkeypatch,
) -> None:
    """An exited client can leave in_flight set with no thread left to clear it."""
    winamax_ax_seats.forget_window_state()
    monkeypatch.setattr(winamax_ax_seats.platform, "system", lambda: "Windows")
    started = []

    class _NeverRuns:
        def __init__(self, target, args=(), **_kwargs) -> None:
            started.append(args)

        def start(self) -> None:
            pass

    monkeypatch.setattr(winamax_ax_seats.threading, "Thread", _NeverRuns)

    monkeypatch.setattr(winamax_ax_seats, "_window_pid", lambda _hwnd: 1000)
    winamax_ax_seats.request_windows_accessibility(1234)
    assert winamax_ax_seats._windows[1234].in_flight is True

    monkeypatch.setattr(winamax_ax_seats, "_window_pid", lambda _hwnd: 2000)
    winamax_ax_seats.request_windows_accessibility(1234)

    assert started == [(1234, 1000), (1234, 2000)]
