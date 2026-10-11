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
    try:
        with _run.patched(download, "new_ydl", N):
            download.probe("https://youtu.be/abc", "youtube", cfg())
    except ProcessingError as e:
        assert "length" in str(e)
    else:
        raise AssertionError("expected ProcessingError")


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


if __name__ == "__main__":
    _run.main(globals())
