import html
import re
import wave
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from .errors import ProcessingError
from .util import log, run_ffmpeg

_TS = re.compile(r"^(?:(\d+):)?(\d{2}):(\d{2})[.,](\d{3})\s+-->")
_models = {}


@dataclass
class Transcript:
    lines: list
    source: str
    language: "str | None"


def parse_vtt(text):
    """Parse WebVTT into [(start_seconds, text)]. YouTube auto captions roll: each cue repeats the
    previous line, so a line already seen in the last 4 cues is dropped."""
    out = []
    recent = deque(maxlen=4)
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n")):
        lines = block.strip().split("\n")
        for i, line in enumerate(lines):
            m = _TS.match(line.strip())
            if m:
                break
        else:
            continue
        h, mi, s, ms = m.groups()
        start = int(h or 0) * 3600 + int(mi) * 60 + int(s) + int(ms) / 1000
        cue = []
        for raw in lines[i + 1:]:
            clean = html.unescape(re.sub(r"<[^>]+>", "", raw)).strip()
            if clean:
                cue.append(clean)
        new = [c for c in cue if not any(c in prev for prev in recent)]
        recent.append(set(cue))
        if new:
            out.append((start, " ".join(new)))
    return out


def _get_model(name):
    if name not in _models:
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            raise ProcessingError("This video has no captions and faster-whisper is not installed. "
                                  "Run pip install -r requirements-whisper.txt.") from None
        log.info("loading whisper model %s (first run downloads it)", name)
        _models[name] = WhisperModel(name, device="cpu", compute_type="int8")
    return _models[name]


def _load_wav(path):
    import numpy as np
    with wave.open(str(path)) as w:
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def transcribe_audio(video, tmp, cfg, banners):
    wav = Path(tmp) / "audio.wav"
    try:
        run_ffmpeg(["-i", str(video), "-vn", "-ac", "1", "-ar", "16000", str(wav)])
        no_audio = not wav.exists() or wav.stat().st_size <= 44        # 44 bytes is an empty WAV header
    except RuntimeError:
        no_audio = True
    if no_audio:
        banners.append("The video has no readable audio track, so there is no transcript.")
        return Transcript([], "none", None)
    model = _get_model(cfg.whisper_model)
    # Decode with the stdlib and pass an array: faster-whisper's own decoder breaks with newer PyAV.
    segments, info = model.transcribe(_load_wav(wav), beam_size=1, vad_filter=True, task="transcribe")
    lines = [(float(s.start), s.text.strip()) for s in segments if s.text.strip()]
    lang = info.language
    log.info("whisper language=%s probability=%.2f lines=%d", lang, info.language_probability, len(lines))
    if lang and lang != "en":
        banners.append(f"Detected spoken language: {lang}. The {cfg.whisper_model} model is weak on "
                       "non-English speech, so treat the transcript with care.")
    if not lines:
        banners.append("No speech was detected.")
    return Transcript(lines, "whisper", lang)
