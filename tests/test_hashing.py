import pytest

from viddup.hashing import get_extrema


def test_get_extrema_returns_frame_and_delta_seconds():
    result = get_extrema([0, 1, 0, 0, 2, 0, 0], min_dist=1, fps=1)

    assert result == [(1, 1.0), (4, 3.0)]


def test_get_extrema_preserves_legacy_error_for_zero_fps():
    with pytest.raises(ValueError):
        get_extrema([0, 1, 0], min_dist=10, fps=0)
