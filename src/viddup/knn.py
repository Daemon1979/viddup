from __future__ import annotations

import importlib
import logging
import multiprocessing
from abc import ABC, abstractmethod
from collections.abc import Sequence

import numpy as np

from .settings import KNN_BACKEND_PRIORITY


Vector = Sequence[float]


class KNNBackend(ABC):
    name: str

    def __init__(self, index_length: int, fixspeed: bool = False):
        self.index_length = index_length
        self.fixspeed = fixspeed

    @abstractmethod
    def build(self, items: list[Vector]) -> None:
        raise NotImplementedError

    @abstractmethod
    def __len__(self) -> int:
        raise NotImplementedError

    @abstractmethod
    def neighbors_within(self, rownum: int, radius: float) -> list[int]:
        raise NotImplementedError

    @abstractmethod
    def row(self, rownum: int):
        raise NotImplementedError

    def _normalize_speed(self, items):
        if not self.fixspeed:
            return items
        arr = np.array(items, dtype=float)
        for n, item in enumerate(arr):
            mean = np.mean(item)
            if mean:
                arr[n] = 128.0 * item / mean
        return arr


class AnnoyBackend(KNNBackend):
    name = "annoy"

    def __init__(self, index_length: int, fixspeed: bool = False):
        super().__init__(index_length, fixspeed)
        self.module = importlib.import_module("annoy")

    def build(self, items: list[Vector]) -> None:
        logging.info("Start building annoy index")
        self.idx = self.module.AnnoyIndex(self.index_length, metric="euclidean")
        self.items = self._normalize_speed(items)
        for n, item in enumerate(self.items):
            self.idx.add_item(n, item)
        self.idx.build(20)

    def __len__(self) -> int:
        return self.idx.get_n_items()

    def neighbors_within(self, rownum: int, radius: float) -> list[int]:
        elem_idx, elem_dists = self.idx.get_nns_by_item(rownum, 20, include_distances=True)
        return [item for n, item in enumerate(elem_idx) if elem_dists[n] < radius]

    def row(self, rownum: int):
        return self.idx.get_item_vector(rownum)


class CyflannBackend(KNNBackend):
    name = "cyflann"

    def __init__(self, index_length: int, fixspeed: bool = False):
        super().__init__(index_length, fixspeed)
        self.module = importlib.import_module("cyflann")

    def build(self, items: list[Vector]) -> None:
        logging.info("Start building flann index")
        self.idx = self.module.FLANNIndex(algorithm="kdtree")
        self.items = self._normalize_speed(items)
        self.idx.build_index(self.items)

    def __len__(self) -> int:
        return len(self.idx.data)

    def neighbors_within(self, rownum: int, radius: float) -> list[int]:
        row = self.idx.data[rownum]
        elem_idx, _ = self.idx.nn_radius(row, radius, sorted=True)
        return elem_idx

    def row(self, rownum: int):
        return self.idx.data[rownum]


class HnswlibBackend(KNNBackend):
    name = "hnswlib"

    def __init__(self, index_length: int, fixspeed: bool = False):
        super().__init__(index_length, fixspeed)
        self.module = importlib.import_module("hnswlib")

    def build(self, items: list[Vector]) -> None:
        logging.info("Start building hnswlib index")
        self.idx = self.module.Index(space="l2", dim=self.index_length)
        self.idx.set_num_threads(multiprocessing.cpu_count())
        self.idx.init_index(max_elements=len(items), ef_construction=100, M=self.index_length)
        self.items = np.array(self._normalize_speed(items))
        self.idx.add_items(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def neighbors_within(self, rownum: int, radius: float) -> list[int]:
        elem_idx, elem_dists = self.idx.knn_query(self.items[rownum], k=min(20, len(self.items)))
        return [item for n, item in enumerate(elem_idx[0]) if elem_dists[0][n] < radius * radius]

    def row(self, rownum: int):
        return self.items[rownum]


class SklearnBackend(KNNBackend):
    name = "sklearn"

    def __init__(self, index_length: int, fixspeed: bool = False):
        super().__init__(index_length, fixspeed)
        self.module = importlib.import_module("sklearn.neighbors")

    def build(self, items: list[Vector]) -> None:
        logging.info("Start building sklearn exact nearest-neighbor index")
        self.items = np.array(self._normalize_speed(items), dtype=float)
        self.idx = self.module.NearestNeighbors(metric="euclidean")
        self.idx.fit(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def neighbors_within(self, rownum: int, radius: float) -> list[int]:
        elem_idx = self.idx.radius_neighbors(self.items[rownum:rownum + 1], radius=radius, return_distance=False)
        return [int(item) for item in elem_idx[0]]

    def row(self, rownum: int):
        return self.items[rownum]


class FaissBackend(KNNBackend):
    name = "faiss"

    def __init__(self, index_length: int, fixspeed: bool = False):
        super().__init__(index_length, fixspeed)
        self.module = importlib.import_module("faiss")

    def build(self, items: list[Vector]) -> None:
        logging.info("Start building faiss exact L2 index")
        self.items = np.ascontiguousarray(self._normalize_speed(items), dtype=np.float32)
        self.idx = self.module.IndexFlatL2(self.index_length)
        self.idx.add(self.items)

    def __len__(self) -> int:
        return int(self.idx.ntotal)

    def neighbors_within(self, rownum: int, radius: float) -> list[int]:
        _, _, elem_idx = self.idx.range_search(self.items[rownum:rownum + 1], radius * radius)
        return [int(item) for item in elem_idx]

    def row(self, rownum: int):
        return self.items[rownum]


class PyNNDescentBackend(KNNBackend):
    name = "pynndescent"

    def __init__(self, index_length: int, fixspeed: bool = False):
        super().__init__(index_length, fixspeed)
        self.module = importlib.import_module("pynndescent")

    def build(self, items: list[Vector]) -> None:
        logging.info("Start building pynndescent approximate nearest-neighbor index")
        self.items = np.array(self._normalize_speed(items), dtype=float)
        self.neighbor_count = min(20, len(self.items))
        self.idx = self.module.NNDescent(self.items, metric="euclidean", n_neighbors=self.neighbor_count)

    def __len__(self) -> int:
        return len(self.items)

    def neighbors_within(self, rownum: int, radius: float) -> list[int]:
        elem_idx, elem_dists = self.idx.query(self.items[rownum:rownum + 1], k=self.neighbor_count)
        return [int(item) for n, item in enumerate(elem_idx[0]) if elem_dists[0][n] < radius]

    def row(self, rownum: int):
        return self.items[rownum]


BACKENDS = {
    "annoy": AnnoyBackend,
    "cyflann": CyflannBackend,
    "faiss": FaissBackend,
    "hnswlib": HnswlibBackend,
    "pynndescent": PyNNDescentBackend,
    "sklearn": SklearnBackend,
}


def available_backends() -> list[str]:
    result = []
    for name in KNN_BACKEND_PRIORITY:
        if importlib.util.find_spec(name) is not None:
            result.append(name)
    return result


def default_backend_name() -> str | None:
    backends = available_backends()
    return backends[0] if backends else None


def create_backend(name: str, index_length: int, fixspeed: bool = False) -> KNNBackend:
    if name not in BACKENDS:
        raise ValueError(f"Unsupported KNN backend {name!r}")
    return BACKENDS[name](index_length=index_length, fixspeed=fixspeed)
