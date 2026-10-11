# Task 6 review (commit 1e5062a)

Verdict: clean. No blocking defects. `.venv/bin/python tests/run_all.py` passes (PASS, incl. test_frames and test_hygiene).
Commit message is plain ("feat: ffmpeg frame sampling with Pillow dHash dedupe"), no attribution. No em dash, no secrets (hygiene tests pass).

## Verified correct
- dhash: 9x8 grid, L-mode, LANCZOS, 64 bits, row-major MSB-first, deterministic; get_flattened_data/getdata fallback fine on Pillow 12.
- hamming: popcount of xor, correct.
- thin: cap enforced (loop runs until len <= n), empty list and n>=len are no-ops, n=1 works, drops the frame with the smallest nearest-neighbour distance (keeps most distinct). Ties are deterministic (earliest index dropped).
- extract_frames: fps=1/interval formatted .6f (2.5 -> 0.400000, 3 -> 0.333333, 20 -> 0.050000 all gave correct counts in experiments); scale=512:-2; t = i*interval; dedupe is against ALL kept frames (not only last); frames decoded one at a time via BytesIO and context manager, JPEG bytes retained only (memory ok at 12-ish kept, all sampled bytes held in `every` but small at 512 px).
- Short video: 1 s and interval>duration give 1 sampled / 1 kept (no crash). 2 sampled never triggers the fallback (needs >=3), matching spec.
- Fallback _evenly(every, 3): always 3 distinct indices for len>=3 (len 3 -> 0,1,2; 4 -> 0,2,3; 5 -> 0,2,4); no duplicates, no IndexError.
- Frame.label defaults to "" and is positional 4th field, per Amendments. Tests are deterministic (seeded) and non-vacuous (assert exact 3 kept, exact sampled count, t values, JPEG magic, thin victim identity, cap).

## Minors (none block)
1. frames.py extract_frames: output dir reuse leaves stale `f_*.jpg`. Reproduced: run on 12 s video then 2 s video in same dir gives sampled=6 not 1, wrong frames/timestamps. Harmless only if the caller (Task 7 video_proc) always passes a fresh temp dir; consider deleting existing `f_*.jpg` before ffmpeg, or document.
2. frames.py extract_frames: a file with no video stream (audio-only .m4a) raises `RuntimeError("ffmpeg failed: ... Output file does not contain any stream")`, which is the transient type, so the queue may retry a permanent failure. Task 7 should check for a video stream or map this to ProcessingError. Not in Task 6 spec.
3. frames.py:`thin`: n=0 with 1 frame left raises ValueError (min of empty); n<=0 is a nonsensical MAX_FRAMES but could be guarded (`max(n,1)` or early return).
4. frames.py:`thin`: ties drop the earlier frame (e.g. t=0 title frame) instead of the later duplicate; cosmetic, deterministic.
5. frames.py:`extract_frames`: `frame_interval_seconds=0` gives ZeroDivisionError; config validation concern, not this module.
6. Fallback replaces 1 or 2 dHash-kept frames with 3 evenly spaced ones, which may not include the kept ones; matches the research note ("fall back to even sampling"), acceptable.
7. test_cap_is_enforced uses hashes (1<<i)-1; passes but only asserts length, not which frames survive (covered by the 3-frame test).
