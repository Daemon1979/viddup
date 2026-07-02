# viddup

`viddup` detects duplicate video scenes by hashing brightness changes and
searching similar hash windows in a SQLite database.

This repository is the modern Python 3.12 port. The initial algorithm is kept
compatible with the legacy tool while packaging, setup, scanning, and KNN
backend handling are cleaned up.

## Quick setup

Use Python 3.12. On this host `/usr/local/bin/python3` points to the target
interpreter.

```sh
/usr/local/bin/python3 -m venv --system-site-packages .venv
. .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[test]"
```

The project may use system packages for heavy dependencies such as `scipy`,
`scikit-learn`, `faiss`, `pynndescent`, `hnswlib`, or `annoy`.

At least one legacy KNN backend must be importable:

1. `hnswlib`
2. `cyflann`
3. `annoy`

That priority is preserved for the default backend when several are installed.

## Usage

After install, the command is available directly:

```sh
dupfind --help
```

Import/update hashes:

```sh
dupfind --db videos.db --dir /PATH/video
```

Skip noisy directories during scan:

```sh
dupfind --db videos.db --dir /PATH/video \
  --exclude-dir /PATH/video/skip-this-dir \
  --exclude-dir /PATH/other-media
```

Search duplicates:

```sh
dupfind --db videos.db --search
```

Purge DB entries whose files no longer exist:

```sh
dupfind --db videos.db --purge
dupfind --db videos.db --purge --delete
```

Run tests:

```sh
pytest
```

## Project layout

- `src/viddup/cli.py` - command line entry point.
- `src/viddup/hashing.py` - video hashing and brightness extrema extraction.
- `src/viddup/search.py` - duplicate search flow.
- `src/viddup/knn.py` - KNN backend registry and adapters.
- `src/viddup/scanner.py` - directory walking, extension filtering, excludes.
- `src/viddup/sqlite_db.py` - SQLite storage.
- `docs/TODO.md` - follow-up work discovered during real scans.

## Notes

PostgreSQL support from the legacy code was intentionally removed. Current DB
support is SQLite only.
