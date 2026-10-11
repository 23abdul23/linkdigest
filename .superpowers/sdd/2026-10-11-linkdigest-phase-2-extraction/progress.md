# SDD ledger - plan: docs/superpowers/plans/2026-10-11-linkdigest-phase-2-extraction.md
Index/spec: docs/superpowers/plans/2026-10-11-linkdigest.md ; docs/linkdigest_handoff_prompt.md + docs/research.md ; docs/CLOUD_HANDOFF.md
Branch: feat/linkdigest-flhm4d (cloud), Phase 1 tagged gate-1 (d46d858). Host: Linux cloud, use .venv/bin/python. ffmpeg, ffprobe, node 22 present. requirements-whisper.txt installed (user approved).

## Preflight scan (Phase 2: Tasks 4a, 5, 6, 7, 7a)
| pair | produces vs consumes | finding |
| 4a->5/6/7/7a | Probe(media,image_urls), probe_duration, Frame.label, Config.max_slides | consistent, defined in plan Amendments |
| 5->7 | Transcript, transcribe_audio | consistent |
| 6->7a | Frame label default keeps Task 6 tests valid | consistent |
| 7->7a | process_video routes images after probe; duration None path | consistent |
Ruling: probe() accepts unknown duration (Instagram reels); measure with ffprobe after download, then apply MAX_VIDEO_SECONDS; unmeasurable continues - cost: a long Instagram video is downloaded before being skipped
Ruling: main() sets stdout/stderr errors="replace" - cost: none
Ruling: NEW Instagram image-post path (Task 4a probe/download_images, Task 7a bundle). No transcript, no dedupe, label "Slide k of N", MAX_SLIDES=10; Phase 3 gets slide prompt, render label, footer - cost: one extra task plus Phase 3 follow-ups
Ruling: no Co-Authored-By / Claude attribution in commits (user hard rule overrides the harness default) - cost: none
Ruling: cloud egress policy denies www.youtube.com and instagram.com (proxy 403), so live Gate 2 checks cannot run until the user allows those hosts or runs locally - cost: Gate 2 live steps wait on the user
Task 4a: complete (commit ef73b98, review clean)
Task 4a: minor (deferred): _image_post None entry AttributeError; _fetch_image unmapped RequestException subclasses (InvalidURL, ChunkedEncodingError); max_slides=0 silent empty; IG video with no formats but a thumbnail becomes a 1-image post; "several videos" msg on single-entry video playlist; entry["url"] fallback and stderr reconfigure untested
Task 5: implemented (commit 2cdeaf9), review pending
