from pathlib import Path
from types import SimpleNamespace

import pytest

from viddup import importer
from viddup.db_common import MediaInfo
from viddup.importer import HashResult, store_hashes
from viddup.sqlite_db import DB


def make_result(path: str, value: float = 1.0) -> HashResult:
    return HashResult(
        fname=path,
        index_info=[(10, value), (20, value + 1)],
        fps=25.0,
        duration=10.0,
        brightness=[value, value + 1],
        elapsed=0.1,
    )


def test_store_hashes_rolls_back_new_file_on_failure(tmp_path: Path, monkeypatch):
    db = DB(SimpleNamespace(db=str(tmp_path / "test.db")))
    path = str(tmp_path / "video.mp4")

    monkeypatch.setattr(db, "insert_brightness", lambda *_: (_ for _ in ()).throw(RuntimeError("write failed")))

    with pytest.raises(RuntimeError, match="write failed"):
        store_hashes(db, make_result(path))

    assert db.get_id(path) is None


def test_store_hashes_rolls_back_refresh_to_previous_data(tmp_path: Path, monkeypatch):
    db = DB(SimpleNamespace(db=str(tmp_path / "test.db")))
    path = str(tmp_path / "video.mp4")
    original = make_result(path, 1.0)
    store_hashes(db, original)
    fid = db.get_id(path)
    cached = MediaInfo(fid, "mp4", "h264", 1280, 720, 123456)
    db.insert_media_infos([cached])
    db.commit()

    monkeypatch.setattr(db, "insert_brightness", lambda *_: (_ for _ in ()).throw(RuntimeError("write failed")))

    with pytest.raises(RuntimeError, match="write failed"):
        store_hashes(db, make_result(path, 9.0))

    assert db.get_hashes(fid, 0, 100) == ([10, 20], [1.0, 2.0])
    assert db.get_media_infos([fid]) == {fid: cached}
    with db.cursor() as cursor:
        cursor.execute("select brightness from brightness where filename_id = ?", [fid])
        assert cursor.fetchone()[0] == "[1.0, 2.0]"


@pytest.mark.parametrize(
    ("cpu_count", "expected"),
    [(None, 1), (1, 1), (2, 1), (3, 1), (6, 4), (32, 4)],
)
def test_default_num_jobs_is_safe_and_capped(monkeypatch, cpu_count, expected):
    monkeypatch.setattr(importer.os, "cpu_count", lambda: cpu_count)

    assert importer.default_num_jobs() == expected
