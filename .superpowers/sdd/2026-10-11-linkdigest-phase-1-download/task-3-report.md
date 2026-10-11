# Task 3 report
Status: DONE
Commits: 3a2ff5a feat: yt-dlp probe and download with mapped errors; 4656103 fix: normalize_url returns empty for malformed URLs
RED: `.venv/Scripts/python tests/test_download.py` -> ImportError: cannot import name 'download' from 'linkdigest'.
GREEN: all 7 test_download tests ok, PASS. run_all.py PASS (all suites incl. hygiene/no em dash).
Fix commit: added the two malformed-URL asserts to test_normalize_url; RED was ValueError: Invalid IPv6 URL; then wrapped urlparse in try/except ValueError returning ""; run_all PASS.
Files: linkdigest/download.py, tests/fixtures.py, tests/test_download.py (new); linkdigest/classify.py, tests/test_classify.py (changed).
Code and tests used verbatim from the brief; no brief test failed.
Concerns: the retry test logs a log.warning line to stderr during the run (expected from brief code, not a failure). classify() in classify.py still calls urlparse unguarded (canonical/classify on junk input); not in scope. Git warns about LF->CRLF on commit (autocrlf), harmless.

## Fix round 1
Commit: fix: classify transient download errors as transient
Changed: download.py classify_error gets _TRANSIENT early branch (after age/bot/instagram-blocked, before private/_GONE) returning ("other", "Download failed: <last line>") via new _other helper; video filter now excludes _NOT_VIDEO suffixes (.vtt .srt .ttml .json3 .json .part .ytdl .jpg .webp .png); probe does `info = info or {}`.
Tests added (RED first: test_transient_errors_are_not_gone and test_probe_none_info FAILED): 503 and subtitle-404 map to "other"/RuntimeError, subtitle-404 download retries without subs, None info raises ProcessingError "length".
Command: `.venv/Scripts/python tests/run_all.py` -> all ok, PASS.

## Gate 1 fix
Commit: fix: silence yt-dlp console output
_opts now sets noprogress=True and logger=_YdlLogger() (debug/info/warning/error all forward to log.debug, never print). Error mapping untouched. Removed unused `log` import in __main__.py (grep confirmed only the import line).
Test (RED first): test_opts_silence_ytdlp_console. run_all.py PASS.
Live: Instagram reel probe --download prints exactly one "Blocked: ..." line; YouTube j2XWVqUQJNg prints only the two summary lines (kind=..., downloaded=...).
