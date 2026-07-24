import json
from contextlib import contextmanager
import logging
import sqlite3 as sq

from .db_common import DBBase, FileInfo, MediaInfo, mk_stmt
from .hash_methods import DEFAULT_HASH_METHOD, get_hash_method


class DB(DBBase):
    def init_statements(self):
        return mk_stmt(sq)

    def get_db(self):
        conn = sq.connect(self.params.db)
        conn.execute("pragma busy_timeout = 300000").close()
        return conn

    @contextmanager
    def cursor(self):
        c = self.conn.cursor()
        yield c
        c.close()

    def make_schema(self):
        """Create the database schema if it does not exist already"""
        logging.info("Asserting DB schema is up-to-date")
        with self.cursor() as c:
            c.execute(
                "select 1 from sqlite_master where type = 'table' and name = 'filenames'"
            )
            existing_database = c.fetchone() is not None
            c.execute("create table if not exists filenames (id INTEGER PRIMARY KEY, name text, fps float, duration float)")
            c.execute("create unique index if not exists name_ux on filenames (name)")
            c.execute("create table if not exists hashes (filename_id int64, frame int, hash float)")
            c.execute("create table if not exists whitelist (id1 INTEGER, id2 INTEGER)")
            c.execute("create table if not exists brightness (filename_id int64, brightness blob)")
            c.execute(
                "create table if not exists media_info "
                "(filename_id INTEGER PRIMARY KEY, extension text, codec text, "
                "width INTEGER, height INTEGER, file_size INTEGER)"
            )
            c.execute("create unique index if not exists whitelist_ux on whitelist (id1, id2)")
            c.execute("create unique index if not exists filename_id_hashes_ux on hashes (filename_id, frame)")
            c.execute(
                "create table if not exists metadata "
                "(key text primary key, value text not null)"
            )

            requested = getattr(self.params, "hash_method", None)
            c.execute("select value from metadata where key = 'hash_method'")
            row = c.fetchone()
            if row is None:
                method = get_hash_method(
                    DEFAULT_HASH_METHOD if existing_database else requested or DEFAULT_HASH_METHOD
                )
                metadata = {
                    "hash_method": method.name,
                    "hash_method_version": str(method.version),
                    "video_filter": method.video_filter,
                    "extrema_distance_seconds": "10",
                }
                c.executemany(
                    "insert into metadata (key, value) values (?, ?)",
                    metadata.items(),
                )
                if existing_database:
                    logging.info(
                        "Legacy database detected; recording hash method %s",
                        method.name,
                    )
            else:
                method = get_hash_method(row[0])
                c.execute(
                    "select value from metadata where key = 'hash_method_version'"
                )
                version_row = c.fetchone()
                if version_row is None or int(version_row[0]) != method.version:
                    raise ValueError(
                        f"database uses unsupported {method.name} hash method version"
                    )
                if requested and requested != method.name:
                    raise ValueError(
                        f"database uses hash method {method.name}; "
                        f"--hash-method {requested} cannot be mixed into it"
                    )

            self.hash_method = method.name
            self.hash_method_version = method.version
        self.conn.commit()

    def del_file(self, fid):
        with self.cursor() as c:
            c.execute(self.s["DEL_FILE"], [fid])
            c.execute("delete from hashes where filename_id = ?", [fid])
            c.execute("delete from brightness where filename_id = ?", [fid])
            c.execute("delete from media_info where filename_id = ?", [fid])
            c.execute("delete from whitelist where id1 = ? or id2 = ?", [fid, fid])
        self.conn.commit()

    def get_file_infos_under_path(self, path):
        prefix = path.rstrip("/") + "/"
        with self.cursor() as c:
            c.execute(
                "select id, name, fps, duration from filenames where name = ? or name like ? order by name asc",
                [path, prefix + "%"],
            )
            return [FileInfo._make(i) for i in c.fetchall()]

    def del_files_under_path(self, path):
        files = self.get_file_infos_under_path(path)
        for fileinfo in files:
            self.del_file(fileinfo.fid)
        return files

    def insert_brightness(self, fid, brightness):
        with self.cursor() as c:
            c.execute(self.s["DELETE_BRIGHTNESS"], [fid])
            c.execute(self.s["INSERT_BRIGHTNESS"], [fid, json.dumps(brightness)])

    def delete_media_info(self, fid):
        with self.cursor() as c:
            c.execute("delete from media_info where filename_id = ?", [fid])

    def get_media_infos(self, fids):
        result = {}
        fids = list(dict.fromkeys(fids))
        with self.cursor() as c:
            for start in range(0, len(fids), 900):
                batch = fids[start:start + 900]
                placeholders = ",".join("?" for _ in batch)
                c.execute(
                    "select filename_id, extension, codec, width, height, "
                    f"file_size from media_info where filename_id in ({placeholders})",
                    batch,
                )
                for row in c.fetchall():
                    info = MediaInfo._make(row)
                    result[info.filename_id] = info
        return result

    def insert_media_infos(self, media_infos):
        with self.cursor() as c:
            c.executemany(
                "insert or replace into media_info "
                "(filename_id, extension, codec, width, height, file_size) "
                "values (?, ?, ?, ?, ?, ?)",
                media_infos,
            )

    def insert_file(self, fname, fps, duration):
        fid = self.get_id(fname)
        if fid is None:
            with self.cursor() as c:
                c.execute("insert into filenames values (null, ?, ?, ?)", [fname, fps, duration])
                fid = c.lastrowid
        else:
            with self.cursor() as c:
                c.execute(self.s["UPDATE_FILE"], [fname, fps, duration, fid])
        return FileInfo(fid, fname, fps, duration)

    def vacuum_db(self):
        logging.info("Vacuuming DB")
        self.conn.execute("vacuum")

    def tidy_db(self):
        logging.info("Cleaning orphaned database rows")
        try:
            with self.cursor() as c:
                c.execute("delete from hashes where filename_id not in (select id from filenames)")
                c.execute("delete from brightness where filename_id not in (select id from  filenames)")
                c.execute("delete from media_info where filename_id not in (select id from filenames)")
                c.execute("delete from whitelist where id1 not in (select id from filenames)")
                c.execute("delete from whitelist where id2 not in (select id from filenames)")
            self.conn.commit()
        except Exception as e:
            logging.error("Error during cleaning up: %s", e, exc_info=True)
            self.conn.rollback()
