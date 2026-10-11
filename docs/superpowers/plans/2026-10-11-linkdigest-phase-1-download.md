# linkdigest Phase 1: Foundation and download

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Read the index `2026-10-11-linkdigest.md` first (global constraints, review focus, test strategy). Steps use checkbox syntax.

**Goal of this phase:** a runnable `python -m linkdigest probe URL [--download]` that talks to real YouTube and real Instagram, with error mapping covered by offline tests. After this phase you can already see whether Instagram reels work at all from your IP.

**Spec:** `linkdigest_handoff_prompt.md` ("Processing: video" steps 1 to 3, "Instagram failures", "Routing", "Configuration") and `research.md` (Download, section 3 items 5 and 6).

## Interfaces defined in this phase

```python
# errors.py
class Skipped(Exception): ...
class ProcessingError(Exception): ...
class Blocked(ProcessingError): ...   # Instagram login wall / rate limit, retried at most once

# util.py
log: logging.Logger
fmt_time(sec: float) -> str                 # 65 -> "1:05"
slug(text: str, n: int = 40) -> str
clip(text: str, n: int) -> str
timed(timings: dict, name: str)             # context manager, logs "step <name> took 1.2s"
run_ffmpeg(args: list[str]) -> None         # ProcessingError if ffmpeg missing, RuntimeError on failure

# config.py
load_env(path=".env") -> None
Config                                      # dataclass, see Task 2; Config.from_env(); .work_path; .mail_sender

# classify.py
classify(url: str) -> str                   # "youtube" | "instagram" | "web"
normalize_url(raw: str) -> str              # "" if not a usable http(s) link
canonical(url: str) -> str                  # stable dedupe key

# download.py
IG_BLOCKED: str; YT_BOT: str
Probe(title: str, duration: int)
Downloaded(video: Path, vtt: Path | None)
classify_error(kind: str, text: str) -> tuple[str, str]   # (category, message)
to_exception(kind: str, text: str) -> Exception
new_ydl(opts: dict)                          # tests replace this
probe(url: str, kind: str, cfg: Config) -> Probe
download(url: str, kind: str, dest: Path, cfg: Config) -> Downloaded
```

---

### Task 1: Project scaffold and hygiene test

**Files:**
- Create: `.gitignore`, `.env.example`, `requirements.txt`, `requirements-whisper.txt`, `linkdigest/__init__.py`, `tests/_run.py`, `tests/run_all.py`, `tests/test_hygiene.py`

**Interfaces:**
- Produces: `tests/_run.py` with `ROOT`, `TESTS`, `run(namespace) -> bool`, `main(namespace)`, `patched(obj, name, value)`; the test convention (functions named `test_*`, files end with `if __name__ == "__main__": _run.main(globals())`).

- [ ] **Step 1: Initialise git and the venv**

Run (Git Bash, from `C:\Users\Azeem\Desktop\LinkDigest`):

```bash
git init
python -m venv .venv
source .venv/Scripts/activate        # PowerShell: .venv\Scripts\Activate.ps1 ; Linux: source .venv/bin/activate
python -m pip install -U pip
```

Expected: `Initialized empty Git repository`, venv created, `python --version` shows 3.10 or newer.

- [ ] **Step 2: Write `.gitignore`**

```
.env
*.db
*.db-wal
*.db-shm
links.csv
out/
.venv/
__pycache__/
*.pyc
```

- [ ] **Step 3: Write `requirements.txt` and `requirements-whisper.txt`**

`requirements.txt`:

```
yt-dlp[default,curl-cffi]>=2026.08.19
trafilatura>=2.3.1
Pillow>=12.3.0
requests>=2.32
```

`requirements-whisper.txt` (optional, for videos without captions):

```
faster-whisper==1.2.1
av<17
```

- [ ] **Step 4: Write `.env.example`** (every key present, secrets blank)

```
SOURCE_CSV=./links.csv
POLL_SECONDS=120
DB_PATH=./jobs.db
WORK_DIR=
OUT_DIR=./out
DRY_RUN=false

MAX_VIDEO_SECONDS=300
LONG_VIDEO_ACTION=skip          # skip | process
FRAME_INTERVAL_SECONDS=2
MAX_FRAMES=12
FRAME_HASH_DISTANCE=10
WHISPER_MODEL=base
YTDLP_COOKIES=                  # optional path to a Netscape cookies.txt
JS_RUNTIME=node                 # node (22+) or deno (2.3+), needed by yt-dlp for YouTube

LLM_PROVIDER=gemini             # gemini | ollama
LLM_API_KEY=
LLM_MODEL=gemini-3.6-flash
LLM_FALLBACK_MODEL=gemini-3.5-flash-lite
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=gemma4:e4b
MAX_TEXT_CHARS=60000
MIN_TEXT_CHARS=500
JINA_FALLBACK=false             # true sends the page URL to r.jina.ai for JS-rendered pages

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
TEST_INSTAGRAM_URL=             # one reel URL, or several separated by commas
```

- [ ] **Step 5: Write `linkdigest/__init__.py`** (empty file) and `tests/_run.py`

```python
"""Tiny assert-based test runner. No pytest."""
import contextlib
import pathlib
import sys
import traceback

TESTS = pathlib.Path(__file__).resolve().parent
ROOT = TESTS.parent
for p in (str(ROOT), str(TESTS)):
    if p not in sys.path:
        sys.path.insert(0, p)


def run(namespace):
    ok = True
    for name, fn in list(namespace.items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
            except Exception:
                ok = False
                print(f"FAIL {name}")
                traceback.print_exc()
            else:
                print(f"ok   {name}")
    return ok


def main(namespace):
    ok = run(namespace)
    print("PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


@contextlib.contextmanager
def patched(obj, name, value):
    old = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield
    finally:
        setattr(obj, name, old)
```

`tests/run_all.py`:

```python
import importlib
import sys

import _run

ok = True
for path in sorted(_run.TESTS.glob("test_*.py")):
    print(f"== {path.stem}")
    mod = importlib.import_module(path.stem)
    ok = _run.run(vars(mod)) and ok
print("PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
```

- [ ] **Step 6: Write the failing hygiene test** `tests/test_hygiene.py`

```python
import re

import _run

ROOT = _run.ROOT
EM_DASH = "\u2014"
SCAN_DIRS = ["linkdigest", "tests"]
SCAN_FILES = ["smoke.py", "smoke_ig.py", "README.md", ".env.example", ".gitignore",
              "requirements.txt", "requirements-whisper.txt"]
SECRET_KEYS = ["LLM_API_KEY", "SMTP_USER", "SMTP_PASS", "MAIL_FROM", "MAIL_TO", "YTDLP_COOKIES"]


def project_files():
    out = []
    for d in SCAN_DIRS:
        out += [p for p in (ROOT / d).rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    out += [ROOT / f for f in SCAN_FILES if (ROOT / f).exists()]
    return out


def env_values():
    vals = {}
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            vals[k.strip()] = v.split(" #")[0].strip()
    return vals


def test_no_em_dash():
    bad = [str(p.relative_to(ROOT)) for p in project_files()
           if EM_DASH in p.read_text(encoding="utf-8", errors="ignore")]
    assert not bad, f"em dash found in {bad}"


def test_gitignore_has_required_entries():
    lines = (ROOT / ".gitignore").read_text(encoding="utf-8").split()
    for need in (".env", "*.db", "links.csv", "out/", ".venv/"):
        assert need in lines, f".gitignore is missing {need}"


def test_env_example_secrets_blank():
    vals = env_values()
    for k in SECRET_KEYS:
        assert k in vals and vals[k] == "", f"{k} must be present and blank"
    for k, v in vals.items():
        if k.startswith("TEST_"):
            assert v == "", f"{k} must be blank in the example"


def test_no_key_shaped_strings():
    pat = re.compile(r"AIza[0-9A-Za-z_\-]{20,}|sk-[A-Za-z0-9]{20,}")
    bad = [str(p.relative_to(ROOT)) for p in project_files()
           if pat.search(p.read_text(encoding="utf-8", errors="ignore"))]
    assert not bad, f"key-shaped string in {bad}"


if __name__ == "__main__":
    _run.main(globals())
```

- [ ] **Step 7: Run it**

Run: `python tests/test_hygiene.py`
Expected: four `ok` lines then `PASS`.

- [ ] **Step 8: Install runtime deps and commit**

```bash
pip install -r requirements.txt
git add -A
git commit -m "chore: scaffold, env template, test runner, hygiene test"
```

---

### Task 2: errors, util, config, classify

**Files:**
- Create: `linkdigest/errors.py`, `linkdigest/util.py`, `linkdigest/config.py`, `linkdigest/classify.py`
- Test: `tests/test_config.py`, `tests/test_classify.py`

**Interfaces:**
- Produces: everything in the "Interfaces defined in this phase" block for `errors`, `util`, `config`, `classify`.

- [ ] **Step 1: Write the failing tests**

`tests/test_classify.py`:

```python
import _run
from linkdigest.classify import canonical, classify, normalize_url


def test_classify_hosts():
    assert classify("https://www.youtube.com/watch?v=abc") == "youtube"
    assert classify("https://youtu.be/abc") == "youtube"
    assert classify("https://m.youtube.com/watch?v=abc") == "youtube"
    assert classify("https://music.youtube.com/watch?v=abc") == "youtube"
    assert classify("https://www.instagram.com/reel/C-cTZA1M9mE/") == "instagram"
    assert classify("https://instagram.com/p/abc/") == "instagram"
    assert classify("https://example.com/blog/post") == "web"
    assert classify("https://notyoutube.com/x") == "web"


def test_normalize_url():
    assert normalize_url("  youtu.be/abc  ") == "https://youtu.be/abc"
    assert normalize_url("https://example.com/a b") == "https://example.com/a b"
    assert normalize_url("hello world") == ""
    assert normalize_url("") == ""
    assert normalize_url("ftp://example.com/x") == ""
    assert normalize_url("javascript:alert(1)") == ""


def test_canonical_youtube_variants_share_one_key():
    want = "https://youtube.com/watch?v=abc123"
    for u in [
        "https://www.youtube.com/watch?v=abc123",
        "https://m.youtube.com/watch?v=abc123&t=30s",
        "https://youtu.be/abc123?si=XYZ",
        "https://www.youtube.com/shorts/abc123",
        "https://www.youtube.com/watch?v=abc123&list=PL1&index=2&utm_source=x",
    ]:
        assert canonical(u) == want, u


def test_canonical_strips_tracking_and_instagram_query():
    assert canonical("https://www.instagram.com/reel/AbC/?igsh=zzz") == "https://instagram.com/reel/AbC"
    assert canonical("https://Example.com/a/?utm_medium=x&id=5&fbclid=1#top") == "https://example.com/a?id=5"


if __name__ == "__main__":
    _run.main(globals())
```

`tests/test_config.py`:

```python
import os
import tempfile
from pathlib import Path

import _run
from linkdigest import config
from linkdigest.config import Config, load_env


def test_load_env_parses_comments_quotes_and_does_not_override():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / ".env"
        p.write_text('# c\nFOO_T1=bar  # tail\nFOO_T2="quoted value"\nFOO_T3=\nEXIST_T4=file\n', encoding="utf-8")
        os.environ["EXIST_T4"] = "real"
        try:
            load_env(str(p))
            assert os.environ["FOO_T1"] == "bar"
            assert os.environ["FOO_T2"] == "quoted value"
            assert os.environ["FOO_T3"] == ""
            assert os.environ["EXIST_T4"] == "real"
        finally:
            for k in ("FOO_T1", "FOO_T2", "FOO_T3", "EXIST_T4"):
                os.environ.pop(k, None)


def test_from_env_types_and_blank_means_default():
    os.environ.update({"POLL_SECONDS": "30", "DRY_RUN": "true", "MAX_FRAMES": "", "FRAME_INTERVAL_SECONDS": "4"})
    try:
        c = Config.from_env()
        assert c.poll_seconds == 30 and isinstance(c.poll_seconds, int)
        assert c.dry_run is True
        assert c.max_frames == 12
        assert c.frame_interval_seconds == 4.0
    finally:
        for k in ("POLL_SECONDS", "DRY_RUN", "MAX_FRAMES", "FRAME_INTERVAL_SECONDS"):
            os.environ.pop(k, None)


def test_work_path_and_sender_defaults():
    c = Config()
    assert c.work_path.name == "linkdigest"
    assert Config(smtp_user="a@b.c").mail_sender == "a@b.c"
    assert Config(smtp_user="a@b.c", mail_from="x@y.z").mail_sender == "x@y.z"


if __name__ == "__main__":
    _run.main(globals())
```

- [ ] **Step 2: Run to verify failure**

Run: `python tests/test_classify.py`
Expected: FAIL / `ModuleNotFoundError: No module named 'linkdigest.classify'`.

- [ ] **Step 3: Write `linkdigest/errors.py`**

```python
class Skipped(Exception):
    """Job is not an error but will not be processed (for example a long video)."""


class ProcessingError(Exception):
    """Permanent failure. The message is shown to the user, so keep it plain."""


class Blocked(ProcessingError):
    """Instagram login wall or rate limit. The worker retries it at most once."""
```

- [ ] **Step 4: Write `linkdigest/util.py`**

```python
import contextlib
import logging
import re
import subprocess
import time

from .errors import ProcessingError

log = logging.getLogger("linkdigest")


def fmt_time(sec):
    s = int(sec)
    return f"{s // 60}:{s % 60:02d}"


def slug(text, n=40):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (s[:n].strip("-")) or "item"


def clip(text, n):
    return text if len(text) <= n else text[: n - 3].rstrip() + "..."


@contextlib.contextmanager
def timed(timings, name):
    t0 = time.monotonic()
    try:
        yield
    finally:
        timings[name] = time.monotonic() - t0
        log.info("step %s took %.1fs", name, timings[name])


def run_ffmpeg(args):
    try:
        subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True,
                       capture_output=True, text=True, timeout=600)
    except FileNotFoundError:
        raise ProcessingError("ffmpeg is not installed. Install it with your package manager.") from None
    except subprocess.CalledProcessError as e:
        raise RuntimeError("ffmpeg failed: " + (e.stderr or "").strip()[-200:]) from None
```

- [ ] **Step 5: Write `linkdigest/config.py`**

```python
import os
import tempfile
from dataclasses import dataclass, fields
from pathlib import Path


def load_env(path=".env"):
    """Tiny .env loader. Real environment variables win over the file."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        val = val.split(" #", 1)[0].strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), val)


def _bool(v):
    return str(v).strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Config:
    source_csv: str = "./links.csv"
    poll_seconds: int = 120
    db_path: str = "./jobs.db"
    work_dir: str = ""
    out_dir: str = "./out"
    dry_run: bool = False
    max_video_seconds: int = 300
    long_video_action: str = "skip"
    frame_interval_seconds: float = 2.0
    max_frames: int = 12
    frame_hash_distance: int = 10
    whisper_model: str = "base"
    ytdlp_cookies: str = ""
    js_runtime: str = "node"
    llm_provider: str = "gemini"
    llm_api_key: str = ""
    llm_model: str = "gemini-3.6-flash"
    llm_fallback_model: str = "gemini-3.5-flash-lite"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "gemma4:e4b"
    max_text_chars: int = 60000
    min_text_chars: int = 500
    jina_fallback: bool = False
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    mail_from: str = ""
    mail_to: str = ""
    notify_on_failure: bool = True
    max_attempts: int = 3
    test_youtube_url: str = ""
    test_youtube_nocaps_url: str = ""
    test_blog_url: str = ""
    test_long_video_url: str = ""
    test_instagram_url: str = ""

    @classmethod
    def from_env(cls):
        kw = {}
        for f in fields(cls):
            raw = os.environ.get(f.name.upper())
            if raw is None or raw == "":
                continue
            kw[f.name] = _bool(raw) if f.type is bool else f.type(raw)
        return cls(**kw)

    @property
    def work_path(self):
        return Path(self.work_dir) if self.work_dir else Path(tempfile.gettempdir()) / "linkdigest"

    @property
    def mail_sender(self):
        return self.mail_from or self.smtp_user
```

- [ ] **Step 6: Write `linkdigest/classify.py`**

```python
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

_TRACK = {"fbclid", "gclid", "si", "igshid", "igsh", "feature", "mc_cid", "mc_eid"}


def _host(h):
    h = (h or "").lower()
    for prefix in ("www.", "m."):
        if h.startswith(prefix):
            h = h[len(prefix):]
    return h


def classify(url):
    host = _host(urlparse(url.strip()).hostname)
    if host in ("youtube.com", "youtu.be") or host.endswith(".youtube.com"):
        return "youtube"
    if host == "instagram.com" or host.endswith(".instagram.com"):
        return "instagram"
    return "web"


def normalize_url(raw):
    """Return a usable http(s) URL, or '' if the text is not a link."""
    u = raw.strip()
    if not u:
        return ""
    if "://" not in u:
        u = "https://" + u
    p = urlparse(u)
    if p.scheme not in ("http", "https") or not p.hostname or "." not in p.hostname:
        return ""
    return u


def canonical(url):
    """Stable key: the same video or page maps to one key whatever the tracking params."""
    p = urlparse(url.strip())
    host = _host(p.hostname)
    path = p.path.rstrip("/")
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
         if k not in _TRACK and not k.startswith("utm_")]
    kind = classify(url)
    if kind == "youtube":
        vid = None
        if host == "youtu.be":
            vid = path.lstrip("/").split("/")[0]
        elif path.split("/")[1:2] in (["shorts"], ["embed"], ["live"]) and len(path.split("/")) > 2:
            vid = path.split("/")[2]
        else:
            vid = dict(q).get("v")
        if vid:
            return f"https://youtube.com/watch?v={vid}"
    if kind == "instagram":
        q = []
    return urlunparse(("https", host, path, "", urlencode(sorted(q)), ""))
```

- [ ] **Step 7: Run all tests**

Run: `python tests/run_all.py`
Expected: every test `ok`, final `PASS`.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat: errors, util, config, url classify and canonical key"
```

---

### Task 3: download.py (probe, download, error mapping)

**Files:**
- Create: `linkdigest/download.py`, `tests/fixtures.py` (fake yt-dlp part only, extended later)
- Test: `tests/test_download.py`

**Interfaces:**
- Consumes: `Config` (`.js_runtime`, `.ytdlp_cookies`), `ProcessingError`, `Blocked`, `classify`.
- Produces: `probe`, `download`, `classify_error`, `to_exception`, `IG_BLOCKED`, `YT_BOT`, `Probe`, `Downloaded`, `new_ydl`.

Error policy (from `research.md`): Instagram login wall, rate limit, 401/403, "empty media" all map to `Blocked` (retry once). The empty-media text also appears for a deleted reel, so the message says "or the reel was removed". YouTube "Sign in to confirm your age" is NOT a bot check. Unrecognised Instagram errors are permanent (never hammer Instagram). Unrecognised YouTube errors are transient (`RuntimeError`).

- [ ] **Step 1: Write the fake yt-dlp in `tests/fixtures.py`**

```python
"""Shared test helpers. Fakes only the network edges."""
import pathlib

import _run  # noqa: F401  (sets sys.path)
from yt_dlp.utils import DownloadError


class FakeYDL:
    """Stands in for yt_dlp.YoutubeDL. Configure through the class attributes of a subclass."""
    info = {"title": "Fake title", "duration": 60, "is_live": False}
    probe_error = None            # str: raise DownloadError on extract_info
    download_errors = []          # list of str, one consumed per download() call
    write_vtt = True
    calls = []

    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download=False):
        type(self).calls.append(("probe", dict(self.opts)))
        if self.probe_error:
            raise DownloadError(self.probe_error)
        return dict(self.info)

    def download(self, urls):
        type(self).calls.append(("download", dict(self.opts)))
        if type(self).download_errors:
            raise DownloadError(type(self).download_errors.pop(0))
        out = pathlib.Path(self.opts["outtmpl"].replace("%(ext)s", "mp4"))
        out.write_bytes(self.video_bytes())
        if self.opts.get("writesubtitles") and self.write_vtt:
            out.with_name("v.en.vtt").write_text(self.vtt_text(), encoding="utf-8")

    def video_bytes(self):
        return b"fake-video"

    def vtt_text(self):
        return "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nhello\n"


def fake_ydl(**attrs):
    """Build a fresh FakeYDL subclass with overridden class attributes."""
    attrs.setdefault("calls", [])
    attrs.setdefault("download_errors", [])
    return type("F", (FakeYDL,), attrs)
```

- [ ] **Step 2: Write the failing tests** `tests/test_download.py`

```python
import tempfile
from pathlib import Path

import _run
from fixtures import fake_ydl
from linkdigest import download
from linkdigest.config import Config
from linkdigest.errors import Blocked, ProcessingError

# Real yt-dlp text measured in research (2026-10-11). Add new real strings here as they are found.
IG_EMPTY_MEDIA = ("ERROR: [Instagram] C-cTZA1M9mE: Instagram sent an empty media response. "
                  "Check if this post is accessible in your browser without being logged-in. "
                  "If it is not, then use --cookies-from-browser or --cookies")
IG_RATE = "ERROR: [Instagram] x: Requested content is not available, rate-limit reached or login required"
YT_BOT = "ERROR: [youtube] x: Sign in to confirm you\u2019re not a bot. Use --cookies-from-browser"
YT_AGE = "ERROR: [youtube] x: Sign in to confirm your age. This video may be inappropriate for some users."
YT_PRIVATE = "ERROR: [youtube] x: Private video. Sign in if you've been granted access to this video"
YT_GONE = "ERROR: [youtube] x: This video is unavailable"


def cfg(**kw):
    return Config(**kw)


def test_error_mapping_categories():
    assert download.classify_error("instagram", IG_EMPTY_MEDIA)[0] == "blocked"
    assert download.classify_error("instagram", IG_RATE)[0] == "blocked"
    assert download.classify_error("instagram", "HTTP Error 403: Forbidden")[0] == "blocked"
    assert download.classify_error("youtube", YT_BOT) == ("bot", download.YT_BOT)
    assert download.classify_error("youtube", YT_AGE)[0] == "age"
    assert download.classify_error("youtube", YT_PRIVATE) == ("private", "Video is private.")
    assert download.classify_error("youtube", YT_GONE) == ("gone", "Video is unavailable or removed.")
    cat, msg = download.classify_error("youtube", "ERROR: something odd\nlast line here")
    assert cat == "other" and msg == "Download failed: last line here"
    assert len(download.classify_error("youtube", "x" * 500)[1]) <= 200


def test_exception_types():
    assert isinstance(download.to_exception("instagram", IG_EMPTY_MEDIA), Blocked)
    assert type(download.to_exception("youtube", YT_BOT)) is ProcessingError
    assert type(download.to_exception("youtube", YT_PRIVATE)) is ProcessingError
    # unknown youtube error is transient, unknown instagram error is permanent (never hammer Instagram)
    assert type(download.to_exception("youtube", "weird")) is RuntimeError
    assert type(download.to_exception("instagram", "weird")) is ProcessingError


def test_probe_ok_and_options():
    F = fake_ydl(info={"title": "T", "duration": 125.4, "is_live": False})
    with _run.patched(download, "new_ydl", F):
        p = download.probe("https://youtu.be/abc", "youtube", cfg(ytdlp_cookies="c.txt"))
    assert p.title == "T" and p.duration == 125
    opts = F.calls[0][1]
    assert opts["skip_download"] is True and opts["noplaylist"] is True
    assert opts["js_runtimes"] == {"node": {}} and opts["cookiefile"] == "c.txt"


def test_probe_rejects_live_playlist_and_missing_duration():
    for info, word in [({"title": "x", "duration": None, "is_live": True}, "Live"),
                       ({"title": "x", "duration": None, "is_live": False, "_type": "playlist"}, "playlist"),
                       ({"title": "x", "duration": None, "is_live": False}, "length")]:
        with _run.patched(download, "new_ydl", fake_ydl(info=info)):
            try:
                download.probe("https://youtu.be/abc", "youtube", cfg())
            except ProcessingError as e:
                assert word in str(e), str(e)
            else:
                raise AssertionError("expected ProcessingError")


def test_probe_maps_instagram_block():
    with _run.patched(download, "new_ydl", fake_ydl(probe_error=IG_EMPTY_MEDIA)):
        try:
            download.probe("https://www.instagram.com/reel/x/", "instagram", cfg())
        except Blocked as e:
            assert str(e) == download.IG_BLOCKED
        else:
            raise AssertionError("expected Blocked")


def test_download_finds_video_and_vtt():
    F = fake_ydl()
    with tempfile.TemporaryDirectory() as d, _run.patched(download, "new_ydl", F):
        r = download.download("https://youtu.be/abc", "youtube", Path(d), cfg())
        assert r.video.name == "v.mp4" and r.vtt is not None and r.vtt.name == "v.en.vtt"
    opts = F.calls[-1][1]
    assert opts["subtitleslangs"] == ["en", "en-orig"]       # never a wildcard
    assert opts["format"].startswith("bv*[height<=480]")


def test_download_retries_without_subs_on_unknown_error_only():
    F = fake_ydl(download_errors=["ERROR: unable to download subtitle: HTTP Error 429"])
    with tempfile.TemporaryDirectory() as d, _run.patched(download, "new_ydl", F):
        r = download.download("https://youtu.be/abc", "youtube", Path(d), cfg())
        assert r.vtt is None
    assert [c[0] for c in F.calls] == ["download", "download"]
    assert F.calls[1][1].get("writesubtitles") is not True

    F = fake_ydl(download_errors=[YT_PRIVATE])
    with tempfile.TemporaryDirectory() as d, _run.patched(download, "new_ydl", F):
        try:
            download.download("https://youtu.be/abc", "youtube", Path(d), cfg())
        except ProcessingError as e:
            assert "private" in str(e)
        else:
            raise AssertionError("expected ProcessingError")
    assert len(F.calls) == 1            # a permanent error is not retried


if __name__ == "__main__":
    _run.main(globals())
```

- [ ] **Step 3: Run to verify failure**

Run: `python tests/test_download.py`
Expected: `ModuleNotFoundError: No module named 'linkdigest.download'`.

- [ ] **Step 4: Write `linkdigest/download.py`**

```python
from dataclasses import dataclass
from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from .errors import Blocked, ProcessingError
from .util import log

IG_BLOCKED = ("Instagram blocked the download (login wall or rate limit), or the reel was removed. "
              "Set YTDLP_COOKIES to a cookies.txt from a logged-in browser, or retry later.")
YT_BOT = "YouTube asked for bot verification. Run pip install -U yt-dlp or set YTDLP_COOKIES."
YT_AGE = "Video is age-restricted. Set YTDLP_COOKIES to a cookies.txt from a logged-in browser."

FORMAT = "bv*[height<=480]+ba/b[height<=480]/b"
_IG = ("login required", "login page", "rate-limit", "rate limit", "empty media",
       "http error 401", "http error 403", "requested content is not available")
_GONE = ("unavailable", "not available", "removed", "does not exist", "deleted",
         "no longer available", "terminated", "not found")


@dataclass
class Probe:
    title: str
    duration: int


@dataclass
class Downloaded:
    video: Path
    vtt: "Path | None"


def classify_error(kind, text):
    low = text.lower()
    if "confirm your age" in low:
        return "age", YT_AGE
    if "sign in to confirm" in low:
        return "bot", YT_BOT
    if kind == "instagram" and any(p in low for p in _IG):
        return "blocked", IG_BLOCKED
    if "private" in low:
        return "private", "Video is private."
    if any(p in low for p in _GONE):
        return "gone", "Video is unavailable or removed."
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    last = lines[-1].strip() if lines else "unknown error"
    return "other", ("Download failed: " + last)[:200]


def to_exception(kind, text):
    cat, msg = classify_error(kind, text)
    if cat == "blocked":
        return Blocked(msg)
    if cat in ("bot", "private", "gone", "age") or kind == "instagram":
        return ProcessingError(msg)
    return RuntimeError(msg)        # unknown YouTube trouble: transient, the worker retries


def new_ydl(opts):
    return YoutubeDL(opts)


def _opts(cfg, **extra):
    o = {"quiet": True, "no_warnings": True, "no_color": True, "noplaylist": True,
         "socket_timeout": 20, "retries": 2}
    if cfg.js_runtime:
        o["js_runtimes"] = {cfg.js_runtime: {}}
    if cfg.ytdlp_cookies:
        o["cookiefile"] = cfg.ytdlp_cookies
    o.update(extra)
    return o


def probe(url, kind, cfg):
    try:
        with new_ydl(_opts(cfg, skip_download=True)) as ydl:
            info = ydl.extract_info(url, download=False)
    except DownloadError as e:
        raise to_exception(kind, str(e)) from None
    if info.get("is_live"):
        raise ProcessingError("Live streams are not supported.")
    if info.get("_type") == "playlist":
        raise ProcessingError("Link is a playlist, not a single video.")
    if not info.get("duration"):
        raise ProcessingError("Could not read the video length.")
    return Probe(title=info.get("title") or url, duration=int(info["duration"]))


def download(url, kind, dest, cfg):
    dest = Path(dest)
    for with_subs in (True, False):
        extra = {"format": FORMAT, "outtmpl": str(dest / "v.%(ext)s")}
        if with_subs:
            extra.update(writesubtitles=True, writeautomaticsub=True,
                         subtitleslangs=["en", "en-orig"], subtitlesformat="vtt/best")
        try:
            with new_ydl(_opts(cfg, **extra)) as ydl:
                ydl.download([url])
            break
        except DownloadError as e:
            exc = to_exception(kind, str(e))
            if with_subs and type(exc) is RuntimeError:
                log.warning("download with subtitles failed, retrying without: %s", exc)
                continue
            raise exc from None
    files = [p for p in dest.iterdir() if p.name.startswith("v.")]
    vtts = sorted(p for p in files if p.suffix == ".vtt")
    vids = [p for p in files if p.suffix not in (".vtt", ".part", ".ytdl", ".json")]
    if not vids:
        raise ProcessingError("Download finished but no video file was found.")
    vtt = next((p for p in vtts if p.name == "v.en.vtt"), vtts[0] if vtts else None)
    return Downloaded(max(vids, key=lambda p: p.stat().st_size), vtt)
```

- [ ] **Step 5: Run all tests**

Run: `python tests/run_all.py`
Expected: all `ok`, `PASS`.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: yt-dlp probe and download with mapped errors"
```

---

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
