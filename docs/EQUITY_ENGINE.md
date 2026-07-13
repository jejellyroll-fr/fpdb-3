# Optional equity engine

fpdb uses `pypoker-eval` through `fpdb_3_legacy/equity.py`. The application
continues to run when the native extension is absent; equity and all-in EV are
then skipped.

## Local Python 3.13 build

With sibling clones at `/Users/jde/Documents/github/poker-eval` and
`/Users/jde/Documents/github/pypoker-eval`:

```bash
brew install cmake
cd /Users/jde/Documents/github/pypoker-eval
cmake -S poker-eval -B poker-eval/build \
  -DCMAKE_POSITION_INDEPENDENT_CODE=ON -DCMAKE_BUILD_TYPE=Release
cmake --build poker-eval/build -j4
cd /Users/jde/Documents/github/fpdb-3
uv pip install --python .venv/bin/python setuptools
uv pip install --python .venv/bin/python --no-build-isolation \
  /Users/jde/Documents/github/pypoker-eval
```

Verify the native backend with:

```bash
.venv/bin/pytest -q test/test_equity.py
```

Community-card streets shorter than five cards are padded with explicit
`__` placeholders. This is required by poker-eval: a three-card board without
placeholders is treated as final rather than as a flop awaiting turn/river.
