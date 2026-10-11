import tempfile
from pathlib import Path

import _run
from fixtures import FakeResponse, fake_get, fake_ydl, ig_post_info, jpeg_bytes
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


def test_probe_rejects_live_and_playlist():
    for info, word in [({"title": "x", "duration": None, "is_live": True}, "Live"),
                       ({"title": "x", "duration": None, "is_live": False, "_type": "playlist"}, "playlist")]:
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


def test_transient_errors_are_not_gone():
    r503 = "ERROR: unable to download: HTTP Error 503: Service Unavailable"
    assert download.classify_error("youtube", r503)[0] == "other"
    assert type(download.to_exception("youtube", r503)) is RuntimeError
    sub404 = "ERROR: Unable to download video subtitles for 'en': HTTP Error 404: Not Found"
    assert download.classify_error("youtube", sub404)[0] == "other"
    F = fake_ydl(download_errors=[sub404])
    with tempfile.TemporaryDirectory() as d, _run.patched(download, "new_ydl", F):
        r = download.download("https://youtu.be/abc", "youtube", Path(d), cfg())
        assert r.vtt is None and r.video.name == "v.mp4"
    assert [c[0] for c in F.calls] == ["download", "download"]


def test_probe_none_info():
    class N(fake_ydl()):
        def extract_info(self, url, download=False):
            return None
    with _run.patched(download, "new_ydl", N):
        p = download.probe("https://youtu.be/abc", "youtube", cfg())
    assert p.duration is None and p.media == "video"


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


def test_opts_silence_ytdlp_console():
    import contextlib
    import io
    o = download._opts(cfg())
    assert o["noprogress"] is True
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        for m in ("debug", "info", "warning", "error"):
            getattr(o["logger"], m)("ERROR: [Instagram] x")
    assert out.getvalue() == "" and err.getvalue() == ""


def test_probe_verbose_flag():
    from linkdigest import __main__ as cli
    assert cli.build_parser().parse_args(["probe", "https://youtu.be/x", "--verbose"]).verbose is True


def test_probe_unknown_duration_is_not_an_error():
    F = fake_ydl(info={"title": "Reel", "is_live": False, "formats": [{"url": "u"}]})
    with _run.patched(download, "new_ydl", F):
        p = download.probe("https://www.instagram.com/reel/x/", "instagram", cfg())
    assert p.duration is None and p.media == "video" and p.image_urls == []
    assert F.calls[0][1]["ignore_no_formats_error"] is True


def test_probe_instagram_carousel_returns_largest_thumbnails_in_order():
    with _run.patched(download, "new_ydl", fake_ydl(info=ig_post_info(3))):
        p = download.probe("https://www.instagram.com/p/x/", "instagram", cfg())
    assert p.media == "images" and p.duration is None and p.title == "Post by someone"
    assert p.image_urls == [f"https://cdn/{i}-big.jpg" for i in (1, 2, 3)]


def test_probe_thumbnail_fallbacks():
    info = {"_type": "playlist", "title": "t", "entries": [
        {"thumbnails": [{"url": "https://cdn/a.jpg"}, {"url": "https://cdn/b.jpg"}]},
        {"thumbnails": [{"url": "https://cdn/c.jpg", "width": 5, "height": 5}]}]}
    with _run.patched(download, "new_ydl", fake_ydl(info=info)):
        p = download.probe("https://www.instagram.com/p/x/", "instagram", cfg())
    assert p.image_urls == ["https://cdn/b.jpg", "https://cdn/c.jpg"]     # last listed when no sizes, else largest


def test_probe_single_image_post():
    info = {"title": "One", "thumbnails": [{"url": "https://cdn/s.jpg", "width": 10, "height": 10}]}
    with _run.patched(download, "new_ydl", fake_ydl(info=info)):
        p = download.probe("https://www.instagram.com/p/x/", "instagram", cfg())
    assert p.media == "images" and p.image_urls == ["https://cdn/s.jpg"]


def expect_error(fn, text):
    try:
        fn()
    except ProcessingError as e:
        assert text in str(e), str(e)
    else:
        raise AssertionError("expected ProcessingError")


def test_probe_instagram_video_carousel_and_empty_are_rejected():
    info = ig_post_info(2)
    info["entries"][0]["formats"] = [{"url": "v"}]
    with _run.patched(download, "new_ydl", fake_ydl(info=info)):
        expect_error(lambda: download.probe("https://www.instagram.com/p/x/", "instagram", cfg()),
                     "several videos are not supported")
    for empty in ({"title": "x"}, {"_type": "playlist", "title": "x", "entries": [{}]}):
        with _run.patched(download, "new_ydl", fake_ydl(info=empty)):
            expect_error(lambda: download.probe("https://www.instagram.com/p/x/", "instagram", cfg()),
                         "No downloadable video or images")


def test_non_instagram_playlist_keeps_old_error():
    with _run.patched(download, "new_ydl", fake_ydl(info=ig_post_info(2))):
        expect_error(lambda: download.probe("https://youtube.com/playlist?list=x", "youtube", cfg()),
                     "not a single video")


def run_images(responses, n=3, **cfg_kw):
    urls = [f"https://cdn/{i}-big.jpg" for i in range(1, n + 1)]
    calls = []
    with tempfile.TemporaryDirectory() as d, _run.patched(download, "http_get", fake_get(responses, calls)):
        paths = download.download_images(urls, Path(d), cfg(**cfg_kw))
        return paths, calls, [p.read_bytes() for p in paths]


def test_download_images_writes_resized_jpegs_in_order():
    import io
    from PIL import Image
    big = jpeg_bytes((3000, 1500))
    r = {f"https://cdn/{i}-big.jpg": FakeResponse(200, big if i == 1 else jpeg_bytes(fmt="PNG"))
         for i in (1, 2, 3)}
    paths, calls, data = run_images(r)
    assert [p.name for p in paths] == ["slide-01.jpg", "slide-02.jpg", "slide-03.jpg"]
    assert all(t == 20 for _, t in calls)
    im = Image.open(io.BytesIO(data[0]))
    assert im.format == "JPEG" and max(im.size) == 1024
    assert Image.open(io.BytesIO(data[1])).format == "JPEG"


def test_download_images_caps_at_max_slides():
    r = {f"https://cdn/{i}-big.jpg": FakeResponse(200, jpeg_bytes()) for i in range(1, 6)}
    paths, calls, _ = run_images(r, n=5, max_slides=2)
    assert len(paths) == 2 and len(calls) == 2


def test_download_images_errors():
    ok = FakeResponse(200, jpeg_bytes())
    import requests
    cases = [(FakeResponse(503), RuntimeError), (requests.Timeout("t"), RuntimeError),
             (requests.ConnectionError("c"), RuntimeError),
             (FakeResponse(404), ProcessingError), (FakeResponse(200, b"not an image"), ProcessingError)]
    for bad, exc in cases:
        r = {"https://cdn/1-big.jpg": ok, "https://cdn/2-big.jpg": bad}
        try:
            run_images(r, n=2)
        except Exception as e:
            assert type(e) is exc, (bad, e)
        else:
            raise AssertionError("expected error")


def test_download_images_leaves_no_partial_set():
    r = {"https://cdn/1-big.jpg": FakeResponse(200, jpeg_bytes()), "https://cdn/2-big.jpg": FakeResponse(404)}
    with tempfile.TemporaryDirectory() as d, _run.patched(download, "http_get", fake_get(r)):
        try:
            download.download_images(list(r), Path(d), cfg())
        except ProcessingError:
            pass
        assert not list(Path(d).iterdir())


def test_probe_duration_parsing():
    import subprocess
    from linkdigest import util

    def runner(out=None, rc=0, exc=None):
        def run(*a, **k):
            if exc:
                raise exc
            return subprocess.CompletedProcess(a, rc, stdout=out, stderr="")
        return run
    for fake, want in [(runner("12.5\n"), 12.5), (runner("N/A\n"), None), (runner("junk"), None),
                       (runner("", rc=1), None), (runner(exc=FileNotFoundError()), None),
                       (runner(exc=subprocess.TimeoutExpired("ffprobe", 1)), None)]:
        with _run.patched(util.subprocess, "run", fake):
            assert util.probe_duration(Path("x.mp4")) == want


def test_cli_probe_unknown_duration_and_posts():
    import io
    import contextlib
    from linkdigest import __main__ as cli
    buf = io.StringIO()
    F = fake_ydl(info={"title": "Reel", "formats": [{"url": "u"}]})
    with _run.patched(download, "new_ydl", F), contextlib.redirect_stdout(buf):
        assert cli.cmd_probe(cfg(), "https://www.instagram.com/reel/x/", False) == 0
    assert "duration=unknown" in buf.getvalue()

    r = {f"https://cdn/{i}-big.jpg": FakeResponse(200, jpeg_bytes()) for i in (1, 2, 3)}
    buf = io.StringIO()
    with tempfile.TemporaryDirectory() as d, _run.patched(download, "new_ydl", fake_ydl(info=ig_post_info(3))), \
            _run.patched(download, "http_get", fake_get(r)), contextlib.redirect_stdout(buf):
        assert cli.cmd_probe(cfg(work_dir=d), "https://www.instagram.com/p/x/", True) == 0
        assert not list(Path(d).glob("job-*"))
    out = buf.getvalue()
    assert "media=images slides=3" in out and "slides=3 bytes=" in out


def test_main_makes_streams_survive_emoji_on_cp1252():
    import io
    import sys
    from linkdigest import __main__ as cli
    raw = io.BytesIO()
    fake = io.TextIOWrapper(raw, encoding="cp1252")
    with _run.patched(sys, "stdout", fake), _run.patched(sys, "stderr", io.TextIOWrapper(io.BytesIO(), encoding="cp1252")):
        cli.main(["probe", "not a link"])
        print("title \U0001F600")
        sys.stdout.flush()
    assert b"title ?" in raw.getvalue()


if __name__ == "__main__":
    _run.main(globals())
