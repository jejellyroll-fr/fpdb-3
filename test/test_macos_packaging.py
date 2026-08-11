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
REPO_ROOT = Path(__file__).resolve().parent.parent
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def _workflow_job(workflow: str, job: str, next_job: str | None = None) -> str:
    start = workflow.index(f"  {job}:\n")
    if next_job is None:
        return workflow[start:]
    return workflow[start : workflow.index(f"\n  {next_job}:\n", start)]


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


def test_release_pyoxidizer_rejects_a_non_developer_id_identity(tmp_path: Path, monkeypatch) -> None:
    app = tmp_path / "fpdb.app"
    (app / "Contents" / "Resources").mkdir(parents=True)
    monkeypatch.setenv(adhoc_sign_macos.REQUIRE_STABLE_SIGNING_ENV, "1")

    with pytest.raises(RuntimeError, match="Developer ID Application"):
        package_pyoxidizer_macos.sign_app(
            app,
            signing_identity="Apple Development: FPDB (TEAMID1234)",
        )


def test_ci_smokes_precede_final_pyoxidizer_signature() -> None:
    workflow = CI_WORKFLOW.read_text()
    start = workflow.index("- name: Assemble PyOxidizer macOS application")
    end = workflow.index("- name: Notarize and staple PyOxidizer macOS release", start)
    assemble = workflow[start:end]

    unsigned = assemble.index("--defer-signing")
    last_smoke = assemble.index("--run-module fpdb.infrastructure.platform.macos")
    final_sign = assemble.index("--sign-existing dist/fpdb.app")
    immutable_smoke = assemble.index("--run-module fpdb_3_legacy.winamax_ax_seats")
    final_verify = assemble.index("codesign --verify --deep --strict dist/fpdb.app")

    assert unsigned < last_smoke < final_sign < immutable_smoke < final_verify
    assert 'PYTHONDONTWRITEBYTECODE: "1"' in assemble
    assert "Contents/MacOS/fpdb" not in assemble[final_verify:]


def test_ci_distributes_macos_only_with_pyoxidizer() -> None:
    workflow = CI_WORKFLOW.read_text()
    pyinstaller = _workflow_job(workflow, "build", "build-pyoxidizer")
    pyoxidizer = _workflow_job(workflow, "build-pyoxidizer")

    assert "os: ubuntu-latest" in pyinstaller
    assert "os: windows-latest" in pyinstaller
    assert "fpdb-pyinstaller-linux-x64" in pyinstaller
    assert "fpdb-pyinstaller-windows-x64" in pyinstaller
    assert "macos-latest" not in pyinstaller
    assert "fpdb-pyinstaller-macos" not in workflow
    assert "fpdb.app" not in pyinstaller
    assert "if: runner.os != 'macOS'" in pyinstaller
    assert "if: github.event_name == 'release' && runner.os != 'macOS'" in pyinstaller

    assert "os: macos-latest" in pyoxidizer
    assert "artifact: fpdb-pyoxidizer-macos-arm64" in pyoxidizer


def test_release_and_rc_pyoxidizer_artifacts_require_stable_developer_id() -> None:
    workflow = CI_WORKFLOW.read_text()
    pyoxidizer = _workflow_job(workflow, "build-pyoxidizer")

    # GitHub sends release/published for public prereleases (including RCs) as
    # well as final releases, so this is the shared distribution gate.
    assert "release:\n    types: [ published ]" in workflow
    assert "FPDB_REQUIRE_STABLE_MACOS_SIGNING: ${{ secrets.MACOS_SIGNING_IDENTITY != '' && '1' || '0' }}" in pyoxidizer
    assert '"Developer ID Application: "*' in pyoxidizer
    assert 'grep -Fqx "Authority=$FPDB_MACOS_SIGNING_IDENTITY"' in pyoxidizer
    assert 'grep -Fqx "TeamIdentifier=$expected_team_id"' in pyoxidizer
    assert "grep -Fq 'anchor apple generic'" in pyoxidizer
    assert "grep -q 'designated => cdhash'" in pyoxidizer
    assert "spctl --assess --type execute --verbose=4 dist/fpdb.app" in pyoxidizer

    archive = pyoxidizer.index('tar -czf "${{ matrix.artifact }}.tar.gz" -C dist fpdb.app')
    extract = pyoxidizer.index('tar -xzf "${{ matrix.artifact }}.tar.gz" -C "$verify_dir"')
    verify = pyoxidizer.index('codesign --verify --deep --strict --verbose=2 "$verify_dir/fpdb.app"')
    upload = pyoxidizer.index("- name: Upload PyOxidizer artifact")
    assert archive < extract < verify < upload


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
    assert "poker client data files" in info["NSAppDataUsageDescription"]
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


def test_fast_hud_qt_contracts_do_not_hang_windows_ci() -> None:
    workflow = CI_WORKFLOW.read_text()
    test_job = _workflow_job(workflow, "test", "native")

    start = test_job.index("- name: Run FastHUD Qt regression tests (offscreen)")
    step = test_job[start : test_job.index("\n      - name:", start + 1)]

    assert "if: runner.os != 'Windows'" in step
    assert "test/test_HUD_main.py" in step
