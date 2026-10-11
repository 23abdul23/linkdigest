# Task 4a review (commit ef73b98)

Verdict: clean. No real defects found. `tests/run_all.py` prints PASS (all ok, hygiene included).

## Checklist
1. Required behaviours: all implemented and pinned. Unknown duration, `ignore_no_formats_error` (asserted on F.calls), carousel order and largest thumbnail, last-listed and `url` fallbacks, single image post, video carousel and empty rejection, non-Instagram playlist, download_images (resize, order, cap, error map, no partial), probe_duration, cmd_probe output and --download on a post, cp1252 emoji, MAX_SLIDES config and .env.example. Tests use real Pillow bytes and assert on outputs, none vacuous.
2. probe(): Instagram playlist, single entry and no-media cases match spec. Video carousel gives the "several videos" error. YouTube playlist keeps "not a single video" (tested with an IG-shaped playlist on kind=youtube). Live check precedes everything. Judgement call (Instagram-only detection) is consistent with the spec text.
3. download_images: 5xx, Timeout and ConnectionError give RuntimeError; other 4xx and undecodable data give ProcessingError. All images are converted before any write, so no partial set. Capped by slicing before fetching. No cookies. 20 s timeout.
4. probe_duration: catches OSError, SubprocessError (incl. TimeoutExpired) and ValueError; non-zero exit gives None. Never raises.
5. main(): both streams reconfigured with errors="replace" when the attribute exists. Test would fail without it (strict cp1252 raises on the emoji print).
6. No em dash, no secrets, no new dependencies (requests and Pillow already used), commit message has no attribution, style matches.
7. No regressions in download() or in probe callers (only cmd_probe uses probe; updated for None duration).

## Defects
None.

## Minors (optional)
- download.py `_image_post`: an Instagram playlist containing a None entry would raise AttributeError (`e.get`). Unlikely from yt-dlp.
- download.py `_fetch_image`: other `requests.RequestException` types (InvalidURL, ChunkedEncodingError) are not mapped and propagate raw.
- download.py `download_images`: `max_slides=0` returns an empty list silently.
- download.py:probe `kind == "instagram" and not info.get("formats")`: an Instagram video that yields no formats but has a thumbnail now becomes a one-image post instead of an error. Spec-conformant, just worth knowing.
- The "several videos" message also fires for a single-entry video playlist.
- Tests: the `entry["url"]` fallback is not exercised, and the stderr reconfigure is not asserted.
