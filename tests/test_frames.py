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


def test_frame_label_defaults_to_empty_string():
    assert Frame(1.0, b"x", 5).label == ""
    assert Frame(1.0, b"x", 5, "Slide 1 of 2").label == "Slide 1 of 2"


if __name__ == "__main__":
    _run.main(globals())
