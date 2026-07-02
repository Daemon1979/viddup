import logging
from itertools import combinations

from tqdm import tqdm

from .knn import create_backend
from .utils import format_duration


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

                known_duplicates.update(set(pairs))

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
                        details.append([fileinfo, frame / fileinfo.fps])
                    except KeyboardInterrupt:
                        raise
                    except Exception:
                        logging.info("Error processing: %s, purge required?", item, exc_info=True)
                if len(details) > 1:
                    result.append(details)
        return result

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

        debug_item_no = 0
        with tqdm(self.dbi.get_file_infos()) as progress_bar:
            for fileinfo in progress_bar:
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

    for match in duplicates:
        logging.info("Group of %d files found", len(match))
        for fileinfo, offset in match:
            logging.info("ffplay -ss %s '%s'", format_duration(offset), fileinfo.name)
