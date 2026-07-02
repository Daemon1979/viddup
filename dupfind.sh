#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
VENV_DIR="${VIDDUP_VENV:-$SCRIPT_DIR/.venv}"

if [ ! -f "$VENV_DIR/bin/activate" ]; then
    echo "viddup venv not found: $VENV_DIR" >&2
    echo "Create it first, for example:" >&2
    echo "  /usr/local/bin/python3 -m venv --system-site-packages .venv" >&2
    echo "  . .venv/bin/activate" >&2
    echo "  python -m pip install -e ." >&2
    exit 1
fi

. "$VENV_DIR/bin/activate"
exec dupfind "$@"
