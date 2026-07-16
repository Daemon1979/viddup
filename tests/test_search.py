from types import SimpleNamespace

import pytest

from viddup.search import brightness_correlation, connected_components
from viddup.cli import build_parser


def detail(fid):
    return [SimpleNamespace(fid=fid), float(fid), fid]


def test_search_defaults_use_balanced_fingerprint_without_brightness_verification():
    args = build_parser().parse_args(["--db", "videos.db", "--search"])

    assert args.indexlength == 12
    assert args.radius == 3.0
    assert args.verify_brightness is False
    assert args.brightness_correlation == 0.70


def test_brightness_correlation_ignores_offset_and_scale():
    first = [10, 20, 15, 40, 25, 50, 20]
    second = [value * 1.7 + 35 for value in first]

    assert brightness_correlation(first, second) == pytest.approx(1.0)


def test_brightness_correlation_rejects_different_profiles():
    first = [0, 10, 0, 10, 0, 10, 0]
    second = [0, 1, 2, 3, 4, 5, 6]

    assert brightness_correlation(first, second) < 0.5


def test_brightness_correlation_tolerates_small_time_shift():
    first = list(range(50)) + list(range(50, 0, -1))
    second = [first[0]] * 2 + first[:-2]

    assert brightness_correlation(first, second) > 0.99


def test_connected_components_removes_false_member_but_keeps_true_pair():
    details = [detail(1), detail(2), detail(3)]

    groups = connected_components(details, {(2, 3)})

    assert [[item[0].fid for item in group] for group in groups] == [[2, 3]]


def test_connected_components_preserves_transitive_group():
    details = [detail(1), detail(2), detail(3)]

    groups = connected_components(details, {(1, 2), (2, 3)})

    assert {item[0].fid for item in groups[0]} == {1, 2, 3}
