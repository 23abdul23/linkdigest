import sys
import tempfile
import wave
from pathlib import Path
from types import SimpleNamespace

import _run
from fixtures import ROLLING_EXPECTED, ROLLING_VTT, make_video
from linkdigest import transcript
from linkdigest.config import Config
from linkdigest.errors import ProcessingError


def test_rolling_vtt_yields_each_line_once_with_start_seconds():
    assert transcript.parse_vtt(ROLLING_VTT) == ROLLING_EXPECTED


def test_vtt_cue_with_blank_space_first_line_stays_intact():
    vtt = ("WEBVTT\n\n"
           "00:00:00.160 --> 00:00:02.230 align:start position:0%\n \n"
           "hello everyone today<00:00:01.000><c> is</c>\n\n"
           "00:00:02.230 --> 00:00:02.240 align:start position:0%\n"
           "hello everyone today is\n \n\n"
           "00:00:02.240 --> 00:00:04.000 align:start position:0%\n"
           "hello everyone today is\nnext line\n\n"
           "00:00:09.500 --> 00:00:10.000 align:start position:0%\n \n"
           "last words\n")
    assert transcript.parse_vtt(vtt) == [(0.16, "hello everyone today is"), (2.24, "next line"),
                                         (9.5, "last words")]
    assert transcript.parse_vtt(ROLLING_VTT) == ROLLING_EXPECTED


def test_vtt_edge_cases():
    assert transcript.parse_vtt("") == []
    assert transcript.parse_vtt("WEBVTT\n\nNOTE just a note\n") == []
    crlf = "WEBVTT\r\n\r\n01:00:05.500 --> 01:00:07.000\r\n&gt;&gt; fish &amp; chips\r\n\r\n"
    assert transcript.parse_vtt(crlf) == [(3605.5, ">> fish & chips")]


def test_no_audio_track_gives_empty_transcript_and_banner():
    with tempfile.TemporaryDirectory() as d:
        video = make_video(d)
        banners = []
        t = transcript.transcribe_audio(video, Path(d), Config(), banners)
    assert t.lines == [] and t.source == "none"
    assert any("audio" in b for b in banners)


def test_missing_faster_whisper_gives_clear_error():
    old = sys.modules.get("faster_whisper", "MISSING")
    sys.modules["faster_whisper"] = None            # makes `import faster_whisper` raise ImportError
    transcript._models.clear()
    try:
        transcript._get_model("base")
    except ProcessingError as e:
        assert "faster-whisper" in str(e) and "pip install" in str(e)
    else:
        raise AssertionError("expected ProcessingError")
    finally:
        if old == "MISSING":
            del sys.modules["faster_whisper"]
        else:
            sys.modules["faster_whisper"] = old


def _silent_wav(path, seconds=1):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 16000 * seconds)


class FakeModel:
    def __init__(self, lang):
        self.lang = lang

    def transcribe(self, audio, **kw):
        assert kw["beam_size"] == 1 and kw["vad_filter"] is True and kw["task"] == "transcribe"
        segs = [SimpleNamespace(start=1.5, text=" namaste doston "), SimpleNamespace(start=4.0, text="  ")]
        return segs, SimpleNamespace(language=self.lang, language_probability=0.91)


def test_whisper_path_with_fake_model_and_language_banner():
    try:
        import numpy  # noqa: F401
    except ImportError:
        print("skip: numpy not installed (pip install -r requirements-whisper.txt)")
        return
    with tempfile.TemporaryDirectory() as d:
        wav = Path(d) / "in.wav"
        _silent_wav(wav)
        banners = []
        with _run.patched(transcript, "_get_model", lambda name: FakeModel("hi")):
            t = transcript.transcribe_audio(wav, Path(d), Config(), banners)
    assert t.lines == [(1.5, "namaste doston")] and t.source == "whisper" and t.language == "hi"
    assert any("hi" in b and "non-English" in b for b in banners)


if __name__ == "__main__":
    _run.main(globals())
