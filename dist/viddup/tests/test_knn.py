from viddup.knn import available_backends


def test_available_backends_returns_legacy_names_only():
    assert set(available_backends()).issubset({"hnswlib", "cyflann", "annoy"})
