import contextlib
import logging
import re
import subprocess
import time

from .errors import ProcessingError

log = logging.getLogger("linkdigest")


def fmt_time(sec):
    s = int(sec)
    return f"{s // 60}:{s % 60:02d}"


def slug(text, n=40):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (s[:n].strip("-")) or "item"


def clip(text, n):
    return text if len(text) <= n else text[: n - 3].rstrip() + "..."


@contextlib.contextmanager
def timed(timings, name):
    t0 = time.monotonic()
    try:
        yield
    finally:
        timings[name] = time.monotonic() - t0
        log.info("step %s took %.1fs", name, timings[name])


def run_ffmpeg(args):
    try:
        subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True,
                       capture_output=True, text=True, timeout=600)
    except FileNotFoundError:
        raise ProcessingError("ffmpeg is not installed. Install it with your package manager.") from None
    except subprocess.CalledProcessError as e:
        raise RuntimeError("ffmpeg failed: " + (e.stderr or "").strip()[-200:]) from None


def probe_duration(path):
    """Length of a media file in seconds from ffprobe, or None when it cannot be read. Never raises."""
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "csv=p=0", str(path)], capture_output=True, text=True, timeout=60)
        return float(r.stdout.strip()) if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
