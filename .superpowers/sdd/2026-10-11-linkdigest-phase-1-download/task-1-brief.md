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

