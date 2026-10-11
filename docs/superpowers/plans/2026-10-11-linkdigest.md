# linkdigest Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. This index holds the shared rules. The tasks live in five phase files listed below. Read this file first, then the phase file you are on.

**Goal:** A single-worker Python service that watches a CSV of links (YouTube, Instagram reels, blogs) with optional notes, extracts what matters with a free-tier or local LLM, and emails one mobile-friendly HTML digest per link.

**Architecture:** One process, no frameworks, no async. `CsvSource` feeds a SQLite `JobQueue`. `pipeline.process_job` routes by URL kind to `video_proc` (yt-dlp, captions or faster-whisper, ffmpeg frames deduped by a Pillow dHash) or `text_proc` (requests + trafilatura), then `llm.analyze` (Gemini REST, Ollama as local option), then `render` and `mailer`. Every stage is a small module with a plain-function interface, and every network edge can be faked in tests.

**Tech Stack:** Python 3.10+, yt-dlp[default,curl-cffi], trafilatura, Pillow, requests, optional faster-whisper, system ffmpeg, node 22+ (or deno 2.3+) for yt-dlp, stdlib sqlite3/smtplib/csv.

**Spec:** `linkdigest_handoff_prompt.md` (Part 2 wins) and `research.md` (2026-10-11, replaces Phase 0). Where `research.md` section 3 deviates from the handoff spec, this plan follows `research.md`.

## Global Constraints

Copied from the spec, apply to every task:

- No paid services. Free-tier APIs or local models only.
- Allowed dependencies: `yt-dlp`, `trafilatura`, `Pillow`, `requests`, optional `faster-whisper`. Ask before adding anything else. No pytest, no vendor LLM SDKs, no python-dotenv (tiny stdlib `.env` loader). Transitive deps pulled by the allowed packages (numpy, av, curl_cffi, yt-dlp-ejs) are accepted in `research.md` section 5 item 9, pending user confirmation.
- All secrets and tunables live in `.env`. Commit `.env.example` with empty secret values. Never write a real key, password or email address into any committed file, log line or test fixture.
- `.gitignore` must contain `.env`, `*.db`, `links.csv`, `out/`, `.venv/`.
- No em dashes anywhere: code, comments, email templates, README, commit messages. (`tests/test_hygiene.py` enforces it.)
- Small readable code. No frameworks, no async, one worker process. Python 3.10+. Use a venv at `.venv`.
- Linux server, no GPU, is the target. This dev machine is Windows 11, so use `pathlib`, no shell strings, no POSIX-only calls.
- Never send real email during automated tests. All automated tests use dry run.
- HTML email: single column, max-width 600px, inline styles only (no `<style>` block), 16px system font stack, line-height 1.5, no images, `<meta name="viewport">`. HTML-escape every piece of text from the model, the page or the CSV.
- Subjects: `Digest: <title>`, `Digest skipped: <url>`, `Digest failed: <url>`, truncated to 150 chars.
- Queue outcomes: `Skipped` (no retry), `ProcessingError` (permanent, fail now), any other exception is transient (requeue until `MAX_ATTEMPTS`, then fail with `Gave up after N attempts: <reason>`). LLM HTTP backoff 10s, 20s, 40s, capped at 60s, 4 tries. Instagram login-wall or rate-limit: retry at most once, requeue to the back.
- Report honestly. Never claim something works without having run it.

## Review Focus

Input classes the spec implies but no spec test exercises. Each line names the task whose tests pin it.

1. Rows a human actually types: URL without a scheme (`youtu.be/abc`), stray spaces, a row that is not a link at all, the same link twice with different tracking params. Expected: scheme added, key is canonical, junk row marked `failed` with "Not a valid link.", duplicates processed once. Pinned in Task 2 (`normalize_url`, `canonical`) and Task 12 and Task 14 (`sync`).
2. YouTube link variants: `&list=` playlist params, `?t=30`, `/shorts/ID`, a live stream, an age-restricted video, a bare playlist URL. Expected: single video only, live and playlists rejected with a clear message, age restriction not mislabeled as a bot check. Pinned in Task 2 and Task 3.
3. A video with no audio track or no speech (screen recording, music). Expected: no crash, a banner, the digest built from frames. Pinned in Task 5 and Task 7.
4. Non-English text: a Hindi note in the CSV, a Devanagari title, a Hinglish video. Expected: notes survive CSV, prompt, HTML and the email encoding intact, and a non-English transcript gets a banner. Pinned in Task 5, Task 9 (render, mailer), Task 12.
5. A title or reason containing newlines or angle brackets. Expected: subject collapses to one line (no header injection), HTML is escaped. Pinned in Task 9.

Also pinned by design: an unrecognised Instagram download error is permanent, not retried, so Instagram is never hammered (Task 3).

## File Structure

```
linkdigest/
  __init__.py     empty
  __main__.py     argparse CLI: run, once, test, probe, extract
  config.py       load_env(), Config dataclass
  errors.py       Skipped, ProcessingError, Blocked
  util.py         log, fmt_time, slug, clip, timed, run_ffmpeg
  classify.py     classify(), normalize_url(), canonical()
  download.py     yt-dlp probe/download, error mapping
  transcript.py   VTT parser, faster-whisper
  frames.py       ffmpeg sampling, Pillow dHash, dedupe, thin
  video_proc.py   orchestrates download, transcript, frames
  text_proc.py    requests + trafilatura (+ optional Jina)
  llm.py          prompt, Gemini and Ollama clients, JSON coercion
  render.py       HTML + plain text digest and notices
  mailer.py       dry-run files, SMTP
  source_csv.py   CsvSource.rows()/mark()
  jobqueue.py     SQLite queue
  pipeline.py     process_job, sync, handle, run_cycle
tests/
  _run.py         tiny assert runner (no pytest)
  run_all.py      runs every tests/test_*.py
  fixtures.py     synthetic video, rolling VTT, fake HTTP, fake yt-dlp
  test_hygiene.py test_config.py test_classify.py test_download.py
  test_transcript.py test_frames.py test_video.py test_llm.py
  test_render_mail.py test_text.py test_pipeline.py
  test_source_csv.py test_jobqueue.py test_worker.py
  test_offline.py            (spec Test A, full cycle, Instagram goes to the back)
  test_offline_ig.py test_logging.py   (Instagram edge cases, no secrets in logs)
smoke.py          real-network smoke run (spec Test B)
smoke_ig.py       Instagram success-rate matrix
README.md  requirements.txt  requirements-whisper.txt  .env.example  .gitignore
```

Deviations from the handoff layout: `video_proc.py` is split into `download.py`, `transcript.py`, `frames.py` plus a thin orchestrator (focused files, each testable alone). The source interface is `rows()` + `mark()` instead of `new_rows()` + `mark()`, because reconcile needs to see rows that already have a status (`research.md` section 3, item 1).

## How testing works in this plan

Rule: every phase ends in a working, runnable slice and a gate. Nothing is built for more than one phase before it is run against real input.

- **Offline tests** (`python tests/run_all.py`): plain asserts, network edges faked, run after every task. They stay green forever (regression).
- **Live gate** at the end of each phase: real YouTube and Instagram links through the CLI built so far. Phases 1 and 2 need no API key. Phase 3 needs `LLM_API_KEY` (or Ollama). Email needs an app password only in Phase 5.
- **Review**: at each gate, dispatch a fresh reviewer (`superpowers:requesting-code-review`, or `/code-review`) on the phase diff, apply the findings that are real, rerun everything.
- **Patch, then move on**: a gate only passes when offline tests, the live checks and the review findings are all clean or consciously deferred in writing.
- **Stop at every gate and report to the user** with the test output, the live output and the review result. Wait for the user's OK. This matches the handoff's checkpoint rule.

Instagram and YouTube are testable from Gate 1 onward through `python -m linkdigest probe URL [--download]`, then `extract` (Gate 2), then `test` (Gate 3), then the matrix `smoke_ig.py` (Gate 6). Real yt-dlp error strings are pasted into the offline tests as they are discovered, so mapping bugs are caught offline from then on.

## What the user must supply, and when

| Gate | Needs from the user |
|---|---|
| 1 | One YouTube URL under 5 min with captions, one YouTube URL over 5 min, two or three public Instagram reel URLs (optional: `cookies.txt` exported from a throwaway logged-in browser profile) |
| 2 | One short YouTube URL with no captions; confirm `pip install -r requirements-whisper.txt` is approved (adds numpy, av) |
| 3 | `LLM_API_KEY` (Google AI Studio, free tier) in `.env`, or a running Ollama; acknowledgement of the free-tier training policy; one blog URL and one JS-heavy or Medium URL |
| 4 | The same URLs as before; no new keys |
| 5 | Gmail app password, `MAIL_TO`, a phone to check rendering |
| 6 | The Instagram reels again; decision on cookies |

## Phase files

| Phase | File | Tasks | Gate |
|---|---|---|---|
| 1 Foundation and download | `2026-10-11-linkdigest-phase-1-download.md` | 1 to 4 | Gate 1: probe and download, YouTube and Instagram, live |
| 2 Extraction | `2026-10-11-linkdigest-phase-2-extraction.md` | 5 to 7 | Gate 2: transcript and frames, live |
| 3 Digest end to end | `2026-10-11-linkdigest-phase-3-digest.md` | 8 to 11 | Gate 3: `test URL` makes an HTML digest for YouTube, Instagram and a blog |
| 4 CSV, queue, worker | `2026-10-11-linkdigest-phase-4-worker.md` | 12 to 14 | Gate 4: full offline cycle (spec Test A) plus a real CSV cycle |
| 5 Smoke, email, Instagram, release | `2026-10-11-linkdigest-phase-5-smoke-release.md` | 15 to 17 | Gate 5: smoke + real email. Gate 6: Instagram matrix, release |

Phase 4 of the handoff (Google Sheets) is not in this plan. It is built only if the user asks, behind the same `rows()`/`mark()` interface (`research.md`: `requests` + `cryptography`).

## Self-review (run when the plan was written)

- Spec coverage: input (Task 12), queue and outcomes (Tasks 13, 14), routing (Task 2), video steps 1 to 6 (Tasks 3, 5, 6, 7, 8), text steps (Task 10), Instagram mapping (Tasks 3, 16), LLM with schema (Task 8), email (Task 9), dry run (Tasks 9, 11), CLI (Tasks 4, 7, 11, 14), logging (Tasks 2, 7), tests A and B (Tasks 14, 15), phases (gates).
- Every function used later is defined earlier with the same name and signature. The interface catalog is repeated at the top of each phase file.
- No task says "add error handling" without showing it.
