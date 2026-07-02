import logging
import time

from .hashing import VideoHashSkip, get_hashes
from .scanner import get_files
from .utils import format_duration, parse_extensions


def import_file(dbi, params, fname: str) -> None:
    """Compute and import hashes of the given filename into the database."""
    start_time = time.time()
    with dbi.transaction() as conn:
        try:
            if dbi.is_name_in_db(fname):
                if not params.refresh:
                    logging.info("File %s already imported", fname)
                    return

            index_info, fps, duration, brightness = get_hashes(fname, params.fixduration)

            fi = dbi.insert_file(fname, fps, duration)
            dbi.insert_hashes(fi.fid, index_info)
            dbi.insert_brightness(fi.fid, brightness)

            conn.commit()
            logging.info("File %s imported in %s", fname, format_duration(time.time() - start_time))

        except KeyboardInterrupt:
            logging.warning("Aborted")
            raise
        except VideoHashSkip as exc:
            logging.warning("Skipped video %s: %s", fname, exc)
        except Exception:
            logging.warning("Failed to insert hashes for %s", fname, exc_info=True)


def handle_import(dbi, params) -> None:
    if params.dir:
        for fname in get_files(params.dir, parse_extensions(params.vidext), params.exclude_dir):
            import_file(dbi, params, fname)
    if params.file:
        import_file(dbi, params, params.file)
