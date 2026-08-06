# FPDB-3 Standalone Legacy (Python)

The original FPDB-3 Python application: hand-history parsers, PySide6 GUI, statistics engine, and the HUD overlay. This repository hosts the standalone, self-contained legacy Python stack. It has been separated from the `fpdb-new` monorepo by removing all Rust and modern FastAPI components to keep it lightweight, fast, and easy to run.

## ✨ Highlights

- **Hand-History Import & Analysis** from 26 poker rooms. See [PARSER_SUPPORT.md](PARSER_SUPPORT.md) for which converters are covered by golden snapshots and which are kept only for historical archives.
- **Live capture** for rooms that write no hand-history files: SwC Poker (HTTP and native desktop), iPoker.
- **Real-Time HUD** overlay with draggable multiblock stats, positional panels, and a per-profile hero toggle.
- **Auto Notes**: rule-driven player notes with a visual workbench and card miniatures.
- **Stats & analytics**: preflop/postflop/sizing/tournament stat modules, leak detector, player profiler.
- **Databases**: SQLite (default), PostgreSQL, MySQL/MariaDB — configurable from the GUI, with a cross-backend migration engine.
- **Localized**: 14 locale catalogues ship with the app; switch at runtime from *View → Language*.
- **PySide6 Desktop GUI**: The graphical interface has been completely ported to PySide6.
- **Self-Contained Platform Detection**: Window detection and geometry calculations are fully integrated for Linux, macOS, and Windows.

## 📦 Prebuilt downloads

Standalone builds for macOS (Apple Silicon), Windows x64 and Linux x64 are attached to every
[release](https://github.com/jejellyroll-fr/fpdb-3/releases/latest). They bundle their own Python
runtime — no install step. On macOS, read [docs/macos-gatekeeper.md](docs/macos-gatekeeper.md) first.

Each platform ships two builds:

- `fpdb-pyoxidizer-*` — a single embedded interpreter, the smaller download.
- `fpdb-pyinstaller-*` — a directory distribution.

**On Windows, take the PyInstaller build**: the PyOxidizer one does not currently run.

## 🔧 Requirements

- Python 3.11+ (3.13 recommended)
- OS: Linux, Windows, macOS
- HUD: X11 (Linux), native window support (Windows/macOS)
- A C compiler and CMake — the equity engine is a native extension built at install time (see below)

## ⚙️ Install

From the repository root:

```bash
# venv + editable install with test extras
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .[test]

# or with uv (faster)
uv pip install -e .[test]
```

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

The builds ship an ad-hoc signed `fpdb.app`, which Gatekeeper assesses as a unit — but they are not
signed with a Developer ID nor notarized, so a browser download still arrives quarantined. Move the
bundle out of `~/Downloads` and clear the attribute:

```bash
mv ~/Downloads/fpdb.app /Applications/
xattr -dr com.apple.quarantine /Applications/fpdb.app
```

Extracting the archive with `tar` rather than Finder avoids the quarantine flag in the first place.
Full explanation in [docs/macos-gatekeeper.md](docs/macos-gatekeeper.md).

### Linux / Wayland

```bash
./fpdb-xwayland.sh        # from repo root
# or: export FPDB_FORCE_X11=1
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
