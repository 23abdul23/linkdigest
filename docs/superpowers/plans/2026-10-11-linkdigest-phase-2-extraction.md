# linkdigest Phase 2: Extraction (transcript and frames)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Read the index `2026-10-11-linkdigest.md` first. Phase 1 must be tagged `gate-1`. Steps use checkbox syntax.

**Goal of this phase:** `python -m linkdigest extract URL` downloads a real video, produces the transcript (captions first, faster-whisper if none) and the deduped frames, and saves them to `out/extract-<title>/` so a human can look at them. No LLM yet. After this phase you know, on real YouTube and Instagram videos, exactly what the model will be fed.

**Spec:** handoff "Processing: video" steps 3 to 5, `research.md` Transcription and Frames sections and deviations 7 and 8.

## Interfaces defined in this phase

```python
# transcript.py
Transcript(lines: list[tuple[float, str]], source: str, language: str | None)   # source: "captions" | "whisper" | "none"
parse_vtt(text: str) -> list[tuple[float, str]]
_get_model(name: str)                                  # cached faster-whisper model; ProcessingError if not installed
transcribe_audio(video: Path, tmp: Path, cfg, banners: list[str]) -> Transcript

# frames.py
Frame(t: float, jpeg: bytes, hash: int)
dhash(img: PIL.Image.Image) -> int
hamming(a: int, b: int) -> int
thin(frames: list[Frame], n: int) -> list[Frame]
extract_frames(video: Path, outdir: Path, cfg) -> tuple[list[Frame], int]   # (kept, sampled)

# video_proc.py
VideoBundle(title: str, duration: int, transcript: Transcript, frames: list[Frame],
            sampled: int, banners: list[str], timings: dict)
process_video(url: str, kind: str, cfg) -> VideoBundle      # raises Skipped for long videos
```

---

### Task 5: transcript.py (VTT parser and Whisper)

**Files:**
- Create: `linkdigest/transcript.py`
- Modify: `tests/fixtures.py` (add `ROLLING_VTT`, `make_video`)
- Test: `tests/test_transcript.py`

**Interfaces:**
- Consumes: `run_ffmpeg`, `ProcessingError`, `log`, `Config.whisper_model`.
- Produces: `Transcript`, `parse_vtt`, `_get_model`, `transcribe_audio`.

- [ ] **Step 1: Append to `tests/fixtures.py`**

```python
import random
import subprocess  # noqa: F401
import tempfile  # noqa: F401

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
```

- [ ] **Step 2: Write the failing tests** `tests/test_transcript.py`

```python
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
```

- [ ] **Step 3: Run to verify failure**

Run: `python tests/test_transcript.py`
Expected: `ModuleNotFoundError: No module named 'linkdigest.transcript'`.

- [ ] **Step 4: Write `linkdigest/transcript.py`**

```python
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
```

- [ ] **Step 5: Run all tests**

Run: `python tests/run_all.py`
Expected: all `ok` (the fake-Whisper test prints `skip` until numpy is installed), `PASS`.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: VTT parser and faster-whisper transcription"
```

---

### Task 6: frames.py (sampling, dHash, dedupe)

**Files:**
- Create: `linkdigest/frames.py`
- Test: `tests/test_frames.py`

**Interfaces:**
- Consumes: `run_ffmpeg`, `Config.frame_interval_seconds/max_frames/frame_hash_distance`, `fixtures.make_video`.
- Produces: `Frame`, `dhash`, `hamming`, `thin`, `extract_frames`.

- [ ] **Step 1: Write the failing tests** `tests/test_frames.py`

```python
import io
import tempfile
from pathlib import Path

import _run
from fixtures import make_video
from linkdigest import frames
from linkdigest.config import Config
from linkdigest.frames import Frame, hamming, thin


def test_three_scene_video_keeps_one_frame_per_scene():
    with tempfile.TemporaryDirectory() as d:
        video = make_video(d)                                   # 3 scenes x 4 s, sampled every 2 s = 6
        kept, sampled = frames.extract_frames(video, Path(d) / "f", Config(frame_interval_seconds=2))
    assert sampled == 6
    assert 2 <= len(kept) < sampled, (len(kept), sampled)
    assert len(kept) == 3
    ts = [f.t for f in kept]
    assert ts == sorted(ts) and ts[0] == 0.0
    assert all(f.jpeg[:2] == b"\xff\xd8" for f in kept)


def test_identical_images_have_zero_distance_and_different_ones_do_not():
    from PIL import Image
    import random
    def img(seed):
        r = random.Random(seed)
        im = Image.new("L", (9, 8))
        im.putdata([r.randint(0, 255) for _ in range(72)])
        return im
    assert hamming(frames.dhash(img(1)), frames.dhash(img(1))) == 0
    assert hamming(frames.dhash(img(1)), frames.dhash(img(2))) > 10


def test_thin_drops_the_frame_most_similar_to_another():
    a, b, c = Frame(0, b"", 0), Frame(2, b"", 1), Frame(4, b"", (1 << 64) - 1)
    kept = thin([a, b, c], 2)
    assert len(kept) == 2 and c in kept and a not in kept


def test_cap_is_enforced():
    fs = [Frame(i, b"", (1 << i) - 1) for i in range(1, 30)]     # 29 frames, each differs from the last
    assert len(thin(fs, 12)) == 12


def test_static_video_falls_back_to_three_evenly_spaced_frames():
    with tempfile.TemporaryDirectory() as d:
        video = make_video(d, seeds=(1,), seconds=8)            # one still for 8 s = 4 sampled, 1 unique
        kept, sampled = frames.extract_frames(video, Path(d) / "f", Config())
    assert sampled == 4 and len(kept) == 3
    assert kept[0].t == 0.0 and kept[-1].t == 6.0


if __name__ == "__main__":
    _run.main(globals())
```

- [ ] **Step 2: Run to verify failure**

Run: `python tests/test_frames.py`
Expected: `ModuleNotFoundError: No module named 'linkdigest.frames'`.

- [ ] **Step 3: Write `linkdigest/frames.py`**

```python
import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from .util import run_ffmpeg


@dataclass
class Frame:
    t: float
    jpeg: bytes
    hash: int


def dhash(img):
    """64-bit difference hash: compare each pixel with its right neighbour on a 9x8 grayscale grid."""
    g = img.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    px = list(g.get_flattened_data()) if hasattr(g, "get_flattened_data") else list(g.getdata())
    bits = 0
    for r in range(8):
        for c in range(8):
            bits = (bits << 1) | (px[r * 9 + c] > px[r * 9 + c + 1])
    return bits


def hamming(a, b):
    return bin(a ^ b).count("1")


def thin(frames, n):
    """Reduce to n frames by repeatedly dropping the frame most similar to another kept frame."""
    kept = list(frames)
    while len(kept) > n:
        worst = min(range(len(kept)),
                    key=lambda i: min(hamming(kept[i].hash, o.hash) for j, o in enumerate(kept) if j != i))
        del kept[worst]
    return kept


def _evenly(frames, k):
    idx = sorted({round(i * (len(frames) - 1) / (k - 1)) for i in range(k)})
    return [frames[i] for i in idx]


def extract_frames(video, outdir, cfg):
    """Sample every FRAME_INTERVAL_SECONDS at 512px wide, keep frames whose dHash differs from every
    kept frame by more than FRAME_HASH_DISTANCE, then thin to MAX_FRAMES. Returns (kept, sampled)."""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(["-i", str(video), "-vf", f"fps={1 / cfg.frame_interval_seconds:.6f},scale=512:-2",
                "-q:v", "4", "-an", str(outdir / "f_%04d.jpg")])
    every = []
    for i, p in enumerate(sorted(outdir.glob("f_*.jpg"))):
        data = p.read_bytes()
        with Image.open(io.BytesIO(data)) as im:
            every.append(Frame(i * cfg.frame_interval_seconds, data, dhash(im)))
    kept = []
    for f in every:
        if all(hamming(f.hash, k.hash) > cfg.frame_hash_distance for k in kept):
            kept.append(f)
    kept = thin(kept, cfg.max_frames)
    if len(kept) < 3 and len(every) >= 3:           # talking head: dHash keeps 1 or 2, give the model 3
        kept = _evenly(every, 3)
    return sorted(kept, key=lambda f: f.t), len(every)
```

- [ ] **Step 4: Run all tests**

Run: `python tests/run_all.py`
Expected: all `ok`, `PASS`. If `test_three_scene_video...` reports a kept count other than 3, print the pairwise distances of the six sampled hashes before changing anything: a scene-boundary frame landing on the wrong scene means the fixture timing, not the code, needs adjusting (use `seconds=5` and `frame_interval_seconds=2`).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: ffmpeg frame sampling with Pillow dHash dedupe"
```

---

### Task 7: video_proc.py and the `extract` command

**Files:**
- Create: `linkdigest/video_proc.py`
- Modify: `linkdigest/__main__.py` (add `cmd_extract`, parser entry, dispatch)
- Test: `tests/test_video.py`

**Interfaces:**
- Consumes: `probe`, `download`, `parse_vtt`, `transcribe_audio`, `Transcript`, `extract_frames`, `Skipped`, `ProcessingError`, `timed`, `fmt_time`.
- Produces: `VideoBundle`, `process_video`, `cmd_extract`.

- [ ] **Step 1: Write the failing tests** `tests/test_video.py`

```python
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
        F = _fake(d, write_vtt=False)
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


if __name__ == "__main__":
    _run.main(globals())
```

- [ ] **Step 2: Run to verify failure**

Run: `python tests/test_video.py`
Expected: `ModuleNotFoundError: No module named 'linkdigest.video_proc'`.

- [ ] **Step 3: Write `linkdigest/video_proc.py`**

```python
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .download import download, probe
from .errors import ProcessingError, Skipped
from .frames import extract_frames
from .transcript import Transcript, parse_vtt, transcribe_audio
from .util import fmt_time, log, timed


@dataclass
class VideoBundle:
    title: str
    duration: int
    transcript: Transcript
    frames: list
    sampled: int
    banners: list = field(default_factory=list)
    timings: dict = field(default_factory=dict)


def process_video(url, kind, cfg):
    timings, banners = {}, []
    with timed(timings, "probe"):
        pr = probe(url, kind, cfg)
    if pr.duration > cfg.max_video_seconds:
        msg = f"Video is {fmt_time(pr.duration)}, over the {fmt_time(cfg.max_video_seconds)} limit."
        if cfg.long_video_action == "skip":
            raise Skipped(msg)
        banners.append(msg + " Processed anyway; the summary may be shallow.")
    cfg.work_path.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="job-", dir=cfg.work_path))
    try:
        with timed(timings, "download"):
            dl = download(url, kind, tmp, cfg)
        with timed(timings, "transcript"):
            tr = None
            if dl.vtt:
                lines = parse_vtt(dl.vtt.read_text(encoding="utf-8", errors="replace"))
                if lines:
                    tr = Transcript(lines, "captions", "en")
            if tr is None:
                tr = transcribe_audio(dl.video, tmp, cfg, banners)
        with timed(timings, "frames"):
            try:
                frames, sampled = extract_frames(dl.video, tmp / "frames", cfg)
            except RuntimeError as e:
                log.warning("frame extraction failed: %s", e)
                frames, sampled = [], 0
                banners.append("Frames could not be read from this video.")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if not frames and not tr.lines:
        raise ProcessingError("Nothing to analyse: the video has no transcript and no readable frames.")
    return VideoBundle(pr.title, pr.duration, tr, frames, sampled, banners, timings)
```

- [ ] **Step 4: Add `cmd_extract` to `linkdigest/__main__.py`**

Add imports at the top: `from .errors import Skipped`, `from .util import fmt_time, log, slug`, `from .video_proc import process_video` (keep existing imports). Add the function above `build_parser`:

```python
def cmd_extract(cfg, url):
    """Run the video half of the pipeline and save what the model would see, for a human to inspect."""
    link = normalize_url(url)
    if not link:
        print("Not a valid link.")
        return 1
    kind = classify(link)
    if kind == "web":
        print("extract is for video links; use the test command for web pages.")
        return 1
    try:
        b = process_video(link, kind, cfg)
    except Skipped as e:
        print(f"Skipped: {e}")
        return 0
    except Exception as e:
        print(f"{type(e).__name__}: {e}")
        return 1
    out = Path(cfg.out_dir) / f"extract-{slug(b.title)}"
    out.mkdir(parents=True, exist_ok=True)
    for f in b.frames:
        (out / f"frame-{int(f.t):04d}s.jpg").write_bytes(f.jpeg)
    (out / "transcript.txt").write_text(
        "\n".join(f"[{fmt_time(t)}] {s}" for t, s in b.transcript.lines), encoding="utf-8")
    print(f"title={b.title!r} duration={fmt_time(b.duration)}")
    print(f"transcript source={b.transcript.source} language={b.transcript.language} lines={len(b.transcript.lines)}")
    print(f"frames kept={len(b.frames)} of sampled={b.sampled} at {[fmt_time(f.t) for f in b.frames]}")
    print("timings " + " ".join(f"{k}={v:.1f}s" for k, v in b.timings.items()))
    for banner in b.banners:
        print("banner:", banner)
    print(f"saved to {out}")
    return 0
```

In `build_parser()` add after the probe parser:

```python
    e = sub.add_parser("extract", help="download a video and save its transcript and frames")
    e.add_argument("url")
```

In `main()` add before `return 2`:

```python
    if args.cmd == "extract":
        return cmd_extract(cfg, args.url)
```

- [ ] **Step 5: Run all tests**

Run: `python tests/run_all.py`
Expected: all `ok`, `PASS`.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: video_proc and the extract command"
```

---

### Gate 2: transcript and frames are right on real videos

Stop and report. Do not start Phase 3 until the user says OK.

**Needs from the user:** approval to install `requirements-whisper.txt` (adds `faster-whisper`, `av<17`, numpy, ctranslate2, onnxruntime; about 280 MB; the base model downloads about 145 MB on first use). Same `.env` URLs as Gate 1.

- [ ] **Step 1: Install Whisper.** `pip install -r requirements-whisper.txt`. Then `python tests/run_all.py`; the fake-Whisper test must now run instead of printing `skip`. Expected `PASS`.

- [ ] **Step 2: YouTube with captions.**

```bash
python -m linkdigest extract "<TEST_YOUTUBE_URL>"
```

Expected: `transcript source=captions`, lines in the hundreds for a 4 to 5 min talk, `frames kept=N of sampled=S` with 2 <= N < S, no `banner:` for audio. Open the files in `out/extract-<title>/`: read `transcript.txt` (no line should repeat the previous one, which is the rolling-caption check) and look at the frame images (each should show a distinct slide or scene, none blank, no near-duplicates side by side). FAIL otherwise.

- [ ] **Step 3: YouTube without captions (Whisper).**

```bash
python -m linkdigest extract "<TEST_YOUTUBE_NOCAPS_URL>"
```

Expected: `transcript source=whisper language=en`, a `timings transcript=<s>` value. Record that number: research measured 12 s of transcription plus about 1.5 s audio extraction for a 4.5 min clip on this machine (Windows, 4 threads). Report the real figure. Read `transcript.txt` and judge accuracy.

- [ ] **Step 4: Instagram reels.** For each reel that downloaded at Gate 1:

```bash
python -m linkdigest extract "<reel url>"
```

Expected: `transcript source=whisper` (reels have no captions) or `source=none` plus the audio banner for a silent reel, and frames. Reels that were blocked at Gate 1 print `Blocked: ...`; that is an acceptable result and goes in the report.

- [ ] **Step 5: Non-English check (Review Focus 4).** If the user has a Hindi or Hinglish link, run `extract` on it. Expected: `language=hi` (or `en`) and a `banner: Detected spoken language ...` line when not English. Report how readable the transcript is. If no such link, say so in the report.

- [ ] **Step 6: Frame cap on a busy video.** Pick any 4 to 5 min screen-recording or fast-cut video, run `extract`, and report kept vs sampled. If the kept count equals `MAX_FRAMES` and the frames look like near-duplicates, note it for the user: this is the known cap risk from `research.md`, tunable through `FRAME_HASH_DISTANCE` and `MAX_FRAMES`.

- [ ] **Step 7: Review.** Dispatch a fresh reviewer on the Phase 2 diff. Brief: "Check parse_vtt against YouTube rolling captions beyond the fixture, dHash and thinning logic, temp-dir cleanup on every exit path, behaviour on videos without audio or without video stream, memory use of holding frames as bytes. Report only real defects." Apply real findings, add a test for each fix, rerun `python tests/run_all.py`.

- [ ] **Step 8: Tag and report.**

```bash
git add -A
git commit -m "test: phase 2 review fixes"
git tag gate-2
```

Report: offline results, per-link table (type, transcript source, language, line count, kept/sampled, timings), the measured Whisper time, a note on what the saved frames looked like, review result. Ask for the OK to start Phase 3.
