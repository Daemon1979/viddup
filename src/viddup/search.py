import logging
from collections import OrderedDict
from itertools import combinations

import json
import numpy as np
from tqdm import tqdm

from .knn import create_backend
from .scanner import is_path_under, normalize_excludes
from .duplicate_report import log_duplicate_groups


BRIGHTNESS_SAMPLES = 1000
BRIGHTNESS_MAX_LAG_RATIO = 0.02
BRIGHTNESS_CACHE_SIZE = 32


def brightness_correlation(first, second, samples=BRIGHTNESS_SAMPLES, max_lag_ratio=BRIGHTNESS_MAX_LAG_RATIO):
    """Compare brightness profile shapes independently of absolute brightness."""
    first = np.asarray(first, dtype=float)
    second = np.asarray(second, dtype=float)
    if len(first) < 2 or len(second) < 2:
        return 0.0

    positions = np.linspace(0.0, 1.0, samples)
    first = np.interp(positions, np.linspace(0.0, 1.0, len(first)), first)
    second = np.interp(positions, np.linspace(0.0, 1.0, len(second)), second)

    first_std = first.std()
    second_std = second.std()
    if first_std == 0 or second_std == 0:
        return 0.0
    first = (first - first.mean()) / first_std
    second = (second - second.mean()) / second_std

    max_lag = max(0, int(samples * max_lag_ratio))
    best = -1.0
    for lag in range(-max_lag, max_lag + 1):
        if lag < 0:
            left, right = first[:lag], second[-lag:]
        elif lag > 0:
            left, right = first[lag:], second[:-lag]
        else:
            left, right = first, second
        score = float(np.corrcoef(left, right)[0, 1])
        if np.isfinite(score):
            best = max(best, score)
    return best


def connected_components(details, accepted_pairs):
    """Return duplicate subgroups after rejected pair edges are removed."""
    adjacency = {detail[0].fid: set() for detail in details}
    by_fid = {detail[0].fid: detail for detail in details}
    for first, second in accepted_pairs:
        adjacency[first].add(second)
        adjacency[second].add(first)

    result = []
    seen = set()
    for fid in adjacency:
        if fid in seen or not adjacency[fid]:
            continue
        stack = [fid]
        component = []
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            component.append(by_fid[current])
            stack.extend(adjacency[current] - seen)
        if len(component) > 1:
            result.append(component)
    return result


class Index:
    def __init__(self, dbi, params):
        logging.info("Using knn library %s", params.knnlib)
        self.dbi = dbi
        self.params = params
        self.backend = create_backend(params.knnlib, params.indexlength, params.fixspeed)
        self.init_index()

    def search(self):
        logging.info("Searching duplicates")
        radius = self.params.radius
        step = self.params.step
        debug = self.params.debug
        if self.empty:
            return []
        data_length = len(self.backend)

        known_duplicates = set()
        result = []
        brightness_cache = OrderedDict()
        brightness_checked = 0
        brightness_rejected = 0

        for i in tqdm(range(0, data_length, step)):
            elem_idx = self.backend.neighbors_within(i, radius)
            elem_idx.sort()
            if len(elem_idx) > 1:
                details = []

                fids = [self.fi_list[i].fid for i in elem_idx]
                fids.sort()

                pairs = list(combinations(fids, 2))

                for pair in pairs[:]:
                    if pair in known_duplicates or self.is_whitelisted(pair):
                        pairs.remove(pair)
                fids = set(i[0] for i in pairs).union(i[1] for i in pairs)

                if not fids:
                    continue

                known_fids = set()
                for item in elem_idx:
                    try:
                        fid = self.fi_list[item].fid
                        if fid not in fids or fid in known_fids:
                            continue
                        known_fids.add(fid)
                        fileinfo, frame = self.fi_list[item], self.frame_list[item]
                        if debug:
                            logging.info("%4d, %-50s: %s", fileinfo.fid, fileinfo.name[-50:], self.backend.row(item))
                        details.append([fileinfo, frame / fileinfo.fps, item])
                    except KeyboardInterrupt:
                        raise
                    except Exception:
                        logging.info("Error processing: %s, purge required?", item, exc_info=True)
                if len(details) > 1:
                    if self.params.verify_brightness:
                        accepted_pairs = set()
                        for first, second in combinations(details, 2):
                            pair = tuple(sorted((first[0].fid, second[0].fid)))
                            if pair not in pairs:
                                continue
                            score = self.brightness_score(first, second, brightness_cache)
                            brightness_checked += 1
                            if score >= self.params.brightness_correlation:
                                accepted_pairs.add(pair)
                                known_duplicates.add(pair)
                            else:
                                brightness_rejected += 1
                                if debug:
                                    logging.info(
                                        "Brightness rejected %.4f < %.4f: %s <> %s",
                                        score,
                                        self.params.brightness_correlation,
                                        first[0].name,
                                        second[0].name,
                                    )
                        result.extend(connected_components(details, accepted_pairs))
                    else:
                        known_duplicates.update(set(pairs))
                        result.append(details)
        if self.params.verify_brightness:
            logging.info(
                "Brightness verification: %d candidate pairs checked, %d rejected below %.3f",
                brightness_checked,
                brightness_rejected,
                self.params.brightness_correlation,
            )
        return result

    def brightness_score(self, first, second, cache):
        first_profile = self.brightness_segment(first, cache)
        second_profile = self.brightness_segment(second, cache)
        return brightness_correlation(first_profile, second_profile)

    def brightness_segment(self, detail, cache):
        fileinfo, _, item = detail
        if fileinfo.fid not in cache:
            raw = self.dbi.get_brightness(fileinfo.fid)
            cache[fileinfo.fid] = np.asarray(json.loads(raw), dtype=float) if raw else np.array([])
            if len(cache) > BRIGHTNESS_CACHE_SIZE:
                cache.popitem(last=False)
        else:
            cache.move_to_end(fileinfo.fid)
        brightness = cache[fileinfo.fid]
        start = self.frame_list[item]
        duration = sum(value for value in self.backend.row(item) if value > 0)
        end = min(len(brightness), start + max(1, round(duration * fileinfo.fps)))
        return brightness[start:end]

    def is_whitelisted(self, ids):
        """Return True if all pairs of filenames are whitelisted."""
        for id1, id2 in combinations(ids, 2):
            if not self.dbi.is_whitelisted(id1, id2):
                return False
        return True

    def init_index(self):
        logging.info("Loading hashes")
        self.fi_list = []
        self.frame_list = []
        items = []

        index_length = self.params.indexlength
        scene_seconds = self.params.scenelength
        ignore_start = self.params.ignore_start
        ignore_end = self.params.ignore_end
        search_excludes = normalize_excludes(self.params.search_exclude_dir)

        debug_item_no = 0
        with tqdm(self.dbi.get_file_infos()) as progress_bar:
            for fileinfo in progress_bar:
                if is_path_under(fileinfo.name, search_excludes):
                    continue
                min_frame = int(ignore_start * fileinfo.fps)
                max_frame = int((fileinfo.duration - ignore_end) * fileinfo.fps)

                frames, hashes = self.dbi.get_hashes(fileinfo.fid, min_frame, max_frame)
                if len(hashes) < 5:
                    continue

                item_count = max(0, len(hashes) - index_length)

                for i in range(item_count):
                    item = hashes[i:i + index_length]
                    total_time = 0
                    for n, value in enumerate(item):
                        if total_time > scene_seconds:
                            item[n] = 0.0
                        total_time += value

                    if self.params.debug:
                        logging.info(
                            "ITEMNO=%s | fid=%s | frame=%s | start_idx=%s | len=%s | sum=%.6f | mean=%.6f | item=%s",
                            debug_item_no,
                            fileinfo.fid,
                            frames[i],
                            i,
                            len(item),
                            sum(item),
                            (sum(item) / len(item)) if item else 0,
                            list(item),
                        )
                    debug_item_no += 1

                    items.append(item)
                    self.fi_list.append(fileinfo)
                    self.frame_list.append(frames[i])

        self.empty = not items
        if self.empty:
            logging.info("No indexable hash windows found")
            return
        self.backend.build(items)


def handle_search(dbi, params):
    idx = Index(dbi, params)
    duplicates = idx.search()

    if len(duplicates) == 0:
        logging.info("No candidates found, giving up")
        return

    log_duplicate_groups(dbi, duplicates, params.numjobs)
