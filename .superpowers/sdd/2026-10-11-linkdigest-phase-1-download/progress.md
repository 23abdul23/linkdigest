# SDD ledger — plan: docs/superpowers/plans/2026-10-11-linkdigest-phase-1-download.md
Index/spec: docs/superpowers/plans/2026-10-11-linkdigest.md ; spec docs/linkdigest_handoff_prompt.md + docs/research.md (moved into docs/ by the user; plan text says repo root)
Branch: feat/linkdigest (git already initialised, plan Task 1 Step 1 git init is skipped)

## Preflight scan (Phase 1, Tasks 1-4)
| pair / task | produces vs consumes | finding |
| T1->T2 | tests/_run.py (ROOT, patched, main) -> test_config/test_classify import _run | consistent |
| T2->T3 | errors.Blocked/ProcessingError, Config(js_runtime, ytdlp_cookies), classify() -> download.py | consistent |
| T3->T4 | probe(url,kind,cfg), download(url,kind,dest,cfg), tests/fixtures.fake_ydl -> cmd_probe, test_download.py appended | consistent; T4 appends to T3's test file before its __main__ block |
| T1 hygiene | scans linkdigest/, tests/, smoke*.py, README.md etc; .superpowers/ not scanned | .superpowers/ must be gitignored |
| T1..T4 self | each task's tests vs code reviewed against each other | no contradiction found |
Ruling: add `.superpowers/` to .gitignore in Task 1 — SDD scratch must not be committed — cost: none (hygiene test only requires the 5 mandatory entries).
Ruling: skip `git init` in Task 1 Step 1 (repo exists, branch feat/linkdigest) — cost: none.
Ruling: spec docs live under docs/ not repo root — plan paths are references only — cost: none.
Ruling: venv python is .venv/Scripts/python on this Windows host; use it for every command — cost: none.
Task 1: complete (commits c62c863..b7d21a6, review clean)
Task 1: minor (deferred): hygiene secret check only covers SECRET_KEYS/TEST_*; key regex knows only AIza and sk- prefixes (brief choice)
Ruling: user instruction 'never commit with Claude as co-author' — history rewritten locally to strip the trailer (Task 1 is now b7d21a6, Task 2 24cca1a); no trailer in any future commit; CLAUDE.md (user file) excluded via .git/info/exclude — cost: none, nothing pushed
Task 2: complete (commits b7d21a6..24cca1a, review clean)
Task 2: minor (deferred): load_env edge cases (BOM, `KEY=# x`, export prefix); TimeoutExpired unmapped in run_ffmpeg; unused import in test_config; si/feature stripped on all hosts
Ruling: normalize_url("http://[abc") raises ValueError (junk CSV row would abort sync every poll) — fixed in Task 3 dispatch by try/except + test — cost: one extra test
Task 3: fix round 1/5 (1 addressed, 0 open — transient errors misclassified as gone; commits 4656103..083192e)
Task 3: complete (commits 24cca1a..083192e, review clean)
Task 3: minor (deferred): retry test does not assert second call lacks writesubtitles; bare token "subtitle" broad; Instagram 5xx is permanent by policy
Task 4: complete (commits 083192e..d4bd847, review clean)
Task 4: minor (deferred): unused log import in __main__.py; Ctrl-C mid-download traceback
Gate 1 offline: complete (HEAD 8a117d8); phase review fixes: cookies ignore + probe --verbose; live YouTube/IG-fake verified by controller; awaiting user URLs for real IG reels
Gate 1: minor (deferred): _run.run catches Exception only, so argparse SystemExit aborts run_all without a FAIL line; canonical/classify unguarded urlparse (callers must normalize_url first - carry into Task 14 sync); normalize_url accepts user@host junk
Ruling: user asked to push everything except .env and .venv — .superpowers/ is no longer git-ignored and the SDD workspace is committed so the cloud session can resume — cost: scratch files in git history
Ruling: .env.example now carries the public TEST_* links (user request) and tests/test_hygiene.py no longer requires TEST_* blank (secrets keys stay required blank); Config gained test_instagram_post_url — cost: none
Ruling: new YouTube Short sJOz9jMko4Q (38s, Hindi, no captions) assigned as TEST_YOUTUBE_NOCAPS_URL
Handoff: docs/CLOUD_HANDOFF.md written for the cloud session; next = Phase 2 plan with three additions (unknown duration after download, stdout errors=replace, Instagram image-post path)
