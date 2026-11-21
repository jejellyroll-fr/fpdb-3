#!/bin/bash
# Install fpdb-3 from source on macOS.
#
# What it does, in order:
#   1. checks for the Xcode Command Line Tools (C compiler for the equity engine);
#   2. installs Python 3.13 and CMake with Homebrew when they are missing;
#   3. creates .venv in the repository (or reuses one, uv-made included) and
#      installs fpdb with the macOS extras;
#   4. smoke-tests PySide6, pyobjc and the native pypoker-eval engine;
#   5. writes fpdb.command, a launcher that can be double-clicked in Finder.
#
# It is idempotent: running it again upgrades the virtual environment in place.
# Nothing is installed outside the repository except the Homebrew packages.
#
# Usage: ./install_macos.sh [--dev] [--postgresql] [--mysql] [--no-brew] [--python PATH]
#
# For the prebuilt, signed fpdb.app see docs/macos-gatekeeper.md instead.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$REPO_DIR/.venv"
PYTHON_FORMULA="python@3.13"
EXTRAS="macos"
USE_BREW=1
PYTHON_BIN=""

usage() {
    sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dev) EXTRAS="$EXTRAS,test" ;;
        --postgresql) EXTRAS="$EXTRAS,postgresql" ;;
        --mysql) EXTRAS="$EXTRAS,mysql" ;;
        --no-brew) USE_BREW=0 ;;
        --python)
            shift
            PYTHON_BIN="${1:?--python needs a path}"
            ;;
        -h | --help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
    shift
done

step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33mWarning:\033[0m %s\n' "$*" >&2; }
die() {
    printf '\033[1;31mError:\033[0m %s\n' "$*" >&2
    exit 1
}

# The oldest supported Python comes from pyproject.toml, so the two cannot drift.
MIN_PYTHON="$(sed -n 's/^requires-python *= *"[^0-9]*\([0-9][0-9]*\.[0-9][0-9]*\).*/\1/p' "$REPO_DIR/pyproject.toml" 2>/dev/null || true)"
[[ "$MIN_PYTHON" =~ ^3\.[0-9]+$ ]] || die "Cannot read requires-python from $REPO_DIR/pyproject.toml; run the script from an fpdb-3 checkout."
MIN_MINOR="${MIN_PYTHON#3.}"
# Exit status 0 when the interpreter given as $1 runs and is recent enough.
python_ok() { "$1" -c "import sys; sys.exit(0 if sys.version_info >= (3, $MIN_MINOR) else 1)" >/dev/null 2>&1; }

[[ "$(uname -s)" == "Darwin" ]] || die "This script is for macOS. On Linux follow the Install section of README.md."

ARCH="$(uname -m)"
MACOS_VERSION="$(sw_vers -productVersion)"
echo "macOS $MACOS_VERSION ($ARCH), repository: $REPO_DIR"
if [[ "${MACOS_VERSION%%.*}" -lt 11 ]]; then
    die "macOS 11 (Big Sur) or newer is required; PySide6 6.8 no longer supports older releases."
fi

# --- 1. Xcode Command Line Tools ---------------------------------------------
step "Checking the Xcode Command Line Tools"
if ! xcode-select -p >/dev/null 2>&1; then
    xcode-select --install || true
    die "The Command Line Tools installer has been opened. Finish it, then run this script again."
fi
echo "Found: $(xcode-select -p)"

# --- 2. Homebrew packages ----------------------------------------------------
if [[ $USE_BREW -eq 1 ]]; then
    step "Checking Homebrew"
    if ! command -v brew >/dev/null 2>&1; then
        for candidate in /opt/homebrew/bin/brew /usr/local/bin/brew; do
            if [[ -x "$candidate" ]]; then
                eval "$("$candidate" shellenv)"
                break
            fi
        done
    fi
    command -v brew >/dev/null 2>&1 || die "Homebrew is not installed. Install it from https://brew.sh, or rerun with --no-brew --python /path/to/python3.13 (CMake must then already be on PATH)."

    missing=()
    for formula in "$PYTHON_FORMULA" cmake; do
        brew list --formula "$formula" >/dev/null 2>&1 || missing+=("$formula")
    done
    if [[ ${#missing[@]} -gt 0 ]]; then
        echo "Installing: ${missing[*]}"
        brew install "${missing[@]}"
    else
        echo "$PYTHON_FORMULA and cmake are already installed."
    fi
    if [[ -z "$PYTHON_BIN" ]]; then
        PYTHON_BIN="$(brew --prefix "$PYTHON_FORMULA")/bin/python3.13"
    fi
fi

if [[ -z "$PYTHON_BIN" ]]; then
    PYTHON_BIN="$(command -v python3.13 || command -v python3 || true)"
fi
[[ -n "$PYTHON_BIN" && -x "$PYTHON_BIN" ]] || die "No Python interpreter found. Pass one with --python."
python_ok "$PYTHON_BIN" || die "Python $MIN_PYTHON or newer is required (3.13 recommended); $PYTHON_BIN is $("$PYTHON_BIN" --version 2>&1)."
echo "Using $("$PYTHON_BIN" --version) at $PYTHON_BIN"
command -v cmake >/dev/null 2>&1 || die "CMake is not on PATH; it is needed to build the pypoker-eval equity engine."

# --- 3. Virtual environment and fpdb -----------------------------------------
step "Creating the virtual environment in $VENV_DIR"
if [[ -e "$VENV_DIR" ]] && ! python_ok "$VENV_DIR/bin/python"; then
    # Also catches a .venv whose interpreter vanished with a Homebrew upgrade.
    warn "Existing .venv has no working Python $MIN_PYTHON+; recreating it."
    rm -rf "$VENV_DIR"
fi
if [[ -x "$VENV_DIR/bin/python" ]]; then
    echo "Reusing the existing .venv ($("$VENV_DIR/bin/python" --version))"
else
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi
VENV_PY="$VENV_DIR/bin/python"
# A .venv made by uv has no pip; bootstrap it rather than failing.
"$VENV_PY" -m pip --version >/dev/null 2>&1 || "$VENV_PY" -m ensurepip --upgrade
"$VENV_PY" -m pip install --upgrade pip setuptools wheel

step "Installing fpdb-3 with extras [$EXTRAS] (builds the native equity engine)"
# pypoker-eval is compiled from source here; point CMake at the SDK explicitly so a
# Homebrew toolchain does not pick a mismatched one.
SDKROOT="$(xcrun --show-sdk-path 2>/dev/null || true)"
export SDKROOT
(cd "$REPO_DIR" && "$VENV_PY" -m pip install -e ".[$EXTRAS]")

# --- 4. Smoke tests ----------------------------------------------------------
step "Checking the installation"
(cd "$REPO_DIR" && "$VENV_PY" - <<'EOF')
import sys

failures = []
for module in ("PySide6.QtWidgets", "objc", "Quartz", "AppKit", "zmq", "numpy", "pandas"):
    try:
        __import__(module)
        print(f"  ok   {module}")
    except Exception as exc:  # noqa: BLE001 - report every failure, not just the first
        failures.append(module)
        print(f"  FAIL {module}: {exc}")

try:
    from fpdb_3_legacy.equity import load_poker_eval

    backend = load_poker_eval()
    if backend is None:
        raise RuntimeError("load_poker_eval() returned None")
    print(f"  ok   pypoker-eval ({type(backend).__name__})")
except Exception as exc:  # noqa: BLE001
    failures.append("pypoker-eval")
    print(f"  FAIL pypoker-eval: {exc}")

sys.exit(1 if failures else 0)
EOF

# --- 5. Launcher -------------------------------------------------------------
step "Writing the Finder launcher"
LAUNCHER="$REPO_DIR/fpdb.command"
# The console script runs fpdb.pyw from fpdb_3_legacy, as the GUI expects.
{
    echo '#!/bin/bash'
    echo '# Generated by install_macos.sh -- double-click in Finder to start fpdb.'
    printf 'exec %q "$@"\n' "$VENV_DIR/bin/fpdb_3_legacy"
} >"$LAUNCHER"
chmod +x "$LAUNCHER"
echo "Created $LAUNCHER"

cat <<EOF

$(printf '\033[1;32m')fpdb-3 is installed.$(printf '\033[0m')

Start it with either of:
  $LAUNCHER                 (or double-click it in Finder)
  $VENV_DIR/bin/fpdb_3_legacy

The HUD reads poker-table windows, which needs these macOS permissions. From a
source install they belong to the app that launched fpdb (Terminal, iTerm, ...),
not to fpdb itself:
  - System Settings > Privacy & Security > Automation (macOS asks on first use)
  - System Settings > Privacy & Security > Screen Recording
  - System Settings > Privacy & Security > Accessibility (never asked: add it by hand)
Check their status any time with:
  cd "$REPO_DIR" && $VENV_PY -m tools.grant_macos_permissions --check-status
EOF
