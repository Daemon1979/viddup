# Install viddup

These steps assume Python 3.12 and a local copy of this `viddup` directory.
On FreeBSD, install the `python3` meta-port/wrapper as well as the concrete
`python312` package, otherwise `/usr/local/bin/python3` may not exist.

## 1. Install system dependencies

Install FFmpeg and the Python scientific stack using the OS package manager
where possible.

Minimum Python modules:

- Python `_sqlite3` module (`py312-sqlite3` on FreeBSD)
- `imageio`
- `numpy`
- `PyYAML`
- `scipy`
- `tqdm`
- at least one KNN backend: `hnswlib`, `cyflann`, or `annoy`

Optional backends for later experiments:

- `scikit-learn`
- `faiss`
- `pynndescent`

On FreeBSD this is expected to look roughly like:

```sh
pkg install python312 python3 py312-sqlite3 ffmpeg sqlite3 \
  py312-imageio py312-numpy py312-pyyaml py312-scipy py312-tqdm \
  py312-annoy py312-pytest
```

If available on the target host, also install packages such as:

```sh
pkg install py312-scikit-learn py312-faiss py312-pynndescent
```

`hnswlib` or `cyflann` may need to be installed manually if they are not
packaged for the target OS.

## 2. Create a venv

Use `--system-site-packages` when heavy dependencies were installed by the OS:

```sh
/usr/local/bin/python3 -m venv --system-site-packages .venv
. .venv/bin/activate
python -m pip install -U pip
```

## 3. Install viddup

From this directory:

```sh
python -m pip install -e ".[test]"
```

## 4. Verify

```sh
python -c "import sqlite3; import _sqlite3; print(sqlite3.sqlite_version)"
dupfind --help
python -m pytest -q
```

## 5. Run

Import or update a database:

```sh
dupfind --db videos.db --dir /PATH/video
```

Skip noisy directories:

```sh
dupfind --db videos.db --dir /PATH/video \
  --exclude-dir /PATH/video/skip-this-dir \
  --exclude-dir /PATH/other-media
```

Search duplicates:

```sh
dupfind --db videos.db --search
```

Purge missing files from DB:

```sh
dupfind --db videos.db --purge
dupfind --db videos.db --purge --delete
```

## Notes

- SQLite is the only supported database backend.
- Default KNN backend priority is `hnswlib -> cyflann -> annoy`.
- If several KNN libraries are installed, pass `--knnlib annoy` or another
  backend name to select one explicitly.
