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


def jpeg_bytes(size=(64, 48), color=(200, 30, 30), fmt="JPEG"):
    """Real small image bytes made with Pillow."""
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, fmt)
    return buf.getvalue()


class FakeResponse:
    def __init__(self, status=200, content=b""):
        self.status_code = status
        self.content = content


def fake_get(responses, calls=None):
    """Fake requests.get. responses: url -> FakeResponse or an exception instance to raise."""
    def get(url, timeout=None, **kw):
        if calls is not None:
            calls.append((url, timeout))
        r = responses[url]
        if isinstance(r, Exception):
            raise r
        return r
    return get


def ig_post_info(n=3, **entry_extra):
    """Instagram carousel as yt-dlp returns it: a playlist of entries with thumbnails and no formats."""
    entries = [{"id": f"e{i}", "title": "Post", "thumbnails": [
        {"url": f"https://cdn/{i}-small.jpg", "width": 100, "height": 100},
        {"url": f"https://cdn/{i}-big.jpg", "width": 1080, "height": 1350}], **entry_extra}
        for i in range(1, n + 1)]
    return {"_type": "playlist", "title": "Post by someone", "entries": entries}
