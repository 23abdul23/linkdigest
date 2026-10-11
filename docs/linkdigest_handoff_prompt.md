# Handoff: `linkdigest` (continue in Claude Code)

Read this whole file before doing anything. Part 1 is context from the planning session.
Part 2 is the full build spec. Where they differ, Part 2 wins.

# PART 1: CONTEXT

## What I asked for originally
- Paste links into a watched input (options I listed: Google Sheet, Excel on OneDrive, CSV,
  or any file/document the service can watch), with an optional `notes` column per link.
- Poll every 2 minutes (configurable in `.env`). Each new row becomes a queued job; the row
  is marked done or failed after processing.
- Link types: YouTube, Instagram reels, blogs/websites and similar "content to absorb" links.
  - Video: download, preprocess (audio transcript + sampled frames, keep only unique frames),
    then a video/vision LLM (free tier or local) extracts what matters, guided by my note.
  - Text: fetch the main content, extract what matters, guided by my note.
- Linux server, no GPU, Python. Local models where the hardware allows, otherwise free-tier APIs.
- No paid services, minimal dependencies, skip or flag videos over 5 minutes, Instagram may
  fail and must fail gracefully with a clear reason in the email or sheet, secrets in env vars.
- One HTML email per job: 3-line summary, key points, timestamps for video, a section showing
  how my note was applied, readable on mobile.
- Process: plan first, then the smallest working version proven on one YouTube link and one
  blog link end to end, then Instagram.

## Decisions already made (and why)
- Language: Python. Single worker process, no frameworks, no async.
- Input: local CSV first (zero auth). Google Sheets later as Phase 4, behind the same source
  interface, because it is the better phone UX. Excel on OneDrive (Microsoft Graph) is
  possible later but not planned; don't build it unless I ask.
- Queue: SQLite (stdlib), for dedupe, retries and crash recovery.
- Video: yt-dlp for YouTube and Instagram (one code path). YouTube captions first, then
  faster-whisper `base` int8 on CPU. Frames via ffmpeg + a Pillow dHash (no OpenCV/imagehash),
  dedupe against all kept frames, cap 8.
- Web: trafilatura.
- LLM: Gemini Flash free tier over plain REST (interleaved images, JSON output). Ollama
  `qwen2.5vl:3b` as the local alternative (slow on CPU, acceptable).
- Email: smtplib with a Gmail app password.
- Dependencies: yt-dlp, trafilatura, Pillow, requests, optional faster-whisper, system ffmpeg.

## What already exists
A first build may be in this directory (from `linkdigest.zip`). If it is here:
- It implements: CSV source with atomic write-back, SQLite queue with crash recovery,
  classifier, trafilatura extraction, yt-dlp probe/download with friendly error mapping,
  rolling-VTT parser, Whisper fallback, ffmpeg + dHash frame dedupe, Gemini and Ollama clients
  with backoff, mobile HTML renderer, smtplib mailer, `run` / `once` / `test` CLI,
  `tests/test_offline.py`.
- It was only tested OFFLINE (the planning sandbox could not reach YouTube, Gemini, websites
  or SMTP). The offline test passed with network edges faked: 3 of 6 synthetic frames kept,
  rolling VTT deduped, nav/footer stripped, long video skipped, Instagram login-wall error
  written to CSV and failure email, no reprocessing on a second cycle, correct t=65s deep links.
- Nothing has been run against real YouTube, real blogs, Gemini or SMTP yet. Instagram is
  wired but completely unverified.

## Changes the existing build needs to match Part 2
Apply these if you start from the existing code:
1. Rename env `GEMINI_API_KEY` -> `LLM_API_KEY`, `GEMINI_MODEL` -> `LLM_MODEL`.
2. Add `action_items` to the LLM schema, renderer (section omitted when empty) and plain text.
3. Add `DRY_RUN` / `--dry-run` writing `.html` + `.txt` to `OUT_DIR` instead of sending.
4. Subjects become `Digest: <title>`, `Digest skipped: <url>`, `Digest failed: <url>`.
5. Add `MIN_TEXT_CHARS` (default 500, was hardcoded 200).
6. Instagram login-wall/rate-limit: retry at most once, requeued jobs go to the back.
7. Add `smoke.py` and the `TEST_*` env vars. Extend `tests/test_offline.py` to Part 2's list
   (escaping check, action items, dry-run output files).
8. Add `.gitignore`, step timings in logs, never log secrets or LLM request bodies.
9. Rename `test` CLI's `--out/--no-email` to `--dry-run`.

## Known risks to watch
- Gemini free tier: tight rate limits, model names change, inputs may be used for training.
  Verify the current free model and limits before relying on the default.
- YouTube increasingly gates captions and downloads behind bot checks. Keep yt-dlp updated;
  `YTDLP_COOKIES` is the escape hatch.
- Instagram usually needs cookies and still rate-limits. Expect partial success; report honestly.
- Whisper on CPU: measure real time for a 5-minute video and tell me.
- CSV edited while the service writes it: writes are atomic, but warn me in the README not to
  keep it open in an editor that locks or rewrites the file.

# PART 2: BUILD SPEC


## Goal
I paste links (YouTube, Instagram reels, blogs/webpages) into an input file with an optional
per-link note. A long-running service picks up new rows, extracts the useful information
(guided by my note), and emails me one HTML digest per link, so I never have to watch the
video or read the full page.

If a `linkdigest/` package already exists in this directory, read it first and improve it
rather than rewriting from scratch. Tell me what you changed.

## Environment
- Linux server, no GPU. Python 3.10+. You have shell and network access, so run real tests.
- `ffmpeg` may need installing via apt. Check before assuming.
- Use a venv at `.venv`.

## Hard constraints
- No paid services. Free-tier APIs or local models only.
- Minimal dependencies. Allowed: `yt-dlp`, `trafilatura`, `Pillow`, `requests`, optional
  `faster-whisper`. Ask me before adding anything else. No pytest, no vendor LLM SDKs,
  no python-dotenv (write a tiny stdlib `.env` loader).
- All secrets and tunables live in `.env`. Commit `.env.example` with empty values only.
  Never write a real key, password or email address into any committed file, log line or
  test fixture.
- `.gitignore` must contain `.env`, `*.db`, `links.csv`, `out/`, `.venv/`. This is deliberate:
  `links.csv` holds my personal reading list and `.env` holds secrets, while `.env.example`
  is a secret-free template meant to be committed.
- No em dashes anywhere: code, comments, email templates, README, commit messages.
- Small readable code. No frameworks, no async, one worker process.

## Configuration (.env.example, all keys present, secrets blank)

    SOURCE_CSV=./links.csv
    POLL_SECONDS=120
    DB_PATH=./jobs.db
    WORK_DIR=/tmp/linkdigest
    OUT_DIR=./out
    DRY_RUN=false

    MAX_VIDEO_SECONDS=300
    LONG_VIDEO_ACTION=skip          # skip | process
    FRAME_INTERVAL_SECONDS=2
    MAX_FRAMES=8
    WHISPER_MODEL=base
    YTDLP_COOKIES=                  # optional path to a Netscape cookies.txt

    LLM_PROVIDER=gemini             # gemini | ollama
    LLM_API_KEY=
    LLM_MODEL=gemini-2.5-flash      # verify current free-tier model name before relying on it
    OLLAMA_URL=http://localhost:11434
    OLLAMA_MODEL=qwen2.5vl:3b
    MAX_TEXT_CHARS=60000
    MIN_TEXT_CHARS=500

    SMTP_HOST=smtp.gmail.com
    SMTP_PORT=587                   # 587 STARTTLS, 465 SSL
    SMTP_USER=
    SMTP_PASS=                      # Gmail app password, not the account password
    MAIL_FROM=                      # defaults to SMTP_USER if blank
    MAIL_TO=
    NOTIFY_ON_FAILURE=true
    MAX_ATTEMPTS=3

    TEST_YOUTUBE_URL=
    TEST_YOUTUBE_NOCAPS_URL=
    TEST_BLOG_URL=
    TEST_LONG_VIDEO_URL=
    TEST_INSTAGRAM_URL=

## Input
- CSV at `SOURCE_CSV` with header `url,notes,status,detail`. Create it with the header if
  missing. A row with a url and empty status is new.
- Put the source behind a small interface (`new_rows()`, `mark(row_key, status, detail)`)
  so a Google Sheets source can be added later without touching the pipeline.
- Poll every `POLL_SECONDS`.
- Write status back to the row: `queued`, `done`, `failed`, `skipped`, with the reason in
  `detail` (max 300 chars). Writes are atomic (temp file in the same dir + `os.replace`).
- Row identity: row index + url, falling back to a url match if rows were reordered.

## Queue
- SQLite table `jobs(id, row_key UNIQUE, url, notes, status, attempts, error, created, updated)`.
- Enqueue with INSERT OR IGNORE so a row is never processed twice, including across restarts.
- On startup, reset `processing` jobs to `queued` (crash recovery).
- Outcomes:
  - `Skipped`: video over the length limit. Mark `skipped`, no retry.
  - `ProcessingError`: permanent (private/removed video, paywall, too little text, LLM
    400/401/403/404, missing key). Mark `failed` immediately, no retry.
  - Any other exception is transient (429, 5xx, timeouts, connection errors, invalid JSON
    from the LLM). Put the job back in the queue until `attempts` reaches `MAX_ATTEMPTS`,
    then mark `failed` with "Gave up after N attempts: <reason>".
- Inside a single attempt, LLM HTTP calls retry with exponential backoff: 10s, 20s, 40s,
  capped at 60s, 4 tries total.
- Instagram exception: a login-wall or rate-limit error is retried at most once, then
  marked `failed`. Never let Instagram retries delay other jobs: requeued jobs go to the
  back of the queue.
- One bad job must never crash the worker loop. Wrap each cycle in a catch-all that logs
  and continues.

## Routing
Classify by hostname after stripping `www.` and `m.`:
youtube.com, youtu.be, *.youtube.com = youtube; *instagram.com = instagram; else web.

## Processing: video (YouTube, Instagram)
1. Probe with yt-dlp (`download=False`) to get title and duration before downloading.
2. Duration > `MAX_VIDEO_SECONDS` (5 min): with `LONG_VIDEO_ACTION=skip`, mark `skipped`
   with "Video is m:ss, over the 5:00 limit." and send a skip notice email. With `process`,
   continue and show a warning banner in the digest.
3. Download at <=480p into a per-job temp dir under `WORK_DIR`, with English subtitles
   (manual and auto, VTT). If only the subtitle fetch fails, retry the download without
   subtitles. Always delete the temp dir in a `finally`.
4. Transcript: YouTube captions first. Parse VTT into `[(start_seconds, text)]`, strip tags,
   and drop lines repeated within the last 4 cues (YouTube auto-captions roll). If no
   captions exist (always true for Instagram), extract 16 kHz mono WAV with ffmpeg and run
   faster-whisper (`WHISPER_MODEL`, CPU, int8, VAD on). If faster-whisper is not installed,
   raise ProcessingError saying so.
5. Frames: ffmpeg at one frame per `FRAME_INTERVAL_SECONDS`, scaled to 512px wide. Dedupe
   with a 64-bit dHash written on Pillow (no imagehash/OpenCV): keep a frame only if its
   Hamming distance to every kept frame is > 10. Then thin evenly to `MAX_FRAMES`. Keep each
   frame's timestamp.
6. Send to the LLM: my note, title, transcript with `[m:ss]` prefixes, and each frame
   preceded by a text part `Frame at m:ss:`.

## Processing: text (blogs, webpages)
1. `trafilatura.fetch_url`, then `extract(favor_recall=True, include_tables=True,
   include_comments=False)`. Title from `extract_metadata`, falling back to the url.
2. Fetch failure or extracted text under `MIN_TEXT_CHARS`: ProcessingError "Page has
   almost no readable text. It may need JavaScript, a login, or be paywalled."
3. Truncate to `MAX_TEXT_CHARS` and add a warning banner if truncated.
4. Send my note, title and text to the LLM (no images).

## Instagram failures
Map yt-dlp errors to messages that go into both the CSV `detail` and the failure email:
- Login wall, rate limit, 401, 403, "empty media": "Instagram blocked the download (login
  wall or rate limit). Set YTDLP_COOKIES to a cookies.txt from a logged-in browser, or retry
  later."
- Private: "Video is private." Removed/unavailable: "Video is unavailable or removed."
- YouTube "Sign in to confirm" / bot check: "YouTube asked for bot verification. Run
  pip install -U yt-dlp or set YTDLP_COOKIES."
- Anything else: "Download failed: " + last line of the error, max 200 chars.

## LLM
- `LLM_PROVIDER=gemini` (default): `POST https://generativelanguage.googleapis.com/v1beta/
  models/{LLM_MODEL}:generateContent`, key in the `x-goog-api-key` header (never in the
  URL, so it can't leak into logs), `responseMimeType: application/json`, temperature 0.2,
  images as `inline_data` base64 JPEG. Check the current free-tier model name and limits
  first; note in the README that the free tier may use inputs for training.
- `LLM_PROVIDER=ollama`: `POST {OLLAMA_URL}/api/chat`, `stream: false`, `format: json`,
  images as base64. Slow on CPU is acceptable.
- Prompt rules: my note is the top-priority instruction and overrides the default focus;
  no filler or praise; nothing not present in the source; timestamps come only from
  transcript markers or frame labels.
- Required JSON, validated and coerced after stripping code fences:

      {
        "summary": ["exactly three short sentences"],
        "key_points": ["5 to 10 specific points: facts, steps, numbers, names, tools"],
        "action_items": ["concrete things I could do next; [] if none"],
        "timestamps": [{"t": 65, "point": "what happens there"}],
        "note_applied": "how my note shaped the output, or 'No note given.'"
      }

  `t` is an integer number of seconds. `timestamps` is `[]` for web content and 3 to 8
  entries for video. A string summary gets split into lines; malformed timestamp entries
  are dropped, not fatal. Unparseable JSON is a transient error.

## Email
- smtplib only. Port 587 uses STARTTLS, 465 uses SMTP_SSL. Sender `MAIL_FROM` (or
  `SMTP_USER`), recipient `MAIL_TO`, both from `.env` only.
- multipart/alternative: plain-text part first, HTML part second.
- Subjects: `Digest: <title>`, `Digest skipped: <url>`, `Digest failed: <url>`. Truncate to
  150 chars. Failure and skip emails only if `NOTIFY_ON_FAILURE=true`.
- HTML: single column, max-width 600px, inline styles only (no `<style>` block), 16px system
  font stack, line-height 1.5, no images, no decoration, `<meta name="viewport">`.
  Must be comfortable to read on a phone. Sections in this order:
  1. Title, link to the source, type, duration (video)
  2. Warning banners, if any
  3. Summary (the 3 lines)
  4. Key points (bulleted)
  5. Action items (bulleted; omit the section if empty)
  6. Timestamps (video only); for YouTube each time links to the video with `t=<sec>s`
     added to the existing query string
  7. How your note was applied: my note quoted, then `note_applied`
  8. Small grey footer: model used, transcript source, frames kept vs sampled
- HTML-escape every piece of text that came from the model, the page, or the CSV.
- Failure/skip email: heading "Failed" or "Skipped", the url, the reason. Nothing else.

## Dry run
`DRY_RUN=true` or `--dry-run` writes each email to `OUT_DIR/<job-id>-<slug>.html` (and a
`.txt` for the plain part) instead of sending. CSV and queue still update normally. All
automated tests use dry run. Never send real email during tests.

## CLI

    python -m linkdigest run                    # poll forever
    python -m linkdigest once                   # poll once, drain queue, exit
    python -m linkdigest test URL [NOTE] [--dry-run]

`test` processes one URL directly, bypassing CSV and queue.

## Logging
stdlib logging at INFO: queued, processing, done, failed/skipped with reason, step timings
(download, transcript, frames, LLM). Full tracebacks only for transient errors. Never log
secrets or full LLM request bodies.

## File layout (propose changes before coding)

    linkdigest/
      __init__.py  __main__.py  config.py  source_csv.py  jobqueue.py  classify.py
      text_proc.py  video_proc.py  llm.py  render.py  mailer.py  pipeline.py
    tests/test_offline.py
    smoke.py
    README.md  requirements.txt  .env.example  .gitignore

## Verification

### A. Offline test: `python tests/test_offline.py` (plain asserts, no pytest)
Fake only the network edges: yt-dlp probe/download, page fetch, LLM HTTP, SMTP. Use an
ffmpeg-generated synthetic video with 3 visually distinct 4-second scenes and a hand-written
rolling VTT. Pass criteria, all must hold:
- classify() is correct for youtube.com, youtu.be, m.youtube.com, instagram.com/reel, a blog
- frames kept is at least 2 and fewer than frames sampled
- rolling VTT yields each line once with correct start seconds
- web extraction keeps the article and drops nav/footer text
- a thin page raises ProcessingError
- one cycle over a CSV with a YouTube row, a blog row, a 15-minute video row, a failing
  Instagram row and an already-done row produces: 2 done, 1 skipped, 1 failed with the
  Instagram message, the done row untouched, and 4 emails in OUT_DIR
- a second cycle produces no new emails
- the YouTube email contains the note, a `t=65s` deep link and the time `1:05`
- the blog email has no Timestamps section
- no email contains an em dash, and model text containing `<script>` is escaped
Prints `PASS` or the first failing assertion.

### B. Real smoke run: `python smoke.py`
Reads the TEST_* urls from `.env`. If any required url is blank, stop and ask me for it.
Pick-criteria to tell me if I ask: YouTube under 5 minutes with captions; a second short
video with no captions; a plain article page (not a SPA, not paywalled); any video over
5 minutes; one public Instagram reel.
Uses a temp CSV, temp DB and DRY_RUN, and prints PASS/FAIL per step with timings:
1. Blog: status `done`, HTML has a 3-line summary and at least 5 key points, no
   Timestamps section, note section present.
2. YouTube with captions, note "only the commands": status `done`, transcript source is
   captions, 3 to 8 timestamps each within the video duration, deep links work, the
   note_applied text references the note.
3. YouTube without captions: status `done`, transcript source is whisper. Report wall-clock
   time for the Whisper step on this CPU.
4. Long video: status `skipped`, nothing downloaded (probe only), skip notice written.
5. Instagram (runs in Phase 3 only): either `done`, or `failed` with one of the mapped
   messages. A raw traceback in `detail` is a FAIL.
6. Rerun the same CSV: no new output files.
Finally send one real email (blog digest only) with `test TEST_BLOG_URL` and ask me to
confirm it rendered correctly on my phone.

## Phases: stop and report at each checkpoint
- Phase 0: inspect the environment and any existing code, then give me the file layout and
  deviations from this spec with reasons. Wait for my OK.
- Phase 1: build everything except Instagram hardening. Show Test A output. Wait.
- Phase 2: run smoke steps 1 to 4 and 6, show the PASS/FAIL output, and attach the YouTube
  and blog HTML from OUT_DIR. Fix failures and rerun. Then the one real email. Wait.
- Phase 3: Instagram. Run step 5 with and without YTDLP_COOKIES on 2 or 3 reels. Report the
  success rate honestly. Confirm failures never crash or block the worker.
- Phase 4 (only if I ask): Google Sheets source via service account and the Sheets REST API
  with `requests`, behind the same source interface.

## Rules for you
- Run things for real; never claim something works without having executed it.
- If a free tier, model name or library behaves differently from this spec, say so and
  adapt. Don't silently work around it.
- Keep reports brief and honest about limitations.
