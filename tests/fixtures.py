"""Shared test helpers. Fakes only the network edges."""
import pathlib
import random

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


ROLLING_VTT = """WEBVTT
Kind: captions
Language: en

00:00:01.000 --> 00:00:03.000 align:start position:0%
hello and welcome<00:00:01.500><c> to</c><00:00:02.000><c> the</c>

00:00:03.000 --> 00:00:03.010 align:start position:0%
hello and welcome to the

00:00:03.010 --> 00:00:05.000 align:start position:0%
hello and welcome to the
today we install<00:00:04.000><c> the</c>

00:00:05.000 --> 00:00:06.000 align:start position:0%
today we install the
dependencies first

00:01:05.000 --> 00:01:07.000 align:start position:0%
dependencies first
run pip install requests
"""

ROLLING_EXPECTED = [(1.0, "hello and welcome to the"), (3.01, "today we install the"),
                    (5.0, "dependencies first"), (65.0, "run pip install requests")]


def make_video(dirpath, seeds=(1, 2, 3), seconds=4):
    """Silent video: one still per seed, each shown for `seconds`. Random blocky stills have far-apart dHashes."""
    from PIL import Image, ImageDraw
    d = pathlib.Path(dirpath)
    paths = []
    for seed in seeds:
        rnd = random.Random(seed)
        im = Image.new("L", (324, 240))
        draw = ImageDraw.Draw(im)
        for r in range(8):
            for c in range(9):
                draw.rectangle([c * 36, r * 30, c * 36 + 35, r * 30 + 29], fill=rnd.randint(0, 255))
        p = d / f"s{seed}.png"
        im.convert("RGB").save(p)
        paths.append(p)
    out = d / "synthetic.mp4"
    args = []
    for p in paths:
        args += ["-loop", "1", "-t", str(seconds), "-i", str(p)]
    n = len(paths)
    chain = "".join(f"[{i}:v]" for i in range(n)) + f"concat=n={n}:v=1:a=0,format=yuv420p"
    from linkdigest.util import run_ffmpeg
    run_ffmpeg([*args, "-filter_complex", chain, "-r", "25", str(out)])
    return out
