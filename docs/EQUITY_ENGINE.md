# Native equity engine

fpdb uses `pypoker-eval` through `fpdb_3_legacy/equity.py`. The application
installs the pinned `v1.2.0` native dependency by default. It still starts when
the extension cannot be loaded; equity and all-in EV are then skipped and the
rest of the application remains usable.

The prebuilt platform bundles include the backend. A source installation needs
the compiler and CMake toolchain described below when a compatible wheel is not
available.

## Local Python 3.13 build

With a checkout of the `poker-eval` repository at
`/Users/jde/Documents/github/poker-eval`:

```bash
brew install cmake
cmake -S /Users/jde/Documents/github/poker-eval \
  -B /Users/jde/Documents/github/poker-eval/build \
  -DCMAKE_POSITION_INDEPENDENT_CODE=ON -DCMAKE_BUILD_TYPE=Release
cmake --build /Users/jde/Documents/github/poker-eval/build -j4
cd /Users/jde/Documents/github/fpdb-3
uv pip install --python .venv/bin/python setuptools
uv pip install --python .venv/bin/python --no-build-isolation \
  /Users/jde/Documents/github/poker-eval
```

Verify the native backend with:

```bash
.venv/bin/pytest -q test/test_equity.py
```

Community-card streets shorter than five cards are padded with explicit
`__` placeholders. This is required by poker-eval: a three-card board without
placeholders is treated as final rather than as a flop awaiting turn/river.
