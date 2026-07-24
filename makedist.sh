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

copy_worktree_file() {
    path=$1
    target="$WORK_DIR/$ROOT_NAME/$path"
    mkdir -p "$(dirname "$target")"
    cp -p "$path" "$target"
}

copy_commit_file() {
    path=$1
    target="$WORK_DIR/$ROOT_NAME/$path"
    mkdir -p "$(dirname "$target")"
    git show "$COMMIT:$path" >"$target"
}

copy_file() {
    if [ "$VERSION" = dev ]; then
        copy_worktree_file "$1"
    else
        copy_commit_file "$1"
    fi
}

copy_production_files() {
    copy_file pyproject.toml
    copy_file README.md
    copy_file INSTALL.md
    copy_file INSTALL_UA.md
    copy_file viddup.conf.example
    copy_file dupfind.sh
    copy_file makedist.sh

    if [ "$VERSION" = dev ]; then
        find src/viddup -type f -name '*.py' -print | sort |
            while IFS= read -r path; do
                copy_file "$path"
            done
    else
        git ls-tree -r --name-only "$COMMIT" -- src/viddup |
            while IFS= read -r path; do
                case "$path" in
                    *.py) copy_file "$path" ;;
                esac
            done
    fi
    chmod +x "$WORK_DIR/$ROOT_NAME/dupfind.sh" \
        "$WORK_DIR/$ROOT_NAME/makedist.sh"
}

if [ "$#" -eq 1 ]; then
    COMMIT=$(git rev-parse --verify "$1^{commit}") || {
        echo "unknown commit: $1" >&2
        exit 1
    }
    VERSION=$(git rev-parse --short "$COMMIT")
    ROOT_NAME="${PROJECT_NAME}-${VERSION}"
    mkdir -p "$WORK_DIR/$ROOT_NAME"
else
    VERSION=dev
    ROOT_NAME="${PROJECT_NAME}-dev"
    mkdir -p "$WORK_DIR/$ROOT_NAME"
fi

copy_production_files

ARCHIVE="$DIST_DIR/${ROOT_NAME}.tar.gz"
tar -czf "$ARCHIVE" -C "$WORK_DIR" "$ROOT_NAME"

echo "created: $ARCHIVE"
if command -v sha256 >/dev/null 2>&1; then
    sha256 "$ARCHIVE"
elif command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$ARCHIVE"
fi
