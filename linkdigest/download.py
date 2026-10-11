import io
from dataclasses import dataclass, field
from pathlib import Path

import requests
from PIL import Image
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from .errors import Blocked, ProcessingError
from .util import log

IG_BLOCKED = ("Instagram blocked the download (login wall or rate limit), or the reel was removed. "
              "Set YTDLP_COOKIES to a cookies.txt from a logged-in browser, or retry later.")
YT_BOT = "YouTube asked for bot verification. Run pip install -U yt-dlp or set YTDLP_COOKIES."
YT_AGE = "Video is age-restricted. Set YTDLP_COOKIES to a cookies.txt from a logged-in browser."

_NOT_VIDEO = (".vtt", ".srt", ".ttml", ".json3", ".json", ".part", ".ytdl", ".jpg", ".webp", ".png")
FORMAT = "bv*[height<=480]+ba/b[height<=480]/b"
_IG = ("login required", "login page", "rate-limit", "rate limit", "empty media",
       "http error 401", "http error 403", "requested content is not available")
_TRANSIENT = ("http error 5", "service unavailable", "subtitle", "timed out",
              "temporary failure", "connection reset")
_GONE = ("unavailable", "not available", "removed", "does not exist", "deleted",
         "no longer available", "terminated", "not found")


http_get = requests.get         # tests replace this


@dataclass
class Probe:
    title: str
    duration: "int | None"          # None when the site does not say (Instagram reels)
    media: str = "video"            # "video" | "images"
    image_urls: list = field(default_factory=list)


@dataclass
class Downloaded:
    video: Path
    vtt: "Path | None"


def _other(text):
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    last = lines[-1].strip() if lines else "unknown error"
    return ("Download failed: " + last)[:200]


def classify_error(kind, text):
    low = text.lower()
    if "confirm your age" in low:
        return "age", YT_AGE
    if "sign in to confirm" in low:
        return "bot", YT_BOT
    if kind == "instagram" and any(p in low for p in _IG):
        return "blocked", IG_BLOCKED
    if any(p in low for p in _TRANSIENT):
        return "other", _other(text)
    if "private" in low:
        return "private", "Video is private."
    if any(p in low for p in _GONE):
        return "gone", "Video is unavailable or removed."
    return "other", _other(text)


def to_exception(kind, text):
    cat, msg = classify_error(kind, text)
    if cat == "blocked":
        return Blocked(msg)
    if cat in ("bot", "private", "gone", "age") or kind == "instagram":
        return ProcessingError(msg)
    return RuntimeError(msg)        # unknown YouTube trouble: transient, the worker retries


def new_ydl(opts):
    return YoutubeDL(opts)


class _YdlLogger:
    """Keeps yt-dlp off the console; errors still arrive as DownloadError and are mapped."""
    def debug(self, msg):
        log.debug("yt-dlp: %s", msg)

    info = warning = error = debug


def _opts(cfg, **extra):
    o = {"quiet": True, "no_warnings": True, "no_color": True, "noplaylist": True,
         "socket_timeout": 20, "retries": 2, "noprogress": True, "logger": _YdlLogger()}
    if cfg.js_runtime:
        o["js_runtimes"] = {cfg.js_runtime: {}}
    if cfg.ytdlp_cookies:
        o["cookiefile"] = cfg.ytdlp_cookies
    o.update(extra)
    return o


def _best_thumbnail(entry):
    thumbs = [t for t in entry.get("thumbnails") or [] if t.get("url")]
    sized = [t for t in thumbs if t.get("width") and t.get("height")]
    if sized:
        return max(sized, key=lambda t: t["width"] * t["height"])["url"]
    return thumbs[-1]["url"] if thumbs else entry.get("url")


def _image_post(info, url):
    """Instagram result without video formats: the images of a post, or an error."""
    entries = (info.get("entries") or [info]) if info.get("_type") == "playlist" else [info]
    if any(e.get("formats") for e in entries):
        raise ProcessingError("Instagram posts with several videos are not supported.")
    urls = [u for u in map(_best_thumbnail, entries) if u]
    if not urls:
        raise ProcessingError("No downloadable video or images were found in this link.")
    return Probe(title=info.get("title") or url, duration=None, media="images", image_urls=urls)


def probe(url, kind, cfg):
    try:
        with new_ydl(_opts(cfg, skip_download=True, ignore_no_formats_error=True)) as ydl:
            info = ydl.extract_info(url, download=False)
    except DownloadError as e:
        raise to_exception(kind, str(e)) from None
    info = info or {}
    if info.get("is_live"):
        raise ProcessingError("Live streams are not supported.")
    is_playlist = info.get("_type") == "playlist"
    if kind == "instagram" and (is_playlist or not info.get("formats")):
        return _image_post(info, url)
    if is_playlist:
        raise ProcessingError("Link is a playlist, not a single video.")
    duration = info.get("duration")
    return Probe(title=info.get("title") or url, duration=int(duration) if duration else None)


def _fetch_image(url):
    try:
        r = http_get(url, timeout=20)
    except (requests.Timeout, requests.ConnectionError) as e:
        raise RuntimeError(f"Image download failed: {type(e).__name__}") from None
    if r.status_code >= 500:
        raise RuntimeError(f"Image download failed: HTTP {r.status_code}")
    if r.status_code >= 400:
        raise ProcessingError("Could not download the post images.")
    try:
        img = Image.open(io.BytesIO(r.content)).convert("RGB")
        img.thumbnail((1024, 1024))
        out = io.BytesIO()
        img.save(out, "JPEG", quality=85)
    except Exception:
        raise ProcessingError("Could not download the post images.") from None
    return out.getvalue()


def download_images(urls, dest, cfg):
    """Fetch up to cfg.max_slides images as slide-01.jpg ... Nothing is written unless all succeed."""
    blobs = [_fetch_image(u) for u in urls[: cfg.max_slides]]
    paths = []
    for i, data in enumerate(blobs, 1):
        p = Path(dest) / f"slide-{i:02d}.jpg"
        p.write_bytes(data)
        paths.append(p)
    return paths


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
    vids = [p for p in files if p.suffix not in _NOT_VIDEO]
    if not vids:
        raise ProcessingError("Download finished but no video file was found.")
    vtt = next((p for p in vtts if p.name == "v.en.vtt"), vtts[0] if vtts else None)
    return Downloaded(max(vids, key=lambda p: p.stat().st_size), vtt)
