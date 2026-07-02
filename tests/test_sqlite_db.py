from pathlib import Path
from types import SimpleNamespace

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
