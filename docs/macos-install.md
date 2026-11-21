# Installing fpdb-3 on macOS

There are two ways to run fpdb on a Mac:

| | Prebuilt `fpdb.app` | Source install (`install_macos.sh`) |
|---|---|---|
| Who it is for | players | contributors, testers, Intel Macs |
| Python needed | no (bundled) | Python 3.11+ (3.13 installed by the script) |
| Architectures | Apple Silicon (arm64) | Apple Silicon and Intel |
| Privacy permissions granted to | `fpdb.app` | the terminal app that starts fpdb |
| Updates | download the next release | `git pull` and rerun the script |

## Option A: prebuilt application

Download `fpdb-pyoxidizer-macos-arm64` from the
[latest release](https://github.com/jejellyroll-fr/fpdb-3/releases/latest), move
`fpdb.app` to `/Applications` and start it from there. Read
[macos-gatekeeper.md](macos-gatekeeper.md) first: it explains quarantine, ad-hoc
versus Developer ID builds, and why only one `fpdb.app` copy should exist.

## Option B: install from source

Requirements: macOS 11 or newer, [Homebrew](https://brew.sh), and about 1.5 GB of
free disk space.

```bash
git clone https://github.com/jejellyroll-fr/fpdb-3.git
cd fpdb-3
./install_macos.sh
```

The script

1. checks for the Xcode Command Line Tools and opens their installer if they are
   missing (run the script again once it finishes);
2. installs `python@3.13` and `cmake` with Homebrew if they are not there;
3. creates `.venv` in the repository and installs fpdb with the `macos` extra,
   which compiles the `pypoker-eval` equity engine;
4. checks that PySide6, PyObjC (Quartz/AppKit) and the equity engine load;
5. writes `fpdb.command`, a launcher you can double-click in Finder.

Options:

| Option | Effect |
|---|---|
| `--dev` | also install the test dependencies (`pytest`, `pytest-qt`, ...) |
| `--postgresql` / `--mysql` | install the extra database drivers |
| `--no-brew` | do not use Homebrew; CMake must already be on `PATH` |
| `--python PATH` | use this interpreter instead of Homebrew's Python 3.13 |

The script is idempotent: rerun it after `git pull` to update the environment.
An existing `.venv` is reused when its Python is recent enough, including one made
by `uv` (which has no `pip`; the script bootstraps it with `ensurepip`). The minimum
Python is read from `requires-python` in `pyproject.toml`.

### Starting fpdb

```bash
./fpdb.command
```

or double-click `fpdb.command` in Finder, or run `.venv/bin/fpdb_3_legacy`.

### Permissions

The HUD needs **Screen Recording**, **Accessibility** and **Automation** to find
poker tables and place its windows on them (System Settings ▸ Privacy &
Security). In a source install macOS attributes these to the program that
started fpdb — Terminal, iTerm, or Terminal again for `fpdb.command` — so grant
them to that application. macOS asks for Automation on first use, but never
asks for Accessibility: add the terminal to that list by hand. To see what is
granted:

```bash
.venv/bin/python -m tools.grant_macos_permissions --check-status
```

### Troubleshooting

- **`pypoker-eval` fails to build**: run `xcode-select --install`, then
  `brew install cmake`, and rerun the script.
- **The HUD finds no tables**: a permission is missing or was granted to a
  different terminal application; quit fpdb fully after granting it.
- **Do not mix with a PyInstaller build**: `build_fpdb-osx.sh` is the old
  PyInstaller packaging. Its `fpdb3.app` uses the same bundle identifier as the
  release build and confuses macOS privacy records.

The installer comes from [thegreatgabbsy](https://github.com/thegreatgabbsy)'s
fork (#828).
