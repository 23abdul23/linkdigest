import tempfile
from pathlib import Path

import _run
from fixtures import ROLLING_VTT, fake_ydl, make_video
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


if __name__ == "__main__":
    _run.main(globals())
