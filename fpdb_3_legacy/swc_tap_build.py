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
import platform
import shutil
import subprocess
import sys
from pathlib import Path

SWC_APP = Path("/Applications/SwC Poker.app")
SWC_EXECUTABLE = SWC_APP / "Contents/MacOS/SwC Poker"
SOURCE_PATH = Path(__file__).with_name("swc_native_tap.c")
BUILD_DIR = Path.home() / ".fpdb" / "swc-native-capture"


def get_tap_library_path() -> Path:
    system_name = platform.system()
    if system_name == "Darwin":
        return BUILD_DIR / "libswc_native_tap.dylib"
    if system_name == "Windows":
        return BUILD_DIR / "swc_native_tap.dll"
    return BUILD_DIR / "libswc_native_tap.so"


#: The compilers tried for each platform, in order of preference.
COMPILERS: dict[str, tuple[str, ...]] = {
    "Darwin": ("clang",),
    "Windows": ("x86_64-w64-mingw32-gcc", "gcc"),
    "Linux": ("clang", "gcc"),
}

#: What to tell someone who has none of them.
INSTALL_HINTS: dict[str, str] = {
    "Darwin": "Install the Xcode command line tools: xcode-select --install",
    "Windows": "Install MSYS2 or another MinGW-w64 distribution and put gcc on PATH.",
    "Linux": "Install clang or gcc with your package manager.",
}


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
        return [compiler, "-shared", "-O2", "-Wall", "-Wextra", "-o", str(tap_lib), str(SOURCE_PATH), "-lws2_32"]
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
    return tap_lib


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
