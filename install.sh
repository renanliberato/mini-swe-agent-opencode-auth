#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

if command -v mini >/dev/null 2>&1 && command -v uv >/dev/null 2>&1; then
    MINI_PATH=$(command -v mini)
    MINI_REAL_PATH=$(python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$MINI_PATH")
    MINI_BIN=$(dirname -- "$MINI_REAL_PATH")
    if [ -x "$MINI_BIN/python" ]; then
        uv pip install --python "$MINI_BIN/python" --no-deps --editable "$ROOT"
        mkdir -p "$HOME/.local/bin"
        ln -sf "$MINI_BIN/mswea" "$HOME/.local/bin/mswea"
        printf 'Installed mswea at %s\n' "$HOME/.local/bin/mswea"
        exit 0
    fi
fi

python3 -m pip install --editable "$ROOT"
printf 'Installed mswea using the current Python environment.\n'
