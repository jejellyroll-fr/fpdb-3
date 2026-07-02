# FPDB-3 Standalone Legacy (Python)

The original FPDB-3 Python application: hand-history parsers, PySide6 GUI, statistics engine, and the HUD overlay. This repository hosts the standalone, self-contained legacy Python stack. It has been separated from the `fpdb-new` monorepo by removing all Rust and modern FastAPI components to keep it lightweight, fast, and easy to run.

## ✨ Highlights

- **Pure Python**: Zero Rust or external compilation dependencies.
- **Hand-History Import & Analysis** from many poker rooms (PokerStars, Winamax, PartyPoker, iPoker, 888/Pacific, GGPoker, Bovada, Merge, OnGame, Microgaming…)
- **Real-Time HUD** overlay on poker tables.
- **Self-Contained Platform Detection**: Window detection and geometry calculations are fully integrated for Linux, macOS, and Windows.
- **PySide6 Desktop GUI**: The graphical interface has been completely ported to PySide6.
- **Databases**: SQLite (default), PostgreSQL, MySQL.

## 🔧 Requirements

- Python 3.10+ (3.13 supported)
- OS: Linux, Windows, macOS
- HUD: X11 (Linux), native window support (Windows/macOS)

## ⚙️ Install

From the repository root:

```bash
# venv + editable install with test extras
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .[test]

# or with uv (faster)
uv pip install -e .[test]
```

Platform/feature extras: `.[linux]`, `.[windows]`, `.[macos]`, `.[postgresql]`.

## ▶️ Run

```bash
# Full launcher (console script — runs fpdb_3_legacy/legacy_launcher.py)
uv run fpdb_3_legacy

# Desktop GUI directly
python fpdb_3_legacy/fpdb.pyw

# HUD process
python fpdb_3_legacy/HUD_main.pyw

# Legacy CLI
python fpdb_3_legacy/fpdb_cli.py --help
```

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

Parser behaviour is locked by a golden-master corpus (`tests/fixtures/`) with per-hand invariant checks.

## 🗂 Layout (selected)

```
fpdb_3_legacy/
├── *ToFpdb.py            # one parser per poker room
├── iPoker/               # iPoker parser split into mixins
├── Hand.py, Database.py  # core hand model + DB layer
├── Hud.py, HUD_main.pyw  # HUD overlay
├── fpdb.pyw              # desktop GUI entry point
├── fpdb_cli.py           # CLI entry point
└── legacy_launcher.py    # `fpdb_3_legacy` console script
fpdb/
└── infrastructure/platform/  # platform window and geometry detection
```

## 📄 License

AGPL v3 — see [LICENSE](LICENSE).
