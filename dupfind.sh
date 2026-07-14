#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
VENV_DIR="${VIDDUP_VENV:-$SCRIPT_DIR/.venv}"

if [ ! -x "$VENV_DIR/bin/python" ]; then
    echo "viddup venv not found: $VENV_DIR" >&2
    echo "Create it first, for example:" >&2
    echo "  /usr/local/bin/python3 -m venv --system-site-packages .venv" >&2
    echo "  . .venv/bin/activate" >&2
    echo "  python -m pip install ." >&2
    exit 1
fi

if [ ! -x "$VENV_DIR/bin/dupfind" ]; then
    echo "viddup is not installed in the venv: $VENV_DIR" >&2
    echo "Install it from the project directory:" >&2
    echo "  $VENV_DIR/bin/python -m pip install '$SCRIPT_DIR'" >&2
    exit 1
fi

exec "$VENV_DIR/bin/dupfind" "$@"
