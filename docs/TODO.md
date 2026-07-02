# TODO

## Import metadata fallback for old or unusual media

Large real-world media scans can produce `Failed to insert hashes` entries for
old, unusual, audio-only, or corrupt files.

Most failures were not obviously bad files. The main classes were:

- `fps=0` from old WMV/ASF metadata, leading to `argrelmax(order=0)`.
- missing `duration` in imageio/ffmpeg metadata.
- `VIDHASH` rejecting some readable FLV/ASF inputs by extension or format gate.
- audio-only `.mp4` files with no video stream.
- genuinely corrupt/tiny files.
- one old interlaced WMV3 file that ffmpeg cannot decode.

Implemented:

- Added an `ffprobe -of json` metadata fallback for missing duration/fps.
- Added clean `VideoHashSkip` handling so audio-only/corrupt files are logged
  without traceback noise.
- Reject `fps <= 0` before `argrelmax`; recover via ffprobe when possible and
  use a conservative 25 fps fallback when ffmpeg reports only unusable timebase
  values such as `1000/1` or `90000/1`.
- If duration is missing but frames can be decoded and fps is known, compute
  duration from decoded frame count.
- Expanded the `VIDHASH` plugin extension gate to include `.asf`, `.flv`, and
  `.ts`.
- Increased the ffmpeg metadata-header wait from 4 seconds to 30 seconds for
  large or slow-to-probe files.

Still planned:

- Keep the current hash algorithm unchanged unless a real fallback decoder path
  is explicitly tested.
- Add an optional structured problem log, for example
  `--problem-log problems.jsonl`, that records files with notable media issues
  seen during scan/import even when hashing eventually succeeds. This should be
  a side-channel for diagnostics and future `vidcheck` input, not a change to
  duplicate-search behavior.

Problem-log candidate signals:

- metadata recovered through fallback instead of the normal reader path;
- missing or suspicious fps/duration values;
- audio-only/non-video inputs skipped by `VideoHashSkip`;
- decode errors, corrupt frames, or files that only hash after fallback logic;
- unusually slow metadata probe or header read;
- extension/container mismatch that may be worth checking later.

## KNN backend expansion

The default priority remains:

1. `hnswlib`
2. `cyflann`
3. `annoy`

Implemented explicit backends:

- `sklearn.neighbors.NearestNeighbors` as an exact baseline.
- `faiss` for larger vector sets and benchmark comparison.
- `pynndescent` for approximate-neighbor comparison.

Follow-up:

- Real DB benchmark on 2026-07-02 showed that corrected `hnswlib` radius
  semantics match `sklearn`, `faiss`, `annoy`, and `pynndescent` output while
  remaining the fastest backend in this environment.
- Optional future benchmark: add an explicit top-k search mode for exact
  backends (`sklearn`, `faiss`) to compare them against the practical
  top-20-plus-radius behavior used by `hnswlib`, `annoy`, and `pynndescent`.

## ImageIO plugin migration

The `VIDHASH` format registration was migrated away from ImageIO's deprecated
`FormatManager.add_format` API on 2026-07-02. Tests now run without ImageIO
deprecation warnings.

Follow-up:

- Keep the current copied ffmpeg-derived plugin while stabilizing the project
  structure.
- Later review whether the whole `VIDHASH` reader should be rewritten as a
  native ImageIO v3 plugin. Do this only if frame iteration and metadata
  behavior can be verified against real files.

## Extended duplicate information

Planned CLI option:

- `--dupinfo`

Goal: add an optional extended report for duplicate groups without changing the
default duplicate-search output.

The report should estimate how likely each found duplicate pair/group is to be a
full video-stream match versus only a repeated fragment inside different videos.

Useful signals:

- matched fragment start time in each file, for example one file starts around
  `00:00:30` and another around `00:00:31`;
- matched fragment duration or matched hash-run length;
- total video duration comparison, with a small tolerance for trimmed starts or
  ends;
- resolution, container/codec metadata, and file size;
- whether the matched fragment covers most of both videos.

Likely classifications:

- probable full video match: near-equal duration, near-equal duplicate start,
  and the matched video sequence covers most of both files;
- partial scene match: the same fragment appears at very different offsets, for
  example one file around `00:10:00` and another around `00:30:00`;
- uncertain: metadata or match coverage is insufficient.

The exact output format should be chosen during implementation after checking
real duplicate groups by eye.

## Media repair side tool

Keep this separate from duplicate search. `dupfind` should keep hashing and
search behavior predictable; repair operations should be explicit and write to
new files first.

The future media-check tool should scan paths directly and may optionally ingest
`dupfind --problem-log` output as one input.

Planned repair tool capabilities:

- Read a list/registry of problematic media files with path, ffprobe metadata,
  original failure class, and suggested handling.
- Classify files into:
  - audio-only/non-video: move/exclude/rename, no video repair.
  - tiny/truncated/corrupt: verify source or restore from backup.
  - container/metadata issue: try remux to a new file with `ffmpeg -i input -c copy output`.
  - codec/decoder issue: optionally transcode to a modern container/codecs.
- Always write repaired output to a separate path first.
- Run `ffprobe` before and after repair and save a report.
- Never replace/delete originals without an explicit destructive flag.
- Optionally generate shell commands first in dry-run mode.

## Scan filtering

Implemented:

- repeatable `--exclude-dir`.
- `.d.ts` skip to avoid TypeScript declaration files matching `.ts`.
- repeatable `--search-exclude-dir` to ignore already-hashed directories during
  duplicate search without deleting them from the database.
- database inspection with `--list-db-files`, `--list-db-dirs`, and
  `--list-db-path`.
- database path removal with `--delete-db-path`, dry-run by default and
  destructive only with `--delete`.

Potential follow-ups:

- `--exclude-name` for names such as `node_modules`, `.git`, cache directories.
- cleaner `--include-ext` alias for `--vidext`.
- better `.ts` handling for transport streams versus non-video project files.
