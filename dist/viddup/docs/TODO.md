# TODO

## Import metadata fallback for old or unusual media

The long `/PATH/video` update scan produced 29 `Failed to insert hashes`
entries. The analysis is saved in:

- `build/failed-hash-analysis.md`
- `build/failed-hash-analysis.tsv`

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

Validation so far:

- Metadata-only recheck of the original 29 failures is saved in
  `build/failed-hash-metadata-recheck.tsv`.
- Result: 22 files have recovered metadata, 3 should hash and derive duration
  from decoded frames, 4 are clean skips.

Still planned:

- Run a full re-import of the original failed-file list on a copied database to
  confirm which files now fully hash and which still fail during frame decode.
- Keep the current hash algorithm unchanged unless a real fallback decoder path
  is explicitly tested.

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

## Media repair side tool

Keep this separate from duplicate search. `dupfind` should keep hashing and
search behavior predictable; repair operations should be explicit and write to
new files first.

Seed registry:

- `docs/PROBLEM_MEDIA.md`

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
