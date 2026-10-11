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
