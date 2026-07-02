import pytest

from viddup.hashing import VideoHashSkip, _parse_rate, get_extrema


def test_get_extrema_returns_frame_and_delta_seconds():
    result = get_extrema([0, 1, 0, 0, 2, 0, 0], min_dist=1, fps=1)

    assert result == [(1, 1.0), (4, 3.0)]


def test_get_extrema_skips_zero_fps():
    with pytest.raises(VideoHashSkip):
        get_extrema([0, 1, 0], min_dist=10, fps=0)


def test_parse_rate_rejects_unreasonable_ffmpeg_timebases():
    assert _parse_rate("25/1") == 25.0
    assert _parse_rate("30000/1001") == pytest.approx(29.97, rel=0.01)
    assert _parse_rate("0/0") is None
    assert _parse_rate("1000/1") is None
    assert _parse_rate("90000/1") is None
