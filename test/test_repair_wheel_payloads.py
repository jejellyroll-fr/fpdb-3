"""Putting a wheel's shared libraries back where their loader expects them.

PyOxidizer loses them two different ways: on Linux it installs "numpy.libs" as
"numpy/libs", reading the dot as a package separator, and on Windows it does not
collect the directory at all. Both leave the bundle unable to import numpy,
which is the application unable to start.

These pin down what may be moved, what may not (a package that genuinely
contains a "libs" subpackage must be left alone), and that a file restored from
a re-downloaded wheel is only accepted when it hashes to what the bundle's own
RECORD says it must.
"""

from __future__ import annotations

import base64
import hashlib
import zipfile
from pathlib import Path

import pytest

from tools.repair_wheel_payloads import (
    PayloadFile,
    digest_of,
    is_payload_directory,
    main,
    missing_payloads,
    payload_files,
    relocate,
    repair,
    restore_from_wheel,
)

OPENBLAS = "libscipy_openblas64_-13e2df515630b4a41f92893938845698.dll"
OPENBLAS_BYTES = b"MZ-openblas-payload"


def _payload(package: Path, name: str = "libs", library: str = "libscipy_openblas64_-56d6093b.so") -> Path:
    payload = package / name
    payload.mkdir(parents=True)
    (payload / library).write_bytes(b"\x7fELF")
    return payload


def _record(lib_dir: Path, distribution: str, rows: list[str]) -> Path:
    dist_info = lib_dir / f"{distribution}.dist-info"
    dist_info.mkdir(parents=True)
    record = dist_info / "RECORD"
    record.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return dist_info


def _sha(data: bytes) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")


# ---------------------------------------------------------------------------
# Phase 1: a payload PyOxidizer put one level too deep
# ---------------------------------------------------------------------------


def test_a_payload_is_moved_beside_its_package(tmp_path: Path) -> None:
    lib = tmp_path / "lib"
    _payload(lib / "numpy")

    moved = relocate(lib)

    assert (lib / "numpy.libs" / "libscipy_openblas64_-56d6093b.so").is_file()
    assert not (lib / "numpy" / "libs").exists()
    assert [target.name for _source, target in moved] == ["numpy.libs"]


def test_windows_and_macos_payload_names_are_both_handled(tmp_path: Path) -> None:
    lib = tmp_path / "lib"
    _payload(lib / "numpy", library=OPENBLAS)
    _payload(lib / "pillow", name="dylibs", library="libjpeg.62.dylib")

    relocate(lib)

    assert (lib / "numpy.libs" / OPENBLAS).is_file()
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


# ---------------------------------------------------------------------------
# Phase 2: a payload PyOxidizer did not collect at all
# ---------------------------------------------------------------------------


def test_a_record_names_its_payload_files(tmp_path: Path) -> None:
    dist_info = _record(
        tmp_path,
        "numpy-2.2.6",
        [
            "numpy/__init__.py,sha256=AAAA,100",
            f"numpy.libs/{OPENBLAS},sha256={_sha(OPENBLAS_BYTES)},19",
            "numpy-2.2.6.dist-info/RECORD,,",
        ],
    )

    entries = payload_files(dist_info / "RECORD")

    assert [entry.path for entry in entries] == [f"numpy.libs/{OPENBLAS}"]
    assert entries[0].sha256 == _sha(OPENBLAS_BYTES)


def test_only_files_the_bundle_lacks_are_reported_missing(tmp_path: Path) -> None:
    lib = tmp_path / "lib"
    lib.mkdir()
    _record(
        lib,
        "numpy-2.2.6",
        [
            f"numpy.libs/{OPENBLAS},sha256={_sha(OPENBLAS_BYTES)},19",
            "numpy.libs/msvcp140-abc.dll,sha256=BBBB,10",
        ],
    )
    present = lib / "numpy.libs"
    present.mkdir()
    (present / "msvcp140-abc.dll").write_bytes(b"present")

    missing = missing_payloads(lib)

    assert [entry.path for entries in missing.values() for entry in entries] == [f"numpy.libs/{OPENBLAS}"]


def test_a_distribution_with_no_payload_is_not_reported(tmp_path: Path) -> None:
    lib = tmp_path / "lib"
    lib.mkdir()
    _record(lib, "colorlog-6.9.0", ["colorlog/__init__.py,sha256=AAAA,100"])

    assert missing_payloads(lib) == {}


def _wheel(path: Path, members: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return path


def test_a_file_is_restored_from_its_wheel(tmp_path: Path) -> None:
    lib = tmp_path / "lib"
    lib.mkdir()
    wheel = _wheel(tmp_path / "numpy-2.2.6-cp310-cp310-win_amd64.whl", {f"numpy.libs/{OPENBLAS}": OPENBLAS_BYTES})

    restored = restore_from_wheel(wheel, [PayloadFile(f"numpy.libs/{OPENBLAS}", _sha(OPENBLAS_BYTES))], lib)

    assert (lib / "numpy.libs" / OPENBLAS).read_bytes() == OPENBLAS_BYTES
    assert restored == [lib / "numpy.libs" / OPENBLAS]


def test_a_wheel_whose_library_does_not_match_the_bundle_is_refused(tmp_path: Path) -> None:
    """Shipping a library the bundle's own numpy was not built against is worse
    than failing the build."""
    lib = tmp_path / "lib"
    lib.mkdir()
    wheel = _wheel(tmp_path / "numpy-2.2.6-cp310-cp310-win_amd64.whl", {f"numpy.libs/{OPENBLAS}": b"another build"})

    with pytest.raises(ValueError, match="RECORD says"):
        restore_from_wheel(wheel, [PayloadFile(f"numpy.libs/{OPENBLAS}", _sha(OPENBLAS_BYTES))], lib)

    assert not (lib / "numpy.libs").exists()


def test_a_wheel_missing_the_file_is_an_error(tmp_path: Path) -> None:
    lib = tmp_path / "lib"
    lib.mkdir()
    wheel = _wheel(tmp_path / "numpy-2.2.6-cp310-cp310-win_amd64.whl", {"numpy/__init__.py": b"x"})

    with pytest.raises(LookupError, match="does not contain"):
        restore_from_wheel(wheel, [PayloadFile(f"numpy.libs/{OPENBLAS}", _sha(OPENBLAS_BYTES))], lib)


def test_the_digest_matches_the_form_a_record_uses() -> None:
    assert digest_of(b"") == "47DEQpj8HBSa-_TImW-5JCeuQeRkm5NMpJWZG3hSuFU"


# ---------------------------------------------------------------------------
# Both phases together
# ---------------------------------------------------------------------------


def test_repair_relocates_and_restores(tmp_path: Path) -> None:
    install = tmp_path / "install"
    lib = install / "lib"
    lib.mkdir(parents=True)
    # pandas' payload is merely misplaced; numpy's is absent entirely.
    _payload(lib / "pandas", library="libfoo.so.1")
    _record(lib, "numpy-2.2.6", [f"numpy.libs/{OPENBLAS},sha256={_sha(OPENBLAS_BYTES)},19"])
    wheel = _wheel(tmp_path / "numpy-2.2.6-cp310-cp310-win_amd64.whl", {f"numpy.libs/{OPENBLAS}": OPENBLAS_BYTES})
    asked: list[tuple[str, str, str]] = []

    def fetch(name: str, version: str, dest: Path, python_version: str) -> Path:
        asked.append((name, version, python_version))
        return wheel

    moved, restored = repair(install, tmp_path / "wheels", fetch=fetch)

    assert [target.name for _source, target in moved] == ["pandas.libs"]
    assert restored == [lib / "numpy.libs" / OPENBLAS]
    assert asked == [("numpy", "2.2.6", "310")]


def test_nothing_is_fetched_when_the_bundle_is_already_whole(tmp_path: Path) -> None:
    """macOS lands here, and so does a bundle already repaired."""
    install = tmp_path / "install"
    (install / "lib").mkdir(parents=True)

    def fetch(*_args) -> Path:
        raise AssertionError("downloaded a wheel with nothing missing")

    assert repair(install, tmp_path / "wheels", fetch=fetch) == ([], [])


def test_the_command_reports_what_it_did(tmp_path: Path, capsys) -> None:
    install = tmp_path / "install"
    _payload(install / "lib" / "numpy")

    assert main([str(install)]) == 0

    assert "numpy.libs" in capsys.readouterr().out


def test_the_command_says_so_when_there_is_nothing_to_do(tmp_path: Path, capsys) -> None:
    install = tmp_path / "install"
    (install / "lib").mkdir(parents=True)

    assert main([str(install)]) == 0

    assert "already in place" in capsys.readouterr().out
