import logging
import os
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from dataclasses import dataclass

from .hashing import VideoHashSkip, get_hashes
from .scanner import get_files
from .utils import format_duration, parse_extensions


@dataclass
class HashResult:
    fname: str
    index_info: list
    fps: float
    duration: float
    brightness: list
    elapsed: float


def default_num_jobs() -> int:
    cpu_count = os.cpu_count() or 1
    return max(1, min(cpu_count - 2, 4))


def compute_hashes(
    fname: str,
    fixduration: bool,
    show_progress: bool = False,
    hash_method: str = "legacy-center",
) -> HashResult:
    start_time = time.monotonic()
    index_info, fps, duration, brightness = get_hashes(
        fname,
        fixduration,
        show_progress=show_progress,
        hash_method=hash_method,
    )
    return HashResult(fname, index_info, fps, duration, brightness, time.monotonic() - start_time)


def store_hashes(dbi, result: HashResult) -> None:
    """Atomically replace all database data for one successfully hashed file."""
    with dbi.transaction():
        fi = dbi.insert_file(result.fname, result.fps, result.duration)
        dbi.delete_media_info(fi.fid)
        dbi.insert_hashes(fi.fid, result.index_info)
        dbi.insert_brightness(fi.fid, result.brightness)


def import_file(dbi, params, fname: str) -> bool:
    """Compute and atomically import hashes of the given filename."""
    try:
        if dbi.is_name_in_db(fname) and not params.refresh:
            logging.info("File %s already imported", fname)
            return False

        result = compute_hashes(
            fname,
            params.fixduration,
            show_progress=True,
            hash_method=params.hash_method,
        )
        store_hashes(dbi, result)
        logging.info("File %s imported in %s", fname, format_duration(result.elapsed))
        return True
    except KeyboardInterrupt:
        logging.warning("Aborted")
        raise
    except VideoHashSkip as exc:
        logging.warning("Skipped video %s: %s", fname, exc)
    except Exception:
        logging.warning("Failed to insert hashes for %s", fname, exc_info=True)
    return False


def _import_directory(dbi, params) -> None:
    files = []
    scanned = 0
    already_imported = 0
    for fname in get_files(params.dir, parse_extensions(params.vidext), params.exclude_dir):
        scanned += 1
        if dbi.is_name_in_db(fname):
            already_imported += 1
            if not params.refresh:
                continue
        files.append(fname)

    jobs = max(1, params.numjobs)
    total = len(files)
    files = iter(files)
    completed = 0
    imported = 0

    if params.refresh:
        logging.info(
            "Scan complete: %d video files found, %d already in database, %d queued (refresh enabled)",
            scanned,
            already_imported,
            total,
        )
    else:
        logging.info(
            "Scan complete: %d video files found, %d already in database, %d new files queued",
            scanned,
            already_imported,
            total,
        )
    logging.info("Importing with %d worker processes", jobs)

    with ProcessPoolExecutor(max_workers=jobs) as executor:
        pending = {}

        def submit_next() -> bool:
            try:
                fname = next(files)
            except StopIteration:
                return False
            future = executor.submit(
                compute_hashes,
                fname,
                params.fixduration,
                False,
                params.hash_method,
            )
            pending[future] = fname
            return True

        for _ in range(jobs):
            if not submit_next():
                break

        try:
            while pending:
                done, _ = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    fname = pending.pop(future)
                    completed += 1
                    try:
                        result = future.result()
                        store_hashes(dbi, result)
                        imported += 1
                        logging.info(
                            "Imported %d/%d: %s in %s",
                            completed,
                            total,
                            fname,
                            format_duration(result.elapsed),
                        )
                    except VideoHashSkip as exc:
                        logging.warning("Skipped %d/%d: %s: %s", completed, total, fname, exc)
                    except Exception:
                        logging.warning("Failed %d/%d: %s", completed, total, fname, exc_info=True)
                    submit_next()
        except KeyboardInterrupt:
            logging.warning("Aborted; cancelling %d queued imports", len(pending))
            for future in pending:
                future.cancel()
            raise

    logging.info("Directory import complete: %d imported, %d processed", imported, completed)


def handle_import(dbi, params) -> None:
    if params.dir:
        _import_directory(dbi, params)
    if params.file:
        import_file(dbi, params, params.file)
