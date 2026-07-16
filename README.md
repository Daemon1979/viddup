# viddup

`viddup` detects duplicate video scenes by hashing brightness changes and
searching similar hash windows in a SQLite database.

Version 1.1 changes the default fingerprint length from 10 to 12 for cleaner
search results and adds optional normalized brightness verification for KNN
candidates via `--verify-brightness`.

Version 1.2 adds layered TOML configuration through `viddup.conf`, independent
import/search settings, and reusable `balanced`, `precise`, and `sensitive`
search profiles.

This repository is the modern Python 3.12 port. The initial algorithm is kept
compatible with the legacy tool while packaging, setup, scanning, and KNN
backend handling are cleaned up.

The original project this port was based on is
[Eierkopp/viddup](https://github.com/Eierkopp/viddup.git).

Most code changes in this port were made with Codex assistance. If that is a
problem for your workflow, this repository may not be the right upstream for
you.

## Quick setup

Full installation instructions:

- English: [INSTALL.md](INSTALL.md)
- Ukrainian: [INSTALL_UA.md](INSTALL_UA.md)

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

At least one KNN backend must be importable. `hnswlib` is the preferred default
backend:

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

Directory imports hash several videos in parallel. By default, `dupfind` uses
the smaller of four workers or the detected CPU thread count minus two, with a
minimum of one. Override this for the storage and CPU available on the machine:

```sh
dupfind --db videos.db --dir /PATH/video --numjobs 6
```

Local SSD storage can usually sustain more workers than an HDD or a network
share. Database writes remain serialized and each video's filename, hashes,
and brightness data are committed atomically.

Build a portable source archive from the current working tree:

```sh
./makedist.sh
```

This creates `dist/viddup-dev.tar.gz`. To package an exact Git commit instead:

```sh
./makedist.sh COMMIT
```

The committed archive is named `dist/viddup-<short-hash>.tar.gz`.

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

The default search uses a fingerprint length of 12 and radius 3. This was found
to provide a good balance between useful matches and false positives on large
real-world databases:

```sh
dupfind --db videos.db --search
```

Use a shorter fingerprint when finding shorter or less similar fragments is
more important than minimizing manual review:

```sh
dupfind --db videos.db --search --indexlength 11
dupfind --db videos.db --search --indexlength 10
```

Lowering `--radius` below its default of 3 makes matching stricter, but can hide
copies changed by frame-rate conversion, editing, or encoding.

KNN candidates can also be verified against the normalized frame-brightness
profiles already stored in the database. This does not decode videos again:

```sh
dupfind --db videos.db --search --verify-brightness
```

The default minimum correlation is `0.70`. Override it when evaluating a media
collection:

```sh
dupfind --db videos.db --search --verify-brightness \
  --brightness-correlation 0.80
```

Normalization makes the check tolerant of global brightness changes, HDR/SDR,
resolution, and codec differences. Raising the threshold produces cleaner
results but may reject heavily edited or differently mastered copies.

## Configuration

Configuration files use TOML syntax with the traditional name `viddup.conf`.
They are loaded in this order, with later files taking precedence:

1. `~/.config/viddup/viddup.conf`
2. `./viddup.conf`
3. `--config /PATH/viddup.conf`

Command-line options override all configuration files. Start from
`viddup.conf.example`. Import and search exclusions are intentionally separate:

```toml
[import]
exclude_dirs = ["/PATH/video/Games"]

[search]
profile = "precise"
exclude_dirs = ["/PATH/video/Credits"]
```

Built-in profiles are `balanced`, `precise`, and `sensitive`:

```sh
dupfind --db videos.db --search --profile precise
```

Sections unrelated to the current operation are ignored. Unknown keys are
reported only when their section is active.

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

## Notes

PostgreSQL support from the legacy code was intentionally removed. Current DB
support is SQLite only.
