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
Task 5: complete (commit 2cdeaf9, review clean)
Task 5: minor (deferred): ffmpeg failure reported as no-audio banner without logging stderr; TimeoutExpired (600s) uncaught in run_ffmpeg; &nbsp; stays U+00A0; real Whisper model load not run (needs model download, host may be blocked)
Task 6: implemented (commit 1e5062a), review pending
Task 6: complete (commit 1e5062a, review clean)
Task 6: minor (deferred): extract_frames does not clear stale f_*.jpg in a reused outdir (Task 7 passes a fresh temp dir); audio-only input raises RuntimeError (transient type) instead of ProcessingError; thin() n=0 ValueError; ties drop earlier frame; interval 0 ZeroDivisionError; test_cap_is_enforced checks length only
Task 7: complete (commit 61e0600, review clean)
Task 7: minor (deferred): no tests for missing-faster-whisper or frame-failure paths in process_video; measured duration truncated by int(); captions always labelled "en"
Task 7a: complete (commit 0a1eb56, review clean)
Phase 2 review: 1 real defect (parse_vtt splits a cue whose first text line is a single space; first line after a pause timestamped one cue late) - fix in progress; Phase 3 carry-ins (7 items) written into the Phase 3 plan
Phase 2 review: minor (deferred): parse_vtt drops short genuine repeats within 4 cues; thin() is O(k^3) (9.8 s at 400 frames, only with LONG_VIDEO_ACTION=process); IG reel with no formats and one thumbnail would be analysed as a 1-slide post (watch at Gate 2)
Note: tag gate-1 exists on the remote at 8a117d8 only (not fetched locally)
Phase 2 review defect fixed (commit 301a782)
Gate 2 offline: complete (HEAD 301a782); live steps blocked by cloud egress policy (www.youtube.com, instagram.com 403), awaiting user
Gate 2 live (cloud, Linux, after user opened hosts): Instagram OK. Reel DeIBJlvzu4i 14s: whisper en, 1 line, 3 of 7 frames, whisper 6.0s (incl. model load). Reel DeEvhJTSP2P 14s: whisper en, 1 line, 6 of 7 frames, 2.3s. Post DeK6kAomai9: media=images slides=7, readable 1024px slides. Long video Em9EzurouOU: Skipped 7:03 over 5:00 OK.
Gate 2 live: YouTube probe works (title, duration) but media download returns HTTP 403 from this datacenter IP on every player client (default, android_vr, mweb 403; tv, web_safari, ios need sign-in). That is the known bot-wall risk; needs cookies (YTDLP_COOKIES) or a PO token. Shorts 3SAARPxSV1U (captions) and sJOz9jMko4Q (Hindi, whisper) not yet verified live.
