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

