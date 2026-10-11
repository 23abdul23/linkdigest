# Task 7a review and Phase 2 gate review

Reviewed commit 0a1eb56 and the Phase 2 diff via git show/diff and a clean worktree at 0a1eb56.
Note: the tag `gate-1` does not exist in this repo (`git tag` is empty). The base used is d46d858
(the commit just before efac8fa, the first Phase 2 commit). If gate-1 should point elsewhere, say so.

## Verdict

Part A: APPROVED. Part B: PASS with one real (low severity) defect and minors. No blocker for Gate 2.

## Checks run

- `tests/run_all.py` in a clean worktree at 0a1eb56: all ok, final line PASS (worktree removed).
- Em dash (U+2014) in linkdigest/ and tests/ source: none.
- Secrets: hygiene tests ok; no key-shaped strings in the diff.
- Commit messages d46d858..HEAD (10 commits): no Co-Authored-By, Claude or "Generated" text.
- Scope: linkdigest/, tests/, .env.example, the Phase 2 plan, a 4-line carry-in note in the Phase 3 plan,
  and .superpowers/sdd/ ledger files. Nothing outside Phase 2 scope.

## Part A: Task 7a conformance

All required behaviours present and tested: `Frame.label` default; Ruling 1 (download first, then
`probe_duration`, same limit and message, unmeasurable logs a warning and continues, `duration` is the
measured int or 0, temp dir removed on the Skipped path via try/finally); `_process_images` bundle
(`media="images"`, empty `Transcript([], "none", None)`, duration 0, `sampled=N`, labels `Slide k of N`,
no dedupe, no audio banner, cap banner `Post has N slides; the first M were analysed.`, timings probe and
download, temp dir removed); `cmd_extract` writes `slide-NN.jpg`, prints `media=images slides=N`, no
transcript.txt. Tests for each listed case exist.

Minors (not defects):
- Label N is `len(paths)` (the capped count), so a capped post reads "Slide 1 of 10" while the banner says
  the post has 12. Spec is ambiguous; consistent with "first M analysed". Fine.
- Per the Task 4a rule, an Instagram result with no `formats` and one thumbnail is claimed as a one-slide
  post. A reel where yt-dlp finds no formats (login or region wall that does not raise) would be analysed
  as a single cover image with no warning. Spec-sanctioned; worth watching at Gate 2 Step 4.
- `_process_images` and `process_video` do not catch `Skipped`; not applicable to images. Fine.

## Part B: Gate 2 Step 7 brief

### Real defect (low severity)

1. `linkdigest/transcript.py:25` `parse_vtt` splits blocks on `\n\s*\n`. A YouTube cue whose first text line
   is a single space (which real auto-caption files emit for the first cue and after every speech gap):
   ```
   00:00:00.160 --> 00:00:02.230 align:start position:0%
    
   hello<00:00:00.640><c> everyone</c>
   ```
   is split into a timestamp-only block and a text-only block (`\s*` matches the whitespace-only line).
   Verified: with that input the line "hello everyone today" gets start 2.23 instead of 0.16, because the text
   is only recovered from the next cue's repeated line. Effect: the first line after each pause is stamped
   one cue late (about 2 to 5 s), which matters for Phase 3 YouTube deep links; if such a cue is the last in
   the file its text is lost. Fix: split on `\n{2,}` after normalising whitespace-only lines to empty
   (`re.sub(r"\n[ \t]+(?=\n)", "\n", text)` before the split) and add a test with a leading `" "` line.
   The existing fixture does not include this shape, which is why tests are green.

### Minors

- `parse_vtt` drops any line already seen in the last 4 cues, so a genuine short repeat ("no no", "yes")
  within about 4 cues is lost (verified). Acceptable trade for rolling captions.
- Captions transcripts are labelled `language="en"` unconditionally (`video_proc.py`); fine while only
  English subs are requested.
- `thin` is O(k^3): 150 kept frames takes 0.6 s, 400 takes 9.8 s (random hashes). Default 300 s limit caps
  sampled at 150, so fine; only `LONG_VIDEO_ACTION=process` on long videos with many distinct frames would
  be slow. Not a defect at current defaults.
- dHash: correct 9x8 right-neighbour comparison, 64 bits. Dedupe compares against all kept frames (a
  revisited slide is dropped, intended). All-black frames hash to 0 and dedupe together. `_evenly` fallback
  to 3 frames covers talking heads.
- Memory: `extract_frames` holds all sampled JPEGs (512 px, q4, tens of KB each) as bytes until dedupe, then
  only kept ones. 150 frames is a few MB. Whisper `_load_wav` makes a float32 array (64 KB per second of
  audio, so about 19 MB at the 300 s limit). Fine. Would only grow with `process` mode on long videos.

### Verified OK

- Temp dir: both `process_video` and `_process_images` use try/finally with rmtree around every step, including
  Skipped after download, download failure, Whisper-not-installed ProcessingError, and frame failure.
  `cmd_probe` likewise.
- No audio stream: ffmpeg failure is caught, banner added, empty `Transcript(..., "none")`; video still
  yields frames. Tested.
- No video stream (audio-only file, reproduced): `extract_frames` raises RuntimeError, caught in
  `process_video`, banner "Frames could not be read", `sampled=0`; if the transcript is also empty
  ProcessingError "Nothing to analyse". Good.
- Video shorter than the sampling interval (1 s clip): one frame sampled, no crash.
- Rolling captions beyond the fixture (realistic YouTube shape with inline timestamps, `<c>` tags, 10 ms
  filler cues, align/position settings): each line emitted once, apart from the leading-space issue above.

## Cross-task consistency with the Phase 3 plan

Probe, Frame and VideoBundle fields match what the Phase 3 plan consumes (`b.title`, `b.transcript.lines`,
`b.frames`, `b.duration`, `b.banners`, `b.transcript.source`, `b.sampled`, `b.timings`). The Phase 3 plan
already carries in the image-post work (4-line section near the top). Nothing breaks on duration 0 or
`media="images"` structurally: `render_digest` uses `if d.duration`, `parse_result` uses `duration and ...`.
Behavioural gaps Phase 3 must handle (code samples in the plan as written would get these wrong):

1. `build_parts` (Phase 3 plan ~line 279): must branch on `b.media == "images"`: no "Source: video /
   Transcript: (no speech detected)" text, interleave `f.label` ("Slide k of N:") instead of
   `Frame at {fmt_time(f.t)}` (t is the slide index, not seconds). `process_job` must pass `media` (or the
   labels) through to `analyze`.
2. `parse_result` with `duration=0`: the upper bound is skipped (`duration and t > duration`), so any
   hallucinated timestamp is accepted. For images, force `timestamps = []` and do not render "Timestamps".
3. Rubric text (lines ~268 to 269) says timestamps come from transcript markers or "Frame at m:ss" labels;
   needs a slide variant with no timestamp request.
4. `render_digest` footer prints `Transcript: none | Frames kept: N of N sampled` for posts; replace with
   `Slides: N`. Kind label should be "Instagram post". Meta line already omits duration when 0.
5. `Digest` has no `media` field; add one (or pass `kind` label) so render and parse_result can tell posts
   from reels. `kind` alone is "instagram" for both.
6. Phase 3 `extract` subparser (line ~1316, `parents=[common]`) redefines the parser built in Task 7; keep
   `cmd_extract`'s images branch intact.
7. `Skipped` from `process_video` (long video, now also raised after download for unknown-duration videos)
   must be handled by the job runner as before; `Probe.duration` may be `None` only inside `process_video`,
   bundles always carry an int.
