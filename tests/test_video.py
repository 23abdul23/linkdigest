import tempfile
from pathlib import Path

import _run
from fixtures import ROLLING_VTT, FakeResponse, fake_get, fake_ydl, ig_post_info, jpeg_bytes, make_video
from linkdigest import download, video_proc
from linkdigest.config import Config
from linkdigest.errors import ProcessingError, Skipped


def _fake(d, **extra):
    data = make_video(d).read_bytes()
    attrs = dict(info={"title": "A talk", "duration": 90, "is_live": False},
                 video_bytes=lambda self: data, vtt_text=lambda self: ROLLING_VTT)
    attrs.update(extra)
    return fake_ydl(**attrs)


def test_captioned_video_end_to_end_and_temp_cleanup():
    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as w:
        F = _fake(d)
        with _run.patched(download, "new_ydl", F):
            b = video_proc.process_video("https://youtu.be/abc", "youtube", Config(work_dir=w))
        assert not list(Path(w).glob("job-*")), "temp dir must be deleted"
    assert b.title == "A talk" and b.duration == 90
    assert b.transcript.source == "captions" and b.transcript.lines[0] == (1.0, "hello and welcome to the")
    assert b.sampled == 6 and 2 <= len(b.frames) < b.sampled
    assert {"probe", "download", "transcript", "frames"} <= set(b.timings)


def test_long_video_is_skipped_after_probe_only():
    F = fake_ydl(info={"title": "Long", "duration": 900, "is_live": False})
    with _run.patched(download, "new_ydl", F):
        try:
            video_proc.process_video("https://youtu.be/abc", "youtube", Config())
        except Skipped as e:
            assert str(e) == "Video is 15:00, over the 5:00 limit."
        else:
            raise AssertionError("expected Skipped")
    assert [c[0] for c in F.calls] == ["probe"], "nothing may be downloaded"


def test_long_video_process_mode_adds_banner():
    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as w:
        F = _fake(d, info={"title": "Long", "duration": 900, "is_live": False})
        with _run.patched(download, "new_ydl", F):
            b = video_proc.process_video("https://youtu.be/abc", "youtube",
                                         Config(work_dir=w, long_video_action="process"))
    assert any("15:00" in x for x in b.banners)


def test_silent_video_without_captions_still_gives_frames_and_a_banner():
    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as w:
        F = _fake(d, write_vtt=False, info={"title": "Reel", "duration": 30, "is_live": False,
                                            "formats": [{"format_id": "v"}]})
        with _run.patched(download, "new_ydl", F):
            b = video_proc.process_video("https://www.instagram.com/reel/x/", "instagram", Config(work_dir=w))
    assert b.transcript.source == "none" and b.transcript.lines == []
    assert len(b.frames) >= 2 and any("audio" in x for x in b.banners)


def test_temp_dir_removed_when_download_fails():
    with tempfile.TemporaryDirectory() as w:
        F = fake_ydl(download_errors=["ERROR: Private video"])
        with _run.patched(download, "new_ydl", F):
            try:
                video_proc.process_video("https://youtu.be/abc", "youtube", Config(work_dir=w))
            except ProcessingError:
                pass
            else:
                raise AssertionError("expected ProcessingError")
        assert not list(Path(w).glob("job-*"))


def _unknown(d, **extra):
    return _fake(d, info={"title": "Reel", "duration": None, "is_live": False, "formats": [{"format_id": "v"}]}, **extra)


def test_unknown_duration_over_limit_skips_after_download_and_cleans_up():
    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as w:
        F = _unknown(d)
        with _run.patched(download, "new_ydl", F), _run.patched(video_proc, "probe_duration", lambda p: 900.4):
            try:
                video_proc.process_video("https://www.instagram.com/reel/x/", "instagram", Config(work_dir=w))
            except Skipped as e:
                assert str(e) == "Video is 15:00, over the 5:00 limit."
            else:
                raise AssertionError("expected Skipped")
        assert [c[0] for c in F.calls] == ["probe", "download"]
        assert not list(Path(w).glob("job-*"))


def test_unknown_duration_over_limit_process_mode_banners_and_keeps_measured_duration():
    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as w:
        F = _unknown(d)
        with _run.patched(download, "new_ydl", F), _run.patched(video_proc, "probe_duration", lambda p: 900.4):
            b = video_proc.process_video("https://www.instagram.com/reel/x/", "instagram",
                                         Config(work_dir=w, long_video_action="process"))
    assert b.duration == 900 and any("15:00" in x for x in b.banners)


def test_unknown_duration_under_limit_proceeds_with_measured_duration():
    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as w:
        F = _unknown(d)
        with _run.patched(download, "new_ydl", F), _run.patched(video_proc, "probe_duration", lambda p: 12.0):
            b = video_proc.process_video("https://www.instagram.com/reel/x/", "instagram", Config(work_dir=w))
    assert b.duration == 12 and b.media == "video" and not any("limit" in x for x in b.banners)


def test_unmeasurable_duration_proceeds_with_zero():
    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as w:
        F = _unknown(d)
        with _run.patched(download, "new_ydl", F), _run.patched(video_proc, "probe_duration", lambda p: None):
            b = video_proc.process_video("https://www.instagram.com/reel/x/", "instagram", Config(work_dir=w))
    assert b.duration == 0 and len(b.frames) >= 2


def _post_http(n):
    return fake_get({f"https://cdn/{i}-big.jpg": FakeResponse(200, jpeg_bytes()) for i in range(1, n + 1)})


def test_image_post_gives_labelled_slides_no_audio_banner_and_cleanup():
    IG = "https://www.instagram.com/p/x/"
    with tempfile.TemporaryDirectory() as w:
        F = fake_ydl(info=ig_post_info(3))
        with _run.patched(download, "new_ydl", F), _run.patched(download, "http_get", _post_http(3)):
            b = video_proc.process_video(IG, "instagram", Config(work_dir=w))
        assert not list(Path(w).glob("job-*")), "temp dir must be deleted"
    assert b.media == "images" and b.duration == 0 and b.sampled == 3
    assert b.transcript.source == "none" and b.transcript.lines == [] and b.transcript.language is None
    assert [f.label for f in b.frames] == ["Slide 1 of 3", "Slide 2 of 3", "Slide 3 of 3"]
    assert [f.t for f in b.frames] == [0, 1, 2] and all(f.hash == 0 for f in b.frames)
    assert all(f.jpeg[:2] == b"\xff\xd8" for f in b.frames)
    assert b.banners == [] and {"probe", "download"} <= set(b.timings)
    assert [c[0] for c in F.calls] == ["probe"], "images are fetched over http, not yt-dlp"


def test_image_post_over_the_cap_gets_a_banner():
    with tempfile.TemporaryDirectory() as w:
        with _run.patched(download, "new_ydl", fake_ydl(info=ig_post_info(4))), \
                _run.patched(download, "http_get", _post_http(4)):
            b = video_proc.process_video("https://www.instagram.com/p/x/", "instagram",
                                         Config(work_dir=w, max_slides=2))
    assert len(b.frames) == 2 and b.sampled == 2
    assert [f.label for f in b.frames] == ["Slide 1 of 2", "Slide 2 of 2"]
    assert b.banners == ["Post has 4 slides; the first 2 were analysed."]


def test_image_post_download_failure_cleans_up():
    with tempfile.TemporaryDirectory() as w:
        r = {"https://cdn/1-big.jpg": FakeResponse(404)}
        with _run.patched(download, "new_ydl", fake_ydl(info=ig_post_info(1))), \
                _run.patched(download, "http_get", fake_get(r)):
            try:
                video_proc.process_video("https://www.instagram.com/p/x/", "instagram", Config(work_dir=w))
            except ProcessingError:
                pass
            else:
                raise AssertionError("expected ProcessingError")
        assert not list(Path(w).glob("job-*"))


def test_cmd_extract_on_a_post_saves_slides_and_no_transcript():
    import contextlib
    import io
    from linkdigest import __main__ as cli
    buf = io.StringIO()
    with tempfile.TemporaryDirectory() as w, tempfile.TemporaryDirectory() as o, \
            _run.patched(download, "new_ydl", fake_ydl(info=ig_post_info(3))), \
            _run.patched(download, "http_get", _post_http(3)), contextlib.redirect_stdout(buf):
        assert cli.cmd_extract(Config(work_dir=w, out_dir=o), "https://www.instagram.com/p/x/") == 0
        folder = next(Path(o).glob("extract-*"))
        names = sorted(p.name for p in folder.iterdir())
    assert names == ["slide-01.jpg", "slide-02.jpg", "slide-03.jpg"]
    out = buf.getvalue()
    assert "media=images slides=3" in out and "timings" in out and "transcript source" not in out


def test_cmd_extract_prints_banners_for_a_capped_post():
    import contextlib
    import io
    from linkdigest import __main__ as cli
    buf = io.StringIO()
    with tempfile.TemporaryDirectory() as w, tempfile.TemporaryDirectory() as o, \
            _run.patched(download, "new_ydl", fake_ydl(info=ig_post_info(3))), \
            _run.patched(download, "http_get", _post_http(3)), contextlib.redirect_stdout(buf):
        cli.cmd_extract(Config(work_dir=w, out_dir=o, max_slides=2), "https://www.instagram.com/p/x/")
    assert "banner: Post has 3 slides; the first 2 were analysed." in buf.getvalue()


if __name__ == "__main__":
    _run.main(globals())
