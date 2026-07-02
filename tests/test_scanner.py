from pathlib import Path

from viddup.scanner import get_files, is_excluded_dir, normalize_excludes


def test_excluded_dir_matches_children(tmp_path: Path):
    excluded = normalize_excludes([str(tmp_path / "skip")])

    assert is_excluded_dir(str(tmp_path / "skip"), excluded)
    assert is_excluded_dir(str(tmp_path / "skip" / "nested"), excluded)
    assert not is_excluded_dir(str(tmp_path / "skip_other"), excluded)


def test_get_files_skips_excluded_dirs_and_typescript_declarations(tmp_path: Path):
    keep = tmp_path / "keep"
    skip = tmp_path / "skip"
    keep.mkdir()
    skip.mkdir()

    video = keep / "movie.mp4"
    declaration = keep / "types.d.ts"
    skipped_video = skip / "ignored.mp4"
    for path in (video, declaration, skipped_video):
        path.write_bytes(b"x")

    # Scanner ignores files modified in the last hour.
    old_time = 1
    for path in (video, declaration, skipped_video):
        path.touch()
        path.chmod(0o644)
        import os

        os.utime(path, (old_time, old_time))

    found = list(get_files(str(tmp_path), {"mp4", "ts"}, [str(skip)]))

    assert found == [str(video)]
