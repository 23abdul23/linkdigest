# Task 7a report: Instagram image posts in video_proc and extract

Status: done. Tests: `.venv/bin/python tests/run_all.py` prints PASS.

## Changes
- `linkdigest/video_proc.py`: `process_video` routes `pr.media == "images"` to a private `_process_images`. It downloads with `download_images` into a temp dir, builds `Frame(k-1, bytes, 0, "Slide k of N")` per saved file, and removes the temp dir in a `finally`. Bundle: `media="images"`, `Transcript([], "none", None)`, duration 0, `sampled=N`, timings `probe` and `download`, no audio banner. A banner `Post has N slides; the first M were analysed.` is added when `len(pr.image_urls)` exceeds the downloaded count.
- `linkdigest/__main__.py`: `cmd_extract` on a post writes `slide-01.jpg` ..., prints `media=images slides=N`, writes no `transcript.txt`; timings and banners still print.
- `tests/test_video.py`: 5 new tests (3-image labels and cleanup, cap banner, download failure cleanup, cmd_extract on a post, cmd_extract banner).

## Not redone
The unknown-duration rule and `Frame.label` default (with its test) were already in place from Task 7 and earlier.

## Deviations
None.
