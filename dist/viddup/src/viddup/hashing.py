import logging
import os
import subprocess

import imageio
import numpy as np
from scipy.signal import argrelmax
from tqdm import tqdm

from . import vidhash  # noqa: F401  importing registers format with imageio
from .settings import INDEX_DIST
from .utils import format_duration


def fix_duration(vidname: str) -> None:
    wd = os.path.dirname(vidname)
    if os.access(vidname, os.W_OK) and os.access(wd, os.W_OK):
        with open(vidname, "rb") as f:
            os.remove(vidname)
            proc = subprocess.Popen(
                ["ffmpeg", "-i", "pipe:", "-vcodec", "copy", "-acodec", "copy", vidname],
                stdin=f,
            )
            proc.wait()
    else:
        logging.warning("target %s is not writable, giving up", vidname)


def get_hashes(vidname: str, fix: bool = True):
    video = imageio.get_reader(vidname, "vidhash")
    md = video.get_meta_data()
    fps = md["fps"]
    nframes = md["nframes"]
    if ("duration" not in md or md["duration"] > 3 * 3600) and fix:
        fix_duration(vidname)
        logging.info("Duration of %s hopefully fixed", vidname)
        return get_hashes(vidname, False)
    duration = md["duration"]
    logging.info("Hashing %s %2.2ff/s: %s", format_duration(duration), fps, vidname)

    brightness = []
    try:
        with tqdm(video.iter_data(), total=nframes, leave=False) as pb:
            for frame in pb:
                brightness.append(frame.mean())
    except KeyboardInterrupt:
        raise
    except imageio.core.format.CannotReadFrameError:
        pass
    except Exception as e:
        logging.warning("Error processing video: %s", e, exc_info=True)

    extrema = get_extrema(brightness, INDEX_DIST, fps)
    return extrema, fps, duration, brightness


def get_extrema(hashes, min_dist: int, fps: float):
    """Compute pairs of frame number and time from previous brightness maximum."""
    order = int(min_dist * fps)
    idx = argrelmax(np.array(hashes), order=order)[0]
    result = []
    old_idx = 0
    for i in idx:
        result.append((int(i), (i - old_idx) / fps))
        old_idx = i
    return result
