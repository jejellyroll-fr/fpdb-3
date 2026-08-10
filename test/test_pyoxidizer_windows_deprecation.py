from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_pyoxidizer_bzl_deprecates_windows_target() -> None:
    """Verify that pyoxidizer.bzl rejects Windows target with a helpful deprecation message."""
    bzl_content = (ROOT / "pyoxidizer.bzl").read_text(encoding="utf-8")
    assert "PyOxidizer is deprecated on Windows" in bzl_content
    assert "build_fpdb.ps1" in bzl_content


def test_build_experiment_sh_warns_on_windows_pyoxidizer() -> None:
    """Verify that build_experiment.sh handles Windows PyOxidizer deprecation."""
    sh_content = (ROOT / "build_experiment.sh").read_text(encoding="utf-8")
    assert "PyOxidizer builds on Windows are deprecated" in sh_content
