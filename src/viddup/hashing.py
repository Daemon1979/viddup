import json
import logging
import os
from dataclasses import dataclass
from fractions import Fraction
import subprocess

import imageio
import numpy as np
from scipy.signal import argrelmax
from tqdm import tqdm

from . import vidhash  # noqa: F401  importing registers format with imageio
from .settings import INDEX_DIST
from .utils import format_duration


DEFAULT_FALLBACK_FPS = 25.0
MAX_REASONABLE_FPS = 240.0


class VideoHashSkip(Exception):
    """Raised when a media file should be skipped without a traceback."""


@dataclass
class ProbeMetadata:
    has_video: bool
    duration: float | None = None
    fps: float | None = None
    error: str | None = None


def _parse_rate(value: str | None) -> float | None:
    if not value or value == "0/0":
        return None
    try:
        if "/" in value:
            rate = float(Fraction(value))
        else:
            rate = float(value)
    except (ValueError, ZeroDivisionError):
        return None
    if rate <= 0 or rate > MAX_REASONABLE_FPS:
        return None
    return rate


def probe_metadata(vidname: str) -> ProbeMetadata:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=codec_type,avg_frame_rate,r_frame_rate",
        "-of",
        "json",
        vidname,
    ]
    try:
        proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    except FileNotFoundError as exc:
        return ProbeMetadata(has_video=False, error=str(exc))
    except subprocess.TimeoutExpired:
        return ProbeMetadata(has_video=False, error="ffprobe timeout")

    if proc.returncode != 0:
        return ProbeMetadata(has_video=False, error=proc.stderr.strip() or f"ffprobe exit {proc.returncode}")

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return ProbeMetadata(has_video=False, error=f"ffprobe json parse failed: {exc}")

    streams = data.get("streams") or []
    video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
    if not video_streams:
        return ProbeMetadata(has_video=False)

    fps = None
    for stream in video_streams:
        fps = _parse_rate(stream.get("avg_frame_rate")) or _parse_rate(stream.get("r_frame_rate"))
        if fps:
            break

    duration = None
    raw_duration = (data.get("format") or {}).get("duration")
    if raw_duration:
        try:
            duration = float(raw_duration)
        except ValueError:
            duration = None

    return ProbeMetadata(has_video=True, duration=duration, fps=fps)


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
    try:
        video = imageio.get_reader(vidname, "vidhash")
    except Exception as exc:
        probe = probe_metadata(vidname)
        if not probe.has_video:
            reason = probe.error or "no video stream"
            raise VideoHashSkip(reason) from exc
        raise

    md = video.get_meta_data()
    fps = md["fps"]
    nframes = md["nframes"]
    if ("duration" not in md or md["duration"] > 3 * 3600) and fix:
        fix_duration(vidname)
        logging.info("Duration of %s hopefully fixed", vidname)
        return get_hashes(vidname, False)
    probe = None
    if "duration" not in md or fps <= 0:
        probe = probe_metadata(vidname)
        if not probe.has_video:
            reason = probe.error or "no video stream"
            raise VideoHashSkip(reason)

    duration = md.get("duration")
    if duration is None:
        duration = probe.duration if probe else None

    if fps <= 0:
        fps = probe.fps if probe and probe.fps else DEFAULT_FALLBACK_FPS
        logging.warning("Using fallback fps %.2f for %s", fps, vidname)

    duration_text = format_duration(duration) if duration is not None else "unknown duration"
    logging.info("Hashing %s %2.2ff/s: %s", duration_text, fps, vidname)

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

    if duration is None and fps > 0 and brightness:
        duration = len(brightness) / fps
        logging.warning("Using decoded frame count duration %s for %s", format_duration(duration), vidname)
    if duration is None:
        raise VideoHashSkip("missing video duration")

    extrema = get_extrema(brightness, INDEX_DIST, fps)
    return extrema, fps, duration, brightness


def get_extrema(hashes, min_dist: int, fps: float):
    """Compute pairs of frame number and time from previous brightness maximum."""
    order = int(min_dist * fps)
    if order < 1:
        raise VideoHashSkip(f"invalid fps for extrema extraction: {fps}")
    idx = argrelmax(np.array(hashes), order=order)[0]
    result = []
    old_idx = 0
    for i in idx:
        result.append((int(i), (i - old_idx) / fps))
        old_idx = i
    return result
