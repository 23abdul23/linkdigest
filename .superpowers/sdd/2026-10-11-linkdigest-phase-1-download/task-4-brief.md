### Task 4: CLI skeleton with `probe`

**Files:**
- Create: `linkdigest/__main__.py`
- Test: `tests/test_download.py` (append one CLI test)

**Interfaces:**
- Consumes: `Config.from_env`, `load_env`, `classify`, `normalize_url`, `probe`, `download`, `fmt_time`.
- Produces: `main(argv=None) -> int`, `cmd_probe(cfg, url, do_download) -> int`. Later tasks add subcommands to `build_parser()` and `main()`.

- [ ] **Step 1: Append the failing test to `tests/test_download.py`** (before the `__main__` block)

```python
def test_cli_probe_prints_info_and_cleans_up():
    import io
    import contextlib
    from linkdigest import __main__ as cli
    F = fake_ydl(info={"title": "Hello", "duration": 65, "is_live": False})
    buf = io.StringIO()
    with tempfile.TemporaryDirectory() as d, _run.patched(download, "new_ydl", F), contextlib.redirect_stdout(buf):
        rc = cli.cmd_probe(cfg(work_dir=d), "youtu.be/abc", True)
        assert not list(Path(d).glob("job-*")), "temp dir must be removed"
    out = buf.getvalue()
    assert rc == 0 and "kind=youtube" in out and "1:05" in out and "captions=yes" in out


def test_cli_probe_reports_mapped_instagram_error_not_traceback():
    import io
    import contextlib
    from linkdigest import __main__ as cli
    buf = io.StringIO()
    with _run.patched(download, "new_ydl", fake_ydl(probe_error=IG_EMPTY_MEDIA)), contextlib.redirect_stdout(buf):
        rc = cli.cmd_probe(cfg(), "https://www.instagram.com/reel/x/", False)
    out = buf.getvalue()
    assert rc == 1 and "Blocked" in out and "Traceback" not in out
```

- [ ] **Step 2: Run to verify failure**

Run: `python tests/test_download.py`
Expected: `ImportError ... cannot import name '__main__'` or missing `cmd_probe`.

- [ ] **Step 3: Write `linkdigest/__main__.py`**

```python
import argparse
import logging
import shutil
import sys
import tempfile
from pathlib import Path

from .classify import classify, normalize_url
from .config import Config, load_env
from .download import download, probe
from .util import fmt_time, log


def cmd_probe(cfg, url, do_download):
    """Probe a link (and optionally download it) and print what yt-dlp saw. For manual checks."""
    link = normalize_url(url)
    if not link:
        print("Not a valid link.")
        return 1
    kind = classify(link)
    try:
        p = probe(link, kind, cfg)
    except Exception as e:                      # show the class so mapped vs unmapped is visible
        print(f"{type(e).__name__}: {e}")
        return 1
    print(f"kind={kind} title={p.title!r} duration={fmt_time(p.duration)} ({p.duration}s)")
    if not do_download:
        return 0
    cfg.work_path.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="job-", dir=cfg.work_path))
    try:
        d = download(link, kind, tmp, cfg)
        print(f"downloaded={d.video.name} bytes={d.video.stat().st_size} captions={'yes' if d.vtt else 'no'}")
        return 0
    except Exception as e:
        print(f"{type(e).__name__}: {e}")
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build_parser():
    ap = argparse.ArgumentParser(prog="linkdigest")
    ap.add_argument("--dry-run", action="store_true", help="write emails to OUT_DIR instead of sending")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("probe", help="probe a video link, optionally download it")
    p.add_argument("url")
    p.add_argument("--download", action="store_true")
    return ap


def main(argv=None):
    load_env()
    args = build_parser().parse_args(argv)
    cfg = Config.from_env()
    if args.dry_run:
        cfg.dry_run = True
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.cmd == "probe":
        return cmd_probe(cfg, args.url, args.download)
    return 2


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run all tests**

Run: `python tests/run_all.py`
Expected: all `ok`, `PASS`.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: linkdigest probe command"
```

---

### Gate 1: download works on real YouTube and real Instagram

Stop here and report to the user. Do not start Phase 2 until the user says OK.

**Needs from the user:** the URLs in the index table row "Gate 1". Put them in `.env` (copy `.env.example` to `.env`) as `TEST_YOUTUBE_URL`, `TEST_YOUTUBE_NOCAPS_URL`, `TEST_LONG_VIDEO_URL`, `TEST_INSTAGRAM_URL` (comma-separated for several reels). Optional: `YTDLP_COOKIES`.

- [ ] **Step 1: Regression.** Run `python tests/run_all.py`. Expected `PASS`.

- [ ] **Step 2: Confirm the toolchain.** Run `python -c "import yt_dlp; print(yt_dlp.version.__version__)"` (expect 2026.08.19 or newer), `ffmpeg -version`, `node --version` (22 or newer, or set `JS_RUNTIME=deno`).

- [ ] **Step 3: YouTube with captions, probe then download.**

```bash
python -m linkdigest probe "<TEST_YOUTUBE_URL>"
python -m linkdigest probe "<TEST_YOUTUBE_URL>" --download
```

Expected: `kind=youtube title=... duration=m:ss`, then `downloaded=v.<ext> bytes=<n> captions=yes`. FAIL if a Python traceback appears, or captions=no for a video the user says has captions.

- [ ] **Step 4: YouTube without captions.** Same with `TEST_YOUTUBE_NOCAPS_URL`. Expected `captions=no`, no error.

- [ ] **Step 5: Long video.** `python -m linkdigest probe "<TEST_LONG_VIDEO_URL>"` (no `--download`). Expected a duration over 5:00 and nothing downloaded.

- [ ] **Step 6: YouTube variants (Review Focus 2).** Probe the same video as `youtu.be/<id>`, `...watch?v=<id>&list=<any playlist id>`, and `.../shorts/<id>` if a short is available. Expected: each prints one video, never a playlist.

- [ ] **Step 7: Instagram, no cookies.** For each reel in `TEST_INSTAGRAM_URL`:

```bash
python -m linkdigest probe "<reel url>" --download
```

Record per reel: success, or the exact line printed. Expected outcome is either success, or `Blocked: Instagram blocked the download ...`. FAIL only if the output is a traceback or an unmapped class (`RuntimeError`, `DownloadError`). Wait about 20 seconds between reels, since rate limits are part of what is being measured.

- [ ] **Step 8: Instagram, with cookies (only if the user supplied `cookies.txt`).** Set `YTDLP_COOKIES` in `.env`, repeat Step 7, record the difference. Warn the user that logged-in cookies risk the account (`research.md`).

- [ ] **Step 9: Capture real strings.** Run Step 7 once with `python -m linkdigest probe "<reel>" 2>&1` plus `--download`, copy any raw yt-dlp error text that is not in `tests/test_download.py` into a new constant there, and add an assertion that it maps to the expected category. Rerun `python tests/run_all.py`.

- [ ] **Step 10: Review.** Dispatch a fresh reviewer on the Phase 1 diff (`git diff` from the first commit) with this brief: "Check error mapping order, any path where a raw traceback or a secret could reach output, the temp-dir cleanup in `cmd_probe`, Windows and Linux path safety. Report only real defects." Apply real findings, rerun tests.

- [ ] **Step 11: Tag and report.**

```bash
git add -A
git commit -m "test: record real yt-dlp error strings"
git tag gate-1
```

Report to the user: offline test output, the table of live results (URL type, outcome, seconds), the Instagram success count with and without cookies, review findings and what was patched. Ask for the OK to start Phase 2.
