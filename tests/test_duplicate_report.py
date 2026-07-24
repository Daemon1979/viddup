import logging
from types import SimpleNamespace

from viddup import duplicate_report
from viddup.db_common import MediaInfo
from viddup.duplicate_report import VideoDisplayInfo, format_file_size


class FakeDB:
    def __init__(self):
        self.media_infos = {}

    def get_media_infos(self, fids):
        return {
            fid: self.media_infos[fid]
            for fid in fids
            if fid in self.media_infos
        }

    def transaction(self):
        class Transaction:
            def __enter__(self):
                return None

            def __exit__(self, *_):
                return False

        return Transaction()

    def insert_media_infos(self, infos):
        for info in infos:
            self.media_infos[info.filename_id] = info


def test_format_file_size(tmp_path):
    path = tmp_path / "video.mp4"
    path.write_bytes(b"x" * 1536)

    assert format_file_size(str(path)) == "1.50 KiB"


def test_log_duplicate_groups_outputs_metadata(tmp_path, monkeypatch, caplog):
    first = tmp_path / "first.mp4"
    second = tmp_path / "second.mkv"
    first.write_bytes(b"x" * 1024)
    second.write_bytes(b"x" * 2048)
    duplicates = [
        [
            [SimpleNamespace(fid=1, name=str(first), duration=600.0), 42.0],
            [SimpleNamespace(fid=2, name=str(second), duration=601.0), 43.0],
        ]
    ]
    db = FakeDB()
    monkeypatch.setattr(
        duplicate_report,
        "probe_video_display_info",
        lambda _: VideoDisplayInfo("h264", 1920, 1080),
    )

    with caplog.at_level(logging.INFO):
        duplicate_report.log_duplicate_groups(db, duplicates, num_jobs=2)

    output = caplog.text
    assert "Group of 2 files found" in output
    assert (
        "match=00:00:42 duration=00:10:00 ext=mp4 codec=h264 "
        "resolution=1920x1080 size=1.00 KiB"
    ) in output
    assert f"path={first}" in output
    assert "ffplay" not in output
    assert len(db.media_infos) == 2


def test_log_duplicate_groups_reuses_cached_metadata(
    tmp_path, monkeypatch, caplog
):
    path = tmp_path / "cached.mp4"
    path.write_bytes(b"x")
    duplicates = [
        [[SimpleNamespace(fid=7, name=str(path), duration=30.0), 5.0]]
    ]
    db = FakeDB()
    db.media_infos[7] = MediaInfo(7, "mp4", "hevc", 3840, 2160, 123456)
    monkeypatch.setattr(
        duplicate_report,
        "probe_video_display_info",
        lambda _: (_ for _ in ()).throw(AssertionError("ffprobe called")),
    )

    with caplog.at_level(logging.INFO):
        duplicate_report.log_duplicate_groups(db, duplicates)

    assert "Media metadata cache: 1 reused, 0 probed, 0 stored" in caplog.text
    assert "codec=hevc resolution=3840x2160 size=120.56 KiB" in caplog.text
