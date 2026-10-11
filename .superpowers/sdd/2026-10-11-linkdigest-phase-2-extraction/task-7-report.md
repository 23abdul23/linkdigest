# Task 7 report: video_proc.py and the extract command

Files: linkdigest/video_proc.py (new), linkdigest/__main__.py (cmd_extract, parser, dispatch, imports), tests/test_video.py (new).

Tests: wrote tests/test_video.py first (ImportError for video_proc), then implemented. The plan's five tests
plus four more: unknown duration over limit skips after download (temp dir cleaned, calls are probe+download),
over limit under LONG_VIDEO_ACTION=process banners and keeps the measured int, under limit proceeds, and
unmeasurable proceeds with duration 0. Full suite: `.venv/bin/python tests/run_all.py` all ok, PASS.

Ruling-1 handling: a shared `_apply_limit` helper; known duration is checked before download, unknown is
measured with util.probe_duration (patched on video_proc in tests) after download; None logs a warning and
continues. VideoBundle.duration is the known or measured int, else 0. VideoBundle gained `media: str = "video"`.
The image-post path (pr.media == "images") is intentionally not implemented (Task 7a).

Deviations:
- The plan's silent-Instagram test used an info dict with no `formats`; after Task 4a probe() treats that as an
  image post, so the test info now includes `formats`. The new unknown-duration tests do the same.
- Explicit `git add` paths instead of `git add -A`.
