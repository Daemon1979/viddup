import logging
import os
import time
from collections.abc import Iterable, Iterator


def normalize_excludes(paths: Iterable[str] | None) -> tuple[str, ...]:
    if not paths:
        return ()
    return tuple(os.path.abspath(path) for path in paths)


def is_excluded_dir(path: str, excludes: tuple[str, ...]) -> bool:
    abspath = os.path.abspath(path)
    return any(abspath == excluded or abspath.startswith(excluded + os.sep) for excluded in excludes)


def get_files(basedir: str, vid_ext: set[str], exclude_dirs: Iterable[str] | None = None) -> Iterator[str]:
    excludes = normalize_excludes(exclude_dirs)
    for excluded in excludes:
        logging.info("Excluding scan directory %s", excluded)

    for root, dirs, files in os.walk(basedir):
        dirs[:] = [d for d in dirs if not is_excluded_dir(os.path.join(root, d), excludes)]
        if is_excluded_dir(root, excludes):
            dirs[:] = []
            continue

        for filename in files:
            now = time.time()
            _, ext = os.path.splitext(filename)
            if filename.lower().endswith(".d.ts"):
                continue
            if ext.lower().lstrip(".") in vid_ext:
                fname = os.path.abspath(os.path.join(root, filename))
                statres = os.stat(fname)
                if now - statres.st_mtime > 3600:
                    yield fname
