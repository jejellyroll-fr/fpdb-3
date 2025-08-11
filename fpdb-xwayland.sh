#!/usr/bin/env bash
# Launch FPDB underXWayland (Option A)

# variables
export FPDB_FORCE_X11=1             
export QT_QPA_PLATFORM=xcb          

# start
uv run python fpdb.pyw "$@"
