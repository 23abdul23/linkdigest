# Task 7 review (commit 61e0600)

Verdict: clean. No real defects.

Verified from a clean worktree of 61e0600: tests/run_all.py prints PASS (all 9 test_video tests ok).

Checked and correct
- Known duration over limit: Skipped raised in process_video before mkdtemp and download (video_proc.py, `_apply_limit` call after probe); test asserts calls == ["probe"].
- Unknown duration (None): downloads, then probe_duration(dl.video); int() of the measured value; limit applied inside the try, so Skipped passes through `finally` and the temp dir is removed (tested). Unmeasurable: warning, continue, duration 0 (tested).
- Boundary: `seconds <= max` proceeds, so equal to limit is allowed. Message "Video is 15:00, over the 5:00 limit." matches spec. Process mode appends banner and does not raise.
- Temp dir cleanup: everything after mkdtemp sits in try/finally, so download failure, Skipped after download, transcribe_audio ProcessingError (missing faster-whisper), ProcessingError from extract_frames (e.g. ffmpeg missing) all clean up. Only the "nothing to analyse" raise is after finally, which is fine (nothing left to clean).
- extract_frames RuntimeError is caught (warning, empty frames, banner); ProcessingError is not caught and propagates. Matches spec.
- Transcript: empty parse_vtt result falls through to whisper; "en" for captions as in the plan.
- "Nothing to analyse" rule matches the plan.
- cmd_extract matches the plan: invalid link returns 1, web returns 1, Skipped prints and returns 0, other exceptions print type and message and return 1; output dir extract-<slug>, frame-NNNNs.jpg, transcript.txt, summary prints, banners. Parser entry and dispatch present.
- No em dash, no secrets in the diff. Commit message is plain "feat: video_proc and the extract command" with no attribution.

Minors (no action needed)
1. No test for the missing-faster-whisper path through process_video or for the frame-failure path (RuntimeError caught vs ProcessingError propagating) with temp dir cleanup. Code is correct by inspection; the transcript.py and frames tests cover the pieces.
2. Measured duration is truncated with int(), so a file measuring 300.9s against a 300s limit is not skipped. Consistent with how probe() truncates known durations; negligible.
3. Captions are labelled language "en" regardless of actual caption language (plan-specified assumption; yt-dlp is not asked for a language here).
4. pr.media == "images" is not handled in process_video (would try to download and fail); intentional, deferred to Task 7a per the report.
5. The silent-Instagram test info was adjusted to include formats (reported as a deviation); reasonable given probe() now routes formats-less Instagram results to the image path.
6. The commit also contains task-7-report.md under .superpowers; expected for this workflow.
