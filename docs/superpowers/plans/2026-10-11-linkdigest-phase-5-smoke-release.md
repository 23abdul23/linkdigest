# linkdigest Phase 5: Smoke, email, Instagram hardening, release

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Read the index `2026-10-11-linkdigest.md` first. Phase 4 must be tagged `gate-4`. Steps use checkbox syntax.

**Goal of this phase:** prove the whole service on real links with the spec's smoke script (Gate 5, including one real email to the user's phone), measure Instagram honestly with and without cookies and confirm failures never block the worker (Gate 6), then write the README and the Linux service files.

**Spec:** handoff "Verification B", "Phases" 2 and 3, "Instagram failures", "Logging", and `research.md` Download, Email sections and the open questions.

## Interfaces defined in this phase

```python
# smoke.py          main() -> int      exit 0 all PASS, 1 any FAIL, 2 missing setup
# smoke_ig.py       main() -> int      exit 0 no UNMAPPED outcome, 1 otherwise, 2 missing setup
```

No new library modules. Tests added: `tests/test_offline_ig.py`, `tests/test_logging.py`.

---

### Task 15: smoke.py (spec Test B)

**Files:**
- Create: `smoke.py`
- Test: none offline for the script body (it only runs against the network). `tests/test_hygiene.py` already scans it for em dashes and key-shaped strings.

**Interfaces:**
- Consumes: `Config.from_env`, `load_env`, `pipeline.run_cycle`, `JobQueue`, `CsvSource`.
- Produces: the smoke run.

- [ ] **Step 1: Write `smoke.py`**

```python
"""Real-network smoke run (spec Test B, steps 1 to 4 and 6). Uses a temp CSV, temp DB and dry run.
Instagram (step 5) lives in smoke_ig.py. Usage: python smoke.py"""
import csv
import logging
import re
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path

from linkdigest import pipeline
from linkdigest.config import Config, load_env
from linkdigest.jobqueue import JobQueue
from linkdigest.source_csv import CsvSource


class Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.msgs = []

    def emit(self, record):
        self.msgs.append(record.getMessage())


def step_times(msgs):
    """{job_id: {step: seconds}} from the worker's log lines."""
    out, cur = {}, None
    for m in msgs:
        j = re.match(r"processing job (\d+):", m)
        if j:
            cur = int(j.group(1))
            out.setdefault(cur, {})
        s = re.match(r"step (\w+) took ([\d.]+)s", m)
        if s and cur is not None:
            out[cur][s.group(1)] = float(s.group(2))
    return out


def section(txt, head):
    lines = txt.splitlines()
    if head not in lines:
        return []
    i, out = lines.index(head) + 1, []
    while i < len(lines) and lines[i].strip():
        out.append(lines[i])
        i += 1
    return out


def secs(mmss):
    m, s = mmss.split(":")
    return int(m) * 60 + int(s)


def main():
    load_env()
    base = Config.from_env()
    need = {"TEST_YOUTUBE_URL": base.test_youtube_url, "TEST_YOUTUBE_NOCAPS_URL": base.test_youtube_nocaps_url,
            "TEST_BLOG_URL": base.test_blog_url, "TEST_LONG_VIDEO_URL": base.test_long_video_url}
    missing = [k for k, v in need.items() if not v]
    if missing:
        print("Set these in .env first:", ", ".join(missing))
        print("Picks: YouTube under 5 min with captions; a short video with no captions; a plain article "
              "page (not a SPA, not paywalled); any video over 5 minutes.")
        return 2
    if base.llm_provider == "gemini" and not base.llm_api_key:
        print("Set LLM_API_KEY in .env (or use LLM_PROVIDER=ollama).")
        return 2

    tmp = Path(tempfile.mkdtemp(prefix="linkdigest-smoke-"))
    cfg = replace(base, source_csv=str(tmp / "links.csv"), db_path=str(tmp / "jobs.db"),
                  out_dir=str(tmp / "out"), work_dir=str(tmp / "work"), dry_run=True)
    rows = [[cfg.test_blog_url, "focus on the main argument"], [cfg.test_youtube_url, "only the commands"],
            [cfg.test_youtube_nocaps_url, ""], [cfg.test_long_video_url, ""]]
    with open(cfg.source_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["url", "notes", "status", "detail"])
        w.writerows([[u, n, "", ""] for u, n in rows])

    cap = Capture()
    lg = logging.getLogger("linkdigest")
    lg.addHandler(cap)
    lg.setLevel(logging.INFO)
    src, q = CsvSource(cfg.source_csv), JobQueue(cfg.db_path)
    t0 = time.time()
    pipeline.run_cycle(cfg, q, src)
    print(f"first cycle took {time.time() - t0:.0f}s")

    out = Path(cfg.out_dir)
    by_url = {r.url: r for r in src.rows()}

    def jid(url):
        return q.get(by_url[url].row_key)["id"]

    def txt(url):
        return next(iter(sorted(out.glob(f"{jid(url)}-*.txt"))), None)

    def body(url):
        p = txt(url)
        assert p, "no digest file was written"
        return p.read_text(encoding="utf-8")

    results = []

    def step(name, fn):
        try:
            detail = fn() or ""
            results.append((name, True, detail))
        except AssertionError as e:
            results.append((name, False, str(e)))
        except Exception as e:
            results.append((name, False, f"{type(e).__name__}: {e}"))

    times = step_times(cap.msgs)

    def s1():
        r, t = by_url[cfg.test_blog_url], body(cfg.test_blog_url)
        assert r.status == "done", f"status {r.status}: {r.detail}"
        assert len(section(t, "SUMMARY")) == 3, "summary is not 3 lines"
        assert len([x for x in section(t, "KEY POINTS") if x.startswith("- ")]) >= 5, "fewer than 5 key points"
        assert "TIMESTAMPS" not in t, "web digest has a Timestamps section"
        assert "HOW YOUR NOTE WAS APPLIED" in t, "no note section"
        return f"llm {times[jid(cfg.test_blog_url)].get('llm', 0):.1f}s"

    def s2():
        u = cfg.test_youtube_url
        r, t = by_url[u], body(u)
        assert r.status == "done", f"status {r.status}: {r.detail}"
        assert "Transcript: captions" in t, "transcript did not come from captions"
        dur = secs(re.search(r"\| (\d+:\d{2})", t).group(1))
        stamps = section(t, "TIMESTAMPS")
        assert 3 <= len(stamps) <= 8, f"{len(stamps)} timestamps"
        assert all(secs(x.split()[0]) <= dur for x in stamps), "a timestamp is past the video end"
        html = next(iter(sorted(out.glob(f"{jid(u)}-*.html")))).read_text(encoding="utf-8")
        assert html.count("&amp;t=") + html.count("?t=") >= len(stamps), "deep links missing"
        applied = " ".join(section(t, "HOW YOUR NOTE WAS APPLIED")).lower()
        assert "command" in applied, "note_applied does not mention the note"
        return f"{len(stamps)} timestamps, llm {times[jid(u)].get('llm', 0):.1f}s"

    def s3():
        u = cfg.test_youtube_nocaps_url
        r, t = by_url[u], body(u)
        assert r.status == "done", f"status {r.status}: {r.detail}"
        assert "Transcript: whisper" in t, "transcript did not come from whisper"
        return f"whisper step {times[jid(u)].get('transcript', 0):.1f}s on this CPU"

    def s4():
        u = cfg.test_long_video_url
        assert by_url[u].status == "skipped", f"status {by_url[u].status}: {by_url[u].detail}"
        assert "download" not in times[jid(u)], "a download happened for the long video"
        assert not list((tmp / "work").glob("job-*")), "temp dir left behind"
        assert any(out.glob(f"{jid(u)}-*.html")), "no skip notice written"
        return by_url[u].detail

    def s6():
        before = sorted(p.name for p in out.glob("*"))
        pipeline.run_cycle(cfg, q, src)
        after = sorted(p.name for p in out.glob("*"))
        assert before == after, "a second cycle wrote new files"

    step("1 blog", s1)
    step("2 youtube with captions", s2)
    step("3 youtube without captions", s3)
    step("4 long video skipped", s4)
    print("5 instagram: run python smoke_ig.py")
    step("6 rerun writes nothing", s6)

    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")
    print(f"outputs kept in {out}")
    return 0 if all(ok for _, ok, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Offline sanity (no network).** Run `python smoke.py` with `.env` missing the TEST_ URLs. Expected: it prints `Set these in .env first: ...` and exits 2 (check with `echo $?`). Then `python tests/run_all.py` still `PASS` (the hygiene test scans `smoke.py`).

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "feat: real-network smoke script"
```

---

### Gate 5: smoke passes on real links, then one real email

Stop and report. Do not start Task 16 until the user says OK.

**Needs from the user:** all `TEST_*` URLs except Instagram in `.env`; `LLM_API_KEY`; for the email step: `SMTP_USER`, `SMTP_PASS` (Gmail app password; needs 2FA on the account), `MAIL_TO`.

- [ ] **Step 1: Run smoke.** `python smoke.py`. Expected five lines `PASS` (steps 1, 2, 3, 4, 6) and the pointer for step 5. For each `FAIL`: read the detail, reproduce with `python -m linkdigest test "<url>" --dry-run`, fix the cause with a failing offline test first when the cause is in our code, rerun. Do not weaken the checks.

- [ ] **Step 2: Report the numbers.** Whisper step seconds on this CPU, LLM seconds per job, total cycle time.

- [ ] **Step 3: Show the digests.** Attach the YouTube and blog `.html` files from the printed `out` path (copy them to the project `out/` so the user can open them) and describe what a reader sees.

- [ ] **Step 4: Ask before sending anything.** Tell the user which address `MAIL_TO` points at and ask for an explicit OK. Only then:

```bash
python -m linkdigest test "<TEST_BLOG_URL>" "focus on the main argument"
```

Expected: `OK 'Digest: ...' -> emailed to MAIL_TO`. Possible failures and what they mean: `SMTP login failed (app password revoked or wrong)` means a bad app password; `Digest was made but sending the email failed ... Saved to <file>` means a network or port problem and the digest is on disk.

- [ ] **Step 5: User checks the phone.** Ask the user to confirm: it arrived, which folder (Inbox or only All Mail, since mail to your own address can skip the Inbox, see `research.md`; if so, the one-time Gmail filter `from:me to:me` with "Never send to spam" fixes it), the layout is readable on the phone, links open the source, and dark mode text is legible. Do not proceed on assumption.

- [ ] **Step 6: Review.** Dispatch a fresh reviewer on the Phase 5 diff so far (`smoke.py` only). Brief: "Does each smoke check really test the claim in the spec's Verification B? Any check that can pass vacuously?" Apply real findings.

- [ ] **Step 7: Tag and report.**

```bash
git add -A
git commit -m "test: gate 5 fixes"
git tag gate-5
```

Report: PASS/FAIL output, timings, the email result and the user's phone confirmation, review result. Ask for the OK to start Task 16 (Instagram hardening).

---

### Task 16: Instagram hardening, log safety, success-rate matrix

**Files:**
- Create: `smoke_ig.py`, `tests/test_offline_ig.py`, `tests/test_logging.py`
- Modify: `linkdigest/download.py` only if the live matrix finds an unmapped error string (see Step 6)

**Interfaces:**
- Consumes: `pipeline.process_job`, `download.IG_BLOCKED`, `Blocked`, `ProcessingError`, `Skipped`, the `test_offline` helpers (`make_ydl`, `setup`, `llm_post`, `blog_get`, `YT`, `IG`).
- Produces: `smoke_ig.main`.

- [ ] **Step 1: Write the failing offline tests** `tests/test_offline_ig.py`

```python
import tempfile

import _run
from fixtures import FakeYDL, make_video
from linkdigest import download, llm, pipeline, text_proc
from test_offline import BLOG, IG, YT, blog_get, llm_post, make_ydl, setup
from yt_dlp.utils import DownloadError


def run(cfg, q, src, ydl):
    with _run.patched(download, "new_ydl", ydl), _run.patched(text_proc, "http_get", blog_get), \
            _run.patched(llm, "http_post", llm_post()):
        pipeline.run_cycle(cfg, q, src)


def test_unknown_instagram_error_is_permanent_and_tried_once():
    class Y(FakeYDL):
        calls = []

        def extract_info(self, url, download=False):
            Y.calls.append(url)
            raise DownloadError("ERROR: [Instagram] x: Something new and strange happened")
    with tempfile.TemporaryDirectory() as d:
        cfg, src, q = setup(d, [[IG, "", "", ""]])
        run(cfg, q, src, Y)
        row = src.rows()[0]
    assert len(Y.calls) == 1, "an unrecognised Instagram error must not be retried"
    assert row.status == "failed" and row.detail.startswith("Download failed: ") and len(row.detail) <= 300


def test_private_and_removed_reels_get_their_own_messages_without_retry():
    for text, want in [("ERROR: [Instagram] x: This account is private", "Video is private."),
                       ("ERROR: [Instagram] x: Video has been removed", "Video is unavailable or removed.")]:
        class Y(FakeYDL):
            calls = []
            msg = text

            def extract_info(self, url, download=False):
                Y.calls.append(url)
                raise DownloadError(self.msg)
        with tempfile.TemporaryDirectory() as d:
            cfg, src, q = setup(d, [[IG, "", "", ""]])
            run(cfg, q, src, Y)
            assert src.rows()[0].detail == want and len(Y.calls) == 1


def test_many_blocked_reels_do_not_stop_a_youtube_job():
    reels = [f"https://www.instagram.com/reel/AAAAAAAAA{i}/" for i in range(5)]
    with tempfile.TemporaryDirectory() as d:
        Y = make_ydl(make_video(d).read_bytes())
        cfg, src, q = setup(d, [[u, "", "", ""] for u in reels] + [[YT, "", "", ""], [BLOG, "", "", ""]])
        run(cfg, q, src, Y)
        status = {r.url: r.status for r in src.rows()}
    assert status[YT] == "done" and status[BLOG] == "done"
    assert all(status[u] == "failed" for u in reels)
    probes = [c[1] for c in Y.calls if c[0] == "probe"]
    assert all(probes.count(u) == 2 for u in reels), "each reel is tried exactly twice (one retry)"
    assert probes[-5:] == reels, "retries run after every first-time job"


def test_a_working_reel_without_audio_still_gives_a_digest_with_a_banner():
    class Y(FakeYDL):
        calls = []
        write_vtt = False
    with tempfile.TemporaryDirectory() as d:
        video = make_video(d).read_bytes()
        Y.video_bytes = lambda self: video
        Y.info = {"title": "A reel", "duration": 20, "is_live": False}
        cfg, src, q = setup(d, [[IG, "what is shown", "", ""]])
        run(cfg, q, src, Y)
        assert src.rows()[0].status == "done"
        html = next(iter(__import__("pathlib").Path(cfg.out_dir).glob("*.html"))).read_text(encoding="utf-8")
    assert "Instagram reel" in html and "audio" in html


def test_cookie_file_option_is_passed_to_yt_dlp_for_instagram():
    class Y(FakeYDL):
        calls = []
        info = {"title": "R", "duration": 20, "is_live": False}
    with tempfile.TemporaryDirectory() as d:
        Y.video_bytes = lambda self: make_video(d).read_bytes()
        cfg, src, q = setup(d, [[IG, "", "", ""]])
        cfg.ytdlp_cookies = "cookies.txt"
        run(cfg, q, src, Y)
    assert all(c[1].get("cookiefile") == "cookies.txt" for c in Y.calls)


if __name__ == "__main__":
    _run.main(globals())
```

`tests/test_logging.py`:

```python
import logging
import tempfile
from pathlib import Path

import _run
from fixtures import make_video
from linkdigest import download, llm, pipeline, text_proc
from test_offline import IG, YT, blog_get, llm_post, make_ydl, setup


class Cap(logging.Handler):
    def __init__(self):
        super().__init__()
        self.msgs = []

    def emit(self, record):
        self.msgs.append(self.format(record))


def test_logs_contain_no_secrets_notes_or_request_bodies():
    with tempfile.TemporaryDirectory() as d:
        Y = make_ydl(make_video(d).read_bytes())
        cfg, src, q = setup(d, [[YT, "my private note", "", ""], [IG, "", "", ""]])
        cfg.llm_api_key, cfg.smtp_pass = "SECRETKEY123", "SECRETPASS456"
        cfg.ytdlp_cookies = str(Path(d) / "cookies-SECRETPATH.txt")
        lg = logging.getLogger("linkdigest")
        cap, old = Cap(), lg.level
        cap.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        lg.addHandler(cap)
        lg.setLevel(logging.DEBUG)
        try:
            with _run.patched(download, "new_ydl", Y), _run.patched(text_proc, "http_get", blog_get), \
                    _run.patched(llm, "http_post", llm_post()):
                pipeline.run_cycle(cfg, q, src)
        finally:
            lg.removeHandler(cap)
            lg.setLevel(old)
        blob = "\n".join(cap.msgs)
    assert "step download took" in blob and "done job" in blob          # logging works at all
    for secret in ("SECRETKEY123", "SECRETPASS456", "SECRETPATH", "my private note", "Reader's note"):
        assert secret not in blob, secret


if __name__ == "__main__":
    _run.main(globals())
```

- [ ] **Step 2: Run to verify behaviour**

Run: `python tests/test_offline_ig.py` and `python tests/test_logging.py`
Expected: these exercise code that already exists, so most should pass at once. Any failure is a real defect to fix in `download.py`, `pipeline.py` or the log calls, not in the test. The ordering check in `test_many_blocked_reels...` (`probes[-5:] == reels`) is the proof that retries run after every first-time job.

- [ ] **Step 3: Fix what failed, rerun** `python tests/run_all.py` until `PASS`.

- [ ] **Step 4: Write `smoke_ig.py`**

```python
"""Instagram success-rate matrix. Usage: python smoke_ig.py
Reels come from TEST_INSTAGRAM_URL (comma separated). Runs each reel without cookies and, if YTDLP_COOKIES
is set, with them. Dry run only. Waits between reels because rate limits are part of what is measured."""
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path

from linkdigest import pipeline
from linkdigest.config import Config, load_env
from linkdigest.errors import Blocked, ProcessingError, Skipped

PAUSE_SECONDS = 20


def outcome(exc):
    if exc is None:
        return "DONE", ""
    if isinstance(exc, Skipped):
        return "SKIPPED", str(exc)
    if isinstance(exc, Blocked):
        return "BLOCKED", str(exc)
    if isinstance(exc, ProcessingError):
        return "FAILED", str(exc)
    return "UNMAPPED", f"{type(exc).__name__}: {exc}"


def main():
    load_env()
    base = Config.from_env()
    reels = [u.strip() for u in base.test_instagram_url.split(",") if u.strip()]
    if not reels:
        print("Set TEST_INSTAGRAM_URL in .env (one or more public reel URLs, comma separated).")
        return 2
    if base.llm_provider == "gemini" and not base.llm_api_key:
        print("Set LLM_API_KEY in .env (or use LLM_PROVIDER=ollama).")
        return 2
    modes = [("no cookies", "")]
    if base.ytdlp_cookies:
        modes.append(("cookies", base.ytdlp_cookies))
    tmp = Path(tempfile.mkdtemp(prefix="linkdigest-ig-"))
    table = []
    for label, cookies in modes:
        for n, url in enumerate(reels):
            if table:
                time.sleep(PAUSE_SECONDS)
            cfg = replace(base, ytdlp_cookies=cookies, work_dir=str(tmp / "work"),
                          out_dir=str(tmp / f"out-{label.replace(' ', '-')}"), dry_run=True)
            t0 = time.time()
            exc = None
            try:
                pipeline.process_job(cfg, url, "what is shown")
            except Exception as e:                  # classify, never crash the matrix
                exc = e
            kind, detail = outcome(exc)
            table.append((label, n + 1, kind, time.time() - t0, detail))
    print()
    for label, n, kind, secs, detail in table:
        print(f"{label:<11} reel {n}  {kind:<9} {secs:5.0f}s  {detail[:110]}")
    for label, _ in modes:
        rows = [r for r in table if r[0] == label]
        done = sum(r[2] == "DONE" for r in rows)
        print(f"{label}: {done}/{len(rows)} reels produced a digest")
    unmapped = [r for r in table if r[2] == "UNMAPPED"]
    if unmapped:
        print("UNMAPPED errors found: add the raw text to tests/test_download.py and map it in download.py")
    return 1 if unmapped else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run offline checks.** `python tests/run_all.py` expect `PASS`; `python smoke_ig.py` with no `TEST_INSTAGRAM_URL` prints the setup hint and exits 2.

- [ ] **Step 6: If the live matrix (Gate 6) finds an UNMAPPED outcome:** copy the raw error text, add a failing case to `tests/test_download.py` that expects the right category, change `_IG`/`_GONE`/`classify_error` in `linkdigest/download.py`, rerun everything. The rule from the plan holds: unknown Instagram errors stay permanent, and a new pattern is added only for something clearly a block.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: Instagram matrix script, Instagram and log-safety tests"
```

---

### Task 17: README, service file, final repository checks

**Files:**
- Create: `README.md`, `deploy/linkdigest.service`
- Test: `tests/test_hygiene.py` (already scans README), plus a manual check that every README command was executed.

- [ ] **Step 1: Write `README.md`**

````markdown
# linkdigest

Paste links into `links.csv`, get one readable HTML email per link. YouTube videos, Instagram reels and web
pages are summarised, guided by an optional note you write next to the link.

## How it works

`links.csv` is polled every 2 minutes. Each new row is queued in SQLite, processed once, and its status
(`queued`, `done`, `failed`, `skipped`) and reason are written back into the CSV. Videos: yt-dlp downloads at
480p or lower, captions are used when they exist, otherwise faster-whisper transcribes on the CPU, ffmpeg
samples frames and a small Pillow hash keeps only the different ones. Pages: trafilatura extracts the text.
A Gemini free-tier model (or a local Ollama model) writes the digest. Videos over 5 minutes are skipped.

## Install (Linux)

```bash
sudo apt install ffmpeg python3-venv nodejs      # node must be 22 or newer (or install deno 2.3+)
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-whisper.txt          # only if you want videos without captions
cp .env.example .env                             # then fill it in
```

yt-dlp needs a JavaScript runtime for YouTube: set `JS_RUNTIME=node` (or `deno`). Keep yt-dlp current:
`pip install -U "yt-dlp[default,curl-cffi]"`. YouTube changes often.

## Configure

Everything is in `.env`; `.env.example` lists every key. Secrets: `LLM_API_KEY` (Google AI Studio),
`SMTP_PASS` (a Gmail app password, not your account password; needs 2-step verification).

## Use

```bash
python -m linkdigest run                                  # poll forever
python -m linkdigest once                                 # poll once, process, exit
python -m linkdigest test URL "your note" --dry-run       # one link, writes out/*.html, sends nothing
python -m linkdigest probe URL --download                 # check what yt-dlp can fetch
python -m linkdigest extract URL                          # see the transcript and frames the model gets
```

`links.csv` has the header `url,notes,status,detail`. Add a row with a url and optionally a note. A row with
an empty status is new. Clear the status of a finished row to run it again. Links may omit `https://`.

## Rules for the CSV

Do not keep `links.csv` open in an editor that locks or rewrites the file (Excel on Windows locks it; the
service then keeps the status in its database and writes it when the file is free). The service rewrites the
whole file for each status update, so save your own edits before the next poll. Use plain comma-separated
UTF-8 CSV. Do not put the CSV or `jobs.db` in a Dropbox, OneDrive or Syncthing folder that makes conflict
copies; `jobs.db` must be on a local disk.

## Limits you should know

- **YouTube from a server.** From datacenter IPs YouTube often answers "Sign in to confirm you are not a
  bot". Set `YTDLP_COOKIES` to a `cookies.txt` exported from a browser, or run the service from a home
  connection. Cookies from your real account can get the account flagged; prefer a throwaway account.
- **Instagram.** Reels frequently fail without a login. The failure is written to the CSV and the email with
  a plain reason. Cookies help but risk the account and still hit rate limits. A failure never blocks other
  jobs; a blocked reel is retried once, after the others.
- **Privacy.** The Gemini free tier may use what you send (transcripts, frames, your notes) to improve
  Google products and humans may review it. Do not use it for content you cannot share. Use
  `LLM_PROVIDER=ollama` to keep everything local (slow on CPU). `JINA_FALLBACK=true` sends the page URL to
  r.jina.ai to read JavaScript pages; it is off by default.
- **Language.** Whisper `base` is fine for English and weak for Hindi and mixed Hindi/English speech. Such
  videos get a banner. Use `WHISPER_MODEL=small` for better accuracy at about three times the time.
- **Model names change.** If the log shows an LLM `HTTP 404`, check the current free model name at
  ai.google.dev/gemini-api/docs/pricing and update `LLM_MODEL`.
- **Mail to yourself** may skip the Inbox in Gmail. Add a filter (from:me to:me, never send to spam) or use a
  different `MAIL_TO`.

## Run as a service (Linux)

Copy `deploy/linkdigest.service`, edit the paths and user, then:

```bash
sudo cp deploy/linkdigest.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now linkdigest
journalctl -u linkdigest -f
```

## Tests

```bash
python tests/run_all.py          # offline, no network, no keys
python tests/test_offline.py     # the full-cycle test
python smoke.py                  # real links from .env, dry run
python smoke_ig.py               # Instagram success rate, with and without cookies
```
````

- [ ] **Step 2: Write `deploy/linkdigest.service`**

```ini
[Unit]
Description=linkdigest worker
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=CHANGE_ME
WorkingDirectory=/home/CHANGE_ME/linkdigest
ExecStart=/home/CHANGE_ME/linkdigest/.venv/bin/python -m linkdigest run
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 3: Run the hygiene test.** `python tests/test_hygiene.py` expect `PASS` (README has no em dash, `.env.example` has no secrets).

- [ ] **Step 4: Execute every README command once** (`once --dry-run`, `test ... --dry-run`, `probe --download`, `extract`, the four test commands) and fix any README line that is wrong. A README command that was not run does not ship.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "docs: README and systemd unit"
```

---

### Gate 6: Instagram measured honestly, release candidate

Stop and report. This is the final gate.

**Needs from the user:** 2 or 3 public reel URLs in `TEST_INSTAGRAM_URL` (comma separated), a decision on cookies (a `cookies.txt` from a throwaway logged-in profile, path in `YTDLP_COOKIES`), and, if the service will run on a Linux server, access to run the Linux checklist below.

- [ ] **Step 1: Full regression.** `python tests/run_all.py` and `python tests/test_offline.py` both `PASS`.

- [ ] **Step 2: Instagram matrix without cookies.** Leave `YTDLP_COOKIES` empty and run `python smoke_ig.py`. Expected: a table with one row per reel (DONE, BLOCKED or FAILED with the mapped message, never UNMAPPED) and the line `no cookies: N/M reels produced a digest`. If any row is UNMAPPED, do Task 16 Step 6, then rerun.

- [ ] **Step 3: Instagram matrix with cookies** (only if the user supplied them). Set `YTDLP_COOKIES`, rerun, record `cookies: N/M`. Warn the user that this uses a logged-in session.

- [ ] **Step 4: Confirm failures never block the worker on real data.** Build a CSV with the reels first, then the YouTube and blog links, and run `python -m linkdigest once --dry-run`. Expected: the YouTube and blog digests exist, every reel row is `done` or `failed` with a mapped reason, each blocked reel appears in the log exactly twice (first try and the single retry, after the other jobs), the command exits normally.

- [ ] **Step 5: Long-run check.** Start `python -m linkdigest run --dry-run` with `POLL_SECONDS=30`, add two rows while it runs, wait three polls, stop it. Expected: rows processed once, no repeated work, no growth in `out/` after they finish.

- [ ] **Step 6: Linux checklist** (skip with a clear note if the user has no server yet). On the Linux host: `sudo apt install ffmpeg python3-venv nodejs`, `node --version` shows 22 or newer, create the venv, install both requirements files, `python tests/run_all.py` is `PASS`, `python smoke.py` and `python smoke_ig.py` are run from the server's own IP. This is the only test that answers whether YouTube blocks the server; report it plainly. Install the systemd unit and confirm `systemctl status linkdigest` is active after a reboot.

- [ ] **Step 7: Whole-branch review.** Dispatch a fresh reviewer on the most capable available model over the entire branch (`git diff` from the first commit). Brief: "Review the whole linkdigest repository against linkdigest_handoff_prompt.md Part 2 and research.md. Look for: spec requirements without a test, error paths that can crash the worker or leak a secret, behaviour that differs from the README, unused code, dependency creep. Report only real defects with the failing scenario." Fix every real finding with a test, rerun everything.

- [ ] **Step 8: Final hygiene.** `python tests/test_hygiene.py` passes. `git status` shows no `.env`, `links.csv`, `jobs.db` or `out/` tracked (`git ls-files | grep -E "\.env$|links.csv|\.db$|^out/"` prints nothing).

- [ ] **Step 9: Tag and report.**

```bash
git add -A
git commit -m "test: gate 6 fixes"
git tag v0.1.0
```

Final report to the user: the Instagram success rate with and without cookies (counts, not adjectives), the exact failure messages seen, per-job timings for a captioned video, an uncaptioned video and a blog on this machine, the Linux result or the fact that it was not run, what the review found and fixed, and the list of known limitations copied from the README. State clearly what was not verified.
