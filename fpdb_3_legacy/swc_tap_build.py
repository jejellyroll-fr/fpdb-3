"""Compile the passive SwC TLS tap.

Kept apart from ``swc_native_capture`` deliberately: the decoder there pulls in
the capture models, the diff engine and the project logger, and through them
third-party packages. Compiling a C file needs none of that, and CI verifies the
compile on three runners — making each of them install the whole project first,
just to invoke a compiler, would be minutes of work for nothing.

Only the standard library is imported here, so
``python -m fpdb_3_legacy.swc_tap_build --build`` runs on a bare checkout.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

SWC_APP = Path("/Applications/SwC Poker.app")
SWC_EXECUTABLE = SWC_APP / "Contents/MacOS/SwC Poker"
SOURCE_PATH = Path(__file__).with_name("swc_native_tap.c")
INJECTOR_SOURCE_PATH = Path(__file__).with_name("swc_inject.c")
BUILD_DIR = Path.home() / ".fpdb" / "swc-native-capture"

#: The SwC Windows client is a 32-bit Qt application, so the tap DLL and the
#: injector that loads it into the client must both be 32-bit. clang targets the
#: MSVC ABI here; MinGW uses -m32.
WINDOWS_CLANG_TARGET = "i686-pc-windows-msvc"


def get_tap_library_path() -> Path:
    system_name = platform.system()
    if system_name == "Darwin":
        return BUILD_DIR / "libswc_native_tap.dylib"
    if system_name == "Windows":
        return BUILD_DIR / "swc_native_tap.dll"
    return BUILD_DIR / "libswc_native_tap.so"


def get_injector_path() -> Path:
    """Path to the Windows same-bitness DLL injector (Windows only)."""
    return BUILD_DIR / "swc_inject.exe"


#: The compilers tried for each platform, in order of preference. clang leads on
#: Windows because it ships a single installer, targets the 32-bit MSVC ABI the
#: client uses, and is what this feature was developed against; MinGW's
#: 32-bit-capable gcc names are tried after it.
COMPILERS: dict[str, tuple[str, ...]] = {
    "Darwin": ("clang",),
    "Windows": ("clang", "i686-w64-mingw32-gcc", "gcc"),
    "Linux": ("clang", "gcc"),
}

#: What to tell someone who has none of them.
INSTALL_HINTS: dict[str, str] = {
    "Darwin": "Install the Xcode command line tools: xcode-select --install",
    "Windows": "Install LLVM (clang) from https://llvm.org, or a 32-bit MinGW-w64 gcc, and put it on PATH.",
    "Linux": "Install clang or gcc with your package manager.",
}


def _windows_x86_link_dirs() -> list[str]:
    """`-L` directories holding the 32-bit import libraries clang links against.

    clang targets the MSVC ABI on Windows, so it needs the Windows SDK (um, ucrt)
    and MSVC (VC runtime) x86 import libraries. These live under fixed roots but
    versioned subdirectories; the newest of each is chosen. Returns an empty list
    when nothing is found -- a MinGW gcc supplies its own libraries and needs
    none of this, so an empty list is not by itself an error.
    """
    program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    dirs: list[str] = []

    sdk_lib_root = Path(program_files_x86) / "Windows Kits" / "10" / "Lib"
    if sdk_lib_root.is_dir():
        versions = sorted((p for p in sdk_lib_root.iterdir() if p.is_dir()), reverse=True)
        for version in versions:
            um = version / "um" / "x86"
            ucrt = version / "ucrt" / "x86"
            if um.is_dir() and ucrt.is_dir():
                dirs.extend([str(um), str(ucrt)])
                break

    for vs_root in (Path(program_files) / "Microsoft Visual Studio", Path(program_files_x86) / "Microsoft Visual Studio"):
        msvc_root = vs_root.glob("*/*/VC/Tools/MSVC/*/lib/x86")
        newest = sorted((p for p in msvc_root if p.is_dir()), reverse=True)
        if newest:
            dirs.append(str(newest[0]))
            break

    return dirs


def resolve_compiler(system_name: str) -> str:
    """The compiler to build the tap with, or a message saying what is missing.

    subprocess used to be handed a compiler name that had never been checked,
    so a machine without one failed with the operating system's own words for
    "that program does not exist":

        SwC Native Capture warning: [WinError 2] Le fichier specifie est introuvable

    Which names no compiler, no file, and nothing to do about it -- it was read
    as an FPDB bug for months. Windows is where it always bit, because a Windows
    machine essentially never has gcc, but a Linux box without a toolchain got
    exactly the same non-answer.
    """
    candidates = COMPILERS.get(system_name, ())
    for name in candidates:
        if shutil.which(name):
            return name
    msg = (
        f"no C compiler found to build the SwC tap: looked for {', '.join(candidates)}. "
        f"{INSTALL_HINTS.get(system_name, 'Install one and try again.')}"
    )
    raise FileNotFoundError(msg)


def _windows_compile_command(compiler: str, source: Path, output: Path, *, shared: bool, libs: tuple[str, ...]) -> list[str]:
    """Build a 32-bit Windows compile command for either the DLL or the injector.

    clang cross-targets the 32-bit MSVC ABI and needs the SDK/MSVC import-library
    search paths; a MinGW gcc builds 32-bit with -m32 and brings its own. Both
    produce a PE32 (x86) matching the 32-bit SwC client.
    """
    base = os.path.basename(compiler).lower()
    is_clang = "clang" in base
    cmd = [compiler]
    if is_clang:
        cmd += [f"--target={WINDOWS_CLANG_TARGET}"]
    else:
        cmd += ["-m32"]
    if shared:
        cmd += ["-shared"]
    cmd += ["-O2", "-Wall", "-Wextra", "-o", str(output), str(source)]
    if is_clang:
        for lib_dir in _windows_x86_link_dirs():
            cmd += ["-L", lib_dir]
    cmd += [f"-l{name}" for name in libs]
    return cmd


def _compile_command(system_name: str, tap_lib: Path) -> list[str]:
    if system_name == "Darwin":
        return [
            resolve_compiler(system_name),
            "-arch",
            "x86_64",
            "-dynamiclib",
            "-O2",
            "-Wall",
            "-Wextra",
            "-undefined",
            "dynamic_lookup",
            "-o",
            str(tap_lib),
            str(SOURCE_PATH),
        ]
    compiler = resolve_compiler(system_name)
    if system_name == "Windows":
        return _windows_compile_command(compiler, SOURCE_PATH, tap_lib, shared=True, libs=("ws2_32",))
    return [compiler, "-shared", "-fPIC", "-O2", "-Wall", "-Wextra", "-o", str(tap_lib), str(SOURCE_PATH), "-ldl"]


def build_tap(*, force: bool = False, check_executable: bool = False) -> Path:
    """Compile the interposer for this platform and return the library path.

    ``check_executable`` is for the launch path, which has no use for a tap when
    the client it would be injected into is not installed. CI leaves it off: it
    is verifying that the C compiles, not that SwC is present.
    """
    system_name = platform.system()
    if system_name not in {"Darwin", "Linux", "Windows"}:
        msg = f"the native SwC tap is not supported on {system_name}"
        raise RuntimeError(msg)
    if check_executable and system_name == "Darwin" and not SWC_EXECUTABLE.exists():
        msg = f"SwC client not found at {SWC_APP}"
        raise FileNotFoundError(msg)

    tap_lib = get_tap_library_path()
    if tap_lib.exists() and not force:
        if not SOURCE_PATH.exists() or tap_lib.stat().st_mtime >= SOURCE_PATH.stat().st_mtime:
            return tap_lib

    if not SOURCE_PATH.exists():
        msg = f"SwC tap source file not found at {SOURCE_PATH}"
        raise FileNotFoundError(msg)

    BUILD_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    subprocess.run(_compile_command(system_name, tap_lib), check=True)
    try:
        tap_lib.chmod(0o700)
    except OSError:
        # Windows ignores the POSIX mode; the parent directory already restricts access.
        pass

    # Windows needs a second artifact: the DLL cannot inject itself, so build the
    # same-bitness injector that loads it into the running client.
    if system_name == "Windows":
        build_injector(force=force)
    return tap_lib


def build_injector(*, force: bool = False) -> Path:
    """Compile the Windows DLL injector and return its path (Windows only).

    The injector is a tiny standalone exe rather than in-process ctypes because
    the SwC client is 32-bit while fpdb's Python is 64-bit: a same-bitness
    LoadLibrary injection is the reliable path, so a 32-bit helper does it.
    """
    system_name = platform.system()
    if system_name != "Windows":
        msg = "the SwC DLL injector is only built on Windows"
        raise RuntimeError(msg)
    if not INJECTOR_SOURCE_PATH.exists():
        msg = f"SwC injector source file not found at {INJECTOR_SOURCE_PATH}"
        raise FileNotFoundError(msg)

    injector = get_injector_path()
    if injector.exists() and not force and injector.stat().st_mtime >= INJECTOR_SOURCE_PATH.stat().st_mtime:
        return injector

    BUILD_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    compiler = resolve_compiler(system_name)
    command = _windows_compile_command(
        compiler, INJECTOR_SOURCE_PATH, injector, shared=False, libs=("shell32",)
    )
    subprocess.run(command, check=True)
    return injector


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true", help="compile the tap for this platform")
    parser.add_argument("--force", action="store_true", help="recompile even if the library is up to date")
    args = parser.parse_args(argv)
    if not args.build:
        parser.error("nothing to do: pass --build")
    print(build_tap(force=args.force))
    return 0


if __name__ == "__main__":
    sys.exit(main())
