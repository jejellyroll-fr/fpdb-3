# FPDB-3 Legacy (Python)

The original FPDB-3 Python application: hand-history parsers, PySide6 GUI,
statistics engine, and the HUD overlay. This is the **reference
implementation** — the Modern (`fpdb/`) and Rust (`rustyFPDB/`) ports are
validated against its behaviour through parity testing.

> Actively maintained for parity. New product work happens on the Modern and
> Rust stacks, but the legacy app remains fully usable.

## ✨ Highlights

- Hand-history import & analysis from many poker rooms (PokerStars, Winamax,
  PartyPoker, iPoker, 888/Pacific, GGPoker, Bovada, Merge, OnGame, Microgaming…)
- Real-time **HUD** overlay on poker tables
- Statistics & reporting
- PySide6 desktop GUI
- Optional web interface and REST API launchers
- Databases: SQLite (default), PostgreSQL, MySQL

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
# Full launcher (console script — runs run_fpdb_full.py)
uv run fpdb_3_legacy

# Desktop GUI directly
python fpdb_3_legacy/fpdb.pyw

# HUD process
python fpdb_3_legacy/HUD_main.pyw

# Legacy CLI
python fpdb_3_legacy/fpdb_cli.py --help

# Legacy REST API launcher
python fpdb_3_legacy/run_fpdb_api.py

# Web launcher
python fpdb_3_legacy/run_fpdb_web.py
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
make test-all             # incl. GUI
uv run pytest -k "stats"  # pattern
make lint && make format
```

Parser behaviour is locked by a golden-master corpus
(`tests/fixtures/`) with per-hand invariant checks. See [`docs/`](../docs/)
for the parser invariant tracker and the current stabilization plan.

## 🗂 Layout (selected)

```
fpdb_3_legacy/
├── *ToFpdb.py            # one parser per poker room
├── iPoker/               # iPoker parser split into mixins (base, hand_info, …)
├── Hand.py, Database.py  # core hand model + DB layer
├── Hud.py, HUD_main.pyw  # HUD overlay
├── fpdb.pyw              # desktop GUI entry point
├── fpdb_cli.py           # CLI entry point
├── run_fpdb_*.py         # api / web / full launchers
└── legacy_launcher.py    # `fpdb_3_legacy` console script
```

## 📄 License

AGPL v3 — see [LICENSE](../LICENSE).
