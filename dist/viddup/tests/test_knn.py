import pytest

from viddup.knn import BACKENDS, available_backends, create_backend


def test_available_backends_returns_supported_names_only():
    assert set(available_backends()).issubset(set(BACKENDS))


@pytest.mark.parametrize("name", ["sklearn", "faiss", "pynndescent"])
def test_extra_backends_find_nearby_rows(name):
    pytest.importorskip(name if name != "sklearn" else "sklearn.neighbors")
    backend = create_backend(name, index_length=2)
    backend.build([[0.0, 0.0], [0.0, 0.5], [5.0, 5.0]])

    neighbors = set(backend.neighbors_within(0, radius=1.0))

    assert {0, 1}.issubset(neighbors)
    assert 2 not in neighbors
