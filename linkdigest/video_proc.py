import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .download import download, download_images, probe
from .errors import ProcessingError, Skipped
from .frames import Frame, extract_frames
from .transcript import Transcript, parse_vtt, transcribe_audio
from .util import fmt_time, log, probe_duration, timed


@dataclass
class VideoBundle:
    title: str
    duration: int
    transcript: Transcript
    frames: list
    sampled: int
    banners: list = field(default_factory=list)
    timings: dict = field(default_factory=dict)
    media: str = "video"


def _apply_limit(seconds, cfg, banners):
    """Skipped when over the limit under LONG_VIDEO_ACTION=skip, else a banner."""
    if seconds <= cfg.max_video_seconds:
        return
    msg = f"Video is {fmt_time(seconds)}, over the {fmt_time(cfg.max_video_seconds)} limit."
    if cfg.long_video_action == "skip":
        raise Skipped(msg)
    banners.append(msg + " Processed anyway; the summary may be shallow.")


def _process_images(pr, cfg, timings):
    """An Instagram image post: the images become labelled slides, with no transcript."""
    banners = []
    cfg.work_path.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="job-", dir=cfg.work_path))
    try:
        with timed(timings, "download"):
            paths = download_images(pr.image_urls, tmp, cfg)
        n = len(paths)
        frames = [Frame(k - 1, p.read_bytes(), 0, f"Slide {k} of {n}") for k, p in enumerate(paths, 1)]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if len(pr.image_urls) > n:
        banners.append(f"Post has {len(pr.image_urls)} slides; the first {n} were analysed.")
    return VideoBundle(pr.title, 0, Transcript([], "none", None), frames, n, banners, timings, "images")


def process_video(url, kind, cfg):
    timings, banners = {}, []
    with timed(timings, "probe"):
        pr = probe(url, kind, cfg)
    if pr.media == "images":
        return _process_images(pr, cfg, timings)
    duration = pr.duration
    if duration is not None:
        _apply_limit(duration, cfg, banners)        # known length: refuse before downloading anything
    cfg.work_path.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="job-", dir=cfg.work_path))
    try:
        with timed(timings, "download"):
            dl = download(url, kind, tmp, cfg)
        if duration is None:                        # unknown length: measure the file, then apply the limit
            measured = probe_duration(dl.video)
            if measured is None:
                log.warning("could not measure the video length; continuing (the frame cap bounds the cost)")
            else:
                duration = int(measured)
                _apply_limit(duration, cfg, banners)
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
    return VideoBundle(pr.title, duration or 0, tr, frames, sampled, banners, timings)
