from __future__ import annotations

import argparse
import cProfile
from itertools import combinations
import logging
import os
import pstats
import sys
from collections import namedtuple

import yaml
from tqdm import tqdm

from . import FileInfo  # noqa: F401  FileInfo needed by yaml Loader
from .importer import default_num_jobs, handle_import
from .knn import BACKENDS, available_backends, default_backend_name
from .scanner import get_files
from .search import handle_search
from .settings import KNOWN_VID_TYPES_DEFAULT
from .utils import parse_extensions, format_duration


class TqdmStream:
    def __init__(self, stream):
        self.stream = stream

    def write(self, data):
        data = data.rstrip("\r\n")
        if data:
            tqdm.write(data, file=self.stream)
            self.stream.flush()

    def flush(self):
        self.stream.flush()


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)-15s;%(levelname)s;%(message)s",
        stream=TqdmStream(sys.stdout),
    )


def handle_purge(dbi, params, do_delete=None):
    if do_delete is None:
        do_delete = params.delete

    del_files = []
    fn_fis = []
    for fi in dbi.get_file_infos():
        fn_fis.append(fi.fid)
        if not os.access(fi.name, os.R_OK):
            del_files.append(fi)

    logging.warning("Need to delete %d of %d files", len(del_files), len(fn_fis))
    if do_delete:
        for fi in del_files:
            logging.info("deleting %s", fi.name)
            dbi.del_file(fi.fid)
    else:
        for fi in del_files:
            logging.info(fi.name)


def handle_list_db_files(dbi, params):
    roots = [os.path.abspath(path) for path in params.list_db_path]
    rows = []
    for fileinfo in dbi.get_file_infos():
        if roots and not any(fileinfo.name == root or fileinfo.name.startswith(root.rstrip("/") + os.sep) for root in roots):
            continue
        rows.append(fileinfo)

    logging.info("DB files: %d", len(rows))
    for fileinfo in rows:
        logging.info("%s", fileinfo.name)


def handle_list_db_dirs(dbi, params):
    roots = [os.path.abspath(path) for path in params.list_db_path]
    counts = {}
    for fileinfo in dbi.get_file_infos():
        if roots and not any(fileinfo.name == root or fileinfo.name.startswith(root.rstrip("/") + os.sep) for root in roots):
            continue
        directory = os.path.dirname(fileinfo.name)
        counts[directory] = counts.get(directory, 0) + 1

    logging.info("DB directories: %d", len(counts))
    for directory, count in sorted(counts.items()):
        logging.info("%6d %s", count, directory)


def handle_delete_db_path(dbi, params):
    for path in params.delete_db_path:
        abspath = os.path.abspath(path)
        files = dbi.get_file_infos_under_path(abspath)
        logging.warning("DB path %s matches %d files", abspath, len(files))
        for fileinfo in files:
            logging.info("%s", fileinfo.name)
        if params.delete:
            deleted = dbi.del_files_under_path(abspath)
            logging.warning("Deleted %d DB entries under %s", len(deleted), abspath)
        else:
            logging.warning("Dry run only; pass --delete to remove these DB entries")


def whitelist(dbi, params, files=None):
    Entry = namedtuple("Entry", "name, fid")

    if files is None:
        files = params.whitelist

    with dbi.transaction() as conn:
        ids = set()
        for filename in files:
            fid = dbi.get_id(filename)
            if fid is not None:
                ids.add(Entry._make([filename, fid]))
            else:
                logging.warning("File %s not found in DB", filename)

        if len(ids) < 2:
            logging.warning("Need at least two files to whitelist")
            return

        retval = []
        for f1, f2 in combinations(list(ids), 2):
            try:
                dbi.whitelist(f1.fid, f2.fid)
                conn.commit()
                retval.append((f1, f2))
                logging.info("Whitelisted %s and %s", f1.name, f2.name)
            except Exception:
                logging.error("Failed to whitelist pair %s - %s", f1.name, f2.name, exc_info=False)
        return retval


def fetch_duplicates(dbi, f):
    candidates = yaml.load(f, Loader=yaml.Loader)
    result = []
    for row in candidates:
        new_row = []
        for fi, pos in row:
            if os.access(fi.name, os.R_OK):
                new_row.append([fi, pos])
        if len(new_row) < 2:
            continue

        fids = [fi[0].fid for fi in new_row]
        fids.sort()
        is_whitelisted = True
        for id1, id2 in combinations(fids, 2):
            if not dbi.is_whitelisted(id1, id2):
                is_whitelisted = False
                break
        if not is_whitelisted:
            result.append(new_row)

    return result


def handle_searchres(dbi, params):
    with open(params.searchres) as f:
        duplicates = fetch_duplicates(dbi, f)

    if params.ui:
        raise NotImplementedError("The legacy UI was not ported yet")

    for match in duplicates:
        logging.info("Group of %d files found", len(match))
        for fileinfo, offset in match:
            logging.info("ffplay -ss %s '%s'", format_duration(offset), fileinfo.name)


def fixfilenames(args):
    for fname in get_files(args.dir, parse_extensions(args.vidext), args.exclude_dir):
        try:
            fname.encode("utf8")
        except Exception:
            logging.warning("invalid filename %s", fname, exc_info=True)
            fn = fname.encode("utf8", "ignore")
            new_fname = fn.decode("utf8")
            logging.info("changed into %s", new_fname)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dupfind")
    parser.add_argument("--purge", default=False, action="store_true", help="Purge deleted files from database (dry run mode)")
    parser.add_argument("--delete", default=False, action="store_true", help="Really delete from database in purge")
    parser.add_argument("--vacuum", default=False, action="store_true", help="Do vacuum on db")
    parser.add_argument("--nice", type=int, help="Nice level for background operation, default 5", default=5)
    parser.add_argument("--dir", help="Import video hashes from directory and its subdirectories")
    parser.add_argument(
        "--numjobs",
        type=int,
        default=default_num_jobs(),
        help="Parallel video hashing processes for --dir, default %(default)s",
    )
    parser.add_argument("--exclude-dir", action="append", default=[], help="Skip this directory during --dir scan; can be passed more than once")
    parser.add_argument("--search-exclude-dir", action="append", default=[], help="Skip this already-hashed directory during --search; can be passed more than once")
    parser.add_argument("--file", help="Import video hashes for a single file")
    parser.add_argument("--refresh", action="store_true", help="Re-hash file but keep whitelistings intact", default=False)
    parser.add_argument("--search", action="store_true", help="Search duplicates in database")
    parser.add_argument("--ignore_start", type=int, default=0, help="Ignore search results starting in the first seconds of a movie, default 0")
    parser.add_argument("--ignore_end", type=int, default=0, help="Ignore search results starting in the last seconds of a movie, default 0")
    parser.add_argument("--db", required=True, help="SQLite3 database file")
    parser.add_argument("--indexlength", default=10, type=int, help="Length of index in searches, default 10")
    parser.add_argument("--scenelength", default=300, type=int, help="Length in seconds of scenes to match, default 300")
    parser.add_argument("--radius", default=3.0, type=float, help="Measure for acceptable index difference, default 3.0")
    parser.add_argument("--ui", action="store_true", help="Launch ui after search results")
    parser.add_argument("--searchres", help="Filename of search result, used in --search and --ui without --search")
    parser.add_argument("--step", type=int, default=1, help="Step width for searching index, default 1")
    parser.add_argument("--whitelist", nargs="+", help="Whitelist a list of files")
    parser.add_argument("--list-db-files", action="store_true", help="List hashed file paths stored in the database")
    parser.add_argument("--list-db-dirs", action="store_true", help="List directories represented in the database with file counts")
    parser.add_argument("--list-db-path", action="append", default=[], help="Limit --list-db-files/--list-db-dirs to this path prefix; can be repeated")
    parser.add_argument("--delete-db-path", action="append", default=[], help="Delete DB entries under this path prefix; dry-run unless --delete is also passed")
    parser.add_argument("--knnlib", help="KNN library to use")
    parser.add_argument("--vidext", default=KNOWN_VID_TYPES_DEFAULT, help=f"filename extensions to consider, default {KNOWN_VID_TYPES_DEFAULT}")
    parser.add_argument("--fixduration", default=False, action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--fixspeed", default=False, action="store_true", help="Make search more robust for time-scaled videos")
    parser.add_argument("--fixfilenames", default=False, action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--debug", default=False, action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--profile", default=False, action="store_true", help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = build_parser()
    params = parser.parse_args(argv)

    if params.numjobs < 1:
        parser.error("--numjobs must be at least 1")

    if params.search:
        available = available_backends()
        if not available:
            logging.error("Please install at least one KNN library: %s", ", ".join(BACKENDS))
            return 1
        if params.knnlib is None:
            params.knnlib = default_backend_name()
        if params.knnlib not in available:
            logging.error("Unsupported or unavailable KNN library %s; available: %s", params.knnlib, ", ".join(available))
            return 1

    try:
        nl = os.nice(0)
        nl = os.nice(max(params.nice - nl, 0))
        logging.info("Nice level %d", nl)
    except Exception:
        logging.info("Setting nice level not supported")

    from .sqlite_db import DB

    dbi = DB(params)

    profile = None
    if params.profile:
        profile = cProfile.Profile()
        profile.enable()

    if params.fixfilenames:
        if params.dir:
            fixfilenames(params)
        else:
            logging.error("please set --dir option as well")

    if params.whitelist:
        whitelist(dbi, params)

    if params.list_db_files:
        handle_list_db_files(dbi, params)

    if params.list_db_dirs:
        handle_list_db_dirs(dbi, params)

    if params.delete_db_path:
        handle_delete_db_path(dbi, params)

    if params.purge:
        dbi.tidy_db()
        handle_purge(dbi, params)

    if params.vacuum:
        dbi.vacuum_db()

    if params.dir or params.file:
        handle_import(dbi, params)

    if params.search:
        handle_search(dbi, params)
    elif params.searchres:
        handle_searchres(dbi, params)

    if profile:
        profile.create_stats()
        stats = pstats.Stats(profile)
        stats.sort_stats("cumulative")
        stats.print_stats(50)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
