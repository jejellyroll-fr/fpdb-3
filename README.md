# FPDB-3 Standalone Legacy (Python)

Version 3.7.0 — released 13 August 2026.

See the [3.7.0 release notes](docs/RELEASE_NOTES_3.7.0.md) for the HUD and
packaging changes.

The original FPDB-3 Python application: hand-history parsers, PySide6 GUI, statistics engine, and the HUD overlay. This repository hosts the standalone, self-contained legacy Python stack. It has been separated from the `fpdb-new` monorepo by removing all Rust and modern FastAPI components to keep it lightweight, fast, and easy to run.

## ✨ Highlights

- **Hand-History Import & Analysis** from 26 poker rooms. See [PARSER_SUPPORT.md](PARSER_SUPPORT.md) for which converters are covered by golden snapshots and which are kept only for historical archives.
- **Live capture** for rooms that write no hand-history files: SwC Poker (HTTP and native desktop), iPoker.
- **Real-Time HUD** overlay with draggable multiblock stats, positional panels, and a per-profile hero toggle.
- **FastHUD for fast-fold tables** with deterministic seat rotation, single-renderer ownership,
  duplicate-HUD interlocks, and platform contracts for macOS and Windows.
- **Auto Notes**: rule-driven player notes with a visual workbench and card miniatures.
- **Stats & analytics**: preflop/postflop/sizing/tournament stat modules, leak detector, player profiler.
- **Databases**: SQLite (default), PostgreSQL, MySQL/MariaDB — configurable from the GUI, with a cross-backend migration engine.
- **Localized**: 14 locale catalogues ship with the app; switch at runtime from *View → Language*.
- **PySide6 Desktop GUI**: The graphical interface has been completely ported to PySide6.
- **Self-Contained Platform Detection**: Window detection and geometry calculations are fully integrated for Linux, macOS, and Windows.

## 📦 Prebuilt downloads

Standalone builds for macOS (Apple Silicon), Windows x64 and Linux x64 are attached to every
[release](https://github.com/jejellyroll-fr/fpdb-3/releases/latest). They bundle their own Python
runtime — no install step. On macOS, read [docs/macos-gatekeeper.md](docs/macos-gatekeeper.md) first:
release artifacts are Developer ID signed and notarized only when the repository's macOS release
credentials are configured; otherwise the workflow publishes an ad-hoc artifact with the limitations
described there.

The available packagers depend on the platform:

- macOS ships only `fpdb-pyoxidizer-macos-arm64`. Keeping a single signed app
  identity is required for reliable Screen Recording and Accessibility grants.
- Linux ships both the PyOxidizer single-interpreter build and the PyInstaller
  directory distribution.
- Windows currently requires the PyInstaller directory distribution; its
  PyOxidizer build does not currently run.

## 🔧 Requirements

- Source installation: Python 3.11+ (3.13 recommended).
- PyOxidizer binaries: no system Python is required; the current PyOxidizer
  0.24 configuration embeds CPython 3.10.14 because it cannot link CPython
  3.11+. This is an implementation detail of the bundle, not the supported
  source-installation minimum.
- OS: Linux, Windows, macOS
- HUD: X11 (Linux), native window support (Windows/macOS)
- A C compiler and CMake — the equity engine is a native extension built at install time (see below)

## ⚙️ Install

From the repository root:

```bash
# venv + editable install with test extras (macOS/Linux)
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[test]

# or with uv (faster)
uv pip install -e .[test]
```

On Windows PowerShell, create and activate the environment with
`py -3 -m venv .venv` and `.venv\Scripts\Activate.ps1`, then run the same
`pip install` command.

Platform/feature extras: `.[linux]`, `.[windows]`, `.[macos]`, `.[postgresql]`, `.[mysql]`.

### Native equity engine

Equity calculations (AoF analyses, hand replayer EV) use the
[pypoker-eval](https://github.com/jejellyroll-fr/poker-eval) C extension. It is a **required**
dependency, pinned to `v1.2.0`, and pip builds it from source during the install above — which is
why a C compiler and CMake are needed. See [docs/EQUITY_ENGINE.md](docs/EQUITY_ENGINE.md).

## ▶️ Run

```bash
# Full launcher (console script — runs fpdb_3_legacy/legacy_launcher.py)
uv run fpdb_3_legacy

# Desktop GUI directly
python fpdb_3_legacy/fpdb.pyw

# HUD process
python fpdb_3_legacy/HUD_main.pyw
```

### macOS prebuilt builds

For an ad-hoc build (including a release built without the optional signing secrets), Gatekeeper
assesses the `fpdb.app` bundle as a unit, but the app is not notarized and its privacy identity is
not stable across builds. Move the bundle out of `~/Downloads` and clear the quarantine attribute:

```bash
mv ~/Downloads/fpdb.app /Applications/
xattr -dr com.apple.quarantine /Applications/fpdb.app
```

Extracting the archive with `tar` rather than Finder avoids the quarantine flag in the first place.
Full explanation in [docs/macos-gatekeeper.md](docs/macos-gatekeeper.md).

The 3.7.0 release also hardens the fast-fold HUD lifecycle: only one renderer may own a table,
stale overlays are removed, and the HUD reports the process holding the interlock when a second
instance is refused.

### Linux / Wayland

```bash
./fpdb-xwayland.sh        # from repo root
# or: export FPDB_FORCE_X11=1
```

### Profiling

Profiling is off by default. To record a session, set `FPDB_PROFILE=1`; fpdb
then writes a `.prof` and a readable summary to `~/fpdb_profiles` on exit.

```bash
FPDB_PROFILE=1 python fpdb_3_legacy/fpdb.pyw
```

## 🧪 Tests

From the repository root:

```bash
make test                 # main suite (excludes GUI)
make test-all             # incl. GUI (using run_tests.sh)
uv run pytest -k "stats"  # pattern
make lint && make format
```

Parser behaviour is locked by a golden-master corpus (`tests/fixtures/`) with per-hand invariant
checks. Adding a hand-history fixture under `tests/fixtures/hands/<room>/` also requires an entry in
`tests/fixtures/hands/live_parser_snapshots.json` — `test_live_parser_regression.py` globs each room
directory and fails on any file the manifest does not cover.

## 🗂 Layout (selected)

```
fpdb_3_legacy/
├── *ToFpdb.py            # one parser per poker room
├── iPoker/               # iPoker parser split into mixins
├── Hand.py, Database.py  # core hand model + DB layer
├── Hud.py, HUD_main.pyw  # HUD overlay
├── AutoNotes*.py         # auto-note rules engine
├── *_capture*.py         # SwC / iPoker live capture
├── fpdb.pyw              # desktop GUI entry point
└── legacy_launcher.py    # `fpdb_3_legacy` console script
fpdb/
└── infrastructure/platform/  # platform window and geometry detection
locale/                   # gettext .po catalogues (14 locales)
tests/fixtures/           # golden-master hand-history corpus
docs/                     # equity engine, macOS Gatekeeper, SwC capture protocol
```

## 📄 License

AGPL v3 — see [LICENSE](LICENSE).
