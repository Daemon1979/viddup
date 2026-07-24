from __future__ import annotations

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
import subprocess

from .db_common import MediaInfo
from .utils import format_duration


@dataclass(frozen=True)
class VideoDisplayInfo:
    codec: str = "unknown"
    width: int | None = None
    height: int | None = None

    @property
    def resolution(self) -> str:
        if self.width and self.height:
            return f"{self.width}x{self.height}"
        return "unknown"


def probe_video_display_info(path: str) -> VideoDisplayInfo:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=codec_type,codec_name,width,height:stream_disposition=attached_pic",
        "-of",
        "json",
        path,
    ]
    try:
        result = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
        if result.returncode != 0:
            return VideoDisplayInfo()
        data = json.loads(result.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return VideoDisplayInfo()

    streams = [
        stream
        for stream in data.get("streams", [])
        if stream.get("codec_type") == "video"
        and not (stream.get("disposition") or {}).get("attached_pic")
    ]
    if not streams:
        return VideoDisplayInfo()
    stream = max(
        streams,
        key=lambda item: int(item.get("width") or 0)
        * int(item.get("height") or 0),
    )
    return VideoDisplayInfo(
        codec=stream.get("codec_name") or "unknown",
        width=stream.get("width"),
        height=stream.get("height"),
    )


def format_file_size(path_or_size: str | int) -> str:
    if isinstance(path_or_size, str):
        try:
            size = os.path.getsize(path_or_size)
        except OSError:
            return "unknown"
    else:
        size = path_or_size
    if size is None:
        return "unknown"
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    value = float(size)
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            return f"{value:.2f} {unit}"
        value /= 1024.0
    return "unknown"


def log_duplicate_groups(dbi, duplicates, num_jobs: int = 4) -> None:
    fileinfos = {
        fileinfo.fid: fileinfo
        for match in duplicates
        for fileinfo, *_ in match
    }
    metadata = dbi.get_media_infos(fileinfos)
    missing = [
        fileinfo for fid, fileinfo in fileinfos.items() if fid not in metadata
    ]

    workers = max(1, min(num_jobs, 16))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        probed = list(
            zip(
                missing,
                executor.map(
                    probe_video_display_info,
                    (fileinfo.name for fileinfo in missing),
                ),
            )
        )

    new_infos = []
    for fileinfo, display in probed:
        if display.codec == "unknown" or not display.width or not display.height:
            continue
        try:
            file_size = os.path.getsize(fileinfo.name)
        except OSError:
            continue
        info = MediaInfo(
            filename_id=fileinfo.fid,
            extension=Path(fileinfo.name).suffix.lower().lstrip(".") or "unknown",
            codec=display.codec,
            width=display.width,
            height=display.height,
            file_size=file_size,
        )
        metadata[fileinfo.fid] = info
        new_infos.append(info)

    if new_infos:
        with dbi.transaction():
            dbi.insert_media_infos(new_infos)
    logging.info(
        "Media metadata cache: %d reused, %d probed, %d stored",
        len(fileinfos) - len(missing),
        len(missing),
        len(new_infos),
    )

    for match in duplicates:
        logging.info("Group of %d files found", len(match))
        for fileinfo, offset, *_ in match:
            info = metadata.get(fileinfo.fid)
            extension = (
                info.extension
                if info
                else Path(fileinfo.name).suffix.lower().lstrip(".") or "unknown"
            )
            logging.info(
                "match=%s duration=%s ext=%s codec=%s resolution=%s size=%s path=%s",
                format_duration(offset),
                format_duration(fileinfo.duration),
                extension,
                info.codec if info else "unknown",
                f"{info.width}x{info.height}" if info else "unknown",
                format_file_size(info.file_size if info else fileinfo.name),
                fileinfo.name,
            )
