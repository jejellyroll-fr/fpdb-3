"""Moving a wheel's shared libraries back beside their package.

PyOxidizer installs "numpy.libs" as "numpy/libs", reading the dot as a package
separator, and every loader that goes looking for the payload -- delvewheel's
os.add_dll_directory shim on Windows, the extension's RPATH on Linux -- looks
beside the package instead. These pin down what may be moved and, more
importantly, what may not: a package that genuinely contains a "libs"
subpackage must be left alone.
"""

from __future__ import annotations

from pathlib import Path

from tools.relocate_wheel_payloads import is_payload_directory, main, relocate


def _payload(package: Path, name: str = "libs", library: str = "libscipy_openblas64_-56d6093b.so") -> Path:
    payload = package / name
    payload.mkdir(parents=True)
    (payload / library).write_bytes(b"\x7fELF")
    return payload


def test_a_payload_is_moved_beside_its_package(tmp_path: Path) -> None:
    lib = tmp_path / "lib"
    _payload(lib / "numpy")

    moved = relocate(lib)

    assert (lib / "numpy.libs" / "libscipy_openblas64_-56d6093b.so").is_file()
    assert not (lib / "numpy" / "libs").exists()
    assert [target.name for _source, target in moved] == ["numpy.libs"]


def test_windows_and_macos_payload_names_are_both_handled(tmp_path: Path) -> None:
    lib = tmp_path / "lib"
    _payload(lib / "numpy", library="libscipy_openblas64_-13e2df51.dll")
    _payload(lib / "pillow", name="dylibs", library="libjpeg.62.dylib")

    relocate(lib)

    assert (lib / "numpy.libs" / "libscipy_openblas64_-13e2df51.dll").is_file()
    assert (lib / "pillow.dylibs" / "libjpeg.62.dylib").is_file()


def test_a_real_subpackage_is_left_where_it_is(tmp_path: Path) -> None:
    """Moving this one out of its package would break every import of it."""
    lib = tmp_path / "lib"
    subpackage = lib / "somepkg" / "libs"
    subpackage.mkdir(parents=True)
    (subpackage / "__init__.py").write_text("", encoding="utf-8")
    (subpackage / "helper.so").write_bytes(b"\x7fELF")

    assert relocate(lib) == []
    assert (lib / "somepkg" / "libs" / "__init__.py").is_file()


def test_a_directory_holding_no_shared_library_is_left_alone(tmp_path: Path) -> None:
    lib = tmp_path / "lib"
    data = lib / "somepkg" / "libs"
    data.mkdir(parents=True)
    (data / "notes.txt").write_text("data\n", encoding="utf-8")

    assert relocate(lib) == []
    assert (data / "notes.txt").is_file()


def test_a_payload_with_a_nested_directory_is_left_alone(tmp_path: Path) -> None:
    """Wheel payloads are flat; anything with structure is somebody's package."""
    lib = tmp_path / "lib"
    payload = _payload(lib / "somepkg")
    (payload / "nested").mkdir()

    assert relocate(lib) == []


def test_running_twice_moves_nothing_the_second_time(tmp_path: Path) -> None:
    lib = tmp_path / "lib"
    _payload(lib / "numpy")

    assert len(relocate(lib)) == 1
    assert relocate(lib) == []
    assert (lib / "numpy.libs" / "libscipy_openblas64_-56d6093b.so").is_file()


def test_a_payload_already_in_place_is_not_disturbed(tmp_path: Path) -> None:
    """A PyOxidizer that gets the name right must not have its work undone."""
    lib = tmp_path / "lib"
    _payload(lib / "numpy")
    correct = lib / "numpy.libs"
    correct.mkdir()
    (correct / "libscipy_openblas64_-56d6093b.so").write_bytes(b"\x7fELF-correct")

    assert relocate(lib) == []
    assert (correct / "libscipy_openblas64_-56d6093b.so").read_bytes() == b"\x7fELF-correct"


def test_a_bundle_without_a_lib_directory_is_not_an_error(tmp_path: Path) -> None:
    assert relocate(tmp_path / "lib") == []


def test_versioned_shared_libraries_count_as_payload(tmp_path: Path) -> None:
    lib = tmp_path / "lib"
    _payload(lib / "somepkg", library="libfoo.so.1.2.3")

    assert is_payload_directory(lib / "somepkg" / "libs") is True


def test_the_command_reports_what_it_moved(tmp_path: Path, capsys) -> None:
    install = tmp_path / "install"
    _payload(install / "lib" / "numpy")

    assert main([str(install)]) == 0

    out = capsys.readouterr().out
    assert "numpy.libs" in out


def test_the_command_says_so_when_there_is_nothing_to_move(tmp_path: Path, capsys) -> None:
    """macOS lands here: delocate keeps its dylibs inside the package."""
    install = tmp_path / "install"
    (install / "lib").mkdir(parents=True)

    assert main([str(install)]) == 0

    assert "no misplaced wheel library payload" in capsys.readouterr().out
