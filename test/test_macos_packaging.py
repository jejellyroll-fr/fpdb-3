"""Assembly and signing of the macOS PyOxidizer bundle.

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


def test_release_signing_gate_rejects_ad_hoc_identity(monkeypatch) -> None:
    monkeypatch.setenv(adhoc_sign_macos.REQUIRE_STABLE_SIGNING_ENV, "1")
    monkeypatch.delenv(adhoc_sign_macos.SIGNING_IDENTITY_ENV, raising=False)

    with pytest.raises(RuntimeError, match="Developer ID"):
        adhoc_sign_macos.resolve_signing_identity()


def test_developer_id_signing_enables_runtime_timestamp_and_entitlements(tmp_path: Path) -> None:
    entitlements = tmp_path / "entitlements.plist"
    entitlements.touch()

    command = adhoc_sign_macos._codesign_command(  # noqa: SLF001
        [tmp_path / "fpdb.app"],
        identity="Developer ID Application: FPDB (TEAMID1234)",
        deep=True,
        entitlements=entitlements,
    )

    assert "--options" in command
    assert "runtime" in command
    assert "--timestamp" in command
    assert command[command.index("--entitlements") + 1] == str(entitlements)


def test_ad_hoc_signing_does_not_claim_hardened_runtime(tmp_path: Path) -> None:
    command = adhoc_sign_macos._codesign_command(  # noqa: SLF001
        [tmp_path / "fpdb.app"],
        identity=adhoc_sign_macos.ADHOC_IDENTITY,
        deep=True,
        entitlements=package_pyoxidizer_macos.ENTITLEMENTS,
    )

    assert "runtime" not in command
    assert "--timestamp" not in command
    assert "--entitlements" not in command


def test_release_entitlements_allow_apple_events() -> None:
    with package_pyoxidizer_macos.ENTITLEMENTS.open("rb") as handle:
        entitlements = plistlib.load(handle)

    assert entitlements["com.apple.security.automation.apple-events"] is True


def test_bundle_keeps_only_the_launcher_in_macos(install_dir: Path, tmp_path: Path, monkeypatch) -> None:
    """codesign refuses to seal a bundle whose MacOS directory holds payload."""
    monkeypatch.setattr(package_pyoxidizer_macos, "sign", lambda paths, **kwargs: None)
    monkeypatch.setattr(package_pyoxidizer_macos, "sign_bundle", lambda app, **kwargs: None)
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


def test_deferred_bundle_is_not_signed(install_dir: Path, tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(package_pyoxidizer_macos, "sign_app", lambda *args, **kwargs: calls.append("sign"))
    monkeypatch.setattr(package_pyoxidizer_macos.subprocess, "run", lambda *args, **kwargs: None)

    package_pyoxidizer_macos.build_app(
        install_dir,
        tmp_path / "fpdb.app",
        "fpdb",
        "3.0.0",
        None,
        defer_signing=True,
    )

    assert calls == []


def test_sign_existing_seals_nested_code_before_bundle(tmp_path: Path, monkeypatch) -> None:
    app = tmp_path / "fpdb.app"
    resources = app / "Contents" / "Resources"
    resources.mkdir(parents=True)
    nested = resources / "libexample.dylib"
    nested.write_bytes(MACH_O_HEADER)
    calls: list[tuple[str, object]] = []

    monkeypatch.setattr(package_pyoxidizer_macos, "resolve_signing_identity", lambda identity: "identity")
    monkeypatch.setattr(package_pyoxidizer_macos, "sign", lambda paths, **kwargs: calls.append(("nested", paths)))
    monkeypatch.setattr(
        package_pyoxidizer_macos,
        "sign_bundle",
        lambda bundle, **kwargs: calls.append(("bundle", bundle)),
    )

    result = package_pyoxidizer_macos.sign_app(app)

    assert result == app
    assert calls == [("nested", [nested]), ("bundle", app)]


def test_ci_smokes_precede_final_pyoxidizer_signature() -> None:
    workflow = (Path(__file__).resolve().parent.parent / ".github" / "workflows" / "ci.yml").read_text()
    start = workflow.index("- name: Assemble PyOxidizer macOS application")
    end = workflow.index("- name: Notarize and staple PyOxidizer macOS release", start)
    assemble = workflow[start:end]

    unsigned = assemble.index("--defer-signing")
    last_smoke = assemble.index("--run-module fpdb.infrastructure.platform.macos")
    final_sign = assemble.index("--sign-existing dist/fpdb.app")
    final_verify = assemble.index("codesign --verify --deep --strict dist/fpdb.app")

    assert unsigned < last_smoke < final_sign < final_verify
    assert 'PYTHONDONTWRITEBYTECODE: "1"' in assemble
    assert "Contents/MacOS/fpdb" not in assemble[final_sign:]


def test_pyoxidizer_runtime_cannot_mutate_a_signed_bundle_with_bytecode() -> None:
    config = (Path(__file__).resolve().parent.parent / "pyoxidizer.bzl").read_text()

    assert '"sys.dont_write_bytecode = True"' in config


def test_bundle_declares_the_launcher_and_icon(install_dir: Path, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(package_pyoxidizer_macos, "sign", lambda paths, **kwargs: None)
    monkeypatch.setattr(package_pyoxidizer_macos, "sign_bundle", lambda app, **kwargs: None)
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
