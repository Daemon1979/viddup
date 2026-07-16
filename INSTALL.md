# Install viddup

These instructions target Python 3.12 and FreeBSD-style deployments where
large scientific Python packages are preferably installed by the OS package
manager and then reused from a virtual environment.

## 1. Install system packages

On FreeBSD, install both the concrete Python package and the `python3`
meta-port/wrapper. The wrapper provides `/usr/local/bin/python3`; it is not
always installed with `python312`.

The Python SQLite module is also a separate package on FreeBSD. Without it,
`dupfind` fails with `ModuleNotFoundError: No module named '_sqlite3'`.

Recommended base packages:

```sh
pkg install python312 python3 py312-sqlite3 ffmpeg sqlite3 \
  py312-imageio py312-numpy py312-pyyaml py312-scipy py312-tqdm \
  py312-pytest
```

Install at least one KNN backend. `hnswlib` is the recommended backend and the
default choice when available. Use packages or ports depending on what exists
on the target host:

```sh
pkg install py312-hnswlib py312-annoy py312-pynndescent
```

If a package is unavailable, install the missing backend from ports or with
`pip` inside the venv after it is created.

Optional benchmark/debug backends:

```sh
pkg install py312-scikit-learn py312-faiss
```

`sklearn` and `faiss` are useful as exact baselines, but they are much slower
than `hnswlib` for full radius searches on large databases.

## 2. Create a venv

Use `--system-site-packages` so the venv can reuse OS-installed modules:

```sh
cd /path/to/viddup
/usr/local/bin/python3 -m venv --system-site-packages .venv
. .venv/bin/activate
python -m pip install -U pip
```

## 3. Install viddup

For normal use:

```sh
python -m pip install .
```

For development and local tests:

```sh
python -m pip install -e ".[test]"
```

If `hnswlib` was not installed by the OS, the recommended fallback is to install
it from the upstream project inside the activated venv:

```sh
git clone https://github.com/nmslib/hnswlib.git
cd hnswlib
python -m pip install .
```

Project page: <https://github.com/nmslib/hnswlib>

## 4. Verify the install

```sh
python -c "import sqlite3, _sqlite3; print(sqlite3.sqlite_version)"
python -c "from viddup.knn import available_backends; print(available_backends())"
dupfind --help
python -m pytest -q
```

The KNN list should include at least one backend. Preferably it includes
`hnswlib`.

## 5. Optional wrapper

After the venv is created and `viddup` is installed, you can use the included
wrapper instead of activating the venv manually each time:

```sh
./dupfind.sh --help
./dupfind.sh --db videos.db --search
```

By default, the wrapper uses `.venv` next to the script. To use another venv:

```sh
VIDDUP_VENV=/path/to/venv ./dupfind.sh --help
```

## 6. Common commands

Create or update a database:

```sh
dupfind --db videos.db --dir /PATH/video
```

Directory imports use up to four parallel hashing processes by default while
keeping SQLite writes serialized and atomic. Tune concurrency for the machine
and storage with `--numjobs`:

```sh
dupfind --db videos.db --dir /PATH/video --numjobs 6
```

Use fewer workers for an HDD or network share if parallel reads reduce
throughput.

Skip directories during scan:

```sh
dupfind --db videos.db --dir /PATH/video \
  --exclude-dir /PATH/video/skip-this-dir \
  --exclude-dir /PATH/other-media
```

Search duplicates:

```sh
dupfind --db videos.db --search
```

The default search uses fingerprint length 12 and radius 3. This provides a
practical balance between useful matches and false positives:

```sh
dupfind --db videos.db --search
```

For shorter or less similar matching fragments, select a more sensitive search:

```sh
dupfind --db videos.db --search --indexlength 11
dupfind --db videos.db --search --indexlength 10
```

Shorter fingerprints increase sensitivity and false positives. Reducing
`--radius` below its default of 3 makes matching stricter, but can hide copies
altered by frame-rate conversion, editing, or encoding.

Optionally verify KNN candidates with normalized frame-brightness profiles that
are already stored in the database:

```sh
dupfind --db videos.db --search --verify-brightness
```

The default minimum correlation is `0.70`. It can be changed explicitly:

```sh
dupfind --db videos.db --search --verify-brightness \
  --brightness-correlation 0.80
```

This stage does not decode media again. It tolerates global brightness, codec,
resolution, and HDR/SDR differences by comparing normalized profile shapes.
Higher values reduce false positives but can reject more heavily edited copies.

### Configuration file

`viddup` reads TOML configuration from `~/.config/viddup/viddup.conf`, then
`./viddup.conf`, and finally a path passed with `--config`. Later files and then
CLI arguments override earlier values. See `viddup.conf.example`.

Use `[import]` for import-only options and `[search]` for search-only options.
Their `exclude_dirs` arrays are independent. Inactive sections are ignored, so
one configuration can safely contain settings for every operation.

Select a built-in or custom search profile with:

```sh
dupfind --db videos.db --search --profile precise
```

Force a KNN backend:

```sh
dupfind --db videos.db --search --knnlib hnswlib
dupfind --db videos.db --search --knnlib annoy
dupfind --db videos.db --search --knnlib pynndescent
```

Search while ignoring already-hashed paths:

```sh
dupfind --db videos.db --search --search-exclude-dir /PATH/video/skip-this-dir
```

Inspect database contents:

```sh
dupfind --db videos.db --list-db-dirs
dupfind --db videos.db --list-db-files --list-db-path /PATH/video/skip-this-dir
```

Dry-run removal of a path from the database:

```sh
dupfind --db videos.db --delete-db-path /PATH/video/skip-this-dir
```

Really remove that path from the database:

```sh
dupfind --db videos.db --delete-db-path /PATH/video/skip-this-dir --delete
```

Purge database entries whose files no longer exist:

```sh
dupfind --db videos.db --purge
dupfind --db videos.db --purge --delete
```

## 7. Backend notes

Default backend priority:

1. `hnswlib`
2. `cyflann`
3. `annoy`
4. `sklearn`
5. `faiss`
6. `pynndescent`

Practical recommendation:

- Use `hnswlib` for normal work. It was the fastest backend in the real DB
  benchmark and matched the exact baseline after radius normalization.
- Use `annoy` or `pynndescent` as alternatives if `hnswlib` is unavailable.
- Use `sklearn` and `faiss` mainly for debugging or benchmark comparison. Their
  exact radius mode is very slow on large databases.

## 8. Troubleshooting

Missing SQLite module:

```text
ModuleNotFoundError: No module named '_sqlite3'
```

Install `py312-sqlite3`, recreate or reactivate the venv, and verify:

```sh
python -c "import sqlite3, _sqlite3"
```

No KNN backend available:

```text
Please install at least one KNN library
```

Install `hnswlib` first if possible. Otherwise install `annoy` or
`pynndescent`.

Slow exact backends:

`sklearn` and `faiss` can be much slower because they are used as exact radius
baselines. This is expected; prefer `hnswlib` for normal runs.
