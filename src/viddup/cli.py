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
from .config import ConfigError, load_config, resolve_defaults
from .duplicate_report import log_duplicate_groups
from .importer import default_num_jobs, handle_import
from .hash_methods import HASH_METHODS
from .knn import BACKENDS, available_backends, default_backend_name
from .scanner import get_files
from .search import handle_search
from .settings import KNOWN_VID_TYPES_DEFAULT
from .utils import parse_extensions


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


def _explicit_repeated_values(argv: list[str], option: str) -> list[str]:
    values = []
    for index, argument in enumerate(argv):
        if argument == option and index + 1 < len(argv):
            values.append(argv[index + 1])
        elif argument.startswith(option + "="):
            values.append(argument.split("=", 1)[1])
    return values


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

    log_duplicate_groups(dbi, duplicates, params.numjobs)


def fixfilenames(args):
    for fname in get_files(args.dir, parse_extensions(args.vidext), args.exclude_dir):
        try:
            fname.encode("utf8")
        except Exception:
            logging.warning("invalid filename %s", fname, exc_info=True)
            fn = fname.encode("utf8", "ignore")
            new_fname = fn.decode("utf8")
            logging.info("changed into %s", new_fname)


def build_parser(defaults: dict | None = None) -> argparse.ArgumentParser:
    defaults = defaults or {}
    parser = argparse.ArgumentParser(prog="dupfind")
    parser.add_argument("--config", help="TOML config file; also checks ~/.config/viddup/viddup.conf and ./viddup.conf")
    parser.add_argument("--profile", default="balanced", help="Search profile, default %(default)s")
    parser.add_argument("--purge", default=False, action="store_true", help="Purge deleted files from database (dry run mode)")
    parser.add_argument("--delete", default=False, action="store_true", help="Really delete from database in purge")
    parser.add_argument("--vacuum", default=False, action="store_true", help="Do vacuum on db")
    parser.add_argument(
        "--nice",
        type=int,
        help="Nice level inherited by hashing and FFmpeg processes, default %(default)s",
        default=10,
    )
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
    parser.add_argument(
        "--hash-method",
        choices=HASH_METHODS,
        help="Hash extraction method for a new database; existing databases keep their recorded method",
    )
    parser.add_argument("--refresh", action="store_true", help="Re-hash file but keep whitelistings intact", default=False)
    parser.add_argument("--search", action="store_true", help="Search duplicates in database")
    parser.add_argument("--ignore_start", type=int, default=0, help="Ignore search results starting in the first seconds of a movie, default 0")
    parser.add_argument("--ignore_end", type=int, default=0, help="Ignore search results starting in the last seconds of a movie, default 0")
    parser.add_argument("--db", required="db" not in defaults, help="SQLite3 database file")
    parser.add_argument(
        "--indexlength",
        default=12,
        type=int,
        help="Fingerprint length; use 10 or 11 for shorter/more sensitive matches, default 12",
    )
    parser.add_argument("--scenelength", default=300, type=int, help="Length in seconds of scenes to match, default 300")
    parser.add_argument(
        "--radius",
        default=3.0,
        type=float,
        help="Maximum fingerprint distance; try 2 for stricter matching, default 3.0",
    )
    parser.add_argument(
        "--verify-brightness",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Verify KNN candidates using normalized frame-brightness correlation",
    )
    parser.add_argument(
        "--brightness-correlation",
        type=float,
        default=0.70,
        metavar="VALUE",
        help="Minimum correlation for --verify-brightness, default 0.70",
    )
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
    parser.add_argument("--cpu-profile", default=False, action="store_true", help=argparse.SUPPRESS)
    parser.set_defaults(**defaults)
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    argv = list(argv) if argv is not None else sys.argv[1:]
    bootstrap = argparse.ArgumentParser(add_help=False)
    bootstrap.add_argument("--config")
    bootstrap.add_argument("--profile")
    bootstrap_args, _ = bootstrap.parse_known_args(argv)
    try:
        config, loaded_configs = load_config(bootstrap_args.config)
        defaults, selected_profile = resolve_defaults(
            config,
            bootstrap_args.profile,
            import_mode="--dir" in argv or "--file" in argv,
            search_mode="--search" in argv,
        )
    except ConfigError as exc:
        bootstrap.error(str(exc))

    defaults["profile"] = selected_profile
    parser = build_parser(defaults)
    params = parser.parse_args(argv)

    if "--exclude-dir" in argv:
        params.exclude_dir = _explicit_repeated_values(argv, "--exclude-dir")
    if "--search-exclude-dir" in argv:
        params.search_exclude_dir = _explicit_repeated_values(argv, "--search-exclude-dir")

    for path in loaded_configs:
        logging.info("Loaded config %s", path)

    if params.numjobs < 1:
        parser.error("--numjobs must be at least 1")
    if not -1.0 <= params.brightness_correlation <= 1.0:
        parser.error("--brightness-correlation must be between -1 and 1")

    if params.search:
        logging.info(
            "Search configuration: profile=%s indexlength=%d radius=%.3f "
            "verify_brightness=%s brightness_correlation=%.3f",
            params.profile,
            params.indexlength,
            params.radius,
            params.verify_brightness,
            params.brightness_correlation,
        )
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

    try:
        dbi = DB(params)
    except ValueError as exc:
        parser.error(str(exc))

    params.hash_method = dbi.hash_method
    logging.info(
        "Database hash method: %s (version %d)",
        dbi.hash_method,
        dbi.hash_method_version,
    )

    profile = None
    if params.cpu_profile:
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
