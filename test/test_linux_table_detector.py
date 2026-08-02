"""Unit tests for the Linux/X11 table detector.

``LinuxTableDetector.__init__`` shells out to a live X11 connection, so the
tests build instances with ``object.__new__`` and inject a fake ``_xconn``
that mimics the xcffib call/return surface used by the detector.
"""

from __future__ import annotations

import builtins
from unittest.mock import Mock, patch

import pytest

from fpdb.infrastructure.platform.linux import LinuxTableDetector
from fpdb.infrastructure.platform.protocol import Platform


class FakeValue:
    def __init__(self, atoms: list[int] | None = None, utf8: str | None = None) -> None:
        self._atoms = atoms
        self._utf8 = utf8
    def to_atoms(self) -> list[int]:
        return self._atoms or []

    def to_utf8(self) -> str:
        return self._utf8 or ""


class FakeReply:
    def __init__(self, **kwargs: object) -> None:
        self.__dict__.update(kwargs)


class FakeCall:
    """Mimics ``xconn.core.Method(...).reply()``."""

    def __init__(self, reply: object) -> None:
        self._reply = reply
        self.calls: list[dict[str, object]] = []

    def __call__(self, **kwargs: object) -> FakeCall:
        self.calls.append(kwargs)
        return self

    def reply(self) -> object:
        return self._reply


def _detector(
    *, wins: tuple[int, ...] = (), titles: dict[int, str] | None = None
) -> LinuxTableDetector:
    titles = titles or {}
    core = Mock()
    core.InternAtom.return_value = FakeCall(FakeReply(atom=0))
    core.GetProperty.side_effect = [
        FakeCall(FakeReply(value=FakeValue(atoms=list(wins)))),
        *(
            FakeCall(FakeReply(value=FakeValue(utf8=titles.get(w, ""))))
            for w in wins
        ),
    ]
    core.GetGeometry.return_value = FakeCall(FakeReply(width=100, height=80))
    core.TranslateCoordinates.return_value = FakeCall(FakeReply(dst_x=10, dst_y=20))

    detector = object.__new__(LinuxTableDetector)
    detector._platform = Platform.LINUX
    detector._xconn = Mock(core=core)
    detector._root = 1
    detector._nclatom = 2
    detector._winatom = 3
    detector._wnameatom = 4
    detector._utf8atom = 5
    return detector


def test_platform_property() -> None:
    detector = _detector()
    assert detector.platform == Platform.LINUX


def test_find_tables_matches_search_string() -> None:
    detector = _detector(wins=(101, 102), titles={101: "PokerStars - Table 1", 102: "Winamax - SpeedPool"})
    tables = detector.find_tables("pokerstars")
    assert [t.window_id for t in tables] == [101]
    assert tables[0].title == "PokerStars - Table 1"
    assert tables[0].geometry.x == 10
    assert tables[0].geometry.y == 20
    assert tables[0].geometry.width == 100
    assert tables[0].geometry.height == 80


def test_find_tables_empty_search_returns_all() -> None:
    detector = _detector(wins=(101, 102), titles={101: "A", 102: "B"})
    tables = detector.find_tables("")
    assert len(tables) == 2


def test_find_tables_skips_windows_without_geometry() -> None:
    detector = _detector(wins=(101, 102), titles={101: "A", 102: "B"})
    detector.get_window_geometry = Mock(side_effect=[None, Mock()])
    tables = detector.find_tables("")
    assert len(tables) == 1


def test_find_tables_swallows_connection_error() -> None:
    core = Mock()
    core.InternAtom.return_value = FakeCall(FakeReply(atom=0))
    core.GetProperty.side_effect = RuntimeError("connection lost")
    detector = object.__new__(LinuxTableDetector)
    detector._platform = Platform.LINUX
    detector._xconn = Mock(core=core)
    detector._root = 1
    detector._nclatom = 2
    detector._winatom = 3
    detector._wnameatom = 4
    detector._utf8atom = 5
    assert detector.find_tables("") == []


def test_get_window_geometry_translates_to_root() -> None:
    detector = _detector()
    geometry = detector.get_window_geometry("101")
    assert geometry == (10, 20, 100, 80) or (geometry.x, geometry.y, geometry.width, geometry.height) == (10, 20, 100, 80)


def test_get_window_geometry_returns_none_on_error() -> None:
    detector = _detector()
    detector._xconn.core.GetGeometry.side_effect = RuntimeError("X error")
    assert detector.get_window_geometry(101) is None


def test_is_window_visible_checks_map_state() -> None:
    detector = _detector()
    detector._xconn.core.GetWindowAttributes.return_value = FakeCall(FakeReply(map_state=1))
    assert detector.is_window_visible(101) is True


def test_is_window_visible_false_for_unmapped() -> None:
    detector = _detector()
    detector._xconn.core.GetWindowAttributes.return_value = FakeCall(FakeReply(map_state=0))
    assert detector.is_window_visible(101) is False


def test_is_window_visible_false_on_error() -> None:
    detector = _detector()
    detector._xconn.core.GetWindowAttributes.side_effect = OSError("gone")
    assert detector.is_window_visible(101) is False


def test_is_window_displayed_mirrors_visibility() -> None:
    detector = _detector()
    detector.is_window_visible = Mock(return_value=True)
    assert detector.is_window_displayed(101) is True
    detector.is_window_visible = Mock(return_value=False)
    assert detector.is_window_displayed(101) is False


def test_get_window_title_reads_utf8_property() -> None:
    detector = _detector()
    assert detector.get_window_title(101) == ""


def test_get_window_title_returns_none_on_error() -> None:
    detector = _detector()
    detector._xconn.core.GetProperty.side_effect = RuntimeError("gone")
    assert detector.get_window_title(101) is None


def test_focus_window_configures_and_flushes() -> None:
    detector = _detector()
    assert detector.focus_window(101) is True
    detector._xconn.core.ConfigureWindow.assert_called_once_with(
        window=101, value_mask=0x0040, value_list=[0x00000001],
    )
    detector._xconn.flush.assert_called_once()


def test_focus_window_returns_false_on_error() -> None:
    detector = _detector()
    detector._xconn.core.ConfigureWindow.side_effect = RuntimeError("denied")
    assert detector.focus_window(101) is False


def test_resize_window_configures_geometry() -> None:
    detector = _detector()
    assert detector.resize_window(101, 5, 6, 90, 70) is True
    detector._xconn.core.ConfigureWindow.assert_called_once_with(
        window=101, value_mask=0x000F, value_list=[5, 6, 90, 70],
    )
    detector._xconn.flush.assert_called_once()


def test_resize_window_returns_false_on_error() -> None:
    detector = _detector()
    detector._xconn.core.ConfigureWindow.side_effect = RuntimeError("denied")
    assert detector.resize_window(101, 0, 0, 10, 10) is False


def test_constructor_raises_when_xcffib_missing() -> None:
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "xcffib":
            raise ImportError("no xcffib")
        return real_import(name, *args, **kwargs)

    with patch.object(builtins, "__import__", side_effect=fake_import):
        with pytest.raises(ImportError, match="xcffib"):
            LinuxTableDetector()


def test_constructor_initializes_connection_and_atoms() -> None:
    connection = Mock()
    setup = Mock()
    setup.roots = [Mock(root=42)]
    connection.get_setup.return_value = setup
    connection.pref_screen = 0
    core = Mock()
    core.InternAtom.side_effect = [
        FakeCall(FakeReply(atom=10)),
        FakeCall(FakeReply(atom=11)),
        FakeCall(FakeReply(atom=12)),
        FakeCall(FakeReply(atom=13)),
    ]
    connection.core = core

    with patch.dict("sys.modules", {"xcffib": Mock(Connection=Mock(return_value=connection))}):
        with patch.dict("sys.modules", {"xcffib.xproto": Mock()}):
            detector = LinuxTableDetector()

    assert detector._platform == Platform.LINUX
    assert detector._root == 42
    assert detector._nclatom == 10
    assert detector._winatom == 11
    assert detector._wnameatom == 12
    assert detector._utf8atom == 13
    assert core.InternAtom.call_count == 4


def test_find_tables_ignores_window_with_bad_property() -> None:
    core = Mock()
    core.InternAtom.return_value = FakeCall(FakeReply(atom=0))
    # First GetProperty (client list) succeeds and yields one window; the
    # second GetProperty (that window's title) fails -> inner except, skip.
    core.GetProperty.side_effect = [
        FakeCall(FakeReply(value=FakeValue(atoms=[101]))),
        RuntimeError("broken window"),
    ]
    detector = object.__new__(LinuxTableDetector)
    detector._platform = Platform.LINUX
    detector._xconn = Mock(core=core)
    detector._root = 1
    detector._nclatom = 2
    detector._winatom = 3
    detector._wnameatom = 4
    detector._utf8atom = 5
    assert detector.find_tables("") == []
