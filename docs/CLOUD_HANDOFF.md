# Cloud session handoff (written 2026-10-11, Phase 1 done, continue at Phase 2)

Read in this order: `docs/superpowers/plans/2026-10-11-linkdigest.md` (index, constraints, test strategy), `docs/linkdigest_handoff_prompt.md` (spec, Part 2 wins), `docs/research.md` (research and deviations), this file, then the Phase 2 plan.

## How work is tracked now
The SDD workspace is committed in this repository on purpose (user decision), under `.superpowers/sdd/<plan-name>/`. For Phase 1 it holds `progress.md` (the ledger with rulings and deferred minors), `task-N-brief.md`, `task-N-report.md` and the review diffs. Continue the same convention for each later plan file: run the skill's `scripts/sdd-workspace <plan file>` to get the directory, and keep `progress.md` there. Commit the workspace with the code so state survives any session move.

## Working agreements (from the user)
- Execute with `superpowers:subagent-driven-development`: one fresh implementer subagent per task, then a spec and quality reviewer, fix loop, a gate review per phase. Stop at each gate and report, because live checks need user input.
- NEVER add `Co-Authored-By` or any Claude/AI attribution to a commit or PR. Use explicit `git add` paths. Commit messages are plain.
- No em dash (U+2014) anywhere in project files. `tests/test_hygiene.py` enforces it.
- The deployed product runs on a Linux server with NO Claude. All analysis, including images, must use a free LLM API (Gemini free tier) or a local Ollama model. Claude is only the developer here.
- Never commit secrets. `.env` and `.venv` are not in git. Keys go in the cloud environment or `.env`, never in chat or git.
- Dev host so far was Windows (use `.venv/Scripts/python` there); on the cloud Linux host use `.venv/bin/python`. Recreate the venv: `python -m venv .venv && .venv/bin/pip install -r requirements.txt`. The user approved installing `requirements-whisper.txt` (faster-whisper, av<17, numpy). ffmpeg and node 22+ (or deno) must exist on the host; install if missing.

## State
Phase 1 (Tasks 1-4) complete, reviewed, tagged `gate-1`. Built: scaffold and assert-based test runner (`python tests/run_all.py`), `errors/util/config/classify`, `download.py` (yt-dlp probe and download, mapped errors, silent yt-dlp logger), CLI `python -m linkdigest probe URL [--download] [--verbose]`. All offline tests pass.

## Test links (also in `.env.example`; copy it to `.env`)
- TEST_YOUTUBE_URL `https://www.youtube.com/shorts/3SAARPxSV1U`: 45 s Short, English captions yes.
- TEST_YOUTUBE_NOCAPS_URL `https://www.youtube.com/shorts/sJOz9jMko4Q`: 38 s Short, Hindi, no captions (Whisper and Hindi test).
- TEST_LONG_VIDEO_URL `https://www.youtube.com/watch?v=Em9EzurouOU`: 7:03, over the 5:00 limit, must be skipped.
- TEST_INSTAGRAM_URL two reels `DeIBJlvzu4i`, `DeEvhJTSP2P`: download anonymously with audio, about 14 s each, 720x1280, no captions.
- TEST_INSTAGRAM_POST_URL `https://www.instagram.com/p/DeK6kAomai9/`: image carousel, 7 slides (the user confirmed 7 is right).
- TEST_BLOG_URL: still blank, the user must supply one (and a JS-heavy or Medium URL) before Gate 3.
- Not available yet: `LLM_API_KEY` (Gemini key from https://aistudio.google.com/apikey, needed before Gate 3 live checks) and Gmail SMTP credentials (Phase 5). Ask the user to add them to the cloud environment.

## Live findings from Gate 1 that change Phase 2 (write these into the plan before executing)
1. Instagram reels return `duration: None` from yt-dlp, so today's `probe()` raises "Could not read the video length." Fix: `Probe.duration` may be unknown for Instagram (or any kind). Allow it, download, then measure the real length with ffprobe and apply `MAX_VIDEO_SECONDS` after download (Skipped if over). Keep the pre-download skip when duration is known.
2. Emoji in a title crashes `print` on a cp1252 Windows console. Make `main()` call `sys.stdout.reconfigure(errors="replace")` (and stderr). Harmless on Linux.
3. NEW feature: Instagram image posts (carousels). yt-dlp errors "No video formats found" unless `ignore_no_formats_error=True`; then `extract_info(url, download=False)` returns a `playlist` with one entry per slide, each entry having `thumbnails` whose largest item is a downloadable JPEG (1080x1080 here, plain `requests.get` works anonymously, no cookies). Plan: probe detects a `_type == "playlist"` of image-only entries and returns `kind="images"` with the image URLs; a new `process_images` (in `video_proc.py` or a small `images.py`) downloads them in order, no transcript, no dHash dedupe, cap at a sane maximum (say 10), returns the same bundle shape with `frames` labelled "Slide k of N". Phase 3 follow-ups: LLM prompt variant for slides ("Slide k of N:" labels, extract the information shown on the slides, note still top priority), `render.py` label "Instagram post", no Timestamps section, footer "Slides: N", `smoke_ig.py` gets a post step using `TEST_INSTAGRAM_POST_URL`. No new dependency. The model reads the images at runtime (Gemini or Ollama), nobody else.
   The 7 slides of the test post are a "20 Claude Code skills" carousel (cover, five groups of four skills, a call-to-action slide).

## Deferred minor findings worth carrying (also in the Phase 1 ledger)
- `canonical()` and `classify()` assume `normalize_url()` ran first; Task 14 `sync()` must normalize, skip junk rows and mark them failed "Not a valid link.".
- `tests/_run.py` `run()` catches `Exception` only, so an argparse `SystemExit` aborts `run_all.py` without a FAIL line. Consider catching `BaseException` subclasses `SystemExit`.
- `load_env` edge cases (BOM, `KEY=# x`, `export KEY=`).
- Unknown Instagram errors are permanent by design (never hammer Instagram); a blocked reel is retried once from the back of the queue (Task 14).

## Open questions for the user
- Where will the service run (home PC or a cloud VPS)? A datacenter IP raises the YouTube bot-wall risk (cookies or a PO-token plugin may be needed). Instagram worked anonymously from the dev machine today.
- Gemini free tier may train on and human-review inputs; the user must accept that before Gate 3, or switch `LLM_PROVIDER=ollama`.

## Next steps
1. Add Phase 2 plan tasks for findings 1 to 3 (an extra task for the image path after Task 7, and amend Tasks 3/4 interfaces as needed), recording each as a Ruling in the new Phase 2 ledger.
2. Execute Phase 2 (Tasks 5 to 7), Gate 2 live checks with the links above (YouTube with captions, no-captions Hindi Short with Whisper, both reels, the image post). Gate 2 needs no API key.
3. Then Phases 3 to 5 per the plan, stopping at each gate for user input.
