#!/bin/sh
set -eu

PROJECT_NAME=viddup
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
DIST_DIR="$SCRIPT_DIR/dist"

usage() {
    echo "usage: $0 [commit]" >&2
    echo "  no commit: package the current working tree as ${PROJECT_NAME}-dev.tar.gz" >&2
    echo "  commit:    package that Git commit as ${PROJECT_NAME}-<short-hash>.tar.gz" >&2
}

if [ "$#" -gt 1 ]; then
    usage
    exit 2
fi

cd "$SCRIPT_DIR"
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || {
    echo "not inside a Git working tree: $SCRIPT_DIR" >&2
    exit 1
}

mkdir -p "$DIST_DIR"
WORK_DIR=$(mktemp -d "${TMPDIR:-/tmp}/${PROJECT_NAME}-dist.XXXXXX")
trap 'rm -rf "$WORK_DIR"' EXIT HUP INT TERM

if [ "$#" -eq 1 ]; then
    COMMIT=$(git rev-parse --verify "$1^{commit}") || {
        echo "unknown commit: $1" >&2
        exit 1
    }
    VERSION=$(git rev-parse --short "$COMMIT")
    ROOT_NAME="${PROJECT_NAME}-${VERSION}"
    mkdir -p "$WORK_DIR/$ROOT_NAME"
    git archive "$COMMIT" | tar -xf - -C "$WORK_DIR/$ROOT_NAME"
else
    VERSION=dev
    ROOT_NAME="${PROJECT_NAME}-dev"
    MANIFEST="$WORK_DIR/manifest.txt"
    mkdir -p "$WORK_DIR/$ROOT_NAME"

    git ls-files --cached --others --exclude-standard | while IFS= read -r path; do
        case "$path" in
            .gitignore|dist/*|build/*|docs/TODO.md|*.db|*.db-*|*.sqlite|*.log)
                continue
                ;;
        esac
        if [ -f "$path" ]; then
            printf '%s\n' "$path"
        fi
    done >"$MANIFEST"

    tar -cf - -T "$MANIFEST" | tar -xf - -C "$WORK_DIR/$ROOT_NAME"
fi

# These paths may exist in old commits but are local/development artifacts.
rm -rf \
    "$WORK_DIR/$ROOT_NAME/.git" \
    "$WORK_DIR/$ROOT_NAME/.venv" \
    "$WORK_DIR/$ROOT_NAME/build" \
    "$WORK_DIR/$ROOT_NAME/dist" \
    "$WORK_DIR/$ROOT_NAME/my" \
    "$WORK_DIR/$ROOT_NAME/my312"
rm -f "$WORK_DIR/$ROOT_NAME/docs/TODO.md" "$WORK_DIR/$ROOT_NAME/.gitignore"

ARCHIVE="$DIST_DIR/${ROOT_NAME}.tar.gz"
tar -czf "$ARCHIVE" -C "$WORK_DIR" "$ROOT_NAME"

echo "created: $ARCHIVE"
if command -v sha256 >/dev/null 2>&1; then
    sha256 "$ARCHIVE"
elif command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$ARCHIVE"
fi
