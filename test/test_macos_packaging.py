"""Assembly and ad-hoc signing of the macOS PyOxidizer bundle.

codesign itself is not exercised here (it only exists on macOS runners); the
layout it demands is, because getting that wrong is what breaks the build.
"""

from __future__ import annotations

import plistlib
from pathlib import Path

import pytest

from tools import adhoc_sign_macos, package_pyoxidizer_macos

MACH_O_HEADER = b"\xcf\xfa\xed\xfe" + b"\x00" * 60


@pytest.fixture
def install_dir(tmp_path: Path) -> Path:
    """A minimal PyOxidizer install directory."""
    root = tmp_path / "install"
    (root / "lib" / "shiboken6").mkdir(parents=True)
    (root / "fpdb_3_legacy").mkdir()
    (root / "fpdb").write_bytes(MACH_O_HEADER)
    (root / "lib" / "shiboken6" / "libshiboken6.dylib").write_bytes(MACH_O_HEADER)
    (root / "fpdb_3_legacy" / "fpdb.pyw").write_text("# entry point\n")
    (root / "HUD_config.xml").write_text("<config/>\n")
    return root


def test_mach_o_detection_ignores_everything_else(tmp_path: Path) -> None:
    binary = tmp_path / "libfoo.dylib"
    binary.write_bytes(MACH_O_HEADER)
    script = tmp_path / "script.py"
    script.write_text("print('hi')\n")

    assert adhoc_sign_macos.is_mach_o(binary)
    assert not adhoc_sign_macos.is_mach_o(script)


def test_mach_o_search_covers_extensionless_framework_binaries(tmp_path: Path) -> None:
    """Qt framework binaries have no extension and are not executable."""
    framework = tmp_path / "QtCore.framework" / "Versions" / "A"
    framework.mkdir(parents=True)
    (framework / "QtCore").write_bytes(MACH_O_HEADER)
    (tmp_path / "notes.txt").write_text("data\n")
    (tmp_path / "alias.dylib").symlink_to(framework / "QtCore")

    found = adhoc_sign_macos.find_mach_o_files(tmp_path)

    assert found == [framework / "QtCore"]


def test_bundle_keeps_only_the_launcher_in_macos(install_dir: Path, tmp_path: Path, monkeypatch) -> None:
    """codesign refuses to seal a bundle whose MacOS directory holds payload."""
    monkeypatch.setattr(package_pyoxidizer_macos, "adhoc_sign", lambda paths: None)
    monkeypatch.setattr(package_pyoxidizer_macos.subprocess, "run", lambda *args, **kwargs: None)
    icon = tmp_path / "tribal.icns"
    icon.write_bytes(b"icns")

    app = package_pyoxidizer_macos.build_app(install_dir, tmp_path / "fpdb.app", "fpdb", "3.0.0", icon)

    macos = app / "Contents" / "MacOS"
    resources = app / "Contents" / "Resources"
    assert [entry.name for entry in macos.iterdir()] == ["fpdb"]
    assert (resources / "lib" / "shiboken6" / "libshiboken6.dylib").is_file()
    assert (resources / "fpdb_3_legacy" / "fpdb.pyw").is_file()
    assert (resources / "HUD_config.xml").is_file()
    assert not (resources / "fpdb").exists()


def test_bundle_declares_the_launcher_and_icon(install_dir: Path, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(package_pyoxidizer_macos, "adhoc_sign", lambda paths: None)
    monkeypatch.setattr(package_pyoxidizer_macos.subprocess, "run", lambda *args, **kwargs: None)
    icon = tmp_path / "tribal.icns"
    icon.write_bytes(b"icns")

    app = package_pyoxidizer_macos.build_app(install_dir, tmp_path / "fpdb.app", "fpdb", "3.0.0", icon)

    with (app / "Contents" / "Info.plist").open("rb") as handle:
        info = plistlib.load(handle)
    assert info["CFBundleExecutable"] == "fpdb"
    assert info["CFBundleIconFile"] == "tribal.icns"
    assert info["CFBundleShortVersionString"] == "3.0.0"
    assert info["CFBundleIdentifier"] == package_pyoxidizer_macos.BUNDLE_IDENTIFIER
    assert "NSAppleEventsUsageDescription" in info
    assert "NSScreenCaptureUsageDescription" in info
    assert "NSAccessibilityUsageDescription" in info
    assert (app / "Contents" / "Resources" / "tribal.icns").is_file()


def test_bundle_rejects_an_install_without_the_launcher(tmp_path: Path) -> None:
    empty = tmp_path / "install"
    empty.mkdir()

    with pytest.raises(FileNotFoundError, match="no fpdb executable"):
        package_pyoxidizer_macos.build_app(empty, tmp_path / "fpdb.app", "fpdb", "3.0.0", None)


def test_version_falls_back_when_pyproject_is_unreadable(tmp_path: Path) -> None:
    assert package_pyoxidizer_macos.read_version(tmp_path / "absent.toml") == package_pyoxidizer_macos.DEFAULT_VERSION


def test_version_comes_from_pyproject() -> None:
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"

    assert package_pyoxidizer_macos.read_version(pyproject) != package_pyoxidizer_macos.DEFAULT_VERSION
