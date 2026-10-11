# linkdigest research (replaces Phase 0)

Date: 2026-10-11. Research only, no project code touched. Full per-agent reports (longer, with commands and raw numbers) are in the session scratchpad `reports\` folder. Anything tagged UNVERIFIED was not measured or not backed by a dated source.

## 1. Machine and network

| Item | Value |
|---|---|
| CPU | Intel Core i5-10300H, 4 cores / 8 threads, 2.5 GHz |
| RAM | 15.8 GB |
| Free disk | 23.6 GB (C:) |
| OS | Windows 11 Home 10.0.26200 (target is Linux, no GPU; Windows numbers are a rough guide) |
| Python | 3.12.10 |
| ffmpeg | 2024-05-27 gyan full build |
| Other | node 22.13 on PATH; global yt-dlp 2024.05.26 is too old and fails on YouTube |
| youtube.com | reachable (HTTP 200) |
| instagram.com | reachable (HTTP 200) |
| generativelanguage.googleapis.com | reachable (HTTP 404 on the bare root, which is normal) |

Test clip for all timings: a 4:30 (269 s) English YouTube code tutorial, 640x360, with auto captions. Agents ran concurrently, so each CPU timing took a lock and ran alone. Hindi/Hinglish audio was NOT tested anywhere.

## 2. Summary table

| Component | Pick | Fallback | Verdict | Risk |
|---|---|---|---|---|
| Input | CSV, stdlib only, re-read before every write | Sheets via `requests` + `cryptography` (Phase 4) | yes | Windows editor lock blocks write-back; Linux user save clobbers status |
| Queue | stdlib sqlite3, WAL, synchronous=FULL | journal_mode=DELETE | yes | DB and CSV drift if write order reversed |
| Download | yt-dlp 2026.08.19 `[default,curl-cffi]` + node 22 or deno 2.3 | PO-token plugin / cookies / residential IP | yes with risk | YouTube bot wall on datacenter IPs; Instagram anonymous is flaky |
| Transcription | faster-whisper 1.2.1 `base` int8 beam 1 | `small`; Gemini 3.5 Transcribe for Hindi/Hinglish | yes with risk | `av` version crash; Hinglish quality |
| Frames | ffmpeg fps=1/2, 512 wide, Pillow dHash threshold 10, cap raised to 12 | fps=1/4 or even sampling | yes with risk | cap drops slides on slide-heavy videos |
| LLM (web path and video) | Gemini `gemini-3.6-flash` free | `gemini-3.5-flash-lite`, then Groq `openai/gpt-oss-120b` (text only) | yes with risk | free tier trains on and human-reviews inputs; limits unpublished |
| LLM (local) | Ollama `gemma4:e4b` | `qwen3-vl:4b` | yes with risk | speed on CPU not measured |
| Embeddings | none | multilingual-e5-small int8 if search is added | no role in MVP | none |
| Web extraction | trafilatura 2.3.1, fetched with `requests` | Jina Reader (opt-in), then ProcessingError | yes with risk | Medium and Cloudflare block datacenter IPs |
| Email | Gmail SMTP + app password, stdlib | Brevo free SMTP relay | yes with risk | app password revoked; self-send skips Inbox |

## 3. Deviations from the handoff spec

1. Row identity: key by normalized URL only, not row index + URL. A reorder would otherwise create a new job and reprocess. Add `seq` and `csv_synced` columns. Evidence: queue and input reports, sqlite.org/wal.html.
2. CSV write path: read `utf-8-sig`, re-read the file before every `mark()`, retry `os.replace` on PermissionError, SQLite holds authoritative status and reconciles each poll. Measured: any open handle on Windows blocks `os.replace`.
3. Default `LLM_MODEL` becomes `gemini-3.6-flash`, add `LLM_FALLBACK_MODEL=gemini-3.5-flash-lite`. `gemini-2.5-flash` still works but 2.0 was shut down 2026-06-01. Source: ai.google.dev/gemini-api/docs/pricing (2026-10-09).
4. `OLLAMA_MODEL` default becomes `gemma4:e4b` (newer than qwen2.5vl:3b, which is over 12 months old). Source: ollama.com/library/gemma4. Speed UNVERIFIED.
5. yt-dlp: require `yt-dlp[default,curl-cffi]`, pass `js_runtimes={"node":{}}`, subtitle langs `["en","en-orig"]` (not a wildcard, which hit HTTP 429 on auto-translated tracks). Match "Sign in to confirm" only (curly apostrophe). Source: github.com/yt-dlp/yt-dlp/wiki/EJS, own measurement.
6. Instagram "empty media" error is also what a deleted reel gives. Reword the message to "blocked, or the reel was removed". Measured on two reel URLs.
7. faster-whisper: decode WAV with stdlib `wave` and pass a numpy array, and pin `av<17`. Current `av` 19 breaks faster-whisper's own decoder (reproduced).
8. `MAX_FRAMES` default 12 (was 8). On a 16-slide video even thinning to 8 dropped key slides. Thin by dropping near-duplicates, not even spacing.
9. Web fetch: use `requests` with a browser UA and pass bytes to `trafilatura.extract`. Do not use `trafilatura.fetch_url` (ignores HTTP proxies, sleeps up to 30 s on 403/429). Add Jina Reader fallback, off unless `JINA_FALLBACK=true`, because the URL goes to a third party.
10. Replace spec text step 3 truncation with head+tail (70/30). Add URL canonicalization (strip utm_*, fbclid, si; youtu.be and /shorts to watch?v=ID).
11. Email: 30 s SMTP timeout, 100 KB HTML cap (Gmail clips at 102 KB), log SMTP 535 as "app password revoked". Recommend a Gmail filter or `MAIL_TO` different from `MAIL_FROM`.
12. README must state: free Gemini tier uses inputs to improve Google products and allows human review (ai.google.dev/gemini-api/terms, updated 2026-04-28).

## 4. Components

### Input source
- Pick: CSV with stdlib `csv`/`os.replace`/`tempfile`. Later: Sheets via `requests` + `cryptography` (RS256 signer only, no google-auth).
- How: open with `utf-8-sig`, `newline=""`; every `mark()` re-reads from disk, finds the row by normalized URL, changes only status/detail, writes tmp in same dir, fsync, `os.replace`. Retry replace about 5 times on PermissionError; if still locked, keep status in SQLite and retry next poll. Reconcile each poll: DB wins status/detail, CSV wins url/notes/new rows.
- Checks: measured here, `os.replace` over a target with any open handle raises PermissionError (WinError 5) for every handle type tried. Excel may save cp1252, so fall back on UnicodeDecodeError. Sheets quota (limits page, updated 2026-09-03): 300 reads/min per project, 60/min per user; a 2 min poll is 0.5 reads/min; no billing for normal use. Service account JWT: RS256, 1 h max, token valid 3600 s (doc updated 2026-03-23). Sheets write-back is cell-level, no clobber race.
- Verdict: yes.
- Risk: lock blocks write-back (PermissionError in log, pending count in DB); on Linux a user save overwrites status (done row reappears blank, fixed next poll by reconcile).
- Fallback: Sheets. Stdlib-only RS256 or `openssl dgst -sign` subprocess are possible but untested (UNVERIFIED). Published-to-web CSV is read-only, so no write-back.
- Evidence: developers.google.com/workspace/sheets/api/limits (2026-09-03); developers.google.com/identity/protocols/oauth2/service-account (2026-03-23); Linux rename-over-open-file behaviour is POSIX, UNVERIFIED here.

### Queue
- Pick: stdlib sqlite3 (SQLite 3.49.1 here), `journal_mode=WAL`, `synchronous=FULL`, one connection, explicit BEGIN/COMMIT, plain `INTEGER PRIMARY KEY` (not AUTOINCREMENT).
- How: `INSERT OR IGNORE` with `rowcount` for new vs duplicate; claim with `UPDATE ... WHERE id=(SELECT ... ORDER BY seq LIMIT 1) RETURNING` (needs 3.35+); requeue sets `seq=max+1`; startup resets `processing` to `queued`; write DB first, then CSV.
- Rules when CSV and DB disagree: empty status + no DB row = enqueue; empty + DB terminal + `csv_synced=0` = re-mark CSV from DB (crash between writes); empty + DB terminal + `csv_synced=1` = user cleared it, retry with attempts=0; status set + no DB row = ignore (except `queued`); reorder no effect; edited URL = new job; same URL on two rows = one job.
- Checks: 15 random kills per journal mode plus a 20000-row mid-transaction kill: integrity ok, only committed rows survive. WAL needs a local disk (not OneDrive or network share).
- Verdict: yes. Redis, Celery, RQ, Postgres, huey, persist-queue are all unjustified for one worker.
- Risk: DB/CSV drift if write order is reversed; seen as a job stuck `processing` or CSV stuck `queued`.
- Fallback: `journal_mode=DELETE`.
- Evidence: sqlite.org/wal.html (2026-08-25), atomiccommit.html (2026-04-21), lang_returning.html (2025-05-31). Linux kill and power-loss behaviour not tested.

### Download
- Pick: yt-dlp 2026.08.19 (released 2026-08-19) as `yt-dlp[default,curl-cffi]` (pulls yt-dlp-ejs 0.8.0, curl_cffi 0.16.3).
- How: `YoutubeDL` params `format="bv*[height<=480]+ba/b[height<=480]/b"`, `writesubtitles`, `writeautomaticsub`, `subtitleslangs=["en","en-orig"]`, `subtitlesformat="vtt/best"`, `js_runtimes={"node":{}}`, `noplaylist`, `socket_timeout=20`, `retries=2`, `cookiefile` optional. Probe with `skip_download=True`. Keep the retry-without-subs step.
- Checks: 19 s video, probe 2.5 to 3.0 s, 480p download 3.4 s (4.0 s with captions), under 0.5 MB. Node must be 22+; yt-dlp defaults to deno only, so node needs `js_runtimes`. Without a runtime a warning appears but this test video still worked. Unlicense, free. YouTube worked from a home IP with no cookies or PO token.
- Verdict: yes with risk.
- Risk: datacenter IPs get "Sign in to confirm you're not a bot" and maintainers say they cannot fix it (issue 15865, Feb 2026). Instagram anonymous: empty-media error on both reel URLs probed (issue 17074, Jun 2026); a `/p/` post probed fine. Whether any public reel works anonymously is UNVERIFIED. Seen as the mapped error in CSV detail.
- Fallback: YouTube: bgutil PO-token plugin, throwaway-account cookies, or residential egress. Instagram: throwaway-account cookies (ban risk). Run `pip install -U yt-dlp` regularly.
- Evidence: github.com/yt-dlp/yt-dlp/releases (2026.08.19 removed android_vr default; 2026.06.09 raised JS runtime minimums); wiki/EJS; wiki/PO-Token-Guide; measured with the project venv-free test script.

### Transcription
- Pick: faster-whisper 1.2.1, `base`, int8, CPU, `beam_size=1`, `vad_filter=True`, auto language, `task="transcribe"`.
- How: ffmpeg to 16 kHz mono WAV (1.5 s), read with stdlib `wave` into float32 numpy, pass the array to `transcribe()`. Log detected language and probability. Pre-download models.
- Checks (269 s clip, 4 threads, peak RSS polled):

| model | load s | transcribe s | peak MB | WER vs captions |
|---|---|---|---|---|
| fw tiny b1 | 1.3 | 6.4 | 414 | 4.5% |
| fw base b1 | 1.1 | 12.1 | 405 | 3.6% |
| fw base b5 | 1.3 | 24.4 | 441 | 3.7% |
| fw small b1 | 2.4 | 37.9 | 709 | 3.7% |
| Parakeet TDT 0.6b v2 int8 | 5.0 | 42.3 | 2591 | 0.2% |

  WER is rough (clean narration, reference is itself ASR). Disk: venv 283 MB, base model about 145 MB, small about 484 MB (UNVERIFIED). Licenses: faster-whisper and Whisper weights MIT, Parakeet CC-BY-4.0.
- Verdict: yes with risk.
- Risk: faster-whisper declares `av>=11` with no ceiling; av 19.0.1 raised `TypeError ... metadata_errors` in `decode_audio` (reproduced). Pin `av<17` (16.1.0 untested) and use the numpy path. Hindi: Whisper detects language once from the first 30 s, so Hinglish clips get one language applied to the whole file, and base/small are weak on Hindi.
- Fallback: `small` (3x slower). For Hindi/Hinglish see section 5 and the Gemini 3.5 Transcribe note below. Parakeet v3 has no Hindi; Moonshine is English only; Hindi-specific models (IndicWhisper, IndicConformer) need torch. Not measured: whisper.cpp, Vosk, large-v3-turbo.
- Evidence: github.com/SYSTRAN/faster-whisper; huggingface.co/nvidia/parakeet-tdt-0.6b-v3; measurement scripts in scratchpad `transcription\`.

### Frames
- Pick: spec approach. `ffmpeg -i in -vf "fps=1/2,scale=512:-2" -q:v 4 -an f_%04d.jpg`, timestamp = index*2, Pillow 12.3.0 dHash (grayscale, 9x8 LANCZOS, 64 bit), keep if Hamming distance > 10 to every kept frame, `MAX_FRAMES=12`.
- Checks: 135 frames, ffmpeg 1.9 s, hashing 0.27 s. Kept 17/16/13 at thresholds 6/10/14, so the clip really has about 16 distinct slides. Scene detect `gt(scene,0.1..0.3)` found 1 frame (the end card; max scene score in the clip was 0.356), so it misses slide and code changes. mpdecimate alone fires on noise (1006 frames); after fps=1/2 plus dHash it matches the pick. PySceneDetect never ran (pip hung over 20 min; it pulls opencv-python-headless 43.8 MB, which breaks the no-OpenCV rule). I viewed contact sheets: titles and body text are readable at 512 px, small monospace code is borderline (source was only 640x360, so 768 adds nothing; use 768 for 1080p sources). Pillow is MIT-CMU, the only Python dependency.
- Verdict: yes with risk.
- Risk: the cap. Screen recordings with scrolling or typing fill the cap with near-duplicates (about one frame per 37 s); crossfade frames slip through at threshold 10; the outro bell card was kept. Talking-head videos keep 1 to 2 frames and the transcript carries the content (reasoned, not measured). Notice from the kept/sampled ratio in the footer.
- Fallback: fps=1/4 (nearly the same set); if dHash keeps fewer than 3 frames, fall back to even sampling.
- Evidence: scripts and sheets in scratchpad `frames\`.

### Video/vision LLM
- Pick: `gemini-3.6-flash` (free tier, released 2026-07-21), fallback `gemini-3.5-flash-lite`. The pricing page (2026-10-09) also lists 3.8 Flash, 3.1 Flash-Lite (shutdown 2027-05-07), 2.5 Flash and 2.5 Flash-Lite as free. I did not compare 3.6 vs 3.8 quotas (see open questions).
- How: plain REST `generateContent`, 8 to 12 JPEGs as `inline_data` (about 2k image tokens, far below the 20 MB request cap), transcript and note as text, `responseMimeType: application/json` plus schema, validate JSON in code. Backoff on 429, switch to Flash-Lite after 2 failures.
- Checks: per-model RPM/RPD/TPM are only shown in AI Studio, not in the docs. Third-party figures of 20 to 250 RPD are UNVERIFIED. Quota is per project and resets midnight Pacific. 5 to 30 calls a day should fit. Policy (terms effective 2026-03-23, updated 2026-04-28): on the unpaid tier Google uses submitted content and responses to "provide, improve, and develop Google products", and human reviewers may read it. Paid tier does not train. EEA/UK/CH users must use paid services. India is on the available-regions list; your location is UNVERIFIED.
- Native video: YouTube URL input is allowed on the free tier, up to 8 hours of YouTube video per day, public videos only. A 5 min video costs about 30k tokens against about 6k for frames, and it cannot do Instagram. Decision: the frame pipeline stays. A YouTube-URL fast path could be added later behind a flag.
- Local: `gemma4:e4b` (6.6 GB on Ollama, 128K context, vision; Gemma 4 page last updated 2026-07-08 says E2B/E4B also take audio and video, Ollama's page lists only text and image input, so audio via Ollama is UNVERIFIED). `gemma4:e2b` is 4.6 GB. Google's memory table: E4B Q4 about 4.5 GB, E2B about 2.9 GB. CPU speed NOT measured (the Ollama zip downloaded at about 100 KB/s here, so I aborted). Estimate, UNVERIFIED: 3 to 6 minutes per job, 5 to 7 GB RAM. Gemma recommends temperature 1.0, not the spec's 0.2; test before forcing 0.2. `qwen2.5vl:3b` was last updated over 12 months ago.
- Other free text APIs: Groq `openai/gpt-oss-120b` 30 RPM, 1K RPD, 8K TPM (keep input under about 6k tokens; table undated); OpenRouter `:free` 20 RPM, 50 RPD (1000 after a $10 purchase); Mistral free tier trains on data (UNVERIFIED limits); Cerebras trial credits only; GitHub Models retired 2026-07-30. Secondary pick: Groq, text only.
- Verdict: yes with risk.
- Risk: Google lowers free quota or renames a model (429 or 404 in logs). Every note, transcript and frame is human-reviewable and trainable on the free tier.
- Fallback: Flash-Lite, then Groq (web path only), then Ollama.
- Evidence: ai.google.dev/gemini-api/docs/pricing, deprecations, rate-limits, video-understanding (all 2026-10-09); image-understanding, structured-output (2026-09-23); terms, available-regions (2026-04-28); ai.google.dev/gemma/docs/core; ollama.com/library/gemma4.

### Embeddings
- Pick: none. No role in MVP.
- Roles: (a) frame dedupe: keep dHash. Measured on 60 frames: dHash 1.5 ms/frame, 0 MB extra, keeps 13; DINOv2-small int8 ONNX 91 ms/frame, keeps 14 to 20 depending on threshold; CLIP B/32 ONNX 47 ms/frame, 352 MB model, keeps 14 and matches dHash plus one crossfade frame. Peak RSS 544 MB with both. No semantic gain, 30 to 60 times the cost. (b) duplicate links: URL canonicalization plus optional 5-word-shingle Jaccard >= 0.6 on extracted text; embeddings add a threshold and 100 to 500 MB for no gain (reasoned, not measured). (c) chunk selection: never needed, 60k chars is about 15k tokens against a 1M context; use head+tail.
- EmbeddingGemma 2 (blog.google 2026-10-06, docs updated 2026-10-06): 740M, Apache 2.0, text/image/audio/video in one 768-dim space (MRL to 128), text-only part 270M (vision 170M, audio 300M), 8K context, about 567 MB RAM full multimodal on a phone (quantized), runs in Ollama and llama.cpp. It is the right model if you later want search across your digests ("find the video where X"), not for dedupe. Not benchmarked here.
- Verdict: no. Fallback: 32x32 grayscale pixel diff in Pillow. Revisit when you add digest search; then use EmbeddingGemma 2 text-only or multilingual-e5-small int8 (118 MB, Hindi) via fastembed/onnxruntime (about 30 MB install). torch is a 555 MB Linux wheel plus CUDA pulls, so avoid sentence-transformers.
- Evidence: scratchpad `embeddings\bench.py`; HF model API sizes (2026-10-11).

### Web extraction
- Pick: trafilatura 2.3.1 (PyPI 2026-10-06, Apache-2.0, Python >= 3.10), fetched with `requests` and a browser UA, bytes passed to `extract(favor_recall=True, include_tables=True, include_comments=False)`.
- Checks (chars / ms, same HTML per library):

| page | trafilatura | readability-lxml | newspaper4k | jusText |
|---|---|---|---|---|
| blog (simonwillison) | 37669 / 73 | 35494 / 54 | 40740 / 1199 | 27500 / 101 |
| dev.to | 19805 / 150 | 22119 / 349 | 15677 / 3209 | 14249 / 137 |
| docs.python.org | 42990 / 194 | 43001 / 127 | 7616 / 1113 | 26550 / 67 |
| Medium | blocked (403 Cloudflare challenge) | same | same | same |
| Notion public page (JS SPA) | 88 | 0 | 89 | 0 |

  Boilerplate: trafilatura leaked a short "latest articles" list on the blog and was clean on dev.to; readability leaked "Enter fullscreen mode" and author bio on dev.to; newspaper4k and jusText dropped code blocks. trafilatura already includes jusText as its own fallback.
- JS/blocked fallback: Jina Reader `r.jina.ai` still exists, free without a key at 20 RPM (500 RPM with a free key). It returned the full Medium article (19.6k chars, 6.2 s) and the Notion page (7.8k chars, 6.6 s). Output is Markdown with links (blog 56k vs 38k chars, more tokens). The URL goes to a third party; reader models are CC-BY-NC. Send `DNT: 1` to disable caching and logging. Wayback and local Playwright rendered not worth it for MVP.
- `trafilatura.fetch_url` hung behind an HTTP proxy in this sandbox (it ignores proxy env vars). Not tested on a direct Linux link, UNVERIFIED.
- Threshold: failures measured at 0 to 89 chars, real pages 7k+. 500 works as the "try fallback" trigger, but legitimate short posts would be rejected; 300 is safer.
- Verdict: yes with risk.
- Risk: Medium and Cloudflare-fronted sites 403 from datacenter IPs; seen as many "< 500 chars" failures. Medium paywall and JSON-LD fallback UNVERIFIED (no real Medium HTML obtainable).
- Fallback: Jina Reader, then ProcessingError.
- Evidence: pypi.org/pypi/trafilatura/json (2026-10-06); github.com/adbar/trafilatura/releases; jina.ai/reader (fetched 2026-10-11).

### Email
- Pick: stdlib `smtplib` + `EmailMessage` to smtp.gmail.com (587 STARTTLS, 465 SSL) with a 16-char app password.
- How: `set_content(plain)` then `add_alternative(html, subtype="html")`; `Date`, `Message-ID`; `SMTP(host, 587, timeout=30)`, `starttls(context=ssl.create_default_context())`; `html.escape` everything; inline styles only, explicit text and background colors for dark mode; keep HTML under about 80 KB.
- Checks: ports 587 and 465 reachable on smtp.gmail.com and smtp-relay.brevo.com (TCP connect only, no auth). 2FA is required to create app passwords. Google calls app passwords "not recommended" but still supports them, no sunset date found for personal accounts. Workspace is OAuth-only for third-party apps since 2025-03-14. Google documents only Workspace limits (2,000 msgs/user/day, updated 2026-10-09); personal limits (about 500/day) are third-party, UNVERIFIED. Digest volume is far below either.
- Verdict: yes with risk.
- Risk: password change revokes the app password (SMTP 535, log loudly, do not retry forever); a login from a new datacenter IP may trigger a security alert or block (UNVERIFIED). Mail from yourself to yourself may skip the Inbox (Google documents that for aliases and groups; direct self-send UNVERIFIED), so add a one-time Gmail filter or use a different `MAIL_TO`.
- Fallback: Brevo free SMTP relay (300/day, verified sender, same smtplib code, `SMTP_HOST` env only). Resend 100/day (domain needed for other recipients, UNVERIFIED), Mailjet 200/day, Mailgun 100/day with sandbox limits. SendGrid free plan retired May 2025, ruled out.
- Evidence: support.google.com/accounts/answer/185833 (undated); knowledge.workspace.google.com sending-limits (2026-10-09); twilio.com/en-us/changelog/sendgrid-free-plan (2025-05-27); mailgun.com/pricing (2026-10-11). No email was sent.

## 5. Open questions

1. Where will the Linux server run? A home or residential IP is likely fine for YouTube. A cloud VPS will probably hit the bot wall, which forces cookies or a PO-token plugin. This is the biggest deployment risk.
2. Hindi/Hinglish: do you accept sending that audio to Google? Gemini 3.5 Transcribe (announced 2026-09-15, blog.google) is free of charge on the free tier (pricing page 2026-10-09), supports 85+ languages, automatic code-switching, files up to 1 hour with timestamps. That is a much better fit than Whisper base for Hinglish, but audio goes to a third party that may train on it, and its free rate limits are unpublished. Suggested rule: English stays on local faster-whisper; if detected language is not `en`, route to Gemini 3.5 Transcribe. Needs your yes and an API key to measure.
3. API key needed to settle: free-tier RPM/RPD for `gemini-3.6-flash` vs `gemini-3.8-flash` (pick the one with the higher daily quota), Gemini 3.5 Transcribe limits, and whether JSON schema mode behaves on 3.6.
4. Local model speed: is the CPU Ollama path really needed? If yes, I should measure `gemma4:e4b` vs `qwen3-vl:4b` on the Linux box with 8 images plus a 3k-token transcript. Also whether Gemma 4 audio works through Ollama.
5. Instagram: no public reel was confirmed working anonymously. A real test needs 2 or 3 public reel URLs from you, and a decision on whether a throwaway-account `cookies.txt` is acceptable.
6. Jina Reader fallback sends URLs to a third party. Default off or on?
7. Gmail: will you create an app password (needs 2FA), and where should the digest land (same address needs a filter)?
8. Which JS runtime on the server: node 22+ or deno 2.3+?
9. Dependency approvals: `numpy` and `av` come in with faster-whisper (av is mandatory, 64 MB of bundled ffmpeg libs); `curl_cffi` and `yt-dlp-ejs` come in with the yt-dlp extras; `cryptography` only in Phase 4. All outside the original allow list.

## 6. Updated dependency list and per-job estimates

Python (pip): `yt-dlp[default,curl-cffi]==2026.08.19` (+ yt-dlp-ejs, curl_cffi), `trafilatura==2.3.1` (+ lxml, courlan, htmldate, justext, certifi, charset_normalizer, urllib3), `Pillow==12.3.0`, `requests`. Optional: `faster-whisper==1.2.1` (+ ctranslate2 4.8.2, onnxruntime 1.31, `av<17`, numpy, tokenizers, huggingface-hub, tqdm). Phase 4 only: `cryptography`. System: ffmpeg, node 22+ or deno 2.3+, Ollama only if the local path is used. No embeddings, no OpenCV, no PySceneDetect, no vendor SDKs.

Rough per-job estimates on this machine (Gemini path). The LLM call and network download times are not measured and depend on your connection and quota, so treat them as estimates.

| Job | Steps (measured unless noted) | Wall time | Peak RAM |
|---|---|---|---|
| 5 min captioned YouTube | probe 3 s, download about 10 s (estimate, 5 MB for the 4:30 clip), VTT parse under 1 s, frames 2.2 s, Gemini call 5 to 20 s (estimate) | about 25 to 40 s | under 200 MB |
| 5 min uncaptioned video | as above plus WAV 1.5 s, Whisper base load 1.1 s and transcribe 12.1 s | about 40 to 55 s | about 410 MB |
| Blog post | fetch 1 to 2 s, extract 0.1 to 0.2 s, Gemini call 5 to 20 s (estimate); Jina fallback adds about 6 s | about 8 to 25 s | under 150 MB (estimate) |
| Any video on local Ollama instead of Gemini | LLM step 3 to 6 min, 5 to 7 GB RAM (UNVERIFIED) | about 4 to 7 min | 5 to 7 GB |

Disk: base model about 145 MB, venv about 283 MB for faster-whisper, per-job temp under 20 MB (deleted in `finally`).

Free-tier privacy note for the README: the free Gemini tier may train on and human-review everything you send, including transcripts and frames.
