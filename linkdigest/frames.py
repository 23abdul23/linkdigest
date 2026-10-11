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
    label: str = ""


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
