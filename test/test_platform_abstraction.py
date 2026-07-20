"""Contracts for the modern cross-platform table abstraction."""

from unittest.mock import Mock, patch

from fpdb.infrastructure.platform import (
    Platform,
    TableDetectorFactory,
    TableGeometry,
    TableInfo,
    get_table_detector,
    reset_detector,
)


def test_geometry_and_table_matching_contracts() -> None:
    geometry = TableGeometry(x=10, y=20, width=100, height=80)

    assert geometry.contains_point(10, 20)
    assert geometry.contains_point(110, 100)
    assert not geometry.contains_point(111, 100)
    assert geometry.intersects(TableGeometry(x=100, y=90, width=20, height=20))
    assert not geometry.intersects(TableGeometry(x=110, y=100, width=20, height=20))
    table = TableInfo(window_id=1, title="Winamax Table Alpha", geometry=geometry)
    assert table.matches_search("winamax")
    # window_class is optional metadata, absent unless the platform reports it.
    assert table.window_class is None
    classed = TableInfo(window_id=2, title="CoinPoker", geometry=geometry, window_class="UnityWndClass")
    assert classed.window_class == "UnityWndClass"


def test_factory_detects_supported_platforms() -> None:
    for sys_platform, expected in (
        ("linux", Platform.LINUX),
        ("win32", Platform.WINDOWS),
        ("darwin", Platform.MACOS),
        ("plan9", Platform.UNKNOWN),
    ):
        with patch("fpdb.infrastructure.platform.factory.sys.platform", sys_platform):
            assert TableDetectorFactory.detect_platform() is expected
    assert all(TableDetectorFactory.is_platform_supported(platform) for platform in (Platform.LINUX, Platform.WINDOWS, Platform.MACOS))
    assert not TableDetectorFactory.is_platform_supported(Platform.UNKNOWN)


def test_global_detector_is_lazy_singleton_and_resettable() -> None:
    first = Mock(platform=Platform.LINUX)
    second = Mock(platform=Platform.LINUX)
    reset_detector()

    with patch.object(TableDetectorFactory, "create", side_effect=(first, second)) as create:
        assert get_table_detector() is first
        assert get_table_detector() is first
        assert get_table_detector(force_reload=True) is second
        assert create.call_count == 2
    reset_detector()
