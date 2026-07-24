from pathlib import Path
from types import SimpleNamespace

from viddup.db_common import MediaInfo
from viddup.sqlite_db import DB


def test_get_and_delete_files_under_path(tmp_path: Path):
    db = DB(SimpleNamespace(db=str(tmp_path / "test.db")))
    keep = str(tmp_path / "Video" / "keep.mp4")
    remove_one = str(tmp_path / "SkipDir" / "one.mp4")
    remove_two = str(tmp_path / "SkipDir" / "nested" / "two.mp4")
    not_remove = str(tmp_path / "SkipDir_old" / "three.mp4")

    for path in (keep, remove_one, remove_two, not_remove):
        db.insert_file(path, fps=25.0, duration=10.0)
    db.commit()

    matches = db.get_file_infos_under_path(str(tmp_path / "SkipDir"))

    assert sorted(item.name for item in matches) == sorted([remove_one, remove_two])

    deleted = db.del_files_under_path(str(tmp_path / "SkipDir"))

    assert sorted(item.name for item in deleted) == sorted([remove_one, remove_two])
    assert db.get_id(remove_one) is None
    assert db.get_id(remove_two) is None
    assert db.get_id(keep) is not None
    assert db.get_id(not_remove) is not None


def test_tidy_keeps_successful_file_without_extrema(tmp_path):
    db = DB(SimpleNamespace(db=str(tmp_path / "videos.db")))
    fileinfo = db.insert_file("/videos/static.mkv", 60.0, 30.0)
    db.insert_brightness(fileinfo.fid, [42.0] * 10)
    db.commit()

    db.tidy_db()

    assert db.get_id("/videos/static.mkv") == fileinfo.fid
    assert db.get_brightness(fileinfo.fid) is not None


def test_new_database_defaults_to_legacy_hash_method(tmp_path):
    db = DB(SimpleNamespace(db=str(tmp_path / "videos.db"), hash_method=None))

    assert db.hash_method == "legacy-center"
    assert db.hash_method_version == 1


def test_new_database_records_requested_full_frame_method(tmp_path):
    path = tmp_path / "videos.db"
    db = DB(SimpleNamespace(db=str(path), hash_method="full-frame"))
    db.conn.close()

    reopened = DB(SimpleNamespace(db=str(path), hash_method=None))

    assert reopened.hash_method == "full-frame"
    with reopened.cursor() as cursor:
        cursor.execute("select value from metadata where key = 'video_filter'")
        assert cursor.fetchone()[0] == "scale=128:72:flags=fast_bilinear"


def test_existing_legacy_database_without_metadata_is_marked_legacy(tmp_path):
    path = tmp_path / "legacy.db"
    import sqlite3

    connection = sqlite3.connect(path)
    connection.execute(
        "create table filenames (id INTEGER PRIMARY KEY, name text, fps float, duration float)"
    )
    connection.commit()
    connection.close()

    db = DB(SimpleNamespace(db=str(path), hash_method=None))

    assert db.hash_method == "legacy-center"


def test_database_rejects_mixed_hash_methods(tmp_path):
    path = tmp_path / "videos.db"
    db = DB(SimpleNamespace(db=str(path), hash_method="full-frame"))
    db.conn.close()

    import pytest

    with pytest.raises(ValueError, match="cannot be mixed"):
        DB(SimpleNamespace(db=str(path), hash_method="legacy-center"))


def test_media_info_cache_is_created_stored_and_deleted(tmp_path):
    db = DB(SimpleNamespace(db=str(tmp_path / "videos.db")))
    fileinfo = db.insert_file("/videos/example.mp4", 25.0, 60.0)
    cached = MediaInfo(fileinfo.fid, "mp4", "h264", 1920, 1080, 123456)
    db.insert_media_infos([cached])
    db.commit()

    assert db.get_media_infos([fileinfo.fid]) == {fileinfo.fid: cached}

    db.del_file(fileinfo.fid)

    assert db.get_media_infos([fileinfo.fid]) == {}
