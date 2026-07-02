# viddup

`viddup` detects duplicate video scenes by hashing brightness changes and
searching similar hash windows in a SQLite database.

This repository is the modern Python 3.12 port. The initial algorithm is kept
compatible with the legacy tool while packaging, setup, scanning, and KNN
backend handling are cleaned up.

## Quick setup

Use Python 3.12. On FreeBSD, install both the concrete Python package and the
`python3` meta-port/wrapper so `/usr/local/bin/python3` exists. The Python
SQLite module is a separate package on FreeBSD and must be installed too.

Example package set:

```sh
pkg install python312 python3 py312-sqlite3 ffmpeg sqlite3 \
  py312-imageio py312-numpy py312-pyyaml py312-scipy py312-tqdm \
  py312-annoy py312-pytest
```

```sh
/usr/local/bin/python3 -m venv --system-site-packages .venv
. .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[test]"
```

The project may use system packages for heavy dependencies such as `scipy`,
`scikit-learn`, `faiss`, `pynndescent`, `hnswlib`, or `annoy`.

At least one KNN backend must be importable. The legacy priority is preserved
for automatic backend selection:

1. `hnswlib`
2. `cyflann`
3. `annoy`

Additional explicit backends are available for comparison:

- `sklearn` - exact `NearestNeighbors` baseline.
- `faiss` - exact L2 index for larger vector sets.
- `pynndescent` - approximate-neighbor backend.

Use `--knnlib NAME` to force a backend, for example:

```sh
dupfind --db videos.db --search --knnlib sklearn
```

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

Search while ignoring already-hashed directories:

```sh
dupfind --db videos.db --search --search-exclude-dir /PATH/video/skip-this-dir
```

Inspect database contents:

```sh
dupfind --db videos.db --list-db-dirs
dupfind --db videos.db --list-db-files --list-db-path /PATH/video/skip-this-dir
```

Remove database entries under a path. Without `--delete` this is a dry run:

```sh
dupfind --db videos.db --delete-db-path /PATH/video/skip-this-dir
dupfind --db videos.db --delete-db-path /PATH/video/skip-this-dir --delete
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
