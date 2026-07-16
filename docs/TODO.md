# TODO

This file contains only planned `viddup` work. Completed migrations, benchmark
history, and media-repair work belonging to the separate `vidcheck` project are
not tracked here.

## Structured media problem log

Add an optional JSONL side-channel such as `--problem-log problems.jsonl` for
files that show notable issues during import, including files that eventually
hash successfully. It should not change duplicate-search behavior and should be
usable as input for the separate `vidcheck` tool.

Candidate signals:

- metadata recovered through the ffprobe fallback;
- missing, fallback, or suspicious fps/duration values;
- audio-only or non-video inputs skipped by `VideoHashSkip`;
- decode errors, corrupt frames, or incomplete frame reads;
- unusually slow metadata probing;
- extension/container mismatch when it can be detected cheaply.

## Extended duplicate information

Add an optional `--dupinfo` report without changing the default output. It
should help distinguish a probable full-video duplicate from a repeated scene,
intro, or credits sequence.

Useful signals:

- exact matched start frame/time in each file;
- matched run length and approximate coverage of each video;
- total duration difference;
- resolution, codec/container, and file size;
- KNN distance and optional brightness correlation;
- classification such as probable full match, partial scene, or uncertain.

Choose the final text/JSONL output format after evaluating real result groups.

## Brightness verification performance

The optional brightness verifier is accurate on tested databases but adds
noticeable runtime on large indexes.

- Separate KNN candidate discovery from brightness verification so only unique
  candidate windows are checked.
- Avoid repeated JSON decoding and profile resampling while keeping memory use
  bounded for very large databases.
- Add optional reporting for rejected pairs and correlation scores for tuning.
- Re-evaluate the default 0.70 threshold when more manually classified data is
  available.

## ImageIO v3 reader migration

The copied `VIDHASH` plugin no longer uses ImageIO's deprecated registration
API. A full native ImageIO v3 rewrite remains optional and should only be done
after frame iteration, cropping, metadata, and failure behavior are compared on
the real legacy-media corpus.

## Scan filtering follow-ups

- Add repeatable `--exclude-name` for matching directory names anywhere below
  the scan root, for example `.git`, `node_modules`, and cache directories.
- Consider a clearer `--include-ext` alias for `--vidext`.
- Improve `.ts` classification so MPEG transport streams are accepted while
  TypeScript and unrelated project files remain excluded.

## Optional KNN research

- Keep `hnswlib` as the default; existing exact and approximate backends remain
  useful for comparison.
- If needed, add an explicit top-k mode for exact backends (`sklearn`, `faiss`)
  to compare with the practical top-20-plus-radius behavior of approximate
  backends.
